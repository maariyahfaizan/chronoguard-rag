"""Kaggle-friendly, year-by-year Week 6 WMT evidence streaming.

Never writes raw WMT archives, never modifies Week 4 artifacts, and only
publishes a year shard after both extraction AND curl exit successfully.
Run from the repository root: python -m src.eval.fetch_week6_wmt_evidence ...
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import yaml

from src.eval.build_week6_archive_coverage import build_coverage, load_archive_years
from src.eval.integrate_week6_extraction import extract_archive_year

OFFICIAL_KEYS_MD5 = "3356d7e38e43b7bf4338e2003ab92f36"


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_windows(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def download_keys(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if digest(path, "md5") != OFFICIAL_KEYS_MD5:
            raise ValueError("Existing sorting keys checksum mismatch; refusing to use")
        return
    temp = path.with_name(path.name + ".partial")
    if temp.exists():
        temp.unlink()  # Incomplete previous download, never trusted
    try:
        with urlopen(url, timeout=90) as source, temp.open("xb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        if digest(temp, "md5") != OFFICIAL_KEYS_MD5:
            raise ValueError("Downloaded sorting keys checksum mismatch")
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def make_netrc(username, password, host):
    if not username or not password:
        raise RuntimeError("Set WMT_NEWSCRAWL_USER and WMT_NEWSCRAWL_PASS")
    if any(c in username + password for c in "\r\n"):
        raise ValueError("Invalid newline in credentials")
    fd, name = tempfile.mkstemp(prefix="week6_netrc_")
    path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f'machine {host}\nlogin {username}\npassword {password}\n')
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def official_module(repo_root):
    path = Path(repo_root) / "third_party" / "streamingqa"
    if not (path / "extraction.py").is_file():
        raise FileNotFoundError(f"Missing official DeepMind parser: {path / 'extraction.py'}")
    sys.path.insert(0, str(path))
    return importlib.import_module("extraction")


def year_urls(cfg, year):
    source = cfg["evidence_source"]
    return source["base_url"] + source["filename_pattern"].format(year=year)


def run_year(*, year, windows, coverage, output_dir, config, keys_path,
             netrc_path, official, curl="curl", max_attempts=2):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    final = output_dir / f"{year}.jsonl.gz"
    audit = output_dir / f"{year}.audit.json"
    if final.exists() or audit.exists():
        raise FileExistsError(f"Year {year} already has output or audit; inspect before rerun")
    if year not in {y for row in coverage for y in row["configured_years"]}:
        raise ValueError(f"Year {year} has no eligible retention windows")
    url = year_urls(config, year)
    last_error = None
    for attempt in range(1, max_attempts + 1):
        stage = output_dir / f".{year}.attempt{attempt}.jsonl.gz"
        stage_audit = output_dir / f".{year}.audit.json.tmp"
        if stage.exists() or stage_audit.exists():
            raise FileExistsError(f"Stale staging file: {stage} or {stage_audit}")
        proc = None
        try:
            proc = subprocess.Popen([
                curl, "--fail", "--location", "--silent", "--show-error",
                "--retry", "0", "--netrc-file", str(netrc_path), url,
            ], stdout=subprocess.PIPE)
            if proc.stdout is None:
                raise RuntimeError("curl stdout pipe unavailable")
            docs = official.get_deduplicated_wmt_docs(
                wmt_archive_files=[proc.stdout],
                deduplicated_sorting_keys_file=str(keys_path),
            )
            count = extract_archive_year(
                year=year, docs=docs, windows=windows, coverage=coverage,
                output_path=stage,
                passage_generator=official.get_wmt_passages_from_docs,
            )
            proc.stdout.close()
            code = proc.wait()
            if code != 0:
                raise RuntimeError(f"curl exited with status {code}")
            record = {
                "year": year, "status": "complete", "passages": count,
                "archive_url": url, "windows_sha256": config["_windows_sha256"],
                "sorting_keys_md5": OFFICIAL_KEYS_MD5,
                "deepmind_extraction_sha256": config["_deepmind_sha256"],
                "output_sha256": digest(stage),
                "attempt": attempt, "prepend_date": False,
                "parser": "DeepMind StreamingQA get_deduplicated_wmt_docs/get_wmt_passages_from_docs",
            }
            with stage_audit.open("x", encoding="utf-8") as f:
                json.dump(record, f, indent=2)
                f.write("\n")
            # Publication occurs only AFTER verified successful curl exit.
            os.link(stage, final)
            os.link(stage_audit, audit)
            return record
        except Exception as exc:
            last_error = exc
            print(f"[{year}] attempt {attempt}/{max_attempts} failed: {exc}", file=sys.stderr)
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                if proc.stdout is not None:
                    proc.stdout.close()
                proc.wait()
            stage.unlink(missing_ok=True)
            stage_audit.unlink(missing_ok=True)
        if final.exists() or audit.exists():
            raise RuntimeError("Partial publication detected; inspect output manually")
    raise RuntimeError(f"Year {year} failed after {max_attempts} attempts") from last_error


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--windows", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=Path("results/week6_wmt_shards"))
    p.add_argument("--config", type=Path, default=Path("configs/streamingqa_config.yaml"))
    p.add_argument("--keys", type=Path, default=Path("data/raw/wmt_sorting_key_ids.txt.gz"))
    p.add_argument("--years", type=int, nargs="+")
    p.add_argument("--max-attempts", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.max_attempts < 1:
        p.error("--max-attempts must be positive")
    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    configured = load_archive_years(args.config)
    windows = read_windows(args.windows)
    coverage = build_coverage(windows, archive_years=configured)
    required = sorted({y for row in coverage for y in row["configured_years"]})
    years = args.years if args.years is not None else required
    if len(years) != len(set(years)) or any(y not in required for y in years):
        p.error(f"Years must be unique and drawn from required years {required}")
    print("Required years:", required, flush=True)
    print("Selected years:", years, flush=True)
    print("Windows SHA256:", digest(args.windows), flush=True)
    if args.dry_run:
        return
    if not shutil.which("curl"):
        raise RuntimeError("curl executable not found")
    repo = Path(__file__).resolve().parents[2]
    official = official_module(repo)
    cfg["_deepmind_sha256"] = digest(repo / "third_party/streamingqa/extraction.py")
    cfg["_windows_sha256"] = digest(args.windows)
    download_keys(cfg["evidence_source"]["sorting_keys_url"], args.keys)
    host = urlparse(cfg["evidence_source"]["base_url"]).hostname
    if not host:
        raise ValueError("Invalid archive base URL")
    netrc = make_netrc(os.getenv("WMT_NEWSCRAWL_USER"), os.getenv("WMT_NEWSCRAWL_PASS"), host)
    try:
        for year in years:
            print(f"Starting {year}", flush=True)
            report = run_year(year=year, windows=windows, coverage=coverage,
                              output_dir=args.out_dir, config=cfg, keys_path=args.keys,
                              netrc_path=netrc, official=official,
                              max_attempts=args.max_attempts)
            print(json.dumps(report, indent=2), flush=True)
    finally:
        netrc.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
