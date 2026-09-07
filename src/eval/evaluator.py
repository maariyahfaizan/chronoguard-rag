from src.eval.metrics import (
    exact_match,
    f1_score,
    get_relevance_labels,
    recall_at_k,
    ndcg_at_k,
)

from src.generation.generate import truncate_passage, DEFAULT_MAX_PASSAGE_CHARS

def evaluate_query(
    answer,
    gold_answer,
    gold_aliases,
    candidates,
    retrieved_indices,
    k=5,
    max_passage_chars=DEFAULT_MAX_PASSAGE_CHARS,
):
    """
    ...(existing docstring)...

    `max_passage_chars` must match whatever build_prompt used for this run --
    it defaults to the same constant generate.py uses, so relevance is scored
    on exactly the text the generator saw, not the full untruncated candidate.
    """
    em = exact_match(answer, gold_answer, gold_aliases)
    f1 = f1_score(answer, gold_answer, gold_aliases)

    truncated_candidates = [truncate_passage(c, max_passage_chars) for c in candidates]
    relevance_labels = get_relevance_labels(truncated_candidates, gold_answer, gold_aliases)
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