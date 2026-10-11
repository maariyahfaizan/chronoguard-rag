import json
from pathlib import Path

path = Path("results/gold_evidence_manual_review.jsonl")

with path.open("r", encoding="utf-8") as f:
    rows = [json.loads(line) for line in f if line.strip()]

for i, row in enumerate(
    sorted(rows, key=lambda r: r["nearest_gap_days"], reverse=True),
    start=1
):
    print("\n" + "=" * 80)
    print(f"RECORD {i} | DATE GAP: {row['nearest_gap_days']} days")
    print("QUESTION:", row["query"])
    print("QUESTION DATE:", row["question_date"])
    print("GOLD ANSWER:", row["gold_answer"])
    print("GOLD ALIASES:", row.get("gold_aliases"))

    for j, passage in enumerate(row.get("gold_passages", []), start=1):
        print(f"\n--- GOLD PASSAGE {j} ---")
        print("TIMESTAMP:", passage.get("timestamp"))
        print("TEXT:", passage.get("text", ""))

