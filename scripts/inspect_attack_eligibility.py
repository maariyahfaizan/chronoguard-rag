import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
from datetime import datetime, timezone


INPUT = Path(
    "data/processed/streamingqa_control_pools_chunked.jsonl"
)


def parse_timestamp(value):
    if value is None:
        return None

    text = str(value).strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def query_tokens(text):
    tokens = set()

    for token in text.lower().split():
        cleaned = "".join(
            ch for ch in token
            if ch.isalnum()
        )

        if len(cleaned) >= 3:
            tokens.add(cleaned)

    return tokens


def overlap(query, text):
    q = query_tokens(query)
    t = query_tokens(text)

    if not q:
        return 0.0

    return len(q & t) / len(q)


total = 0
with_old = 0
with_30_day_old = 0
with_old_overlap = 0
with_30_day_old_overlap = 0

examples = []


with INPUT.open("r", encoding="utf-8") as f:
    for record_index, line in enumerate(f):
        if not line.strip():
            continue

        record = json.loads(line)
        total += 1

        question_dt = parse_timestamp(
            record["question_ts"]
        )

        if question_dt is None:
            continue

        gold_ids = set(
            record["gold_chunk_ids"]
        )

        old_candidates = []
        old_overlap_candidates = []

        for candidate in record["candidates"]:
            if candidate["doc_id"] in gold_ids:
                continue

            candidate_dt = parse_timestamp(
                candidate["timestamp"]
            )

            if candidate_dt is None:
                continue

            age_days = (
                question_dt - candidate_dt
            ).total_seconds() / 86400.0

            if age_days > 0:
                with_old += 1
                old_candidates.append(
                    (age_days, candidate)
                )

                if overlap(
                    record["query"],
                    candidate["text"],
                ) > 0:
                    old_overlap_candidates.append(
                        (age_days, candidate)
                    )

            if age_days >= 30:
                with_30_day_old += 1

                if overlap(
                    record["query"],
                    candidate["text"],
                ) > 0:
                    with_30_day_old_overlap += 1

        if old_candidates:
            with_old += 0

        if old_overlap_candidates:
            with_old_overlap += 1

        if old_candidates and len(examples) < 5:
            examples.append(
                (
                    record_index,
                    record["query"],
                    question_dt.isoformat(),
                    sorted(
                        old_candidates,
                        key=lambda x: x[0],
                        reverse=True,
                    )[:3],
                )
            )


print("=== STALE-ELIGIBILITY DIAGNOSTIC ===")
print("Total records:", total)
print()
print(
    "Records with at least one older non-gold candidate:",
    with_old,
)
print(
    "Records with at least one >=30-day-old non-gold candidate:",
    with_30_day_old,
)
print(
    "Records with older candidate + query-token overlap:",
    with_old_overlap,
)
print(
    "Records with >=30-day-old candidate + query-token overlap:",
    with_30_day_old_overlap,
)

print()
print("=== EXAMPLES ===")

for record_index, query, question_ts, candidates in examples:
    print()
    print("Record:", record_index)
    print("Query:", query)
    print("Question timestamp:", question_ts)

    for age_days, candidate in candidates:
        print(
            f"  age_days={age_days:.1f}, "
            f"timestamp={candidate['timestamp']}, "
            f"doc_id={candidate['doc_id']}"
        )