"""
Weeks 3-4 | StreamingQA Step 2c: emit the final records that
src/retrieval/{bm25,dense,hybrid,reranker}.py and src/eval/evaluator.py
consume.

NOTE ON THIS REVISION (Gate A-1 schema fix):
build_streamingqa_pools.py no longer emits a single `gold_doc_id` field --
Gate A-1 replaced it with `gold_chunk_ids` (a LIST, since multiple chunks
of an article can legitimately be validated) and `gold_validated` (a
bool, distinguishing "at least one chunk lexically confirmed to contain
the answer" from "no chunk matched, an unvalidated fallback passage was
used instead"). Every candidate dict also now carries `is_source_document`
(True only for validated gold chunks). validate_record() and
emit_shared_shape() below are updated to match -- the old
`r["gold_doc_id"] not in {...}` check would KeyError immediately against
the new pool shape, since that field simply doesn't exist anymore.

NOTE ON PRIOR REVISION (temporal metrics support, unchanged):
The original version emitted exactly {query, gold_answer, gold_aliases,
candidates} -- the same shape as the TriviaQA control pools, on the
assumption that no downstream code needed anything else. That's no longer
true: the plan's Section 7 requires temporal-QA metrics (Time-Valid Answer
Accuracy, correctness conditioned on query date) and retrieval metrics
(valid-evidence Recall@k, fraction of top-k violating the query-time
constraint) that can't be computed without a "query time" reference point
to compare each candidate's timestamp against. That reference point is
question_ts, which existed in the raw sample all along but was being
silently dropped here. recent_or_past is also now kept, since Section 6's
"Evaluation slices" explicitly calls for a Recent vs historical breakdown,
and that field is the direct label for it.

Input:  data/raw/streamingqa_pools_raw.jsonl        (from build_streamingqa_pools.py)
Output: data/processed/streamingqa_control_pools.jsonl

Strips no audit fields anymore (gold_chunk_ids/gold_validated ARE part of
the shared downstream shape now, unlike the old gold_doc_id which was
audit-only) and validates every record before writing, so a malformed
pool fails loudly here rather than surfacing as a confusing retrieval-
stage bug later.
"""

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

REQUIRED_KEYS = {
    "query", "gold_answer", "gold_aliases", "candidates", "question_ts",
    "gold_chunk_ids", "gold_validated",
}
REQUIRED_CANDIDATE_KEYS = {"doc_id", "text", "timestamp", "is_source_document"}


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

    candidate_doc_ids = {c["doc_id"] for c in r["candidates"]}

    # gold_chunk_ids (validated OR the unvalidated single-element fallback,
    # see build_streamingqa_pools.py) must all actually be present among
    # this record's own candidates -- same spirit as the old gold_doc_id
    # check, just over a list instead of a single id.
    missing_gold = set(r["gold_chunk_ids"]) - candidate_doc_ids
    if missing_gold:
        problems.append(f"gold_chunk_ids not present among candidates: {missing_gold}")

    # Cross-check is_source_document against gold_validated: if the query
    # was validated, exactly the gold_chunk_ids should be flagged True and
    # nothing else; if unvalidated, NOTHING should be flagged True. A
    # mismatch here means build_streamingqa_pools.py and this validator
    # disagree about what "gold" means for this record -- worth catching
    # here rather than silently trusting whichever one happens to be read
    # downstream.
    flagged_true = {c["doc_id"] for c in r["candidates"] if c.get("is_source_document")}
    if r["gold_validated"]:
        if flagged_true != set(r["gold_chunk_ids"]):
            problems.append(
                f"gold_validated=True but is_source_document flags "
                f"({flagged_true}) don't match gold_chunk_ids "
                f"({set(r['gold_chunk_ids'])})"
            )
    else:
        if flagged_true:
            problems.append(
                f"gold_validated=False but {flagged_true} are still "
                f"flagged is_source_document=True"
            )

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
        "candidates": r["candidates"],  # already carries is_source_document per-candidate
        "question_ts": r["question_ts"],
        "gold_chunk_ids": r["gold_chunk_ids"],
        "gold_validated": r["gold_validated"],
        # recent_or_past is kept if present, but not required -- some
        # sample records may predate this field being populated upstream,
        # and losing the slice breakdown for a few records shouldn't block
        # the whole run the way a missing question_ts would.
        "recent_or_past": r.get("recent_or_past"),
    }


if __name__ == "__main__":
    cfg = load_config()
    in_path = REPO_ROOT / "data" / "raw" / "streamingqa_pools_raw.jsonl"
    out_path = REPO_ROOT / cfg["output"]["processed_path"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_written, n_flagged = 0, 0
    n_gold_validated = 0
    with open(in_path, "r", encoding="utf-8") as fin, open(out_path, "w", encoding="utf-8") as fout:
        for line in fin:
            r = json.loads(line)
            problems = validate_record(r, cfg)
            if problems:
                n_flagged += 1
                print(f"SKIPPING query {r.get('query', '?')!r}: {problems}")
                continue
            if r["gold_validated"]:
                n_gold_validated += 1
            fout.write(json.dumps(emit_shared_shape(r)) + "\n")
            n_written += 1

    print(f"Wrote {n_written} validated records to {out_path}")
    print(f"Of those, {n_gold_validated}/{n_written} have gold_validated=True "
          f"(a lexically-confirmed answer-bearing chunk) -- this is the "
          f"Gate A-1 before/after number to report, alongside "
          f"build_streamingqa_pools.py's own printed count (should match).")
    if n_flagged:
        print(f"WARNING: {n_flagged} records failed validation and were dropped "
              f"-- final eval set is {n_written}/100, not 100/100. Decide whether "
              f"that's acceptable for the paper or worth investigating before Step 3.")