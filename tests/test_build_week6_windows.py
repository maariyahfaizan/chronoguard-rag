
"""Unit tests for Week 6 reserve-to-window construction."""

import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.eval.build_week6_windows import build_windows


class TestWeek6Windows(unittest.TestCase):

    def test_balanced_ranked_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw.jsonl.gz"
            reserve = root / "reserve.jsonl"

            raw_rows = [
                {
                    "qa_id": "r1",
                    "recent_or_past": "recent",
                    "evidence_ts": 1577836800,
                    "evidence_id": "gold_recent",
                },
                {
                    "qa_id": "p1",
                    "recent_or_past": "past",
                    "evidence_ts": 1577923200,
                    "evidence_id": "gold_past",
                },
            ]

            reserve_rows = [
                {
                    "qa_id": "p1",
                    "recent_or_past": "past",
                    "reserve_rank": 1,
                },
                {
                    "qa_id": "r1",
                    "recent_or_past": "recent",
                    "reserve_rank": 1,
                },
            ]

            with gzip.open(raw, "wt", encoding="utf-8") as f:
                for row in raw_rows:
                    f.write(json.dumps(row) + "\n")

            with reserve.open("w", encoding="utf-8") as f:
                for row in reserve_rows:
                    f.write(json.dumps(row) + "\n")

            windows = build_windows(raw, reserve, per_stratum=1)

            self.assertEqual(len(windows), 2)
            self.assertEqual(
                {row["qa_id"] for row in windows},
                {"r1", "p1"},
            )

            for row in windows:
                start = datetime.fromisoformat(row["window_start"])
                end = datetime.fromisoformat(row["window_end"])

                self.assertEqual(start.utcoffset(), timedelta(0))
                self.assertEqual(end.utcoffset(), timedelta(0))
                self.assertEqual(end - start, timedelta(days=112))

                center = datetime.fromtimestamp(
                    row["evidence_ts"], tz=timezone.utc
                )

                self.assertEqual(start, center - timedelta(days=56))
                self.assertEqual(end, center + timedelta(days=56))

    def test_rejects_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            build_windows("unused", "unused", per_stratum=0)

    def test_rejects_duplicate_reserve_rank(self):
        import tempfile
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            reserve = Path(tmp) / "reserve.jsonl"

            rows = [
                {
                    "qa_id": "r1",
                    "recent_or_past": "recent",
                    "reserve_rank": 1,
                },
                {
                    "qa_id": "r2",
                    "recent_or_past": "recent",
                    "reserve_rank": 1,
                },
                {
                    "qa_id": "p1",
                    "recent_or_past": "past",
                    "reserve_rank": 1,
                },
            ]

            with reserve.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")

            with self.assertRaises(ValueError):
                build_windows(
                    raw_path=Path(tmp) / "unused.jsonl.gz",
                    reserve_path=reserve,
                    per_stratum=1,
                )
    def test_rejects_duplicate_reserve_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            reserve = Path(tmp) / "reserve.jsonl"

            rows = [
                {
                    "qa_id": "duplicate-001",
                    "recent_or_past": "recent",
                    "reserve_rank": 1,
                },
                {
                    "qa_id": "duplicate-001",
                    "recent_or_past": "past",
                    "reserve_rank": 1,
                },
            ]

            with reserve.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")

            with self.assertRaisesRegex(
                ValueError, "Duplicate reserve qa_id"
            ):
                build_windows(
                    raw_path=Path(tmp) / "unused.jsonl.gz",
                    reserve_path=reserve,
                    per_stratum=1,
                )
    def test_rejects_missing_reserve_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            reserve = Path(tmp) / "reserve.jsonl"

            rows = [
                {
                    "qa_id": "r1",
                    "recent_or_past": "recent",
                    "reserve_rank": 1,
                },
                {
                    "qa_id": "r2",
                    "recent_or_past": "recent",
                    "reserve_rank": 3,
                },
                {
                    "qa_id": "p1",
                    "recent_or_past": "past",
                    "reserve_rank": 1,
                },
            ]

            with reserve.open("w", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")

            with self.assertRaisesRegex(ValueError, "Non-contiguous reserve ranks"):
                build_windows(
                    raw_path=Path(tmp) / "unused.jsonl.gz",
                    reserve_path=reserve,
                    per_stratum=1,
                )


if __name__ == "__main__":
    unittest.main()
