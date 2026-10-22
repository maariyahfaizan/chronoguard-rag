#!/usr/bin/env python3
"""Week-4 W4-F1: config-driven smoke tests for E2, E3 and E4 (POST-FREEZE validation).

Run from the repo root on Kaggle (GPU):
    python scripts/smoke_test_e2_e4_post_freeze.py            # first 5 frozen StreamingQA queries
    python scripts/smoke_test_e2_e4_post_freeze.py --n 10

This does NOT change the frozen Week-4 baseline. It reads the frozen chunked
pool and frozen E2-E4 logs, and writes only to logs/week4_post_freeze_smoke/
and results/week4_post_freeze_smoke.json.

Each driver is called with NO explicit parameters other than model objects and
input/log paths, so every retrieval parameter (top_k, candidate_top_k,
fused_top_k, final_top_k, rrf_k, reranker model) must come from
configs/streamingqa_eval_config.yaml. The test then checks:
  - pass criteria: every row was logged; logged parameters equal the YAML;
    each row retrieved exactly the configured number of passages;
  - reported, not pass criteria: whether retrieved indices and answers equal
    the frozen Week-4 logs for the same queries. The frozen runs did not
    record model revisions, so a difference is reported as such and is not
    a failure.
Models are loaded at the revisions pinned in configs/model_revisions.yaml.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)

from src.eval.config_loader import experiment_params, model_revisions  # noqa: E402
from src.eval.run_metadata import environment_info, git_info, sha256_file  # noqa: E402

OUT = "logs/week4_post_freeze_smoke"
REPORT = "results/week4_post_freeze_smoke.json"
EXPECTED_K = {"E2": ("top_k",), "E3": ("candidate_top_k", "final_top_k", "rrf_k"),
              "E4": ("candidate_top_k", "fused_top_k", "final_top_k", "rrf_k")}


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5)
    args = parser.parse_args()

    import torch

    from src.generation.generate import load_model
    from src.retrieval.dense import load_dense_model
    from src.retrieval.reranker import load_reranker
    from run_dense_streamingqa import run_dense_streamingqa
    from run_hybrid_streamingqa import run_hybrid_streamingqa
    from run_hybrid_reranker_streamingqa import run_hybrid_cross_encoder_streamingqa

    params = {e: experiment_params(e) for e in ("E2", "E3", "E4")}
    revs = model_revisions()
    torch.manual_seed(0)
    model, tok = load_model(params["E2"]["generator_model"],
                            revision=revs[params["E2"]["generator_model"]])
    r_model, r_tok, r_dev = load_dense_model("facebook/contriever", revision=revs["facebook/contriever"])
    rr_model, _ = load_reranker(params["E4"]["reranker_model"], revision=revs[params["E4"]["reranker_model"]])
    dense = dict(retriever_model=r_model, retriever_tokenizer=r_tok, retriever_device=r_dev)

    os.makedirs(OUT, exist_ok=True)
    subset = f"{OUT}/frozen_pool_first_{args.n}.jsonl"
    frozen_pool = params["E2"]["input_path"]
    with open(frozen_pool, encoding="utf-8") as src, open(subset, "w", encoding="utf-8", newline="\n") as dst:
        for i, line in enumerate(src):
            if i >= args.n:
                break
            dst.write(line)

    runs = {
        "E2": lambda log: run_dense_streamingqa(model=model, tokenizer=tok, input_path=subset,
                                                log_path=log, **dense),
        "E3": lambda log: run_hybrid_streamingqa(model=model, tokenizer=tok, input_path=subset,
                                                 log_path=log, **dense),
        "E4": lambda log: run_hybrid_cross_encoder_streamingqa(
            model=model, tokenizer=tok, input_path=subset, log_path=log,
            reranker_model=rr_model, **dense),
    }

    results = {}
    for exp, run in runs.items():
        log = f"{OUT}/{exp}.jsonl"
        run(log)
        rows = read_jsonl(log)
        frozen = read_jsonl(params[exp]["log_path"])[: args.n]
        p = params[exp]
        k = p.get("final_top_k", p["top_k"])
        checks = {
            "all_rows_logged": len(rows) == args.n,
            "retrieved_count_equals_config": all(len(r["retrieved_passage_indices"]) == k for r in rows),
        }
        for key in EXPECTED_K[exp]:
            checks[f"logged_{key}_equals_config"] = all(r.get(key) == p[key] for r in rows)
        if exp == "E4":
            checks["logged_reranker_equals_config"] = all(r.get("reranker") == p["reranker_model"]
                                                          for r in rows)
        results[exp] = {
            "config_params": p,
            "checks": checks,
            "passed": all(checks.values()),
            "same_retrieval_as_frozen_log": [a["retrieved_passage_indices"] == b["retrieved_passage_indices"]
                                             for a, b in zip(rows, frozen)],
            "same_answer_as_frozen_log": [a["generated_answer"] == b["generated_answer"]
                                          for a, b in zip(rows, frozen)],
            "log": log,
            "log_sha256": sha256_file(log),
        }
        print(exp, "PASS" if results[exp]["passed"] else "FAIL", checks)

    report = {
        "purpose": "W4-F1 post-freeze validation; does not change the frozen Week-4 baseline",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_info(),
        "frozen_tag": "week4-frozen",
        "frozen_pool": frozen_pool,
        "frozen_pool_sha256": sha256_file(frozen_pool),
        "n_queries": args.n,
        "model_revisions_pinned_for_this_test": revs,
        "note": ("The frozen Week-4 runs did not record model revisions; differences from the "
                 "frozen logs are reported, not treated as failures."),
        "environment": environment_info(),
        "results": results,
        "result": "PASS" if all(r["passed"] for r in results.values()) else "FAIL",
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("saved", REPORT, report["result"])
    sys.exit(0 if report["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
