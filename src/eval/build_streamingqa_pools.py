"""
Weeks 3-4 | StreamingQA Step 2b (revised again): build per-query candidate
pools from the gzip-sharded relevant-passages files produced by
fetch_wmt_archives.py, WITHOUT ever holding all ~49M passages' full text
in memory at once.

NOTE ON THIS REVISION (gold-evidence CHUNK-LEVEL fix, per supervisor
Gate A-1):
Previous versions resolved evidence_id (an article-level sorting_key) to
that article's FIRST passage (P0) and used it as the canonical gold
chunk, unconditionally. This is not scientifically justified: an article
can have many passages (P0..Pn), and the actual answer-bearing text can
be in any of them, not necessarily P0. Using P0 by default means the
real evidence passage may never even be a candidate in the pool -- and
since evaluate_query() (in evaluator.py) determines relevance by
re-matching gold_answer/aliases against each CANDIDATE'S TEXT at eval
time, not from a stored flag, an absent-from-the-pool answer passage is
exactly why a query can come back with recall_at_5/ndcg_at_5 = None (no
candidate's text matches) even though a real answer-bearing passage
exists somewhere in the corpus -- it just was never given a chance to be
retrieved.

Fix: for each gold article, retrieve ALL its passages, lexically match
each one's text against gold_answer/gold_aliases (same normalized
token-subset test evaluator.py's get_relevance_labels() uses elsewhere,
imported directly so "how a chunk gets validated as gold" and "how
evaluate_query later scores relevance" can never silently disagree), and
mark every matching passage as a validated gold chunk. If MULTIPLE
passages match, ALL are included as candidates -- a single forced gold
chunk is not assumed. If NONE match lexically, the article's first
passage is still included as a candidate (for retrieval realism -- the
article's other passages remain the article-level context this question
was drawn from) but is explicitly marked unvalidated
(gold_validated=False, is_source_document=False on every one of that
question's candidates) rather than silently treated as gold by default.
This is a deliberate, documented choice, not a silent default: it means
such a question's recall_at_5/ndcg_at_5 will likely resolve to None,
correctly reporting "no validated relevant evidence was retrievable,"
which is the honest state per the None-vs-zero convention used
throughout metrics.py -- not something to force away by mislabeling a
passage as gold when it isn't confirmed to contain the answer.

This changes the shape of what's stored per query pool: candidates now
carry `is_source_document` (validated gold, or False), and each pool
record carries `gold_chunk_ids` (list, possibly empty) and
`gold_validated` (bool) at the query level, so before/after evidence
quality is auditable directly from the output file, per Gate A-1's
reporting requirement.

Gate A-1 explicitly scopes OUT the separate "freeze one evidence
chunking unit across BM25/Contriever/reranker/evaluator/generator" item
(Gate A-2 in the review) -- passage boundaries here are still whatever
fetch_wmt_archives.py's original WMTPassage segmentation produced, not a
new fixed-token-window rechunking. That's a distinct, larger change
(affects retrieval/generation/eval truncation consistency project-wide,
not just gold-evidence resolution) and is intentionally not bundled into
this fix.

NOTE ON PRIOR REVISION (OOM + performance fix, still in effect):
The previous version's load_relevant_passages() built a single Python
list of ALL 49.3M passage dicts (including full text) in memory --
almost certainly tens of GB, which appears to have OOM-killed or hung
the Kaggle kernel. Separately, select_distractors() did a fresh O(n)
list-comprehension scan over all 49M passages every time it was called,
up to ~800 full scans -- prohibitively slow even without the memory
problem. Both remain fixed via the two-pass design below: Pass 1 indexes
(timestamp, doc_id) only, using bisect for window queries; a full-text
fetch only ever happens for the specific doc_ids actually needed
(previously: pool candidates; now: also every passage of a gold article,
which is a small, bounded set -- ~100 articles' full passage lists, not
49M).

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
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

sys.path.append(str(REPO_ROOT))
try:
    # Reuse the EXACT SAME matching logic evaluate_query() uses downstream
    # to score relevance, so "how a chunk gets validated as gold here" and
    # "how it gets scored as relevant later" can never silently drift
    # apart into two different definitions of relevance.
    from src.eval.metrics import normalize_answer
except ImportError as e:
    raise ImportError(
        "Could not import normalize_answer from src.eval.metrics -- this "
        "script deliberately reuses the evaluator's own matching logic "
        "for gold-chunk validation rather than reimplementing a second, "
        "potentially-divergent version. Fix the import path rather than "
        "adding a local fallback implementation."
    ) from e

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


def load_passage_index(raw_dir: Path, gold_sorting_keys: set):
    """Pass 1: builds a lightweight (timestamp, doc_id) index across ALL
    shards WITHOUT holding passage text in memory (needed for the global
    distractor-window bisect queries, same as before).

    ALSO builds sorting_key_to_chunks: sorting_key -> list of
    (passage_idx, doc_id, dt), one entry per passage, sorted by
    passage_idx -- but ONLY for sorting_keys in gold_sorting_keys (the
    ~100 articles actually cited as evidence by this sample), not every
    article in the 49M-passage corpus. This keeps memory bounded the same
    way the original single-first-passage version did, while still
    capturing every chunk of the articles that actually matter for gold
    resolution.

    Returns (sorted_dts, sorted_doc_ids, sorting_key_to_chunks).
    """
    entries = []  # list of (datetime, doc_id), every passage, for the global window index
    sorting_key_to_chunks = {}  # only for gold_sorting_keys

    for shard_path in _shard_paths(raw_dir):
        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            for line in f:
                p = json.loads(line)
                doc_id = p["doc_id"]
                dt = datetime.datetime.fromisoformat(p["timestamp"])
                entries.append((dt, doc_id))

                sorting_key, passage_idx = _split_passage_id(doc_id)
                if sorting_key in gold_sorting_keys:
                    sorting_key_to_chunks.setdefault(sorting_key, []).append(
                        (passage_idx, doc_id, dt)
                    )

    entries.sort(key=lambda e: e[0])
    sorted_dts = [e[0] for e in entries]
    sorted_doc_ids = [e[1] for e in entries]

    for sorting_key in sorting_key_to_chunks:
        sorting_key_to_chunks[sorting_key].sort(key=lambda c: c[0])  # by passage_idx

    return sorted_dts, sorted_doc_ids, sorting_key_to_chunks


def _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, exclude_doc_ids: set) -> list:
    i = bisect.bisect_left(sorted_dts, lo)
    j = bisect.bisect_right(sorted_dts, hi)
    return [d for d in sorted_doc_ids[i:j] if d not in exclude_doc_ids]


def select_distractor_ids(
    exclude_doc_ids: set,
    gold_date: datetime.datetime,
    sorted_dts: list,
    sorted_doc_ids: list,
    window_days: int,
    n_needed: int,
    rng,
) -> list:
    """Same window-widening logic as before, except now excludes ALL of
    the gold article's chunk doc_ids (exclude_doc_ids), not just a single
    chosen one -- so a different passage from the SAME gold article can
    never accidentally get drawn as a "distractor" when it's really just
    more of the same on-topic evidence.
    """
    widened = window_days
    lo = gold_date - datetime.timedelta(days=widened)
    hi = gold_date + datetime.timedelta(days=widened)
    candidates = _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, exclude_doc_ids)

    while len(candidates) < n_needed and widened < window_days * 8:
        widened += window_days
        lo = gold_date - datetime.timedelta(days=widened)
        hi = gold_date + datetime.timedelta(days=widened)
        candidates = _window_doc_ids(sorted_dts, sorted_doc_ids, lo, hi, exclude_doc_ids)

    return rng.sample(candidates, min(n_needed, len(candidates)))


def find_validated_gold_chunks(chunks: list, texts: dict, gold_answer, gold_aliases) -> list:
    """Lexically matches each of an article's chunks (passage_idx, doc_id,
    dt) against gold_answer/gold_aliases using the SAME normalized
    token-subset test evaluate_query() uses for relevance labeling
    elsewhere (imported from metrics.py, not reimplemented) -- so gold
    validation here and relevance scoring later are guaranteed to agree
    on what counts as a match.

    Returns the list of (passage_idx, doc_id, dt) tuples whose text
    matched -- may be empty (no chunk validated), may contain more than
    one (multiple chunks legitimately support the answer -- per Gate A-1,
    "do not force a single gold chunk when multiple chunks legitimately
    support the answer").
    """
    gold_list = [gold_answer] + list(gold_aliases or [])
    gold_token_sets = [set(normalize_answer(g).split()) for g in gold_list if g]
    gold_token_sets = [g for g in gold_token_sets if g]
    if not gold_token_sets:
        return []

    matched = []
    for passage_idx, doc_id, dt in chunks:
        p = texts.get(doc_id)
        if p is None:
            continue  # text fetch miss -- see fetch_texts' own WARNING
        cand_tokens = set(normalize_answer(p["text"]).split())
        if any(g.issubset(cand_tokens) for g in gold_token_sets):
            matched.append((passage_idx, doc_id, dt))

    return matched


def build_pool_specs(cfg: dict, sample: list[dict], sorted_dts, sorted_doc_ids,
                      sorting_key_to_chunks: dict, gold_texts: dict) -> list[dict]:
    """Selection only -- produces doc_ids per query, no candidate text
    assembly yet (that's assemble_records, which reuses gold_texts plus a
    second fetch for distractors).
    """
    rng = random.Random(cfg["sample"]["seed"])
    window_days = cfg["candidate_pool"]["window_days"]
    pool_size = cfg["candidate_pool"]["candidates_per_query"]

    specs = []
    skipped = []  # articles with no chunks found at all
    n_validated = 0
    n_unvalidated = 0
    n_capped = 0  # articles with MORE validated chunks than pool_size-1 allows

    for q in sample:
        sorting_key = q["evidence_id"]
        chunks = sorting_key_to_chunks.get(sorting_key)
        if not chunks:
            skipped.append((q["qa_id"], sorting_key, q.get("evidence_ts")))
            continue

        gold_answer = q["answers"][0] if q["answers"] else None
        gold_aliases = q["answers"]

        validated = find_validated_gold_chunks(chunks, gold_texts, gold_answer, gold_aliases)

        if validated:
            n_validated += 1
            if len(validated) > pool_size - 1:
                # Documented, deliberate cap -- keep in passage_idx order
                # (earliest chunks first) rather than dropping evidence
                # silently or letting pool size balloon unboundedly.
                validated = validated[: pool_size - 1]
                n_capped += 1
            gold_chunk_entries = validated
            gold_validated = True
        else:
            n_unvalidated += 1
            # Fallback: first passage, included for retrieval realism,
            # explicitly NOT marked as validated gold. See module
            # docstring for why this isn't "assigning P0 by default" in
            # the sense the review prohibits -- it's included as an
            # ordinary, unlabeled candidate, not as gold.
            gold_chunk_entries = [chunks[0]]
            gold_validated = False

        gold_date = gold_chunk_entries[0][2]  # all chunks of one article share a date
        exclude_ids = {doc_id for _, doc_id, _ in chunks}  # exclude the WHOLE article, not just chosen chunks
        n_distractors = pool_size - len(gold_chunk_entries)

        distractor_ids = select_distractor_ids(
            exclude_ids, gold_date, sorted_dts, sorted_doc_ids, window_days, n_distractors, rng
        )

        specs.append({
            "query": q["question"],
            "gold_answer": gold_answer,
            "gold_aliases": gold_aliases,
            "sorting_key": sorting_key,
            "gold_chunk_ids": [doc_id for _, doc_id, _ in gold_chunk_entries],
            "gold_validated": gold_validated,
            "candidate_ids": [doc_id for _, doc_id, _ in gold_chunk_entries] + distractor_ids,
            "n_gold_candidates": len(gold_chunk_entries),
            "question_ts": q["question_ts"],
            "recent_or_past": q.get("recent_or_past"),
        })

    if skipped:
        print(f"WARNING: {len(skipped)} questions had no gold article in the "
              f"relevant-passages shards at all (sorting_key not found), "
              f"eval set is {len(specs)}/{len(sample)}:")
        for qa_id, sorting_key, evidence_ts in skipped:
            ts_str = (
                datetime.datetime.fromtimestamp(evidence_ts, tz=datetime.timezone.utc).isoformat()
                if evidence_ts is not None else "MISSING evidence_ts"
            )
            print(f"  qa_id={qa_id!r} evidence_id(sorting_key)={sorting_key!r} "
                  f"evidence_ts={ts_str}")

    print()
    print("Gold-evidence validation (Gate A-1)")
    print("------------------------------------")
    print(f"Queries with >=1 validated gold chunk: {n_validated}/{len(specs)}")
    print(f"Queries with NO validated gold chunk (article-level only, "
          f"unvalidated fallback used): {n_unvalidated}/{len(specs)}")
    if n_capped:
        print(f"Queries where validated chunks exceeded pool capacity and "
              f"were capped: {n_capped} (kept earliest {pool_size - 1} by "
              f"passage_idx)")

    return specs


def fetch_texts(raw_dir: Path, needed_ids: set) -> dict:
    """Rereads the shards, keeping text only for the requested doc_ids.
    Used twice: once (small) for every chunk of every gold article, and
    once (larger) for the final selected candidate set (gold + distractors)
    in the main flow below.
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
        print(f"WARNING: {len(remaining)} requested doc_ids were not found "
              f"on this pass: {sample_missing}")

    return texts


def assemble_records(pool_specs: list[dict], texts: dict, seed: int) -> list[dict]:
    rng = random.Random(seed)
    records = []
    for spec in pool_specs:
        gold_set = set(spec["gold_chunk_ids"]) if spec["gold_validated"] else set()

        candidates = []
        for doc_id in spec["candidate_ids"]:
            p = texts.get(doc_id)
            if p is None:
                continue  # see fetch_texts' WARNING if this ever fires
            candidates.append({
                "doc_id": doc_id,
                "text": p["text"],
                "timestamp": p["timestamp"],
                "is_source_document": doc_id in gold_set,
            })
        rng.shuffle(candidates)

        records.append({
            "query": spec["query"],
            "gold_answer": spec["gold_answer"],
            "gold_aliases": spec["gold_aliases"],
            "sorting_key": spec["sorting_key"],
            "gold_chunk_ids": spec["gold_chunk_ids"],
            "gold_validated": spec["gold_validated"],
            "candidates": candidates,
            "question_ts": spec["question_ts"],
            "recent_or_past": spec["recent_or_past"],
        })
    return records


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    sample = load_sample(raw_dir)
    print(f"Loaded {len(sample)} sampled questions.")
    gold_sorting_keys = {q["evidence_id"] for q in sample}

    print("Pass 1: indexing passage timestamps across all shards, plus "
          f"every chunk of this sample's {len(gold_sorting_keys)} gold "
          "articles (no other text held in memory)...")
    sorted_dts, sorted_doc_ids, sorting_key_to_chunks = load_passage_index(
        raw_dir, gold_sorting_keys
    )
    print(f"Indexed {len(sorted_dts)} passages globally; found chunk lists "
          f"for {len(sorting_key_to_chunks)}/{len(gold_sorting_keys)} gold articles.")

    all_gold_chunk_ids = {
        doc_id
        for chunks in sorting_key_to_chunks.values()
        for _, doc_id, _ in chunks
    }
    print(f"Pass 2: fetching text for all {len(all_gold_chunk_ids)} gold-article "
          f"chunks (to validate which chunk(s) actually contain the answer)...")
    gold_texts = fetch_texts(raw_dir, all_gold_chunk_ids)

    print("Selecting candidate pools "
          f"(+/-{cfg['candidate_pool']['window_days']}d window, "
          f"{cfg['candidate_pool']['candidates_per_query']} candidates/query)...")
    pool_specs = build_pool_specs(
        cfg, sample, sorted_dts, sorted_doc_ids, sorting_key_to_chunks, gold_texts
    )

    needed_ids = set()
    for spec in pool_specs:
        needed_ids.update(spec["candidate_ids"])
    # Gold chunks' text is already in gold_texts -- only fetch what's new
    # (the distractors) on this pass.
    still_needed = needed_ids - set(gold_texts.keys())
    print(f"Pass 3: fetching text for {len(still_needed)} additional "
          f"(distractor) passages...")
    distractor_texts = fetch_texts(raw_dir, still_needed)
    all_texts = {**gold_texts, **distractor_texts}

    records = assemble_records(pool_specs, all_texts, cfg["sample"]["seed"])

    out_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(records)} pools to {out_path}")