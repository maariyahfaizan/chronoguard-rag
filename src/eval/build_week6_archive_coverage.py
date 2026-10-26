"""Compute configured WMT archive-year coverage for Week 6 windows."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

CONFIG_PATH = Path("configs/streamingqa_config.yaml")


def load_archive_years(config_path=CONFIG_PATH):
    """Load the exact configured WMT archive years."""
    with Path(config_path).open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    years = config["evidence_source"]["years"]
    if not isinstance(years, list) or not years or any(type(y) is not int for y in years):
        raise ValueError("Invalid configured archive years")
    if len(years) != len(set(years)):
        raise ValueError("Duplicate configured archive years")
    if any(y < 1 or y > 9999 for y in years):
        raise ValueError("Archive year outside supported range")
    return sorted(years)


def _parse_utc(value, qid):
    try:
        timestamp = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timestamp for {qid}: {value}") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ValueError(f"Timestamp must be UTC for {qid}")
    return timestamp


def build_coverage(windows, archive_years=None):
    """Return coverage records without modifying original retention windows."""
    if archive_years is None:
        archive_years = load_archive_years()
    archive_years = set(archive_years)
    result = []
    seen_ids = set()

    for row in windows:
        qid = row["qa_id"]
        if qid in seen_ids:
            raise ValueError(f"Duplicate window qa_id: {qid}")
        seen_ids.add(qid)
        start = _parse_utc(row["window_start"], qid)
        end = _parse_utc(row["window_end"], qid)
        if start > end:
            raise ValueError(f"Window start after end for {qid}")

        requested_years = list(range(start.year, end.year + 1))
        available_years = [year for year in requested_years if year in archive_years]
        unavailable_years = [year for year in requested_years if year not in archive_years]

        evidence_id = row["evidence_id"]
        if not isinstance(evidence_id, str) or len(evidence_id) < 4 or not evidence_id[:4].isdigit():
            raise ValueError(f"Invalid evidence_id year for {qid}")
        gold_year = int(evidence_id[:4])

        result.append({
            "qa_id": qid,
            "recent_or_past": row["recent_or_past"],
            "reserve_rank": row["reserve_rank"],
            "gold_year": gold_year,
            "requested_years": requested_years,
            "configured_years": available_years,
            "outside_configured_range": unavailable_years,
            "gold_year_in_configured_range": gold_year in archive_years,
        })

    return result


def windows_for_archive_year(windows, coverage, year):
    """Return UTC intervals for year-specific extraction planning.

    A clipped calendar-year end is exclusive; an original retention-window
    end remains inclusive. Reconcile these with the existing extractor's
    inclusive-end comparison before integration.
    """
    if type(year) is not int or not 1 <= year <= 9999:
        raise ValueError("Invalid archive year")
    if len(windows) != len(coverage):
        raise ValueError("Window and coverage record counts differ")

    coverage_by_id = {}
    for row in coverage:
        qid = row["qa_id"]
        if qid in coverage_by_id:
            raise ValueError(f"Duplicate qa_id in coverage manifest: {qid}")
        coverage_by_id[qid] = row

    seen_windows = set()
    result = []
    year_start = datetime(year, 1, 1, tzinfo=timezone.utc)
    next_year_start = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if year < 9999 else None
    )

    for row in windows:
        qid = row["qa_id"]
        if qid in seen_windows:
            raise ValueError(f"Duplicate qa_id in windows: {qid}")
        seen_windows.add(qid)
        if qid not in coverage_by_id:
            raise ValueError(f"Missing coverage for {qid}")
        info = coverage_by_id[qid]
        if year not in info["configured_years"]:
            continue

        start = _parse_utc(row["window_start"], qid)
        end = _parse_utc(row["window_end"], qid)
        if start > end:
            raise ValueError(f"Window start after end for {qid}")

        clipped_start = max(start, year_start)
        clipped_end = min(end, next_year_start) if next_year_start else end
        if clipped_start < clipped_end:
            result.append((clipped_start, clipped_end))

    if seen_windows != set(coverage_by_id):
        raise ValueError("Coverage contains qa_id absent from windows")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)

    with args.windows.open(encoding="utf-8") as f:
        windows = [json.loads(line) for line in f if line.strip()]
    archive_years = load_archive_years()
    coverage = build_coverage(windows, archive_years=archive_years)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        for row in coverage:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Coverage records: {len(coverage)}")
    print("Configured WMT years:", archive_years)
    print("Archive years to inspect:", sorted({
        year for row in coverage for year in row["configured_years"]
    }))
    print("Questions with windows outside configured range:",
          sum(bool(row["outside_configured_range"]) for row in coverage))
    print("Questions with gold year outside configured range:",
          sum(not row["gold_year_in_configured_range"] for row in coverage))


if __name__ == "__main__":
    main()
