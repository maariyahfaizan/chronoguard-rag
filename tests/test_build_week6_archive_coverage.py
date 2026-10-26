"""Regression tests for Week 6 WMT archive coverage and UTC year boundaries."""

import tempfile
import unittest
from pathlib import Path

from src.eval.build_week6_archive_coverage import (
    build_coverage,
    load_archive_years,
    windows_for_archive_year,
)


def make_window(qid="test-001", start="2020-10-06T00:00:00+00:00",
                end="2021-01-26T00:00:00+00:00",
                evidence_id="20201201000000000000"):
    return {
        "qa_id": qid,
        "recent_or_past": "recent",
        "reserve_rank": 1,
        "evidence_id": evidence_id,
        "window_start": start,
        "window_end": end,
    }


class TestArchiveCoverage(unittest.TestCase):
    def test_window_crossing_2020_boundary(self):
        result = build_coverage([make_window()], archive_years=[2020])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["requested_years"], [2020, 2021])
        self.assertEqual(result[0]["configured_years"], [2020])
        self.assertEqual(result[0]["outside_configured_range"], [2021])
        self.assertTrue(result[0]["gold_year_in_configured_range"])

    def test_gold_year_outside_configured_range(self):
        row = make_window(evidence_id="20210101000000000000")
        result = build_coverage([row], archive_years=[2020])
        self.assertFalse(result[0]["gold_year_in_configured_range"])

    def test_windows_for_archive_year_clips_boundaries(self):
        row = make_window(start="2020-12-01T00:00:00+00:00",
                          end="2021-01-15T00:00:00+00:00")
        coverage = build_coverage([row], archive_years=[2020])
        result = windows_for_archive_year([row], coverage, 2020)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].isoformat(), "2020-12-01T00:00:00+00:00")
        self.assertEqual(result[0][1].isoformat(), "2021-01-01T00:00:00+00:00")
        self.assertEqual(windows_for_archive_year([row], coverage, 2021), [])

    def test_windows_for_archive_year_starts_at_january_first(self):
        row = make_window(start="2019-12-20T12:00:00+00:00",
                          end="2020-01-12T12:00:00+00:00",
                          evidence_id="20191225000000000000")
        coverage = build_coverage([row], archive_years=[2019, 2020])
        result = windows_for_archive_year([row], coverage, 2020)
        self.assertEqual(result[0][0].isoformat(), "2020-01-01T00:00:00+00:00")
        self.assertEqual(result[0][1].isoformat(), "2020-01-12T12:00:00+00:00")

    def test_excludes_unconfigured_archive_year(self):
        row = make_window()
        coverage = build_coverage([row], archive_years=[2020])
        self.assertEqual(windows_for_archive_year([row], coverage, 2021), [])

    def test_missing_coverage_is_rejected(self):
        row = make_window()
        with self.assertRaisesRegex(ValueError, "counts differ"):
            windows_for_archive_year([row], [], 2020)

    def test_mismatched_coverage_id_is_rejected(self):
        row = make_window()
        other = make_window(qid="other")
        coverage = build_coverage([other], archive_years=[2020])
        with self.assertRaisesRegex(ValueError, "Missing coverage"):
            windows_for_archive_year([row], coverage, 2020)

    def test_duplicate_window_ids_are_rejected(self):
        row = make_window()
        with self.assertRaisesRegex(ValueError, "Duplicate window qa_id"):
            build_coverage([row, row], archive_years=[2020])

    def test_duplicate_coverage_ids_are_rejected(self):
        row = make_window()
        coverage = build_coverage([row], archive_years=[2020])
        with self.assertRaisesRegex(ValueError, "Duplicate qa_id"):
            windows_for_archive_year([row, row], coverage + coverage, 2020)

    def test_rejects_non_utc_and_naive_times(self):
        for start in ["2020-10-06T00:00:00", "2020-10-06T01:00:00+01:00"]:
            with self.subTest(start=start):
                with self.assertRaisesRegex(ValueError, "UTC"):
                    build_coverage([make_window(start=start)], archive_years=[2020])

    def test_rejects_reversed_window(self):
        row = make_window(start="2021-01-27T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "start after end"):
            build_coverage([row], archive_years=[2020])

    def test_noncontiguous_configured_years(self):
        row = make_window(start="2018-12-01T00:00:00+00:00",
                          end="2020-01-01T00:00:00+00:00",
                          evidence_id="20190101000000000000")
        result = build_coverage([row], archive_years=[2018, 2020])
        self.assertEqual(result[0]["configured_years"], [2018, 2020])
        self.assertEqual(result[0]["outside_configured_range"], [2019])
        self.assertFalse(result[0]["gold_year_in_configured_range"])

    def test_config_loader_reads_exact_years(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.yaml"
            config.write_text("evidence_source:\\n  years: [2020, 2018]\\n".replace("\\n", "\n"), encoding="utf-8")
            self.assertEqual(load_archive_years(config), [2018, 2020])

    def test_config_loader_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.yaml"
            config.write_text("evidence_source:\n  years: [2020, 2020]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_archive_years(config)


if __name__ == "__main__":
    unittest.main()
