"""Regression tests for the Week-5 attack pool (supervisor items W5-1, W5-2, W5-3, W5-5).

Run from the repo root:
    python -m unittest tests.test_attack_pool_regressions -v

Covers what tests/test_attack_pool.py does not:
  * ineligible cases for every attack (including the source == only-target no-op),
  * poison counts 1/2/5 on a pool large enough to hold them,
  * unique, non-gold target slots, unchanged gold, unique doc_ids,
  * copy attacks never overwrite a source slot used by another operation.
"""

import copy
import unittest

from src.attacks.attack_pool import apply_attack

ATTACK_TYPES = [
    "stale_evidence",
    "fabricated_fresh",
    "future_date",
    "duplicate_fresh",
    "correct_content_wrong_date",
]
COPY_ATTACKS = ["stale_evidence", "duplicate_fresh", "correct_content_wrong_date"]

QUERY = "What is the current Rangers football team position?"

PAYLOAD = {
    "payload_id": "test-poison-001",
    "text": (
        "A deliberately fabricated test claim about the Rangers football "
        "team and its current league position."
    ),
    "timestamp": "2025-02-10T12:00:00Z",
}


def cand(doc_id, text, timestamp, **extra):
    c = {
        "doc_id": doc_id,
        "text": text,
        "timestamp": timestamp,
        "is_source_document": True,
    }
    c.update(extra)
    return c


GOLD = cand(
    "gold-001",
    "Rangers are in the validated test position according to the official league table.",
    "2025-01-30T12:00:00Z",
)
STALE = cand(
    "stale-001",
    "Rangers football team league position and season standings from an older competition.",
    "2024-01-01T12:00:00Z",
    stale_evidence_validated=True,
)


def fresh(n, day):
    return cand(
        f"fresh-00{n}",
        f"Recent Rangers football team league position update number {n} from the league.",
        f"2025-01-{day:02d}T12:00:00Z",
    )


def filler(n):
    return cand(
        f"filler-00{n}",
        f"An unrelated document number {n} about gardening and cooking.",
        "2024-11-01T12:00:00Z",
    )


def make_record(candidates, gold_ids=("gold-001",)):
    return {
        "query": QUERY,
        "gold_answer": "Rangers are in the test position.",
        "gold_aliases": ["Rangers test position"],
        "question_ts": "2025-02-01T12:00:00Z",
        "gold_chunk_ids": list(gold_ids),
        "gold_validated": True,
        "candidates": copy.deepcopy(candidates),
    }


def full_record():
    """11 candidates: 1 gold, 1 validated stale, 3 fresh, 6 filler (10 non-gold)."""
    return make_record(
        [GOLD, STALE, fresh(1, 25), fresh(2, 26), fresh(3, 27)]
        + [filler(i) for i in range(1, 7)]
    )


def run(record, attack_type, seed=42, count=1):
    kwargs = {}
    if attack_type == "fabricated_fresh":
        kwargs["poison_payload"] = PAYLOAD
    return apply_attack(
        record,
        attack_type=attack_type,
        seed=seed,
        poison_count=count,
        **kwargs,
    )


class TestIneligibleCases(unittest.TestCase):
    def assert_declined(self, record, attack_type):
        original = copy.deepcopy(record)
        attacked, meta = run(record, attack_type)
        self.assertFalse(meta["applied"])
        self.assertFalse(meta["eligible"])
        self.assertIn("reason", meta)
        self.assertEqual(attacked["candidates"], original["candidates"])
        self.assertEqual(record, original)

    def test_duplicate_fresh_declines_when_source_is_only_non_gold_slot(self):
        # W5-2 regression: source == only possible target must be ineligible.
        self.assert_declined(make_record([GOLD, fresh(1, 25)]), "duplicate_fresh")

    def test_stale_declines_when_source_is_only_non_gold_slot(self):
        # W5-1 regression: the no-op (source overwriting itself) must not happen.
        self.assert_declined(make_record([GOLD, STALE]), "stale_evidence")

    def test_correct_content_wrong_date_declines_without_target(self):
        self.assert_declined(make_record([GOLD]), "correct_content_wrong_date")

    def test_correct_content_wrong_date_declines_without_gold_candidate(self):
        record = make_record([STALE, fresh(1, 25)], gold_ids=("missing-gold",))
        self.assert_declined(record, "correct_content_wrong_date")

    def test_future_date_declines_with_unparseable_timestamps(self):
        record = make_record([GOLD, cand("x-001", "some text", "not a date")])
        self.assert_declined(record, "future_date")

    def test_fabricated_fresh_declines_without_replaceable_slot(self):
        self.assert_declined(make_record([GOLD]), "fabricated_fresh")

    def test_fabricated_fresh_requires_payload_and_fields(self):
        record = full_record()
        with self.assertRaises(ValueError):
            apply_attack(record, attack_type="fabricated_fresh", seed=1)
        with self.assertRaises(ValueError):
            apply_attack(
                record,
                attack_type="fabricated_fresh",
                seed=1,
                poison_payload={"timestamp": "2025-02-10T12:00:00Z"},
            )
        with self.assertRaises(ValueError):
            apply_attack(
                record,
                attack_type="fabricated_fresh",
                seed=1,
                poison_payload={"text": "x"},
            )


class TestPoisonCounts(unittest.TestCase):
    def test_counts_use_unique_non_gold_slots(self):
        for attack_type in ATTACK_TYPES:
            for count in (1, 2, 5):
                with self.subTest(attack_type=attack_type, count=count):
                    record = full_record()
                    original = copy.deepcopy(record)
                    attacked, meta = run(record, attack_type, count=count)

                    self.assertTrue(meta["applied"], msg=meta)
                    self.assertEqual(meta["requested_poison_count"], count)
                    self.assertEqual(meta["actual_poison_count"], count)

                    targets = meta["target_indices"]
                    self.assertEqual(len(targets), count)
                    self.assertEqual(len(set(targets)), count)

                    gold = set(original["gold_chunk_ids"])
                    for i in targets:
                        self.assertNotIn(original["candidates"][i]["doc_id"], gold)

                    self.assertEqual(
                        len(attacked["candidates"]), len(original["candidates"])
                    )
                    # gold slot untouched
                    self.assertEqual(
                        attacked["candidates"][0], original["candidates"][0]
                    )
                    # doc_ids stay unique
                    ids = [c["doc_id"] for c in attacked["candidates"]]
                    self.assertEqual(len(ids), len(set(ids)))
                    # input not mutated
                    self.assertEqual(record, original)

    def test_counts_are_deterministic_for_a_fixed_seed(self):
        for attack_type in ATTACK_TYPES:
            for count in (1, 2, 5):
                with self.subTest(attack_type=attack_type, count=count):
                    a, ma = run(full_record(), attack_type, seed=7, count=count)
                    b, mb = run(full_record(), attack_type, seed=7, count=count)
                    self.assertEqual(a, b)
                    self.assertEqual(ma, mb)

    def test_invalid_poison_count_is_rejected(self):
        with self.assertRaises(ValueError):
            run(full_record(), "future_date", count=3)

    def test_copy_attacks_never_overwrite_a_source_slot(self):
        """A passage copied by one operation must not be overwritten by another.

        Expected to FAIL on the current wrapper for duplicate_fresh with some
        seeds, until the used_sources check is added to apply_attack.
        """
        for seed in range(20):
            for attack_type in COPY_ATTACKS:
                with self.subTest(attack_type=attack_type, seed=seed):
                    attacked, meta = run(full_record(), attack_type, seed=seed, count=5)
                    self.assertTrue(meta["applied"], msg=meta)
                    sources = {op["source_index"] for op in meta["operations"]}
                    targets = set(meta["target_indices"])
                    self.assertTrue(
                        sources.isdisjoint(targets),
                        msg=f"sources {sources} overlap targets {targets}",
                    )


if __name__ == "__main__":
    unittest.main()