#!/usr/bin/env python3
"""Build the attacked Week-5 pilot pools (CPU only, no models).

Run from the repo root, AFTER scripts/validate_pilot_attacks.py has passed:
    python scripts/build_pilot_attack_pools.py

Writes one pool file per (condition, poison count) under
    data/processed/attack_pools/pilot/<condition>_n<count>.jsonl
plus data/processed/attack_pools/pilot/pilot_pools_manifest.json.

Each pool has the same schema as the clean chunked pool, so the frozen E1-E4
drivers can read it through their input_path argument. The clean pools are never
modified. Records where an attack is ineligible are left OUT (never forced).
stale_evidence is skipped: no validated stale evidence exists for the pilot.

Every record carries attack_condition (the condition name, unique per variant),
attack_metadata (including target_doc_ids, used for poison rank) and pilot_index.
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attacks.attack_pool import _stable_seed, apply_attack, load_jsonl, write_jsonl  # noqa: E402

PILOT_PATH = PROJECT_ROOT / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
PAYLOAD_PATH = PROJECT_ROOT / "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl"
VALIDATION_REPORT = PROJECT_ROOT / "results/pilot_attack_validation.json"
OUT_DIR = PROJECT_ROOT / "data/processed/attack_pools/pilot"

BASE_SEED = 42
POISON_COUNTS = [1, 2, 5]

CONDITIONS = [
    {"name": "fabricated_fresh", "attack_type": "fabricated_fresh", "kwargs": {}},
    {"name": "future_date", "attack_type": "future_date", "kwargs": {}},
    {"name": "duplicate_fresh", "attack_type": "duplicate_fresh", "kwargs": {}},
    {"name": "correct_content_wrong_date_30d", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 30}},
    {"name": "correct_content_wrong_date_0d_control", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 0}},
]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git_state():
    def run(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True,
                                  check=True, cwd=PROJECT_ROOT).stdout.strip()
        except Exception:
            return None
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def load_payloads():
    with open(PAYLOAD_PATH, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def require_passed_validation():
    if not VALIDATION_REPORT.exists():
        raise SystemExit("Run scripts/validate_pilot_attacks.py first (no validation report found).")
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    if report["cases_failed"] or report["payload_problems"]:
        raise SystemExit("The saved validation report has failures. Fix them and rerun the validator.")
    if report["pilot_file_sha256"] != sha256_file(PILOT_PATH) or \
            report["payload_file_sha256"] != sha256_file(PAYLOAD_PATH):
        raise SystemExit("The pilot or payload file changed since validation. Rerun the validator.")
    return report


def main():
    report = require_passed_validation()
    records = load_jsonl(PILOT_PATH)
    payloads = load_payloads()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_entries = []

    for condition in CONDITIONS:
        for count in POISON_COUNTS:
            attacked_records, skipped = [], []

            for index, record in enumerate(records):
                kwargs = dict(
                    attack_type=condition["attack_type"],
                    seed=_stable_seed(BASE_SEED, index, condition["attack_type"]),
                    poison_count=count,
                    **condition["kwargs"],
                )
                if condition["attack_type"] == "fabricated_fresh":
                    payload = payloads[index]
                    kwargs["poison_payload"] = {
                        "payload_id": payload["payload_id"],
                        "text": payload["text"],
                        "timestamp": payload["timestamp"],
                    }

                attacked, meta = apply_attack(record, **kwargs)

                if not meta["applied"]:
                    skipped.append({"pilot_index": index, "reason": meta.get("reason")})
                    continue

                attacked["attack_condition"] = condition["name"]
                attacked["pilot_index"] = index
                attacked_records.append(attacked)

            path = OUT_DIR / f"{condition['name']}_n{count}.jsonl"
            write_jsonl(attacked_records, path)
            manifest_entries.append({
                "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "condition": condition["name"],
                "attack_type": condition["attack_type"],
                "poison_count": count,
                "condition_kwargs": condition["kwargs"],
                "n_records": len(attacked_records),
                "pilot_indices": [r["pilot_index"] for r in attacked_records],
                "skipped_ineligible": skipped,
                "sha256": sha256_file(path),
            })
            print(f"{path.name}: {len(attacked_records)} records, {len(skipped)} skipped")

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "base_seed": BASE_SEED,
        "pilot_file_sha256": sha256_file(PILOT_PATH),
        "payload_file_sha256": sha256_file(PAYLOAD_PATH),
        "validation_report_generated_at": report["generated_at_utc"],
        "not_generated": [{
            "condition": "stale_evidence",
            "reason": "No validated stale evidence for the pilot; ineligible, not forced.",
        }],
        "pools": manifest_entries,
    }
    (OUT_DIR / "pilot_pools_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Manifest: {OUT_DIR / 'pilot_pools_manifest.json'}")


if __name__ == "__main__":
    main()
