import json
from pathlib import Path
from src.attacks.attack_pool import _parse_timestamp, _gold_ids

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")
records = [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

counts = []

for record in records:
    question_time = _parse_timestamp(record["question_ts"])
    gold_ids = _gold_ids(record)
    count = 0

    if question_time is not None:
        for candidate in record["candidates"]:
            if str(candidate["doc_id"]) in gold_ids:
                continue

            candidate_time = _parse_timestamp(candidate["timestamp"])
            if candidate_time is None:
                continue

            age_days = (question_time - candidate_time).total_seconds() / 86400

            if 0 <= age_days <= 30:
                count += 1

    counts.append(count)

print("Records:", len(records))
print("With eligible duplicate sources:", sum(n > 0 for n in counts))
print("Without eligible duplicate sources:", sum(n == 0 for n in counts))
print("Eligible sources per record: min =", min(counts), "max =", max(counts), "total =", sum(counts))
