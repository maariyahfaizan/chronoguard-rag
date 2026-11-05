import copy
import json
import sys

import pytest

from src.eval.no_execution_boundary import ExecutionBlocked
from src.eval.request_context_traces import (
    build_traces, registered_pairs, validate_traces, write_traces,
)


@pytest.fixture(scope="module")
def pairs():
    return registered_pairs()


def test_registered_context_and_exact_prompt(pairs):
    traces=build_traces(pairs)
    assert len(traces)==16
    for trace in traces:
        assert not trace["violations"]
        assert trace["false_claim_complete"] and trace["gold_evidence_complete"]
        assert trace["context"]=="\n\n".join(trace["selected_passage_texts"])
        assert trace["prompt"].split("Context:\n",1)[1].startswith(trace["context"])
        assert trace["user_message"]["content"]==trace["prompt"]
        assert trace["generator_token_count"]=="UNKNOWN"
        assert trace["model_receipt"]=="NOT_EXECUTED"
        assert trace["selected_slots"]==[0,1]
        assert trace["execution_status"]=="NOT_AUTHORIZED_FOR_EXECUTION"


@pytest.mark.parametrize("mutation",["request_id","real_qa","hash","candidate_order","header",
                                    "body","metadata","configuration","date","budget"])
def test_unauthorized_request_rejected(pairs,mutation):
    changed=copy.deepcopy(pairs)
    req=changed[0]["requests"][0]
    if mutation=="request_id":req["condition_id"]="unauthorized"
    elif mutation=="real_qa":req["source_qa_id"]="real-benchmark-001"
    elif mutation=="hash":req["runner_request_sha256"]="0"*64
    elif mutation=="candidate_order":req["pool_record"]["candidates"].reverse()
    elif mutation=="header":req["intervention"]["header"]="Different:\n"
    elif mutation=="body":req["pool_record"]["candidates"][1]["text"]+="changed body"
    elif mutation=="metadata":req["pool_record"]["candidates"][1]["source_metadata"]["origin"]="drift"
    elif mutation=="configuration":req["configuration"]["generation"]["max_passage_chars"]=12
    elif mutation=="date":req["pool_record"]["candidates"][1]["timestamp"]="2099-01-01T00:00:00+00:00"
    else:req["poison_budget"]=2
    with pytest.raises(ValueError):build_traces(changed)


def test_false_claim_truncation_and_asymmetry(pairs):
    body=pairs[0]["requests"][0]["intervention"]["body"]
    traces=build_traces(pairs,audit_caps={"passage_chars":len(body)+15})
    assert any(t["asymmetric_false_claim_truncation"] for t in traces)
    assert any("FALSE_CLAIM_NOT_COMPLETE_IN_ASSEMBLED_PROMPT" in t["violations"] for t in traces)
    assert all("PASSAGE_BUDGET_OVERRIDE_SYNTHETIC_FAULT" in t["violations"] for t in traces)


@pytest.mark.parametrize("key,marker",[("context_chars","CONTEXT_BUDGET_VIOLATION_SYNTHETIC_FAULT"),
                                      ("prompt_chars","PROMPT_BUDGET_VIOLATION_SYNTHETIC_FAULT")])
def test_global_budget_faults_are_explicit(pairs,key,marker):
    traces=build_traces(pairs,audit_caps={key:20})
    assert all(marker in t["violations"] for t in traces)
    assert all(not t["false_claim_complete"] for t in traces)


def test_missing_claim_is_not_retrieval_exposure(pairs):
    traces=build_traces(pairs,selected_slots=[0])
    assert all(not t["false_claim_complete"] for t in traces)
    assert all(t["retrieved_passages"]=="NOT_EXECUTED" for t in traces)


@pytest.mark.parametrize("slots",[[1,0],[1,1],[-1],[True],[],[2]])
def test_selection_order_and_bounds(pairs,slots):
    with pytest.raises(ValueError):build_traces(pairs,selected_slots=slots)


def test_duplicate_or_modified_trace_rejected(pairs):
    traces=build_traces(pairs)
    with pytest.raises(ValueError):validate_traces(traces+[copy.deepcopy(traces[0])],pairs)
    traces[0]["context"]+="modified"
    with pytest.raises(ValueError):validate_traces(traces,pairs)


def test_deterministic_traces_and_pair_invariants(pairs):
    a,b=build_traces(pairs),build_traces(pairs)
    assert a==b
    for neutral,fresh in zip(a[::2],a[1::2]):
        for field in ("pair_id","source_qa_id","candidate_order","selected_slots","configuration_sha256",
                      "body_sha256","false_claim_body","configured_passage_char_limit","allocated_passage_characters",
                      "pair_invariant_binding","selected_evidence_bodies"):
            assert neutral[field]==fresh[field]
        assert neutral["header"]!=fresh["header"]
        assert neutral["original_request_sha256"]!=fresh["original_request_sha256"]


def test_writer_path_guards_and_no_overwrite(pairs,tmp_path,monkeypatch):
    import src.eval.request_context_traces as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    traces=build_traces(pairs)
    path=tmp_path/"audits/g2_i3_v1/context_traces.jsonl"
    write_traces(traces,pairs,output=path)
    assert [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]==traces
    with pytest.raises(FileExistsError):write_traces(traces,pairs,output=path)
    for forbidden in (tmp_path/"data/pool.jsonl",tmp_path/"audits/g2_i2_v1/trace.jsonl",tmp_path/"results/trace.jsonl"):
        with pytest.raises(ValueError):write_traces(traces,pairs,output=forbidden)
        assert not forbidden.exists()


@pytest.mark.parametrize("operation",["retrieval","generation","attack","model_import","network","process"])
def test_boundary_denies_before_operation_body(operation):
    guard=sys._chronoguard_g2_i3_boundary
    with pytest.raises(ExecutionBlocked):guard.probe(operation)
    assert guard.report()["profile_active"]


@pytest.mark.parametrize("caps",[{"passage_chars":0},{"prompt_chars":True},{"unknown":1}])
def test_invalid_budgets_rejected(pairs,caps):
    with pytest.raises(ValueError):build_traces(pairs,audit_caps=caps)
