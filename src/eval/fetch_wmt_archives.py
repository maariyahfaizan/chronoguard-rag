"""
Weeks 3-4 | StreamingQA combined fetch+extract, year-by-year, disk-bounded.

REPLACES the old fetch_wmt_archives.py (which downloaded all 13 years'
raw archives before any extraction happened -- ~50GB peak disk usage,
which broke on Kaggle when running several years in parallel: curl started
failing with "Failure writing output to destination" and burning
bandwidth throwing away gigabytes on every retry).

This version never holds more than ONE year's raw archive on disk at a
time: for each year it downloads the archive, extracts ONLY the passages
that fall within a safety margin of any sampled question's evidence_ts
(not the whole year), appends those to a running "relevant passages"
file, then DELETES the raw archive before moving to the next year.

Run this, then build_streamingqa_pools.py (also replaced -- see that
file's own docstring), then preprocess_streamingqa.py (unchanged).

Prerequisite: data/raw/streamingqa_control_sample.jsonl must already exist
(from save_snapshot_streamingqa.py) -- this script reads it, it does not
regenerate it.

AUTH: doc/en/ is login-gated (user: newscrawl). Credentials are read from
environment variables and written to a temporary --netrc-file for curl (so
the password never appears in the process command line, unlike `-u
user:pass` would) -- that file is deleted as soon as the run finishes or
fails. Set these before running:

    PowerShell:  $env:WMT_NEWSCRAWL_USER = "newscrawl"
                 $env:WMT_NEWSCRAWL_PASS = "<password>"
    bash:        export WMT_NEWSCRAWL_USER=newscrawl
                 export WMT_NEWSCRAWL_PASS=<password>

Requires curl on PATH.

---
NOTE ON THIS REVISION (WMTPassage fix):
extraction.WMTPassage only has two fields -- `id` and `text` (bytes). It
carries NO date of its own. The real publication_ts lives on the parent
WMTDoc, and is only recoverable via the sorting_key embedded in the
passage's id ('{sorting_key}_{passage_idx}', see extraction._PASSAGE_ID).
So we now: (1) materialize wmt_docs into a list and build a
sorting_key -> publication_ts lookup BEFORE handing docs to
get_wmt_passages_from_docs (which consumes them once), (2) recover
sorting_key from each passage id via regex (splitting on the trailing
'_{digits}' rather than a plain '_' split, since sorting_key itself may
contain underscores), (3) decode passage.text from bytes to str before
JSON-serializing it, and (4) force prepend_date=False, since with
publication_ts now captured as clean structured metadata, leaving
prepend_date=True would ALSO stamp the date into passage text itself --
duplicating it and leaking a temporal signal into content that a
poisoning experiment shouldn't have baked in as free text.
---
NOTE ON THIS REVISION (disk-exhaustion fix):
The previous version wrote ALL years into one single, ever-growing,
uncompressed streamingqa_relevant_passages.jsonl. On a 20GB Kaggle disk
this ran out of space partway through 2014 (17GB already used by just
2008-2013 -- ~2.5-3M kept passages/year, uncompressed). Two changes:

  1. Output is now ONE GZIP-COMPRESSED SHARD PER YEAR, under
     data/raw/streamingqa_relevant_passages/{year}.jsonl.gz, instead of
     one flat file. JSON text compresses roughly 4-6x, and per-year
     files bound how much any single run needs to hold.
  2. The script is now RESUMABLE: if a year's shard file already exists,
     that year's download+extraction is skipped entirely. Previously the
     output file was opened with mode "w" at the top of __main__, which
     silently TRUNCATED already-extracted years on every rerun -- if you
     pull this revision in in place of the old one, delete the old flat
     streamingqa_relevant_passages.jsonl first (it is now a stale format
     that downstream scripts no longer read), which will also free the
     disk space needed to keep going.

build_streamingqa_pools.py's load_relevant_passages() must be updated to
read this sharded/gzipped directory instead of a single flat file -- see
the paired revision of that script.
---
"""

import datetime
import gzip
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/eval -> src -> repo root
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"

# TODO: point this at wherever third_party/streamingqa
# (google-deepmind/streamingqa) actually lives in your cloned repo.
sys.path.insert(0, str(REPO_ROOT / "third_party" / "streamingqa"))
import extraction  # noqa: E402

# How far beyond the configured candidate_pool.window_days we retain
# passages during extraction, to cover build_streamingqa_pools.py's own
# window-widening fallback (which widens up to window_days * 8 if a
# window is sparse). Must be >= that cap, or the widening fallback has
# nothing to widen INTO, since anything outside this margin was never
# extracted at all.
RETENTION_MARGIN_MULTIPLIER = 8


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# curl/auth helpers (previously imported from the old fetch_wmt_archives.py --
# inlined here since this file now IS fetch_wmt_archives.py)
# ---------------------------------------------------------------------------

def _require_curl() -> str:
    curl_path = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_path:
        raise RuntimeError(
            "curl not found on PATH. Windows 10 1803+ ships curl.exe in "
            "System32 by default -- if it's genuinely missing, install it "
            "or add it to PATH before rerunning."
        )
    return curl_path


def _write_netrc(user: str, password: str, host: str) -> Path:
    """Writes credentials to a temp file curl reads via --netrc-file, so the
    password never appears in the process command line (visible to e.g.
    `tasklist /v` while the download is running) the way `-u user:pass`
    would. Caller is responsible for deleting this file when done.
    """
    fd, path_str = tempfile.mkstemp(prefix="chronoguard_netrc_", text=True)
    path = Path(path_str)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"machine {host}\nlogin {user}\npassword {password}\n")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def _download_with_curl(
    curl_path: str,
    url: str,
    out_path: Path,
    netrc_path: Path,
    max_full_attempts: int = 5,
    retry_per_attempt: int = 3,
) -> None:
    """Resumable download via curl -C - (auto-resume), backed by a .partial
    file. Falls back to a full restart if the server doesn't support Range
    (confirmed exit code 33 on this host for news-docs.2015) instead of
    retrying the same doomed resume request.
    """
    if out_path.exists():
        print(f"  already have {out_path.name}, skipping")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".partial")

    for attempt in range(1, max_full_attempts + 1):
        resume_from = tmp_path.stat().st_size if tmp_path.exists() else 0
        cmd = [
            curl_path,
            "--netrc-file", str(netrc_path),
            "-C", "-",
            "--retry", str(retry_per_attempt),
            "--retry-delay", "5",
            "--retry-all-errors",
            "--fail",
            "--show-error",
            "-o", str(tmp_path),
            url,
        ]

        if resume_from:
            print(f"  downloading {out_path.name} via curl "
                  f"(resuming from {resume_from:,} bytes, full-attempt {attempt}/{max_full_attempts})")
        else:
            print(f"  downloading {out_path.name} via curl "
                  f"(full-attempt {attempt}/{max_full_attempts})")

        result = subprocess.run(cmd)

        if result.returncode == 0:
            tmp_path.rename(out_path)
            return

        if result.returncode == 33:
            print("  server doesn't support resuming this file -- discarding "
                  f"partial ({resume_from:,} bytes) and restarting from 0")
            tmp_path.unlink(missing_ok=True)
            continue

        print(f"  curl exited {result.returncode} after its internal retries; "
              f"{tmp_path.stat().st_size if tmp_path.exists() else 0:,} bytes "
              f"on disk, trying again (full-attempt {attempt + 1}/{max_full_attempts})")
        time.sleep(5)

    raise RuntimeError(
        f"Failed to download {url} after {max_full_attempts} full attempts. "
        f"Partial file kept at {tmp_path} -- rerun this script to keep trying."
    )


def download_sorting_keys(cfg: dict, raw_dir: Path) -> Path:
    # Hosted on storage.googleapis.com (no auth needed).
    url = cfg["evidence_source"]["sorting_keys_url"]
    out_path = raw_dir / "wmt_sorting_key_ids.txt.gz"
    if out_path.exists():
        print(f"  already have {out_path.name}, skipping")
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, out_path)
    return out_path


# ---------------------------------------------------------------------------
# per-year fetch + filtered extraction + cleanup
# ---------------------------------------------------------------------------

def load_sample(raw_dir: Path) -> list[dict]:
    sample_path = raw_dir / "streamingqa_control_sample.jsonl"
    if not sample_path.exists():
        raise FileNotFoundError(
            f"{sample_path} not found -- run save_snapshot_streamingqa.py "
            f"first (this script reads the sample, it doesn't create it)."
        )
    with open(sample_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def compute_retention_windows(sample: list[dict], window_days: int) -> list[tuple]:
    margin = window_days * RETENTION_MARGIN_MULTIPLIER
    windows = []
    for q in sample:
        gold_dt = datetime.datetime.fromtimestamp(
            q["evidence_ts"], tz=datetime.timezone.utc
        )
        lo = gold_dt - datetime.timedelta(days=margin)
        hi = gold_dt + datetime.timedelta(days=margin)
        windows.append((lo, hi))
    return windows


def in_any_window(date: datetime.datetime, windows: list[tuple]) -> bool:
    return any(lo <= date <= hi for lo, hi in windows)


def _extract_sorting_key(passage_id: str) -> str:
    """Recovers the parent WMTDoc's sorting_key from a WMTPassage id of the
    form '{sorting_key}_{passage_idx}' (see extraction._PASSAGE_ID). Splits
    on the trailing digits only, since sorting_key itself may contain '_'
    (it's built via _SORTING_KEY_FIELD_SEPARATOR.join(...), which doesn't
    guarantee '_' is absent from its fields).
    """
    match = re.match(r'^(.*)_(\d+)$', passage_id)
    if not match:
        raise ValueError(f"Unexpected passage id format: {passage_id!r}")
    return match.group(1)


def _passage_timestamp(p, sorting_key_to_ts: dict) -> datetime.datetime:
    """WMTPassage carries no date of its own (only `id` and `text`) -- the
    real publication_ts lives on the parent WMTDoc and must be looked up
    via the sorting_key embedded in the passage id."""
    sorting_key = _extract_sorting_key(p.id)
    ts = sorting_key_to_ts[sorting_key]
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)


def _passage_text(p) -> str:
    text = p["text"] if isinstance(p, dict) else p.text
    if isinstance(text, bytes):
        return text.decode("utf-8", errors="replace")
    return text


def _passage_doc_id(p):
    return p["doc_id"] if isinstance(p, dict) else p.id


def process_year(
    year: int,
    cfg: dict,
    raw_dir: Path,
    shards_dir: Path,
    curl_path: str,
    netrc_path: Path,
    sorting_keys_path: Path,
    windows: list[tuple],
) -> int:
    shard_path = shards_dir / f"{year}.jsonl.gz"
    if shard_path.exists():
        # Resumable: don't re-download or re-extract a year we already have.
        with gzip.open(shard_path, "rt", encoding="utf-8") as f:
            kept = sum(1 for _ in f)
        print(f"[{year}] shard already exists ({kept} passages), skipping")
        return kept

    src = cfg["evidence_source"]
    fname = src["filename_pattern"].format(year=year)
    url = src["base_url"] + fname
    archive_path = raw_dir / "wmt" / fname

    print(f"[{year}] downloading...")
    _download_with_curl(curl_path, url, archive_path, netrc_path)

    print(f"[{year}] deduplicating + extracting...")
    wmt_docs = list(extraction.get_deduplicated_wmt_docs(
        wmt_archive_files=[str(archive_path)],
        deduplicated_sorting_keys_file=str(sorting_keys_path),
    ))
    sorting_key_to_ts = {doc.sorting_key: doc.publication_ts for doc in wmt_docs}

    passages = extraction.get_wmt_passages_from_docs(
        wmt_docs,
        prepend_date=False,  # publication_ts is now captured separately via
                              # sorting_key_to_ts -- leaving this True would
                              # ALSO stamp the date into passage text itself,
                              # duplicating it and leaking a temporal signal
                              # into content that a poisoning experiment
                              # shouldn't have baked in as free text
    )

    # Write to a .tmp path and rename on success, so a crash mid-year never
    # leaves a shard that LOOKS complete (and would be wrongly skipped on
    # the next resumed run) but actually has partial/truncated content.
    tmp_shard_path = shard_path.with_suffix(shard_path.suffix + ".tmp")
    kept = 0
    with gzip.open(tmp_shard_path, "wt", encoding="utf-8") as out_f:
        for p in passages:
            dt = _passage_timestamp(p, sorting_key_to_ts)
            if in_any_window(dt, windows):
                out_f.write(json.dumps({
                    "doc_id": _passage_doc_id(p),
                    "text": _passage_text(p),
                    "timestamp": dt.isoformat(),
                }) + "\n")
                kept += 1
    tmp_shard_path.rename(shard_path)

    print(f"[{year}] kept {kept} passages within the retention margin "
          f"(shard: {shard_path.stat().st_size / 1e6:.1f} MB compressed)")

    # The whole point of the year-by-year design: free the disk before the
    # next (possibly 16GB, for 2017) year starts downloading.
    archive_path.unlink()
    print(f"[{year}] deleted raw archive, freed disk")

    return kept


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    sample = load_sample(raw_dir)
    print(f"Loaded {len(sample)} sampled questions.")

    window_days = cfg["candidate_pool"]["window_days"]
    windows = compute_retention_windows(sample, window_days)
    print(f"Retention margin: +/-{window_days * RETENTION_MARGIN_MULTIPLIER} days "
          f"around each of {len(windows)} gold dates.")

    curl_path = _require_curl()
    user = os.environ.get("WMT_NEWSCRAWL_USER")
    password = os.environ.get("WMT_NEWSCRAWL_PASS")
    if not user or not password:
        raise RuntimeError(
            "Set WMT_NEWSCRAWL_USER and WMT_NEWSCRAWL_PASS environment "
            "variables before running."
        )
    netrc_path = _write_netrc(user, password, host="data.statmt.org")

    sorting_keys_path = download_sorting_keys(cfg, raw_dir)

    shards_dir = raw_dir / "streamingqa_relevant_passages"
    shards_dir.mkdir(parents=True, exist_ok=True)

    try:
        total_kept = 0
        for year in cfg["evidence_source"]["years"]:
            total_kept += process_year(
                year, cfg, raw_dir, shards_dir, curl_path, netrc_path,
                sorting_keys_path, windows,
            )
    finally:
        netrc_path.unlink(missing_ok=True)

    print(f"Done. {total_kept} relevant passages written across "
          f"{len(cfg['evidence_source']['years'])} shard(s) in {shards_dir}")
    print("Next: run build_streamingqa_pools.py.")