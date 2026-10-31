"""Opt-in, offline two-example Contriever diagnostic; never installs or downloads."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, canonical_jsonl
from src.eval.bm25_header_diagnostic import HEADERS, inventory, render_conditions
from src.eval.config_loader import model_revisions

ROOT = Path(__file__).resolve().parents[2]
MODEL = "facebook/contriever"
REVISION = "2bd46a25019aeea091fd42d1f0fd4801675cf699"
SCHEMA = "chronoguard.synthetic-contriever-header-diagnostic/v1"
CONTRASTS = (("general_notice", "freshness"), ("neutral", "freshness"),
             ("neutral", "general_notice"))
ARCHIVES = {
    "bm25_v1": "f55b9df259b55bee5f3c29a24db9b0fe48e94365742d70a63a496b6fe952cb51",
    "bm25_header_controls_v1": "343cf43e883780003247a3adc46d55eef1fd1ade07c4d623b2a1136d8a928527",
}
PACKAGES = ("torch", "transformers", "huggingface-hub", "numpy", "tokenizers",
            "safetensors", "PyYAML")
PINS = {"torch": "2.10.0", "transformers": "5.0.0", "huggingface-hub": "1.11.0"}
SOURCES = ("src/eval/contriever_header_diagnostic.py", "src/retrieval/dense.py",
           "src/eval/bm25_header_diagnostic.py", "src/attacks/freshness_smoke.py",
           "src/eval/evidence_identity.py", "src/eval/config_loader.py",
           "configs/model_revisions.yaml", "requirements.txt")
ATOL = RTOL = 1e-5


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encoded(rows):
    return canonical_jsonl(rows).encode("utf-8")


def close(a, b):
    if not (math.isfinite(a) and math.isfinite(b)
            and math.isclose(a, b, abs_tol=ATOL, rel_tol=RTOL)):
        raise ValueError("nonfinite value or dot-product reconstruction mismatch")


def environment():
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "packages": versions}


def verify_snapshot(snapshot, manifest_path):
    """Compare every snapshot byte to an independently trusted revision inventory.

    A directory named after a commit is insufficient proof of identity. The
    supplied manifest is a trust anchor, NOT generated from the files under test.
    HF cache symlinks are allowed; their resolved contents are hashed.
    """
    if model_revisions()[MODEL] != REVISION:
        raise ValueError("repository revision differs from approved protocol")
    snapshot = Path(snapshot)
    manifest_path = Path(manifest_path)
    if snapshot.is_symlink() or not snapshot.is_dir() or snapshot.name != REVISION:
        raise ValueError("snapshot must be a real directory named by the exact revision")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model") != MODEL or manifest.get("revision") != REVISION:
        raise ValueError("trusted snapshot identity mismatch")
    expected = manifest.get("files", {})
    if not isinstance(expected, dict) or not expected:
        raise ValueError("trusted file inventory is required")
    actual = {}
    for path in sorted(snapshot.rglob("*")):
        if path.is_dir() and path.is_symlink():
            raise ValueError("directory symlinks are forbidden")
        if path.is_file():
            actual[path.relative_to(snapshot).as_posix()] = sha(path)
        elif path.is_symlink():
            raise ValueError("broken snapshot symlink")
    if actual != expected:
        raise ValueError("snapshot integrity mismatch (missing, extra or changed file)")
    required = {"config.json", "tokenizer.json", "tokenizer_config.json",
                "special_tokens_map.json", "vocab.txt"}
    weights = {"pytorch_model.bin", "model.safetensors"} & actual.keys()
    if not required <= actual.keys() or len(weights) != 1:
        raise ValueError("require complete tokenizer and exactly one unsharded weight file")
    config = json.loads((snapshot / "config.json").read_text(encoding="utf-8"))
    if (config.get("model_type") != "bert" or config.get("hidden_size") != 768
            or config.get("num_hidden_layers") != 12):
        raise ValueError("incompatible Contriever configuration")
    return {"model": MODEL, "revision": REVISION, "files": actual,
            "trusted_manifest_sha256": sha(manifest_path),
            "identity_basis": "operator-supplied independently trusted revision inventory"}


def protect(prior_dirs):
    snapshots, archive_checks = {}, {}
    for directory in prior_dirs:
        path = Path(directory).resolve()
        if str(path) in snapshots:
            raise ValueError("duplicate prior directory")
        files = inventory(directory)
        snapshots[str(path)] = files
        for label, expected in ARCHIVES.items():
            # Accept either the named directory itself or a parent archive tree.
            key = "results.jsonl" if path.name == label else label + "/results.jsonl"
            if key in files:
                if files[key] != expected:
                    raise ValueError(f"known archive hash mismatch: {label}/results.jsonl")
                archive_checks[label] = {"status": "verified", "sha256": expected}
    for label in ARCHIVES:
        archive_checks.setdefault(label, {"status": "not_supplied"})
    return snapshots, archive_checks


def ranking(outputs, candidates):
    if len(outputs) != 2:
        raise ValueError("both candidates must be returned")
    seen, rows = set(), []
    for rank, (i, text, score) in enumerate(outputs, 1):
        if (type(i) is not int or i not in (0, 1) or i in seen
                or text != candidates[i]["text"] or not math.isfinite(score)):
            raise ValueError("invalid retrieval identity or score")
        seen.add(i)
        rows.append({"candidate_index": i, "doc_id": candidates[i]["doc_id"],
                     "text": text, "score": float(score), "original_rank": rank})
    if rows[0]["score"] < rows[1]["score"]:
        raise ValueError("retriever order is not score descending")
    ordered = sorted(rows, key=lambda r: (-r["score"], r["candidate_index"]))
    for row in rows:
        row["resolved_rank"] = ordered.index(row) + 1
        row["exact_tie"] = rows[0]["score"] == rows[1]["score"]
    return rows


def comparison(left, right):
    a = {r["candidate_index"]: r for r in left["outputs"]}
    b = {r["candidate_index"]: r for r in right["outputs"]}
    return {"kind": "comparison", "source_qa_id": left["source_qa_id"],
            "reference": left["condition"], "target": right["condition"],
            "primary": (left["condition"], right["condition"]) == CONTRASTS[0],
            "passage_deltas": [{"candidate_index": i, "doc_id": a[i]["doc_id"],
                "score_delta": b[i]["score"] - a[i]["score"],
                "original_rank_delta": b[i]["original_rank"] - a[i]["original_rank"],
                "resolved_rank_delta": b[i]["resolved_rank"] - a[i]["resolved_rank"]}
                for i in (0, 1)],
            "margin_delta": right["poison_minus_correct_margin"] - left["poison_minus_correct_margin"]}


def token_audit(tokenizer, texts, headers):
    """Mirror encoder batching; offsets are diagnostic only, never model inputs."""
    batch = tokenizer(texts, padding=True, truncation=True,
                      return_offsets_mapping=True, return_special_tokens_mask=True)
    audits = []
    for i, (text, header) in enumerate(zip(texts, headers)):
        full = tokenizer(text, truncation=False)["input_ids"]
        ids, mask = batch["input_ids"][i], batch["attention_mask"][i]
        effective = [token for token, attended in zip(ids, mask) if attended]
        truncated = effective != full
        offsets = batch["offset_mapping"][i]
        body = [{"position": j, "token_id": ids[j],
                 "body_offset": [start - len(header), end - len(header)]}
                for j, (start, end) in enumerate(offsets)
                if mask[j] and end > start and end > len(header)]
        audits.append({"text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                       "utf8_bytes": len(text.encode("utf-8")), "input_ids": ids,
                       "tokens": tokenizer.convert_ids_to_tokens(ids),
                       "attention_mask": mask, "special_tokens_mask": batch["special_tokens_mask"][i],
                       "token_type_ids": batch.get("token_type_ids", [None] * len(texts))[i],
                       "offset_mapping": offsets, "effective_length": sum(mask),
                       "untruncated_length": len(full), "truncated": truncated,
                       "body_tokens": body})
    if any(a["truncated"] for a in audits):
        raise ValueError("truncation detected; experiment refused")
    return audits


def structural_control(fresh, general):
    # Different header token identities are intended. Match lengths and the
    # entire body-token identity/position/offset sequence, not whole input IDs.
    reasons = []
    for key in ("effective_length", "body_tokens"):
        if fresh[key] != general[key]:
            reasons.append(key + " differs")
    return {"structurally_matched": not reasons, "structural_confounds": reasons,
            "definition": "equal effective lengths and identical body token IDs, positions and relative offsets; header IDs may differ"}


def validate_token_audit(audit, text, header):
    ids, mask = audit["input_ids"], audit["attention_mask"]
    offsets = audit["offset_mapping"]
    if (not ids or len(mask) != len(ids) or len(offsets) != len(ids)
            or len(audit["tokens"]) != len(ids)
            or len(audit["special_tokens_mask"]) != len(ids)
            or any(x not in (0, 1) for x in mask)
            or audit["truncated"] or sum(mask) != audit["effective_length"]
            or audit["effective_length"] != audit["untruncated_length"]
            or audit["text_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest()
            or audit["utf8_bytes"] != len(text.encode("utf-8"))):
        raise ValueError("token audit integrity mismatch")
    body = []
    for j, (start, end) in enumerate(offsets):
        if not 0 <= start <= end <= len(text):
            raise ValueError("invalid tokenizer offsets")
        if mask[j] and end > start and end > len(header):
            body.append({"position": j, "token_id": ids[j],
                         "body_offset": [start-len(header), end-len(header)]})
    if body != audit["body_tokens"]:
        raise ValueError("body token position mismatch")


def vector_record(vector):
    values = [float(x) for x in vector]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("invalid embedding")
    return {"values": values, "dimension": len(values), "dtype": "float32",
            "l2_norm": math.sqrt(math.fsum(x*x for x in values)),
            "sha256": hashlib.sha256(encoded([{"values": values}])).hexdigest()}


def reconstruct(query, candidate, score):
    if len(query) != len(candidate):
        raise ValueError("embedding dimension mismatch")
    total = math.fsum(q*d for q, d in zip(query, candidate))
    close(total, score)
    return {"float64_dot": total, "residual": total - score}


def load_backend(snapshot, env):
    for name, version in PINS.items():
        if (env["packages"].get(name) or "").split("+")[0] != version:
            raise ValueError(f"required {name}=={version}")
    # This function is reachable only through explicit --run-inference.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.manual_seed(42)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True,
                                               use_fast=True, trust_remote_code=False)
    model, info = AutoModel.from_pretrained(str(snapshot), local_files_only=True,
                                            trust_remote_code=False, output_loading_info=True)
    if any(info.get(k) for k in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
        raise ValueError(f"incompatible weight loading: {info}")
    if (not tokenizer.is_fast or model.config.model_type != "bert"
            or model.config.hidden_size != 768 or len(tokenizer) != model.config.vocab_size):
        raise ValueError("loaded tokenizer/model incompatible")
    model = model.to(device="cpu", dtype=torch.float32).eval()
    provenance = {"torch_build": torch.__config__.show(), "cpu_threads": torch.get_num_threads(),
                  "interop_threads": torch.get_num_interop_threads(),
                  "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                  "tokenizer_class": type(tokenizer).__name__, "model_class": type(model).__name__,
                  "tokenizer_backend": json.loads(tokenizer.backend_tokenizer.to_str()),
                  "tokenizer_options": {k: getattr(tokenizer, k, None) for k in
                                        ("do_lower_case", "clean_up_tokenization_spaces")},
                  "model_max_length": tokenizer.model_max_length,
                  "special_tokens_map": tokenizer.special_tokens_map,
                  "padding_side": tokenizer.padding_side, "truncation_side": tokenizer.truncation_side,
                  "model_config": model.config.to_dict(), "loading_info": info}
    return model, tokenizer, torch.device("cpu"), provenance


def measure_all(model, tokenizer, device):
    from src.retrieval.dense import encode_texts, retrieve_best
    measurements, vectors, contrasts = [], [], []
    for example in SYNTHETIC_EXAMPLES:
        records = render_conditions(example)
        saved = copy.deepcopy(records)
        group = {}
        for condition, record in records.items():
            texts = [c["text"] for c in record["candidates"]]
            query_audit = token_audit(tokenizer, [record["query"]], [""])[0]
            audits = token_audit(tokenizer, texts, ["", HEADERS[condition]])
            outputs = ranking(retrieve_best(record["query"], texts, model, tokenizer, device,
                                            top_k=20), record["candidates"])
            q = vector_record(encode_texts([record["query"]], model, tokenizer, device, batch_size=1)[0].tolist())
            ds = [vector_record(v) for v in encode_texts(texts, model, tokenizer, device).tolist()]
            for output in outputs:
                i = output["candidate_index"]
                output["reconstruction"] = reconstruct(q["values"], ds[i]["values"], output["score"])
            scores = {r["candidate_index"]: r["score"] for r in outputs}
            row = {"kind": "measurement", "source_qa_id": example.source_qa_id,
                   "condition": condition, "header": HEADERS[condition], "input": record,
                   "query_tokens": query_audit, "candidate_tokens": audits, "outputs": outputs,
                   "poison_minus_correct_margin": scores[1] - scores[0]}
            group[condition] = row
            measurements.append(row)
            vectors.append({"source_qa_id": example.source_qa_id, "condition": condition,
                            "query": q, "candidates": ds})
        control = structural_control(group["freshness"]["candidate_tokens"][1],
                                     group["general_notice"]["candidate_tokens"][1])
        for row in group.values():
            row["specificity_control"] = control
        contrasts.extend(comparison(group[a], group[b]) for a, b in CONTRASTS)
        if records != saved:
            raise ValueError("input mutation")
    return measurements, vectors, contrasts


def validate_results(rows, vectors):
    measured = [r for r in rows if r.get("kind") == "measurement"]
    contrasts = [r for r in rows if r.get("kind") == "comparison"]
    expected = {(e.source_qa_id, c) for e in SYNTHETIC_EXAMPLES for c in HEADERS}
    if (len(rows) != 13 or len(measured) != 6 or len(contrasts) != 6 or len(vectors) != 6
            or {(r["source_qa_id"], r["condition"]) for r in measured} != expected
            or {(r["source_qa_id"], r["condition"]) for r in vectors} != expected):
        raise ValueError("invalid result coverage")
    by_vector = {(r["source_qa_id"], r["condition"]): r for r in vectors}
    for example in SYNTHETIC_EXAMPLES:
        group = {r["condition"]: r for r in measured if r["source_qa_id"] == example.source_qa_id}
        if {c: r["input"] for c, r in group.items()} != render_conditions(example):
            raise ValueError("input control mismatch")
        control = structural_control(group["freshness"]["candidate_tokens"][1], group["general_notice"]["candidate_tokens"][1])
        for c, row in group.items():
            validate_token_audit(row["query_tokens"], row["input"]["query"], "")
            if len(row["candidate_tokens"]) != 2:
                raise ValueError("missing candidate token audit")
            for i, audit in enumerate(row["candidate_tokens"]):
                validate_token_audit(audit, row["input"]["candidates"][i]["text"],
                                     HEADERS[c] if i == 1 else "")
            rebuilt = ranking([(r["candidate_index"], r["text"], r["score"]) for r in row["outputs"]], row["input"]["candidates"])
            v = by_vector[(example.source_qa_id, c)]
            for item in [v["query"], *v["candidates"]]:
                if vector_record(item["values"]) != item or item["dimension"] != 768:
                    raise ValueError("embedding integrity mismatch")
            for output in rebuilt:
                i = output["candidate_index"]
                output["reconstruction"] = reconstruct(v["query"]["values"], v["candidates"][i]["values"], output["score"])
            scores = {r["candidate_index"]: r["score"] for r in rebuilt}
            if (rebuilt != row["outputs"] or row["poison_minus_correct_margin"] != scores[1]-scores[0]
                    or row["specificity_control"] != control):
                raise ValueError("measurement arithmetic mismatch")
        found = [r for r in contrasts if r["source_qa_id"] == example.source_qa_id]
        if found != [comparison(group[a], group[b]) for a, b in CONTRASTS]:
            raise ValueError("paired comparison mismatch")


def git_provenance():
    def git(*args):
        return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
                                       cwd=ROOT, text=True).strip()
    return {"commit": git("rev-parse", "HEAD"), "status": git("status", "--porcelain", "--untracked-files=normal")}


def execute(snapshot, snapshot_manifest, prior_dirs, out_dir, *, run_inference=False):
    if not run_inference:
        raise ValueError("real inference requires explicit --run-inference")
    out = Path(out_dir).resolve()
    if Path(out_dir).is_symlink() or out.exists() or not prior_dirs:
        raise ValueError("output must be new; at least one protected prior directory required")
    protected = [Path(p).resolve() for p in [*prior_dirs, snapshot, snapshot_manifest, ROOT / "src", ROOT / "configs"]]
    if any(out == p or p in out.parents or out in p.parents for p in protected):
        raise ValueError("output overlaps protected input")
    before, archives = protect(prior_dirs)
    identity = verify_snapshot(snapshot, snapshot_manifest)
    env = environment()
    source_hashes = {p: sha(ROOT / p) for p in SOURCES}
    model, tokenizer, device, backend = load_backend(snapshot, env)
    manifest = {"kind": "manifest", "schema": SCHEMA,
                "scope": "two_example_synthetic_diagnostic_not_attack_success",
                "environment": env, "backend": backend, "snapshot": identity,
                "source_sha256": source_hashes, "git": git_provenance(),
                "parameters": {"seed": 42, "device": "cpu", "dtype": "float32", "top_k": 20,
                               "query_batch_size": 1, "candidate_batch_size": 16},
                "score": "attention-mask mean pooling including attended special tokens; raw CPU dot product; no L2 normalization",
                "original_ties": "unchanged torch.topk; no guaranteed index tie breaker",
                "resolved_ties": "exact score descending then original candidate index ascending; near ties retained",
                "primary_contrast": "freshness minus general_notice",
                "delta_definition": "target minus reference; negative rank delta means improvement",
                "tolerance": {"absolute": ATOL, "relative": RTOL},
                "interpretation": "same-environment repeatability is not semantic freshness preference or successful poisoning"}
    first = measure_all(model, tokenizer, device)
    second = measure_all(model, tokenizer, device)
    if encoded([first]) != encoded([second]):
        raise ValueError("same-environment repeat mismatch")
    measured, vectors, contrasts = first
    rows = [manifest, *measured, *contrasts]
    result_bytes, vector_bytes = encoded(rows), encoded(vectors)
    validate_results([json.loads(x) for x in result_bytes.splitlines()],
                     [json.loads(x) for x in vector_bytes.splitlines()])
    after, _ = protect(prior_dirs)
    if (before != after or identity != verify_snapshot(snapshot, snapshot_manifest)
            or source_hashes != {p: sha(ROOT / p) for p in SOURCES}):
        raise ValueError("protected inputs changed")
    drift = []
    for example in SYNTHETIC_EXAMPLES:
        group = [v for v in vectors if v["source_qa_id"] == example.source_qa_id]
        scores = [{r["candidate_index"]: r["score"] for r in m["outputs"]}
                  for m in measured if m["source_qa_id"] == example.source_qa_id]
        drift.append({"source_qa_id": example.source_qa_id,
                      "query_vectors_identical": all(v["query"] == group[0]["query"] for v in group),
                      "correct_vectors_identical": all(v["candidates"][0] == group[0]["candidates"][0] for v in group),
                      "correct_raw_scores_identical": all(s[0] == scores[0][0] for s in scores),
                      "correct_raw_score_deltas_from_neutral": [s[0] - scores[0][0] for s in scores]})
    validation = {"validation": "passed", "measurement_count": 6, "passage_count": 12,
                  "comparison_count": 6, "same_environment_repeat_identical": True,
                  "cross_environment_bitwise_guarantee": False, "invariant_vector_audit": drift,
                  "prior_sha256_before": before, "prior_sha256_after": after, "known_archives": archives}
    out.mkdir(parents=True, exist_ok=False)
    for name, data in (("results.jsonl", result_bytes), ("embeddings.jsonl", vector_bytes),
                       ("validation.json", encoded([validation]))):
        with (out / name).open("xb") as stream:
            stream.write(data)
    with (out / "sha256.json").open("xb") as stream:
        stream.write(encoded([{name: sha(out / name) for name in
                               ("results.jsonl", "embeddings.jsonl", "validation.json")}]))
    if protect(prior_dirs)[0] != before or verify_snapshot(snapshot, snapshot_manifest) != identity:
        raise ValueError("protected inputs changed during writing; retain output for inspection")
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true", help="metadata and file checks only; no model loading")
    mode.add_argument("--run-inference", action="store_true", help="explicitly authorize real local model inference")
    parser.add_argument("--model-snapshot", required=True)
    parser.add_argument("--snapshot-manifest", required=True, help="independently trusted model/revision/file SHA-256 inventory")
    parser.add_argument("--prior-dir", action="append", default=[])
    parser.add_argument("--out-dir")
    parser.add_argument("--repeat-check", action="store_true", help="always enforced for inference")
    args = parser.parse_args()
    if args.preflight_only:
        identity = verify_snapshot(args.model_snapshot, args.snapshot_manifest)
        _, archives = protect(args.prior_dir)
        print(canonical_jsonl([{"snapshot": identity, "environment": environment(),
                               "known_archives": archives, "model_loaded": False}]), end="")
    else:
        if not args.out_dir or not args.prior_dir:
            parser.error("--run-inference requires --out-dir and --prior-dir")
        print(canonical_jsonl([execute(args.model_snapshot, args.snapshot_manifest,
                                      args.prior_dir, args.out_dir, run_inference=True)]), end="")


if __name__ == "__main__":
    main()
