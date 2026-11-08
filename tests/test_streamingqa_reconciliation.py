"""Pure synthetic grouping/report tests; no backends, judging or estimators."""
from copy import deepcopy

import pytest

from scripts import reconcile_streamingqa_children as audit


def fixture(text="Paris"):
    parent = {"query": "Fictional question", "gold_answer": "Paris", "gold_aliases": ["Paris"],
              "question_ts": 123, "gold_validated": True, "gold_chunk_ids": ["synthetic_2"],
              "candidates": [{"doc_id": "synthetic_2", "text": text, "timestamp": "2020-01-01",
                              "is_source_document": True}]}
    chunked = {**deepcopy(parent), "n_candidates_pre_chunk": 1, "n_candidates_post_chunk": 1}
    chunked["candidates"] = [{"doc_id": "synthetic_2#chunk0", "parent_doc_id": "synthetic_2",
                              "text": text, "timestamp": "2020-01-01",
                              "is_source_document": True, "chunk_token_count": 2}]
    chunked["gold_chunk_ids"] = ["synthetic_2#chunk0"]
    sample = {"qa_id": "synthetic-qa", "question": parent["query"], "answers": ["Paris"],
              "question_ts": 123, "evidence_id": "synthetic"}
    return parent, chunked, sample


def reconcile(parent, child, sample):
    return audit.reconcile_question(parent, child, sample, 0, {"baseline": []})


def test_unique_overlapping_content_coverage():
    assert audit.complete_alignment("abc def ghi", ["abc def", "def ghi"]) == [[0, 6], [3, 9]]


@pytest.mark.parametrize("parent,parts,reason", [
    ("abcXdef", ["abc", "def"], "INCOMPLETE"),
    ("abc\u2122", ["abc"], "INCOMPLETE"),
    ("value\u00bd", ["value"], "INCOMPLETE"),
    ("abc", ["ab"], "INCOMPLETE"),
    ("abc", ["bc"], "INCOMPLETE"),
    ("abc", ["abcX"], "INCOMPLETE"),
    ("aaaaaa", ["aaa", "aaa", "aaa"], "AMBIGUOUS"),
    ("abc", [""], "EMPTY"),
])
def test_incomplete_or_ambiguous_coverage_rejected(parent, parts, reason):
    with pytest.raises(audit.LineageError, match=reason):
        audit.complete_alignment(parent, parts)


def test_valid_provisional_record_is_deterministic_and_not_approved():
    parent, child, sample = fixture()
    before = deepcopy((parent, child, sample))
    row, queue = reconcile(parent, child, sample)
    assert row["status"] == "PROVISIONAL_LEXICAL_RECONCILIATION"
    assert row["proposed_labeling"]["children"][0]["semantic_support_status"] == "NOT_INDEPENDENTLY_REVIEWED"
    assert queue["review_status"] == "NOT_REVIEWED" and queue["review_decision"] is None
    assert queue["reasons"] == ["LEXICAL_MATCH_REQUIRES_SEMANTIC_REVIEW"]
    assert (parent, child, sample) == before
    assert audit.encoded(row) == audit.encoded(reconcile(parent, child, sample)[0])


def test_incomplete_question_never_calls_labeler(monkeypatch):
    parent, child, sample = fixture("Paris\u2122")
    child["candidates"][0]["text"] = "Paris"
    def forbidden(*args):
        raise AssertionError("blocked question must not be labeled")
    monkeypatch.setattr(audit, "label_children_v1", forbidden)
    row, queue = reconcile(parent, child, sample)
    assert row["status"] == "BLOCKED_NO_PROPOSED_LABELS"
    assert row["proposed_labeling"] is None
    assert row["comparisons"][0]["new_child_lexical_match"] is None
    assert row["comparisons"][0]["proposed_source_restricted_lexical_label"] is None
    assert queue["priority"] == "P0_BLOCKED"


@pytest.mark.parametrize("mutation,reason", [
    ("timestamp", "TIMESTAMP_DRIFT"), ("id", "CHILD_ORDER_OR_ID_DRIFT"),
    ("parent", "PARENT_ORDER_OR_ID_DRIFT"), ("missing", "MISSING_PARENT_CHILD_BLOCK"),
    ("count", "CHILD_COUNT_DRIFT"), ("tokens", "REPORTED_TOKEN_COUNT_OUT_OF_SCOPE"),
    ("gold_ids", "HISTORICAL_GOLD_ID_DRIFT"),
])
def test_lineage_drift_blocks_question(mutation, reason):
    parent, child, sample = fixture()
    if mutation == "timestamp": child["candidates"][0]["timestamp"] = "2099-01-01"
    elif mutation == "id": child["candidates"][0]["doc_id"] = "synthetic_2#chunk1"; child["gold_chunk_ids"] = ["synthetic_2#chunk1"]
    elif mutation == "parent": child["candidates"][0]["parent_doc_id"] = "wrong"
    elif mutation == "missing": child["candidates"] = []; child["gold_chunk_ids"] = []; child["n_candidates_post_chunk"] = 0
    elif mutation == "count": child["n_candidates_post_chunk"] = 2
    elif mutation == "tokens": child["candidates"][0]["chunk_token_count"] = 321
    elif mutation == "gold_ids": child["gold_chunk_ids"] = []
    row, _ = reconcile(parent, child, sample)
    assert row["proposed_labeling"] is None
    assert reason in row["validation_failures"][0]["reason"]


def test_duplicate_occurrences_follow_explicit_producer_order():
    parent, child, sample = fixture()
    parent["candidates"].append(deepcopy(parent["candidates"][0]))
    child["candidates"].append(deepcopy(child["candidates"][0]))
    child["gold_chunk_ids"] *= 2
    child["n_candidates_pre_chunk"] = child["n_candidates_post_chunk"] = 2
    row, queue = reconcile(parent, child, sample)
    assert row["duplicate_child_occurrences"] == 1
    assert [c["parent_candidate_slot"] for c in row["proposed_labeling"]["children"]] == [0, 1]
    assert "DUPLICATE_CANONICAL_IDS_REQUIRE_OCCURRENCE_POLICY_REVIEW" in queue["reasons"]


def test_historically_unvalidated_and_undefined_record_is_retained():
    parent, child, sample = fixture("unrelated")
    parent["gold_validated"] = child["gold_validated"] = False
    parent["candidates"][0]["is_source_document"] = child["candidates"][0]["is_source_document"] = False
    child["gold_chunk_ids"] = []
    row, queue = audit.reconcile_question(parent, child, sample, 0, {"baseline": ["recall_at_5"]})
    assert row["fallback_parent_ids"] == ["synthetic_2"]
    assert row["historical_undefined_metrics"]["baseline"] == ["recall_at_5"]
    assert row["proposed_labeling"]["lexically_validated_gold_chunk_ids"] == []
    assert "NO_SOURCE_RESTRICTED_LEXICALLY_SUPPORTING_CHILD" in queue["reasons"]


def test_truncation_queue_does_not_claim_model_visibility():
    parent, child, sample = fixture("x " * 750 + "Paris")
    row, queue = reconcile(parent, child, sample)
    assert row["proposed_labeling"]["children"][0]["generator_model_visibility"] == "UNVERIFIED"
    assert queue["candidate_slots_over_character_budget"] == [0]


def test_alias_identity_drift_is_fatal_not_silently_joined():
    parent, child, sample = fixture()
    sample["answers"] = ["different"]
    with pytest.raises(audit.LineageError, match="SAMPLE_ALIAS_DRIFT"):
        reconcile(parent, child, sample)
