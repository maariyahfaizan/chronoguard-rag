"""W6-J1 integration tests use fiction only, never historical outcomes."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.eval import attack_postprocess_v2 as post
from src.eval.answer_judge_v2 import RUBRIC_VERSION

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts/postprocess_attacks_v2.py"


def process(bundle=None):
    return post.process(post.fixture_bundle() if bundle is None else bundle,
                        rubric_version=RUBRIC_VERSION)


def cli(*args, rubric=RUBRIC_VERSION):
    selection = [] if rubric is None else ["--rubric", rubric]
    return subprocess.run([sys.executable, "-B", str(CLI), *selection, *map(str, args)],
                          cwd=ROOT, capture_output=True, text=True)


def test_fixture_processing_preserves_multiclass_outcomes():
    output = process()
    judgments = [r["judgment"] for r in output["rows"]]
    assert [j["label"] for j in judgments] == [
        "POISON_ADOPTED", "CORRECT", "OTHER_WRONG", "OTHER_WRONG", "NEEDS_REVIEW", "NEEDS_REVIEW"]
    assert judgments[2]["reason"] == "pure_abstention"
    assert judgments[3]["reason"] == "empty_answer"
    assert judgments[5]["reason"] == "mixed_gold_and_false"
    assert output["scientific_validation"] == "NOT_VALIDATED"
    assert output["real_case_authority"] == "DISABLED_NO_AUTHENTICATED_PROVIDER"
    post.verify_output(json.loads(post.encode(output)), post.fixture_bundle(), rubric_version=RUBRIC_VERSION)


def test_actual_cli_roundtrip_and_no_overwrite(tmp_path):
    source, target = tmp_path / "fixtures.json", tmp_path / "judgments.json"
    for args in (("fixtures", "--output", source),
                 ("process", "--input", source, "--output", target),
                 ("verify", "--input", source, "--output", target)):
        result = cli(*args)
        assert result.returncode == 0, result.stderr
    saved = target.read_bytes()
    assert cli("process", "--input", source, "--output", target).returncode == 1
    assert target.read_bytes() == saved
    assert cli("fixtures", "--output", source).returncode == 1
    post.verify_file_output(post.read(target), source, rubric_version=RUBRIC_VERSION)


@pytest.mark.parametrize("mutation", [
    "missing_key", "null_key", "wrong_key_digest", "wrong_question", "wrong_source",
    "wrong_question_text", "wrong_source_text", "wrong_gold", "wrong_aliases",
    "missing_approval", "revoked", "stale_digest", "stale_rubric", "stale_implementation",
    "unapproved_key", "ambiguous_key", "unverifiable_reviewer", "provenance", "real_id",
    "altered_answer", "tuple_type", "extra_field",
])
def test_admission_rejects_invalid_records(mutation):
    bundle = post.fixture_bundle()
    r = bundle["records"][0]
    if mutation == "missing_key": del r["claim_key"]
    elif mutation == "null_key": r["claim_key"] = None
    elif mutation == "wrong_key_digest": r["key_digest"] = "0" * 64
    elif mutation == "wrong_question": r["context"]["question_id"] = "synthetic-other"
    elif mutation == "wrong_source": r["context"]["source_id"] = "synthetic-other"
    elif mutation == "wrong_question_text": r["context"]["question"] = "Other?"
    elif mutation == "wrong_source_text": r["context"]["source_text"] = "Changed"
    elif mutation == "wrong_gold": r["context"]["primary_gold"] = "Carol"
    elif mutation == "wrong_aliases": r["context"]["aliases"] = ["Carol"]
    elif mutation == "missing_approval": del r["approval"]
    elif mutation == "revoked": r["approval"]["status"] = "REVOKED"
    elif mutation == "stale_digest": r["approval"]["key_digest"] = "0" * 64
    elif mutation == "stale_rubric": r["approval"]["rubric_version"] = "old"
    elif mutation == "stale_implementation": r["approval"]["implementation_version"] = "old"
    elif mutation == "unapproved_key": r["claim_key"]["approval_status"] = "pending"
    elif mutation == "ambiguous_key": r["claim_key"]["ambiguous"] = True
    elif mutation == "unverifiable_reviewer": r["claim_key"]["reviewer"] = "claimed-real-reviewer"
    elif mutation == "provenance": r["provenance"]["event_origin"] = "REAL_MODEL"
    elif mutation == "real_id": r["event_id"] = "eval-001639"
    elif mutation == "altered_answer": r["generated_answer"] = "A new real answer"
    elif mutation == "tuple_type": r["context"]["aliases"] = "Alice Smith"
    else: r["extra"] = True
    with pytest.raises(ValueError): process(bundle)


@pytest.mark.parametrize("field", ["schema_version", "rubric_version", "implementation_version"])
def test_bundle_revision_rejected(field):
    bundle = post.fixture_bundle()
    bundle[field] = "old"
    with pytest.raises(ValueError, match="revision"): process(bundle)


@pytest.mark.parametrize("scope", ["REAL", "AUTHENTICATED_REAL", None])
def test_real_authority_disabled_even_with_claimed_approval(scope):
    bundle = post.fixture_bundle()
    bundle["scope"] = scope
    bundle["authority"] = {"authenticated": True, "signature": "caller-supplied"}
    with pytest.raises(ValueError, match="no authenticated authority provider"): process(bundle)


def test_duplicate_event_rejected():
    bundle = post.fixture_bundle()
    bundle["records"].append(deepcopy(bundle["records"][0]))
    with pytest.raises(ValueError, match="duplicate"): process(bundle)


def test_duplicate_evaluation_identity_rejected_by_existing_replay(monkeypatch):
    registry = post.fixture_bundle()
    # Simulate two registered events with identical evaluation inputs.
    registry["records"][1]["generated_answer"] = registry["records"][0]["generated_answer"]
    monkeypatch.setattr(post, "fixture_bundle", lambda: deepcopy(registry))
    with pytest.raises(ValueError, match="duplicate output identity"): process(registry)


@pytest.mark.parametrize("mutation", ["label", "revision", "evaluation", "evidence", "event",
                                     "embedded_input", "digest", "scope", "duplicate", "missing"])
def test_tampered_serialized_output_rejected(mutation):
    output = process()
    row = output["rows"][0]
    if mutation == "label": row["judgment"]["label"] = "CORRECT"
    elif mutation == "revision": row["judgment"]["implementation_version"] = "old"
    elif mutation == "evaluation": row["judgment"]["evaluation_id"] = "forged"
    elif mutation == "evidence": row["judgment"]["evidence"] = []
    elif mutation == "event": row["event_id"] = "other"
    elif mutation == "embedded_input": row["input_record"]["generated_answer"] = "Alice Smith"
    elif mutation == "digest": row["input_record_digest"] = "forged"
    elif mutation == "scope": output["scope"] = "REAL"
    elif mutation == "duplicate": output["rows"].append(deepcopy(row))
    else: output["rows"].pop()
    with pytest.raises(ValueError):
        post.verify_output(output, post.fixture_bundle(), rubric_version=RUBRIC_VERSION)


@pytest.mark.parametrize("rubric", [None, "answer_judge_v1", "unknown"])
def test_cli_has_no_implicit_v1_fallback(tmp_path, rubric):
    target = tmp_path / "out.json"
    result = cli("fixtures", "--output", target, rubric=rubric)
    assert result.returncode != 0
    assert not target.exists()


def test_cli_rejection_writes_no_partial_output(tmp_path):
    bundle = post.fixture_bundle()
    bundle["records"][-1]["approval"]["status"] = "REVOKED"
    source, target = tmp_path / "bad.json", tmp_path / "out.json"
    source.write_bytes(post.encode(bundle))
    result = cli("process", "--input", source, "--output", target)
    assert result.returncode == 1
    assert not target.exists()


def test_input_file_hash_and_cli_tamper_detection(tmp_path):
    source, target = tmp_path / "input.json", tmp_path / "out.json"
    source.write_bytes(post.encode(post.fixture_bundle()))
    post.run(source, target, rubric_version=RUBRIC_VERSION)
    output = post.read(target)
    output["rows"][0]["judgment"]["label"] = "CORRECT"
    target.write_bytes(post.encode(output))
    assert cli("verify", "--input", source, "--output", target).returncode == 1
    post.run(source, tmp_path / "good.json", rubric_version=RUBRIC_VERSION)
    source.write_bytes(source.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file digest"):
        post.verify_file_output(post.read(tmp_path / "good.json"), source, rubric_version=RUBRIC_VERSION)


def test_strict_json_rejects_duplicate_fields_and_nonfinite(tmp_path):
    source = tmp_path / "bad.json"
    for raw in ('{"scope": "REAL", "scope": "REGISTERED_SYNTHETIC_ONLY"}', '{"value": NaN}'):
        source.write_text(raw)
        with pytest.raises(ValueError): post.read(source)


@pytest.mark.parametrize("tree", ["data", "logs", "results", "audits", "docs", ".git"])
def test_protected_output_trees_rejected(tree):
    with pytest.raises(ValueError, match="protected"):
        post.write_new(ROOT / tree / "w6-j1-must-not-exist.json", {})


def test_no_backend_network_or_v1_judge_calls(monkeypatch):
    import builtins
    import socket
    from src.eval import answer_judge
    original_import = builtins.__import__

    def deny(*args, **kwargs):
        raise AssertionError("prohibited backend/network/v1 call")

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in {"torch", "transformers", "sentence_transformers", "requests", "huggingface_hub"}:
            deny()
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", deny)
    monkeypatch.setattr(answer_judge, "judge_answer", deny)
    output = process()
    post.verify_output(output, post.fixture_bundle(), rubric_version=RUBRIC_VERSION)
