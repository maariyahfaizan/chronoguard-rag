from __future__ import annotations
import re, shutil
from pathlib import Path

TARGET = Path('src/attacks/attack_pool.py')
MARKER = '# WEEK5_POISON_COUNT_WRAPPER'
if not TARGET.exists():
    raise SystemExit(f'Cannot find {TARGET}. Run from the repository root.')
source = TARGET.read_text(encoding='utf-8')
if MARKER in source:
    print('Patch already present; no changes made.')
    raise SystemExit(0)
if len(re.findall(r'(?m)^def apply_attack\(', source)) != 1:
    raise SystemExit('Expected exactly one public apply_attack() definition.')
source = re.sub(r'(?m)^def apply_attack\(', 'def _apply_attack_once(', source, count=1)

wrapper = r'''
# WEEK5_POISON_COUNT_WRAPPER
def apply_attack(
    record: Mapping[str, Any], *, attack_type: AttackType, seed: int,
    poison_payload: Optional[Mapping[str, Any]] = None,
    min_stale_age_days: int = 30, future_days: int = 7,
    wrong_date_days: int = 30, poison_count: int = 1,
) -> tuple[Record, Dict[str, Any]]:
    # Apply 1, 2, or 5 poisons to distinct non-gold slots atomically.
    if poison_count not in (1, 2, 5):
        raise ValueError('poison_count must be one of: 1, 2, 5')
    _validate_record(record)
    get_attack_spec(attack_type)

    if poison_count == 1:
        attacked, metadata = _apply_attack_once(
            record, attack_type=attack_type, seed=seed,
            poison_payload=poison_payload,
            min_stale_age_days=min_stale_age_days,
            future_days=future_days, wrong_date_days=wrong_date_days,
        )
        metadata['requested_poison_count'] = 1
        metadata['actual_poison_count'] = 1 if metadata.get('applied') else 0
        if isinstance(attacked.get('attack_metadata'), dict):
            attacked['attack_metadata'] = metadata
        return attacked, metadata

    original = copy.deepcopy(dict(record))
    working = copy.deepcopy(dict(record))
    used_targets: list[int] = []
    operation_details: list[Dict[str, Any]] = []
    base_count = len(record['candidates'])

    for operation_index in range(poison_count):
        selected = None
        selected_metadata = None
        max_attempts = max(100, base_count * 20)
        for attempt in range(max_attempts):
            operation_seed = _stable_seed(
                seed, operation_index * max_attempts + attempt, attack_type
            )
            candidate_working, candidate_metadata = _apply_attack_once(
                working, attack_type=attack_type, seed=operation_seed,
                poison_payload=poison_payload,
                min_stale_age_days=min_stale_age_days,
                future_days=future_days, wrong_date_days=wrong_date_days,
            )
            details = candidate_metadata.get('details', {})
            target_index = details.get('target_index')
            if not candidate_metadata.get('applied'):
                if attempt == 0 and operation_index == 0:
                    metadata = {
                        'attack_type': attack_type, 'seed': seed,
                        'eligible': False, 'applied': False,
                        'reason': candidate_metadata.get('reason', 'no_eligible_target'),
                        'requested_poison_count': poison_count,
                        'actual_poison_count': 0, 'target_indices': [],
                        'operations': [], 'candidate_count_before': base_count,
                        'candidate_count_after': base_count,
                    }
                    original['attack_condition'] = attack_type
                    original['attack_metadata'] = metadata
                    return original, metadata
                continue
            if target_index is None or target_index in used_targets:
                continue
            selected, selected_metadata = candidate_working, candidate_metadata
            break

        if selected is None or selected_metadata is None:
            metadata = {
                'attack_type': attack_type, 'seed': seed,
                'eligible': False, 'applied': False,
                'reason': 'insufficient_distinct_targets',
                'requested_poison_count': poison_count,
                'actual_poison_count': 0, 'target_indices': [],
                'operations': [], 'candidate_count_before': base_count,
                'candidate_count_after': base_count,
            }
            original['attack_condition'] = attack_type
            original['attack_metadata'] = metadata
            return original, metadata

        details = copy.deepcopy(selected_metadata['details'])
        target_index = int(details['target_index'])
        used_targets.append(target_index)
        operation_details.append(details)
        working = selected
        # Validation applies to the reviewed stale source, not copied slots.
        if attack_type == 'stale_evidence':
            working['candidates'][target_index].pop('stale_evidence_validated', None)

    if len(used_targets) != poison_count or len(set(used_targets)) != poison_count:
        raise AssertionError('Poison targets must be unique and match poison_count.')
    if len(working['candidates']) != base_count:
        raise AssertionError('Attack changed candidate cardinality.')
    for field in ('query', 'gold_answer', 'gold_aliases', 'question_ts',
                  'gold_chunk_ids', 'gold_validated'):
        if working[field] != record[field]:
            raise AssertionError(f'Attack illegally modified ground-truth field: {field}')
    gold_ids = _gold_ids(record)
    for candidate in working['candidates']:
        if _is_gold(candidate, gold_ids) and not candidate['is_source_document']:
            raise AssertionError(f'Gold chunk lost source status: {candidate["doc_id"]}')
    metadata = {
        'attack_type': attack_type, 'seed': seed,
        'eligible': True, 'applied': True,
        'requested_poison_count': poison_count,
        'actual_poison_count': len(used_targets),
        'target_indices': used_targets, 'operations': operation_details,
        'candidate_count_before': base_count,
        'candidate_count_after': len(working['candidates']),
    }
    working['attack_condition'] = attack_type
    working['attack_metadata'] = metadata
    return working, metadata
'''

anchor = r'(?m)^def generate_attacked_records\('
if len(re.findall(anchor, source)) != 1:
    raise SystemExit('Could not find exactly one generate_attacked_records() anchor.')
source = re.sub(anchor, wrapper + '\n\ndef generate_attacked_records(', source, count=1)
old_sig = '    wrong_date_days: int = 30,\n) -> List[Record]:\n    """Generate an attacked copy of every supplied record."""'
new_sig = '    wrong_date_days: int = 30,\n    poison_count: int = 1,\n) -> List[Record]:\n    """Generate an attacked copy of every supplied record."""'
if old_sig not in source:
    raise SystemExit('Could not find generate_attacked_records() signature.')
source = source.replace(old_sig, new_sig, 1)
needle = '            wrong_date_days=wrong_date_days,\n        )\n\n        attacked["attack_record_index"] = index'
replacement = '            wrong_date_days=wrong_date_days,\n            poison_count=poison_count,\n        )\n\n        attacked["attack_record_index"] = index'
if needle not in source:
    raise SystemExit('Could not find generate_attacked_records() apply_attack call.')
source = source.replace(needle, replacement, 1)
backup = TARGET.with_suffix('.py.week5-backup')
if not backup.exists():
    shutil.copy2(TARGET, backup)
TARGET.write_text(source, encoding='utf-8')

# Add focused automated coverage for multi-poison counts.
test_path = Path('tests/test_attack_pool_poison_counts.py')
test_source = r'''import copy
import unittest

from src.attacks.attack_pool import apply_attack

ATTACK_TYPES = [
    'stale_evidence', 'fabricated_fresh', 'future_date',
    'duplicate_fresh', 'correct_content_wrong_date',
]
PAYLOAD = {
    'payload_id': 'count-test-payload',
    'text': 'A deliberately fabricated test claim about Rangers.',
    'timestamp': '2025-02-10T12:00:00Z',
}


def make_record():
    qts = '2025-02-01T12:00:00Z'
    candidates = [{
        'doc_id': 'gold-001',
        'text': 'Rangers are in the validated test position according to the official league table.',
        'timestamp': '2025-01-30T12:00:00Z',
        'is_source_document': True,
    }]
    candidates.append({
        'doc_id': 'stale-001',
        'text': 'Rangers football team league position and season standings from an older competition.',
        'timestamp': '2024-01-01T12:00:00Z',
        'is_source_document': True,
        'stale_evidence_validated': True,
    })
    for i in range(1, 8):
        candidates.append({
            'doc_id': f'fresh-{i:03d}',
            'text': f'Recent Rangers football team league position report number {i}.',
            'timestamp': f'2025-01-{25-i:02d}T12:00:00Z',
            'is_source_document': True,
        })
    return {
        'query': 'What is the current Rangers football team position?',
        'gold_answer': 'Rangers are in the test position.',
        'gold_aliases': ['Rangers test position'],
        'question_ts': qts,
        'gold_chunk_ids': ['gold-001'],
        'gold_validated': True,
        'candidates': candidates,
    }


class TestAttackPoolPoisonCounts(unittest.TestCase):
    def test_supported_counts_apply_to_distinct_slots(self):
        for attack_type in ATTACK_TYPES:
            for count in (1, 2, 5):
                with self.subTest(attack_type=attack_type, count=count):
                    record = make_record()
                    before = copy.deepcopy(record)
                    kwargs = {'poison_payload': PAYLOAD} if attack_type == 'fabricated_fresh' else {}
                    attacked, metadata = apply_attack(
                        record, attack_type=attack_type, seed=42,
                        poison_count=count, **kwargs,
                    )
                    self.assertEqual(record, before, 'input record mutated')
                    self.assertEqual(len(attacked['candidates']), len(record['candidates']))
                    if metadata['applied']:
                        self.assertEqual(metadata['actual_poison_count'], count)
                        self.assertEqual(metadata['requested_poison_count'], count)
                        self.assertEqual(len(metadata['target_indices']), count)
                        self.assertEqual(len(set(metadata['target_indices'])), count)
                        self.assertEqual(metadata['candidate_count_before'], metadata['candidate_count_after'])
                        self.assertEqual(attacked['gold_answer'], record['gold_answer'])
                        self.assertEqual(attacked['question_ts'], record['question_ts'])
                        self.assertEqual(attacked['gold_chunk_ids'], record['gold_chunk_ids'])
                        self.assertEqual(attacked['candidates'][0], record['candidates'][0])
                    else:
                        self.assertEqual(metadata['actual_poison_count'], 0)
                        self.assertEqual(attacked['candidates'], record['candidates'])

    def test_invalid_count_rejected(self):
        with self.assertRaises(ValueError):
            apply_attack(make_record(), attack_type='future_date', seed=42, poison_count=3)

    def test_multi_count_is_deterministic(self):
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                kwargs = {'poison_payload': PAYLOAD} if attack_type == 'fabricated_fresh' else {}
                first = apply_attack(make_record(), attack_type=attack_type, seed=77, poison_count=2, **kwargs)
                second = apply_attack(make_record(), attack_type=attack_type, seed=77, poison_count=2, **kwargs)
                self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
'''
if not test_path.exists():
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(test_source, encoding='utf-8')

print(f'Patched {TARGET}; backup saved to {backup}')
print(f'Added {test_path}')
print('Run: python -m unittest tests.test_attack_pool tests.test_attack_pool_poison_counts -v')
