"""Synthetic preparation scenarios only; no real policy or review approval."""
from copy import deepcopy

import pytest

from src.eval import sampling_preparation as prep
from src.eval import evidence_admissibility as b1


@pytest.fixture
def context():
    frame, exposure = [], []
    for stratum in prep.STRATA:
        for index in range(200):
            qid = f"synthetic-{stratum}-{index:03d}"
            outside = stratum == "past" and index >= 190
            answers, aliases = ["30"], ["thirty"]
            frame.append({"qa_id": qid, "stratum": stratum, "reserve_rank": index + 1,
                          "queue_status_claim": "ineligible_configured_source_scope" if outside else
                          ("provisional_priority" if index < 150 else "reserve"),
                          "evidence": {"availability": "OUT_OF_SCOPE" if outside else "AVAILABLE_RECONSTRUCTED", "parent_id": "parent-" + qid},
                          "keys": {"answers": answers, "answers_additional": aliases,
                                   "original_key_sha256": b1.digest({"answers": answers, "answers_additional": aliases})},
                          "question": {"original_record": {"source": "synthetic-original", "physical_line": index + 1}}})
            confirmed = 92 if stratum == "recent" else 24
            state = "CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY" if index < confirmed else (
                "POSSIBLE_EXPOSURE_REQUIRES_REVIEW" if index < 150 else "UNKNOWN_INCOMPLETE_COVERAGE")
            exposure.append({"qa_id": qid, "status": state})
    return {"frame": frame, "exposure": exposure}


def case(outputs, policy, which):
    return next(r for r in outputs["simulations.jsonl"] if r["scenario"] == policy and r["case"] == which)


def test_deterministic_order_and_input_order_independence(context):
    first = prep.derive(context)
    second = deepcopy(context)
    second["frame"].reverse()
    second["exposure"].reverse()
    assert b1.canonical(first) == b1.canonical(prep.derive(second))
    rows = first["frame_order.jsonl"]
    assert [r["stratum"] for r in rows[:200]] == ["recent"] * 200
    assert [r["reserve_rank"] for r in rows[:200]] == list(range(1, 201))


@pytest.mark.parametrize("bad", ["duplicate_id", "missing_id", "duplicate_rank", "unknown_exposure", "original_key_change"])
def test_bad_inputs_rejected(context, bad):
    if bad == "duplicate_id":
        context["frame"].append(deepcopy(context["frame"][0]))
    elif bad == "missing_id":
        context["exposure"].pop()
    elif bad == "duplicate_rank":
        context["frame"][1]["reserve_rank"] = context["frame"][0]["reserve_rank"]
    elif bad == "unknown_exposure":
        context["exposure"][0]["status"] = "APPROVED_UNEXPOSED"
    else:
        context["frame"][0]["keys"]["answers"] = ["changed"]
    with pytest.raises(ValueError):
        prep.derive(context)


def test_ten_out_of_scope_never_enter_simulated_membership(context):
    output = prep.derive(context)
    outside = {r["qa_id"] for r in context["frame"] if r["evidence"]["availability"] == "OUT_OF_SCOPE"}
    assert len(outside) == 10
    for simulation in output["simulations.jsonl"]:
        assert set(simulation["source_scope_excluded_ids"]) == outside
        selected = [qid for s in simulation["strata"].values() for qid in s["simulated_ids"]]
        assert not set(selected) & outside
        assert len(selected) == len(set(selected))


def test_shortfalls_do_not_borrow_from_other_stratum(context):
    output = prep.derive(context)
    conditional = case(output, prep.POLICIES[1], prep.CASES[1])
    assert conditional["strata"]["recent"]["simulated_count"] == 108
    assert conditional["strata"]["recent"]["shortfall"] == 42
    assert conditional["strata"]["past"]["simulated_count"] == 150
    assert conditional["strata"]["past"]["shortfall"] == 0
    assert len(conditional["strata"]["past"]["unused_reserve_ids"]) == 16


def test_each_conditional_replacement_has_identity_reason_and_stratum(context):
    output = prep.derive(context)
    simulation = case(output, prep.POLICIES[1], prep.CASES[1])
    events = [event for s in simulation["strata"].values() for event in s["replacement_events"]]
    assert len(events) == 74
    originals = {r["qa_id"]: r for r in context["frame"]}
    for event in events:
        assert event["reason"] == "CONFIRMED_RECORDED_ACTIVITY_EXCLUDED_IN_PROPOSED_B_ONLY"
        assert originals[event["replacement_id"]]["queue_status_claim"] == "reserve"
        assert originals[event["replaced_priority_id"]]["queue_status_claim"] == "provisional_priority"
        assert originals[event["replacement_id"]]["stratum"] == originals[event["replaced_priority_id"]]["stratum"] == event["stratum"]
        assert event["label"] == prep.LABEL


def test_all_current_cases_are_unfilled_and_all_outputs_unapproved(context):
    output = prep.derive(context)
    for name in ("frame_order.jsonl", "eligibility.jsonl", "policy_scenarios.jsonl", "simulations.jsonl"):
        assert all(r["label"] == prep.LABEL for r in output[name])
    for simulation in output["simulations.jsonl"]:
        assert simulation["approved"] is False and simulation["scenario_status"] == "PROPOSED"
        if simulation["case"] == prep.CASES[0]:
            assert all(s["shortfall"] == 150 and s["simulated_ids"] == [] for s in simulation["strata"].values())
    assert output["feasibility.json"]["final_selection_approved"] is False


def test_unknown_family_eligibility_and_temporal_intent_are_not_guessed(context):
    output = prep.derive(context)
    for row in output["eligibility.jsonl"]:
        assert row["temporal_intent"] == {"status": "UNKNOWN", "label": None, "reviewer": None}
        for family in prep.REQUIREMENTS:
            status = row["families"][family]
            assert status["eligibility"] in {"UNKNOWN", "INELIGIBLE_CURRENT_SOURCE_SCOPE"}
            assert status["attack_success"] == "NOT_EVALUATED"
            assert status["rule_status"] == "PROPOSED_NOT_APPROVED"


def test_exposure_policy_does_not_change_attack_family_readiness(context):
    first = prep.derive(context)
    changed = deepcopy(context)
    for row in changed["exposure"]:
        row["status"] = "NO_RECORDED_EXPOSURE"
    second = prep.derive(changed)
    assert first["eligibility.jsonl"] == second["eligibility.jsonl"]
    # A policy pass alone cannot establish semantic/temporal primary eligibility.
    assert case(second, prep.POLICIES[0], prep.CASES[0])["strata"]["recent"]["simulated_count"] == 0


def test_attack_outcomes_are_not_inputs_to_order_or_simulation(context):
    first = prep.derive(context)
    for n, row in enumerate(context["frame"]):
        row.update(attack_success=bool(n % 2), asr=n, generated_answer="unused", machine_label="POISON_ADOPTED")
    for row in context["exposure"]:
        row.update(held_out_outcome="UNUSED_TEST_FIELD", system="unused")
    assert b1.canonical(first) == b1.canonical(prep.derive(context))


def test_original_keys_ids_and_context_are_preserved(context):
    original = deepcopy(context)
    output = prep.derive(context)
    assert context == original
    source = {r["qa_id"]: r for r in context["frame"]}
    for row in output["frame_order.jsonl"]:
        assert row["original_source_qa_id"] == row["qa_id"]
        assert row["source_evidence_parent_id"] == source[row["qa_id"]]["evidence"]["parent_id"]
        assert row["original_answers"] == source[row["qa_id"]]["keys"]["answers"]
    output["frame_order.jsonl"][0]["original_answers"][0] = "mutated output"
    assert context == original


def test_policy_alternatives_do_not_equate_activity_with_disqualification(context):
    row = prep.ordered_frame(context["frame"], context["exposure"])[0]
    assert prep.policy_decision(row, prep.POLICIES[0])["decision"] == "EXCLUDE"
    assert prep.policy_decision(row, prep.POLICIES[1])["decision"] == "EXCLUDE"
    assert prep.policy_decision(row, prep.POLICIES[2])["decision"] == "HOLD"


@pytest.mark.parametrize("purpose,expected", [("CONSTRUCTION_REVIEW_ONLY", "PASS_PROPOSED_POLICY_ONLY"),
                                             ("OUTCOME_DRIVEN_TUNING", "EXCLUDE")])
def test_governed_policy_future_attestation_contract_synthetic_only(context, purpose, expected):
    row = prep.ordered_frame(context["frame"], context["exposure"])[0]
    row["governance_purpose"] = {"status": purpose, "authority": "synthetic-test-only",
                                 "attestation_status": "EXTERNALLY_VERIFIED", "evidence_refs": ["synthetic-only"],
                                 "no_outcome_access": "VERIFIED", "roles_and_rule_tuning_separation": "VERIFIED"}
    decision = prep.policy_decision(row, prep.POLICIES[2])
    assert decision["decision"] == expected
    assert decision["approved"] is False
    # Production projection never imports or fabricates these future attestations.
    assert all(r["governance_purpose"]["authority"] is None for r in prep.ordered_frame(context["frame"], context["exposure"]))


def test_governance_name_without_attestation_does_not_clear_hold(context):
    row = prep.ordered_frame(context["frame"], context["exposure"])[0]
    row["governance_purpose"].update(status="CONSTRUCTION_REVIEW_ONLY", authority="name-alone")
    assert prep.policy_decision(row, prep.POLICIES[2])["decision"] == "HOLD"


@pytest.mark.parametrize("change", ["approval", "eligible", "temporal_intent", "scope_selection", "replacement_reason", "frame_member"])
def test_validator_rejects_promotions_or_silent_changes(context, change):
    output = prep.derive(context)
    if change == "approval":
        output["simulations.jsonl"][0]["approved"] = True
    elif change == "eligible":
        output["eligibility.jsonl"][0]["families"]["stale_amplification"]["eligibility"] = "ELIGIBLE"
    elif change == "temporal_intent":
        output["eligibility.jsonl"][0]["temporal_intent"]["label"] = "recent"
    elif change == "scope_selection":
        output["simulations.jsonl"][0]["strata"]["past"]["simulated_ids"] = ["synthetic-past-199"]
    elif change == "replacement_reason":
        simulation = case(output, prep.POLICIES[1], prep.CASES[1])
        simulation["strata"]["recent"]["replacement_events"][0]["reason"] = ""
    else:
        output["frame_order.jsonl"][0]["qa_id"] = "unknown-id"
    with pytest.raises(ValueError):
        prep.validate(output, context)


def test_strict_and_governed_conditional_bounds_are_explicit(context):
    output = prep.derive(context)
    strict = case(output, prep.POLICIES[0], prep.CASES[1])
    governed = case(output, prep.POLICIES[2], prep.CASES[1])
    assert all(s["simulated_count"] == 0 for s in strict["strata"].values())
    assert all(s["simulated_count"] == 150 for s in governed["strata"].values())
    assert governed["assumptions"] and governed["final_benchmark_membership_created"] is False
    assert all(not s["replacement_events"] for s in governed["strata"].values())
