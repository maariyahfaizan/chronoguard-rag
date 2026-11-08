"""Local P0-S3 audit only: no retrieval, models, metrics or historical writes.

Ordered parent occurrences are bound to consecutive #chunkN blocks. Complete
coverage means a UNIQUE monotone, overlapping character alignment after removing
Unicode whitespace ONLY. No punctuation, numbers, symbols or compatibility forms
are normalized away. This is NOT reproduction of the original BGE tokenization.
An inconsistent/ambiguous group blocks labeling of the ENTIRE question; the
question remains in the 100-row report with null proposed labels, never filtered.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.eval.streamingqa_child_relevance import label_children_v1

OUT = ROOT / "audits/p0_s3_v1"
PARENT = "data/processed/streamingqa_control_pools.jsonl"
CHILD = "data/processed/streamingqa_control_pools_chunked.jsonl"
SAMPLE = "data/raw/streamingqa_control_sample.jsonl"
PINS = {
    PARENT: "fb4b3b8eecef861b3cd956922216c0892919c0bbaed102aeef06bd212ed61c2d",
    CHILD: "b4eede5c1ed4b06808fe44754cc04ee5036d3a572088de61dd6dff1f77174ddd",
    SAMPLE: "4da9ac126e118ae4bedfc8221ad0369c6cc517daad4e2e124384909ce51bcad4",
    "src/eval/streamingqa_child_relevance.py": "2ee4020e4feacc8692fa78bd2dfc1fe5e6eb66964758b8a6d82fc136a4eda418",
    "src/eval/chunk_streamingqa_pools.py": "ca06073cfd0857182485a455772465c2c642775c4b5c86a6f0a5d34f3cdf8e53",
    "src/eval/metrics.py": "1da371333a794636c2f8181189e9b5bbd7b7125e8dfa3ecb6844540bde22a4a7",
}
LOGS = {name: f"logs/streamingqa_{name}_run_chunked.jsonl"
        for name in ("baseline", "dense", "hybrid", "hybrid_reranker")}
UNDEFINED_KEYS = ("recall_at_5", "ndcg_at_5", "valid_evidence_recall_at_5")


class LineageError(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise LineageError(reason)


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode() + b"\n"


def complete_alignment(parent_text, child_texts):
    """Return unique intervals in NONWHITESPACE character coordinates, or fail."""
    parent = re.sub(r"\s+", "", parent_text)
    parts = [re.sub(r"\s+", "", t) for t in child_texts]
    if parts == [""] and not parent:
        return [[0, 0]]
    require(bool(parts) and all(parts), "EMPTY_CHILD_CONTENT")
    states = {}
    for number, part in enumerate(parts):
        placements = []
        at = parent.find(part)
        while at >= 0:
            placements.append((at, at + len(part)))
            at = parent.find(part, at + 1)
        next_states = {}
        for start, end in placements:
            predecessors = [(1, [])] if number == 0 and start == 0 else []
            if number:
                predecessors = [(count, path) for (prev_start, prev_end), (count, path)
                                in states.items() if prev_start < start <= prev_end < end]
            count = min(2, sum(n for n, _ in predecessors))
            if count:
                next_states[start, end] = (count, predecessors[0][1] + [[start, end]])
        require(len(next_states) <= 10000, "ALIGNMENT_RESOURCE_LIMIT")
        states = next_states
    finals = [(count, path) for (_, end), (count, path) in states.items() if end == len(parent)]
    total = sum(count for count, _ in finals)
    require(total != 0, "INCOMPLETE_OR_TRANSFORMED_PARENT_CONTENT")
    require(total == 1, "AMBIGUOUS_CONTENT_ALIGNMENT")
    return finals[0][1]


def verify_groups(parent, chunked):
    """Bind occurrence order; never build an ID->candidate map that drops copies."""
    for key in ("query", "gold_answer", "gold_aliases", "question_ts", "gold_validated"):
        require(parent[key] == chunked[key], "QUESTION_METADATA_DRIFT:" + key)
    require(parent.get("recent_or_past") == chunked.get("recent_or_past"), "STRATUM_DRIFT")
    require(chunked["n_candidates_pre_chunk"] == len(parent["candidates"]), "PARENT_COUNT_DRIFT")
    require(chunked["n_candidates_post_chunk"] == len(chunked["candidates"]), "CHILD_COUNT_DRIFT")
    require(chunked["gold_chunk_ids"] == [c["doc_id"] for c in chunked["candidates"]
                                          if c["is_source_document"]], "HISTORICAL_GOLD_ID_DRIFT")
    groups, proofs, failures = [], [], []
    position = 0
    for slot, passage in enumerate(parent["candidates"]):
        group = []
        while position < len(chunked["candidates"]):
            child = chunked["candidates"][position]
            if group and (child["parent_doc_id"] != passage["doc_id"]
                          or child["doc_id"] == passage["doc_id"] + "#chunk0"):
                break
            require(child["parent_doc_id"] == passage["doc_id"], "PARENT_ORDER_OR_ID_DRIFT")
            require(child["doc_id"] == f"{passage['doc_id']}#chunk{len(group)}", "CHILD_ORDER_OR_ID_DRIFT")
            require(child["timestamp"] == passage["timestamp"], "TIMESTAMP_DRIFT")
            require(type(child["is_source_document"]) is bool and
                    child["is_source_document"] == passage["is_source_document"], "HISTORICAL_FLAG_DRIFT")
            require(type(child["chunk_token_count"]) is int and 0 <= child["chunk_token_count"] <= 320,
                    "REPORTED_TOKEN_COUNT_OUT_OF_SCOPE")
            group.append(child)
            position += 1
        require(bool(group), "MISSING_PARENT_CHILD_BLOCK")
        proof = {"parent_candidate_slot": slot, "parent_doc_id": passage["doc_id"],
                 "child_slots": list(range(position - len(group), position)),
                 "child_ids": [c["doc_id"] for c in group],
                 "tokenization_replay": "UNVERIFIED_ORIGINAL_TOKENIZER_UNAVAILABLE"}
        try:
            proof["nonwhitespace_character_intervals"] = complete_alignment(
                passage["text"], [c["text"] for c in group])
            proof["status"] = "UNIQUE_COMPLETE_NONWHITESPACE_CHARACTER_COVERAGE"
        except LineageError as error:
            proof["status"] = "BLOCKED"
            proof["reason"] = str(error)
            failures.append({"parent_candidate_slot": slot, "reason": str(error)})
        groups.append(group)
        proofs.append(proof)
    require(position == len(chunked["candidates"]), "EXTRA_CHILD_BLOCK")
    return groups, proofs, failures


def reconcile_question(parent, chunked, sample, query_id, undefined):
    require(parent["query"] == sample["question"], "SAMPLE_QUESTION_IDENTITY_DRIFT")
    require(parent["gold_aliases"] == sample["answers"], "SAMPLE_ALIAS_DRIFT")
    require(parent["gold_answer"] == (sample["answers"][0] if sample["answers"] else None),
            "SAMPLE_GOLD_DRIFT")
    require(parent["question_ts"] == sample["question_ts"], "SAMPLE_QUESTION_TIME_DRIFT")
    identity = {"query_id": query_id, "source_qa_id": sample["qa_id"]}
    row = {**identity, "source_article_evidence_id": sample["evidence_id"],
           "question": parent["query"], "gold_answer": parent["gold_answer"],
           "gold_aliases": parent["gold_aliases"], "question_ts": parent["question_ts"],
           "historical_gold_validated": parent["gold_validated"],
           "historical_undefined_metrics": undefined,
           "historical_parent_record": parent, "historical_chunked_record": chunked,
           "semantic_support_status": "NOT_INDEPENDENTLY_REVIEWED",
           "temporal_validity_status": "NOT_REVIEWED",
           "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}
    try:
        groups, proofs, failures = verify_groups(parent, chunked)
        row["grouping_proofs"] = proofs
    except (LineageError, KeyError, TypeError) as error:
        failures = [{"parent_candidate_slot": None, "reason": str(error)}]
        groups = None
        row["grouping_proofs"] = []
    proposed = None
    if not failures:
        try:
            proposed = label_children_v1(parent, groups)
        except (ValueError, TypeError, KeyError) as error:
            failures = [{"parent_candidate_slot": None, "reason": "LABELER_REJECTED:" + str(error)}]
    row["validation_failures"] = failures
    row["status"] = "BLOCKED_NO_PROPOSED_LABELS" if failures else "PROVISIONAL_LEXICAL_RECONCILIATION"
    row["proposed_labeling"] = proposed
    comparisons = []
    for slot, old in enumerate(chunked["candidates"]):
        new = proposed["children"][slot] if proposed else None
        gold_match = (new["parent_role"] == "LEGACY_LEXICALLY_VALIDATED_PARENT" and
                      new["full_text_lexical_match"]) if new else None
        comparisons.append({"candidate_slot": slot, "doc_id": old["doc_id"],
            "parent_doc_id": old["parent_doc_id"], "timestamp": old["timestamp"],
            "historical_flag": old["is_source_document"],
            "new_child_lexical_match": new["full_text_lexical_match"] if new else None,
            "proposed_source_restricted_lexical_label": gold_match,
            "changed_from_historical_label": gold_match != old["is_source_document"] if new else None,
            "character_truncated": len(old["text"]) > 1500})
    row["comparisons"] = comparisons
    row["fallback_parent_ids"] = parent["gold_chunk_ids"] if not parent["gold_validated"] else []
    parent_dups = len(parent["candidates"]) - len({c["doc_id"] for c in parent["candidates"]})
    child_dups = len(chunked["candidates"]) - len({c["doc_id"] for c in chunked["candidates"]})
    row["duplicate_parent_occurrences"] = parent_dups
    row["duplicate_child_occurrences"] = child_dups
    reasons = []
    if failures:
        reasons.append("GROUPING_OR_CONTENT_VALIDATION_BLOCKED")
    if any(c["changed_from_historical_label"] for c in comparisons):
        reasons.append("CHANGED_PROVISIONAL_LABELS")
    if proposed and not proposed["lexical_gold_validated"]:
        reasons.append("NO_SOURCE_RESTRICTED_LEXICALLY_SUPPORTING_CHILD")
    if proposed and any(c["full_text_lexical_match"] for c in proposed["children"]):
        reasons.append("LEXICAL_MATCH_REQUIRES_SEMANTIC_REVIEW")
    if parent_dups or child_dups:
        reasons.append("DUPLICATE_CANONICAL_IDS_REQUIRE_OCCURRENCE_POLICY_REVIEW")
    if any(c["character_truncated"] for c in comparisons):
        reasons.append("STATIC_GENERATOR_CHARACTER_TRUNCATION_MODEL_RECEIPT_UNVERIFIED")
    queue = {**identity, "report_line": query_id + 1, "reasons": reasons,
             "priority": "P0_BLOCKED" if failures else "P1_EXCEPTION" if any(
                 r != "LEXICAL_MATCH_REQUIRES_SEMANTIC_REVIEW" for r in reasons) else "P2_LEXICAL_ONLY",
             "candidate_slots_for_changed_labels": [c["candidate_slot"] for c in comparisons
                                                     if c["changed_from_historical_label"]],
             "candidate_slots_over_character_budget": [c["candidate_slot"] for c in comparisons
                                                        if c["character_truncated"]],
             "review_status": "NOT_REVIEWED", "reviewer_identity": None, "review_decision": None}
    return row, queue


def read_rows(path):
    return [json.loads(line) for line in (ROOT / path).read_text(encoding="utf-8").splitlines() if line.strip()]


def build_artifacts():
    source_paths = list(PINS) + list(LOGS.values()) + [
        "scripts/reconcile_streamingqa_children.py", "tests/test_streamingqa_reconciliation.py"]
    hashes = {p: digest_bytes((ROOT / p).read_bytes()) for p in source_paths}
    require(all(hashes[p] == h for p, h in PINS.items()), "PINNED_INPUT_HASH_MISMATCH")
    head = subprocess.check_output(["git", "-c", "safe.directory=" + ROOT.as_posix(),
                                    "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    require(head == "d371020e6a9dd91edb0fd2114e9dbe34c5e25c76", "PUBLISHED_BASELINE_DRIFT")
    parents, children, sample = (read_rows(p) for p in (PARENT, CHILD, SAMPLE))
    require(len(parents) == len(children) == len(sample) == 100, "FIXED_100_FRAME_MISMATCH")
    require(len({r["qa_id"] for r in sample}) == 100, "DUPLICATE_QA_ID")
    undefined = [dict() for _ in range(100)]
    for name, path in LOGS.items():
        logs = read_rows(path)
        require(len(logs) == 100 and sorted(r["query_id"] for r in logs) == list(range(100)),
                "HISTORICAL_LOG_FRAME_DRIFT")
        for log in logs:
            qi = log["query_id"]
            require(log["query"] == parents[qi]["query"], "HISTORICAL_LOG_IDENTITY_DRIFT")
            undefined[qi][name] = [k for k in UNDEFINED_KEYS if log[k] is None]
    report, queue = [], []
    for i, (parent, child, question) in enumerate(zip(parents, children, sample)):
        row, review = reconcile_question(parent, child, question, i, undefined[i])
        report.append(row)
        if review["reasons"]:
            queue.append(review)
    blocked = [r["query_id"] for r in report if r["validation_failures"]]
    counts = {
        "question_records": 100, "provisionally_labeled_questions": 100 - len(blocked),
        "blocked_questions": len(blocked), "blocked_query_ids": blocked,
        "parent_occurrences": sum(len(r["candidates"]) for r in parents),
        "child_occurrences": sum(len(r["candidates"]) for r in children),
        "changed_label_occurrences_in_validated_questions": sum(c["changed_from_historical_label"] is True
            for r in report for c in r["comparisons"]),
        "questions_with_changed_labels": sum(any(c["changed_from_historical_label"] for c in r["comparisons"]) for r in report),
        "historically_unvalidated_query_ids": [i for i, r in enumerate(parents) if not r["gold_validated"]],
        "historically_undefined_query_ids": [i for i, d in enumerate(undefined) if any(d.values())],
        "questions_without_lexical_gold_among_labeled": [r["query_id"] for r in report
            if r["proposed_labeling"] and not r["proposed_labeling"]["lexical_gold_validated"]],
        "questions_with_duplicate_ids": sum(bool(r["duplicate_parent_occurrences"] or
                                                  r["duplicate_child_occurrences"]) for r in report),
        "truncated_child_occurrences": sum(c["character_truncated"] for r in report for c in r["comparisons"]),
        "human_review_queue_questions": len(queue),
        "review_reasons": dict(sorted(Counter(reason for q in queue for reason in q["reasons"]).items())),
        "review_priorities": dict(sorted(Counter(q["priority"] for q in queue).items())),
    }
    summary = {"schema_version": "p0_s3_reconciliation_v1", "status": "PARTIAL_BLOCKED_CASES" if blocked else
               "PROVISIONAL_ENGINEERING_RECONCILIATION", "counts": counts,
               "scientific_metrics_recomputed": False, "scientific_approval": "UNRECORDED",
               "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}
    failures = [{"query_id": r["query_id"], "source_qa_id": r["source_qa_id"],
                 "failures": r["validation_failures"]} for r in report if r["validation_failures"]]
    validation = {"frame_membership": "ALL_100_RETAINED", "per_question_fail_closed": True,
                  "coverage_rule": "UNIQUE_MONOTONE_NONWHITESPACE_CHARACTER_COVERAGE_V1",
                  "token_level_reproduction": "UNVERIFIED", "validation_failures": failures,
                  "missing_required_input_files": [], "missing_verification_evidence": [
                      "Original BGE tokenizer revision/runtime and token-level replay",
                      "Evidence explaining dropped or transformed nonwhitespace parent characters",
                      "Independent semantic/temporal support judgments", "Verified model input receipt"],
                  "no_scientific_metrics_computed": True}
    sources = {"published_head": head, "files": hashes,
               "stable_identity_basis": "qa_id from preserved control sample; full question/key/time cross-checks",
               "record_order": "preserved parent/child/sample row order, query_id 0..99",
               "publication_classification": "RESTRICTED_QUESTION_KEY_AND_REVIEW_MATERIAL_NOT_APPROVED_FOR_PUBLICATION"}
    readme = """# P0-S3 development reconciliation v1

RESTRICTED question/key/review material. Not approved for publication or execution.
All 100 questions are retained. Invalid or ambiguous parent-content coverage blocks
the entire question: proposed_labeling and proposed labels are null, never zero.
Others have provisional lexical annotations only, not independent semantic gold.

Grouping follows the preserved historical producer's ordered parent/child blocks,
including duplicate occurrences. Character coverage removes Unicode whitespace
only; no symbol deletion or mathematical normalization is permitted. This does
not reproduce BGE tokens or prove model receipt. Duplicate occurrences are retained;
the scientific unit/deduplication policy still requires review. All lexical matches
require semantic review, even if no heuristic finds a suspicious phrase.

reconciliation.jsonl contains original IDs, answers/aliases, parent/child snapshots,
coverage proofs, lexical annotations and nulls for blocked cases. review_queue.jsonl
has one concise entry per queued question, referencing its report line; reasons can
overlap. No human decision or reviewer identity is supplied. Historical undefined
metric flags are copied as missingness only; no metric is recomputed.

Reproduce with Python -B scripts/reconcile_streamingqa_children.py --check (read-only).
Initial creation omits --check and refuses an existing output directory. Exit 2 on
creation means reports were written but some questions are BLOCKED; exit 0 from
--check means exact artifact reproduction, NOT that blocked cases were resolved.
sha256.json covers all other report files; source_inventory.json binds source code
and inputs. No historical pool, log, summary, supervisor document or tag is changed.
"""
    files = {"reconciliation.jsonl": b"".join(encoded(r) for r in report),
             "review_queue.jsonl": b"".join(encoded(r) for r in queue),
             "summary.json": encoded(summary), "validation_report.json": encoded(validation),
             "source_inventory.json": encoded(sources), "README.md": readme.encode()}
    files["sha256.json"] = encoded({p: digest_bytes(data) for p, data in sorted(files.items())})
    return files, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files, summary = build_artifacts()
    if args.check:
        require(OUT.is_dir() and {p.name for p in OUT.iterdir()} == set(files), "OUTPUT_MEMBERSHIP_MISMATCH")
        for name, data in files.items():
            require((OUT / name).read_bytes() == data, "OUTPUT_BYTES_MISMATCH:" + name)
        print(json.dumps({"artifact_reproduction": "PASS", **summary}, sort_keys=True))
        return 0
    OUT.mkdir(exist_ok=False)
    for name, data in files.items():
        with (OUT / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps(summary, sort_keys=True))
    return 2 if summary["counts"]["blocked_questions"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
