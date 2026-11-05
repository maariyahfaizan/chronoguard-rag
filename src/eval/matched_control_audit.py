"""Offline text audits; no model imports or inference. All visibility is scoped."""
from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import Path

from src.attacks.matched_controls import digest
from src.eval.bm25_header_diagnostic import tokenize, TOKENIZERS


def generator_prompt(query, texts, max_passage_chars=1500):
    """Execute only the existing pure prompt helpers, without heavy imports.

    AST allowlisting avoids importing generation.generate (which imports model
    runtimes at module scope). Source digest is included by the audit runner.
    """
    source = Path(__file__).resolve().parents[1] / "generation" / "generate.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in {"truncate_passage", "build_prompt"}]
    if len(nodes) != 2:
        raise ValueError("unsupported generator helper layout")
    scope = {"DEFAULT_MAX_PASSAGE_CHARS": 1500}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), scope)
    return scope["build_prompt"](query, texts, max_passage_chars)


def _length(text):
    return {"characters": len(text), "utf8_bytes": len(text.encode("utf-8"))}


def audit_header_pair(pair, *, max_passage_chars=None, retrieved_slots=None,
                      context_log=None, extra_tokenizers=None):
    """extra_tokenizers: explicit name -> offline counting callable.

    Counts alone cannot establish truncation behavior or model visibility.
    No backend or max-token limit is guessed from a model name.
    A context log is evidence of a logged prompt, not authenticated model input.
    """
    if pair["kind"] != "header_pair":
        raise ValueError("header pair required")
    configured_limit = pair["settings"]["generation"].get("max_passage_chars")
    if max_passage_chars is None:
        max_passage_chars = configured_limit
    if type(max_passage_chars) is not int or max_passage_chars <= 0:
        raise ValueError("positive passage character limit required")
    headers = pair["declarations"]["headers"]
    body = pair["declarations"]["body"]
    tokenizers = {n: (lambda text, n=n: tokenize(text, n)) for n in TOKENIZERS}
    for name, fn in (extra_tokenizers or {}).items():
        if name in tokenizers or not callable(fn):
            raise ValueError("distinct named offline tokenizer required")
        tokenizers[name] = fn
    spans = []
    for op, a, b, c, d in difflib.SequenceMatcher(
            None, headers["neutral"], headers["freshness"], autojunk=False).get_opcodes():
        if op != "equal":
            spans.append({"operation": op, "neutral": [a, b, headers["neutral"][a:b]],
                          "freshness": [c, d, headers["freshness"][c:d]]})
    records = pair["conditions"]
    if retrieved_slots is not None and (type(retrieved_slots) is not list
            or any(type(s) is not int or s < 0 or s >= len(records["neutral"]["candidates"])
                   for s in retrieved_slots) or len(set(retrieved_slots)) != len(retrieved_slots)):
        raise ValueError("explicit ordered unique retrieval slots required")
    conditions = {}
    for name, header in headers.items():
        text = header + body
        if any(records[name]["candidates"][s]["text"] != text for s in pair["target_slots"]):
            raise ValueError("invalid rendered body/header; validate pair first")
        counts = {n: {part: len(fn(value)) for part, value in
                     (("header", header), ("body", body), ("rendered", text))}
                  for n, fn in tokenizers.items()}
        prompt = None if retrieved_slots is None else generator_prompt(
            records[name]["query"], [records[name]["candidates"][s]["text"]
                                     for s in retrieved_slots], max_passage_chars)
        logged = "UNKNOWN"
        if context_log is not None:
            log = context_log.get(name)
            if (not isinstance(log, dict) or log.get("pair_sha256") != digest(pair)
                    or log.get("source_qa_id") != pair["source_qa_id"]
                    or log.get("retrieved_slots") != retrieved_slots
                    or prompt is None or log.get("prompt") != prompt):
                raise ValueError("context log does not match exact pair, ordering and prompt")
            logged = "EXACT_LOGGED_PRETOKENIZATION_PROMPT"
        conditions[name] = {
            "header": _length(header), "body": _length(body), "rendered": _length(text),
            "body_character_span": [len(header), len(text)], "token_counts": counts,
            "passage_character_limit": max_passage_chars,
            "configured_passage_character_limit": configured_limit,
            "audit_limit_matches_declared_configuration": max_passage_chars == configured_limit,
            "passage_truncated": len(text) > max_passage_chars,
            "full_claim_survives_passage_truncation": len(text) <= max_passage_chars,
            "claim_in_selected_context": "UNKNOWN" if retrieved_slots is None else (
                any(s in retrieved_slots for s in pair["target_slots"])
                and len(text) <= max_passage_chars),
            "assembled_prompt_sha256": None if prompt is None else hashlib.sha256(prompt.encode()).hexdigest(),
            "logged_context_evidence": logged,
            "actual_model_input_visibility": "UNKNOWN",
            "generator_token_count": "UNAVAILABLE" if "generator" not in tokenizers else counts["generator"],
            "token_limit_truncation_risk": "UNKNOWN_WITHOUT_BACKEND_LIMIT_AND_TRUNCATION_POLICY",
        }
    return {"pair_sha256": digest(pair), "exact_header_diff_spans": spans,
            "span_units": "Unicode code points; half-open offsets in rendered candidate",
            "conditions": conditions,
            "retrieval_tokenizer_scope": {"frozen_space_split": "actual BM25 literal-space tokenizer",
                                          "diagnostic_whitespace_split": "sensitivity diagnostic only"},
            "dense_and_reranker_token_counts": "UNAVAILABLE_WITHOUT_LOCAL_TOKENIZER_RUNTIME"}


def write_synthetic_audit(output_dir):
    """Reproduce fictional fixtures only; no dataset or outcome loading."""
    import importlib.util
    import json
    from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, build_conditions
    from src.attacks.matched_controls import (
        canonical, date_pair, header_pair, metadata_visibility, validate_pair,
    )

    settings = {"retrieval": {"system": "BM25", "top_k": 2},
                "generation": {"max_passage_chars": 1500, "max_new_tokens": 64,
                               "do_sample": False},
                "evaluation_rule": "synthetic structural checks only; no scientific labels"}
    pairs, audits = [], []
    for example in SYNTHETIC_EXAMPLES:
        base = build_conditions(example)[1]
        for kind, body in (("false_claim", example.incorrect_claim),
                           ("correct_content", example.correct_text)):
            pair = header_pair(base, [1], settings, body, kind=kind)
            validate_pair(pair, base, [1], settings, body=body, kind=kind)
            pairs.append(pair)
            audits.append(audit_header_pair(pair))
        for kind in ("future_metadata_only", "timestamp_shift", "correct_duplication"):
            args = {"kind": kind, "offset_days": 30}
            if kind == "correct_duplication":
                args["source_slot"] = 0
            pair = date_pair(base, [1], settings, **args)
            validate_pair(pair, base, [1], settings, **args)
            pairs.append(pair)
            audits.append({"pair_sha256": digest(pair),
                           "date_blind_interface": metadata_visibility(pair),
                           "metadata_aware_interface": metadata_visibility(pair, metadata_aware=True)})
    sources = ["src/attacks/attack_pool.py", "src/attacks/identity.py",
               "src/attacks/pilot_protocol.py", "src/attacks/freshness_smoke.py",
               "src/attacks/matched_controls.py", "src/eval/matched_control_audit.py",
               "src/eval/bm25_header_diagnostic.py", "src/eval/contriever_header_diagnostic.py",
               "src/generation/generate.py", "src/retrieval/bm25.py", "src/retrieval/dense.py",
               "src/retrieval/hybrid.py", "src/retrieval/reranker.py",
               "configs/streamingqa_eval_config.yaml", "configs/model_revisions.yaml",
               "tests/test_matched_controls.py", "docs/p1_a1_matched_controls.md"]
    source_hashes = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources}
    availability = {name: importlib.util.find_spec(name) is not None
                    for name in ("rank_bm25", "transformers", "tokenizers", "torch")}
    files = {"pairs.jsonl": "".join(canonical(p) + "\n" for p in pairs),
             "audits.jsonl": "".join(canonical(a) + "\n" for a in audits),
             "source_inventory.json": canonical(source_hashes) + "\n",
             "summary.json": canonical({"scope": "SYNTHETIC ONLY / NOT APPROVED", "pairs": len(pairs),
                 "header_pairs": 4, "date_pairs": 6, "runtime_availability": availability,
                 "actual_generator_visibility": "UNKNOWN; no context logs or inference",
                 "dense_reranker_generator_token_counts": "UNAVAILABLE",
                 "scientific_keys_created": 0}) + "\n"}
    files["sha256.json"] = canonical({name: hashlib.sha256(value.encode()).hexdigest()
                                      for name, value in files.items()}) + "\n"
    output = Path(output_dir)
    # Refuse to overwrite differing evidence; identical reruns are permitted.
    for name, value in files.items():
        if (output / name).exists() and (output / name).read_bytes() != value.encode():
            raise ValueError(f"existing audit differs: {name}")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output / name).write_bytes(value.encode("utf-8"))
    return {"pairs": len(pairs), "files": sorted(files)}


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Synthetic-only matched-control audit; no inference")
    parser.add_argument("--output", required=True)
    print(json.dumps(write_synthetic_audit(parser.parse_args().output), sort_keys=True))
