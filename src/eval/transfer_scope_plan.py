"""Development-only scope/resource planning; no model loading or outcome inputs."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from src.eval.offline_input_audit import ROOT, sha

UNKNOWN = "UNKNOWN"
ROLES = {"StreamingQA": "primary_temporal", "FreshQA": "independent_temporal_factual",
         "TriviaQA": "static_control", "NaturalQuestions": "static_control"}
GATES = ["evidence_and_key_adjudication", "exposure_sampling_policy", "statistical_protocol",
         "backend_input_verification", "independent_judge_validation", "benchmark_protocol_freeze",
         "explicit_week6_authorization"]
WEB_SOURCES = [
    {"url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct", "basis": "official model card; Apache-2.0; 7.61B; apply_chat_template"},
    {"url": "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct", "basis": "official model card; gated access; Llama 3.1 license; 8B; chat template"},
    {"url": "https://huggingface.co/docs/transformers/quantization/bitsandbytes", "basis": "official runtime/quantization documentation; no local compatibility measurement"},
]


def weight_memory(parameters, bits):
    if type(parameters) not in (int,float) or not math.isfinite(parameters) or parameters <= 0 or bits not in (4,8,16,32):
        raise ValueError("positive parameter count and supported bit width required")
    return parameters * bits / 8 / 2**30


def model_candidates():
    return [{"model": model, "family": family, "revision": UNKNOWN, "parameters_approx": p,
             "license_access": access, "local_model_available": False,
             "weight_only_GiB_16bit": weight_memory(p,16), "weight_only_GiB_4bit": weight_memory(p,4),
             "peak_VRAM_GiB": UNKNOWN, "seconds_per_answer": UNKNOWN,
             "tokenizer_chat_template": "model-specific AutoTokenizer.apply_chat_template; unverified locally",
             "quantization": "proposed 4-bit bitsandbytes; not locally verified or mandatory on unknown hardware",
             "decoding": "proposed do_sample=False; exact determinism across hardware not established",
             "status": "PROPOSED_CONDITIONAL" if family == "Qwen2.5" else "ALTERNATIVE_NOT_SELECTED"}
            for model,family,p,access in [
                ("Qwen/Qwen2.5-7B-Instruct","Qwen2.5",7.61e9,"Apache-2.0 per official card; account/network access not tested"),
                ("meta-llama/Llama-3.1-8B-Instruct","Llama3.1",8e9,"gated HF access; Llama 3.1 Community License and use policy; acceptance not established")]]


def validate_models(models):
    for m in models:
        allowed={"Qwen/Qwen2.5-7B-Instruct":"Qwen2.5","meta-llama/Llama-3.1-8B-Instruct":"Llama3.1"}
        if allowed.get(m["model"])!=m["family"]:
            raise ValueError("model identifier/family mismatch")
        if m["family"].lower().startswith("mistral"):
            raise ValueError("transfer family must differ from primary Mistral")
        if m["revision"] != UNKNOWN or m.get("seconds_per_answer") != UNKNOWN or m.get("peak_VRAM_GiB") != UNKNOWN:
            raise ValueError("this proposal has no verified revision or benchmark measurements")
    return True


def validate_roles(datasets):
    names=[d["name"] for d in datasets]
    if (len(names)!=3 or len(set(names))!=3 or not {"StreamingQA","FreshQA"}.issubset(names)
            or len(set(names)&{"TriviaQA","NaturalQuestions"})!=1):
        raise ValueError("exactly three roles including one static-control dataset required")
    for dataset in datasets:
        if dataset["name"] not in ROLES or dataset["role"] != ROLES[dataset["name"]]:
            raise ValueError("dataset-role mismatch")
        if dataset["provenance"] not in ("UNRESOLVED", "TRACEABLE_NOT_AUTHENTICATED", "UNKNOWN"):
            raise ValueError("unestablished dataset provenance claim")
        if dataset.get("confirmatory_approved") is not False:
            raise ValueError("no dataset approval recorded")
    return True


def gate_report(states=None):
    states = {} if states is None else states
    if set(states) - set(GATES) or any(v != "UNRECORDED" for v in states.values()):
        raise ValueError("this checkpoint cannot record approvals")
    return {"execution": "BLOCKED", "ordered_dependencies": [
        {"gate": g, "status": states.get(g,"UNRECORDED"), "depends_on": GATES[:i]} for i,g in enumerate(GATES)],
        "missing_records": [g for g in GATES if g not in states]}


def scenario(*, questions, retrieval_conditions, attack_families, matched_conditions=2,
             negative_controls=0, rq3_questions=0, generators=2, generation_repetitions=1,
             retrieval_repetitions=1, evaluation_passes=1, judge_passes=1,
             retrieval_variant_groups=None, generation_variant_groups=None,
             seconds_per_generation=None, seconds_per_retrieval=None, seconds_per_judge=None):
    """Counts are hypothetical. Clean runs shared across attack families.

    Retrieval is cached across generators/generation repeats. RQ3 is its own
    eight-cell workload with no retrieval/family/matched-condition multiplier.
    Negative controls must be disjoint from the counted matched arms.
    """
    args = locals().copy()
    dimensions = ["questions","retrieval_conditions","attack_families","matched_conditions","negative_controls",
                  "rq3_questions","generators","generation_repetitions","retrieval_repetitions","evaluation_passes","judge_passes"]
    if any(type(args[k]) is not int or args[k] < 0 for k in dimensions):
        raise ValueError("nonnegative integer dimensions required")
    if any(args[k] < 1 for k in ("retrieval_conditions","matched_conditions","generators","generation_repetitions","retrieval_repetitions")):
        raise ValueError("positive active backend/condition/repetition counts required")
    if rq3_questions > questions:
        raise ValueError("RQ3 count must be a subset count of the hypothetical frame")
    variants = 1 + attack_families * matched_conditions + negative_controls
    groups=[]
    for value in (retrieval_variant_groups,generation_variant_groups):
        value=list(map(str,range(variants))) if value is None else value
        if type(value) is not list or len(value)!=variants or any(type(k) is not str or not k for k in value):
            raise ValueError("one explicit equivalence-group key per declared variant required")
        groups.append(value)
    # Reusing a generated answer requires the same underlying context group.
    mapping={}
    for ret,gen in zip(*groups):
        if gen in mapping and mapping[gen]!=ret:
            raise ValueError("cannot reuse an answer across distinct context groups")
        mapping[gen]=ret
    retrieval = questions * retrieval_conditions * len(set(groups[0])) * retrieval_repetitions
    end_to_end = questions * retrieval_conditions * len(set(groups[1])) * retrieval_repetitions * generators * generation_repetitions
    isolated = rq3_questions * 8 * generators * generation_repetitions
    generations = end_to_end + isolated
    judge = generations * judge_passes
    for k in ("seconds_per_generation","seconds_per_retrieval","seconds_per_judge"):
        if args[k] is not None and (type(args[k]) not in (int,float) or not math.isfinite(args[k]) or args[k] < 0):
            raise ValueError("per-unit durations must be nonnegative measured inputs or unavailable")
    times = [(generations,seconds_per_generation),(retrieval,seconds_per_retrieval),(judge,seconds_per_judge)]
    total = sum(n*t for n,t in times if n and t is not None) if all(n==0 or t is not None for n,t in times) else UNKNOWN
    return {"status": "HYPOTHETICAL_NOT_APPROVED", "inputs": args,
            "declared_variants":variants,"retrieval_variant_groups":groups[0],"generation_variant_groups":groups[1],
            "unique_retrieval_work_units": retrieval, "end_to_end_generations": end_to_end,
            "rq3_direct_generations": isolated, "total_generations": generations,
            "evaluation_passes": generations * evaluation_passes, "judge_passes": judge,
            "total_serial_seconds_excluding_setup_and_evaluation": total,
            "GPU_availability": UNKNOWN, "peak_memory": UNKNOWN, "token_usage": UNKNOWN,
            "reuse_assumption": "same frozen retrieval/config/seed hashes across generators; distinct retrieval repeats require distinct contexts"}


def dataset_inventory():
    """Read question/evidence artifacts only; never generated-answer logs."""
    paths = {"streaming_sample": "data/raw/streamingqa_control_sample.jsonl",
             "streaming_pools": "data/processed/streamingqa_control_pools_chunked.jsonl",
             "fresh_questions": "data/processed/freshqa_questions.jsonl",
             "fresh_snapshot": "data/raw/freshqa_evidence_snapshot.jsonl",
             "fresh_pools": "data/processed/freshqa_control_pools.jsonl",
             "trivia_pools": "data/processed/triviaqa_control_clean.jsonl"}
    result = {}
    for name,relative in paths.items():
        count, ids, counters = 0, set(), Counter()
        with (ROOT/relative).open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                count += 1
                ident = row.get("query_id",row.get("qa_id"))
                if ident is not None:
                    ids.add(str(ident))
                if name == "fresh_snapshot":
                    counters["fetch_status:"+str(row.get("fetch_status","MISSING"))] += 1
                    counters["nonempty_text"] += bool(row.get("text"))
                    counters["source_date_present"] += bool(row.get("source_date"))
                    counters["retrieval_time_present"] += bool(row.get("snapshot_retrieved_at"))
                if "candidates" in row:
                    candidates = row["candidates"]
                    counters["candidate_occurrences"] += len(candidates)
                    counters["dict_candidate_occurrences"] += sum(isinstance(c,dict) for c in candidates)
                    counters["string_candidate_occurrences"] += sum(isinstance(c,str) for c in candidates)
                    counters["nonempty_candidate_rows"] += bool(candidates)
                    counters["rows_with_source_flagged_candidate"] += any(isinstance(c,dict) and c.get("is_source_document") for c in candidates)
                    for c in candidates:
                        if isinstance(c,dict):
                            counters["candidate_timestamp_present"] += bool(c.get("timestamp"))
                            counters["source_flagged_candidates"] += bool(c.get("is_source_document"))
                counters["gold_answer_present"] += bool(row.get("gold_answer"))
                counters["question_time_present"] += bool(row.get("question_ts"))
                if "candidate_metadata" in row:
                    metadata = row["candidate_metadata"]
                    counters["metadata_occurrences"] += len(metadata)
                    counters["rows_with_metadata_source_flag"] += any(c.get("is_source_document") for c in metadata)
                    counters["metadata_source_date_present"] += sum(bool(c.get("source_date")) for c in metadata)
                    counters["metadata_source_flags"] += sum(bool(c.get("is_source_document")) for c in metadata)
                    counters["candidate_metadata_length_mismatch"] += len(metadata) != len(row.get("candidates",[]))
        result[name] = {"path": relative,"sha256":sha(ROOT/relative),"rows":count,
                        "explicit_unique_question_ids":len(ids),"field_coverage":dict(sorted(counters.items()))}
    return result


def dataset_roles():
    return [{"name":name,"role":role,"provenance":"UNRESOLVED", "confirmatory_approved":False,
             "attack_family_eligibility":"UNKNOWN_PENDING_CASE_REVIEW"}
            for name,role in ROLES.items() if name != "NaturalQuestions"]
