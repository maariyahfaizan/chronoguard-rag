import json
from pathlib import Path

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")

with path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        record = json.loads(line)
        print("QUERY:", record.get("query"))
        print("GOLD ANSWER:", record.get("gold_answer"))
        print("GOLD ALIASES:", record.get("gold_aliases"))
        print("GOLD CHUNK IDS:", record.get("gold_chunk_ids"))
        print("GOLD VALIDATED:", record.get("gold_validated"))
        print("\nCANDIDATE FIELDS:")
        if record.get("candidates"):
            print(sorted(record["candidates"][0].keys()))
        break
