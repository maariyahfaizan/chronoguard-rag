"""A9 identity regressions on fictional inputs; no real-pool validation.

Reuse the already-reviewed synthetic offset tokenizer. No assets, models,
retrieval, metrics or scientific relevance labels are produced by these tests.
"""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json

import pytest

from test_streamingqa_chunking_v2 import CharacterTokenizer
from src.eval import chunk_streamingqa_pools_v2 as chunker
from src.eval import week4_v2_schema as schema


PROFILE = chunker.TokenizerProfile(scope="SYNTHETIC_ONLY")


def synthetic_inputs(rows):
    """Rows contain (opaque ID, text) entries; all positions come from fixtures."""
    qids = [f"synthetic-a9-question-{i}" for i in range(len(rows))]
    frame = schema.make_frame(qids, "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    questions = []
    for row, entries in enumerate(rows):
        qa = {"qa_id": qids[row], "question": "Fictional identity check?",
              "answers": ["fixture-only reference"], "question_ts": 1609459200}
        parents = {"query": qa["question"], "gold_answer": qa["answers"][0],
                   "gold_aliases": qa["answers"][:], "question_ts": qa["question_ts"],
                   "candidates": [{"doc_id": doc, "text": text,
                                   "timestamp": "2020-01-01T00:00:00+00:00",
                                   "is_source_document": True,
                                   "extra_metadata": {"tags": ["retained"], "date_basis": "recorded_only"}}
                                  for doc, text in entries]}
        questions.append(schema.make_question(qa, parents, frame, row))
    return questions, frame


def construct(rows, *, parameters=None):
    originals, frame = synthetic_inputs(rows)
    records = [chunker.chunk_question(q, frame, CharacterTokenizer(), profile=PROFILE,
                                     parameters=parameters) for q in originals]
    return records, originals, frame


def test_exact_serialization_format_and_hash_inputs():
    doc = " \u00e9/raw\x00\x01identifier_0007\n "
    parent_hash = schema.text_sha256("Exact \u2122 \u00bd text\r\n")
    source = schema.parent_source_identity(doc, parent_hash)

    def expected(domain, *parts):
        raw = json.dumps([domain, *parts], ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        return domain + ":" + hashlib.sha256(raw).hexdigest()

    assert source == expected("sqa-parent-source-a9-v1", doc, parent_hash)
    child_hash, config = schema.text_sha256("Exact"), "4" * 64
    child = schema.child_identity(source, child_hash, 0, 5, chunking_config_sha256=config)
    assert child == expected("sqa-child-a9-v1", source, child_hash, 0, 5, config)
    assert schema.child_occurrence_identity(7, 12, child) == expected(
        "sqa-child-occurrence-a9-v1", 7, 12, child)
    assert schema.identity("fixture", "a|b", "c") != schema.identity("fixture", "a", "b|c")
    assert schema.identity("fixture", "\x00", "x") != schema.identity("fixture", "", "\x00x")


def test_repeated_source_preserves_occurrences_metadata_and_unknown_relevance():
    doc = "  original\x00\x01/source\u2122-without-suffix  "
    records, originals, frame = construct([[(doc, "same text"), (doc, "same text")]])
    q, = records
    first, second = q["parents"]
    a, b = q["candidates"]
    assert first["parent_source_id"] == second["parent_source_id"]
    assert first["parent_occurrence_id"] != second["parent_occurrence_id"]
    assert a["canonical_child_id"] == b["canonical_child_id"]
    assert a["child_occurrence_id"] != b["child_occurrence_id"]
    assert first["original_parent_passage_id"].encode("utf-8") == doc.encode("utf-8")
    assert first["claimed_source_document_id"] == doc  # NOT a split article key
    assert a["original_parent_passage_id"] == doc
    assert first["original_source_record"]["timestamp"] == "2020-01-01T00:00:00+00:00"
    assert first["original_source_record"]["extra_metadata"] == {
        "tags": ["retained"], "date_basis": "recorded_only"}
    assert a["publication_time"] == first["publication_time"]
    assert a["relevance_grade"] == b["relevance_grade"] == "UNKNOWN"
    assert all("is_source_document" not in c for c in q["candidates"])
    report = chunker.validate_pool(q, frame, original_question=originals[0])
    assert report["unique_canonical_children"] == 1
    assert report["child_occurrences"] == 2
    assert report["scientific_approval"] == "NOT_GRANTED"


def test_same_text_different_opaque_sources_never_merges():
    records, _, _ = construct([[('id with no suffix', 'identical'), ('id with no suffix ', 'identical')]])
    parents = records[0]["parents"]
    children = records[0]["candidates"]
    assert parents[0]["parent_text_sha256"] == parents[1]["parent_text_sha256"]
    assert parents[0]["parent_source_id"] != parents[1]["parent_source_id"]
    assert children[0]["canonical_child_id"] != children[1]["canonical_child_id"]


def test_same_doc_id_different_text_is_rejected_not_silently_versioned():
    assert schema.parent_source_identity("same-id", schema.text_sha256("A")) != schema.parent_source_identity(
        "same-id", schema.text_sha256("B"))
    with pytest.raises(schema.SchemaError, match="PARENT_IDENTITY_COLLISION"):
        synthetic_inputs([[('same-id', 'A'), ('same-id', 'B')]])
    records, _, frame = construct([[('same-id', 'A')], [('same-id', 'B')]])
    with pytest.raises(schema.SchemaError, match="CROSS_QUESTION_PARENT_COLLISION"):
        chunker.validate_pool_records(records, frame)


def test_same_child_text_at_different_spans_has_distinct_canonical_identity():
    params = {"max_tokens": 2, "requested_overlap": 0, "max_chars": 1500}
    records, _, _ = construct([[('opaque', 'abab')]], parameters=params)
    a, b = records[0]["candidates"]
    assert a["child_text"] == b["child_text"] == "ab"
    assert a["child_text_sha256"] == b["child_text_sha256"]
    assert (a["char_start"], a["char_end"]) == (0, 2)
    assert (b["char_start"], b["char_end"]) == (2, 4)
    assert a["canonical_child_id"] != b["canonical_child_id"]


def test_same_canonical_child_different_question_and_candidate_positions():
    rows = [[('A', 'source'), ('B', 'source')],
            [('B', 'source'), ('A', 'source'), ('A', 'source')]]
    records, _, frame = construct(rows)
    a = records[0]["candidates"][0]
    b, c = records[1]["candidates"][1:]
    assert a["canonical_child_id"] == b["canonical_child_id"] == c["canonical_child_id"]
    assert len({x["child_occurrence_id"] for x in (a, b, c)}) == 3
    children = [child for q in records for child in q["candidates"]]
    assert len({child["child_occurrence_id"] for child in children}) == len(children)
    assert chunker.validate_pool_records(records, frame)["unique_canonical_children"] == 2
    repeated, _, _ = construct(rows)
    assert repeated == records


def test_chunk_configuration_is_part_of_canonical_identity_not_position():
    questions, frame = synthetic_inputs([[('A', 'same text')]])
    q, = questions
    a = chunker.chunk_question(q, frame, CharacterTokenizer(), profile=PROFILE)["candidates"][0]
    b = chunker.chunk_question(q, frame, CharacterTokenizer(), profile=replace(
        PROFILE, runtime_version="synthetic-profile-change"))["candidates"][0]
    assert a["child_text"] == b["child_text"]
    assert (a["char_start"], a["char_end"]) == (b["char_start"], b["char_end"])
    assert a["chunking_config_sha256"] != b["chunking_config_sha256"]
    assert a["canonical_child_id"] != b["canonical_child_id"]


@pytest.mark.parametrize("doc", ["\x00\x01", "article_01", "\t source \r\n", "\u00e9", "e\u0301"])
def test_identifiers_are_opaque_utf8_without_unicode_normalization(doc):
    source = schema.parent_source_identity(doc, schema.text_sha256("text"))
    assert schema.source_ids(doc, schema.text_sha256("text"))[0] == doc
    assert source == schema.parent_source_identity(doc, schema.text_sha256("text"))
    assert source != schema.parent_source_identity(doc + " ", schema.text_sha256("text"))
    assert schema.parent_source_identity("\u00e9", "1" * 64) != schema.parent_source_identity("e\u0301", "1" * 64)


@pytest.mark.parametrize("doc", [None, True, b"not decoded implicitly", "", "\ud800"])
def test_invalid_source_identifiers_fail_closed(doc):
    with pytest.raises(schema.SchemaError):
        schema.parent_source_identity(doc, "1" * 64)


@pytest.mark.parametrize("row,slot", [(True, 0), (0, True), (-1, 0), (0, -1), ("0", 0), (0, 0.0)])
def test_occurrence_position_types_and_ranges(row, slot):
    source = schema.parent_source_identity("id", "1" * 64)
    child = schema.child_identity(source, "2" * 64, 0, 1, chunking_config_sha256="3" * 64)
    with pytest.raises(schema.SchemaError):
        schema.child_occurrence_identity(row, slot, child)


@pytest.mark.parametrize("kind", ["child_hash", "parent_hash", "slice", "coherent_text_edit", "metadata"])
def test_invalid_slice_hash_and_metadata_bindings_are_rejected(kind):
    records, originals, frame = construct([[('id', 'source text')]])
    q = records[0]
    c = q["candidates"][0]
    if kind == "child_hash":
        c["child_text_sha256"] = "0" * 64
    elif kind == "parent_hash":
        q["parents"][0]["parent_text_sha256"] = "0" * 64
    elif kind == "slice":
        c["char_start"] = 1
    elif kind == "metadata":
        q["parents"][0]["original_source_record"]["timestamp"] = "altered"
    else:
        c["child_text"] = "edited text"
        c["child_text_sha256"] = schema.text_sha256(c["child_text"])
        c["canonical_child_id"] = schema.child_identity(c["parent_source_id"], c["child_text_sha256"],
            c["char_start"], c["char_end"], chunking_config_sha256=c["chunking_config_sha256"])
        c["child_occurrence_id"] = schema.child_occurrence_identity(0, 0, c["canonical_child_id"])
    with pytest.raises(schema.SchemaError):
        chunker.validate_pool(q, frame, original_question=originals[0])


def test_supplied_parent_text_hash_cannot_disagree_with_source_text():
    qids = ['synthetic-hash']
    frame = schema.make_frame(qids, "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    qa = {"qa_id": qids[0], "question": "Fictional?", "answers": ['reference'], "question_ts": 0}
    record = {"query": qa['question'], "gold_answer": 'reference', "gold_aliases": ['reference'],
              "question_ts": 0, "candidates": [{"doc_id": 'opaque', "text": 'exact text',
                  "text_sha256": "0" * 64, "timestamp": None, "is_source_document": False}]}
    with pytest.raises(schema.SchemaError, match="SOURCE_TEXT_HASH"):
        schema.make_question(qa, record, frame, 0)


def test_forced_child_digest_collision_does_not_merge_equal_text_different_spans(monkeypatch):
    questions, frame = synthetic_inputs([[('id', 'abab')]])
    monkeypatch.setattr(chunker, "child_identity", lambda *a, **kw: schema.CHILD_DOMAIN + ":" + "f" * 64)
    with pytest.raises(schema.SchemaError, match="CHILD_IDENTITY_COLLISION"):
        chunker.chunk_question(questions[0], frame, CharacterTokenizer(), profile=PROFILE,
                              parameters={"max_tokens": 2, "requested_overlap": 0, "max_chars": 1500})


def test_forced_parent_digest_collision_does_not_merge_sources(monkeypatch):
    monkeypatch.setattr(schema, "parent_source_identity", lambda *a: schema.PARENT_SOURCE_DOMAIN + ":" + "f" * 64)
    with pytest.raises(schema.SchemaError, match="PARENT_IDENTITY_COLLISION"):
        synthetic_inputs([[('A', 'same'), ('B', 'same')]])


def test_duplicate_occurrence_digest_is_rejected(monkeypatch):
    questions, frame = synthetic_inputs([[('A', 'same'), ('A', 'same')]])
    monkeypatch.setattr(chunker, "child_occurrence_identity", lambda *a: schema.CHILD_OCCURRENCE_DOMAIN + ":" + "f" * 64)
    with pytest.raises(schema.SchemaError, match="DUPLICATE_CHILD_OCCURRENCE"):
        chunker.chunk_question(questions[0], frame, CharacterTokenizer(), profile=PROFILE)


def test_stale_identity_records_and_old_positional_api_cannot_be_silently_reused():
    records, _, frame = construct([[('id', 'text')]])
    q = deepcopy(records[0])
    q["identity_version"] = "pre-A9"
    with pytest.raises(schema.SchemaError, match="IDENTITY_VERSION"):
        chunker.validate_pool(q, frame)
    source = schema.parent_source_identity('id', schema.text_sha256('text'))
    with pytest.raises(TypeError):
        schema.child_identity(source, '1' * 64, 0, 1, '2' * 64)
