"""Audit Week 6 gold parent-document recovery in one WMT passage shard.

Read-only on input data. String matches are *signals*, not semantic adjudication.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path


def read_jsonl(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def audit(metadata_path, shard_path, year):
    candidates = {}
    for row in read_jsonl(metadata_path):
        qid = row['qa_id']
        if qid in candidates:
            raise ValueError(f'Duplicate candidate ID: {qid}')
        candidates[qid] = row
    if not candidates:
        raise ValueError('Empty metadata')
    selected = {qid: row for qid, row in candidates.items()
                if row['evidence_id'][:4] == str(year)}
    parents = defaultdict(list)
    for qid, row in selected.items():
        parents[row['evidence_id']].append(qid)
    found = defaultdict(list)
    for passage in read_jsonl(shard_path):
        pid = passage['doc_id']
        parent, separator, index = pid.rpartition('_')
        if separator and index.isdecimal() and parent in parents:
            found[parent].append(passage)
    results = []
    for qid, row in selected.items():
        passages = found[row['evidence_id']]
        by_id = defaultdict(set)
        timestamps = set()
        for p in passages:
            by_id[p['doc_id']].add((p['text'], p['timestamp']))
            timestamps.add(p['timestamp'])
        conflicts = sorted(pid for pid, variants in by_id.items() if len(variants) > 1)
        start = datetime.fromisoformat(row['window_start'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(row['window_end'].replace('Z', '+00:00'))
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError(f'{qid}: window must be timezone-aware')
        passage_times = [datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in timestamps]
        window_ok = bool(passages) and all(start <= ts <= end for ts in passage_times)
        expected_day = datetime.fromtimestamp(row['evidence_ts'], tz=timezone.utc).date()
        day_ok = bool(passages) and all(ts.astimezone(timezone.utc).date() == expected_day for ts in passage_times)
        text = '\n'.join(p['text'] for p in passages).casefold()
        answer_hits = [a for a in row.get('answers', []) if isinstance(a, str) and a.strip() and a.strip().casefold() in text]
        results.append({
            'qa_id': qid, 'recent_or_past': row['recent_or_past'], 'archive_year': int(year),
            'parent_found': bool(passages), 'passage_count': len(passages),
            'unique_passage_ids': len(by_id), 'conflicting_passage_ids': conflicts,
            'window_ok': window_ok, 'evidence_day_ok': day_ok,
            'answer_string_hits': answer_hits,
            'status': ('needs_review' if not passages or conflicts or not window_ok or not day_ok or not answer_hits
                       else 'candidate_for_semantic_review'),
        })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--shard', type=Path, required=True)
    parser.add_argument('--year', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f'Output already exists: {args.out}')
    rows = audit(args.metadata, args.shard, args.year)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(f'Audited {len(rows)} gold parent documents for {args.year}; output: {args.out}')
    for row in rows:
        print(row['qa_id'], row['status'], 'passages=', row['passage_count'],
              'answer_hits=', row['answer_string_hits'])


if __name__ == '__main__':
    main()
