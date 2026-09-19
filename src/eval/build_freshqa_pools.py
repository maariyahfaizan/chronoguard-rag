import argparse
import json
import os
import random
import re
import urllib.parse
from collections import defaultdict
from urllib.parse import urlparse


def load_jsonl(path):
    rows = []

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:

            line = line.strip()

            if line:
                rows.append(
                    json.loads(line)
                )

    return rows


def save_jsonl(rows, path):
    os.makedirs(
        os.path.dirname(path) or ".",
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        for row in rows:

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )


def normalize_url(url):
    if not url:
        return ""

    parsed = urlparse(
        str(url).strip()
    )

    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{parsed.path}"
        + (
            f"?{parsed.query}"
            if parsed.query
            else ""
        )
    ).rstrip("/")


def make_candidate_text(doc):
    title = (
        str(doc.get("title") or "")
        .strip()
    )

    text = (
        str(doc.get("text") or "")
        .strip()
    )

    if title:
        return (
            f"Title: {title}\n\n"
            f"{text}"
        )

    return text


def build_url_lookup(evidence_rows):
    lookup = defaultdict(list)

    for doc in evidence_rows:

        if (
            doc.get("fetch_status")
            != "success"
        ):
            continue

        if not doc.get("text"):
            continue

        normalized = normalize_url(
            doc.get("url")
        )

        if not normalized:
            continue

        lookup[normalized].append(doc)

    return lookup


def select_distractors(
    all_documents,
    positive_ids,
    number,
    rng,
):
    candidates = [
        doc
        for doc in all_documents
        if doc.get("doc_id")
        not in positive_ids
    ]

    if len(candidates) <= number:
        return candidates

    return rng.sample(
        candidates,
        number,
    )


# ---------------------------------------------------------------------------
# Text-fragment (#:~:text=...) handling -- 2e: extract the annotator's
# actually-cited span from the fetched page text, rather than keeping the
# whole page as the candidate. This is a simplified, non-spec-complete
# parser of the WICG Text Fragments directive
# (https://wicg.github.io/scroll-to-text-fragment/): it handles the common
# single-directive forms (`text=quote`, `text=prefix-,quote`,
# `text=quote,-suffix`, `text=start,end`) but not multiple &-joined
# directives. That's sufficient for FreshQA's citations, which are
# single Wikipedia/news links, not multi-highlight bundles.
# ---------------------------------------------------------------------------

def parse_text_fragment(url):
    """
    Extract the #:~:text= directive from a URL, if present. Returns a dict
    with keys prefix/text_start/text_end/suffix (any may be None), or None
    if the URL has no text-fragment directive at all.
    """
    if not url or "#:~:text=" not in url:
        return None

    frag = url.split("#:~:text=", 1)[1]
    # Only take the first directive if multiple are &-joined.
    frag = frag.split("&text=")[0]

    prefix = None
    suffix = None

    # Suffix marker: ",-something" at the end.
    if ",-" in frag:
        frag, suffix = frag.rsplit(",-", 1)

    # Prefix marker: "something-," at the start.
    if "-," in frag:
        maybe_prefix, rest = frag.split("-,", 1)
        if rest:
            prefix, frag = maybe_prefix, rest

    parts = frag.split(",", 1)
    text_start = parts[0] if parts else ""
    text_end = parts[1] if len(parts) > 1 else None

    def decode(s):
        if s is None:
            return None
        return urllib.parse.unquote(s).replace("+", " ").strip()

    return {
        "prefix": decode(prefix),
        "text_start": decode(text_start),
        "text_end": decode(text_end),
        "suffix": decode(suffix),
    }


def extract_cited_span(page_text, fragment, context_chars=400):
    """
    Locate the fragment's quoted span inside page_text via a normalized
    (whitespace-collapsed, lowercased), case-insensitive substring search --
    the Text Fragments spec itself does fuzzy matching, so a literal exact
    match would under-match real pages. Returns a window of context_chars
    on each side of the match (so the candidate keeps surrounding context,
    not just the bare quoted phrase), or None if text_start can't be found
    at all (page structure likely changed since the citation was made --
    expected sometimes per freshqa_report.md 2e, not a bug).

    NOTE: the returned span is a slice of the *normalized* (whitespace-
    collapsed, lowercased) text, not the original page_text -- remapping
    offsets back to the original would need a second alignment pass this
    doesn't implement. So fragment-extracted candidates are
    whitespace-normalized/lowercased while whole-page fallback candidates
    are not; flag this as a minor extraction-path inconsistency in the
    methodology writeup rather than assuming it away.
    """
    if not fragment or not fragment.get("text_start"):
        return None

    def normalize_ws(s):
        return re.sub(r"\s+", " ", s).strip().lower()

    norm_page = normalize_ws(page_text or "")
    start_needle = normalize_ws(fragment["text_start"])

    if not start_needle:
        return None

    start_pos = norm_page.find(start_needle)
    if start_pos == -1:
        return None

    end_needle = (
        normalize_ws(fragment["text_end"])
        if fragment.get("text_end")
        else None
    )
    if end_needle:
        end_pos = norm_page.find(
            end_needle, start_pos + len(start_needle)
        )
        span_end = (
            (end_pos + len(end_needle))
            if end_pos != -1
            else (start_pos + len(start_needle))
        )
    else:
        span_end = start_pos + len(start_needle)

    window_start = max(0, start_pos - context_chars)
    window_end = min(len(norm_page), span_end + context_chars)

    return norm_page[window_start:window_end]


def make_positive_candidate_text(doc, source_urls_for_doc, stats):
    """
    For a positive (cited-source) document: try each original source_url
    that matched this doc (preserving its #:~:text= fragment, if any) and
    return the extracted cited span the first time one succeeds. Falls
    back to the whole page (existing make_candidate_text) if no source_url
    had a fragment, or if fragment extraction failed for all of them --
    per the granularity decision, whole-page fallback beats dropping the
    candidate, so no_evidence_count doesn't inflate purely from fragment-
    parsing misses. `stats` is a dict this function increments in place
    (fragment_extracted / fragment_fallback / no_fragment) for the run
    summary.
    """
    title = str(doc.get("title") or "").strip()
    page_text = doc.get("text") or ""

    had_any_fragment = False

    for url in source_urls_for_doc or []:
        fragment = parse_text_fragment(url)
        if not fragment:
            continue
        had_any_fragment = True

        span = extract_cited_span(page_text, fragment)
        if span:
            stats["fragment_extracted"] += 1
            if title:
                return f"Title: {title}\n\n{span}"
            return span

    if had_any_fragment:
        stats["fragment_fallback"] += 1
    else:
        stats["no_fragment"] += 1

    return make_candidate_text(doc)


def compute_question_ts(selected_docs):
    """
    ASSUMPTION -- confirm against fetch_freshqa_sources.py: each evidence
    doc is expected to carry a `snapshot_retrieved_at` field, set when that
    URL was fetched. Per the query-time-reference decision (freshqa_report.md
    2d: use snapshot_retrieved_at), this returns the MAX
    snapshot_retrieved_at across all of this question's SELECTED candidate
    documents (positives + distractors, i.e. the full pool the retriever
    actually sees) -- the latest point by which the whole shown evidence
    pool is known to have existed. Returns None if no selected document
    carries the field, in which case is_time_valid() and the four temporal
    metrics correctly return None for this question (undefined, not a
    fabricated 0.0), matching metrics.py's None-vs-zero convention.

    If fetch_freshqa_sources.py instead stores one global snapshot
    timestamp (a single run-level fetch time, not per-document), that's
    simpler and this function should be replaced with just reading that
    one value -- can't confirm which without seeing that script.
    """
    timestamps = [
        doc.get("snapshot_retrieved_at")
        for doc in selected_docs
        if doc.get("snapshot_retrieved_at")
    ]
    return max(timestamps) if timestamps else None


def build_pools(
    questions,
    evidence,
    output_path,
    candidates_per_query=20,
    seed=42,
):
    rng = random.Random(seed)

    url_lookup = build_url_lookup(
        evidence
    )

    valid_documents = [
        doc
        for doc in evidence
        if (
            doc.get("fetch_status")
            == "success"
            and doc.get("text")
        )
    ]

    pools = []

    no_source_count = 0
    no_evidence_count = 0
    fragment_stats = {
        "fragment_extracted": 0,
        "fragment_fallback": 0,
        "no_fragment": 0,
    }
    no_question_ts_count = 0

    for question in questions:

        source_urls = question.get(
            "source_urls",
            [],
        )

        # Map each matched positive doc_id -> the original (unnormalized,
        # fragment-preserving) source_urls that led to it, so fragment
        # extraction (2e) has the actual cited URL to work with, not just
        # the normalized lookup key.
        doc_id_to_source_urls = defaultdict(list)
        positive_documents_by_id = {}

        for url in source_urls:
            norm = normalize_url(url)
            if not norm:
                continue
            for doc in url_lookup.get(norm, []):
                positive_documents_by_id[doc["doc_id"]] = doc
                doc_id_to_source_urls[doc["doc_id"]].append(url)

        positive_documents = list(
            positive_documents_by_id.values()
        )

        if not source_urls:
            no_source_count += 1

        if not positive_documents:
            no_evidence_count += 1
            continue

        # If a question has more source documents than the entire
        # candidate pool allows, select deterministically.
        if len(positive_documents) > candidates_per_query:

            positive_documents = rng.sample(
                positive_documents,
                candidates_per_query,
            )

        positive_ids = {
            doc["doc_id"]
            for doc in positive_documents
        }

        remaining = (
            candidates_per_query
            - len(positive_documents)
        )

        distractors = select_distractors(
            valid_documents,
            positive_ids,
            remaining,
            rng,
        )

        selected = (
            positive_documents
            + distractors
        )

        rng.shuffle(selected)

        # 2a: candidates are now list[{doc_id, text, timestamp}], the same
        # shape as StreamingQA -- not list[str] + a separate position-
        # aligned candidate_metadata list. is_source_document (2b) rides
        # along on each candidate dict rather than in a sidecar, so a
        # harness only needs one unpack step (same pattern as
        # run_baseline_streamingqa.py's raw_candidates -> parallel lists).
        candidates = []

        for doc in selected:
            is_source = doc.get("doc_id") in positive_ids

            if is_source:
                text = make_positive_candidate_text(
                    doc,
                    doc_id_to_source_urls.get(doc.get("doc_id")),
                    fragment_stats,
                )
            else:
                text = make_candidate_text(doc)

            candidates.append(
                {
                    "doc_id": doc.get("doc_id"),
                    "text": text,
                    "timestamp": doc.get("source_date"),
                    "is_source_document": is_source,
                    # Kept for audit/debugging only -- not read by any
                    # retrieval/eval code, which should only ever read
                    # doc_id/text/timestamp/is_source_document above.
                    "url": doc.get("url"),
                    "final_url": doc.get("final_url"),
                    "title": doc.get("title"),
                }
            )

        question_ts = compute_question_ts(selected)
        if question_ts is None:
            no_question_ts_count += 1

        pool = {
            "query_id": question[
                "query_id"
            ],

            "split": question.get(
                "split"
            ),

            "query": question[
                "query"
            ],

            "gold_answer": question[
                "gold_answer"
            ],

            "gold_aliases": question.get(
                "gold_aliases",
                [],
            ),

            "effective_year": question.get(
                "effective_year"
            ),

            "next_review": question.get(
                "next_review"
            ),

            "false_premise": question.get(
                "false_premise"
            ),

            "num_hops": question.get(
                "num_hops"
            ),

            "fact_type": question.get(
                "fact_type"
            ),

            "note": question.get(
                "note"
            ),

            "source_urls": source_urls,

            "question_ts": question_ts,

            "candidates": candidates,

            "pool_config": {
                "candidates_per_query":
                    candidates_per_query,
                "seed": seed,
                "query_time_reference": "snapshot_retrieved_at (max over selected docs)",
                "evidence_granularity": "cited_fragment_with_whole_page_fallback",
            },
        }

        pools.append(pool)

    save_jsonl(
        pools,
        output_path,
    )

    print()
    print("Candidate pools")
    print("----------------")
    print(
        f"Questions processed: {len(questions)}"
    )
    print(
        f"Pools created:       {len(pools)}"
    )
    print(
        f"No source URLs:      {no_source_count}"
    )
    print(
        f"No matched evidence: {no_evidence_count}"
    )
    print(
        f"No question_ts:      {no_question_ts_count}  "
        f"(temporal metrics will be None for these)"
    )
    print(
        f"Fragment extracted:  {fragment_stats['fragment_extracted']}"
    )
    print(
        f"Fragment fallback:   {fragment_stats['fragment_fallback']}  "
        f"(had a #:~:text= but span not found in fetched text)"
    )
    print(
        f"No fragment at all:  {fragment_stats['no_fragment']}"
    )
    print(
        f"Candidates/query:    {candidates_per_query}"
    )
    print(
        f"Seed:                {seed}"
    )
    print(
        f"Output:              {output_path}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description=(
            "Build frozen FreshQA "
            "retrieval candidate pools."
        )
    )

    parser.add_argument(
        "--questions",
        default=(
            "data/processed/"
            "freshqa_questions.jsonl"
        ),
    )

    parser.add_argument(
        "--evidence",
        default=(
            "data/raw/"
            "freshqa_evidence_snapshot.jsonl"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "data/processed/"
            "freshqa_control_pools.jsonl"
        ),
    )

    parser.add_argument(
        "--candidates-per-query",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    questions = load_jsonl(
        args.questions
    )

    evidence = load_jsonl(
        args.evidence
    )

    build_pools(
        questions=questions,
        evidence=evidence,
        output_path=args.output,
        candidates_per_query=(
            args.candidates_per_query
        ),
        seed=args.seed,
    )