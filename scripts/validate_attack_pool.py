
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attacks.attack_pool import apply_attack


ATTACK_TYPES = [
    "stale_evidence",
    "fabricated_fresh",
    "future_date",
    "duplicate_fresh",
    "correct_content_wrong_date",
]

POISON_COUNTS = [1, 2, 5]

PAYLOAD = {
    "payload_id": "validation-test-payload",
    "text": "A deliberately fabricated test claim about Rangers.",
    "timestamp": "2025-02-10T12:00:00Z",
}

PROTECTED_FIELDS = [
    "query",
    "gold_answer",
    "gold_aliases",
    "question_ts",
    "gold_chunk_ids",
    "gold_validated",
]


def make_record():
    candidates = [
        {
            "doc_id": "gold-001",
            "text": (
                "Rangers are in the validated test position "
                "according to the official league table."
            ),
            "timestamp": "2025-01-30T12:00:00Z",
            "is_source_document": True,
        },
        {
            "doc_id": "stale-001",
            "text": (
                "Rangers football team league position and "
                "season standings from an older competition."
            ),
            "timestamp": "2024-01-01T12:00:00Z",
            "is_source_document": True,
            "stale_evidence_validated": True,
        },
    ]

    for i in range(1, 8):
        candidates.append({
            "doc_id": f"fresh-{i:03d}",
            "text": (
                f"Recent Rangers football team league "
                f"position report number {i}."
            ),
            "timestamp": f"2025-01-{25-i:02d}T12:00:00Z",
            "is_source_document": True,
        })

    return {
        "query": "What is the current Rangers football team position?",
        "gold_answer": "Rangers are in the test position.",
        "gold_aliases": ["Rangers test position"],
        "question_ts": "2025-02-01T12:00:00Z",
        "gold_chunk_ids": ["gold-001"],
        "gold_validated": True,
        "candidates": candidates,
    }


def sha256_json(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_case(attack_type, poison_count):
    record = make_record()
    original = copy.deepcopy(record)

    kwargs = {}
    if attack_type == "fabricated_fresh":
        kwargs["poison_payload"] = PAYLOAD

    attacked, metadata = apply_attack(
        record,
        attack_type=attack_type,
        seed=42,
        poison_count=poison_count,
        **kwargs,
    )

    checks = {
        "input_unchanged": record == original,
        "candidate_count_preserved": (
            len(attacked["candidates"]) == len(original["candidates"])
        ),
        "protected_fields_preserved": all(
            attacked.get(field) == original.get(field)
            for field in PROTECTED_FIELDS
        ),
        "gold_candidate_preserved": (
            attacked["candidates"][0] == original["candidates"][0]
        ),
        "attack_applied": metadata.get("applied") is True,
        "requested_count_correct": (
            metadata.get("requested_poison_count") == poison_count
        ),
        "actual_count_correct": (
            metadata.get("actual_poison_count") == poison_count
        ),
        "target_indices_distinct": (
            len(metadata.get("target_indices", [])) == poison_count
            and len(set(metadata.get("target_indices", []))) == poison_count
        ),
    }

    indices = metadata.get("target_indices", [])
    checks["targets_are_valid_non_gold_slots"] = all(
        isinstance(index, int)
        and 0 <= index < len(original["candidates"])
        and original["candidates"][index]["doc_id"]
        not in original["gold_chunk_ids"]
        for index in indices
    )

    # Repeat the same attack to check fixed-seed determinism.
    repeated_record = make_record()
    repeated, repeated_metadata = apply_attack(
        repeated_record,
        attack_type=attack_type,
        seed=42,
        poison_count=poison_count,
        **kwargs,
    )
    checks["fixed_seed_deterministic"] = (
        attacked == repeated and metadata == repeated_metadata
    )

    return {
        "attack_type": attack_type,
        "requested_poison_count": poison_count,
        "checks": checks,
        "passed": all(checks.values()),
        "metadata": metadata,
    }


def main():
    results = []

    for attack_type in ATTACK_TYPES:
        for count in POISON_COUNTS:
            try:
                results.append(validate_case(attack_type, count))
            except Exception as exc:
                results.append({
                    "attack_type": attack_type,
                    "requested_poison_count": count,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    passed = sum(result["passed"] for result in results)
    failed = len(results) - passed

    report = {
        "report_type": "synthetic_attack_pool_validation",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": 42,
        "attack_types": ATTACK_TYPES,
        "requested_poison_counts": POISON_COUNTS,
        "cases_total": len(results),
        "cases_passed": passed,
        "cases_failed": failed,
        "payload_sha256": sha256_json(PAYLOAD),
        "source_record": "synthetic test record; not real StreamingQA data",
        "stale_evidence_note": (
            "The stale-evidence case uses a synthetic candidate marked "
            "validated. Real-corpus stale-evidence validation remains "
            "deferred until the original Kaggle shards are restored."
        ),
        "results": results,
    }

    output_path = PROJECT_ROOT / "results" / "attack_pool_validation.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("=== ATTACK POOL VALIDATION ===")
    print(f"Cases: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Report: {output_path}")

    if failed:
        print("Some validation cases failed. Inspect the saved report.")
        raise SystemExit(1)

    print("All synthetic validation cases passed.")


if __name__ == "__main__":
    main()