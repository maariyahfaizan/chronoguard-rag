"""
Weeks 3-4 | Gate A-4: paired statistics for the StreamingQA clean baselines
(E1-E4), with Holm-Bonferroni correction across pairwise comparisons.

Reuses src/eval/statistics.py UNCHANGED (bootstrap_ci, paired_bootstrap_test,
mcnemar_test, wilcoxon_test, paired_defined_only) so TriviaQA's existing
statistics_results.json stays reproducible against unmodified code. The one
thing that module does not have -- multiplicity correction -- is implemented
here (holm_bonferroni) rather than added to the shared module; it can be
moved there later as a deliberate, separate change.

Input:  logs/streamingqa_{baseline,dense,hybrid,hybrid_reranker}_run_chunked.jsonl
        (the corrected A1+A2 logs from Gate A-3)
Output: logs/statistics_results_streamingqa.json  (new file; TriviaQA's
        logs/statistics_results.json is never touched)

TEST CHOICE PER METRIC (same convention as the TriviaQA analysis):
  - binary metrics (EM, time-valid answer accuracy): exact McNemar test
  - continuous metrics (F1, Recall@5, nDCG@5, fraction of top-5 violating,
    valid-evidence Recall@5): paired bootstrap test (primary), with a
    Wilcoxon signed-rank test reported as a secondary check
Whether a metric is binary is detected from the data (all values in {0,1}),
not hardcoded, and printed so it is visible which test was used.

UNDEFINED VALUES: Recall@5 / nDCG@5 / valid-evidence Recall@5 are None for
queries with no validated relevant chunk. None is never coerced to 0
(metrics.py's convention): each pairwise comparison uses only the queries
where BOTH systems are defined (paired_defined_only), and n is reported.

MULTIPLICITY (documented choice -- flag alongside the results, since the
review says only "across pairwise comparisons" and does not define the
family):
  - PRIMARY: Holm-Bonferroni WITHIN each metric, over its 6 pairwise
    comparisons (each metric is treated as its own hypothesis family).
  - SENSITIVITY: Holm-Bonferroni over ALL primary tests across ALL metrics
    at once (more conservative). Both are reported side by side; a result
    that only survives the primary correction should be described as such.
  - The secondary Wilcoxon p-values get their own within-metric Holm column.

Paired bootstrap p-values come from 10,000 resamples, so their resolution
is about 1e-4; values below that print as "<1e-4".

Usage (from the repo root):
    python -m src.eval.run_statistics_streamingqa
"""

import json
import sys
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]  # src/eval -> src -> repo root
sys.path.insert(0, str(REPO_ROOT))

from src.eval.statistics import (  # noqa: E402
    bootstrap_ci,
    paired_bootstrap_test,
    mcnemar_test,
    wilcoxon_test,
    paired_defined_only,
)

OUTPUT_PATH = REPO_ROOT / "logs" / "statistics_results_streamingqa.json"

LOGS = {
    "E1_BM25": "logs/streamingqa_baseline_run_chunked.jsonl",
    "E2_Contriever": "logs/streamingqa_dense_run_chunked.jsonl",
    "E3_HybridRRF": "logs/streamingqa_hybrid_run_chunked.jsonl",
    "E4_HybridReranked": "logs/streamingqa_hybrid_reranker_run_chunked.jsonl",
}

# display label -> per-query key in the run logs (the keys evaluate_query()
# writes via **metrics). Verified against the first log record at startup;
# a missing key stops the script with the list of keys that ARE present,
# rather than guessing a substitute.
METRICS = {
    "EM": "em",
    "F1": "f1",
    "Recall@5": "recall_at_5",
    "nDCG@5": "ndcg_at_5",
    "Frac_top5_violating": "fraction_top_5_violating",
    "ValidEvidence_Recall@5": "valid_evidence_recall_at_5",
    "TVAA": "time_valid_answer_accuracy",
}


def holm_bonferroni(p_values: list) -> list:
    """Holm step-down adjusted p-values, returned in the ORIGINAL order.

    Sort ascending; the k-th smallest (0-based) is multiplied by (m - k),
    capped at 1, and adjusted values are forced to be non-decreasing along
    the sorted order (running max), which is what makes Holm valid.
    """
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [None] * m
    running_max = 0.0
    for rank, i in enumerate(order):
        adj = min(1.0, (m - rank) * p_values[i])
        running_max = max(running_max, adj)
        adjusted[i] = running_max
    return adjusted


def fmt_p(p) -> str:
    if p is None:
        return "  n/a "
    return "<1e-4" if p < 1e-4 else f"{p:.4f}"


def load_run(log_path: Path) -> list:
    with open(log_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    # Sort by query_id so every system's list is aligned to the same query
    # order -- required for every paired comparison below to be valid.
    records.sort(key=lambda r: r["query_id"])
    return records


def check_metric_keys(runs: dict) -> None:
    for name, records in runs.items():
        present = set(records[0].keys())
        missing = [k for k in METRICS.values() if k not in present]
        if missing:
            raise KeyError(
                f"{name}'s log is missing per-query metric key(s) {missing}. "
                f"Keys actually present: {sorted(present)}. Fix the METRICS "
                f"mapping at the top of this script; not guessing a substitute."
            )


def report_undefined_alignment(metrics: dict, label: str) -> None:
    """Prints whether the same queries are undefined for every system. The
    pairwise tests are correct either way (paired_defined_only filters per
    pair); this just makes the shared-pool assumption visible."""
    sets = {
        name: {i for i, v in enumerate(m[label]) if v is None}
        for name, m in metrics.items()
    }
    reference = next(iter(sets.values()))
    if all(s == reference for s in sets.values()):
        print(f"  {label}: same {len(reference)} undefined queries across all systems")
    else:
        print(f"  {label}: WARNING undefined-query sets DIFFER across systems "
              f"{ {n: len(s) for n, s in sets.items()} } -- pairwise n will vary")


def is_binary(metrics: dict, label: str) -> bool:
    vals = [v for m in metrics.values() for v in m[label] if v is not None]
    return bool(vals) and all(v in (0, 1) for v in vals)


def main():
    runs = {name: load_run(REPO_ROOT / path) for name, path in LOGS.items()}

    reference_ids = [r["query_id"] for r in next(iter(runs.values()))]
    for name, records in runs.items():
        ids = [r["query_id"] for r in records]
        assert ids == reference_ids, (
            f"{name}'s query_id sequence does not match the reference run -- "
            f"paired comparisons require identical, identically-ordered queries."
        )
    check_metric_keys(runs)

    metrics = {
        name: {label: [r.get(key) for r in records] for label, key in METRICS.items()}
        for name, records in runs.items()
    }
    n_queries = len(reference_ids)
    print(f"Loaded {len(runs)} runs x {n_queries} queries (aligned by query_id).")

    print("\nUndefined-value alignment:")
    for label in METRICS:
        report_undefined_alignment(metrics, label)

    # ------------------------------------------------------------------
    # Per-system bootstrap CIs
    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("PER-SYSTEM BOOTSTRAP CONFIDENCE INTERVALS (95%, 10,000 resamples)")
    print("=" * 78)
    output = {
        "meta": {
            "n_queries": n_queries,
            "logs": LOGS,
            "bootstrap_resamples": 10000,
            "bootstrap_seed": 42,
            "primary_family": "Holm-Bonferroni within each metric over its 6 pairwise comparisons",
            "sensitivity_family": "Holm-Bonferroni over all primary tests across all metrics",
        },
        "per_system": {},
        "pairwise": {},
    }
    for name in runs:
        print(f"\n{name}")
        output["per_system"][name] = {}
        for label in METRICS:
            defined = [v for v in metrics[name][label] if v is not None]
            if not defined:
                print(f"  {label:<24} no defined values")
                output["per_system"][name][label] = None
                continue
            pe, lo, hi = bootstrap_ci(defined)
            print(f"  {label:<24} {pe:.4f}  [{lo:.4f}, {hi:.4f}]  (n={len(defined)}/{n_queries})")
            output["per_system"][name][label] = {
                "point": pe, "ci_lower": lo, "ci_upper": hi, "n_defined": len(defined),
            }

    # ------------------------------------------------------------------
    # Pairwise tests (raw p-values first, then Holm)
    # ------------------------------------------------------------------
    pairs = list(combinations(runs.keys(), 2))
    entries = []  # (label, pair_key, entry_dict) for every completed comparison
    binary_labels = {label for label in METRICS if is_binary(metrics, label)}

    for label in METRICS:
        for name_a, name_b in pairs:
            va, vb = paired_defined_only(metrics[name_a][label], metrics[name_b][label])
            if not va:
                continue
            pair_key = f"{name_a}_vs_{name_b}"
            if label in binary_labels:
                mc = mcnemar_test(va, vb)
                entry = {
                    "test": "mcnemar_exact",
                    "n": len(va),
                    "mean_diff": sum(va) / len(va) - sum(vb) / len(vb),
                    **mc,
                    "primary_p": mc["p_value"],
                    "wilcoxon_p": None,
                }
            else:
                pb = paired_bootstrap_test(va, vb)
                wx = wilcoxon_test(va, vb)
                entry = {
                    "test": "paired_bootstrap",
                    "n": len(va),
                    **pb,
                    "primary_p": pb["p_value"],
                    "wilcoxon_p": wx["p_value"] if wx is not None else None,
                }
            entries.append((label, pair_key, entry))

    # Holm: primary family within each metric
    for label in METRICS:
        idx = [i for i, (lab, _, _) in enumerate(entries) if lab == label]
        if not idx:
            continue
        adj = holm_bonferroni([entries[i][2]["primary_p"] for i in idx])
        for i, a in zip(idx, adj):
            entries[i][2]["holm_p_within_metric"] = a
        wx_idx = [i for i in idx if entries[i][2]["wilcoxon_p"] is not None]
        if wx_idx:
            wx_adj = holm_bonferroni([entries[i][2]["wilcoxon_p"] for i in wx_idx])
            for i, a in zip(wx_idx, wx_adj):
                entries[i][2]["wilcoxon_holm_p_within_metric"] = a

    # Holm: conservative sensitivity family across everything
    all_adj = holm_bonferroni([e["primary_p"] for _, _, e in entries])
    for (_, _, e), a in zip(entries, all_adj):
        e["holm_p_all_metrics"] = a

    # ------------------------------------------------------------------
    # Print + collect
    # ------------------------------------------------------------------
    print("\n" + "=" * 78)
    print("PAIRWISE TESTS (paired; Holm-adjusted). diff = first system - second.")
    print("* = Holm-within-metric p < 0.05    ** = also significant in the all-metrics family")
    print("=" * 78)

    for label in METRICS:
        rows = [(pk, e) for lab, pk, e in entries if lab == label]
        if not rows:
            continue
        kind = "McNemar exact" if label in binary_labels else "paired bootstrap (+Wilcoxon secondary)"
        print(f"\n{label}   [{kind}]")
        print(f"  {'pair':<36}{'n':>4} {'diff':>8}  {'raw p':>7} {'Holm(metric)':>13} {'Holm(all)':>10}  wilcoxon p / Holm")
        output["pairwise"][label] = {}
        for pk, e in rows:
            star = ""
            if e["holm_p_within_metric"] < 0.05:
                star = "*"
                if e["holm_p_all_metrics"] < 0.05:
                    star = "**"
            wx = ""
            if e["wilcoxon_p"] is not None:
                wx = f"{fmt_p(e['wilcoxon_p'])} / {fmt_p(e.get('wilcoxon_holm_p_within_metric'))}"
            print(f"  {pk:<36}{e['n']:>4} {e['mean_diff']:>+8.4f}  {fmt_p(e['primary_p']):>7} "
                  f"{fmt_p(e['holm_p_within_metric']):>13} {fmt_p(e['holm_p_all_metrics']):>10}  {wx} {star}")
            output["pairwise"][label][pk] = e

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=float)
    print(f"\nFull results written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()