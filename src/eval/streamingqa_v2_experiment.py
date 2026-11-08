"""Occurrence-preserving Week 4 v2 engineering adapter; no annotation inference."""
from copy import deepcopy
import math
from pathlib import Path
import platform
import random

from . import streamingqa_v2_persistence as persistence
from .config_loader import experiment_params, load_eval_config, model_revisions
from .metrics import exact_match, f1_score

A15_SHA256 = "54bcdb17b8ba086c2a1a2208e0621bdac6713ded619b414a02f8c04b4424ba1a"
RESULTS_ROOT = Path(__file__).resolve().parents[2] / "results/week4_v2"
SYSTEMS = ("E1", "E2", "E3", "E4")
LIMITATIONS = [
    "Engineering execution does not confer scientific approval or execution authorization.",
    "No approved child annotation artifact is consumed; relevance and temporal metrics are unavailable.",
    "Answer scores compare preserved, unreviewed answer aliases only; they do not validate evidence.",
    "Recorded chronology and source authentication are separate; neither filters the pool.",
    "Generation retains the historical 1500-character passage cap and 64-token greedy decoding.",
    "Model tokenizers may truncate query/passage pairs; content-token accounting excludes special tokens.",
    "Pinned revisions are repository pins, not reconstructed historical Week 4 revisions.",
]


def load_pool(directory, expected_manifest_sha256=A15_SHA256):
    return persistence.read_package(directory, expected_manifest_sha256=expected_manifest_sha256)


def configuration():
    cfg = load_eval_config()
    generator = cfg["shared"]["generator"]
    if (generator["decoding"] != {"do_sample": False, "max_new_tokens": 64}
            or generator["max_passage_chars"] != 1500 or generator["quantization"] != "4-bit"):
        raise ValueError("Generation configuration incompatible with shared generation interface")
    return {"evaluation": cfg, "model_revisions": model_revisions(),
            "seed": cfg["shared"]["seed"], "deterministic_execution_verified": False,
            "python": platform.python_version(),
            "adapter_sha256": persistence.sha(Path(__file__).read_bytes())}


def _checked(results, texts):
    results = list(results)
    indices = []
    for index, passage, score in results:
        if (type(index) is not int or not 0 <= index < len(texts)
                or passage != texts[index] or not math.isfinite(float(score))):
            raise ValueError("Invalid retrieval index/text/score binding")
        indices.append(index)
    if len(set(indices)) != len(indices):
        raise ValueError("Duplicate retrieval occurrence index")
    return results


def evaluate_record(envelope, system, backend):
    """Backend uses existing tuple APIs; only answer metrics are eligible."""
    if system not in SYSTEMS:
        raise ValueError("Unknown experiment")
    q = envelope["record"]
    texts = [c["child_text"] for c in q["candidates"]]
    query = q["original_question"]
    params = experiment_params(system)
    final_k = params.get("final_top_k", params["top_k"])
    candidate_k = params.get("candidate_top_k", final_k)
    stages = {}
    if system != "E2":
        stages["bm25"] = _checked(backend.bm25(query, texts, top_k=candidate_k), texts)
    if system != "E1":
        stages["dense"] = _checked(backend.dense(query, texts, top_k=candidate_k), texts)
    if system in ("E3", "E4"):
        stages["fusion"] = _checked(backend.fuse(stages["bm25"], stages["dense"],
            top_k=params.get("fused_top_k", final_k), rrf_k=params["rrf_k"]), texts)
        selected = stages["fusion"]
        if system == "E4":
            stages["reranker"] = _checked(backend.rerank(query, selected, top_k=final_k,
                                                        batch_size=8), texts)
            if not {r[0] for r in stages["reranker"]} <= {r[0] for r in selected}:
                raise ValueError("Reranker introduced an occurrence")
            selected = stages["reranker"]
    else:
        selected = stages["bm25" if system == "E1" else "dense"]
    if len(selected) > final_k:
        raise ValueError("Retrieval exceeded configured top-k")
    answer = backend.generate(query, [r[1] for r in selected])
    metrics = {}
    for name, value in (("answer_em", exact_match(answer, q["gold_answer"], q["gold_aliases"])),
                        ("answer_f1", f1_score(answer, q["gold_answer"], q["gold_aliases"]))):
        metrics[name] = {"value": value, "eligible": True, "denominator": 1,
                         "basis": "preserved_unreviewed_answer_aliases"}
    for name in (f"recall_at_{final_k}", f"ndcg_at_{final_k}",
                 f"fraction_top_{final_k}_violating", f"valid_evidence_recall_at_{final_k}",
                 "time_valid_answer_accuracy"):
        metrics[name] = {"value": None, "eligible": False, "denominator": 0,
                         "reason": "No provenance-bound explicitly approved child annotations"}
    def entries(rows):
        return [{"index": i, "child_occurrence_id": q["candidates"][i]["child_occurrence_id"],
                 "score": float(score)} for i, _, score in rows]
    return {"system": system, "source_envelope": deepcopy(envelope),
            "ordered_child_occurrence_ids": [c["child_occurrence_id"] for c in q["candidates"]],
            "retrieval_stages": {k: entries(v) for k, v in stages.items()},
            "retrieved": entries(selected), "generated_answer": answer, "metrics": metrics,
            "limitations": LIMITATIONS, "scientific_approval": "NOT_GRANTED"}


class ModelBackend:
    """Lazy loading: constructing this class alone never downloads a model."""
    def __init__(self, config):
        self.config = config
        self.models = {}

    def bm25(self, *args, **kwargs):
        from src.retrieval.bm25 import retrieve_best
        return retrieve_best(*args, **kwargs)

    def dense(self, query, texts, **kwargs):
        from src.retrieval.dense import load_dense_model, retrieve_best
        name = "facebook/contriever"
        if "dense" not in self.models:
            self.models["dense"] = load_dense_model(name, self.config["model_revisions"][name])
        return retrieve_best(query, texts, *self.models["dense"], **kwargs)

    def fuse(self, *args, **kwargs):
        from src.retrieval.hybrid import reciprocal_rank_fusion
        return reciprocal_rank_fusion(*args, **kwargs)

    def rerank(self, query, candidates, **kwargs):
        from src.retrieval.reranker import load_reranker, rerank
        name = experiment_params("E4")["reranker_model"]
        if "reranker" not in self.models:
            self.models["reranker"] = load_reranker(name, self.config["model_revisions"][name])[0]
        return rerank(query, candidates, self.models["reranker"], **kwargs)

    def generate(self, query, passages):
        from src.generation.generate import load_model, generate_answer
        name = self.config["evaluation"]["shared"]["generator"]["model"]
        if "generator" not in self.models:
            self.models["generator"] = load_model(name, self.config["model_revisions"][name])
        return generate_answer(query, passages, *self.models["generator"])


def execute(directory, run_name, system, *, expected_manifest_sha256=A15_SHA256,
            backend=None, limit=None):
    """Explicit caller authorization required; writes only a new v2 run directory."""
    envelopes, manifest = load_pool(directory, expected_manifest_sha256)
    if system not in SYSTEMS or not run_name or any(c not in
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in run_name):
        raise ValueError("Invalid system/run name")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be positive")
    config = configuration()
    target = RESULTS_ROOT / run_name
    target.mkdir(parents=True, exist_ok=False)
    metadata = {"manifest_sha256": expected_manifest_sha256, "manifest": manifest,
                "configuration": config, "system": system, "limit": limit,
                "backend": "production" if backend is None else "injected_test_backend",
                "limitations": LIMITATIONS, "status": "INCOMPLETE"}
    (target / "run.json").write_bytes(persistence.encode_json(metadata) + b"\n")
    random.seed(config["seed"])
    if backend is None:
        import torch
        torch.manual_seed(config["seed"])
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(config["seed"])
        # TorchVersion is a str subclass; A14 requires an exact built-in str.
        metadata["runtime"] = {"torch": str(torch.__version__), "cuda": torch.version.cuda,
                               "cuda_available": torch.cuda.is_available()}
        backend = ModelBackend(config)
    rows = []
    with (target / "answers.jsonl").open("xb") as stream:
        for envelope in envelopes[:limit]:
            row = evaluate_record(envelope, system, backend)
            stream.write(persistence.encode_json(row) + b"\n")
            stream.flush()
            rows.append(row)
    summary = {}
    for metric in rows[0]["metrics"]:
        values = [r["metrics"][metric]["value"] for r in rows
                  if r["metrics"][metric]["eligible"]]
        summary[metric] = {"value": sum(values) / len(values) if values else None,
                           "denominator": len(values), "total_questions": len(rows),
                           "reason": None if values else rows[0]["metrics"][metric]["reason"]}
    (target / "summary.json").write_bytes(persistence.encode_json(summary) + b"\n")
    metadata["status"] = "COMPLETE"
    (target / "run.json").write_bytes(persistence.encode_json(metadata) + b"\n")
    return target
