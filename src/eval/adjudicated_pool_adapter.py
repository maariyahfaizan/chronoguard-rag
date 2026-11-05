"""G2-I1 runner-compatible projection. Real conversion is deliberately disabled.

Synthetic grants are checked against independently reconstructed fictional
fixtures, not a caller-supplied approval hash. This is not an approval service.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from src.attacks.attack_pool import _validate_record
from src.attacks.attack_specs import ATTACK_SPECS
from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES
from src.attacks.matched_controls import canonical, digest
from src.eval.claim_keys import ClaimContext, ClaimKey, identity_hash
from src.eval.evidence_identity import EvidenceRecord, validate_timestamp, variant_id

ROOT = Path(__file__).resolve().parents[2]
INPUT_VERSION = "chronoguard.adjudicated-to-runner/input-v1"
OUTPUT_VERSION = "chronoguard.adjudicated-to-runner/pool-v1"
IMPLEMENTATION = "g2_i1_synthetic_adapter_1"
G1_ROOT = ROOT / "docs/consolidation/g1_v1"
PREFIX = "synthetic-g2-i1-"
GATES = ("provenance", "answer_key", "claim_key", "independent_adjudication",
         "exposure_policy", "family_eligibility", "protocol_benchmark_freeze")
SUPPORTED_FAMILIES = ("fabricated_fresh", "future_date", "correct_content_wrong_date")


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _contract_reference():
    manifest = G1_ROOT / "checksums.json"
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != "6a4876be1f48671ea87e4f6b4fd237c29da4333de017445b258ef25c2d5e2f87":
        raise ValueError("missing or stale G1 contract manifest")
    hashes = json.loads(raw)
    contract_bytes = (G1_ROOT / "integration_contracts.json").read_bytes()
    expected = hashes["integration_contracts.json"]
    if hashlib.sha256(contract_bytes).hexdigest() != expected:
        raise ValueError("G1 integration contract changed")
    return {"contract_id": "A", "sha256": expected, "profile": INPUT_VERSION}


def _fixture(index):
    """Registered manual fictional authority; no real review decisions exist."""
    ex = SYNTHETIC_EXAMPLES[index]
    qid = PREFIX + str(index + 1).zfill(3)
    original = {"source_qa_id": qid, "dataset": "manual-fictional-fixture", "question": ex.query,
                "answers": [ex.original_answer], "aliases": [ex.original_answer],
                "question_ts": ex.timestamp, "metadata": {"origin": "manual_fiction"}}
    sources = {f"synthetic://{qid}/original": original}
    def reference(uri):
        return {"uri": uri, "sha256": digest(sources[uri]), "record_ref": "/",
                "hash_basis": "canonical_json_utf8"}
    evidence = []
    for role, body in (("gold", ex.correct_text), ("distractor", "A fictional exhibit opens at the observatory."),
                       ("false_payload", ex.incorrect_claim)):
        source_id = qid + ":" + role
        source = {"source_qa_id": qid, "doc_id": source_id, "source_id": source_id,
                  "text": body, "timestamp": ex.timestamp,
                  "metadata": {"origin": "manual_fiction", "role": role}}
        uri = f"synthetic://{qid}/{role}"
        sources[uri] = source
        item = {"source": reference(uri), "doc_id": source_id, "source_id": source_id,
                "text_sha256": text_sha(body), "role": role,
                "variant_id": variant_id(EvidenceRecord(source_id, body.encode(), ex.timestamp,
                                            tuple(sorted(source["metadata"].items()))))}
        if role == "false_payload":
            false_ref = item
        else:
            evidence.append(item)
    context = ClaimContext(qid, ex.query, ex.original_answer, tuple(original["aliases"]),
                           false_ref["source_id"], ex.incorrect_claim)
    key = ClaimKey(key_id=qid+":claim-key", question_id=qid, question_hash=identity_hash(ex.query),
        primary_gold_hash=identity_hash(ex.original_answer), aliases_hash=identity_hash(context.aliases),
        source_id=context.source_id, source_hash=identity_hash(context.source_text),
        subject="fictional subject", relation="fictional answer relation", false_state=ex.incorrect_answer,
        units=None, polarity="positive", temporal_qualifiers=("fictional question time",),
        false_expressions=(ex.incorrect_answer, ex.incorrect_claim),
        gold_expressions=(ex.original_answer, ex.correct_text), provenance="SYNTHETIC_ONLY_MANUAL_FIXTURE",
        approval_status="approved", reviewer="synthetic-reviewer-a;synthetic-reviewer-b")
    record = {"schema_version": INPUT_VERSION, "scope": "SYNTHETIC_ONLY", "qa_id": qid,
        "original_source": reference(f"synthetic://{qid}/original"),
        "question_time_answer": {"status": "MOCK_APPROVED", "question_sha256": text_sha(ex.query),
                                 "primary": ex.original_answer, "aliases": original["aliases"].copy()},
        "evidence": evidence, "candidate_order": [e["doc_id"] for e in evidence],
        "gold_chunk_ids": [evidence[0]["doc_id"]],
        "claim": {"context": _plain(asdict(context)), "key": _plain(asdict(key)),
                  "key_digest": key.digest, "source": false_ref},
        "provenance": {"tier": "SYNTHETIC_ORIGIN_VERIFIED", "authority": "synthetic-authority:g2-i1"},
        "eligibility": {"status": "ELIGIBLE", "source_scope": "IN_SCOPE",
                        "families": {f: "ELIGIBLE" for f in SUPPORTED_FAMILIES}},
        "exposure": {"status": "ALLOW_SYNTHETIC_ONLY", "policy_id": "synthetic-policy:g2-i1"},
        "adjudication": {"status": "MOCK_APPROVED", "reviewers": ["synthetic-reviewer-a", "synthetic-reviewer-b"],
                         "adjudicator": "synthetic-adjudicator-c", "independence": "MOCK_VERIFIED"},
        "protocol": {"id": "synthetic-protocol:g2-i1", "sha256": digest({"protocol": "fictional only"}),
                     "benchmark_id": "synthetic-benchmark:g2-i1", "benchmark_sha256": digest({"benchmark": "fictional only"}),
                     "freeze_status": "MOCK_FROZEN", "execution_authorization": "NOT_GRANTED"}}
    core = digest(record)
    record["approvals"] = {gate: {"token": f"synthetic-approval:g2-i1:{gate}", "record_sha256": core,
                                  "scope": "SYNTHETIC_ONLY"} for gate in GATES}
    return record, sources


def synthetic_fixture_bundle():
    records, sources = [], {}
    for i in range(len(SYNTHETIC_EXAMPLES)):
        record, source = _fixture(i)
        records.append(record)
        sources.update(source)
    return copy.deepcopy(records), copy.deepcopy(sources)


def _source(ref, sources):
    if type(ref) is not dict or set(ref) != {"uri", "sha256", "record_ref", "hash_basis"}:
        raise ValueError("invalid source reference")
    if (not ref["uri"].startswith("synthetic://") or ref["uri"] not in sources
            or ref["record_ref"] != "/" or ref["hash_basis"] != "canonical_json_utf8"):
        raise ValueError("missing or unsupported source authority")
    source = sources[ref["uri"]]
    if digest(source) != ref["sha256"]:
        raise ValueError("source hash mismatch")
    return source


def _evidence(item, sources, qid):
    source = _source(item["source"], sources)
    if source["source_qa_id"] != qid or source["doc_id"] != item["doc_id"] or source["source_id"] != item["source_id"]:
        raise ValueError("evidence identity mismatch")
    validate_timestamp(source["timestamp"])
    if text_sha(source["text"]) != item["text_sha256"]:
        raise ValueError("body hash mismatch")
    variant = variant_id(EvidenceRecord(source["source_id"], source["text"].encode(), source["timestamp"],
                                      tuple(sorted(source["metadata"].items()))))
    if variant != item["variant_id"]:
        raise ValueError("variant identity mismatch")
    return source


def _convert(record, sources, family):
    if type(record) is not dict or record.get("schema_version") != INPUT_VERSION:
        raise ValueError("unsupported adjudicated record version")
    qid = record.get("qa_id")
    if (type(qid) is not str or not qid.startswith(PREFIX) or record.get("scope") != "SYNTHETIC_ONLY"):
        raise ValueError("synthetic/real namespace isolation")
    registry = {_fixture(i)[0]["qa_id"]: _fixture(i) for i in range(len(SYNTHETIC_EXAMPLES))}
    if qid not in registry:
        raise ValueError("unregistered synthetic authority")
    trusted, trusted_sources = registry[qid]
    eligibility = record["eligibility"]
    if (eligibility["status"] != "ELIGIBLE" or eligibility["source_scope"] != "IN_SCOPE"
            or eligibility["families"].get(family) != "ELIGIBLE"):
        raise ValueError("unknown/ineligible/out-of-scope family")
    adjudication = record["adjudication"]
    if (type(adjudication) is not dict or adjudication.get("status") != "MOCK_APPROVED"
            or adjudication.get("independence") != "MOCK_VERIFIED"
            or adjudication.get("reviewers") != ["synthetic-reviewer-a", "synthetic-reviewer-b"]
            or adjudication.get("adjudicator") != "synthetic-adjudicator-c"):
        raise ValueError("independent adjudication absent")
    if record["exposure"] != trusted["exposure"]:
        raise ValueError("unapproved exposure policy")
    if record["protocol"] != trusted["protocol"]:
        raise ValueError("protocol/benchmark freeze identity absent or stale")
    if record["provenance"] != trusted["provenance"]:
        raise ValueError("unsupported provenance promotion")
    original = _source(record["original_source"], sources)
    if original["source_qa_id"] != qid:
        raise ValueError("original question identity mismatch")
    validate_timestamp(original["question_ts"])
    answer = record["question_time_answer"]
    if (answer["status"] != "MOCK_APPROVED" or answer["question_sha256"] != text_sha(original["question"])
            or answer["aliases"] != original["aliases"] or not answer["primary"].strip()):
        raise ValueError("unapproved answer or rewritten aliases")
    items = record["evidence"]
    ids = [item["doc_id"] for item in items]
    if not ids or len(set(ids)) != len(ids) or ids != record["candidate_order"]:
        raise ValueError("duplicate or reordered candidate identities")
    if (not record["gold_chunk_ids"] or not set(record["gold_chunk_ids"]).issubset(ids)
            or len(set(record["gold_chunk_ids"])) != len(record["gold_chunk_ids"])):
        raise ValueError("unbound gold document identities")
    candidates = []
    for item in items:
        source = _evidence(item, sources, qid)
        candidates.append({"doc_id": item["doc_id"], "text": source["text"], "timestamp": source["timestamp"],
            "is_source_document": item["doc_id"] in record["gold_chunk_ids"],
            "source_id": source["source_id"], "variant_id": item["variant_id"],
            "text_sha256": item["text_sha256"], "source_reference": copy.deepcopy(item["source"]),
            "source_metadata": copy.deepcopy(source["metadata"])})
    claim = record["claim"]
    if family == "fabricated_fresh" and claim is None:
        raise ValueError("approved false-claim key required")
    if claim is not None:
        false_source = _evidence(claim["source"], sources, qid)
        context_data = copy.deepcopy(claim["context"])
        context_data["aliases"] = tuple(context_data["aliases"])
        context = ClaimContext(**context_data)
        key_data = copy.deepcopy(claim["key"])
        for field in ("temporal_qualifiers", "false_expressions", "gold_expressions"):
            key_data[field] = tuple(key_data[field])
        key = ClaimKey(**key_data)
        expected_context = ClaimContext(qid, original["question"], answer["primary"], tuple(original["aliases"]),
                                        false_source["source_id"], false_source["text"])
        if context != expected_context or key.digest != claim["key_digest"] or key.problems(context, {key.key_id: key.digest}):
            raise ValueError("unsupported, mismatched or unapproved synthetic claim key")
    # The authoritative fixture is separate from the caller record AND sources.
    # Rehashing changed input or inventing a matching manifest cannot authorize it.
    if canonical(record) != canonical(trusted):
        raise ValueError("record lacks exact registered synthetic approval binding")
    for uri, value in trusted_sources.items():
        if uri not in sources or canonical(sources[uri]) != canonical(value):
            raise ValueError("unregistered source bytes")
    out = {"schema_version": OUTPUT_VERSION, "source_qa_id": qid, "query": original["question"],
        "gold_answer": answer["primary"], "gold_aliases": original["aliases"].copy(),
        "aliases": original["aliases"].copy(), "question_ts": original["question_ts"],
        "candidates": candidates, "gold_chunk_ids": record["gold_chunk_ids"].copy(), "gold_validated": True,
        "original_record": copy.deepcopy(original), "original_source_reference": copy.deepcopy(record["original_source"]),
        "original_answers": original["answers"].copy(), "original_aliases": original["aliases"].copy(),
        "question_time_answer": copy.deepcopy(answer), "synthetic_claim_key": copy.deepcopy(claim),
        "adapter_metadata": {"implementation": IMPLEMENTATION, "scope": "SYNTHETIC_ONLY",
            "contract_reference": _contract_reference(),
            "attack_family": family, "input_sha256": digest(record), "execution_authorized": False,
            "scientific_approval": "NONE", "provenance": copy.deepcopy(record["provenance"]),
            "eligibility": copy.deepcopy(eligibility), "exposure": copy.deepcopy(record["exposure"]),
            "adjudication": copy.deepcopy(adjudication), "protocol": copy.deepcopy(record["protocol"]),
            "synthetic_gate_tokens": copy.deepcopy(record["approvals"])}}
    _validate_record(out)
    return out


def convert_records(records, *, sources, attack_family, mode):
    try:
        _contract_reference()
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("G1 contract unavailable or inconsistent") from exc
    if mode != "synthetic":
        raise ValueError("real conversion disabled: no authenticated external authority verifier installed")
    if attack_family not in ATTACK_SPECS or attack_family not in SUPPORTED_FAMILIES:
        raise ValueError("unsupported attack family in this adapter revision")
    canonical(records)
    canonical(sources)
    if type(records) is not list or not records or type(sources) is not dict:
        raise ValueError("nonempty record list and authoritative source mapping required")
    ids = [r.get("qa_id") for r in records if type(r) is dict]
    if len(ids) != len(records) or any(type(q) is not str for q in ids) or len(set(ids)) != len(ids):
        raise ValueError("duplicate or missing QA identities")
    # Entire batch validates before callers can receive or write any output.
    try:
        return [_convert(r, sources, attack_family) for r in records]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed or missing adjudication/source field") from exc


def validate_output(output, records, *, sources, attack_family, mode):
    expected = convert_records(records, sources=sources, attack_family=attack_family, mode=mode)
    if canonical(output) != canonical(expected):
        raise ValueError("output lost metadata/order or differs from authoritative conversion")
    return True


def write_synthetic_pool(records, *, sources, attack_family, output, mode):
    repo = ROOT.resolve()
    expected_root = repo / "audits/g2_i1_v1"
    allowed = expected_root.resolve()
    target = Path(output).resolve()
    if (allowed != expected_root or not allowed.is_relative_to(repo) or not target.is_relative_to(allowed)
            or target == allowed or target.suffix != ".jsonl"):
        raise ValueError("synthetic output restricted to audits/g2_i1_v1; production paths forbidden")
    result = convert_records(records, sources=sources, attack_family=attack_family, mode=mode)
    data = "".join(canonical(r) + "\n" for r in result).encode()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(data)
    return {"scope": "SYNTHETIC_ONLY", "rows": len(result), "sha256": hashlib.sha256(data).hexdigest(),
            "execution_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Registered fictional fixture conversion only; no attack execution")
    parser.add_argument("--synthetic-fixtures", action="store_true", required=True)
    parser.add_argument("--attack-family", default="fabricated_fresh", choices=SUPPORTED_FAMILIES)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records, sources = synthetic_fixture_bundle()
    print(json.dumps(write_synthetic_pool(records, sources=sources, attack_family=args.attack_family,
                                          output=args.output, mode="synthetic"), sort_keys=True))
