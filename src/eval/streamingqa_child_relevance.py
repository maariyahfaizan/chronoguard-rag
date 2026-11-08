"""Opt-in StreamingQA child-relevance audit schema, version 1.

No file I/O, tokenizer loading, semantic judging or runner integration. Call with
an unchunked legacy parent record and explicitly grouped emitted children (one
group per parent candidate slot, in original order). This avoids guessing which
occurrence a repeated canonical document ID belongs to. Empty/malformed groups
fail; no fallback child is invented. Chunk boundaries and texts are not changed.

The lexical rule deliberately matches the historical builder: normalized unordered
answer-token containment. Negation, misleading mentions and paraphrase are NOT
resolved. Full-child and exact first-1500-character-prefix annotations are separate;
the latter is only a static character view, not verified model receipt. A cut may
split a word. Neither annotation authenticates provenance or temporal validity.

Legacy fields are preserved under source/historical metadata, never reinterpreted
in place. The output uses ``children``, not the runner's ``candidates`` schema;
there is no execution path or writer. Gold-ID lists below mean only lexical
matches within legacy validated source parents, not independently approved gold.
Identical duplicate parents/children retain occurrence order; conflicting reuse
of a canonical ID is rejected. Deduplication for scientific metrics remains open.
"""

from copy import deepcopy
import hashlib
import json

from src.eval.metrics import normalize_answer

SCHEMA_VERSION = "streamingqa_child_relevance_v1"
LEXICAL_BASIS = "squad_normalization_unordered_answer_token_subset_v1"
GENERATOR_PREFIX_CHARS = 1500  # generate.py's historical static character view


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _text(value, name, *, nonempty=False):
    _require(isinstance(value, str) and (not nonempty or bool(value)), name + " must be a string")
    return value


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_sha(value):
    return _sha(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                           separators=(",", ":")))


def _unique(values):
    return list(dict.fromkeys(values))


def _matches(text, answers):
    tokens = set(normalize_answer(text).split())
    return [i for i, answer in enumerate(answers)
            if answer and (gold := set(normalize_answer(answer).split())) and gold <= tokens]


def label_children_v1(parent_record, children_by_parent):
    """Return a new audit record; never mutate input or automatically approve it.

    ``children_by_parent[i]`` must contain ALL emitted children of parent slot i,
    in #chunk0, #chunk1, ... order. Completeness of tokenization itself cannot be
    proven by this labeler; callers must bind the producer/tokenizer separately.
    Candidate timestamps are copied verbatim, including None, never inferred.
    """
    _require(type(parent_record) is dict, "parent_record must be a dict")
    required = {"query", "gold_answer", "gold_aliases", "candidates", "gold_chunk_ids",
                "gold_validated", "question_ts"}
    _require(required <= parent_record.keys(), "missing parent record fields")
    _text(parent_record["query"], "query")
    answer = parent_record["gold_answer"]
    _require(answer is None or isinstance(answer, str), "gold_answer must be string or None")
    aliases = parent_record["gold_aliases"]
    _require(type(aliases) is list and all(isinstance(a, str) for a in aliases), "invalid aliases")
    answers = [answer] + aliases
    parents = parent_record["candidates"]
    _require(type(parents) is list and bool(parents), "nonempty parent candidates required")
    _require(type(children_by_parent) is list and len(children_by_parent) == len(parents),
             "one explicit child group per parent slot required")
    validated = parent_record["gold_validated"]
    _require(type(validated) is bool, "gold_validated must be bool")
    old_ids = parent_record["gold_chunk_ids"]
    _require(type(old_ids) is list and all(isinstance(x, str) and x for x in old_ids),
             "invalid legacy gold IDs")
    old_set = set(old_ids)
    parent_seen, child_seen = {}, {}
    for parent in parents:
        _require(type(parent) is dict and {"doc_id", "text", "timestamp", "is_source_document"}
                 <= parent.keys(), "missing parent candidate fields")
        doc = _text(parent["doc_id"], "parent doc_id", nonempty=True)
        _text(parent["text"], "parent text")
        _require(parent["timestamp"] is None or isinstance(parent["timestamp"], str),
                 "parent timestamp must be string or None")
        _require(type(parent["is_source_document"]) is bool, "parent source flag must be bool")
        _require(parent["is_source_document"] == (validated and doc in old_set),
                 "inconsistent legacy parent gold fields")
        _require(doc not in parent_seen or parent_seen[doc] == parent,
                 "conflicting duplicate parent ID")
        parent_seen[doc] = parent
    _require(old_set <= parent_seen.keys(), "legacy gold reference missing from parents")
    _require(not validated or bool(old_set), "validated legacy record has no gold IDs")

    output = []
    for parent_slot, (parent, children) in enumerate(zip(parents, children_by_parent)):
        _require(type(children) is list and bool(children), "empty or invalid child group")
        role = ("LEGACY_LEXICALLY_VALIDATED_PARENT" if validated and parent["doc_id"] in old_set
                else "UNVALIDATED_FALLBACK_PARENT" if parent["doc_id"] in old_set
                else "OTHER_PARENT")
        for child_index, child in enumerate(children):
            _require(type(child) is dict and {"doc_id", "parent_doc_id", "text", "timestamp"}
                     <= child.keys(), "missing child fields")
            _require(child["parent_doc_id"] == parent["doc_id"], "child parent lineage mismatch")
            _require(child["doc_id"] == f"{parent['doc_id']}#chunk{child_index}",
                     "child ID/order mismatch")
            _require(child["timestamp"] == parent["timestamp"], "child timestamp mismatch")
            if "is_source_document" in child:
                _require(type(child["is_source_document"]) is bool
                         and child["is_source_document"] == parent["is_source_document"],
                         "inconsistent historical child flag")
            text = _text(child["text"], "child text")
            doc = child["doc_id"]
            binding = (child["parent_doc_id"], text, child["timestamp"])
            _require(doc not in child_seen or child_seen[doc] == binding,
                     "conflicting duplicate child ID")
            child_seen[doc] = binding
            full = _matches(text, answers)
            prefix = text[:GENERATOR_PREFIX_CHARS]
            visible = _matches(prefix, answers)
            output.append({
                "doc_id": doc, "text": text, "timestamp": child["timestamp"],
                "occurrence_id": f"parent-slot-{parent_slot}/child-{child_index}",
                "candidate_slot": len(output), "parent_candidate_slot": parent_slot,
                "parent_doc_id": parent["doc_id"], "child_index": child_index,
                "parent_role": role, "parent_text_sha256": _sha(parent["text"]),
                "child_text_sha256": _sha(text), "historical_child_metadata": deepcopy(child),
                "lexical_basis": LEXICAL_BASIS,
                "full_text_lexical_match": bool(full), "full_text_matching_answer_indices": full,
                "generator_prefix_lexical_match": bool(visible),
                "generator_prefix_matching_answer_indices": visible,
                "generator_prefix_sha256": _sha(prefix),
                "character_truncated": len(text) > GENERATOR_PREFIX_CHARS,
                "character_cut_splits_alphanumeric_run": (len(text) > GENERATOR_PREFIX_CHARS
                    and text[GENERATOR_PREFIX_CHARS - 1].isalnum()
                    and text[GENERATOR_PREFIX_CHARS].isalnum()),
                "semantic_support_status": "NOT_INDEPENDENTLY_REVIEWED",
                "temporal_validity_status": "NOT_REVIEWED",
                "source_authenticity_status": "NOT_ESTABLISHED_BY_LABELER",
                "generator_model_visibility": "UNVERIFIED",
            })
    lexical_gold = [c for c in output if c["parent_role"] == "LEGACY_LEXICALLY_VALIDATED_PARENT"
                    and c["full_text_lexical_match"]]
    fallback = [c for c in output if c["parent_role"] == "UNVALIDATED_FALLBACK_PARENT"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DEVELOPMENT_ONLY_NOT_SCIENTIFICALLY_VALIDATED",
        "execution_authorization": "NOT_AUTHORIZED_FOR_EXECUTION",
        "lexical_basis": LEXICAL_BASIS,
        "generator_prefix_chars": GENERATOR_PREFIX_CHARS,
        "source_record_sha256": _json_sha(parent_record),
        "emitted_children_sha256": _json_sha(children_by_parent),
        "source_question": deepcopy({k: v for k, v in parent_record.items() if k not in
                                      {"candidates", "gold_chunk_ids", "gold_validated"}}),
        "historical_parent_metadata": deepcopy(parents),
        "historical_gold_chunk_ids": deepcopy(old_ids),
        "historical_gold_validated": validated,
        "children": output,
        "lexical_gold_validated": bool(lexical_gold),
        "lexically_validated_gold_chunk_ids": _unique(c["doc_id"] for c in lexical_gold),
        "lexically_validated_gold_occurrence_ids": [c["occurrence_id"] for c in lexical_gold],
        "unvalidated_fallback_parent_ids": _unique(c["parent_doc_id"] for c in fallback),
        "unvalidated_fallback_child_occurrence_ids": [c["occurrence_id"] for c in fallback],
        "duplicate_policy": "PRESERVE_IDENTICAL_OCCURRENCES_REJECT_CONFLICTS",
        "duplicate_parent_occurrences": len(parents) - len(parent_seen),
        "duplicate_child_occurrences": len(output) - len(child_seen),
        "semantic_support_status": "NOT_INDEPENDENTLY_REVIEWED",
        "temporal_validity_status": "NOT_REVIEWED",
    }
