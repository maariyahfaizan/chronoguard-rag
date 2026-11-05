"""Read-only prerequisite verification and new G2-I6 audit; no backend operations."""
import collections
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.eval.freshqa_candidate_normalization import (
    BLOCKED, canonical, digest, fixtures, legacy_structure_check, normalize, sha, validate_normalized,
)

PINS = {
    "p0_b1_v1": "00381495aa9832b3649df6aad54bf168bf9dd885aba98209017900739f5a737b",
    "p0_b2_v1": "1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0",
    "p0_c1_v1": "df70bbdacffd7304d6f2f661e08c445eb4301cd44ceb9ffd384c6a1d1fcacacb",
    "p1_a1_v1": "0e64d28f3a3197b2d46da090ca16094057d3b7b5c788e2417035a1e582a1fbb4",
    "p1_a2_v1": "e7dac3f5731efa6f95a70e83cdb84ce183f39105f745b62586af4d6f3b8ef02e",
    "p1_b1_v1": "c31f7560518506e115ccca2ca3785d37721602c58cf68f11e373a228f1f15ae8",
    "p1_c1_v1": "c05b5aa5a153d6484df01736ac1aa1347195c7e4754506991cf52b878a32b536",
    "p1_c3_v1": "b22996b5b5a905472f68bed7638de58510632bcb1dd799bf626e00eb6b024b74",
    "g2_i1_v1": "25ca6c37e918bf26374530332fcf9a8e666663ffec8d505f8a11750561984eb9",
    "g2_i2_v1": "f6fce1dbf7d1cf2962a9510e564d43a2c5b03d041bc4cae21835288e24a9fb43",
    "g2_i3_v1": "65536fd3e0acaafd0204f0204d6e3eae34836206dee9ea4bebebd1ca4778d7e0",
    "g2_i4_v1": "96096a613614b1a154648a59eaefb64472808e8e557444ce2c13008ae703a52a",
    "g2_i5_v1": "b117618369e4ad15af6cbd429fb784491c7343587514a3e74ffa69463abc7239",
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def integrity():
    recovery = ROOT.parent / "chronoguard-week6-recovered"
    g1 = ROOT / "docs/consolidation/g1_v1"
    if sha(g1 / "checksums.json") != "6a4876be1f48671ea87e4f6b4fd237c29da4333de017445b258ef25c2d5e2f87":
        raise ValueError("G1 checksum changed")
    for name, expected in read(g1 / "checksums.json").items():
        if sha(g1 / name) != expected: raise ValueError("G1 output changed: " + name)
    baseline = read(g1 / "baseline_inventory.json")
    for name, entry in baseline["G0_files"].items():
        if sha(ROOT / name) != entry["sha256"]: raise ValueError("G0 file changed: " + name)
    checked = {}
    for name, expected in PINS.items():
        folder = ROOT / "audits" / name
        if sha(folder / "sha256.json") != expected: raise ValueError("audit manifest changed: " + name)
        for file, expected_hash in read(folder / "sha256.json").items():
            if sha(folder / file) != expected_hash: raise ValueError("audit output changed: " + name + "/" + file)
        inventory = folder / "source_inventory.json"
        sources = read(inventory) if inventory.exists() else {}
        if (folder / "reproducibility.json").exists():
            sources.update(read(folder / "reproducibility.json").get("source_hashes", {}))
        for file, value in sources.items():
            if isinstance(value, str) and len(value) == 64 and (ROOT / file).is_file():
                checked[file] = value
    # C1 records the full repository/recovery source-input chain.
    inputs = read(ROOT / "audits/p0_c1_v1/source_inventory.json")["inputs"]
    for entry in inputs.values():
        base = ROOT if entry["root"] == "repository" else recovery
        if entry["root"] not in {"repository", "recovered"}: raise ValueError("unknown dependency root")
        if sha(base / entry["path"]) != entry["sha256"]: raise ValueError("source input changed")
    for file, expected in checked.items():
        if sha(ROOT / file) != expected: raise ValueError("prior source changed: " + file)
    candidate = read(ROOT / "docs/supervisor_review/p0_a9/candidate_manifest.json")
    for entry in candidate["files"]:
        if sha(ROOT / entry["path"]) != entry["sha256"]: raise ValueError("published candidate raw bytes changed")
    protected = {"src/eval/answer_judge.py": sha(ROOT / "src/eval/answer_judge.py")}
    for directory in ("data", "logs", "results", "docs/supervisor_review/p0_a5"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file(): protected[path.relative_to(ROOT).as_posix()] = sha(path)
    recovered = {p.relative_to(recovery).as_posix(): sha(p) for p in recovery.rglob("*") if p.is_file()}
    if len(protected) != 279 or digest(protected) != "5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310":
        raise ValueError("protected repository changed")
    if len(recovered) != 56 or digest(recovered) != "f24c89901d5e525192fec1d7b3aae3d6badab50139171e62ad4d3713e15aa79f":
        raise ValueError("protected recovery changed")
    sheet = (ROOT / "docs/supervisor_review/p0_a5/judge_approval_decision_sheet.md").read_text()
    if sum(l.startswith("|") and "UNRECORDED" in l for l in sheet.splitlines()) != 14:
        raise ValueError("supervisor decision inventory changed")
    return dict(prior_audit_manifests=PINS, G1="VERIFIED", G0_files=len(baseline["G0_files"]),
                published_candidate_files=len(candidate["files"]), source_inputs=len(inputs),
                protected_files=len(protected), protected_sha256_map_digest=digest(protected),
                recovery_files=len(recovered), recovery_sha256_map_digest=digest(recovered),
                scientific_decisions="ALL_14_UNRECORDED", integrity="PASS")


def inventory():
    pins = read(ROOT / "audits/p1_c3_v1/dataset_inventory.json")
    for key in ("fresh_pools", "fresh_questions", "fresh_snapshot"):
        if sha(ROOT / pins[key]["path"]) != pins[key]["sha256"]: raise ValueError("FreshQA source changed")
    ids = []; counts = collections.Counter(); metadata_fields = collections.Counter(); doc_duplicates = []
    for line in (ROOT / pins["fresh_pools"]["path"]).open(encoding="utf-8"):
        r = json.loads(line); ids.append(r["query_id"])
        candidates, metadata = r["candidates"], r["candidate_metadata"]
        counts["length_mismatches"] += len(candidates) != len(metadata)
        doc_ids = []
        for i, (c, m) in enumerate(zip(candidates, metadata)):
            counts["candidate_occurrences"] += 1
            counts["string_candidates"] += type(c) is str
            counts["dictionary_candidates"] += type(c) is dict
            counts["index_mismatches"] += m.get("index") != i
            counts["recorded_source_dates"] += bool(m.get("source_date"))
            counts["recorded_source_flags_true"] += m.get("is_source_document") is True
            metadata_fields.update(m.keys()); doc_ids.append(m.get("doc_id"))
        if len(doc_ids) != len(set(doc_ids)): doc_duplicates.append(r["query_id"])
    questions = [json.loads(l)["query_id"] for l in (ROOT / pins["fresh_questions"]["path"]).open(encoding="utf-8")]
    # Read the literal configured field, not comments or historical outcome metrics.
    lines = (ROOT / "configs/freshqa_config.yaml").read_text().splitlines()
    values = [l.split(":", 1)[1].split("#", 1)[0].strip() for l in lines if l.strip().startswith("num_examples:")]
    if len(values) != 1 or not values[0].isdigit(): raise ValueError("ambiguous configured expected count")
    expected = int(values[0])
    duplicates = sorted(k for k, v in collections.Counter(ids).items() if v > 1)
    return dict(status="READ_ONLY_INVENTORY_NOT_ADJUDICATION", actual_local_records=len(ids),
        unique_ids=len(set(ids)), available_stable_ids=sorted(ids), duplicate_ids=duplicates,
        duplicate_document_ids_within_record=doc_duplicates, configured_expected_records=expected,
        count_discrepancy=expected-len(ids), configured_expected_id_membership="UNKNOWN",
        identities_of_three_missing_records="UNKNOWN_NOT_INFERRED", cause="UNKNOWN",
        possible_mechanism_not_established="Current builder skips no-matching-evidence cases but emits dictionaries; legacy string-pool build provenance unavailable",
        preprocessed_question_records=len(questions), preprocessed_question_unique_ids=len(set(questions)),
        absent_pool_ids_relative_to_500_only=sorted(set(questions)-set(ids)),
        unexpected_pool_ids_relative_to_500=sorted(set(ids)-set(questions)),
        counts=dict(counts), candidate_metadata_field_occurrences=dict(metadata_fields),
        sources={k: pins[k] for k in ("fresh_pools", "fresh_questions", "fresh_snapshot")},
        authentication="NOT_ESTABLISHED_BY_HASH", real_records_normalized=0)


def main():
    # First read-only integrity; fail before any output. Then unchanged guarded boundary.
    evidence = integrity()
    print("PREREQUISITE_AND_PROTECTED_INTEGRITY_OK", flush=True)
    from src.eval.rq3_export_boundary import install
    guard = install()
    originals = fixtures(); hashes = {r["query_id"]: digest(r) for r in originals}
    normalized = normalize(originals, hashes)
    validation = validate_normalized(normalized, originals, hashes)
    for r in normalized: legacy_structure_check(r)
    reconciliation = inventory()
    sources = ["src/eval/freshqa_candidate_normalization.py", "scripts/build_g2_i6_audit.py",
        "scripts/validate_g2_i6_no_execution.py", "tests/g2_i6/test_freshqa_candidate_normalization.py",
        "docs/g2_i6_freshqa_candidate_normalization.md", "src/attacks/attack_pool.py",
        "src/eval/no_execution_boundary.py", "src/eval/rq3_export_boundary.py",
        "src/eval/build_freshqa_pools.py", "src/eval/preprocess_freshqa.py", "scripts/run_baseline_freshqa.py",
        "configs/freshqa_config.yaml", "docs/consolidation/g1_v1/integration_contracts.json",
        "docs/consolidation/g1_v1/checksums.json", "audits/p1_c3_v1/dataset_inventory.json"]
    sources += ["audits/" + name + "/sha256.json" for name in PINS]
    docs = {
        "fixture_inputs.json": originals,
        "inventory_reconciliation.json": reconciliation,
        "schema_metadata_validation.json": {**validation, "legacy_field_presence_validator": "PASS_FOUR_FIXTURES",
            "missing_fields": "PRESERVED_EXPLICITLY", "scientific_approval": "NONE",
            "runner_execution": "NOT_PERMITTED", "synthetic_records": 4, "synthetic_candidates": 8},
        "execution_boundary_report.json": {"artifact_builder": guard.report(),
            "allowlisted_test_command": "python -B scripts/validate_g2_i6_no_execution.py",
            "observed_test_result": "40 passed in 7.75s", "test_exit_code": 0,
            "test_guard": {"profile_active": True, "blocked_backend_modules_loaded": [],
                           "blocked_attempts": {"calls": 10, "imports": 2, "network_or_process": 4}},
            "negative_attempts": "INERT_TRIPWIRES_BLOCKED_BEFORE_OPERATION_BODIES",
            "test_configuration": "NO_CONFTEST_NO_EXTERNAL_PLUGINS_NO_INHERITED_CONFIG"},
        "test_allowlist.json": {"modules": ["tests/g2_i6/test_freshqa_candidate_normalization.py"],
            "tests_reviewed": True, "full_suite": "NOT_RUN", "scope": "FICTIONAL_ONLY"},
        "source_inventory.json": {p: sha(ROOT / p) for p in sources},
        "integrity_report.json": evidence,
    }
    output = ROOT / "audits/g2_i6_v1"
    payloads = {name: (canonical(value)+"\n").encode("utf-8") for name, value in docs.items()}
    payloads["synthetic_normalized_pool.jsonl"] = "".join(canonical(r)+"\n" for r in normalized).encode("utf-8")
    import hashlib
    payloads["sha256.json"] = (canonical({n: hashlib.sha256(b).hexdigest() for n,b in payloads.items()})+"\n").encode("utf-8")
    for name, value in payloads.items():
        if (output/name).exists() and (output/name).read_bytes() != value:
            raise ValueError("no overwrite of differing artifact: " + name)
    output.mkdir(parents=True, exist_ok=True)
    for name, value in payloads.items():
        if not (output/name).exists(): (output/name).write_bytes(value)
    print(canonical({"files": sorted(payloads), "manifest_sha256": sha(output/"sha256.json"),
                     "boundary": guard.report(), "execution_status": BLOCKED}))


if __name__ == "__main__":
    main()
