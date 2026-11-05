import copy
import json
import sys

import pytest

from src.eval.no_execution_boundary import ExecutionBlocked
from src.eval.canonical_analysis_input import (
    _legacy_validator, build_analysis_input, identity_map, lookup_identity, registered_exports,
    require_estimator_ingestion, validate_analysis_input, validate_identity_map, write_analysis_input,
)


@pytest.fixture(scope="module")
def records():
    return registered_exports()


def test_reversible_map_and_grouping(records):
    mapping=identity_map(records)
    assert len(mapping["entries"])==2
    for e in mapping["entries"]:
        cid,aid=e["canonical_question_id"],e["analysis_question_id"]
        assert aid.startswith("synthetic-stat-g2-i5-")
        assert lookup_identity(mapping,cid,direction="canonical_to_analysis",records=records)==aid
        assert lookup_identity(mapping,aid,direction="analysis_to_canonical",records=records)==cid
        assert len(e["cells"])==len({c["cell_id"] for c in e["cells"]})==8
        assert all(c["canonical_question_id"]==cid for c in e["cells"])


def test_actual_legacy_validator_projection_without_estimation(records):
    bundle=build_analysis_input(records,mode="synthetic")
    validator=_legacy_validator()
    canonical_frame=[{"question_id":q,"eligibility":"UNKNOWN","clean":"MISSING"}
                     for q in sorted({r["question_id"] for r in records})]
    with pytest.raises(ValueError,match="fictional question IDs"):
        validator(canonical_frame,[r["analysis_projection"] for r in records])
    assert validator([r["analysis_frame"] for r in bundle["frame_records"]],
                     [r["analysis_projection"] for r in bundle["records"]])
    assert "src.eval.synthetic_analysis" not in sys.modules


def test_preserved_canonical_cell_prompt_identity_and_missingness(records):
    bundle=build_analysis_input(records,mode="synthetic")
    source={r["cell_id"]:r for r in records}
    for r in bundle["records"]:
        old=source[r["cell_id"]]
        assert r["question_id"]==r["canonical_question_id"]==old["question_id"]
        assert r["cell_id"]==old["cell_id"]
        for field in ("source_construction_sha256","prompt_sha256","context_sha256","analysis_condition",
                      "source_factors","analysis_factors","passages","missingness_reason"):
            assert r[field]==old[field]
        assert r["outcome_state"]=="UNOBSERVED"
        assert r["analysis_projection"]["outcome"]=="MISSING"
        assert r["analysis_projection"]["generator"]=="UNVERIFIED"
        assert r["execution_status"]=="NOT_AUTHORIZED_FOR_EXECUTION"
        assert r["source_analysis_projection"]["question_id"]==r["canonical_question_id"]


@pytest.mark.parametrize("mutation",["collision","duplicate_canonical","source_hash","missing_cell",
                                    "wrong_pair","real_id","version"])
def test_invalid_identity_map(records,mutation):
    m=identity_map(records)
    if mutation=="collision":m["entries"][1]["analysis_question_id"]=m["entries"][0]["analysis_question_id"]
    elif mutation=="duplicate_canonical":m["entries"].append(copy.deepcopy(m["entries"][0]))
    elif mutation=="source_hash":m["entries"][0]["cells"][0]["source_construction_sha256"]="0"*64
    elif mutation=="missing_cell":m["entries"][0]["cells"].pop()
    elif mutation=="wrong_pair":m["entries"][0]["cells"][0]=copy.deepcopy(m["entries"][1]["cells"][0])
    elif mutation=="real_id":m["entries"][0]["canonical_question_id"]="real-qa-id"
    else:m["schema_version"]="unsupported"
    with pytest.raises(ValueError):validate_identity_map(m,records)


def test_collision_during_map_creation_is_rejected(records,monkeypatch):
    import src.eval.canonical_analysis_input as module
    monkeypatch.setattr(module,"_alias",lambda *a:"synthetic-stat-g2-i5-forced-collision")
    with pytest.raises(ValueError,match="collision"):identity_map(records)


@pytest.mark.parametrize("mutation",["missing","duplicate","source_hash","factor","prompt_hash","real_id"])
def test_invalid_source_exports(records,mutation):
    changed=copy.deepcopy(records)
    if mutation=="missing":changed.pop()
    elif mutation=="duplicate":changed[-1]=copy.deepcopy(changed[0])
    elif mutation=="source_hash":changed[0]["source_construction_sha256"]="0"*64
    elif mutation=="factor":changed[0]["analysis_condition"]="incorrect_newer/freshness/incorrect_first"
    elif mutation=="prompt_hash":changed[0]["prompt_sha256"]="0"*64
    else:changed[0]["question_id"]="real-question"
    with pytest.raises(ValueError):build_analysis_input(changed,mode="synthetic")


@pytest.mark.parametrize("mutation",["pairing","outcome","visibility","eligibility","authorization","canonical_id"])
def test_bundle_pairing_and_gates(records,mutation):
    b=build_analysis_input(records,mode="synthetic")
    if mutation=="pairing":b["records"][0]["analysis_projection"]["question_id"]=b["frame_records"][1]["analysis_question_id"]
    elif mutation=="outcome":b["records"][0]["analysis_projection"]["outcome"]=0
    elif mutation=="visibility":b["records"][0]["analysis_projection"]["generator"]="YES"
    elif mutation=="eligibility":b["frame_records"][0]["analysis_frame"]["eligibility"]="ELIGIBLE"
    elif mutation=="authorization":b["records"][0]["execution_status"]="FORGED_AUTHORIZATION"
    else:b["records"][0]["canonical_question_id"]="different"
    with pytest.raises(ValueError):validate_analysis_input(b,records)


def test_estimator_gate_never_returns_numerical_rows(records):
    b=build_analysis_input(records,mode="synthetic")
    assert validate_analysis_input(b,records)
    with pytest.raises(ValueError,match="NOT_ESTIMABLE"):require_estimator_ingestion(b,records)
    with pytest.raises(ValueError):build_analysis_input(records,mode="real")


def test_deterministic_map_and_export(records):
    assert identity_map(records)==identity_map(list(reversed(records)))
    assert build_analysis_input(records,mode="synthetic")==build_analysis_input(list(reversed(records)),mode="synthetic")


def test_writer_paths_and_no_overwrite(records,tmp_path,monkeypatch):
    import src.eval.canonical_analysis_input as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    b=build_analysis_input(records,mode="synthetic")
    p=tmp_path/"audits/g2_i5_v1/bundle.json"
    write_analysis_input(b,records,output=p)
    assert json.loads(p.read_text(encoding="utf-8"))==b
    with pytest.raises(FileExistsError):write_analysis_input(b,records,output=p)
    for forbidden in (tmp_path/"data/bundle.json",tmp_path/"audits/g2_i4_v1/bundle.json",
                      tmp_path/"audits/g2_i5_v1/../../../escape.json"):
        with pytest.raises(ValueError):write_analysis_input(b,records,output=forbidden)
        assert not forbidden.exists()


@pytest.mark.parametrize("operation",["retrieval","generation","attack","model_import","network","process","judge","statistics"])
def test_prohibited_operations(operation):
    guard=sys._chronoguard_g2_i5_boundary
    with pytest.raises(ExecutionBlocked):guard.probe(operation)
    assert guard.report()["profile_active"]
