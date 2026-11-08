"""Pure construction/schema tests: no retrieval, model loading or metrics."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.eval.week4_v2_schema import (
    SchemaError, canonical_bytes, child_identity, child_occurrence_identity,
    execution_preflight, identity, load_config, make_frame, make_question,
    source_ids, text_sha256, validate_config, validate_frame,
    validate_frame_records, validate_question, verify_source_files, validate_against_sources,
)

ROOT = Path(__file__).resolve().parents[1]


def fixture(count=1, duplicate=False):
    ids = [f"synthetic-schema-{i}" for i in range(count)]
    frame = make_frame(ids, "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    qa = {"qa_id": ids[0], "question": "Which fictional city?", "answers": ["Paris", "City of Paris"],
          "question_ts": 1609459200}
    candidate = {"doc_id": "article\x00\x01original_2", "text": "Paris is a city.",
                 "timestamp": "2020-01-01T00:00:00Z", "is_source_document": True}
    pool = {"query": qa["question"], "gold_answer": "Paris", "gold_aliases": qa["answers"][:],
            "question_ts": qa["question_ts"], "candidates": [candidate]}
    if duplicate:
        pool["candidates"].append(deepcopy(candidate))
    return qa, pool, frame


def test_identities_and_occurrence_distinction_preserve_control_characters():
    qa, pool, frame = fixture(duplicate=True)
    before = deepcopy((qa, pool, frame))
    q = make_question(qa, pool, frame, 0)
    assert (qa, pool, frame) == before
    a, b = q["parents"]
    assert "\x00\x01" in a["original_parent_passage_id"]
    assert a["canonical_parent_passage_id"] == b["canonical_parent_passage_id"]
    assert a["parent_occurrence_id"] != b["parent_occurrence_id"]
    cid = child_identity(a["parent_source_id"], text_sha256("Paris"), 0, 5, chunking_config_sha256="4" * 64)
    assert cid == child_identity(b["parent_source_id"], text_sha256("Paris"), 0, 5, chunking_config_sha256="4" * 64)
    assert child_occurrence_identity(0, 0, cid) != child_occurrence_identity(0, 1, cid)
    assert cid != child_identity(a["parent_source_id"], text_sha256("aris"), 1, 5, chunking_config_sha256="4" * 64)
    q["original_answers"].append("must not mutate source")
    assert qa["answers"] == ["Paris", "City of Paris"]


@pytest.mark.parametrize("value", [0.5, float("nan"), {1: "bad"}, ("not", "a list"), b"bytes"])
def test_identity_serialization_rejects_unsupported_types(value):
    with pytest.raises(SchemaError):
        canonical_bytes(value)


def test_hashes_are_unicode_exact_and_order_deterministic():
    assert text_sha256("\u00bd") != text_sha256("1/2")
    assert text_sha256("a\r\nb") != text_sha256("a\nb")
    assert canonical_bytes({"b": 1, "a": 2}) == canonical_bytes({"a": 2, "b": 1})
    code = "from src.eval.week4_v2_schema import identity; print(identity('test', 'abc', 1))"
    actual = []
    for seed in ("1", "97"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        actual.append(subprocess.check_output([sys.executable, "-B", "-c", code], cwd=ROOT, env=env, text=True))
    assert actual[0] == actual[1] == identity("test", "abc", 1) + "\n"


@pytest.mark.parametrize("doc", ["", "missing-suffix", "article_01", "article_-1", "_0", True])
def test_noncanonical_or_missing_source_ids_rejected(doc):
    # A9 treats nonempty doc_ids as opaque, including strings that would not
    # parse under the old article/passagenumber grammar. Preserve those cases.
    if type(doc) is str and doc:
        assert source_ids(doc, "1" * 64)[0] == doc
        return
    with pytest.raises(SchemaError):
        source_ids(doc, "1" * 64)


@pytest.mark.parametrize("field,value,code", [
    ("parent_text_sha256", "0" * 64, "PARENT_TEXT_HASH"),
    ("parent_slot", True, "PARENT_OCCURRENCE"),
    ("canonical_document_id", "wrong", "PARENT_IDENTITY"),
    ("source_authentication", "AUTHENTICATED", "UNSUPPORTED_PROVENANCE_PROMOTION"),
])
def test_parent_field_drift_rejected(field, value, code):
    qa, pool, frame = fixture()
    q = make_question(qa, pool, frame, 0)
    q["parents"][0][field] = value
    with pytest.raises(SchemaError, match=code):
        validate_question(q, frame)


@pytest.mark.parametrize("key,value", [("text", "different text"), ("timestamp", None),
                                      ("timestamp", "2021-01-01Z")])
def test_conflicting_same_parent_identity_blocks_pool(key, value):
    qa, pool, frame = fixture(duplicate=True)
    pool["candidates"][1][key] = value
    with pytest.raises(SchemaError, match="PARENT_IDENTITY_COLLISION"):
        make_question(qa, pool, frame, 0)


@pytest.mark.parametrize("key", ["qa_id", "question", "answers", "question_ts"])
def test_missing_original_question_fields(key):
    qa, pool, frame = fixture()
    del qa[key]
    with pytest.raises(SchemaError, match="MISSING_QA_FIELDS"):
        make_question(qa, pool, frame, 0)


def test_original_alias_order_and_question_time_cannot_drift():
    qa, pool, frame = fixture()
    pool["gold_aliases"].reverse()
    with pytest.raises(SchemaError, match="ORIGINAL_KEY_DRIFT"):
        make_question(qa, pool, frame, 0)
    pool["gold_aliases"].reverse()
    pool["question_ts"] += 1
    with pytest.raises(SchemaError, match="ORIGINAL_KEY_DRIFT"):
        make_question(qa, pool, frame, 0)


def test_unknown_dates_stay_unknown_and_unapproved():
    qa, pool, frame = fixture()
    pool["candidates"][0]["timestamp"] = None
    q = make_question(qa, pool, frame, 0)
    assert q["parents"][0]["publication_time"]["raw_value"] is None
    assert q["parents"][0]["publication_time"]["status"] == "UNKNOWN"
    assert q["scientific_approval"] == "NOT_GRANTED"
    q["parents"][0]["publication_time"]["parsed_utc"] = "invented"
    with pytest.raises(SchemaError, match="UNSUPPORTED_TIME_PROMOTION"):
        validate_question(q, frame)


def test_frame_validation_no_missing_duplicate_or_reordered_questions():
    qa, pool, frame = fixture()
    q = make_question(qa, pool, frame, 0)
    validate_frame_records([q], frame)
    with pytest.raises(SchemaError, match="FRAME_COMPLETENESS"):
        validate_frame_records([], frame)
    with pytest.raises(SchemaError, match="DUPLICATE_QUESTION_ID"):
        make_frame(["synthetic-q", "synthetic-q"], "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    altered = deepcopy(frame)
    altered["frame_id"] = "sqa-frame-v2:" + "0" * 64
    with pytest.raises(SchemaError, match="FRAME_IDENTITY_MISMATCH"):
        validate_frame(altered)
    with pytest.raises(SchemaError, match="SYNTHETIC_NAMESPACE"):
        make_frame(["eval-real"], "1" * 64, "2" * 64, "3" * 64, synthetic=True)
    with pytest.raises(SchemaError, match="FIXED_FRAME_REQUIRES_100"):
        make_frame(["eval-real"], "1" * 64, "2" * 64, "3" * 64)


def test_fixed_frame_definition_requires_exactly_100_without_building_pools():
    f = make_frame([f"fictional-frame-{i}" for i in range(100)], "1" * 64, "2" * 64, "3" * 64)
    validate_frame(f)
    f["question_ids"].reverse()
    with pytest.raises(SchemaError, match="FRAME_IDENTITY_MISMATCH"):
        validate_frame(f)


def test_checked_in_config_opt_in_and_targeted_source_hashes():
    c = load_config(ROOT / "configs/streamingqa_week4_v2.yaml")
    assert c["enabled_by_default"] is False
    assert len(verify_source_files(c, ROOT)) == 3  # read-only file hashes, no pool conversion
    with pytest.raises(SchemaError, match="UNVERIFIED_TOKENIZER"):
        execution_preflight(c)


@pytest.mark.parametrize("kind", ["missing", "unknown", "limits", "seed", "runtime", "approval", "source_hash"])
def test_configuration_fails_closed(kind):
    c = load_config(ROOT / "configs/streamingqa_week4_v2.yaml")
    if kind == "missing":
        del c["reproducibility"]
    elif kind == "unknown":
        c["run_now"] = True
    elif kind == "limits":
        c["chunking"]["max_tokens"] = 321
    elif kind == "seed":
        c["reproducibility"]["proposed_seed"] = True
    elif kind == "runtime":
        c["reproducibility"]["actual_runtime"] = "guessed"
    elif kind == "approval":
        c["scientific_validation"] = "APPROVED"
    else:
        c["frame"]["sample_sha256"] = "bad"
    with pytest.raises(SchemaError):
        validate_config(c)


def test_caller_supplied_runtime_flags_never_authorize_execution():
    c = load_config(ROOT / "configs/streamingqa_week4_v2.yaml")
    c["chunking"].update(tokenizer_assets_sha256={"tokenizer.json": "1" * 64},
                         tokenizer_runtime_version="caller assertion", offset_verification="VERIFIED")
    with pytest.raises(SchemaError, match="EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED"):
        execution_preflight(c)


def test_cyclic_mutable_container_rejected_without_recursion():
    data = []
    data.append(data)
    with pytest.raises(SchemaError, match="CYCLIC_CONTAINER"):
        canonical_bytes(data)


def test_original_upstream_metadata_preserved_without_authentication():
    qa, pool, frame = fixture()
    qa.update(evidence_id="recorded-source-only", evidence_ts=1.25,
              answers_additional=["kept but not promoted"], recent_or_past="recent")
    q = make_question(qa, pool, frame, 0)
    assert q["original_qa_record"] == qa
    q["original_qa_record"]["answers_additional"].append("local mutation")
    assert qa["answers_additional"] == ["kept but not promoted"]
    assert q["parents"][0]["source_authentication"] == "NOT_AUTHENTICATED"


def test_authoritative_rows_detect_fully_rehashed_source_change():
    qa, pool, frame = fixture()
    altered = deepcopy(pool)
    altered["candidates"][0]["text"] = "coherently rehashed but unauthorized text"
    q = make_question(qa, altered, frame, 0)
    with pytest.raises(SchemaError, match="AUTHORITATIVE_SOURCE_DRIFT"):
        validate_against_sources(q, frame, qa, pool)


def test_yaml_duplicate_keys_are_not_silently_overwritten(monkeypatch):
    from io import StringIO
    original = (ROOT / "configs/streamingqa_week4_v2.yaml").read_text(encoding="utf-8")
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO(original + "\nschema_version: replaced\n"))
    with pytest.raises(SchemaError, match="DUPLICATE_CONFIG_KEY"):
        load_config("not-read-from-disk.yaml")


def test_source_hash_mismatch_is_not_schema_validity_or_authentication():
    c = load_config(ROOT / "configs/streamingqa_week4_v2.yaml")
    c["frame"]["sample_sha256"] = "0" * 64
    with pytest.raises(SchemaError, match="SOURCE_FILE_HASH"):
        verify_source_files(c, ROOT)


def test_malformed_upstream_mutable_metadata_is_rejected():
    qa, pool, f = fixture()
    q = make_question(qa, pool, f, 0)
    q["original_qa_record"]["metadata"] = float("nan")
    with pytest.raises(SchemaError, match="INVALID_ORIGINAL_QA_RECORD"):
        validate_question(q, f)


def test_parent_collision_cannot_hide_in_another_question():
    qa, pool, frame = fixture(count=2)
    first = make_question(qa, pool, frame, 0)
    qa["qa_id"] = frame["question_ids"][1]
    pool["candidates"][0]["text"] = "same claimed source, conflicting content"
    second = make_question(qa, pool, frame, 1)
    with pytest.raises(SchemaError, match="CROSS_QUESTION_PARENT_COLLISION"):
        validate_frame_records([first, second], frame)
