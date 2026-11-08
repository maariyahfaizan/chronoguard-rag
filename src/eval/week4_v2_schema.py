"""Opt-in construction schema. No models, I/O at import, scoring or approvals.

Mechanical validity never grants semantic validity or execution authorization.
The constructors copy inputs; validators recompute identities rather than trust
caller-supplied digest strings. Original identifiers remain opaque Unicode.
"""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "streamingqa_week4_v2_1"
SPEC = "streamingqa_week4_v2_spec_1"
ALGORITHM = "streamingqa_source_slice_v2_1"
TOKENIZER = "BAAI/bge-reranker-base"
REVISION = "2cfc18c9415c912f9d8155881c133215df768a70"
LIMITS = {"max_tokens": 320, "requested_overlap": 64, "max_chars": 1500}
# A9 supersedes A2's split-ID, config-free child and parent-local occurrence
# bindings. Existing snapshot/config schemas stay opt-in; old identity records
# are rejected rather than silently interpreted under these new domains.
IDENTITY_VERSION = "streamingqa_identity_a9_v1"
PARENT_SOURCE_DOMAIN = "sqa-parent-source-a9-v1"
CHILD_DOMAIN = "sqa-child-a9-v1"
CHILD_OCCURRENCE_DOMAIN = "sqa-child-occurrence-a9-v1"


class SchemaError(ValueError):
    """Stable error code followed by a diagnostic; never a silent repair."""


def require(condition, code):
    if not condition:
        raise SchemaError(code)


def text(value, name="text"):
    require(type(value) is str and bool(value.strip()), "INVALID_" + name)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise SchemaError("INVALID_UNICODE_" + name) from exc
    return value


def integer(value, name, minimum=0):
    require(type(value) is int and value >= minimum, "INVALID_" + name)
    return value


def sha256_bytes(value):
    require(type(value) is bytes, "HASH_REQUIRES_BYTES")
    return hashlib.sha256(value).hexdigest()


def text_sha256(value):
    require(type(value) is str, "TEXT_HASH_REQUIRES_STRING")
    try:
        return sha256_bytes(value.encode("utf-8", errors="strict"))
    except UnicodeError as exc:
        raise SchemaError("INVALID_UNICODE") from exc


def digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "INVALID_SHA256")
    return value


def canonical_bytes(value):
    active = set()
    def check(v):
        if type(v) is str:
            text_sha256(v)
        elif v is None or type(v) in (int, bool):
            return
        elif type(v) is list:
            require(id(v) not in active, "CYCLIC_CONTAINER")
            active.add(id(v))
            for x in v:
                check(x)
            active.remove(id(v))
        elif type(v) is dict:
            require(id(v) not in active, "CYCLIC_CONTAINER")
            active.add(id(v))
            require(all(type(k) is str for k in v), "NONSTRING_JSON_KEY")
            for k, x in v.items():
                check(k)
                check(x)
            active.remove(id(v))
        else:
            raise SchemaError("UNSUPPORTED_CANONICAL_TYPE")
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def identity(domain, *parts):
    return domain + ":" + sha256_bytes(canonical_bytes([domain, *parts]))


def bound_id(value, domain):
    require(type(value) is str and value.startswith(domain + ":"), "INVALID_ID_DOMAIN")
    digest(value[len(domain) + 1:])
    return value


def question_identity(raw_eval_sha256, question_id):
    return identity("sqa-q-v2", digest(raw_eval_sha256), text(question_id, "QA_ID"))


def opaque_source_id(value):
    """Validate UTF-8 encodability without trimming, splitting or normalizing."""
    require(type(value) is str and len(value) > 0, "INVALID_PARENT_ID")
    text_sha256(value)
    return value


def parent_source_identity(doc_id, parent_text_sha256):
    """Identity of exact source ID + exact UTF-8 text hash, not source authority."""
    return identity(PARENT_SOURCE_DOMAIN, opaque_source_id(doc_id), digest(parent_text_sha256))


def source_ids(parent_id, parent_text_sha256):
    """Keep the existing field projection, but never infer an article key.

    claimed_source_document_id now retains the ENTIRE original opaque doc_id.
    canonical_parent_passage_id is an alias of the content-bound parent source
    identity. None of these fields authenticates an article or publication date.
    """
    original = opaque_source_id(parent_id)
    document = identity("sqa-source-document-a9-v1", original)
    return original, document, parent_source_identity(original, parent_text_sha256)


def parent_occurrence_identity(frame_id, question_id, slot):
    return identity("sqa-po-v2", bound_id(frame_id, "sqa-frame-v2"),
                    bound_id(question_id, "sqa-q-v2"), integer(slot, "PARENT_SLOT"))


def child_identity(parent_source_id, child_sha256, start, end, *, chunking_config_sha256):
    """Canonical source span/config; no question or candidate position.

    Keyword-only configuration prevents old five-positional-argument A2 calls
    from silently being interpreted as the A9 binding.
    """
    integer(start, "START")
    require(type(end) is int and end > start, "INVALID_END")
    return identity(CHILD_DOMAIN, bound_id(parent_source_id, PARENT_SOURCE_DOMAIN),
                    digest(child_sha256), start, end, digest(chunking_config_sha256))


def child_occurrence_identity(question_row, candidate_slot, child_id):
    """Unique evaluated-pool position + canonical child; frame-scoped address."""
    return identity(CHILD_OCCURRENCE_DOMAIN, integer(question_row, "QUESTION_ROW"),
                    integer(candidate_slot, "CANDIDATE_SLOT"), bound_id(child_id, CHILD_DOMAIN))


def make_frame(question_ids, raw_eval_sha256, sample_sha256, parent_pool_sha256,
               *, synthetic=False):
    require(type(question_ids) is list and bool(question_ids), "INVALID_FRAME_IDS")
    require(type(synthetic) is bool, "INVALID_SYNTHETIC_FLAG")
    for q in question_ids:
        text(q, "QA_ID")
    require(len(set(question_ids)) == len(question_ids), "DUPLICATE_QUESTION_ID")
    if synthetic:
        require(all(q.startswith("synthetic-") for q in question_ids), "SYNTHETIC_NAMESPACE")
    else:
        require(len(question_ids) == 100, "FIXED_FRAME_REQUIRES_100")
    refs = [digest(x) for x in (raw_eval_sha256, sample_sha256, parent_pool_sha256)]
    return {"frame_id": identity("sqa-frame-v2", *refs, question_ids),
            "question_ids": deepcopy(question_ids), "raw_eval_sha256": refs[0],
            "sample_sha256": refs[1], "parent_pool_sha256": refs[2],
            "scope": "SYNTHETIC_ONLY" if synthetic else "FIXED_100_DEVELOPMENT"}


def validate_frame(frame):
    require(type(frame) is dict, "INVALID_FRAME")
    fields = {"frame_id", "question_ids", "raw_eval_sha256", "sample_sha256",
              "parent_pool_sha256", "scope"}
    require(set(frame) == fields, "FRAME_FIELDS")
    require(frame["scope"] in ("SYNTHETIC_ONLY", "FIXED_100_DEVELOPMENT"), "FRAME_SCOPE")
    expected = make_frame(frame["question_ids"], frame["raw_eval_sha256"],
                          frame["sample_sha256"], frame["parent_pool_sha256"],
                          synthetic=frame["scope"] == "SYNTHETIC_ONLY")
    require(frame == expected, "FRAME_IDENTITY_MISMATCH")


def validate_parameters(params, *, synthetic=False):
    require(type(params) is dict and set(params) == set(LIMITS), "PARAMETER_FIELDS")
    for key, value in params.items():
        integer(value, key, 0 if key == "requested_overlap" else 1)
    require(params["requested_overlap"] < params["max_tokens"], "INVALID_OVERLAP")
    require(params["max_tokens"] <= 320 and params["max_chars"] <= 1500, "BUDGET_EXCEEDED")
    require(synthetic or params == LIMITS, "EXPERIMENTAL_PARAMETER_CHANGE")


def unknown_time(raw_value, basis):
    # Preserve the original value/type. No timezone, publication date or truth is inferred.
    require(raw_value is None or type(raw_value) in (str, int, float), "INVALID_TIME_VALUE")
    if type(raw_value) is float:
        import math
        require(math.isfinite(raw_value), "NONFINITE_TIME")
    return {"raw_value": raw_value, "parsed_utc": None, "status": "UNKNOWN",
            "basis": basis, "authentication": "NOT_AUTHENTICATED"}


def validate_time(value):
    require(type(value) is dict and set(value) == {
        "raw_value", "parsed_utc", "status", "basis", "authentication"}, "TIME_FIELDS")
    text(value["basis"], "TIME_BASIS")
    require(value == unknown_time(value["raw_value"], value["basis"]), "UNSUPPORTED_TIME_PROMOTION")


def make_question(qa, parent_record, frame, order):
    """Convert ONE question's preserved parent occurrences, never a pool batch."""
    validate_frame(frame)
    integer(order, "QUESTION_ORDER")
    require(order < len(frame["question_ids"]), "QUESTION_ORDER_RANGE")
    require(type(qa) is dict and type(parent_record) is dict, "INPUT_RECORD_TYPES")
    required = {"qa_id", "question", "answers", "question_ts"}
    require(required <= qa.keys(), "MISSING_QA_FIELDS")
    try:
        serialized = json.dumps(qa, ensure_ascii=False, allow_nan=False)
        require(json.loads(serialized) == qa, "NON_JSON_QA_RECORD")
        serialized.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SchemaError("INVALID_ORIGINAL_QA_RECORD") from exc
    require(qa["qa_id"] == frame["question_ids"][order], "QUESTION_FRAME_BINDING")
    text(qa["question"], "QUESTION")
    answers = qa["answers"]
    require(type(answers) is list and bool(answers), "INVALID_ANSWERS")
    for answer in answers:
        text(answer, "ANSWER")
    require({"query", "gold_answer", "gold_aliases", "question_ts", "candidates"}
            <= parent_record.keys(), "MISSING_PARENT_RECORD_FIELDS")
    require((parent_record["query"], parent_record["gold_answer"],
             parent_record["gold_aliases"], parent_record["question_ts"])
            == (qa["question"], answers[0], answers, qa["question_ts"]), "ORIGINAL_KEY_DRIFT")
    candidates = parent_record["candidates"]
    require(type(candidates) is list and bool(candidates), "INVALID_PARENTS")
    require(frame["scope"] == "SYNTHETIC_ONLY" or len(candidates) == 20, "PARENT_COUNT")
    qid = question_identity(frame["raw_eval_sha256"], qa["qa_id"])
    parents = []
    for slot, c in enumerate(candidates):
        require(type(c) is dict and {"doc_id", "text", "timestamp", "is_source_document"}
                <= c.keys(), "PARENT_FIELDS")
        text(c["text"], "PARENT_TEXT")
        require(type(c["is_source_document"]) is bool, "HISTORICAL_FLAG_TYPE")
        parent_hash = text_sha256(c["text"])
        original_id, doc, pid = source_ids(c["doc_id"], parent_hash)
        parents.append({"original_parent_passage_id": c["doc_id"],
                        "claimed_source_document_id": original_id, "canonical_document_id": doc,
                        "canonical_parent_passage_id": pid, "parent_source_id": pid, "parent_slot": slot,
                        "parent_occurrence_id": parent_occurrence_identity(frame["frame_id"], qid, slot),
                        "parent_text": c["text"], "parent_text_sha256": parent_hash,
                        "original_source_record": deepcopy(c),
                        "publication_time": unknown_time(c["timestamp"], "preserved_parent_snapshot"),
                        "historical_relevance_flag": c["is_source_document"],
                        "provenance_tier": "PRESERVED_SNAPSHOT_ONLY",
                        "source_authentication": "NOT_AUTHENTICATED"})
    result = {"schema_version": SCHEMA, "specification_id": SPEC, "identity_version": IDENTITY_VERSION,
              "frame_id": frame["frame_id"], "scope": frame["scope"],
              "question_id": qa["qa_id"], "canonical_question_id": qid,
              "legacy_query_id": order, "question_order": order,
              "original_question": qa["question"], "question_text_sha256": text_sha256(qa["question"]),
              "original_answers": deepcopy(answers), "original_aliases": deepcopy(answers),
              "original_qa_record": deepcopy(qa),
              "gold_answer": answers[0], "gold_aliases": deepcopy(answers),
              "answer_key_id": identity("sqa-key-v2", qid, answers[0], answers),
              "answer_key_status": "NOT_REVIEWED", "question_time": unknown_time(qa["question_ts"], "raw_dataset_question_ts"),
              "source_parent_pool_sha256": frame["parent_pool_sha256"], "parents": parents,
              "scientific_approval": "NOT_GRANTED",
              "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}
    validate_question(result, frame)
    return deepcopy(result)


def validate_question(q, frame):
    validate_frame(frame)
    require(type(q) is dict, "INVALID_QUESTION")
    required = {"schema_version", "specification_id", "identity_version", "frame_id", "scope", "question_id",
                "canonical_question_id", "legacy_query_id", "question_order", "original_question",
                "question_text_sha256", "original_answers", "original_aliases", "gold_answer",
                "original_qa_record",
                "gold_aliases", "answer_key_id", "answer_key_status", "question_time",
                "source_parent_pool_sha256", "parents", "scientific_approval", "execution_authorization"}
    require(required <= q.keys(), "MISSING_QUESTION_FIELDS")
    extras = {"candidates", "parent_chunk_audits", "backend_verification"}
    require(set(q) == required or set(q) == required | extras, "QUESTION_FIELDS")
    require(q["schema_version"] == SCHEMA and q["specification_id"] == SPEC, "SCHEMA_VERSION")
    require(q["identity_version"] == IDENTITY_VERSION, "IDENTITY_VERSION")
    require(q["frame_id"] == frame["frame_id"] and q["scope"] == frame["scope"], "FRAME_BINDING")
    index = integer(q["question_order"], "QUESTION_ORDER")
    require(type(q["legacy_query_id"]) is int and q["legacy_query_id"] == index, "LEGACY_ORDER")
    require(index < len(frame["question_ids"]) and q["question_id"] == frame["question_ids"][index], "QUESTION_FRAME_BINDING")
    cq = question_identity(frame["raw_eval_sha256"], q["question_id"])
    require(q["canonical_question_id"] == cq, "QUESTION_IDENTITY")
    raw = q["original_qa_record"]
    require(type(raw) is dict and {"qa_id", "question", "answers", "question_ts"} <= raw.keys(), "ORIGINAL_QA_FIELDS")
    try:
        serialized = json.dumps(raw, ensure_ascii=False, allow_nan=False)
        require(json.loads(serialized) == raw, "NON_JSON_QA_RECORD")
        serialized.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise SchemaError("INVALID_ORIGINAL_QA_RECORD") from exc
    require((raw["qa_id"], raw["question"], raw["answers"])
            == (q["question_id"], q["original_question"], q["original_answers"]), "ORIGINAL_QA_BINDING")
    text(q["original_question"], "QUESTION")
    require(q["question_text_sha256"] == text_sha256(q["original_question"]), "QUESTION_TEXT_HASH")
    a = q["original_answers"]
    require(type(a) is list and bool(a), "INVALID_ANSWERS")
    for answer in a:
        text(answer, "ANSWER")
    require(type(q["original_aliases"]) is list and type(q["gold_aliases"]) is list and
            q["original_aliases"] == q["gold_aliases"] == a and q["gold_answer"] == a[0], "ANSWER_ALIAS_DRIFT")
    require(q["answer_key_id"] == identity("sqa-key-v2", cq, a[0], a), "ANSWER_KEY_IDENTITY")
    require(q["answer_key_status"] == "NOT_REVIEWED", "UNSUPPORTED_KEY_APPROVAL")
    require(q["source_parent_pool_sha256"] == frame["parent_pool_sha256"], "SOURCE_HASH_BINDING")
    require(q["scientific_approval"] == "NOT_GRANTED" and
            q["execution_authorization"] == "NOT_AUTHORIZED_FOR_EXECUTION", "UNSUPPORTED_AUTHORIZATION")
    validate_time(q["question_time"])
    require(q["question_time"]["raw_value"] == raw["question_ts"], "QUESTION_TIME_BINDING")
    require(type(q["parents"]) is list and bool(q["parents"]), "INVALID_PARENTS")
    require(frame["scope"] == "SYNTHETIC_ONLY" or len(q["parents"]) == 20, "PARENT_COUNT")
    seen, source_bindings = {}, {}
    for slot, p in enumerate(q["parents"]):
        parent_fields = {"original_parent_passage_id", "claimed_source_document_id",
                "canonical_document_id", "canonical_parent_passage_id", "parent_source_id", "parent_slot", "parent_occurrence_id",
                "parent_text", "parent_text_sha256", "publication_time", "historical_relevance_flag",
                "original_source_record", "provenance_tier", "source_authentication"}
        require(type(p) is dict and set(p) == parent_fields, "PARENT_FIELDS")
        text(p["parent_text"], "PARENT_TEXT")
        actual_hash = text_sha256(p["parent_text"])
        require(p["parent_text_sha256"] == actual_hash, "PARENT_TEXT_HASH")
        original_id, document, pid = source_ids(p["original_parent_passage_id"], actual_hash)
        require((p["claimed_source_document_id"], p["canonical_document_id"], p["canonical_parent_passage_id"])
                == (original_id, document, pid) and p["parent_source_id"] == pid, "PARENT_IDENTITY")
        require(type(p["parent_slot"]) is int and p["parent_slot"] == slot and
                p["parent_occurrence_id"] == parent_occurrence_identity(frame["frame_id"], cq, slot), "PARENT_OCCURRENCE")
        validate_time(p["publication_time"])
        require(type(p["historical_relevance_flag"]) is bool, "HISTORICAL_FLAG_TYPE")
        source = p["original_source_record"]
        require(type(source) is dict and {"doc_id", "text", "timestamp", "is_source_document"} <= source.keys(), "ORIGINAL_SOURCE_FIELDS")
        try:
            serialized = json.dumps(source, ensure_ascii=False, allow_nan=False)
            require(json.loads(serialized) == source, "NON_JSON_SOURCE_RECORD")
            serialized.encode("utf-8", errors="strict")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise SchemaError("INVALID_ORIGINAL_SOURCE_RECORD") from exc
        require(source["doc_id"] == original_id and source["text"] == p["parent_text"] and
                type(source["timestamp"]) is type(p["publication_time"]["raw_value"]) and
                source["timestamp"] == p["publication_time"]["raw_value"] and
                type(source["is_source_document"]) is bool and
                source["is_source_document"] == p["historical_relevance_flag"], "ORIGINAL_SOURCE_BINDING")
        for name in ("text_sha256", "parent_text_sha256"):
            if name in source:
                require(digest(source[name]) == actual_hash, "SOURCE_TEXT_HASH")
        require(p["provenance_tier"] == "PRESERVED_SNAPSHOT_ONLY" and
                p["source_authentication"] == "NOT_AUTHENTICATED", "UNSUPPORTED_PROVENANCE_PROMOTION")
        signature = (p["parent_text"], p["publication_time"])
        # Key conflicts by RAW ID, not the content-bound digest: otherwise a
        # changed text would obtain a new digest and evade conflict detection.
        require(original_id not in seen or seen[original_id] == signature, "PARENT_IDENTITY_COLLISION")
        seen[original_id] = signature
        binding = (original_id, actual_hash, p["parent_text"])
        require(pid not in source_bindings or source_bindings[pid] == binding, "PARENT_IDENTITY_COLLISION")
        source_bindings[pid] = binding


def validate_frame_records(records, frame):
    """Validate source-frame completeness/order and cross-question collisions.

    This is not a substitute for validate_pool on each constructed child pool.
    """
    validate_frame(frame)
    require(type(records) is list and len(records) == len(frame["question_ids"]), "FRAME_COMPLETENESS")
    canonical_parents, source_bindings = {}, {}
    for index, record in enumerate(records):
        validate_question(record, frame)
        require(record["question_order"] == index, "FRAME_RECORD_ORDER")
        for parent in record["parents"]:
            key = parent["original_parent_passage_id"]
            signature = (parent["parent_text"], parent["publication_time"])
            require(key not in canonical_parents or canonical_parents[key] == signature,
                    "CROSS_QUESTION_PARENT_COLLISION")
            canonical_parents[key] = signature
            pid = parent["parent_source_id"]
            binding = (key, parent["parent_text_sha256"], parent["parent_text"])
            require(pid not in source_bindings or source_bindings[pid] == binding,
                    "CROSS_QUESTION_PARENT_COLLISION")
            source_bindings[pid] = binding


def verify_source_files(config, root):
    """Explicit, read-only verification of the THREE configured source files.

    This establishes bytes relative to the configured references, not original
    publication authenticity. It does not chunk or select any question.
    """
    validate_config(config)
    root = Path(root).resolve()
    verified = {}
    for role in ("raw_eval", "sample", "parent_pool"):
        path = (root / config["frame"][role + "_path"]).resolve()
        require(path.is_relative_to(root) and path.is_file(), "SOURCE_PATH")
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(block)
        require(h.hexdigest() == config["frame"][role + "_sha256"], "SOURCE_FILE_HASH")
        verified[role] = h.hexdigest()
    return verified


def load_bound_sources(config, root):
    """Read/validate the original frame and parent snapshot; never build children.

    Pure frame hashing does not establish membership in the original snapshot.
    This explicit boundary verifies the configured files and their actual rows.
    """
    verify_source_files(config, root)
    root = Path(root).resolve()
    rows = {}
    for role in ("sample", "parent_pool"):
        path = (root / config["frame"][role + "_path"]).resolve()
        require(path.is_relative_to(root) and path.is_file(), "SOURCE_PATH")
        # Read once and verify AGAIN to bind parsed bytes, not a previous open.
        content = path.read_bytes()
        require(sha256_bytes(content) == config["frame"][role + "_sha256"], "SOURCE_FILE_HASH")
        lines = content.splitlines()
        require(len(lines) == 100 and all(line.strip() for line in lines), "FIXED_FRAME_COMPLETENESS")
        try:
            rows[role] = [json.loads(line) for line in lines]
        except (ValueError, UnicodeError) as exc:
            raise SchemaError("INVALID_SOURCE_JSONL") from exc
    sample, parents = rows["sample"], rows["parent_pool"]
    require(all(type(q) is dict and "qa_id" in q for q in sample), "SOURCE_QA_ID")
    f = config["frame"]
    frame = make_frame([q["qa_id"] for q in sample], f["raw_eval_sha256"],
                       f["sample_sha256"], f["parent_pool_sha256"])
    return frame, deepcopy(sample), deepcopy(parents)


def validate_against_sources(question, frame, original_qa, original_parent_record):
    """Detect coherently rehashed source/key edits against supplied source rows.

    Callers must obtain those rows via load_bound_sources, not from a record
    under validation. Neither a digest nor this check authenticates publication.
    """
    expected = make_question(original_qa, original_parent_record, frame, question["question_order"])
    validate_question(question, frame)
    require(all(question[k] == value for k, value in expected.items()), "AUTHORITATIVE_SOURCE_DRIFT")


def load_config(path):
    # Optional existing YAML dependency; no model dependency or implicit activation.
    import yaml
    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        pairs = loader.construct_pairs(node, deep=deep)
        require(all(type(k) is str for k, _ in pairs), "CONFIG_KEY_TYPE")
        require(len({k for k, _ in pairs}) == len(pairs), "DUPLICATE_CONFIG_KEY")
        return dict(pairs)

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    with Path(path).open(encoding="utf-8") as handle:
        config = yaml.load(handle, Loader=UniqueLoader)
    validate_config(config)
    return deepcopy(config)


def validate_config(config):
    require(type(config) is dict, "INVALID_CONFIG")
    require(set(config) == {"schema_version", "specification_id", "enabled_by_default", "frame",
            "systems", "chunking", "reproducibility", "identity_policy", "duplicate_policy",
            "relevance_rubric", "unknown_policy", "scientific_validation", "execution_authorization"}, "CONFIG_FIELDS")
    require(config.get("schema_version") == SCHEMA and config.get("specification_id") == SPEC, "CONFIG_VERSION")
    require(config.get("enabled_by_default") is False, "OPT_IN_REQUIRED")
    require(config.get("systems") == ["E1", "E2", "E3", "E4"], "SYSTEMS_CHANGED")
    f = config.get("frame")
    require(type(f) is dict and f.get("size") == 100 and type(f.get("size")) is int
            and type(f.get("parent_occurrences_per_question")) is int and
            f.get("parent_occurrences_per_question") == 20 and
            f.get("ordering") == "original_sample_jsonl_order", "CONFIG_FRAME")
    require(set(f) == {"size", "ordering", "sample_path", "sample_sha256", "raw_eval_path",
            "raw_eval_sha256", "parent_pool_path", "parent_pool_sha256", "parent_occurrences_per_question"}, "CONFIG_FRAME_FIELDS")
    for key in ("sample", "raw_eval", "parent_pool"):
        text(f.get(key + "_path"), "SOURCE_PATH")
        digest(f.get(key + "_sha256"))
    c = config.get("chunking")
    require(type(c) is dict and c.get("algorithm_id") == ALGORITHM, "CONFIG_ALGORITHM")
    require(set(c) == {"algorithm_id", *LIMITS, "normalization", "tail_merge", "tokenizer_model",
            "tokenizer_revision", "tokenizer_assets_sha256", "tokenizer_runtime_version", "offset_verification"}, "CONFIG_CHUNK_FIELDS")
    validate_parameters({k: c.get(k) for k in LIMITS})
    require(c.get("normalization") == "NONE" and c.get("tail_merge") is False, "TEXT_POLICY")
    require(c.get("tokenizer_model") == TOKENIZER and c.get("tokenizer_revision") == REVISION, "TOKENIZER_TARGET")
    assets = c["tokenizer_assets_sha256"]
    require(assets is None or (type(assets) is dict and bool(assets)), "ASSET_MANIFEST")
    if assets is not None:
        for path, sha in assets.items():
            text(path, "ASSET_PATH")
            digest(sha)
    require(c["tokenizer_runtime_version"] is None or
            (type(c["tokenizer_runtime_version"]) is str and bool(c["tokenizer_runtime_version"].strip())), "RUNTIME_VERSION")
    require(c["offset_verification"] in ("UNVERIFIED", "VERIFIED"), "OFFSET_VERIFICATION")
    r = config.get("reproducibility")
    require(type(r) is dict and set(r) == {"proposed_seed", "actual_runtime", "actual_devices",
            "deterministic_execution_verified"}, "REPRODUCIBILITY_FIELDS")
    require(type(r["proposed_seed"]) is int and r["proposed_seed"] == 42, "SEED_CHANGED")
    require(r["actual_runtime"] is None or type(r["actual_runtime"]) is dict, "ACTUAL_RUNTIME_TYPE")
    require(r["actual_devices"] is None or type(r["actual_devices"]) is list, "DEVICE_TYPE")
    require(type(r["deterministic_execution_verified"]) is bool, "DETERMINISM_TYPE")
    require(config.get("identity_policy") == "source_qualified_span_v2" and
            config.get("duplicate_policy") == "preserve_occurrences_unique_canonical_credit", "IDENTITY_POLICY")
    require(config.get("relevance_rubric") == "sqa_child_support_graded_v2_1" and
            config.get("unknown_policy") == "never_coerce_to_negative_or_drop", "RELEVANCE_POLICY")
    require(config.get("scientific_validation") == "NOT_VALIDATED" and
            config.get("execution_authorization") == "NOT_AUTHORIZED_FOR_EXECUTION", "CONFIG_AUTHORIZATION")


def execution_preflight(config):
    """This construction checkpoint provides no execution-authority verifier."""
    validate_config(config)
    c = config["chunking"]
    require(c.get("tokenizer_assets_sha256") and c.get("tokenizer_runtime_version")
            and c.get("offset_verification") == "VERIFIED", "UNVERIFIED_TOKENIZER")
    raise SchemaError("EXECUTION_NOT_IMPLEMENTED_OR_AUTHORIZED")
