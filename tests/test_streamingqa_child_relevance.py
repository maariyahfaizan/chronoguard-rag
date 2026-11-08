"""Synthetic-only tests. No retrieval, tokenizer loading, inference or writes.

The historical chunker imports an unavailable optional model library. Extract
only its three inspected pure function definitions to exercise the real window
and child-emission code with a fictional tokenizer, without mocking a backend.
"""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from src.eval.build_streamingqa_pools import (
    assemble_records, build_pool_specs, find_validated_gold_chunks,
)
from src.eval.streamingqa_child_relevance import (
    GENERATOR_PREFIX_CHARS, LEXICAL_BASIS, SCHEMA_VERSION, label_children_v1,
)

ROOT = Path(__file__).resolve().parents[1]


def pure_functions(path, names, environment=None):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in definitions} == set(names)
    env = {} if environment is None else environment
    exec(compile(ast.Module(body=definitions, type_ignores=[]), path, "exec"), env)
    return env


class FictionalTokenizer:
    def encode(self, text, add_special_tokens=False):
        assert add_special_tokens is False
        return text.split()

    def decode(self, tokens, skip_special_tokens=True):
        return " ".join(tokens)


@pytest.fixture
def historical_chunker():
    return pure_functions("src/eval/chunk_streamingqa_pools.py",
                          {"chunk_token_ids", "chunk_candidate", "chunk_record"})


def record(text="Paris", *, validated=True, doc="synthetic-article_2", aliases=None):
    return {"qa_id": "synthetic-child-qa", "query": "Fictional capital question?",
            "sorting_key": "synthetic-article", "question_ts": 1609459200,
            "gold_answer": "Paris", "gold_aliases": [] if aliases is None else aliases,
            "gold_validated": validated, "gold_chunk_ids": [doc],
            "candidates": [{"doc_id": doc, "text": text,
                            "timestamp": "2020-01-01T00:00:00Z",
                            "is_source_document": validated}]}


def emitted(parent, texts):
    return [{"doc_id": f"{parent['doc_id']}#chunk{i}", "parent_doc_id": parent["doc_id"],
             "text": text, "timestamp": parent["timestamp"],
             "is_source_document": parent["is_source_document"]}
            for i, text in enumerate(texts)]


def annotate(texts, *, r=None):
    r = record(" ".join(texts)) if r is None else r
    return label_children_v1(r, [emitted(r["candidates"][0], texts)])


def built_pool(*, matched):
    stamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    chunks = [(i, f"synthetic-article_{i}", stamp) for i in range(3)]
    texts = {doc: {"text": "Paris" if matched and i == 2 else "unrelated",
                   "timestamp": stamp.isoformat()} for i, doc, _ in chunks}
    texts["synthetic-other_0"] = {"text": "distractor", "timestamp": stamp.isoformat()}
    question = {"qa_id": "synthetic-child-qa", "question": "Fictional capital?",
                "evidence_id": "synthetic-article", "evidence_ts": stamp.timestamp(),
                "answers": ["Paris"], "question_ts": stamp.timestamp()}
    specs = build_pool_specs({"sample": {"seed": 42}, "candidate_pool": {
        "window_days": 7, "candidates_per_query": 2}}, [question], [stamp] * 4,
        list(texts), {"synthetic-article": chunks}, texts)
    return assemble_records(specs, texts, seed=42)[0]


def test_answer_in_article_P2_only():
    chunks = [(i, f"synthetic-article_{i}", None) for i in range(3)]
    texts = {doc: {"text": "Paris" if i == 2 else "Unrelated evidence"}
             for i, doc, _ in chunks}
    selected = find_validated_gold_chunks(chunks, texts, "Paris", [])
    assert selected == [chunks[2]]
    parent_pool = built_pool(matched=True)
    assert parent_pool["gold_chunk_ids"] == ["synthetic-article_2"]
    assert {p["doc_id"] for p in parent_pool["candidates"]} == {
        "synthetic-article_2", "synthetic-other_0"}
    result = label_children_v1(parent_pool, [emitted(p, [p["text"]])
                                           for p in parent_pool["candidates"]])
    assert result["lexically_validated_gold_chunk_ids"] == ["synthetic-article_2#chunk0"]


def test_only_one_child_of_positive_parent_matches(historical_chunker):
    r = record("pad " * 700 + "Paris")
    old = historical_chunker["chunk_record"](r, FictionalTokenizer(), 320, 64, 64)
    assert [c["is_source_document"] for c in old["candidates"]] == [True, True, True]
    result = label_children_v1(r, [old["candidates"]])
    assert [c["full_text_lexical_match"] for c in result["children"]] == [False, False, True]
    assert result["lexically_validated_gold_chunk_ids"] == ["synthetic-article_2#chunk2"]
    # The old output is neither modified nor silently reinterpreted in place.
    assert len(old["gold_chunk_ids"]) == 3


def test_no_child_matches_does_not_invent_fallback(historical_chunker):
    r = {**record("alpha " + "pad " * 700 + "beta"), "gold_answer": "alpha beta"}
    old = historical_chunker["chunk_record"](r, FictionalTokenizer(), 320, 64, 64)
    result = label_children_v1(r, [old["candidates"]])
    assert result["historical_gold_validated"] is True
    assert result["lexical_gold_validated"] is False
    assert result["lexically_validated_gold_chunk_ids"] == []
    assert result["unvalidated_fallback_child_occurrence_ids"] == []
    assert len(result["children"]) == 3


def test_multiple_children_and_alias_matches():
    result = annotate(["Paris", "City of Light", "unrelated"],
                      r=record(aliases=["City of Light"]))
    assert [c["full_text_matching_answer_indices"] for c in result["children"]] == [[0], [1], []]
    assert result["lexically_validated_gold_chunk_ids"] == [
        "synthetic-article_2#chunk0", "synthetic-article_2#chunk1"]


def test_unvalidated_fallback_is_never_promoted_even_with_lexical_match():
    result = annotate(["Paris", "unrelated"], r=record(validated=False))
    assert result["children"][0]["full_text_lexical_match"] is True
    assert result["lexically_validated_gold_chunk_ids"] == []
    assert result["unvalidated_fallback_parent_ids"] == ["synthetic-article_2"]
    assert result["unvalidated_fallback_child_occurrence_ids"] == [
        "parent-slot-0/child-0", "parent-slot-0/child-1"]
    assert result["historical_gold_chunk_ids"] == ["synthetic-article_2"]


def test_actual_builder_fallback_reference_is_separated():
    r = built_pool(matched=False)
    assert not r["gold_validated"] and r["gold_chunk_ids"] == ["synthetic-article_0"]
    assert not any(p["is_source_document"] for p in r["candidates"])
    result = label_children_v1(r, [emitted(p, [p["text"]]) for p in r["candidates"]])
    assert result["lexically_validated_gold_chunk_ids"] == []
    assert result["unvalidated_fallback_parent_ids"] == ["synthetic-article_0"]
    assert len(result["unvalidated_fallback_child_occurrence_ids"]) == 1


def test_other_source_lexical_match_stays_separate_from_gold_article():
    r = record()
    r["candidates"].append({"doc_id": "synthetic-distractor_0", "text": "Paris",
                            "timestamp": None, "is_source_document": False})
    result = label_children_v1(r, [emitted(p, [p["text"]]) for p in r["candidates"]])
    assert [c["full_text_lexical_match"] for c in result["children"]] == [True, True]
    assert result["children"][1]["parent_role"] == "OTHER_PARENT"
    assert result["lexically_validated_gold_chunk_ids"] == ["synthetic-article_2#chunk0"]


@pytest.mark.parametrize("text,answer", [("The capital is not Paris.", "Paris"),
                                         ("York has a new library.", "New York")])
def test_misleading_lexical_match_never_becomes_semantic_validation(text, answer):
    r = record(text); r["gold_answer"] = answer
    c = annotate([text], r=r)["children"][0]
    assert c["full_text_lexical_match"] is True
    assert c["lexical_basis"] == LEXICAL_BASIS
    assert c["semantic_support_status"] == "NOT_INDEPENDENTLY_REVIEWED"
    assert c["temporal_validity_status"] == "NOT_REVIEWED"
    assert c["source_authenticity_status"] == "NOT_ESTABLISHED_BY_LABELER"


def test_paraphrase_is_not_claimed_semantically_irrelevant():
    r = record("a dozen"); r["gold_answer"] = "twelve"
    c = annotate(["a dozen"], r=r)["children"][0]
    assert c["full_text_lexical_match"] is False
    assert c["semantic_support_status"] == "NOT_INDEPENDENTLY_REVIEWED"


def test_identity_timestamp_and_immutable_input():
    r = record(aliases=["City of Light"]); children = [emitted(r["candidates"][0], ["Paris"])]
    before = deepcopy((r, children))
    result = label_children_v1(r, children)
    c = result["children"][0]
    assert (r, children) == before
    assert c["parent_doc_id"] == "synthetic-article_2" and c["doc_id"].endswith("#chunk0")
    assert c["parent_candidate_slot"] == c["candidate_slot"] == 0
    assert c["timestamp"] == "2020-01-01T00:00:00Z"
    assert result["source_question"]["qa_id"] == r["qa_id"]
    assert result["source_question"]["sorting_key"] == r["sorting_key"]
    assert result["source_question"]["gold_aliases"] == r["gold_aliases"]
    assert c["child_text_sha256"] == hashlib.sha256(b"Paris").hexdigest()
    result["source_question"]["gold_aliases"].append("mutated output")
    result["historical_parent_metadata"][0]["text"] = "changed output"
    c["historical_child_metadata"]["text"] = "changed output"
    assert (r, children) == before


def test_unknown_date_is_preserved_without_inference():
    r = record(); r["candidates"][0]["timestamp"] = None
    c = annotate(["Paris"], r=r)["children"][0]
    assert c["timestamp"] is None and c["temporal_validity_status"] == "NOT_REVIEWED"


def test_identical_duplicate_ids_preserve_occurrences_and_order():
    r = record(); r["candidates"].append(deepcopy(r["candidates"][0]))
    groups = [emitted(p, ["Paris"]) for p in r["candidates"]]
    result = label_children_v1(r, groups)
    assert [c["doc_id"] for c in result["children"]] == ["synthetic-article_2#chunk0"] * 2
    assert [c["occurrence_id"] for c in result["children"]] == [
        "parent-slot-0/child-0", "parent-slot-1/child-0"]
    assert result["duplicate_parent_occurrences"] == result["duplicate_child_occurrences"] == 1
    assert len(result["lexically_validated_gold_chunk_ids"]) == 1
    assert len(result["lexically_validated_gold_occurrence_ids"]) == 2
    assert json.dumps(result, sort_keys=True) == json.dumps(label_children_v1(r, groups), sort_keys=True)


@pytest.mark.parametrize("where", ["parent", "child"])
def test_conflicting_duplicate_ids_are_rejected(where):
    r = record(); r["candidates"].append(deepcopy(r["candidates"][0]))
    groups = [emitted(p, ["Paris"]) for p in r["candidates"]]
    if where == "parent": r["candidates"][1]["text"] = "conflicting parent"
    else: groups[1][0]["text"] = "conflicting child"
    with pytest.raises(ValueError, match="conflicting duplicate " + where):
        label_children_v1(r, groups)


@pytest.mark.parametrize("padding,prefix_match", [(1494, True), (1495, False), (1500, False)])
def test_exact_1500_character_boundary(padding, prefix_match):
    text = "x" * padding + " Paris"
    c = annotate([text])["children"][0]
    assert c["full_text_lexical_match"] is True
    assert c["generator_prefix_lexical_match"] is prefix_match
    assert c["generator_prefix_sha256"] == hashlib.sha256(text[:1500].encode()).hexdigest()
    assert c["character_truncated"] is (len(text) > 1500)
    assert c["generator_model_visibility"] == "UNVERIFIED"


def test_character_view_matches_historical_truncate_function():
    truncate = pure_functions("src/generation/generate.py", {"truncate_passage"},
                              {"DEFAULT_MAX_PASSAGE_CHARS": 1500})["truncate_passage"]
    text = "\u00e9 " * 749 + " Paris"
    c = annotate([text])["children"][0]
    assert c["generator_prefix_sha256"] == hashlib.sha256(truncate(text).encode()).hexdigest()
    assert GENERATOR_PREFIX_CHARS == 1500


def test_cut_word_can_create_lexical_match_but_is_flagged_not_endorsed():
    c = annotate(["x" * 1494 + " Parisian"])["children"][0]
    assert not c["full_text_lexical_match"] and c["generator_prefix_lexical_match"]
    assert c["character_cut_splits_alphanumeric_run"]
    assert c["semantic_support_status"] == "NOT_INDEPENDENTLY_REVIEWED"


def test_versioned_schema_cannot_be_silently_consumed_as_legacy_pool():
    result = annotate(["Paris"])
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["execution_authorization"] == "NOT_AUTHORIZED_FOR_EXECUTION"
    assert not {"candidates", "gold_chunk_ids", "gold_validated"} & result.keys()
    assert "is_source_document" not in result["children"][0]


@pytest.mark.parametrize("mutation,reason", [
    ("empty", "empty or invalid child group"), ("groups", "one explicit child group"),
    ("parent", "child parent lineage mismatch"), ("order", "child ID/order mismatch"),
    ("timestamp", "child timestamp mismatch"), ("flag", "inconsistent historical child flag"),
    ("aliases", "invalid aliases"), ("validated", "gold_validated must be bool"),
    ("text", "child text must be a string"), ("parent_timestamp", "parent timestamp"),
    ("missing", "missing child fields"),
])
def test_malformed_or_drifting_inputs_fail_closed(mutation, reason):
    r = record(); groups = [emitted(r["candidates"][0], ["Paris"])]
    if mutation == "empty": groups[0] = []
    elif mutation == "groups": groups = []
    elif mutation == "parent": groups[0][0]["parent_doc_id"] = "wrong"
    elif mutation == "order": groups[0][0]["doc_id"] = "synthetic-article_2#chunk1"
    elif mutation == "timestamp": groups[0][0]["timestamp"] = "2099-01-01"
    elif mutation == "flag": groups[0][0]["is_source_document"] = False
    elif mutation == "aliases": r["gold_aliases"] = "Paris"
    elif mutation == "validated": r["gold_validated"] = "true"
    elif mutation == "text": groups[0][0]["text"] = []
    elif mutation == "parent_timestamp": r["candidates"][0]["timestamp"] = 123
    elif mutation == "missing": del groups[0][0]["timestamp"]
    with pytest.raises(ValueError, match=reason): label_children_v1(r, groups)


def test_empty_normalized_answer_does_not_match_every_child():
    r = record(); r["gold_answer"] = "the"; r["gold_aliases"] = []
    assert not annotate(["unrelated"], r=r)["lexical_gold_validated"]
