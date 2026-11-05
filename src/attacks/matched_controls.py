"""Development-only matched controls. No sampling, inference or key approval.

Validation replays construction against authoritative caller inputs, rather
than trusting a hash inside a mutable output. Inputs must be JSON values.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

from src.attacks.identity import require_source_qa_id
from src.eval.evidence_identity import validate_timestamp

SCHEMA = "chronoguard.matched-controls/v1"
HEADERS = {"neutral": "General notice:\n", "freshness": "Latest update:\n"}
STATUS = "DEVELOPMENT ONLY / NOT FINAL / NOT APPROVED"
SETTING_FIELDS = {"retrieval", "generation", "evaluation_rule"}


def canonical(value):
    """Reject non-JSON/mutable custom objects and nonfinite numeric values."""
    def check(v):
        if type(v) in (str, int, float, bool) or v is None:
            return
        if type(v) is list:
            for x in v:
                check(x)
            return
        if type(v) is dict and all(type(k) is str for k in v):
            for x in v.values():
                check(x)
            return
        raise ValueError("only plain JSON containers and values are supported")
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _inputs(base, slots, settings):
    canonical(base)
    canonical(settings)
    require_source_qa_id(base)
    for field in ("query", "question_ts", "gold_answer"):
        if not isinstance(base.get(field), str) or not base[field].strip():
            raise ValueError(f"missing {field}")
    validate_timestamp(base["question_ts"])
    if not isinstance(base.get("gold_aliases"), list):
        raise ValueError("gold_aliases must be a list")
    if not isinstance(base.get("gold_chunk_ids"), list) or not base["gold_chunk_ids"]:
        raise ValueError("gold_chunk_ids required")
    candidates = base.get("candidates")
    if type(candidates) is not list or not candidates:
        raise ValueError("nonempty candidate list required")
    ids = []
    for c in candidates:
        if type(c) is not dict or not isinstance(c.get("doc_id"), str) or not c["doc_id"]:
            raise ValueError("document identity required")
        if not isinstance(c.get("text"), str):
            raise ValueError("text must be a string")
        validate_timestamp(c.get("timestamp"))
        ids.append(c["doc_id"])
    if len(ids) != len(set(ids)) or not set(base["gold_chunk_ids"]).issubset(ids):
        raise ValueError("duplicate document IDs or absent gold source")
    if type(slots) is not list or not slots or any(type(s) is not int for s in slots):
        raise ValueError("explicit integer target slots required")
    if len(set(slots)) != len(slots) or slots != sorted(slots):
        raise ValueError("target slots must be unique and sorted")
    if any(s < 0 or s >= len(ids) or ids[s] in base["gold_chunk_ids"] for s in slots):
        raise ValueError("invalid target slot or gold overwrite")
    if type(settings) is not dict or set(settings) != SETTING_FIELDS:
        raise ValueError("retrieval, generation and evaluation_rule settings required")
    if any(not settings[k] for k in SETTING_FIELDS):
        raise ValueError("settings cannot be empty")
    if (type(settings["retrieval"]) is not dict or type(settings["generation"]) is not dict
            or not isinstance(settings["evaluation_rule"], str)):
        raise ValueError("retrieval/generation dictionaries and explicit evaluation rule required")


def _envelope(base, slots, settings, kind, declarations, conditions):
    return {"schema": SCHEMA, "status": STATUS, "kind": kind,
            "base_sha256": digest(base), "source_qa_id": base["source_qa_id"],
            "target_slots": copy.deepcopy(slots), "poison_budget": len(slots),
            "settings": copy.deepcopy(settings),
            "declarations": copy.deepcopy(declarations), "conditions": conditions}


def header_pair(base, slots, settings, body, *, kind="false_claim", headers=None):
    """Identical body/metadata/settings; only the declared header differs.

    'false_claim' is a caller declaration, never a scientific key decision.
    Correct controls must copy an exact body from an original gold document.
    """
    _inputs(base, slots, settings)
    if not isinstance(body, str) or not body.strip():
        raise ValueError("explicit body required")
    if kind not in ("false_claim", "correct_content"):
        raise ValueError("unsupported body kind")
    if kind == "correct_content" and not any(
            c["doc_id"] in base["gold_chunk_ids"] and c["text"] == body
            for c in base["candidates"]):
        raise ValueError("correct control must copy original gold-source text")
    headers = copy.deepcopy(HEADERS if headers is None else headers)
    if type(headers) is not dict or set(headers) != set(HEADERS) or any(
            not isinstance(h, str) or not h.endswith("\n") or not h.strip()
            for h in headers.values()) or headers["neutral"] == headers["freshness"]:
        raise ValueError("two distinct explicit newline-terminated headers required")
    conditions = {}
    for name, header in headers.items():
        record = copy.deepcopy(base)
        for slot in slots:
            record["candidates"][slot]["text"] = header + body
        conditions[name] = record
    return _envelope(base, slots, settings, "header_pair", {
        "body": body, "body_kind": kind, "headers": headers,
        "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }, conditions)


def date_pair(base, slots, settings, *, kind, offset_days, source_slot=None):
    """Only explicitly declared UTC timestamp changes are allowed.

    Future shift: max(question time, original target date) + positive days.
    Timestamp shift: original target date + signed days.
    Correct duplication: source date at zero days versus source minus offset.
    """
    _inputs(base, slots, settings)
    if type(offset_days) is not int or offset_days == 0:
        raise ValueError("nonzero integer day offset required")
    if kind not in ("future_metadata_only", "timestamp_shift", "correct_duplication"):
        raise ValueError("unsupported date control")
    if kind != "timestamp_shift" and offset_days < 0:
        raise ValueError("positive offset required")
    if kind == "correct_duplication":
        if type(source_slot) is not int or not 0 <= source_slot < len(base["candidates"]):
            raise ValueError("gold source slot required")
        source = base["candidates"][source_slot]
        if source["doc_id"] not in base["gold_chunk_ids"]:
            raise ValueError("source must be an original gold document")
    elif source_slot is not None:
        raise ValueError("source slot only applies to correct duplication")
    left, right = copy.deepcopy(base), copy.deepcopy(base)
    for slot in slots:
        original = base["candidates"][slot]
        if kind == "correct_duplication":
            for record in (left, right):
                record["candidates"][slot]["text"] = source["text"]
            left["candidates"][slot]["timestamp"] = source["timestamp"]
            anchor = datetime.fromisoformat(source["timestamp"])
            delta = -offset_days
        else:
            anchor = datetime.fromisoformat(original["timestamp"])
            if kind == "future_metadata_only":
                anchor = max(anchor, datetime.fromisoformat(base["question_ts"]))
            delta = offset_days
        right["candidates"][slot]["timestamp"] = (anchor + timedelta(days=delta)).isoformat()
    names = ("zero_day", "offset") if kind == "correct_duplication" else ("unchanged", "shifted")
    return _envelope(base, slots, settings, kind, {
        "offset_days": offset_days, "source_slot": source_slot,
        "date_basis": "explicit UTC; calendar-day timedelta; no date inference",
    }, dict(zip(names, (left, right))))


def validate_pair(pair, base, slots, settings, **construction):
    """Replay against separately supplied authoritative construction arguments.

    Caller-supplied hashes alone provide no authenticity. Never use output
    declarations as the authoritative construction arguments.
    """
    expected = (header_pair(base, slots, settings, **construction)
                if pair.get("kind") == "header_pair"
                else date_pair(base, slots, settings, **construction))
    if canonical(pair) != canonical(expected):
        raise ValueError("pair differs from authoritative construction replay")
    return True


def metadata_visibility(pair, *, metadata_aware=False):
    """Interface-level visibility, not a measured retrieval effect."""
    records = list(pair["conditions"].values())
    texts = [[c["text"] for c in r["candidates"]] for r in records]
    return {"text_inputs_identical": texts[0] == texts[1],
            "metadata_aware": metadata_aware,
            "metadata_intervention_visible_to_interface": metadata_aware,
            "retrieval_effect": "NOT_MEASURED"}
