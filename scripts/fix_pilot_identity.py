#!/usr/bin/env python3
"""One-off fix (pre-Week-6, supervisor items 1 and 8): give the pilot records
and the authoritative fabricated payloads a stable source_qa_id.

Run once from the repo root:
    python scripts/fix_pilot_identity.py

Evidence used (no ID is invented):
- Each pilot record is matched to the frozen StreamingQA source
  data/raw/streamingqa_eval.jsonl.gz on question text, question_ts and the
  full answers list. Exactly one source record must match, or the script stops.
- The pilot record must be byte-equal (ignoring pilot_role/pilot_notes) to the
  frozen chunked pool record at the same position as that qa_id in
  data/raw/streamingqa_control_sample.jsonl.
- The old payloads carried question_id values of raw records 0-2
  (eval-007296, eval-001639, eval-018024), which are NOT the pilot questions.
  Their text was paired with the pilot questions by file order. The mapping
  below follows that text content and is checked: each payload must share a
  content word with its question and gold answer.

Payload text and timestamps are not changed. Old IDs are kept as
legacy_payload_id / legacy_question_id for audit. The original files are
copied to data/processed/attack_sources/legacy/ before being rewritten.
"""

import gzip
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.attacks.identity import query_sha256  # noqa: E402

SOURCES = ROOT / "data/processed/attack_sources"
PILOT = SOURCES / "streamingqa_attack_pilot.jsonl"
PAYLOADS = SOURCES / "streamingqa_pilot_fabricated_payloads.jsonl"
LEGACY = SOURCES / "legacy"
RAW_EVAL = ROOT / "data/raw/streamingqa_eval.jsonl.gz"
RAW_SAMPLE = ROOT / "data/raw/streamingqa_control_sample.jsonl"
CHUNKED = ROOT / "data/processed/streamingqa_control_pools_chunked.jsonl"

PAYLOAD_SCHEMA = "chronoguard.pilot_payload.v2"

# legacy payload_id -> source_qa_id of the question its text is about.
LEGACY_PAYLOAD_TO_QA_ID = {
    "eval-007296-fabricated_fresh-1": "eval-001639",  # Rangers / split
    "eval-001639-fabricated_fresh-1": "eval-001952",  # coronavirus countries
    "eval-018024-fabricated_fresh-1": "eval-005229",  # Djokovic / US Open
}
PILOT_ONLY_FIELDS = ("pilot_role", "pilot_notes")


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(rows, path):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) >= 4}


def resolve_qa_id(record, raw_by_question, sample_ids, chunked):
    matches = [r for r in raw_by_question.get(record["query"], [])
               if r["question_ts"] == record["question_ts"]
               and r["answers"] == record["gold_aliases"]]
    if len(matches) != 1:
        raise SystemExit(f"{len(matches)} source matches for {record['query']!r}; need exactly 1.")
    qa_id = matches[0]["qa_id"]

    position = sample_ids.index(qa_id)
    bare = {k: v for k, v in record.items() if k not in PILOT_ONLY_FIELDS and k != "source_qa_id"}
    if chunked[position] != bare:
        raise SystemExit(f"{qa_id}: pilot record differs from chunked pool record {position}.")
    return qa_id, position


def main():
    pilot = read_jsonl(PILOT)
    payloads = read_jsonl(PAYLOADS)
    if any("source_qa_id" in r for r in pilot + payloads):
        raise SystemExit("Files already carry source_qa_id; nothing to do.")

    raw_by_question = {}
    with gzip.open(RAW_EVAL, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            raw_by_question.setdefault(row["question"], []).append(row)
    sample_ids = [r["qa_id"] for r in read_jsonl(RAW_SAMPLE)]
    chunked = read_jsonl(CHUNKED)

    new_pilot, by_id = [], {}
    for record in pilot:
        qa_id, position = resolve_qa_id(record, raw_by_question, sample_ids, chunked)
        fixed = {"source_qa_id": qa_id, "source_chunked_pool_index": position, **record}
        new_pilot.append(fixed)
        by_id[qa_id] = fixed
        print(f"pilot {record['query'][:50]!r} -> {qa_id} (chunked pool index {position})")

    new_payloads = []
    for payload in payloads:
        qa_id = LEGACY_PAYLOAD_TO_QA_ID[payload["payload_id"]]
        record = by_id[qa_id]
        shared = content_words(payload["text"]) & content_words(
            record["query"] + " " + record["gold_answer"])
        if not shared:
            raise SystemExit(f"{payload['payload_id']} shares no content word with {qa_id}.")
        new_payloads.append({
            "payload_schema": PAYLOAD_SCHEMA,
            "payload_id": f"{qa_id}-fabricated_fresh-1",
            "source_qa_id": qa_id,
            "query_sha256": query_sha256(record["query"]),
            "attack_type": payload["attack_type"],
            "text": payload["text"],
            "timestamp": payload["timestamp"],
            "synthetic": payload["synthetic"],
            "legacy_payload_id": payload["payload_id"],
            "legacy_question_id": payload["question_id"],
        })
        print(f"payload {payload['payload_id']} -> {qa_id} (shared: {sorted(shared)[:3]})")

    LEGACY.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PILOT, LEGACY / "streamingqa_attack_pilot.pre_source_qa_id.jsonl")
    shutil.copy2(PAYLOADS, LEGACY / "streamingqa_pilot_fabricated_payloads.pre_source_qa_id.jsonl")
    write_jsonl(new_pilot, PILOT)
    write_jsonl(new_payloads, PAYLOADS)
    print("Rewrote", PILOT.relative_to(ROOT), "and", PAYLOADS.relative_to(ROOT))


if __name__ == "__main__":
    main()
