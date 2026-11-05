"""P0-C1 proposed exposure policies and bounded simulations; never a sample freeze."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path

from . import evidence_admissibility as b1
from . import review_authority_audit as b2

VERSION = "chronoguard-sampling-preparation/p0-c1-v1"
LABEL = "NOT_FINAL_NOT_APPROVED"
STRATA = ("recent", "past")
TARGET = 150
POLICIES = ("A_STRICT", "B_CONFIRMED_EXCLUSION_REVIEW_HOLDS", "C_GOVERNED_CONSTRUCTION_REVIEW")
EXPOSURES = {"CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY", "POSSIBLE_EXPOSURE_REQUIRES_REVIEW",
             "UNKNOWN_INCOMPLETE_COVERAGE", "NO_RECORDED_EXPOSURE"}
CASES = ("CURRENT_REVIEW_READY", "CONDITIONAL_ALL_HOLDS_CLEARED_AND_PRIMARY_ADMISSIBLE")
REQUIREMENTS = {
    "stale_amplification": ("reviewed_obsolete_claim", "reviewed_temporal_contrast", "approved_false_claim_key"),
    "fabricated_fresh_evidence": ("reviewed_false_proposition", "approved_false_claim_key", "payload_identity_and_threat_model"),
    "future_date_metadata_shift": ("reviewed_correct_source_content", "permitted_timestamp_transformation", "metadata_only_pair_integrity"),
    "fresh_looking_duplication": ("reviewed_correct_source_content", "permitted_duplicate_and_date_policy", "duplicate_identity_integrity"),
    "correct_content_wrong_date_controls": ("reviewed_correct_source_content", "paired_zero_day_and_wrong_date_control", "matched_content_slots_and_generation_conditions"),
}
COMMON = ("question_time_gold_and_alias_adjudication", "semantic_support", "temporal_validity",
          "source_provenance_policy", "candidate_pool_integrity")


def tagged(**fields):
    return {"schema_version": VERSION, "label": LABEL, **fields}


def ordered_frame(frame_rows, exposure_rows):
    frame, exposure = b1.keyed(frame_rows, "C1 frame"), b1.keyed(exposure_rows, "C1 exposure")
    if len(frame) != 400 or set(frame) != set(exposure):
        raise ValueError("requires identical 400-ID frame and exposure membership")
    ranks = set()
    projected = []
    for qid, row in frame.items():
        stratum, rank = row["stratum"], row["reserve_rank"]
        if stratum not in STRATA or type(rank) is not int or rank < 1 or (stratum, rank) in ranks:
            raise ValueError("invalid/duplicate stratum reserve rank")
        ranks.add((stratum, rank))
        state = exposure[qid]["status"]
        if state not in EXPOSURES:
            raise ValueError("unsupported exposure state")
        scope = row["evidence"]["availability"]
        if scope not in {"AVAILABLE_RECONSTRUCTED", "OUT_OF_SCOPE"}:
            raise ValueError("unknown source scope must be resolved before this simulator")
        role = row["queue_status_claim"]
        if role not in {"provisional_priority", "reserve", "ineligible_configured_source_scope"}:
            raise ValueError("unsupported existing queue status")
        keys = row["keys"]
        if b1.digest({"answers": keys["answers"], "answers_additional": keys["answers_additional"]}) != keys["original_key_sha256"]:
            raise ValueError("original key binding mismatch")
        projected.append(tagged(qa_id=qid, stratum=stratum, reserve_rank=rank,
                                original_queue_role=role, source_scope=scope, exposure_status=state,
                                original_source_qa_id=qid, source_evidence_parent_id=row["evidence"]["parent_id"],
                                original_answers=keys["answers"], original_answers_additional=keys["answers_additional"],
                                original_key_sha256=keys["original_key_sha256"],
                                original_record=row["question"]["original_record"],
                                temporal_intent={"status": "UNKNOWN", "label": None, "reviewer": None},
                                governance_purpose={"status": "UNKNOWN_REQUIRES_INDEPENDENT_EVIDENCE", "authority": None,
                                                    "attestation_status": "NOT_PROVIDED", "evidence_refs": [],
                                                    "no_outcome_access": "UNKNOWN", "roles_and_rule_tuning_separation": "UNKNOWN"}))
    if Counter(r["stratum"] for r in projected) != Counter(recent=200, past=200):
        raise ValueError("expected 200 recent and 200 past")
    if sum(r["source_scope"] == "OUT_OF_SCOPE" for r in projected) != 10:
        raise ValueError("expected ten source-scope exclusions")
    for stratum in STRATA:
        if sum(r["stratum"] == stratum and r["original_queue_role"] == "provisional_priority" for r in projected) != TARGET:
            raise ValueError("expected 150 original provisional priorities per stratum")
    # Never read model answers, attack outcomes, ASR, judge labels or semantic
    # preferences. Only pinned frame/order/source/exposure metadata is projected.
    return deepcopy(sorted(projected, key=lambda r: (STRATA.index(r["stratum"]), r["reserve_rank"], r["qa_id"])))


def eligibility(row):
    outside = row["source_scope"] == "OUT_OF_SCOPE"
    status = "INELIGIBLE_CURRENT_SOURCE_SCOPE" if outside else "UNKNOWN"
    return tagged(qa_id=row["qa_id"], stratum=row["stratum"],
                  temporal_intent=deepcopy(row["temporal_intent"]),
                  primary_admissibility=status,
                  primary_missing_evidence=list(COMMON) if not outside else ["gold_evidence_outside_configured_archives"],
                  families={family: {"eligibility": status, "rule_status": "PROPOSED_NOT_APPROVED",
                                     "prerequisites": {name: "UNKNOWN" for name in COMMON + requirements},
                                     "source_scope": row["source_scope"], "attack_success": "NOT_EVALUATED"}
                            for family, requirements in REQUIREMENTS.items()},
                  interpretation="ELIGIBILITY_IS_NOT_ATTACK_SUCCESS_AND_DOES_NOT_REQUIRE_ALL_FAMILIES_FOR_PRIMARY_MEMBERSHIP")


def policy_decision(row, policy):
    if policy not in POLICIES:
        raise ValueError("unsupported proposed policy")
    state = row["exposure_status"]
    if row["source_scope"] == "OUT_OF_SCOPE":
        decision, reason = "EXCLUDE", "GOLD_2007_OUTSIDE_CURRENT_SOURCE_SCOPE"
    elif policy == POLICIES[0]:
        decision = "PASS_PROPOSED_POLICY_ONLY" if state == "NO_RECORDED_EXPOSURE" else "EXCLUDE"
        reason = "NO_RECORDED_EXPOSURE_NOT_PROOF_OF_GLOBAL_NONEXPOSURE" if decision.startswith("PASS") else "STRICT_RECORDED_POSSIBLE_OR_UNKNOWN_EXPOSURE_EXCLUSION"
    elif policy == POLICIES[1]:
        if state == "CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY":
            decision, reason = "EXCLUDE", "CONFIRMED_RECORDED_ACTIVITY_EXCLUDED_IN_PROPOSED_B_ONLY"
        elif state == "NO_RECORDED_EXPOSURE":
            decision, reason = "PASS_PROPOSED_POLICY_ONLY", "NO_RECORDED_EXPOSURE_REQUIRES_COVERAGE_CONFIRMATION"
        else:
            decision, reason = "HOLD", "POSSIBLE_OR_UNKNOWN_EXPOSURE_INDEPENDENT_REVIEW_REQUIRED"
    else:
        # A screening/assessment label cannot prove construction-only use or the
        # absence of outcome-driven tuning. Authenticated purpose records are absent.
        purpose = row["governance_purpose"]
        supported = (purpose.get("attestation_status") == "EXTERNALLY_VERIFIED"
                     and bool(purpose.get("authority")) and bool(purpose.get("evidence_refs")))
        if supported and purpose["status"] == "OUTCOME_DRIVEN_TUNING":
            decision, reason = "EXCLUDE", "OUTCOME_DRIVEN_TUNING_EXCLUDED_IN_PROPOSED_C_ONLY"
        elif (supported and purpose["status"] == "CONSTRUCTION_REVIEW_ONLY"
              and purpose.get("no_outcome_access") == "VERIFIED"
              and purpose.get("roles_and_rule_tuning_separation") == "VERIFIED"):
            decision, reason = "PASS_PROPOSED_POLICY_ONLY", "GOVERNED_CONSTRUCTION_ONLY_UNDER_PROPOSED_C"
        else:
            decision, reason = "HOLD", "CONSTRUCTION_VS_OUTCOME_TUNING_PURPOSE_AND_GOVERNANCE_UNKNOWN"
    return tagged(qa_id=row["qa_id"], stratum=row["stratum"], scenario=policy,
                  scenario_status="PROPOSED", approved=False, decision=decision, reason=reason,
                  exposure_status=state, governed_purpose_status=row["governance_purpose"]["status"],
                  scientific_eligibility_decision="NOT_MADE")


def simulate(frame, decisions, eligibility_rows, policy, case):
    if case not in CASES:
        raise ValueError("unsupported simulation case")
    masks, ready = b1.keyed(decisions, "policy mask"), b1.keyed(eligibility_rows, "eligibility")
    if set(masks) != {r["qa_id"] for r in frame} or set(ready) != set(masks):
        raise ValueError("simulation membership mismatch")
    conditional = case == CASES[1]
    def reason(row):
        mask = masks[row["qa_id"]]
        if row["source_scope"] == "OUT_OF_SCOPE":
            return "GOLD_2007_OUTSIDE_CURRENT_SOURCE_SCOPE"
        if mask["decision"] == "EXCLUDE":
            return mask["reason"]
        if not conditional and mask["decision"] == "HOLD":
            return mask["reason"]
        if not conditional and ready[row["qa_id"]]["primary_admissibility"] != "ELIGIBLE":
            return "PRIMARY_SEMANTIC_TEMPORAL_ADMISSIBILITY_UNKNOWN"
        return None
    strata = {}
    for stratum in STRATA:
        pool = [r for r in frame if r["stratum"] == stratum]
        priorities = [r for r in pool if r["original_queue_role"] == "provisional_priority"]
        reserves = [r for r in pool if r["original_queue_role"] == "reserve"]
        chosen, slots, replacements, reserve_checks = [], [], [], []
        cursor = 0
        for slot, priority in enumerate(priorities, 1):
            blocked = reason(priority)
            pick = priority if blocked is None else None
            if pick is None:
                while cursor < len(reserves):
                    candidate = reserves[cursor]
                    cursor += 1
                    failure = reason(candidate)
                    reserve_checks.append({"label": LABEL, "qa_id": candidate["qa_id"],
                                           "reason": failure or "SIMULATED_REPLACEMENT_AVAILABLE"})
                    if failure is None:
                        pick = candidate
                        replacements.append({"label": LABEL, "stratum": stratum, "slot": slot,
                                             "replaced_priority_id": priority["qa_id"], "replacement_id": pick["qa_id"],
                                             "reason": blocked, "case": case})
                        break
            if pick is not None:
                chosen.append(pick["qa_id"])
            slots.append({"label": LABEL, "slot": slot, "original_priority_id": priority["qa_id"],
                          "simulated_id": pick["qa_id"] if pick else None,
                          "reason": blocked or "ORIGINAL_PRIORITY_RETAINED",
                          "unfilled_reason": "NO_ELIGIBLE_RESERVE_IN_SAME_STRATUM" if pick is None else None})
        if len(chosen) != len(set(chosen)):
            raise ValueError("duplicate simulated membership")
        strata[stratum] = {"label": LABEL, "target_proposed": TARGET, "original_priority_count": len(priorities),
                           "original_reserve_count": len(reserves), "simulated_ids": chosen,
                           "simulated_count": len(chosen), "shortfall": TARGET - len(chosen),
                           "slots": slots, "replacement_events": replacements, "reserve_checks": reserve_checks,
                           "unused_reserve_ids": [r["qa_id"] for r in reserves if r["qa_id"] not in chosen]}
    return tagged(scenario=policy, scenario_status="PROPOSED", case=case, approved=False,
                  assumptions=([] if not conditional else ["ALL_POLICY_HOLDS_CLEARED_WITH_REQUIRED_AUTHORITY",
                               "ALL_SOURCE_AVAILABLE_PRIMARY_UNKNOWN_CASES_BECOME_ADMISSIBLE",
                               "FOR_C_ONLY_EVERY_HELD_CASE_IS_INDEPENDENTLY_CONFIRMED_GOVERNED_CONSTRUCTION_ONLY",
                               "THESE_ARE_COUNTERFACTUAL_ASSUMPTIONS_NOT_REVIEW_DECISIONS"]),
                  source_scope_excluded_ids=[r["qa_id"] for r in frame if r["source_scope"] == "OUT_OF_SCOPE"],
                  strata=strata, final_benchmark_membership_created=False)


def derive(context):
    frame = ordered_frame(context["frame"], context["exposure"])
    elig = [eligibility(r) for r in frame]
    policies = [policy_decision(r, policy) for policy in POLICIES for r in frame]
    simulations, reports = [], []
    for policy in POLICIES:
        masks = [r for r in policies if r["scenario"] == policy]
        mask_by_id = b1.keyed(masks, "scenario policy")
        cases = [simulate(frame, masks, elig, policy, case) for case in CASES]
        simulations.extend(cases)
        by_stratum = {}
        for stratum in STRATA:
            pool = [r for r in frame if r["stratum"] == stratum]
            mask = [r for r in masks if r["stratum"] == stratum]
            current, conditional = (c["strata"][stratum] for c in cases)
            capacity = sum(r["decision"] != "EXCLUDE" for r in mask)
            by_stratum[stratum] = {"frame_count": len(pool), "source_available": sum(r["source_scope"] != "OUT_OF_SCOPE" for r in pool),
                                   "original_priority": sum(r["original_queue_role"] == "provisional_priority" for r in pool),
                                   "original_reserve": sum(r["original_queue_role"] == "reserve" for r in pool),
                                   "policy_decisions": dict(sorted(Counter(r["decision"] for r in mask).items())),
                                   "conditional_policy_surviving_priority": sum(
                                       mask_by_id[row["qa_id"]]["decision"] != "EXCLUDE" and row["original_queue_role"] == "provisional_priority"
                                       for row in pool),
                                   "conditional_policy_surviving_reserve": sum(
                                       mask_by_id[row["qa_id"]]["decision"] != "EXCLUDE" and row["original_queue_role"] == "reserve"
                                       for row in pool),
                                   "currently_review_ready": current["simulated_count"], "current_shortfall": current["shortfall"],
                                   "conditional_capacity_if_all_holds_cleared": capacity,
                                   "conditional_target_simulated_count": conditional["simulated_count"],
                                   "conditional_target_shortfall": conditional["shortfall"],
                                   "conditional_replacements": len(conditional["replacement_events"])}
        reports.append(tagged(scenario=policy, scenario_status="PROPOSED", approved=False, by_stratum=by_stratum,
                              attack_family_sensitivity={family: {s: {"currently_verified_eligible": 0,
                                   "optimistic_capacity_if_unknown_family_and_primary_reviews_pass": by_stratum[s]["conditional_capacity_if_all_holds_cleared"],
                                   "optimistic_target_bound": by_stratum[s]["conditional_target_simulated_count"]} for s in STRATA}
                                                         for family in REQUIREMENTS},
                              statistical_power_or_adequacy="NOT_ASSESSED_NO_JUSTIFIED_MODEL"))
    return deepcopy({"frame_order.jsonl": frame, "eligibility.jsonl": elig, "policy_scenarios.jsonl": policies,
                     "simulations.jsonl": simulations,
                     "feasibility.json": tagged(target_proposed={s: TARGET for s in STRATA},
                         ordering_rule="STRATUM_RECENT_PAST_THEN_ORIGINAL_RESERVE_RANK_THEN_QA_ID; EXISTING_PRIORITY_SEATS_THEN_ORDERED_RESERVES",
                         random_seed="NOT_APPLICABLE_NO_RANDOMIZATION", reports=reports,
                         temporal_intent="UNKNOWN_INDEPENDENT_OF_RECENT_PAST_STRATUM",
                         final_selection_approved=False, exposure_policy_approved=False, eligibility_rules_approved=False)})


def validate(outputs, context):
    frame_ids = set(b1.keyed(context["frame"], "input frame"))
    for name in ("frame_order.jsonl", "eligibility.jsonl"):
        indexed = b1.keyed(outputs[name], name)
        if len(indexed) != 400 or set(indexed) != frame_ids:
            raise ValueError("changed fixed frame")
    if b1.canonical(outputs) != b1.canonical(derive(context)):
        raise ValueError("simulation differs from pinned rules or invents approval/eligibility")
    return tagged(valid=True, frame_count=400, scientific_approval_granted=False, final_sample_created=False)


def load(repo, recovered, b1_root, b2_root):
    if b1.sha(b1_root / "manifest.jsonl") != b2.BASELINE_HASH:
        raise ValueError("STOP: B1 manifest mismatch")
    if b1.sha(b2_root / "sha256.json") != "1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0":
        raise ValueError("STOP: B2 checksums manifest mismatch")
    b2.run(repo, recovered, b1_root, b2_root, validate_only=True)
    frame, exposure = b1.jsonl(b1_root / "manifest.jsonl"), b1.jsonl(b2_root / "exposure.jsonl")
    inventory = deepcopy(b1.strict_json((b2_root / "source_inventory.json").read_bytes())["inputs"])
    for root in (b1_root, b2_root):
        for path in sorted(root.iterdir()):
            relative = path.relative_to(repo).as_posix()
            inventory["C1/" + relative] = {"root": "repository", "path": relative, "sha256": b1.sha(path), "bytes": path.stat().st_size}
    for relative in ("src/eval/sampling_preparation.py", "results/week6_sampling_draft/screening_batch_v1/screening_batch_ids.jsonl"):
        path = repo / relative
        inventory["C1/" + relative] = {"root": "repository", "path": relative, "sha256": b1.sha(path), "bytes": path.stat().st_size}
    original = b1.keyed(b1.jsonl(repo / "results/week6_sampling_draft/screening_batch_v1/screening_batch_ids.jsonl"), "original frame")
    if set(original) != {r["qa_id"] for r in frame}:
        raise ValueError("B1 differs from original 400-ID frame")
    for row in frame:
        if (row["stratum"], row["reserve_rank"]) != (original[row["qa_id"]]["recent_or_past"], original[row["qa_id"]]["reserve_rank"]):
            raise ValueError("original stratum/rank changed")
    return {"frame": frame, "exposure": exposure, "inputs": inventory}


def run(repo, recovered, b1_root, b2_root, output, *, validate_only=False):
    repo, recovered, b1_root, b2_root, output = map(lambda p: Path(p).resolve(), (repo, recovered, b1_root, b2_root, output))
    protected = [recovered, b1_root, b2_root] + [repo / name for name in ("data", "logs", "results", "src", "tests", "docs")]
    if repo not in output.parents or any(output == p or p in output.parents or output in p.parents for p in protected):
        raise ValueError("output overlaps protected inputs")
    if output.exists() and not validate_only:
        raise FileExistsError("never overwrite a preparation artifact")
    context = load(repo, recovered, b1_root, b2_root)
    outputs = derive(context)
    outputs["validation.json"] = validate(outputs, context)
    outputs["source_inventory.json"] = tagged(inputs=context["inputs"], held_out_attack_outcomes_inspected=False,
                                            sampling_rule_uses_attack_outcomes=False,
                                            baseline_revalidation_reads_historical_review_exports=True,
                                            b1_manifest_sha256=b2.BASELINE_HASH,
                                            b2_checksums_sha256="1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0")
    roots = {"repository": repo, "recovered": recovered}
    for source in context["inputs"].values():
        if b1.sha(roots[source["root"]] / source["path"]) != source["sha256"]:
            raise ValueError("input changed during preparation")
    if validate_only:
        for name, value in outputs.items():
            observed = b1.jsonl(output / name) if name.endswith(".jsonl") else b1.strict_json((output / name).read_bytes())
            if b1.canonical(observed) != b1.canonical(value):
                raise ValueError("preparation output changed: " + name)
        hashes = b1.strict_json((output / "sha256.json").read_bytes())
        if set(hashes) != set(outputs) or any(b1.sha(output / name) != h for name, h in hashes.items()):
            raise ValueError("preparation output checksum mismatch")
        return outputs["validation.json"]
    output.mkdir(parents=True, exist_ok=False)
    for name, value in outputs.items():
        text = "".join(b1.canonical(row) + "\n" for row in value) if name.endswith(".jsonl") else b1.canonical(value) + "\n"
        (output / name).write_bytes(text.encode("ascii"))
    (output / "sha256.json").write_bytes((b1.canonical({p.name: b1.sha(p) for p in sorted(output.iterdir())}) + "\n").encode("ascii"))
    return outputs["validation.json"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--recovered-root", type=Path, required=True)
    parser.add_argument("--b1", type=Path, default=Path("audits/p0_b1_v1"))
    parser.add_argument("--b2", type=Path, default=Path("audits/p0_b2_v1"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    print(b1.canonical(run(args.repo, args.recovered_root, args.b1, args.b2, args.out_dir, validate_only=args.validate_only)))


if __name__ == "__main__":
    main()
