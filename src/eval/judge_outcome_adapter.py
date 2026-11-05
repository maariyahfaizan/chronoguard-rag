"""Fictional judge-label projections and blocked analysis envelopes. No judging.

AST inspection reads schemas only. A label demonstration is never an observation;
all numerical-interface outcomes remain MISSING and ingestion always fails closed.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "chronoguard.judge-outcome-adapter/v1"
MAPPING_VERSION = "chronoguard.proposed-judge-analysis-mapping/v1"
BLOCKED = "NOT_AUTHORIZED_FOR_EXECUTION"
RUBRIC = "answer_judge_v2_claim_specific"
IMPLEMENTATION = "p0_a8_v2_repair_3"
LABELS = {"CORRECT", "POISON_ADOPTED", "OTHER_WRONG", "NEEDS_REVIEW"}
STATES = LABELS | {"ABSTAIN", "MISSING"}
GATES = ("claim_key_approval", "evidence_admissibility", "question_eligibility",
         "provenance_authentication", "protocol_approval", "benchmark_approval",
         "execution_authorization", "judge_validation", "mapping_policy_approval",
         "authoritative_replay")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def schemas():
    """Read exact source schemas without importing judges, matching or estimators."""
    manifest = read(ROOT / "docs/supervisor_review/p0_a9/candidate_manifest.json")
    inventory = {r["path"]: r["sha256"] for r in manifest["files"]}
    paths = ("src/eval/answer_judge_v2.py", "src/eval/claim_keys.py", "src/eval/claim_matching_v2.py")
    for p in paths:
        if sha(ROOT / p) != inventory[p]: raise ValueError("published judge source hash mismatch")
    legacy_inventory = read(ROOT / "audits/p1_c1_v1/reproducibility.json")["source_hashes"]
    analyzer = "src/eval/synthetic_analysis.py"
    if sha(ROOT / analyzer) != legacy_inventory[analyzer]: raise ValueError("analyzer hash mismatch")
    tree = ast.parse((ROOT / paths[0]).read_text(encoding="utf-8"))
    constants = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in {"RUBRIC_VERSION", "IMPLEMENTATION_VERSION"}:
            constants[n.targets[0].id] = ast.literal_eval(n.value)
    if constants != {"RUBRIC_VERSION": RUBRIC, "IMPLEMENTATION_VERSION": IMPLEMENTATION}:
        raise ValueError("unsupported judge revision")
    judge_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JudgementV2")
    fields = [n.target.id for n in judge_class.body if isinstance(n, ast.AnnAssign)]
    tree = ast.parse((ROOT / analyzer).read_text(encoding="utf-8"))
    schema = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                  and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "SCHEMA")
    if set(schema["row_fields"]["outcome"]) != STATES: raise ValueError("analysis states changed")
    return {"judge_fields": fields, "judge_labels": sorted(LABELS), "analysis_schema": schema,
            "judge_revision": IMPLEMENTATION, "rubric": RUBRIC,
            "abstention_note": "OTHER_WRONG/pure_abstention; ABSTAIN is not a judge label"}


def source_bundle():
    folder = ROOT / "audits/g2_i5_v1"
    if sha(folder / "sha256.json") != "b117618369e4ad15af6cbd429fb784491c7343587514a3e74ffa69463abc7239":
        raise ValueError("G2-I5 manifest mismatch")
    for p, h in read(folder / "sha256.json").items():
        if sha(folder / p) != h: raise ValueError("G2-I5 output mismatch")
    bundle = read(folder / "analysis_input.json")
    if len(bundle["records"]) != 16 or len({r["cell_id"] for r in bundle["records"]}) != 16:
        raise ValueError("unexpected registered cells")
    for r in bundle["records"]:
        if (r["outcome_state"] != "UNOBSERVED" or r["analysis_projection"]["outcome"] != "MISSING"
                or r["analysis_projection"]["generator"] != "UNVERIFIED" or r["execution_status"] != BLOCKED):
            raise ValueError("source missingness/authorization changed")
        for text in ("prompt", "context"):
            if hashlib.sha256(r[text].encode()).hexdigest() != r[text+"_sha256"]:
                raise ValueError("source prompt/context mismatch")
    return bundle


def _binding(source):
    return {k: source[k] for k in ("canonical_question_id", "analysis_question_id", "cell_id",
        "analysis_condition", "source_construction_sha256", "prompt_sha256", "context_sha256",
        "identity_mapping_sha256")}


def fixtures():
    """Descriptors invented for software testing, not outputs of any judge run."""
    sources = source_bundle()["records"]
    cases = [("correct", "CORRECT", "endorsed_reviewed_gold", "VALID"),
             ("poison", "POISON_ADOPTED", "endorsed_reviewed_false", "VALID"),
             ("abstention", "OTHER_WRONG", "pure_abstention", "VALID"),
             ("empty", "OTHER_WRONG", "empty_answer", "VALID"),
             ("review", "NEEDS_REVIEW", "mixed_gold_and_false", "VALID"),
             ("missing", None, None, "NOT_SUPPLIED"),
             ("invalid", None, None, "INVALID_UNSUPPORTED_INPUT"),
             ("other_wrong", "OTHER_WRONG", "fictional_generic_other_wrong", "VALID")]
    result = []
    for source, (name, label, reason, status) in zip(sources, cases):
        fid = "synthetic-judge-g2-i7-" + name
        key_id = fid + "-unapproved-key-descriptor"
        key_hash = digest({"fictional_key_descriptor": key_id})
        judge = None if label is None else dict(label=label, reason=reason, rubric_version=RUBRIC,
            implementation_version=IMPLEMENTATION, claim_key_id=key_id, claim_key_hash=key_hash,
            review_status="required" if label == "NEEDS_REVIEW" else "automatic",
            evaluation_id=digest({"fixture_id": fid, "binding": _binding(source), "label": label}), evidence=[])
        result.append(dict(fixture_id=fid, scope="SYNTHETIC_ONLY", binding=_binding(source),
            source_analysis_record_sha256=digest(source), judge_output=judge, judge_input_status=status,
            generation_state="UNOBSERVED", generated_answer=None,
            fixture_authority="FICTIONAL_LABEL_DESCRIPTOR_NOT_JUDGE_EXECUTION",
            fingerprint_basis="SYNTHETIC_PLACEHOLDER_NOT_AUTHORITATIVE_JUDGE_FINGERPRINT",
            claim_key_identity_basis="FICTIONAL_DESCRIPTOR_NOT_AN_APPROVED_CLAIM_KEY",
            gates={g: "UNRECORDED" for g in GATES}))
    return result


def map_descriptor(judge, input_status):
    """Proposed semantic projection only; never numeric eligibility or observation."""
    if input_status not in {"VALID", "NOT_SUPPLIED", "INVALID_UNSUPPORTED_INPUT"}:
        raise ValueError("unsupported input status")
    if input_status != "VALID":
        if judge is not None: raise ValueError("invalid/missing input cannot carry a judge result")
        return ("MISSING", "NO_JUDGE_RESULT") if input_status == "NOT_SUPPLIED" else ("NEEDS_REVIEW", "INVALID_UNSUPPORTED_JUDGE_INPUT")
    if type(judge) is not dict or set(judge) != set(schemas()["judge_fields"]):
        raise ValueError("invalid judgement fields")
    label, reason = judge["label"], judge["reason"]
    if type(label) is not str or label not in LABELS: raise ValueError("unsupported judge label")
    if type(reason) is not str or not reason.strip(): raise ValueError("missing judgement reason")
    if judge["rubric_version"] != RUBRIC or judge["implementation_version"] != IMPLEMENTATION:
        raise ValueError("stale judge revision")
    if judge["review_status"] != ("required" if label == "NEEDS_REVIEW" else "automatic"):
        raise ValueError("review-status mismatch")
    if label == "OTHER_WRONG" and reason == "pure_abstention":
        return "ABSTAIN", "PROPOSED_ABSTENTION_POLICY_NOT_APPROVED"
    if label == "OTHER_WRONG" and reason == "empty_answer":
        return "MISSING", "EMPTY_ANSWER_RETAINED_SEPARATELY_POLICY_NOT_APPROVED"
    return label, "NEEDS_INDEPENDENT_REVIEW" if label == "NEEDS_REVIEW" else "FICTIONAL_LABEL_ONLY_NOT_AN_OBSERVATION"


def project(records, *, mode):
    if mode != "synthetic": raise ValueError("real outcome projection forbidden")
    if type(records) is not list or not records or any(type(r) is not dict for r in records):
        raise ValueError("nonempty plain fixture list required")
    registered = {r["fixture_id"]: r for r in fixtures()}
    seen, identities, evaluation_ids = set(), set(), set()
    outputs = []
    source_index = {r["cell_id"]: r for r in source_bundle()["records"]}
    for record in records:
        fid = record.get("fixture_id")
        if type(fid) is not str or fid not in registered or record.get("scope") != "SYNTHETIC_ONLY":
            raise ValueError("real/unregistered fixture rejected")
        if fid in seen: raise ValueError("duplicate fixture identity")
        seen.add(fid)
        state, uncertainty = map_descriptor(record.get("judge_output"), record.get("judge_input_status"))
        binding = record.get("binding")
        if type(binding) is not dict or binding.get("cell_id") not in source_index:
            raise ValueError("unknown condition binding")
        identity = (binding.get("canonical_question_id"), binding.get("cell_id"))
        if identity in identities: raise ValueError("duplicate/colliding condition identity")
        identities.add(identity)
        source = source_index[binding["cell_id"]]
        if binding != _binding(source) or record.get("source_analysis_record_sha256") != digest(source):
            raise ValueError("identity/condition/hash binding mismatch")
        judge = record["judge_output"]
        if judge is not None:
            if judge["evaluation_id"] in evaluation_ids: raise ValueError("duplicate evaluation identity")
            evaluation_ids.add(judge["evaluation_id"])
        if canonical(record) != canonical(registered[fid]):
            raise ValueError("altered/rehashed/unregistered fixture or authority promotion")
        reasons = ["NO_OBSERVED_GENERATED_ANSWER", "SYNTHETIC_LABEL_NOT_SCIENTIFIC_OBSERVATION",
                   "UNVERIFIED_GENERATOR_INPUT"] + ["UNAPPROVED_" + g.upper() for g in GATES]
        if state in {"MISSING", "NEEDS_REVIEW"}: reasons.append(uncertainty)
        outputs.append(dict(schema_version=VERSION, mapping_version=MAPPING_VERSION, scope="SYNTHETIC_ONLY",
            fixture_id=fid, **copy.deepcopy(binding), source_analysis_record_sha256=digest(source),
            source_fixture_sha256=digest(record), original_judge_output=copy.deepcopy(judge),
            original_judge_label=judge["label"] if judge else None,
            original_judge_reason=judge["reason"] if judge else None,
            judge_version=judge["implementation_version"] if judge else None,
            judge_rubric=judge["rubric_version"] if judge else None,
            claim_key_id=judge["claim_key_id"] if judge else None,
            claim_key_hash=judge["claim_key_hash"] if judge else None,
            claim_key_approval="UNRECORDED", authoritative_replay="REQUIRED_NOT_PERFORMED",
            fingerprint_basis=record["fingerprint_basis"], projected_analysis_state=state,
            uncertainty_reason=uncertainty, missingness_reasons=reasons,
            generation_state="UNOBSERVED", outcome_state="UNOBSERVED",
            analysis_projection=copy.deepcopy(source["analysis_projection"]),
            analysis_eligibility="BLOCKED", execution_status=BLOCKED,
            gate_statuses=copy.deepcopy(record["gates"])))
    return sorted(outputs, key=lambda r: r["fixture_id"])


def validate_export(outputs, records):
    if canonical(outputs) != canonical(project(records, mode="synthetic")):
        raise ValueError("output identity, state, provenance or eligibility drift")
    return True


def require_numerical_eligibility(outputs, records):
    validate_export(outputs, records)
    raise ValueError("BLOCKED: no observations; unapproved keys/evidence/eligibility/protocol/benchmark/execution/judge validation/policy/replay")


def validate_analysis_structure(outputs, records):
    """Reuse only the pinned AST-extracted P1-C1 field validator, no estimator."""
    from src.eval.canonical_analysis_input import _legacy_validator
    validate_export(outputs, records)
    bundle = source_bundle()
    frames = [r["analysis_frame"] for r in bundle["frame_records"]]
    _legacy_validator()(frames, [r["analysis_projection"] for r in outputs])
    _legacy_validator()(frames, [r["analysis_projection"] for r in unobserved_source_export()])
    return {"status": "STRUCTURE_ONLY_VALID", "numerical_eligibility": "BLOCKED"}


def unobserved_source_export():
    """Full sixteen-cell original source projection, unchanged missingness semantics."""
    result = []
    for source in source_bundle()["records"]:
        result.append(dict(schema_version=VERSION, **_binding(source), scope="SYNTHETIC_ONLY",
            source_analysis_record_sha256=digest(source), original_judge_label=None,
            original_judge_reason=None, judge_version=None, claim_key_id=None, claim_key_hash=None,
            projected_analysis_state="MISSING", outcome_state="UNOBSERVED",
            analysis_projection=copy.deepcopy(source["analysis_projection"]),
            missingness_reason="NO_GENERATION_NO_JUDGING", analysis_eligibility="BLOCKED",
            execution_status=BLOCKED))
    return result


def write_export(outputs, records, *, output):
    target = Path(output).resolve()
    allowed = ROOT / "audits/g2_i7_v1/analysis_state_export.json"
    if target != allowed.resolve() or allowed.parent.resolve() != allowed.parent:
        raise ValueError("output escape/production/earlier audit path rejected")
    validate_export(outputs, records)
    payload = {"schema_version": VERSION, "fictional_label_projections": outputs,
               "unobserved_source_records": unobserved_source_export(), "numeric_eligibility": "BLOCKED"}
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream: stream.write((canonical(payload)+"\n").encode())
