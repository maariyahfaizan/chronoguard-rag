"""
Weeks 3-4 | StreamingQA Step 2b (revised again): build per-query candidate
pools from the gzip-sharded relevant-passages files produced by
fetch_wmt_archives.py, WITHOUT ever holding all ~49M passages' full text
in memory at once.

NOTE ON THIS REVISION (OOM + performance fix):
The previous version's load_relevant_passages() built a single Python list
of ALL 49.3M passage dicts (including full text) in memory -- almost
certainly tens of GB, which appears to have OOM-killed or hung the Kaggle
kernel (symptom: "IOStream.flush timed out" immediately after printing
just "Loaded 100 sampled questions", i.e. it never got past the load).
Separately, select_distractors() did a fresh O(n) list-comprehension scan
over all 49M passages EVERY time it was called (once per question, up to
8x each for the sparse-window widening fallback) -- up to ~800 full scans
of a 49M-element list, which would have been prohibitively slow even if
memory hadn't been a problem first.

NOTE ON THIS REVISION (gold-evidence ID mismatch fix):
Diagnostic output showed ALL 100/100 questions were being skipped for
"missing" gold evidence -- but every skip's evidence_id turned out to be
an EXACT PREFIX of some real doc_id, always missing exactly the trailing
"_0" suffix. Root cause: evidence_id in the sample is the article's
sorting_key (document-level), not a specific WMTPassage's id
(chunk-level, '{sorting_key}_{passage_idx}'). doc_id_to_dt was keyed by
full passage id, so an exact-match lookup against a bare sorting_key could
never hit. Fix: Pass 1 now ALSO builds sorting_key_to_gold, mapping each
article's sorting_key to its FIRST passage (lowest passage_idx, i.e. the
"_0" chunk) -- used as the canonical gold passage, since all of an
article's passages share the same publication date and the eval format
needs exactly one gold passage per question.

Fix: two passes instead of one.
  Pass 1 (load_passage_index): reads all shards but keeps only
    (timestamp, doc_id) pairs -- no text -- sorted by timestamp, PLUS a
    sorting_key -> (doc_id, dt) map to the first passage of each article
    (for gold resolution, see above). Window lookups use bisect
    (O(log n) + slice) instead of scanning all 49M entries per candidate.
  Pass 2 (fetch_texts): rereads the shards once more, but only keeps text
    for the small set of doc_ids actually selected across all 100
    questions (gold + distractors, typically ~2000 total) -- everything
    else is checked and discarded immediately, so full-corpus text never
    sits in memory at once.

Same gold/distractor selection semantics as before (+/-window_days,
sparse-window widening capped at 8x, shuffle so gold isn't predictably
first) -- only the implementation changed.

Input:  data/raw/streamingqa_relevant_passages/{year}.jsonl.gz  (from fetch_wmt_archives.py)
        data/raw/streamingqa_control_sample.jsonl               (from save_snapshot_streamingqa.py)
Output: data/raw/streamingqa_pools_raw.jsonl                    (feeds preprocess_streamingqa.py, unchanged)
"""

import bisect
import datetime
import gzip
import json
import random
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

_PASSAGE_ID_RE = re.compile(r'^(.*)_(\d+)$')


def _split_passage_id(doc_id: str) -> tuple[str, int]:
    """Splits a WMTPassage doc_id ('{sorting_key}_{passage_idx}') back into
    its parent article's sorting_key and this chunk's passage_idx. Mirrors
    the same regex used in fetch_wmt_archives.py's _extract_sorting_key --
    splits on the trailing digits only, since sorting_key itself may
    contain underscores.
    """
    match = _PASSAGE_ID_RE.match(doc_id)
    if not match:
        raise ValueError(f"Unexpected passage id format: {doc_id!r}")
    return match.group(1), int(match.group(2))


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sample(raw_dir: Path) -> list[dict]:
    sample_path = raw_dir / "streamingqa_control_sample.jsonl"
    with open(sample_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _shard_paths(raw_dir: Path) -> list[Path]:
    shards_dir = raw_dir / "streamingqa_relevant_passages"
    paths = sorted(shards_dir.glob("*.jsonl.gz"))
    if not paths:
        raise FileNotFoundError(
            f"No shards found in {shards_dir} -- run fetch_wmt_archives.py "
            f"first (this script reads its output, it doesn't create it)."
        )
    return paths


def load_passage_index(raw_dir: Path):
    """Pass 1: builds a lightweight (timestamp, doc_id) index across all
    shards WITHOUT holding passage text in memory -- the full-text version
    of this (49M dicts including text) is what appears to have exhausted
    memory previously. Also builds sorting_key_to_gold, mapping each
    article's sorting_key to its FIRST passage (lowest passage_idx) --
    used to resolve gold evidence, since evidence_id in the sample is a
    document-level sorting_key, not a specific passage id.

    Returns (sorted_dts, sorted_doc_ids, sorting_key_to_gold), the first
    two aligned/sorted ascending by timestamp so window queries can use
    bisect instead of an O(n) scan per candidate.
    """
    entries = []  # list of (datetime, doc_id)
    sorting_key_to_gold = {}  # sorting_key -> (passage_idx, doc_id, dt), kept at min passage_idx
    for shard_path in _shard_paths(raw_dir):
        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                doc_id = p["doc_id"]
                dt = datetime.datetime.fromisoformat(p["timestamp"])
                entries.append((dt, doc_id))

                sorting_key, passage_idx = _split_passage_id(doc_id)
                existing = sorting_key_to_gold.get(sorting_key)
                if existing is None or passage_idx < existing[0]:
                    sorting_key_to_gold[sorting_key] = (passage_idx, doc_id, dt)

    entries.sort(key=lambda e: e[0])
    sorted_dts = [e[0] for e in entries]
    sorted_doc_ids = [e[1] for e in entries]
    return sorted_dts, sorted_doc_ids, sorting_key_to_gold


def _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, exclude_doc_id) -> list:
    i = bisect.bisect_left(sorted_dts, lo)
    j = bisect.bisect_right(sorted_dts, hi)
    return [d for d in sorted_doc_ids[i:j] if d != exclude_doc_id]


def select_distractor_ids(
    gold_doc_id,
    gold_date: datetime.datetime,
    sorted_dts: list,
    sorted_doc_ids: list,
    window_days: int,
    n_needed: int,
    rng,
) -> list:
    widened = window_days
    lo = gold_date - datetime.timedelta(days=widened)
    hi = gold_date + datetime.timedelta(days=widened)
    candidates = _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, gold_doc_id)

    # Documented fallback: widen by +window_days increments, capped at 8x --
    # matches RETENTION_MARGIN_MULTIPLIER in fetch_wmt_archives.py, so the
    # data needed to satisfy this widening was actually retained.
    while len(candidates) < n_needed and widened < window_days * 8:
        widened += window_days
        lo = gold_date - datetime.timedelta(days=widened)
        hi = gold_date + datetime.timedelta(days=widened)
        candidates = _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, gold_doc_id)

    return rng.sample(candidates, min(n_needed, len(candidates)))


def build_pool_specs(cfg: dict, sample: list[dict], sorted_dts, sorted_doc_ids, sorting_key_to_gold) -> list[dict]:
    """Selection only -- produces doc_ids per query, no text yet."""
    rng = random.Random(cfg["sample"]["seed"])
    window_days = cfg["candidate_pool"]["window_days"]
    pool_size = cfg["candidate_pool"]["candidates_per_query"]

    specs = []
    skipped = []  # (qa_id, evidence_id, evidence_ts) for diagnosis
    for q in sample:
        # evidence_id is the article's sorting_key (document-level), not a
        # specific passage id -- resolved to that article's first passage
        # (lowest passage_idx) as the canonical gold text. See module
        # docstring for how this was diagnosed (100/100 questions were
        # failing an exact doc_id match before this fix).
        sorting_key = q["evidence_id"]
        gold_entry = sorting_key_to_gold.get(sorting_key)
        if gold_entry is None:
            # This time a genuinely missing article, not an ID-format
            # mismatch -- record for inspection, but don't expect many.
            skipped.append((q["qa_id"], sorting_key, q.get("evidence_ts")))
            continue

        _passage_idx, gold_id, gold_date = gold_entry

        n_distractors = pool_size - 1
        distractor_ids = select_distractor_ids(
            gold_id, gold_date, sorted_dts, sorted_doc_ids, window_days, n_distractors, rng
        )

        specs.append({
            "query": q["question"],
            "gold_answer": q["answers"][0] if q["answers"] else None,
            "gold_aliases": q["answers"],
            "gold_doc_id": gold_id,
            "candidate_ids": [gold_id] + distractor_ids,
        })

    if skipped:
        print(f"WARNING: {len(skipped)} questions had no gold article in the "
              f"relevant-passages shards at all (sorting_key not found, "
              f"not just an id-format mismatch), eval set is {len(specs)}/100:")
        for qa_id, sorting_key, evidence_ts in skipped:
            ts_str = (
                datetime.datetime.fromtimestamp(evidence_ts, tz=datetime.timezone.utc).isoformat()
                if evidence_ts is not None else "MISSING evidence_ts"
            )
            print(f"  qa_id={qa_id!r} evidence_id(sorting_key)={sorting_key!r} "
                  f"evidence_ts={ts_str}")

    return specs



def fetch_texts(raw_dir: Path, needed_ids: set) -> dict:
    """Pass 2: rereads the shards, but only KEEPS text for the small set of
    doc_ids actually selected across all queries (gold + distractors,
    typically ~2000 total, not 49M) -- everything else is discarded as
    soon as it's checked, so full-corpus text is never held in memory.
    """
    texts = {}
    remaining = set(needed_ids)
    for shard_path in _shard_paths(raw_dir):
        if not remaining:
            break
        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                doc_id = p["doc_id"]
                if doc_id in remaining:
                    texts[doc_id] = p
                    remaining.discard(doc_id)
                    if not remaining:
                        break

    if remaining:
        sample_missing = list(remaining)[:5]
        print(f"WARNING: {len(remaining)} selected doc_ids were not found on "
              f"the second pass (unexpected -- these came from the same "
              f"shards moments earlier): {sample_missing}")

    return texts


def assemble_records(pool_specs: list[dict], texts: dict, seed: int) -> list[dict]:
    rng = random.Random(seed)
    records = []
    for spec in pool_specs:
        candidates = []
        for doc_id in spec["candidate_ids"]:
            p = texts.get(doc_id)
            if p is None:
                continue  # see fetch_texts' WARNING if this ever fires
            candidates.append({
                "doc_id": doc_id,
                "text": p["text"],
                "timestamp": p["timestamp"],
            })
        rng.shuffle(candidates)

        records.append({
            "query": spec["query"],
            "gold_answer": spec["gold_answer"],
            "gold_aliases": spec["gold_aliases"],
            "gold_doc_id": spec["gold_doc_id"],
            "candidates": candidates,
        })
    return records


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    sample = load_sample(raw_dir)
    print(f"Loaded {len(sample)} sampled questions.")

    print("Pass 1/2: indexing passage timestamps across all shards "
          "(no text held in memory)...")
    sorted_dts, sorted_doc_ids, sorting_key_to_gold = load_passage_index(raw_dir)
    print(f"Indexed {len(sorted_dts)} passages.")

    print("Selecting candidate pools "
          f"(+/-{cfg['candidate_pool']['window_days']}d window, "
          f"{cfg['candidate_pool']['candidates_per_query']} candidates/query)...")
    pool_specs = build_pool_specs(cfg, sample, sorted_dts, sorted_doc_ids, sorting_key_to_gold)

    needed_ids = set()
    for spec in pool_specs:
        needed_ids.update(spec["candidate_ids"])
    print(f"Pass 2/2: fetching text for {len(needed_ids)} selected passages...")
    texts = fetch_texts(raw_dir, needed_ids)

    records = assemble_records(pool_specs, texts, cfg["sample"]["seed"])

    out_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} pools to {out_path}")