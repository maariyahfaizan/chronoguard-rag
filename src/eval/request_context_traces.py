"""Pre-tokenization traces for pinned fictional requests, never dispatches."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT
VERSION = "chronoguard.request-context-trace/v1"
PIN = "f6fce1dbf7d1cf2962a9510e564d43a2c5b03d041bc4cae21835288e24a9fb43"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registered_pairs():
    root = SOURCE_ROOT / "audits/g2_i2_v1"
    if sha(root / "sha256.json") != PIN:
        raise ValueError("G2-I2 registration manifest mismatch")
    for name, expected in json.loads((root / "sha256.json").read_text()).items():
        if sha(root / name) != expected:
            raise ValueError("G2-I2 artifact changed")
    for name, expected in json.loads((root / "source_inventory.json").read_text()).items():
        if sha(SOURCE_ROOT / name) != expected:
            raise ValueError("G2-I2 source changed")
    return [json.loads(line) for line in (root / "request_pairs.jsonl").read_text(encoding="utf-8").splitlines()]


def _helpers():
    path = SOURCE_ROOT / "src/generation/generate.py"
    inventory = json.loads((SOURCE_ROOT / "audits/g2_i2_v1/source_inventory.json").read_text())
    if sha(path) != inventory["src/generation/generate.py"]:
        raise ValueError("prompt helper revision mismatch")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"truncate_passage", "build_prompt"}]
    if len(nodes) != 2:
        raise ValueError("unsupported helper layout")
    for node in nodes:
        if any(isinstance(n, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal)) for n in ast.walk(node)):
            raise ValueError("unsafe helper definition")
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            if not ((isinstance(call.func, ast.Name) and call.func.id == "truncate_passage") or
                    (isinstance(call.func, ast.Attribute) and call.func.attr == "join")):
                raise ValueError("unexpected helper call")
    scope = {"DEFAULT_MAX_PASSAGE_CHARS":1500}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),scope)
    return scope["truncate_passage"], scope["build_prompt"]


def _slots(slots, count):
    if (type(slots) is not list or not slots or any(type(s) is not int or not 0 <= s < count for s in slots)
            or slots != sorted(set(slots))):
        raise ValueError("selection must be a nonempty ordered subset of candidate slots")


def build_traces(pairs, *, selected_slots=None, audit_caps=None):
    trusted = registered_pairs()
    if canonical(pairs) != canonical(trusted):
        raise ValueError("unregistered or altered synthetic request/pair identity")
    selected_slots = [0,1] if selected_slots is None else selected_slots
    caps = {} if audit_caps is None else audit_caps
    if type(caps) is not dict or set(caps)-{"passage_chars","context_chars","prompt_chars"} or any(
            type(v) is not int or v <= 0 for v in caps.values()):
        raise ValueError("invalid synthetic audit budget")
    truncate, prompt_helper = _helpers()
    traces = []
    for pair in pairs:
        pair_traces = []
        normalized = []
        for request in pair["requests"]:
            row = request["pool_record"]
            _slots(selected_slots,len(row["candidates"]))
            configured = request["configuration"]["generation"]["max_passage_chars"]
            limit = caps.get("passage_chars",configured)
            texts = [row["candidates"][s]["text"] for s in selected_slots]
            retained = [truncate(t,limit) for t in texts]
            production_context = "\n\n".join(retained)
            production_prompt = prompt_helper(row["query"],texts,limit)
            context = production_context[:caps.get("context_chars",len(production_context))]
            start = production_prompt.index("Context:\n") + len("Context:\n")
            prompt = production_prompt[:start] + context + production_prompt[start+len(production_context):]
            prompt = prompt[:caps.get("prompt_chars",len(prompt))]
            body = request["intervention"]["body"]
            header = request["intervention"]["header"]
            cursor, spans, gold_complete, false_complete = 0, [], [], False
            for slot,text,kept in zip(selected_slots,texts,retained):
                candidate = row["candidates"][slot]
                target = slot in request["target_slots"]
                expected_body = body if target else text
                body_start = cursor + (len(header) if target else 0)
                body_end = body_start + len(expected_body)
                survived = (len(text) <= limit and body_end <= len(context)
                    and context[body_start:body_end] == expected_body
                    and start+body_end <= len(prompt) and prompt[start+body_start:start+body_end] == expected_body)
                if target:
                    false_complete = false_complete or survived
                if candidate["doc_id"] in row["gold_chunk_ids"]:
                    gold_complete.append(survived)
                spans.append({"slot":slot,"doc_id":candidate["doc_id"],"original_text":text,"retained_text":kept,
                    "original_characters":len(text),"retained_characters":len(kept),
                    "passage_truncation_boundary":min(len(text),limit),"body_context_span":[body_start,body_end],
                    "body_prompt_span":[start+body_start,start+body_end],"complete_body_in_assembled_prompt":survived})
                cursor += len(kept)+2
            violations = []
            if limit != configured:
                violations.append("PASSAGE_BUDGET_OVERRIDE_SYNTHETIC_FAULT")
            if context != production_context:
                violations.append("CONTEXT_BUDGET_VIOLATION_SYNTHETIC_FAULT")
            if len(prompt) < start+len(context)+len(production_prompt)-(start+len(production_context)):
                violations.append("PROMPT_BUDGET_VIOLATION_SYNTHETIC_FAULT")
            if not false_complete:
                violations.append("FALSE_CLAIM_NOT_COMPLETE_IN_ASSEMBLED_PROMPT")
            selected_gold = [row["candidates"][s]["doc_id"] for s in selected_slots
                             if row["candidates"][s]["doc_id"] in row["gold_chunk_ids"]]
            gold_visible = set(selected_gold)==set(row["gold_chunk_ids"]) and bool(gold_complete) and all(gold_complete)
            if not gold_visible:
                violations.append("GOLD_EVIDENCE_NOT_COMPLETE_IN_ASSEMBLED_PROMPT")
            normalized_texts=[]
            for slot,text in zip(selected_slots,texts):
                normalized_texts.append(text[len(header):] if slot in request["target_slots"] else text)
            normalized.append(normalized_texts)
            trace = {"schema_version":VERSION,"scope":"SYNTHETIC_ONLY","execution_status":"NOT_AUTHORIZED_FOR_EXECUTION",
                "trace_id":"g2-i3:"+digest({"request":request["runner_request_sha256"],"slots":selected_slots,"caps":caps,"version":VERSION}),
                "pair_id":request["pair_id"],"condition_id":request["condition_id"],"condition":request["condition"],
                "source_qa_id":request["source_qa_id"],"original_request_sha256":request["runner_request_sha256"],
                "candidate_order":request["candidate_order"],"selected_slots":selected_slots.copy(),
                "selected_document_ids":[row["candidates"][s]["doc_id"] for s in selected_slots],
                "selection_basis":"EXPLICIT_SYNTHETIC_PLAN_NOT_RETRIEVAL", "retrieved_passages":"NOT_EXECUTED",
                "selected_passage_texts":texts,"header":header,"false_claim_body":body,"body_sha256":request["body_sha256"],
                "selected_evidence_bodies":[body if s in request["target_slots"] else row["candidates"][s]["text"]
                                            for s in selected_slots],
                "pair_invariant_binding":{
                    "header_only_request_proof":copy.deepcopy(pair["header_only_proof"]),
                    "candidate_identity_date_metadata_sha256":digest([{k:c[k] for k in
                        ("doc_id","source_id","variant_id","timestamp","source_metadata")} for c in row["candidates"]]),
                    "answers_aliases_sha256":digest({k:row[k] for k in
                        ("gold_answer","gold_aliases","original_answers","original_aliases")}),
                    "placement_budget_sha256":digest({"slots":request["target_slots"],"poison_budget":request["poison_budget"],
                        "passage_char_limit":configured})},
                "configuration_sha256":request["configuration_sha256"],
                "context":context,"context_sha256":text_sha(context),"prompt":prompt,"prompt_sha256":text_sha(prompt),
                "context_characters":len(context),"context_utf8_bytes":len(context.encode()),
                "prompt_characters":len(prompt),"prompt_utf8_bytes":len(prompt.encode()),
                "configured_passage_char_limit":configured,"allocated_passage_characters":configured*len(selected_slots),
                "global_context_or_prompt_char_limit":"NOT_CONFIGURED_IN_PRODUCTION", "synthetic_fault_caps":copy.deepcopy(caps),
                "passages":spans,"false_claim_complete":false_complete,"gold_evidence_complete":gold_visible,
                "generator_call_inputs":{"query":row["query"],"candidate_passages":texts},
                "user_message":{"role":"user","content":prompt},
                "generator_token_count":"UNKNOWN","actual_tokenizer_visibility":"UNKNOWN_UNAVAILABLE_BACKEND",
                "model_receipt":"NOT_EXECUTED", "prompt_helper_source_sha256":sha(SOURCE_ROOT/"src/generation/generate.py"),
                "violations":violations}
            pair_traces.append(trace)
        if normalized[0] != normalized[1]:
            raise ValueError("undeclared matched-condition payload difference")
        asymmetry = pair_traces[0]["false_claim_complete"] != pair_traces[1]["false_claim_complete"]
        for trace in pair_traces:
            trace["matched_pair_invariants"]="PASS_REGISTERED_HEADER_ONLY_REQUESTS"
            trace["asymmetric_false_claim_truncation"]=asymmetry
            if asymmetry:
                trace["violations"].append("ASYMMETRIC_FALSE_CLAIM_TRUNCATION")
        traces.extend(pair_traces)
    return traces


def validate_traces(traces,pairs,*,selected_slots=None,audit_caps=None):
    if type(traces) is not list or any(type(t) is not dict or type(t.get("trace_id")) is not str for t in traces):
        raise ValueError("malformed trace identities")
    if len({t["trace_id"] for t in traces}) != len(traces):
        raise ValueError("duplicate trace identity")
    if canonical(traces) != canonical(build_traces(pairs,selected_slots=selected_slots,audit_caps=audit_caps)):
        raise ValueError("trace differs from registered request/context replay")
    return True


def write_traces(traces,pairs,*,output):
    repo=ROOT.resolve(); expected=repo/"audits/g2_i3_v1"; allowed=expected.resolve(); target=Path(output).resolve()
    if allowed != expected or not target.is_relative_to(allowed) or target==allowed or target.suffix!=".jsonl":
        raise ValueError("synthetic audit path required; production/prior paths forbidden")
    validate_traces(traces,pairs)
    if any(t["violations"] for t in traces):
        raise ValueError("faulted or incomplete context cannot be published as normal trace")
    data="".join(canonical(t)+"\n" for t in traces).encode()
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as f:f.write(data)
    return {"traces":len(traces),"sha256":hashlib.sha256(data).hexdigest(),"execution_status":"NOT_AUTHORIZED_FOR_EXECUTION"}


if __name__=="__main__":
    import argparse
    from src.eval.no_execution_boundary import install
    guard=install()
    parser=argparse.ArgumentParser(description="Static fictional context assembly; execution denied")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    pairs=registered_pairs(); traces=build_traces(pairs)
    result=write_traces(traces,pairs,output=args.output)
    print(canonical({**result,"boundary":guard.report()}))
