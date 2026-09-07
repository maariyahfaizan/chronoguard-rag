from src.eval.metrics import (
    normalize_answer,
    exact_match,
    f1_score,
    get_relevance_labels,
    recall_at_k,
    ndcg_at_k,
)


def test_exact_match_basic():
    assert exact_match("Paris", "paris") == 1
    assert exact_match("Paris", "London") == 0


def test_f1_partial_overlap():
    # Gold "eiffel tower" vs prediction "eiffel tower in paris" -> shares both
    # gold tokens but adds extra ones, so precision < 1 while recall = 1.
    score = f1_score("eiffel tower in paris", "eiffel tower")
    assert 0.0 < score < 1.0


def test_relevance_labels_do_not_match_substrings():
    """
    Regression test for Step 5: gold answer 'Cook' must NOT match 'cookies'
    or 'Cookson' -- only whole-word/whole-phrase occurrences count.
    """
    candidates = [
        "James Cook was an explorer.",      # relevant: "Cook" as a whole word
        "She baked cookies for the party.", # NOT relevant: "cook" is inside "cookies"
        "Cookson Group is a UK company.",   # NOT relevant: "cook" is inside "Cookson"
    ]
    labels = get_relevance_labels(candidates, gold_answer="Cook")
    assert labels == [1, 0, 0]


def test_relevance_labels_multiword_phrase():
    candidates = [
        "New York is a major city.",     # relevant: exact phrase
        "The New Yorker magazine.",      # NOT relevant: "New" and "Yorker", not "New York"
    ]
    labels = get_relevance_labels(candidates, gold_answer="New York")
    assert labels == [1, 0]


def test_recall_at_k_returns_none_when_no_relevant_candidates():
    """
    Regression test for the None-vs-zero distinction (Section 5 of the
    original report, and the Step 3 aggregate_metrics fix): if a query's
    candidate pool has no relevant passage at all, recall/ndcg must be
    undefined (None), never silently 0.0.
    """
    relevance_labels = [0, 0, 0]
    assert recall_at_k([0, 1, 2], relevance_labels, k=3) is None
    assert ndcg_at_k([0, 1, 2], relevance_labels, k=3) is None


def test_recall_at_k_basic():
    relevance_labels = [1, 0, 1, 0]
    # top-3 retrieved by index: [0, 1, 2] -> hits indices 0 and 2 -> both relevant
    recall = recall_at_k([0, 1, 2], relevance_labels, k=3)
    assert recall == 1.0  # both relevant candidates (idx 0, idx 2) were retrieved