#!/usr/bin/env python3
"""W4-F1 post-freeze validation for E2, E3 and E4 using preloaded notebook models.

IMPORTANT:
    This file must be imported and run from the SAME Kaggle notebook kernel
    that already holds the shared model objects. Do not launch it with `!python`,
    because a separate process cannot reuse the notebook's model objects.

Example notebook call:
    from scripts.smoke_test_e2_e4_post_freeze import run_smoke_test
    report = run_smoke_test(
        model=model,
        tokenizer=tokenizer,
        retriever_model=retriever_model,
        retriever_tokenizer=retriever_tokenizer,
        retriever_device=retriever_device,
        reranker_model=reranker_model,
        n=5,
    )

The script does not load or unload models. It runs E2, E3 and E4 sequentially,
writes only to logs/week4_post_freeze_smoke/ and
results/week4_post_freeze_smoke.json, and never overwrites frozen Week-4 logs.

Pass criteria:
- all requested rows are logged;
- each row retrieves the configured number of passages;
- logged retrieval parameters match configs/streamingqa_eval_config.yaml;
- E4's logged reranker matches the configured reranker.

Retrieval and answer comparisons with frozen logs are reported, not pass
criteria, because frozen runs may not have recorded the same model revisions.
The report records configured model revisions, but does not independently
prove that already-loaded model objects were loaded at those revisions.
"""
import gc
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
os.chdir(ROOT)

OUT = "logs/week4_post_freeze_smoke"
REPORT = "results/week4_post_freeze_smoke.json"
EXPECTED_K = {
    "E2": ("top_k",),
    "E3": ("candidate_top_k", "final_top_k", "rrf_k"),
    "E4": ("candidate_top_k", "fused_top_k", "final_top_k", "rrf_k"),
}


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _validate_experiment(exp, log_path, params, n, sha256_file):
    rows = _read_jsonl(log_path)
    frozen = _read_jsonl(params["log_path"])[:n]
    if len(frozen) < n:
        raise RuntimeError(
            f"{exp} frozen log contains {len(frozen)} rows; requested {n}."
        )

    k = params.get("final_top_k", params.get("top_k"))
    checks = {
        "all_rows_logged": len(rows) == n,
        "retrieved_count_equals_config": all(
            len(row.get("retrieved_passage_indices", [])) == k for row in rows
        ),
    }
    for key in EXPECTED_K[exp]:
        checks[f"logged_{key}_equals_config"] = all(
            row.get(key) == params[key] for row in rows
        )
    if exp == "E4":
        checks["logged_reranker_equals_config"] = all(
            row.get("reranker") == params["reranker_model"] for row in rows
        )

    return {
        "config_params": params,
        "checks": checks,
        "passed": all(checks.values()),
        "same_retrieval_as_frozen_log": [
            row.get("retrieved_passage_indices")
            == frozen_row.get("retrieved_passage_indices")
            for row, frozen_row in zip(rows, frozen)
        ],
        "same_answer_as_frozen_log": [
            row.get("generated_answer") == frozen_row.get("generated_answer")
            for row, frozen_row in zip(rows, frozen)
        ],
        "log": log_path,
        "log_sha256": sha256_file(log_path),
    }


def run_smoke_test(
    *,
    model,
    tokenizer,
    retriever_model,
    retriever_tokenizer,
    retriever_device,
    reranker_model,
    n=5,
):
    """Run the smoke test using model objects already loaded in this notebook."""
    if not isinstance(n, int) or n < 1:
        raise ValueError("n must be a positive integer")

    from src.eval.config_loader import experiment_params, model_revisions
    from src.eval.run_metadata import environment_info, git_info, sha256_file
    from run_dense_streamingqa import run_dense_streamingqa
    from run_hybrid_streamingqa import run_hybrid_streamingqa
    from run_hybrid_reranker_streamingqa import (
        run_hybrid_cross_encoder_streamingqa,
    )

    params = {exp: experiment_params(exp) for exp in ("E2", "E3", "E4")}
    revisions = model_revisions()

    os.makedirs(OUT, exist_ok=True)
    subset = f"{OUT}/frozen_pool_first_{n}.jsonl"
    frozen_pool = params["E2"]["input_path"]

    # Copy the first N frozen records to a separate test input.
    with open(frozen_pool, encoding="utf-8") as source, open(
        subset, "w", encoding="utf-8", newline="\n"
    ) as destination:
        for index, line in enumerate(source):
            if index >= n:
                break
            destination.write(line)

    subset_count = len(_read_jsonl(subset))
    if subset_count != n:
        raise RuntimeError(
            f"Frozen pool contains {subset_count} records; requested {n}."
        )

    dense_args = {
        "retriever_model": retriever_model,
        "retriever_tokenizer": retriever_tokenizer,
        "retriever_device": retriever_device,
    }
    runners = {
        "E2": lambda output: run_dense_streamingqa(
            model=model,
            tokenizer=tokenizer,
            input_path=subset,
            log_path=output,
            **dense_args,
        ),
        "E3": lambda output: run_hybrid_streamingqa(
            model=model,
            tokenizer=tokenizer,
            input_path=subset,
            log_path=output,
            **dense_args,
        ),
        "E4": lambda output: run_hybrid_cross_encoder_streamingqa(
            model=model,
            tokenizer=tokenizer,
            input_path=subset,
            log_path=output,
            reranker_model=reranker_model,
            **dense_args,
        ),
    }

    results = {}
    for exp in ("E2", "E3", "E4"):
        output = f"{OUT}/{exp}.jsonl"
        # Remove only this validator's previous output, never frozen logs.
        if os.path.exists(output):
            os.remove(output)

        print(f"Running {exp} on {n} frozen queries...", flush=True)
        runners[exp](output)

        if not os.path.isfile(output):
            raise RuntimeError(f"{exp} runner did not create {output}")

        results[exp] = _validate_experiment(
            exp, output, params[exp], n, sha256_file
        )
        print(
            exp,
            "PASS" if results[exp]["passed"] else "FAIL",
            results[exp]["checks"],
            flush=True,
        )

        # Clear transient allocations/caches between runs. The shared models
        # remain referenced and are not deleted.
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    report = {
        "purpose": (
            "W4-F1 post-freeze validation using preloaded notebook models; "
            "does not change the frozen Week-4 baseline"
        ),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": git_info(),
        "frozen_tag": "week4-frozen",
        "frozen_pool": frozen_pool,
        "frozen_pool_sha256": sha256_file(frozen_pool),
        "subset": subset,
        "subset_sha256": sha256_file(subset),
        "n_queries": n,
        "configured_model_revisions": revisions,
        "note": (
            "The validator reuses model objects supplied by the notebook and "
            "does not independently verify their loaded revisions. Frozen Week-4 "
            "runs may not have recorded model revisions; comparisons are reported "
            "but are not pass criteria."
        ),
        "environment": environment_info(),
        "results": results,
        "result": (
            "PASS"
            if len(results) == 3 and all(item["passed"] for item in results.values())
            else "FAIL"
        ),
    }

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as output_file:
        json.dump(report, output_file, indent=2)
    print("saved", REPORT, report["result"], flush=True)
    return report


if __name__ == "__main__":
    raise SystemExit(
        "This validator requires the model objects from the active notebook "
        "kernel. Import run_smoke_test(...) in that notebook; do not run this "
        "file with `!python`, which would create a separate process."
    )
