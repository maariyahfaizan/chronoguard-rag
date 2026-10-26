import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_week6_reserve import make_reserve, normalize


class TestSampling(unittest.TestCase):
    def setUp(self):
        self.raw = [
            {'qa_id': 'eval-001639', 'question': 'Pilot A', 'recent_or_past': 'past'},
            {'qa_id': 'eval-001952', 'question': 'Pilot B', 'recent_or_past': 'recent'},
            {'qa_id': 'eval-005229', 'question': 'Pilot C', 'recent_or_past': 'past'},
            {'qa_id': 'dup', 'question': 'Pilot A ', 'recent_or_past': 'past'},
        ] + [dict(qa_id=f'x{i}', question=f'Q{i}', recent_or_past='recent' if i % 2 else 'past')
             for i in range(20)]
        self.week4 = [{'query': q} for q in ['Pilot A', 'Pilot B', 'Pilot C']]

    def test_normalize(self):
        self.assertEqual(normalize('  A\t B  '), normalize('a b'))

    def test_exclusion_duplicate_and_pilots(self):
        rows, stats, excluded = make_reserve(self.raw, self.week4)
        self.assertEqual(stats['week4_excluded_raw_ids'], 4)
        self.assertTrue(stats['pilot_ids_all_in_week4_exclusions'])
        self.assertEqual(len(rows), 20)
        self.assertNotIn('dup', {r['qa_id'] for r in rows})

    def test_deterministic_and_order_independent(self):
        a = make_reserve(self.raw, self.week4)[0]
        b = make_reserve(list(reversed(self.raw)), self.week4)[0]
        self.assertEqual(a, b)
        self.assertEqual(a, make_reserve(self.raw, self.week4)[0])

    def test_additional_exclusion(self):
        rows, stats, _ = make_reserve(self.raw, self.week4, extra_exclusions=['x1'])
        self.assertEqual(len(rows), 19)
        self.assertEqual(stats['total_excluded_ids'], 5)

    def test_unmatched_baseline_fails_closed(self):
        with self.assertRaises(ValueError):
            make_reserve(self.raw, [{'query': 'Not present'}])

    def test_duplicate_ids_fails_closed(self):
        with self.assertRaises(ValueError):
            make_reserve(self.raw + [self.raw[0]], self.week4)


if __name__ == '__main__':
    unittest.main()
