"""Opt-in synthetic-only tokenizer/input audit. No downloads or inference.

This observer does not patch any production runner. Missing exact backends
remain unavailable. The capture model stops at the generate call boundary.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path

from src.attacks.matched_controls import canonical, digest, validate_pair
from src.eval.config_loader import model_revisions
from src.eval.matched_control_audit import audit_header_pair, generator_prompt

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    "contriever": ("facebook/contriever", "2bd46a25019aeea091fd42d1f0fd4801675cf699"),
    "reranker": ("BAAI/bge-reranker-base", "2cfc18c9415c912f9d8155881c133215df768a70"),
    "generator": ("mistralai/Mistral-7B-Instruct-v0.2", "63a8b081895390a26e140280378bc85ec8bce07a"),
}
ANCHOR = ROOT / "results/smoke_diagnostics/contriever_header_controls_v1/snapshot/contriever_verified_snapshot_manifest.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_tokenizer_files(role, snapshot, manifest):
    """Manifest must come from a separately trusted inventory, not this cache.

    Matching bytes establishes consistency with that inventory, not independent
    original-source authentication. Never infer revision from directory alone.
    """
    model, revision = PINS[role]
    if model_revisions().get(model) != revision:
        raise ValueError("unsupported configured revision")
    if manifest.get("model") != model or manifest.get("revision") != revision:
        raise ValueError("unsupported tokenizer manifest identity/revision")
    root = Path(snapshot)
    if not root.is_dir():
        return {"status": "UNAVAILABLE", "reason": "MISSING_CACHE"}
    files = manifest.get("files", {})
    names = {n for n in files if n in {"config.json", "tokenizer.json", "tokenizer_config.json",
             "special_tokens_map.json", "vocab.txt", "tokenizer.model", "added_tokens.json",
             "vocab.json", "merges.txt", "chat_template.jinja"}}
    if not {"tokenizer_config.json", "tokenizer.json"}.issubset(names):
        raise ValueError("insufficient tokenizer inventory")
    # Unlisted files might change AutoTokenizer behavior; do not load such caches.
    actual = {p.name for p in root.iterdir() if p.is_file() and
              (p.name.startswith(("tokenizer", "special_tokens", "added_tokens", "chat_template"))
               or p.name in {"config.json", "vocab.txt", "vocab.json", "merges.txt"})}
    if actual != names:
        raise ValueError("missing or unlisted tokenizer files")
    hashes = {n: sha(root / n) for n in sorted(names)}
    if any(hashes[n] != files[n] for n in names):
        raise ValueError("tokenizer cache hash mismatch")
    config = json.loads((root / "tokenizer_config.json").read_text(encoding="utf-8"))
    return {"status": "FILES_MATCH_RECORDED_INVENTORY", "files": hashes,
            "tokenizer_class": config.get("tokenizer_class", "UNKNOWN"),
            "model_max_length": config.get("model_max_length", "UNKNOWN"),
            "preprocessing": {k: config[k] for k in (
                "do_lower_case", "strip_accents", "tokenize_chinese_chars", "padding_side",
                "truncation_side", "add_bos_token", "add_eos_token") if k in config}}


def backend_inventory(cache_root=None):
    cache_root = Path(cache_root) if cache_root is not None else Path.home() / ".cache/huggingface/hub"
    versions = {}
    for package in ("rank-bm25", "transformers", "tokenizers", "torch", "sentence-transformers"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "UNAVAILABLE"
    inventory = {"bm25": {"status": "VERIFIED", "implementation": "text.split(' ')",
                            "version": versions["rank-bm25"], "token_limit": "NONE_IN_RETRIEVER"}}
    for role, (model, revision) in PINS.items():
        if model_revisions().get(model) != revision:
            raise ValueError("unsupported configured revision")
        snapshot = cache_root / ("models--" + model.replace("/", "--")) / "snapshots" / revision
        evidence = {"status": "UNAVAILABLE", "reason": "MISSING_CACHE"}
        if snapshot.is_dir():
            if role == "contriever":
                evidence = verify_tokenizer_files(role, snapshot, json.loads(ANCHOR.read_text()))
                evidence["inventory_sha256"] = sha(ANCHOR)
            else:
                evidence = {"status": "UNAVAILABLE", "reason": "NO_SEPARATELY_RECORDED_TOKENIZER_INVENTORY"}
        inventory[role] = {"model": model, "revision": revision,
                           "token_counts": "UNAVAILABLE", "file_evidence": evidence,
                           "runtime_versions": versions,
                           "reason": "EXACT_OFFLINE_TOKENIZER_NOT_LOADED"}
    return inventory


def load_verified_tokenizer(role, snapshot, manifest):
    """Optional tokenizer-only loading, offline and exact pinned runtime only.

    Not called automatically by the audit. No weights or remote code are loaded.
    """
    evidence = verify_tokenizer_files(role, snapshot, manifest)
    if evidence["status"] == "UNAVAILABLE":
        return None
    if importlib.util.find_spec("transformers") is None:
        return None
    if importlib.metadata.version("transformers") != "5.0.0":
        raise ValueError("unsupported Transformers version")
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True,
                                         trust_remote_code=False)


class _Captured(Exception):
    def __init__(self, inputs):
        self.inputs = inputs


def capture_generate_boundary(query, passages, tokenizer):
    """Run the existing generate_answer function with a non-inferencing sink.

    Requires a real usable tokenizer/tensor runtime to verify the real backend.
    Test doubles exercise plumbing only. No model weights are needed.
    """
    class Sink:
        device = "cpu"

        def generate(self, **kwargs):
            raise _Captured(kwargs)

    path = ROOT / "src/generation/generate.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate_answer"]
    if len(nodes) != 1:
        raise ValueError("unsupported generation layout")
    scope = {"build_prompt": generator_prompt}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    try:
        scope["generate_answer"](query, passages, Sink(), tokenizer)
    except _Captured as captured:
        return captured.inputs
    raise ValueError("generation did not reach the expected capture boundary")


def _slots(value, n):
    if (type(value) is not list or any(type(s) is not int or not 0 <= s < n for s in value)
            or len(value) != len(set(value))):
        raise ValueError("invalid ordered slots")


def instrument_pair(pair, base, slots, settings, construction, *, enabled=False,
                    retrieved=None, selected=None, passage_limits=None, prompt_char_limit=None):
    """Opt-in static observer. Does not execute retrieval or call a tokenizer.

    Explicit synthetic plans describe allocation, never measured rankings.
    Optional whole-prompt caps are synthetic fault injection, not production
    behavior (production has no explicit whole-prompt character cap).
    """
    if not enabled:
        raise ValueError("instrumentation must be explicitly enabled")
    if base.get("data_scope") != "synthetic_only" or not base["source_qa_id"].startswith("synthetic-smoke-"):
        raise ValueError("synthetic fixtures only")
    validate_pair(pair, base, slots, settings, **construction)
    names = list(pair["conditions"])
    n = len(base["candidates"])
    retrieved = retrieved if retrieved is not None else {k: list(range(n)) for k in names}
    selected = selected if selected is not None else {k: list(retrieved[k]) for k in names}
    limits = passage_limits if passage_limits is not None else {
        k: settings["generation"]["max_passage_chars"] for k in names}
    if set(retrieved) != set(names) or set(selected) != set(names) or set(limits) != set(names):
        raise ValueError("condition plan mismatch")
    if prompt_char_limit is not None and (type(prompt_char_limit) is not int or prompt_char_limit <= 0):
        raise ValueError("invalid synthetic prompt cap")
    violations, traces = [], {}
    if retrieved[names[0]] != retrieved[names[1]]:
        violations.append("UNEQUAL_RETRIEVAL_PLAN")
    if selected[names[0]] != selected[names[1]] or limits[names[0]] != limits[names[1]]:
        violations.append("UNEQUAL_CONTEXT_ALLOCATION")
    for name, record in pair["conditions"].items():
        _slots(retrieved[name], n)
        _slots(selected[name], n)
        if [s for s in retrieved[name] if s in selected[name]] != selected[name]:
            raise ValueError("selected slots must preserve retrieved order")
        limit = limits[name]
        if type(limit) is not int or limit <= 0:
            raise ValueError("positive passage cap required")
        if limit != settings["generation"]["max_passage_chars"]:
            violations.append("UNEXPECTED_PREPROCESSING")
        candidates = record["candidates"]
        inputs = [candidates[s]["text"] for s in selected[name]]
        retained = [text[:limit] for text in inputs]
        prompt = generator_prompt(record["query"], inputs, limit)
        final_prompt = prompt if prompt_char_limit is None else prompt[:prompt_char_limit]
        if final_prompt != prompt:
            violations.append("PROMPT_TRUNCATION")
        body = (pair["declarations"]["body"] if pair["kind"] == "header_pair"
                else candidates[slots[0]]["text"])
        header_len = (len(pair["declarations"]["headers"][name])
                      if pair["kind"] == "header_pair" else 0)
        spans, visible = [], []
        context_start = prompt.index("Context:\n") + len("Context:\n")
        cursor = context_start
        for slot, text, kept in zip(selected[name], inputs, retained):
            target = slot in slots
            complete = target and len(text) <= limit
            start = cursor + header_len if target else None
            end = start + len(body) if target else None
            in_final = bool(complete and end <= len(final_prompt)
                            and final_prompt[start:end] == body)
            spans.append({"slot": slot, "doc_id": candidates[slot]["doc_id"],
                          "retained_text": kept,
                          "original_chars": len(text), "retained_chars": len(kept),
                          "truncation_boundary": min(len(text), limit),
                          "body_prompt_span": [start, end] if target else None,
                          "complete_target_body_in_final_assembled_prompt": in_final})
            if in_final:
                visible.append(slot)
            cursor += len(kept) + 2
        if not visible:
            violations.append("MISSING_COMPLETE_GENERATOR_CONTEXT_TARGET")
        traces[name] = {"question_id": record["source_qa_id"], "condition": name,
            "pair_id": digest(pair), "candidate_doc_ids": [c["doc_id"] for c in candidates],
            "source_metadata": [c.get("source_metadata", "UNKNOWN") for c in candidates],
            "retrieved_slots": retrieved[name], "selected_slots": selected[name],
            "retrieved_doc_ids": [candidates[s]["doc_id"] for s in retrieved[name]],
            "selected_doc_ids": [candidates[s]["doc_id"] for s in selected[name]],
            "generator_context_target_slots": visible, "passages": spans,
            "prompt_assembly_inputs": {"query": record["query"], "passages": inputs,
                                      "max_passage_chars": limit},
            "prompt": prompt, "final_assembled_prompt": final_prompt,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "generator_token_count": "UNAVAILABLE", "chat_template_ids": "UNAVAILABLE",
            "actual_model_receipt": "NOT_EXECUTED",
            "model": PINS["generator"][0], "revision": PINS["generator"][1],
            "generation_config": settings["generation"],
            "generation_source_sha256": sha(ROOT / "src/generation/generate.py"),
            "revision_config_sha256": sha(ROOT / "configs/model_revisions.yaml")}
    if traces[names[0]]["generator_context_target_slots"] != traces[names[1]]["generator_context_target_slots"]:
        violations.append("ASYMMETRIC_CLAIM_TRUNCATION_OR_VISIBILITY")
    return {"status": "PARTIAL_FINAL_TOKENIZED_INPUT_UNAVAILABLE", "pair_id": digest(pair),
            "allocation_basis": "SYNTHETIC_FIXED_PLAN_NOT_MEASURED_RETRIEVAL",
            "violations": sorted(set(violations)), "conditions": traces}


def capture_verified_trace(trace, snapshot, manifest):
    """Optional real tokenizer/tensor probe, never calls a real model.

    Production generate_answer hardcodes its default 1500-character passage
    limit and 64 new tokens. Refuse observer configurations it cannot reproduce.
    A trusted manifest remains an external dependency, not created by this probe.
    """
    inputs = trace["prompt_assembly_inputs"]
    if (inputs["max_passage_chars"] != 1500
            or trace["generation_config"].get("max_new_tokens", 64) != 64
            or trace["generation_config"].get("do_sample", False) is not False
            or trace["final_assembled_prompt"] != trace["prompt"]):
        raise ValueError("trace cannot replay the production generation defaults")
    if generator_prompt(inputs["query"], inputs["passages"]) != trace["prompt"]:
        raise ValueError("trace prompt differs from exact production assembly")
    tokenizer = load_verified_tokenizer("generator", snapshot, manifest)
    if tokenizer is None or importlib.util.find_spec("torch") is None:
        return {"status": "UNAVAILABLE", "reason": "TOKENIZER_OR_TENSOR_RUNTIME_UNAVAILABLE"}
    if importlib.metadata.version("torch") != "2.10.0":
        raise ValueError("unsupported tensor runtime version")
    captured = capture_generate_boundary(inputs["query"], inputs["passages"], tokenizer)
    ids = captured["input_ids"].tolist()
    return {"status": "CAPTURED_AT_GENERATE_BOUNDARY_NO_INFERENCE",
            "question_id": trace["question_id"], "pair_id": trace["pair_id"],
            "condition": trace["condition"], "model": PINS["generator"][0],
            "revision": PINS["generator"][1], "input_ids": ids,
            "input_token_count": len(ids[0]), "input_ids_sha256": digest(ids),
            "tokenizer_inventory_digest": digest(manifest),
            "actual_model_receipt": "NOT_EXECUTED",
            "complete_body_in_final_token_ids": "UNKNOWN_WITHOUT_OFFSET_OR_ROUNDTRIP_VALIDATION"}


def verify_prerequisites():
    """Read bytes only. Fail before writing on any integrity mismatch."""
    expected = {"p0_b1_v1": "00381495aa9832b3649df6aad54bf168bf9dd885aba98209017900739f5a737b",
                "p0_b2_v1": "1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0",
                "p0_c1_v1": "df70bbdacffd7304d6f2f661e08c445eb4301cd44ceb9ffd384c6a1d1fcacacb",
                "p1_a1_v1": "0e64d28f3a3197b2d46da090ca16094057d3b7b5c788e2417035a1e582a1fbb4"}
    for directory, checksum in expected.items():
        root = ROOT / "audits" / directory
        if sha(root / "sha256.json") != checksum:
            raise ValueError(f"changed checksum inventory: {directory}")
        for name, h in json.loads((root / "sha256.json").read_text()).items():
            if sha(root / name) != h:
                raise ValueError(f"changed audit output: {directory}/{name}")
    inventory = json.loads((ROOT / "audits/p0_c1_v1/source_inventory.json").read_text())["inputs"]
    roots = {"repository": ROOT, "recovered": ROOT.parent / "chronoguard-week6-recovered"}
    for reference in inventory.values():
        if sha(roots[reference["root"]] / reference["path"]) != reference["sha256"]:
            raise ValueError("B1/B2/C1 source integrity mismatch")
    for name, h in json.loads((ROOT / "audits/p1_a1_v1/source_inventory.json").read_text()).items():
        if sha(ROOT / name) != h:
            raise ValueError(f"P1-A1 source changed: {name}")
    candidate = json.loads((ROOT / "docs/supervisor_review/p0_a9/candidate_manifest.json").read_text())
    if any(sha(ROOT / f["path"]) != f["sha256"] for f in candidate["files"]):
        raise ValueError("published engineering candidate changed")
    paths = [ROOT / "src/eval/answer_judge.py"] + [p for r in (
        "data", "logs", "results", "docs/supervisor_review/p0_a5") for p in (ROOT / r).rglob("*") if p.is_file()]
    record = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}
    checksum = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if len(record) != 279 or checksum != "5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310":
        raise ValueError("protected artifact integrity mismatch")
    return {"audit_checksum_manifests": expected, "source_inputs": len(inventory),
            "published_candidate_files": len(candidate["files"]),
            "protected_files": len(record), "protected_sha256_map_digest": checksum}


def build_synthetic_reports():
    from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, build_conditions
    examples = {e.source_qa_id: e for e in SYNTHETIC_EXAMPLES}
    pairs = [json.loads(line) for line in (ROOT / "audits/p1_a1_v1/pairs.jsonl").read_text().splitlines()]
    reports = []
    for pair in pairs:
        example = examples[pair["source_qa_id"]]
        base = build_conditions(example)[1]
        d = pair["declarations"]
        construction = ({"body": d["body"], "kind": d["body_kind"], "headers": d["headers"]}
                        if pair["kind"] == "header_pair" else
                        {"kind": pair["kind"], "offset_days": d["offset_days"], "source_slot": d["source_slot"]})
        trace = instrument_pair(pair, base, pair["target_slots"], pair["settings"], construction, enabled=True)
        lengths = {}
        for name, record in pair["conditions"].items():
            lengths[name] = [{"slot": i, "doc_id": c["doc_id"],
                "source_metadata": c.get("source_metadata", "UNKNOWN"),
                "characters": len(c["text"]), "utf8_bytes": len(c["text"].encode()),
                "rendered_sha256": hashlib.sha256(c["text"].encode()).hexdigest(),
                "bm25_literal_space_tokens": len(c["text"].split(" ")),
                "contriever_tokens": "UNAVAILABLE", "reranker_tokens": "UNAVAILABLE",
                "generator_tokens": "UNAVAILABLE"} for i, c in enumerate(record["candidates"])]
        reports.append({"pair_id": digest(pair), "kind": pair["kind"], "trace": trace,
                        "candidate_audit": lengths,
                        "header_audit": audit_header_pair(pair, retrieved_slots=[0, 1])
                        if pair["kind"] == "header_pair" else "NOT_APPLICABLE"})
    return reports


def write_reports(output):
    integrity = verify_prerequisites()
    inventory = backend_inventory()
    reports = build_synthetic_reports()
    sources = ["src/eval/offline_input_audit.py", "tests/test_offline_input_audit.py",
               "docs/p1_a2_offline_input_audit.md", "src/generation/generate.py",
               "src/retrieval/bm25.py", "src/retrieval/dense.py", "src/retrieval/reranker.py",
               "scripts/run_baseline_streamingqa.py", "configs/model_revisions.yaml",
               "configs/streamingqa_eval_config.yaml", "requirements.txt"]
    files = {"tokenizer_inventory.json": canonical(inventory) + "\n",
             "input_audits.jsonl": "".join(canonical(r) + "\n" for r in reports),
             "integrity.json": canonical(integrity) + "\n",
             "source_inventory.json": canonical({p: sha(ROOT / p) for p in sources}) + "\n",
             "summary.json": canonical({"status": "PARTIAL", "synthetic_pairs": len(reports),
                 "invariant_violations": sum(len(r["trace"]["violations"]) for r in reports),
                 "real_tokenized_generator_path": "UNAVAILABLE", "inference_executed": False,
                 "decisions": "ALL_14_UNRECORDED"}) + "\n"}
    files["sha256.json"] = canonical({n: hashlib.sha256(v.encode()).hexdigest() for n, v in files.items()}) + "\n"
    output = Path(output)
    for name, value in files.items():
        if (output / name).exists() and (output / name).read_bytes() != value.encode():
            raise ValueError(f"existing audit differs: {name}")
    output.mkdir(parents=True, exist_ok=True)
    for name, value in files.items():
        (output / name).write_bytes(value.encode())
    return {"status": "PARTIAL", "pairs": len(reports), "files": sorted(files)}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Offline synthetic input observer; no inference")
    parser.add_argument("--output", required=True)
    print(json.dumps(write_reports(parser.parse_args().output), sort_keys=True))
