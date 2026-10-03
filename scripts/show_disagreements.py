#!/usr/bin/env python3
"""List judge-validation disagreements and write them to a UTF-8 text file.

Run AFTER you have finished labelling (it reads key.csv):
    python scripts/show_disagreements.py              # human vs judge1 (Mistral)
    python scripts/show_disagreements.py --judge 2    # human vs judge2

Writes results/judge_validation/disagreements.txt (or disagreements_judge2.txt) and prints only
a short summary, because the Windows console can choke on non-Latin characters in answers.
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

D = Path("results/judge_validation")

ap = argparse.ArgumentParser()
ap.add_argument("--judge", type=int, choices=[1, 2], default=1)
args = ap.parse_args()
label_col = "judge_label" if args.judge == 1 else "judge2_label"
why_col = "judge_rationale" if args.judge == 1 else "judge2_rationale"
out = D / ("disagreements.txt" if args.judge == 1 else "disagreements_judge2.txt")


def read(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


key = {r["item_id"]: r for r in read(D / "key.csv")}
ann = [r for r in read(D / "annotation.csv") if r["human_label"].strip() != ""]

lenient, strict = [], []
for r in ann:
    k = key[r["item_id"]]
    h, j = r["human_label"].strip(), k.get(label_col, "").strip()
    if j == "":
        continue
    if h == "0" and j == "1":
        lenient.append((r, k))   # human wrong, judge correct
    elif h == "1" and j == "0":
        strict.append((r, k))    # human correct, judge wrong


def block(r, k):
    return (f"#{r['item_id']}  [{k['system']} / {k['stratum']}]  false_premise={r.get('false_premise', '?')}\n"
            f"  Q:      {r['question']}\n"
            f"  gold:   {r['gold']}\n"
            f"  answer: {r['answer'][:400]}\n"
            f"  judge{args.judge}:  {k.get(why_col, '')}\n"
            f"  notes:  {r.get('notes', '')}\n")


with open(out, "w", encoding="utf-8") as f:
    f.write(f"JUDGE{args.judge} SAID CORRECT, I SAID WRONG: {len(lenient)}\n{'=' * 70}\n\n")
    for r, k in lenient:
        f.write(block(r, k) + "\n")
    f.write(f"\nJUDGE{args.judge} SAID WRONG, I SAID CORRECT: {len(strict)}\n{'=' * 70}\n\n")
    for r, k in strict:
        f.write(block(r, k) + "\n")

print(f"judge{args.judge} lenient (judge=1, human=0): {len(lenient)}")
print(f"judge{args.judge} strict  (judge=0, human=1): {len(strict)}")
print("lenient cases by stratum:", dict(Counter(k["stratum"] for _, k in lenient)))
print("strict cases by stratum: ", dict(Counter(k["stratum"] for _, k in strict)))
print(f"\nfull details written to {out}")