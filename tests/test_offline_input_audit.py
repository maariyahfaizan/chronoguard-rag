import copy
import json

import pytest

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, build_conditions
from src.attacks.matched_controls import canonical, header_pair
from src.eval.offline_input_audit import (
    PINS, backend_inventory, build_synthetic_reports, capture_generate_boundary,
    instrument_pair, verify_tokenizer_files,
    capture_verified_trace,
)


@pytest.fixture
def args():
    example = SYNTHETIC_EXAMPLES[0]
    base = build_conditions(example)[1]
    settings = {"retrieval": {"top_k": 2}, "generation": {"max_passage_chars": 1500},
                "evaluation_rule": "synthetic-only"}
    pair = header_pair(base, [1], settings, example.incorrect_claim)
    return [pair, base, [1], settings, {"body": example.incorrect_claim}]


def test_valid_header_pair_and_explicit_opt_in(args):
    with pytest.raises(ValueError):
        instrument_pair(*args)
    report = instrument_pair(*args, enabled=True)
    assert report["violations"] == []
    for name, trace in report["conditions"].items():
        assert trace["generator_context_target_slots"] == [1]
        assert trace["chat_template_ids"] == "UNAVAILABLE"
        assert trace["actual_model_receipt"] == "NOT_EXECUTED"
        span = trace["passages"][1]["body_prompt_span"]
        assert trace["final_assembled_prompt"][slice(*span)] == args[4]["body"]


@pytest.mark.parametrize("field", ["text", "doc_id", "timestamp", "source_metadata"])
def test_reject_undeclared_candidate_changes(args, field):
    args[0]["conditions"]["freshness"]["candidates"][1][field] = "changed"
    with pytest.raises(ValueError):
        instrument_pair(*args, enabled=True)


@pytest.mark.parametrize("what", ["candidate_order", "source_slot", "body"])
def test_reject_identity_and_body_mismatch(args, what):
    if what == "candidate_order":
        args[0]["conditions"]["neutral"]["candidates"].reverse()
    elif what == "source_slot":
        args[0]["target_slots"] = [0]
    else:
        args[0]["declarations"]["body"] = "different"
    with pytest.raises(ValueError):
        instrument_pair(*args, enabled=True)


def test_unequal_allocation_and_preprocessing(args):
    report = instrument_pair(*args, enabled=True, passage_limits={"neutral": 10, "freshness": 1500})
    assert "UNEQUAL_CONTEXT_ALLOCATION" in report["violations"]
    assert "UNEXPECTED_PREPROCESSING" in report["violations"]
    assert "ASYMMETRIC_CLAIM_TRUNCATION_OR_VISIBILITY" in report["violations"]


def test_header_length_asymmetry_at_truncation_boundary(args):
    # Neutral has 16 prefix chars, freshness 15: one-character boundary effect.
    limit = len(args[4]["body"]) + 15
    args[3]["generation"]["max_passage_chars"] = limit
    args[0] = header_pair(args[1], args[2], args[3], args[4]["body"])
    report = instrument_pair(*args, enabled=True)
    assert "ASYMMETRIC_CLAIM_TRUNCATION_OR_VISIBILITY" in report["violations"]


def test_missing_target_and_prompt_truncation(args):
    plan = {k: [0] for k in ("neutral", "freshness")}
    report = instrument_pair(*args, enabled=True, selected=plan)
    assert "MISSING_COMPLETE_GENERATOR_CONTEXT_TARGET" in report["violations"]
    report = instrument_pair(*args, enabled=True, prompt_char_limit=30)
    assert "PROMPT_TRUNCATION" in report["violations"]
    assert "MISSING_COMPLETE_GENERATOR_CONTEXT_TARGET" in report["violations"]


def test_different_selection_order(args):
    report = instrument_pair(*args, enabled=True,
        retrieved={"neutral": [0, 1], "freshness": [1, 0]})
    assert "UNEQUAL_RETRIEVAL_PLAN" in report["violations"]
    assert "UNEQUAL_CONTEXT_ALLOCATION" in report["violations"]
    with pytest.raises(ValueError):
        instrument_pair(*args, enabled=True, selected={"neutral": [1, 0], "freshness": [0, 1]})


@pytest.mark.parametrize("bad", [[True], [1, 1], [-1], [9]])
def test_bad_plan(args, bad):
    with pytest.raises(ValueError):
        instrument_pair(*args, enabled=True, retrieved={"neutral": bad, "freshness": bad})


def test_missing_cache_and_revision_rejection(tmp_path):
    result = backend_inventory(tmp_path)
    assert result["generator"]["file_evidence"]["reason"] == "MISSING_CACHE"
    assert result["contriever"]["token_counts"] == "UNAVAILABLE"
    model, revision = PINS["generator"]
    with pytest.raises(ValueError):
        verify_tokenizer_files("generator", tmp_path, {"model": model, "revision": "stale"})
    assert verify_tokenizer_files("generator", tmp_path / "missing",
        {"model": model, "revision": revision})["status"] == "UNAVAILABLE"


def test_file_hash_and_unlisted_file_detection(tmp_path):
    import hashlib
    model, revision = PINS["generator"]
    (tmp_path / "tokenizer_config.json").write_text('{}')
    (tmp_path / "tokenizer.json").write_text('{}')
    manifest = {"model": model, "revision": revision, "files": {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}}
    assert verify_tokenizer_files("generator", tmp_path, manifest)["status"] == "FILES_MATCH_RECORDED_INVENTORY"
    (tmp_path / "tokenizer.json").write_text('tampered')
    with pytest.raises(ValueError):
        verify_tokenizer_files("generator", tmp_path, manifest)
    (tmp_path / "chat_template.jinja").write_text('unlisted')
    with pytest.raises(ValueError):
        verify_tokenizer_files("generator", tmp_path, manifest)


def test_capture_stops_before_inference_and_preserves_template_flags():
    class Batch(dict):
        def to(self, device):
            assert device == "cpu"
            return self

    class SyntheticTokenizer:
        eos_token_id = 99

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs == {"return_tensors": "pt", "add_generation_prompt": True, "return_dict": True}
            assert messages[0]["role"] == "user"
            # Different header lengths give different synthetic character-token counts.
            return Batch(input_ids=[[ord(c) for c in messages[0]["content"]]])

        def decode(self, *args, **kwargs):
            pytest.fail("capture must stop before decode/inference")

    first = capture_generate_boundary("Synthetic?", ["General notice:\nclaim"], SyntheticTokenizer())
    second = capture_generate_boundary("Synthetic?", ["Latest update:\nclaim"], SyntheticTokenizer())
    assert len(first["input_ids"][0]) == len(second["input_ids"][0]) + 1
    assert first["do_sample"] is False and first["max_new_tokens"] == 64


def test_all_pairs_deterministic_and_no_real_backend_claims():
    a, b = build_synthetic_reports(), build_synthetic_reports()
    assert canonical(a) == canonical(b)
    assert len(a) == 10
    assert all(not r["trace"]["violations"] for r in a)
    assert all(r["trace"]["status"].startswith("PARTIAL") for r in a)


def test_no_non_synthetic_records(args):
    args[1]["data_scope"] = "held_out"
    with pytest.raises(ValueError):
        instrument_pair(*args, enabled=True)


def test_verified_probe_missing_cache_and_configuration_guard(args, tmp_path):
    trace = instrument_pair(*args, enabled=True)["conditions"]["neutral"]
    model, revision = PINS["generator"]
    manifest = {"model": model, "revision": revision}
    assert capture_verified_trace(trace, tmp_path / "missing", manifest)["status"] == "UNAVAILABLE"
    trace["prompt_assembly_inputs"]["max_passage_chars"] = 10
    with pytest.raises(ValueError):
        capture_verified_trace(trace, tmp_path / "missing", manifest)
