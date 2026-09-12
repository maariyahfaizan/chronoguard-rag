"""
Weeks 3-4 | StreamingQA Step 2b (revised): build per-query candidate pools
from the pre-filtered relevant-passages shards produced by
fetch_wmt_archives.py, instead of re-running extraction.py against full
year archives (which no longer exist on disk -- they were deleted right
after each year's extraction to keep peak disk usage bounded).

Same gold/distractor selection logic as the original build_streamingqa_pools.py
(±window_days, sparse-window fallback widening, shuffle so gold isn't
predictably first) -- only the data source changed.

NOTE ON THIS REVISION: fetch_wmt_archives.py switched from a single flat
streamingqa_relevant_passages.jsonl to gzip-compressed per-year shards
under streamingqa_relevant_passages/{year}.jsonl.gz (the flat file ran a
20GB Kaggle disk out of space after ~6 of 13 years). Only
load_relevant_passages() changes here to read the shard directory instead
-- everything else (selection logic, output shape) is unchanged.

Input:  data/raw/streamingqa_relevant_passages/{year}.jsonl.gz  (from fetch_wmt_archives.py)
        data/raw/streamingqa_control_sample.jsonl               (from save_snapshot_streamingqa.py)
Output: data/raw/streamingqa_pools_raw.jsonl                    (feeds preprocess_streamingqa.py, unchanged)
"""

import datetime
import gzip
import json
import random
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sample(raw_dir: Path) -> list[dict]:
    sample_path = raw_dir / "streamingqa_control_sample.jsonl"
    with open(sample_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_relevant_passages(raw_dir: Path) -> tuple[dict, list[dict]]:
    """Returns (passages_by_doc_id, all_passages) -- same shape the old
    build_passage_index() produced, just sourced from the gzip-sharded
    per-year directory instead of one flat file."""
    shards_dir = raw_dir / "streamingqa_relevant_passages"
    shard_paths = sorted(shards_dir.glob("*.jsonl.gz"))
    if not shard_paths:
        raise FileNotFoundError(
            f"No shards found in {shards_dir} -- run fetch_wmt_archives.py "
            f"first (this script reads its output, it doesn't create it)."
        )

    by_doc_id = {}
    all_passages = []
    for shard_path in shard_paths:
        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                by_doc_id[p["doc_id"]] = p
                all_passages.append(p)

    all_passages.sort(key=lambda p: p["timestamp"])
    return by_doc_id, all_passages


def _passage_date(p: dict) -> datetime.datetime:
    return datetime.datetime.fromisoformat(p["timestamp"])


def select_distractors(
    gold_doc_id,
    gold_date: datetime.datetime,
    all_passages: list[dict],
    window_days: int,
    n_needed: int,
    rng,
) -> list[dict]:
    lo = gold_date - datetime.timedelta(days=window_days)
    hi = gold_date + datetime.timedelta(days=window_days)

    in_window = [
        p for p in all_passages
        if lo <= _passage_date(p) <= hi and p["doc_id"] != gold_doc_id
    ]

    if len(in_window) < n_needed:
        # Documented fallback: widen by +window_days increments, capped at
        # 8x -- matches RETENTION_MARGIN_MULTIPLIER in
        # fetch_wmt_archives.py, so the data needed to satisfy this
        # widening was actually kept during extraction.
        widened = window_days
        while len(in_window) < n_needed and widened < window_days * 8:
            widened += window_days
            lo = gold_date - datetime.timedelta(days=widened)
            hi = gold_date + datetime.timedelta(days=widened)
            in_window = [
                p for p in all_passages
                if lo <= _passage_date(p) <= hi and p["doc_id"] != gold_doc_id
            ]

    return rng.sample(in_window, min(n_needed, len(in_window)))


def build_pools(cfg: dict, sample: list[dict], by_doc_id: dict, all_passages: list[dict]) -> list[dict]:
    rng = random.Random(cfg["sample"]["seed"])
    window_days = cfg["candidate_pool"]["window_days"]
    pool_size = cfg["candidate_pool"]["candidates_per_query"]

    records = []
    skipped = []
    for q in sample:
        gold_id = q["evidence_id"]
        gold_passage = by_doc_id.get(gold_id)
        if gold_passage is None:
            # Gold evidence wasn't retained during extraction -- means its
            # evidence_ts fell outside RETENTION_MARGIN_MULTIPLIER's window,
            # which shouldn't happen since the margin is centered on gold
            # dates themselves, but flag rather than silently drop.
            skipped.append(q["question_id"])
            continue

        gold_date = _passage_date(gold_passage)
        n_distractors = pool_size - 1
        distractors = select_distractors(
            gold_id, gold_date, all_passages, window_days, n_distractors, rng
        )

        candidates = [{
            "doc_id": gold_id,
            "text": gold_passage["text"],
            "timestamp": gold_passage["timestamp"],
        }] + [
            {"doc_id": d["doc_id"], "text": d["text"], "timestamp": d["timestamp"]}
            for d in distractors
        ]
        rng.shuffle(candidates)

        records.append({
            "query": q["question"],
            "gold_answer": q["answers"][0] if q["answers"] else None,
            "gold_aliases": q["answers"],
            "gold_doc_id": gold_id,
            "candidates": candidates,
        })

    if skipped:
        print(f"WARNING: {len(skipped)} questions had no gold evidence in the "
              f"relevant-passages shards, eval set is {len(records)}/100: {skipped}")

    return records


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    sample = load_sample(raw_dir)
    print(f"Loaded {len(sample)} sampled questions.")

    by_doc_id, all_passages = load_relevant_passages(raw_dir)
    print(f"Loaded {len(all_passages)} relevant passages from shards.")

    print("Building candidate pools "
          f"(+/-{cfg['candidate_pool']['window_days']}d window, "
          f"{cfg['candidate_pool']['candidates_per_query']} candidates/query)...")
    records = build_pools(cfg, sample, by_doc_id, all_passages)

    out_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} pools to {out_path}")