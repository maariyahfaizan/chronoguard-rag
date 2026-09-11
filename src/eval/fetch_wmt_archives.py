"""
Weeks 3-4 | StreamingQA Step 2a: fetch WMT News Crawl archives.

Downloads only the years the seeded n=100 StreamingQA sample's evidence_ts
values actually span (2008-2020, confirmed by save_snapshot_streamingqa.py),
plus the deduplicated sorting-key file, from a SINGLE confirmed source:

    https://data.statmt.org/news-crawl/doc/en/news-docs.<year>.en.filtered.gz

NOTE on source choice: data.statmt.org/news-crawl/doc/ also has a
doc/wmt19/en-doc/ directory covering 2007-2018, but its files are a
DIFFERENT (earlier, smaller) crawl vintage of the same years -- e.g. 2008 is
610M there vs 1.6G in doc/en/. We deliberately source every year from doc/en/
only, so no year is silently built from a different underlying corpus than
its neighbors. See configs/streamingqa_config.yaml for the frozen year list.

AUTH: doc/en/ is login-gated (user: newscrawl). Credentials are read from
environment variables and written to a temporary --netrc-file for curl (so
the password never appears in the process command line, unlike `-u
user:pass` would) -- that file is deleted as soon as the run finishes or
fails. Set these before running:

    PowerShell:  $env:WMT_NEWSCRAWL_USER = "newscrawl"
                 $env:WMT_NEWSCRAWL_PASS = "<password>"
    bash:        export WMT_NEWSCRAWL_USER=newscrawl
                 export WMT_NEWSCRAWL_PASS=<password>

Requires curl on PATH (ships with Windows 10 1803+ by default).

Downloads are resumable: each file downloads to a .partial path first via
`curl -C -` (auto-resume) with --retry-all-errors so a dropped connection
(including local interference like AV/VPN killing long-lived connections --
if you keep seeing WinError 10053, that's the next thing to check) retries
automatically; only renamed to its final name on a clean exit.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/eval -> src -> repo root
CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_config.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    # Best-effort lock-down; Windows ACLs aren't fully controlled by chmod,
    # but this at least clears world/group read bits where it does apply.
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
    file so a run that dies mid-download never leaves something at out_path
    that a later `if out_path.exists(): skip` check would mistake for done.

    Handles two distinct failure modes differently, since conflating them
    is what caused the previous version to retry a doomed request 5 times:
      - mid-transfer connection drop -> curl's own --retry handles this
        within one attempt (the partial bytes are still good, resume works)
      - server doesn't support Range at all (curl exit 33, confirmed on
        this host for news-docs.2015) -> resuming can NEVER succeed, so we
        discard the partial and restart from byte 0 instead of retrying
        the same doomed resume request.
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
            "-C", "-",                 # auto-resume from tmp_path's current size (no-op if 0)
            "--retry", str(retry_per_attempt),
            "--retry-delay", "5",
            "--retry-all-errors",      # retry on connection resets too, not just 5xx/timeouts
            "--fail",                  # non-zero exit on HTTP errors instead of saving an error page
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

        # Not capturing stdout/stderr here on purpose: curl's live progress
        # meter (% complete, speed, ETA) prints straight to your terminal,
        # which matters on files this large -- capturing it would leave you
        # staring at a blank screen for the better part of an hour on 2017's
        # 16GB archive with no way to tell if it's stalled.
        result = subprocess.run(cmd)

        if result.returncode == 0:
            tmp_path.rename(out_path)
            return

        if result.returncode == 33:
            # Confirmed: this server does not support byte-range requests
            # for at least some of these files. Resuming can't work here --
            # discard the partial and let the next loop iteration start a
            # clean full download instead of repeating the same failure.
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
        f"Partial file kept at {tmp_path} -- rerun this script to keep trying "
        f"(if the server doesn't support resume, each attempt restarts from 0, "
        f"so a flaky connection may need several runs to get lucky with an "
        f"uninterrupted pass)."
    )


def download_year_archives(cfg: dict, raw_dir: Path, parallelism: int = 4) -> list[Path]:
    """Downloads all configured years, up to `parallelism` at once.

    Added after we measured ~27.5 KB/s on a single connection to
    data.statmt.org -- at that rate 50GB across 13 years is ~3 weeks, not
    workable. This is almost certainly server-side per-connection
    throttling (small academic mirror, not a CDN) rather than a local
    bandwidth limit, so running several downloads concurrently can multiply
    effective throughput even though any single file's speed stays capped.
    If total throughput does NOT increase with parallelism > 1, the limit
    is per-IP instead and this won't help -- at that point the fix is
    running the fetch from a different network (e.g. a Kaggle notebook)
    rather than more concurrency here.
    """
    curl_path = _require_curl()
    src = cfg["evidence_source"]

    user = os.environ.get("WMT_NEWSCRAWL_USER")
    password = os.environ.get("WMT_NEWSCRAWL_PASS")
    if not user or not password:
        raise RuntimeError(
            "Set WMT_NEWSCRAWL_USER and WMT_NEWSCRAWL_PASS environment "
            "variables before running (data.statmt.org/news-crawl/doc/ is "
            "credential-gated)."
        )
    netrc_path = _write_netrc(user, password, host="data.statmt.org")

    jobs = []
    for year in src["years"]:
        fname = src["filename_pattern"].format(year=year)
        url = src["base_url"] + fname
        out_path = raw_dir / "wmt" / fname
        jobs.append((url, out_path))

    paths = [out for _, out in jobs]
    try:
        with ThreadPoolExecutor(max_workers=parallelism) as pool:
            futures = {
                pool.submit(_download_with_curl, curl_path, url, out_path, netrc_path): out_path
                for url, out_path in jobs
            }
            for future in as_completed(futures):
                out_path = futures[future]
                future.result()  # re-raises if that year's download ultimately failed
                print(f"  finished {out_path.name}")
    finally:
        netrc_path.unlink(missing_ok=True)  # never leave the password file behind

    return paths


def download_sorting_keys(cfg: dict, raw_dir: Path) -> Path:
    # This file is hosted on storage.googleapis.com (no auth needed) --
    # reuse the plain urlretrieve path from save_snapshot_streamingqa.py's
    # convention rather than the authed opener.
    url = cfg["evidence_source"]["sorting_keys_url"]
    out_path = raw_dir / "wmt_sorting_key_ids.txt.gz"
    if out_path.exists():
        print(f"  already have {out_path.name}, skipping")
        return out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, out_path)
    return out_path


if __name__ == "__main__":
    cfg = load_config()
    raw_dir = REPO_ROOT / cfg["output"]["raw_dir"]

    # Optional: python fetch_wmt_archives.py 6   -> 6 years downloading at once.
    # Default 4 is a reasonable starting guess; push it higher if throughput
    # keeps scaling, back off if individual downloads start timing out more.
    parallelism = int(sys.argv[1]) if len(sys.argv) > 1 else 4

    print(f"Fetching sorting keys...")
    sorting_keys_path = download_sorting_keys(cfg, raw_dir)

    print(f"Fetching {len(cfg['evidence_source']['years'])} WMT archive years "
          f"from {cfg['evidence_source']['base_url']} ({parallelism} at a time)")
    archive_paths = download_year_archives(cfg, raw_dir, parallelism=parallelism)

    print(f"Done. {len(archive_paths)} archives + sorting keys in {raw_dir}")