"""P0-B2: reconcile recorded claims and activity, never certify their authority."""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import re

from . import evidence_admissibility as b1

VERSION = "chronoguard-review-authority/p0-b2-v1"
BASELINE_HASH = "317fd7c4652fd6d62614d064b2f6c673405323b32d78062acc95ae295a802b44"
GROUPS = {
    "semantic": ("semantic_support", "assistant_preliminary_semantic_support", "semantic_preliminary"),
    "alias_quality": ("gold_alias_quality", "assistant_preliminary_alias_quality", "alias_preliminary"),
    "temporal": ("temporal_suitability", "temporal_status"),
    "human_verification": ("human_verified",),
}
EMPTY_ASSESSMENTS = {"", "not_assessed", "not_certified", "not_adjudicated", "pending",
                     "not_semantically_assessed", "unknown", "not_independently_adjudicated"}
DERIVED_FIELDS = {"derived_answer", "question_time_answer", "canonical_answer", "proposed_answer",
                  "corrected_answer", "revised_answer", "distinct_normalized_aliases_json"}
FALSE_FIELDS = {"false_claim", "false_proposition", "proposed_false_claim", "false_expressions", "false_state"}


def claimed_true(value):
    return value is True or (type(value) is str and value.strip().casefold() == "true")


def values(claims, names):
    return {name: claims[name] for name in names if name in claims and claims[name] not in (None, "")}


def substantive(claims):
    """Recorded assessment exists; this says nothing about correctness or authorship."""
    return any(str(value).strip().casefold() not in EMPTY_ASSESSMENTS
               for value in values(claims, GROUPS["semantic"]).values())


def annotation_type(claims):
    if claimed_true(claims.get("human_verified")):
        return "CLAIMED_HUMAN_ASSESSMENT_UNAUTHENTICATED"
    stage = " ".join(str(claims.get(f, "")) for f in ("review_stage", "review_status", "screening_method")).casefold()
    if substantive(claims):
        return "ASSISTANT_OR_PRELIMINARY_ASSESSMENT" if "assistant" in stage or "preliminary" in stage or "assistant_preliminary_semantic_support" in claims else "UNATTRIBUTED_SEMANTIC_CLAIM"
    return "SCREENING_OR_UNREVIEWED_EXPORT"


def array_claim(value):
    """Decode declared list syntax only; never infer a new scientific answer."""
    if type(value) is list:
        return value
    if type(value) is not str:
        return None
    for parser in (b1.strict_json, ast.literal_eval):
        try:
            result = parser(value)
            if type(result) is list and all(type(item) is str for item in result):
                return result
        except (ValueError, SyntaxError, TypeError):
            pass
    return None


def collect_annotations(records, frame, input_hashes):
    """Deduplicate identical file/row identities; preserve every physical location."""
    merged = {}
    for item in records:
        claims, reference = item["claims"], item["reference"]
        if b1.digest(claims) != reference["record_sha256"]:
            raise ValueError("annotation record hash mismatch")
        if reference["source"] not in input_hashes:
            raise ValueError("unknown annotation source")
        source_hash = input_hashes[reference["source"]]
        coordinate = reference.get("physical_line", reference.get("json_pointer"))
        if not (type(coordinate) is int and coordinate > 0 or type(coordinate) is str and coordinate.startswith("/")):
            raise ValueError("invalid source row coordinate")
        aid = b1.digest({"artifact_sha256": source_hash, "coordinate": coordinate,
                         "record_sha256": reference["record_sha256"]})
        if aid in merged:
            if merged[aid]["claims"] != claims:
                raise ValueError("conflicting duplicate annotation identity")
            if reference not in merged[aid]["locations"]:
                merged[aid]["locations"].append(reference)
            continue
        qid = claims.get("qa_id", claims.get("source_qa_id"))
        if type(qid) is not str or not qid.strip():
            qid = None
        merged[aid] = {"annotation_id": aid, "qa_id": qid,
                       "frame_membership": "IN_FRAME" if qid in frame else ("OUT_OF_FRAME" if qid else "MISSING_STABLE_QA_ID"),
                       "source_artifact_sha256": source_hash, "locations": [reference],
                       "record_sha256": reference["record_sha256"], "claims": claims,
                       "annotation_type": annotation_type(claims),
                       "claimed_reviewer_identity": values(claims, ("reviewer_id", "reviewer", "reviewer_name", "adjudicator_id")),
                       "claimed_review_date": values(claims, ("review_date", "date", "adjudication_date")),
                       "claimed_human_verification": claims.get("human_verified"),
                       "reviewer_authority": "NOT_ESTABLISHED", "second_independent_review": "NOT_ESTABLISHED",
                       "adjudication_claims": values(claims, ("adjudication", "adjudication_status", "adjudicator_id", "review_stage", "review_status")),
                       "adjudication_presence": "RECORDED_PRELIMINARY_CLAIM" if any("adjudicat" in str(v).casefold() for v in
                           values(claims, ("adjudication", "adjudication_status", "review_stage", "review_status")).values()) else
                           ("SOURCE_TITLE_ONLY" if "adjudicat" in reference["source"].casefold() else "NO_AUTHENTICATED_ADJUDICATION_RECORD"),
                       "independent_adjudication": "NOT_ESTABLISHED",
                       "missing_authority_evidence": ["AUTHENTICATED_REVIEWER_IDENTITY_DATE_AND_INDEPENDENCE",
                                                      "SECOND_INDEPENDENT_REVIEW_LINK", "ADJUDICATION_AUTHORITY_IF_REQUIRED"],
                       "duplicate_claim_group": b1.digest({"qa_id": qid, "claims": claims})}
    counts = Counter(a["duplicate_claim_group"] for a in merged.values())
    for a in merged.values():
        a["locations"].sort(key=b1.canonical)
        a["identical_claim_records"] = counts[a["duplicate_claim_group"]]
        a["duplicate_file_locations"] = len(a["locations"])
        a["independent_vote_count"] = 0
    return sorted(merged.values(), key=lambda a: (a["qa_id"] or "", a["annotation_id"]))


def layer_differences(annotations):
    differences = []
    for group, fields in GROUPS.items():
        observed = defaultdict(list)
        for a in annotations:
            for name, value in values(a["claims"], fields).items():
                token = str(value).strip().casefold()
                observed[token].append({"annotation_id": a["annotation_id"], "field": name, "claimed_value": value})
        if len(observed) < 2:
            continue
        keys = set(observed)
        supported = any(s.startswith(("supported", "preliminary_supported", "historical_support")) for s in keys)
        opposed = any(s.startswith(("unsupported", "contradictory")) for s in keys)
        kind = ("SUBSTANTIVE_OPPOSITION_CLAIMS" if group == "semantic" and supported and opposed else
                "HUMAN_VERIFICATION_FLAG_DIFFERENCE" if group == "human_verification" else
                "LAYER_STATUS_OR_QUALIFIER_DIFFERENCE")
        differences.append({"dimension": group, "type": kind,
                            "values": {k: sorted(v, key=b1.canonical) for k, v in sorted(observed.items())},
                            "resolution": "NOT_ADJUDICATED", "interpretation": "RECORDED_CLAIM_DIFFERENCE_NOT_PROVEN_SCIENTIFIC_DISAGREEMENT"})
    return differences


def derive(context):
    frame = context["frame"]
    if len(frame) != 400:
        raise ValueError("requires exact 400-ID baseline")
    annotations = collect_annotations(context["records"], frame, {k: v["sha256"] for k, v in context["inputs"].items()})
    by_id = defaultdict(list)
    quarantine = []
    for a in annotations:
        if a["frame_membership"] != "IN_FRAME":
            quarantine.append(a)
        else:
            by_id[a["qa_id"]].append(a)
    reviews, exposures, keys, conflicts, missing = [], [], [], [], []
    audited_hashes = {v["sha256"] for v in context["inputs"].values()}
    for qid in sorted(frame):
        base, aa = frame[qid], by_id[qid]
        variants = {v["variant_id"] for v in base["evidence"]["variants"]}
        bindings = []
        derived, false_keys, originals = [], [], []
        for a in aa:
            claims = a["claims"]
            refs = values(claims, ("supporting_variant_id", "supporting_variant_ids", "evidence_variant_ids_json"))
            declared = sorted({vid for value in refs.values() for vid in re.findall(r"cgei:v1:variant:[0-9a-f]{64}", str(value))})
            hashes = {name: {"claimed_sha256": value, "resolves_to_audited_bytes": type(value) is str and value in audited_hashes}
                      for name, value in claims.items() if name.endswith("sha256") and value}
            bindings.append({"annotation_id": a["annotation_id"], "declared_variant_ids": declared,
                             "unresolved_or_wrong_question_variants": sorted(set(declared) - variants),
                             "supporting_evidence_status": "NO_EXPLICIT_VARIANT_REFERENCE" if substantive(claims) and not declared else
                             ("UNRESOLVED_VARIANT_REFERENCE" if set(declared) - variants else
                              "DECLARED_REFERENCES_MATCH_BASELINE" if declared else "NO_SUPPORT_ASSERTION_VERIFIED"),
                             "claimed_source_hashes": hashes,
                             "question_text_matches": claims["question"] == base["question"]["text"] if claims.get("question") else None})
            for name in sorted(DERIVED_FIELDS):
                if name in claims and claims[name] not in (None, ""):
                    derived.append({"annotation_id": a["annotation_id"], "field": name, "verbatim_proposal": claims[name],
                                    "kind": "NORMALIZED_ALIAS_PROPOSAL" if name == "distinct_normalized_aliases_json" else "QUESTION_TIME_ANSWER_PROPOSAL",
                                    "authority": "NOT_ESTABLISHED", "approved": False})
            for name in sorted(FALSE_FIELDS):
                if name in claims and claims[name] not in (None, ""):
                    false_keys.append({"annotation_id": a["annotation_id"], "field": name, "verbatim_proposal": claims[name],
                                       "claimed_approval": values(claims, ("approval_status", "approved", "claim_key_status")), "approved": False})
            if claims.get("payload_schema") and claims.get("text"):
                false_keys.append({"annotation_id": a["annotation_id"], "field": "text", "verbatim_proposal": claims["text"], "approved": False})
            for name in ("gold_answers_original_json", "gold_answers_json", "gold_answers", "gold_answers_original", "additional_answers_json"):
                if not claims.get(name):
                    continue
                decoded = array_claim(claims[name])
                target = base["keys"]["answers_additional" if name == "additional_answers_json" else "answers"]
                originals.append({"annotation_id": a["annotation_id"], "field": name, "verbatim_value": claims[name],
                                  "decoded_list": decoded, "comparison": "UNPARSEABLE" if decoded is None else
                                  ("MATCHES_ORIGINAL" if decoded == target else "DIFFERS_FROM_ORIGINAL"),
                                  "authority": "IMPORTED_COPY_NOT_ORIGINAL_AUTHORITY"})
        differences = layer_differences(aa)
        for original in originals:
            if original["comparison"] != "MATCHES_ORIGINAL":
                differences.append({"dimension": "original_key_copy", "type": original["comparison"],
                                    "annotation_id": original["annotation_id"], "field": original["field"],
                                    "resolution": "NOT_ADJUDICATED"})
        events = deepcopy(context["events"].get(qid, []))
        assessments = [a["annotation_id"] for a in aa if substantive(a["claims"])]
        prepared = bool(aa or context["mentions"].get(qid))
        confirmed = bool(assessments or events)
        exposure_status = ("CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY" if confirmed else
                           "POSSIBLE_EXPOSURE_REQUIRES_REVIEW" if prepared else
                           "NO_RECORDED_EXPOSURE" if context.get("coverage_complete") is True else "UNKNOWN_INCOMPLETE_COVERAGE")
        # The observation below describes an artifact, never a proven human read
        # or an approved benchmark exclusion rule.
        exposures.append({"qa_id": qid, "status": exposure_status,
                          "recorded_specific_exposure": "PRESENT" if confirmed or prepared else "NONE_IN_AUDITED_SOURCES_BEYOND_FRAME_SCREENING",
                          "coverage_complete": context.get("coverage_complete") is True,
                          "specific_event_records": events, "assessment_annotation_ids": assessments,
                          "prepared_annotation_ids": [a["annotation_id"] for a in aa],
                          "document_mentions": context["mentions"].get(qid, []),
                          "baseline_screening_activity": base["source_records"].get("screening_audit"),
                          "human_access_independently_authenticated": False,
                          "eligibility_decision": "NOT_MADE_NO_APPROVED_EXPOSURE_POLICY"})
        reviews.append({"qa_id": qid, "annotations": aa, "source_binding_checks": bindings,
                        "independent_reviewer_authority": "NOT_ESTABLISHED", "second_independent_review": "NOT_ESTABLISHED",
                        "independent_adjudication": "NOT_ESTABLISHED", "scientific_disposition": "NOT_ADJUDICATED"})
        keys.append({"qa_id": qid, "original_answers": base["keys"]["answers"],
                     "original_answers_additional": base["keys"]["answers_additional"],
                     "original_key_sha256": base["keys"]["original_key_sha256"],
                     "original_source_record": base["question"]["original_record"],
                     "original_status": "UNCHANGED_ORIGINAL_DATASET_RECORD",
                     "imported_original_key_copies": originals, "derived_proposals": derived,
                     "false_claim_candidates": false_keys, "independently_approved_keys": [],
                     "question_time_answer_adjudication": "NOT_ESTABLISHED",
                     "claim_key_approval": "NOT_ESTABLISHED", "scientific_disposition": "NOT_ADJUDICATED"})
        conflicts.append({"qa_id": qid, "differences": differences, "adjudication": "NOT_PERFORMED"})
        requirements = ["EXPOSURE_POLICY_AND_COVERAGE_RECONCILIATION", "QUESTION_TIME_KEY_SEMANTIC_REVIEW",
                        "FALSE_CLAIM_KEY_REVIEW_AND_AUTHORIZED_DIGEST", "INDEPENDENT_ADJUDICATION_IF_REQUIRED"]
        if aa:
            requirements += ["AUTHENTICATED_REVIEWER_IDENTITY_DATE_AND_INDEPENDENCE", "SECOND_INDEPENDENT_REVIEW"]
        else:
            requirements.append("NO_INDEPENDENT_REVIEW_RECORD_AVAILABLE")
        if any(claimed_true(a["claimed_human_verification"]) for a in aa):
            requirements.append("AUTHENTICATION_FOR_HUMAN_VERIFIED_FLAGS")
        if any(b["unresolved_or_wrong_question_variants"] for b in bindings):
            requirements.append("SUPPORTING_VARIANT_REFERENCE_RECONCILIATION")
        if any(b["supporting_evidence_status"] == "NO_EXPLICIT_VARIANT_REFERENCE" for b in bindings):
            requirements.append("EXPLICIT_EVIDENCE_BINDING_FOR_ASSESSMENT")
        if any(b["question_text_matches"] is False for b in bindings):
            requirements.append("ANNOTATION_QUESTION_TEXT_RECONCILIATION")
        if any(not h["resolves_to_audited_bytes"] for b in bindings for h in b["claimed_source_hashes"].values()):
            requirements.append("UNRESOLVED_DECLARED_SOURCE_HASHES")
        if differences:
            requirements.append("LAYER_DIFFERENCE_RECONCILIATION_WITH_VERSION_AND_AUTHORITY")
        missing.append({"qa_id": qid, "requirements": sorted(requirements), "scientific_disposition": "NOT_ADJUDICATED"})
    count = lambda vals: dict(sorted(Counter(vals).items()))
    summary = {"schema_version": VERSION, "frame_count": 400,
               "review_records_in_frame": sum(len(r["annotations"]) for r in reviews),
               "frame_questions_with_review_exports": sum(bool(r["annotations"]) for r in reviews),
               "questions_with_recorded_assessment": sum(bool(r["assessment_annotation_ids"]) for r in exposures),
               "questions_with_claimed_human_verification": sum(any(claimed_true(a["claimed_human_verification"]) for a in r["annotations"]) for r in reviews),
               "annotation_types": count(a["annotation_type"] for a in annotations if a["frame_membership"] == "IN_FRAME"),
               "quarantined_records": len(quarantine), "quarantine_reasons": count(a["frame_membership"] for a in quarantine),
               "duplicate_file_location_excess": sum(a["duplicate_file_locations"] - 1 for a in annotations),
               "questions_with_layer_differences": sum(bool(r["differences"]) for r in conflicts),
               "questions_with_substantive_opposition_claims": sum(any(d["type"] == "SUBSTANTIVE_OPPOSITION_CLAIMS" for d in r["differences"]) for r in conflicts),
               "exposure_status": count(r["status"] for r in exposures),
               "original_keys_preserved": 400,
               "original_key_copy_mismatches": sum(p["comparison"] == "DIFFERS_FROM_ORIGINAL" for r in keys for p in r["imported_original_key_copies"]),
               "derived_question_time_proposals": sum(p["kind"] == "QUESTION_TIME_ANSWER_PROPOSAL" for r in keys for p in r["derived_proposals"]),
               "normalized_alias_proposals": sum(p["kind"] == "NORMALIZED_ALIAS_PROPOSAL" for r in keys for p in r["derived_proposals"]),
               "false_claim_candidates_in_frame": sum(len(r["false_claim_candidates"]) for r in keys),
               "independently_approved_keys": 0, "authenticated_independent_reviewers": 0,
               "independent_adjudications": 0, "accepted_questions": 0,
               "authority": "AUDIT_OF_RECORDED_CLAIMS_ONLY_NO_SCIENTIFIC_APPROVAL"}
    return deepcopy({"review_authority.jsonl": reviews, "exposure.jsonl": exposures, "keys.jsonl": keys,
            "cross_layer_conflicts.jsonl": conflicts, "missing_authority.jsonl": missing,
            "unbound_records.jsonl": quarantine, "summary.json": summary})


def load(repo, recovered, baseline):
    repo, recovered, baseline = Path(repo).resolve(), Path(recovered).resolve(), Path(baseline).resolve()
    if b1.sha(baseline / "manifest.jsonl") != BASELINE_HASH:
        raise ValueError("STOP: B1 baseline manifest mismatch")
    b1.run(repo, recovered, baseline, validate_only=True)
    rows = b1.jsonl(baseline / "manifest.jsonl")
    frame = b1.keyed(rows, "B1 frame")
    prior_inventory = b1.strict_json((baseline / "source_inventory.json").read_bytes())
    inputs = deepcopy(prior_inventory["inputs"])
    def register(root, relative):
        label = root + ":" + relative
        path = (repo if root == "repository" else recovered) / relative
        inputs[label] = {"root": root, "path": relative, "sha256": b1.sha(path), "bytes": path.stat().st_size}
        return label, path
    for p in sorted(baseline.iterdir()):
        register("repository", p.relative_to(repo).as_posix())
    register("repository", "src/eval/review_authority_audit.py")
    paths = set()
    for sub in ("calibration", "remaining_280"):
        paths.update(("recovered", p.relative_to(recovered).as_posix()) for p in (recovered / sub).glob("*.csv"))
    for p in (repo / "results").rglob("*"):
        if p.is_file() and ((p.suffix == ".csv" and ("review" in p.name or p.parent.name == "judge_validation"))
                            or (p.suffix in {".jsonl", ".json"} and "review" in p.name)):
            paths.add(("repository", p.relative_to(repo).as_posix()))
    records, source_reports = [], []
    for root, relative in sorted(paths):
        label, path = register(root, relative)
        if path.suffix == ".csv":
            located = b1.csv_records(path)
        elif path.suffix == ".jsonl":
            located = list(enumerate(b1.jsonl(path), 1))
        else:
            document = b1.strict_json(path.read_bytes())
            located = [("/" + str(index), row) for index, row in enumerate(document)] if isinstance(document, list) else [("/", document)]
        for line, claims in located:
            if type(claims) is not dict:
                raise ValueError("review export row is not an object")
            reference = b1.ref(label, line, claims) if type(line) is int else {"source": label, "json_pointer": line, "record_sha256": b1.digest(claims)}
            records.append({"reference": reference, "claims": claims})
        source_reports.append({"source": label, "kind": "REVIEW_EXPORT", "records": len(located),
                               "authority": "CLAIMS_ONLY_NO_AUTHENTICATION"})
    # Actual payloads are candidates, not approved claim keys; no state is generated.
    label, path = register("repository", "data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl")
    payloads = b1.jsonl(path)
    for line, claims in enumerate(payloads, 1):
        records.append({"reference": b1.ref(label, line, claims), "claims": claims})
    source_reports.append({"source": label, "kind": "EXISTING_FALSE_PAYLOAD_PROPOSALS", "records": len(payloads), "authority": "NOT_CLAIM_KEY_APPROVAL"})

    events, mentions = defaultdict(list), defaultdict(list)
    for row in rows:
        mentions[row["qa_id"]] = row["development_exposure"]["document_mentions"]
    for relative, kind in (("results/week6_sampling_draft/prefreeze_exposed_ids.jsonl", "EXPLICIT_EXPOSURE_LEDGER"),
                           ("results/week6_sampling_draft/filtered_reserve_v1/exposure_exclusions.jsonl", "EXPOSURE_FILTER_RECORD"),
                           ("data/processed/attack_sources/streamingqa_attack_pilot.jsonl", "PILOT_MEMBERSHIP"),
                           ("data/raw/streamingqa_control_sample.jsonl", "WEEK4_DEVELOPMENT_MEMBERSHIP")):
        label, path = register("repository", relative)
        found, outside = 0, 0
        for line, claim in enumerate(b1.jsonl(path), 1):
            qid = claim.get("source_qa_id", claim.get("qa_id"))
            if qid in frame:
                events[qid].append({"type": kind, "reference": b1.ref(label, line, claim), "claims": claim})
                found += 1
            else:
                outside += 1
        source_reports.append({"source": label, "kind": kind, "frame_matches": found, "outside_frame": outside,
                               "authority": "RECORDED_ACTIVITY_ONLY_NOT_AN_EXCLUSION_DECISION"})
    return {"frame": frame, "inputs": inputs, "records": records, "events": dict(events),
            "mentions": dict(mentions), "coverage_complete": False, "source_reports": source_reports,
            "baseline_manifest_sha256": BASELINE_HASH}


def validate(outputs, context):
    for name in ("review_authority.jsonl", "exposure.jsonl", "keys.jsonl", "cross_layer_conflicts.jsonl", "missing_authority.jsonl"):
        indexed = b1.keyed(outputs[name], name)
        if len(indexed) != 400 or set(indexed) != set(context["frame"]):
            raise ValueError("wrong frame membership: " + name)
    if b1.canonical(outputs) != b1.canonical(derive(context)):
        raise ValueError("reconciliation differs from pinned claims or invents authority/acceptance")
    return {"schema_version": VERSION, "valid": True, "frame_count": 400, "scientific_approval_granted": False}


def run(repo, recovered, baseline, out, *, validate_only=False):
    repo, recovered, baseline, out = map(lambda p: Path(p).resolve(), (repo, recovered, baseline, out))
    protected = [baseline, recovered] + [repo / p for p in ("data", "logs", "results", "src", "tests", "docs")]
    if repo not in out.parents or any(out == p or p in out.parents or out in p.parents for p in protected):
        raise ValueError("output overlaps protected inputs")
    if out.exists() and not validate_only:
        raise FileExistsError("never overwrite an existing audit")
    context = load(repo, recovered, baseline)
    outputs = derive(context)
    result = validate(outputs, context)
    outputs["validation.json"] = result
    outputs["source_inventory.json"] = {"schema_version": VERSION, "baseline_manifest_sha256": BASELINE_HASH,
                                        "inputs": context["inputs"], "sources": context["source_reports"],
                                        "exposure_coverage": "INCOMPLETE_NO_AUTHENTICATED_COMPLETENESS_ATTESTATION",
                                        "reviewer_authority_registry": "NOT_AVAILABLE",
                                        "approved_derived_or_claim_key_registry": "NOT_AVAILABLE"}
    roots = {"repository": repo, "recovered": recovered}
    for value in context["inputs"].values():
        if b1.sha(roots[value["root"]] / value["path"]) != value["sha256"]:
            raise ValueError("source changed during audit")
    if validate_only:
        for name, expected in outputs.items():
            value = b1.jsonl(out / name) if name.endswith(".jsonl") else b1.strict_json((out / name).read_bytes())
            if b1.canonical(value) != b1.canonical(expected):
                raise ValueError("audit report changed: " + name)
        checksums = b1.strict_json((out / "sha256.json").read_bytes())
        if set(checksums) != set(outputs) or any(b1.sha(out / n) != h for n, h in checksums.items()):
            raise ValueError("output checksum mismatch")
        return result
    out.mkdir(parents=True, exist_ok=False)
    for name, value in outputs.items():
        text = "".join(b1.canonical(r) + "\n" for r in value) if name.endswith(".jsonl") else b1.canonical(value) + "\n"
        (out / name).write_bytes(text.encode("ascii"))
    (out / "sha256.json").write_bytes((b1.canonical({p.name: b1.sha(p) for p in sorted(out.iterdir())}) + "\n").encode("ascii"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--recovered-root", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=Path("audits/p0_b1_v1"))
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    print(b1.canonical(run(args.repo, args.recovered_root, args.baseline, args.out_dir, validate_only=args.validate_only)))


if __name__ == "__main__":
    main()
