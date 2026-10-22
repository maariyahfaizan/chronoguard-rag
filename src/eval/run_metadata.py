"""Per-run and per-row provenance for StreamingQA E1-E4 logs (pre-Week-6 item 6).

attack_log_fields(row) is merged into every log row by the four drivers. It
records the pool's actual attack condition instead of a hardcoded "clean".
For a clean row (no attack fields) it returns only
{"attack_condition": "clean"}, so clean-run logs keep their Week-4 shape.

build_run_metadata(...) describes one (pool, experiment) run: model names
and pinned revisions, config hash, pool hash, git commit, seeds and
package/environment versions. The runner passes it to the driver, which
stores it on every row under "run_metadata".
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

PACKAGES = ("torch", "transformers", "sentence-transformers", "rank-bm25",
            "bitsandbytes", "accelerate", "numpy", "PyYAML")


def attack_log_fields(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Attack identity fields copied from a pool record into its log row."""
    fields: Dict[str, Any] = {"attack_condition": row.get("attack_condition", "clean")}

    if "source_qa_id" in row:
        fields["source_qa_id"] = row["source_qa_id"]

    meta = row.get("attack_metadata")
    if meta:
        fields.update({
            "attack_type": meta.get("attack_type"),
            "attack_protocol_version": row.get("attack_protocol_version"),
            "poison_count": row.get("poison_count", meta.get("actual_poison_count")),
            "attack_seed": meta.get("seed"),
            "poison_target_indices": meta.get("target_indices"),
            "poison_target_doc_ids": meta.get("target_doc_ids"),
        })

    return fields


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_json(obj: Any) -> str:
    """Hash of a JSON-serialisable object with sorted keys (stable across runs)."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_info(root: Path = REPO_ROOT) -> Dict[str, Any]:
    def run(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True,
                                  check=True, cwd=root).stdout.strip()
        except Exception:
            return None

    status = run("status", "--porcelain")
    return {"commit": run("rev-parse", "HEAD"),
            "dirty": None if status is None else bool(status)}


def environment_info() -> Dict[str, Any]:
    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = importlib_metadata.version(package)
        except importlib_metadata.PackageNotFoundError:
            versions[package] = None

    info: Dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": versions,
    }

    try:
        import torch

        info["cuda"] = torch.version.cuda
        info["cuda_available"] = torch.cuda.is_available()
        info["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:  # torch missing locally
        info["cuda"] = info["cuda_available"] = info["gpu"] = None

    return info


def build_run_metadata(
    *,
    experiment: str,
    pool_name: str,
    pool_path: str | Path,
    params: Mapping[str, Any],
    models: Mapping[str, Mapping[str, Any]],
    config_files: Mapping[str, str | Path],
    torch_seed: Optional[int],
    attack_base_seed: Optional[int],
    protocol_version: Optional[str],
    git: Optional[Mapping[str, Any]] = None,
    environment: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe one (pool, experiment) run.

    models maps role -> {"name", "pinned_revision", "loaded_revision"}.
    config_hash covers the experiment params, the model pins and the bytes
    of every config file, so any change to what was run changes the hash.
    """
    config_file_hashes = {label: sha256_file(path) for label, path in config_files.items()}
    model_pins = {role: {"name": m["name"], "revision": m["pinned_revision"]}
                  for role, m in models.items()}

    return {
        "experiment": experiment,
        "pool": pool_name,
        "pool_path": str(Path(pool_path).as_posix()),
        "pool_sha256": sha256_file(pool_path),
        "attack_protocol_version": protocol_version,
        "attack_base_seed": attack_base_seed,
        "torch_seed": torch_seed,
        "decoding": "greedy (do_sample=False)",
        "models": dict(models),
        "params": dict(params),
        "config_files_sha256": config_file_hashes,
        "config_hash": sha256_json({"params": dict(params), "models": model_pins,
                                    "files": config_file_hashes}),
        "git": dict(git) if git is not None else git_info(),
        "environment": dict(environment) if environment is not None else environment_info(),
    }
