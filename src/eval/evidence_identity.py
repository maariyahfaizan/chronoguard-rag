"""Derived evidence identity v1: pure encodings and an in-memory prototype.

No file I/O, extraction, gold matching, or changes to the raw integrity contract.
See docs/w6_r19_evidence_identity_v1.md for the normative schema.
"""
from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re

SCHEMA_VERSION = "chronoguard-evidence-identity/v1"
_DOMAIN = SCHEMA_VERSION.encode("ascii") + b"\x00"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z"
)


def _string(value: object, name: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, str) or (nonempty and not value):
        raise ValueError(f"{name} must be {'a nonempty' if nonempty else 'a'} string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain Unicode scalar values") from exc


def validate_timestamp(value: str) -> None:
    """Require a real UTC RFC3339 date/time, preserving its original spelling."""
    _string(value, "timestamp")
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError("timestamp must be UTC RFC3339 (Z or +00:00; up to 6 fractional digits)")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp contains an invalid date or time") from exc


@dataclass(frozen=True)
class EvidenceRecord:
    upstream_passage_id: str
    text: bytes
    timestamp: str
    evidence_fields: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _string(self.upstream_passage_id, "upstream_passage_id", nonempty=True)
        if type(self.text) is not bytes:
            raise ValueError("text must be immutable bytes")
        validate_timestamp(self.timestamp)
        if type(self.evidence_fields) is not tuple:
            raise ValueError("evidence_fields must be a tuple of string pairs")
        names = set()
        for pair in self.evidence_fields:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("evidence_fields must contain string pairs")
            name, value = pair
            _string(name, "evidence field name", nonempty=True)
            _string(value, "evidence field value")
            if name in names:
                raise ValueError("duplicate evidence field name")
            names.add(name)
        object.__setattr__(self, "evidence_fields", tuple(sorted(self.evidence_fields)))


def record_from_mapping(record: Mapping) -> EvidenceRecord:
    """Adapt the frozen JSON record schema without silently dropping extra fields.

    JSON text is strictly UTF-8 encoded; it cannot recover bytes lost upstream.
    Additional designated evidence fields must be supplied under evidence_fields.
    """
    required = {"doc_id", "text", "timestamp"}
    if not isinstance(record, Mapping):
        raise ValueError("record must be a mapping")
    if not required <= record.keys():
        raise ValueError("missing required fields: doc_id, text, timestamp")
    if record.keys() - (required | {"evidence_fields"}):
        raise ValueError("unknown record fields; explicitly designate evidence fields")
    _string(record["text"], "text")
    fields = record.get("evidence_fields", {})
    if not isinstance(fields, Mapping):
        raise ValueError("evidence_fields must be a mapping of strings to strings")
    return EvidenceRecord(record["doc_id"], record["text"].encode("utf-8"),
                          record["timestamp"], tuple(fields.items()))


def _encode(kind: str, payload: list) -> bytes:
    return _DOMAIN + kind.encode("ascii") + b"\x00" + json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False,
    ).encode("ascii")


def variant_encoding(record: EvidenceRecord) -> bytes:
    """Canonical preimage; text is RFC4648 padded standard Base64, never decoded."""
    return _encode("variant", [record.upstream_passage_id,
                               base64.b64encode(record.text).decode("ascii"),
                               record.timestamp, [list(pair) for pair in record.evidence_fields]])


def _identifier(kind: str, encoding: bytes) -> str:
    return f"cgei:v1:{kind}:{hashlib.sha256(encoding).hexdigest()}"


def variant_id(record: EvidenceRecord) -> str:
    return _identifier("variant", variant_encoding(record))


@dataclass(frozen=True, order=True)
class SourceOccurrence:
    artifact_sha256: str
    physical_line: int

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_sha256, str) or not _SHA256.fullmatch(self.artifact_sha256):
            raise ValueError("artifact_sha256 must be 64 lowercase hexadecimal characters")
        if type(self.physical_line) is not int or self.physical_line < 1:
            raise ValueError("physical_line must be a positive integer (1-based)")


def occurrence_encoding(source: SourceOccurrence) -> bytes:
    return _encode("occurrence", [source.artifact_sha256, source.physical_line])


def occurrence_id(source: SourceOccurrence) -> str:
    return _identifier("occurrence", occurrence_encoding(source))


@dataclass(frozen=True)
class VariantGroup:
    variant_id: str
    record: EvidenceRecord
    occurrences: tuple[SourceOccurrence, ...]

    @property
    def occurrence_count(self) -> int:
        return len(self.occurrences)


@dataclass(frozen=True)
class UpstreamAlias:
    upstream_passage_id: str
    variants: tuple[VariantGroup, ...]

    @property
    def occurrence_count(self) -> int:
        return sum(v.occurrence_count for v in self.variants)

    @property
    def exact_duplicate_count(self) -> int:
        """Extra occurrences equal under the designated v1 evidence schema."""
        return self.occurrence_count - len(self.variants)

    @property
    def has_conflicting_variants(self) -> bool:
        return len(self.variants) > 1


def group_occurrences(
    records: Iterable[tuple[SourceOccurrence, EvidenceRecord]],
) -> tuple[UpstreamAlias, ...]:
    """Order-independent, lossless grouping for small fixtures only.

    Re-ingesting a source occurrence is an error, even with identical content.
    Upstream aliases are lookup groups, never claims of gold evidence recovery.
    """
    seen_sources: dict[str, SourceOccurrence] = {}
    variants: dict[str, tuple[EvidenceRecord, list[SourceOccurrence]]] = {}
    for source, record in records:
        oid = occurrence_id(source)
        if oid in seen_sources:
            if seen_sources[oid] != source:
                raise ValueError("occurrence SHA-256 collision")
            raise ValueError("source occurrence supplied more than once")
        seen_sources[oid] = source
        vid = variant_id(record)
        if vid in variants:
            old, occurrences = variants[vid]
            if variant_encoding(old) != variant_encoding(record):
                raise ValueError("variant SHA-256 collision")
            occurrences.append(source)
        else:
            variants[vid] = (record, [source])
    aliases: dict[str, list[VariantGroup]] = {}
    for vid, (record, occurrences) in variants.items():
        aliases.setdefault(record.upstream_passage_id, []).append(
            VariantGroup(vid, record, tuple(sorted(occurrences))))
    return tuple(UpstreamAlias(pid, tuple(sorted(groups, key=lambda v: v.variant_id)))
                 for pid, groups in sorted(aliases.items()))
