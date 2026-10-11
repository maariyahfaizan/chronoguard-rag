import json
from pathlib import Path

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")

with path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        record = json.loads(line)
        print("QUERY:", record["query"])
        print("GOLD ANSWER:", record["gold_answer"])
        print("GOLD ALIASES:", record["gold_aliases"])
        gold_ids = set(record.get("gold_chunk_ids", []))
        print("\nGOLD CANDIDATE PASSAGES:")

        for candidate in record.get("candidates", []):
            if candidate.get("doc_id") in gold_ids:
                print("DOC ID:", candidate.get("doc_id"))
                print("TIMESTAMP:", candidate.get("timestamp"))
                print("TEXT:", candidate.get("text", ""))
                print()

        break
