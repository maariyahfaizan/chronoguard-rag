"""
ChronoGuard-RAG -- StreamingQA stale-source extractor

Week 5 attack benchmark:
Find genuinely relevant older WMT passages that can be used as
stale-evidence attack sources.

Design:
    Question
        ↓
    Clean evidence / gold evidence as relevance anchor
        ↓
    Search older WMT passages
        ↓
    Require timestamp >= stale_days older than question
        ↓
    Require relevance to the question/evidence
        ↓
    Keep best N candidates per query

The script is:
- memory-safe
- year-by-year
- resumable
- checkpointed
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ATTACK_DIR = PROCESSED_DIR / "attack_sources"

QUESTIONS_PATH = RAW_DIR / "streamingqa_control_sample.jsonl"

OUTPUT_PATH = (
    ATTACK_DIR / "streamingqa_stale_sources_pilot.jsonl"
)

CHECKPOINT_PATH = (
    ATTACK_DIR / "streamingqa_stale_sources_pilot.checkpoint.json"
)


# ============================================================
# PILOT SETTINGS
# ============================================================

PILOT_QUERY_COUNT = 10

STALE_DAYS = 30

MAX_CANDIDATES_PER_QUERY = 5

# Minimum number of shared meaningful tokens.
MIN_QUERY_TOKEN_OVERLAP = 2

# We additionally compare against the clean evidence/topic.
MIN_EVIDENCE_TOKEN_OVERLAP = 2

# Keep only candidates with a reasonable relevance score.
MIN_RELEVANCE_SCORE = 2


# ============================================================
# WMT
# ============================================================

WMT_BASE_URL = (
    "https://data.statmt.org/news-crawl/doc/en/"
)

SORTING_KEY_URL = (
    "https://data.statmt.org/news-crawl/"
    "doc/en/news-docs.2011.en.filtered.gz"
)


# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "then",
    "than",
    "that",
    "this",
    "these",
    "those",
    "was",
    "were",
    "is",
    "are",
    "be",
    "been",
    "being",
    "to",
    "of",
    "in",
    "on",
    "for",
    "from",
    "with",
    "by",
    "at",
    "as",
    "into",
    "about",
    "after",
    "before",
    "during",
    "over",
    "under",
    "between",
    "through",
    "which",
    "who",
    "whom",
    "whose",
    "what",
    "when",
    "where",
    "why",
    "how",
    "did",
    "does",
    "do",
    "has",
    "have",
    "had",
    "will",
    "would",
    "could",
    "should",
    "can",
    "may",
    "might",
    "their",
    "there",
    "they",
    "them",
    "he",
    "she",
    "his",
    "her",
    "its",
    "it",
    "we",
    "our",
    "you",
    "your",
    "i",
    "me",
    "my",
    "not",
    "no",
    "yes",
    "also",
    "just",
    "more",
    "most",
    "some",
    "any",
    "all",
    "one",
    "two",
    "three",
}


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text: str) -> str:
    """
    Lowercase and keep simple alphanumeric tokens.
    """
    text = str(text or "").lower()

    text = re.sub(r"[^a-z0-9\s]", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def meaningful_tokens(text: str) -> set[str]:
    """
    Extract meaningful tokens from text.
    """
    tokens = normalize_text(text).split()

    return {
        token
        for token in tokens
        if len(token) >= 3
        and token not in STOPWORDS
    }


def token_overlap(
    left_tokens: set[str],
    right_tokens: set[str],
) -> int:
    """
    Number of shared meaningful tokens.
    """
    return len(left_tokens & right_tokens)


# ============================================================
# DATE HELPERS
# ============================================================

def parse_timestamp(value) -> Optional[float]:
    """
    Convert common timestamp formats to Unix timestamp.
    """
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Already numeric.
    try:
        return float(value)
    except ValueError:
        pass

    # Common ISO/date formats.
    from datetime import datetime, timezone

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.timestamp()

        except ValueError:
            continue

    return None


def days_difference(
    newer_timestamp: float,
    older_timestamp: float,
) -> float:
    """
    Return how many days older the second timestamp is.
    """
    return (newer_timestamp - older_timestamp) / 86400.0


# ============================================================
# QUESTION / EVIDENCE EXTRACTION
# ============================================================

def first_value(record: dict, keys: List[str]):
    """
    Return first non-empty value among candidate keys.
    """
    for key in keys:
        value = record.get(key)

        if value is not None and value != "":
            return value

    return None


def get_question_text(record: dict) -> str:
    return str(
        first_value(
            record,
            [
                "question",
                "query",
                "question_text",
                "query_text",
            ],
        )
        or ""
    )


def get_question_id(record: dict) -> str:
    return str(
        first_value(
            record,
            [
                "id",
                "question_id",
                "query_id",
                "uid",
            ],
        )
        or ""
    )


def get_question_timestamp(record: dict) -> Optional[float]:
    return parse_timestamp(
        first_value(
            record,
            [
                "question_ts",
                "query_ts",
                "timestamp",
                "question_timestamp",
            ],
        )
    )


def extract_clean_evidence_text(record: dict) -> str:
    """
    Try several known locations for the clean evidence text.

    If no evidence text exists, return an empty string.
    We do NOT invent evidence.
    """

    possible_keys = [
        "gold_text",
        "gold_passage",
        "gold_evidence",
        "evidence",
        "context",
        "answer_context",
        "supporting_passage",
    ]

    value = first_value(record, possible_keys)

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        for key in [
            "text",
            "passage",
            "content",
            "evidence",
        ]:
            if value.get(key):
                return str(value[key])

    if isinstance(value, list):
        pieces = []

        for item in value:
            if isinstance(item, str):
                pieces.append(item)

            elif isinstance(item, dict):
                for key in [
                    "text",
                    "passage",
                    "content",
                    "evidence",
                ]:
                    if item.get(key):
                        pieces.append(str(item[key]))
                        break

        return " ".join(pieces)

    # Some StreamingQA records keep passages/candidates.
    for key in [
        "candidates",
        "passages",
        "contexts",
        "documents",
    ]:
        value = record.get(key)

        if not isinstance(value, list):
            continue

        for item in value:
            if not isinstance(item, dict):
                continue

            is_gold = (
                item.get("is_gold")
                or item.get("gold")
                or item.get("is_answer")
                or item.get("answer_bearing")
            )

            if is_gold:
                text = first_value(
                    item,
                    [
                        "text",
                        "passage",
                        "content",
                        "evidence",
                    ],
                )

                if text:
                    return str(text)

    return ""


# ============================================================
# LOAD PILOT QUESTIONS
# ============================================================

def load_questions() -> List[dict]:
    """
    Load the frozen StreamingQA control sample.
    """
    if not QUESTIONS_PATH.exists():
        raise FileNotFoundError(
            f"Missing question file:\n{QUESTIONS_PATH}"
        )

    records = []

    with QUESTIONS_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:
            line = line.strip()

            if not line:
                continue

            records.append(json.loads(line))

    if len(records) < PILOT_QUERY_COUNT:
        raise RuntimeError(
            f"Expected at least {PILOT_QUERY_COUNT} questions, "
            f"found {len(records)}."
        )

    return records[:PILOT_QUERY_COUNT]


# ============================================================
# WMT DOWNLOAD
# ============================================================

def download_file(
    url: str,
    output_path: Path,
    attempts: int = 5,
) -> Path:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path

    last_error = None

    for attempt in range(1, attempts + 1):

        print(
            f"  downloading {url} "
            f"(attempt {attempt}/{attempts})",
            flush=True,
        )

        try:
            with requests.get(
                url,
                stream=True,
                timeout=120,
            ) as response:

                response.raise_for_status()

                tmp_path = output_path.with_suffix(
                    output_path.suffix + ".partial"
                )

                with tmp_path.open("wb") as out:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):
                        if chunk:
                            out.write(chunk)

                tmp_path.replace(output_path)

                return output_path

        except Exception as exc:
            last_error = exc

            print(
                f"  download failed: {exc}",
                flush=True,
            )

            time.sleep(5)

    raise RuntimeError(
        f"Could not download {url}: {last_error}"
    )


# ============================================================
# WMT SORTING KEY
# ============================================================

def load_sorting_key_years(
    years: List[int],
) -> Dict[str, str]:
    """
    Download/load WMT sorting-key data needed for the years.

    The exact WMT sorting-key format can differ across snapshots,
    so this parser intentionally accepts several common forms.
    """

    sorting_path = (
        RAW_DIR / "wmt_sorting_key_ids.txt.gz"
    )

    if not sorting_path.exists():
        raise FileNotFoundError(
            f"Missing WMT sorting-key file:\n{sorting_path}"
        )

    wanted = set(years)

    result = {}

    with gzip.open(
        sorting_path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            parts = line.split()

            if len(parts) < 2:
                continue

            # We try to find a YYYY token in the line.
            year = None

            for part in parts:
                match = re.search(
                    r"(20\d{2})",
                    part,
                )

                if match:
                    candidate_year = int(
                        match.group(1)
                    )

                    if candidate_year in wanted:
                        year = candidate_year
                        break

            if year is None:
                continue

            # First field is normally the document/sorting ID.
            doc_id = parts[0]

            result[doc_id] = str(year)

    return result


# ============================================================
# WMT STREAMING
# ============================================================

def stream_wmt_year(
    year: int,
) -> Iterable[Tuple[str, str]]:
    """
    Stream a WMT year without loading the whole archive.

    Yields:
        (document_id, document_text)
    """

    archive_path = (
        RAW_DIR
        / "wmt"
        / f"news-docs.{year}.en.filtered.gz"
    )

    if not archive_path.exists():

        url = (
            f"{WMT_BASE_URL}"
            f"news-docs.{year}.en.filtered.gz"
        )

        archive_path = download_file(
            url,
            archive_path,
        )

    print(
        f"  streaming {archive_path}",
        flush=True,
    )

    with gzip.open(
        archive_path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as f:

        doc_id = None
        buffer = []

        for line in f:

            line = line.rstrip("\n")

            # The WMT document files commonly use
            # document headers beginning with <doc.
            if line.startswith("<doc"):

                if doc_id is not None:
                    yield (
                        doc_id,
                        "\n".join(buffer),
                    )

                buffer = []

                match = re.search(
                    r'id="([^"]+)"',
                    line,
                )

                if match:
                    doc_id = match.group(1)
                else:
                    doc_id = line

                continue

            if line.startswith("</doc>"):

                if doc_id is not None:
                    yield (
                        doc_id,
                        "\n".join(buffer),
                    )

                doc_id = None
                buffer = []

                continue

            if doc_id is not None:
                buffer.append(line)

        if doc_id is not None:
            yield (
                doc_id,
                "\n".join(buffer),
            )


# ============================================================
# PASSAGE EXTRACTION
# ============================================================

def split_into_passages(
    document_text: str,
) -> Iterable[str]:
    """
    Split a WMT document into manageable text passages.

    We intentionally keep this simple and deterministic.
    """

    for paragraph in re.split(
        r"\n\s*\n+",
        document_text,
    ):

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        # Avoid tiny fragments.
        if len(paragraph) < 80:
            continue

        yield paragraph


# ============================================================
# RELEVANCE SCORING
# ============================================================

def relevance_score(
    question_tokens: set[str],
    evidence_tokens: set[str],
    passage_tokens: set[str],
) -> Tuple[int, int, int]:
    """
    Return:

        total_score,
        question_overlap,
        evidence_overlap

    Evidence overlap is weighted more heavily because it represents
    the topic/content of the clean answer-bearing source.
    """

    q_overlap = token_overlap(
        question_tokens,
        passage_tokens,
    )

    e_overlap = token_overlap(
        evidence_tokens,
        passage_tokens,
    )

    # Evidence overlap is more informative than raw question overlap.
    total = q_overlap + (2 * e_overlap)

    return (
        total,
        q_overlap,
        e_overlap,
    )


# ============================================================
# CANDIDATE MANAGEMENT
# ============================================================

def add_candidate(
    candidate_store: Dict[str, List[dict]],
    question_id: str,
    candidate: dict,
) -> bool:
    """
    Add candidate while keeping only the strongest candidates.
    """

    candidates = candidate_store.setdefault(
        question_id,
        [],
    )

    candidates.append(candidate)

    # Sort strongest first.
    candidates.sort(
        key=lambda x: (
            x["relevance_score"],
            x["evidence_overlap"],
            x["question_overlap"],
        ),
        reverse=True,
    )

    # Remove duplicate passage texts.
    unique = []

    seen = set()

    for item in candidates:

        key = normalize_text(
            item["text"]
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    candidates[:] = unique[
        :MAX_CANDIDATES_PER_QUERY
    ]

    return True


# ============================================================
# CHECKPOINT
# ============================================================

def write_checkpoint(
    questions: List[dict],
    candidate_store: Dict[str, List[dict]],
    completed_years: List[int],
    streamed_counts: Dict[str, int],
) -> None:

    ATTACK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "pilot_query_count": PILOT_QUERY_COUNT,
        "stale_days": STALE_DAYS,
        "max_candidates_per_query": (
            MAX_CANDIDATES_PER_QUERY
        ),
        "min_query_token_overlap": (
            MIN_QUERY_TOKEN_OVERLAP
        ),
        "min_evidence_token_overlap": (
            MIN_EVIDENCE_TOKEN_OVERLAP
        ),
        "min_relevance_score": (
            MIN_RELEVANCE_SCORE
        ),
        "question_ids": [
            get_question_id(q)
            for q in questions
        ],
        "completed_years": sorted(
            set(completed_years)
        ),
        "streamed_counts": streamed_counts,
        "candidate_store": candidate_store,
    }

    tmp_path = CHECKPOINT_PATH.with_suffix(
        CHECKPOINT_PATH.suffix + ".tmp"
    )

    with tmp_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    tmp_path.replace(
        CHECKPOINT_PATH
    )

    print(
        "  checkpoint saved",
        flush=True,
    )


def load_checkpoint() -> dict:

    if not CHECKPOINT_PATH.exists():
        return {
            "completed_years": [],
            "streamed_counts": {},
            "candidate_store": {},
        }

    with CHECKPOINT_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


# ============================================================
# FINAL OUTPUT
# ============================================================

def write_final_output(
    questions: List[dict],
    candidate_store: Dict[str, List[dict]],
) -> None:

    ATTACK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as f:

        for question in questions:

            qid = get_question_id(question)

            row = {
                "question_id": qid,
                "question": get_question_text(
                    question
                ),
                "question_ts": question.get(
                    "question_ts"
                ),
                "stale_days": STALE_DAYS,
                "candidates": candidate_store.get(
                    qid,
                    [],
                ),
            }

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

    print()
    print("=" * 70)
    print("FINAL OUTPUT WRITTEN")
    print("=" * 70)
    print(OUTPUT_PATH)

    total = sum(
        len(v)
        for v in candidate_store.values()
    )

    print(
        f"Total candidate passages: {total}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("ChronoGuard-RAG -- STALE SOURCE PILOT")
    print("=" * 70)

    print(
        f"Questions: {PILOT_QUERY_COUNT}"
    )

    print(
        f"Stale threshold: >= {STALE_DAYS} days"
    )

    print(
        f"Maximum candidates/query: "
        f"{MAX_CANDIDATES_PER_QUERY}"
    )

    print(
        f"Minimum question-token overlap: "
        f"{MIN_QUERY_TOKEN_OVERLAP}"
    )

    print(
        f"Minimum evidence-token overlap: "
        f"{MIN_EVIDENCE_TOKEN_OVERLAP}"
    )

    print(
        f"Minimum relevance score: "
        f"{MIN_RELEVANCE_SCORE}"
    )

    print(
        f"Output: {OUTPUT_PATH}"
    )

    print(
        f"Checkpoint: {CHECKPOINT_PATH}"
    )

    # --------------------------------------------------------
    # Load questions.
    # --------------------------------------------------------

    questions = load_questions()

    print()
    print(
        "Loaded pilot questions:"
    )

    for question in questions:

        qid = get_question_id(question)

        qts = get_question_timestamp(
            question
        )

        evidence = extract_clean_evidence_text(
            question
        )

        print(
            f"  {qid} | "
            f"question_ts={qts} | "
            f"evidence_chars={len(evidence)}"
        )

    # --------------------------------------------------------
    # Build query information.
    # --------------------------------------------------------

    query_info = {}

    for question in questions:

        qid = get_question_id(question)

        question_text = get_question_text(
            question
        )

        evidence_text = extract_clean_evidence_text(
            question
        )

        question_ts = get_question_timestamp(
            question
        )

        if question_ts is None:
            print(
                f"WARNING: {qid} has no question_ts; "
                f"it will be skipped."
            )

            continue

        question_tokens = meaningful_tokens(
            question_text
        )

        evidence_tokens = meaningful_tokens(
            evidence_text
        )

        query_info[qid] = {
            "question_text": question_text,
            "question_ts": question_ts,
            "question_tokens": question_tokens,
            "evidence_text": evidence_text,
            "evidence_tokens": evidence_tokens,
        }

    # --------------------------------------------------------
    # Determine years.
    #
    # IMPORTANT:
    # We use the existing question/evidence timestamps to
    # decide which years can possibly contain stale sources.
    # --------------------------------------------------------

    years = set()

    from datetime import datetime, timezone

    for info in query_info.values():

        question_date = datetime.fromtimestamp(
            info["question_ts"],
            tz=timezone.utc,
        )

        # Search years up to the year before the query.
        for year in range(
            2008,
            question_date.year,
        ):
            years.add(year)

    years = sorted(years)

    print()
    print(
        f"Years potentially needed: {years}"
    )

    # --------------------------------------------------------
    # Load checkpoint.
    # --------------------------------------------------------

    checkpoint = load_checkpoint()

    completed_years = set(
        checkpoint.get(
            "completed_years",
            [],
        )
    )

    streamed_counts = checkpoint.get(
        "streamed_counts",
        {},
    )

    candidate_store = checkpoint.get(
        "candidate_store",
        {},
    )

    print()
    print(
        f"Completed years from checkpoint: "
        f"{sorted(completed_years)}"
    )

    # --------------------------------------------------------
    # Process one year at a time.
    # --------------------------------------------------------

    for year in years:

        if year in completed_years:

            print()
            print(
                f"[{year}] already completed; "
                f"skipping"
            )

            continue

        print()
        print(
            f"[{year}] processing "
            f"(targeted relevance + "
            f"memory-safe streaming)..."
        )

        streamed = 0
        added = 0

        try:

            for doc_id, document_text in stream_wmt_year(
                year
            ):

                streamed += 1

                if streamed % 500_000 == 0:

                    print(
                        f"  streamed documents: "
                        f"{streamed:,}",
                        flush=True,
                    )

                # ------------------------------------------------
                # Evaluate each passage against the pilot questions.
                # ------------------------------------------------

                for passage in split_into_passages(
                    document_text
                ):

                    passage_tokens = meaningful_tokens(
                        passage
                    )

                    if not passage_tokens:
                        continue

                    # --------------------------------------------
                    # Check every query.
                    # --------------------------------------------

                    for qid, info in query_info.items():

                        # Already have enough strong candidates.
                        current = candidate_store.get(
                            qid,
                            [],
                        )

                        # We still allow stronger candidates to
                        # replace weaker ones, so do not blindly
                        # skip here.
                        #
                        # The cheap checks happen first.

                        q_overlap = token_overlap(
                            info["question_tokens"],
                            passage_tokens,
                        )

                        if (
                            q_overlap
                            < MIN_QUERY_TOKEN_OVERLAP
                        ):
                            continue

                        e_overlap = token_overlap(
                            info["evidence_tokens"],
                            passage_tokens,
                        )

                        # If clean evidence exists, require
                        # meaningful overlap with it.
                        if info["evidence_tokens"]:

                            if (
                                e_overlap
                                < MIN_EVIDENCE_TOKEN_OVERLAP
                            ):
                                continue

                        # ----------------------------------------
                        # Try to obtain a passage date.
                        #
                        # WMT document IDs sometimes contain dates.
                        # We deliberately do not invent a date when
                        # one cannot be recovered.
                        # ----------------------------------------

                        passage_timestamp = None

                        date_match = re.search(
                            r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})",
                            passage,
                        )

                        if date_match:

                            y = int(
                                date_match.group(1)
                            )

                            m = int(
                                date_match.group(2)
                            )

                            d = int(
                                date_match.group(3)
                            )

                            try:

                                from datetime import datetime, timezone

                                passage_timestamp = (
                                    datetime(
                                        y,
                                        m,
                                        d,
                                        tzinfo=timezone.utc,
                                    ).timestamp()
                                )

                            except ValueError:
                                passage_timestamp = None

                        # ----------------------------------------
                        # If passage itself has no date, use year
                        # as a conservative timestamp.
                        # ----------------------------------------

                        if passage_timestamp is None:

                            from datetime import datetime, timezone

                            try:

                                passage_timestamp = (
                                    datetime(
                                        year,
                                        1,
                                        1,
                                        tzinfo=timezone.utc,
                                    ).timestamp()
                                )

                            except ValueError:
                                continue

                        # ----------------------------------------
                        # Temporal requirement.
                        # ----------------------------------------

                        age_days = days_difference(
                            info["question_ts"],
                            passage_timestamp,
                        )

                        if age_days < STALE_DAYS:
                            continue

                        # ----------------------------------------
                        # Final relevance score.
                        # ----------------------------------------

                        score = (
                            q_overlap
                            + 2 * e_overlap
                        )

                        if score < MIN_RELEVANCE_SCORE:
                            continue

                        candidate = {
                            "source_year": year,
                            "doc_id": doc_id,
                            "text": passage,
                            "passage_timestamp": (
                                passage_timestamp
                            ),
                            "age_days": round(
                                age_days,
                                2,
                            ),
                            "question_overlap": (
                                q_overlap
                            ),
                            "evidence_overlap": (
                                e_overlap
                            ),
                            "relevance_score": score,
                        }

                        add_candidate(
                            candidate_store,
                            qid,
                            candidate,
                        )

                        added += 1

            # ----------------------------------------------------
            # Year complete.
            # ----------------------------------------------------

            completed_years.add(
                year
            )

            streamed_counts[
                str(year)
            ] = streamed

            print(
                f"[{year}] complete"
            )

            print(
                f"  streamed documents: "
                f"{streamed:,}"
            )

            print(
                f"  candidate additions: "
                f"{added}"
            )

            write_checkpoint(
                questions=questions,
                candidate_store=candidate_store,
                completed_years=list(
                    completed_years
                ),
                streamed_counts=streamed_counts,
            )

        except KeyboardInterrupt:

            print()
            print(
                "INTERRUPTED BY USER"
            )

            print(
                "The current year was NOT marked "
                "complete."
            )

            print(
                "The previous completed-year "
                "checkpoint is preserved."
            )

            raise

        except Exception as exc:

            print()
            print(
                f"[{year}] FAILED: {exc}"
            )

            print(
                "Saving checkpoint before stopping..."
            )

            write_checkpoint(
                questions=questions,
                candidate_store=candidate_store,
                completed_years=list(
                    completed_years
                ),
                streamed_counts=streamed_counts,
            )

            raise

    # --------------------------------------------------------
    # Final output.
    # --------------------------------------------------------

    print()
    print(
        "Candidate counts by question:"
    )

    for question in questions:

        qid = get_question_id(
            question
        )

        candidates = candidate_store.get(
            qid,
            [],
        )

        print(
            f"  {qid}: "
            f"{len(candidates)} candidates"
        )

    write_final_output(
        questions,
        candidate_store,
    )


if __name__ == "__main__":
    main()