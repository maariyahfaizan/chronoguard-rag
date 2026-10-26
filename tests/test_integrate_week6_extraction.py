"""End-to-end synthetic checks for Week 6 year-specific extraction."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.eval.build_week6_archive_coverage import build_coverage
from src.eval.integrate_week6_extraction import (
    extraction_windows_for_year,
    extract_archive_year,
)
from src.eval.extract_week6_evidence import read_shard

UTC = dt.timezone.utc


def ts(iso):
    return dt.datetime.fromisoformat(iso).timestamp()


def row(qid, start, end, evidence_id="20201201000000000000"):
    return {
        "qa_id": qid,
        "recent_or_past": "recent",
        "reserve_rank": 1,
        "evidence_id": evidence_id,
        "window_start": start,
        "window_end": end,
    }


def passages(docs, prepend_date=False):
    assert prepend_date is False
    for doc in docs:
        yield SimpleNamespace(id=doc.id + "__0", text=doc.text.encode("utf-8"))


class TestWeek6ExtractionIntegration(unittest.TestCase):
    def setUp(self):
        self.windows = [
            row("q1", "2020-12-20T00:00:00+00:00",
                "2021-01-10T00:00:00+00:00"),
        ]
        self.coverage = build_coverage(self.windows, archive_years=[2020])

    def test_2020_year_end_is_inclusive_at_last_microsecond(self):
        intervals = extraction_windows_for_year(self.windows, self.coverage, 2020)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(
            intervals[0][1],
            dt.datetime(2020, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        )

    def test_2021_is_excluded_by_configuration(self):
        self.assertEqual(
            extraction_windows_for_year(self.windows, self.coverage, 2021), []
        )

    def test_synthetic_extraction_filters_and_preserves_ids(self):
        docs = [
            SimpleNamespace(id="before", text="old", publication_ts=ts("2020-12-19T23:59:59+00:00")),
            SimpleNamespace(id="start", text="valid start", publication_ts=ts("2020-12-20T00:00:00+00:00")),
            SimpleNamespace(id="inside", text="valid middle", publication_ts=ts("2020-12-25T12:00:00+00:00")),
            SimpleNamespace(id="last", text="valid end", publication_ts=ts("2020-12-31T23:59:59+00:00")),
            SimpleNamespace(id="nextyear", text="wrong year", publication_ts=ts("2021-01-01T00:00:00+00:00")),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "year2020.jsonl.gz"
            count = extract_archive_year(
                year=2020, docs=iter(docs),
                windows=self.windows, coverage=self.coverage,
                output_path=output, passage_generator=passages,
            )
            self.assertEqual(count, 3)
            records = read_shard(output)
            self.assertEqual([r["doc_id"] for r in records],
                             ["start__0", "inside__0", "last__0"])
            self.assertEqual(records[0]["text"], "valid start")
            self.assertEqual(records[0]["timestamp"], "2020-12-20T00:00:00+00:00")

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "year2020.jsonl.gz"
            output.write_bytes(b"existing")
            with self.assertRaises(FileExistsError):
                extract_archive_year(
                    year=2020, docs=iter([]),
                    windows=self.windows, coverage=self.coverage,
                    output_path=output, passage_generator=passages,
                )
            self.assertEqual(output.read_bytes(), b"existing")

    def test_unconfigured_year_does_not_consume_docs_or_create_output(self):
        def forbidden_docs():
            raise AssertionError("Documents should not be read")
            yield

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "year2021.jsonl.gz"
            count = extract_archive_year(
                year=2021, docs=forbidden_docs(),
                windows=self.windows, coverage=self.coverage,
                output_path=output, passage_generator=passages,
            )
            self.assertEqual(count, 0)
            self.assertFalse(output.exists())

    def test_original_manifest_is_not_mutated(self):
        before = [dict(r) for r in self.windows]
        _ = extraction_windows_for_year(self.windows, self.coverage, 2020)
        self.assertEqual(self.windows, before)


if __name__ == "__main__":
    unittest.main()
