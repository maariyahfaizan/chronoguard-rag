#!/usr/bin/env python3
"""Vulnerability summary for the v2 pilot (supervisor item 10).

Run from the repo root after scripts/postprocess_pilot_attacks.py:
    python scripts/summarize_pilot_attacks.py

Reads results/pilot_attack_rows.csv, results/pilot_judge_review.csv (human
labels for NEEDS_REVIEW items) and the pool manifest. Writes
results/pilot_vulnerability_summary.csv: one row per condition x poison count
x system, with every quantity in its own column. There is no single headline
"answers changed / poison-selected" cell.

Undefined stays undefined: a quantity with an empty denominator, or a delta
with no question where both values are defined, is written as an empty cell
and never as 0. ASR and Conditional ASR are "not_applicable" for conditions
that assert no false claim, and empty while any judged answer in the cell is
still NEEDS_REVIEW without a human label.

n=3 is a development case study, not a statistical benchmark.
"""
import argparse
import csv
import json
import os
import statistics
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.attacks.pilot_protocol import CONDITIONS, NOT_BUILT, POISON_COUNTS, POOL_DIR, STALE_INELIGIBLE_REASON  # noqa: E402
from src.eval.answer_judge import CORRECT, LABELS, NEEDS_REVIEW, POISON_ADOPTED  # noqa: E402

SRC = os.path.join(ROOT, "results", "pilot_attack_rows.csv")
REVIEW = os.path.join(ROOT, "results", "pilot_judge_review.csv")
OUT = os.path.join(ROOT, "results", "pilot_vulnerability_summary.csv")
EXPS = ["E1", "E2", "E3", "E4"]
DELTAS = {"recall_at_5": "delta_recall_at_5", "ndcg_at_5": "delta_ndcg_at_5",
          "valid_evidence_recall_at_5": "delta_valid_evidence_recall_at_5",
          "time_valid_answer_accuracy": "delta_tvaa",
          "fraction_top_5_violating": "delta_fraction_top_5_violating"}


def num(x):
    return None if x in ("", None) else float(x)


def ratio(n, d):
    return "" if not d else round(n / d, 4)


def resolved(row, which, human):
    label = row[f"judge_{which}"]
    if label == NEEDS_REVIEW:
        label = human.get(f"{row['pool']}|{row['experiment']}|{row['source_qa_id']}|{which}", "")
        if label not in LABELS:
            return None
    return label


def main():
    global SRC, REVIEW, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default=os.path.dirname(OUT))
    args = parser.parse_args()
    SRC, REVIEW, OUT = (os.path.join(args.results_dir, os.path.basename(p)) for p in (SRC, REVIEW, OUT))

    rows = list(csv.DictReader(open(SRC, encoding="utf-8", newline="")))
    human = {}
    if os.path.exists(REVIEW):
        human = {r["key"]: r["human_label"].strip() for r in csv.DictReader(open(REVIEW, encoding="utf-8"))}
    manifest = json.load(open(os.path.join(POOL_DIR, "pilot_pools_manifest.json"), encoding="utf-8"))
    n_total = len({r["source_qa_id"] for r in rows}) or 3
    skipped = {(p["condition"], p["poison_count"]): len(p["skipped_ineligible"]) for p in manifest["pools"]}

    out = []
    for condition in [c["name"] for c in CONDITIONS]:
        for count in POISON_COUNTS:
            for exp in EXPS:
                base = {"condition": condition, "poison_count": count, "experiment": exp,
                        "n_questions_total": n_total}
                if condition in NOT_BUILT:
                    out.append({**base, "n_eligible_attacked": 0, "n_ineligible": n_total,
                                "ineligible_reason": STALE_INELIGIBLE_REASON})
                    continue
                rs = [r for r in rows if r["condition"] == condition
                      and int(r["poison_count"]) == count and r["experiment"] == exp]
                n = len(rs)
                applicable = all(r["poison_claim_applicable"] == "True" for r in rs) and n > 0
                selected = [r for r in rs if int(r["n_poison_selected"]) > 0]
                att = [resolved(r, "attacked", human) for r in rs]
                cln = [resolved(r, "clean", human) for r in rs]
                pending = sum(x is None for x in att + cln)
                adopted = sum(x == POISON_ADOPTED for x in att)
                adopted_sel = sum(resolved(r, "attacked", human) == POISON_ADOPTED for r in selected)
                ranks = [int(r["best_poison_rank"]) for r in selected]
                gold_clean = [r for r in rs if r["gold_in_top5_clean"] == "True"]

                o = {**base, "n_eligible_attacked": n,
                     "n_ineligible": skipped.get((condition, count), 0), "ineligible_reason": "",
                     "n_poison_selected_questions": len(selected),
                     "poison_selection_rate": ratio(len(selected), n),
                     "n_needs_review_unresolved": pending}
                if not applicable:
                    o["asr"] = o["conditional_asr"] = "not_applicable"
                elif pending:
                    o["asr"] = o["conditional_asr"] = ""
                else:
                    o["asr"] = ratio(adopted, n)
                    o["conditional_asr"] = ratio(adopted_sel, len(selected))
                o["n_poison_adopted"] = adopted if applicable and not pending else ""
                if pending:
                    o["correct_rate_clean"] = o["correct_rate_attacked"] = o["correctness_drop"] = ""
                else:
                    cc, ca = sum(x == CORRECT for x in cln) / n, sum(x == CORRECT for x in att) / n
                    o["correct_rate_clean"], o["correct_rate_attacked"] = round(cc, 4), round(ca, 4)
                    o["correctness_drop"] = round(cc - ca, 4)
                o["gold_displacement_rate"] = ratio(
                    sum(r["gold_in_top5_attacked"] == "False" for r in gold_clean), len(gold_clean))
                o["n_gold_in_top5_clean"] = len(gold_clean)
                o["mean_best_poison_rank"] = round(statistics.mean(ranks), 3) if ranks else ""
                o["median_best_poison_rank"] = statistics.median(ranks) if ranks else ""
                for metric, col in DELTAS.items():
                    pairs = [(num(r[f"{metric}_clean"]), num(r[f"{metric}_attacked"])) for r in rs]
                    pairs = [(c, a) for c, a in pairs if c is not None and a is not None]
                    o[f"{col}_n_defined"] = len(pairs)
                    o[col] = round(sum(a - c for c, a in pairs) / len(pairs), 4) if pairs else ""
                out.append(o)

    fields = []
    for o in out:
        fields += [k for k in o if k not in fields]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print("rows written:", len(out), "(expect 72; the 12 stale_evidence rows are ineligible)")
    print("saved:", os.path.relpath(OUT, ROOT))
    print("n=3 is a development case study, not a statistical benchmark.")


if __name__ == "__main__":
    main()
