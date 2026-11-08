"""Synthetic offset tokenizers + SIX preserved parents only; no backend loads."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.eval.week4_v2_schema import SchemaError, make_frame, make_question, text_sha256
from src.eval.chunk_streamingqa_pools_v2 import (
    TokenizerProfile, chunk_question, chunk_text, validate_pool, verify_coverage,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = TokenizerProfile(scope="SYNTHETIC_ONLY")


class CharacterTokenizer:
    """Fictional character tokens, NOT BGE token counts or backend verification."""
    is_fast = True
    unk_token_id = -1

    def __call__(self, value, **kwargs):
        assert kwargs == {"add_special_tokens": False, "return_offsets_mapping": True,
                          "truncation": False, "padding": False}
        return {"input_ids": [ord(c) + 1 for c in value],
                "offset_mapping": [(i, i + 1) for i in range(len(value))]}

    def decode(self, ids, skip_special_tokens=True):
        return "".join(chr(i - 1) for i in ids)

    def convert_ids_to_tokens(self, ids):
        return [chr(i - 1) for i in ids]


def question(duplicate=False, value="Paris is not Rome. " * 30):
    qa = {"qa_id": "synthetic-chunk-test", "question": "Fictional reference?",
          "answers": ["Paris"], "question_ts": 1609459200}
    c = {"doc_id": "article\x00\x01x_2", "text": value,
         "timestamp": "2020-01-01T00:00:00Z", "is_source_document": True}
    pool = {"query": qa["question"], "gold_answer": "Paris", "gold_aliases": ["Paris"],
            "question_ts": qa["question_ts"], "candidates": [c]}
    if duplicate:
        pool["candidates"].append(deepcopy(c))
    f = make_frame([qa["qa_id"]], "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    return make_question(qa, pool, f, 0), f


def test_exact_chunking_no_inheritance_occurrences_and_determinism():
    q, frame = question(duplicate=True)
    original = deepcopy(q)
    result = chunk_question(q, frame, CharacterTokenizer(), profile=PROFILE)
    assert result == chunk_question(q, frame, CharacterTokenizer(), profile=PROFILE)
    assert q == original
    assert len(result["candidates"]) > 2
    by_parent = [[c for c in result["candidates"] if c["parent_slot"] == p] for p in [0, 1]]
    assert [c["canonical_child_id"] for c in by_parent[0]] == [c["canonical_child_id"] for c in by_parent[1]]
    assert set(c["child_occurrence_id"] for c in by_parent[0]).isdisjoint(c["child_occurrence_id"] for c in by_parent[1])
    assert all(c["relevance_grade"] == "UNKNOWN" and c["semantic_review_status"] == "NOT_REVIEWED"
               and c["temporal_validity"] == "UNKNOWN" and "is_source_document" not in c for c in result["candidates"])
    assert all(c["publication_time"] == q["parents"][c["parent_slot"]]["publication_time"] for c in result["candidates"])
    assert [c["candidate_slot"] for c in result["candidates"]] == list(range(len(result["candidates"])))
    assert validate_pool(result, frame, original_question=q)["execution_authorization"] == "NOT_AUTHORIZED_FOR_EXECUTION"


@pytest.mark.parametrize("size", [1, 64, 319, 320, 321, 1500, 1501, 1700])
def test_budget_overlap_coverage_and_no_zero_length(size):
    value = "x" * size
    plan = chunk_text(value, CharacterTokenizer(), profile=PROFILE)
    verify_coverage(value, plan["children"], plan["parameters"])
    assert all(0 < len(c["child_text"]) <= 1500 and c["standalone_token_count"] <= 320
               for c in plan["children"])
    assert len({(c["char_start"], c["char_end"]) for c in plan["children"]}) == len(plan["children"])
    assert plan["backend_verification"] == "UNVERIFIED"


def test_original_unicode_whitespace_and_utf8_offsets():
    value = " \r\n" + "A\u2033 B\u2122 1\u00bd \ufffd \U0001f600 e\u0301\t" * 50 + " \n"
    plan = chunk_text(value, CharacterTokenizer(), profile=PROFILE)
    verify_coverage(value, plan["children"], plan["parameters"])
    for c in plan["children"]:
        assert value.encode("utf-8")[c["byte_start"]:c["byte_end"]].decode("utf-8") == c["child_text"]
    assert "ORIGINAL_CHARACTER_UNKNOWN" in plan["review_flags"]


def test_character_cap_can_shorten_token_windows_without_unsafe_tail_merge():
    params = {"max_tokens": 320, "requested_overlap": 64, "max_chars": 10}
    plan = chunk_text("abcdef" * 10, CharacterTokenizer(), profile=PROFILE, parameters=params)
    assert any(c["short_window_overlap"] for c in plan["children"])
    assert all(len(c["child_text"]) <= 10 for c in plan["children"])
    verify_coverage("abcdef" * 10, plan["children"], params)


class OmissionTokenizer(CharacterTokenizer):
    def __call__(self, value, **kwargs):
        pairs = [(i, c) for i, c in enumerate(value) if c != "\u00bd"]
        return {"input_ids": [ord(c) + 1 for _, c in pairs],
                "offset_mapping": [(i, i + 1) for i, _ in pairs]}


def test_tokenizer_omission_is_preserved_and_never_cleared():
    value = "1\u00bd acres"
    plan = chunk_text(value, OmissionTokenizer(), profile=PROFILE)
    assert plan["children"][0]["child_text"] == value
    assert "NON_WHITESPACE_TOKENIZER_GAP" in plan["review_flags"]
    assert "DECODE_DIFFERENCE_REQUIRES_REVIEW" in plan["review_flags"]
    assert plan["representation_status"] == "REVIEW_REQUIRED"


class InvalidOffsets(CharacterTokenizer):
    def __init__(self, offsets):
        self.offsets = offsets

    def __call__(self, value, **kwargs):
        return {"input_ids": [1] * len(self.offsets), "offset_mapping": self.offsets}


@pytest.mark.parametrize("offsets", [[], [(0, 0)], [(0, 2), (1, 2)], [(-1, 1)], [(0, 99)], [(True, 2)]])
def test_unsupported_offsets_fail_closed(offsets):
    if offsets == [(0, 2), (1, 2)]:
        # Preserve this old regression input, but A5R explicitly makes its
        # monotone partial overlap valid. Its uncovered 'c' is still retained.
        plan = chunk_text("abc", InvalidOffsets(offsets), profile=PROFILE)
        assert plan["children"][0]["child_text"] == "abc"
        return
    with pytest.raises(SchemaError):
        chunk_text("abc", InvalidOffsets(offsets), profile=PROFILE)


def test_byte_offset_profile_and_slow_tokenizer_rejected():
    with pytest.raises(SchemaError, match="UNSUPPORTED_OFFSET_UNIT"):
        chunk_text("\u00e9", CharacterTokenizer(), profile=TokenizerProfile(scope="SYNTHETIC_ONLY", offset_unit="BYTE"))
    t = CharacterTokenizer()
    t.is_fast = False
    with pytest.raises(SchemaError, match="FAST_OFFSETS_REQUIRED"):
        chunk_text("abc", t, profile=PROFILE)


def test_long_single_token_cannot_be_silently_cut():
    class OneToken(CharacterTokenizer):
        def __call__(self, value, **kwargs):
            return {"input_ids": [1], "offset_mapping": [(0, len(value))]}
    with pytest.raises(SchemaError, match="UNSPLITTABLE_WITHIN_BUDGET"):
        chunk_text("x" * 1501, OneToken(), profile=PROFILE)


@pytest.mark.parametrize("value", ["", " \r\n\t", None, True, "\ud800"])
def test_invalid_parent_text(value):
    with pytest.raises(SchemaError):
        chunk_text(value, CharacterTokenizer(), profile=PROFILE)


@pytest.mark.parametrize("kind", ["text", "slot", "negative_parent", "lineage", "duplicate", "date", "hash", "missing", "grade", "review", "authority", "order", "byte"])
def test_pool_tampering_rejected(kind):
    q, f = question()
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    c = out["candidates"][0]
    if kind == "text":
        c["child_text"] += "changed"
    elif kind == "slot":
        c["candidate_slot"] = True
    elif kind == "negative_parent":
        c["parent_slot"] = -1
    elif kind == "lineage":
        c["parent_occurrence_id"] = "unrelated"
    elif kind == "duplicate":
        out["candidates"].append(deepcopy(c))
    elif kind == "date":
        c["publication_time"]["raw_value"] = "invented"
    elif kind == "hash":
        c["child_text_sha256"] = "0" * 64
    elif kind == "missing":
        del c["relevance_grade"]
    elif kind == "grade":
        c["relevance_grade"] = True
    elif kind == "review":
        c["relevance_grade"] = 2
    elif kind == "authority":
        c["scientific_approval"] = "APPROVED"
    elif kind == "order":
        out["candidates"].reverse()
    else:
        c["byte_end"] += 1
    with pytest.raises(SchemaError):
        validate_pool(out, f, original_question=q)


def test_known_grade_requires_review_references_but_is_not_approval():
    q, f = question()
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    c = out["candidates"][0]
    c.update(relevance_grade=1, semantic_review_status="REVIEWED_PROVISIONAL",
             semantic_review_refs=["synthetic-review-not-real-authority"])
    assert validate_pool(out, f)["scientific_approval"] == "NOT_GRANTED"


def test_authoritative_parent_binding_catches_coherent_rehash():
    q, f = question()
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    out["original_question"] = "altered but rehashed"
    out["original_qa_record"]["question"] = out["original_question"]
    out["question_text_sha256"] = text_sha256(out["original_question"])
    with pytest.raises(SchemaError, match="AUTHORITATIVE_SOURCE_DRIFT"):
        validate_pool(out, f, original_question=q)


def test_no_implicit_tokenizer_load_or_execution_entrypoint():
    import ast
    p = ROOT / "src/eval/chunk_streamingqa_pools_v2.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    imports = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not any(x in " ".join(imports) for x in ["transformers", "torch", "retrieval", "generation"])
    assert "from_pretrained" not in p.read_text(encoding="utf-8")


@pytest.mark.parametrize("query_id", [9, 25, 67, 73, 94, 99])
def test_six_preserved_parent_regressions_without_real_tokenizer_claims(query_id):
    # Only the six diagnostic parent strings; never the full 100-question pool.
    d = json.loads((ROOT / "audits/p0_s3b_v1/diagnostics.json").read_text(encoding="utf-8"))
    case, = [c for c in d["cases"] if c["query_id"] == query_id]
    value = case["parent"]["text"]
    assert text_sha256(value) == case["parent_text_sha256"]
    plan = chunk_text(value, CharacterTokenizer(), profile=PROFILE)
    verify_coverage(value, plan["children"], plan["parameters"])
    assert plan["tokenizer"]["scope"] == "SYNTHETIC_ONLY"
    assert plan["backend_verification"] == "UNVERIFIED"
    assert case["P0_S3_disposition"] == "REMAINS_BLOCKED_NO_RELABELING"


@pytest.mark.parametrize("kind", ["offset", "token_count", "overlap", "window", "legacy_flag", "tokenizer", "audit_flags"])
def test_saved_token_and_config_audits_cannot_be_altered(kind):
    q, f = question()
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    c = out["candidates"][0]
    if kind == "offset":
        c["tokenization"]["offsets"][0] = [0, 999]
    elif kind == "token_count":
        c["standalone_token_count"] -= 1
    elif kind == "overlap":
        c["actual_parent_token_overlap_to_next"] = 0
    elif kind == "window":
        c["parent_token_start"] = 1
    elif kind == "legacy_flag":
        c["is_source_document"] = True
    elif kind == "tokenizer":
        out["parent_chunk_audits"][0]["tokenizer"]["revision"] = "unapproved"
    else:
        out["parent_chunk_audits"][0]["review_flags"] = ["invented"]
    with pytest.raises(SchemaError):
        validate_pool(out, f, original_question=q)


def test_standalone_retokenization_can_reduce_the_parent_window():
    class BoundaryTokenizer(CharacterTokenizer):
        def __call__(self, value, **kwargs):
            stride = 2 if len(value) > 640 else 1
            return {"input_ids": [ord(value[i]) + 1 for i in range(0, len(value), stride)],
                    "offset_mapping": [(i, min(i + stride, len(value))) for i in range(0, len(value), stride)]}
    value = "x" * 1000
    plan = chunk_text(value, BoundaryTokenizer(), profile=PROFILE)
    assert len(plan["parent_tokenization"]["input_ids"]) == 500
    assert plan["children"][0]["parent_token_end"] == 160
    assert plan["children"][0]["standalone_token_count"] == 320
    verify_coverage(value, plan["children"], plan["parameters"])


def test_missing_profile_or_wrong_revision_never_loads_an_alternative():
    with pytest.raises(SchemaError, match="TOKENIZER_PROFILE_REQUIRED"):
        chunk_text("abc", CharacterTokenizer(), profile=None)
    with pytest.raises(SchemaError, match="TOKENIZER_TARGET"):
        chunk_text("abc", CharacterTokenizer(), profile=TokenizerProfile(revision="main"))
    with pytest.raises(SchemaError, match="MUTABLE_ASSET_MANIFEST"):
        chunk_text("abc", CharacterTokenizer(), profile=TokenizerProfile(asset_hashes=[]))


@pytest.mark.parametrize("grade", [None, 0.0, True, -1, 3, "unknown", [], "UNKNOWN "])
def test_invalid_relevance_types_and_vocabulary(grade):
    q, f = question(value="one short parent")
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    out["candidates"][0]["relevance_grade"] = grade
    with pytest.raises(SchemaError, match="INVALID_RELEVANCE_GRADE"):
        validate_pool(out, f)


def test_no_answer_lexical_matching_or_fallback_promotion():
    q, f = question(value="Paris is not the answer. Unrelated context.")
    out = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    assert all(c["relevance_grade"] == "UNKNOWN" for c in out["candidates"])
    q["parents"][0]["historical_relevance_flag"] = False
    q["parents"][0]["original_source_record"]["is_source_document"] = False
    again = chunk_question(q, f, CharacterTokenizer(), profile=PROFILE)
    assert all(c["relevance_grade"] == "UNKNOWN" for c in again["candidates"])


class RepeatedSpanTokenizer(CharacterTokenizer):
    """Synthetic multi-ID Unicode spans; never presented as the real BGE."""
    def __init__(self, *, repeats=3, skip_whitespace=False):
        self.repeats = repeats
        self.skip_whitespace = skip_whitespace

    def __call__(self, value, **kwargs):
        ids, offsets = [], []
        for i, char in enumerate(value):
            if self.skip_whitespace and char.isspace():
                continue
            count = self.repeats if char in "\u2122\u2033\u00bd\ufffd" else 1
            ids.extend([ord(char) + 1] * count)
            offsets.extend([(i, i + 1)] * count)
        return {"input_ids": ids, "offset_mapping": offsets}


class SlidingSpanTokenizer(CharacterTokenizer):
    def __call__(self, value, **kwargs):
        return {"input_ids": [ord(c) + 1 for c in value],
                "offset_mapping": [(i, min(i + 2, len(value))) for i in range(len(value))]}


class GrowingSpanTokenizer(CharacterTokenizer):
    def __call__(self, value, **kwargs):
        return {"input_ids": [ord(c) + 1 for c in value],
                "offset_mapping": [(0, i + 1) for i in range(len(value))]}


def assert_advancing_exact_plan(value, plan):
    children = plan["children"]
    verify_coverage(value, children, plan["parameters"])
    assert all(0 < len(c["child_text"]) <= 1500 and c["standalone_token_count"] <= 320
               for c in children)
    assert all(a["char_start"] < b["char_start"] and a["char_end"] < b["char_end"]
               and b["char_start"] <= a["char_end"] for a, b in zip(children, children[1:]))
    assert all(c["child_text"] == value[c["char_start"]:c["char_end"]] for c in children)
    assert all(c["child_text"].encode("utf-8") == value.encode("utf-8")[c["byte_start"]:c["byte_end"]]
               for c in children)
    assert plan["backend_verification"] == "UNVERIFIED"


@pytest.mark.parametrize("symbol", ["\u2122", "\u2033", "\u00bd", "\ufffd"])
def test_repeated_unicode_offsets_preserve_characters_and_audits(symbol):
    value = ("Left " + symbol + " right\r\n") * 60
    q, f = question(value=value)
    tokenizer = RepeatedSpanTokenizer(skip_whitespace=True)
    plan = chunk_text(value, tokenizer, profile=PROFILE)
    assert_advancing_exact_plan(value, plan)
    assert plan == chunk_text(value, tokenizer, profile=PROFILE)
    offsets = plan["parent_tokenization"]["offsets"]
    assert any(a == b for a, b in zip(offsets, offsets[1:]))
    assert all(not gap["non_whitespace"] for gap in plan["parent_tokenization"]["gaps"])
    assert "NON_WHITESPACE_TOKENIZER_GAP" not in plan["review_flags"]
    out = chunk_question(q, f, tokenizer, profile=PROFILE)
    assert validate_pool(out, f, original_question=q)["mechanical_validation"] == "PASS"


def test_partial_overlaps_preserve_distinct_token_and_character_overlap():
    value = "abcde" * 180
    tokenizer = SlidingSpanTokenizer()
    plan = chunk_text(value, tokenizer, profile=PROFILE)
    assert_advancing_exact_plan(value, plan)
    first = plan["children"][0]
    assert first["actual_parent_token_overlap_to_next"] == 64
    assert first["actual_character_overlap_to_next"] == 65
    assert first["standalone_token_count"] == 320
    assert plan == chunk_text(value, tokenizer, profile=PROFILE)
    q, f = question(value=value)
    validate_pool(chunk_question(q, f, tokenizer, profile=PROFILE), f, original_question=q)


def test_identical_offsets_at_boundary_reduce_overlap_instead_of_stalling():
    value = "\u2122\u2033\u00bd\ufffd"
    params = {"max_tokens": 3, "requested_overlap": 2, "max_chars": 1500}
    tokenizer = RepeatedSpanTokenizer()
    plan = chunk_text(value, tokenizer, profile=PROFILE, parameters=params)
    assert_advancing_exact_plan(value, plan)
    assert [c["child_text"] for c in plan["children"]] == list(value)
    assert all(c["actual_parent_token_overlap_to_next"] == 0 for c in plan["children"])
    assert all(c["short_window_overlap"] for c in plan["children"][:-1])
    assert all(c["requested_overlap"] == 2 for c in plan["children"])
    q, f = question(value=value)
    validate_pool(chunk_question(q, f, tokenizer, profile=PROFILE, parameters=params), f, original_question=q)


def test_constant_starts_growing_ends_use_advancing_source_end_fallback():
    value = "abcde" * 180
    tokenizer = GrowingSpanTokenizer()
    plan = chunk_text(value, tokenizer, profile=PROFILE)
    assert_advancing_exact_plan(value, plan)
    assert all(c["actual_parent_token_overlap_to_next"] == 0 for c in plan["children"])
    assert plan == chunk_text(value, tokenizer, profile=PROFILE)
    q, f = question(value=value)
    validate_pool(chunk_question(q, f, tokenizer, profile=PROFILE), f, original_question=q)


def test_whitespace_gaps_are_diagnostics_not_deleted_source():
    value = " \t\r\nalpha \t beta\r\n "
    plan = chunk_text(value, RepeatedSpanTokenizer(skip_whitespace=True), profile=PROFILE)
    assert_advancing_exact_plan(value, plan)
    assert plan["parent_tokenization"]["gaps"]
    assert all(not g["non_whitespace"] for g in plan["parent_tokenization"]["gaps"])
    assert "NON_WHITESPACE_TOKENIZER_GAP" not in plan["review_flags"]
    assert plan["children"][0]["child_text"] == value


@pytest.mark.parametrize("offsets", [[(1, 2), (0, 3)], [(0, 3), (1, 2)],
                                     [(0, 1), (1, 1)], [(0, 1), (1, 4)],
                                     [(0, 1), (1.0, 2)], [(0, 1), (True, 2)]])
def test_backward_starts_or_ends_and_malformed_spans_still_rejected(offsets):
    with pytest.raises(SchemaError, match="UNSUPPORTED_OFFSET_MAPPING"):
        chunk_text("abc", InvalidOffsets(offsets), profile=PROFILE)


def test_unfittable_repeated_single_character_fails_instead_of_looping():
    # One character needs 321 synthetic tokens: no legal nonempty slice fits.
    with pytest.raises(SchemaError, match="UNSPLITTABLE_WITHIN_BUDGET"):
        chunk_text("\u2122", RepeatedSpanTokenizer(repeats=321), profile=PROFILE)


def test_partial_spans_and_whitespace_gaps_obey_default_character_cap():
    import re

    class WordSpans(CharacterTokenizer):
        def __call__(self, value, **kwargs):
            spans = [m.span() for m in re.finditer(r"\S+", value)]
            return {"input_ids": [1] * (2 * len(spans)),
                    "offset_mapping": [span for span in spans for _ in range(2)]}

    value = ("a_long_synthetic_word " * 200).rstrip()
    plan = chunk_text(value, WordSpans(), profile=PROFILE)
    assert_advancing_exact_plan(value, plan)
    assert len(plan["children"]) > 1
    assert max(len(c["child_text"]) for c in plan["children"]) > 1400


@pytest.mark.parametrize("field", ["actual_character_overlap_to_next", "actual_parent_token_overlap_to_next"])
def test_overlap_receipt_tampering_rejected(field):
    q, f = question(value="abcde" * 180)
    out = chunk_question(q, f, SlidingSpanTokenizer(), profile=PROFILE)
    out["candidates"][0][field] += 1
    with pytest.raises(SchemaError, match="OVERLAP_AUDIT"):
        validate_pool(out, f)


def test_saved_backward_offsets_and_stale_boundary_policy_are_rejected():
    q, f = question(value="abcde" * 180)
    out = chunk_question(q, f, SlidingSpanTokenizer(), profile=PROFILE)
    bad = deepcopy(out)
    bad["parent_chunk_audits"][0]["parent_tokenization"]["offsets"][1] = [0, 1]
    with pytest.raises(SchemaError, match="TOKEN_AUDIT_OFFSET"):
        validate_pool(bad, f)
    del out["parent_chunk_audits"][0]["offset_policy"]
    with pytest.raises(SchemaError, match="UNSUPPORTED_OFFSET_POLICY"):
        validate_pool(out, f)
