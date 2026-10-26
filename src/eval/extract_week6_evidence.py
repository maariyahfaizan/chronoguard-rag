"""Week 6: bounded-memory WMT passage extraction (no downloads).

Uses DeepMind StreamingQA's passage segmentation without materializing a
whole year's WMTDoc objects. Does not change Week 4 artifacts.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import os
from pathlib import Path
from typing import Iterable, Callable


def extract_documents(
    docs: Iterable,
    windows: list[tuple[dt.datetime, dt.datetime]],
    output_path: Path,
    passage_generator: Callable,
) -> int:
    """Write passages from eligible WMTDoc objects to a new gzip JSONL shard.

    `passage_generator` is extraction.get_wmt_passages_from_docs.
    Windows and publication timestamps must be timezone-aware UTC.
    Output is created exclusively; an existing output is never overwritten.
    """
    output_path = Path(output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    if not windows:
        raise ValueError("At least one retention window is required")
    if any(
    a.tzinfo is None
    or b.tzinfo is None
    or a.utcoffset() != dt.timedelta(0)
    or b.utcoffset() != dt.timedelta(0)
    or a > b
    for a, b in windows):
        raise ValueError("Windows must be ordered and UTC-aware")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp = output_path.with_name(output_path.name + '.tmp')
    if temp.exists():
        raise FileExistsError(temp)

    count = 0
    try:
        with temp.open('xb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as zipped:
                for doc in docs:
                    when = dt.datetime.fromtimestamp(doc.publication_ts, tz=dt.timezone.utc)
                    if not any(start <= when <= end for start, end in windows):
                        continue
                    for passage in passage_generator([doc], prepend_date=False):
                        record = {
                            'doc_id': passage.id,
                            'text': passage.text.decode('utf-8', errors='replace'),
                            'timestamp': when.isoformat(),
                        }
                        zipped.write((json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8'))
                        count += 1
        # No-overwrite policy even if output appeared during extraction.
        # Publish without replacing an existing destination.
        os.link(temp, output_path)
        temp.unlink()
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return count


def read_shard(path: Path) -> list[dict]:
    """Small-fixture helper only; do not use on full WMT shards."""
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return [json.loads(line) for line in f]
