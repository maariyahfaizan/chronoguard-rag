"""Opt-in persistence, not execution or scientific approval.

Records use sorted-key, compact UTF-8 JSON and exactly one LF per record. This
codec intentionally differs from the float-free A9 identity codec. Chronology
compares recorded UTC calendar dates only: same-date ordering is uncertain,
naive datetimes are unknown, and no recorded date authenticates a publication.

Packages preserve original input bytes. An expected manifest digest must come
from outside the package; a self-consistent package is not authentic evidence.
Tokenizer receipts are external claims with byte-checked assets, not tokenizer
execution performed by this module. No model or tokenizer is loaded here.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

from . import week4_v2_schema as schema
from . import chunk_streamingqa_pools_v2 as chunker

VERSION = "streamingqa_persistence_v1"
ROOT = Path(__file__).resolve().parents[2]
INPUT_NAMES = {"raw_eval": "inputs/streamingqa_eval.jsonl.gz",
               "sample": "inputs/streamingqa_control_sample.jsonl",
               "parent_pool": "inputs/streamingqa_control_pools.jsonl"}
IMPLEMENTATIONS = ("src/eval/week4_v2_schema.py",
                   "src/eval/chunk_streamingqa_pools_v2.py",
                   "src/eval/streamingqa_v2_persistence.py")
require = schema.require
sha = schema.sha256_bytes


def _json_value(value, active=None):
    active = set() if active is None else active
    t = type(value)
    require(t in (dict, list, str, int, float, bool, type(None)), "UNSUPPORTED_JSON_VALUE")
    if t is float:
        require(math.isfinite(value), "NONFINITE_JSON_NUMBER")
    if t is str:
        value.encode("utf-8", errors="strict")
    if t in (dict, list):
        require(id(value) not in active, "CYCLIC_JSON")
        active.add(id(value))
        if t is dict:
            require(all(type(k) is str for k in value), "JSON_KEY_TYPE")
            for k, v in value.items():
                _json_value(k, active)
                _json_value(v, active)
        else:
            for v in value:
                _json_value(v, active)
        active.remove(id(value))


def encode_json(value):
    """Return canonical record bytes, preserving finite JSON floats."""
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def decode_json(raw):
    """Strict UTF-8/JSON including nested duplicate-key and overflow rejection."""
    require(type(raw) is bytes, "JSON_BYTES_REQUIRED")
    def pairs(items):
        require(len({k for k, _ in items}) == len(items), "DUPLICATE_JSON_KEY")
        return dict(items)
    def constant(value):
        raise schema.SchemaError("NONFINITE_JSON_NUMBER:" + value)
    value = json.loads(raw.decode("utf-8", errors="strict"),
                       object_pairs_hook=pairs, parse_constant=constant)
    _json_value(value)
    return value


def _jsonl(raw):
    require(type(raw) is bytes and raw.endswith(b"\n"), "INCOMPLETE_JSONL")
    lines = raw.split(b"\n")[:-1]
    require(bool(lines) and all(line.strip() for line in lines), "EMPTY_JSONL_RECORD")
    return [decode_json(line) for line in lines]


def _date(value):
    try:
        if type(value) in (int, float):
            require(math.isfinite(value), "NONFINITE_TIMESTAMP")
            return datetime.fromtimestamp(value, timezone.utc).date().isoformat(), "UNIX_SECONDS_UTC"
        if type(value) is str:
            if len(value) == 10:
                return date.fromisoformat(value).isoformat(), "RECORDED_DATE_ONLY"
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).date().isoformat(), "OFFSET_TIMESTAMP_TO_UTC"
    except (ValueError, OverflowError, OSError):
        pass
    return None, "UNPARSEABLE_OR_UNSPECIFIED_TIMEZONE"


def chronology_annotation(question_timestamp, publication_timestamp):
    """Calendar ordering only; never modifies core temporal_validity."""
    q, qb = _date(question_timestamp)
    p, pb = _date(publication_timestamp)
    state = "UNKNOWN" if q is None or p is None else (
        "PRIOR_DATE" if p < q else "FUTURE_DATED" if p > q else "SAME_DATE_UNCERTAIN")
    return {"question_timestamp": question_timestamp, "publication_timestamp": publication_timestamp,
            "question_utc_date": q, "publication_utc_date": p,
            "question_date_basis": qb, "publication_date_basis": pb,
            "chronology": state, "policy": "UTC_CALENDAR_DATE_ONLY",
            "temporal_validity": "UNKNOWN", "source_authority": "UNKNOWN"}


def _configuration(raw):
    import yaml
    class Loader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        items = loader.construct_pairs(node, deep=deep)
        require(all(type(k) is str for k, _ in items), "CONFIG_KEY_TYPE")
        require(len({k for k, _ in items}) == len(items), "DUPLICATE_CONFIG_KEY")
        return dict(items)
    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    result = yaml.load(raw.decode("utf-8"), Loader=Loader)
    schema.validate_config(result)
    encode_json(result)
    return result


def _safe_name(name):
    require(type(name) is str and name and "\\" not in name and ":" not in name
            and not name.startswith("/") and all(x not in ("", ".", "..") for x in name.split("/"))
            and all(ord(c) >= 32 for c in name), "UNSAFE_PACKAGE_PATH")
    return name


def _initial(q):
    require(q["scientific_approval"] == "NOT_GRANTED" and
            q["execution_authorization"] == "NOT_AUTHORIZED_FOR_EXECUTION" and
            q["answer_key_status"] == "NOT_REVIEWED", "INITIAL_QUESTION_STATE")
    for p in q["parents"]:
        require(p["source_authentication"] == "NOT_AUTHENTICATED", "INITIAL_AUTHENTICATION")
    for c in q["candidates"]:
        require(c["relevance_grade"] == "UNKNOWN" and c["semantic_review_status"] == "NOT_REVIEWED"
                and c["semantic_review_refs"] == [] and c["temporal_validity"] == "UNKNOWN"
                and c["temporal_review_refs"] == [] and c["source_authentication"] == "NOT_AUTHENTICATED"
                and c["scientific_approval"] == "NOT_GRANTED", "INITIAL_CHILD_STATE")


def _receipt(receipt, assets, profiles, configs, scope, required):
    require(type(assets) is dict, "ASSET_MAPPING")
    for name, value in assets.items():
        _safe_name(name)
        require(type(value) is bytes, "ASSET_BYTES")
    status = {"receipt": "UNAVAILABLE", "asset_verification": "NOT_PERFORMED",
              "offset_execution": "NOT_REEXECUTED_BY_PERSISTENCE"}
    if receipt is None:
        require(not required and not assets, "TOKENIZER_RECEIPT_REQUIRED")
        return status
    r = decode_json(receipt)
    require(type(r) is dict and set(r) == {"schema_version", "scope", "model_id", "revision",
            "construction_config_sha256", "asset_sha256", "runtime_versions", "offset_verification",
            "limitations"}, "TOKENIZER_RECEIPT_FIELDS")
    require(r["schema_version"] == "streamingqa_tokenizer_receipt_v1" and r["scope"] == scope
            and r["model_id"] == schema.TOKENIZER and r["revision"] == schema.REVISION
            and r["construction_config_sha256"] == configs, "TOKENIZER_RECEIPT_BINDING")
    require(type(r["asset_sha256"]) is dict and type(r["runtime_versions"]) is dict
            and r["offset_verification"] in ("VERIFIED", "UNVERIFIED")
            and type(r["limitations"]) is list and all(type(x) is str for x in r["limitations"]),
            "TOKENIZER_RECEIPT_TYPES")
    for name, digest in r["asset_sha256"].items():
        _safe_name(name)
        schema.digest(digest)
    require(set(assets) <= set(r["asset_sha256"]), "UNDECLARED_TOKENIZER_ASSET")
    for name, raw in assets.items():
        require(sha(raw) == r["asset_sha256"][name], "TOKENIZER_ASSET_HASH")
    for profile in profiles:
        if profile["asset_hashes"]:
            require(dict(profile["asset_hashes"]) == r["asset_sha256"], "PROFILE_ASSET_MISMATCH")
        if profile["runtime_version"] is not None:
            require(profile["runtime_version"] in r["runtime_versions"].values(), "PROFILE_RUNTIME_MISMATCH")
    complete = bool(assets) and set(assets) == set(r["asset_sha256"])
    if required:
        require(complete and r["offset_verification"] == "VERIFIED"
                and all(type(r["runtime_versions"].get(k)) is str and r["runtime_versions"][k]
                        for k in ("transformers", "tokenizers")), "TOKENIZER_VERIFICATION_REQUIRED")
    status.update(receipt="EXTERNAL_RECEIPT_BOUND", asset_verification=(
        "MATCHES_RECEIPT" if complete else "INCOMPLETE"), reported_verification=r)
    return status


def serialize_package(records, frame, *, input_artifacts, configuration_bytes,
                      tokenizer_receipt=None, tokenizer_assets=None,
                      require_tokenizer_verification=False):
    """Return (relative-path -> bytes, manifest SHA256); no filesystem writes."""
    require(type(require_tokenizer_verification) is bool, "VERIFICATION_REQUIREMENT_TYPE")
    encode_json(records)
    schema.validate_frame(frame)
    require(type(records) is list and type(input_artifacts) is dict
            and set(input_artifacts) == set(INPUT_NAMES), "PACKAGE_INPUTS")
    config = _configuration(configuration_bytes)
    for role, raw in input_artifacts.items():
        require(type(raw) is bytes, "INPUT_BYTES")
        require(sha(raw) == frame[role + "_sha256"] == config["frame"][role + "_sha256"],
                "INPUT_CHECKSUM:" + role)
    sample = _jsonl(input_artifacts["sample"])
    parents = _jsonl(input_artifacts["parent_pool"])
    expected_frame = schema.make_frame([q["qa_id"] for q in sample], frame["raw_eval_sha256"],
        frame["sample_sha256"], frame["parent_pool_sha256"], synthetic=frame["scope"] == "SYNTHETIC_ONLY")
    require(encode_json(frame) == encode_json(expected_frame), "FRAME_SOURCE_MISMATCH")
    require(len(records) == len(sample) == len(parents), "QUESTION_COUNT")
    chunker.validate_pool_records(records, frame)
    envelopes, profiles, configs, representation = [], [], [], []
    for q, qa, source in zip(records, sample, parents):
        schema.validate_against_sources(q, frame, qa, source)
        _initial(q)
        require(type(source.get("gold_chunk_ids")) is list and
                all(type(x) is str for x in source["gold_chunk_ids"]) and
                type(source.get("gold_validated")) is bool, "HISTORICAL_GOLD_METADATA_REQUIRED")
        source_ids = {p["original_parent_passage_id"] for p in q["parents"]}
        require(all(x in source_ids for x in source["gold_chunk_ids"]), "UNRESOLVED_HISTORICAL_GOLD_ID")
        annotations = [{"parent_occurrence_id": p["parent_occurrence_id"],
                        "source_authority": "UNKNOWN", "authority_review_status": "NOT_REVIEWED",
                        "chronology": chronology_annotation(qa["question_ts"],
                                                             p["original_source_record"]["timestamp"])}
                       for p in q["parents"]]
        envelopes.append({"persistence_schema": VERSION, "frame_id": frame["frame_id"],
            "question_order": q["question_order"], "record": deepcopy(q),
            "audit": {"source_authority": "UNKNOWN", "scientific_approval": "NOT_GRANTED",
                      "historical_gold": {k: deepcopy(source[k]) for k in ("gold_chunk_ids", "gold_validated")},
                      "parent_annotations": annotations}})
        for a in q["parent_chunk_audits"]:
            require(a["parameters"] == {k: config["chunking"][k] for k in schema.LIMITS}
                    and a["tokenizer"]["model_id"] == config["chunking"]["tokenizer_model"]
                    and a["tokenizer"]["revision"] == config["chunking"]["tokenizer_revision"],
                    "CONSTRUCTION_CONFIG_MISMATCH")
            if config["chunking"]["tokenizer_assets_sha256"] is not None:
                require(dict(a["tokenizer"]["asset_hashes"]) == config["chunking"]["tokenizer_assets_sha256"],
                        "CONFIG_ASSET_MISMATCH")
            if config["chunking"]["tokenizer_runtime_version"] is not None:
                require(a["tokenizer"]["runtime_version"] == config["chunking"]["tokenizer_runtime_version"],
                        "CONFIG_RUNTIME_MISMATCH")
            profiles.append(a["tokenizer"])
            configs.append(a["chunking_config_sha256"])
            representation.append({"parent_occurrence_id": a["parent_occurrence_id"],
                                   "review_flags": a["review_flags"],
                                   "representation_status": a["representation_status"]})
    configs = sorted(set(configs))
    unique_profiles = [decode_json(x) for x in sorted({encode_json(p) for p in profiles})]
    assets = {} if tokenizer_assets is None else tokenizer_assets
    receipt_status = _receipt(tokenizer_receipt, assets, unique_profiles, configs,
                              frame["scope"], require_tokenizer_verification)
    files = {INPUT_NAMES[k]: v for k, v in input_artifacts.items()}
    files["configuration.yaml"] = configuration_bytes
    files["pool.jsonl"] = b"".join(encode_json(e) + b"\n" for e in envelopes)
    if tokenizer_receipt is not None:
        files["tokenizer/receipt.json"] = tokenizer_receipt
    files.update({"tokenizer/assets/" + k: v for k, v in assets.items()})
    sequences = {"questions": [q["canonical_question_id"] for q in records],
                 "parent_occurrences": [p["parent_occurrence_id"] for q in records for p in q["parents"]],
                 "canonical_children": [c["canonical_child_id"] for q in records for c in q["candidates"]],
                 "child_occurrences": [c["child_occurrence_id"] for q in records for c in q["candidates"]]}
    manifest = {"persistence_schema": VERSION, "schema_version": schema.SCHEMA,
        "identity_version": schema.IDENTITY_VERSION, "frame": deepcopy(frame),
        "configuration": config,
        "files": {k: {"sha256": sha(v), "bytes": len(v)} for k, v in files.items()},
        "implementation_sha256": {k: sha((ROOT / k).read_bytes()) for k in IMPLEMENTATIONS},
        "ordered_identities": sequences,
        "identity_sequence_sha256": {k: sha(encode_json(v)) for k, v in sequences.items()},
        "expected_counts": {k: len(v) for k, v in sequences.items()},
        "tokenizer": {"profiles": unique_profiles, "construction_config_sha256": configs,
                      "verification": receipt_status},
        "representation_review": representation,
        "limitations": ["Recorded dates and hashes do not authenticate sources.",
                        "Tokenizer behavior is not reexecuted by persistence.",
                        "Semantic and temporal validity remain UNKNOWN; review flags are retained."],
        "scientific_approval": "NOT_GRANTED", "scientific_validation": "NOT_VALIDATED",
        "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}
    files["manifest.json"] = encode_json(manifest) + b"\n"
    return files, sha(files["manifest.json"])


def _read_files(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink()
            and not (hasattr(directory, "is_junction") and directory.is_junction()), "PACKAGE_DIRECTORY")
    result = {}
    for path in directory.rglob("*"):
        require(not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction()),
                "PACKAGE_LINK")
        if path.is_file():
            name = path.relative_to(directory).as_posix()
            _safe_name(name)
            result[name] = path.read_bytes()
    return result


def read_package(directory, *, expected_manifest_sha256, require_tokenizer_verification=False):
    """Revalidate complete package and current implementation; return envelopes, manifest."""
    schema.digest(expected_manifest_sha256)
    files = _read_files(directory)
    require("manifest.json" in files and sha(files["manifest.json"]) == expected_manifest_sha256,
            "MANIFEST_CHECKSUM")
    manifest = decode_json(files["manifest.json"])
    require(type(manifest) is dict and type(manifest.get("files")) is dict, "MANIFEST_FIELDS")
    require(set(files) == set(manifest["files"]) | {"manifest.json"}, "PACKAGE_FILE_SET")
    for name, binding in manifest["files"].items():
        require(binding == {"sha256": sha(files[name]), "bytes": len(files[name])}, "FILE_CHECKSUM:" + name)
    envelopes = _jsonl(files["pool.jsonl"])
    require(all(type(e) is dict and "record" in e for e in envelopes), "ENVELOPE_FIELDS")
    assets = {k.removeprefix("tokenizer/assets/"): v for k, v in files.items()
              if k.startswith("tokenizer/assets/")}
    expected, digest = serialize_package([e["record"] for e in envelopes], manifest["frame"],
        input_artifacts={k: files[v] for k, v in INPUT_NAMES.items()},
        configuration_bytes=files["configuration.yaml"],
        tokenizer_receipt=files.get("tokenizer/receipt.json"), tokenizer_assets=assets,
        require_tokenizer_verification=require_tokenizer_verification)
    require(digest == expected_manifest_sha256 and expected == files, "PACKAGE_RECONSTRUCTION_MISMATCH")
    return envelopes, manifest


def validate_roundtrip(directory, *, expected_manifest_sha256, expected_records, expected_frame,
                       require_tokenizer_verification=False):
    envelopes, manifest = read_package(directory, expected_manifest_sha256=expected_manifest_sha256,
        require_tokenizer_verification=require_tokenizer_verification)
    require(encode_json([e["record"] for e in envelopes]) == encode_json(expected_records)
            and encode_json(manifest["frame"]) == encode_json(expected_frame), "ROUNDTRIP_SOURCE_MISMATCH")
    return {"status": "MECHANICAL_PASS", "counts": manifest["expected_counts"],
            "scientific_approval": "NOT_GRANTED"}


def _rename_no_replace(source, destination):
    if os.name == "nt":
        os.rename(source, destination)  # Windows rename refuses existing destinations.
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        require(hasattr(libc, "renameat2"), "ATOMIC_NOREPLACE_UNAVAILABLE")
        result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
        if result:
            raise OSError(ctypes.get_errno(), "atomic no-replace publication failed")
    else:
        raise schema.SchemaError("ATOMIC_NOREPLACE_UNAVAILABLE")


def publish_package(destination, records, frame, *, workspace_root, input_artifacts,
                    configuration_bytes, tokenizer_receipt=None, tokenizer_assets=None,
                    require_tokenizer_verification=False):
    """Publish a validated NEW directory below data/processed/week4_v2, never overwrite."""
    root = Path(workspace_root).resolve(strict=True)
    namespace = root / "data" / "processed" / "week4_v2"
    destination = Path(destination).absolute()
    require(destination.parent == namespace and destination.name not in ("", ".", "..")
            and not destination.name.startswith(".v2-stage-"), "V2_DESTINATION_REQUIRED")
    for part in (root / "data", root / "data/processed", namespace):
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()),
                "DESTINATION_LINK")
    require(not destination.exists() and not destination.is_symlink(), "NO_OVERWRITE")
    files, digest = serialize_package(records, frame, input_artifacts=input_artifacts,
        configuration_bytes=configuration_bytes, tokenizer_receipt=tokenizer_receipt,
        tokenizer_assets=tokenizer_assets, require_tokenizer_verification=require_tokenizer_verification)
    namespace.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".v2-stage-", dir=namespace))
    try:
        for name, raw in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        validate_roundtrip(stage, expected_manifest_sha256=digest, expected_records=records,
                           expected_frame=frame, require_tokenizer_verification=require_tokenizer_verification)
        _rename_no_replace(stage, destination)
    finally:
        if stage.exists():
            require(stage.resolve().parent == namespace.resolve() and stage.name.startswith(".v2-stage-"),
                    "STAGING_CLEANUP_BOUNDARY")
            shutil.rmtree(stage)
    return digest
