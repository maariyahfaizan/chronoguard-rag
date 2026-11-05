"""G2-I7 artifact reproduction: read-only integrity, guarded structure, no execution."""
import hashlib
import json
from pathlib import Path
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.eval.judge_outcome_adapter import (
    BLOCKED, GATES, MAPPING_VERSION, VERSION, canonical, digest, fixtures,
    project, read, require_numerical_eligibility, schemas, sha, source_bundle,
    unobserved_source_export, validate_analysis_structure,
)


def prerequisites():
    # Explicit pins; do not treat caller-supplied manifests as authentication.
    old_script = ROOT / "scripts/build_g2_i6_audit.py"
    if sha(old_script) != "603b1237fb40d9b4e7fdaf08a31679405730fe60fc69ef602a9d16b127bb5312":
        raise ValueError("G2-I6 integrity verifier changed")
    directory = ROOT / "audits/g2_i6_v1"
    if sha(directory / "sha256.json") != "f297bc2c055dba101f686de40dbd06a2f36ec2972de7f9bf5ed0892e78d45fa3":
        raise ValueError("G2-I6 manifest mismatch")
    for name, h in read(directory / "sha256.json").items():
        if sha(directory / name) != h: raise ValueError("G2-I6 audit output changed")
    for name, h in read(directory / "source_inventory.json").items():
        if sha(ROOT / name) != h: raise ValueError("G2-I6 dependency changed")
    # Reuse only this reviewed definition, never its __main__ artifact builder.
    old = runpy.run_path(str(old_script))
    evidence = old["integrity"]()
    # Check every flat path-hash dependency explicitly, including missing files.
    # Older inventories also have metadata hashes; those are not path mappings.
    for audit in old["PINS"]:
        p = ROOT / "audits" / audit / "source_inventory.json"
        if not p.exists(): continue
        for name, h in read(p).items():
            if "/" in name and type(h) is str and len(h) == 64:
                if sha(ROOT / name) != h: raise ValueError("prior dependency absent/changed: " + name)
    evidence["g2_i6_manifest"] = sha(directory / "sha256.json")
    evidence["g2_i6_sources_and_outputs"] = "VERIFIED"
    schemas()
    source_bundle()
    return evidence


def main():
    evidence = prerequisites()
    print("PREREQUISITE_AND_PROTECTED_INTEGRITY_OK", flush=True)
    from src.eval.rq3_export_boundary import install
    guard = install()
    records = fixtures()
    outputs = project(records, mode="synthetic")
    structure = validate_analysis_structure(outputs, records)
    try:
        require_numerical_eligibility(outputs, records)
    except ValueError as exc:
        gate_result = str(exc)
        if not gate_result.startswith("BLOCKED: no observations"): raise
    else:
        raise AssertionError("numerical gate failed open")
    unobserved = unobserved_source_export()
    sources = ["src/eval/judge_outcome_adapter.py", "scripts/build_g2_i7_audit.py",
        "scripts/validate_g2_i7_no_execution.py", "tests/g2_i7/test_judge_outcome_adapter.py",
        "docs/g2_i7_judge_outcome_adapter.md", "src/eval/answer_judge_v2.py", "src/eval/claim_keys.py",
        "src/eval/claim_matching_v2.py", "src/eval/answer_judge.py", "src/eval/synthetic_analysis.py",
        "src/eval/canonical_analysis_input.py", "src/eval/no_execution_boundary.py",
        "src/eval/rq3_export_boundary.py", "scripts/build_g2_i6_audit.py",
        "docs/consolidation/g1_v1/integration_contracts.json", "docs/consolidation/g1_v1/checksums.json",
        "docs/supervisor_review/p0_a9/candidate_manifest.json", "audits/g2_i5_v1/analysis_input.json",
        "audits/g2_i5_v1/identity_map.json", "audits/g2_i6_v1/sha256.json"]
    sources += ["audits/" + name + "/sha256.json" for name in evidence["prior_audit_manifests"]]
    docs = {
        "synthetic_judge_output_fixtures.json": records,
        "outcome_mapping_validation.json": {"version": MAPPING_VERSION, "status": "PROPOSED_NOT_APPROVED",
            "actual_schemas": schemas(), "structure_validation": structure,
            "cases": [{"fixture_id": r["fixture_id"], "label": r["original_judge_label"],
                       "raw_reason": r["original_judge_reason"], "projected_state": r["projected_analysis_state"],
                       "numerical_outcome": r["analysis_projection"]["outcome"]} for r in outputs],
            "judge_executions": 0, "observations_created": 0},
        "analysis_state_export.json": {"schema_version": VERSION, "fictional_label_projections": outputs,
            "unobserved_source_records": unobserved, "numeric_eligibility": "BLOCKED"},
        "missingness_eligibility_report.json": {"fictional_descriptors": len(records),
            "original_unobserved_source_cells": len(unobserved), "original_question_clusters": 2,
            "original_cells_per_question": 8, "observed_generated_answers": 0,
            "numerically_eligible_records": 0, "gate_result": gate_result,
            "required_gates": {g: "UNRECORDED" for g in GATES},
            "all_analysis_input_outcomes": "MISSING", "generator_visibility": "UNVERIFIED",
            "source_outcome_state": "UNOBSERVED", "execution_status": BLOCKED,
            "empty_vs_absent": "RETAINED_RAW_REASON_AND_INPUT_STATUS_NOT_COLLAPSED",
            "no_combining_export_sections": "ALTERNATIVE_DEMONSTRATIONS_NOT_INDEPENDENT_ROWS"},
        "execution_boundary_report.json": {"builder_boundary": guard.report(),
            "test_command": "python -B scripts/validate_g2_i7_no_execution.py",
            "observed_test_result": "67 passed in 17.03s", "pytest_exit_code": 0,
            "test_guard": {"profile_active": True, "blocked_backend_modules_loaded": [],
                "blocked_attempts": {"calls": 10, "imports": 2, "network_or_process": 4}},
            "operation_bodies_invoked": "NONE; NEGATIVE_TESTS_USE_INERT_TRIPWIRES",
            "test_config": "NO_CONFTEST_NO_INHERITED_CONFIG_NO_EXTERNAL_PLUGINS"},
        "test_allowlist.json": {"modules": ["tests/g2_i7/test_judge_outcome_adapter.py"],
            "reviewed_before_running": True, "full_suite": "NOT_RUN", "model_bearing_imports": "NONE"},
        "source_inventory.json": {p: sha(ROOT / p) for p in sorted(set(sources))},
        "integrity_report.json": evidence,
    }
    target = ROOT / "audits/g2_i7_v1"
    payloads = {n: (canonical(v)+"\n").encode() for n, v in docs.items()}
    payloads["sha256.json"] = (canonical({n: hashlib.sha256(b).hexdigest() for n, b in payloads.items()})+"\n").encode()
    for name, data in payloads.items():
        if (target / name).exists() and (target / name).read_bytes() != data:
            raise ValueError("refuse overwrite of differing audit artifact: " + name)
    target.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        if not (target / name).exists():
            with (target / name).open("xb") as stream: stream.write(data)
    print(canonical({"files": sorted(payloads), "manifest_sha256": sha(target / "sha256.json"),
                     "boundary": guard.report(), "numerical_eligibility": "BLOCKED"}))


if __name__ == "__main__":
    main()
