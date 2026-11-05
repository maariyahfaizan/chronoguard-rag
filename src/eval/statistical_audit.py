"""Reproducible fictional analysis only; no real-outcome input option."""
import copy
import hashlib
import json
from pathlib import Path

from src.eval.offline_input_audit import ROOT, sha
from src.eval.rq3_factorial_audit import prerequisites as earlier_prerequisites
from src.eval.synthetic_analysis import (
    SCHEMA, POPULATIONS, CELL_LEVELS, cell_name, factorial_effects, holm,
    paired_difference, planning_inputs, rate, validate,
)
from src.attacks.matched_controls import canonical


def fictional_data():
    frame = [{"question_id": f"synthetic-stat-{i:03d}", "eligibility": "ELIGIBLE", "clean": "CORRECT"}
             for i in range(4)]
    rows = []
    # Hand-authored paired outcomes: differences +1,+1,0,-1 -> +0.25.
    for q, (neutral, fresh) in zip(frame, [(0, 1), (0, 1), (1, 1), (1, 0)]):
        for c, y in (("neutral", neutral), ("freshness", fresh)):
            rows.append({"question_id": q["question_id"], "family": "synthetic_header", "condition": c,
                "construction": "SUCCEEDED", "retrieval": "YES", "generator": "YES",
                "outcome": "POISON_ADOPTED" if y else "CORRECT"})
        # Fictional deterministic date-only response: NOT model judgments.
        for levels in CELL_LEVELS:
            rows.append({"question_id": q["question_id"], "family": "rq3", "condition": cell_name(levels),
                "construction": "SUCCEEDED", "retrieval": "NOT_APPLICABLE", "generator": "YES",
                "outcome": "POISON_ADOPTED" if levels[0] == 1 else "CORRECT"})
    return frame, rows


def analyze_synthetic():
    frame, rows = fictional_data()
    validate(frame, rows)
    paired = paired_difference(frame, rows, families=["synthetic_header"])
    rq3 = factorial_effects(frame, rows)
    family = ["freshness"] + ["rq3:" + k for k in rq3["effects"]]
    p = {"freshness": paired["p_value_proposed_sign_flip"], **{
        "rq3:" + k: v["p_value_proposed_sign_flip"] for k, v in rq3["effects"].items()}}
    missing = copy.deepcopy(rows)
    missing[0]["outcome"] = "NEEDS_REVIEW"
    missing[1]["retrieval"] = "UNKNOWN"
    missing[1]["generator"] = "UNVERIFIED"
    return {"scope": "FICTIONAL_CALCULATIONS_NOT_SCIENTIFIC_RESULTS", "rates": {
        pop: rate(frame, rows, population=pop, family="synthetic_header", condition="freshness") for pop in POPULATIONS},
        "paired": paired, "rq3": rq3, "proposed_confirmatory_family": family,
        "holm_proposed": holm(p, family=family), "planning": planning_inputs(),
        "missingness_examples": {"rate": rate(frame, missing, population="eligible", family="synthetic_header", condition="neutral"),
            "unknown_exposure": rate(frame, missing, population="retrieved", family="synthetic_header", condition="freshness"),
            "paired": paired_difference(frame, missing, families=["synthetic_header"])}}


def verify_prerequisites():
    root = ROOT / "audits/p1_b1_v1"
    if sha(root / "sha256.json") != "c31f7560518506e115ccca2ca3785d37721602c58cf68f11e373a228f1f15ae8":
        raise ValueError("P1-B1 checksum inventory mismatch")
    for name, h in json.loads((root / "sha256.json").read_text()).items():
        if sha(root / name) != h:
            raise ValueError("P1-B1 audit output mismatch")
    for name, h in json.loads((root / "source_inventory.json").read_text()).items():
        if sha(ROOT / name) != h:
            raise ValueError("P1-B1 source mismatch")
    return {"p1_b1_checksum_manifest": sha(root / "sha256.json"), **earlier_prerequisites()}


def write_reports(output):
    integrity = verify_prerequisites()
    frame, rows = fictional_data()
    result = analyze_synthetic()
    names = ["src/eval/synthetic_analysis.py", "src/eval/statistical_audit.py", "tests/test_synthetic_analysis.py",
             "docs/p1_c1_analysis_plan.md", "src/eval/metrics.py", "src/eval/answer_judge_v2.py",
             "src/attacks/rq3_factorial.py"]
    documents = {"analysis_schema.json": SCHEMA, "synthetic_inputs.json": {"frame": frame, "rows": rows},
                 "synthetic_results.json": result, "validation_missingness.json": {
                     "input_validation": "PASS", "scope": "SYNTHETIC_ONLY", "frame_questions": len(frame),
                     "rows": len(rows), "missingness_scenarios": result["missingness_examples"],
                     "approvals": "NONE; ALL_14_DECISIONS_UNRECORDED"},
                 "integrity.json": integrity,
                 "reproducibility.json": {"seed": 20261104, "bootstrap_draws": 2000,
                     "source_hashes": {name: sha(ROOT / name) for name in names}}}
    files = {n: canonical(v) + "\n" for n, v in documents.items()}
    files["estimand_specification.md"] = (ROOT / "docs/p1_c1_analysis_plan.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    files["sha256.json"] = canonical({n: hashlib.sha256(v.encode()).hexdigest() for n,v in files.items()}) + "\n"
    output = Path(output)
    for name, value in files.items():
        if (output / name).exists() and (output / name).read_bytes() != value.encode():
            raise ValueError("existing output differs: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output / name).write_bytes(value.encode())
    return {"scope": "SYNTHETIC_ONLY", "files": sorted(files)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fictional statistical calculations; no real outcome input")
    parser.add_argument("--output", required=True)
    print(json.dumps(write_reports(parser.parse_args().output), sort_keys=True))
