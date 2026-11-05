"""P0-B1: deterministic evidence audit foundation; never scientific acceptance.

Original files are read-only. Existing review claims are preserved, not certified.
The validator re-derives each row from pinned authoritative input records.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

VERSION = "chronoguard-evidence-admissibility/p0-b1-v1"
TIERS = {"AUTHENTICATED_ORIGINAL", "TRACEABLE_RECONSTRUCTED", "UNVERIFIED_OR_UNUSABLE"}
STATES = {"UNKNOWN", "NOT_REVIEWED", "NOT_APPLICABLE", "VERIFIED"}
FAMILIES = ("fabricated_fresh", "stale_evidence", "future_date", "duplicate_fresh",
            "correct_content_wrong_date")
FRAME = Path("results/week6_sampling_draft/screening_batch_v1")
RAW = Path("data/raw/streamingqa_eval.jsonl.gz")
EXPOSURE = Path("results/week6_sampling_draft/prefreeze_exposed_ids.jsonl")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field: " + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs)


def jsonl(path):
    return [strict_json(line) for line in Path(path).read_bytes().splitlines()]


def keyed(rows, name):
    result = {}
    for row in rows:
        qid = row["qa_id"]
        if type(qid) is not str or not qid or qid in result:
            raise ValueError("invalid/duplicate QA ID in " + name)
        result[qid] = row
    return result


def csv_records(path):
    """Preserve the starting physical line even for multiline CSV records."""
    result = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        _ = reader.fieldnames
        start = reader.line_num + 1
        for row in reader:
            result.append((start, row))
            start = reader.line_num + 1
    return result


def ref(source, line, row):
    return {"source": source, "physical_line": line, "record_sha256": digest(row)}


def load_context(repo, recovered):
    """Validate the closed snapshot, immutable frame and raw dataset bindings."""
    from .prepare_week6_review_queue import validate as validate_snapshot
    from . import evidence_identity

    repo, recovered = Path(repo).resolve(), Path(recovered).resolve()
    if (repo / "src/eval/evidence_admissibility.py").resolve() != Path(__file__).resolve():
        raise ValueError("execution code does not belong to the declared repository")
    snapshot = recovered / "development_backup/consolidated_evidence"
    review_root = recovered / "development_backup/development_review"
    inputs = {}
    def register(source, path, root_name):
        root = repo if root_name == "repository" else recovered
        path = Path(path)
        inputs[source] = {"root": root_name, "path": path.relative_to(root).as_posix(),
                          "sha256": sha(path), "bytes": path.stat().st_size}
        return path

    for name in ("evidence_admissibility.py", "prepare_week6_review_queue.py",
                 "consolidate_week6_target_evidence.py", "index_week6_target_evidence.py",
                 "evidence_identity.py"):
        register("code/" + name, repo / "src/eval" / name, "repository")

    # Preserve exact local bytes; compatibility copies exist only in a temp dir.
    names = ("evidence_windows_400.jsonl", "candidate_metadata_400.jsonl", "screening_batch_ids.jsonl")
    frame_paths = [register(key, repo / FRAME / name, "repository")
                   for key, name in zip(("windows", "metadata", "frame"), names)]
    sm = strict_json((snapshot / "manifest.json").read_bytes())
    equivalence = {}
    for source, path, key in zip(("windows", "metadata", "frame"), frame_paths,
                                  ("windows_raw_sha256", "metadata_sha256", "batch_sha256")):
        data = path.read_bytes()
        lf_hash = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
        if sm["inputs"][key] not in {inputs[source]["sha256"], lf_hash}:
            raise ValueError("frame input does not match snapshot: " + source)
        equivalence[source] = {"raw_sha256": inputs[source]["sha256"],
                               "lf_sha256": lf_hash, "snapshot_sha256": sm["inputs"][key],
                               "basis": "RAW" if inputs[source]["sha256"] == sm["inputs"][key] else "LF_EQUIVALENT"}
    with tempfile.TemporaryDirectory(prefix="b1-input-check-", dir=repo) as temporary:
        copies = []
        for source in frame_paths:
            copy = Path(temporary) / source.name
            copy.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
            copies.append(copy)
        manifest, ledger_rows = validate_snapshot(snapshot, *copies)

    register("snapshot_manifest", snapshot / "manifest.json", "recovered")
    for name in manifest["output_sha256"]:
        register("snapshot/" + name, snapshot / name, "recovered")
    for name in ("screening_audit.jsonl", "review_queue.jsonl", "review_queue.csv", "summary.json", "sha256.json"):
        register("review/" + name, review_root / name, "recovered")
    review_summary = strict_json((review_root / "summary.json").read_bytes())
    if review_summary["manifest_sha256"] != inputs["snapshot_manifest"]["sha256"]:
        raise ValueError("review queue snapshot mismatch")
    for name, expected in review_summary["output_sha256"].items():
        if sha(review_root / name) != expected:
            raise ValueError("review export hash mismatch: " + name)
    for name, expected in strict_json((review_root / "sha256.json").read_bytes()).items():
        if sha(review_root / name) != expected:
            raise ValueError("review checksum mismatch: " + name)
    backup = register("backup_inventory", recovered / "development_backup/BACKUP_FILE_MANIFEST.json", "recovered")
    for entry in strict_json(backup.read_bytes()):
        relative = Path(entry["archive_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe backup inventory path")
        path = recovered / "development_backup" / relative
        if sha(path) != entry["sha256"] or path.stat().st_size != entry["size_bytes"]:
            raise ValueError("backup inventory mismatch: " + str(relative))
        source = "backup/" + relative.as_posix()
        register(source, path, "recovered")
    for path in sorted((recovered / "original_archives").glob("*.zip")):
        register("backup_archive/" + path.name, path, "recovered")

    frame_rows, metadata_rows = jsonl(frame_paths[2]), jsonl(frame_paths[1])
    frame, metadata, ledger = (keyed(rows, label) for rows, label in
                              ((frame_rows, "frame"), (metadata_rows, "metadata"), (ledger_rows, "ledger")))
    if len(frame) != 400 or set(metadata) != set(frame) or set(ledger) != set(frame):
        raise ValueError("expected identical 400-ID frame/metadata/ledger membership")
    if Counter(r["recent_or_past"] for r in frame_rows) != Counter(recent=200, past=200):
        raise ValueError("frame stratum mismatch")
    trace = defaultdict(dict)
    for source, rows in (("frame", frame_rows), ("windows", jsonl(frame_paths[0])),
                         ("metadata", metadata_rows), ("snapshot/recovery_ledger.jsonl", ledger_rows)):
        if set(keyed(rows, source)) != set(frame):
            raise ValueError("input membership mismatch: " + source)
        for line, row in enumerate(rows, 1):
            trace[row["qa_id"]][source] = ref(source, line, row)
    raw_path = register("original_dataset", repo / RAW, "repository")
    raw = {}
    with gzip.open(raw_path, "rb") as stream:
        for line, data in enumerate(stream, 1):
            row = strict_json(data)
            if row["qa_id"] not in frame:
                continue
            if row["qa_id"] in raw:
                raise ValueError("duplicate original dataset QA ID")
            qid = row["qa_id"]
            raw[qid] = row
            trace[qid]["original_dataset"] = ref("original_dataset", line, row)
            for field in ("question", "question_ts", "answers", "answers_additional", "evidence_id", "evidence_ts", "recent_or_past"):
                if metadata[qid].get(field) != row.get(field):
                    raise ValueError("original question/key mismatch: " + qid + ":" + field)
    if set(raw) != set(frame):
        raise ValueError("missing original dataset question-time keys")
    for qid in frame:
        for field, value in metadata[qid].items():
            if ledger[qid].get(field) != value:
                raise ValueError("snapshot/metadata mismatch: " + qid + ":" + field)
        if any(metadata[qid][k] != v for k, v in frame[qid].items()):
            raise ValueError("frame metadata binding mismatch")

    # Recompute variant/occurrence identities; never derive dates from an ID prefix.
    variants, occurrences = defaultdict(list), defaultdict(list)
    all_variants = {}
    for line, row in enumerate(jsonl(snapshot / "variants.jsonl"), 1):
        record = evidence_identity.EvidenceRecord(row["upstream_passage_id"], row["text"].encode("utf-8"), row["timestamp"], tuple(row["evidence_fields"].items()))
        if evidence_identity.variant_id(record) != row["variant_id"] or row["variant_id"] in all_variants:
            raise ValueError("invalid/duplicate variant identity")
        value = {**row, "reference": ref("snapshot/variants.jsonl", line, row)}
        variants[row["parent_id"]].append(value)
        all_variants[row["variant_id"]] = value
    artifacts = {a["physical_sha256"]: a for a in manifest["artifacts"]}
    for line, row in enumerate(jsonl(snapshot / "occurrences.jsonl"), 1):
        occurrence = evidence_identity.SourceOccurrence(row["artifact_sha256"], row["physical_line"])
        if (row["variant_id"] not in all_variants or row["artifact_sha256"] not in artifacts
                or evidence_identity.occurrence_id(occurrence) != row["occurrence_id"]):
            raise ValueError("invalid occurrence/source reference")
        occurrences[row["variant_id"]].append({**row, "reference": ref("snapshot/occurrences.jsonl", line, row)})
    audit_rows = jsonl(review_root / "screening_audit.jsonl")
    audit = keyed(audit_rows, "screening audit")
    if set(audit) != set(frame):
        raise ValueError("screening audit membership mismatch")
    for line, row in enumerate(audit_rows, 1):
        qid = row["qa_id"]
        if any(row[k] != v for k, v in ledger[qid].items()):
            raise ValueError("screening audit differs from ledger")
        if {r["variant_id"] for r in row["evidence_variants"]} != {r["variant_id"] for r in variants[row["evidence_id"]]}:
            raise ValueError("screening audit variants differ")
        trace[qid]["screening_audit"] = ref("review/screening_audit.jsonl", line, row)

    exposure_path = register("exposure_ledger", repo / EXPOSURE, "repository")
    exposure = defaultdict(list)
    for line, row in enumerate(jsonl(exposure_path), 1):
        exposure[row["qa_id"]].append({"reference": ref("exposure_ledger", line, row), "claims": row})
    annotations, mentions = defaultdict(list), defaultdict(list)
    annotation_inventory = []
    for directory in ("calibration", "remaining_280"):
        for path in sorted((recovered / directory).iterdir()):
            if path.suffix not in {".csv", ".md"}:
                continue
            source = "prior_review/" + path.relative_to(recovered).as_posix()
            register(source, path, "recovered")
            if path.suffix == ".csv":
                located = csv_records(path)
                imported = [row for _, row in located]
                for line, row in located:
                    qid = row.get("qa_id")
                    if qid in frame:
                        annotations[qid].append({"reference": ref(source, line, row), "claims": row})
                annotation_inventory.append({"source": source, "records": len(imported),
                                             "frame_records": sum(r.get("qa_id") in frame for r in imported),
                                             "named_reviewer_field_present": any("reviewer_id" in r for r in imported),
                                             "human_verified_true_claims": sum(r.get("human_verified", "").lower() == "true" for r in imported)})
            else:
                import re
                for line, text in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                    for qid in sorted(set(re.findall(r"eval-\d{6}", text)) & frame.keys()):
                        mentions[qid].append(ref(source, line, text))
    # Inventory historical annotations separately; never silently text-match an
    # unidentified pilot/FreshQA row to a new frame question.
    for relative in ("results/gold_evidence_manual_review.jsonl", "results/stale_evidence_review.jsonl",
                     "results/pilot_judge_review.csv", "results/judge_validation/annotation.csv",
                     "results/judge_validation/annotation_rater2.csv"):
        path = register("legacy_annotations/" + relative, repo / relative, "repository")
        located = csv_records(path) if path.suffix == ".csv" else list(enumerate(jsonl(path), 1))
        matches = 0
        no_identity = 0
        for line, row in located:
            qid = row.get("qa_id", row.get("source_qa_id"))
            no_identity += not bool(qid)
            if qid in frame:
                matches += 1
                annotations[qid].append({"reference": ref("legacy_annotations/" + relative, line, row), "claims": row})
        annotation_inventory.append({"source": "legacy_annotations/" + relative,
                                     "records": len(located), "frame_records": matches,
                                     "records_without_stable_qa_id": no_identity,
                                     "authority": "LEGACY_CLAIMS_ONLY_NOT_INDEPENDENT_ADJUDICATION"})
    return {"frame": frame, "metadata": metadata, "raw": raw, "ledger": ledger,
            "audit": audit, "trace": dict(trace), "variants": dict(variants),
            "occurrences": dict(occurrences), "artifacts": artifacts,
            "annotations": dict(annotations), "mentions": dict(mentions),
            "exposure": dict(exposure), "inputs": inputs,
            "input_equivalence": equivalence, "annotation_inventory": annotation_inventory,
            "source_manifest": manifest}


def build_rows(context):
    rows = []
    for qid in sorted(context["frame"]):
        meta, ledger = context["metadata"][qid], context["ledger"][qid]
        original = context["raw"][qid]
        if (type(original.get("answers")) is not list or not original["answers"]
                or any(type(a) is not str or not a.strip() for a in original["answers"])
                or type(original.get("answers_additional", [])) is not list):
            raise ValueError("missing/malformed original question-time key: " + qid)
        selected = sorted(context["variants"].get(meta["evidence_id"], []), key=lambda r: r["variant_id"])
        availability = ledger["evidence_availability"]
        outside = availability == "gold_outside_configured_archives"
        if outside and selected:
            raise ValueError("out-of-scope case unexpectedly has evidence")
        if bool(selected) != (availability == "present") or len(selected) != ledger["variant_count"]:
            raise ValueError("ledger evidence availability mismatch: " + qid)
        annotation = context["annotations"].get(qid, [])
        mentions = context["mentions"].get(qid, [])
        explicit = context["exposure"].get(qid, [])
        excluded = any(r["claims"].get("primary_heldout_eligible") is False for r in explicit)
        evidence = []
        for variant in selected:
            occ = sorted(context["occurrences"].get(variant["variant_id"], []), key=lambda r: r["occurrence_id"])
            if not occ:
                raise ValueError("variant without source occurrences")
            evidence.append({"variant_id": variant["variant_id"],
                             "upstream_passage_id": variant["upstream_passage_id"],
                             "parent_id": variant["parent_id"], "reference": variant["reference"],
                             "text_sha256": hashlib.sha256(variant["text"].encode("utf-8")).hexdigest(),
                             "timestamp": variant["timestamp"],
                             "date_basis": "RECONSTRUCTED_PASSAGE_TIMESTAMP",
                             "publication_authentication": "UNKNOWN", "occurrences": occ})
        source_hashes = sorted({o["artifact_sha256"] for v in evidence for o in v["occurrences"]})
        source_refs = [{"physical_sha256": h,
                        "sidecar_sha256": context["artifacts"][h]["sidecar_sha256"],
                        "manifest_reference": {"source": "snapshot_manifest", "artifact_physical_sha256": h,
                                               "record_sha256": digest(context["artifacts"][h])},
                        "declared_source_path": context["artifacts"][h]["path"],
                        "verification_basis": context["artifacts"][h]["verification_basis"],
                        "original_source_authentication": "UNKNOWN",
                        "original_bytes_available_here": "UNKNOWN"} for h in source_hashes]
        missing = ["original_source_authentication", "independent_reviewer_identity_and_date",
                   "semantic_support", "temporal_validity", "adjudication",
                   "question_time_key_semantic_review", "derived_key_registry",
                   "candidate_false_claim", "approved_claim_key", "exposure_reconciliation",
                   "attack_family_review"]
        if outside:
            missing.append("evidence_outside_configured_archives")
        if any(r["claims"].get("human_verified", "").lower() == "true" for r in annotation):
            missing.append("identity_and_authority_for_imported_human_verified_claim")
        reasons = (["GOLD_EVIDENCE_OUTSIDE_CONFIGURED_ARCHIVES"] if outside else
                   ["INDEPENDENT_SEMANTIC_TEMPORAL_AND_PROVENANCE_REVIEW_REQUIRED"])
        if excluded:
            reasons.append("EXPLICIT_DEVELOPMENT_EXPOSURE_EXCLUSION")
        elif annotation or mentions:
            reasons.append("PRIOR_DEVELOPMENT_REVIEW_ARTIFACTS_REQUIRE_EXPOSURE_RECONCILIATION")
        row = {"schema_version": VERSION, "qa_id": qid,
               "stratum": meta["recent_or_past"], "reserve_rank": meta["reserve_rank"],
               "question": {"dataset": "StreamingQA", "original_identity_status": "VERIFIED",
                            "text": original["question"], "text_sha256": digest(original["question"]),
                            "question_ts": original["question_ts"],
                            "original_record": context["trace"][qid]["original_dataset"]},
               "keys": {"original_status": "VERIFIED", "original_basis": "UNCHANGED_DATASET_ANSWER_LIST",
                        "answers": original["answers"], "answers_additional": original.get("answers_additional", []),
                        "original_key_sha256": digest({"answers": original["answers"], "answers_additional": original.get("answers_additional", [])}),
                        "question_time_semantic_status": "NOT_REVIEWED", "adjudicated_answer": None,
                        "derived_key_status": "UNKNOWN", "derived_key_reference": None},
               "claim": {"candidate_status": "UNKNOWN", "false_proposition": None,
                         "claim_key_status": "NOT_REVIEWED", "claim_key_id": None,
                         "claim_key_sha256": None, "approval_reference": None},
               "evidence": {"parent_id": meta["evidence_id"], "dataset_evidence_ts": meta["evidence_ts"],
                            "dataset_date_basis": "ORIGINAL_DATASET_EVIDENCE_TIMESTAMP",
                            "availability": "OUT_OF_SCOPE" if outside else "AVAILABLE_RECONSTRUCTED",
                            "scope_status": "VERIFIED", "variants": evidence, "source_artifacts": source_refs,
                            "publication_date_status": "UNKNOWN"},
               "provenance": {"tier": "UNVERIFIED_OR_UNUSABLE" if outside else "TRACEABLE_RECONSTRUCTED",
                              "internal_traceability": "NOT_APPLICABLE" if outside else "VERIFIED",
                              "original_authentication": "UNKNOWN",
                              "basis": "CLOSED_SNAPSHOT_AND_OCCURRENCE_TRACE_ONLY",
                              "source_validation_claim": ledger["source_validation"]},
               "semantic_support": {"status": "NOT_REVIEWED", "decision": None},
               "temporal_validity": {"status": "NOT_REVIEWED", "decision": None,
                                     "reported_temporal_issues": ledger["temporal_issues"],
                                     "canonical_coverage": ledger["canonical_temporal_coverage"],
                                     "effective_coverage": ledger["effective_prequestion_temporal_coverage"]},
               "independent_review": {"status": "NOT_REVIEWED", "reviewer_ids": [], "decisions": []},
               "adjudication": {"status": "NOT_REVIEWED", "reviewer_id": None, "rationale": None, "date": None},
               "development_exposure": {"status": "VERIFIED" if excluded else "UNKNOWN",
                                        "explicit_exclusion_records": explicit,
                                        "independent_exclusion_status": "EXCLUDED" if excluded else "UNRESOLVED",
                                        "prior_review_artifact_present": bool(annotation or mentions),
                                        "document_mentions": mentions},
               "imported_annotations": annotation,
               "review_claim_status": "CLAIMED_UNVERIFIED" if annotation else "NOT_REVIEWED",
               "attack_family_eligibility": {family: {"status": "INELIGIBLE_SOURCE_SCOPE" if outside else
                                                     ("INELIGIBLE_EXPOSURE" if excluded else "NOT_REVIEWED"),
                                                     "scientifically_approved": False} for family in FAMILIES},
               "queue_status_claim": context["audit"][qid]["queue_status"],
               "provisional_eligibility": "INELIGIBLE_SOURCE_SCOPE" if outside else
                                          ("INELIGIBLE_EXPOSURE" if excluded else "REVIEW_REQUIRED"),
               "final_disposition": "INELIGIBLE" if outside or excluded else "UNRESOLVED",
               "disposition_scope": "ENGINEERING_AUDIT_ONLY_NOT_SCIENTIFIC_ACCEPTANCE",
               "exclusion_or_unresolved_reasons": reasons,
               "missing_evidence": sorted(missing), "source_records": context["trace"][qid]}
        rows.append(row)
    # Exported rows must not alias the pinned context: an accidental row edit
    # must not change the reference facts used by the validator.
    return deepcopy(rows)


def validate_manifest(rows, context):
    """Fail closed on changes to pinned facts, invented reviews or promotions.

    This B1 schema intentionally cannot certify human approval; a future reviewed
    adjudication importer must be explicitly designed before accepting decisions.
    """
    indexed = keyed(rows, "admissibility manifest")
    if len(indexed) != 400 or set(indexed) != set(context["frame"]):
        raise ValueError("manifest must contain exactly the 400 frame IDs")
    expected = keyed(build_rows(context), "derived expected manifest")
    def check_shape(value, prototype, field):
        if type(value) is not type(prototype):
            raise ValueError("wrong field type: " + field)
        if isinstance(prototype, dict):
            if value.keys() != prototype.keys():
                raise ValueError("required/unexpected fields: " + field)
            for key in prototype:
                check_shape(value[key], prototype[key], field + "." + key)
        elif isinstance(prototype, list):
            if len(value) != len(prototype):
                raise ValueError("wrong record/reference count: " + field)
            for index, (actual, expected_value) in enumerate(zip(value, prototype)):
                check_shape(actual, expected_value, field + "[" + str(index) + "]")
    for qid, row in indexed.items():
        check_shape(row, expected[qid], qid)
        if row["provenance"]["tier"] not in TIERS:
            raise ValueError("invalid provenance vocabulary")
        for key in ("semantic_support", "temporal_validity", "independent_review", "adjudication"):
            if row[key]["status"] not in STATES:
                raise ValueError("invalid review/adjudication vocabulary")
        if row["final_disposition"] == "ACCEPTED" or row["provenance"]["tier"] == "AUTHENTICATED_ORIGINAL":
            raise ValueError("B1 cannot grant acceptance or original authentication")
        if row["independent_review"]["reviewer_ids"] or row["adjudication"]["reviewer_id"]:
            raise ValueError("B1 cannot invent/authorize reviewers")
        if canonical(row) != canonical(expected[qid]):
            raise ValueError("manifest differs from pinned source facts or unreviewed foundation: " + qid)
    outside = [r for r in rows if r["evidence"]["availability"] == "OUT_OF_SCOPE"]
    if len(outside) != 10 or any(r["stratum"] != "past" or r["final_disposition"] != "INELIGIBLE"
                                or datetime.fromtimestamp(r["evidence"]["dataset_evidence_ts"], timezone.utc).year != 2007
                                for r in outside):
        raise ValueError("expected ten explicit past/2007 out-of-scope cases")
    return {"schema_version": VERSION, "valid": True, "row_count": 400,
            "scientific_acceptance_granted": False}


def summarize(rows):
    def counts(values):
        return dict(sorted(Counter(values).items()))
    return {"schema_version": VERSION, "row_count": len(rows),
            "by_stratum": counts(r["stratum"] for r in rows),
            "by_provenance_tier": counts(r["provenance"]["tier"] for r in rows),
            "by_evidence_availability": counts(r["evidence"]["availability"] for r in rows),
            "by_review_status": counts(r["independent_review"]["status"] for r in rows),
            "by_provisional_eligibility": counts(r["provisional_eligibility"] for r in rows),
            "by_final_disposition": counts(r["final_disposition"] for r in rows),
            "by_queue_status_claim": counts(r["queue_status_claim"] for r in rows),
            "original_question_key_bindings_verified": sum(r["keys"]["original_status"] == "VERIFIED" for r in rows),
            "independently_verified_admissible": 0, "scientifically_accepted": 0,
            "with_prior_review_artifacts": sum(r["development_exposure"]["prior_review_artifact_present"] for r in rows),
            "with_imported_human_verified_claim": sum(any(a["claims"].get("human_verified", "").lower() == "true"
                                                       for a in r["imported_annotations"]) for r in rows),
            "missing_data_counts": counts(field for r in rows for field in r["missing_evidence"]),
            "interpretation": "PROVISIONAL_ENGINEERING_ACCOUNTING_NOT_ADJUDICATION_OR_BENCHMARK_FREEZE"}


def inventory(context):
    return {"schema_version": VERSION, "inputs": context["inputs"],
            "input_equivalence": context["input_equivalence"],
            "reconstruction_artifacts": context["source_manifest"]["artifacts"],
            "prior_annotation_inventory": context["annotation_inventory"]}


def output_records(context, rows):
    return {"manifest.jsonl": rows,
            "missing_data.jsonl": [{"qa_id": r["qa_id"], "missing_evidence": r["missing_evidence"]} for r in rows],
            "ineligible_unresolved.jsonl": [{"qa_id": r["qa_id"], "disposition": r["final_disposition"],
                                             "reasons": r["exclusion_or_unresolved_reasons"]} for r in rows]}


def run(repo, recovered, output, *, validate_only=False):
    repo, recovered, output = Path(repo).resolve(), Path(recovered).resolve(), Path(output).resolve()
    # New outputs cannot overlap any immutable input/artifact tree.
    protected = [repo / name for name in ("data", "logs", "results", "src", "tests", "docs")]
    protected.append(recovered)
    if output == repo or any(output == p or p in output.parents or output in p.parents for p in protected):
        raise ValueError("output must not overlap protected inputs")
    context = load_context(repo, recovered)
    if validate_only:
        rows = jsonl(output / "manifest.jsonl")
        result = validate_manifest(rows, context)
        expected_rows = build_rows(context)
        for name, records in output_records(context, expected_rows).items():
            if jsonl(output / name) != records:
                raise ValueError("derived output/order mismatch: " + name)
        for name, record in {"source_inventory.json": inventory(context),
                             "summary.json": summarize(expected_rows), "validation.json": result}.items():
            if strict_json((output / name).read_bytes()) != record:
                raise ValueError("derived audit report differs: " + name)
        hashes = strict_json((output / "sha256.json").read_bytes())
        if set(hashes) != {"manifest.jsonl", "summary.json", "validation.json", "source_inventory.json",
                           "missing_data.jsonl", "ineligible_unresolved.jsonl"}:
            raise ValueError("missing/unexpected output checksums")
        for name, expected in hashes.items():
            if Path(name).name != name or sha(output / name) != expected:
                raise ValueError("output hash mismatch")
        return result
    if output.exists():
        raise FileExistsError("output exists; never overwrite an audit")
    rows = build_rows(context)
    result = validate_manifest(rows, context)
    # Pin all consumed bytes again after full interpretation, before publication.
    roots = {"repository": repo, "recovered": recovered}
    for source in context["inputs"].values():
        if sha(roots[source["root"]] / source["path"]) != source["sha256"]:
            raise ValueError("input changed during generation")
    output.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        (output / name).write_bytes((canonical(value) + "\n").encode("ascii"))
    def write_rows(name, records):
        (output / name).write_bytes("".join(canonical(r) + "\n" for r in records).encode("ascii"))
    for name, records in output_records(context, rows).items():
        write_rows(name, records)
    write("summary.json", summarize(rows))
    write("validation.json", result)
    write("source_inventory.json", inventory(context))
    write("sha256.json", {p.name: sha(p) for p in sorted(output.iterdir())})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--recovered-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    print(canonical(run(args.repo, args.recovered_root, args.out_dir, validate_only=args.validate_only)))


if __name__ == "__main__":
    main()
