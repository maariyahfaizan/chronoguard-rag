import json
from pathlib import Path

path = Path("results/stale_evidence_review.jsonl")
rows = [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

rows.sort(
    key=lambda row: (row["overlap_score"], row["age_days"]),
    reverse=True,
)

for i, row in enumerate(rows[:10], start=1):
    print(f"\n--- Candidate {i} ---")
    print("Query:", row["query"])
    print("Age in days:", row["age_days"])
    print("Overlap score:", row["overlap_score"])
    print("Document ID:", row["doc_id"])
    print("Timestamp:", row["timestamp"])
    print("Text:", row["text"][:1200])
