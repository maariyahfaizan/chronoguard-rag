"""Offline unit tests for the Week 6 WMT trial entrypoint."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.eval.run_week6_wmt_trial import run_trial


class TestWMTTrial(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "config.yaml"
        self.config.write_text(
            "evidence_source:\n  years: [2019, 2020]\n",
            encoding="utf-8",
        )
        self.windows = self.root / "windows.jsonl"
        self.windows.write_text(json.dumps({
            "qa_id": "q1",
            "recent_or_past": "recent",
            "reserve_rank": 1,
            "evidence_id": "20201201000000000000",
            "window_start": "2020-12-01T00:00:00+00:00",
            "window_end": "2021-01-20T00:00:00+00:00",
        }) + "\n", encoding="utf-8")
        self.archive = self.root / "archive.gz"
        self.dedup = self.root / "keys.gz"
        self.out = self.root / "out.jsonl.gz"

    def call(self, **changes):
        args = {
            "year": 2020,
            "archive": self.archive,
            "dedup_keys": self.dedup,
            "windows_path": self.windows,
            "output_path": self.out,
            "config_path": self.config,
        }
        args.update(changes)
        return run_trial(**args)

    def test_dry_run_does_not_require_archives(self):
        report = self.call(dry_run=True)
        self.assertEqual(report["questions_intersecting_year"], 1)
        self.assertEqual(report["qa_ids"], ["q1"])
        self.assertFalse(self.out.exists())

    def test_dry_run_does_not_modify_windows(self):
        before = self.windows.read_bytes()
        self.call(dry_run=True)
        self.assertEqual(self.windows.read_bytes(), before)

    def test_rejects_unconfigured_year(self):
        with self.assertRaisesRegex(ValueError, "not in configured"):
            self.call(year=2021, dry_run=True)

    def test_rejects_missing_archive(self):
        with self.assertRaisesRegex(FileNotFoundError, "WMT archive missing"):
            self.call()

    def test_rejects_missing_dedup_file(self):
        self.archive.write_bytes(b"placeholder")
        with self.assertRaisesRegex(FileNotFoundError, "Deduplication keys missing"):
            self.call()

    def test_rejects_existing_output(self):
        self.out.write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            self.call(dry_run=True)
        self.assertEqual(self.out.read_bytes(), b"original")

    def test_rejects_year_without_windows(self):
        self.archive.write_bytes(b"placeholder")
        self.dedup.write_bytes(b"placeholder")
        with self.assertRaisesRegex(ValueError, "No retention windows"):
            self.call(year=2019)

    def test_wires_official_reader_to_existing_adapter(self):
        self.archive.write_bytes(b"placeholder")
        self.dedup.write_bytes(b"placeholder")

        class FakeOfficial:
            @staticmethod
            def get_deduplicated_wmt_docs(archives, keys):
                assert archives == [str(self.archive)]
                assert keys == str(self.dedup)
                return iter(["synthetic-document"])

            @staticmethod
            def get_wmt_passages_from_docs(docs, prepend_date=True):
                return iter([])

        with patch(
            "src.eval.run_week6_wmt_trial.load_official_extraction",
            return_value=FakeOfficial,
        ), patch(
            "src.eval.run_week6_wmt_trial.extract_archive_year",
            return_value=2,
        ) as extractor, patch(
            "src.eval.run_week6_wmt_trial.sha256",
            return_value="testhash",
        ):
            report = self.call()
            self.assertEqual(report["passages_written"], 2)
            self.assertEqual(report["output_sha256"], "testhash")
            self.assertEqual(extractor.call_args.kwargs["year"], 2020)
            self.assertEqual(
                list(extractor.call_args.kwargs["docs"]),
                ["synthetic-document"],
            )


if __name__ == "__main__":
    unittest.main()
