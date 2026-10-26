"""Week 6 synthetic-safe archive-year extraction adapter.

This module does not download archives or modify frozen artifacts.
It invokes the existing bounded-memory extractor using only UTC windows
associated with a configured archive year.

Important: year-clipped intervals use an exclusive upper bound at Jan 1,
whereas extract_documents accepts inclusive endpoints. We avoid changing
the original extractor by translating the clipped upper bound to the
previous representable microsecond only when it is a year boundary.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from src.eval.build_week6_archive_coverage import windows_for_archive_year
from src.eval.extract_week6_evidence import extract_documents

UTC = dt.timezone.utc
MICROSECOND = dt.timedelta(microseconds=1)


def extraction_windows_for_year(windows, coverage, year):
    """Return UTC inclusive intervals safe for the existing extractor.

    An original retention window ending exactly at a year boundary is
    inclusive, but that instant belongs to the next year's archive and
    must not be extracted from the preceding year.
    """
    clipped = windows_for_archive_year(windows, coverage, year)
    next_year_start = dt.datetime(year + 1, 1, 1, tzinfo=UTC) if year < 9999 else None
    inclusive = []
    for start, end in clipped:
        if next_year_start is not None and end == next_year_start:
            end -= MICROSECOND
        if start <= end:
            inclusive.append((start, end))
    return inclusive


def extract_archive_year(
    *,
    year: int,
    docs,
    windows: list[dict],
    coverage: list[dict],
    output_path: Path,
    passage_generator,
):
    """Extract relevant passages from a caller-supplied stream of WMT docs.

    Archive reading and downloads are deliberately outside this adapter.
    Does not create empty output files for years without windows.
    """
    intervals = extraction_windows_for_year(windows, coverage, year)
    if not intervals:
        return 0
    return extract_documents(
        docs=docs,
        windows=intervals,
        output_path=Path(output_path),
        passage_generator=passage_generator,
    )
