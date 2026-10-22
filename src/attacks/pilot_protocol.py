"""Single definition of the Week-5 development pilot attack protocol (v2).

Shared by scripts/validate_pilot_attacks.py, scripts/build_pilot_attack_pools.py
and scripts/check_pilot_pools.py so they cannot drift apart.

v2 (pre-Week-6 fixes) differs from the v1 pilot:
- payloads are paired by source_qa_id only (identity.py);
- per-question seeds come from source_qa_id, not file position;
- poison counts are nested (n=1 subset of n=2 subset of n=5);
- pools are written to a new folder; the v1 pools are legacy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from .attack_pool import _stable_seed
from .identity import PayloadIdentityError, index_by_source_qa_id, require_source_qa_id

ROOT = Path(__file__).resolve().parents[2]

PILOT_PATH = ROOT / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
# The ONLY payload file the active pipeline reads (supervisor item 8).
AUTHORITATIVE_PAYLOAD_PATH = (
    ROOT / "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl"
)
PAYLOAD_SCHEMA = "chronoguard.pilot_payload.v2"
POOL_DIR = ROOT / "data/processed/attack_pools/pilot_v2_nested"
PROTOCOL_VERSION = "week5_pilot_v2_nested"

BASE_SEED = 42
POISON_COUNTS = [1, 2, 5]

CONDITIONS: List[Dict[str, Any]] = [
    {"name": "stale_evidence", "attack_type": "stale_evidence", "kwargs": {}},
    {"name": "fabricated_fresh", "attack_type": "fabricated_fresh", "kwargs": {}},
    {"name": "future_date", "attack_type": "future_date", "kwargs": {}},
    {"name": "duplicate_fresh", "attack_type": "duplicate_fresh", "kwargs": {}},
    {"name": "correct_content_wrong_date_30d", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 30}},
    {"name": "correct_content_wrong_date_0d_control", "attack_type": "correct_content_wrong_date",
     "kwargs": {"wrong_date_days": 0}},
]
# Supervisor decision (Option A): no reviewed stale evidence exists for the
# three pilot questions, so stale_evidence is reported as ineligible.
STALE_INELIGIBLE_REASON = "no reviewed stale evidence available"
NOT_BUILT = {"stale_evidence"}
# Conditions that may legitimately be ineligible for a record (never forced).
MAY_BE_INELIGIBLE = {"stale_evidence", "duplicate_fresh"}


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_pilot_records(path: Path = PILOT_PATH) -> List[Dict[str, Any]]:
    """Load pilot records; every record must have a unique source_qa_id."""
    from .attack_pool import load_jsonl

    records = load_jsonl(path)
    index_by_source_qa_id(records, "pilot record")
    return records


def load_authoritative_payloads(path: Path = AUTHORITATIVE_PAYLOAD_PATH) -> Dict[str, Dict[str, Any]]:
    """Load the authoritative fabricated payloads, keyed by source_qa_id.

    Refuses any other file and any row that is not the v2 schema, so a legacy
    payload file can never be read silently.
    """
    if Path(path).resolve() != AUTHORITATIVE_PAYLOAD_PATH.resolve():
        raise PayloadIdentityError(
            f"{path} is not the authoritative payload file "
            f"({AUTHORITATIVE_PAYLOAD_PATH.relative_to(ROOT)})."
        )

    rows = read_jsonl(path)

    for row in rows:
        if row.get("payload_schema") != PAYLOAD_SCHEMA:
            raise PayloadIdentityError(
                f"payload {row.get('payload_id')!r} is not {PAYLOAD_SCHEMA}."
            )
        for key in ("payload_id", "source_qa_id", "query_sha256", "text", "timestamp"):
            if key not in row:
                raise PayloadIdentityError(f"payload is missing '{key}': {row}")

    return dict(index_by_source_qa_id(rows, "payload"))


def record_seed(record: Mapping[str, Any], attack_type: str) -> int:
    """Per-question seed derived from source_qa_id (position-independent)."""
    return _stable_seed(BASE_SEED, require_source_qa_id(record), attack_type)


def payload_kwargs(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """The payload fields passed to apply_attack."""
    return {key: payload[key] for key in ("payload_id", "source_qa_id", "query_sha256",
                                          "text", "timestamp")}


def nesting_problems(targets_by_count: Mapping[int, Sequence[int]]) -> List[str]:
    """Return problems if applied counts are not nested prefixes of each other.

    targets_by_count maps poison count -> target slot list, for the counts
    that were applied. n=1 must be the first slot of n=2, and n=2 the first
    two slots of n=5. A count that is ineligible is simply absent.
    """
    problems = []
    counts = sorted(targets_by_count)

    for small, big in zip(counts, counts[1:]):
        small_t = list(targets_by_count[small])
        big_t = list(targets_by_count[big])
        if big_t[:len(small_t)] != small_t:
            problems.append(f"n={small} slots {small_t} are not the first slots of n={big} {big_t}")

    return problems
