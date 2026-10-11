import json
from pathlib import Path

pool_path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")
gap_path = Path("results/gold_date_gap_report.json")
out_path = Path("results/gold_evidence_manual_review.jsonl")

with gap_path.open("r", encoding="utf-8") as f:
    gaps = json.load(f)

top_queries = {
    row["query"]: row
    for row in gaps[:10]
}

review_rows = []

with pool_path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue

        record = json.loads(line)
        query = record.get("query", "")

        if query not in top_queries:
            continue

        gap = top_queries[query]
        gold_ids = set(record.get("gold_chunk_ids", []))

        gold_candidates = [
            candidate
            for candidate in record.get("candidates", [])
            if candidate.get("doc_id") in gold_ids
        ]

        review_rows.append({
            "query": query,
            "question_date": gap["question_date"],
            "gold_dates": gap["gold_dates"],
            "nearest_gap_days": gap["nearest_gap_days"],
            "gold_answer": record.get("gold_answer"),
            "gold_aliases": record.get("gold_aliases"),
            "gold_passages": [
                {
                    "doc_id": candidate.get("doc_id"),
                    "timestamp": candidate.get("timestamp"),
                    "text": candidate.get("text", "")
                }
                for candidate in gold_candidates
            ],
            "review_decision": "PENDING",
            "review_notes": ""
        })

out_path.parent.mkdir(parents=True, exist_ok=True)

with out_path.open("w", encoding="utf-8") as f:
    for row in review_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("Review records created:", len(review_rows))
print("Saved to:", out_path)

for i, row in enumerate(
    sorted(review_rows, key=lambda r: r["nearest_gap_days"], reverse=True),
    start=1
):
    print(f"\n{i}. Gap: {row['nearest_gap_days']} days")
    print("Question:", row["query"])
    print("Question date:", row["question_date"])
    print("Gold passage dates:", row["gold_dates"])
    print("Gold answer:", row["gold_answer"])
    print("Gold passage count:", len(row["gold_passages"]))
