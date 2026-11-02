"""CPU-only synthetic ranking diagnostics, with optional installed retrievers.

Run as a module for canonical JSONL on stdout. Never installs or downloads.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
import platform
from collections import Counter

from src.attacks.freshness_smoke import (
    SYNTHETIC_EXAMPLES, build_conditions, canonical_jsonl, validate_conditions,
)

REVISION = "2bd46a25019aeea091fd42d1f0fd4801675cf699"
MODEL = "facebook/contriever"
PARAMETERS = {"seed": 42, "top_k": 20, "final_top_k": 5, "rrf_k": 60,
              "device": "cpu", "dtype": "float32", "cpu_threads": 1,
              "tie_policy": "exact score descending, original candidate index ascending"}
DEFINITIONS = {
    "bm25": "Raw BM25Okapi scores, split(' '), case sensitive; per-condition corpus fit; k1=1.5, b=0.75, epsilon=0.25.",
    "dense": "Raw Contriever mean-pooled embedding dot product; no L2 or corpus normalization.",
    "hybrid": "RRF sum of 1/(60+one_based_component_rank); ranks only, not similarity.",
    "score_delta": "target minus reference, within one retriever only",
    "rank_delta": "target minus reference; negative means improved rank",
    "margin": "poison score minus correct score, within one condition/retriever",
}


def _hash(value):
    return hashlib.sha256(canonical_jsonl([value]).encode("utf-8")).hexdigest()


def inspect_environment():
    """Inspect installed metadata and the exact local snapshot without inference."""
    versions = {}
    for name in ("rank-bm25", "numpy", "torch", "transformers", "huggingface-hub"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    snapshot = hub / "models--facebook--contriever" / "snapshots" / REVISION
    names = ("config.json", "pytorch_model.bin", "model.safetensors", "tokenizer.json",
             "tokenizer_config.json", "special_tokens_map.json", "vocab.txt")
    files = {name: (snapshot / name).stat().st_size
             for name in names if (snapshot / name).is_file()}
    return {"python": platform.python_version(), "platform": platform.platform(),
            "dependencies": versions, "model": MODEL, "revision": REVISION,
            "cache_files_bytes": files, "local_only": True}, snapshot


def _unavailable(reason):
    return {"status": "unavailable", "reason": reason}


def load_backends(environment, snapshot):
    """Load only installed components, with the dense model explicitly on CPU.

    Existing automatic CUDA-selecting model loaders are intentionally not used.
    Returns callables plus explicit component availability, never fallback scores.
    """
    backends, status = {}, {}
    deps = environment["dependencies"]
    if deps["rank-bm25"] is None:
        status["bm25"] = _unavailable("rank-bm25 is not installed")
    else:
        try:
            from src.retrieval.bm25 import retrieve_best
            backends["bm25"] = lambda q, texts: retrieve_best(q, texts, top_k=20)
            status["bm25"] = {"status": "available"}
        except Exception as exc:
            status["bm25"] = _unavailable(f"BM25 import failed: {type(exc).__name__}: {exc}")
    if any(deps[name] is None for name in ("torch", "transformers", "huggingface-hub")):
        status["dense"] = _unavailable("required dense dependencies are not installed; loading not attempted")
    elif not snapshot.is_dir():
        status["dense"] = _unavailable("exact revision snapshot is absent; loading not attempted")
    else:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
            from src.retrieval.dense import retrieve_best
            torch.manual_seed(42)
            torch.set_num_threads(1)
            torch.use_deterministic_algorithms(True)
            tokenizer = AutoTokenizer.from_pretrained(str(snapshot), local_files_only=True)
            model = AutoModel.from_pretrained(str(snapshot), local_files_only=True)
            model = model.to(device="cpu", dtype=torch.float32).eval()
            backends["dense"] = lambda q, texts: retrieve_best(
                q, texts, model, tokenizer, torch.device("cpu"), top_k=20)
            status["dense"] = {"status": "available", "load_attempted": True}
        except Exception as exc:
            status["dense"] = _unavailable(f"exact local CPU load failed: {type(exc).__name__}: {exc}")
    if all(k in backends for k in ("bm25", "dense")):
        from src.retrieval.hybrid import reciprocal_rank_fusion
        backends["rrf"] = reciprocal_rank_fusion
        status["hybrid"] = {"status": "available"}
    else:
        status["hybrid"] = _unavailable("requires available BM25 and dense components")
    return backends, status


def corpus_statistics(row, include_bm25=False):
    tokens = [c["text"].split(" ") for c in row["candidates"]]
    df = Counter(token for passage in tokens for token in set(passage))
    result = {"document_count": len(tokens), "space_split_lengths": list(map(len, tokens)),
              "average_space_split_length": sum(map(len, tokens)) / len(tokens),
              "vocabulary_size": len(df), "document_frequencies": dict(sorted(df.items()))}
    if include_bm25:
        from rank_bm25 import BM25Okapi
        index = BM25Okapi(tokens)
        result["bm25"] = {"k1": index.k1, "b": index.b, "epsilon": index.epsilon,
                          "average_idf": index.average_idf, "effective_idf": dict(sorted(index.idf.items()))}
    return result


def ranking_view(outputs, candidates):
    """Preserve original order, add an explicitly separate deterministic view."""
    if len(outputs) != len(candidates):
        raise ValueError("retriever must return every candidate")
    seen = set()
    for index, text, score in outputs:
        if (type(index) is not int or index in seen or not 0 <= index < len(candidates)
                or text != candidates[index]["text"] or not math.isfinite(score)):
            raise ValueError("invalid retrieval output")
        seen.add(index)
    scores = Counter(float(item[2]) for item in outputs)
    deterministic = sorted(outputs, key=lambda item: (-float(item[2]), item[0]))
    resolved_rank = {item[0]: rank for rank, item in enumerate(deterministic, 1)}
    original = []
    for rank, (index, text, score) in enumerate(outputs, 1):
        original.append({"candidate_index": index, "doc_id": candidates[index]["doc_id"],
                         "text": text, "score": float(score), "original_rank": rank,
                         "resolved_rank": resolved_rank[index], "score_tied": scores[float(score)] > 1})
    return {"status": "available", "original_outputs": original,
            "deterministic_order": [item[0] for item in deterministic],
            "original_order": [item[0] for item in outputs]}


def _triples(view):
    by_index = {item["candidate_index"]: item for item in view["original_outputs"]}
    return [(i, by_index[i]["text"], by_index[i]["score"]) for i in view["deterministic_order"]]


def compare(reference, target, retriever):
    """Keep score deltas and both rank-view deltas in distinct named fields."""
    left, right = reference["retrievers"][retriever], target["retrievers"][retriever]
    base = {"kind": "comparison", "source_qa_id": reference["input"]["source_qa_id"],
            "retriever": retriever, "reference": reference["input"]["condition"],
            "target": target["input"]["condition"],
            "candidate_set_changed": len(reference["input"]["candidates"]) != len(target["input"]["candidates"])}
    if left["status"] != "available" or right["status"] != "available":
        return dict(base, **_unavailable("one or both condition measurements unavailable"))
    a = {r["doc_id"]: r for r in left["original_outputs"]}
    b = {r["doc_id"]: r for r in right["original_outputs"]}
    deltas = []
    for role in ("correct", "poison"):
        doc_id = base["source_qa_id"] + ":" + role
        if doc_id not in a or doc_id not in b:
            deltas.append({"doc_id": doc_id, "role": role, "score_delta": None,
                           "original_rank_delta": None, "resolved_rank_delta": None,
                           "reason": "passage absent in reference or target"})
        else:
            deltas.append({"doc_id": doc_id, "role": role,
                           "score_delta": b[doc_id]["score"] - a[doc_id]["score"],
                           "original_rank_delta": b[doc_id]["original_rank"] - a[doc_id]["original_rank"],
                           "resolved_rank_delta": b[doc_id]["resolved_rank"] - a[doc_id]["resolved_rank"]})
    def margin(items):
        correct, poison = (base["source_qa_id"] + ":" + role for role in ("correct", "poison"))
        return items[poison]["score"] - items[correct]["score"] if poison in items else None
    before, after = margin(a), margin(b)
    return dict(base, status="available", deltas=deltas,
                reference_margin=before, target_margin=after,
                margin_delta=after - before if before is not None and after is not None else None)


def run_experiment(backends, availability, environment, examples=SYNTHETIC_EXAMPLES):
    """Run fixed inputs; backend injection supports bookkeeping tests only."""
    root = Path(__file__).resolve().parents[2]
    source_paths = ("src/attacks/freshness_smoke.py", "src/retrieval/bm25.py",
                    "src/retrieval/dense.py", "src/retrieval/hybrid.py",
                    "configs/streamingqa_eval_config.yaml", "configs/model_revisions.yaml")
    source_hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                     for name in source_paths}
    result = [{"kind": "manifest", "schema": "chronoguard.synthetic-ranking-smoke/v1",
               "scope": "synthetic_diagnostics_not_attack_success_rate",
               "parameters": PARAMETERS.copy(), "environment": copy.deepcopy(environment),
               "score_definitions": DEFINITIONS.copy(), "availability": copy.deepcopy(availability),
               "source_sha256": source_hashes,
               "rrf_component_order": "deterministic score/index order, not original retriever order"}]
    for example in examples:
        rows = build_conditions(example, seed=42)
        validate_conditions(rows, example, seed=42)
        saved = copy.deepcopy(rows)
        measurements = []
        for row in rows:
            views = {}
            texts = [c["text"] for c in row["candidates"]]
            for name in ("bm25", "dense"):
                if name not in backends:
                    views[name] = copy.deepcopy(availability[name])
                    continue
                try:
                    views[name] = ranking_view(backends[name](row["query"], texts.copy()), row["candidates"])
                except Exception as exc:
                    views[name] = _unavailable(f"retrieval failed: {type(exc).__name__}: {exc}")
            if (all(views[n]["status"] == "available" for n in ("bm25", "dense"))
                    and "rrf" in backends):
                fused = backends["rrf"](_triples(views["bm25"]), _triples(views["dense"]),
                                         top_k=5, rrf_k=60)
                views["hybrid"] = ranking_view(fused, row["candidates"])
                views["hybrid"]["component_orders"] = {
                    n: views[n]["deterministic_order"] for n in ("bm25", "dense")}
            else:
                views["hybrid"] = _unavailable("required component ranking or RRF implementation unavailable")
            measurement = {"kind": "measurement", "input": copy.deepcopy(row), "input_sha256": _hash(row),
                           "retrievers": views,
                           "corpus_statistics": corpus_statistics(row, "bm25" in backends)}
            measurements.append(measurement)
            result.append(measurement)
        if rows != saved:
            raise ValueError("experiment mutated input records")
        for name in ("bm25", "dense", "hybrid"):
            for left, right in ((1, 2), (0, 1), (0, 2)):
                result.append(compare(measurements[left], measurements[right], name))
    return result


def main():
    environment, snapshot = inspect_environment()
    backends, availability = load_backends(environment, snapshot)
    print(canonical_jsonl(run_experiment(backends, availability, environment)), end="")


if __name__ == "__main__":
    main()
