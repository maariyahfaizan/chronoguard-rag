"""Checkpoint 1: tiny offline fixtures; no corpus transformation or gold recovery."""
from dataclasses import replace
import hashlib
from itertools import permutations
import json
from pathlib import Path

import pytest

from src.eval import evidence_identity as identity
from src.eval.evidence_identity import (
    EvidenceRecord, SourceOccurrence, group_occurrences, occurrence_encoding,
    occurrence_id, record_from_mapping, variant_encoding, variant_id,
)


def record(**changes):
    return replace(EvidenceRecord("parent_0", b"Evidence.", "2008-09-22T00:00:00+00:00"), **changes)


def source(line=1, digest="a" * 64):
    return SourceOccurrence(digest, line)


def test_repeated_content_keeps_distinct_occurrences():
    r = record()
    sources = [source(1), source(2), source(1, "b" * 64)]
    alias, = group_occurrences((s, r) for s in sources)
    assert alias.occurrence_count == 3
    assert alias.exact_duplicate_count == 2
    assert not alias.has_conflicting_variants
    assert len(alias.variants) == 1
    assert alias.variants[0].occurrences == tuple(sorted(sources))
    assert len({occurrence_id(s) for s in sources}) == 3


@pytest.mark.parametrize("changed", [
    {"text": b"Different evidence."},
    {"timestamp": "2008-09-23T00:00:00+00:00"},
    {"timestamp": "2008-09-22T00:00:00Z"},
    {"evidence_fields": (("language", "en"),)},
])
def test_variant_changes_for_every_evidence_component(changed):
    a, b = record(), record(**changed)
    assert variant_id(a) != variant_id(b)
    alias, = group_occurrences([(source(1), a), (source(2), b), (source(3), b)])
    assert alias.has_conflicting_variants
    assert len(alias.variants) == 2
    assert alias.occurrence_count == 3
    assert alias.exact_duplicate_count == 1


def test_same_text_different_upstream_ids_remain_separate():
    a, b = record(), record(upstream_passage_id="other_0")
    assert variant_id(a) != variant_id(b)
    groups = group_occurrences([(source(1), a), (source(2), b)])
    assert len(groups) == 2
    assert all(not g.has_conflicting_variants for g in groups)


def test_determinism_across_runs_and_ordering():
    entries = [(source(3), record()), (source(1), record(text=b"Other")),
               (source(2), record()), (source(4), record(upstream_passage_id="other_0"))]
    expected = group_occurrences(entries)
    for ordering in permutations(entries):
        assert group_occurrences(ordering) == expected
        assert group_occurrences(iter(ordering)) == expected
    assert record(evidence_fields=(("z", "2"), ("a", "1"))) == record(
        evidence_fields=(("a", "1"), ("z", "2")))


def test_canonical_encoding_contract():
    r = EvidenceRecord("p_0", b"\x00\xff", "2008-09-22T00:00:00Z", (("z", "2"), ("a", "1")))
    expected = (b'chronoguard-evidence-identity/v1\x00variant\x00'
                b'["p_0","AP8=","2008-09-22T00:00:00Z",[["a","1"],["z","2"]]]')
    assert variant_encoding(r) == expected
    assert variant_id(r) == "cgei:v1:variant:" + hashlib.sha256(expected).hexdigest()
    encoded_source = (b'chronoguard-evidence-identity/v1\x00occurrence\x00["'
                      + b"a" * 64 + b'",1]')
    assert occurrence_encoding(source()) == encoded_source
    assert occurrence_id(source()) == "cgei:v1:occurrence:" + hashlib.sha256(encoded_source).hexdigest()


def test_serialization_boundaries_and_embedded_delimiters():
    pairs = [
        (record(upstream_passage_id="ab", text=b"c"), record(upstream_passage_id="a", text=b"bc")),
        (record(text=b"a\x00b"), record(text=b"ab")),
        (record(evidence_fields=(("ab", "c"),)), record(evidence_fields=(("a", "bc"),))),
        (record(text=b'"\\\n\t'), record(text=b'"\\\\n\\t')),
    ]
    for a, b in pairs:
        assert variant_encoding(a) != variant_encoding(b)
        assert variant_id(a) != variant_id(b)


@pytest.mark.parametrize("text", ["é", "e\u0301", "🙂", " Evidence. ", "Evidence.\r\n", "Evidence.\n", "\x00", ""])
def test_unicode_and_whitespace_round_trip(text):
    mapped = {"doc_id": "parent_0", "text": text, "timestamp": "2008-09-22T00:00:00Z"}
    r = record_from_mapping(mapped)
    assert r.text == text.encode("utf-8")
    assert r.text.decode("utf-8") == text


def test_unicode_normalization_is_never_applied():
    texts = ["é", "e\u0301", "A", "a", " a", "a ", "a\n", "a\r\n"]
    assert len({variant_id(record(text=t.encode())) for t in texts}) == len(texts)
    assert variant_id(record(text=b"\xff")) != variant_id(record(text="�".encode()))
    with pytest.raises(ValueError, match="scalar"):
        record_from_mapping({"doc_id": "p", "text": "\ud800", "timestamp": "2008-09-22T00:00:00Z"})


@pytest.mark.parametrize("field", ["doc_id", "text", "timestamp"])
def test_missing_required_fields(field):
    mapping = {"doc_id": "p", "text": "x", "timestamp": "2008-09-22T00:00:00Z"}
    del mapping[field]
    with pytest.raises(ValueError, match="missing required"):
        record_from_mapping(mapping)


@pytest.mark.parametrize("timestamp", [
    None, 123, "", "2008-09-22", "2008-09-22T00:00:00", "2008-09-22 00:00:00Z",
    "2008-02-30T00:00:00Z", "2008-13-22T00:00:00Z", "2008-09-22T24:00:00Z",
    "2008-09-22T00:00:60Z", "2008-09-22T00:00:00-00:00", "2008-09-22T01:00:00+01:00",
    "2008-09-22T00:00:00.1234567Z", "2008-09-22T00:00:00Z\n", "0000-01-01T00:00:00Z",
])
def test_malformed_or_out_of_contract_timestamps(timestamp):
    with pytest.raises(ValueError):
        record(timestamp=timestamp)


def test_fractional_timestamp_is_valid_but_not_normalized():
    a, b = record(timestamp="2008-09-22T00:00:00.0Z"), record(timestamp="2008-09-22T00:00:00.000000Z")
    assert variant_id(a) != variant_id(b)
    record(timestamp="2008-02-29T00:00:00Z")


@pytest.mark.parametrize("changes", [
    {"doc_id": ""}, {"doc_id": 1}, {"text": b"x"}, {"extra": "must not disappear"},
    {"evidence_fields": {"language": 1}}, {"evidence_fields": {"": "en"}},
    {"evidence_fields": {1: "en"}}, {"evidence_fields": None},
])
def test_adapter_rejects_undefined_fields_and_types(changes):
    mapping = {"doc_id": "p", "text": "x", "timestamp": "2008-09-22T00:00:00Z", **changes}
    with pytest.raises(ValueError):
        record_from_mapping(mapping)


def test_adapter_copies_designated_fields():
    fields = {"language": "en"}
    r = record_from_mapping({"doc_id": "p", "text": "x", "timestamp": "2008-09-22T00:00:00Z", "evidence_fields": fields})
    fields["language"] = "fr"
    assert r.evidence_fields == (("language", "en"),)
    with pytest.raises(ValueError, match="duplicate"):
        record(evidence_fields=(("x", "a"), ("x", "b")))
    with pytest.raises(ValueError):
        record(text=bytearray(b"mutable"))


@pytest.mark.parametrize("digest,line", [("A" * 64, 1), ("a" * 63, 1), ("g" * 64, 1), (None, 1), ("a" * 64, 0), ("a" * 64, True), ("a" * 64, 1.0)])
def test_invalid_source_coordinates(digest, line):
    with pytest.raises(ValueError):
        SourceOccurrence(digest, line)


@pytest.mark.parametrize("second", [record(), record(text=b"conflict")])
def test_same_source_cannot_be_ingested_twice(second):
    with pytest.raises(ValueError, match="more than once"):
        group_occurrences([(source(), record()), (source(), second)])


def test_hash_collision_fails_closed(monkeypatch):
    original = identity._identifier
    monkeypatch.setattr(identity, "_identifier", lambda kind, encoding: "forced" if kind == "variant" else original(kind, encoding))
    with pytest.raises(ValueError, match="variant SHA-256 collision"):
        group_occurrences([(source(1), record()), (source(2), record(text=b"different"))])


def test_occurrence_hash_collision_fails_closed(monkeypatch):
    original = identity._identifier
    monkeypatch.setattr(identity, "_identifier", lambda kind, encoding: "forced" if kind == "occurrence" else original(kind, encoding))
    with pytest.raises(ValueError, match="occurrence SHA-256 collision"):
        group_occurrences([(source(1), record()), (source(2), record())])


def test_variant_identity_is_independent_of_artifact_and_field_order():
    a = record(evidence_fields=(("z", "last"), ("a", "first")))
    b = record(evidence_fields=(("a", "first"), ("z", "last")))
    assert variant_id(a) == variant_id(b)
    alias, = group_occurrences([(source(1), a), (source(2, "b" * 64), b)])
    assert len(alias.variants) == 1
    assert alias.exact_duplicate_count == 1


def test_known_2008_conflict_fixture():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "w6_r19_2008_identity_conflict.json").read_text(encoding="utf-8"))
    longer, shorter = [record_from_mapping(r) for r in fixture["records"]]
    assert longer.upstream_passage_id == shorter.upstream_passage_id
    assert longer.text.startswith(shorter.text)
    assert longer.text[len(shorter.text):] == b" See the winners and losers of the Wall Street mess here."
    # Coordinates refer to an explicit two-line in-memory artifact, not the archive.
    artifact = b"".join((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8") for r in fixture["records"])
    digest = hashlib.sha256(artifact).hexdigest()
    alias, = group_occurrences([(source(1, digest), longer), (source(2, digest), shorter)])
    assert alias.has_conflicting_variants
    assert alias.exact_duplicate_count == 0
    assert {v.record.text for v in alias.variants} == {longer.text, shorter.text}
    assert group_occurrences([]) == ()
