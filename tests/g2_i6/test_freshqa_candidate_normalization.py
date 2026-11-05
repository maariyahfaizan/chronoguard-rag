"""Reviewed fixture-only tests. No runners, model modules or real datasets."""
import copy
import sys

import pytest

from src.eval.no_execution_boundary import ExecutionBlocked
from src.eval.freshqa_candidate_normalization import (
    BLOCKED, ROOT, authorize_execution, digest, fixtures, legacy_structure_check,
    normalize, validate_normalized, write_synthetic,
)


def batch():
    records = fixtures()
    return records, {r["query_id"]: digest(r) for r in records}


def test_valid_synthetic_conversion_and_legacy_validator():
    originals, hashes = batch()
    before = copy.deepcopy(originals)
    out = normalize(originals, hashes)
    assert originals == before
    assert len(out) == 4
    assert validate_normalized(out, originals, hashes)["structural_only"]
    for r, original in zip(out, originals):
        assert r["query_id"] == original["query_id"]
        assert r["gold_answer"] == original["gold_answer"]
        assert r["gold_aliases"] == original["gold_aliases"]
        assert r["original_record"] == original
        assert r["source_record_sha256"] == digest(original)
        assert legacy_structure_check(r)["texts"] == original["candidates"]
        assert [c["source_metadata"] for c in r["candidates"]] == original["candidate_metadata"]
        assert r["execution_status"] == BLOCKED
        assert r["benchmark_eligibility"] == "NOT_REVIEWED"
        assert r["gold_validated"] is None


def test_source_flags_order_and_exact_dates():
    rows, hashes = batch()
    r = normalize(rows, hashes)[0]
    assert [c["is_source_document"] for c in r["candidates"]] == [True, False]
    assert [c["doc_id"] for c in r["candidates"]] == [m["doc_id"] for m in rows[0]["candidate_metadata"]]
    assert [c["timestamp"] for c in r["candidates"]] == [m["source_date"] for m in rows[0]["candidate_metadata"]]


def test_missing_dates_and_empty_metadata_remain_unknown():
    rows, hashes = batch()
    out = normalize(rows, hashes)
    for c in out[1]["candidates"]:
        assert c["timestamp"] is None and c["date_status"] == "MISSING"
    assert out[1]["question_ts"] is None  # effective_year never supplies a date
    for c in out[2]["candidates"]:
        assert c["doc_id"] is None and c["is_source_document"] is None
        assert c["source_flag_status"] == "UNKNOWN"
        assert c["alignment_status"] == "POSITIONAL_ONLY_UNVERIFIED"


def test_repeated_text_distinct_document_identities():
    rows, hashes = batch()
    a, b = normalize(rows, hashes)[3]["candidates"]
    assert a["text"] == b["text"] and a["text_sha256"] == b["text_sha256"]
    assert a["doc_id"] != b["doc_id"]


def test_determinism_and_mutable_container_isolation():
    rows, hashes = batch()
    a, b = normalize(rows, hashes), normalize(rows, hashes)
    assert a == b
    a[0]["original_record"]["gold_aliases"].append("changed")
    a[0]["candidates"][0]["source_metadata"]["title"] = "changed"
    assert rows == fixtures() and b == normalize(rows, hashes)


@pytest.mark.parametrize("change", ["length", "type", "metadata_type", "index", "flag", "duplicate_doc",
    "date", "date_conflict", "missing_answer", "aliases", "missing_dates_guess", "approval", "unknown_metadata"])
def test_invalid_or_rehashed_mutations_rejected(change):
    rows, hashes = batch()
    r = rows[0]
    if change == "length": r["candidate_metadata"].pop()
    elif change == "type": r["candidates"][0] = {"text": "unsupported dictionary input"}
    elif change == "metadata_type": r["candidate_metadata"][0] = []
    elif change == "index": r["candidate_metadata"][0]["index"] = 1
    elif change == "flag": r["candidate_metadata"][0]["is_source_document"] = "true"
    elif change == "duplicate_doc": r["candidate_metadata"][1]["doc_id"] = r["candidate_metadata"][0]["doc_id"]
    elif change == "date": r["candidate_metadata"][0]["source_date"] = "yesterday"
    elif change == "date_conflict": r["candidate_metadata"][0]["timestamp"] = "1999-01-01"
    elif change == "missing_answer": del r["gold_answer"]
    elif change == "aliases": r["gold_aliases"] = "two"
    elif change == "missing_dates_guess": r["candidate_metadata"][0]["source_date"] = "2020-12-31"
    elif change == "approval": r["approved"] = True
    else: r["candidate_metadata"][0]["provenance"] = "AUTHENTICATED"
    hashes[r["query_id"]] = digest(r)
    with pytest.raises(ValueError): normalize(rows, hashes)


def test_source_hash_mismatch():
    rows, hashes = batch()
    hashes[rows[0]["query_id"]] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"): normalize(rows, hashes)


def test_duplicate_qa_ids():
    rows, hashes = batch()
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate QA"): normalize(rows, hashes)


@pytest.mark.parametrize("qid", ["123", 123, "synthetic-freshqa-unknown"])
def test_real_and_unregistered_records_rejected(qid):
    rows, hashes = batch()
    rows[0]["query_id"] = qid
    with pytest.raises(ValueError, match="unregistered"): normalize(rows, hashes)


@pytest.mark.parametrize("field", ["text", "doc_id", "timestamp", "is_source_document"])
def test_normalized_output_drift_rejected(field):
    rows, hashes = batch()
    out = normalize(rows, hashes)
    out[0]["candidates"][0][field] = "altered"
    with pytest.raises(ValueError, match="drift"): validate_normalized(out, rows, hashes)


def test_reordering_is_not_lossless():
    rows, hashes = batch()
    out = normalize(rows, hashes)
    out[0]["candidates"].reverse()
    with pytest.raises(ValueError): validate_normalized(out, rows, hashes)


def test_execution_always_rejected():
    rows, hashes = batch()
    for r in normalize(rows, hashes):
        with pytest.raises(ValueError, match="no real or synthetic execution"): authorize_execution(r)


@pytest.mark.parametrize("path", ["data/processed/not_allowed.jsonl", "audits/g2_i5_v1/new.jsonl", "../escape.jsonl"])
def test_output_path_escape_rejected(path):
    rows, hashes = batch()
    with pytest.raises(ValueError, match="path"): write_synthetic(ROOT / path, normalize(rows, hashes), rows, hashes)


@pytest.mark.parametrize("operation", ["retrieval", "generation", "attack", "model_import", "network", "process", "judge", "statistics"])
def test_no_execution_tripwires(operation):
    guard = sys._chronoguard_g2_i6_boundary
    with pytest.raises(ExecutionBlocked): guard.probe(operation)
    assert guard.report()["profile_active"]
