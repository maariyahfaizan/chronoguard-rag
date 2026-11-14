"""W6-J1 offline integration. Only registered fictional inputs are admitted.

Fixture digests are consistency checks, never signatures or real approval.
There is deliberately no real authority provider or real-case execution path.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .answer_judge_v2 import (
    IMPLEMENTATION_VERSION, RUBRIC_VERSION, judge_answer, validate_output_batch,
)
from .claim_keys import ClaimContext, ClaimKey, identity_hash

VERSION = "chronoguard.attack-postprocess/w6-j1-v1"
SCOPE = "REGISTERED_SYNTHETIC_ONLY"
ROOT = Path(__file__).resolve().parents[2]


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       allow_nan=False, indent=2) + "\n").encode("utf-8")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field: " + key)
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def fixture_bundle():
    """Independent code-owned registry; not caller-issued real approval."""
    context = ClaimContext(
        "synthetic-w6-j1-race", "Who won the fictional Luma race?", "Alice Smith",
        ("Alice Smith",), "synthetic-w6-j1-passage",
        "Fictional report: Bob Jones won the Luma race.")
    key = ClaimKey(
        "synthetic-w6-j1-key", context.question_id, identity_hash(context.question),
        identity_hash(context.primary_gold), identity_hash(context.aliases),
        context.source_id, identity_hash(context.source_text), "Luma race winner",
        "won race", "Bob Jones", None, "positive", (),
        ("Bob Jones", "Bob Jones won the race"),
        ("Alice Smith", "Alice Smith won the race"),
        "W6-J1 handwritten fictional fixture; no scientific approval",
        "approved", "synthetic-fixture-reviewer")
    records = []
    for index, answer in enumerate(("Bob Jones", "Alice Smith", "unknown", "",
                                    "Maybe Bob Jones won the race.",
                                    "Alice Smith won the race. Bob Jones won the race.")):
        records.append({
            "event_id": f"synthetic-w6-j1-event-{index}", "context": asdict(context),
            "generated_answer": answer, "claim_key": asdict(key), "key_digest": key.digest,
            "provenance": {"source_kind": "HANDWRITTEN_FICTION",
                           "event_origin": "CODE_OWNED_FIXTURE", "fixture_index": index},
            "approval": {"kind": "SYNTHETIC_FIXTURE_ONLY", "status": "ACTIVE",
                         "key_id": key.key_id, "key_digest": key.digest,
                         "rubric_version": RUBRIC_VERSION,
                         "implementation_version": IMPLEMENTATION_VERSION},
        })
    # JSON roundtrip supplies the same list representation as a CLI input.
    return json.loads(encode({"schema_version": VERSION, "scope": SCOPE,
                            "rubric_version": RUBRIC_VERSION,
                            "implementation_version": IMPLEMENTATION_VERSION,
                            "records": records}))


def admit(bundle, *, rubric_version):
    if rubric_version != RUBRIC_VERSION:
        raise ValueError("explicit supported v2 rubric required; no fallback")
    if type(bundle) is not dict or bundle.get("scope") != SCOPE:
        raise ValueError("real-case execution disabled: no authenticated authority provider")
    registry = fixture_bundle()
    for field in ("schema_version", "rubric_version", "implementation_version"):
        if bundle.get(field) != registry[field]:
            raise ValueError("mismatched revision: " + field)
    if set(bundle) != set(registry):
        raise ValueError("unexpected bundle fields")
    records = bundle.get("records")
    if type(records) is not list or not records:
        raise ValueError("nonempty controlled records required")
    registered = {r["event_id"]: r for r in registry["records"]}
    inputs, events = [], set()
    for record in records:
        if type(record) is not dict:
            raise ValueError("invalid controlled record")
        event = record.get("event_id")
        if type(event) is not str or event not in registered or event in events:
            raise ValueError("duplicate or unregistered event identity")
        events.add(event)
        try:
            c = dict(record["context"])
            k = dict(record["claim_key"])
            for obj, names in ((c, ("aliases",)),
                               (k, ("temporal_qualifiers", "false_expressions", "gold_expressions"))):
                for name in names:
                    if type(obj[name]) is not list:
                        raise ValueError("JSON array required: " + name)
                    obj[name] = tuple(obj[name])
            context, key = ClaimContext(**c), ClaimKey(**k)
            context.validate_types()
            key.validate_types()
            approval = record["approval"]
            if approval != registered[event]["approval"]:
                raise ValueError("absent, revoked, stale or unverifiable fixture approval")
            approved = {approval["key_id"]: approval["key_digest"]}
            if record["key_digest"] != key.digest or key.problems(context, approved):
                raise ValueError("invalid key digest or question/source binding")
            if identity_hash(record) != identity_hash(registered[event]):
                raise ValueError("unregistered or altered fixture record/provenance")
        except (KeyError, TypeError) as exc:
            raise ValueError("missing or malformed controlled key/input") from exc
        inputs.append(dict(rubric_version=rubric_version, context=context,
                           generated_answer=record["generated_answer"], claim_key=key,
                           approved_keys=approved))
    return inputs


def process(bundle, *, rubric_version):
    inputs = admit(bundle, rubric_version=rubric_version)
    judgments = [judge_answer(**source).to_dict() for source in inputs]
    # Also detects identical evaluation inputs under different event identities.
    validate_output_batch(judgments, rubric_version=rubric_version, authoritative_inputs=inputs)
    return json.loads(encode({
        "schema_version": VERSION, "scope": SCOPE, "scientific_validation": "NOT_VALIDATED",
        "real_case_authority": "DISABLED_NO_AUTHENTICATED_PROVIDER",
        "input_digest": identity_hash(bundle), "rubric_version": RUBRIC_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "rows": [{"event_id": record["event_id"], "input_record": record,
                  "input_record_digest": identity_hash(record), "judgment": judgment}
                 for record, judgment in zip(bundle["records"], judgments)],
    }))


def verify_output(output, bundle, *, rubric_version):
    """Re-admit independently loaded input; never trust embedded input as authority."""
    inputs = admit(bundle, rubric_version=rubric_version)
    try:
        validate_output_batch([r["judgment"] for r in output["rows"]],
                              rubric_version=rubric_version, authoritative_inputs=inputs)
        if identity_hash(output) != identity_hash(process(bundle, rubric_version=rubric_version)):
            raise ValueError("output provenance or envelope differs from authoritative replay")
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed output") from exc


def write_new(path, value):
    """Never overwrite, or write into historical artifact trees."""
    path = Path(path).resolve()
    for name in ("data", "logs", "results", "audits", "docs", ".git"):
        if path.is_relative_to(ROOT / name):
            raise ValueError("output must be outside protected repository artifact trees")
    with path.open("xb") as stream:
        stream.write(encode(value))


def run(input_path, output_path, *, rubric_version):
    raw = Path(input_path).read_bytes()
    bundle = read(input_path)
    output = process(bundle, rubric_version=rubric_version)
    output["input_file_sha256"] = hashlib.sha256(raw).hexdigest()
    # File digest is transport provenance; the replay envelope is otherwise exact.
    verify_file_output(output, input_path, rubric_version=rubric_version)
    serialized = json.loads(encode(output))
    verify_file_output(serialized, input_path, rubric_version=rubric_version)
    write_new(output_path, serialized)


def verify_file_output(output, input_path, *, rubric_version):
    raw = Path(input_path).read_bytes()
    core = dict(output)
    if core.pop("input_file_sha256", None) != hashlib.sha256(raw).hexdigest():
        raise ValueError("input file digest mismatch")
    verify_output(core, read(input_path), rubric_version=rubric_version)
