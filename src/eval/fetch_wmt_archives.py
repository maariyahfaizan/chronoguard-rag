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
"""

import datetime
import json
import os
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
        gold_dt = datetime.datetime.utcfromtimestamp(q["evidence_ts"])
        lo = gold_dt - datetime.timedelta(days=margin)
        hi = gold_dt + datetime.timedelta(days=margin)
        windows.append((lo, hi))
    return windows


def in_any_window(date: datetime.datetime, windows: list[tuple]) -> bool:
    return any(lo <= date <= hi for lo, hi in windows)


def _passage_date(p) -> datetime.datetime:
    raw = p["date"] if isinstance(p, dict) else p.date
    if isinstance(raw, datetime.datetime):
        return raw
    return datetime.datetime.fromisoformat(raw)


def _passage_text(p) -> str:
    return p["text"] if isinstance(p, dict) else p.text


def _passage_evidence_id(p):
    return p["evidence_id"] if isinstance(p, dict) else p.evidence_id


def process_year(
    year: int,
    cfg: dict,
    raw_dir: Path,
    curl_path: str,
    netrc_path: Path,
    sorting_keys_path: Path,
    windows: list[tuple],
    out_f,
) -> int:
    src = cfg["evidence_source"]
    fname = src["filename_pattern"].format(year=year)
    url = src["base_url"] + fname
    archive_path = raw_dir / "wmt" / fname

    print(f"[{year}] downloading...")
    _download_with_curl(curl_path, url, archive_path, netrc_path)

    print(f"[{year}] deduplicating + extracting...")
    wmt_docs = extraction.get_deduplicated_wmt_docs(
        wmt_archive_files=[str(archive_path)],
        deduplicated_sorting_keys_file=str(sorting_keys_path),
    )
    passages = extraction.get_wmt_passages_from_docs(
        wmt_docs, prepend_date=cfg["candidate_pool"]["prepend_date"]
    )

    kept = 0
    for p in passages:
        d = _passage_date(p)
        if in_any_window(d, windows):
            out_f.write(json.dumps({
                "doc_id": _passage_evidence_id(p),
                "text": _passage_text(p),
                "timestamp": d.isoformat(),
            }) + "\n")
            kept += 1

    print(f"[{year}] kept {kept} passages within the retention margin")

    # The whole point of this rewrite: free the disk before the next
    # (possibly 16GB, for 2017) year starts downloading.
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

    relevant_path = raw_dir / "streamingqa_relevant_passages.jsonl"
    relevant_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        total_kept = 0
        with open(relevant_path, "w", encoding="utf-8") as out_f:
            for year in cfg["evidence_source"]["years"]:
                total_kept += process_year(
                    year, cfg, raw_dir, curl_path, netrc_path,
                    sorting_keys_path, windows, out_f,
                )
    finally:
        netrc_path.unlink(missing_ok=True)

    print(f"Done. {total_kept} relevant passages written to {relevant_path}")
    print("Next: run build_streamingqa_pools.py.")