import copy
import json
import sys

import pytest

from src.eval.no_execution_boundary import ExecutionBlocked
from src.eval.rq3_analysis_export import (
    CONDITIONS, FACTOR_MAP, _analysis_schema, analysis_bundle, estimator_inputs,
    export_conditions, map_factors, registered_cells, validate_export, write_export,
)


@pytest.fixture(scope="module")
def cells():
    return registered_cells()


def test_complete_blocks_and_explicit_mapping(cells):
    records=export_conditions(cells)
    assert len(records)==16
    for qid in {c["synthetic_case_id"] for c in cells}:
        block=[r for r in records if r["question_id"]==qid]
        assert len(block)==8 and {r["analysis_condition"] for r in block}==set(CONDITIONS)
    assert FACTOR_MAP["newer_looking"]=={"correct":"correct_newer","incorrect":"incorrect_newer"}
    for r in records:
        assert r["cell_id"]==r["source_cell_id"]
        assert r["question_id"].startswith("synthetic-smoke-")
        assert r["outcome_state"]=="UNOBSERVED"
        assert r["analysis_projection"]["outcome"]=="MISSING"
        assert r["passage_order_verified"]
        assert r["actual_model_visibility"]=="UNKNOWN"
        assert all(p["complete_claim"] for p in r["passages"])


def test_context_hash_order_and_source_prompt(cells):
    records=export_conditions(cells)
    indexed={c["cell_id"]:c for c in cells}
    for r in records:
        source=indexed[r["cell_id"]]
        assert r["prompt"]==source["prompt"]
        assert r["prompt_sha256"]==source["prompt_sha256"]
        assert [p["doc_id"] for p in r["passages"]]==[p["doc_id"] for p in source["passages"]]
        assert [p["original_body_sha256"] for p in r["passages"]]==[p["original_body_sha256"] for p in source["passages"]]
        assert r["context"]=="\n\n".join(p["rendered_text"] for p in source["passages"])


@pytest.mark.parametrize("mutation",["missing","duplicate","extra","factor","hash","passage_order",
                                    "claim","date","question","real_id","header","body_variant"])
def test_unregistered_or_incomplete_constructions_rejected(cells,mutation):
    changed=copy.deepcopy(cells)
    if mutation=="missing":changed.pop()
    elif mutation=="duplicate":changed[-1]=copy.deepcopy(changed[0])
    elif mutation=="extra":changed.append(copy.deepcopy(changed[0]))
    elif mutation=="factor":changed[0]["factors"]["newer_looking"]="incorrect"
    elif mutation=="hash":changed[0]["prompt_sha256"]="0"*64
    elif mutation=="passage_order":changed[0]["passages"].reverse()
    elif mutation=="claim":changed[0]["passages"][0]["body"]+="altered"
    elif mutation=="date":changed[0]["passages"][0]["assigned_date_label"]="2099-01-01"
    elif mutation=="question":changed[0]["question"]="Changed question?"
    elif mutation=="real_id":changed[0]["synthetic_case_id"]="real-benchmark-id"
    elif mutation=="header":changed[0]["passages"][0]["header"]="Changed:\n"
    else:changed[0]["passages"][0]["original_body_sha256"]="0"*64
    with pytest.raises(ValueError):export_conditions(changed)


@pytest.mark.parametrize("factors",[
    {"newer_looking":"correct_newer","header_wording":"neutral","passage_order":"correct_first"},
    {"newer_looking":"not_incorrect","header_wording":"neutral","passage_order":"correct_first"},
    {"newer_looking":"correct","header_wording":"freshness","passage_order":"incorrect"},
    {"newer_looking":"correct","header_wording":"neutral"},
])
def test_no_factor_substring_inference(factors):
    with pytest.raises(ValueError):map_factors(factors)


def test_deterministic_order_even_if_input_order_changes(cells):
    assert export_conditions(cells)==export_conditions(list(reversed(cells)))


def test_unobserved_is_never_numerical(cells):
    records=export_conditions(cells)
    bundle=analysis_bundle(records,cells)
    schema=_analysis_schema()
    assert bundle["status"]=="NOT_ESTIMABLE_UNOBSERVED"
    assert all(q["eligibility"]=="UNKNOWN" for q in bundle["frame"])
    assert all(set(row)==set(schema["row_fields"]) for row in bundle["rows"])
    assert all(row["outcome"]=="MISSING" and row["generator"]=="UNVERIFIED" for row in bundle["rows"])
    with pytest.raises(ValueError,match="NOT_ESTIMABLE"):estimator_inputs(records,cells)
    for name in ("src.eval.synthetic_analysis","src.eval.answer_judge_v2","src.generation.generate","src.retrieval.bm25"):
        assert name not in sys.modules


@pytest.mark.parametrize("mutation",["observed","condition","factor","cell_id","duplicate_export","binding"])
def test_export_tampering_rejected(cells,mutation):
    records=export_conditions(cells)
    if mutation=="observed":records[0]["outcome_state"]="OBSERVED_FORGED"
    elif mutation=="condition":records[0]["analysis_projection"]["condition"]="wrong"
    elif mutation=="factor":records[0]["analysis_factors"]["newer_looking"]="incorrect_newer"
    elif mutation=="cell_id":records[0]["cell_id"]="wrong"
    elif mutation=="duplicate_export":records[-1]=copy.deepcopy(records[0])
    else:records[0]["source_construction_sha256"]="0"*64
    with pytest.raises(ValueError):validate_export(records,cells)


def test_output_paths_and_no_overwrite(cells,tmp_path,monkeypatch):
    import src.eval.rq3_analysis_export as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    records=export_conditions(cells)
    path=tmp_path/"audits/g2_i4_v1/export.jsonl"
    write_export(records,cells,output=path)
    assert [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]==records
    with pytest.raises(FileExistsError):write_export(records,cells,output=path)
    for p in (tmp_path/"data/export.jsonl",tmp_path/"audits/g2_i3_v1/export.jsonl",
              tmp_path/"audits/g2_i4_v1/../../../escape.jsonl"):
        with pytest.raises(ValueError):write_export(records,cells,output=p)
        assert not p.exists()


@pytest.mark.parametrize("operation",["retrieval","generation","attack","model_import","network","process","judge","statistics"])
def test_no_execution_operations(operation):
    guard=sys._chronoguard_g2_i4_boundary
    with pytest.raises(ExecutionBlocked):guard.probe(operation)
    assert guard.report()["profile_active"]
