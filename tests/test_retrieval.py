from src.retrieval.bm25 import retrieve_best
from src.retrieval.hybrid import reciprocal_rank_fusion


def test_bm25_returns_index_passage_score_triples():
    candidates = ["apple pie recipe", "banana bread recipe", "apple pie recipe"]
    results = retrieve_best("apple pie", candidates, top_k=3)

    # Each result must be a 3-tuple: (index, passage, score)
    assert all(len(r) == 3 for r in results)

    indices = [idx for idx, passage, score in results]
    # Regression test: candidates[0] and candidates[2] are IDENTICAL text.
    # Before the Step 2 fix, downstream code recovered indices via
    # candidates.index(passage), which always returns the FIRST match (0)
    # for both -- silently losing one of the two distinct occurrences.
    # Retrieval itself must keep them distinguishable.
    assert len(set(indices)) == len(indices), (
        "Duplicate-text candidates must still be returned as distinct indices"
    )


def test_rrf_does_not_merge_distinct_candidates_with_identical_text():
    """
    Regression test for the Step 2 hybrid.py bug: reciprocal_rank_fusion used
    to key its running score dict on passage TEXT, so two different candidates
    sharing identical text were silently merged into a single RRF entry.
    """
    # idx 0 and idx 2 have identical text but are meant to be distinct candidates
    bm25_results = [(0, "duplicate passage", 5.0), (1, "unique passage", 3.0)]
    dense_results = [(2, "duplicate passage", 0.9), (1, "unique passage", 0.5)]

    fused = reciprocal_rank_fusion(bm25_results, dense_results, top_k=3)
    fused_indices = [idx for idx, passage, score in fused]

    # idx 0 and idx 2 must BOTH appear -- they are different candidates,
    # even though their text happens to be identical.
    assert 0 in fused_indices
    assert 2 in fused_indices
    assert len(set(fused_indices)) == len(fused_indices)