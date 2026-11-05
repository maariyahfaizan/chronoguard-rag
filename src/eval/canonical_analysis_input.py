"""Explicit reversible aliases for pinned fictional, unobserved RQ3 inputs.

Canonical identities never change. Only the legacy validator projection uses
the compatibility alias. No estimator module is imported or invoked.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE_ROOT=ROOT
VERSION="chronoguard.canonical-analysis-input/v1"
MAP_VERSION="chronoguard.synthetic-rq3-identity-map/v1"


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs():
    pins={"docs/consolidation/g1_v1":("checksums.json","6a4876be1f48671ea87e4f6b4fd237c29da4333de017445b258ef25c2d5e2f87"),
          "audits/g2_i4_v1":("sha256.json","96096a613614b1a154648a59eaefb64472808e8e557444ce2c13008ae703a52a"),
          "audits/p1_b1_v1":("sha256.json","c31f7560518506e115ccca2ca3785d37721602c58cf68f11e373a228f1f15ae8"),
          "audits/p1_c1_v1":("sha256.json","c05b5aa5a153d6484df01736ac1aa1347195c7e4754506991cf52b878a32b536")}
    for relative,(manifest,pin) in pins.items():
        root=SOURCE_ROOT/relative
        if sha(root/manifest)!=pin:raise ValueError("prerequisite manifest mismatch")
        for name,h in json.loads((root/manifest).read_text()).items():
            if sha(root/name)!=h:raise ValueError("prerequisite output changed")
        if (root/"source_inventory.json").exists():
            inv=json.loads((root/"source_inventory.json").read_text())
        elif (root/"reproducibility.json").exists():
            inv=json.loads((root/"reproducibility.json").read_text())["source_hashes"]
        else:inv={}
        for name,h in inv.items():
            if sha(SOURCE_ROOT/name)!=h:raise ValueError("prerequisite source changed")
    return pins


def registered_exports():
    verify_inputs()
    return [json.loads(line) for line in (SOURCE_ROOT/"audits/g2_i4_v1/condition_export.jsonl").read_text(encoding="utf-8").splitlines()]


def _validate_registered(records):
    trusted=registered_exports()
    if type(records) is not list or len(records)!=len(trusted) or any(type(r) is not dict for r in records):
        raise ValueError("complete registered synthetic export required")
    ids=[r.get("cell_id") for r in records]
    if any(type(x) is not str for x in ids) or len(set(ids))!=len(ids):raise ValueError("duplicate/missing cell identity")
    index={r["cell_id"]:r for r in trusted}
    if set(ids)!=set(index) or any(canonical(r)!=canonical(index[r["cell_id"]]) for r in records):
        raise ValueError("real, rehashed, altered or unregistered export")
    groups={}
    for r in records:
        if not r["question_id"].startswith("synthetic-smoke-"):raise ValueError("synthetic canonical namespace required")
        groups.setdefault(r["question_id"],[]).append(r)
    if len(groups)!=2 or any(len(v)!=8 or len({r["analysis_condition"] for r in v})!=8 for v in groups.values()):
        raise ValueError("complete unique eight-cell question blocks required")
    return groups


def _alias(canonical_id,construction_block_hash):
    return "synthetic-stat-g2-i5-"+digest({"mapping_version":MAP_VERSION,"canonical_id":canonical_id,
                                         "construction_block_sha256":construction_block_hash})


def _expected_map(groups):
    entries=[]
    for qid,rows in sorted(groups.items()):
        cells=[{"canonical_question_id":qid,"cell_id":r["cell_id"],"analysis_condition":r["analysis_condition"],
            "source_construction_sha256":r["source_construction_sha256"],
            "source_export_record_sha256":digest(r),"context_sha256":r["context_sha256"],
            "prompt_sha256":r["prompt_sha256"]} for r in sorted(rows,key=lambda r:r["cell_id"])]
        block_hash=digest(cells)
        entries.append({"canonical_question_id":qid,"analysis_question_id":_alias(qid,block_hash),
            "source_construction_block_sha256":block_hash,"cells":cells,
            "scope":"SYNTHETIC_ONLY","identity_basis":"explicit registered source binding; no inferred equivalence"})
    if len({e["analysis_question_id"] for e in entries})!=len(entries):raise ValueError("analysis namespace collision")
    return {"schema_version":MAP_VERSION,"scope":"SYNTHETIC_ONLY","entries":entries,
            "source_export_path":"audits/g2_i4_v1/condition_export.jsonl",
            "source_export_sha256":sha(SOURCE_ROOT/"audits/g2_i4_v1/condition_export.jsonl"),
            "purpose":"legacy synthetic-fixture namespace compatibility only; not source identity replacement"}


def identity_map(records):
    return _expected_map(_validate_registered(records))


def validate_identity_map(mapping,records):
    groups=_validate_registered(records)
    if type(mapping) is not dict or type(mapping.get("entries")) is not list:raise ValueError("malformed identity map")
    entries=mapping["entries"]
    if any(type(e) is not dict or type(e.get("canonical_question_id")) is not str or type(e.get("analysis_question_id")) is not str for e in entries):
        raise ValueError("missing mapping identities")
    if len({e["canonical_question_id"] for e in entries})!=len(entries):raise ValueError("duplicate canonical identity")
    if len({e["analysis_question_id"] for e in entries})!=len(entries):raise ValueError("analysis alias collision")
    if canonical(mapping)!=canonical(_expected_map(groups)):raise ValueError("map differs from registered provenance or version")
    return True


def lookup_identity(mapping,value,*,direction,records):
    validate_identity_map(mapping,records)
    if direction not in ("canonical_to_analysis","analysis_to_canonical"):raise ValueError("explicit lookup direction required")
    left,right=("canonical_question_id","analysis_question_id") if direction=="canonical_to_analysis" else ("analysis_question_id","canonical_question_id")
    for entry in mapping["entries"]:
        if entry[left]==value:return entry[right]
    raise ValueError("identity not present in explicit reversible map")


def _legacy_validator():
    path=SOURCE_ROOT/"src/eval/synthetic_analysis.py"
    hashes=json.loads((SOURCE_ROOT/"audits/g2_i4_v1/source_inventory.json").read_text())
    if sha(path)!=hashes["src/eval/synthetic_analysis.py"]:raise ValueError("legacy validator source changed")
    tree=ast.parse(path.read_text(encoding="utf-8"));scope={}
    for name in ("SCHEMA","RESOLVED"):
        node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
        scope[name]=ast.literal_eval(node.value)
    validator=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="validate")
    allowed_names={"type","isinstance","set","len","tuple","ValueError"}
    allowed_attributes={"startswith","strip","append","add"}
    for n in ast.walk(validator):
        if isinstance(n,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal)):raise ValueError("unsafe validator dependency")
        if isinstance(n,ast.Call) and not ((isinstance(n.func,ast.Name) and n.func.id in allowed_names)
                or (isinstance(n.func,ast.Attribute) and n.func.attr in allowed_attributes)):
            raise ValueError("unexpected validator call; no estimator dependency allowed")
    exec(compile(ast.Module(body=[validator],type_ignores=[]),str(path),"exec"),scope)
    return scope["validate"]


def _build(records,mapping):
    entries={e["canonical_question_id"]:e for e in mapping["entries"]}
    mapped=[]
    for source in sorted(records,key=lambda r:(r["question_id"],r["analysis_condition"])):
        qid=source["question_id"];alias=entries[qid]["analysis_question_id"]
        result=copy.deepcopy(source)
        result.update({"schema_version":VERSION,"source_export_schema_version":source["schema_version"],
            "canonical_question_id":qid,"analysis_question_id":alias,"identity_mapping_version":MAP_VERSION,
            "identity_mapping_sha256":digest(mapping),"source_condition_export_record_sha256":digest(source),
            "source_analysis_projection":copy.deepcopy(source["analysis_projection"]),
            "legacy_analysis_compatibility":"STRUCTURE_VALIDATED_WITH_EXPLICIT_REVERSIBLE_ALIAS"})
        result["analysis_projection"]["question_id"]=alias
        mapped.append(result)
    frames=[{"canonical_question_id":qid,"analysis_question_id":e["analysis_question_id"],
             "analysis_frame":{"question_id":e["analysis_question_id"],"eligibility":"UNKNOWN","clean":"MISSING"}}
            for qid,e in sorted(entries.items())]
    _legacy_validator()([f["analysis_frame"] for f in frames],[r["analysis_projection"] for r in mapped])
    return {"schema_version":VERSION,"scope":"SYNTHETIC_ONLY","execution_status":"NOT_AUTHORIZED_FOR_EXECUTION",
        "identity_mapping":copy.deepcopy(mapping),"frame_records":frames,"records":mapped,
        "legacy_structure_validation":"PASS_ACTUAL_VALIDATOR_DEFINITION_ONLY",
        "estimator_ingestion":"BLOCKED_UNOBSERVED_UNVERIFIED_UNAPPROVED",
        "numeric_outputs_produced":False}


def build_analysis_input(records,*,mode,mapping=None):
    if mode!="synthetic":raise ValueError("real analysis-input conversion forbidden")
    groups=_validate_registered(records)
    expected=_expected_map(groups)
    if mapping is not None:
        validate_identity_map(mapping,records)
    return _build(records,expected if mapping is None else mapping)


def validate_analysis_input(bundle,records):
    if type(bundle) is not dict:raise ValueError("malformed bundle")
    mapping=bundle.get("identity_mapping")
    validate_identity_map(mapping,records)
    expected=_build(records,mapping)
    if canonical(bundle)!=canonical(expected):raise ValueError("identity/pairing/outcome/provenance drift in analysis input")
    return True


def require_estimator_ingestion(bundle,records):
    validate_analysis_input(bundle,records)
    raise ValueError("NOT_ESTIMABLE: UNOBSERVED/MISSING outcomes, UNVERIFIED input, UNKNOWN eligibility and execution authorization unresolved")


def write_analysis_input(bundle,records,*,output):
    repo=ROOT.resolve();expected=repo/"audits/g2_i5_v1";allowed=expected.resolve();target=Path(output).resolve()
    if allowed!=expected or not target.is_relative_to(allowed) or target==allowed or target.suffix!=".json":
        raise ValueError("synthetic audit output only; prior and production paths forbidden")
    validate_analysis_input(bundle,records)
    data=(canonical(bundle)+"\n").encode();target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as f:f.write(data)
    return {"scope":"SYNTHETIC_ONLY","records":len(bundle["records"]),"sha256":hashlib.sha256(data).hexdigest(),
            "estimator_ingestion":bundle["estimator_ingestion"]}


if __name__=="__main__":
    import argparse
    from src.eval.rq3_export_boundary import install
    guard=install()
    p=argparse.ArgumentParser(description="Explicit fictional ID projection; structural validation, never estimation")
    p.add_argument("--output",required=True);args=p.parse_args()
    records=registered_exports();bundle=build_analysis_input(records,mode="synthetic")
    print(canonical({**write_analysis_input(bundle,records,output=args.output),"boundary":guard.report()}))
