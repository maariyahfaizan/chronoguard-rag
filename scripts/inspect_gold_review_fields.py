import json
from pathlib import Path

path = Path("results/gold_evidence_manual_review.jsonl")

with path.open("r", encoding="utf-8") as f:
    row = json.loads(next(line for line in f if line.strip()))

print("Top-level fields:")
for key, value in row.items():
    print(f"  {key}: {type(value).__name__}")

print("\nGold passage fields:")
for passage in row.get("gold_passages", []):
    print(" ", list(passage.keys()))
    break

print("\nExisting review decision:", row.get("review_decision"))
print("Existing review notes:", row.get("review_notes"))
