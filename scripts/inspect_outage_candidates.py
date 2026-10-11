import json
from pathlib import Path

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")

with path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue

        record = json.loads(line)

        if "During internet outages reported on October 27, 2021" not in record.get("query", ""):
            continue

        print("QUERY:", record["query"])
        print("QUESTION TIMESTAMP:", record.get("question_ts"))
        print("GOLD ANSWER:", record.get("gold_answer"))
        print("GOLD ALIASES:", record.get("gold_aliases"))

        for i, candidate in enumerate(record.get("candidates", []), start=1):
            print(f"\n--- Candidate {i} ---")
            print("DOC ID:", candidate.get("doc_id"))
            print("TIMESTAMP:", candidate.get("timestamp"))
            print("TEXT:", candidate.get("text", ""))

        break
