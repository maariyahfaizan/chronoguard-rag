import json
import os
import sys
from itertools import combinations

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.eval.statistics import (
    bootstrap_ci,
    paired_bootstrap_test,
    mcnemar_test,
    wilcoxon_test,
    paired_defined_only,
)

STATS_OUTPUT_PATH = "logs/statistics_results.json"

LOGS = {
    "E1_BM25": "logs/baseline_run.jsonl",
    "E2_Contriever": "logs/dense_run.jsonl",
    "E3_HybridRRF": "logs/hybrid_run.jsonl",
    "E4_HybridReranked": "logs/hybrid_reranker_run.jsonl",
}


def load_run(log_path):
    with open(log_path) as f:
        records = [json.loads(line) for line in f]
    # Sort by query_id so every system's list is aligned to the same query
    # order -- required for every paired comparison below to be valid.
    records.sort(key=lambda r: r["query_id"])
    return records


def extract_metric(records, key):
    return [r[key] for r in records]


def main():
    runs = {name: load_run(path) for name, path in LOGS.items()}

    reference_ids = [r["query_id"] for r in next(iter(runs.values()))]
    for name, records in runs.items():
        ids = [r["query_id"] for r in records]
        assert ids == reference_ids, (
            f"{name}'s query_id sequence does not match the reference run -- "
            f"paired comparisons require identical, identically-ordered queries."
        )

    print("=" * 70)
    print("PER-SYSTEM BOOTSTRAP CONFIDENCE INTERVALS (95%, 10,000 resamples)")
    print("=" * 70)

    metrics = {}
    output = {"per_system": {}, "pairwise": {}}

    for name, records in runs.items():
        em = extract_metric(records, "em")
        f1 = extract_metric(records, "f1")
        recall = [r.get("recall_at_5") for r in records]
        ndcg = [r.get("ndcg_at_5") for r in records]

        recall_defined = [v for v in recall if v is not None]
        ndcg_defined = [v for v in ndcg if v is not None]

        metrics[name] = {"em": em, "f1": f1, "recall": recall, "ndcg": ndcg}

        print(f"\n{name}")
        pe, lo, hi = bootstrap_ci(em)
        print(f"  EM:        {pe:.4f}  [{lo:.4f}, {hi:.4f}]")
        pe, lo, hi = bootstrap_ci(f1)
        print(f"  F1:        {pe:.4f}  [{lo:.4f}, {hi:.4f}]")
        if recall_defined:
            pe, lo, hi = bootstrap_ci(recall_defined)
            print(f"  Recall@5:  {pe:.4f}  [{lo:.4f}, {hi:.4f}]  (n_defined={len(recall_defined)}/{len(recall)})")
        if ndcg_defined:
            pe, lo, hi = bootstrap_ci(ndcg_defined)
            print(f"  nDCG@5:    {pe:.4f}  [{lo:.4f}, {hi:.4f}]  (n_defined={len(ndcg_defined)}/{len(ndcg)})")

        output["per_system"][name] = {
            "em": dict(zip(["point", "ci_lower", "ci_upper"], bootstrap_ci(em))),
            "f1": dict(zip(["point", "ci_lower", "ci_upper"], bootstrap_ci(f1))),
            "recall_at_5": dict(zip(["point", "ci_lower", "ci_upper"], bootstrap_ci(recall_defined))) if recall_defined else None,
            "ndcg_at_5": dict(zip(["point", "ci_lower", "ci_upper"], bootstrap_ci(ndcg_defined))) if ndcg_defined else None,
            "n_recall_defined": len(recall_defined),
            "n_ndcg_defined": len(ndcg_defined),
        }

    print("\n" + "=" * 70)
    print("PAIRWISE SIGNIFICANCE TESTS (paired, since all systems share queries)")
    print("=" * 70)

    for name_a, name_b in combinations(metrics.keys(), 2):
        print(f"\n{name_a}  vs  {name_b}")

        # --- EM: McNemar's exact test ---
        mc = mcnemar_test(metrics[name_a]["em"], metrics[name_b]["em"])
        print(f"  EM (McNemar):   n_discordant={mc['n_discordant']} "
              f"({name_a} only right: {mc['n_10']}, {name_b} only right: {mc['n_01']})  "
              f"p={mc['p_value']:.4f}")

        # --- F1: paired bootstrap + Wilcoxon ---
        f1_pb = paired_bootstrap_test(metrics[name_a]["f1"], metrics[name_b]["f1"])
        print(f"  F1 (bootstrap): diff={f1_pb['mean_diff']:+.4f}  "
              f"95% CI=[{f1_pb['ci_95_lower']:+.4f}, {f1_pb['ci_95_upper']:+.4f}]  p={f1_pb['p_value']:.4f}")
        f1_wx = wilcoxon_test(metrics[name_a]["f1"], metrics[name_b]["f1"])
        if f1_wx is not None:
            print(f"  F1 (Wilcoxon):  p={f1_wx['p_value']:.4f}")

        # --- Recall@5 / nDCG@5: paired bootstrap over jointly-defined queries ---
        recall_pb = None
        r_a, r_b = paired_defined_only(metrics[name_a]["recall"], metrics[name_b]["recall"])
        if r_a:
            recall_pb = paired_bootstrap_test(r_a, r_b)
            print(f"  Recall@5 (bootstrap, n={len(r_a)}): diff={recall_pb['mean_diff']:+.4f}  "
                  f"95% CI=[{recall_pb['ci_95_lower']:+.4f}, {recall_pb['ci_95_upper']:+.4f}]  p={recall_pb['p_value']:.4f}")

        ndcg_pb = None
        n_a, n_b = paired_defined_only(metrics[name_a]["ndcg"], metrics[name_b]["ndcg"])
        if n_a:
            ndcg_pb = paired_bootstrap_test(n_a, n_b)
            print(f"  nDCG@5 (bootstrap, n={len(n_a)}):   diff={ndcg_pb['mean_diff']:+.4f}  "
                  f"95% CI=[{ndcg_pb['ci_95_lower']:+.4f}, {ndcg_pb['ci_95_upper']:+.4f}]  p={ndcg_pb['p_value']:.4f}")

        pair_key = f"{name_a}_vs_{name_b}"
        output["pairwise"][pair_key] = {
            "em_mcnemar": mc,
            "f1_bootstrap": f1_pb,
            "f1_wilcoxon": f1_wx,
            "recall_at_5_bootstrap": recall_pb,
            "ndcg_at_5_bootstrap": ndcg_pb,
        }

    with open(STATS_OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results written to {STATS_OUTPUT_PATH}")
    
def assert_same_undefined_queries(metrics, metric_key):
    """
    Verify the assumption that 'undefined' queries (relevance metric = None)
    are identical across all systems, since they all score relevance against
    the same shared candidate pool. Structural, not dataset-specific -- but
    checked explicitly rather than assumed, since StreamingQA's candidate
    pools and relevance patterns differ from TriviaQA's.
    """
    undefined_sets = {
        name: {i for i, v in enumerate(m[metric_key]) if v is None}
        for name, m in metrics.items()
    }
    reference = next(iter(undefined_sets.values()))
    for name, s in undefined_sets.items():
        assert s == reference, (
            f"{name}'s undefined-{metric_key} queries differ from other systems "
            f"-- the shared-candidate-pool assumption does not hold here, and "
            f"paired_defined_only needs to handle per-system-differing undefined "
            f"sets instead of assuming they match."
        )

if __name__ == "__main__":
    main()