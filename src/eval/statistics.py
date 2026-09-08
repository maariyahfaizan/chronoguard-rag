"""
Statistical testing and uncertainty quantification for comparing retrieval
systems (E1-E4) on shared, paired query-level metrics.

All comparisons here are PAIRED: every experiment evaluates the same 100
queries in the same order, so query i's score under system A and system B
are matched observations, not independent samples. Every function in this
file assumes and relies on that pairing -- callers must pass metric lists
that are aligned by query_id.
"""

import random
import math

from scipy import stats


def bootstrap_ci(values, n_bootstrap=10000, ci=0.95, seed=42):
    """
    Bootstrap confidence interval for the mean of a single system's metric
    (e.g. one system's per-query F1 scores).

    Resamples `values` with replacement n_bootstrap times, recomputes the
    mean each time, and reports the (ci*100)% percentile interval. This
    makes no assumption about the underlying distribution being normal,
    which matters here since EM is binary and F1/Recall/nDCG are bounded
    and often skewed near their ceiling (as documented in Section 4 of the
    project report for TriviaQA specifically).

    Returns (point_estimate, lower_bound, upper_bound).
    """
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return None, None, None

    point_estimate = sum(values) / n

    boot_means = []
    for _ in range(n_bootstrap):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)

    boot_means.sort()
    alpha = 1.0 - ci
    lower_idx = int((alpha / 2) * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap) - 1

    return point_estimate, boot_means[lower_idx], boot_means[upper_idx]


def paired_bootstrap_test(values_a, values_b, n_bootstrap=10000, seed=42):
    """
    Paired bootstrap test for a difference in means between two systems on
    the SAME queries (e.g. system A's F1 per query vs system B's F1 per
    query, aligned by query_id).

    Critically, each bootstrap iteration resamples QUERY INDICES ONCE and
    applies that same resampling to both A and B -- this preserves the
    pairing. Resampling A and B independently would silently convert this
    into an unpaired test and throw away the statistical power the paired
    design is supposed to give you.

    Returns a dict with the observed mean difference (A - B), its bootstrap
    CI, and a two-sided p-value: the fraction of bootstrap resamples where
    the sign of the difference flipped relative to the observed direction,
    doubled (two-sided), capped at 1.0.
    """
    assert len(values_a) == len(values_b), (
        "values_a and values_b must be paired (same length, same query order)"
    )

    rng = random.Random(seed)
    n = len(values_a)
    if n == 0:
        return None

    observed_diff = (sum(values_a) - sum(values_b)) / n

    boot_diffs = []
    for _ in range(n_bootstrap):
        idx = [rng.randrange(n) for _ in range(n)]
        sample_a = sum(values_a[i] for i in idx) / n
        sample_b = sum(values_b[i] for i in idx) / n
        boot_diffs.append(sample_a - sample_b)

    boot_diffs.sort()
    alpha = 0.05
    lower_idx = int((alpha / 2) * n_bootstrap)
    upper_idx = int((1 - alpha / 2) * n_bootstrap) - 1

    frac_le_zero = sum(1 for d in boot_diffs if d <= 0) / n_bootstrap
    frac_ge_zero = sum(1 for d in boot_diffs if d >= 0) / n_bootstrap
    p_value = min(1.0, 2 * min(frac_le_zero, frac_ge_zero))

    return {
        "mean_diff": observed_diff,
        "ci_95_lower": boot_diffs[lower_idx],
        "ci_95_upper": boot_diffs[upper_idx],
        "p_value": p_value,
    }


def mcnemar_test(em_a, em_b):
    """
    Exact McNemar's test for paired binary outcomes (EM) between two systems
    on the same queries.

    McNemar's test ignores queries where both systems agree (both right or
    both wrong) -- agreement carries no information about which system is
    better. It looks only at DISCORDANT pairs: queries where exactly one
    system got it right. If A tends to win those disagreements far more
    often than B (or vice versa), that's evidence of a real difference.

    Uses the exact binomial form (appropriate at n=100; the chi-square
    approximation with continuity correction is only needed for much larger
    discordant-pair counts than we have here).

    Returns a dict with the discordant pair counts and a two-sided p-value.
    """
    assert len(em_a) == len(em_b)

    # n_10: A correct, B wrong.  n_01: A wrong, B correct.
    n_10 = sum(1 for a, b in zip(em_a, em_b) if a == 1 and b == 0)
    n_01 = sum(1 for a, b in zip(em_a, em_b) if a == 0 and b == 1)

    n_discordant = n_10 + n_01
    if n_discordant == 0:
        # No queries where the systems disagreed at all -- no evidence
        # either way, and the test isn't meaningfully defined.
        return {"n_10": 0, "n_01": 0, "n_discordant": 0, "p_value": 1.0}

    result = stats.binomtest(min(n_10, n_01), n_discordant, 0.5, alternative="two-sided")

    return {
        "n_10": n_10,
        "n_01": n_01,
        "n_discordant": n_discordant,
        "p_value": result.pvalue,
    }


def wilcoxon_test(values_a, values_b):
    """
    Wilcoxon signed-rank test: a distribution-free paired test for continuous
    metrics (F1, Recall@k, nDCG@k). Used as a secondary check alongside the
    paired bootstrap test above -- if both agree, that's a stronger basis for
    a claim than either alone; if they disagree, that discrepancy itself is
    worth reporting rather than picking whichever one supports the claim you
    wanted to make.

    Returns None if every paired difference is exactly zero (the test is
    undefined in that case -- there's nothing to rank).
    """
    diffs = [a - b for a, b in zip(values_a, values_b)]
    if all(d == 0 for d in diffs):
        return None

    statistic, p_value = stats.wilcoxon(values_a, values_b)
    return {"statistic": statistic, "p_value": p_value}


def paired_defined_only(values_a, values_b):
    """
    Filter two paired lists down to positions where BOTH are non-None.

    Used for Recall@k/nDCG@k, which can be None (undefined) for a query with
    no relevant candidate in its pool at all. As noted in the accompanying
    report: this undefined-ness depends only on the query's gold answer and
    candidate pool, which are identical across E1-E4, so in practice the same
    queries end up dropped from both sides -- but this function makes that
    assumption explicit and safe rather than assumed silently.
    """
    paired = [(a, b) for a, b in zip(values_a, values_b) if a is not None and b is not None]
    if not paired:
        return [], []
    a_vals, b_vals = zip(*paired)
    return list(a_vals), list(b_vals)