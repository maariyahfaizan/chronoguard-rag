"""
Gate A-3 chunking verification.

A3 requires confirming chunking was actually uniform across all four
components (BM25/dense/hybrid/reranker/generator), not assumed from the
fact that chunk_streamingqa_pools.py ran without error. This script
checks that directly, using data already on disk -- no rerun needed.

METHOD:
For each of the four run logs, take every `retrieved_doc_ids` entry
(the doc_ids that specific driver's retriever/reranker actually selected
and handed to the generator) and cross-reference them against
streamingqa_control_pools_chunked.jsonl (the chunked candidate pool that
was the INPUT to that run). Three things are checked per retrieved doc_id:

  1. It carries the "#chunkN" suffix chunk_streamingqa_pools.py adds to
     every candidate (single-window passages included -- see that
     script's chunk_candidate(), which always emits at least #chunk0).
     A retrieved doc_id WITHOUT that suffix would mean this run somehow
     retrieved from the unchunked pool instead -- i.e. Gate A-2 silently
     did not apply to this run.
  2. Its chunk_token_count (recorded in the chunked pool file at
     chunking time) is <= TARGET_CHUNK_TOKENS. A chunk over target would
     mean the chunking itself malfunctioned for that passage.
  3. Its text length in CHARACTERS is <= MAX_PASSAGE_CHARS (1500, the
     cap generate.py's truncate_passage() applies before the generator
     sees the text, and that the evaluator reuses for relevance
     labeling). Chunks are sized in tokens, not characters, so nothing
     in the chunking step itself guarantees this -- if a chunk exceeds
     1500 chars, generate.py silently cuts it, and the generator sees
     less text than the retriever/reranker scored.

It ALSO reports the same two size checks (tokens, chars) across the
ENTIRE chunked pool, not just retrieved chunks, since a retrieved-only
check could miss oversized chunks that simply weren't selected in
these particular runs.

This does NOT re-measure tokens with each component's own tokenizer
(BM25 has none; Contriever's and the reranker's limits are both 512,
and chunks are already <=320 reranker-tokens) -- it verifies the things
that could actually have gone wrong silently: that A2's chunked file was
really what got consumed, end to end, and that every chunk stayed within
BOTH the token and character limits this was designed to respect.

Usage: run from repo root after all four E1-E4 runs have completed.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent  # adjust if placed elsewhere
CHUNKED_POOLS_PATH = REPO_ROOT / "data" / "processed" / "streamingqa_control_pools_chunked.jsonl"

TARGET_CHUNK_TOKENS = 320    # must match chunk_streamingqa_pools.py
MAX_PASSAGE_CHARS = 1500     # must match generate.py's DEFAULT_MAX_PASSAGE_CHARS

LOGS = {
    "E1 BM25":              "logs/streamingqa_baseline_run_chunked.jsonl",
    "E2 Dense":              "logs/streamingqa_dense_run_chunked.jsonl",
    "E3 Hybrid RRF":         "logs/streamingqa_hybrid_run_chunked.jsonl",
    "E4 Hybrid+Reranker":    "logs/streamingqa_hybrid_reranker_run_chunked.jsonl",
}


def load_chunk_sizes(path: Path) -> dict:
    """doc_id -> (chunk_token_count, char_length), from the chunked pool file."""
    lookup = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            for c in record["candidates"]:
                lookup[c["doc_id"]] = (c.get("chunk_token_count"), len(c["text"]))
    return lookup


def verify_whole_pool(chunk_lookup: dict) -> None:
    """Size checks over EVERY chunk in the pool, independent of what any
    run happened to retrieve."""
    tokens = [t for t, _ in chunk_lookup.values() if t is not None]
    chars = [c for _, c in chunk_lookup.values()]
    over_tokens = [d for d, (t, _) in chunk_lookup.items()
                   if t is not None and t > TARGET_CHUNK_TOKENS]
    over_chars = [d for d, (_, c) in chunk_lookup.items() if c > MAX_PASSAGE_CHARS]

    print("\nWhole chunked pool (every chunk, retrieved or not)")
    print(f"  chunks: {len(chunk_lookup)}")
    if tokens:
        print(f"  tokens per chunk: avg {sum(tokens)/len(tokens):.1f}, max {max(tokens)} "
              f"(target <= {TARGET_CHUNK_TOKENS})")
    print(f"  chars per chunk:  avg {sum(chars)/len(chars):.1f}, max {max(chars)} "
          f"(generate.py cap {MAX_PASSAGE_CHARS})")
    if over_tokens:
        print(f"  ⚠ {len(over_tokens)} chunks exceed {TARGET_CHUNK_TOKENS} tokens. "
              f"Examples: {over_tokens[:3]}")
    else:
        print(f"  ✓ no chunk exceeds {TARGET_CHUNK_TOKENS} tokens")
    if over_chars:
        print(f"  ⚠ {len(over_chars)} chunks exceed {MAX_PASSAGE_CHARS} chars -- "
              f"generate.py would silently cut these before the generator sees them. "
              f"Examples: {over_chars[:3]}")
    else:
        print(f"  ✓ no chunk exceeds {MAX_PASSAGE_CHARS} chars (generate.py never truncates a chunk)")


def verify_log(name: str, log_path: Path, chunk_lookup: dict) -> None:
    if not log_path.exists():
        print(f"\n{name}: SKIPPED -- {log_path} not found")
        return

    total_retrieved = 0
    missing_suffix = []
    over_tokens = []
    over_chars = []
    not_in_pool_file = []
    token_counts = []
    char_counts = []

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            for doc_id in rec.get("retrieved_doc_ids", []):
                total_retrieved += 1
                if "#chunk" not in doc_id:
                    missing_suffix.append(doc_id)
                    continue
                if doc_id not in chunk_lookup:
                    not_in_pool_file.append(doc_id)
                    continue
                tok, chars = chunk_lookup[doc_id]
                char_counts.append(chars)
                if chars > MAX_PASSAGE_CHARS:
                    over_chars.append((doc_id, chars))
                if tok is not None:
                    token_counts.append(tok)
                    if tok > TARGET_CHUNK_TOKENS:
                        over_tokens.append((doc_id, tok))

    print(f"\n{name}  ({log_path})")
    print(f"  retrieved doc_ids checked: {total_retrieved}")
    if missing_suffix:
        print(f"  ⚠ {len(missing_suffix)} retrieved doc_ids have NO #chunkN suffix "
              f"-- these did NOT come from the chunked pool. Examples: {missing_suffix[:3]}")
    else:
        print("  ✓ every retrieved doc_id carries a #chunkN suffix (chunked pool was used)")

    if not_in_pool_file:
        print(f"  ⚠ {len(not_in_pool_file)} retrieved doc_ids not found in "
              f"{CHUNKED_POOLS_PATH.name} at all -- can't verify their size. "
              f"Examples: {not_in_pool_file[:3]}")

    if token_counts:
        print(f"  retrieved chunk tokens: avg {sum(token_counts)/len(token_counts):.1f}, "
              f"max {max(token_counts)} (target <= {TARGET_CHUNK_TOKENS})")
    if char_counts:
        print(f"  retrieved chunk chars:  avg {sum(char_counts)/len(char_counts):.1f}, "
              f"max {max(char_counts)} (generate.py cap {MAX_PASSAGE_CHARS})")

    if over_tokens:
        print(f"  ⚠ {len(over_tokens)} retrieved chunks exceeded {TARGET_CHUNK_TOKENS} tokens. "
              f"Examples: {over_tokens[:3]}")
    elif token_counts:
        print(f"  ✓ no retrieved chunk exceeded {TARGET_CHUNK_TOKENS} tokens")

    if over_chars:
        print(f"  ⚠ {len(over_chars)} retrieved chunks exceeded {MAX_PASSAGE_CHARS} chars "
              f"-- generate.py cut these before generation. Examples: {over_chars[:3]}")
    elif char_counts:
        print(f"  ✓ no retrieved chunk exceeded {MAX_PASSAGE_CHARS} chars "
              f"(generator saw every retrieved chunk in full)")


if __name__ == "__main__":
    print(f"Loading chunk sizes from {CHUNKED_POOLS_PATH}")
    chunk_lookup = load_chunk_sizes(CHUNKED_POOLS_PATH)
    print(f"Indexed {len(chunk_lookup)} chunk doc_ids.")

    verify_whole_pool(chunk_lookup)

    for name, rel_path in LOGS.items():
        verify_log(name, REPO_ROOT / rel_path, chunk_lookup)

    print("\nDone. This is the Gate A-3 chunking-uniformity confirmation "
          "-- paste this output alongside the four run summaries in the "
          "Gate A completion note.")