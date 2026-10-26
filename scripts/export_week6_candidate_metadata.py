"""Export selected StreamingQA metadata for Kaggle without copying the raw dataset.

Run locally from the repository root. The output contains question text, answer
strings and gold evidence metadata, not model predictions or raw articles.
"""
import argparse
import gzip
import json
from pathlib import Path


def read_jsonl(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def export(raw, windows, output):
    selected = {}
    for row in read_jsonl(windows):
        qid = row['qa_id']
        if qid in selected:
            raise ValueError(f'duplicate window qa_id: {qid}')
        selected[qid] = row
    if not selected:
        raise ValueError('empty windows manifest')
    found = {}
    for row in read_jsonl(raw):
        qid = row.get('qa_id')
        if qid not in selected:
            continue
        if qid in found:
            raise ValueError(f'duplicate raw qa_id: {qid}')
        window = selected[qid]
        for field in ('evidence_id', 'evidence_ts', 'recent_or_past'):
            if row.get(field) != window.get(field):
                raise ValueError(f'{qid}: {field} differs between raw and windows')
        found[qid] = {
            'qa_id': qid,
            'question': row['question'],
            'answers': row['answers'],
            'answers_additional': row.get('answers_additional', []),
            'question_ts': row['question_ts'],
            **window,
        }
    missing = selected.keys() - found.keys()
    if missing:
        raise ValueError(f'missing raw records: {sorted(missing)[:10]}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        for qid in selected:
            f.write(json.dumps(found[qid], ensure_ascii=False) + '\n')
    return len(found)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--windows', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(f'Exported {export(args.raw, args.windows, args.out)} records to {args.out}')


if __name__ == '__main__':
    main()
