#!/usr/bin/env python3
"""Join attacked v2 pilot logs with the clean pilot logs and judge every answer.

Run from the repo root after the Kaggle run (logs in logs/pilot_attacks_v2_nested/):
    python scripts/postprocess_pilot_attacks.py

Writes:
    results/pilot_attack_rows.csv          one row per pool x system x question
    results/pilot_consistency_check.json   log integrity + negative-control checks (exit 1 on failure)
    results/pilot_judge_review.csv         NEEDS_REVIEW rows for a human (existing labels kept)

Everything is joined by source_qa_id, never by file position. The clean logs
(logs/pilot_attacks/clean__E*.jsonl) predate source_qa_id; each clean row is
mapped to its question by exact query text, which must match exactly one pilot
record. The clean logs are only read.

Answers are labelled by src/eval/answer_judge.py from the question, the primary
gold answer, the poison claim (fabricated_fresh payload text; None for
conditions that assert no false claim) and the generated answer.
"""
import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.attacks.pilot_protocol import (  # noqa: E402
    AUTHORITATIVE_PAYLOAD_PATH, PILOT_PATH, POOL_DIR, PROTOCOL_VERSION,
    load_authoritative_payloads, read_jsonl,
)
from src.eval.answer_judge import NEEDS_REVIEW, RUBRIC_VERSION, judge_answer  # noqa: E402
from src.eval.config_loader import model_revisions  # noqa: E402

LOG_DIR = os.path.join(ROOT, "logs", "pilot_attacks_v2_nested")
CLEAN_LOG = os.path.join(ROOT, "logs", "pilot_attacks", "clean__{exp}.jsonl")
OUT_CSV = os.path.join(ROOT, "results", "pilot_attack_rows.csv")
OUT_CHECK = os.path.join(ROOT, "results", "pilot_consistency_check.json")
REVIEW_CSV = os.path.join(ROOT, "results", "pilot_judge_review.csv")
EXPS = ["E1", "E2", "E3", "E4"]
METRICS = ["em", "f1", "recall_at_5", "ndcg_at_5", "fraction_top_5_violating",
           "valid_evidence_recall_at_5", "time_valid_answer_accuracy"]
# Conditions whose poison asserts a false claim the judge can detect.
CLAIM_CONDITIONS = {"fabricated_fresh"}
REVIEW_FIELDS = ["key", "pool", "experiment", "source_qa_id", "which", "question", "gold_answer",
                 "poison_claim", "generated_answer", "judge_reason", "human_label", "reviewer", "notes"]


def norm(s):
    return " ".join((s or "").split())


def main():
    global LOG_DIR, OUT_CSV, OUT_CHECK, REVIEW_CSV
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-dir", default=LOG_DIR)
    parser.add_argument("--results-dir", default=os.path.dirname(OUT_CSV))
    args = parser.parse_args()
    LOG_DIR = args.log_dir
    OUT_CSV, OUT_CHECK, REVIEW_CSV = (os.path.join(args.results_dir, os.path.basename(p))
                                      for p in (OUT_CSV, OUT_CHECK, REVIEW_CSV))

    pilot = {r["source_qa_id"]: r for r in read_jsonl(PILOT_PATH)}
    by_query = {r["query"]: qa for qa, r in pilot.items()}
    assert len(by_query) == len(pilot), "pilot queries are not unique"
    payloads = load_authoritative_payloads(AUTHORITATIVE_PAYLOAD_PATH)
    pins = model_revisions()
    problems = []

    clean = {}
    for exp in EXPS:
        for row in read_jsonl(CLEAN_LOG.format(exp=exp)):
            qa = by_query.get(row["query"])
            if qa is None or row["gold_answer"] != pilot[qa]["gold_answer"]:
                problems.append(f"clean {exp}: row {row['query'][:40]!r} matches no pilot record")
                continue
            if row.get("attack_condition") != "clean":
                problems.append(f"clean {exp} {qa}: attack_condition {row.get('attack_condition')!r}")
            clean[(exp, qa)] = row

    def judge(qa, claim, answer):
        r = pilot[qa]
        return judge_answer(r["query"], r["gold_answer"], claim, answer)

    def gold_in(row, qa):
        gold = {str(g) for g in pilot[qa]["gold_chunk_ids"]}
        return any(str(d) in gold for d in row["retrieved_doc_ids"])

    rows, hidden, review = [], {}, []
    for pool_path in sorted(glob.glob(os.path.join(POOL_DIR, "*_n*.jsonl"))):
        pool = os.path.basename(pool_path)[:-6]
        records = {r["source_qa_id"]: r for r in read_jsonl(pool_path)}
        for exp in EXPS:
            log_path = os.path.join(LOG_DIR, f"{pool}__{exp}.jsonl")
            if not os.path.exists(log_path):
                problems.append(f"missing log {os.path.relpath(log_path, ROOT)}")
                continue
            logs = read_jsonl(log_path)
            if len(logs) != len(records):
                problems.append(f"{pool} {exp}: {len(logs)} log rows vs {len(records)} records")
            for row in logs:
                qa = row.get("source_qa_id")
                rec = records.get(qa)
                tag = f"{pool} {exp} {qa}"
                if rec is None:
                    problems.append(f"{tag}: log row has no matching pool record"); continue
                meta = rec["attack_metadata"]
                if row.get("attack_condition") != rec["attack_condition"]:
                    problems.append(f"{tag}: logged condition {row.get('attack_condition')!r}")
                if row.get("poison_target_doc_ids") != meta["target_doc_ids"]:
                    problems.append(f"{tag}: logged poison doc_ids differ from the pool")
                if row["query"] != rec["query"] or row["gold_answer"] != rec["gold_answer"]:
                    problems.append(f"{tag}: query or gold differs from the pool")
                run_meta = row.get("run_metadata") or {}
                if run_meta.get("attack_protocol_version") != PROTOCOL_VERSION:
                    problems.append(f"{tag}: run_metadata missing or wrong protocol")
                for m in (run_meta.get("models") or {}).values():
                    if m.get("pinned_revision") != pins.get(m.get("name")):
                        problems.append(f"{tag}: {m.get('name')} not at the pinned revision")
                    if m.get("loaded_revision") not in (None, m.get("pinned_revision")):
                        problems.append(f"{tag}: {m.get('name')} loaded {m.get('loaded_revision')}")

                c = clean[(exp, qa)]
                claim = payloads[qa]["text"] if rec["attack_condition"] in CLAIM_CONDITIONS else None
                targets = meta["target_indices"]
                retrieved = row["retrieved_passage_indices"]
                ranks = [retrieved.index(t) + 1 if t in retrieved else None for t in targets]
                chosen = [r for r in ranks if r is not None]
                j_clean, j_att = judge(qa, claim, c["generated_answer"]), judge(qa, claim, row["generated_answer"])
                out = {
                    "pool": pool,
                    "condition": rec["attack_condition"],
                    "poison_count": len(targets),
                    "experiment": exp,
                    "source_qa_id": qa,
                    "poison_claim_applicable": claim is not None,
                    "poison_slots": ";".join(str(t) for t in targets),
                    "poison_ranks_top5": ";".join("NA" if r is None else str(r) for r in ranks),
                    "n_poison_selected": len(chosen),
                    "best_poison_rank": min(chosen) if chosen else "",
                    "gold_in_top5_clean": gold_in(c, qa),
                    "gold_in_top5_attacked": gold_in(row, qa),
                    "answer_clean": c["generated_answer"],
                    "answer_attacked": row["generated_answer"],
                    "answer_changed": norm(c["generated_answer"]) != norm(row["generated_answer"]),
                    "same_retrieved_as_clean": retrieved == c["retrieved_passage_indices"],
                    "same_prompt_as_clean": row["prompt"] == c["prompt"],
                    "judge_clean": j_clean.label,
                    "judge_clean_reason": j_clean.reason,
                    "judge_attacked": j_att.label,
                    "judge_attacked_reason": j_att.reason,
                    "judge_rubric_version": RUBRIC_VERSION,
                    "config_hash": run_meta.get("config_hash", ""),
                }
                for m in METRICS:
                    for tag_, src in (("clean", c), ("attacked", row)):
                        v = src.get(m)
                        out[f"{m}_{tag_}"] = "" if v is None else v
                rows.append(out)
                hidden[(pool, exp, qa)] = (retrieved, row["prompt"], norm(row["generated_answer"]))
                for which, j, ans in (("clean", j_clean, c["generated_answer"]),
                                      ("attacked", j_att, row["generated_answer"])):
                    if j.label == NEEDS_REVIEW:
                        review.append({"key": f"{pool}|{exp}|{qa}|{which}", "pool": pool,
                                       "experiment": exp, "source_qa_id": qa, "which": which,
                                       "question": pilot[qa]["query"],
                                       "gold_answer": pilot[qa]["gold_answer"],
                                       "poison_claim": claim or "", "generated_answer": ans,
                                       "judge_reason": j.reason})

    # Negative control: future_date must equal clean in retrieval, prompt and answer.
    bad_future = [f"{r['pool']} {r['experiment']} {r['source_qa_id']}" for r in rows
                  if r["condition"] == "future_date" and
                  (r["answer_changed"] or not r["same_retrieved_as_clean"] or not r["same_prompt_as_clean"])]
    # 30-day attack vs 0-day duplication control: same slots and content, so same outputs.
    bad_ctrl = []
    for r in rows:
        if r["condition"] == "correct_content_wrong_date_30d":
            ctrl = hidden.get((r["pool"].replace("30d", "0d_control"), r["experiment"], r["source_qa_id"]))
            if ctrl != hidden[(r["pool"], r["experiment"], r["source_qa_id"])]:
                bad_ctrl.append(f"{r['pool']} {r['experiment']} {r['source_qa_id']}")

    if rows:
        os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
        with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    # Keep any human labels already entered; add new NEEDS_REVIEW items.
    existing = {}
    if os.path.exists(REVIEW_CSV):
        existing = {r["key"]: r for r in csv.DictReader(open(REVIEW_CSV, encoding="utf-8", newline=""))}
    for item in review:
        old = existing.get(item["key"], {})
        item.update({k: old.get(k, "") for k in ("human_label", "reviewer", "notes")})
    with open(REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_FIELDS)
        w.writeheader()
        w.writerows(review)

    report = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "judge_rubric_version": RUBRIC_VERSION,
        "n_rows": len(rows),
        "expected_rows": 15 * 4 * 3,
        "log_problems": problems,
        "future_date_rows_differing_from_clean": bad_future,
        "ccwd_30d_vs_0d_control_mismatches": bad_ctrl,
        "n_needs_review": len(review),
        "note": ("future_date is metadata-only for E1-E4, so any difference from clean would be "
                 "run-to-run drift between the earlier clean session and this session. A 30d vs "
                 "0d difference is the only evidence that the wrong date itself had an effect."),
        "result": "FAILED" if problems or len(rows) != 180 else "OK",
    }
    with open(OUT_CHECK, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("rows written:", len(rows), "(expect 180)")
    print("log problems:", problems or "none")
    print("future_date rows differing from clean:", len(bad_future), bad_future)
    print("30d vs 0d control mismatches:", len(bad_ctrl), bad_ctrl)
    print("NEEDS_REVIEW judgements:", len(review), "->", os.path.relpath(REVIEW_CSV, ROOT))
    print("saved:", os.path.relpath(OUT_CSV, ROOT), os.path.relpath(OUT_CHECK, ROOT))
    sys.exit(1 if report["result"] != "OK" else 0)


if __name__ == "__main__":
    main()
