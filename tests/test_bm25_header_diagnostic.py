"""Synthetic controls and numerical checks; real scoring needs rank-bm25 0.2.2."""
import copy
import importlib.metadata
import json
import math

import pytest

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, build_conditions, canonical_jsonl
from src.eval import bm25_header_diagnostic as diagnostic

try:
    HAS_BM25 = importlib.metadata.version("rank-bm25") == "0.2.2"
except importlib.metadata.PackageNotFoundError:
    HAS_BM25 = False
real_bm25 = pytest.mark.skipif(not HAS_BM25, reason="rank-bm25==0.2.2 unavailable; no installation")


@pytest.mark.parametrize("example", SYNTHETIC_EXAMPLES)
def test_controls_preserve_everything_except_declared_header(example):
    before = copy.deepcopy(example)
    records = diagnostic.render_conditions(example)
    neutral = build_conditions(example)[1]
    assert records["neutral"] == neutral
    for condition, header in diagnostic.HEADERS.items():
        normalized = copy.deepcopy(records[condition])
        text = normalized["candidates"][1]["text"].encode("utf-8")
        assert text.startswith(header.encode("utf-8"))
        body = text[len(header.encode("utf-8")):]
        assert body == example.incorrect_claim.encode("utf-8")
        normalized["candidates"][1]["text"] = body.decode("utf-8")
        assert normalized == neutral
    assert example == before
    records["freshness"]["candidates"][0]["source_metadata"]["origin"] = "changed"
    assert records["neutral"] == neutral


@pytest.mark.parametrize("example", SYNTHETIC_EXAMPLES)
@pytest.mark.parametrize("tokenizer,length", [("frozen_space_split", 10), ("diagnostic_whitespace_split", 11)])
def test_equal_header_lengths_and_explicit_lexical_differences(example, tokenizer, length):
    records = diagnostic.render_conditions(example)
    lengths = [len(diagnostic.tokenize(records[c]["candidates"][1]["text"], tokenizer))
               for c in diagnostic.HEADERS]
    assert lengths == [9, length, length]
    assert len(diagnostic.tokenize(diagnostic.HEADERS["freshness"], tokenizer)) == 2
    assert len(diagnostic.tokenize(diagnostic.HEADERS["general_notice"], tokenizer)) == 2
    audit = diagnostic.lexical_audit(records)[tokenizer]
    assert audit["freshness_only_tokens"] != audit["general_only_tokens"]
    assert audit["freshness_query_overlap"] == audit["general_query_overlap"]
    if tokenizer == "frozen_space_split":
        assert "update:\nThe" in audit["freshness_only_tokens"]
        assert "notice:\nThe" in audit["general_only_tokens"]
    else:
        assert "update:" in audit["freshness_only_tokens"]


@pytest.mark.parametrize("change", ["timestamp", "ordering", "body", "correct", "metadata"])
def test_controls_reject_unintended_changes(change):
    records = diagnostic.render_conditions(SYNTHETIC_EXAMPLES[0])
    candidates = records["freshness"]["candidates"]
    if change == "ordering":
        candidates.reverse()
    elif change == "body":
        candidates[1]["text"] += " "
    elif change == "correct":
        candidates[0]["text"] += " "
    elif change == "metadata":
        candidates[1]["source_metadata"]["origin"] = "changed"
    else:
        candidates[1]["timestamp"] = "2021-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        diagnostic.validate_controls(records)


def test_independent_formula_negative_idf_repeated_and_missing_terms():
    stats, traces = diagnostic.independent_components([["x"], ["x"]], ["x", "missing", "x"])
    assert stats["raw_idf"]["x"] == pytest.approx(-math.log(5))
    assert stats["negative_idf_adjustment"] < 0
    for trace in traces:
        assert trace[1]["contribution"] == 0
        assert trace[0]["contribution"] == pytest.approx(-0.25 * math.log(5))
        assert sum(t["contribution"] for t in trace) == pytest.approx(-0.5 * math.log(5))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.01])
def test_numerical_mismatch_is_rejected(value):
    with pytest.raises(ValueError):
        diagnostic._close(1.0, value)


def test_tolerance_is_explicit():
    diagnostic._close(1.0, 1.0 + 1e-13)
    assert diagnostic.ABS_TOL == diagnostic.REL_TOL == 1e-12


def test_inventory_detects_changes_and_preserves_checksum_files(tmp_path):
    (tmp_path / "results.jsonl").write_bytes(b"original\n")
    (tmp_path / "sha256.json").write_bytes(b"pinned checksum record\n")
    before = diagnostic.inventory(tmp_path)
    assert before == diagnostic.inventory(tmp_path)
    assert set(before) == {"results.jsonl", "sha256.json"}
    (tmp_path / "results.jsonl").write_bytes(b"changed\n")
    assert before != diagnostic.inventory(tmp_path)


@pytest.mark.parametrize("relative", ["prior", "prior/child", "."])
def test_overlapping_or_existing_output_rejected(tmp_path, relative):
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "results.jsonl").write_bytes(b"original")
    with pytest.raises(ValueError, match="new and non-overlapping"):
        diagnostic.execute(prior, tmp_path / relative)
    assert (prior / "results.jsonl").read_bytes() == b"original"


def test_output_repeat_and_prior_integrity_checks_without_scoring(tmp_path, monkeypatch):
    """I/O bookkeeping only; placeholder rows are not retrieval measurements."""
    prior, out = tmp_path / "prior", tmp_path / "out"
    prior.mkdir()
    (prior / "results.jsonl").write_bytes(b"original")
    monkeypatch.setattr(diagnostic, "run_diagnostic", lambda: [{"test_only": True}])
    monkeypatch.setattr(diagnostic, "validate_results", lambda rows: None)
    summary, hashes = diagnostic.execute(prior, out)
    assert summary["prior_sha256_before"] == summary["prior_sha256_after"]
    assert summary["repeat_identical"] is True
    assert set(hashes) == {"results.jsonl", "validation.json"}
    assert (prior / "results.jsonl").read_bytes() == b"original"
    with pytest.raises(ValueError):
        diagnostic.execute(prior, out)


def test_prior_change_during_run_refuses_output(tmp_path, monkeypatch):
    prior, out = tmp_path / "prior", tmp_path / "out"
    prior.mkdir()
    p = prior / "results.jsonl"
    p.write_bytes(b"original")
    def changed():
        p.write_bytes(b"external change")
        return [{"test_only": True}]
    monkeypatch.setattr(diagnostic, "run_diagnostic", changed)
    with pytest.raises(ValueError, match="prior results changed"):
        diagnostic.execute(prior, out)
    assert not out.exists()


def test_repeat_mismatch_refuses_output(tmp_path, monkeypatch):
    prior, out = tmp_path / "prior", tmp_path / "out"
    prior.mkdir()
    (prior / "results.jsonl").write_bytes(b"original")
    counter = iter([1, 2])
    monkeypatch.setattr(diagnostic, "run_diagnostic", lambda: [{"test_only": next(counter)}])
    with pytest.raises(ValueError, match="repeat serialization mismatch"):
        diagnostic.execute(prior, out)
    assert not out.exists()


@real_bm25
@pytest.mark.parametrize("example", SYNTHETIC_EXAMPLES)
@pytest.mark.parametrize("tokenizer", diagnostic.TOKENIZERS)
def test_real_contributions_and_general_notice_contrast(example, tokenizer):
    records = diagnostic.render_conditions(example)
    saved = copy.deepcopy(records)
    measured = {c: diagnostic.measure(example, c, r, tokenizer) for c, r in records.items()}
    assert records == saved
    for row in measured.values():
        for p in row["original_outputs"]:
            assert math.isclose(sum(t["contribution"] for t in p["query_token_contributions"]),
                                p["score"], rel_tol=1e-12, abs_tol=1e-12)
    # The structurally matched headers should give equal scores for these inputs.
    difference = diagnostic.comparison(measured["general_notice"], measured["freshness"])
    assert all(abs(p["score_delta"]) <= 1e-12 for p in difference["passage_deltas"])


@real_bm25
def test_real_frozen_outputs_match_and_ties_remain_visible():
    from src.retrieval.bm25 import retrieve_best
    example = SYNTHETIC_EXAMPLES[0]
    records = diagnostic.render_conditions(example)
    record = records["neutral"]
    measured = diagnostic.measure(example, "neutral", record, "frozen_space_split")
    expected = retrieve_best(record["query"], [p["text"] for p in record["candidates"]], top_k=20)
    assert [(p["candidate_index"], p["text"], p["score"]) for p in measured["original_outputs"]] == expected
    assert all(p["score_tied"] for p in measured["original_outputs"])
    assert all(p["score"] < 0 for p in measured["original_outputs"])


@real_bm25
def test_real_schema_repeatability_and_failure_detection():
    rows = diagnostic.run_diagnostic()
    assert canonical_jsonl(rows) == canonical_jsonl(diagnostic.run_diagnostic())
    diagnostic.validate_results([json.loads(line) for line in canonical_jsonl(rows).splitlines()])
    assert len(rows) == 25
    corrupt = copy.deepcopy(rows)
    measurement = next(r for r in corrupt if r["kind"] == "measurement")
    measurement["original_outputs"][0]["score"] += 1
    with pytest.raises(ValueError):
        diagnostic.validate_results(corrupt)
