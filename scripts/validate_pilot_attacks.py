#!/usr/bin/env python3
"""Validate every actual Week-5 pilot attack condition on the real pilot pools (W5-7).

Run from the repo root:
    python scripts/validate_pilot_attacks.py

Reads:
    data/processed/attack_sources/streamingqa_attack_pilot.jsonl          (3 pilot records)
    data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl

Writes:
    results/pilot_attack_validation.json   (saved integrity report; exit code 1 on any failure)

Payloads are paired with pilot records by FILE ORDER (the pilot records carry no
question_id). The pairing is checked: each payload must share a content word with
its record's query or gold answer, otherwise the script stops.

Conditions: stale_evidence (expected ineligible, never forced), fabricated_fresh,
future_date (metadata-only negative control for E1-E4), duplicate_fresh (may be
ineligible for a record), correct_content_wrong_date at wrong_date_days=30, and the
same attack at wrong_date_days=0 (duplication-only control). Poison counts 1, 2, 5.
"""

import copy
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.attacks.attack_pool import (  # noqa: E402
    _parse_timestamp,
    _stable_seed,
    apply_attack,
    load_jsonl,
)

PILOT_PATH = PROJECT_ROOT / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
PAYLOAD_PATH = PROJECT_ROOT / "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl"
REPORT_PATH = PROJECT_ROOT / "results/pilot_attack_validation.json"

BASE_SEED = 42
POISON_COUNTS = [1, 2, 5]
PROTECTED_FIELDS = ["query", "gold_answer", "gold_aliases", "question_ts",
                    "gold_chunk_ids", "gold_validated"]

CONDITIONS = [
    {"name": "stale_evidence", "attack_type": "stale_evidence", "kwargs": {}},
    {"name": "fabricated_fresh", "attack_type": "fabricated_fresh", "kwargs": {}},
    {"name": "future_date", "attack_type": "future_date", "kwargs": {}},
    {"name": "duplicate_fresh", "attack_type": "duplicate_fresh", "kwargs": {}},
    {"name": "correct_content_wrong_date_30d", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 30}},
    {"name": "correct_content_wrong_date_0d_control", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 0}},
]
# Conditions that may legitimately be ineligible for a record (never forced).
MAY_BE_INELIGIBLE = {"stale_evidence", "duplicate_fresh"}


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


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) >= 4}


def load_payloads(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                for key in ("payload_id", "question_id", "text", "timestamp"):
                    if key not in row:
                        raise SystemExit(f"Payload is missing '{key}': {row}")
                rows.append(row)
    return rows


def iso(dt):
    return dt.isoformat() if dt else None


def validate_case(record, index, condition, count, payload):
    original = copy.deepcopy(record)
    attack_type = condition["attack_type"]
    kwargs = dict(
        attack_type=attack_type,
        seed=_stable_seed(BASE_SEED, index, attack_type),
        poison_count=count,
        **condition["kwargs"],
    )
    if attack_type == "fabricated_fresh":
        kwargs["poison_payload"] = {
            "payload_id": payload["payload_id"],
            "text": payload["text"],
            "timestamp": payload["timestamp"],
        }

    attacked, meta = apply_attack(record, **kwargs)
    again, meta_again = apply_attack(record, **kwargs)

    checks = {
        "input_unchanged": record == original,
        "fixed_seed_deterministic": attacked == again and meta == meta_again,
    }
    result = {
        "pilot_index": index,
        "condition": condition["name"],
        "poison_count": count,
        "seed": kwargs["seed"],
    }

    if not meta["applied"]:
        checks["declined_pool_unchanged"] = attacked["candidates"] == original["candidates"]
        expected = condition["name"] in MAY_BE_INELIGIBLE
        result.update(status="ineligible" if expected else "UNEXPECTEDLY_INELIGIBLE",
                      reason=meta.get("reason"), checks=checks,
                      passed=expected and all(checks.values()))
        return result

    if condition["name"] == "stale_evidence":
        result.update(status="UNEXPECTEDLY_APPLIED", checks=checks, passed=False,
                      note="No stale evidence has been validated for the pilot; "
                           "stale_evidence must be ineligible.")
        return result

    gold_ids = {str(x) for x in original["gold_chunk_ids"]}
    before, after = original["candidates"], attacked["candidates"]
    targets = meta["target_indices"]
    sources = {op["source_index"] for op in meta["operations"] if "source_index" in op}
    changed = {i for i, (a, o) in enumerate(zip(after, before)) if a != o}

    checks.update({
        "candidate_count_preserved": len(after) == len(before),
        "protected_fields_preserved": all(attacked[f] == original[f] for f in PROTECTED_FIELDS),
        "gold_candidates_unchanged": all(
            a == o for a, o in zip(after, before) if str(o["doc_id"]) in gold_ids),
        "doc_id_set_unchanged": {c["doc_id"] for c in after} == {c["doc_id"] for c in before},
        "poison_count_correct": (meta["requested_poison_count"] == count
                                 == meta["actual_poison_count"] == len(targets)
                                 == len(set(targets))),
        "targets_are_non_gold": all(str(before[t]["doc_id"]) not in gold_ids for t in targets),
        "target_doc_ids_match": meta["target_doc_ids"] == [before[t]["doc_id"] for t in targets],
        "only_target_slots_changed": changed <= set(targets),
    })
    if sources:
        checks["single_source_never_overwritten"] = (
            len(sources) == 1 and sources.isdisjoint(targets))

    question_dt = _parse_timestamp(original["question_ts"])

    if attack_type == "fabricated_fresh":
        checks["payload_text_inserted"] = all(after[t]["text"] == payload["text"] for t in targets)
        checks["payload_timestamp_inserted"] = all(
            after[t]["timestamp"] == payload["timestamp"] for t in targets)
        checks["flagged_synthetic"] = all(after[t].get("is_synthetic_poison") is True for t in targets)
    elif attack_type == "future_date":
        checks["text_and_id_unchanged"] = all(
            {k: v for k, v in after[t].items() if k != "timestamp"}
            == {k: v for k, v in before[t].items() if k != "timestamp"} for t in targets)
        checks["timestamp_after_question"] = all(
            _parse_timestamp(after[t]["timestamp"]) > question_dt for t in targets)
    elif attack_type == "duplicate_fresh":
        s = next(iter(sources))
        checks["copies_source_text_and_date"] = all(
            after[t]["text"] == before[s]["text"] and after[t]["timestamp"] == before[s]["timestamp"]
            for t in targets)
    elif attack_type == "correct_content_wrong_date":
        s = next(iter(sources))
        days = condition["kwargs"]["wrong_date_days"]
        expected_dt = _parse_timestamp(before[s]["timestamp"]) - timedelta(days=days)
        checks["gold_text_copied"] = all(after[t]["text"] == before[s]["text"] for t in targets)
        checks["timestamp_shifted_as_specified"] = all(
            _parse_timestamp(after[t]["timestamp"]) == expected_dt for t in targets)

    result.update(status="applied", checks=checks, passed=all(checks.values()),
                  target_doc_ids=meta["target_doc_ids"])
    return result


def main():
    records = load_jsonl(PILOT_PATH)
    payloads = load_payloads(PAYLOAD_PATH)
    if len(records) != len(payloads):
        raise SystemExit(f"{len(records)} pilot records but {len(payloads)} payloads.")

    mapping, problems, results = [], [], []

    for index, (record, payload) in enumerate(zip(records, payloads)):
        shared = content_words(payload["text"]) & content_words(
            record["query"] + " " + record["gold_answer"])
        question_dt = _parse_timestamp(record["question_ts"])
        gold_ids = {str(x) for x in record["gold_chunk_ids"]}
        gold_dts = [_parse_timestamp(c["timestamp"]) for c in record["candidates"]
                    if str(c["doc_id"]) in gold_ids]
        latest_gold = max(d for d in gold_dts if d)
        payload_dt = _parse_timestamp(payload["timestamp"])

        entry = {
            "pilot_index": index,
            "query": record["query"],
            "payload_id": payload["payload_id"],
            "question_id": payload["question_id"],
            "shared_words": sorted(shared),
            "question_ts": iso(question_dt),
            "latest_gold_timestamp": iso(latest_gold),
            "payload_timestamp": iso(payload_dt),
            "payload_after_gold_evidence": bool(payload_dt and payload_dt > latest_gold),
            "payload_not_after_question": bool(payload_dt and payload_dt <= question_dt),
        }
        if not shared:
            problems.append(f"Pilot record {index} and payload {payload['payload_id']} share no "
                            "content word: the file order does not match.")
        if not entry["payload_after_gold_evidence"]:
            problems.append(f"{payload['payload_id']}: payload timestamp is not later than the gold "
                            f"evidence ({iso(latest_gold)}); it would not look fresher than the answer.")
        if not entry["payload_not_after_question"]:
            # Valid window: later than the gold evidence, not later than the question.
            candidate = question_dt - timedelta(hours=1)
            suggested = iso(candidate) if candidate > latest_gold else None
            entry["suggested_timestamp"] = suggested
            problems.append(f"{payload['payload_id']}: payload timestamp {iso(payload_dt)} is AFTER the "
                            f"question time {iso(question_dt)}, so it is future-dated, not fresh. "
                            f"Valid window: after {iso(latest_gold)} and not after {iso(question_dt)}. "
                            f"Suggested: {suggested}")
        mapping.append(entry)

    if any("share no content word" in p for p in problems):
        print("\n".join(problems))
        raise SystemExit(1)

    for index, record in enumerate(records):
        for condition in CONDITIONS:
            for count in POISON_COUNTS:
                try:
                    results.append(validate_case(record, index, condition, count, payloads[index]))
                except Exception as exc:  # report, do not crash
                    results.append({"pilot_index": index, "condition": condition["name"],
                                    "poison_count": count, "status": "ERROR", "passed": False,
                                    "error": f"{type(exc).__name__}: {exc}"})

    applied = [r for r in results if r["status"] == "applied"]
    ineligible = [r for r in results if r["status"] == "ineligible"]
    failed = [r for r in results if not r["passed"]]

    report = {
        "report_type": "pilot_attack_validation_real_pool",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "base_seed": BASE_SEED,
        "poison_counts": POISON_COUNTS,
        "pilot_file": str(PILOT_PATH.relative_to(PROJECT_ROOT)),
        "pilot_file_sha256": sha256_file(PILOT_PATH),
        "payload_file": str(PAYLOAD_PATH.relative_to(PROJECT_ROOT)),
        "payload_file_sha256": sha256_file(PAYLOAD_PATH),
        "payload_pairing_and_dates": mapping,
        "payload_problems": problems,
        "cases_total": len(results),
        "cases_applied_and_passed": sum(r["passed"] for r in applied),
        "cases_ineligible_not_forced": len(ineligible),
        "cases_failed": len(failed),
        "note": ("future_date is metadata-only for E1-E4. correct_content_wrong_date also "
                 "duplicates gold text; the 0d variant is the duplication-only control. "
                 "Ineligible cases are not forced into the benchmark."),
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== PILOT ATTACK VALIDATION (real pool) ===")
    for m in mapping:
        print(f"[{m['pilot_index']}] {m['query'][:70]!r} <-> {m['payload_id']} "
              f"(shared: {', '.join(m['shared_words'][:4])})")
        print(f"     question {m['question_ts']} | gold {m['latest_gold_timestamp']} | "
              f"payload {m['payload_timestamp']}")
    print(f"Cases: {len(results)}  applied+passed: {report['cases_applied_and_passed']}  "
          f"ineligible (not forced): {len(ineligible)}  failed: {len(failed)}")
    for r in ineligible:
        print(f"  ineligible: pilot {r['pilot_index']} {r['condition']} x{r['poison_count']} ({r.get('reason')})")
    for r in failed:
        bad = [k for k, v in r.get("checks", {}).items() if not v]
        print(f"  FAILED: pilot {r['pilot_index']} {r['condition']} x{r['poison_count']} "
              f"{r.get('status')} {bad or r.get('error') or r.get('note')}")
    for p in problems:
        print("  PAYLOAD PROBLEM:", p)
    print(f"Report: {REPORT_PATH}")

    if failed or problems:
        print("Validation did not pass. See the report.")
        raise SystemExit(1)
    print("All pilot conditions validated.")


if __name__ == "__main__":
    main()