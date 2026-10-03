#!/usr/bin/env python3
"""Draw the stratified sample for FreshQA judge validation (Gate B item 9).

Writes (in OUT_DIR):
    annotation.csv         YOU label this one. No judge verdicts, no system, no stratum.
    key.csv                Judge verdicts + system + stratum. DO NOT OPEN until you finish labelling.
    annotation_rater2.csv  Same format, first N_SECOND_RATER items, for a labmate/supervisor (optional).

Refuses to run if annotation.csv already exists, so a rerun can never wipe your labels.

Run from the repo root:
    python scripts/judge_validation_sample.py
"""
import csv
import glob
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------- EDIT THESE ----------------------------------
SEED = 42
# System label -> log file. The label comes from the FILE, because the 'retriever' field
# is a plain string in some logs and a list in others (hybrid).
LOGS = {
    "E1_BM25": "logs/freshqa_baseline_run.jsonl",
    "E2_Dense": "logs/freshqa_dense_run.jsonl",
    "E3_Hybrid": "logs/freshqa_hybrid_run.jsonl",
    "E4_Hybrid+Reranker": "logs/freshqa_hybrid_reranker.jsonl",
}
CONDITION = "clean"
PER_CELL = 7                        # 4 systems x 4 strata x 7 = up to 112
MIN_TOTAL = 100                     # top up at random if the cells give fewer
N_SECOND_RATER = 30
OUT_DIR = Path("results/judge_validation")
# --------------------------------------------------------------------------


def stratum_of(r):
    # false_premise is the STRING "TRUE"/"FALSE" in these logs, not a boolean
    if str(r.get("false_premise", "")).strip().upper() == "TRUE":
        return "false-premise"
    return r["fact_type"]            # never-changing / slow-changing / fast-changing


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ann_path = OUT_DIR / "annotation.csv"
    if ann_path.exists():
        sys.exit(f"{ann_path} already exists. Refusing to overwrite your labels. "
                 "Move or delete it deliberately if you really want a new sample.")

    missing = [p for p in LOGS.values() if not Path(p).exists()]
    if missing:
        sys.exit("Missing log file(s): " + ", ".join(missing))
    print("log files:", *[f"{k}: {v}" for k, v in LOGS.items()], sep="\n  ")

    # one record per (system, query_id); keep the last (resumable logs can hold duplicates)
    recs = {}
    for system, path in LOGS.items():
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("attack_condition", CONDITION) != CONDITION:
                continue
            if r.get("fresheval_correct") is None:
                continue
            recs[(system, r["query_id"])] = r

    cells = defaultdict(list)
    for (system, qid), r in recs.items():
        cells[(system, stratum_of(r))].append({
            "system": system, "stratum": stratum_of(r), "query_id": qid,
            "question": r["query"], "gold": r["gold_answer"],
            "false_premise": str(r.get("false_premise", "")).strip().upper(),
            "aliases": "; ".join(r.get("gold_aliases", [])),
            "answer": r["generated_answer"],
            "judge": int(bool(r["fresheval_correct"])),
            "rationale": r.get("fresheval_rationale", ""),
        })

    print("\nitems per cell (system, stratum):")
    for k in sorted(cells):
        print(f"  {k}: {len(cells[k])}")
    systems = sorted({k[0] for k in cells})
    print("systems found:", systems)
    if len(systems) != 4:
        print("WARNING: expected 4 systems (E1-E4). Check LOG_GLOB and the 'retriever' field.")

    rng = random.Random(SEED)
    sample = []
    for k in sorted(cells):
        items = cells[k]
        sample += rng.sample(items, min(PER_CELL, len(items)))

    if len(sample) < MIN_TOTAL:
        chosen = {(s["system"], s["query_id"]) for s in sample}
        rest = [it for items in cells.values() for it in items
                if (it["system"], it["query_id"]) not in chosen]
        need = MIN_TOTAL - len(sample)
        sample += rng.sample(rest, min(need, len(rest)))
        print(f"topped up to {len(sample)} items from the remaining pool")

    rng.shuffle(sample)  # hides system/stratum from the annotator via row order
    for i, s in enumerate(sample):
        s["item_id"] = i

    head = ["item_id", "question", "gold", "aliases", "false_premise", "answer", "human_label", "notes"]

    def write_sheet(path, items):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(head)
            for s in items:
                w.writerow([s["item_id"], s["question"], s["gold"], s["aliases"],
                            s["false_premise"], s["answer"], "", ""])

    write_sheet(ann_path, sample)
    write_sheet(OUT_DIR / "annotation_rater2.csv", sample[:N_SECOND_RATER])

    with open(OUT_DIR / "key.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "query_id", "system", "stratum", "judge_label", "judge_rationale",
                    "judge2_label"])
        for s in sample:
            w.writerow([s["item_id"], s["query_id"], s["system"], s["stratum"], s["judge"],
                        s["rationale"], ""])

    print(f"\n{len(sample)} items written to {OUT_DIR}/")
    print("Label annotation.csv with 1 (correct) or 0 (incorrect). Do not open key.csv.")


if __name__ == "__main__":
    main()