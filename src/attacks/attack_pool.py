"""Deterministic construction of Week-5 poisoned StreamingQA pools.

This module operates on the frozen chunked StreamingQA schema.

Design principles:
- Never modify the clean input file in place.
- Never alter query or ground-truth answer fields.
- Never replace a gold/source chunk.
- Preserve candidate cardinality.
- Make every poisoning operation explicit and traceable.
- Do not invent fabricated claims inside this module.
- Use deterministic random selection controlled by a seed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .attack_specs import AttackType, get_attack_spec


Candidate = Dict[str, Any]
Record = Dict[str, Any]


REQUIRED_RECORD_FIELDS = {
    "query",
    "gold_answer",
    "gold_aliases",
    "candidates",
    "question_ts",
    "gold_chunk_ids",
    "gold_validated",
}

REQUIRED_CANDIDATE_FIELDS = {
    "doc_id",
    "text",
    "timestamp",
    "is_source_document",
}


def _stable_seed(base_seed: int, record_index: int, attack_type: str) -> int:
    """Create a reproducible per-record seed."""
    payload = f"{base_seed}|{record_index}|{attack_type}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return int(digest[:16], 16)


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO timestamp into a timezone-aware datetime."""
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _format_timestamp(dt: datetime) -> str:
    """Format timestamp consistently as ISO-8601 UTC."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_record(record: Mapping[str, Any]) -> None:
    """Validate the frozen chunked-pool schema."""
    missing = REQUIRED_RECORD_FIELDS - set(record)
    if missing:
        raise ValueError(
            f"Record is missing required fields: {sorted(missing)}"
        )

    if not isinstance(record["candidates"], list):
        raise TypeError("'candidates' must be a list")

    if not isinstance(record["gold_chunk_ids"], list):
        raise TypeError("'gold_chunk_ids' must be a list")

    for candidate in record["candidates"]:
        missing_candidate = REQUIRED_CANDIDATE_FIELDS - set(candidate)
        if missing_candidate:
            raise ValueError(
                "Candidate is missing required fields: "
                f"{sorted(missing_candidate)}"
            )


def _gold_ids(record: Mapping[str, Any]) -> set[str]:
    """Return the immutable set of gold chunk IDs."""
    return {str(x) for x in record["gold_chunk_ids"]}


def _candidate_index(record: Mapping[str, Any]) -> Dict[str, Candidate]:
    """Index candidates by their chunk-level ID."""
    return {
        str(candidate["doc_id"]): candidate
        for candidate in record["candidates"]
    }


def _is_gold(candidate: Candidate, gold_ids: set[str]) -> bool:
    """Return whether a candidate is part of the validated gold evidence."""
    return str(candidate["doc_id"]) in gold_ids


def _query_tokens(query: str) -> set[str]:
    """Simple deterministic tokenization for attack eligibility only."""
    tokens = []
    for token in query.lower().split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 3:
            tokens.append(cleaned)
    return set(tokens)


def _text_overlap(query: str, text: str) -> float:
    """Compute simple token overlap used only for selecting attack sources."""
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return 0.0

    text_tokens = set()
    for token in text.lower().split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 3:
            text_tokens.add(cleaned)

    return len(query_tokens & text_tokens) / len(query_tokens)


def _select_stale_candidate(
    record: Mapping[str, Any],
    *,
    rng: random.Random,
    min_age_days: int = 30,
) -> Optional[Candidate]:
    """Select an explicit old, non-gold candidate.

    The candidate must:
    - not be gold evidence;
    - have a parseable timestamp;
    - precede the question reference time by at least min_age_days;
    - have some lexical topical overlap with the query.

    A candidate is not called 'stale' merely because it is old.
    """

    question_dt = _parse_timestamp(record["question_ts"])
    if question_dt is None:
        return None

    gold_ids = _gold_ids(record)

    eligible = []
    for candidate in record["candidates"]:
        if _is_gold(candidate, gold_ids):
            continue

        candidate_dt = _parse_timestamp(candidate["timestamp"])
        if candidate_dt is None:
            continue

        age_days = (question_dt - candidate_dt).total_seconds() / 86400.0
        if age_days < min_age_days:
            continue

        overlap = _text_overlap(record["query"], candidate["text"])
        if overlap <= 0:
            continue

        eligible.append((overlap, age_days, candidate))

    if not eligible:
        return None

    # Prefer topical relevance first, then greater age.
    eligible.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True,
    )

    # Keep deterministic but avoid always selecting the exact same record
    # when several candidates are effectively equivalent.
    best_overlap = eligible[0][0]
    top = [
        item for item in eligible
        if item[0] >= max(0.01, best_overlap - 0.05)
    ]

    return rng.choice(top)[2]


def _select_replaceable_candidate(
    record: Mapping[str, Any],
    *,
    rng: random.Random,
) -> Optional[int]:
    """Select a non-gold candidate position for replacement."""
    gold_ids = _gold_ids(record)

    eligible = [
        index
        for index, candidate in enumerate(record["candidates"])
        if not _is_gold(candidate, gold_ids)
    ]

    if not eligible:
        return None

    return rng.choice(eligible)


def _replace_candidate(
    record: Record,
    *,
    target_index: int,
    poison_candidate: Candidate,
) -> None:
    """Replace one non-gold candidate while preserving candidate count."""
    original = record["candidates"][target_index]

    replacement = copy.deepcopy(poison_candidate)

    # Keep the target's slot identity unique and traceable.
    replacement["doc_id"] = str(original["doc_id"])

    # This is deliberately false for an injected poison.
    replacement["is_source_document"] = False

    record["candidates"][target_index] = replacement


def _make_future_timestamp(
    timestamp: Any,
    question_ts: Any,
    *,
    days_after: int,
) -> Optional[str]:
    """Move a candidate timestamp into the future relative to the query."""
    candidate_dt = _parse_timestamp(timestamp)
    question_dt = _parse_timestamp(question_ts)

    if candidate_dt is None or question_dt is None:
        return None

    shifted = max(
        candidate_dt,
        question_dt,
    )

    shifted = shifted.replace(
        microsecond=0,
    )

    from datetime import timedelta

    shifted = shifted + timedelta(days=days_after)

    return _format_timestamp(shifted)


def _apply_future_date(
    record: Record,
    *,
    rng: random.Random,
    days_after: int = 7,
) -> Optional[Dict[str, Any]]:
    """Apply a metadata timestamp shift to one non-gold candidate."""
    target_index = _select_replaceable_candidate(record, rng=rng)
    if target_index is None:
        return None

    target = record["candidates"][target_index]

    shifted_timestamp = _make_future_timestamp(
        target["timestamp"],
        record["question_ts"],
        days_after=days_after,
    )

    if shifted_timestamp is None:
        return None

    original_timestamp = target["timestamp"]
    target["timestamp"] = shifted_timestamp

    return {
        "target_index": target_index,
        "original_timestamp": original_timestamp,
        "shifted_timestamp": shifted_timestamp,
    }


def _apply_duplicate_fresh(
    record: Record,
    *,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    """Duplicate a non-gold temporally recent candidate.

    This does not fabricate content. It tests whether repetition alone
    increases the influence of an existing fresh-looking passage.
    """
    question_dt = _parse_timestamp(record["question_ts"])
    if question_dt is None:
        return None

    gold_ids = _gold_ids(record)

    eligible = []

    for index, candidate in enumerate(record["candidates"]):
        if _is_gold(candidate, gold_ids):
            continue

        candidate_dt = _parse_timestamp(candidate["timestamp"])
        if candidate_dt is None:
            continue

        age_days = (
            question_dt - candidate_dt
        ).total_seconds() / 86400.0

        # Candidate must be no more than 30 days old relative to query time.
        if 0 <= age_days <= 30:
            eligible.append((index, candidate, age_days))

    if not eligible:
        return None

    source_index, source, _ = rng.choice(eligible)

    target_index = _select_replaceable_candidate(record, rng=rng)
    if target_index is None:
        return None

    if target_index == source_index:
        return None

    duplicate = copy.deepcopy(source)

    # Preserve the candidate slot ID so the candidate count and slot
    # accounting remain stable.
    duplicate["doc_id"] = record["candidates"][target_index]["doc_id"]
    duplicate["is_source_document"] = False

    record["candidates"][target_index] = duplicate

    return {
        "source_index": source_index,
        "target_index": target_index,
        "source_doc_id": source["doc_id"],
    }


def _apply_stale_evidence(
    record: Record,
    *,
    rng: random.Random,
    min_age_days: int = 30,
) -> Optional[Dict[str, Any]]:
    """Amplify an explicitly old and topically relevant candidate."""
    source = _select_stale_candidate(
        record,
        rng=rng,
        min_age_days=min_age_days,
    )

    if source is None:
        return None

    target_index = _select_replaceable_candidate(record, rng=rng)
    if target_index is None:
        return None

    poison = copy.deepcopy(source)

    original_target = record["candidates"][target_index]

    poison["doc_id"] = original_target["doc_id"]
    poison["is_source_document"] = False

    record["candidates"][target_index] = poison

    return {
        "target_index": target_index,
        "source_doc_id": source["doc_id"],
        "source_timestamp": source["timestamp"],
    }


def _apply_fabricated_fresh(
    record: Record,
    *,
    rng: random.Random,
    payload: Mapping[str, Any],
) -> Optional[Dict[str, Any]]:
    """Insert an explicitly supplied fabricated-fresh evidence payload.

    The false claim must be supplied externally. This function deliberately
    does not invent a claim from the gold answer.
    """
    if "text" not in payload:
        raise ValueError(
            "fabricated_fresh payload requires an explicit 'text' field"
        )

    if "timestamp" not in payload:
        raise ValueError(
            "fabricated_fresh payload requires an explicit 'timestamp' field"
        )

    target_index = _select_replaceable_candidate(record, rng=rng)
    if target_index is None:
        return None

    poison = {
        "doc_id": record["candidates"][target_index]["doc_id"],
        "text": str(payload["text"]),
        "timestamp": str(payload["timestamp"]),
        "is_source_document": False,
    }

    record["candidates"][target_index] = poison

    return {
        "target_index": target_index,
        "payload_id": payload.get("payload_id"),
        "timestamp": poison["timestamp"],
    }


def apply_attack(
    record: Mapping[str, Any],
    *,
    attack_type: AttackType,
    seed: int,
    poison_payload: Optional[Mapping[str, Any]] = None,
    min_stale_age_days: int = 30,
    future_days: int = 7,
) -> tuple[Record, Dict[str, Any]]:
    """Apply one attack condition to one clean record.

    Returns:
        (attacked_record, attack_metadata)

    If the attack is not scientifically eligible for the record,
    the original record is returned unchanged and metadata contains
    ``eligible=False``.
    """
    _validate_record(record)

    get_attack_spec(attack_type)

    attacked = copy.deepcopy(dict(record))
    rng = random.Random(seed)

    before_count = len(attacked["candidates"])

    metadata: Dict[str, Any] = {
        "attack_type": attack_type,
        "seed": seed,
        "eligible": False,
        "applied": False,
    }

    if attack_type == "stale_evidence":
        details = _apply_stale_evidence(
            attacked,
            rng=rng,
            min_age_days=min_stale_age_days,
        )

    elif attack_type == "fabricated_fresh":
        if poison_payload is None:
            raise ValueError(
                "fabricated_fresh requires an explicit poison_payload"
            )

        details = _apply_fabricated_fresh(
            attacked,
            rng=rng,
            payload=poison_payload,
        )

    elif attack_type == "future_date":
        details = _apply_future_date(
            attacked,
            rng=rng,
            days_after=future_days,
        )

    elif attack_type == "duplicate_fresh":
        details = _apply_duplicate_fresh(
            attacked,
            rng=rng,
        )

    else:
        raise ValueError(f"Unsupported attack type: {attack_type}")

    if details is None:
        metadata["reason"] = "no_eligible_target"

        attacked["attack_condition"] = attack_type
        attacked["attack_metadata"] = metadata

        return attacked, metadata
    
    after_count = len(attacked["candidates"])

    if after_count != before_count:
        raise AssertionError(
            "Attack changed candidate cardinality: "
            f"{before_count} -> {after_count}"
        )

    # Ground truth must remain byte-for-byte equivalent at the logical
    # field level.
    for field in (
        "query",
        "gold_answer",
        "gold_aliases",
        "question_ts",
        "gold_chunk_ids",
        "gold_validated",
    ):
        if attacked[field] != record[field]:
            raise AssertionError(
                f"Attack illegally modified ground-truth field: {field}"
            )

    # No gold chunk may have been modified into poison.
    gold_ids = _gold_ids(record)

    for candidate in attacked["candidates"]:
        if candidate["doc_id"] in gold_ids and not candidate["is_source_document"]:
            raise AssertionError(
                f"Gold chunk lost source status: {candidate['doc_id']}"
            )

    metadata.update(
        {
            "eligible": True,
            "applied": True,
            "details": details,
            "candidate_count_before": before_count,
            "candidate_count_after": after_count,
        }
    )

    attacked["attack_condition"] = attack_type
    attacked["attack_metadata"] = metadata

    return attacked, metadata


def generate_attacked_records(
    records: Iterable[Mapping[str, Any]],
    *,
    attack_type: AttackType,
    seed: int = 42,
    poison_payloads: Optional[Mapping[str, Mapping[str, Any]]] = None,
    min_stale_age_days: int = 30,
    future_days: int = 7,
) -> List[Record]:
    """Generate an attacked copy of every supplied record."""
    output: List[Record] = []

    for index, record in enumerate(records):
        per_record_seed = _stable_seed(
            seed,
            index,
            attack_type,
        )

        payload = None
        if poison_payloads is not None:
            payload = poison_payloads.get(str(index))

        attacked, _ = apply_attack(
            record,
            attack_type=attack_type,
            seed=per_record_seed,
            poison_payload=payload,
            min_stale_age_days=min_stale_age_days,
            future_days=future_days,
        )

        attacked["attack_record_index"] = index
        output.append(attacked)

    return output


def load_jsonl(path: str | Path) -> List[Record]:
    """Load records from JSONL."""
    path = Path(path)

    records: List[Record] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at {path}:{line_number}"
                ) from exc

            _validate_record(record)
            records.append(record)

    return records


def write_jsonl(
    records: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> None:
    """Write attacked records to JSONL."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=False,
                )
                + "\n"
            )