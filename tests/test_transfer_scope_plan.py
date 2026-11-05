import copy

import pytest

from src.eval.transfer_scope_plan import (
    dataset_roles, gate_report, model_candidates, scenario, validate_models, validate_roles, weight_memory,
)


def test_dataset_roles_no_static_temporal_promotion():
    roles=dataset_roles()
    assert validate_roles(roles)
    roles[-1]["role"]="primary_temporal"
    with pytest.raises(ValueError):
        validate_roles(roles)


@pytest.mark.parametrize("provenance",["AUTHENTICATED","APPROVED",None])
def test_missing_or_unsupported_provenance(provenance):
    roles=dataset_roles()
    roles[0]["provenance"]=provenance
    with pytest.raises(ValueError):
        validate_roles(roles)


def test_explicit_unknown_provenance_not_approval():
    roles=dataset_roles()
    roles[0]["provenance"]="UNKNOWN"
    assert validate_roles(roles)
    roles[0]["confirmatory_approved"]=True
    with pytest.raises(ValueError):
        validate_roles(roles)


@pytest.mark.parametrize("change",["family","revision","measurement"])
def test_no_fabricated_revision_benchmark_or_same_family(change):
    models=model_candidates()
    assert validate_models(models)
    if change=="family":
        models[0]["family"]="Mistral"
    elif change=="revision":
        models[0]["revision"]="invented"
    else:
        models[0]["seconds_per_answer"]=1
    with pytest.raises(ValueError):
        validate_models(models)


def test_resource_arithmetic_and_clean_reuse():
    s=scenario(questions=2,retrieval_conditions=4,attack_families=1,rq3_questions=2)
    assert s["unique_retrieval_work_units"]==24
    assert s["end_to_end_generations"]==48
    assert s["rq3_direct_generations"]==32
    assert s["total_generations"]==80
    assert s["total_serial_seconds_excluding_setup_and_evaluation"]=="UNKNOWN"
    extra=scenario(questions=2,retrieval_conditions=4,attack_families=2,rq3_questions=2)
    assert extra["unique_retrieval_work_units"]==40  # no extra clean arm per family
    assert extra["rq3_direct_generations"]==32  # no family multiplier


def test_shared_retrieval_across_generators_and_generation_repetitions():
    a=scenario(questions=10,retrieval_conditions=4,attack_families=2,generators=1)
    b=scenario(questions=10,retrieval_conditions=4,attack_families=2,generators=2,generation_repetitions=3)
    assert a["unique_retrieval_work_units"]==b["unique_retrieval_work_units"]
    assert b["total_generations"]==6*a["total_generations"]


def test_known_times_are_hypothetical_inputs_not_benchmarks():
    s=scenario(questions=2,retrieval_conditions=4,attack_families=1,rq3_questions=2,
               seconds_per_generation=1,seconds_per_retrieval=2,seconds_per_judge=3)
    assert s["total_serial_seconds_excluding_setup_and_evaluation"]==80+24*2+80*3
    assert s["status"]=="HYPOTHETICAL_NOT_APPROVED"


def test_missing_gates_and_no_approval():
    report=gate_report()
    assert report["execution"]=="BLOCKED"
    assert len(report["missing_records"])==7
    with pytest.raises(ValueError):
        gate_report({"explicit_week6_authorization":"APPROVED"})


@pytest.mark.parametrize("kwargs",[{"questions":True},{"rq3_questions":3},{"generators":0},
                                    {"seconds_per_generation":-1},{"attack_families":-1}])
def test_invalid_scenarios(kwargs):
    inputs=dict(questions=2,retrieval_conditions=4,attack_families=1)
    inputs.update(kwargs)
    with pytest.raises(ValueError):
        scenario(**inputs)


def test_weight_only_memory_and_unknown_overhead():
    assert weight_memory(8e9,16)==pytest.approx(14.90116119)
    assert model_candidates()[0]["peak_VRAM_GiB"]=="UNKNOWN"


def test_explicit_retrieval_and_answer_reuse_groups():
    s=scenario(questions=2,retrieval_conditions=4,attack_families=1,
        retrieval_variant_groups=["same","same","other"],generation_variant_groups=["same","same","other"])
    assert s["unique_retrieval_work_units"]==16
    assert s["end_to_end_generations"]==32
    with pytest.raises(ValueError):
        scenario(questions=2,retrieval_conditions=4,attack_families=1,
            retrieval_variant_groups=["a","b","c"],generation_variant_groups=["same","same","c"])


def test_deterministic_artifacts_and_refuse_overwrite(tmp_path,monkeypatch):
    import src.eval.transfer_scope_audit as writer
    monkeypatch.setattr(writer,"prerequisites",lambda:{"synthetic_test":True})
    monkeypatch.setattr(writer,"dataset_inventory",lambda:{"synthetic_test":True})
    writer.write_reports(tmp_path/"a")
    writer.write_reports(tmp_path/"b")
    for p in (tmp_path/"a").iterdir():
        assert p.read_bytes()==(tmp_path/"b"/p.name).read_bytes()
    (tmp_path/"a"/"feasibility.json").write_text("tampered")
    with pytest.raises(ValueError):
        writer.write_reports(tmp_path/"a")
