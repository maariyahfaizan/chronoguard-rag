"""Synthetic-only generator-isolated 2x2x2 construction. Never retrieves."""
from __future__ import annotations

import copy
import hashlib
from datetime import date
from itertools import product

from src.attacks.freshness_smoke import build_conditions
from src.attacks.matched_controls import HEADERS, canonical, digest
from src.eval.matched_control_audit import generator_prompt
from src.eval.config_loader import load_eval_config, model_revisions
from src.eval.offline_input_audit import PINS, sha, ROOT

SCHEMA = "chronoguard.generator-isolated-rq3/v1"
LEVELS = (("correct", "incorrect"), ("neutral", "freshness"),
          ("correct_first", "incorrect_first"))
DEFAULT_DATES = ["2020-01-01", "2020-01-02"]
STATUS = "SYNTHETIC ONLY / PRE-APPROVAL / NOT FINAL"


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def configuration():
    configured = load_eval_config()["shared"]["generator"]
    model, revision = PINS["generator"]
    if configured["model"] != model or model_revisions().get(model) != revision:
        raise ValueError("unsupported configured generator identity")
    return {"model": model, "revision": revision,
            "max_passage_chars": configured["max_passage_chars"],
            "max_new_tokens": configured["decoding"]["max_new_tokens"],
            "do_sample": configured["decoding"]["do_sample"]}


def factorial(example, *, dates=None, generation=None):
    """Both passages are supplied directly, with no ranking/selection interface.

    The same wording is applied to BOTH passages, so header wording is not
    confounded with which claim receives a header. Dates are assigned cues.
    Constant allocation means equal passage caps, not equal tokenizer lengths.
    """
    build_conditions(example)  # existing fictional-fixture validation only
    dates = copy.deepcopy(DEFAULT_DATES if dates is None else dates)
    generation = copy.deepcopy(configuration() if generation is None else generation)
    canonical(generation)
    if (type(dates) is not list or len(dates) != 2
            or any(type(d) is not str or len(d) != 10 for d in dates)
            or not date.fromisoformat(dates[0]) < date.fromisoformat(dates[1])):
        raise ValueError("two distinct ascending ISO calendar date cues required")
    expected = configuration()
    if (set(generation) != set(expected) or generation["model"] != expected["model"]
            or generation["revision"] != expected["revision"]
            or type(generation["max_passage_chars"]) is not int
            or generation["max_passage_chars"] <= 0
            or type(generation["max_new_tokens"]) is not int or generation["max_new_tokens"] <= 0
            or generation["do_sample"] is not False):
        raise ValueError("unsupported generator configuration")
    sources = {role: {"doc_id": example.source_qa_id + ":" + role,
                     "body": body, "original_body_sha256": text_hash(body),
                     "origin": "manually_authored_fictional_fixture",
                     "original_fixture_timestamp": example.timestamp}
               for role, body in (("correct", example.correct_text),
                                  ("incorrect", example.incorrect_claim))}
    cells = []
    for newer, wording, order in product(*LEVELS):
        cell_id = "/".join((example.source_qa_id, newer, wording, order))
        roles = ["correct", "incorrect"] if order == "correct_first" else ["incorrect", "correct"]
        passages = []
        for role in roles:
            assigned = dates[1] if role == newer else dates[0]
            header = HEADERS[wording]
            cue = "Assigned date cue: " + assigned + "\n"
            rendered = header + cue + sources[role]["body"]
            passages.append({"role": role, **copy.deepcopy(sources[role]),
                "assigned_date_label": assigned, "date_basis": "EXPERIMENTAL_CUE_NOT_AUTHENTICATED_PUBLICATION",
                "header": header, "date_cue_text": cue, "rendered_text": rendered,
                "body_span": [len(header + cue), len(rendered)]})
        prompt = generator_prompt(example.query, [p["rendered_text"] for p in passages],
                                  generation["max_passage_chars"])
        cells.append({"schema": SCHEMA, "status": STATUS,
            "synthetic_case_id": example.source_qa_id, "cell_id": cell_id,
            "factors": {"newer_looking": newer, "header_wording": wording, "passage_order": order},
            "question": example.query, "date_pair": dates.copy(), "passages": passages,
            "presentation": "DIRECT_BOTH_PASSAGES_NO_RETRIEVAL", "passage_count": 2,
            "generation": copy.deepcopy(generation), "generation_configuration_sha256": digest(generation),
            "allocated_context_characters": 2 * generation["max_passage_chars"],
            "prompt": prompt, "prompt_sha256": text_hash(prompt),
            "prompt_template_source_sha256": sha(ROOT / "src/generation/generate.py"),
            "revision_record_sha256": sha(ROOT / "configs/model_revisions.yaml")})
        cells[-1]["evaluation_configuration_sha256"] = sha(ROOT / "configs/streamingqa_eval_config.yaml")
    return cells


def validate_factorial(cells, example, *, dates=None, generation=None):
    """Authoritative replay rejects missing cells and undeclared confounds."""
    expected = factorial(example, dates=dates, generation=generation)
    if type(cells) is not list or len(cells) != 8:
        raise ValueError("exactly eight cells required")
    ids = [c.get("cell_id") for c in cells if type(c) is dict]
    if len(ids) != 8 or len(set(ids)) != 8:
        raise ValueError("missing or duplicate cell identity")
    actual = {c["cell_id"]: c for c in cells}
    if set(actual) != {c["cell_id"] for c in expected}:
        raise ValueError("invalid factorial coverage")
    for cell in expected:
        if canonical(actual[cell["cell_id"]]) != canonical(cell):
            raise ValueError("undeclared intervention or identity/prompt/configuration mismatch")
    return True


def audit_factorial(cells, example, *, dates=None, generation=None):
    validate_factorial(cells, example, dates=dates, generation=generation)
    rows, all_visibility = [], []
    for cell in cells:
        limit = cell["generation"]["max_passage_chars"]
        passage_audits = []
        visibility = {}
        for p in cell["passages"]:
            text = p["rendered_text"]
            kept = text[:limit]
            start, end = p["body_span"]
            complete = end <= len(kept) and kept[start:end] == p["body"]
            visibility[p["role"]] = complete
            passage_audits.append({"role": p["role"], "doc_id": p["doc_id"],
                "body_sha256": p["original_body_sha256"], "assigned_date_label": p["assigned_date_label"],
                "header_characters": len(p["header"]), "header_utf8_bytes": len(p["header"].encode()),
                "body_characters": len(p["body"]), "body_utf8_bytes": len(p["body"].encode()),
                "header_bm25_literal_space_tokens": len(p["header"].split(" ")),
                "body_bm25_literal_space_tokens": len(p["body"].split(" ")),
                "characters": len(text), "utf8_bytes": len(text.encode()),
                "bm25_literal_space_tokens": len(text.split(" ")),
                "generator_tokens": "UNKNOWN", "neural_tokenization": "UNAVAILABLE",
                "retained_characters": len(kept), "truncation_boundary": min(len(text), limit),
                "body_span": p["body_span"], "complete_body_in_assembled_input": complete})
        violations = []
        if not all(visibility.values()):
            violations.append("INCOMPLETE_EVIDENCE_CLAIM")
        if visibility["correct"] != visibility["incorrect"]:
            violations.append("ASYMMETRIC_CLAIM_TRUNCATION")
        rows.append({"cell_id": cell["cell_id"], "factors": cell["factors"],
            "passages": passage_audits, "claim_visibility": visibility,
            "prompt_characters": len(cell["prompt"]), "prompt_utf8_bytes": len(cell["prompt"].encode()),
            "prompt_bm25_literal_space_tokens": len(cell["prompt"].split(" ")),
            "prompt_sha256": cell["prompt_sha256"], "generation_configuration_sha256": cell["generation_configuration_sha256"],
            "token_level_balancing": "UNVERIFIED", "final_tokenized_input_visibility": "UNKNOWN",
            "model_receipt": "NOT_EXECUTED", "violations": violations})
        all_visibility.append(visibility)
    varying_visibility = any(v != all_visibility[0] for v in all_visibility[1:])
    return {"synthetic_case_id": example.source_qa_id, "cells": rows,
        "coverage": "EXACTLY_EIGHT_UNIQUE_CELLS", "character_allocation_equal": True,
        "rendered_prompt_character_lengths_equal": len({r["prompt_characters"] for r in rows}) == 1,
        "header_character_difference": len(HEADERS["neutral"]) - len(HEADERS["freshness"]),
        "visibility_changes_across_cells": varying_visibility,
        "all_claims_complete": all(all(v.values()) for v in all_visibility),
        "token_level_balancing": "UNVERIFIED", "retrieval_executed": False,
        "unresolved": ["exact Mistral tokenizer/runtime", "chat-template and token-span verification",
                       "independent scientific design and key approval"]}
