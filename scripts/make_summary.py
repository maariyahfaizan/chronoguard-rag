#!/usr/bin/env python3
"""Build the frozen clean-baseline summary from RAW per-query logs only.

Outputs (one row per dataset x experiment):
    results/summary.json   -> {"meta": {...}, "rows": [...]}
    results/summary.csv    -> same rows, flattened

Every number is recomputed from the JSONL logs (plus, for the headline FreshQA metric, the
second judge's raw verdict file). Nothing is hand-typed and nothing is read from earlier
summary files. Paper tables should be generated from results/summary.json.

FreshQA has two judged-accuracy metrics:
    fresheval_judge2_correct   HEADLINE. Qwen2.5-14B-Instruct, validated against human labels.
    fresheval_correct          DEVELOPMENT ONLY. The Mistral-7B self-judge, shown to be lenient.
Both are reported; do not present the Mistral one as the headline.

Run from the repo root, AFTER the final commit of the frozen baseline:
    python scripts/make_summary.py
Dry run on one dataset while others are not ready (do NOT commit that output):
    python scripts/make_summary.py --only freshqa
"""
import argparse
import csv
import glob
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ----------------------------------------------------------------------------
# EDIT THIS BLOCK if paths differ. Missing files stop the script.
# ----------------------------------------------------------------------------
SEED = 42            # bootstrap seed; also the fallback if no seed is found in the config
N_BOOT = 10_000
CONDITION = "clean"  # only rows with this attack_condition are used (if the field exists)
OUT_DIR = Path("results")

DATASETS = {
    "streamingqa": {
        "config": "configs/streamingqa_eval_config.yaml",
        # Snapshot identity = the frozen chunked pool (A2 output) + the config that built it.
        "snapshots": ["data/processed/streamingqa_control_pools_chunked.jsonl",
                      "configs/streamingqa_config.yaml"],
        "pool": "data/processed/streamingqa_control_pools_chunked.jsonl",
        "logs": {
            "E1": "logs/streamingqa_baseline_run_chunked.jsonl",
            "E2": "logs/streamingqa_dense_run_chunked.jsonl",
            "E3": "logs/streamingqa_hybrid_run_chunked.jsonl",
            "E4": "logs/streamingqa_hybrid_reranker_run_chunked.jsonl",
        },
    },
    "freshqa": {
        # Not named anywhere I could see: the first existing candidate / the matching files are
        # used and printed, and their hashes are recorded in the output. Edit if they are wrong.
        "config_candidates": ["configs/freshqa_eval_config.yaml", "configs/freshqa_config.yaml"],
        "snapshot_globs": ["data/raw/freshqa*"],
        "pool": None,  # 646 MB, untracked; gold-validated count is skipped
        "logs": {
            "E1": "logs/freshqa_baseline_run.jsonl",
            "E2": "logs/freshqa_dense_run.jsonl",
            "E3": "logs/freshqa_hybrid_run.jsonl",
            "E4": "logs/freshqa_hybrid_reranker.jsonl",
        },
        "extra_metrics": ["fresheval_correct"],          # Mistral self-judge (development only)
        "judge2": {                                      # Qwen2.5-14B-Instruct (headline)
            "path": "results/judge_validation/judge2_all.jsonl",
            "metric": "fresheval_judge2_correct",
            "systems": {"E1": "E1_BM25", "E2": "E2_Dense", "E3": "E3_Hybrid",
                        "E4": "E4_Hybrid+Reranker"},
        },
    },
    "triviaqa": {
        # StreamingQA's config calls this file configs/triviaqa_config.yaml.
        "config": "configs/triviaqa_config.yaml",
        "snapshots": ["data/processed/triviaqa_control_clean.jsonl"],   # shared.input_path
        "pool": None,
        "logs": {
            "E1": "logs/baseline_run.jsonl",
            "E2": "logs/dense_run.jsonl",
            "E3": "logs/hybrid_run.jsonl",
            "E4": "logs/hybrid_reranker_run.jsonl",
        },
    },
}

# Per-query field names written by the shared evaluator.
METRICS = [
    "em",
    "f1",
    "recall_at_5",
    "ndcg_at_5",
    "fraction_top_5_violating",
    "valid_evidence_recall_at_5",
    "time_valid_answer_accuracy",
]
# ----------------------------------------------------------------------------


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def find_key(obj, key):
    """First value stored under `key` anywhere in a nested dict/list."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def config_value(config_path, key):
    """Read a documented value from the YAML (used to read the seed and to CROSS-CHECK counts)."""
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return find_key(yaml.safe_load(f), key)
    except Exception:
        return None


def read_seed(config_path):
    seed = config_value(config_path, "seed")
    try:
        return int(seed) if seed is not None else SEED
    except (TypeError, ValueError):
        return SEED


def load_log(path):
    """Keep only the chosen attack condition and the LAST record per query_id
    (resumable logs can contain duplicates)."""
    by_qid = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "attack_condition" in r and r["attack_condition"] != CONDITION:
                continue
            # Older logs (e.g. TriviaQA) may have no query_id: fall back to line order,
            # which means duplicates cannot be detected for such logs.
            qid = r.get("query_id", f"_line{len(by_qid)}")
            r["query_id"] = qid
            by_qid[qid] = r
    return list(by_qid.values())


def mean_ci(values, rng):
    """Mean and percentile bootstrap 95% CI over the defined (non-None) values."""
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return {"value": None, "ci_lo": None, "ci_hi": None, "n_defined": 0}
    arr = np.asarray(vals)
    idx = rng.integers(0, n, size=(N_BOOT, n))
    boots = arr[idx].mean(axis=1)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"value": float(arr.mean()), "ci_lo": float(lo), "ci_hi": float(hi), "n_defined": n}


def count_gold_validated(pool_path, query_ids):
    """Queries with at least one validated gold chunk, from the pool file. Returns None if the
    pool is missing or carries no validation field (a wrong guess is never reported as data)."""
    if not pool_path or not Path(pool_path).exists():
        return None
    seen_field, validated = False, set()
    with open(pool_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            qid = r.get("query_id")
            if qid not in query_ids:
                continue
            cands = r.get("candidates") or r.get("passages") or []
            for c in cands:
                if isinstance(c, dict) and "gold_validated" in c:
                    seen_field = True
                    if c["gold_validated"]:
                        validated.add(qid)
            if r.get("gold_chunk_ids"):
                seen_field = True
                validated.add(qid)
    return len(validated) if seen_field else None


def load_judge2(path):
    """Latest verdict per (system, query_id) from the second judge's raw file."""
    last = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                last[(r["system"], str(r["query_id"]))] = r
    return last


def resolve_paths(name, d):
    """Fill in config and snapshot paths for datasets that use candidates/globs."""
    if "config" not in d:
        found = [p for p in d["config_candidates"] if Path(p).exists()]
        if not found:
            sys.exit(f"{name}: none of these configs exist: {d['config_candidates']}. Edit DATASETS.")
        d["config"] = found[0]
    if "snapshots" not in d:
        files = sorted(p for g in d["snapshot_globs"] for p in glob.glob(g) if Path(p).is_file())
        if not files:
            sys.exit(f"{name}: no snapshot files match {d['snapshot_globs']}. Edit DATASETS.")
        d["snapshots"] = files
    print(f"{name}: config = {d['config']}")
    print(f"{name}: snapshot files = {d['snapshots']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(DATASETS), help="partial run for testing; do not commit")
    args = ap.parse_args()
    selected = {k: v for k, v in DATASETS.items() if not args.only or k == args.only}

    for name, d in selected.items():
        resolve_paths(name, d)

    missing = []
    for name, d in selected.items():
        extra = [d["judge2"]["path"]] if d.get("judge2") else []
        for p in [d["config"], *d["snapshots"], *d["logs"].values(), *extra]:
            if not Path(p).exists():
                missing.append(f"{name}: {p}")
    if missing:
        sys.exit("Missing files (edit the DATASETS block):\n  " + "\n  ".join(missing))

    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain"))
    if dirty:
        print("WARNING: working tree has uncommitted changes; the recorded commit hash does not "
              "describe the exact state. Commit first, then rerun.", file=sys.stderr)
    if args.only:
        print("WARNING: --only gives a PARTIAL summary. Do not commit it.", file=sys.stderr)

    rows = []
    for name, d in selected.items():
        config_sha = sha256_file(d["config"])
        snapshot_hashes = {p: sha256_file(p) for p in d["snapshots"]}
        seed = read_seed(d["config"])
        metrics = METRICS + d.get("extra_metrics", [])

        j2cfg = d.get("judge2")
        j2_all = load_judge2(j2cfg["path"]) if j2cfg else None
        j2_sha = sha256_file(j2cfg["path"]) if j2cfg else None

        for exp, log_path in d["logs"].items():
            recs = load_log(log_path)
            # A field that is absent everywhere is a naming problem, not "undefined".
            # (TriviaQA has no temporal fields by design, so those notes are expected there.)
            for m in metrics:
                if recs and not any(m in r for r in recs):
                    print(f"  NOTE {name} {exp}: field '{m}' not found in any record", file=sys.stderr)

            rng = np.random.default_rng(SEED)  # same stream per row -> reproducible CIs
            row = {
                "dataset": name,
                "experiment": exp,
                "n_queries": len(recs),
                "n_gold_validated": count_gold_validated(d["pool"], {r["query_id"] for r in recs}),
                "n_retrieval_defined": sum(r.get("recall_at_5") is not None for r in recs),
                "n_ndcg_defined": sum(r.get("ndcg_at_5") is not None for r in recs),
                "metrics": {m: mean_ci([r.get(m) for r in recs], rng) for m in metrics},
                "config_path": d["config"],
                "config_sha256": config_sha,
                "snapshot_sha256": snapshot_hashes,
                "log_path": log_path,
                "log_sha256": sha256_file(log_path),
                "seed": seed,
                "bootstrap": {"n_resamples": N_BOOT, "seed": SEED, "type": "percentile"},
                "attack_condition": CONDITION,
            }

            if j2cfg:
                system = j2cfg["systems"][exp]
                entries = {qid: e for (s, qid), e in j2_all.items() if s == system}
                values = []
                for r in recs:
                    e = entries.get(str(r["query_id"]))
                    values.append(None if (e is None or e.get("correct") is None) else bool(e["correct"]))
                row["metrics"][j2cfg["metric"]] = mean_ci(values, rng)
                n_def = row["metrics"][j2cfg["metric"]]["n_defined"]
                if n_def < len(recs):
                    print(f"  WARNING {name} {exp}: second judge has {n_def}/{len(recs)} verdicts; "
                          "rerun judge2_run.py --all to retry the missing ones", file=sys.stderr)
                row["judge2"] = {
                    "metric": j2cfg["metric"],
                    "path": j2cfg["path"],
                    "sha256": j2_sha,
                    "models": sorted({str(e.get("model")) for e in entries.values()}),
                    "revisions": sorted({str(e.get("revision")) for e in entries.values()}),
                }

            rows.append(row)
            print(f"{name} {exp}: n={row['n_queries']}")

            # shared.gold_validated is documented in the StreamingQA config; a mismatch means
            # one of the two is stale.
            cfg_gold = config_value(d["config"], "gold_validated")
            if cfg_gold is not None and row["n_gold_validated"] is not None \
                    and cfg_gold != row["n_gold_validated"]:
                print(f"  WARNING {name} {exp}: pool gives {row['n_gold_validated']} gold-validated "
                      f"queries, config documents {cfg_gold}", file=sys.stderr)

    meta = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "git_dirty": dirty,
        "partial_run": bool(args.only),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "note": ("Computed from raw logs (and the second judge's raw verdict file). Undefined "
                 "values (None) are excluded, never counted as 0. For FreshQA, "
                 "fresheval_judge2_correct is the headline judged accuracy; fresheval_correct "
                 "(Mistral-7B self-judge) is a development metric. See results/judge_validation."),
    }

    OUT_DIR.mkdir(exist_ok=True)
    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows}, f, indent=2)

    all_metrics = sorted({m for r in rows for m in r["metrics"]}, key=lambda m: (m not in METRICS, m))
    head = ["dataset", "experiment", "n_queries", "n_gold_validated", "n_retrieval_defined",
            "n_ndcg_defined"]
    for m in all_metrics:
        head += [m, f"{m}_ci_lo", f"{m}_ci_hi", f"{m}_n_defined"]
    head += ["config_sha256", "snapshot_sha256", "log_sha256", "judge2_model", "judge2_revision",
             "judge2_sha256", "seed", "git_commit", "git_dirty"]
    with open(OUT_DIR / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in rows:
            line = [r["dataset"], r["experiment"], r["n_queries"], r["n_gold_validated"],
                    r["n_retrieval_defined"], r["n_ndcg_defined"]]
            for m in all_metrics:
                x = r["metrics"].get(m) or {}
                line += [x.get("value"), x.get("ci_lo"), x.get("ci_hi"), x.get("n_defined")]
            j2 = r.get("judge2") or {}
            line += [r["config_sha256"], ";".join(f"{p}:{h[:12]}" for p, h in r["snapshot_sha256"].items()),
                     r["log_sha256"], ";".join(j2.get("models", [])), ";".join(j2.get("revisions", [])),
                     (j2.get("sha256") or "")[:12], r["seed"], commit, dirty]
            w.writerow(line)

    print(f"Wrote {OUT_DIR / 'summary.json'} and {OUT_DIR / 'summary.csv'}")


if __name__ == "__main__":
    main()