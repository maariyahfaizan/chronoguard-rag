from src.eval.metrics import (
    exact_match,
    f1_score,
    get_relevance_labels,
    recall_at_k,
    ndcg_at_k,
)


def evaluate_query(
    answer,
    gold_answer,
    gold_aliases,
    candidates,
    retrieved_indices,
    k=5,
):
    """
    Compute the full metric suite for a single query.

    `retrieved_indices` must be the ORIGINAL candidate positions (the `idx`
    values from Step 2's retrieval functions), not passage text -- Recall@k
    and nDCG@k index directly into the candidate pool using these.

    Returns a dict with keys: em, f1, recall_at_{k}, ndcg_at_{k}.
    recall_at_{k} / ndcg_at_{k} may be None, meaning "undefined for this
    query" (e.g. no relevant candidate exists anywhere in its pool) -- this
    must be excluded, not treated as zero, when averaging across queries.
    """
    em = exact_match(answer, gold_answer, gold_aliases)
    f1 = f1_score(answer, gold_answer, gold_aliases)

    relevance_labels = get_relevance_labels(candidates, gold_answer, gold_aliases)

    recall = recall_at_k(retrieved_indices, relevance_labels, k=k)
    ndcg = ndcg_at_k(retrieved_indices, relevance_labels, k=k)

    return {
        "em": em,
        "f1": f1,
        f"recall_at_{k}": recall,
        f"ndcg_at_{k}": ndcg,
    }


def aggregate_metrics(results, k=5):
    """
    Average metrics across all queries in a completed run.

    EM/F1 are always defined, so they're averaged over every query.
    Recall@k/nDCG@k are averaged only over queries where they were defined
    (not None) -- queries with no relevant candidate at all are EXCLUDED
    from the denominator, never counted as zero. If every single query in
    the run is undefined for a metric, that metric's average is reported as
    None (not silently defaulted to 0.0).
    """
    n = len(results)
    if n == 0:
        raise ValueError("Cannot aggregate metrics over zero results.")

    recall_key = f"recall_at_{k}"
    ndcg_key = f"ndcg_at_{k}"

    valid_recall = [r[recall_key] for r in results if r[recall_key] is not None]
    valid_ndcg = [r[ndcg_key] for r in results if r[ndcg_key] is not None]

    avg_recall = sum(valid_recall) / len(valid_recall) if valid_recall else None
    avg_ndcg = sum(valid_ndcg) / len(valid_ndcg) if valid_ndcg else None

    return {
        "n_examples": n,
        "n_recall_defined": len(valid_recall),
        "n_ndcg_defined": len(valid_ndcg),
        "average_em": sum(r["em"] for r in results) / n,
        "average_f1": sum(r["f1"] for r in results) / n,
        f"average_recall_at_{k}": avg_recall,
        f"average_ndcg_at_{k}": avg_ndcg,
    }