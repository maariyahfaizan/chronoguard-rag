"""
Weeks 3-4 | StreamingQA Step 2d (Gate A-2): rechunk candidate passages into
a single fixed token-window size, shared across BM25/Contriever/reranker/
generator, so all four components see the same text instead of silently
disagreeing about where a passage gets cut off.

WHY THIS EXISTS (confirmed directly against current source, not assumed):
  - bm25.py            -- no truncation at all (whitespace-split, full text)
  - dense.py            -- truncation=True, no max_length override, so it
                            silently truncates at Contriever's tokenizer
                            default (512 tokens, BERT-based)
  - reranker.py          -- CrossEncoder truncates at bge-reranker-base's
                            default too, but that budget is SHARED between
                            query + passage together, not passage alone
  - generate.py           -- truncates at 1500 CHARACTERS (not tokens),
                            via DEFAULT_MAX_PASSAGE_CHARS, and the same
                            1500-char rule is reused for relevance
                            labeling in the evaluator

Four different truncation rules, three different units (untruncated,
tokens-alone, tokens-shared, characters). A passage that looks complete
to BM25 can be silently cut off by the time it reaches the reranker or
the generator, and generation may see MORE or LESS of a passage than
whatever the retriever actually scored -- Gate A-2 is the tracked fix
for exactly this, per the inline notes already left in
run_dense_streamingqa.py and run_hybrid_reranker_streamingqa.py.

SCOPE (per prior agreement, not re-litigated here):
This is a NEW step inside StreamingQA's own pipeline only. bm25.py,
dense.py, hybrid.py, reranker.py, generate.py are NOT edited -- TriviaQA
and FreshQA, which import those same shared modules with zero
per-dataset branching, see zero behavioral change. This file reads
StreamingQA's own pool output and writes a new StreamingQA-only file;
nothing else in the repo is touched.

TOKENIZER CHOICE (documented, deliberate -- not yet confirmed by
supervisor, flag alongside the Gate A completion note per project
convention):
Chunk boundaries are measured using the RERANKER's tokenizer
(BAAI/bge-reranker-base), not Contriever's and not a character count.
This is deliberate: the reranker has the TIGHTEST effective budget of
the four components (512 tokens shared between query + passage, not
passage alone), so sizing chunks against it is the binding constraint --
a chunk that fits the reranker's budget is guaranteed to also fit
comfortably under Contriever's passage-only 512-token limit and under
generate.py's 1500-character limit (see the ~4 chars/token sanity check
printed at the end of this script). Sizing against Contriever's tokenizer
instead would NOT have this property, since the reranker's shared
query+passage budget is stricter per passage.

CHUNK SIZE: target 320 tokens (middle of the requested 256-384 token
range), 64-token overlap between consecutive chunks of the SAME original
passage (so an answer sitting at a chunk boundary isn't split across two
chunks with zero shared context). A trailing fragment shorter than
MIN_CHUNK_TOKENS is merged into the previous chunk rather than emitted
as its own near-empty candidate.

POOL SIZE DECISION (documented assumption, per user instruction):
Pool size is kept in ORIGINAL-PASSAGE terms, not chunk terms. Gate A-1's
pool of `candidates_per_query` (20) original passages is chunked in
full, and the resulting pool naturally grows past 20 once passages
become multiple chunks -- it is NOT capped back down to 20 chunks. This
keeps every one of A1's validated gold passages intact (no gold text is
ever dropped to make room under a chunk-count cap) at the cost of
downstream retrieval seeing a larger, variable-size candidate pool per
query. This tradeoff is a documented, revisitable choice, not a silent
default -- flag it in the same note as the tokenizer choice above.

Input:  data/processed/streamingqa_control_pools.jsonl   (from preprocess_streamingqa.py)
Output: data/processed/streamingqa_control_pools_chunked.jsonl
        (this is what the E1-E4 drivers should point INPUT_PATH at, once
        this step is adopted -- they are NOT repointed automatically by
        this script; that's a one-line change in each driver, left for
        the user to make deliberately rather than silently redirected)
"""

import json
from pathlib import Path

from transformers import AutoTokenizer

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/eval -> src -> repo root

IN_PATH = REPO_ROOT / "data" / "processed" / "streamingqa_control_pools.jsonl"
OUT_PATH = REPO_ROOT / "data" / "processed" / "streamingqa_control_pools_chunked.jsonl"

# Authoritative tokenizer for chunk-boundary sizing -- see module
# docstring for why this one (tightest effective budget of the four
# downstream consumers), not Contriever's tokenizer and not char count.
CHUNK_TOKENIZER_NAME = "BAAI/bge-reranker-base"

TARGET_CHUNK_TOKENS = 320      # middle of the requested 256-384 range
OVERLAP_TOKENS = 64            # shared context between consecutive chunks
MIN_CHUNK_TOKENS = 64          # trailing fragments below this get merged
                                # into the previous chunk instead of being
                                # emitted as their own near-empty candidate

assert OVERLAP_TOKENS < TARGET_CHUNK_TOKENS, (
    "overlap must be smaller than the chunk size or the chunking loop "
    "never advances"
)


def load_pools(in_path: Path = IN_PATH) -> list[dict]:
    with open(in_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def chunk_token_ids(token_ids: list[int], target: int, overlap: int, min_tail: int) -> list[list[int]]:
    """Splits one passage's token ids into overlapping fixed-size windows.

    A passage shorter than `target` is returned as a single unsplit
    chunk -- there's nothing to gain from padding or forcing a split on
    text that already fits. A final trailing window shorter than
    `min_tail` is merged into the previous window rather than kept as
    its own tiny, low-context candidate.
    """
    n = len(token_ids)
    if n <= target:
        return [token_ids]

    windows = []
    start = 0
    while start < n:
        end = min(start + target, n)
        windows.append(token_ids[start:end])
        if end == n:
            break
        start = end - overlap

    # Merge a too-short trailing window into the one before it, rather
    # than emit a near-empty final chunk.
    if len(windows) > 1 and len(windows[-1]) < min_tail:
        tail = windows.pop()
        # Extend the previous window with whatever new token ids the
        # tail contributed beyond where it already overlapped.
        prev = windows[-1]
        new_tail_len = len(tail) - overlap if len(tail) > overlap else len(tail)
        windows[-1] = prev + tail[len(tail) - new_tail_len:] if new_tail_len > 0 else prev

    return windows


def chunk_candidate(candidate: dict, tokenizer, target: int, overlap: int, min_tail: int) -> list[dict]:
    """Expands one candidate dict into one or more chunk-candidate dicts.

    Every chunk of a candidate inherits that candidate's timestamp and
    is_source_document flag unchanged -- a chunk of a validated gold
    passage is still gold evidence; a chunk of a distractor is still a
    distractor. doc_id gets a `#chunkN` suffix so chunks remain
    individually addressable and never collide with the parent doc_id or
    with each other.
    """
    token_ids = tokenizer.encode(candidate["text"], add_special_tokens=False)
    windows = chunk_token_ids(token_ids, target, overlap, min_tail)

    chunks = []
    for i, window in enumerate(windows):
        text = tokenizer.decode(window, skip_special_tokens=True)
        chunks.append({
            "doc_id": f"{candidate['doc_id']}#chunk{i}",
            "text": text,
            "timestamp": candidate["timestamp"],
            "is_source_document": candidate["is_source_document"],
            "parent_doc_id": candidate["doc_id"],  # audit trail back to the
                                                     # original un-chunked
                                                     # passage
            "chunk_token_count": len(window),
        })
    return chunks


def chunk_record(record: dict, tokenizer, target: int, overlap: int, min_tail: int) -> dict:
    new_candidates = []
    for candidate in record["candidates"]:
        new_candidates.extend(
            chunk_candidate(candidate, tokenizer, target, overlap, min_tail)
        )

    # gold_chunk_ids is now expressed in chunk-doc_id terms (every chunk
    # derived from an originally-gold passage), not the original
    # passage-level doc_ids -- so it stays consistent with what
    # is_source_document actually flags True on THIS record's candidates.
    new_gold_chunk_ids = [
        c["doc_id"] for c in new_candidates if c["is_source_document"]
    ]

    out = dict(record)
    out["candidates"] = new_candidates
    out["gold_chunk_ids"] = new_gold_chunk_ids
    out["n_candidates_pre_chunk"] = len(record["candidates"])
    out["n_candidates_post_chunk"] = len(new_candidates)
    return out


if __name__ == "__main__":
    print(f"Loading chunk-boundary tokenizer: {CHUNK_TOKENIZER_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(CHUNK_TOKENIZER_NAME)

    records = load_pools()
    print(f"Loaded {len(records)} pool records from {IN_PATH}")

    chunked_records = []
    total_pre, total_post = 0, 0
    all_chunk_token_counts = []

    for record in records:
        out = chunk_record(record, tokenizer, TARGET_CHUNK_TOKENS, OVERLAP_TOKENS, MIN_CHUNK_TOKENS)
        chunked_records.append(out)
        total_pre += out["n_candidates_pre_chunk"]
        total_post += out["n_candidates_post_chunk"]
        all_chunk_token_counts.extend(c["chunk_token_count"] for c in out["candidates"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for r in chunked_records:
            f.write(json.dumps(r) + "\n")

    avg_pre = total_pre / len(records) if records else 0
    avg_post = total_post / len(records) if records else 0
    avg_chunk_tokens = (
        sum(all_chunk_token_counts) / len(all_chunk_token_counts)
        if all_chunk_token_counts else 0
    )
    max_chunk_tokens = max(all_chunk_token_counts) if all_chunk_token_counts else 0

    print()
    print("Chunking summary (Gate A-2)")
    print("----------------------------")
    print(f"Records: {len(records)}")
    print(f"Candidates per query, pre-chunk:  avg {avg_pre:.1f} (pool size before chunking)")
    print(f"Candidates per query, post-chunk: avg {avg_post:.1f} (pool size after chunking -- "
          f"NOT capped back down, per the documented pool-size decision above)")
    print(f"Chunk size: avg {avg_chunk_tokens:.1f} tokens, max {max_chunk_tokens} tokens "
          f"(target {TARGET_CHUNK_TOKENS}, measured with {CHUNK_TOKENIZER_NAME}'s tokenizer)")
    print(f"Wrote {len(chunked_records)} chunked records to {OUT_PATH}")
    print()
    print("NOTE: E1-E4 driver INPUT_PATH constants still point at "
          "streamingqa_control_pools.jsonl (unchunked). Repointing them "
          "at streamingqa_control_pools_chunked.jsonl is a deliberate "
          "one-line change left for the user to make per driver, not "
          "done automatically here.")