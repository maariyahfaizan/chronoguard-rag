"""G2-I6: registered fictional legacy-FreshQA records to blocked runner drafts.

No runner/backend imports. Hashes establish byte identity, never authenticity.
Real records are inventory-only; this version has no real conversion interface.
"""
from __future__ import annotations

import ast
import copy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "chronoguard.freshqa-candidate-normalization/v1"
SCOPE = "SYNTHETIC_ONLY"
BLOCKED = "NOT_AUTHORIZED_FOR_EXECUTION"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def fixtures():
    """Independent registry, regenerated per call; no caller-supplied approvals."""
    records = []
    for name in ("complete", "missing-date", "empty-metadata", "repeated-text"):
        qid = "synthetic-freshqa-g2-i6-" + name
        texts = ["Fictional Luma has two moons.\n", "Fictional Nera has three moons. Î©"]
        if name == "repeated-text":
            texts[1] = texts[0]
        metadata = [dict(index=i, doc_id=qid + "-doc-" + str(i), url="https://example.invalid/" + str(i),
                         final_url=None, title="Fictional evidence", source_date="2020-01-02T03:04:05+00:00",
                         is_source_document=(i == 0)) for i in range(2)]
        if name == "missing-date":
            metadata[0]["source_date"] = None
            del metadata[1]["source_date"]
        if name == "empty-metadata":
            metadata = [{}, {}]
        records.append(dict(query_id=qid, dataset_scope=SCOPE, query="How many moons has fictional Luma?",
                            gold_answer="two", gold_aliases=["2", "two moons"], candidates=texts,
                            candidate_metadata=metadata, effective_year="2020"))
    return records


def _date(value):
    if value is None:
        return
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("unsupported date; no inference or coercion")
    try:
        if len(value) == 10:
            date.fromisoformat(value)
        else:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("timezone missing")
    except ValueError as exc:
        raise ValueError("unsupported recorded source date") from exc


def normalize(records, expected_source_hashes):
    """Lossless, independently registered fixtures only. All-or-nothing validation."""
    if type(records) is not list or not records or type(expected_source_hashes) is not dict:
        raise ValueError("nonempty record list and source hash map required")
    registry = {r["query_id"]: digest(r) for r in fixtures()}
    ids = []
    result = []
    for r in records:
        if type(r) is not dict:
            raise ValueError("record must be dictionary")
        qid = r.get("query_id")
        if type(qid) is not str or qid not in registry or r.get("dataset_scope") != SCOPE:
            raise ValueError("real or unregistered record rejected")
        if qid in ids:
            raise ValueError("duplicate QA identity")
        ids.append(qid)
        for field in ("query", "gold_answer"):
            if type(r.get(field)) is not str or not r[field]:
                raise ValueError("missing question/answer identity")
        if type(r.get("gold_aliases")) is not list or any(type(a) is not str for a in r["gold_aliases"]):
            raise ValueError("aliases must be unchanged string list")
        texts, metadata = r.get("candidates"), r.get("candidate_metadata")
        if type(texts) is not list or not texts or type(metadata) is not list or len(texts) != len(metadata):
            raise ValueError("candidate/metadata length mismatch or missing candidates")
        candidates, document_ids = [], set()
        for i, (text, m) in enumerate(zip(texts, metadata)):
            if type(text) is not str or type(m) is not dict:
                raise ValueError("unsupported candidate or metadata type")
            if "index" in m and (type(m["index"]) is not int or m["index"] != i):
                raise ValueError("metadata index/order conflict")
            doc = m.get("doc_id")
            if doc is not None:
                if type(doc) is not str or not doc or doc in document_ids:
                    raise ValueError("invalid or duplicate document identity")
                document_ids.add(doc)
            flag = m.get("is_source_document")
            if flag is not None and type(flag) is not bool:
                raise ValueError("source flag must be boolean or unknown")
            source_date = m.get("source_date")
            _date(source_date)
            if "timestamp" in m and m["timestamp"] != source_date:
                raise ValueError("conflicting date metadata; inference forbidden")
            candidates.append(dict(doc_id=doc, text=text, timestamp=source_date, is_source_document=flag,
                source_metadata=copy.deepcopy(m), candidate_index=i,
                text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), metadata_sha256=digest(m),
                document_identity_status="RECORDED_UNAUTHENTICATED" if doc is not None else "MISSING",
                source_flag_status="RECORDED_UNVERIFIED" if flag is not None else "UNKNOWN",
                date_status="RECORDED_UNAUTHENTICATED" if source_date is not None else "MISSING",
                alignment_status="INDEX_CHECKED" if "index" in m else "POSITIONAL_ONLY_UNVERIFIED"))
        source_hash = digest(r)
        if expected_source_hashes.get(qid) != source_hash:
            raise ValueError("source hash mismatch")
        if registry[qid] != source_hash:
            raise ValueError("rehashed unregistered mutation; no authenticity from caller hash")
        # Compatibility placeholders are explicitly unknown, never gold approval.
        out = copy.deepcopy(r)
        out.update(schema_version=VERSION, candidates=candidates, original_record=copy.deepcopy(r),
                   source_record_sha256=source_hash, source_hash_basis="canonical-json-utf8/v1",
                   question_ts=r.get("question_ts"), question_time_status="MISSING",
                   gold_chunk_ids=[], gold_validated=None, gold_validation_status="NOT_REVIEWED",
                   gold_chunk_ids_status="UNKNOWN_EMPTY_COMPATIBILITY_PLACEHOLDER",
                   provenance_status="UNKNOWN_NOT_AUTHENTICATED", benchmark_eligibility="NOT_REVIEWED",
                   execution_status=BLOCKED, dataset_scope=SCOPE)
        result.append(out)
    if set(expected_source_hashes) != set(ids):
        raise ValueError("source registry keys differ from batch identities")
    return result


def validate_normalized(outputs, originals, hashes):
    if canonical(outputs) != canonical(normalize(originals, hashes)):
        raise ValueError("normalized output drift")
    return {"records": len(outputs), "execution": BLOCKED, "structural_only": True}


def legacy_structure_check(record):
    """Execute only pinned AST-extracted pure legacy field validator, no runner import.

    It validates field presence, not source authenticity, temporal fitness or execution.
    """
    source = ROOT / "src/attacks/attack_pool.py"
    if sha(source) != LEGACY_VALIDATOR_SHA:
        raise ValueError("legacy validator source changed")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
                {"REQUIRED_RECORD_FIELDS", "REQUIRED_CANDIDATE_FIELDS"} for t in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_validate_record":
            node.args.args[0].annotation = None
            node.returns = None
            nodes.append(node)
    if len(nodes) != 3:
        raise ValueError("unsupported validator structure")
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    namespace["_validate_record"](record)
    # Exact field accesses used by FreshQA runner, without importing its entrypoint.
    return {"texts": [c["text"] for c in record["candidates"]],
            "doc_ids": [c["doc_id"] for c in record["candidates"]],
            "timestamps": [c["timestamp"] for c in record["candidates"]],
            "source_flags": [c["is_source_document"] for c in record["candidates"]]}


def authorize_execution(record):
    raise ValueError("no real or synthetic execution interface exists in G2-I6")


def write_synthetic(path, records, originals, hashes):
    target = Path(path).resolve()
    allowed = (ROOT / "audits/g2_i6_v1/synthetic_normalized_pool.jsonl").resolve()
    if target != allowed:
        raise ValueError("output path escape or production path rejected")
    validate_normalized(records, originals, hashes)
    payload = "".join(canonical(r) + "\n" for r in records).encode("utf-8")
    if target.exists():
        raise ValueError("no overwrite")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


LEGACY_VALIDATOR_SHA = "6f1c581804af69e65ca5b9210060e926f0d9c597860fc270910e312eaf54ee74"
