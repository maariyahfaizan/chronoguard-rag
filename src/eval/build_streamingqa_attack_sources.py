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
# Memory-safe, resumable main pilot
# ---------------------------------------------------------------------------

def _stream_year_timestamped_passages(
    curl_path: str,
    url: str,
    netrc_path: Path,
    sorting_keys_path: Path,
    max_attempts: int = 5,
):
    """
    Stream one WMT year without materializing the complete year in memory.

    Important:
        - WMT documents are consumed as a generator.
        - publication timestamps are recorded as each document passes through.
        - WMT passages are yielded immediately.
        - no multi-million-passage list is created.

    If the network stream fails, the complete year is retried.
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

        sorting_key_to_ts = {}
        passage_count = 0

        try:
            raw_docs = extraction.get_deduplicated_wmt_docs(
                wmt_archive_files=[proc.stdout],
                deduplicated_sorting_keys_file=str(
                    sorting_keys_path
                ),
            )

            def docs_with_timestamps():
                """
                Pass WMT documents through while recording only the
                sorting-key -> publication-timestamp mapping needed
                for passage timestamp recovery.
                """
                for doc in raw_docs:
                    sorting_key_to_ts[doc.sorting_key] = (
                        doc.publication_ts
                    )
                    yield doc

            passages = extraction.get_wmt_passages_from_docs(
                docs_with_timestamps(),
                prepend_date=False,
            )

            for passage in passages:
                passage_count += 1

                try:
                    passage_dt = _passage_timestamp(
                        passage,
                        sorting_key_to_ts,
                    )
                except Exception:
                    continue

                yield {
                    "doc_id": _passage_doc_id(passage),
                    "text": _passage_text(passage),
                    "timestamp": passage_dt.isoformat(),
                    "timestamp_unix": int(
                        passage_dt.timestamp()
                    ),
                }

            proc.stdout.close()

            returncode = proc.wait()

            if returncode != 0:
                raise RuntimeError(
                    f"curl exited {returncode} mid-stream"
                )

            print(
                f"  completed stream: "
                f"{passage_count} passages"
            )

            return

        except Exception as exc:
            print(
                f"  stream attempt {attempt} failed: {exc!r}"
            )

            try:
                proc.kill()
            except Exception:
                pass

            try:
                proc.stdout.close()
            except Exception:
                pass

            try:
                proc.wait()
            except Exception:
                pass

            if attempt == max_attempts:
                raise RuntimeError(
                    f"Failed to stream {url} after "
                    f"{max_attempts} attempts."
                ) from exc

            time.sleep(5)


def _add_passage_to_candidates(
    passage: dict,
    question_infos: list[dict],
    candidate_store: dict[str, list[dict]],
    seen_doc_ids: dict[str, set[str]],
) -> None:
    """
    Test one streamed passage against the pilot questions.

    Only the best MAX_CANDIDATES_PER_QUERY passages are retained
    for each question, so memory usage remains tiny compared with
    storing the entire WMT corpus.
    """

    passage_dt = datetime.datetime.fromisoformat(
        passage["timestamp"]
    )

    passage_ts = passage["timestamp_unix"]

    for info in question_infos:
        if passage_ts > info["cutoff_ts"]:
            continue

        qa_id = info["qa_id"]

        # Prevent duplicates if a year has to be retried.
        if passage["doc_id"] in seen_doc_ids[qa_id]:
            continue

        overlap = lexical_overlap_score(
            info["question_tokens"],
            passage["text"],
        )

        if overlap < MIN_QUERY_TOKEN_OVERLAP:
            continue

        candidate = {
            **passage,
            "question_ts": info["question_ts"],
            "question_datetime": info["question_dt"].isoformat(),
            "age_days": (
                info["question_dt"] - passage_dt
            ).total_seconds() / 86400.0,
            "lexical_overlap": overlap,
        }

        candidates = candidate_store[qa_id]
        candidates.append(candidate)

        # Keep only the best candidates.
        candidates.sort(
            key=lambda x: (
                -x["lexical_overlap"],
                -x["timestamp_unix"],
            )
        )

        if len(candidates) > MAX_CANDIDATES_PER_QUERY:
            removed = candidates.pop()

            # It is safe to remove this ID from the seen set because
            # another passage with the same doc_id should not normally
            # be considered again. The candidate list itself remains
            # authoritative.
            seen_doc_ids[qa_id].add(
                candidate["doc_id"]
            )

        else:
            seen_doc_ids[qa_id].add(
                candidate["doc_id"]
            )


def _write_checkpoint(
    checkpoint_path: Path,
    questions: list[dict],
    candidate_store: dict[str, list[dict]],
    completed_years: list[int],
) -> None:
    """
    Atomically save the small pilot checkpoint.

    Only selected candidates are stored here, never the WMT passages.
    """

    state = {
        "version": 1,
        "pilot_query_count": len(questions),
        "stale_days": STALE_DAYS,
        "max_candidates_per_query": (
            MAX_CANDIDATES_PER_QUERY
        ),
        "min_query_token_overlap": (
            MIN_QUERY_TOKEN_OVERLAP
        ),
        "question_ids": [
            q["qa_id"]
            for q in questions
        ],
        "completed_years": sorted(
            set(completed_years)
        ),
        "candidate_store": candidate_store,
    }

    temporary_path = checkpoint_path.with_suffix(
        checkpoint_path.suffix + ".tmp"
    )

    with open(
        temporary_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(checkpoint_path)


def _load_checkpoint(
    checkpoint_path: Path,
    questions: list[dict],
) -> tuple[set[int], dict[str, list[dict]]]:
    """
    Load an existing checkpoint if it belongs to the same pilot.

    Returns:
        completed_years
        candidate_store
    """

    if not checkpoint_path.exists():
        return set(), {
            q["qa_id"]: []
            for q in questions
        }

    print(
        f"Found checkpoint: {checkpoint_path}"
    )

    with open(
        checkpoint_path,
        "r",
        encoding="utf-8",
    ) as f:
        state = json.load(f)

    expected_ids = [
        q["qa_id"]
        for q in questions
    ]

    if state.get("version") != 1:
        raise RuntimeError(
            "Checkpoint version is incompatible. "
            "Delete the checkpoint and rerun."
        )

    if state.get("question_ids") != expected_ids:
        raise RuntimeError(
            "Checkpoint question set does not match "
            "the current pilot questions. "
            "Delete the checkpoint before rerunning."
        )

    if state.get("stale_days") != STALE_DAYS:
        raise RuntimeError(
            "Checkpoint STALE_DAYS does not match "
            "the current script."
        )

    candidate_store = {
        q["qa_id"]: []
        for q in questions
    }

    saved_candidates = state.get(
        "candidate_store",
        {},
    )

    for qa_id in candidate_store:
        candidate_store[qa_id] = saved_candidates.get(
            qa_id,
            []
        )

    completed_years = set(
        state.get(
            "completed_years",
            [],
        )
    )

    print(
        "Checkpoint contains completed years: "
        f"{sorted(completed_years)}"
    )

    return completed_years, candidate_store


def _write_final_output(
    output_path: Path,
    questions: list[dict],
    candidate_store: dict[str, list[dict]],
) -> None:
    """
    Convert the small checkpoint state into the final pilot JSONL.
    """

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:

        for question in questions:
            candidates = candidate_store[
                question["qa_id"]
            ]

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
                "answers": question.get(
                    "answers",
                    [],
                ),
                "question_ts": question["question_ts"],
                "evidence_ts": question["evidence_ts"],
                "stale_threshold_days": STALE_DAYS,
                "candidate_count": len(candidates),
                "candidates": candidates,
            }

            f.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                + "\n"
            )


def main():
    cfg = load_config()

    raw_dir = (
        REPO_ROOT
        / cfg["output"]["raw_dir"]
    )

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

    checkpoint_path = (
        output_dir
        / "streamingqa_stale_sources_pilot.checkpoint.json"
    )

    sample = load_sample(raw_dir)

    questions = sample[:PILOT_QUERY_COUNT]

    print("=" * 70)
    print("ChronoGuard-RAG -- STALE SOURCE PILOT")
    print("=" * 70)
    print(f"Questions: {len(questions)}")
    print(
        f"Stale threshold: >= {STALE_DAYS} days"
    )
    print(
        f"Maximum candidates/query: "
        f"{MAX_CANDIDATES_PER_QUERY}"
    )
    print(
        f"Minimum lexical overlap: "
        f"{MIN_QUERY_TOKEN_OVERLAP}"
    )
    print(f"Output: {output_path}")
    print(
        f"Checkpoint: {checkpoint_path}"
    )
    print()

    # ---------------------------------------------------------------
    # Prepare per-question metadata.
    # ---------------------------------------------------------------

    question_infos = []

    for question in questions:
        question_dt = datetime.datetime.fromtimestamp(
            question["question_ts"],
            tz=datetime.timezone.utc,
        )

        cutoff_dt = (
            question_dt
            - datetime.timedelta(days=STALE_DAYS)
        )

        question_infos.append(
            {
                "qa_id": question["qa_id"],
                "question_ts": question["question_ts"],
                "question_dt": question_dt,
                "cutoff_ts": int(
                    cutoff_dt.timestamp()
                ),
                "question_tokens": normalize_tokens(
                    question["question"]
                ),
            }
        )

    # ---------------------------------------------------------------
    # WMT sorting-key file.
    # ---------------------------------------------------------------

    sorting_keys_path = (
        raw_dir
        / "wmt_sorting_key_ids.txt.gz"
    )

    if not sorting_keys_path.exists():
        print(
            "Downloading WMT sorting-key file..."
        )

        url = cfg[
            "evidence_source"
        ][
            "sorting_keys_url"
        ]

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

        print(
            f"Years needed for pilot: {years}"
        )
        print()

        # ---------------------------------------------------------------
        # Load small checkpoint, if present.
        # ---------------------------------------------------------------

        completed_years, candidate_store = (
            _load_checkpoint(
                checkpoint_path,
                questions,
            )
        )

        # Used only to avoid duplicate document IDs within
        # the current execution.
        seen_doc_ids = {
            q["qa_id"]: {
                candidate["doc_id"]
                for candidate in candidate_store[
                    q["qa_id"]
                ]
            }
            for q in questions
        }

        # ---------------------------------------------------------------
        # Process one year at a time.
        #
        # CRITICAL:
        # We never create:
        #
        #     all_passages = [...]
        #
        # and we never convert the WMT documents into a list.
        # ---------------------------------------------------------------

        for year in years:

            if year in completed_years:
                print(
                    f"[{year}] already completed "
                    f"according to checkpoint -- skipping"
                )
                continue

            fname = src[
                "filename_pattern"
            ].format(
                year=year
            )

            url = (
                src["base_url"]
                + fname
            )

            print(
                f"[{year}] processing "
                f"(memory-safe streaming)..."
            )

            streamed_count = 0
            eligible_count = 0

            for passage in _stream_year_timestamped_passages(
                curl_path,
                url,
                netrc_path,
                sorting_keys_path,
            ):
                streamed_count += 1

                before_counts = {
                    qa_id: len(candidates)
                    for qa_id, candidates
                    in candidate_store.items()
                }

                _add_passage_to_candidates(
                    passage,
                    question_infos,
                    candidate_store,
                    seen_doc_ids,
                )

                after_counts = {
                    qa_id: len(candidates)
                    for qa_id, candidates
                    in candidate_store.items()
                }

                if any(
                    after_counts[qa_id]
                    > before_counts[qa_id]
                    for qa_id in candidate_store
                ):
                    eligible_count += 1

            # Only mark the year complete AFTER the entire
            # year has streamed successfully.
            completed_years.add(year)

            _write_checkpoint(
                checkpoint_path,
                questions,
                candidate_store,
                sorted(completed_years),
            )

            print(
                f"[{year}] complete"
            )
            print(
                f"  streamed passages: "
                f"{streamed_count}"
            )
            print(
                f"  passages added to candidate sets: "
                f"{eligible_count}"
            )
            print(
                f"  checkpoint saved"
            )
            print()

        # ---------------------------------------------------------------
        # Final output.
        # ---------------------------------------------------------------

        _write_final_output(
            output_path,
            questions,
            candidate_store,
        )

        print()
        print("=" * 70)
        print("PILOT COMPLETE")
        print("=" * 70)
        print(
            f"Saved: {output_path}"
        )

        total_candidates = 0
        queries_with_candidates = 0

        for question in questions:
            count = len(
                candidate_store[
                    question["qa_id"]
                ]
            )

            total_candidates += count

            if count > 0:
                queries_with_candidates += 1

            print(
                f"{question['qa_id']}: "
                f"{count} stale candidates"
            )

        print()
        print(
            f"Queries with >=1 candidate: "
            f"{queries_with_candidates}/"
            f"{len(questions)}"
        )

        print(
            f"Total candidate passages: "
            f"{total_candidates}"
        )

        print()
        print(
            "Checkpoint retained at:"
        )
        print(
            checkpoint_path
        )

    finally:
        try:
            netrc_path.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()