"""Source-slice construction for ONE question; no batch CLI or output writer.

The injected tokenizer must provide fast code-point offsets. It is never loaded
here. Declaring a model/revision is not proof of verified assets; all results
remain non-executable pending an independently verified backend input path.
"""
from copy import deepcopy
from dataclasses import dataclass
from collections.abc import Mapping

from src.eval.week4_v2_schema import (
    ALGORITHM, IDENTITY_VERSION, LIMITS, REVISION, TOKENIZER, canonical_bytes, child_identity,
    child_occurrence_identity, digest, require, sha256_bytes, text,
    text_sha256, validate_frame_records, validate_parameters, validate_question,
)

# P0-V2-A5R supersedes A2's disjoint-offset assumption. Bind this repair to
# construction hashes without changing the historical specification/schema.
OFFSET_POLICY = "monotone_offsets_source_bounds_v1"


def _offset_geometry(value, offsets, *, stored=False):
    """Validate monotone starts AND ends; derive gaps from interval union.

    A fast tokenizer may emit multiple IDs for one Unicode character, or spans
    sharing only part of their source range. Neither is source-text deletion.
    """
    previous_start, covered_end = -1, 0
    normalized, gaps = [], []
    for pair in offsets:
        require(type(pair) in ((list,) if stored else (tuple, list)) and len(pair) == 2,
                "TOKEN_AUDIT_OFFSET" if stored else "OFFSET_PAIR")
        start, end = pair
        require(type(start) is int and type(end) is int and
                0 <= start < end <= len(value) and
                start >= previous_start and end >= covered_end,
                "TOKEN_AUDIT_OFFSET" if stored else "UNSUPPORTED_OFFSET_MAPPING")
        if start > covered_end:
            gap = value[covered_end:start]
            gaps.append({"start": covered_end, "end": start, "text": gap,
                         "non_whitespace": bool(gap.strip())})
        normalized.append([start, end])
        previous_start, covered_end = start, end
    if covered_end < len(value):
        gap = value[covered_end:]
        gaps.append({"start": covered_end, "end": len(value), "text": gap,
                     "non_whitespace": bool(gap.strip())})
    return normalized, gaps


def _source_end(offsets, length, b):
    # Include the complete last token span and any gap before the next token.
    # Unlike start-only anchors, this cannot cut off a repeated/overlapping span.
    return length if b == len(offsets) else max(offsets[b - 1][1], offsets[b][0])


def _next_boundary(offsets, a, b, start, end, requested):
    """Prefer the requested parent-index overlap, reducing it for progress.

    If remaining token starts all coincide with the current source start, use
    the emitted end and zero parent-index overlap. Standalone retokenization
    remains authoritative for token budgets; parent-index overlap is NOT a
    claim of equal retokenized tokens or equal character overlap.
    """
    if b == len(offsets):
        return b, end, 0
    first = b - min(requested, b - a - 1)
    for index in range(first, b + 1):
        next_start = offsets[index][0]
        if start < next_start <= end:
            return index, next_start, b - index
    return b, end, 0


@dataclass(frozen=True)
class TokenizerProfile:
    model_id: str = TOKENIZER
    revision: str = REVISION
    scope: str = "OFFLINE_UNVERIFIED"
    offset_unit: str = "UNICODE_CODE_POINT"
    runtime_version: str | None = None
    asset_hashes: tuple = ()

    def as_record(self):
        require(self.model_id == TOKENIZER and self.revision == REVISION, "TOKENIZER_TARGET")
        require(self.scope in ("SYNTHETIC_ONLY", "OFFLINE_UNVERIFIED"), "TOKENIZER_SCOPE")
        require(self.offset_unit == "UNICODE_CODE_POINT", "UNSUPPORTED_OFFSET_UNIT")
        require(type(self.asset_hashes) is tuple, "MUTABLE_ASSET_MANIFEST")
        for pair in self.asset_hashes:
            require(type(pair) is tuple and len(pair) == 2, "ASSET_MANIFEST")
            text(pair[0], "ASSET_PATH")
            digest(pair[1])
        require(len({x[0] for x in self.asset_hashes}) == len(self.asset_hashes), "DUPLICATE_ASSET_PATH")
        require(self.runtime_version is None or type(self.runtime_version) is str, "RUNTIME_VERSION")
        return {"model_id": self.model_id, "revision": self.revision,
                "scope": self.scope, "offset_unit": self.offset_unit,
                "runtime_version": self.runtime_version,
                "asset_hashes": [list(x) for x in self.asset_hashes]}


def _tokenize(value, tokenizer):
    require(getattr(tokenizer, "is_fast", False) is True, "FAST_OFFSETS_REQUIRED")
    encoded = tokenizer(value, add_special_tokens=False, return_offsets_mapping=True,
                        truncation=False, padding=False)
    require(isinstance(encoded, Mapping) and {"input_ids", "offset_mapping"} <= encoded.keys(), "TOKENIZER_FIELDS")
    ids, offsets = encoded["input_ids"], encoded["offset_mapping"]
    require(type(ids) is list and type(offsets) is list and bool(ids)
            and len(ids) == len(offsets), "TOKEN_OFFSET_ALIGNMENT")
    require(all(type(x) is int and x >= 0 for x in ids), "TOKEN_ID_TYPE")
    normalized_offsets, gaps = _offset_geometry(value, offsets)
    unknown = []
    for token_id, (start, end) in zip(ids, normalized_offsets):
        if token_id == getattr(tokenizer, "unk_token_id", None):
            unknown.append([start, end])
    flags = []
    if any(g["non_whitespace"] for g in gaps):
        flags.append("NON_WHITESPACE_TOKENIZER_GAP")
    if unknown:
        flags.append("UNKNOWN_TOKEN_SPAN")
    decoded_hash = None
    if callable(getattr(tokenizer, "decode", None)):
        decoded = tokenizer.decode(ids, skip_special_tokens=True)
        require(type(decoded) is str, "DECODE_DIAGNOSTIC_TYPE")
        decoded_hash = text_sha256(decoded)
        if decoded != value:
            flags.append("DECODE_DIFFERENCE_REQUIRES_REVIEW")
    else:
        flags.append("DECODE_DIAGNOSTIC_UNAVAILABLE")
    token_strings = None
    if callable(getattr(tokenizer, "convert_ids_to_tokens", None)):
        token_strings = tokenizer.convert_ids_to_tokens(ids)
        require(type(token_strings) is list and len(token_strings) == len(ids)
                and all(type(x) is str for x in token_strings), "TOKEN_STRINGS")
    return {"input_ids": deepcopy(ids), "offsets": normalized_offsets,
            "gaps": gaps, "unknown_spans": unknown, "token_strings": token_strings,
            "decoded_text_sha256": decoded_hash, "review_flags": flags}


def _validate_token_audit(value, audit):
    """Check stored offset geometry/gaps independently, without a backend call."""
    require(type(audit) is dict and set(audit) == {"input_ids", "offsets", "gaps", "unknown_spans",
            "token_strings", "decoded_text_sha256", "review_flags"}, "TOKEN_AUDIT_FIELDS")
    ids, offsets = audit["input_ids"], audit["offsets"]
    require(type(ids) is list and bool(ids) and all(type(x) is int and x >= 0 for x in ids)
            and type(offsets) is list and len(ids) == len(offsets), "TOKEN_AUDIT_BINDING")
    _, gaps = _offset_geometry(value, offsets, stored=True)
    require(audit["gaps"] == gaps, "TOKEN_AUDIT_GAPS")
    unknown = audit["unknown_spans"]
    require(type(unknown) is list and all(x in offsets for x in unknown), "TOKEN_AUDIT_UNKNOWN")
    strings = audit["token_strings"]
    require(strings is None or (type(strings) is list and len(strings) == len(ids)
            and all(type(x) is str for x in strings)), "TOKEN_AUDIT_STRINGS")
    flags = []
    if any(x["non_whitespace"] for x in gaps):
        flags.append("NON_WHITESPACE_TOKENIZER_GAP")
    if unknown:
        flags.append("UNKNOWN_TOKEN_SPAN")
    decoded_hash = audit["decoded_text_sha256"]
    if decoded_hash is None:
        flags.append("DECODE_DIAGNOSTIC_UNAVAILABLE")
    else:
        digest(decoded_hash)
        if decoded_hash != text_sha256(value):
            flags.append("DECODE_DIFFERENCE_REQUIRES_REVIEW")
    require(audit["review_flags"] == flags, "TOKEN_AUDIT_FLAGS")


def chunk_text(value, tokenizer, *, profile, parameters=None):
    """Lossless literal slices; synthetic counts never become backend counts."""
    text(value, "PARENT_TEXT")
    require(type(profile) is TokenizerProfile, "TOKENIZER_PROFILE_REQUIRED")
    profile_record = profile.as_record()
    params = deepcopy(LIMITS if parameters is None else parameters)
    validate_parameters(params, synthetic=profile.scope == "SYNTHETIC_ONLY")
    source = _tokenize(value, tokenizer)
    offsets = source["offsets"]
    n = len(offsets)
    children = []
    a, start, covered = 0, 0, 0
    while a < n:
        chosen = None
        for b in range(min(a + params["max_tokens"], n), a, -1):
            end = _source_end(offsets, len(value), b)
            if end <= covered or not 0 < end - start <= params["max_chars"]:
                continue
            literal = value[start:end]
            audit = _tokenize(literal, tokenizer)
            if len(audit["input_ids"]) <= params["max_tokens"]:
                chosen = b, start, end, literal, audit
                break
        require(chosen is not None, "UNSPLITTABLE_WITHIN_BUDGET")
        b, start, end, literal, audit = chosen
        require(end > covered, "NONADVANCING_COVERAGE")
        next_a, next_start, overlap = _next_boundary(
            offsets, a, b, start, end, params["requested_overlap"])
        children.append({"char_start": start, "char_end": end,
                         "byte_start": len(value[:start].encode("utf-8")),
                         "byte_end": len(value[:end].encode("utf-8")),
                         "child_text": literal, "child_text_sha256": text_sha256(literal),
                         "parent_token_start": a, "parent_token_end": b,
                         "standalone_token_count": len(audit["input_ids"]), "tokenization": audit,
                         "requested_overlap": params["requested_overlap"],
                         "actual_parent_token_overlap_to_next": overlap,
                         "actual_character_overlap_to_next": 0 if b == n else end - next_start,
                         "short_window_overlap": b < n and overlap < params["requested_overlap"],
                         "short_final_tail": b == n and len(audit["input_ids"]) < 64})
        covered = end
        if b == n:
            break
        require(next_a > a and next_start > start and next_start <= end, "NONADVANCING_BOUNDARY")
        a, start = next_a, next_start
    verify_coverage(value, children, params)
    all_flags = sorted(set(source["review_flags"] + [flag for c in children
                      for flag in c["tokenization"]["review_flags"]]))
    if "\ufffd" in value:
        all_flags.append("ORIGINAL_CHARACTER_UNKNOWN")
    config = {"algorithm_id": ALGORITHM, "parameters": params,
              "normalization": "NONE", "tail_merge": False, "tokenizer": profile_record,
              "offset_policy": OFFSET_POLICY, "identity_version": IDENTITY_VERSION}
    return {"algorithm_id": ALGORITHM, "offset_policy": OFFSET_POLICY, "identity_version": IDENTITY_VERSION,
            "parameters": params, "tokenizer": profile_record,
            "chunking_config_sha256": sha256_bytes(canonical_bytes(config)),
            "parent_text_sha256": text_sha256(value), "parent_tokenization": source,
            "children": children, "coverage": "EXACT_SOURCE_RECONSTRUCTION",
            "review_flags": all_flags,
            "representation_status": "REVIEW_REQUIRED" if all_flags else "NO_DIAGNOSTIC_LOSS_DETECTED",
            "backend_verification": "UNVERIFIED", "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}


def verify_coverage(parent_text, children, params):
    """Independent literal/UTF-8 coverage check, not a semantic equivalence test."""
    require(type(children) is list and bool(children), "MISSING_CHILDREN")
    covered, previous_start, stitched, seen = 0, -1, "", set()
    for c in children:
        require(type(c) is dict and {"char_start", "char_end", "child_text", "child_text_sha256",
                "byte_start", "byte_end", "standalone_token_count"} <= c.keys(), "CHILD_SPAN_FIELDS")
        start, end = c["char_start"], c["char_end"]
        require(type(start) is int and type(end) is int and
                0 <= start <= covered < end <= len(parent_text) and start > previous_start, "CHILD_COVERAGE")
        require((start, end) not in seen, "DUPLICATE_CHILD_SPAN")
        seen.add((start, end))
        literal = parent_text[start:end]
        require(c["child_text"] == literal and c["child_text_sha256"] == text_sha256(literal), "CHILD_TEXT_BINDING")
        require(type(c["byte_start"]) is int and type(c["byte_end"]) is int and
                (c["byte_start"], c["byte_end"]) == (len(parent_text[:start].encode("utf-8")),
                len(parent_text[:end].encode("utf-8"))), "CHILD_BYTE_OFFSETS")
        require(type(c["standalone_token_count"]) is int and
                0 < c["standalone_token_count"] <= params["max_tokens"] and
                len(literal) <= params["max_chars"], "CHILD_BUDGET")
        stitched += literal[covered - start:]
        covered, previous_start = end, start
    require(covered == len(parent_text) and stitched == parent_text and
            stitched.encode("utf-8") == parent_text.encode("utf-8"), "PARENT_RECONSTRUCTION")


def chunk_question(question, frame, tokenizer, *, profile, parameters=None):
    """Construct a single diagnostic question, retaining every parent occurrence."""
    validate_question(question, frame)
    require(type(profile) is TokenizerProfile, "TOKENIZER_PROFILE_REQUIRED")
    require(frame["scope"] == profile.scope or
            (frame["scope"] == "FIXED_100_DEVELOPMENT" and profile.scope == "OFFLINE_UNVERIFIED"),
            "TOKENIZER_FRAME_SCOPE")
    out = deepcopy(question)
    out["candidates"] = []
    out["parent_chunk_audits"] = []
    for p in question["parents"]:
        plan = chunk_text(p["parent_text"], tokenizer, profile=profile, parameters=parameters)
        out["parent_chunk_audits"].append({"parent_occurrence_id": p["parent_occurrence_id"],
                                          **{k: deepcopy(v) for k, v in plan.items() if k != "children"}})
        for index, span in enumerate(plan["children"]):
            child = deepcopy(span)
            cid = child_identity(p["parent_source_id"], span["child_text_sha256"],
                                 span["char_start"], span["char_end"],
                                 chunking_config_sha256=plan["chunking_config_sha256"])
            child.update({"canonical_child_id": cid, "child_occurrence_id": child_occurrence_identity(
                question["question_order"], len(out["candidates"]), cid),
                "canonical_parent_passage_id": p["canonical_parent_passage_id"],
                "parent_source_id": p["parent_source_id"],
                "original_parent_passage_id": p["original_parent_passage_id"],
                "parent_occurrence_id": p["parent_occurrence_id"], "parent_slot": p["parent_slot"],
                "local_child_index": index, "candidate_slot": len(out["candidates"]),
                "chunking_config_sha256": plan["chunking_config_sha256"],
                "publication_time": deepcopy(p["publication_time"]),
                "provenance_tier": p["provenance_tier"], "source_authentication": p["source_authentication"],
                "relevance_grade": "UNKNOWN", "semantic_review_status": "NOT_REVIEWED",
                "semantic_review_refs": [], "temporal_validity": "UNKNOWN", "temporal_review_refs": [],
                "scientific_approval": "NOT_GRANTED"})
            out["candidates"].append(child)
    out["backend_verification"] = "UNVERIFIED"
    validate_pool(out, frame)
    return out


def validate_pool(question, frame, *, original_question=None):
    """Validate all occurrences against authoritative parent strings in this record.

    Supplying the original pre-chunk question additionally detects coherently
    rehashed source edits. File authenticity is a separate external requirement.
    """
    validate_question(question, frame)
    if original_question is not None:
        validate_question(original_question, frame)
        require(all(question[k] == v for k, v in original_question.items()), "AUTHORITATIVE_SOURCE_DRIFT")
    require(question.get("backend_verification") == "UNVERIFIED", "UNSUPPORTED_BACKEND_PROMOTION")
    children, audits = question.get("candidates"), question.get("parent_chunk_audits")
    require(type(children) is list and bool(children) and type(audits) is list
            and len(audits) == len(question["parents"]), "POOL_FIELDS")
    groups = [[] for _ in question["parents"]]
    occurrences, canonical, last_parent = set(), {}, -1
    for slot, c in enumerate(children):
        required = {"candidate_slot", "parent_slot", "local_child_index", "parent_occurrence_id",
                    "canonical_parent_passage_id", "parent_source_id", "original_parent_passage_id",
                    "canonical_child_id", "child_occurrence_id",
                    "chunking_config_sha256", "publication_time", "provenance_tier", "source_authentication",
                    "relevance_grade", "semantic_review_status", "semantic_review_refs",
                    "temporal_validity", "temporal_review_refs", "scientific_approval", "tokenization"}
        require(type(c) is dict and required <= c.keys(), "MISSING_CHILD_FIELDS")
        span_fields = {"char_start", "char_end", "byte_start", "byte_end", "child_text", "child_text_sha256",
                       "parent_token_start", "parent_token_end", "standalone_token_count", "requested_overlap",
                       "actual_parent_token_overlap_to_next", "actual_character_overlap_to_next",
                       "short_window_overlap", "short_final_tail"}
        require(set(c) == required | span_fields, "UNKNOWN_CHILD_FIELDS")
        require(type(c["candidate_slot"]) is int and c["candidate_slot"] == slot, "CANDIDATE_SLOT")
        ps = c["parent_slot"]
        require(type(ps) is int and 0 <= ps < len(groups) and last_parent <= ps, "CHILD_PARENT_ORDER")
        last_parent = ps
        parent = question["parents"][ps]
        require(c["parent_occurrence_id"] == parent["parent_occurrence_id"] and
                c["canonical_parent_passage_id"] == parent["canonical_parent_passage_id"] and
                c["parent_source_id"] == parent["parent_source_id"] and
                c["original_parent_passage_id"] == parent["original_parent_passage_id"], "CHILD_LINEAGE")
        require(type(c["local_child_index"]) is int and c["local_child_index"] == len(groups[ps]), "CHILD_INDEX")
        groups[ps].append(c)
        for key in ("publication_time", "provenance_tier", "source_authentication"):
            require(c[key] == parent[key], "CHILD_METADATA_DRIFT")
        grade = c["relevance_grade"]
        require((type(grade) is int and grade in (0, 1, 2)) or
                (type(grade) is str and grade == "UNKNOWN"), "INVALID_RELEVANCE_GRADE")
        require(type(c["semantic_review_refs"]) is list and type(c["temporal_review_refs"]) is list, "REVIEW_REFS_TYPE")
        require(all(type(r) is str and r.strip() for r in c["semantic_review_refs"] + c["temporal_review_refs"]), "REVIEW_REF")
        require(c["semantic_review_status"] in ("NOT_REVIEWED", "REVIEWED_UNRESOLVED", "REVIEWED_PROVISIONAL", "ADJUDICATED"), "REVIEW_STATUS")
        require((grade == "UNKNOWN" and c["semantic_review_status"] in ("NOT_REVIEWED", "REVIEWED_UNRESOLVED"))
                or (type(grade) is int and c["semantic_review_status"] in ("REVIEWED_PROVISIONAL", "ADJUDICATED")
                    and bool(c["semantic_review_refs"])), "CONFLICTING_SEMANTIC_REVIEW")
        require(c["semantic_review_status"] != "NOT_REVIEWED" or not c["semantic_review_refs"], "CONFLICTING_SEMANTIC_REVIEW")
        require(c["semantic_review_status"] != "REVIEWED_UNRESOLVED" or bool(c["semantic_review_refs"]), "CONFLICTING_SEMANTIC_REVIEW")
        require(c["temporal_validity"] in ("UNKNOWN", "YES", "NO", "NOT_APPLICABLE"), "TEMPORAL_STATE")
        require(c["temporal_validity"] == "UNKNOWN" or bool(c["temporal_review_refs"]), "MISSING_TEMPORAL_REVIEW")
        require(c["scientific_approval"] == "NOT_GRANTED", "UNSUPPORTED_SCIENTIFIC_APPROVAL")
        cid = child_identity(parent["parent_source_id"], c.get("child_text_sha256"),
                             c.get("char_start"), c.get("char_end"),
                             chunking_config_sha256=c["chunking_config_sha256"])
        require(c["canonical_child_id"] == cid, "CHILD_IDENTITY")
        binding = (parent["parent_source_id"], c.get("child_text"), c.get("child_text_sha256"),
                   c.get("char_start"), c.get("char_end"), c["chunking_config_sha256"])
        require(cid not in canonical or canonical[cid] == binding, "CHILD_IDENTITY_COLLISION")
        canonical[cid] = binding
        expected = child_occurrence_identity(question["question_order"], c["candidate_slot"], cid)
        require(c["child_occurrence_id"] == expected, "CHILD_OCCURRENCE_IDENTITY")
        require(expected not in occurrences, "DUPLICATE_CHILD_OCCURRENCE")
        occurrences.add(expected)
    for parent, group, audit in zip(question["parents"], groups, audits):
        require(type(audit) is dict and {"parent_occurrence_id", "algorithm_id", "parameters", "tokenizer",
                "chunking_config_sha256", "parent_text_sha256", "coverage", "backend_verification"} <= audit.keys(), "AUDIT_FIELDS")
        require(audit["parent_occurrence_id"] == parent["parent_occurrence_id"] and
                audit["parent_text_sha256"] == parent["parent_text_sha256"] and
                audit["algorithm_id"] == ALGORITHM and audit["backend_verification"] == "UNVERIFIED", "AUDIT_BINDING")
        require(audit["coverage"] == "EXACT_SOURCE_RECONSTRUCTION", "AUDIT_COVERAGE")
        require(audit.get("offset_policy") == OFFSET_POLICY, "UNSUPPORTED_OFFSET_POLICY")
        require(audit.get("identity_version") == IDENTITY_VERSION, "AUDIT_IDENTITY_VERSION")
        tr = audit["tokenizer"]
        require(type(tr) is dict and set(tr) == {"model_id", "revision", "scope", "offset_unit",
                "runtime_version", "asset_hashes"} and type(tr["asset_hashes"]) is list, "TOKENIZER_AUDIT_FIELDS")
        require(all(type(x) is list and len(x) == 2 for x in tr["asset_hashes"]), "ASSET_MANIFEST")
        profile = TokenizerProfile(tr["model_id"], tr["revision"], tr["scope"], tr["offset_unit"],
                                   tr["runtime_version"], tuple(tuple(x) for x in tr["asset_hashes"]))
        require(profile.as_record() == tr and (tr["scope"] == frame["scope"] or
                (frame["scope"] == "FIXED_100_DEVELOPMENT" and tr["scope"] == "OFFLINE_UNVERIFIED")), "TOKENIZER_FRAME_SCOPE")
        validate_parameters(audit["parameters"], synthetic=frame["scope"] == "SYNTHETIC_ONLY")
        require("parent_tokenization" in audit, "MISSING_PARENT_TOKEN_AUDIT")
        _validate_token_audit(parent["parent_text"], audit["parent_tokenization"])
        config = {"algorithm_id": ALGORITHM, "parameters": audit["parameters"],
                  "normalization": "NONE", "tail_merge": False, "tokenizer": audit["tokenizer"],
                  "offset_policy": OFFSET_POLICY, "identity_version": IDENTITY_VERSION}
        expected = sha256_bytes(canonical_bytes(config))
        require(audit["chunking_config_sha256"] == expected and
                all(c["chunking_config_sha256"] == expected for c in group), "CHUNK_CONFIG_HASH")
        verify_coverage(parent["parent_text"], group, audit["parameters"])
        parent_offsets = audit["parent_tokenization"]["offsets"]
        n = len(parent_offsets)
        a, start = 0, 0
        for index, c in enumerate(group):
            tokenization = c["tokenization"]
            _validate_token_audit(c["child_text"], tokenization)
            require(len(tokenization["input_ids"]) == c["standalone_token_count"], "TOKEN_AUDIT_BINDING")
            b = c["parent_token_end"]
            require(type(c["parent_token_start"]) is int and c["parent_token_start"] == a and
                    type(b) is int and a < b <= min(a + audit["parameters"]["max_tokens"], n) and
                    (c["char_start"], c["char_end"]) ==
                    (start, _source_end(parent_offsets, len(parent["parent_text"]), b)), "PARENT_TOKEN_WINDOW")
            next_a, next_start, overlap = _next_boundary(parent_offsets, a, b, start,
                                                        c["char_end"], audit["parameters"]["requested_overlap"])
            require(type(c["requested_overlap"]) is int and c["requested_overlap"] == audit["parameters"]["requested_overlap"] and
                    type(c["actual_parent_token_overlap_to_next"]) is int and c["actual_parent_token_overlap_to_next"] == overlap,
                    "OVERLAP_AUDIT")
            require(type(c["actual_character_overlap_to_next"]) is int and
                    c["actual_character_overlap_to_next"] == (0 if b == n else c["char_end"] - next_start),
                    "CHARACTER_OVERLAP_AUDIT")
            require(type(c["short_window_overlap"]) is bool and
                    c["short_window_overlap"] == (b < n and overlap < audit["parameters"]["requested_overlap"]) and
                    type(c["short_final_tail"]) is bool and
                    c["short_final_tail"] == (b == n and c["standalone_token_count"] < 64), "TAIL_AUDIT")
            require((b == n) == (index == len(group) - 1), "PARENT_TOKEN_COMPLETENESS")
            a, start = next_a, next_start
        flags = sorted(set(audit["parent_tokenization"]["review_flags"] + [flag for c in group
                           for flag in c["tokenization"]["review_flags"]]))
        if "\ufffd" in parent["parent_text"]:
            flags.append("ORIGINAL_CHARACTER_UNKNOWN")
        require(audit.get("review_flags") == flags and audit.get("representation_status") ==
                ("REVIEW_REQUIRED" if flags else "NO_DIAGNOSTIC_LOSS_DETECTED"), "REPRESENTATION_AUDIT")
    return {"questions": 1, "parent_occurrences": len(groups), "child_occurrences": len(children),
            "unique_canonical_children": len(canonical), "mechanical_validation": "PASS",
            "backend_verification": "UNVERIFIED", "scientific_approval": "NOT_GRANTED",
            "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}


def validate_pool_records(records, frame):
    """Read-only cross-question identity validation; never constructs a pool.

    Counts refer only to the supplied records. This checks byte/position bindings,
    not source authority, temporal truth, relevance or execution permission.
    """
    validate_frame_records(records, frame)
    occurrences, canonical, count = set(), {}, 0
    for question in records:
        validate_pool(question, frame)
        for child in question["candidates"]:
            occurrence = child["child_occurrence_id"]
            require(occurrence not in occurrences, "DUPLICATE_CHILD_OCCURRENCE")
            occurrences.add(occurrence)
            cid = child["canonical_child_id"]
            binding = (child["parent_source_id"], child["child_text"], child["child_text_sha256"],
                       child["char_start"], child["char_end"], child["chunking_config_sha256"])
            require(cid not in canonical or canonical[cid] == binding, "CHILD_IDENTITY_COLLISION")
            canonical[cid] = binding
            count += 1
    return {"questions": len(records), "child_occurrences": count,
            "unique_canonical_children": len(canonical), "mechanical_identity_validation": "PASS",
            "backend_verification": "UNVERIFIED", "scientific_approval": "NOT_GRANTED",
            "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION"}
