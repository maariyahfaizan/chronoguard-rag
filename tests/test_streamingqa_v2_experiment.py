"""No-model synthetic integration smoke through the real persistence reader."""
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_streamingqa_v2_persistence import bundle, dump
from src.eval import streamingqa_v2_experiment as adapter
from src.eval import streamingqa_v2_persistence as persistence
from src.eval.week4_v2_schema import SchemaError


class FakeBackend:
    """Deterministic test double; not scientific retrieval or generation."""
    def __init__(self):
        self.calls = []

    def bm25(self, query, texts, top_k):
        self.calls.append(("bm25", list(texts), top_k))
        return [(i, t, float(len(texts) - i)) for i, t in enumerate(texts)][:top_k]

    def dense(self, query, texts, top_k):
        self.calls.append(("dense", list(texts), top_k))
        return [(i, texts[i], float(i)) for i in reversed(range(len(texts)))][:top_k]

    def fuse(self, first, second, top_k, rrf_k):
        self.calls.append(("fusion", rrf_k, top_k))
        # Same index-keyed RRF equation, without importing torch in this smoke.
        scores, texts = {}, {}
        for rows in (first, second):
            for rank, (i, text, _) in enumerate(rows, 1):
                scores[i] = scores.get(i, 0) + 1 / (rrf_k + rank)
                texts[i] = text
        return [(i, texts[i], score) for i, score in
                sorted(scores.items(), key=lambda x: x[1], reverse=True)][:top_k]

    def rerank(self, query, rows, top_k, batch_size):
        self.calls.append(("reranker", batch_size, top_k))
        return list(reversed(rows))[:top_k]

    def generate(self, query, passages):
        self.calls.append(("generate", query, list(passages)))
        return "Paris"


@pytest.mark.parametrize("system,stages", [
    ("E1", ["bm25"]), ("E2", ["dense"]),
    ("E3", ["bm25", "dense", "fusion"]),
    ("E4", ["bm25", "dense", "fusion", "reranker"])])
def test_synthetic_smoke(bundle, tmp_path, monkeypatch, system, stages):
    records, frame, kwargs = bundle
    files, digest = persistence.serialize_package(records, frame, **kwargs)
    package = dump(tmp_path, files)
    monkeypatch.setattr(adapter, "RESULTS_ROOT", tmp_path / "results/week4_v2")
    before = {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}
    historical = [Path("scripts") / name for name in (
        "run_baseline_streamingqa.py", "run_dense_streamingqa.py",
        "run_hybrid_streamingqa.py", "run_hybrid_reranker_streamingqa.py")]
    historical += list(Path("logs").glob("*streamingqa*"))
    hashes = {p: persistence.sha(p.read_bytes()) for p in historical if p.is_file()}
    backend = FakeBackend()
    target = adapter.execute(package, "smoke", system, expected_manifest_sha256=digest,
                             backend=backend, limit=1)
    row = persistence.decode_json((target / "answers.jsonl").read_bytes())
    original = records[0]
    assert row["source_envelope"]["record"] == original
    assert list(row["retrieval_stages"]) == sorted(stages)  # JSON codec sorts keys
    assert {c[0] for c in backend.calls} == set(stages + ["generate"])
    ids = row["ordered_child_occurrence_ids"]
    assert len(ids) == len(set(ids))
    canonical = [c["canonical_child_id"] for c in original["candidates"]]
    assert len(set(canonical)) < len(canonical)
    for stage in row["retrieval_stages"].values():
        assert all(r["child_occurrence_id"] == ids[r["index"]] for r in stage)
    for call in backend.calls:
        if call[0] in ("bm25", "dense"):
            assert call[1] == [c["child_text"] for c in original["candidates"]]
    assert row["metrics"]["answer_em"]["value"] == 1
    assert all(c["relevance_grade"] == c["temporal_validity"] == "UNKNOWN"
               for c in row["source_envelope"]["record"]["candidates"])
    assert all(m["denominator"] == 0 and m["value"] is None and m["reason"]
               for name, m in row["metrics"].items() if not name.startswith("answer_"))
    assert before == {p: p.read_bytes() for p in before}
    assert hashes == {p: persistence.sha(p.read_bytes()) for p in hashes}
    with pytest.raises(FileExistsError):
        adapter.execute(package, "smoke", system, expected_manifest_sha256=digest, backend=backend)


def test_execute_production_runtime_metadata(bundle, tmp_path, monkeypatch):
    # Reproduce torch.torch_version.TorchVersion without importing torch.
    class TorchVersion(str):
        pass

    version = TorchVersion("2.5.1+cu124")
    with pytest.raises(SchemaError, match="UNSUPPORTED_JSON_VALUE"):
        persistence.encode_json({"runtime": {"torch": version}})
    torch = SimpleNamespace(
        __version__=version, version=SimpleNamespace(cuda="12.4"),
        manual_seed=Mock(),
        cuda=SimpleNamespace(is_available=Mock(return_value=False), manual_seed_all=Mock()))
    monkeypatch.setitem(sys.modules, "torch", torch)
    backend = FakeBackend()
    factory = Mock(return_value=backend)
    monkeypatch.setattr(adapter, "ModelBackend", factory)
    monkeypatch.setattr(adapter, "RESULTS_ROOT", tmp_path / "results")
    records, frame, kwargs = bundle
    files, digest = persistence.serialize_package(records, frame, **kwargs)
    package = dump(tmp_path, files)

    target = adapter.execute(package, "runtime", "E1",
                             expected_manifest_sha256=digest, limit=1)

    assert (target / "run.json").is_file()
    metadata = persistence.decode_json((target / "run.json").read_bytes())
    assert metadata == {
        "manifest_sha256": digest,
        "manifest": adapter.load_pool(package, digest)[1],
        "configuration": adapter.configuration(), "system": "E1", "limit": 1,
        "backend": "production", "limitations": adapter.LIMITATIONS,
        "status": "COMPLETE",
        "runtime": {"torch": "2.5.1+cu124", "cuda": "12.4", "cuda_available": False},
    }
    factory.assert_called_once_with(adapter.configuration())
    torch.manual_seed.assert_called_once_with(metadata["configuration"]["seed"])
    torch.cuda.manual_seed_all.assert_not_called()
    assert [call[0] for call in backend.calls] == ["bm25", "generate"]
    assert (target / "answers.jsonl").is_file()
    assert (target / "summary.json").is_file()


def test_failed_execute_preserves_artifacts_and_retry_uses_new_name(bundle, tmp_path, monkeypatch):
    class FailingBackend(FakeBackend):
        def generate(self, query, passages):
            raise RuntimeError("mock generation failure")

    records, frame, kwargs = bundle
    files, digest = persistence.serialize_package(records, frame, **kwargs)
    package = dump(tmp_path, files)
    root = tmp_path / "results"
    monkeypatch.setattr(adapter, "RESULTS_ROOT", root)
    with pytest.raises(RuntimeError, match="mock generation failure"):
        adapter.execute(package, "failed", "E1", expected_manifest_sha256=digest,
                        backend=FailingBackend(), limit=1)
    failed = root / "failed"
    before = {p: p.read_bytes() for p in failed.iterdir()}
    assert persistence.decode_json(before[failed / "run.json"])["status"] == "INCOMPLETE"
    assert before[failed / "answers.jsonl"] == b""
    assert not (failed / "summary.json").exists()
    with pytest.raises(FileExistsError):
        adapter.execute(package, "failed", "E1", expected_manifest_sha256=digest,
                        backend=FakeBackend(), limit=1)
    retry = adapter.execute(package, "failed_retry1", "E1", expected_manifest_sha256=digest,
                            backend=FakeBackend(), limit=1)
    assert persistence.decode_json((retry / "run.json").read_bytes())["status"] == "COMPLETE"
    assert before == {p: p.read_bytes() for p in failed.iterdir()}


def test_manifest_rejection_and_read_only_cli(bundle, tmp_path):
    records, frame, kwargs = bundle
    files, digest = persistence.serialize_package(records, frame, **kwargs)
    package = dump(tmp_path, files)
    with pytest.raises(SchemaError, match="MANIFEST_CHECKSUM"):
        adapter.load_pool(package, "0" * 64)
    command = [sys.executable, "-B", "scripts/run_streamingqa_v2.py", str(package),
               "--expected-manifest-sha256", digest]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "VERIFIED_READ_ONLY" in result.stdout


def test_no_parent_relevance_leakage(bundle):
    records, _, _ = bundle
    first = {"record": records[0]}
    changed = deepcopy(first)
    for parent in changed["record"]["parents"]:
        parent["historical_relevance_flag"] = False
        parent["original_source_record"]["is_source_document"] = False
    a = adapter.evaluate_record(first, "E4", FakeBackend())
    b = adapter.evaluate_record(changed, "E4", FakeBackend())
    assert a["metrics"] == b["metrics"]
    assert a["retrieved"] == b["retrieved"]


def test_bad_retrieval_binding(bundle):
    class Broken(FakeBackend):
        def bm25(self, *args, **kwargs):
            return [(99999, "wrong", 1)]
    with pytest.raises(ValueError, match="binding"):
        adapter.evaluate_record({"record": bundle[0][0]}, "E1", Broken())


def test_optional_real_package():
    path = Path("data/processed/week4_v2/a15_full_roundtrip_v1")
    if not path.is_dir():
        pytest.skip("A15 package not available")
    envelopes, manifest = adapter.load_pool(path)
    assert len(envelopes) == 100
    assert manifest["expected_counts"]["child_occurrences"] == 2072
