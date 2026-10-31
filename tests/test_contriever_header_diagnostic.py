"""Bookkeeping fixtures are artificial and never experimental measurements."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from src.eval import contriever_header_diagnostic as d


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def snapshot_fixture(tmp_path):
    snapshot = tmp_path / d.REVISION
    snapshot.mkdir()
    config = {"model_type": "bert", "hidden_size": 768, "num_hidden_layers": 12}
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json",
                 "special_tokens_map.json", "vocab.txt", "pytorch_model.bin"):
        write_json(snapshot / name, config if name == "config.json" else {})
    manifest = tmp_path / "trusted.json"
    write_json(manifest, {"model": d.MODEL, "revision": d.REVISION,
                          "files": {p.name: d.sha(p) for p in snapshot.iterdir()}})
    return snapshot, manifest


@pytest.mark.parametrize("example", d.SYNTHETIC_EXAMPLES)
def test_exact_construction_and_isolation(example):
    records = d.render_conditions(example)
    saved = copy.deepcopy(records)
    for c, header in d.HEADERS.items():
        normalized = copy.deepcopy(records[c])
        assert normalized["candidates"][1]["text"].encode() == (header + example.incorrect_claim).encode()
        normalized["candidates"][1]["text"] = example.incorrect_claim
        assert normalized == records["neutral"]
        assert [x["doc_id"] for x in normalized["candidates"]] == [example.source_qa_id + ":correct", example.source_qa_id + ":poison"]
    records["freshness"]["candidates"][0]["source_metadata"]["origin"] = "changed"
    assert records["neutral"] == saved["neutral"]


def candidates():
    return d.render_conditions(d.SYNTHETIC_EXAMPLES[0])["neutral"]["candidates"]


def test_native_ties_preserved_separate_resolution():
    cs = candidates()
    rows = d.ranking([(1, cs[1]["text"], 2.), (0, cs[0]["text"], 2.)], cs)
    assert [r["candidate_index"] for r in rows] == [1, 0]
    assert [r["resolved_rank"] for r in rows] == [2, 1]
    assert all(r["exact_tie"] for r in rows)


def test_near_ties_and_negative_scores():
    cs = candidates()
    rows = d.ranking([(1, cs[1]["text"], -1.), (0, cs[0]["text"], -1.0000000001)], cs)
    assert not any(r["exact_tie"] for r in rows)
    assert rows[0]["score"] == -1.


@pytest.mark.parametrize("bad", ["missing", "duplicate", "text", "nan", "inf", "order", "index"])
def test_bad_rankings_rejected(bad):
    cs = candidates()
    outputs = [(0, cs[0]["text"], 2.), (1, cs[1]["text"], 1.)]
    if bad == "missing":
        outputs.pop()
    elif bad == "duplicate":
        outputs[1] = outputs[0]
    elif bad == "text":
        outputs[1] = (1, "wrong", 1.)
    elif bad == "order":
        outputs.reverse()
    elif bad == "index":
        outputs[1] = (True, cs[1]["text"], 1.)
    else:
        outputs[1] = (1, cs[1]["text"], float(bad))
    with pytest.raises(ValueError):
        d.ranking(outputs, cs)


def test_primary_contrast_arithmetic():
    cs = candidates()
    def row(condition, scores):
        outputs = sorted([(i, cs[i]["text"], score) for i, score in enumerate(scores)], key=lambda x: -x[2])
        return {"source_qa_id": "test", "condition": condition, "outputs": d.ranking(outputs, cs),
                "poison_minus_correct_margin": scores[1]-scores[0]}
    result = d.comparison(row("general_notice", [2., 1.]), row("freshness", [2., 3.]))
    assert result["primary"] is True
    assert result["margin_delta"] == 2.
    assert result["passage_deltas"][1]["score_delta"] == 2.
    assert result["passage_deltas"][1]["original_rank_delta"] == -1
    assert d.CONTRASTS[0] == ("general_notice", "freshness")


def test_vector_integrity_and_dot_reconstruction():
    vector = d.vector_record([1., 2.])
    assert vector["l2_norm"] == pytest.approx(5**.5)
    assert vector == d.vector_record([1., 2.])
    assert d.reconstruct([1., 2.], [3., 4.], 11.) == {"float64_dot": 11., "residual": 0.}


@pytest.mark.parametrize("q,c,s", [([1.], [1., 2.], 1.), ([1.], [2.], 7.), ([float("nan")], [1.], 1.), ([1.], [1.], float("inf"))])
def test_bad_arithmetic_rejected(q, c, s):
    with pytest.raises(ValueError):
        d.reconstruct(q, c, s)


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")]])
def test_nonfinite_vectors_rejected(values):
    with pytest.raises(ValueError):
        d.vector_record(values)


def test_snapshot_provenance(tmp_path):
    snapshot, manifest = snapshot_fixture(tmp_path)
    result = d.verify_snapshot(snapshot, manifest)
    assert result["revision"] == d.REVISION
    assert result["trusted_manifest_sha256"] == d.sha(manifest)


@pytest.mark.parametrize("bad", ["revision", "model", "changed", "extra", "missing", "config", "two_weights", "pin"])
def test_snapshot_failures_before_loading(tmp_path, monkeypatch, bad):
    snapshot, manifest = snapshot_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    if bad in ("revision", "model"):
        data[bad] = "wrong"
    elif bad == "changed":
        (snapshot / "vocab.txt").write_bytes(b"changed")
    elif bad == "extra":
        (snapshot / "extra").write_bytes(b"extra")
    elif bad == "missing":
        (snapshot / "vocab.txt").unlink()
    elif bad == "config":
        write_json(snapshot / "config.json", {"model_type": "wrong"})
        data["files"]["config.json"] = d.sha(snapshot / "config.json")
    elif bad == "two_weights":
        (snapshot / "model.safetensors").write_bytes(b"x")
        data["files"]["model.safetensors"] = d.sha(snapshot / "model.safetensors")
    elif bad == "pin":
        monkeypatch.setattr(d, "model_revisions", lambda: {d.MODEL: "a"*40})
    write_json(manifest, data)
    with pytest.raises(ValueError):
        d.verify_snapshot(snapshot, manifest)


def test_missing_dependencies_fail_before_import():
    with pytest.raises(ValueError, match="required torch"):
        d.load_backend(Path("unused"), {"packages": {}})


def test_archive_hashes_and_inventory(tmp_path, monkeypatch):
    prior = tmp_path / "bm25_v1"
    prior.mkdir()
    (prior / "results.jsonl").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="known archive hash"):
        d.protect([prior])
    monkeypatch.setattr(d, "ARCHIVES", {"bm25_v1": hashlib.sha256(b"fixture").hexdigest(), "other": "unused"})
    before, checks = d.protect([tmp_path])
    assert checks["bm25_v1"]["status"] == "verified"
    assert checks["other"]["status"] == "not_supplied"
    (prior / "checksum.json").write_bytes(b"new")
    assert before != d.protect([tmp_path])[0]


@pytest.mark.parametrize("output", ["prior", "prior/child", "."])
def test_existing_or_overlapping_outputs_refused(tmp_path, output):
    prior = tmp_path / "prior"
    prior.mkdir()
    (prior / "original").write_bytes(b"preserve")
    with pytest.raises(ValueError):
        d.execute(tmp_path / "model", tmp_path / "manifest", [prior], tmp_path / output, run_inference=True)
    assert (prior / "original").read_bytes() == b"preserve"


def test_explicit_inference_required(tmp_path):
    with pytest.raises(ValueError, match="explicit"):
        d.execute("unused", "unused", [], tmp_path / "out")
    assert not (tmp_path / "out").exists()


class FixtureTokenizer:
    """Character tokens solely to exercise audit bookkeeping, never Contriever."""
    def __call__(self, texts, **kwargs):
        single = isinstance(texts, str)
        texts = [texts] if single else texts
        fields = {k: [] for k in ("input_ids", "attention_mask", "special_tokens_mask", "offset_mapping")}
        width = max(len(t) for t in texts) + 2
        for text in texts:
            ids = [101] + [ord(c) for c in text] + [102]
            pad = width-len(ids) if kwargs.get("padding") else 0
            fields["input_ids"].append(ids + [0]*pad)
            fields["attention_mask"].append([1]*len(ids) + [0]*pad)
            fields["special_tokens_mask"].append([1]+[0]*len(text)+[1]+[1]*pad)
            fields["offset_mapping"].append([(0, 0)]+[(i, i+1) for i in range(len(text))]+[(0, 0)]*(pad+1))
        return {k: v[0] if single else v for k, v in fields.items()}

    def convert_ids_to_tokens(self, ids):
        return [str(i) for i in ids]


def test_token_audit_records_padding_body_and_confounds():
    tokenizer = FixtureTokenizer()
    fresh = d.token_audit(tokenizer, ["Latest update:\nbody"], ["Latest update:\n"])[0]
    general = d.token_audit(tokenizer, ["General notice:\nbody"], ["General notice:\n"])[0]
    assert not d.structural_control(fresh, general)["structurally_matched"]
    assert fresh["body_tokens"][0]["body_offset"] == [0, 1]
    assert fresh["effective_length"] == fresh["untruncated_length"]
    assert not fresh["truncated"]
    padded = d.token_audit(tokenizer, ["a", "abc"], ["", ""])
    assert padded[0]["attention_mask"][-1] == 0
    assert d.structural_control(fresh, copy.deepcopy(fresh))["structurally_matched"]


def test_truncation_rejected():
    class Truncated(FixtureTokenizer):
        def __call__(self, texts, **kwargs):
            result = super().__call__(texts, **kwargs)
            if kwargs.get("truncation"):
                result["input_ids"][0][1] = 999
            return result
    with pytest.raises(ValueError, match="truncation"):
        d.token_audit(Truncated(), ["abc"], [""])


def fixture_measurements():
    """Synthetic arithmetic fixtures; not a model substitute in the runner."""
    measured, vectors, contrasts = [], [], []
    for example in d.SYNTHETIC_EXAMPLES:
        group = {}
        for c, record in d.render_conditions(example).items():
            q = d.vector_record([1.] + [0.]*767)
            ds = [d.vector_record([2.] + [0.]*767), d.vector_record([1.] + [0.]*767)]
            outputs = d.ranking([(i, x["text"], 2.-i) for i, x in enumerate(record["candidates"])], record["candidates"])
            for output in outputs:
                output["reconstruction"] = d.reconstruct(q["values"], ds[output["candidate_index"]]["values"], output["score"])
            tokenizer = FixtureTokenizer()
            audits = d.token_audit(tokenizer, [x["text"] for x in record["candidates"]], ["", d.HEADERS[c]])
            row = {"kind": "measurement", "source_qa_id": example.source_qa_id, "condition": c,
                   "input": record, "outputs": outputs, "candidate_tokens": audits,
                   "query_tokens": d.token_audit(tokenizer, [record["query"]], [""])[0],
                   "poison_minus_correct_margin": -1.}
            measured.append(row)
            group[c] = row
            vectors.append({"source_qa_id": example.source_qa_id, "condition": c, "query": q, "candidates": ds})
        control = d.structural_control(group["freshness"]["candidate_tokens"][1], group["general_notice"]["candidate_tokens"][1])
        for row in group.values():
            row["specificity_control"] = control
        contrasts.extend(d.comparison(group[a], group[b]) for a, b in d.CONTRASTS)
    return measured, vectors, contrasts


def test_serialized_result_validation_and_corruption():
    measured, vectors, contrasts = fixture_measurements()
    rows = [{"kind": "manifest"}, *measured, *contrasts]
    d.validate_results(json.loads("[" + ",".join(d.canonical_jsonl(rows).splitlines()) + "]"), vectors)
    damaged = copy.deepcopy(rows)
    damaged[-1]["margin_delta"] = 99
    with pytest.raises(ValueError, match="comparison"):
        d.validate_results(damaged, vectors)
    damaged = copy.deepcopy(vectors)
    damaged[0]["query"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="embedding"):
        d.validate_results(rows, damaged)


@pytest.mark.parametrize("field", ["body_tokens", "text_sha256", "effective_length", "truncated"])
def test_serialized_token_audit_corruption_rejected(field):
    measured, vectors, contrasts = fixture_measurements()
    audit = measured[0]["query_tokens"]
    audit[field] = {"body_tokens": [], "text_sha256": "wrong", "effective_length": -1, "truncated": True}[field]
    with pytest.raises(ValueError, match="token"):
        d.validate_results([{"kind": "manifest"}, *measured, *contrasts], vectors)


@pytest.mark.parametrize("failure", [None, "repeat", "prior"])
def test_executor_preserves_inputs_and_refuses_repeat_drift(tmp_path, monkeypatch, failure):
    prior, out = tmp_path / "prior", tmp_path / "out"
    prior.mkdir()
    (prior / "original").write_bytes(b"original")
    snapshot, manifest = snapshot_fixture(tmp_path)
    monkeypatch.setattr(d, "load_backend", lambda *args: (None, None, None, {}))
    calls = []
    def fixtures(*args):
        calls.append(1)
        rows = fixture_measurements()
        if len(calls) == 2 and failure == "repeat":
            rows[0][0]["poison_minus_correct_margin"] = 10.
        if failure == "prior":
            (prior / "external").write_bytes(b"external change")
        return rows
    monkeypatch.setattr(d, "measure_all", fixtures)
    monkeypatch.setattr(d, "git_provenance", lambda: {"test_only": True})
    if failure:
        with pytest.raises(ValueError):
            d.execute(snapshot, manifest, [prior], out, run_inference=True)
        assert not out.exists()
    else:
        result = d.execute(snapshot, manifest, [prior], out, run_inference=True)
        assert result["same_environment_repeat_identical"]
        assert result["prior_sha256_before"] == result["prior_sha256_after"]
        hashes = json.loads((out / "sha256.json").read_text())
        assert all(d.sha(out / name) == digest for name, digest in hashes.items())
        with pytest.raises(ValueError):
            d.execute(snapshot, manifest, [prior], out, run_inference=True)
    assert (prior / "original").read_bytes() == b"original"


def test_import_does_not_import_dense_dependencies():
    code = "import sys; from src.eval import contriever_header_diagnostic; assert 'torch' not in sys.modules; assert 'transformers' not in sys.modules"
    subprocess.run([sys.executable, "-B", "-c", code], cwd=d.ROOT, check=True)
