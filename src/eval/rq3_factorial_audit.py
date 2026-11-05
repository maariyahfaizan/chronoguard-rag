"""Opt-in synthetic factorial audit writer; no retrieval or model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES
from src.attacks.matched_controls import canonical
from src.attacks.rq3_factorial import audit_factorial, factorial
from src.eval.offline_input_audit import ROOT, backend_inventory, sha, verify_prerequisites

P1_A2_SHA = "e7dac3f5731efa6f95a70e83cdb84ce183f39105f745b62586af4d6f3b8ef02e"


def prerequisites():
    root = ROOT / "audits/p1_a2_v1"
    if sha(root / "sha256.json") != P1_A2_SHA:
        raise ValueError("P1-A2 checksum manifest changed")
    for name, h in json.loads((root / "sha256.json").read_text()).items():
        if sha(root / name) != h:
            raise ValueError("P1-A2 output changed")
    for name, h in json.loads((root / "source_inventory.json").read_text()).items():
        if sha(ROOT / name) != h:
            raise ValueError("P1-A2 source changed")
    return {"p1_a2_checksum_manifest": P1_A2_SHA, **verify_prerequisites()}


def reports():
    cells, audits = [], []
    for example in SYNTHETIC_EXAMPLES:
        case = factorial(example)
        cells.extend(case)
        audits.append(audit_factorial(case, example))
    return cells, audits


def write_reports(output):
    integrity = prerequisites()
    cells, audits = reports()
    sources = ["src/attacks/rq3_factorial.py", "src/eval/rq3_factorial_audit.py",
               "tests/test_rq3_factorial.py", "docs/p1_b1_rq3_factorial.md",
               "src/generation/generate.py", "src/eval/offline_input_audit.py",
               "src/eval/matched_control_audit.py", "src/attacks/freshness_smoke.py",
               "configs/model_revisions.yaml", "configs/streamingqa_eval_config.yaml"]
    files = {"cells.jsonl": "".join(canonical(c) + "\n" for c in cells),
             "audits.jsonl": "".join(canonical(a) + "\n" for a in audits),
             "tokenizer_inventory.json": canonical(backend_inventory()) + "\n",
             "integrity.json": canonical(integrity) + "\n",
             "source_inventory.json": canonical({p: sha(ROOT / p) for p in sources}) + "\n",
             "summary.json": canonical({"status": "PARTIAL_TOKEN_LEVEL_VERIFICATION_OUTSTANDING",
                 "synthetic_cases": len(audits), "cells": len(cells),
                 "all_claims_complete_in_assembled_prompts": all(a["all_claims_complete"] for a in audits),
                 "invariant_violations": sum(len(c["violations"]) for a in audits for c in a["cells"]),
                 "token_level_balancing": "UNVERIFIED", "inference_executed": False,
                 "retrieval_executed": False, "scientific_approvals": "NONE"}) + "\n"}
    files["sha256.json"] = canonical({p: hashlib.sha256(v.encode()).hexdigest() for p, v in files.items()}) + "\n"
    output = Path(output)
    for name, value in files.items():
        if (output / name).exists() and (output / name).read_bytes() != value.encode():
            raise ValueError("existing audit differs: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output / name).write_bytes(value.encode())
    return {"files": sorted(files), "cells": len(cells), "status": "PARTIAL"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Synthetic RQ3 construction audit; no inference")
    parser.add_argument("--output", required=True)
    print(json.dumps(write_reports(parser.parse_args().output), sort_keys=True))
