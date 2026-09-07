from src.eval.evaluator import evaluate_query, aggregate_metrics


def test_evaluate_query_returns_all_expected_keys():
    candidates = ["The capital of France is Paris.", "Berlin is in Germany."]
    result = evaluate_query(
        answer="Paris",
        gold_answer="Paris",
        gold_aliases=[],
        candidates=candidates,
        retrieved_indices=[0, 1],
        k=2,
    )
    assert set(result.keys()) == {"em", "f1", "recall_at_2", "ndcg_at_2"}
    assert result["em"] == 1


def test_evaluate_query_respects_truncation_for_relevance():
    """
    Regression test for Step 4: a gold answer that only appears AFTER the
    truncation cutoff must not count as relevant, since the generator never
    saw that part of the passage.
    """
    padding = "x " * 1000  # pushes the real content past a small max_passage_chars
    candidate = padding + "the answer is Zanzibar"
    result = evaluate_query(
        answer="unknown",
        gold_answer="Zanzibar",
        gold_aliases=[],
        candidates=[candidate],
        retrieved_indices=[0],
        k=1,
        max_passage_chars=20,  # small on purpose, cuts off well before "Zanzibar"
    )
    # With such a small truncation window, "Zanzibar" never appears in the
    # truncated text, so this candidate must NOT be scored as relevant.
    assert result["recall_at_1"] is None


def test_aggregate_metrics_none_when_all_undefined():
    """
    Regression test for the run_hybrid_reranker.py bug found in Step 3: when
    every query in a run has an undefined recall/ndcg, the AVERAGE must be
    None, never silently defaulted to 0.0.
    """
    results = [
        {"em": 1, "f1": 1.0, "recall_at_5": None, "ndcg_at_5": None},
        {"em": 0, "f1": 0.5, "recall_at_5": None, "ndcg_at_5": None},
    ]
    summary = aggregate_metrics(results, k=5)
    assert summary["average_recall_at_5"] is None
    assert summary["average_ndcg_at_5"] is None
    assert summary["n_recall_defined"] == 0
    # EM/F1 must still be averaged normally regardless
    assert summary["average_em"] == 0.5