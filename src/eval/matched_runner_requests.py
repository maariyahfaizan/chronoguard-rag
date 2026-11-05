"""Blocked synthetic matched requests. No retrieval/generator dispatch exists."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import inspect
import json
from pathlib import Path

from src.attacks.attack_pool import _validate_record
from src.attacks.matched_controls import canonical, digest, header_pair, validate_pair
from src.eval.adjudicated_pool_adapter import synthetic_fixture_bundle, convert_records, validate_output
from src.eval.config_loader import experiment_params, load_eval_config, model_revisions
from src.eval.run_metadata import attack_log_fields

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT
VERSION = "chronoguard.matched-runner-request/v1"
BLOCKED = "NOT_AUTHORIZED_FOR_EXECUTION"
INTERFACES = {
    "E1": ("run_baseline_streamingqa.py", "run_baseline_streamingqa", []),
    "E2": ("run_dense_streamingqa.py", "run_dense_streamingqa", ["retriever_model", "retriever_tokenizer", "retriever_device"]),
    "E3": ("run_hybrid_streamingqa.py", "run_hybrid_streamingqa", ["retriever_model", "retriever_tokenizer", "retriever_device"]),
    "E4": ("run_hybrid_reranker_streamingqa.py", "run_hybrid_cross_encoder_streamingqa",
           ["retriever_model", "retriever_tokenizer", "retriever_device", "reranker_model"]),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs():
    roots = {
        "audits/g2_i1_v1": "25ca6c37e918bf26374530332fcf9a8e666663ffec8d505f8a11750561984eb9",
        "audits/p1_a1_v1": "0e64d28f3a3197b2d46da090ca16094057d3b7b5c788e2417035a1e582a1fbb4",
        "audits/p1_a2_v1": "e7dac3f5731efa6f95a70e83cdb84ce183f39105f745b62586af4d6f3b8ef02e",
    }
    for relative, expected in roots.items():
        root = SOURCE_ROOT / relative
        if sha(root / "sha256.json") != expected:
            raise ValueError("stale prerequisite checksum manifest")
        for name, value in json.loads((root / "sha256.json").read_text()).items():
            if sha(root / name) != value:
                raise ValueError("prerequisite output changed")
        for name, value in json.loads((root / "source_inventory.json").read_text()).items():
            if sha(SOURCE_ROOT / name) != value:
                raise ValueError("prerequisite source changed")
    return roots


def runner_signature(system):
    file, function, _ = INTERFACES[system]
    tree = ast.parse((SOURCE_ROOT / "scripts" / file).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    if node.args.posonlyargs or node.args.vararg or node.args.kwarg or node.args.kwonlyargs:
        raise ValueError("unsupported runner signature revision")
    required = len(node.args.args) - len(node.args.defaults)
    return inspect.Signature([inspect.Parameter(a.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD,
        default=inspect.Parameter.empty if i < required else None) for i,a in enumerate(node.args.args)])


def configuration(system):
    if system not in INTERFACES:
        raise ValueError("unsupported runner")
    cfg = load_eval_config()
    params = experiment_params(system)
    revs = model_revisions()
    generation = copy.deepcopy(cfg["shared"]["generator"])
    if (generation["max_passage_chars"] != 1500 or generation["decoding"] != {"do_sample":False,"max_new_tokens":64}):
        raise ValueError("configured generation cannot be represented by unchanged driver defaults")
    generation["revision"] = revs[generation["model"]]
    generation["dtype_argument"] = "float16"
    generation["bnb_4bit_compute_dtype"] = "NOT_EXPLICITLY_SET"
    generation["template_source_sha256"] = sha(SOURCE_ROOT / "src/generation/generate.py")
    signature = runner_signature(system)
    runtime = ["model", "tokenizer"] + INTERFACES[system][2]
    knobs = [n for n in signature.parameters if n not in runtime + ["input_path","log_path","run_metadata"]]
    return {"retrieval": {"system":system, "definition":copy.deepcopy(cfg["experiments"][system]["retriever"]),
                         "parameters":{n:params[n] for n in knobs}, "pinned_model_revisions":revs},
            "generation":generation,
            "evaluation_rule":"legacy_streamingqa_evaluator@" + sha(SOURCE_ROOT / "src/eval/evaluator.py")}


def _call_template(system, pair_id, condition_id, config_hash):
    file, function, extra = INTERFACES[system]
    kwargs = {"input_path":"__SYNTHETIC_INPUT_NOT_MATERIALIZED__", "log_path":"__EXECUTION_FORBIDDEN__",
              "run_metadata":{"pair_id":pair_id, "condition_id":condition_id, "configuration_sha256":config_hash,
                              "scope":"SYNTHETIC_ONLY", "execution_status":BLOCKED},
              **configuration(system)["retrieval"]["parameters"]}
    return {"entrypoint":"scripts/" + file + ":" + function,
            "entrypoint_source_sha256":sha(SOURCE_ROOT / "scripts" / file),
            "runtime_bindings":["model","tokenizer"] + extra, "keyword_arguments":kwargs}


def validate_call_shape(call, system):
    expected_runtime = ["model", "tokenizer"] + INTERFACES[system][2]
    if call["runtime_bindings"] != expected_runtime:
        raise ValueError("missing or changed runtime binding contract")
    kwargs = call["keyword_arguments"]
    if (kwargs.get("input_path") != "__SYNTHETIC_INPUT_NOT_MATERIALIZED__"
            or kwargs.get("log_path") != "__EXECUTION_FORBIDDEN__"):
        raise ValueError("real execution paths forbidden")
    runner_signature(system).bind(**{**{n:object() for n in expected_runtime}, **kwargs})
    return True


def build_request_pairs(pool_records, *, mode, systems=None, slots=None, configurations=None):
    if mode != "synthetic":
        raise ValueError("synthetic-only request construction; execution is forbidden")
    verify_inputs()
    originals, sources = synthetic_fixture_bundle()
    validate_output(pool_records, originals, sources=sources, attack_family="fabricated_fresh", mode="synthetic")
    systems = list(INTERFACES) if systems is None else systems
    slots = [1] if slots is None else slots
    if (type(systems) is not list or not systems or any(s not in INTERFACES for s in systems)
            or len(set(systems)) != len(systems) or slots != [1] or type(slots) is not list):
        raise ValueError("registered systems and exact nongold slot [1] required")
    expected_configs = {s:configuration(s) for s in systems}
    if configurations is not None and canonical(configurations) != canonical(expected_configs):
        raise ValueError("missing or altered authoritative configuration")
    pairs = []
    for original in pool_records:
        body = original["synthetic_claim_key"]["context"]["source_text"]
        false_source = original["synthetic_claim_key"]["source"]
        base = copy.deepcopy(original)
        base.update({"attack_condition":"g2_i2_matched_header", "attack_protocol_version":VERSION, "poison_count":1,
            "attack_metadata":{"attack_type":"fabricated_fresh", "actual_poison_count":1, "target_indices":[1],
                               "target_doc_ids":[base["candidates"][1]["doc_id"]], "seed":None},
            "intervention_source":{"scope":"SYNTHETIC_ONLY", "payload_variant_id":false_source["variant_id"],
                                   "payload_source_reference":copy.deepcopy(false_source["source"]),
                                   "body_sha256":false_source["text_sha256"]}})
        for system in systems:
            settings = expected_configs[system]
            matched = header_pair(base, slots, settings, body)
            validate_pair(matched, base, slots, settings, body=body)
            config_hash = digest(settings)
            pair_id = "g2-i2:" + digest({"pool":digest(original),"system":system,"settings":settings,
                                         "slots":slots,"body":false_source["text_sha256"],"schema":VERSION})
            requests = []
            normalized = []
            for condition in ("neutral", "freshness"):
                row = matched["conditions"][condition]
                _validate_record(row)
                stripped = copy.deepcopy(row)
                header = matched["declarations"]["headers"][condition]
                stripped["candidates"][1]["text"] = row["candidates"][1]["text"][len(header):]
                normalized.append(stripped)
                condition_id = pair_id + "/" + condition
                request = {"schema_version":VERSION, "scope":"SYNTHETIC_ONLY", "execution_status":BLOCKED,
                    "pair_id":pair_id, "condition_id":condition_id, "condition":condition,
                    "source_qa_id":row["source_qa_id"], "original_pool_sha256":digest(original),
                    "configuration":copy.deepcopy(settings), "configuration_sha256":config_hash,
                    "pool_record":copy.deepcopy(row), "pool_record_sha256":digest(row),
                    "candidate_order":[c["doc_id"] for c in row["candidates"]], "target_slots":[1], "poison_budget":1,
                    "source_variant_ids":[c["variant_id"] for c in row["candidates"]],
                    "false_claim_variant_id":false_source["variant_id"], "body_sha256":false_source["text_sha256"],
                    "variant_identity_scope":{"source_variant_ids":"original slot lineage, not rendered text",
                        "false_claim_variant_id":"registered false-claim body without header",
                        "rendered_text_sha256":"exact rendered intervention including header"},
                    "intervention":{"header":header,"body":body,"rendered_text":header+body,
                                    "rendered_text_sha256":hashlib.sha256((header+body).encode()).hexdigest()},
                    "runner_call_template":_call_template(system,pair_id,condition_id,config_hash),
                    "legacy_log_projection":attack_log_fields(row),
                    "final_generator_visibility":"UNKNOWN_NOT_EXECUTED"}
                validate_call_shape(request["runner_call_template"],system)
                request["runner_request_sha256"] = digest(request)
                requests.append(request)
            if canonical(normalized[0]) != canonical(normalized[1]):
                raise ValueError("undeclared pool differences beyond header")
            pairs.append({"schema_version":VERSION,"scope":"SYNTHETIC_ONLY","execution_status":BLOCKED,
                "pair_id":pair_id,"system":system,"source_qa_id":original["source_qa_id"],
                "requests":requests, "header_only_proof":{"method":"strip declared prefix; compare complete canonical pool",
                    "normalized_pool_sha256":digest(normalized[0]),"source_lineage_equal":True,
                    "condition_trace_fields_differ_by_design":True}})
    return pairs


def validate_request_pairs(pairs, pool_records, *, mode, systems=None, slots=None, configurations=None):
    if type(pairs) is not list or any(type(p) is not dict or type(p.get("pair_id")) is not str for p in pairs):
        raise ValueError("malformed request-pair list")
    if len({p["pair_id"] for p in pairs}) != len(pairs):
        raise ValueError("duplicate pair identity")
    expected = build_request_pairs(pool_records, mode=mode, systems=systems, slots=slots, configurations=configurations)
    if canonical(pairs) != canonical(expected):
        raise ValueError("request differs from authoritative registered replay")
    return True


def write_pairs(pairs, pool_records, *, output, mode, systems=None):
    repo = ROOT.resolve()
    expected_root = repo / "audits/g2_i2_v1"
    allowed = expected_root.resolve()
    target = Path(output).resolve()
    if allowed != expected_root or not target.is_relative_to(allowed) or target == allowed or target.suffix != ".jsonl":
        raise ValueError("synthetic audit paths only; production and prior audits forbidden")
    validate_request_pairs(pairs,pool_records,mode=mode,systems=systems)
    data = "".join(canonical(p)+"\n" for p in pairs).encode()
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as handle:
        handle.write(data)
    return {"pairs":len(pairs),"requests":2*len(pairs),"sha256":hashlib.sha256(data).hexdigest(),
            "scope":"SYNTHETIC_ONLY","execution_status":BLOCKED}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Blocked synthetic request construction; no model/runner execution")
    parser.add_argument("--synthetic-fixtures",action="store_true",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    records,sources=synthetic_fixture_bundle()
    pool=convert_records(records,sources=sources,attack_family="fabricated_fresh",mode="synthetic")
    pairs=build_request_pairs(pool,mode="synthetic")
    print(json.dumps(write_pairs(pairs,pool,output=args.output,mode="synthetic"),sort_keys=True))
