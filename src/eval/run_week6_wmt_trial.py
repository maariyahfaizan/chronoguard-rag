"""Week 6 single-year WMT extraction trial. No downloads, no Week 4 writes."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from src.eval.build_week6_archive_coverage import (
    build_coverage, load_archive_years,
)
from src.eval.integrate_week6_extraction import extract_archive_year


def read_jsonl(path):
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_official_extraction(source_path):
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"DeepMind extraction.py missing: {source_path}")
    spec = importlib.util.spec_from_file_location(
        "week6_deepmind_extraction", source_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return module


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_trial(
    *, year, archive, dedup_keys, windows_path, output_path,
    deepmind_source=Path("third_party/streamingqa/extraction.py"),
    config_path=Path("configs/streamingqa_config.yaml"),
    dry_run=False,
):
    archive = Path(archive)
    dedup_keys = Path(dedup_keys)
    windows_path = Path(windows_path)
    output_path = Path(output_path)

    years = load_archive_years(config_path)
    if year not in years:
        raise ValueError(f"Archive year {year} not in configured years")
    if not windows_path.is_file():
        raise FileNotFoundError(f"Windows manifest missing: {windows_path}")
    if output_path.exists():
        raise FileExistsError(f"Output exists: {output_path}")

    windows = read_jsonl(windows_path)
    coverage = build_coverage(windows, archive_years=years)
    applicable = [
        row["qa_id"] for row in coverage if year in row["configured_years"]
    ]
    plan = {
        "year": year,
        "questions_intersecting_year": len(applicable),
        "qa_ids": applicable,
        "archive": str(archive),
        "dedup_keys": str(dedup_keys),
        "output": str(output_path),
        "windows_sha256": sha256(windows_path),
        "configured_years": years,
    }
    if dry_run:
        return plan

    if not applicable:
        raise ValueError(f"No retention windows intersect archive year {year}")
    if not archive.is_file():
        raise FileNotFoundError(f"WMT archive missing: {archive}")
    if not dedup_keys.is_file():
        raise FileNotFoundError(f"Deduplication keys missing: {dedup_keys}")

    official = load_official_extraction(deepmind_source)
    docs = official.get_deduplicated_wmt_docs(
        [str(archive)], str(dedup_keys)
    )
    count = extract_archive_year(
        year=year,
        docs=docs,
        windows=windows,
        coverage=coverage,
        output_path=output_path,
        passage_generator=official.get_wmt_passages_from_docs,
    )
    plan["passages_written"] = count
    plan["output_sha256"] = sha256(output_path)
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--dedup-keys", type=Path, required=True)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--deepmind-source", type=Path,
        default=Path("third_party/streamingqa/extraction.py"),
    )
    parser.add_argument(
        "--config", type=Path,
        default=Path("configs/streamingqa_config.yaml"),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = run_trial(
        year=args.year, archive=args.archive, dedup_keys=args.dedup_keys,
        windows_path=args.windows, output_path=args.out,
        deepmind_source=args.deepmind_source, config_path=args.config,
        dry_run=args.dry_run,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
