#!/usr/bin/env python3
"""Kaggle runner: E1-E4 on the clean pilot file plus every attacked pilot pool.
Run from the repo root on Kaggle (GPU). Frozen drivers and config are not edited.
Logs go to logs/pilot_attacks/<pool>__<E>.jsonl (written as .partial, renamed on success)."""
import glob, json, os, subprocess, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.chdir(ROOT)

from src.eval.config_loader import experiment_params
from src.generation.generate import load_model
from src.retrieval.dense import load_dense_model
from src.retrieval.reranker import load_reranker
from run_baseline_streamingqa import run_baseline_streamingqa
from run_dense_streamingqa import run_dense_streamingqa
from run_hybrid_streamingqa import run_hybrid_streamingqa
from run_hybrid_reranker_streamingqa import run_hybrid_cross_encoder_streamingqa

CLEAN = "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
POOLS = "data/processed/attack_pools/pilot/*_n*.jsonl"
OUT = "logs/pilot_attacks"

params = {e: experiment_params(e) for e in ("E1", "E2", "E3", "E4")}
gen_names = {p["generator_model"] for p in params.values()}
assert len(gen_names) == 1, f"generator differs across E1-E4: {gen_names}"
print("Generator:", gen_names)

model, tok = load_model(gen_names.pop())
r_model, r_tok, r_dev = load_dense_model()
rr_model, _rr_device = load_reranker(params["E4"]["reranker_model"])

dense = dict(retriever_model=r_model, retriever_tokenizer=r_tok, retriever_device=r_dev)
RUNS = [
    ("E1", lambda i, l: run_baseline_streamingqa(model=model, tokenizer=tok, input_path=i, log_path=l)),
    ("E2", lambda i, l: run_dense_streamingqa(model=model, tokenizer=tok, input_path=i, log_path=l, **dense)),
    ("E3", lambda i, l: run_hybrid_streamingqa(model=model, tokenizer=tok, input_path=i, log_path=l, **dense)),
    ("E4", lambda i, l: run_hybrid_cross_encoder_streamingqa(
        model=model, tokenizer=tok, input_path=i, log_path=l, reranker_model=rr_model, **dense)),
]

pools = [("clean", CLEAN)] + [(os.path.basename(p)[:-6], p) for p in sorted(glob.glob(POOLS))]
os.makedirs(OUT, exist_ok=True)
record = []
for name, path in pools:
    n_in = sum(1 for l in open(path, encoding="utf-8") if l.strip())
    for exp, fn in RUNS:
        final = f"{OUT}/{name}__{exp}.jsonl"
        if os.path.exists(final):
            print("skip (exists)", final); continue
        tmp = final + ".partial"
        t0 = time.time()
        fn(path, tmp)
        os.replace(tmp, final)
        n_out = sum(1 for l in open(final, encoding="utf-8") if l.strip())
        note = "" if n_out == n_in else f"  WARNING: {n_out} log lines vs {n_in} records"
        print(f"{name} {exp}: {time.time()-t0:.0f}s{note}")
        record.append({"pool": name, "experiment": exp, "input": path, "log": final,
                       "n_records": n_in, "n_log_lines": n_out})

try:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
except Exception:
    commit = None
with open(f"{OUT}/run_manifest.json", "w", encoding="utf-8") as f:
    json.dump({"git_commit": commit, "runs": record}, f, indent=2)
print("Done.")