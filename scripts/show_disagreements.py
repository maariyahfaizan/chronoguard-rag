#!/usr/bin/env python3
"""List judge-validation disagreements and write them to a UTF-8 text file.

Run AFTER you have finished labelling (it reads key.csv):
    python scripts/show_disagreements.py

Writes results/judge_validation/disagreements.txt and prints only a short summary,
because the Windows console can choke on non-Latin characters in answers.
Read the text file in VS Code or Notepad.
"""
import csv
from collections import Counter
from pathlib import Path

D = Path("results/judge_validation")


def read(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


key = {r["item_id"]: r for r in read(D / "key.csv")}
ann = [r for r in read(D / "annotation.csv") if r["human_label"].strip() != ""]

judge_lenient, judge_strict = [], []
for r in ann:
    k = key[r["item_id"]]
    h, j = r["human_label"].strip(), k["judge_label"].strip()
    if h == "0" and j == "1":
        judge_lenient.append((r, k))   # human wrong, judge correct
    elif h == "1" and j == "0":
        judge_strict.append((r, k))    # human correct, judge wrong


def block(r, k):
    return (f"#{r['item_id']}  [{k['system']} / {k['stratum']}]  false_premise={r.get('false_premise', '?')}\n"
            f"  Q:      {r['question']}\n"
            f"  gold:   {r['gold']}\n"
            f"  answer: {r['answer'][:400]}\n"
            f"  judge:  {k['judge_rationale']}\n"
            f"  notes:  {r.get('notes', '')}\n")


out = D / "disagreements.txt"
with open(out, "w", encoding="utf-8") as f:
    f.write(f"JUDGE SAID CORRECT, I SAID WRONG: {len(judge_lenient)}\n{'=' * 70}\n\n")
    for r, k in judge_lenient:
        f.write(block(r, k) + "\n")
    f.write(f"\nJUDGE SAID WRONG, I SAID CORRECT: {len(judge_strict)}\n{'=' * 70}\n\n")
    for r, k in judge_strict:
        f.write(block(r, k) + "\n")

print(f"judge lenient (judge=1, human=0): {len(judge_lenient)}")
print(f"judge strict  (judge=0, human=1): {len(judge_strict)}")
print("lenient cases by stratum:", dict(Counter(k["stratum"] for _, k in judge_lenient)))
print("lenient cases by system: ", dict(Counter(k["system"] for _, k in judge_lenient)))
print(f"\nfull details written to {out}")