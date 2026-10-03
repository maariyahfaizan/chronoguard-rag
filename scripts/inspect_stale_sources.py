import gzip
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


POOL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "streamingqa_control_pools_chunked.jsonl"
)

SHARDS_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "streamingqa_relevant_passages"
)


MIN_AGE_DAYS = 30
MAX_EXAMPLES = 10


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


def tokenize(text):
    tokens = set()

    for token in re.findall(r"\b[a-zA-Z0-9]+\b", text.lower()):
        if len(token) >= 3:
            tokens.add(token)

    return tokens


def overlap_score(query, text):
    query_tokens = tokenize(query)
    text_tokens = tokenize(text)

    if not query_tokens:
        return 0.0

    return len(query_tokens & text_tokens) / len(query_tokens)


# ---------------------------------------------------------------------
# Load clean query records.
# ---------------------------------------------------------------------

records = []

with POOL_PATH.open("r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))


print("Loaded clean records:", len(records))
print()


# ---------------------------------------------------------------------
# Search the raw corpus.
# ---------------------------------------------------------------------

shards = sorted(SHARDS_DIR.glob("*.jsonl.gz"))

if not shards:
    raise FileNotFoundError(
        f"No relevant-passage shards found in {SHARDS_DIR}"
    )


found = 0

for record_index, record in enumerate(records):

    if found >= MAX_EXAMPLES:
        break

    question_ts = parse_timestamp(record["question_ts"])

    if question_ts is None:
        continue

    query = record["query"]
    gold_ids = set(record["gold_chunk_ids"])

    best = []

    for shard_path in shards:

        with gzip.open(
            shard_path,
            "rt",
            encoding="utf-8",
        ) as f:

            for line in f:

                passage = json.loads(line)

                doc_id = passage["doc_id"]

                # Never use a known gold chunk.
                if doc_id in gold_ids:
                    continue

                passage_ts = parse_timestamp(
                    passage["timestamp"]
                )

                if passage_ts is None:
                    continue

                age_days = (
                    question_ts - passage_ts
                ).total_seconds() / 86400.0

                if age_days < MIN_AGE_DAYS:
                    continue

                score = overlap_score(
                    query,
                    passage["text"],
                )

                if score <= 0:
                    continue

                best.append(
                    (
                        score,
                        age_days,
                        doc_id,
                        passage["timestamp"],
                        passage["text"],
                    )
                )

        # Keep only a manageable number of candidates
        # for inspection.
        best.sort(
            key=lambda x: (x[0], x[1]),
            reverse=True,
        )

        best = best[:20]

    if not best:
        continue

    found += 1

    print("=" * 80)
    print("QUERY RECORD:", record_index)
    print("QUERY:", query)
    print("QUESTION TIME:", record["question_ts"])
    print()

    print("OLDER TOPICAL CANDIDATES:")

    for (
        score,
        age_days,
        doc_id,
        timestamp,
        text,
    ) in best[:5]:

        print()
        print(
            f"overlap={score:.3f} "
            f"age_days={age_days:.1f}"
        )
        print("doc_id:", doc_id)
        print("timestamp:", timestamp)
        print("text:", text[:500].replace("\n", " "))

    print()


print("=" * 80)
print("Total records with at least one older topical source:", found)