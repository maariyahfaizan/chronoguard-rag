"""Regression tests for the pre-Week-6 fixes: payload identity and nested
poison counts (supervisor items 1 and 2).

Run from the repo root:
    python -m pytest tests/test_identity_and_nesting.py -v
"""

import copy
import json
import random
import unittest
from pathlib import Path

from src.attacks.attack_pool import (
    _stable_seed,
    apply_attack,
    generate_attacked_records,
)
from src.attacks.identity import (
    PayloadIdentityError,
    check_payload_matches_record,
    pair_payloads_by_id,
    query_sha256,
)
from tests.test_attack_pool_regressions import (
    ATTACK_TYPES,
    PAYLOAD,
    full_record,
)

ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = ROOT / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
PAYLOAD_PATH = ROOT / "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl"


def record_with_id(qa_id, query):
    record = full_record()
    record["source_qa_id"] = qa_id
    record["query"] = query
    return record


def payload_for(qa_id, query, text):
    return {
        "payload_id": f"{qa_id}-fabricated_fresh-1",
        "source_qa_id": qa_id,
        "query_sha256": query_sha256(query),
        "text": text,
        "timestamp": "2025-02-10T12:00:00Z",
    }


class TestPayloadIdentity(unittest.TestCase):
    def setUp(self):
        self.rec_a = record_with_id("eval-A", "Question about Rangers?")
        self.rec_b = record_with_id("eval-B", "Question about Celtic?")
        self.pay_a = payload_for("eval-A", self.rec_a["query"], "Payload A.")
        self.pay_b = payload_for("eval-B", self.rec_b["query"], "Payload B.")

    def test_deliberately_mismatched_pair_is_rejected(self):
        with self.assertRaises(PayloadIdentityError):
            apply_attack(self.rec_a, attack_type="fabricated_fresh", seed=1,
                         poison_payload=self.pay_b)

    def test_mismatch_is_rejected_for_every_poison_count(self):
        for count in (1, 2, 5):
            with self.subTest(count=count):
                with self.assertRaises(PayloadIdentityError):
                    apply_attack(self.rec_a, attack_type="fabricated_fresh",
                                 seed=1, poison_payload=self.pay_b,
                                 poison_count=count)

    def test_missing_id_on_record_or_payload_is_rejected(self):
        no_id_record = copy.deepcopy(self.rec_a)
        del no_id_record["source_qa_id"]
        no_id_payload = {k: v for k, v in self.pay_a.items() if k != "source_qa_id"}

        with self.assertRaises(PayloadIdentityError):
            check_payload_matches_record(no_id_record, self.pay_a)
        with self.assertRaises(PayloadIdentityError):
            check_payload_matches_record(self.rec_a, no_id_payload)

    def test_same_id_but_different_query_hash_is_rejected(self):
        bad = dict(self.pay_a, query_sha256=query_sha256("some other question"))
        with self.assertRaises(PayloadIdentityError):
            check_payload_matches_record(self.rec_a, bad)

    def test_matching_pair_is_accepted(self):
        attacked, meta = apply_attack(self.rec_a, attack_type="fabricated_fresh",
                                      seed=1, poison_payload=self.pay_a)
        self.assertTrue(meta["applied"])
        slot = attacked["candidates"][meta["target_indices"][0]]
        self.assertEqual(slot["payload_source_qa_id"], "eval-A")

    def test_pairing_ignores_file_order(self):
        pairs = pair_payloads_by_id([self.rec_a, self.rec_b], [self.pay_b, self.pay_a])
        self.assertEqual([(r["source_qa_id"], p["source_qa_id"]) for r, p in pairs],
                         [("eval-A", "eval-A"), ("eval-B", "eval-B")])

    def test_pairing_rejects_missing_extra_and_duplicate_payloads(self):
        with self.assertRaises(PayloadIdentityError):
            pair_payloads_by_id([self.rec_a, self.rec_b], [self.pay_a])
        with self.assertRaises(PayloadIdentityError):
            pair_payloads_by_id([self.rec_a], [self.pay_a, self.pay_b])
        with self.assertRaises(PayloadIdentityError):
            pair_payloads_by_id([self.rec_a], [self.pay_a, dict(self.pay_a)])

    def test_generate_records_is_independent_of_input_order(self):
        records = [record_with_id(f"eval-{i}", f"Rangers question {i}?") for i in range(5)]
        payloads = {r["source_qa_id"]: payload_for(r["source_qa_id"], r["query"],
                                                   f"Payload {r['source_qa_id']}.")
                    for r in records}
        shuffled = records[:]
        random.Random(7).shuffle(shuffled)

        for count in (1, 2, 5):
            with self.subTest(count=count):
                ordered = generate_attacked_records(
                    records, attack_type="fabricated_fresh", seed=42,
                    poison_payloads=payloads, poison_count=count)
                reordered = generate_attacked_records(
                    shuffled, attack_type="fabricated_fresh", seed=42,
                    poison_payloads=payloads, poison_count=count)

                by_id = {r["source_qa_id"]: r for r in ordered}
                for r in reordered:
                    expected = by_id[r["source_qa_id"]]
                    self.assertEqual(r["candidates"], expected["candidates"])
                    self.assertEqual(r["attack_metadata"], expected["attack_metadata"])
                    for i in r["attack_metadata"]["target_indices"]:
                        self.assertEqual(r["candidates"][i]["text"],
                                         f"Payload {r['source_qa_id']}.")

    def test_generate_records_requires_ids_when_payloads_are_given(self):
        record = full_record()
        with self.assertRaises(ValueError):
            generate_attacked_records([record], attack_type="fabricated_fresh",
                                      poison_payloads={"0": PAYLOAD})


class TestNestedPoisonCounts(unittest.TestCase):
    def kwargs(self, attack_type):
        if attack_type == "fabricated_fresh":
            return {"poison_payload": PAYLOAD}
        return {}

    def test_n1_subset_n2_subset_n5_for_every_attack_and_many_seeds(self):
        for attack_type in ATTACK_TYPES:
            for seed in range(25):
                with self.subTest(attack_type=attack_type, seed=seed):
                    runs = {n: apply_attack(full_record(), attack_type=attack_type, seed=seed,
                                            poison_count=n, **self.kwargs(attack_type))
                            for n in (1, 2, 5)}
                    applied = {n: meta["applied"] for n, (_, meta) in runs.items()}
                    if not applied[1]:
                        continue
                    t1, t2, t5 = (runs[n][1]["target_indices"] for n in (1, 2, 5))
                    if applied[2]:
                        self.assertEqual(t2[:1], t1)
                    if applied[5]:
                        self.assertEqual(t5[:2], t2)
                        self.assertTrue(set(t1) <= set(t2) <= set(t5))

    def test_shared_slots_hold_identical_poison_content(self):
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                runs = {n: apply_attack(full_record(), attack_type=attack_type, seed=3,
                                        poison_count=n, **self.kwargs(attack_type))
                        for n in (1, 2, 5)}
                if not all(meta["applied"] for _, meta in runs.values()):
                    continue
                small_record, small_meta = runs[1]
                for n in (2, 5):
                    big_record, big_meta = runs[n]
                    for slot in small_meta["target_indices"]:
                        self.assertEqual(big_record["candidates"][slot],
                                         small_record["candidates"][slot])
                    self.assertEqual(big_meta["operations"][:1], small_meta["operations"])
                    self.assertEqual(big_meta["target_doc_ids"][:1], small_meta["target_doc_ids"])

    def test_30d_attack_and_0d_control_use_the_same_slots(self):
        for count in (1, 2, 5):
            with self.subTest(count=count):
                _, m30 = apply_attack(full_record(), attack_type="correct_content_wrong_date",
                                      seed=9, poison_count=count, wrong_date_days=30)
                _, m0 = apply_attack(full_record(), attack_type="correct_content_wrong_date",
                                     seed=9, poison_count=count, wrong_date_days=0)
                self.assertEqual(m30["target_indices"], m0["target_indices"])
                self.assertEqual([op["source_index"] for op in m30["operations"]],
                                 [op["source_index"] for op in m0["operations"]])

    def test_seed_from_source_qa_id_ignores_position(self):
        self.assertEqual(_stable_seed(42, "eval-001639", "future_date"),
                         _stable_seed(42, "eval-001639", "future_date"))
        self.assertNotEqual(_stable_seed(42, "eval-001639", "future_date"),
                            _stable_seed(42, "eval-001952", "future_date"))


@unittest.skipUnless(PILOT_PATH.exists() and PAYLOAD_PATH.exists(), "pilot data not present")
class TestRealPilotFiles(unittest.TestCase):
    """The authoritative pilot files must pair by source_qa_id."""

    def load(self, path):
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_pilot_records_and_payloads_pair_by_id(self):
        records, payloads = self.load(PILOT_PATH), self.load(PAYLOAD_PATH)
        pairs = pair_payloads_by_id(records, list(reversed(payloads)))
        self.assertEqual([r["source_qa_id"] for r, _ in pairs],
                         ["eval-001639", "eval-001952", "eval-005229"])

    def test_swapping_two_real_payload_ids_is_rejected(self):
        records, payloads = self.load(PILOT_PATH), self.load(PAYLOAD_PATH)
        with self.assertRaises(PayloadIdentityError):
            apply_attack(records[0], attack_type="fabricated_fresh", seed=1,
                         poison_payload=payloads[1])


if __name__ == "__main__":
    unittest.main()
