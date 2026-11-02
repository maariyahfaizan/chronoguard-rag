"""Synthetic bookkeeping tests; injected scores are never measured results."""
import copy
from dataclasses import replace
import json

import pytest

from src.attacks.freshness_smoke import (
    FRESHNESS_HEADER, SYNTHETIC_EXAMPLES, build_conditions, canonical_jsonl,
    validate_conditions,
)
from src.eval import freshness_ranking_smoke as smoke


def unavailable():
    return {name: {"status": "unavailable", "reason": "test: no dependencies"}
            for name in ("bm25", "dense", "hybrid")}


def test_unavailable_results_are_explicit_and_have_no_fabricated_scores():
    result = smoke.run_experiment({}, unavailable(), {"test_only": True})
    measurements = [r for r in result if r["kind"] == "measurement"]
    comparisons = [r for r in result if r["kind"] == "comparison"]
    assert len(measurements) == 6
    assert len(comparisons) == 18
    for row in measurements:
        assert all(v["status"] == "unavailable" for v in row["retrievers"].values())
        assert all("original_outputs" not in v for v in row["retrievers"].values())
    assert all(r["status"] == "unavailable" and "deltas" not in r for r in comparisons)


def test_original_ties_preserved_and_resolved_view_separate():
    candidates = build_conditions(SYNTHETIC_EXAMPLES[0])[1]["candidates"]
    outputs = [(1, candidates[1]["text"], 2.0), (0, candidates[0]["text"], 2.0)]
    saved = copy.deepcopy(outputs)
    view = smoke.ranking_view(outputs, candidates)
    assert outputs == saved
    assert view["original_order"] == [1, 0]
    assert view["deterministic_order"] == [0, 1]
    assert [r["original_rank"] for r in view["original_outputs"]] == [1, 2]
    assert [r["resolved_rank"] for r in view["original_outputs"]] == [2, 1]
    assert all(r["score_tied"] for r in view["original_outputs"])


@pytest.mark.parametrize("scores", [(2.0, 2.0 + 1e-12), (-2.0, -1.0)])
def test_near_ties_and_negative_scores_are_not_normalized(scores):
    candidates = build_conditions(SYNTHETIC_EXAMPLES[0])[1]["candidates"]
    outputs = [(i, c["text"], scores[i]) for i, c in enumerate(candidates)]
    view = smoke.ranking_view(outputs, candidates)
    assert view["deterministic_order"] == [1, 0]
    assert not any(r["score_tied"] for r in view["original_outputs"])
    assert [r["score"] for r in view["original_outputs"]] == list(scores)


@pytest.mark.parametrize("bad", ["duplicate", "missing", "wrong_text", "nan", "inf"])
def test_invalid_retriever_outputs_fail(bad):
    candidates = build_conditions(SYNTHETIC_EXAMPLES[0])[1]["candidates"]
    outputs = [(i, c["text"], 1.0) for i, c in enumerate(candidates)]
    if bad == "duplicate":
        outputs[1] = outputs[0]
    elif bad == "missing":
        outputs.pop()
    elif bad == "wrong_text":
        outputs[0] = (0, "modified", 1.0)
    else:
        outputs[0] = (0, candidates[0]["text"], float(bad))
    with pytest.raises(ValueError):
        smoke.ranking_view(outputs, candidates)


def fixture_dense(query, texts):
    """Deliberately artificial scores testing arithmetic only."""
    scores = [1.0] + ([3.0 if texts[1].startswith(FRESHNESS_HEADER) else 0.5] if len(texts) == 2 else [])
    return sorted([(i, text, scores[i]) for i, text in enumerate(texts)],
                  key=lambda x: -x[2])


def test_deltas_margins_and_absent_poison():
    result = smoke.run_experiment({"dense": fixture_dense}, unavailable(), {"test_only": True})
    comparisons = [r for r in result if r["kind"] == "comparison" and r["retriever"] == "dense"]
    paired = comparisons[0]
    assert paired["candidate_set_changed"] is False
    assert paired["deltas"][0]["score_delta"] == 0.0
    assert paired["deltas"][0]["original_rank_delta"] == 1
    assert paired["deltas"][1]["score_delta"] == 2.5
    assert paired["deltas"][1]["resolved_rank_delta"] == -1
    assert paired["reference_margin"] == -0.5
    assert paired["target_margin"] == 2.0
    assert paired["margin_delta"] == 2.5
    clean_comparison = comparisons[1]
    assert clean_comparison["candidate_set_changed"] is True
    assert clean_comparison["deltas"][1]["score_delta"] is None
    assert clean_comparison["reference_margin"] is None
    assert clean_comparison["margin_delta"] is None


def test_pairing_verbatim_utf8_inputs_and_deterministic_serialization(monkeypatch):
    example = replace(SYNTHETIC_EXAMPLES[0], correct_text="  Mira Vale\n café\r\n")
    rows = build_conditions(example)
    before = copy.deepcopy(rows)
    monkeypatch.setattr(smoke, "build_conditions", lambda *args, **kwargs: rows)
    first = smoke.run_experiment({"dense": fixture_dense}, unavailable(), {"test_only": True}, [example])
    second = smoke.run_experiment({"dense": fixture_dense}, unavailable(), {"test_only": True}, [example])
    assert rows == before
    assert canonical_jsonl(first) == canonical_jsonl(second)
    assert [json.loads(line) for line in canonical_jsonl(first).splitlines()] == first
    measured = [r["input"] for r in first if r["kind"] == "measurement"]
    validate_conditions(measured, example)
    assert (measured[2]["candidates"][1]["text"].encode()[len(FRESHNESS_HEADER.encode()):]
            == measured[1]["candidates"][1]["text"].encode())
    assert all(r["candidates"][0]["text"].encode() == example.correct_text.encode() for r in measured)


def test_pair_violation_rejected_before_retrieval(monkeypatch):
    rows = build_conditions(SYNTHETIC_EXAMPLES[0])
    rows[2]["candidates"][1]["timestamp"] = "2021-01-01T00:00:00Z"
    monkeypatch.setattr(smoke, "build_conditions", lambda *args, **kwargs: rows)
    with pytest.raises(ValueError, match="beyond"):
        smoke.run_experiment({}, unavailable(), {}, [SYNTHETIC_EXAMPLES[0]])


def test_corpus_statistics_include_exact_space_tokenization():
    clean, neutral, fresh = build_conditions(SYNTHETIC_EXAMPLES[0])
    a, b = smoke.corpus_statistics(neutral), smoke.corpus_statistics(fresh)
    assert a["document_count"] == b["document_count"] == 2
    assert b["space_split_lengths"][0] == a["space_split_lengths"][0]
    # split(' ') makes 'update:\nThe' one token: this is frozen behavior.
    assert "update:\nThe" in b["document_frequencies"]
    assert b["average_space_split_length"] != a["average_space_split_length"]
    assert smoke.corpus_statistics(clean)["document_count"] == 1


def test_hybrid_uses_declared_resolved_component_orders(monkeypatch):
    original_stats = smoke.corpus_statistics
    monkeypatch.setattr(smoke, "corpus_statistics", lambda row, *args: original_stats(row))
    def tied(query, texts):
        return [(i, texts[i], 1.0) for i in reversed(range(len(texts)))]
    def fixture_rrf(bm25, dense, top_k, rrf_k):
        assert [r[0] for r in bm25] == [r[0] for r in dense] == list(range(len(bm25)))
        assert top_k == 5 and rrf_k == 60
        return [(i, text, 2 / (rrf_k + rank)) for rank, (i, text, _) in enumerate(bm25, 1)]
    result = smoke.run_experiment({"bm25": tied, "dense": tied, "rrf": fixture_rrf},
                                  unavailable(), {"test_only": True})
    for row in (r for r in result if r["kind"] == "measurement"):
        assert row["retrievers"]["hybrid"]["component_orders"]["bm25"] == list(range(len(row["input"]["candidates"])))
        assert row["retrievers"]["hybrid"]["original_outputs"][0]["score"] == 2 / 61


def test_backend_failure_marks_hybrid_unavailable():
    def fail(*args):
        raise RuntimeError("test failure")
    result = smoke.run_experiment({"dense": fail}, unavailable(), {"test_only": True})
    for row in (r for r in result if r["kind"] == "measurement"):
        assert "test failure" in row["retrievers"]["dense"]["reason"]
        assert row["retrievers"]["hybrid"]["status"] == "unavailable"


def test_missing_dependencies_do_not_attempt_model_loading(tmp_path):
    environment = {"dependencies": {name: None for name in ("rank-bm25", "torch", "transformers", "huggingface-hub")}}
    backends, status = smoke.load_backends(environment, tmp_path)
    assert backends == {}
    assert all(v["status"] == "unavailable" for v in status.values())
    assert "loading not attempted" in status["dense"]["reason"]


@pytest.mark.skipif(smoke.importlib.metadata.packages_distributions().get("rank_bm25") is None,
                    reason="rank-bm25 not installed")
def test_real_bm25_matches_existing_original_outputs():
    from src.retrieval.bm25 import retrieve_best
    row = build_conditions(SYNTHETIC_EXAMPLES[0])[1]
    outputs = retrieve_best(row["query"], [c["text"] for c in row["candidates"]], top_k=20)
    view = smoke.ranking_view(outputs, row["candidates"])
    assert [(r["candidate_index"], r["text"], r["score"]) for r in view["original_outputs"]] == outputs
    assert "effective_idf" in smoke.corpus_statistics(row, True)["bm25"]
