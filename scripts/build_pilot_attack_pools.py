#!/usr/bin/env python3
"""Build the attacked Week-5 pilot pools, protocol v2 (CPU only, no models).

Run from the repo root, AFTER scripts/validate_pilot_attacks.py has passed:
    python scripts/build_pilot_attack_pools.py

Writes one pool file per (condition, poison count) under
    data/processed/attack_pools/pilot_v2_nested/<condition>_n<count>.jsonl
plus pilot_pools_manifest.json in the same folder.

Each pool has the same schema as the clean chunked pool, so the E1-E4 drivers
can read it through their input_path argument. The clean pools are never
modified. Records where an attack is ineligible are left OUT (never forced).
stale_evidence is not built: no reviewed stale evidence is available.

Payloads are paired with questions by source_qa_id only. Seeds come from
source_qa_id. Poison counts are nested per question and condition; the build
stops before writing anything if they are not.

Every record carries source_qa_id, attack_condition (unique per variant),
attack_metadata (seed, target_indices, target_doc_ids, operations),
poison_count and attack_protocol_version.
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attacks.attack_pool import apply_attack, write_jsonl  # noqa: E402
from src.attacks.pilot_protocol import (  # noqa: E402
    AUTHORITATIVE_PAYLOAD_PATH,
    BASE_SEED,
    CONDITIONS,
    NOT_BUILT,
    PILOT_PATH,
    POISON_COUNTS,
    POOL_DIR,
    PROTOCOL_VERSION,
    STALE_INELIGIBLE_REASON,
    load_authoritative_payloads,
    load_pilot_records,
    nesting_problems,
    payload_kwargs,
    record_seed,
)

VALIDATION_REPORT = PROJECT_ROOT / "results/pilot_attack_validation.json"


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


def rel(path):
    return str(Path(path).relative_to(PROJECT_ROOT)).replace("\\", "/")


def require_passed_validation():
    if not VALIDATION_REPORT.exists():
        raise SystemExit("Run scripts/validate_pilot_attacks.py first (no validation report found).")
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    if report.get("protocol_version") != PROTOCOL_VERSION:
        raise SystemExit("The validation report is not for protocol "
                         f"{PROTOCOL_VERSION}. Rerun the validator.")
    if report["cases_failed"] or report["payload_problems"] or report["nesting_failures"]:
        raise SystemExit("The saved validation report has failures. Fix them and rerun the validator.")
    if not report["identity_mismatch_self_test"]["rejected"]:
        raise SystemExit("The validation report shows a mismatched payload was not rejected.")
    if report["pilot_file_sha256"] != sha256_file(PILOT_PATH) or \
            report["payload_file_sha256"] != sha256_file(AUTHORITATIVE_PAYLOAD_PATH):
        raise SystemExit("The pilot or payload file changed since validation. Rerun the validator.")
    return report


def main():
    report = require_passed_validation()
    records = load_pilot_records(PILOT_PATH)
    payloads = load_authoritative_payloads(AUTHORITATIVE_PAYLOAD_PATH)

    built = {}          # (condition, count) -> (records, skipped)
    selections = []     # per question x condition: seed and nested slots

    for condition in CONDITIONS:
        if condition["name"] in NOT_BUILT:
            continue
        for record in records:
            qa_id = record["source_qa_id"]
            seed = record_seed(record, condition["attack_type"])
            targets_by_count, doc_ids_by_count = {}, {}

            for count in POISON_COUNTS:
                kwargs = dict(attack_type=condition["attack_type"], seed=seed,
                              poison_count=count, **condition["kwargs"])
                if condition["attack_type"] == "fabricated_fresh":
                    kwargs["poison_payload"] = payload_kwargs(payloads[qa_id])

                attacked, meta = apply_attack(record, **kwargs)
                pool_records, skipped = built.setdefault((condition["name"], count), ([], []))

                if not meta["applied"]:
                    skipped.append({"source_qa_id": qa_id, "reason": meta.get("reason")})
                    continue

                attacked["attack_condition"] = condition["name"]
                attacked["poison_count"] = count
                attacked["attack_protocol_version"] = PROTOCOL_VERSION
                pool_records.append(attacked)
                targets_by_count[count] = meta["target_indices"]
                doc_ids_by_count[count] = meta["target_doc_ids"]

            problems = nesting_problems(targets_by_count)
            if problems:
                raise SystemExit(f"Not nested for {qa_id} {condition['name']}: {problems}")
            selections.append({
                "source_qa_id": qa_id,
                "condition": condition["name"],
                "seed": seed,
                "target_indices_by_count": {str(k): v for k, v in targets_by_count.items()},
                "target_doc_ids_by_count": {str(k): v for k, v in doc_ids_by_count.items()},
                "nested": True,
            })

    POOL_DIR.mkdir(parents=True, exist_ok=True)
    manifest_entries = []

    for (name, count), (pool_records, skipped) in built.items():
        condition = next(c for c in CONDITIONS if c["name"] == name)
        path = POOL_DIR / f"{name}_n{count}.jsonl"
        write_jsonl(pool_records, path)
        manifest_entries.append({
            "file": rel(path),
            "condition": name,
            "attack_type": condition["attack_type"],
            "poison_count": count,
            "condition_kwargs": condition["kwargs"],
            "n_records": len(pool_records),
            "source_qa_ids": [r["source_qa_id"] for r in pool_records],
            "skipped_ineligible": skipped,
            "sha256": sha256_file(path),
        })
        print(f"{path.name}: {len(pool_records)} records, {len(skipped)} skipped")

    manifest = {
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "base_seed": BASE_SEED,
        "seed_rule": "sha256(base_seed|source_qa_id|attack_type)[:16] per question and attack type",
        "pilot_file": rel(PILOT_PATH),
        "pilot_file_sha256": sha256_file(PILOT_PATH),
        "payload_file": rel(AUTHORITATIVE_PAYLOAD_PATH),
        "payload_file_sha256": sha256_file(AUTHORITATIVE_PAYLOAD_PATH),
        "validation_report_generated_at": report["generated_at_utc"],
        "not_generated": [{"condition": "stale_evidence", "eligible": False,
                           "reason": STALE_INELIGIBLE_REASON}],
        "nested_selections": selections,
        "pools": manifest_entries,
    }
    (POOL_DIR / "pilot_pools_manifest.json").write_text(json.dumps(manifest, indent=2),
                                                        encoding="utf-8")
    print(f"Manifest: {rel(POOL_DIR / 'pilot_pools_manifest.json')}")


if __name__ == "__main__":
    main()
