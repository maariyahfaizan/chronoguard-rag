import json
from pathlib import Path
from src.attacks.attack_pool import apply_attack

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")
record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

attacks = [
    "stale_evidence",
    "future_date",
    "duplicate_fresh",
    "correct_content_wrong_date",
]

for attack in attacks:
    result, metadata = apply_attack(record, attack_type=attack, seed=42)
    print(f"\n{attack}:")
    print("  Eligible:", metadata.get("eligible"))
    print("  Applied:", metadata.get("applied"))
    print("  Reason:", metadata.get("reason", "—"))

    original = {c["doc_id"]: c for c in record["candidates"]}
    changed = 0

    for candidate in result["candidates"]:
        previous = original.get(candidate["doc_id"])

        if previous is None:
            print("  New candidate ID:", candidate["doc_id"])
            changed += 1
        elif candidate != previous:
            fields = [
                key for key in candidate
                if candidate.get(key) != previous.get(key)
            ]
            print(f"  Candidate {candidate['doc_id']}: {fields}")
            changed += 1

    print("  Changed candidates:", changed)
