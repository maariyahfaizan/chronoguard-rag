"""Synthetic fixture tests; no network or WMT archives needed."""
import datetime as dt
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path

from src.eval.extract_week6_evidence import extract_documents, read_shard

Doc = namedtuple('Doc', 'sorting_key publication_ts text')
Passage = namedtuple('Passage', 'id text')


def fake_original_passages(docs, prepend_date=True):
    # Stand-in for DeepMind API. A separate integration test against the
    # pinned DeepMind module is needed to prove actual library equivalence.
    for doc in docs:
        for i, chunk in enumerate(doc.text.split(b'|')):
            yield Passage(f'{doc.sorting_key}_{i}', chunk)


class TestWeek6Extractor(unittest.TestCase):
    def setUp(self):
        self.t0 = dt.datetime(2020, 1, 10, tzinfo=dt.timezone.utc)
        self.docs = [
            Doc('article_a_', int(self.t0.timestamp()), b'first|second'),
            Doc('article_b_', int((self.t0 + dt.timedelta(days=100)).timestamp()), b'outside'),
        ]
        self.windows = [(self.t0 - dt.timedelta(days=1), self.t0 + dt.timedelta(days=1))]

    def test_matches_original_passage_generator_on_eligible_documents(self):
        expected = [
            {'doc_id': p.id, 'text': p.text.decode(), 'timestamp': self.t0.isoformat()}
            for p in fake_original_passages([self.docs[0]], prepend_date=False)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '2020.jsonl.gz'
            count = extract_documents(iter(self.docs), self.windows, path, fake_original_passages)
            self.assertEqual(count, 2)
            self.assertEqual(read_shard(path), expected)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '2020.jsonl.gz'
            extract_documents(self.docs, self.windows, path, fake_original_passages)
            with self.assertRaises(FileExistsError):
                extract_documents(self.docs, self.windows, path, fake_original_passages)

    def test_rejects_naive_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                extract_documents(self.docs, [(dt.datetime(2020, 1, 1), self.t0)],
                                  Path(tmp) / 'bad.gz', fake_original_passages)

    def test_real_deepmind_generator(self):
        import sys
        import tempfile
        from pathlib import Path
        from datetime import datetime, timezone

        sys.path.insert(0, "third_party/streamingqa")
        from extraction import WMTDoc, get_wmt_passages_from_docs

        docs = [
            WMTDoc(
                sorting_key="week6_test_a_",
                publication_ts=1577836800,
                text=b"One. Two. Three. Four. Five. Six. Seven."
            ),
            WMTDoc(
                sorting_key="week6_test_b_",
                publication_ts=1577923200,
                text=b"Alpha. Beta. Gamma."
            ),
        ]

        windows = [
            (
                datetime(2020, 1, 1, tzinfo=timezone.utc),
                datetime(2020, 1, 1, 23, 59, 59, tzinfo=timezone.utc),
            )
        ]

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "test.jsonl.gz"

            count = extract_documents(
                docs=iter(docs),
                windows=windows,
                output_path=output,
                passage_generator=get_wmt_passages_from_docs,
            )

            records = read_shard(output)

            expected = [
                {
                    "doc_id": passage.id,
                    "text": passage.text.decode("utf-8", errors="replace"),
                    "timestamp": datetime.fromtimestamp(
                        docs[0].publication_ts,
                        tz=timezone.utc,
                    ).isoformat(),
                }
                for passage in get_wmt_passages_from_docs(
                    [docs[0]], prepend_date=False
                )
            ]

            self.assertEqual(records, expected)
            self.assertEqual(count, len(expected))


if __name__ == '__main__':
    unittest.main()
