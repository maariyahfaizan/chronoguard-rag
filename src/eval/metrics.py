import re
import string
import math
import datetime


def normalize_answer(text: str) -> str:
    """Standard SQuAD/TriviaQA-style normalization: lowercase, strip punctuation,
    remove articles, collapse whitespace."""
    text = text.lower()
    text = "".join(ch for ch in text if ch not in string.punctuation)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = " ".join(text.split())
    return text


def exact_match(prediction: str, gold_answer: str, gold_aliases: list[str] = None) -> int:
    """Returns 1 if normalized prediction matches gold_answer or any gold_alias exactly, else 0."""
    gold_list = [gold_answer] + (gold_aliases or [])
    pred_norm = normalize_answer(prediction)
    return int(any(pred_norm == normalize_answer(g) for g in gold_list))


def f1_score(prediction: str, gold_answer: str, gold_aliases: list[str] = None) -> float:
    """Token-overlap F1 between prediction and gold, taking the max across gold_answer + gold_aliases."""
    gold_list = [gold_answer] + (gold_aliases or [])
    pred_tokens = normalize_answer(prediction).split()

    best_f1 = 0.0
    for gold in gold_list:
        gold_tokens = normalize_answer(gold).split()

        if not pred_tokens or not gold_tokens:
            # Both empty -> perfect match; one empty -> zero overlap
            f1 = 1.0 if pred_tokens == gold_tokens else 0.0
            best_f1 = max(best_f1, f1)
            continue

        common = {}
        for tok in pred_tokens:
            common[tok] = min(pred_tokens.count(tok), gold_tokens.count(tok))
        num_common = sum(common.values())

        if num_common == 0:
            continue

        precision = num_common / len(pred_tokens)
        recall = num_common / len(gold_tokens)
        f1 = 2 * precision * recall / (precision + recall)
        best_f1 = max(best_f1, f1)

    return best_f1


def get_relevance_labels_phrase_match(candidates: list[str], gold_answer: str, gold_aliases: list[str] = None) -> list[int]:
    """
    LEGACY: the original whole-contiguous-phrase relevance labeling
    (word-boundary regex requiring the full normalized gold answer to
    appear verbatim). Kept as-is, unmodified, specifically so already-
    completed TriviaQA runs (Report_week3.md) remain reproducible against
    the exact methodology they were scored under, without needing a
    rerun. Use get_relevance_labels() (below) for any NEW run -- including
    any future TriviaQA rerun, should one happen -- since that version
    fixes a real problem this one has with sentence-style gold answers
    (see get_relevance_labels' docstring). Do not use this for
    StreamingQA or FreshQA; it was never correct for their answer styles.
    """
    gold_list = [gold_answer] + (gold_aliases or [])
    gold_norms = [normalize_answer(g) for g in gold_list]

    gold_patterns = [
        re.compile(r"\b" + re.escape(g) + r"\b")
        for g in gold_norms
        if g
    ]

    return [
        int(any(pattern.search(normalize_answer(c)) for pattern in gold_patterns))
        for c in candidates
    ]


def get_relevance_labels(candidates: list[str], gold_answer: str, gold_aliases: list[str] = None) -> list[int]:
    """
    Weak-supervision relevance label per candidate: 1 if the candidate's
    normalized text contains ALL of at least one gold answer's tokens
    (unordered, subset match), else 0.

    NOTE ON THIS REVISION: previously required the full normalized gold
    answer to appear as ONE CONTIGUOUS PHRASE (word-boundary regex). That
    works for short entity-style answers (TriviaQA: "Marquette
    University") but breaks down for StreamingQA and FreshQA, where many
    gold answers are full sentences (e.g. "No, Ferne McCann did not spend
    Christmas with her new boyfriend, Albie Gibbs, in December 2020.") --
    no real passage contains that exact wording verbatim, so the old
    version silently returned all-zero relevance for such queries, and
    recall_at_k/ndcg_at_k got excluded from aggregate_metrics' denominator
    rather than actually measured (confirmed against real StreamingQA
    pools: 13/100 gold answers have 6+ words). Token-subset matching is
    looser but still meaningful -- it requires every substantive word of
    the answer to be present in the candidate, just not glued into one
    exact phrase.

    For datasets with real ground-truth relevance available (e.g.
    FreshQA's is_source_document, marking a candidate as one of the
    question's actual cited sources), prefer passing those directly to
    evaluate_query()/aggregate_metrics() instead of this weak-supervision
    fallback -- see evaluator.py.

    Already-completed TriviaQA results (Report_week3.md) were scored
    under the OLD phrase-match logic and are NOT being rerun -- use
    get_relevance_labels_phrase_match() (above) if anything needs to
    reproduce that exact methodology. This function is for StreamingQA,
    FreshQA, and any future dataset/rerun going forward.
    """
    gold_list = [gold_answer] + (gold_aliases or [])
    gold_token_sets = [set(normalize_answer(g).split()) for g in gold_list]
    gold_token_sets = [g for g in gold_token_sets if g]  # drop empties

    labels = []
    for c in candidates:
        cand_tokens = set(normalize_answer(c).split())
        labels.append(int(any(g.issubset(cand_tokens) for g in gold_token_sets)))
    return labels


def recall_at_k(retrieved_indices: list[int], relevance_labels: list[int], k: int) -> float | None:
    """Fraction of all relevant candidates (across the full pool) that appear in the top-k retrieved.
    Returns None if there are no relevant candidates at all (undefined, not zero)."""
    total_relevant = sum(relevance_labels)
    if total_relevant == 0:
        return None

    top_k_indices = retrieved_indices[:k]
    hits = sum(relevance_labels[i] for i in top_k_indices if i < len(relevance_labels))
    return hits / total_relevant


def ndcg_at_k(retrieved_indices: list[int], relevance_labels: list[int], k: int) -> float | None:
    """Binary-relevance NDCG@k. Returns None if there are no relevant candidates (undefined)."""
    total_relevant = sum(relevance_labels)
    if total_relevant == 0:
        return None

    def dcg(indices):
        return sum(
            relevance_labels[idx] / math.log2(pos + 2)  # pos+2 because pos starts at 0
            for pos, idx in enumerate(indices)
            if idx < len(relevance_labels)
        )

    actual_dcg = dcg(retrieved_indices[:k])

    # Ideal ranking: all relevant candidates first
    ideal_order = sorted(range(len(relevance_labels)), key=lambda i: relevance_labels[i], reverse=True)
    ideal_dcg = dcg(ideal_order[:k])

    if ideal_dcg == 0:
        return None
    return actual_dcg / ideal_dcg


# ---------------------------------------------------------------------------
# Temporal metrics (plan Section 7: "Temporal QA" and "Retrieval" rows) --
# added once question_ts survived into the processed StreamingQA shape.
# All four require a real per-query "query time" reference point
# (question_ts) to compare candidate timestamps against. For datasets with
# no genuine per-question timestamp (FreshQA's effective_year is a coarse
# bucket, not a precise date -- see freshqa_report.md), pass question_ts
# as None and every function below returns None, rather than silently
# fabricating a comparison -- these metrics simply aren't meaningful
# without a real reference point, and that should show up as "undefined"
# in your results, not a fabricated 0.0.
# ---------------------------------------------------------------------------

def _to_datetime(value) -> datetime.datetime | None:
    """Accepts a UNIX epoch (int/float, as StreamingQA's question_ts/
    evidence_ts are stored) or an ISO-8601 string (as candidate
    `timestamp` fields are stored), and returns a tz-aware UTC datetime.
    Returns None if value is None or unparseable, rather than raising --
    callers treat None as "validity can't be determined" and exclude it,
    never as "invalid" (an unknown date is not the same claim as a future
    date).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, tz=datetime.timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.datetime.fromisoformat(value)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    return None


def is_time_valid(candidate_timestamp, question_ts) -> bool | None:
    """
    True if the candidate's timestamp is at or before question_ts (the
    evidence could actually have existed when the question was asked).
    False if strictly after (the evidence is "from the future" relative
    to the question -- exactly the kind of thing ChronoGuard-RAG is meant
    to catch). None if either timestamp is missing/unparseable, meaning
    validity genuinely can't be determined -- callers must NOT treat None
    as False.
    """
    cand_dt = _to_datetime(candidate_timestamp)
    q_dt = _to_datetime(question_ts)
    if cand_dt is None or q_dt is None:
        return None
    return cand_dt <= q_dt


def fraction_top_k_violating(
    retrieved_indices: list[int],
    candidate_timestamps: list,
    question_ts,
    k: int,
) -> float | None:
    """
    Fraction of the top-k RETRIEVED candidates whose evidence is
    time-invalid (dated after question_ts) -- how often the retriever
    surfaces evidence that couldn't have existed yet when the question was
    asked, independent of whether that evidence is topically relevant.
    Candidates whose validity can't be determined (missing/unparseable
    timestamp) are excluded from both numerator and denominator, not
    counted as violations. Returns None if question_ts is missing, or if
    no top-k candidate's validity could be determined at all.
    """
    top_k = retrieved_indices[:k]
    validities = []
    for idx in top_k:
        if idx >= len(candidate_timestamps):
            continue
        v = is_time_valid(candidate_timestamps[idx], question_ts)
        if v is not None:
            validities.append(v)

    if not validities:
        return None

    violations = sum(1 for v in validities if not v)
    return violations / len(validities)


def valid_evidence_recall_at_k(
    retrieved_indices: list[int],
    relevance_labels: list[int],
    candidate_timestamps: list,
    question_ts,
    k: int,
) -> float | None:
    """
    Recall@k restricted to candidates that are BOTH relevant AND
    time-valid (timestamp <= question_ts) -- did retrieval surface
    evidence that's actually usable, not just topically relevant evidence
    that couldn't have existed yet. A candidate whose time-validity can't
    be determined (missing/unparseable timestamp) is treated as NOT
    counting toward "valid relevant" (conservative: unknown validity is
    not proof of validity). Returns None if there is no relevant AND
    time-valid candidate anywhere in the pool (undefined, not zero) --
    same convention as recall_at_k/ndcg_at_k.
    """
    valid_relevant = [
        int(bool(rel) and is_time_valid(ts, question_ts) is True)
        for rel, ts in zip(relevance_labels, candidate_timestamps)
    ]
    total_valid_relevant = sum(valid_relevant)
    if total_valid_relevant == 0:
        return None

    top_k_indices = retrieved_indices[:k]
    hits = sum(valid_relevant[i] for i in top_k_indices if i < len(valid_relevant))
    return hits / total_valid_relevant


def time_valid_answer_accuracy(
    em: int,
    used_candidate_timestamps: list,
    question_ts,
) -> int | None:
    """
    1 if the answer was correct (em==1) AND every piece of evidence
    actually shown to the generator (used_candidate_timestamps -- e.g. the
    top-k retrieved or top-1 reranked passages, whichever the run actually
    fed to generation) is time-valid. 0 if the answer was correct but at
    least one piece of evidence used was time-invalid -- a correct answer
    reached via evidence that couldn't have existed yet is NOT counted as
    a properly time-grounded correct answer, which is the point of this
    metric vs. plain EM. Also 0 if the answer was simply wrong (em==0).
    None only if question_ts is missing, or if the time-validity of at
    least one piece of used evidence can't be determined at all --
    grounding can't be assessed either way in that case.

    ASSUMPTION, undocumented beyond the metric's name in the research
    plan: this treats "Time-Valid Answer Accuracy" as correctness
    conditioned on properly-grounded evidence, not as accuracy computed
    only over some pre-filtered subset of the eval set. Confirm this
    matches the intended definition before relying on it for reported
    paper numbers.
    """
    if question_ts is None:
        return None

    validities = [is_time_valid(ts, question_ts) for ts in used_candidate_timestamps]
    if any(v is None for v in validities):
        return None

    all_valid = all(validities) if validities else False
    return int(bool(em) and all_valid)