"""Prepare a deterministic ID-only Week 6 reserve manifest; no model/evidence runs.

Example:
  python scripts/prepare_week6_reserve.py \
    --raw data/raw/streamingqa_eval.jsonl.gz \
    --week4 data/processed/streamingqa_control_pools_chunked.jsonl \
    --out-dir results/week6_sampling_draft

Outputs contain IDs, stratum, reserve ranks and provenance only; they do NOT
represent a finalized held-out benchmark. Refuses to overwrite output files.
"""
import argparse
import gzip
import hashlib
import json
import platform
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

PILOT_IDS = frozenset({'eval-001639', 'eval-001952', 'eval-005229'})
STRATA = ('recent', 'past')


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', str(text))).strip().casefold()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path}:{n}: invalid JSON') from exc


def make_reserve(raw_records, week4_records, seed=42, extra_exclusions=()):
    baseline = {normalize(r['query']) for r in week4_records}
    if not baseline:
        raise ValueError('Week 4 question set is empty')
    by_question = defaultdict(set)
    raw = {}
    for r in raw_records:
        qid = r['qa_id']
        if qid in raw:
            raise ValueError(f'Duplicate qa_id: {qid}')
        if r.get('recent_or_past') not in STRATA:
            raise ValueError(f'Unexpected stratum for {qid}: {r.get("recent_or_past")}')
        raw[qid] = r
        by_question[normalize(r['question'])].add(qid)
    if not raw:
        raise ValueError('Raw dataset is empty')
    unmatched = baseline - set(by_question)
    if unmatched:
        raise ValueError(f'{len(unmatched)} Week 4 questions did not match raw data; stop')
    baseline_excluded = set().union(*(by_question[q] for q in baseline))
    missing_pilots = PILOT_IDS - set(raw)
    if missing_pilots:
        raise ValueError(f'Corrected pilot IDs absent from raw dataset: {sorted(missing_pilots)}')
    extras = set(extra_exclusions)
    unknown_extras = extras - set(raw)
    if unknown_extras:
        raise ValueError(f'Unknown additional exclusions: {sorted(unknown_extras)[:10]}')
    excluded = baseline_excluded | PILOT_IDS | extras
    by_stratum = {s: sorted(qid for qid, r in raw.items()
                            if qid not in excluded and r['recent_or_past'] == s)
                  for s in STRATA}
    # Independent RNGs so changing one stratum cannot change the other.
    for s in STRATA:
        random.Random(f'week6-v1:{seed}:{s}').shuffle(by_stratum[s])
    rows = [{'qa_id': qid, 'recent_or_past': s, 'reserve_rank': i + 1}
            for s in STRATA for i, qid in enumerate(by_stratum[s])]
    stats = {'raw_count': len(raw), 'raw_unique_questions': len(by_question),
             'week4_unique_questions': len(baseline),
             'week4_excluded_raw_ids': len(baseline_excluded),
             'pilot_ids_all_in_week4_exclusions': PILOT_IDS <= baseline_excluded,
             'extra_exclusion_ids': len(extras), 'total_excluded_ids': len(excluded),
             'remaining_ids': len(rows),
             'remaining_by_stratum': {s: len(by_stratum[s]) for s in STRATA}}
    return rows, stats, sorted(excluded)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--week4', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--extra-exclusions', type=Path, help='Optional text file: one qa_id per line')
    args = p.parse_args()
    extra = []
    if args.extra_exclusions:
        extra = [s.strip() for s in args.extra_exclusions.read_text(encoding='utf-8').splitlines()
                 if s.strip() and not s.lstrip().startswith('#')]
    rows, stats, excluded = make_reserve(read_jsonl(args.raw), read_jsonl(args.week4), args.seed, extra)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {'reserve': args.out_dir / 'reserve_ids.jsonl',
               'exclusions': args.out_dir / 'excluded_ids.txt',
               'audit': args.out_dir / 'sampling_audit.json'}
    if any(path.exists() for path in outputs.values()):
        raise FileExistsError('Refusing to overwrite an existing manifest; choose a new --out-dir')
    audit = {'status': 'DRAFT_RESERVE_NOT_FINAL_BENCHMARK', 'sampling_algorithm':
             'sorted qa_id per stratum; Python random.Random(str seed).shuffle, independent per stratum',
             'seed': args.seed, 'python_version': platform.python_version(),
             'source_sha256': sha256(args.raw), 'week4_sha256': sha256(args.week4),
             'extra_exclusions_sha256': sha256(args.extra_exclusions) if args.extra_exclusions else None,
             'target_per_stratum_proposed': 150, 'stats': stats}
    with outputs['reserve'].open('x', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + '\n')
    outputs['exclusions'].write_text('\n'.join(excluded) + '\n', encoding='utf-8')
    audit['reserve_sha256'] = sha256(outputs['reserve'])
    audit['exclusions_sha256'] = sha256(outputs['exclusions'])
    outputs['audit'].write_text(json.dumps(audit, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(stats, indent=2))
    print('Draft ID-only reserve manifest written to:', args.out_dir)
    print('Not a final held-out sample. No evidence eligibility checks performed.')


if __name__ == '__main__':
    main()
