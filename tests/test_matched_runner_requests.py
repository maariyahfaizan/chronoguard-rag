import copy

import pytest

from src.attacks.attack_pool import _validate_record
from src.attacks.matched_controls import digest
from src.attacks.pilot_protocol import read_jsonl
from src.eval.adjudicated_pool_adapter import synthetic_fixture_bundle, convert_records
from src.eval.matched_runner_requests import (
    BLOCKED, INTERFACES, build_request_pairs, configuration, validate_call_shape,
    validate_request_pairs, write_pairs,
)


@pytest.fixture(scope="module")
def registered_pool():
    r,s=synthetic_fixture_bundle()
    return convert_records(r,sources=s,attack_family="fabricated_fresh",mode="synthetic")


def build(pool):
    return build_request_pairs(pool,mode="synthetic",systems=["E1"])


def test_all_runners_and_actual_schema(registered_pool,tmp_path):
    pairs=build_request_pairs(registered_pool,mode="synthetic")
    assert len(pairs)==8 and len({p["pair_id"] for p in pairs})==8
    assert {p["system"] for p in pairs}==set(INTERFACES)
    for p in pairs:
        for req in p["requests"]:
            assert req["scope"]=="SYNTHETIC_ONLY"
            assert req["execution_status"]==BLOCKED
            _validate_record(req["pool_record"])
            assert validate_call_shape(req["runner_call_template"],p["system"])
            file=tmp_path/(req["condition"]+p["system"]+".jsonl")
            # Actual loader compatibility; no runner is called.
            import json
            file.write_text(json.dumps(req["pool_record"])+"\n",encoding="utf-8")
            assert read_jsonl(file)==[req["pool_record"]]


def test_only_header_changes_and_lineage_stays_bound(registered_pool):
    for pair in build(registered_pool):
        a,b=pair["requests"]
        assert a["intervention"]["body"]==b["intervention"]["body"]
        assert a["false_claim_variant_id"]==b["false_claim_variant_id"]
        assert a["source_variant_ids"]==b["source_variant_ids"]
        assert a["candidate_order"]==b["candidate_order"]
        assert a["configuration"]==b["configuration"]
        assert a["poison_budget"]==b["poison_budget"]==1
        normalized=[]
        for req in (a,b):
            row=copy.deepcopy(req["pool_record"])
            header=req["intervention"]["header"]
            assert row["candidates"][1]["text"].startswith(header)
            row["candidates"][1]["text"]=row["candidates"][1]["text"][len(header):]
            normalized.append(row)
            assert row["adapter_metadata"]["execution_authorized"] is False
            assert req["legacy_log_projection"]["attack_condition"]!="clean"
        assert normalized[0]==normalized[1]


@pytest.mark.parametrize("mutation",["body","source_id","variant","order","metadata","aliases","timestamp",
                                    "budget","configuration","config_hash","request_hash","missing_config",
                                    "runtime_binding","real_input_path","real_log_path","proof"])
def test_reject_undeclared_request_changes(registered_pool,mutation):
    pairs=build(registered_pool)
    req=pairs[0]["requests"][1]
    row=req["pool_record"]
    if mutation=="body":
        row["candidates"][1]["text"]+="changed"
    elif mutation=="source_id":
        row["candidates"][1]["source_id"]="changed"
    elif mutation=="variant":
        req["false_claim_variant_id"]="changed"
    elif mutation=="order":
        row["candidates"].reverse()
    elif mutation=="metadata":
        row["candidates"][1]["source_metadata"]["origin"]="changed"
    elif mutation=="aliases":
        row["gold_aliases"]=[]
    elif mutation=="timestamp":
        row["candidates"][1]["timestamp"]="2099-01-01T00:00:00+00:00"
    elif mutation=="budget":
        req["poison_budget"]=2
    elif mutation=="configuration":
        req["configuration"]["generation"]["decoding"]["max_new_tokens"]=100
    elif mutation=="config_hash":
        req["configuration_sha256"]="0"*64
    elif mutation=="request_hash":
        req["runner_request_sha256"]="0"*64
    elif mutation=="missing_config":
        del req["configuration"]
    elif mutation=="runtime_binding":
        req["runner_call_template"]["runtime_bindings"]=[]
    elif mutation in ("real_input_path","real_log_path"):
        key="input_path" if mutation=="real_input_path" else "log_path"
        req["runner_call_template"]["keyword_arguments"][key]="data/production.jsonl"
    else:
        pairs[0]["header_only_proof"]["normalized_pool_sha256"]="0"*64
    with pytest.raises(ValueError):
        validate_request_pairs(pairs,registered_pool,mode="synthetic",systems=["E1"])


def test_rehashed_unauthorized_request_still_rejected(registered_pool):
    pairs=build(registered_pool)
    req=pairs[0]["requests"][0]
    req["pool_record"]["candidates"][1]["text"]="unauthorized body"
    req["pool_record_sha256"]=digest(req["pool_record"])
    req["runner_request_sha256"]=digest({k:v for k,v in req.items() if k!="runner_request_sha256"})
    with pytest.raises(ValueError):
        validate_request_pairs(pairs,registered_pool,mode="synthetic",systems=["E1"])


@pytest.mark.parametrize("mutation",["real_id","unknown_eligibility","missing_registration","provenance","claim_key","ordering"])
def test_registered_pool_gates(registered_pool,mutation):
    pool=copy.deepcopy(registered_pool)
    if mutation=="real_id":
        pool[0]["source_qa_id"]="real-benchmark-001"
    elif mutation=="unknown_eligibility":
        pool[0]["adapter_metadata"]["eligibility"]["status"]="UNKNOWN"
    elif mutation=="missing_registration":
        del pool[0]["adapter_metadata"]
    elif mutation=="provenance":
        pool[0]["adapter_metadata"]["provenance"]["tier"]="AUTHENTICATED_ORIGINAL"
    elif mutation=="claim_key":
        pool[0]["synthetic_claim_key"]["key"]["approval_status"]="candidate"
    else:
        pool[0]["candidates"].reverse()
    with pytest.raises(ValueError):
        build(pool)


def test_missing_or_changed_configs_rejected(registered_pool):
    with pytest.raises(ValueError):
        build_request_pairs(registered_pool,mode="synthetic",systems=["E1"],configurations={})
    cfg={"E1":configuration("E1")}
    cfg["E1"]["retrieval"]["parameters"]["top_k"]=1
    with pytest.raises(ValueError):
        build_request_pairs(registered_pool,mode="synthetic",systems=["E1"],configurations=cfg)


def test_duplicate_pair_and_system_ids(registered_pool):
    pairs=build(registered_pool)
    with pytest.raises(ValueError):
        validate_request_pairs(pairs+[copy.deepcopy(pairs[0])],registered_pool,mode="synthetic",systems=["E1"])
    with pytest.raises(ValueError):
        build_request_pairs(registered_pool,mode="synthetic",systems=["E1","E1"])


def test_no_retrieval_generation_or_dispatch(registered_pool,monkeypatch):
    import src.retrieval.bm25 as bm25
    import src.eval.offline_input_audit as observer
    def forbidden(*args,**kwargs):
        pytest.fail("retrieval/generation execution is forbidden")
    monkeypatch.setattr(bm25,"retrieve_best",forbidden)
    monkeypatch.setattr(observer,"capture_generate_boundary",forbidden)
    assert build(registered_pool)==build(registered_pool)
    with pytest.raises(ValueError):
        build_request_pairs(registered_pool,mode="real")


def test_writer_guards_and_deterministic_bytes(registered_pool,tmp_path,monkeypatch):
    import src.eval.matched_runner_requests as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    pairs=build(registered_pool)
    first=tmp_path/"audits/g2_i2_v1/a.jsonl"
    second=tmp_path/"audits/g2_i2_v1/b.jsonl"
    write_pairs(pairs,registered_pool,output=first,mode="synthetic",systems=["E1"])
    write_pairs(pairs,registered_pool,output=second,mode="synthetic",systems=["E1"])
    assert first.read_bytes()==second.read_bytes()
    with pytest.raises(FileExistsError):
        write_pairs(pairs,registered_pool,output=first,mode="synthetic",systems=["E1"])
    for path in (tmp_path/"data/production.jsonl",tmp_path/"audits/g2_i1_v1/pool.jsonl"):
        with pytest.raises(ValueError):
            write_pairs(pairs,registered_pool,output=path,mode="synthetic",systems=["E1"])
        assert not path.exists()


def test_call_template_rejects_real_paths_and_signature_errors(registered_pool):
    call=build(registered_pool)[0]["requests"][0]["runner_call_template"]
    call["keyword_arguments"]["input_path"]="data/production.jsonl"
    with pytest.raises(ValueError):
        validate_call_shape(call,"E1")
    call["keyword_arguments"]["input_path"]="__SYNTHETIC_INPUT_NOT_MATERIALIZED__"
    call["keyword_arguments"]["unexpected_kwarg"]=1
    with pytest.raises(TypeError):
        validate_call_shape(call,"E1")
