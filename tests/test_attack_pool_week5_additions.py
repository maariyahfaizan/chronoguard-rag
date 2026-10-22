"""Tests for the Week-5 additions to src/attacks/attack_pool.py.

Run from the repo root:
    python -m unittest tests.test_attack_pool_week5_additions -v
"""

import copy
import unittest
from datetime import datetime, timezone

from src.attacks.attack_pool import (
    _parse_timestamp,
    apply_attack,
    generate_attacked_records,
    merge_stale_reviews,
)
from src.attacks.attack_specs import ATTACK_SPECS
from tests.test_attack_pool_regressions import (
    ATTACK_TYPES,
    GOLD,
    STALE,
    cand,
    filler,
    fresh,
    full_record,
    make_record,
    run,
)


class TestTimestamps(unittest.TestCase):
    def test_parser_reads_unix_numeric_string_and_iso(self):
        expected = datetime(2020, 10, 31, 7, 0, tzinfo=timezone.utc)
        self.assertEqual(_parse_timestamp(1604127600), expected)
        self.assertEqual(_parse_timestamp("1604127600"), expected)
        self.assertEqual(_parse_timestamp("2020-10-31T07:00:00+00:00"), expected)
        self.assertEqual(_parse_timestamp("2020-10-31T07:00:00Z"), expected)

    def test_short_digit_strings_are_not_read_as_unix_seconds(self):
        parsed = _parse_timestamp("20200709")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2020)

    def test_unparseable_values_return_none(self):
        for value in (None, "", "not a date", True, "nan"):
            with self.subTest(value=value):
                self.assertIsNone(_parse_timestamp(value))

    def test_attacked_timestamps_match_clean_pool_format(self):
        # The clean pool stores e.g. '2012-10-20T00:00:00+00:00'.
        for attack_type in ("future_date", "correct_content_wrong_date"):
            with self.subTest(attack_type=attack_type):
                attacked, meta = run(full_record(), attack_type)
                ts = attacked["candidates"][meta["target_indices"][0]]["timestamp"]
                self.assertTrue(ts.endswith("+00:00"), msg=ts)
                self.assertNotIn("Z", ts)


class TestMetadata(unittest.TestCase):
    def test_target_doc_ids_match_target_slots(self):
        for attack_type in ATTACK_TYPES:
            for count in (1, 2, 5):
                with self.subTest(attack_type=attack_type, count=count):
                    record = full_record()
                    attacked, meta = run(record, attack_type, count=count)
                    expected = [record["candidates"][i]["doc_id"] for i in meta["target_indices"]]
                    self.assertEqual(meta["target_doc_ids"], expected)

    def test_declined_attack_has_empty_target_doc_ids(self):
        _, meta = run(make_record([GOLD]), "future_date")
        self.assertEqual(meta["target_doc_ids"], [])

    def test_fabricated_poison_is_flagged_synthetic(self):
        attacked, meta = run(full_record(), "fabricated_fresh", count=2)
        for i in meta["target_indices"]:
            poison = attacked["candidates"][i]
            self.assertTrue(poison["is_synthetic_poison"])
            self.assertEqual(poison["payload_id"], "test-poison-001")
            self.assertFalse(poison["is_source_document"])

    def test_fabricated_payload_with_bad_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_attack(
                full_record(),
                attack_type="fabricated_fresh",
                seed=1,
                poison_payload={"source_qa_id": "test-qa-001", "text": "x",
                                "timestamp": "not a date"},
            )

    def test_wrong_date_days_zero_is_the_duplication_only_control(self):
        record = full_record()
        attacked, meta = apply_attack(
            record, attack_type="correct_content_wrong_date", seed=3, wrong_date_days=0
        )
        self.assertTrue(meta["applied"])
        target = attacked["candidates"][meta["target_indices"][0]]
        gold = record["candidates"][0]
        self.assertEqual(target["text"], gold["text"])
        self.assertEqual(_parse_timestamp(target["timestamp"]), _parse_timestamp(gold["timestamp"]))

    def test_spec_marks_future_date_as_metadata_only(self):
        self.assertFalse(ATTACK_SPECS["future_date"].changes_visible_text)
        for name in ATTACK_TYPES:
            if name != "future_date":
                self.assertTrue(ATTACK_SPECS[name].changes_visible_text)


class TestStaleReviews(unittest.TestCase):
    def unflagged_record(self):
        stale = copy.deepcopy(STALE)
        stale.pop("stale_evidence_validated")
        return make_record([GOLD, stale, fresh(1, 25), filler(1)])

    def review(self, **overrides):
        base = {
            "query_index": 0,
            "doc_id": "stale-001",
            "validated": True,
            "reviewer": "reviewer-1",
            "reason": "Superseded by a later result for the same question.",
        }
        base.update(overrides)
        return base

    def test_unreviewed_old_candidate_is_not_stale_eligible(self):
        _, meta = run(self.unflagged_record(), "stale_evidence")
        self.assertFalse(meta["applied"])

    def test_reviewed_candidate_becomes_eligible_and_copies_carry_no_flag(self):
        merged = merge_stale_reviews([self.unflagged_record()], [self.review()])[0]
        source = next(c for c in merged["candidates"] if c["doc_id"] == "stale-001")
        self.assertTrue(source["stale_evidence_validated"])
        self.assertEqual(source["stale_review"]["reviewer"], "reviewer-1")

        attacked, meta = run(merged, "stale_evidence")
        self.assertTrue(meta["applied"])
        copy_slot = attacked["candidates"][meta["target_indices"][0]]
        self.assertEqual(copy_slot["text"], source["text"])
        self.assertNotIn("stale_evidence_validated", copy_slot)
        self.assertNotIn("stale_review", copy_slot)

    def test_unvalidated_review_does_not_set_the_flag(self):
        merged = merge_stale_reviews(
            [self.unflagged_record()], [self.review(validated=False)]
        )[0]
        source = next(c for c in merged["candidates"] if c["doc_id"] == "stale-001")
        self.assertNotIn("stale_evidence_validated", source)

    def test_review_requires_reviewer_and_reason(self):
        for key in ("reviewer", "reason"):
            with self.subTest(missing=key):
                with self.assertRaises(ValueError):
                    merge_stale_reviews([self.unflagged_record()], [self.review(**{key: ""})])

    def test_gold_or_unknown_doc_cannot_be_validated(self):
        with self.assertRaises(ValueError):
            merge_stale_reviews([self.unflagged_record()], [self.review(doc_id="gold-001")])
        with self.assertRaises(ValueError):
            merge_stale_reviews([self.unflagged_record()], [self.review(doc_id="nope-999")])

    def test_merge_does_not_mutate_inputs(self):
        record = self.unflagged_record()
        original = copy.deepcopy(record)
        merge_stale_reviews([record], [self.review()])
        self.assertEqual(record, original)


class TestGenerateAttackedRecords(unittest.TestCase):
    def test_skip_ineligible_drops_declined_records(self):
        records = [full_record(), make_record([GOLD])]
        kept = generate_attacked_records(
            records, attack_type="future_date", seed=42, skip_ineligible=True
        )
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0]["attack_metadata"]["applied"])
        self.assertEqual(kept[0]["attack_record_index"], 0)

    def test_default_keeps_declined_records_unchanged(self):
        records = [full_record(), make_record([GOLD])]
        everything = generate_attacked_records(records, attack_type="future_date", seed=42)
        self.assertEqual(len(everything), 2)
        self.assertFalse(everything[1]["attack_metadata"]["applied"])
        self.assertEqual(everything[1]["candidates"], records[1]["candidates"])


if __name__ == "__main__":
    unittest.main()