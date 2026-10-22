#!/usr/bin/env python3
"""Kaggle runner (protocol v2): E1-E4 on every attacked pilot pool.

Run from the repo root on Kaggle (GPU):
    python scripts/run_pilot_attacks_kaggle.py            # all 15 pools x 4 systems
    python scripts/run_pilot_attacks_kaggle.py --dry-run  # checks inputs only, loads no model

Inputs:  data/processed/attack_pools/pilot_v2_nested/*_n*.jsonl  (+ pilot_pools_manifest.json)
Outputs: logs/pilot_attacks_v2_nested/<pool>__<E>.jsonl and run_manifest.json

The clean pilot is NOT rerun. Attacked runs are compared with the existing
clean logs in logs/pilot_attacks/clean__E*.jsonl, which are only read and
hashed here, never written.

Every model is loaded at the revision pinned in configs/model_revisions.yaml,
and the revision transformers actually resolved is checked against the pin.
Every log row carries attack_condition, source_qa_id, poison slots, attack
seed and a run_metadata block (model names and revisions, config hash, pool
hash, git commit, seeds, package and environment versions).
Logs are written as .partial and renamed on success; an existing final log is
skipped, so a crashed session can be resumed.
"""
import argparse
import glob
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)

from src.attacks.pilot_protocol import BASE_SEED, POOL_DIR, PROTOCOL_VERSION  # noqa: E402
from src.eval.config_loader import EVAL_CONFIG_PATH, MODEL_REVISIONS_PATH, experiment_params, model_revisions  # noqa: E402
from src.eval.run_metadata import build_run_metadata, environment_info, git_info, sha256_file  # noqa: E402

POOLS = os.path.join(os.path.relpath(POOL_DIR, ROOT), "*_n*.jsonl")
MANIFEST = os.path.join(os.path.relpath(POOL_DIR, ROOT), "pilot_pools_manifest.json")
CLEAN_LOGS = "logs/pilot_attacks/clean__{exp}.jsonl"
OUT = "logs/pilot_attacks_v2_nested"
TORCH_SEED = 0
EXPERIMENTS = ("E1", "E2", "E3", "E4")
GENERATOR, RETRIEVER, RERANKER = ("mistralai/Mistral-7B-Instruct-v0.2", "facebook/contriever",
                                  "BAAI/bge-reranker-base")


def loaded_revision(model):
    """Commit hash transformers resolved when loading (None if unavailable)."""
    for candidate in (model, getattr(model, "model", None)):
        config = getattr(candidate, "config", None)
        if config is not None and getattr(config, "_commit_hash", None):
            return config._commit_hash
    try:  # sentence-transformers CrossEncoder keeps the HF model in its first module
        return model[0].auto_model.config._commit_hash
    except Exception:
        return None


def check_inputs():
    params = {e: experiment_params(e) for e in EXPERIMENTS}
    revisions = model_revisions()
    gen_names = {p["generator_model"] for p in params.values()}
    assert gen_names == {GENERATOR}, f"generator differs across E1-E4: {gen_names}"
    assert params["E4"]["reranker_model"] == RERANKER, params["E4"]["reranker_model"]
    for name in (GENERATOR, RETRIEVER, RERANKER):
        assert name in revisions, f"no pinned revision for {name}"

    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    assert manifest["protocol_version"] == PROTOCOL_VERSION, manifest["protocol_version"]
    expected = {os.path.basename(p["file"]): p["sha256"] for p in manifest["pools"]}
    pools = sorted(glob.glob(POOLS))
    assert len(pools) == len(expected) == 15, (len(pools), len(expected))
    for path in pools:
        assert sha256_file(path) == expected[os.path.basename(path)], f"{path} differs from manifest"

    clean = {e: CLEAN_LOGS.format(exp=e) for e in EXPERIMENTS}
    for path in clean.values():
        assert os.path.exists(path), f"missing clean log {path}"
    return params, revisions, pools, clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="check inputs, load no model")
    args = parser.parse_args()

    params, revisions, pools, clean_logs = check_inputs()
    git = git_info()
    print(f"Protocol {PROTOCOL_VERSION}: {len(pools)} pools x {len(EXPERIMENTS)} systems")
    print("Pinned revisions:", json.dumps(revisions, indent=2))
    print("Git:", git)
    if args.dry_run:
        print("Dry run OK: inputs, manifest hashes, pins and clean logs all present.")
        return

    import torch

    from src.generation.generate import load_model
    from src.retrieval.dense import load_dense_model
    from src.retrieval.reranker import load_reranker
    from run_baseline_streamingqa import run_baseline_streamingqa
    from run_dense_streamingqa import run_dense_streamingqa
    from run_hybrid_streamingqa import run_hybrid_streamingqa
    from run_hybrid_reranker_streamingqa import run_hybrid_cross_encoder_streamingqa

    torch.manual_seed(TORCH_SEED)
    model, tok = load_model(GENERATOR, revision=revisions[GENERATOR])
    r_model, r_tok, r_dev = load_dense_model(RETRIEVER, revision=revisions[RETRIEVER])
    rr_model, _rr_device = load_reranker(params["E4"]["reranker_model"], revision=revisions[RERANKER])

    loaded = {GENERATOR: loaded_revision(model), RETRIEVER: loaded_revision(r_model),
              RERANKER: loaded_revision(rr_model)}
    for name, rev in loaded.items():
        if rev is not None and rev != revisions[name]:
            raise SystemExit(f"{name}: loaded revision {rev} != pinned {revisions[name]}")
        print(f"{name}: pinned {revisions[name]} loaded {rev or 'not reported by library'}")

    def model_block(names):
        roles = {GENERATOR: "generator", RETRIEVER: "dense_retriever", RERANKER: "reranker"}
        return {roles[n]: {"name": n, "pinned_revision": revisions[n], "loaded_revision": loaded[n]}
                for n in names}

    models_for = {"E1": [GENERATOR], "E2": [GENERATOR, RETRIEVER], "E3": [GENERATOR, RETRIEVER],
                  "E4": [GENERATOR, RETRIEVER, RERANKER]}
    dense = dict(retriever_model=r_model, retriever_tokenizer=r_tok, retriever_device=r_dev)
    runs = {
        "E1": lambda i, l, m: run_baseline_streamingqa(model=model, tokenizer=tok, input_path=i,
                                                       log_path=l, run_metadata=m),
        "E2": lambda i, l, m: run_dense_streamingqa(model=model, tokenizer=tok, input_path=i,
                                                    log_path=l, run_metadata=m, **dense),
        "E3": lambda i, l, m: run_hybrid_streamingqa(model=model, tokenizer=tok, input_path=i,
                                                     log_path=l, run_metadata=m, **dense),
        "E4": lambda i, l, m: run_hybrid_cross_encoder_streamingqa(
            model=model, tokenizer=tok, input_path=i, log_path=l, run_metadata=m,
            reranker_model=rr_model, **dense),
    }

    environment = environment_info()
    config_files = {"streamingqa_eval_config.yaml": EVAL_CONFIG_PATH,
                    "model_revisions.yaml": MODEL_REVISIONS_PATH,
                    "pilot_pools_manifest.json": MANIFEST}
    os.makedirs(OUT, exist_ok=True)
    record = []

    for path in pools:
        name = os.path.basename(path)[:-6]
        n_in = sum(1 for line in open(path, encoding="utf-8") if line.strip())
        for exp in EXPERIMENTS:
            final = f"{OUT}/{name}__{exp}.jsonl"
            meta = build_run_metadata(
                experiment=exp, pool_name=name, pool_path=path, params=params[exp],
                models=model_block(models_for[exp]), config_files=config_files,
                torch_seed=TORCH_SEED, attack_base_seed=BASE_SEED,
                protocol_version=PROTOCOL_VERSION, git=git, environment=environment)
            if os.path.exists(final):
                print("skip (exists)", final)
            else:
                tmp = final + ".partial"
                t0 = time.time()
                runs[exp](path, tmp, meta)
                os.replace(tmp, final)
                print(f"{name} {exp}: {time.time() - t0:.0f}s")
            n_out = sum(1 for line in open(final, encoding="utf-8") if line.strip())
            if n_out != n_in:
                print(f"  WARNING: {n_out} log lines vs {n_in} records")
            record.append({"pool": name, "experiment": exp, "input": path.replace("\\", "/"),
                           "log": final, "n_records": n_in, "n_log_lines": n_out,
                           "pool_sha256": meta["pool_sha256"], "log_sha256": sha256_file(final),
                           "config_hash": meta["config_hash"]})

    with open(f"{OUT}/run_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"protocol_version": PROTOCOL_VERSION, "git": git, "environment": environment,
                   "model_revisions_pinned": revisions, "model_revisions_loaded": loaded,
                   "torch_seed": TORCH_SEED, "attack_base_seed": BASE_SEED,
                   "clean_logs_reused_not_rerun": {e: {"path": p, "sha256": sha256_file(p)}
                                                   for e, p in clean_logs.items()},
                   "runs": record}, f, indent=2)
    print("Done.")


if __name__ == "__main__":
    main()
