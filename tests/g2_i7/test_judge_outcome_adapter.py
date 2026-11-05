"""Reviewed pure fixtures/structure only. No judge, analyzer or backend imports."""
import copy
import sys

import pytest

from src.eval.no_execution_boundary import ExecutionBlocked
from src.eval.judge_outcome_adapter import (
    BLOCKED, GATES, ROOT, fixtures, map_descriptor, project, require_numerical_eligibility,
    schemas, source_bundle, unobserved_source_export, validate_analysis_structure, validate_export, write_export,
)


def test_actual_source_schema_inspection():
    s = schemas()
    assert set(s["judge_labels"]) == {"CORRECT", "POISON_ADOPTED", "OTHER_WRONG", "NEEDS_REVIEW"}
    assert "ABSTAIN" not in s["judge_labels"]
    assert "ABSTAIN" in s["analysis_schema"]["row_fields"]["outcome"]


@pytest.mark.parametrize("case,state", [("correct", "CORRECT"), ("poison", "POISON_ADOPTED"),
    ("abstention", "ABSTAIN"), ("empty", "MISSING"), ("review", "NEEDS_REVIEW"),
    ("missing", "MISSING"), ("invalid", "NEEDS_REVIEW"), ("other_wrong", "OTHER_WRONG")])
def test_every_label_and_distinction(case, state):
    source = next(r for r in fixtures() if r["fixture_id"].endswith("-" + case))
    out = project([source], mode="synthetic")[0]
    assert out["projected_analysis_state"] == state
    assert out["original_judge_output"] == source["judge_output"]
    assert out["analysis_projection"]["outcome"] == "MISSING"
    assert out["outcome_state"] == "UNOBSERVED"
    assert out["analysis_eligibility"] == "BLOCKED"


def test_uncertainty_is_not_correct_or_negative():
    out = {r["fixture_id"]: r for r in project(fixtures(), mode="synthetic")}
    assert out["synthetic-judge-g2-i7-review"]["projected_analysis_state"] == "NEEDS_REVIEW"
    assert out["synthetic-judge-g2-i7-other_wrong"]["projected_analysis_state"] == "OTHER_WRONG"
    assert out["synthetic-judge-g2-i7-empty"]["uncertainty_reason"] != out["synthetic-judge-g2-i7-missing"]["uncertainty_reason"]


def test_source_identities_and_hashes_preserved():
    records = fixtures()
    out = project(records, mode="synthetic")
    sources = {r["fixture_id"]: r for r in records}
    for r in out:
        for k, v in sources[r["fixture_id"]]["binding"].items(): assert r[k] == v
        assert r["source_analysis_record_sha256"] == sources[r["fixture_id"]]["source_analysis_record_sha256"]
        assert r["execution_status"] == BLOCKED
        assert "UNAPPROVED_CLAIM_KEY_APPROVAL" in r["missingness_reasons"]
    assert validate_export(out, records)


def test_complete_current_source_remains_unobserved():
    rows = unobserved_source_export()
    assert len(rows) == 16
    for qid in {r["canonical_question_id"] for r in rows}:
        cells = [r for r in rows if r["canonical_question_id"] == qid]
        assert len(cells) == 8 and len({r["cell_id"] for r in cells}) == 8
    for r in rows:
        assert r["outcome_state"] == "UNOBSERVED"
        assert r["analysis_projection"]["outcome"] == "MISSING"
        assert r["analysis_projection"]["generator"] == "UNVERIFIED"
        assert r["original_judge_label"] is None


def test_actual_analysis_field_validator_only():
    records = fixtures()
    assert validate_analysis_structure(project(records, mode="synthetic"), records)["numerical_eligibility"] == "BLOCKED"


def test_unknown_eligibility_and_missing_provenance_rejected():
    r = fixtures()[0]; r["gates"]["question_eligibility"] = "UNKNOWN"
    with pytest.raises(ValueError): project([r], mode="synthetic")
    r = fixtures()[0]; del r["gates"]["provenance_authentication"]
    with pytest.raises(ValueError): project([r], mode="synthetic")


def test_duplicate_evaluation_identity_rejected():
    r = fixtures()[:2]
    r[1]["judge_output"]["evaluation_id"] = r[0]["judge_output"]["evaluation_id"]
    with pytest.raises(ValueError, match="duplicate evaluation"): project(r, mode="synthetic")


def test_deterministic_order_and_no_mutation():
    source = fixtures(); before = copy.deepcopy(source)
    a = project(source, mode="synthetic")
    assert a == project(list(reversed(source)), mode="synthetic")
    a[0]["gate_statuses"]["claim_key_approval"] = "changed"
    assert source == before


@pytest.mark.parametrize("label", ["ABSTAIN", "MISSING", "INCORRECT", "INVALID", "UNOBSERVED", None, 1])
def test_unsupported_judge_label_rejected(label):
    r = fixtures()[0]
    r["judge_output"]["label"] = label
    with pytest.raises(ValueError, match="label"): project([r], mode="synthetic")


@pytest.mark.parametrize("field", ["canonical_question_id", "analysis_question_id", "cell_id", "analysis_condition",
    "source_construction_sha256", "prompt_sha256", "context_sha256", "identity_mapping_sha256"])
def test_identity_and_hash_mismatches_rejected(field):
    r = fixtures()[0]
    r["binding"][field] = "altered"
    with pytest.raises(ValueError): project([r], mode="synthetic")


def test_duplicate_fixture_and_condition_collision():
    rows = fixtures()
    with pytest.raises(ValueError, match="duplicate"): project([rows[0], rows[0]], mode="synthetic")
    rows[1]["binding"] = copy.deepcopy(rows[0]["binding"])
    with pytest.raises(ValueError, match="colliding"): project(rows, mode="synthetic")


def test_source_record_hash_mismatch():
    r = fixtures()[0]; r["source_analysis_record_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash"): project([r], mode="synthetic")


@pytest.mark.parametrize("gate", list(GATES))
def test_no_approval_flag_can_promote_fixture(gate):
    r = fixtures()[0]; r["gates"][gate] = "APPROVED"
    with pytest.raises(ValueError, match="promotion"): project([r], mode="synthetic")


def test_no_observation_estimator_gate_and_unapproved_key_rejection():
    rows = fixtures(); out = project(rows, mode="synthetic")
    with pytest.raises(ValueError, match="no observations"): require_numerical_eligibility(out, rows)
    out[0]["claim_key_approval"] = "APPROVED"
    with pytest.raises(ValueError): require_numerical_eligibility(out, rows)


@pytest.mark.parametrize("field", ["outcome_state", "projected_analysis_state", "analysis_eligibility", "claim_key_hash"])
def test_output_mutation_rejected(field):
    rows = fixtures(); out = project(rows, mode="synthetic")
    out[0][field] = "altered"
    with pytest.raises(ValueError, match="drift"): validate_export(out, rows)


def test_numerical_projection_cannot_be_changed_to_observation():
    rows = fixtures(); out = project(rows, mode="synthetic")
    out[0]["analysis_projection"]["outcome"] = "CORRECT"
    with pytest.raises(ValueError): require_numerical_eligibility(out, rows)


def test_real_and_rehashed_modified_judge_rejected():
    rows = fixtures()
    with pytest.raises(ValueError, match="real"): project(rows, mode="real")
    rows[0]["binding"]["canonical_question_id"] = "real-qa-id"
    with pytest.raises(ValueError): project(rows, mode="synthetic")
    rows = fixtures(); rows[0]["fixture_id"] = "real-review"
    with pytest.raises(ValueError, match="real"): project(rows, mode="synthetic")
    rows = fixtures(); rows[0]["judge_output"]["evaluation_id"] = "0" * 64
    with pytest.raises(ValueError, match="altered"): project(rows, mode="synthetic")


@pytest.mark.parametrize("change", ["stale", "status", "missing_field", "type", "invalid_input_with_label", "generation"])
def test_malformed_and_contradictory_input(change):
    r = fixtures()[0]
    if change == "stale": r["judge_output"]["implementation_version"] = "p0_a6_v2_repair_2"
    elif change == "status": r["judge_output"]["review_status"] = "required"
    elif change == "missing_field": del r["judge_output"]["claim_key_hash"]
    elif change == "type": r["judge_output"] = []
    elif change == "invalid_input_with_label": r["judge_input_status"] = "INVALID_UNSUPPORTED_INPUT"
    else: r["generation_state"] = "OBSERVED"
    with pytest.raises(ValueError): project([r], mode="synthetic")


@pytest.mark.parametrize("path", ["data/processed/forbidden.json", "audits/g2_i6_v1/new.json", "../escape.json"])
def test_output_escape_rejected(path):
    rows = fixtures()
    with pytest.raises(ValueError, match="path"): write_export(project(rows, mode="synthetic"), rows, output=ROOT / path)


@pytest.mark.parametrize("operation", ["retrieval", "generation", "attack", "model_import", "network", "process", "judge", "statistics"])
def test_guarded_attempts_never_enter_operation_body(operation):
    guard = sys._chronoguard_g2_i7_boundary
    with pytest.raises(ExecutionBlocked): guard.probe(operation)
    assert guard.report()["profile_active"]
