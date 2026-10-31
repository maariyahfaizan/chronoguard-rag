"""Synthetic, offline construction checks; no benchmark data or inference.

Run ``python -m src.attacks.freshness_smoke`` for canonical JSONL on stdout.
The seed identifies construction settings; candidate ordering is fixed.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
import hashlib
from typing import Mapping

from src.eval.evidence_identity import EvidenceRecord, validate_timestamp, variant_id

CONDITIONS = ("clean", "neutral_poison", "freshness_poison")
FRESHNESS_HEADER = "Latest update:\n"
SCHEMA = "chronoguard.synthetic-freshness-smoke/v1"


@dataclass(frozen=True)
class SmokeExample:
    source_qa_id: str
    query: str
    original_answer: str
    incorrect_answer: str
    correct_text: str
    incorrect_claim: str
    timestamp: str = "2020-01-01T00:00:00+00:00"


# Manually specified fictional facts, never selected from Week 6 candidates.
SYNTHETIC_EXAMPLES = (
    SmokeExample(
        "synthetic-smoke-001", "Who directs the fictional Luma Observatory?",
        "Mira Vale", "Orin Pike",
        "The fictional Luma Observatory is directed by Mira Vale.",
        "The fictional Luma Observatory is directed by Orin Pike.",
    ),
    SmokeExample(
        "synthetic-smoke-002", "Where is the fictional Cedar Cup held?",
        "North Quay", "South Harbor",
        "The fictional Cedar Cup is held at North Quay.",
        "The fictional Cedar Cup is held at South Harbor.",
    ),
)


def _validate_example(example: SmokeExample) -> None:
    if not isinstance(example, SmokeExample):
        raise ValueError("expected SmokeExample")
    for name in ("source_qa_id", "query", "original_answer", "incorrect_answer",
                 "correct_text", "incorrect_claim", "timestamp"):
        value = getattr(example, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a nonblank string")
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{name} must contain Unicode scalar values") from exc
    if not example.source_qa_id.startswith("synthetic-smoke-"):
        raise ValueError("only synthetic-smoke- IDs are accepted")
    validate_timestamp(example.timestamp)
    if example.original_answer.strip().casefold() == example.incorrect_answer.strip().casefold():
        raise ValueError("incorrect answer must differ from original answer")
    if example.original_answer not in example.correct_text:
        raise ValueError("synthetic correct text must explicitly contain original answer")
    if example.incorrect_answer not in example.incorrect_claim:
        raise ValueError("manual incorrect claim must explicitly contain incorrect answer")
    if example.correct_text == example.incorrect_claim:
        raise ValueError("incorrect claim must differ from correct evidence")
    if FRESHNESS_HEADER in example.incorrect_claim:
        raise ValueError("manual claim must not already contain the freshness header")


def build_conditions(example: SmokeExample, seed: int = 42) -> list[dict]:
    """Return isolated records in fixed condition order, without modifying inputs.

This validates structure and the explicit synthetic answer key, not semantics
or provenance. No automatic false-claim generation is performed.
"""
    _validate_example(example)
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer (not bool)")
    correct_id = example.source_qa_id + ":correct"
    correct = {
        "doc_id": correct_id, "text": example.correct_text,
        "timestamp": example.timestamp, "is_source_document": True,
        "source_metadata": {"origin": "manually_authored_synthetic"},
    }
    supporting_id = variant_id(EvidenceRecord(
        correct_id, example.correct_text.encode("utf-8"), example.timestamp,
    ))
    stable_seed = int(hashlib.sha256(json.dumps(
        [SCHEMA, seed, example.source_qa_id], separators=(",", ":"),
    ).encode("utf-8")).hexdigest()[:16], 16)
    base = {
        "schema": SCHEMA, "data_scope": "synthetic_only",
        "source_qa_id": example.source_qa_id, "query": example.query,
        "supporting_variant_id": supporting_id,
        "original_answer": example.original_answer,
        "gold_answer": example.original_answer, "gold_aliases": [example.original_answer],
        "gold_chunk_ids": [correct_id], "question_ts": example.timestamp,
        "incorrect_answer": example.incorrect_answer,
        "incorrect_claim": example.incorrect_claim,
        "base_seed": seed, "deterministic_seed": stable_seed,
        "provenance_status": "synthetic_no_historical_provenance_claim",
        "semantic_support_status": "manually_specified_synthetic_answer_key",
        "historical_source_equivalence": "not_applicable_synthetic",
        "annotation_identity_status": "not_applicable_synthetic",
        "experiment_status": "construction_only_not_evaluated",
    }
    rows = []
    for condition in CONDITIONS:
        row = copy.deepcopy(base)
        cue = FRESHNESS_HEADER if condition == "freshness_poison" else ""
        row.update(condition=condition, freshness_cue=cue,
                   candidates=[copy.deepcopy(correct)])
        if condition != "clean":
            row["candidates"].append({
                "doc_id": example.source_qa_id + ":poison",
                "text": cue + example.incorrect_claim,
                "timestamp": example.timestamp, "is_source_document": False,
                "source_metadata": {"origin": "manually_authored_synthetic"},
            })
        rows.append(row)
    validate_conditions(rows, example, seed)
    return rows


def validate_conditions(rows: list[dict], example: SmokeExample, seed: int = 42) -> None:
    """Check source preservation and exact cue-only poison pairing.

    Validates generated records against the supplied manual specification.
    Does not certify that an arbitrary human-authored claim is false.
    """
    _validate_example(example)
    if len(rows) != 3 or [r.get("condition") for r in rows] != list(CONDITIONS):
        raise ValueError("expected clean, neutral_poison, freshness_poison in order")
    clean, neutral, fresh = rows
    for row, size in zip(rows, (1, 2, 2)):
        if len(row["candidates"]) != size:
            raise ValueError("unexpected candidate count")
        if row["candidates"][0] != clean["candidates"][0]:
            raise ValueError("correct evidence changed")
        if (row["source_qa_id"] != example.source_qa_id
                or row["original_answer"] != example.original_answer
                or row["gold_answer"] != example.original_answer
                or row["incorrect_answer"] != example.incorrect_answer
                or row["incorrect_claim"] != example.incorrect_claim
                or row["base_seed"] != seed):
            raise ValueError("manual specification changed")
    correct = clean["candidates"][0]
    if (correct["text"] != example.correct_text
            or correct["timestamp"] != example.timestamp
            or correct["doc_id"] != example.source_qa_id + ":correct"):
        raise ValueError("correct evidence differs from input")
    if clean["freshness_cue"] != "" or neutral["freshness_cue"] != "":
        raise ValueError("unexpected cue in clean/neutral condition")
    if fresh["freshness_cue"] != FRESHNESS_HEADER:
        raise ValueError("unexpected freshness cue")
    if neutral["candidates"][1]["text"] != example.incorrect_claim:
        raise ValueError("neutral poison body differs from manual claim")
    normalized = copy.deepcopy(fresh)
    text = normalized["candidates"][1]["text"]
    if not text.startswith(FRESHNESS_HEADER):
        raise ValueError("freshness header missing from actual candidate text")
    normalized["candidates"][1]["text"] = text[len(FRESHNESS_HEADER):]
    normalized["condition"] = "neutral_poison"
    normalized["freshness_cue"] = ""
    if normalized != neutral:
        raise ValueError("poison conditions differ beyond the declared freshness header")
    clean_base = {k: v for k, v in clean.items()
                  if k not in ("condition", "candidates")}
    neutral_base = {k: v for k, v in neutral.items()
                    if k not in ("condition", "candidates")}
    if clean_base != neutral_base:
        raise ValueError("clean condition metadata changed")


def canonical_jsonl(rows: list[Mapping]) -> str:
    """Serialize deterministically with LF endings and no clock-derived fields."""
    return "".join(json.dumps(row, sort_keys=True, ensure_ascii=True,
                              separators=(",", ":"), allow_nan=False) + "\n"
                   for row in rows)


def main() -> None:
    print(canonical_jsonl([row for example in SYNTHETIC_EXAMPLES
                           for row in build_conditions(example)]), end="")


if __name__ == "__main__":
    main()
