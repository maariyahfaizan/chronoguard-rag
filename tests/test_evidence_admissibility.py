"""Synthetic B1 fixtures only; no real reviewers, keys or approvals."""
from copy import deepcopy
import hashlib

import pytest

from src.eval import evidence_admissibility as audit
from src.eval.evidence_identity import EvidenceRecord, SourceOccurrence, occurrence_id, variant_id


@pytest.fixture
def context():
    result = {key: {} for key in ("frame", "metadata", "raw", "ledger", "audit", "trace",
                                  "variants", "occurrences", "artifacts", "annotations",
                                  "mentions", "exposure", "inputs")}
    source_hash, sidecar_hash = "a" * 64, "b" * 64
    result["artifacts"][source_hash] = {"sidecar_sha256": sidecar_hash,
                                       "path": "/synthetic/unavailable-source", "verification_basis": "observed_plain_only"}
    for index in range(400):
        qid = f"synthetic-{index:06d}"
        outside = index >= 390
        timestamp = 1191999600 if outside else 1597647600
        parent = "synthetic-parent-" + qid
        frame = {"qa_id": qid, "recent_or_past": "recent" if index < 200 else "past",
                 "reserve_rank": index + 1}
        original = {**frame, "question": "Synthetic question " + qid, "question_ts": 1598166000,
                    "answers": ["30"], "answers_additional": ["thirty"],
                    "evidence_id": parent, "evidence_ts": timestamp}
        result["frame"][qid] = frame
        result["metadata"][qid] = deepcopy(original)
        result["raw"][qid] = deepcopy(original)
        result["ledger"][qid] = {"evidence_availability": "gold_outside_configured_archives" if outside else "present",
                                   "variant_count": 0 if outside else 1,
                                   "source_validation": "provisional_historical_equivalence_unverified",
                                   "temporal_issues": [], "canonical_temporal_coverage": {},
                                   "effective_prequestion_temporal_coverage": {}}
        result["audit"][qid] = {"queue_status": "ineligible_configured_source_scope" if outside else "provisional_priority"}
        result["trace"][qid] = {"original_dataset": audit.ref("original_dataset", index + 1, original),
                                "frame": audit.ref("frame", index + 1, frame)}
        if not outside:
            record = EvidenceRecord(parent + "_0", b"Synthetic evidence", "2020-08-17T00:00:00+00:00")
            vid = variant_id(record)
            variant = {"variant_id": vid, "parent_id": parent, "upstream_passage_id": parent + "_0",
                       "text": "Synthetic evidence", "timestamp": record.timestamp,
                       "reference": audit.ref("variants", index + 1, {"variant_id": vid})}
            result["variants"][parent] = [variant]
            occurrence = {"variant_id": vid, "artifact_sha256": source_hash,
                          "occurrence_id": occurrence_id(SourceOccurrence(source_hash, index + 1)),
                          "physical_line": index + 1, "raw_line_sha256": "c" * 64,
                          "reference": audit.ref("occurrences", index + 1, {"variant_id": vid})}
            result["occurrences"][vid] = [occurrence]
    return result


def test_full_foundation_has_no_acceptance(context):
    rows = audit.build_rows(context)
    assert audit.validate_manifest(rows, context)["row_count"] == 400
    summary = audit.summarize(rows)
    assert summary["by_stratum"] == {"past": 200, "recent": 200}
    assert summary["by_final_disposition"] == {"INELIGIBLE": 10, "UNRESOLVED": 390}
    assert summary["independently_verified_admissible"] == 0
    assert summary["by_review_status"] == {"NOT_REVIEWED": 400}


@pytest.mark.parametrize("change", ["duplicate", "missing", "extra", "missing_source_hash",
    "unsupported_tier", "authenticated_original", "missing_key", "wrong_alias",
    "wrong_question", "wrong_source", "wrong_variant", "conflicting_review",
    "invented_reviewer", "invalid_adjudication", "unsupported_adjudication_status",
    "accepted", "promoted_ineligible", "cleared_exclusion", "missing_field", "wrong_type"])
def test_corrupt_records_fail_closed(context, change):
    rows = audit.build_rows(context)
    row = rows[0]
    if change == "duplicate":
        rows[-1] = deepcopy(rows[0])
    elif change == "missing":
        rows.pop()
    elif change == "extra":
        rows.append({**row, "qa_id": "outside-frame"})
    elif change == "missing_source_hash":
        row["evidence"]["source_artifacts"][0].pop("physical_sha256")
    elif change == "unsupported_tier":
        row["provenance"]["tier"] = "HASH_MATCH_MEANS_AUTHENTIC"
    elif change == "authenticated_original":
        row["provenance"]["tier"] = "AUTHENTICATED_ORIGINAL"
    elif change == "missing_key":
        row["keys"].pop("answers")
    elif change == "wrong_alias":
        row["keys"]["answers_additional"] = ["edited original alias"]
    elif change == "wrong_question":
        row["question"]["text"] = "different question"
    elif change == "wrong_source":
        row["source_records"]["frame"]["source"] = "unknown-source"
    elif change == "wrong_variant":
        row["evidence"]["variants"][0]["variant_id"] = "stale-variant"
    elif change == "conflicting_review":
        row["semantic_support"].update(status="VERIFIED", decision="supported")
    elif change == "invented_reviewer":
        row["independent_review"]["reviewer_ids"] = ["invented"]
    elif change == "invalid_adjudication":
        row["adjudication"]["status"] = "VERIFIED"
    elif change == "unsupported_adjudication_status":
        row["adjudication"]["status"] = "approved"
    elif change == "accepted":
        row["final_disposition"] = "ACCEPTED"
    elif change == "promoted_ineligible":
        rows[-1]["final_disposition"] = "UNRESOLVED"
    elif change == "cleared_exclusion":
        rows[-1]["exclusion_or_unresolved_reasons"] = []
    elif change == "missing_field":
        row.pop("claim")
    elif change == "wrong_type":
        row["reserve_rank"] = True
    with pytest.raises(ValueError):
        audit.validate_manifest(rows, context)


def test_missing_original_question_time_key_is_not_invented(context):
    context["raw"]["synthetic-000000"]["answers"] = []
    with pytest.raises(ValueError, match="question-time key"):
        audit.build_rows(context)


def test_unreviewed_claims_preserved_without_human_authority(context):
    qid = "synthetic-000000"
    claims = {"qa_id": qid, "human_verified": "true", "semantic_support": "supported",
              "reviewer_notes": "Synthetic imported assertion, not real approval"}
    context["annotations"][qid] = [{"reference": audit.ref("prior_csv", 2, claims), "claims": claims}]
    row = audit.build_rows(context)[0]
    assert row["imported_annotations"][0]["claims"] == claims
    assert row["independent_review"] == {"status": "NOT_REVIEWED", "reviewer_ids": [], "decisions": []}
    assert row["semantic_support"] == {"status": "NOT_REVIEWED", "decision": None}
    assert row["review_claim_status"] == "CLAIMED_UNVERIFIED"
    assert row["development_exposure"]["status"] == "UNKNOWN"
    assert row["final_disposition"] == "UNRESOLVED"


def test_explicit_exposure_exclusion_is_separate_from_review_approval(context):
    qid = "synthetic-000000"
    claims = {"qa_id": qid, "primary_heldout_eligible": False}
    context["exposure"][qid] = [{"reference": audit.ref("exposures", 1, claims), "claims": claims}]
    rows = audit.build_rows(context)
    assert rows[0]["provisional_eligibility"] == "INELIGIBLE_EXPOSURE"
    assert rows[0]["semantic_support"]["status"] == "NOT_REVIEWED"
    audit.validate_manifest(rows, context)


def test_out_of_scope_is_explicit_not_a_missing_row(context):
    rows = audit.build_rows(context)
    outside = rows[-10:]
    assert all(r["evidence"]["variants"] == [] for r in outside)
    assert all(r["provenance"]["internal_traceability"] == "NOT_APPLICABLE" for r in outside)
    assert all(r["evidence"]["publication_date_status"] == "UNKNOWN" for r in outside)
    assert all(r["final_disposition"] == "INELIGIBLE" for r in outside)


def test_ordering_and_serialization_are_deterministic(context):
    first = audit.build_rows(context)
    shuffled = deepcopy(context)
    shuffled["frame"] = dict(reversed(list(shuffled["frame"].items())))
    second = audit.build_rows(shuffled)
    assert audit.canonical(first) == audit.canonical(second)
    assert [r["qa_id"] for r in first] == sorted(context["frame"])
    assert hashlib.sha256(audit.canonical(first).encode()).digest() == hashlib.sha256(audit.canonical(second).encode()).digest()


def test_multiline_csv_source_coordinates(tmp_path):
    path = tmp_path / "source.csv"
    path.write_bytes(b'qa_id,notes\nq1,"first\nsecond"\nq2,third\n')
    rows = audit.csv_records(path)
    assert [line for line, _ in rows] == [2, 4]
    assert rows[0][1]["notes"] == "first\nsecond"
