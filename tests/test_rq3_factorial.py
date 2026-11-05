import copy
from dataclasses import replace
from itertools import product

import pytest

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES
from src.attacks.matched_controls import canonical
from src.attacks.rq3_factorial import (
    LEVELS, audit_factorial, configuration, factorial, validate_factorial,
)
from src.eval.rq3_factorial_audit import reports


@pytest.mark.parametrize("example", SYNTHETIC_EXAMPLES)
def test_eight_cell_coverage_and_direct_presentation(example):
    cells = factorial(example)
    assert len(cells) == len({c["cell_id"] for c in cells}) == 8
    assert {tuple(c["factors"].values()) for c in cells} == set(product(*LEVELS))
    assert validate_factorial(cells, example)
    assert all(c["presentation"] == "DIRECT_BOTH_PASSAGES_NO_RETRIEVAL" for c in cells)
    assert all({p["role"] for p in c["passages"]} == {"correct", "incorrect"} for c in cells)


def test_date_swaps_headers_order_and_fixed_sources():
    e = SYNTHETIC_EXAMPLES[0]
    cells = factorial(e)
    for c in cells:
        assert sorted(p["assigned_date_label"] for p in c["passages"]) == c["date_pair"]
        for p in c["passages"]:
            assert p["assigned_date_label"] == c["date_pair"][p["role"] == c["factors"]["newer_looking"]]
            assert p["body"] == (e.correct_text if p["role"] == "correct" else e.incorrect_claim)
            assert p["doc_id"] == e.source_qa_id + ":" + p["role"]
            assert "NOT_AUTHENTICATED" in p["date_basis"]
        assert len({p["header"] for p in c["passages"]}) == 1
        first = "correct" if c["factors"]["passage_order"] == "correct_first" else "incorrect"
        assert c["passages"][0]["role"] == first
    assert len({canonical(c["generation"]) for c in cells}) == 1
    assert len({c["allocated_context_characters"] for c in cells}) == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "factor", "body", "date", "doc_id",
                                      "order", "header", "prompt", "settings", "question", "budget"])
def test_reject_missing_duplicate_or_confounded_cells(mutation):
    e = SYNTHETIC_EXAMPLES[0]
    cells = factorial(e)
    if mutation == "missing":
        cells.pop()
    elif mutation == "duplicate":
        cells[-1] = copy.deepcopy(cells[0])
    elif mutation == "factor":
        cells[0]["factors"]["newer_looking"] = "incorrect"
    elif mutation in ("body", "doc_id", "header"):
        cells[0]["passages"][0][mutation] += "changed"
    elif mutation == "date":
        cells[0]["passages"][0]["assigned_date_label"] = "2099-01-01"
    elif mutation == "order":
        cells[0]["passages"].reverse()
    elif mutation == "prompt":
        cells[0]["prompt"] = "Different instructions"
    elif mutation == "question":
        cells[0]["question"] = "Different question"
    elif mutation == "budget":
        cells[0]["allocated_context_characters"] -= 1
    else:
        cells[0]["generation"]["max_new_tokens"] = 99
    with pytest.raises(ValueError):
        validate_factorial(cells, e)


def test_visibility_lengths_and_unknown_token_balance():
    e = SYNTHETIC_EXAMPLES[0]
    audit = audit_factorial(factorial(e), e)
    assert audit["all_claims_complete"]
    assert audit["header_character_difference"] == 1
    assert not audit["rendered_prompt_character_lengths_equal"]
    assert audit["character_allocation_equal"]
    assert audit["token_level_balancing"] == "UNVERIFIED"
    for c in audit["cells"]:
        assert c["final_tokenized_input_visibility"] == "UNKNOWN"
        assert all(p["generator_tokens"] == "UNKNOWN" for p in c["passages"])
        assert all(p["bm25_literal_space_tokens"] > 0 for p in c["passages"])


def test_asymmetric_truncation_and_changed_visibility_across_cells():
    e = SYNTHETIC_EXAMPLES[1]
    full = factorial(e)
    # Between correct/incorrect body ends, with an additional header boundary.
    limit = len(full[0]["passages"][0]["rendered_text"])
    config = configuration()
    config["max_passage_chars"] = limit
    audit = audit_factorial(factorial(e, generation=config), e, generation=config)
    assert not audit["all_claims_complete"]
    assert any("ASYMMETRIC_CLAIM_TRUNCATION" in c["violations"] for c in audit["cells"])
    assert any("INCOMPLETE_EVIDENCE_CLAIM" in c["violations"] for c in audit["cells"])


@pytest.mark.parametrize("dates", [["2020-01-01", "2020-01-01"], ["2020-01-02", "2020-01-01"],
                                    ["not-a-date", "2020-01-02"], ["2020-01-01"],
                                    ["2020-01-01", "2020-02-31"]])
def test_invalid_date_cues(dates):
    with pytest.raises(ValueError):
        factorial(SYNTHETIC_EXAMPLES[0], dates=dates)


def test_non_synthetic_input_and_unsupported_revision():
    with pytest.raises(ValueError):
        factorial(replace(SYNTHETIC_EXAMPLES[0], source_qa_id="held-out"))
    config = configuration()
    config["revision"] = "other"
    with pytest.raises(ValueError):
        factorial(SYNTHETIC_EXAMPLES[0], generation=config)


def test_no_retrieval_or_generation_dependency(monkeypatch):
    import src.attacks.rq3_factorial as module
    import src.retrieval.bm25 as bm25
    import src.eval.offline_input_audit as observer
    def forbidden(*args, **kwargs):
        pytest.fail("isolated construction must not retrieve or enter model input execution")
    monkeypatch.setattr(bm25, "retrieve_best", forbidden)
    monkeypatch.setattr(observer, "capture_generate_boundary", forbidden)
    # Prompt assembly is pure; no retrieval loader or generate function is used.
    assert not hasattr(module, "retrieve_best")
    assert not hasattr(module, "generate_answer")
    a = reports()
    assert canonical(list(a)) == canonical(list(reports()))
    assert len(a[0]) == 16 and len(a[1]) == 2
    assert all(not r["retrieval_executed"] for r in a[1])


def test_audit_output_bytes_and_overwrite_rejection(tmp_path, monkeypatch):
    import src.eval.rq3_factorial_audit as writer
    monkeypatch.setattr(writer, "prerequisites", lambda: {"test_double": True})
    monkeypatch.setattr(writer, "backend_inventory", lambda: {"test_double": True})
    writer.write_reports(tmp_path / "a")
    writer.write_reports(tmp_path / "b")
    for file in (tmp_path / "a").iterdir():
        assert file.read_bytes() == (tmp_path / "b" / file.name).read_bytes()
    (tmp_path / "a" / "cells.jsonl").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError):
        writer.write_reports(tmp_path / "a")
