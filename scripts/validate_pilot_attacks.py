#!/usr/bin/env python3
"""Validate every Week-5 pilot attack condition on the real pilot pools (protocol v2).

Run from the repo root:
    python scripts/validate_pilot_attacks.py

Reads (paths and conditions come from src/attacks/pilot_protocol.py):
    data/processed/attack_sources/streamingqa_attack_pilot.jsonl          (3 pilot records)
    data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl  (authoritative)

Writes:
    results/pilot_attack_validation.json   (saved integrity report; exit code 1 on any failure)

Payloads are paired with pilot records ONLY by source_qa_id. The query hash is a
secondary check and shared content words a third. A deliberately mismatched pair
is also run and must be rejected.

Conditions: stale_evidence (ineligible: no reviewed stale evidence available),
fabricated_fresh, future_date (metadata-only negative control for E1-E4),
duplicate_fresh (may be ineligible for a record), correct_content_wrong_date at
wrong_date_days=30, and the same attack at wrong_date_days=0 (duplication-only
control). Poison counts 1, 2, 5, which must be nested per question and condition.
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

from src.attacks.attack_pool import _parse_timestamp, apply_attack  # noqa: E402
from src.attacks.identity import PayloadIdentityError, pair_payloads_by_id, query_sha256  # noqa: E402
from src.attacks.pilot_protocol import (  # noqa: E402
    AUTHORITATIVE_PAYLOAD_PATH,
    BASE_SEED,
    CONDITIONS,
    MAY_BE_INELIGIBLE,
    PILOT_PATH,
    POISON_COUNTS,
    PROTOCOL_VERSION,
    STALE_INELIGIBLE_REASON,
    load_authoritative_payloads,
    load_pilot_records,
    nesting_problems,
    payload_kwargs,
    record_seed,
)

REPORT_PATH = PROJECT_ROOT / "results/pilot_attack_validation.json"
PROTECTED_FIELDS = ["source_qa_id", "query", "gold_answer", "gold_aliases", "question_ts",
                    "gold_chunk_ids", "gold_validated"]


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


def iso(dt):
    return dt.isoformat() if dt else None


def validate_case(record, condition, count, payload):
    original = copy.deepcopy(record)
    attack_type = condition["attack_type"]
    kwargs = dict(
        attack_type=attack_type,
        seed=record_seed(record, attack_type),
        poison_count=count,
        **condition["kwargs"],
    )
    if attack_type == "fabricated_fresh":
        kwargs["poison_payload"] = payload_kwargs(payload)

    attacked, meta = apply_attack(record, **kwargs)
    again, meta_again = apply_attack(record, **kwargs)

    checks = {
        "input_unchanged": record == original,
        "fixed_seed_deterministic": attacked == again and meta == meta_again,
    }
    result = {
        "source_qa_id": record["source_qa_id"],
        "condition": condition["name"],
        "poison_count": count,
        "seed": kwargs["seed"],
    }

    if not meta["applied"]:
        checks["declined_pool_unchanged"] = attacked["candidates"] == original["candidates"]
        expected = condition["name"] in MAY_BE_INELIGIBLE
        reason = meta.get("reason")
        if condition["name"] == "stale_evidence":
            reason = STALE_INELIGIBLE_REASON
        result.update(status="ineligible" if expected else "UNEXPECTEDLY_INELIGIBLE",
                      reason=reason, checks=checks,
                      passed=expected and all(checks.values()))
        return result, None

    if condition["name"] == "stale_evidence":
        result.update(status="UNEXPECTEDLY_APPLIED", checks=checks, passed=False,
                      note="No stale evidence has been reviewed for the pilot; "
                           "stale_evidence must be ineligible.")
        return result, None

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
        checks["inserted_payload_id_matches_question"] = all(
            after[t].get("payload_source_qa_id") == record["source_qa_id"] for t in targets)
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
                  target_indices=targets, target_doc_ids=meta["target_doc_ids"])
    return result, attacked


def identity_self_test(records, payloads_by_id):
    """A deliberately mismatched payload-question pair must be rejected."""
    a, b = records[0], records[1]
    wrong = payload_kwargs(payloads_by_id[b["source_qa_id"]])
    try:
        apply_attack(a, attack_type="fabricated_fresh", seed=1, poison_payload=wrong)
    except PayloadIdentityError as exc:
        return {"record": a["source_qa_id"], "payload": wrong["payload_id"],
                "rejected": True, "error": str(exc)}
    return {"record": a["source_qa_id"], "payload": wrong["payload_id"], "rejected": False}


def main():
    records = load_pilot_records(PILOT_PATH)
    payloads_by_id = load_authoritative_payloads(AUTHORITATIVE_PAYLOAD_PATH)
    pairs = pair_payloads_by_id(records, payloads_by_id.values())

    mapping, problems, results, nesting = [], [], [], []

    for record, payload in pairs:
        shared = content_words(payload["text"]) & content_words(
            record["query"] + " " + record["gold_answer"])
        question_dt = _parse_timestamp(record["question_ts"])
        gold_ids = {str(x) for x in record["gold_chunk_ids"]}
        gold_dts = [_parse_timestamp(c["timestamp"]) for c in record["candidates"]
                    if str(c["doc_id"]) in gold_ids]
        latest_gold = max(d for d in gold_dts if d)
        payload_dt = _parse_timestamp(payload["timestamp"])

        entry = {
            "source_qa_id": record["source_qa_id"],
            "query": record["query"],
            "payload_id": payload["payload_id"],
            "payload_source_qa_id": payload["source_qa_id"],
            "ids_match": payload["source_qa_id"] == record["source_qa_id"],
            "query_sha256_match": payload["query_sha256"] == query_sha256(record["query"]),
            "shared_words": sorted(shared),
            "question_ts": iso(question_dt),
            "latest_gold_timestamp": iso(latest_gold),
            "payload_timestamp": iso(payload_dt),
            "payload_after_gold_evidence": bool(payload_dt and payload_dt > latest_gold),
            "payload_not_after_question": bool(payload_dt and payload_dt <= question_dt),
        }
        if not (entry["ids_match"] and entry["query_sha256_match"]):
            problems.append(f"{payload['payload_id']}: identity check failed.")
        if not shared:
            problems.append(f"{payload['payload_id']}: shares no content word with its question.")
        if not entry["payload_after_gold_evidence"]:
            problems.append(f"{payload['payload_id']}: payload timestamp is not later than the gold "
                            f"evidence ({iso(latest_gold)}).")
        if not entry["payload_not_after_question"]:
            problems.append(f"{payload['payload_id']}: payload timestamp {iso(payload_dt)} is after "
                            f"the question time {iso(question_dt)}.")
        mapping.append(entry)

    self_test = identity_self_test(records, payloads_by_id)
    if not self_test["rejected"]:
        problems.append("A deliberately mismatched payload-question pair was NOT rejected.")

    for record, payload in pairs:
        for condition in CONDITIONS:
            targets_by_count = {}
            for count in POISON_COUNTS:
                try:
                    result, _ = validate_case(record, condition, count, payload)
                except Exception as exc:  # report, do not crash
                    result = {"source_qa_id": record["source_qa_id"], "condition": condition["name"],
                              "poison_count": count, "status": "ERROR", "passed": False,
                              "error": f"{type(exc).__name__}: {exc}"}
                results.append(result)
                if result["status"] == "applied":
                    targets_by_count[count] = result["target_indices"]
            nest = nesting_problems(targets_by_count)
            nesting.append({"source_qa_id": record["source_qa_id"], "condition": condition["name"],
                            "targets_by_count": {str(k): v for k, v in targets_by_count.items()},
                            "nested": not nest, "problems": nest})
            problems.extend(f"{record['source_qa_id']} {condition['name']}: {p}" for p in nest)

    applied = [r for r in results if r["status"] == "applied"]
    ineligible = [r for r in results if r["status"] == "ineligible"]
    failed = [r for r in results if not r["passed"]]

    report = {
        "report_type": "pilot_attack_validation_real_pool",
        "protocol_version": PROTOCOL_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_state(),
        "base_seed": BASE_SEED,
        "seed_rule": "sha256(base_seed|source_qa_id|attack_type)[:16] per question and attack type",
        "poison_counts": POISON_COUNTS,
        "pilot_file": str(PILOT_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "pilot_file_sha256": sha256_file(PILOT_PATH),
        "payload_file": str(AUTHORITATIVE_PAYLOAD_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "payload_file_sha256": sha256_file(AUTHORITATIVE_PAYLOAD_PATH),
        "pairing_rule": "payload.source_qa_id == record.source_qa_id (query_sha256 secondary)",
        "payload_pairing_and_dates": mapping,
        "identity_mismatch_self_test": self_test,
        "nesting": nesting,
        "nesting_failures": sum(not n["nested"] for n in nesting),
        "payload_problems": problems,
        "cases_total": len(results),
        "cases_applied_and_passed": sum(r["passed"] for r in applied),
        "cases_ineligible_not_forced": len(ineligible),
        "cases_failed": len(failed),
        "note": ("future_date is metadata-only for E1-E4. correct_content_wrong_date also "
                 "duplicates gold text; the 0d variant is the duplication-only control and "
                 "uses the same slots as the 30d attack. stale_evidence is ineligible for all "
                 f"three pilot questions ({STALE_INELIGIBLE_REASON}). Ineligible cases are "
                 "not forced and are not attack failures."),
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== PILOT ATTACK VALIDATION (real pool, protocol v2) ===")
    for m in mapping:
        print(f"[{m['source_qa_id']}] {m['query'][:60]!r} <-> {m['payload_id']} "
              f"(ids match: {m['ids_match']}, hash match: {m['query_sha256_match']})")
    print(f"Mismatched-pair self-test rejected: {self_test['rejected']}")
    print(f"Nesting: {len(nesting) - report['nesting_failures']}/{len(nesting)} "
          "question x condition groups nested")
    print(f"Cases: {len(results)}  applied+passed: {report['cases_applied_and_passed']}  "
          f"ineligible (not forced): {len(ineligible)}  failed: {len(failed)}")
    for r in ineligible:
        print(f"  ineligible: {r['source_qa_id']} {r['condition']} x{r['poison_count']} ({r.get('reason')})")
    for r in failed:
        bad = [k for k, v in r.get("checks", {}).items() if not v]
        print(f"  FAILED: {r['source_qa_id']} {r['condition']} x{r['poison_count']} "
              f"{r.get('status')} {bad or r.get('error') or r.get('note')}")
    for p in problems:
        print("  PROBLEM:", p)
    print(f"Report: {REPORT_PATH}")

    if failed or problems:
        print("Validation did not pass. See the report.")
        raise SystemExit(1)
    print("All pilot conditions validated.")


if __name__ == "__main__":
    main()
