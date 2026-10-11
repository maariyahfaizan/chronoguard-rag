import json
from datetime import datetime, timezone
from pathlib import Path

from src.attacks.attack_pool import (
    _gold_ids,
    _is_gold,
    _parse_timestamp,
    _text_overlap,
)

source = Path("data/processed/streamingqa_control_pools_chunked.jsonl")
output = Path("results/stale_evidence_review.jsonl")
output.parent.mkdir(parents=True, exist_ok=True)

review_rows = []

with source.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue

        record = json.loads(line)
        question_dt = _parse_timestamp(record.get("question_ts"))

        if question_dt is None:
            continue

        gold_ids = _gold_ids(record)

        for candidate in record.get("candidates", []):
            if _is_gold(candidate, gold_ids):
                continue

            candidate_dt = _parse_timestamp(candidate.get("timestamp"))
            if candidate_dt is None:
                continue

            age_days = (
                question_dt - candidate_dt
            ).total_seconds() / 86400

            if age_days < 30:
                continue

            overlap = _text_overlap(
                record.get("query", ""),
                candidate.get("text", ""),
            )

            if overlap <= 0:
                continue

            review_rows.append({
                "query": record.get("query"),
                "question_ts": record.get("question_ts"),
                "doc_id": candidate.get("doc_id"),
                "timestamp": candidate.get("timestamp"),
                "age_days": round(age_days, 1),
                "overlap_score": round(overlap, 4),
                "stale_evidence_validated": (
                    candidate.get("stale_evidence_validated") is True
                ),
                "text": candidate.get("text", ""),
                "review_decision": "PENDING",
                "review_notes": "",
            })

review_rows.sort(
    key=lambda row: (row["overlap_score"], row["age_days"]),
    reverse=True,
)

with output.open("w", encoding="utf-8") as f:
    for row in review_rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("Candidates for review:", len(review_rows))
print("Already explicitly validated:", sum(
    row["stale_evidence_validated"] for row in review_rows
))
print("Saved review report:", output)
