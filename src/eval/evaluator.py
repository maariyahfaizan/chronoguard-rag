from src.eval.metrics import (
    exact_match,
    f1_score,
    get_relevance_labels,
    recall_at_k,
    ndcg_at_k,
    fraction_top_k_violating,
    valid_evidence_recall_at_k,
    time_valid_answer_accuracy,
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
    question_ts=None,
    candidate_timestamps=None,
    used_candidate_timestamps=None,
):
    """
    ...(existing docstring)...

    `max_passage_chars` must match whatever build_prompt used for this run --
    it defaults to the same constant generate.py uses, so relevance is scored
    on exactly the text the generator saw, not the full untruncated candidate.

    `candidates` MUST be list[str] (passage text only). For StreamingQA/
    FreshQA, whatever harness calls this needs to unpack the
    {doc_id, text, timestamp} dicts into a plain text list first -- the
    same way it must before calling retrieve_best(), since BM25Okapi's
    tokenization (c.split(" ")) and this function's normalize_answer()
    both assume a string. Passing raw dicts through would fail with an
    unhelpful AttributeError/TypeError deep inside normalization rather
    than a clear error at the boundary.

    Temporal args (all optional; StreamingQA-only for now -- FreshQA has
    no real per-question timestamp, see freshqa_report.md 2d):
      question_ts: the query's reference time. If None (TriviaQA, FreshQA
        as currently processed), none of the temporal metrics are
        computed and their keys are OMITTED from the returned dict --
        not set to None. None would mean "attempted, came back
        undefined"; omission means "not applicable to this dataset,"
        which is a different fact and needs to stay distinguishable in
        aggregate_metrics().
      candidate_timestamps: list, same length/order as `candidates`, one
        raw timestamp per candidate (None per-candidate if unknown).
        Required whenever question_ts is given -- raises otherwise,
        since "I have a query time but no evidence times" is a caller
        bug, not a legitimately-undefined metric.
      used_candidate_timestamps: timestamps of whichever candidates were
        actually shown to generation (top-k retrieved, or a reranked
        subset if this run uses a reranker). Defaults to
        candidate_timestamps at retrieved_indices[:k], which matches
        run_baseline.py's current flow (retrieve_best already returns
        exactly top_k, and generation is called on retrieved_passages
        unchanged) -- pass it explicitly the moment that stops being true
        (e.g. once E4's reranker reorders/truncates before generation).
    """
    em = exact_match(answer, gold_answer, gold_aliases)
    f1 = f1_score(answer, gold_answer, gold_aliases)

    truncated_candidates = [truncate_passage(c, max_passage_chars) for c in candidates]
    relevance_labels = get_relevance_labels(truncated_candidates, gold_answer, gold_aliases)
    recall = recall_at_k(retrieved_indices, relevance_labels, k=k)
    ndcg = ndcg_at_k(retrieved_indices, relevance_labels, k=k)

    metrics = {
        "em": em,
        "f1": f1,
        f"recall_at_{k}": recall,
        f"ndcg_at_{k}": ndcg,
    }

    if question_ts is not None:
        if candidate_timestamps is None:
            raise ValueError(
                "question_ts was given but candidate_timestamps was not -- "
                "the temporal metrics need a per-candidate timestamp to "
                "compare against question_ts, not just a query-time reference."
            )

        metrics[f"fraction_top_{k}_violating"] = fraction_top_k_violating(
            retrieved_indices, candidate_timestamps, question_ts, k=k
        )
        metrics[f"valid_evidence_recall_at_{k}"] = valid_evidence_recall_at_k(
            retrieved_indices, relevance_labels, candidate_timestamps, question_ts, k=k
        )

        if used_candidate_timestamps is None:
            used_candidate_timestamps = [
                candidate_timestamps[i]
                for i in retrieved_indices[:k]
                if i < len(candidate_timestamps)
            ]
        metrics["time_valid_answer_accuracy"] = time_valid_answer_accuracy(
            em, used_candidate_timestamps, question_ts
        )

    return metrics


def aggregate_metrics(results, k=5):
    """
    Average metrics across all queries in a completed run.

    EM/F1 are always defined, so they're averaged over every query.
    Recall@k/nDCG@k, and the three temporal metrics when present
    (fraction_top_k_violating, valid_evidence_recall_at_k,
    time_valid_answer_accuracy), all follow the same undefined-vs-zero
    convention: None entries are excluded from the denominator, never
    counted as zero, and if every entry for a metric is None its average
    is reported as None.

    A temporal key that is ABSENT from every result (e.g. a TriviaQA or
    current-FreshQA run, where evaluate_query() was never given
    question_ts) is simply left out of the returned summary entirely --
    that's "not computed for this dataset," a different fact from
    "computed, came back undefined for every query," and collapsing the
    two would make a StreamingQA run's temporal columns silently
    disappear if even one result happened to lack them, or make a
    TriviaQA summary misleadingly report None for metrics that were
    never applicable in the first place.
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

    summary = {
        "n_examples": n,
        "n_recall_defined": len(valid_recall),
        "n_ndcg_defined": len(valid_ndcg),
        "average_em": sum(r["em"] for r in results) / n,
        "average_f1": sum(r["f1"] for r in results) / n,
        f"average_recall_at_{k}": avg_recall,
        f"average_ndcg_at_{k}": avg_ndcg,
    }

    temporal_keys = [
        (f"fraction_top_{k}_violating", f"average_fraction_top_{k}_violating"),
        (f"valid_evidence_recall_at_{k}", f"average_valid_evidence_recall_at_{k}"),
        ("time_valid_answer_accuracy", "average_time_valid_answer_accuracy"),
    ]
    for raw_key, avg_key in temporal_keys:
        if not any(raw_key in r for r in results):
            continue  # not applicable to this dataset -- omit entirely
        values = [r[raw_key] for r in results if r.get(raw_key) is not None]
        summary[avg_key] = sum(values) / len(values) if values else None
        summary[f"n_{raw_key}_defined"] = len(values)

    return summary


def aggregate_metrics_by_group(results, groups, k=5):
    """
    Same aggregation as aggregate_metrics(), computed separately per group
    label -- e.g. StreamingQA's recent_or_past -- to satisfy Section 7's
    "correctness conditioned on query date" and Section 6's "Evaluation
    slices" requirement.

    `groups` must be the same length as `results`, one label per query,
    in the same order (e.g. row["recent_or_past"] for each row in the
    run, in query_id order). This function reads labels ONLY from
    `groups`, never from `results` itself, since not every dataset
    carries the same grouping field, and a mismatched-length pair of
    lists would otherwise silently attach the wrong label to the wrong
    result rather than raising.

    Returns {group_label: aggregate_metrics(...)} for each distinct label
    found in `groups`, reusing aggregate_metrics() unchanged.
    """
    if len(groups) != len(results):
        raise ValueError(
            f"groups (len={len(groups)}) must be the same length as "
            f"results (len={len(results)}) -- one group label per query."
        )

    grouped_results = {}
    for group_label, result in zip(groups, results):
        grouped_results.setdefault(group_label, []).append(result)

    return {
        group_label: aggregate_metrics(group_results, k=k)
        for group_label, group_results in grouped_results.items()
    }