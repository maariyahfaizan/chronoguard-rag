"""Versioned planning report. No model downloads, outcome analysis or execution."""
import hashlib
import json
from pathlib import Path

from src.attacks.matched_controls import canonical
from src.eval.offline_input_audit import ROOT, sha
from src.eval.statistical_audit import verify_prerequisites as earlier_prerequisites
from src.eval.transfer_scope_plan import (
    WEB_SOURCES, dataset_inventory, dataset_roles, gate_report, model_candidates,
    scenario, validate_models, validate_roles,
)


def prerequisites():
    root = ROOT/"audits/p1_c1_v1"
    if sha(root/"sha256.json") != "c05b5aa5a153d6484df01736ac1aa1347195c7e4754506991cf52b878a32b536":
        raise ValueError("P1-C1 checksum mismatch")
    for p,h in json.loads((root/"sha256.json").read_text()).items():
        if sha(root/p) != h:
            raise ValueError("P1-C1 output mismatch")
    for p,h in json.loads((root/"reproducibility.json").read_text())["source_hashes"].items():
        if sha(ROOT/p) != h:
            raise ValueError("P1-C1 source mismatch")
    return {"p1_c1_checksum_manifest":sha(root/"sha256.json"),**earlier_prerequisites()}


def write_reports(output):
    integrity = prerequisites()
    inventory = dataset_inventory()
    models, roles = model_candidates(), dataset_roles()
    validate_models(models)
    validate_roles(roles)
    scenarios = {"arithmetic_fixture":scenario(questions=2,retrieval_conditions=4,attack_families=1,rq3_questions=2),
                 "provisional_300_not_selected":scenario(questions=300,retrieval_conditions=4,attack_families=5,
                                                        negative_controls=2,rq3_questions=300),
                 "three_dataset_illustration_not_allocation":{name:scenario(questions=100,retrieval_conditions=4,
                     attack_families=2,rq3_questions=100) for name in ("StreamingQA","FreshQA","TriviaQA")}}
    sources = ["src/eval/transfer_scope_plan.py","src/eval/transfer_scope_audit.py","tests/test_transfer_scope_plan.py",
               "docs/p1_c3_transfer_scope_plan.md","src/generation/generate.py","configs/model_revisions.yaml",
               "configs/freshqa_config.yaml","configs/baseline_config.yaml","src/eval/preprocess_freshqa.py",
               "src/eval/build_freshqa_pools.py","src/eval/fetch_freshqa_sources.py","scripts/run_baseline.py",
               "scripts/run_baseline_streamingqa.py","scripts/run_baseline_freshqa.py"]
    docs = {"feasibility.json":{"status":"PARTIAL_NOT_APPROVED","models":models,"datasets":roles,
                                "technical_blockers":["FreshQA actual 474 rows versus configured 477",
                                    "FreshQA string candidates versus current dictionary runner schema",
                                    "transfer model revisions/cache/runtime/GPU fit unverified",
                                    "static-control authoritative identity mapping missing"],
                                "GPU_availability":"UNKNOWN","strong_scope_sufficiency":"NOT_ESTABLISHED"},
            "dataset_inventory.json":inventory,"resource_scenarios.json":scenarios,"execution_gates.json":gate_report(),
            "external_sources.json":{"consulted_date":"2026-11-04","sources":WEB_SOURCES,
                                     "exact_model_revisions":"UNKNOWN; mutable model-card descriptions only"},
            "integrity.json":integrity,
            "source_inventory.json":{p:sha(ROOT/p) for p in sources},
            "validation.json":{"model_family_check":"PASS","dataset_role_check":"PASS",
                               "runtime_measurements":"NONE","approvals":"NONE; ALL_14_UNRECORDED"}}
    files = {p:canonical(v)+"\n" for p,v in docs.items()}
    files["sha256.json"] = canonical({p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()})+"\n"
    output = Path(output)
    for p,v in files.items():
        if (output/p).exists() and (output/p).read_bytes()!=v.encode():
            raise ValueError("existing report differs: "+p)
    output.mkdir(parents=True,exist_ok=True)
    for p,v in files.items():
        (output/p).write_bytes(v.encode())
    return {"status":"PARTIAL","files":sorted(files)}


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description="Planning only; no model execution")
    parser.add_argument("--output",required=True)
    print(json.dumps(write_reports(parser.parse_args().output),sort_keys=True))
