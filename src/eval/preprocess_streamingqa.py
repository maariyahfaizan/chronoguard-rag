"""
Weeks 3-4 | StreamingQA Step 2c: emit the final {query, gold_answer,
gold_aliases, candidates} records that src/retrieval/{bm25,dense,hybrid,
reranker}.py and src/eval/evaluator.py already consume (same shape as the
TriviaQA control pools) -- no changes to retrieval/eval code needed.

Input:  data/raw/streamingqa_pools_raw.jsonl        (from build_streamingqa_pools.py)
Output: data/processed/streamingqa_control_pools.jsonl

Strips the `gold_doc_id` audit field (useful while building pools, not part
of the shared downstream shape) and validates every record before writing,
so a malformed pool fails loudly here rather than surfacing as a confusing
retrieval-stage bug later.
"""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

REQUIRED_KEYS = {"query", "gold_answer", "gold_aliases", "candidates"}
REQUIRED_CANDIDATE_KEYS = {"doc_id", "text", "timestamp"}


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_record(r: dict, cfg: dict) -> list[str]:
    problems = []
    missing = REQUIRED_KEYS - r.keys()
    if missing:
        problems.append(f"missing top-level keys: {missing}")
        return problems  # can't check further without these

    if not r["candidates"]:
        problems.append("empty candidate pool")
    expected_size = cfg["candidate_pool"]["candidates_per_query"]
    if len(r["candidates"]) != expected_size:
        problems.append(
            f"pool size {len(r['candidates'])} != configured "
            f"candidates_per_query {expected_size}"
        )
    if r["gold_doc_id"] not in {c["doc_id"] for c in r["candidates"]}:
        problems.append("gold_doc_id not present among its own candidates")

    for c in r["candidates"]:
        c_missing = REQUIRED_CANDIDATE_KEYS - c.keys()
        if c_missing:
            problems.append(f"candidate missing keys: {c_missing}")
            break  # one report is enough per record

    return problems


def emit_shared_shape(r: dict) -> dict:
    return {
        "query": r["query"],
        "gold_answer": r["gold_answer"],
        "gold_aliases": r["gold_aliases"],
        "candidates": r["candidates"],
    }


if __name__ == "__main__":
    cfg = load_config()
    in_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path = REPO_ROOT / cfg["output"]["processed_path"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_written, n_flagged = 0, 0
    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            problems = validate_record(r, cfg)
            if problems:
                n_flagged += 1
                print(f"SKIPPING query {r.get('query', '?')!r}: {problems}")
                continue
            fout.write(json.dumps(emit_shared_shape(r)) + "\n")
            n_written += 1

    print(f"Wrote {n_written} validated records to {out_path}")
    if n_flagged:
        print(f"WARNING: {n_flagged} records failed validation and were dropped "
              f"-- final eval set is {n_written}/100, not 100/100. Decide whether "
              f"that's acceptable for the paper or worth investigating before Step 3.")