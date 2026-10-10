
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

POISON_PAYLOAD = {
    "payload_id": "test-poison-001",
    "text": (
        "A deliberately fabricated test claim about the "
        "Rangers football team and its current league position."
    ),
    "timestamp": "2025-02-10T12:00:00Z",
}


def make_test_record():
    """Create a small, controlled record for attack tests."""
    return {
        "query": "What is the current Rangers football team position?",
        "gold_answer": "Rangers are in the test position.",
        "gold_aliases": ["Rangers test position"],
        "question_ts": "2025-02-01T12:00:00Z",
        "gold_chunk_ids": ["gold-001"],
        "gold_validated": True,
        "candidates": [
            {
                "doc_id": "gold-001",
                "text": (
                    "Rangers are in the validated test position "
                    "according to the official league table."
                ),
                "timestamp": "2025-01-30T12:00:00Z",
                "is_source_document": True,
            },
            {
                "doc_id": "stale-001",
                "text": (
                    "Rangers football team league position and "
                    "season standings from an older competition."
                ),
                "timestamp": "2024-01-01T12:00:00Z",
                "is_source_document": True,
            },
            {
                "doc_id": "fresh-001",
                "text": (
                    "Recent Rangers football team league position "
                    "and standings reported in a recent update."
                ),
                "timestamp": "2025-01-25T12:00:00Z",
                "is_source_document": True,
            },
            {
                "doc_id": "replace-001",
                "text": "An unrelated document about gardening.",
                "timestamp": "2024-12-01T12:00:00Z",
                "is_source_document": True,
            },
            {
                "doc_id": "replace-002",
                "text": "Another unrelated document about cooking.",
                "timestamp": "2024-11-01T12:00:00Z",
                "is_source_document": True,
            },
        ],
    }


def run_attack(record, attack_type, seed=42):
    """Run an attack with a payload when the attack requires one."""
    kwargs = {}

    if attack_type == "fabricated_fresh":
        kwargs["poison_payload"] = POISON_PAYLOAD

    return apply_attack(
        record,
        attack_type=attack_type,
        seed=seed,
        **kwargs,
    )


class TestAttackPool(unittest.TestCase):

    def test_all_attacks_preserve_input_record(self):
        """Attacks must not mutate the original input record."""
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                original = copy.deepcopy(record)

                run_attack(record, attack_type)

                self.assertEqual(record, original)

    def test_all_attacks_preserve_ground_truth(self):
        """Question and gold fields must remain unchanged."""
        protected_fields = [
            "query",
            "gold_answer",
            "gold_aliases",
            "question_ts",
            "gold_chunk_ids",
            "gold_validated",
        ]

        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                attacked, metadata = run_attack(record, attack_type)

                for field in protected_fields:
                    self.assertEqual(
                        attacked[field],
                        record[field],
                        msg=f"{attack_type} changed {field}",
                    )

    def test_all_attacks_preserve_candidate_count(self):
        """Attacks must not add or remove candidate slots."""
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                attacked, metadata = run_attack(record, attack_type)

                self.assertEqual(
                    len(attacked["candidates"]),
                    len(record["candidates"]),
                )

                if metadata["applied"]:
                    self.assertEqual(
                        metadata["candidate_count_before"],
                        metadata["candidate_count_after"],
                    )

    def test_gold_candidate_is_never_modified(self):
        """The gold evidence candidate must remain exactly unchanged."""
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                original_gold = copy.deepcopy(record["candidates"][0])

                attacked, metadata = run_attack(record, attack_type)

                gold_after = next(
                    candidate
                    for candidate in attacked["candidates"]
                    if candidate["doc_id"] == "gold-001"
                )

                self.assertEqual(gold_after, original_gold)
                self.assertTrue(gold_after["is_source_document"])

    def test_same_seed_produces_same_result(self):
        """The same record, attack, and seed must be reproducible."""
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()

                first_record, first_metadata = run_attack(
                    record, attack_type, seed=42
                )
                second_record, second_metadata = run_attack(
                    record, attack_type, seed=42
                )

                self.assertEqual(first_record, second_record)
                self.assertEqual(first_metadata, second_metadata)

    def test_applied_attacks_report_metadata_consistently(self):
        """Successful attacks must report applied status and valid indices."""
        for attack_type in ATTACK_TYPES:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                attacked, metadata = run_attack(record, attack_type)

                if metadata["applied"]:
                    self.assertTrue(metadata["eligible"])
                    self.assertIn("details", metadata)

                    details = metadata["details"]

                    if "target_index" in details:
                        target_index = details["target_index"]
                        self.assertGreaterEqual(target_index, 0)
                        self.assertLess(
                            target_index,
                            len(attacked["candidates"]),
                        )

                        target = attacked["candidates"][target_index]
                        self.assertNotIn(
                            target["doc_id"],
                            record["gold_chunk_ids"],
                        )

    def test_source_and_target_differ_for_copy_attacks(self):
        """Copy-style attacks must not overwrite their own source slot."""
        copy_attacks = [
            "stale_evidence",
            "duplicate_fresh",
            "correct_content_wrong_date",
        ]

        for attack_type in copy_attacks:
            with self.subTest(attack_type=attack_type):
                record = make_test_record()
                attacked, metadata = run_attack(record, attack_type)

                if metadata["applied"]:
                    details = metadata["details"]

                    if "source_index" in details:
                        self.assertNotEqual(
                            details["source_index"],
                            details["target_index"],
                        )


    def test_stale_attack_is_ineligible_without_old_candidates(self):
        """Stale attack should decline when no candidate is old enough."""
        record = make_test_record()
        record["candidates"][1]["timestamp"] = "2025-01-20T12:00:00Z"

        attacked, metadata = run_attack(
            record,
            "stale_evidence",
            seed=42,
        )

        self.assertFalse(metadata["applied"])
        self.assertFalse(metadata["eligible"])
        self.assertEqual(
            attacked["candidates"],
            record["candidates"],
        )

    
    def test_stale_attack_rejects_old_candidate_with_overlap_only(self):
        """Old age and topical overlap alone do not prove staleness."""
        record = make_test_record()

        # The candidate is old and mentions Rangers, but has no
        # explicit evidence that it is obsolete or conflicting.
        stale_candidate = record["candidates"][1]
        stale_candidate.pop("stale_evidence_validated", None)
        stale_candidate.pop("obsolete_validated", None)
        stale_candidate.pop("conflict_validated", None)
        stale_candidate.pop("answer_bearing_stale_validated", None)

        attacked, metadata = run_attack(
            record,
            "stale_evidence",
            seed=42,
        )

        self.assertFalse(metadata["applied"])
        self.assertFalse(metadata["eligible"])
        self.assertEqual(
            attacked["candidates"],
            record["candidates"],
        )

    def test_duplicate_attack_is_ineligible_without_fresh_candidates(self):
        """Duplicate attack should decline without a recent non-gold source."""
        record = make_test_record()

        for candidate in record["candidates"]:
            if candidate["doc_id"] != "gold-001":
                candidate["timestamp"] = "2024-01-01T12:00:00Z"

        attacked, metadata = run_attack(
            record,
            "duplicate_fresh",
            seed=42,
        )

        self.assertFalse(metadata["applied"])
        self.assertFalse(metadata["eligible"])
        self.assertEqual(
            attacked["candidates"],
            record["candidates"],
        )

    
    def test_future_date_changes_timestamp_not_text(self):
        """Future-date attack changes only the selected timestamp."""
        record = make_test_record()
        original_candidates = copy.deepcopy(record["candidates"])

        attacked, metadata = run_attack(
            record,
            "future_date",
            seed=42,
        )

        self.assertTrue(metadata["applied"])

        target_index = metadata["details"]["target_index"]
        original_target = original_candidates[target_index]
        attacked_target = attacked["candidates"][target_index]

        self.assertEqual(
            attacked_target["text"],
            original_target["text"],
        )
        self.assertNotEqual(
            attacked_target["timestamp"],
            original_target["timestamp"],
        )
        self.assertEqual(
            attacked_target["doc_id"],
            original_target["doc_id"],
        )
        self.assertEqual(
            attacked_target["is_source_document"],
            original_target["is_source_document"],
        )

    
    def test_correct_content_wrong_date_preserves_target_id(self):
        """Wrong-date attack copies gold content but preserves target identity."""
        record = make_test_record()
        original_candidates = copy.deepcopy(record["candidates"])

        attacked, metadata = run_attack(
            record,
            "correct_content_wrong_date",
            seed=42,
        )

        self.assertTrue(metadata["applied"])

        details = metadata["details"]
        target_index = details["target_index"]
        source_index = details["source_index"]

        self.assertNotEqual(source_index, target_index)

        original_target = original_candidates[target_index]
        attacked_target = attacked["candidates"][target_index]

        # The target slot keeps its original document identity.
        self.assertEqual(
            attacked_target["doc_id"],
            original_target["doc_id"],
        )

        # The target now contains the gold candidate's correct text.
        gold_candidate = next(
            candidate
            for candidate in original_candidates
            if candidate["doc_id"] == "gold-001"
        )
        self.assertEqual(
            attacked_target["text"],
            gold_candidate["text"],
        )

        # The attack should change the date.
        self.assertNotEqual(
            attacked_target["timestamp"],
            gold_candidate["timestamp"],
        )

        # The original gold candidate must remain unchanged.
        self.assertEqual(
            attacked["candidates"][0],
            original_candidates[0],
        )

    
    def test_fabricated_fresh_uses_supplied_payload(self):
        """Fabricated-fresh attack must insert the provided payload."""
        record = make_test_record()
        original_candidates = copy.deepcopy(record["candidates"])

        attacked, metadata = run_attack(
            record,
            "fabricated_fresh",
            seed=42,
        )

        self.assertTrue(metadata["applied"])

        target_index = metadata["details"]["target_index"]
        target = attacked["candidates"][target_index]

        # The target must contain the exact supplied fabricated content.
        self.assertEqual(target["text"], POISON_PAYLOAD["text"])
        self.assertEqual(
            target["timestamp"],
            POISON_PAYLOAD["timestamp"],
        )

        # It must not overwrite a gold candidate.
        self.assertNotEqual(target["doc_id"], "gold-001")

        # The attack must preserve the target slot's original document ID.
        self.assertEqual(
            target["doc_id"],
            original_candidates[target_index]["doc_id"],
        )

        # The original gold evidence remains untouched.
        self.assertEqual(
            attacked["candidates"][0],
            original_candidates[0],
        )

    
    def test_duplicate_fresh_copies_source_but_preserves_target_id(self):
        """Duplicate-fresh copies source content into a distinct target slot."""
        record = make_test_record()
        original_candidates = copy.deepcopy(record["candidates"])

        attacked, metadata = run_attack(
            record,
            "duplicate_fresh",
            seed=42,
        )

        self.assertTrue(metadata["applied"])

        details = metadata["details"]
        source_index = details["source_index"]
        target_index = details["target_index"]

        self.assertNotEqual(source_index, target_index)

        source = original_candidates[source_index]
        original_target = original_candidates[target_index]
        attacked_target = attacked["candidates"][target_index]

        # The target receives the source's content and timestamp.
        self.assertEqual(attacked_target["text"], source["text"])
        self.assertEqual(
            attacked_target["timestamp"],
            source["timestamp"],
        )

        # The target retains its original document ID.
        self.assertEqual(
            attacked_target["doc_id"],
            original_target["doc_id"],
        )

        # The original source slot must remain unchanged.
        self.assertEqual(
            attacked["candidates"][source_index],
            source,
        )

        # Gold evidence must remain untouched.
        self.assertEqual(
            attacked["candidates"][0],
            original_candidates[0],
        )

    
    def test_stale_evidence_copies_source_to_distinct_target(self):
        """Stale attack copies old evidence without overwriting its source."""
        record = make_test_record()
        record["candidates"][1]["stale_evidence_validated"] = True
        original_candidates = copy.deepcopy(record["candidates"])

        attacked, metadata = run_attack(
            record,
            "stale_evidence",
            seed=42,
        )

        self.assertTrue(metadata["applied"])

        details = metadata["details"]
        source_index = details["source_index"]
        target_index = details["target_index"]

        self.assertNotEqual(source_index, target_index)

        source = original_candidates[source_index]
        original_target = original_candidates[target_index]
        attacked_target = attacked["candidates"][target_index]

        # The attack copies the selected stale source's content.
        self.assertEqual(attacked_target["text"], source["text"])
        self.assertEqual(
            attacked_target["timestamp"],
            source["timestamp"],
        )

        # The destination keeps its original document ID.
        self.assertEqual(
            attacked_target["doc_id"],
            original_target["doc_id"],
        )

        # The source slot and gold evidence remain unchanged.
        self.assertEqual(
            attacked["candidates"][source_index],
            source,
        )
        self.assertEqual(
            attacked["candidates"][0],
            original_candidates[0],
        )

if __name__ == "__main__":
    unittest.main()