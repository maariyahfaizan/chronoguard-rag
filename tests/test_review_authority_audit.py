"""Synthetic authority claims only; never real judgments or approvals."""
from copy import deepcopy

import pytest

from src.eval import review_authority_audit as audit
from src.eval import evidence_admissibility as b1


@pytest.fixture
def context():
    frame = {}
    for i in range(400):
        qid = f"synthetic-{i:06d}"
        answers = ["Original answer " + qid]
        frame[qid] = {"qa_id": qid, "question": {"text": "Synthetic question", "original_record": {"source": "raw", "physical_line": i + 1}},
                      "keys": {"answers": answers, "answers_additional": ["Original alias"], "original_key_sha256": b1.digest(answers)},
                      "evidence": {"variants": []}, "source_records": {"screening_audit": {"source": "screen", "physical_line": i + 1}}}
    return {"frame": frame, "records": [], "events": {}, "mentions": {}, "coverage_complete": False,
            "inputs": {"first": {"sha256": "a" * 64}, "second": {"sha256": "b" * 64}}}


def add(context, claims, source="first", line=2):
    context["records"].append({"claims": claims, "reference": b1.ref(source, line, claims)})


def test_empty_frame_audit_is_explicitly_unknown(context):
    outputs = audit.derive(context)
    assert audit.validate(outputs, context)["scientific_approval_granted"] is False
    assert outputs["summary.json"]["exposure_status"] == {"UNKNOWN_INCOMPLETE_COVERAGE": 400}
    assert outputs["summary.json"]["accepted_questions"] == 0
    assert outputs["summary.json"]["independently_approved_keys"] == 0
    assert all(r["second_independent_review"] == "NOT_ESTABLISHED" for r in outputs["review_authority.jsonl"])


def test_identical_export_copies_are_not_two_reviews(context):
    qid = "synthetic-000000"
    claims = {"qa_id": qid, "semantic_support": "supported", "human_verified": "true"}
    context["inputs"]["second"]["sha256"] = context["inputs"]["first"]["sha256"]
    add(context, claims)
    add(context, deepcopy(claims), source="second")
    outputs = audit.derive(context)
    aa = outputs["review_authority.jsonl"][0]["annotations"]
    assert len(aa) == 1 and len(aa[0]["locations"]) == 2
    assert aa[0]["independent_vote_count"] == 0
    assert outputs["summary.json"]["duplicate_file_location_excess"] == 1


def test_duplicate_claims_at_different_coordinates_remain_traceable(context):
    claims = {"qa_id": "synthetic-000000", "semantic_support": "supported"}
    add(context, claims, line=2)
    add(context, deepcopy(claims), line=3)
    aa = audit.derive(context)["review_authority.jsonl"][0]["annotations"]
    assert len(aa) == 2 and all(a["identical_claim_records"] == 2 for a in aa)
    assert all(a["second_independent_review"] == "NOT_ESTABLISHED" for a in aa)


def test_conflicting_layers_remain_unadjudicated(context):
    add(context, {"qa_id": "synthetic-000000", "semantic_support": "supported", "human_verified": "true"})
    add(context, {"qa_id": "synthetic-000000", "semantic_support": "unsupported_by_recovered_evidence", "human_verified": "false"}, source="second")
    differences = audit.derive(context)["cross_layer_conflicts.jsonl"][0]
    assert differences["adjudication"] == "NOT_PERFORMED"
    assert {d["type"] for d in differences["differences"]} == {"SUBSTANTIVE_OPPOSITION_CLAIMS", "HUMAN_VERIFICATION_FLAG_DIFFERENCE"}


def test_not_assessed_versus_supported_is_not_declared_scientific_disagreement(context):
    for n, status in enumerate(("supported", "not_assessed")):
        add(context, {"qa_id": "synthetic-000000", "semantic_support": status}, line=n + 2)
    differences = audit.derive(context)["cross_layer_conflicts.jsonl"][0]["differences"]
    assert differences[0]["type"] == "LAYER_STATUS_OR_QUALIFIER_DIFFERENCE"


def test_named_reviewers_flags_and_dates_do_not_authenticate(context):
    for n in range(2):
        add(context, {"qa_id": "synthetic-000000", "reviewer_id": f"synthetic-reviewer-{n}",
                      "review_date": "2026-11-03", "human_verified": True,
                      "semantic_support": "supported"}, line=n + 2)
    output = audit.derive(context)["review_authority.jsonl"][0]
    assert output["second_independent_review"] == "NOT_ESTABLISHED"
    assert all(a["reviewer_authority"] == "NOT_ESTABLISHED" and a["claimed_reviewer_identity"] for a in output["annotations"])


def test_missing_coverage_is_not_no_exposure(context):
    output = audit.derive(context)["exposure.jsonl"][0]
    assert output["status"] == "UNKNOWN_INCOMPLETE_COVERAGE"
    assert output["recorded_specific_exposure"] == "NONE_IN_AUDITED_SOURCES_BEYOND_FRAME_SCREENING"
    assert output["eligibility_decision"].startswith("NOT_MADE")


def test_prepared_packet_is_possible_not_proven_human_access(context):
    context["mentions"]["synthetic-000000"] = [{"source": "synthetic-packet", "physical_line": 1}]
    output = audit.derive(context)["exposure.jsonl"][0]
    assert output["status"] == "POSSIBLE_EXPOSURE_REQUIRES_REVIEW"
    assert output["human_access_independently_authenticated"] is False


def test_assessment_is_recorded_development_activity_not_automatic_exclusion(context):
    add(context, {"qa_id": "synthetic-000000", "assistant_preliminary_semantic_support": "supported"})
    output = audit.derive(context)["exposure.jsonl"][0]
    assert output["status"] == "CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY"
    assert output["eligibility_decision"].startswith("NOT_MADE")


def test_original_and_derived_answers_never_overwrite_each_other(context):
    original = deepcopy(context["frame"]["synthetic-000000"]["keys"]["answers"])
    add(context, {"qa_id": "synthetic-000000", "gold_answers_original_json": '["altered"]', "proposed_answer": "proposal only"})
    output = audit.derive(context)["keys.jsonl"][0]
    assert output["original_answers"] == original
    assert output["imported_original_key_copies"][0]["comparison"] == "DIFFERS_FROM_ORIGINAL"
    assert output["derived_proposals"][0]["approved"] is False


def test_normalized_alias_proposal_is_not_question_time_adjudication(context):
    add(context, {"qa_id": "synthetic-000000", "distinct_normalized_aliases_json": '["normalized"]'})
    output = audit.derive(context)
    assert output["summary.json"]["normalized_alias_proposals"] == 1
    assert output["summary.json"]["derived_question_time_proposals"] == 0


def test_claim_key_approval_flag_is_not_authorization(context):
    add(context, {"qa_id": "synthetic-000000", "false_state": "synthetic false state",
                  "claim_key_id": "synthetic-key", "claim_key_status": "approved"})
    output = audit.derive(context)["keys.jsonl"][0]
    assert output["false_claim_candidates"][0]["approved"] is False
    assert output["false_claim_candidates"][0]["claimed_approval"] == {"claim_key_status": "approved"}
    assert output["independently_approved_keys"] == []


def test_unknown_ids_and_missing_ids_are_quarantined(context):
    add(context, {"qa_id": "unknown-qa", "semantic_support": "supported"})
    add(context, {"query_id": 42, "human_verified": "true"}, line=3)
    output = audit.derive(context)
    assert len(output["review_authority.jsonl"]) == 400
    assert {r["frame_membership"] for r in output["unbound_records.jsonl"]} == {"OUT_OF_FRAME", "MISSING_STABLE_QA_ID"}
    audit.validate(output, context)


def test_deterministic_output_order_and_detached_context(context):
    add(context, {"qa_id": "synthetic-000002", "semantic_support": "supported"})
    add(context, {"qa_id": "synthetic-000001", "semantic_support": "supported"}, source="second")
    first = audit.derive(context)
    changed = deepcopy(context)
    changed["frame"] = dict(reversed(list(changed["frame"].items())))
    changed["records"].reverse()
    assert b1.canonical(first) == b1.canonical(audit.derive(changed))
    first["keys.jsonl"][0]["original_answers"][0] = "edited output"
    assert context["frame"]["synthetic-000000"]["keys"]["answers"][0] != "edited output"


@pytest.mark.parametrize("change", ["accepted", "authority", "key_approval", "exposure", "unknown_id", "original_key", "summary"])
def test_validator_rejects_unsupported_promotions(context, change):
    output = audit.derive(context)
    if change == "accepted":
        output["review_authority.jsonl"][0]["scientific_disposition"] = "ACCEPTED"
    elif change == "authority":
        output["review_authority.jsonl"][0]["independent_reviewer_authority"] = "ESTABLISHED"
    elif change == "key_approval":
        output["keys.jsonl"][0]["independently_approved_keys"] = ["invented"]
    elif change == "exposure":
        output["exposure.jsonl"][0]["eligibility_decision"] = "EXCLUDED"
    elif change == "unknown_id":
        output["exposure.jsonl"][0]["qa_id"] = "outside-frame"
    elif change == "original_key":
        output["keys.jsonl"][0]["original_answers"][0] = "changed"
    else:
        output["summary.json"]["accepted_questions"] = 1
    with pytest.raises(ValueError):
        audit.validate(output, context)


def test_record_hash_mismatch_rejected(context):
    add(context, {"qa_id": "synthetic-000000", "semantic_support": "supported"})
    context["records"][0]["claims"]["semantic_support"] = "unsupported"
    with pytest.raises(ValueError, match="record hash"):
        audit.derive(context)


def test_missing_or_wrong_evidence_binding_is_reported(context):
    add(context, {"qa_id": "synthetic-000000", "semantic_support": "supported",
                  "supporting_variant_id": "cgei:v1:variant:" + "a" * 64,
                  "source_packet_sha256": "f" * 64, "question": "wrong question"})
    output = audit.derive(context)
    binding = output["review_authority.jsonl"][0]["source_binding_checks"][0]
    assert binding["supporting_evidence_status"] == "UNRESOLVED_VARIANT_REFERENCE"
    assert binding["claimed_source_hashes"]["source_packet_sha256"]["resolves_to_audited_bytes"] is False
    required = output["missing_authority.jsonl"][0]["requirements"]
    assert "SUPPORTING_VARIANT_REFERENCE_RECONCILIATION" in required
    assert "ANNOTATION_QUESTION_TEXT_RECONCILIATION" in required


def test_assessment_without_variant_link_stays_unauthenticated(context):
    add(context, {"qa_id": "synthetic-000000", "semantic_support": "supported"})
    output = audit.derive(context)
    assert "EXPLICIT_EVIDENCE_BINDING_FOR_ASSESSMENT" in output["missing_authority.jsonl"][0]["requirements"]
    assert output["review_authority.jsonl"][0]["independent_adjudication"] == "NOT_ESTABLISHED"
