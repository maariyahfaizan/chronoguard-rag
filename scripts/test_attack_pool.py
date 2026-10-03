import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json

from src.attacks.attack_pool import apply_attack


INPUT = Path(
    "data/processed/streamingqa_control_pools_chunked.jsonl"
)


with INPUT.open("r", encoding="utf-8") as f:
    for record_index, line in enumerate(f):
        record = json.loads(line)

        attacked, metadata = apply_attack(
            record,
            attack_type="stale_evidence",
            seed=42,
        )

        if metadata["applied"]:
            print("=== ELIGIBLE STALE ATTACK FOUND ===")
            print("Record index:", record_index)
            print("Query:", record["query"])
            print("Attack metadata:")
            print(json.dumps(
                metadata,
                indent=2,
                ensure_ascii=False,
            ))

            print()
            print(
                "Original candidates:",
                len(record["candidates"]),
            )
            print(
                "Attacked candidates:",
                len(attacked["candidates"]),
            )

            print()
            print(
                "Gold answer unchanged:",
                attacked["gold_answer"]
                == record["gold_answer"],
            )
            print(
                "Question timestamp unchanged:",
                attacked["question_ts"]
                == record["question_ts"],
            )
            print(
                "Gold chunk IDs unchanged:",
                attacked["gold_chunk_ids"]
                == record["gold_chunk_ids"],
            )

            target_index = metadata["details"]["target_index"]

            print()
            print("Changed candidate index:", target_index)
            print(
                "Original candidate:",
                json.dumps(
                    record["candidates"][target_index],
                    ensure_ascii=False,
                ),
            )
            print(
                "Poisoned candidate:",
                json.dumps(
                    attacked["candidates"][target_index],
                    ensure_ascii=False,
                ),
            )

            break

    else:
        print("NO ELIGIBLE STALE ATTACK FOUND")