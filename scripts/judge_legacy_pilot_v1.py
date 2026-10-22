#!/usr/bin/env python3
"""Development check: rule-based judge vs the manual v1 pilot labels.

Run from the repo root:
    python scripts/judge_legacy_pilot_v1.py

Reads the legacy v1 rows and manual reviews in results/legacy/week5_pilot_v1_nonnested/
and writes pilot_v1_judge_vs_manual.csv there. The manual labels
(adopted_poison / phrasing_only / resisted) are copied unchanged into their own
columns; they are never rewritten as judge labels.

This is NOT a validation of the judge: its rules were written with these
answers visible. Week-6 human-judge agreement must use a fresh stratified
sample (docs/week6_judging_protocol.md).
"""
import csv
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.eval.answer_judge import CORRECT, POISON_ADOPTED, RUBRIC_VERSION, judge_answer  # noqa: E402

LEGACY = os.path.join(ROOT, "results", "legacy", "week5_pilot_v1_nonnested")
LEGACY_PILOT = os.path.join(ROOT, "data/processed/attack_sources/legacy/"
                                  "streamingqa_attack_pilot.pre_source_qa_id.jsonl")
PILOT = os.path.join(ROOT, "data/processed/attack_sources/streamingqa_attack_pilot.jsonl")
PAYLOADS = os.path.join(ROOT, "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl")
OUT = os.path.join(LEGACY, "pilot_v1_judge_vs_manual.csv")
# Which judge labels are consistent with each manual label.
CONSISTENT = {"adopted_poison": {POISON_ADOPTED}, "phrasing_only": {CORRECT},
              "resisted": {CORRECT, "OTHER_WRONG"}}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    # v1 rows use pilot_index (position in the v1 pilot file); map it to source_qa_id by query text.
    by_query = {r["query"]: r for r in read_jsonl(PILOT)}
    v1 = [by_query[r["query"]] for r in read_jsonl(LEGACY_PILOT)]
    claims = {p["source_qa_id"]: p["text"] for p in read_jsonl(PAYLOADS)}

    manual = []
    for name in ("pilot_harm_review.csv", "pilot_djokovic_review.csv"):
        for row in csv.DictReader(open(os.path.join(LEGACY, name), encoding="utf-8")):
            manual.append({**row, "manual_source": name})

    out = []
    for row in manual:
        rec = v1[int(row["pilot_index"])]
        claim = claims[rec["source_qa_id"]] if row["pool"].startswith("fabricated_fresh") else None
        j = judge_answer(rec["query"], rec["gold_answer"], claim, row["answer_attacked"])
        out.append({
            "pool": row["pool"], "experiment": row["experiment"],
            "source_qa_id": rec["source_qa_id"], "answer_attacked": row["answer_attacked"],
            "manual_label": row["manual_label"], "manual_source": row["manual_source"],
            "judge_label": j.label, "judge_reason": j.reason,
            "consistent": j.label in CONSISTENT.get(row["manual_label"], set()),
            "judge_rubric_version": RUBRIC_VERSION,
        })

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    n_ok = sum(r["consistent"] for r in out)
    print(f"{n_ok}/{len(out)} judge labels consistent with the manual label; "
          f"{sum(r['judge_label'] == 'NEEDS_REVIEW' for r in out)} flagged NEEDS_REVIEW")
    for r in out:
        if not r["consistent"]:
            print(f"  {r['pool']} {r['experiment']} {r['source_qa_id']}: manual {r['manual_label']} "
                  f"judge {r['judge_label']} ({r['judge_reason']}) {r['answer_attacked'][:60]!r}")
    print("saved:", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
