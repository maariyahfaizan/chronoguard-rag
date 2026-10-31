"""Offline synthetic construction tests; no real candidate data or models."""
import copy
from dataclasses import replace
import json

import pytest

from src.attacks.freshness_smoke import (
    FRESHNESS_HEADER, SYNTHETIC_EXAMPLES, build_conditions, canonical_jsonl,
    validate_conditions,
)
from src.eval.evidence_identity import EvidenceRecord, variant_id


@pytest.mark.parametrize("example", SYNTHETIC_EXAMPLES)
def test_exact_rendered_header_is_the_only_poison_difference(example):
    clean, neutral, fresh = build_conditions(example)
    assert FRESHNESS_HEADER == "Latest update:\n"
    # Slice only the declared leading header; no strip/replace/normalization.
    assert fresh["candidates"][1]["text"].startswith(FRESHNESS_HEADER)
    assert (fresh["candidates"][1]["text"][len(FRESHNESS_HEADER):]
            == neutral["candidates"][1]["text"] == example.incorrect_claim)
    assert (fresh["candidates"][1]["text"].encode("utf-8")[len(FRESHNESS_HEADER.encode("utf-8")):]
            == neutral["candidates"][1]["text"].encode("utf-8"))
    normalized = copy.deepcopy(fresh)
    normalized["candidates"][1]["text"] = normalized["candidates"][1]["text"][len(FRESHNESS_HEADER):]
    normalized["condition"] = "neutral_poison"
    normalized["freshness_cue"] = ""
    assert normalized == neutral  # Includes all IDs, metadata, answers and ordering.
    assert clean["candidates"] == neutral["candidates"][:1] == fresh["candidates"][:1]
    assert len(clean["candidates"]) == 1
    assert len(neutral["candidates"]) == len(fresh["candidates"]) == 2


def test_verbatim_evidence_identity_and_independent_outputs():
    example = replace(SYNTHETIC_EXAMPLES[0], correct_text="  Mira Vale\n\t café\r\n")
    before = copy.deepcopy(example)
    rows = build_conditions(example)
    for row in rows:
        assert row["candidates"][0]["text"].encode() == example.correct_text.encode()
        assert row["supporting_variant_id"] == variant_id(EvidenceRecord(
            example.source_qa_id + ":correct", example.correct_text.encode(), example.timestamp))
        assert row["original_answer"] == row["gold_answer"] == example.original_answer
        assert row["experiment_status"] == "construction_only_not_evaluated"
        assert row["provenance_status"] == "synthetic_no_historical_provenance_claim"
    rows[1]["candidates"][0]["source_metadata"]["origin"] = "changed"
    assert rows[0]["candidates"][0]["source_metadata"]["origin"] == "manually_authored_synthetic"
    assert rows[2]["candidates"][0]["source_metadata"]["origin"] == "manually_authored_synthetic"
    assert example == before


def test_determinism_serialization_and_position_independent_seeds():
    first = {e.source_qa_id: build_conditions(e) for e in SYNTHETIC_EXAMPLES}
    second = {e.source_qa_id: build_conditions(e) for e in reversed(SYNTHETIC_EXAMPLES)}
    assert first == second
    for example in SYNTHETIC_EXAMPLES:
        rows = first[example.source_qa_id]
        encoded = canonical_jsonl(rows)
        assert encoded == canonical_jsonl(build_conditions(example))
        assert [json.loads(line) for line in encoded.splitlines()] == rows
        assert "\r" not in encoded
        assert len({r["deterministic_seed"] for r in rows}) == 1
        assert rows[0]["deterministic_seed"] != build_conditions(example, seed=43)[0]["deterministic_seed"]


@pytest.mark.parametrize("changes", [
    {"source_qa_id": "eval-001639"}, {"query": " "},
    {"original_answer": "Orin Pike"}, {"incorrect_answer": "Mira Vale"},
    {"incorrect_claim": "Unspecified claim"},
    {"incorrect_claim": FRESHNESS_HEADER + SYNTHETIC_EXAMPLES[0].incorrect_claim},
    {"timestamp": "2020-02-30T00:00:00Z"}, {"correct_text": "No explicit answer"},
    {"query": "\ud800"},
])
def test_invalid_manual_specifications_fail(changes):
    with pytest.raises(ValueError):
        build_conditions(replace(SYNTHETIC_EXAMPLES[0], **changes))


@pytest.mark.parametrize("seed", [True, -1, 1.2, "42", None])
def test_invalid_seeds_fail(seed):
    with pytest.raises(ValueError):
        build_conditions(SYNTHETIC_EXAMPLES[0], seed=seed)


@pytest.mark.parametrize("field,value", [
    ("doc_id", "changed"), ("timestamp", "2021-01-01T00:00:00Z"),
    ("text", FRESHNESS_HEADER + "Different claim"),
    ("is_source_document", True), ("source_metadata", {"origin": "changed"}),
])
def test_pair_validator_rejects_other_candidate_changes(field, value):
    example = SYNTHETIC_EXAMPLES[0]
    rows = build_conditions(example)
    rows[2]["candidates"][1][field] = value
    with pytest.raises(ValueError):
        validate_conditions(rows, example)


@pytest.mark.parametrize("mutation", ["order", "correct", "claim", "header", "condition"])
def test_validator_rejects_pairing_and_evidence_changes(mutation):
    example = SYNTHETIC_EXAMPLES[0]
    rows = build_conditions(example)
    if mutation == "order":
        rows[2]["candidates"].reverse()
    elif mutation == "correct":
        for row in rows:
            row["candidates"][0]["text"] += " "
    elif mutation == "claim":
        rows[2]["incorrect_claim"] += " "
    elif mutation == "header":
        rows[2]["candidates"][1]["text"] = example.incorrect_claim
    else:
        rows.reverse()
    with pytest.raises(ValueError):
        validate_conditions(rows, example)
