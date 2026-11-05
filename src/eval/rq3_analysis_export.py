"""Pinned synthetic factorial export. Unobserved outcomes are never numerical data."""
from __future__ import annotations

import ast
import copy
from datetime import date
import hashlib
from itertools import product
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE_ROOT=ROOT
VERSION="chronoguard.rq3-condition-export/v1"
MAPPING_VERSION="chronoguard.rq3-factor-mapping/v1"
FACTOR_MAP={"newer_looking":{"correct":"correct_newer","incorrect":"incorrect_newer"},
            "header_wording":{"neutral":"neutral","freshness":"freshness"},
            "passage_order":{"correct_first":"correct_first","incorrect_first":"incorrect_first"}}
CONDITIONS=["/".join(x) for x in product(FACTOR_MAP["newer_looking"].values(),
    FACTOR_MAP["header_wording"].values(),FACTOR_MAP["passage_order"].values())]


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs():
    pins={"audits/p1_b1_v1":"c31f7560518506e115ccca2ca3785d37721602c58cf68f11e373a228f1f15ae8",
          "audits/p1_c1_v1":"c05b5aa5a153d6484df01736ac1aa1347195c7e4754506991cf52b878a32b536",
          "audits/g2_i3_v1":"65536fd3e0acaafd0204f0204d6e3eae34836206dee9ea4bebebd1ca4778d7e0"}
    for directory,expected in pins.items():
        root=SOURCE_ROOT/directory
        if sha(root/"sha256.json")!=expected:raise ValueError("prerequisite checksum mismatch")
        for name,h in json.loads((root/"sha256.json").read_text()).items():
            if sha(root/name)!=h:raise ValueError("prerequisite artifact changed")
        inv=(json.loads((root/"reproducibility.json").read_text())["source_hashes"]
             if directory.endswith("p1_c1_v1") else json.loads((root/"source_inventory.json").read_text()))
        for name,h in inv.items():
            if sha(SOURCE_ROOT/name)!=h:raise ValueError("prerequisite source changed")
    return pins


def registered_cells():
    verify_inputs()
    return [json.loads(l) for l in (SOURCE_ROOT/"audits/p1_b1_v1/cells.jsonl").read_text(encoding="utf-8").splitlines()]


def map_factors(factors):
    if type(factors) is not dict or set(factors)!=set(FACTOR_MAP):raise ValueError("invalid factor fields")
    try:
        mapped={k:FACTOR_MAP[k][factors[k]] for k in FACTOR_MAP}
    except (KeyError,TypeError) as exc:raise ValueError("unsupported explicit factor level") from exc
    return mapped,"/".join(mapped[k] for k in FACTOR_MAP)


def _analysis_schema():
    # Read the existing schema literal only; do not import or run estimators.
    tree=ast.parse((SOURCE_ROOT/"src/eval/synthetic_analysis.py").read_text(encoding="utf-8"))
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(
        isinstance(t,ast.Name) and t.id=="SCHEMA" for t in n.targets))
    return ast.literal_eval(node.value)


def export_conditions(cells):
    trusted=registered_cells()
    if type(cells) is not list or len(cells)!=len(trusted) or any(type(c) is not dict for c in cells):
        raise ValueError("complete registered factorial artifact required")
    ids=[c.get("cell_id") for c in cells]
    if any(type(x) is not str for x in ids) or len(set(ids))!=len(ids):raise ValueError("duplicate/missing cell ID")
    index={c["cell_id"]:c for c in trusted}
    if set(ids)!=set(index) or any(canonical(c)!=canonical(index[c["cell_id"]]) for c in cells):
        raise ValueError("unregistered real/modified construction cell")
    # Reuse exactly G2-I3's pinned pure helper extraction, not its request-only API.
    from src.eval.request_context_traces import _helpers
    truncate,prompt_helper=_helpers()
    source_schema=_analysis_schema()
    output=[]
    seen={}
    block_bindings={}
    for cell in sorted(cells,key=lambda c:(c["synthetic_case_id"],CONDITIONS.index(map_factors(c["factors"])[1]))):
        qid=cell["synthetic_case_id"]
        if not qid.startswith("synthetic-smoke-"):raise ValueError("real namespace forbidden")
        mapped,condition=map_factors(cell["factors"])
        seen.setdefault(qid,set()).add(condition)
        roles=["correct","incorrect"] if mapped["passage_order"]=="correct_first" else ["incorrect","correct"]
        passages=cell["passages"]
        if len(passages)!=2 or [p["role"] for p in passages]!=roles:raise ValueError("passage-order drift")
        if cell["presentation"]!="DIRECT_BOTH_PASSAGES_NO_RETRIEVAL" or cell["passage_count"]!=2:
            raise ValueError("direct complete evidence presentation required")
        dates=cell["date_pair"]
        if len(dates)!=2 or not date.fromisoformat(dates[0])<date.fromisoformat(dates[1]):raise ValueError("invalid paired date cues")
        cap=cell["generation"]["max_passage_chars"]
        if (digest(cell["generation"])!=cell["generation_configuration_sha256"]
                or cell["allocated_context_characters"]!=2*cap):
            raise ValueError("configuration identity or allocation mismatch")
        stable={"question":cell["question"],"generation":cell["generation"],"date_pair":dates,
                "claims":sorted([{k:p[k] for k in ("role","doc_id","body","original_body_sha256",
                    "origin","original_fixture_timestamp")} for p in passages],key=lambda p:p["role"])}
        binding=digest(stable)
        if qid in block_bindings and block_bindings[qid]!=binding:
            raise ValueError("question/claim/variant/configuration/date-pair drift within factorial block")
        block_bindings[qid]=binding
        texts=[p["rendered_text"] for p in passages]
        kept=[truncate(text,cap) for text in texts]
        context="\n\n".join(kept)
        prompt=prompt_helper(cell["question"],texts,cap)
        if prompt!=cell["prompt"] or text_sha(prompt)!=cell["prompt_sha256"]:raise ValueError("prompt hash mismatch")
        cursor=0; rendered=[]; visibility={}
        context_start=prompt.index("Context:\n")+len("Context:\n")
        for slot,p in enumerate(passages):
            if text_sha(p["body"])!=p["original_body_sha256"]:raise ValueError("claim identity drift")
            expected_date=dates[1] if p["role"]==cell["factors"]["newer_looking"] else dates[0]
            if p["assigned_date_label"]!=expected_date:raise ValueError("date assignment drift")
            if p["date_cue_text"]!="Assigned date cue: "+expected_date+"\n":raise ValueError("date cue rendering drift")
            expected_header={"neutral":"General notice:\n","freshness":"Latest update:\n"}[mapped["header_wording"]]
            if p["header"]!=expected_header or p["rendered_text"]!=expected_header+p["date_cue_text"]+p["body"]:
                raise ValueError("wording/body rendering drift")
            begin,end=p["body_span"]
            complete=(len(p["rendered_text"])<=cap and kept[slot][begin:end]==p["body"]
                and prompt[context_start+cursor+begin:context_start+cursor+end]==p["body"])
            visibility[p["role"]]="COMPLETE_IN_ASSEMBLED_PROMPT" if complete else "TRUNCATED"
            variant={"doc_id":p["doc_id"],"body_sha256":p["original_body_sha256"],
                     "fixture_timestamp":p["original_fixture_timestamp"],"origin":p["origin"]}
            rendered.append({"slot":slot,"role":p["role"],"doc_id":p["doc_id"],
                "original_body_sha256":p["original_body_sha256"],"body_variant_sha256":digest(variant),
                "variant_hash_basis":"DERIVED_SYNTHETIC_BODY_DESCRIPTOR_NOT_ORIGINAL_SOURCE_AUTHENTICATION",
                "rendered_text_sha256":text_sha(p["rendered_text"]),"assigned_date_label":p["assigned_date_label"],
                "date_basis":p["date_basis"],"context_body_span":[cursor+begin,cursor+end],
                "prompt_body_span":[context_start+cursor+begin,context_start+cursor+end],
                "characters":len(p["rendered_text"]),"utf8_bytes":len(p["rendered_text"].encode()),
                "retained_characters":len(kept[slot]),"complete_claim":complete})
            cursor+=len(kept[slot])+2
        if not all(p["complete_claim"] for p in rendered):raise ValueError("incomplete evidence claims")
        row={"question_id":qid,"family":"rq3","condition":condition,"construction":"SUCCEEDED",
             "retrieval":"NOT_APPLICABLE","generator":"UNVERIFIED","outcome":"MISSING"}
        if set(row)!=set(source_schema["row_fields"]):raise ValueError("legacy analysis field mismatch")
        for k in ("construction","retrieval","generator","outcome"):
            if row[k] not in source_schema["row_fields"][k]:raise ValueError("unsupported analysis state")
        source_hash=digest(cell)
        result={"schema_version":VERSION,"scope":"SYNTHETIC_ONLY","execution_status":"NOT_AUTHORIZED_FOR_EXECUTION",
            "question_id":qid,"cell_id":cell["cell_id"],"source_cell_id":cell["cell_id"],
            "export_id":"g2-i4:"+digest({"source":source_hash,"mapping":MAPPING_VERSION,"condition":condition}),
            "mapping_version":MAPPING_VERSION,"source_factors":copy.deepcopy(cell["factors"]),"analysis_factors":mapped,
            "analysis_condition":condition,"source_construction_sha256":source_hash,
            "source_artifact":{"path":"audits/p1_b1_v1/cells.jsonl","sha256":sha(SOURCE_ROOT/"audits/p1_b1_v1/cells.jsonl")},
            "question_sha256":text_sha(cell["question"]),"passages":rendered,"passage_order_verified":True,
            "context":context,"context_sha256":text_sha(context),"prompt":prompt,"prompt_sha256":text_sha(prompt),
            "context_characters":len(context),"prompt_characters":len(prompt),"passage_char_limit":cap,
            "claim_visibility":visibility,"token_level_balancing":"UNVERIFIED","actual_model_visibility":"UNKNOWN",
            "outcome_state":"UNOBSERVED","missingness_reason":"NO_GENERATION_NO_JUDGING",
            "analysis_eligibility":"NOT_ELIGIBLE_UNOBSERVED_AND_UNVERIFIED_INPUT",
            "analysis_projection":row,"legacy_analysis_compatibility":"BLOCKED_CANONICAL_ID_NAMESPACE_GUARD",
            "assembly_source":"G2-I3 pinned pure helper extraction; no G2-I2 request impersonation",
            "generation_configuration_sha256":cell["generation_configuration_sha256"]}
        output.append(result)
    if len(seen)!=2 or any(v!=set(CONDITIONS) for v in seen.values()):raise ValueError("incomplete eight-cell block")
    return output


def validate_export(records,cells):
    if type(records) is not list or any(type(r) is not dict or type(r.get("export_id")) is not str for r in records):
        raise ValueError("malformed condition export")
    if len({r["export_id"] for r in records})!=len(records):raise ValueError("duplicate condition export")
    if canonical(records)!=canonical(export_conditions(cells)):raise ValueError("condition export differs from registered replay")
    return True


def analysis_bundle(records,cells):
    validate_export(records,cells)
    return {"schema_version":"chronoguard.canonical-rq3-analysis-pending/v1","status":"NOT_ESTIMABLE_UNOBSERVED",
        "frame":[{"question_id":qid,"eligibility":"UNKNOWN","clean":"MISSING"} for qid in sorted({r["question_id"] for r in records})],
        "rows":[copy.deepcopy(r["analysis_projection"]) for r in records],
        "bindings":[{"question_id":r["question_id"],"condition":r["analysis_condition"],"cell_id":r["cell_id"],
                     "source_construction_sha256":r["source_construction_sha256"],"export_id":r["export_id"]} for r in records],
        "legacy_ingestion":"BLOCKED; requires separately reviewed canonical-ID analysis profile, not ID renaming"}


def estimator_inputs(records,cells):
    validate_export(records,cells)
    raise ValueError("NOT_ESTIMABLE: unobserved outcomes and unverified model input cannot enter numerical estimators")


def write_export(records,cells,*,output):
    repo=ROOT.resolve();expected=repo/"audits/g2_i4_v1";allowed=expected.resolve();target=Path(output).resolve()
    if allowed!=expected or not target.is_relative_to(allowed) or target==allowed or target.suffix!=".jsonl":
        raise ValueError("synthetic audit path only; production/prior paths forbidden")
    validate_export(records,cells)
    data="".join(canonical(r)+"\n" for r in records).encode()
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("xb") as f:f.write(data)
    return {"records":len(records),"sha256":hashlib.sha256(data).hexdigest(),"outcome_state":"UNOBSERVED"}


if __name__=="__main__":
    import argparse
    from src.eval.rq3_export_boundary import install
    guard=install()
    p=argparse.ArgumentParser(description="Synthetic unobserved RQ3 condition export; no judging or inference")
    p.add_argument("--output",required=True);args=p.parse_args()
    cells=registered_cells();records=export_conditions(cells)
    print(canonical({**write_export(records,cells,output=args.output),"boundary":guard.report()}))
