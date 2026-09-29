"""
Weeks 3-4 | Gate A-5: single point where the four StreamingQA experiment
runners (run_*_streamingqa.py) read top_k/candidate_top_k/rrf_k/paths/
model names from configs/streamingqa_eval_config.yaml, instead of each
driver hardcoding its own copy of these values separately from what the
YAML documents. Before this, the YAML documented the experiment after the
fact; a change to top_k in the YAML did not change what any driver
actually ran with.

SCOPE (same convention as A2): this does NOT touch bm25.py, dense.py,
hybrid.py, reranker.py, or generate.py. Those five shared modules still
take their parameters as plain function arguments, unchanged. This loader
only changes WHERE the four drivers get the values they pass INTO those
functions -- from this file's read of the YAML, instead of a literal
duplicated in each driver's source. generate.py's load_model() and
reranker.py's load_reranker() both already accept a model name as an
argument; drivers now pass the YAML's value into that existing argument
rather than relying on the shared module's own hardcoded default.

FAIL LOUD, NOT SILENT: if a key the caller asks for is missing from the
YAML, this raises immediately, naming the exact missing key path. A
silent fallback to some undocumented default would defeat the point of
A5 -- one parameter source, not two that can drift apart unnoticed.

Usage (from a driver):
    from src.eval.config_loader import experiment_params
    _CFG = experiment_params("E1")
    INPUT_PATH = _CFG["input_path"]
    LOG_PATH = _CFG["log_path"]
    TOP_K = _CFG["top_k"]
    GENERATOR_MODEL = _CFG["generator_model"]
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/eval -> src -> repo root
EVAL_CONFIG_PATH = REPO_ROOT / "configs" / "streamingqa_eval_config.yaml"


def _get(d: dict, dotted_path: str):
    """Nested dict lookup by a dotted path (e.g. 'shared.generator.model'),
    raising a KeyError that names the exact missing segment -- so a typo
    or a config that hasn't caught up points directly at the problem
    instead of a bare 'KeyError: model' with no context.
    """
    node = d
    parts = dotted_path.split(".")
    for i, part in enumerate(parts):
        if not isinstance(node, dict) or part not in node:
            walked = ".".join(parts[: i + 1])
            raise KeyError(
                f"{EVAL_CONFIG_PATH.name} is missing '{walked}' "
                f"(looked up via '{dotted_path}'). Gate A-5 requires this "
                f"file to be the execution source of truth -- add the "
                f"missing key to the YAML rather than adding a hardcoded "
                f"fallback here."
            )
        node = node[part]
    return node


def load_eval_config(path: Path = EVAL_CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def experiment_params(experiment_key: str, path: Path = EVAL_CONFIG_PATH) -> dict:
    """Flat dict of everything one StreamingQA driver (E1-E4) needs,
    pulled from the shared block plus that experiment's own block. Only
    surfaces keys that actually vary across drivers -- add more here as
    drivers need them, rather than handing every caller the raw YAML.

    Always present: input_path, top_k, generator_model, log_path.
    Present only for hybrid/reranker experiments (E3/E4), read via
    exp.get() rather than _get() since E1/E2 legitimately don't have
    them: candidate_top_k, fused_top_k, final_top_k, rrf_k,
    reranker_model.
    """
    cfg = load_eval_config(path)
    exp = cfg["experiments"].get(experiment_key)
    if exp is None:
        raise KeyError(
            f"{EVAL_CONFIG_PATH.name} has no experiments.{experiment_key} block. "
            f"Known experiments: {sorted(cfg['experiments'].keys())}"
        )

    params = {
        "input_path": _get(cfg, "shared.input_path"),
        "top_k": _get(cfg, "shared.top_k"),
        "generator_model": _get(cfg, "shared.generator.model"),
        "log_path": exp.get("log_path"),
    }
    if params["log_path"] is None:
        raise KeyError(
            f"{EVAL_CONFIG_PATH.name}'s experiments.{experiment_key} block "
            f"is missing 'log_path'."
        )

    retriever = exp.get("retriever", {})
    if "candidate_top_k" in retriever:
        params["candidate_top_k"] = retriever["candidate_top_k"]
    if "fused_top_k" in retriever:
        params["fused_top_k"] = retriever["fused_top_k"]

    fusion = retriever.get("fusion", {})
    if "rrf_k" in fusion:
        params["rrf_k"] = fusion["rrf_k"]

    # final_top_k lives under the experiment directly for E4, and under
    # retriever for E3 -- both real locations in the current YAML, so
    # check both rather than assuming one schema.
    if "final_top_k" in exp:
        params["final_top_k"] = exp["final_top_k"]
    elif "final_top_k" in retriever:
        params["final_top_k"] = retriever["final_top_k"]

    reranker = exp.get("reranker", {})
    if "model" in reranker:
        params["reranker_model"] = reranker["model"]

    return params