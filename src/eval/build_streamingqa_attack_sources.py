"""
ChronoGuard-RAG -- StreamingQA stale-source pilot

Week 5:
Find older, topically relevant WMT passages that can serve as
stale-evidence attack sources.

Important:
- Uses the frozen StreamingQA question sample.
- Uses the existing processed clean pools as the evidence/topic anchor.
- Keeps the existing WMT year-by-year, memory-safe approach.
- Searches only years that can actually be stale for the pilot.
- Resumes from checkpoint.
"""

from __future__ import annotations

import gzip
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ATTACK_DIR = PROCESSED_DIR / "attack_sources"

QUESTIONS_PATH = (
    RAW_DIR / "streamingqa_control_sample.jsonl"
)

CLEAN_POOLS_PATH = (
    PROCESSED_DIR / "streamingqa_control_pools_chunked.jsonl"
)

OUTPUT_PATH = (
    ATTACK_DIR
    / "streamingqa_stale_sources_pilot.jsonl"
)

CHECKPOINT_PATH = (
    ATTACK_DIR
    / "streamingqa_stale_sources_pilot.checkpoint.json"
)


# ============================================================
# PILOT SETTINGS
# ============================================================

PILOT_QUERY_COUNT = 10

STALE_DAYS = 30

MAX_CANDIDATES_PER_QUERY = 5

MIN_QUERY_TOKEN_OVERLAP = 2

MIN_EVIDENCE_TOKEN_OVERLAP = 1

MIN_RELEVANCE_SCORE = 3


# ============================================================
# WMT
# ============================================================

WMT_BASE_URL = (
    "https://data.statmt.org/news-crawl/doc/en/"
)

WMT_DIR = RAW_DIR / "wmt"


# ============================================================
# STOPWORDS
# ============================================================

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if",
    "then", "than", "that", "this", "these", "those",
    "was", "were", "is", "are", "be", "been",
    "being", "to", "of", "in", "on", "for", "from",
    "with", "by", "at", "as", "into", "about",
    "after", "before", "during", "over", "under",
    "between", "through", "which", "who", "whom",
    "whose", "what", "when", "where", "why", "how",
    "did", "does", "do", "has", "have", "had",
    "will", "would", "could", "should", "can",
    "may", "might", "their", "there", "they",
    "them", "he", "she", "his", "her", "its",
    "it", "we", "our", "you", "your", "i", "me",
    "my", "not", "no", "yes", "also", "just",
    "more", "most", "some", "any", "all", "one",
    "two", "three",
}


# ============================================================
# TEXT
# ============================================================

def normalize_text(text) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def meaningful_tokens(text) -> set[str]:
    return {
        x
        for x in normalize_text(text).split()
        if len(x) >= 3 and x not in STOPWORDS
    }


# ============================================================
# GENERIC JSON HELPERS
# ============================================================

def find_first_value(obj, keys):
    """
    Recursively search a JSON object for the first useful value
    associated with one of the requested keys.
    """

    if isinstance(obj, dict):

        # Prefer direct matches first.
        for key in keys:
            if key in obj:
                value = obj[key]

                if value is not None and value != "":
                    return value

        # Then recurse.
        for value in obj.values():
            result = find_first_value(value, keys)

            if result is not None and result != "":
                return result

    elif isinstance(obj, list):

        for item in obj:
            result = find_first_value(item, keys)

            if result is not None and result != "":
                return result

    return None


def find_all_values(obj, keys):
    """
    Recursively collect values for requested keys.
    """

    results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            if key in keys:
                results.append(value)

            results.extend(
                find_all_values(value, keys)
            )

    elif isinstance(obj, list):

        for item in obj:
            results.extend(
                find_all_values(item, keys)
            )

    return results


# ============================================================
# QUESTION FIELDS
# ============================================================

def get_question_id(record: dict) -> str:
    value = find_first_value(
        record,
        [
            "question_id",
            "query_id",
            "eval_id",
            "example_id",
            "qid",
            "id",
            "uid",
        ],
    )

    if value is None:
        return ""

    return str(value)


def get_question_text(record: dict) -> str:
    value = find_first_value(
        record,
        [
            "question",
            "query",
            "question_text",
            "query_text",
        ],
    )

    return str(value or "")


def get_question_timestamp(record: dict) -> Optional[float]:
    value = find_first_value(
        record,
        [
            "question_ts",
            "query_ts",
            "question_timestamp",
            "query_timestamp",
        ],
    )

    return parse_timestamp(value)


# ============================================================
# DATE
# ============================================================

def parse_timestamp(value) -> Optional[float]:

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip()

    if not value:
        return None

    try:
        return float(value)
    except ValueError:
        pass

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
    ]

    for fmt in formats:

        try:

            dt = datetime.strptime(
                value,
                fmt,
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.timestamp()

        except ValueError:
            continue

    return None


# ============================================================
# CLEAN POOL LOADING
# ============================================================

def load_clean_pool_records():

    if not CLEAN_POOLS_PATH.exists():

        raise FileNotFoundError(
            f"Missing clean pool file:\n"
            f"{CLEAN_POOLS_PATH}"
        )

    records = []

    with CLEAN_POOLS_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            records.append(
                json.loads(line)
            )

    return records


def get_record_id(record):

    return get_question_id(record)


def extract_text_from_object(obj) -> list[str]:
    """
    Recursively collect plausible passage/evidence text.
    """

    texts = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

            if key_lower in {
                "text",
                "passage",
                "content",
                "evidence",
                "document",
                "document_text",
                "chunk_text",
                "context",
            }:

                if isinstance(value, str):
                    if len(value.strip()) >= 30:
                        texts.append(value)

            else:
                texts.extend(
                    extract_text_from_object(value)
                )

    elif isinstance(obj, list):

        for item in obj:
            texts.extend(
                extract_text_from_object(item)
            )

    return texts


def extract_clean_evidence_from_pool(
    pool_record: dict,
) -> str:
    """
    Find the answer-bearing / gold text in the clean pool.

    We first look for explicit gold/answer-bearing structures.
    """

    # --------------------------------------------------------
    # Explicit gold fields.
    # --------------------------------------------------------

    gold_values = find_all_values(
        pool_record,
        [
            "gold_text",
            "gold_passage",
            "gold_evidence",
            "answer_bearing_text",
            "supporting_passage",
        ],
    )

    for value in gold_values:

        if isinstance(value, str) and len(value) >= 30:
            return value

    # --------------------------------------------------------
    # Look through candidate/passages/documents.
    # --------------------------------------------------------

    containers = find_all_values(
        pool_record,
        [
            "candidates",
            "passages",
            "chunks",
            "documents",
            "contexts",
        ],
    )

    for container in containers:

        if not isinstance(container, list):
            continue

        for item in container:

            if not isinstance(item, dict):
                continue

            is_gold = (
                item.get("is_gold") is True
                or item.get("gold") is True
                or item.get("is_answer") is True
                or item.get("answer_bearing") is True
                or item.get("is_answer_bearing") is True
            )

            if not is_gold:
                continue

            text = find_first_value(
                item,
                [
                    "text",
                    "passage",
                    "content",
                    "chunk_text",
                    "evidence",
                ],
            )

            if isinstance(text, str) and len(text) >= 30:
                return text

    return ""


def build_clean_evidence_map():

    print()
    print(
        "Loading clean StreamingQA pools..."
    )

    records = load_clean_pool_records()

    evidence_map = {}

    for record in records:

        qid = get_record_id(record)

        if not qid:
            continue

        evidence = extract_clean_evidence_from_pool(
            record
        )

        if evidence:
            evidence_map[qid] = evidence

    print(
        f"Clean-pool records: {len(records)}"
    )

    print(
        f"Questions with extracted evidence: "
        f"{len(evidence_map)}"
    )

    return evidence_map


# ============================================================
# LOAD PILOT
# ============================================================

def load_questions():

    if not QUESTIONS_PATH.exists():

        raise FileNotFoundError(
            f"Missing:\n{QUESTIONS_PATH}"
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

            records.append(
                json.loads(line)
            )

    return records[:PILOT_QUERY_COUNT]


# ============================================================
# WMT DOWNLOAD
# ============================================================

def download_wmt_year(year: int) -> Path:

    WMT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        WMT_DIR
        / f"news-docs.{year}.en.filtered.gz"
    )

    if path.exists() and path.stat().st_size > 0:
        return path

    url = (
        f"{WMT_BASE_URL}"
        f"news-docs.{year}.en.filtered.gz"
    )

    for attempt in range(1, 6):

        print(
            f"  downloading {url} "
            f"(attempt {attempt}/5)",
            flush=True,
        )

        try:

            with requests.get(
                url,
                stream=True,
                timeout=120,
            ) as response:

                response.raise_for_status()

                tmp = path.with_suffix(
                    path.suffix + ".partial"
                )

                with tmp.open("wb") as out:

                    for chunk in response.iter_content(
                        chunk_size=1024 * 1024
                    ):

                        if chunk:
                            out.write(chunk)

                tmp.replace(path)

                return path

        except Exception as exc:

            print(
                f"  download failed: {exc}"
            )

            time.sleep(5)

    raise RuntimeError(
        f"Failed downloading WMT {year}"
    )


# ============================================================
# WMT STREAMING
# ============================================================

def stream_wmt_documents(year: int):

    path = download_wmt_year(year)

    print(
        f"  streaming {path}",
        flush=True,
    )

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as f:

        doc_id = None
        buffer = []

        for line in f:

            line = line.rstrip("\n")

            if line.startswith("<doc"):

                if doc_id is not None:
                    yield (
                        doc_id,
                        "\n".join(buffer),
                    )

                match = re.search(
                    r'id="([^"]+)"',
                    line,
                )

                doc_id = (
                    match.group(1)
                    if match
                    else line
                )

                buffer = []

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


def split_passages(text: str):

    for paragraph in re.split(
        r"\n\s*\n+",
        text,
    ):

        paragraph = paragraph.strip()

        if len(paragraph) < 80:
            continue

        yield paragraph


# ============================================================
# CANDIDATES
# ============================================================

def add_candidate(
    candidate_store,
    qid,
    candidate,
):

    candidates = candidate_store.setdefault(
        qid,
        [],
    )

    candidates.append(candidate)

    candidates.sort(
        key=lambda x: (
            x["relevance_score"],
            x["evidence_overlap"],
            x["question_overlap"],
        ),
        reverse=True,
    )

    seen = set()
    unique = []

    for item in candidates:

        key = normalize_text(
            item["text"]
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    candidate_store[qid] = unique[
        :MAX_CANDIDATES_PER_QUERY
    ]


# ============================================================
# CHECKPOINT
# ============================================================

def load_checkpoint():

    if not CHECKPOINT_PATH.exists():

        return {
            "completed_years": [],
            "candidate_store": {},
            "streamed_counts": {},
        }

    with CHECKPOINT_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def save_checkpoint(
    candidate_store,
    completed_years,
    streamed_counts,
):

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
        "completed_years": sorted(
            completed_years
        ),
        "streamed_counts": streamed_counts,
        "candidate_store": candidate_store,
    }

    tmp = CHECKPOINT_PATH.with_suffix(
        ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    tmp.replace(
        CHECKPOINT_PATH
    )

    print(
        "  checkpoint saved",
        flush=True,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "ChronoGuard-RAG -- STALE SOURCE PILOT"
    )
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

    # --------------------------------------------------------
    # Load clean evidence.
    # --------------------------------------------------------

    evidence_map = build_clean_evidence_map()

    # --------------------------------------------------------
    # Build pilot query information.
    # --------------------------------------------------------

    query_info = {}

    print()
    print(
        "Loaded pilot questions:"
    )

    for index, question in enumerate(
        questions
    ):

        qid = get_question_id(
            question
        )

        qtext = get_question_text(
            question
        )

        qts = get_question_timestamp(
            question
        )

        evidence = evidence_map.get(
            qid,
            "",
        )

        # Fallback: if ID wasn't found in the
        # question record, create the known StreamingQA
        # evaluation ID format only when available
        # elsewhere in the record.
        if not qid:

            # Search all strings for eval-XXXXX.
            strings = []

            def collect_strings(obj):

                if isinstance(obj, dict):

                    for value in obj.values():
                        collect_strings(value)

                elif isinstance(obj, list):

                    for value in obj:
                        collect_strings(value)

                elif isinstance(obj, str):

                    strings.append(obj)

            collect_strings(question)

            for value in strings:

                match = re.search(
                    r"eval-\d{6}",
                    value,
                )

                if match:

                    qid = match.group(0)
                    break

        print(
            f"  {qid or '[NO-ID]'} | "
            f"question_ts={qts} | "
            f"evidence_chars={len(evidence)}"
        )

        if not qid or qts is None:
            continue

        query_info[qid] = {
            "question": qtext,
            "question_ts": qts,
            "question_tokens": (
                meaningful_tokens(qtext)
            ),
            "evidence": evidence,
            "evidence_tokens": (
                meaningful_tokens(evidence)
            ),
        }

    # --------------------------------------------------------
    # IMPORTANT:
    # Only search years that can actually contain passages
    # at least 30 days before the question.
    #
    # This avoids scanning every year from 2008 onward.
    # --------------------------------------------------------

    years_needed = set()

    for info in query_info.values():

        qdate = datetime.fromtimestamp(
            info["question_ts"],
            tz=timezone.utc,
        )

        # Any year earlier than the question year
        # can contain stale evidence.
        #
        # We use the same broad year selection as the
        # previous working pilot, rather than scanning
        # 2008-2019 indiscriminately.
        #
        # The available WMT years are the years for which
        # archives are actually present/requested.

        for year in range(
            2008,
            qdate.year,
        ):

            # Only retain years where the year-end is
            # at least 30 days before the question.
            year_end = datetime(
                year,
                12,
                31,
                tzinfo=timezone.utc,
            ).timestamp()

            age = (
                info["question_ts"]
                - year_end
            ) / 86400.0

            if age >= STALE_DAYS:
                years_needed.add(year)

    # --------------------------------------------------------
    # Reduce to years actually represented by the existing
    # WMT archives, if those files already exist.
    #
    # Otherwise the year remains eligible for download.
    # --------------------------------------------------------

    years_needed = sorted(
        years_needed
    )

    print()
    print(
        f"Years potentially needed: "
        f"{years_needed}"
    )

    # --------------------------------------------------------
    # Checkpoint.
    # --------------------------------------------------------

    checkpoint = load_checkpoint()

    completed_years = set(
        checkpoint.get(
            "completed_years",
            [],
        )
    )

    candidate_store = checkpoint.get(
        "candidate_store",
        {},
    )

    streamed_counts = checkpoint.get(
        "streamed_counts",
        {},
    )

    print()
    print(
        "Completed years from checkpoint: "
        f"{sorted(completed_years)}"
    )

    # --------------------------------------------------------
    # PROCESS YEAR
    # --------------------------------------------------------

    for year in years_needed:

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
        additions = 0

        try:

            for doc_id, document_text in (
                stream_wmt_documents(year)
            ):

                streamed += 1

                if streamed % 500_000 == 0:

                    print(
                        f"  streamed documents: "
                        f"{streamed:,}",
                        flush=True,
                    )

                for passage in split_passages(
                    document_text
                ):

                    passage_tokens = (
                        meaningful_tokens(
                            passage
                        )
                    )

                    if not passage_tokens:
                        continue

                    for qid, info in query_info.items():

                        q_overlap = len(
                            info["question_tokens"]
                            & passage_tokens
                        )

                        if (
                            q_overlap
                            < MIN_QUERY_TOKEN_OVERLAP
                        ):
                            continue

                        e_overlap = len(
                            info["evidence_tokens"]
                            & passage_tokens
                        )

                        # If evidence is available,
                        # use it as the relevance anchor.
                        if info["evidence_tokens"]:

                            if (
                                e_overlap
                                < MIN_EVIDENCE_TOKEN_OVERLAP
                            ):
                                continue

                        # Conservative year-level timestamp.
                        #
                        # A 2011 passage is treated as 2011
                        # for the initial stale-source screening.
                        passage_timestamp = datetime(
                            year,
                            1,
                            1,
                            tzinfo=timezone.utc,
                        ).timestamp()

                        age_days = (
                            info["question_ts"]
                            - passage_timestamp
                        ) / 86400.0

                        if age_days < STALE_DAYS:
                            continue

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
                            "relevance_score": (
                                score
                            ),
                        }

                        add_candidate(
                            candidate_store,
                            qid,
                            candidate,
                        )

                        additions += 1

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
                f"{additions}"
            )

            # Show current yield.
            for qid in query_info:

                count = len(
                    candidate_store.get(
                        qid,
                        [],
                    )
                )

                print(
                    f"    {qid}: "
                    f"{count} candidates"
                )

            save_checkpoint(
                candidate_store,
                completed_years,
                streamed_counts,
            )

        except KeyboardInterrupt:

            print()
            print(
                "STOPPED BY USER."
            )

            print(
                "Saving checkpoint..."
            )

            save_checkpoint(
                candidate_store,
                completed_years,
                streamed_counts,
            )

            raise

        except Exception:

            print()
            print(
                f"[{year}] failed."
            )

            print(
                "Saving checkpoint before exit..."
            )

            save_checkpoint(
                candidate_store,
                completed_years,
                streamed_counts,
            )

            raise

    # --------------------------------------------------------
    # FINAL OUTPUT
    # --------------------------------------------------------

    ATTACK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as f:

        for qid, info in query_info.items():

            row = {
                "question_id": qid,
                "question": info["question"],
                "question_ts": info["question_ts"],
                "clean_evidence": info["evidence"],
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
    print(
        "FINAL STALE-SOURCE PILOT RESULTS"
    )
    print("=" * 70)

    for qid in query_info:

        count = len(
            candidate_store.get(
                qid,
                [],
            )
        )

        print(
            f"{qid}: {count} candidates"
        )

    print()
    print(
        f"Output: {OUTPUT_PATH}"
    )

    print(
        f"Checkpoint: {CHECKPOINT_PATH}"
    )


if __name__ == "__main__":
    main()