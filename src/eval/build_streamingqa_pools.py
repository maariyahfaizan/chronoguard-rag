"""
Weeks 3-4 | StreamingQA Step 2b: build per-query candidate pools.

For each of the 100 sampled questions:
  1. Deduplicate the downloaded WMT year-archives against the sorting-key list.
  2. Extract passages, keeping each passage's source date (prepend_date=True).
  3. Locate the GOLD passage via the question's evidence_id.
  4. Draw DISTRACTORS from passages whose date falls within +/- window_days
     of evidence_ts (per configs/streamingqa_config.yaml), excluding gold.
  5. Cap the pool at candidates_per_query total (gold + distractors).

ASSUMPTION FLAGGED: this imports `extraction` from the streamingqa repo
(google-deepmind/streamingqa) using the corrected kwarg names we confirmed
against the actual source (not the README, which has typos):

    get_deduplicated_wmt_docs(wmt_archive_files, deduplicated_sorting_keys_file)
    get_wmt_passages_from_docs(wmt_docs, prepend_date=True)

I have not seen your repo's actual directory layout for where the
streamingqa package/extraction.py lives (only its docstring, from earlier
research) -- the `sys.path` line below is a placeholder. Point it at
wherever you vendored/installed google-deepmind/streamingqa before running,
and shout if the real function signature differs from what's above.
"""

import datetime
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

# TODO: point this at wherever google-deepmind/streamingqa is vendored,
# e.g. REPO_ROOT / "third_party" / "streamingqa"
sys.path.insert(0, str(REPO_ROOT / "third_party" / "streamingqa"))
import extraction  # noqa: E402  (path must be set before this import)


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sample(raw_dir: Path) -> list[dict]:
    sample_path = raw_dir / "streamingqa_control_sample.jsonl"
    with open(sample_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def build_deduped_docs(cfg: dict, raw_dir: Path):
    wmt_archive_files = [
        raw_dir / "wmt" / cfg["evidence_source"]["filename_pattern"].format(year=y)
        for y in cfg["evidence_source"]["years"]
    ]
    sorting_keys_file = raw_dir / "wmt_sorting_key_ids.txt.gz"
    return extraction.get_deduplicated_wmt_docs(
        wmt_archive_files=[str(p) for p in wmt_archive_files],
        deduplicated_sorting_keys_file=str(sorting_keys_file),
    )


def build_passage_index(wmt_docs, prepend_date: bool):
    """Returns (passages_by_evidence_id, passages_sorted_by_date).

    ASSUMPTION FLAGGED: I'm assuming get_wmt_passages_from_docs yields
    objects/dicts exposing an `evidence_id`, a `text`, and a `date`
    (datetime or ISO string) -- matching the fields StreamingQA's own
    question records use to point at evidence. If the real return shape
    differs (e.g. a different key name), this indexing step needs those
    field names swapped in.
    """
    passages = extraction.get_wmt_passages_from_docs(wmt_docs, prepend_date=prepend_date)

    by_evidence_id = {}
    all_passages = []
    for p in passages:
        pid = p["evidence_id"] if isinstance(p, dict) else p.evidence_id
        by_evidence_id[pid] = p
        all_passages.append(p)

    all_passages.sort(key=lambda p: _passage_date(p))
    return by_evidence_id, all_passages


def _passage_date(p) -> datetime.datetime:
    raw = p["date"] if isinstance(p, dict) else p.date
    if isinstance(raw, datetime.datetime):
        return raw
    return datetime.datetime.fromisoformat(raw)


def _passage_text(p) -> str:
    return p["text"] if isinstance(p, dict) else p.text


def select_distractors(
    gold_evidence_id,
    gold_date: datetime.datetime,
    all_passages: list,
    window_days: int,
    n_needed: int,
    rng,
) -> list:
    lo = gold_date - datetime.timedelta(days=window_days)
    hi = gold_date + datetime.timedelta(days=window_days)

    in_window = [
        p for p in all_passages
        if lo <= _passage_date(p) <= hi
        and (p["evidence_id"] if isinstance(p, dict) else p.evidence_id) != gold_evidence_id
    ]

    if len(in_window) < n_needed:
        # Frozen fallback rule (documented for the methods section): if the
        # window is sparse, widen it in fixed +window_days increments rather
        # than silently falling back to a different selection strategy.
        widened = window_days
        while len(in_window) < n_needed and widened < window_days * 8:
            widened += window_days
            lo = gold_date - datetime.timedelta(days=widened)
            hi = gold_date + datetime.timedelta(days=widened)
            in_window = [
                p for p in all_passages
                if lo <= _passage_date(p) <= hi
                and (p["evidence_id"] if isinstance(p, dict) else p.evidence_id) != gold_evidence_id
            ]

    return rng.sample(in_window, min(n_needed, len(in_window)))


def build_pools(cfg: dict, sample: list[dict], by_evidence_id: dict, all_passages: list) -> list[dict]:
    import random
    rng = random.Random(cfg["sample"]["seed"])

    window_days = cfg["candidate_pool"]["window_days"]
    pool_size = cfg["candidate_pool"]["candidates_per_query"]

    records = []
    skipped = []
    for q in sample:
        gold_id = q["evidence_id"]
        gold_passage = by_evidence_id.get(gold_id)
        if gold_passage is None:
            # Gold evidence didn't survive dedup/extraction -- flag rather
            # than silently drop, since this shrinks the eval set below 100.
            skipped.append(q["question_id"])
            continue

        gold_date = _passage_date(gold_passage)
        n_distractors = pool_size - 1
        distractors = select_distractors(
            gold_id, gold_date, all_passages, window_days, n_distractors, rng
        )

        candidates = [
            {
                "doc_id": gold_id,
                "text": _passage_text(gold_passage),
                "timestamp": gold_date.isoformat(),
            }
        ] + [
            {
                "doc_id": (d["evidence_id"] if isinstance(d, dict) else d.evidence_id),
                "text": _passage_text(d),
                "timestamp": _passage_date(d).isoformat(),
            }
            for d in distractors
        ]
        rng.shuffle(candidates)  # gold position must not be predictable (e.g. always index 0)

        records.append({
            "query": q["question"],
            "gold_answer": q["answers"][0] if q["answers"] else None,
            "gold_aliases": q["answers"],
            "gold_doc_id": gold_id,  # kept for pool-building audits; not part of the shared shape
            "candidates": candidates,
        })

    if skipped:
        print(f"WARNING: {len(skipped)} questions had no gold evidence after "
              f"dedup/extraction, eval set is {len(records)}/100: {skipped}")

    return records


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    sample = load_sample(raw_dir)
    print(f"Loaded {len(sample)} sampled questions.")

    print("Deduplicating WMT docs against sorting-key list...")
    wmt_docs = build_deduped_docs(cfg, raw_dir)

    print("Extracting passages...")
    by_evidence_id, all_passages = build_passage_index(
        wmt_docs, prepend_date=cfg["candidate_pool"]["prepend_date"]
    )
    print(f"Indexed {len(all_passages)} passages.")

    print("Building candidate pools "
          f"(+/-{cfg['candidate_pool']['window_days']}d window, "
          f"{cfg['candidate_pool']['candidates_per_query']} candidates/query)...")
    records = build_pools(cfg, sample, by_evidence_id, all_passages)

    out_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} pools to {out_path}")