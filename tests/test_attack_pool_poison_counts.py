import copy
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
