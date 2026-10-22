"""Stable question identity for attack payloads (pre-Week-6 fix, item 1).

Every StreamingQA record used for attacks carries `source_qa_id`, the `qa_id`
copied verbatim from the frozen StreamingQA source. Every fabricated payload
carries the same `source_qa_id`. Payloads are paired with questions ONLY by
this identifier: never by file order or list index.

A SHA-256 of the query text may be stored on the payload (`query_sha256`) as a
secondary check. It never replaces the identifier.

Any missing identifier, duplicate identifier or mismatch raises
PayloadIdentityError immediately.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Mapping, Tuple

ID_FIELD = "source_qa_id"


class PayloadIdentityError(ValueError):
    """A payload cannot be proven to belong to the question it is paired with."""


def query_sha256(query: str) -> str:
    """Secondary-check hash of a query (whitespace-trimmed, UTF-8)."""
    return hashlib.sha256(str(query).strip().encode("utf-8")).hexdigest()


def require_source_qa_id(item: Mapping[str, Any], what: str = "record") -> str:
    """Return the item's source_qa_id, or raise if it is missing or blank."""
    value = item.get(ID_FIELD)

    if not isinstance(value, str) or not value.strip():
        raise PayloadIdentityError(
            f"{what} has no '{ID_FIELD}' (got {value!r}). Pairing by file "
            "order or index is not allowed."
        )

    return value


def check_payload_matches_record(
    record: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> None:
    """Fail unless payload.source_qa_id == record.source_qa_id.

    If the payload also stores query_sha256, it must match the record's query.
    """
    record_id = require_source_qa_id(record, "record")
    payload_id = require_source_qa_id(
        payload, f"payload {payload.get('payload_id')!r}"
    )

    if payload_id != record_id:
        raise PayloadIdentityError(
            f"payload {payload.get('payload_id')!r} has {ID_FIELD}="
            f"{payload_id!r} but the record has {ID_FIELD}={record_id!r}."
        )

    expected_hash = payload.get("query_sha256")

    if expected_hash is not None and expected_hash != query_sha256(record["query"]):
        raise PayloadIdentityError(
            f"payload {payload.get('payload_id')!r} matches {ID_FIELD} "
            f"{record_id!r} but its query_sha256 does not match the record's "
            "query text."
        )


def index_by_source_qa_id(
    items: Iterable[Mapping[str, Any]],
    what: str,
) -> Dict[str, Mapping[str, Any]]:
    """Map source_qa_id -> item, rejecting missing or duplicate identifiers."""
    indexed: Dict[str, Mapping[str, Any]] = {}

    for item in items:
        key = require_source_qa_id(item, what)

        if key in indexed:
            raise PayloadIdentityError(f"duplicate {ID_FIELD} {key!r} in {what}s")

        indexed[key] = item

    return indexed


def pair_payloads_by_id(
    records: Iterable[Mapping[str, Any]],
    payloads: Iterable[Mapping[str, Any]],
) -> List[Tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """Pair every record with exactly one payload by source_qa_id.

    The returned list follows the order of `records`; payload order is
    irrelevant. Raises if a record has no payload, a payload has no record,
    or any pair fails check_payload_matches_record.
    """
    records = list(records)
    by_id = index_by_source_qa_id(payloads, "payload")
    index_by_source_qa_id(records, "record")  # uniqueness check only

    pairs = []

    for record in records:
        key = require_source_qa_id(record, "record")

        if key not in by_id:
            raise PayloadIdentityError(f"no payload for {ID_FIELD} {key!r}")

        payload = by_id.pop(key)
        check_payload_matches_record(record, payload)
        pairs.append((record, payload))

    if by_id:
        raise PayloadIdentityError(
            f"payloads with no matching record: {sorted(by_id)}"
        )

    return pairs
