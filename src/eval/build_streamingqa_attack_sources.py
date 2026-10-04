"""
ChronoGuard-RAG -- Week-5 stale-source extractor.

Purpose
-------
Build a separate pool of older, topically relevant WMT passages that can
later be injected into the frozen StreamingQA control pools as a
stale-evidence attack.

IMPORTANT
---------
This script does NOT modify:
    data/processed/streamingqa_control_pools.jsonl
    data/processed/streamingqa_control_pools_chunked.jsonl

It also does not create fabricated evidence.

Pilot behavior:
    - first 10 questions only
    - stale threshold: >= 30 days before question_ts
    - maximum 5 stale candidates per question
    - lexical filtering only
    - provenance is preserved
"""

import datetime
import gzip
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Repository / existing StreamingQA extraction code
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

sys.path.insert(0, str(REPO_ROOT / "third_party" / "streamingqa"))
import extraction  # noqa: E402


# ---------------------------------------------------------------------------
# Pilot settings
# ---------------------------------------------------------------------------

PILOT_QUERY_COUNT = 10
STALE_DAYS = 30
MAX_CANDIDATES_PER_QUERY = 5

# Require at least this many meaningful question tokens to occur in the
# passage. This is deliberately only a cheap first-pass relevance filter.
MIN_QUERY_TOKEN_OVERLAP = 2

# Keep the extractor conservative about extremely short tokens.
MIN_TOKEN_LENGTH = 3


# ---------------------------------------------------------------------------
# Config / authentication helpers
# ---------------------------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _require_curl() -> str:
    from shutil import which

    curl_path = which("curl")
    if curl_path is None:
        raise RuntimeError(
            "curl was not found on PATH. Install/enable curl before running "
            "the WMT attack-source extractor."
        )
    return curl_path


def _make_netrc(cfg: dict) -> Path:
    """
    Create a temporary netrc file using the same environment variables
    required by the existing WMT fetcher.

    The file is temporary and is never written into the repository.
    """
    username = cfg["evidence_source"].get("username_env", "WMT_NEWSCRAWL_USER")
    password = cfg["evidence_source"].get("password_env", "WMT_NEWSCRAWL_PASS")

    user = __import__("os").environ.get(username)
    password_value = __import__("os").environ.get(password)

    if not user or not password_value:
        raise RuntimeError(
            f"Missing WMT credentials. Set {username} and {password} "
            "in the environment before running this script."
        )

    fd, path = tempfile.mkstemp(prefix="chronoguard_wmt_", text=True)

    netrc_path = Path(path)

    # WMT News Crawl host used by the existing fetch configuration.
    host = cfg["evidence_source"].get(
        "netrc_machine",
        "data.statmt.org",
    )

    netrc_path.write_text(
        f"machine {host}\n"
        f"login {user}\n"
        f"password {password_value}\n",
        encoding="utf-8",
    )

    return netrc_path


def _start_curl_stream(
    curl_path: str,
    url: str,
    netrc_path: Path,
):
    cmd = [
        curl_path,
        "--netrc-file",
        str(netrc_path),
        "--fail",
        "--show-error",
        "--silent",
        url,
    ]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
    )


def _stream_year_docs(
    curl_path: str,
    url: str,
    netrc_path: Path,
    sorting_keys_path: Path,
    max_attempts: int = 5,
) -> list:
    """
    Reuse the same streaming approach as fetch_wmt_archives.py.

    No complete WMT archive is written to disk.
    """
    for attempt in range(1, max_attempts + 1):
        print(
            f"  streaming {url} "
            f"(attempt {attempt}/{max_attempts})"
        )

        proc = _start_curl_stream(
            curl_path,
            url,
            netrc_path,
        )

        try:
            docs = list(
                extraction.get_deduplicated_wmt_docs(
                    wmt_archive_files=[proc.stdout],
                    deduplicated_sorting_keys_file=str(
                        sorting_keys_path
                    ),
                )
            )

            proc.stdout.close()

            returncode = proc.wait()

            if returncode != 0:
                raise RuntimeError(
                    f"curl exited {returncode} mid-stream"
                )

            return docs

        except Exception as exc:
            print(
                f"  stream attempt {attempt} failed: {exc!r}"
            )

            try:
                proc.kill()
            except Exception:
                pass

            proc.wait()

            if attempt == max_attempts:
                raise RuntimeError(
                    f"Failed to stream {url} after "
                    f"{max_attempts} attempts."
                ) from exc

            time.sleep(5)


# ---------------------------------------------------------------------------
# WMT passage timestamp helpers
# ---------------------------------------------------------------------------

def _extract_sorting_key(passage_id: str) -> str:
    """
    Recover the parent WMTDoc sorting_key from:

        {sorting_key}_{passage_idx}

    We split only on the final numeric suffix because sorting_key itself
    may contain underscores.
    """
    match = re.match(r"^(.*)_(\d+)$", passage_id)

    if not match:
        raise ValueError(
            f"Unexpected passage id format: {passage_id!r}"
        )

    return match.group(1)


def _passage_timestamp(
    passage,
    sorting_key_to_ts: dict,
) -> datetime.datetime:
    sorting_key = _extract_sorting_key(passage.id)

    ts = sorting_key_to_ts[sorting_key]

    return datetime.datetime.fromtimestamp(
        ts,
        tz=datetime.timezone.utc,
    )


def _passage_text(passage) -> str:
    text = (
        passage["text"]
        if isinstance(passage, dict)
        else passage.text
    )

    if isinstance(text, bytes):
        return text.decode(
            "utf-8",
            errors="replace",
        )

    return text


def _passage_doc_id(passage) -> str:
    return (
        passage["doc_id"]
        if isinstance(passage, dict)
        else passage.id
    )


# ---------------------------------------------------------------------------
# Question loading
# ---------------------------------------------------------------------------

def load_sample(raw_dir: Path) -> list[dict]:
    sample_path = raw_dir / "streamingqa_control_sample.jsonl"

    if not sample_path.exists():
        raise FileNotFoundError(
            f"{sample_path} not found.\n"
            "Restore the frozen StreamingQA control sample before "
            "running the attack-source extractor."
        )

    with open(sample_path, "r", encoding="utf-8") as f:
        return [
            json.loads(line)
            for line in f
            if line.strip()
        ]


# ---------------------------------------------------------------------------
# Lexical relevance filter
# ---------------------------------------------------------------------------

def normalize_tokens(text: str) -> set[str]:
    """
    Cheap lexical normalization.

    This is NOT a semantic relevance judgment.
    It is only used to reduce the number of candidate passages that
    require manual inspection.
    """
    tokens = re.findall(
        r"[A-Za-z0-9]+",
        text.lower(),
    )

    return {
        token
        for token in tokens
        if len(token) >= MIN_TOKEN_LENGTH
    }


def lexical_overlap_score(
    question_tokens: set[str],
    passage_text: str,
) -> int:
    passage_tokens = normalize_tokens(passage_text)

    return len(question_tokens & passage_tokens)


# ---------------------------------------------------------------------------
# Per-query stale candidate selection
# ---------------------------------------------------------------------------

def build_query_metadata(question: dict) -> dict:
    question_ts = question["question_ts"]

    question_dt = datetime.datetime.fromtimestamp(
        question_ts,
        tz=datetime.timezone.utc,
    )

    cutoff_dt = (
        question_dt
        - datetime.timedelta(days=STALE_DAYS)
    )

    return {
        "qa_id": question["qa_id"],
        "question": question["question"],
        "question_ts": question_ts,
        "question_datetime": question_dt.isoformat(),
        "stale_cutoff_datetime": cutoff_dt.isoformat(),
        "stale_days": STALE_DAYS,
    }


def select_stale_candidates(
    question: dict,
    passages: list,
) -> list[dict]:
    """
    Select older passages for one question.

    Conditions:
        1. passage timestamp must be >= 30 days older than question_ts
        2. passage must have lexical overlap with the question
        3. maximum 5 candidates
        4. candidates are ranked by lexical overlap, then recency

    No gold labels are changed here.
    """
    question_dt = datetime.datetime.fromtimestamp(
        question["question_ts"],
        tz=datetime.timezone.utc,
    )

    cutoff_dt = (
        question_dt
        - datetime.timedelta(days=STALE_DAYS)
    )

    question_tokens = normalize_tokens(
        question["question"]
    )

    candidates = []

    for passage in passages:
        try:
            passage_dt = _passage_timestamp(
                passage,
                passage._sorting_key_to_ts
                if hasattr(passage, "_sorting_key_to_ts")
                else {},
            )
        except Exception:
            # Timestamp recovery is handled by the caller because
            # WMTPassage does not itself contain publication_ts.
            continue

        if passage_dt > cutoff_dt:
            continue

        text = _passage_text(passage)

        overlap = lexical_overlap_score(
            question_tokens,
            text,
        )

        if overlap < MIN_QUERY_TOKEN_OVERLAP:
            continue

        candidates.append(
            {
                "doc_id": _passage_doc_id(passage),
                "text": text,
                "timestamp": passage_dt.isoformat(),
                "timestamp_unix": int(
                    passage_dt.timestamp()
                ),
                "question_ts": question["question_ts"],
                "question_datetime": question_dt.isoformat(),
                "age_days": (
                    question_dt - passage_dt
                ).total_seconds() / 86400.0,
                "lexical_overlap": overlap,
            }
        )

    candidates.sort(
        key=lambda x: (
            -x["lexical_overlap"],
            -x["timestamp_unix"],
        )
    )

    return candidates[:MAX_CANDIDATES_PER_QUERY]


# ---------------------------------------------------------------------------
# Main pilot
# ---------------------------------------------------------------------------

def main():
    cfg = load_config()

    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    output_dir = (
        REPO_ROOT
        / "data"
        / "processed"
        / "attack_sources"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_dir
        / "streamingqa_stale_sources_pilot.jsonl"
    )

    sample = load_sample(raw_dir)

    questions = sample[:PILOT_QUERY_COUNT]

    print("=" * 70)
    print("ChronoGuard-RAG -- STALE SOURCE PILOT")
    print("=" * 70)
    print(f"Questions: {len(questions)}")
    print(f"Stale threshold: >= {STALE_DAYS} days")
    print(
        f"Maximum candidates/query: "
        f"{MAX_CANDIDATES_PER_QUERY}"
    )
    print(
        f"Minimum lexical overlap: "
        f"{MIN_QUERY_TOKEN_OVERLAP}"
    )
    print(f"Output: {output_path}")
    print()

    sorting_keys_path = (
        raw_dir
        / "wmt_sorting_key_ids.txt.gz"
    )

    if not sorting_keys_path.exists():
        print("Downloading WMT sorting-key file...")
        url = cfg["evidence_source"]["sorting_keys_url"]
        urllib.request.urlretrieve(
            url,
            sorting_keys_path,
        )

    curl_path = _require_curl()

    netrc_path = _make_netrc(cfg)

    try:
        src = cfg["evidence_source"]

        years = sorted(
            {
                datetime.datetime.fromtimestamp(
                    q["question_ts"],
                    tz=datetime.timezone.utc,
                ).year
                for q in questions
            }
            |
            {
                datetime.datetime.fromtimestamp(
                    q["evidence_ts"],
                    tz=datetime.timezone.utc,
                ).year
                for q in questions
            }
        )

        print(f"Years needed for pilot: {years}")
        print()

        # Accumulate passages by year.
        all_passages = []

        for year in years:
            fname = src["filename_pattern"].format(
                year=year
            )

            url = src["base_url"] + fname

            print(f"[{year}] extracting WMT documents...")

            wmt_docs = _stream_year_docs(
                curl_path,
                url,
                netrc_path,
                sorting_keys_path,
            )

            sorting_key_to_ts = {
                doc.sorting_key: doc.publication_ts
                for doc in wmt_docs
            }

            passages = list(
                extraction.get_wmt_passages_from_docs(
                    wmt_docs,
                    prepend_date=False,
                )
            )

            print(
                f"[{year}] extracted "
                f"{len(passages)} passages"
            )

            for passage in passages:
                try:
                    passage_dt = _passage_timestamp(
                        passage,
                        sorting_key_to_ts,
                    )
                except Exception:
                    continue

                # Attach timestamp mapping locally so the selector can
                # operate without changing the third-party WMTPassage class.
                all_passages.append(
                    {
                        "doc_id": _passage_doc_id(passage),
                        "text": _passage_text(passage),
                        "timestamp": passage_dt.isoformat(),
                        "timestamp_unix": int(
                            passage_dt.timestamp()
                        ),
                    }
                )

        print()
        print(
            f"Total timestamped passages available "
            f"for pilot: {len(all_passages)}"
        )
        print()

        # ---------------------------------------------------------------
        # Select candidates query-by-query.
        # ---------------------------------------------------------------

        results = []

        for index, question in enumerate(
            questions,
            start=1,
        ):
            question_dt = datetime.datetime.fromtimestamp(
                question["question_ts"],
                tz=datetime.timezone.utc,
            )

            cutoff_dt = (
                question_dt
                - datetime.timedelta(days=STALE_DAYS)
            )

            question_tokens = normalize_tokens(
                question["question"]
            )

            candidates = []

            for passage in all_passages:
                passage_dt = datetime.datetime.fromisoformat(
                    passage["timestamp"]
                )

                if passage_dt > cutoff_dt:
                    continue

                overlap = lexical_overlap_score(
                    question_tokens,
                    passage["text"],
                )

                if overlap < MIN_QUERY_TOKEN_OVERLAP:
                    continue

                candidates.append(
                    {
                        **passage,
                        "question_ts": question[
                            "question_ts"
                        ],
                        "question_datetime": (
                            question_dt.isoformat()
                        ),
                        "age_days": (
                            question_dt - passage_dt
                        ).total_seconds() / 86400.0,
                        "lexical_overlap": overlap,
                    }
                )

            candidates.sort(
                key=lambda x: (
                    -x["lexical_overlap"],
                    -x["timestamp_unix"],
                )
            )

            candidates = candidates[
                :MAX_CANDIDATES_PER_QUERY
            ]

            result = {
                "qa_id": question["qa_id"],
                "question": question["question"],
                "answers": question.get("answers", []),
                "question_ts": question["question_ts"],
                "evidence_ts": question["evidence_ts"],
                "stale_threshold_days": STALE_DAYS,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }

            results.append(result)

            print(
                f"[{index:02d}/{len(questions)}] "
                f"{question['qa_id']}: "
                f"{len(candidates)} stale candidates"
            )

        # ---------------------------------------------------------------
        # Write pilot output.
        # ---------------------------------------------------------------

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as f:
            for result in results:
                f.write(
                    json.dumps(
                        result,
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        print()
        print("=" * 70)
        print("PILOT COMPLETE")
        print("=" * 70)
        print(f"Saved: {output_path}")

        total_candidates = sum(
            r["candidate_count"]
            for r in results
        )

        queries_with_candidates = sum(
            r["candidate_count"] > 0
            for r in results
        )

        print(
            f"Queries with >=1 candidate: "
            f"{queries_with_candidates}/{len(results)}"
        )

        print(
            f"Total candidate passages: "
            f"{total_candidates}"
        )

    finally:
        try:
            netrc_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()