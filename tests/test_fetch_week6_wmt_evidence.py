"""No-network tests of Kaggle WMT streaming, cleanup and publication."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.eval.fetch_week6_wmt_evidence import run_year, digest, download_keys


class FakePipe:
    def close(self):
        pass


class FakeProcess:
    def __init__(self, code=0):
        self.stdout = FakePipe()
        self.code = code
        self.killed = False

    def wait(self):
        return self.code

    def poll(self):
        return self.code

    def kill(self):
        self.killed = True


class TestKaggleYear(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.windows = [{
            "qa_id": "q", "window_start": "2020-06-01T00:00:00+00:00",
            "window_end": "2020-06-30T00:00:00+00:00",
            "evidence_id": "2020gold", "recent_or_past": "recent", "reserve_rank": 1,
        }]
        self.coverage = [{"qa_id": "q", "configured_years": [2020]}]
        self.config = {"evidence_source": {
            "base_url": "https://example.org/doc/en/",
            "filename_pattern": "news-docs.{year}.en.filtered.gz",
        }, "_windows_sha256": "windows-hash", "_deepmind_sha256": "parser-hash"}
        self.keys = self.root / "keys.gz"
        self.keys.write_bytes(b"fixture")
        self.netrc = self.root / "netrc"
        self.netrc.write_text("fixture")
        self.doc = SimpleNamespace(publication_ts=int(dt.datetime(
            2020, 6, 10, tzinfo=dt.timezone.utc).timestamp()))

        def passages(docs, prepend_date=True):
            self.assertFalse(prepend_date)
            for doc in docs:
                yield SimpleNamespace(id="test_doc_0", text=b"test passage")

        self.official = SimpleNamespace(
            get_deduplicated_wmt_docs=lambda **kwargs: iter([self.doc]),
            get_wmt_passages_from_docs=passages,
        )

    def call(self, **overrides):
        params = dict(year=2020, windows=self.windows, coverage=self.coverage,
                      output_dir=self.root / "out", config=self.config,
                      keys_path=self.keys, netrc_path=self.netrc,
                      official=self.official, max_attempts=1)
        params.update(overrides)
        return run_year(**params)

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_success_publishes_shard_and_audit(self, popen):
        popen.return_value = FakeProcess(0)
        result = self.call()
        self.assertEqual(result["passages"], 1)
        shard = self.root / "out/2020.jsonl.gz"
        audit = self.root / "out/2020.audit.json"
        self.assertTrue(shard.exists())
        self.assertTrue(audit.exists())
        self.assertEqual(result["output_sha256"], digest(shard))
        import gzip
        with gzip.open(shard, "rt", encoding="utf-8") as f:
            record = json.loads(f.readline())
        self.assertEqual(record["doc_id"], "test_doc_0")
        self.assertEqual(record["timestamp"], "2020-06-10T00:00:00+00:00")
        self.assertEqual(list((self.root / "out").glob(".*")), [])

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_curl_failure_never_publishes(self, popen):
        popen.return_value = FakeProcess(22)
        with self.assertRaisesRegex(RuntimeError, "failed after"):
            self.call()
        self.assertEqual(list((self.root / "out").iterdir()), [])

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_parser_failure_never_publishes(self, popen):
        popen.return_value = FakeProcess(0)
        self.official.get_deduplicated_wmt_docs = lambda **kw: (_ for _ in ()).throw(ValueError("bad gzip"))
        with self.assertRaisesRegex(RuntimeError, "failed after"):
            self.call()
        self.assertEqual(list((self.root / "out").iterdir()), [])

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_existing_shard_never_overwritten(self, popen):
        out = self.root / "out"
        out.mkdir()
        (out / "2020.jsonl.gz").write_bytes(b"original")
        with self.assertRaises(FileExistsError):
            self.call()
        self.assertEqual((out / "2020.jsonl.gz").read_bytes(), b"original")
        popen.assert_not_called()

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_no_windows_does_not_start_download(self, popen):
        with self.assertRaisesRegex(ValueError, "no eligible"):
            self.call(coverage=[{"qa_id": "q", "configured_years": [2019]}])
        popen.assert_not_called()

    @patch("src.eval.fetch_week6_wmt_evidence.subprocess.Popen")
    def test_retries_from_scratch_after_curl_failure(self, popen):
        popen.side_effect = [FakeProcess(22), FakeProcess(0)]
        result = self.call(max_attempts=2)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(popen.call_count, 2)

    def test_existing_keys_reject_bad_checksum(self):
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            download_keys("https://example.org/keys", self.keys)


if __name__ == "__main__":
    unittest.main()
