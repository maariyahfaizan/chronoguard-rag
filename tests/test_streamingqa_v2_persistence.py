"""Synthetic persistence only: no model, retrieval, judging or scientific metrics."""
from copy import deepcopy
from pathlib import Path

import pytest

from src.eval import streamingqa_v2_persistence as p
from src.eval import week4_v2_schema as s
from src.eval.chunk_streamingqa_pools_v2 import chunk_question, TokenizerProfile
from test_streamingqa_chunking_v2 import CharacterTokenizer


@pytest.fixture
def bundle():
    qa = [{"qa_id": "synthetic-persist-" + str(i), "question": "Fictional question?",
           "answers": ["Paris"], "question_ts": 1609545600, "metadata": {"float": 0.125, "zero": -0.0}}
          for i in range(2)]
    candidates = [{"doc_id": "opaque\x00\x1f™" + str(i), "text": "Paris ½ ™. " * 40,
                   "timestamp": timestamp, "is_source_document": True,
                   "extra": {"finite": 1.25}}
                  for i, timestamp in enumerate(("2020-12-31", "2021-01-02", "2021-01-03"))]
    candidates.append(deepcopy(candidates[0]))
    parents = [{"query": q["question"], "gold_answer": "Paris", "gold_aliases": ["Paris"],
                "question_ts": q["question_ts"], "candidates": deepcopy(candidates),
                "gold_chunk_ids": [candidates[0]["doc_id"]], "gold_validated": i == 0}
               for i, q in enumerate(qa)]
    inputs = {"raw_eval": b"fictional raw artifact; not a real dataset",
              "sample": b"".join(p.encode_json(q) + b"\n" for q in qa),
              "parent_pool": b"".join(p.encode_json(q) + b"\n" for q in parents)}
    frame = s.make_frame([q["qa_id"] for q in qa], *(p.sha(inputs[k]) for k in
                        ("raw_eval", "sample", "parent_pool")), synthetic=True)
    config = s.load_config(Path(__file__).resolve().parents[1] / "configs/streamingqa_week4_v2.yaml")
    for k in inputs:
        config["frame"][k + "_sha256"] = p.sha(inputs[k])
    records = [chunk_question(s.make_question(q, row, frame, i), frame, CharacterTokenizer(),
                             profile=TokenizerProfile(scope="SYNTHETIC_ONLY"))
               for i, (q, row) in enumerate(zip(qa, parents))]
    return records, frame, {"input_artifacts": inputs, "configuration_bytes": p.encode_json(config)}


def dump(tmp_path, files):
    directory = tmp_path / "package"
    directory.mkdir()
    for name, raw in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return directory


def test_deterministic_roundtrip_and_scientific_boundaries(bundle, tmp_path):
    records, frame, kwargs = bundle
    files, digest = p.serialize_package(records, frame, **kwargs)
    assert (files, digest) == p.serialize_package(records, frame, **kwargs)
    directory = dump(tmp_path, files)
    envelopes, manifest = p.read_package(directory, expected_manifest_sha256=digest)
    assert p.encode_json([e["record"] for e in envelopes]) == p.encode_json(records)
    assert p.validate_roundtrip(directory, expected_manifest_sha256=digest,
        expected_records=records, expected_frame=frame)["status"] == "MECHANICAL_PASS"
    assert p.serialize_package([e["record"] for e in envelopes], frame, **kwargs)[0] == files
    assert manifest["tokenizer"]["verification"]["receipt"] == "UNAVAILABLE"
    assert envelopes[0]["audit"]["historical_gold"]["gold_validated"] is True
    assert envelopes[1]["audit"]["historical_gold"]["gold_validated"] is False
    annotations = envelopes[0]["audit"]["parent_annotations"]
    assert [a["chronology"]["chronology"] for a in annotations] == [
        "PRIOR_DATE", "SAME_DATE_UNCERTAIN", "FUTURE_DATED", "PRIOR_DATE"]
    assert all(c["temporal_validity"] == "UNKNOWN" and c["relevance_grade"] == "UNKNOWN"
               for q in records for c in q["candidates"])
    assert records[0]["parents"][0]["original_parent_passage_id"] == "opaque\x00\x1f™0"
    assert len(set(manifest["ordered_identities"]["canonical_children"])) < len(
        manifest["ordered_identities"]["child_occurrences"])
    assert len(set(manifest["ordered_identities"]["child_occurrences"])) == len(
        manifest["ordered_identities"]["child_occurrences"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), {1}, (1,), b"x"])
def test_unsupported_json(value):
    with pytest.raises((s.SchemaError, ValueError)):
        p.encode_json({"nested": [value]})


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}',
                                 b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}'])
def test_strict_json_read(raw):
    with pytest.raises((s.SchemaError, ValueError)):
        p.decode_json(raw)


@pytest.mark.parametrize("mutation", ["missing_question", "reordered", "missing_child", "duplicate_child",
                                     "source_text", "child_text", "annotation", "missing_gold"])
def test_invalid_records(bundle, mutation):
    records, frame, kwargs = deepcopy(bundle)
    if mutation == "missing_question":
        records.pop()
    elif mutation == "reordered":
        records.reverse()
    elif mutation == "missing_child":
        records[0]["candidates"].pop()
    elif mutation == "duplicate_child":
        records[0]["candidates"].append(deepcopy(records[0]["candidates"][0]))
    elif mutation == "source_text":
        records[0]["parents"][0]["parent_text"] += "changed"
    elif mutation == "child_text":
        records[0]["candidates"][0]["child_text"] += "changed"
    elif mutation == "annotation":
        records[0]["candidates"][0]["relevance_grade"] = 2
    else:
        source = p._jsonl(kwargs["input_artifacts"]["parent_pool"])
        del source[0]["gold_chunk_ids"]
        raw = b"".join(p.encode_json(x) + b"\n" for x in source)
        kwargs["input_artifacts"]["parent_pool"] = raw
    with pytest.raises((s.SchemaError, ValueError)):
        p.serialize_package(records, frame, **kwargs)


@pytest.mark.parametrize("target", ["pool.jsonl", "configuration.yaml", "manifest.json",
                                     "inputs/streamingqa_control_sample.jsonl"])
def test_corruption(bundle, tmp_path, target):
    records, frame, kwargs = bundle
    files, digest = p.serialize_package(records, frame, **kwargs)
    files[target] += b" "
    directory = dump(tmp_path, files)
    with pytest.raises(s.SchemaError, match="CHECKSUM"):
        p.read_package(directory, expected_manifest_sha256=digest)


@pytest.mark.parametrize("change", ["chronology", "gold", "extra", "reordered"])
def test_coherently_rehashed_envelope_tampering(bundle, tmp_path, change):
    records, frame, kwargs = bundle
    files, _ = p.serialize_package(records, frame, **kwargs)
    rows = p._jsonl(files["pool.jsonl"])
    if change == "chronology":
        rows[0]["audit"]["parent_annotations"][0]["chronology"]["chronology"] = "FUTURE_DATED"
    elif change == "gold":
        rows[0]["audit"]["historical_gold"]["gold_validated"] = False
    elif change == "extra":
        rows[0]["unexpected"] = True
    else:
        rows.reverse()
    files["pool.jsonl"] = b"".join(p.encode_json(x) + b"\n" for x in rows)
    manifest = p.decode_json(files["manifest.json"])
    manifest["files"]["pool.jsonl"] = {"sha256": p.sha(files["pool.jsonl"]), "bytes": len(files["pool.jsonl"])}
    files["manifest.json"] = p.encode_json(manifest) + b"\n"
    directory = dump(tmp_path, files)
    with pytest.raises(s.SchemaError):
        p.read_package(directory, expected_manifest_sha256=p.sha(files["manifest.json"]))


@pytest.mark.parametrize("q,pub,expected", [
    ("2021-01-02T00:00:00Z", "2021-01-01T23:00:00-02:00", "SAME_DATE_UNCERTAIN"),
    ("2021-01-02T00:00:00", "2020-01-01", "UNKNOWN"),
    (None, "2020-01-01", "UNKNOWN"), (1609545600, "invalid", "UNKNOWN"),
    (1609545600, "2021-01-03", "FUTURE_DATED")])
def test_date_policy(q, pub, expected):
    assert p.chronology_annotation(q, pub)["chronology"] == expected


def test_publication_safety(bundle, tmp_path):
    records, frame, kwargs = bundle
    destination = tmp_path / "data/processed/week4_v2/synthetic-test"
    digest = p.publish_package(destination, records, frame, workspace_root=tmp_path, **kwargs)
    p.read_package(destination, expected_manifest_sha256=digest)
    with pytest.raises(s.SchemaError, match="NO_OVERWRITE"):
        p.publish_package(destination, records, frame, workspace_root=tmp_path, **kwargs)
    with pytest.raises(s.SchemaError, match="V2_DESTINATION"):
        p.publish_package(tmp_path / "data/processed/old.jsonl", records, frame, workspace_root=tmp_path, **kwargs)


def test_atomic_failure_leaves_no_package(bundle, tmp_path, monkeypatch):
    records, frame, kwargs = bundle
    def fail(*args):
        raise OSError("injected publication failure")
    monkeypatch.setattr(p, "_rename_no_replace", fail)
    destination = tmp_path / "data/processed/week4_v2/synthetic-test"
    with pytest.raises(OSError, match="injected"):
        p.publish_package(destination, records, frame, workspace_root=tmp_path, **kwargs)
    assert not destination.exists()
    assert list(destination.parent.iterdir()) == []


def test_required_receipt_missing(bundle):
    records, frame, kwargs = bundle
    with pytest.raises(s.SchemaError, match="TOKENIZER_RECEIPT_REQUIRED"):
        p.serialize_package(records, frame, require_tokenizer_verification=True, **kwargs)


def test_reviewed_states_not_accepted_as_initial(bundle):
    records, frame, kwargs = deepcopy(bundle)
    child = records[0]["candidates"][0]
    child.update(relevance_grade=2, semantic_review_status="REVIEWED_PROVISIONAL",
                 semantic_review_refs=["synthetic-review-only"])
    with pytest.raises(s.SchemaError, match="INITIAL_CHILD_STATE"):
        p.serialize_package(records, frame, **kwargs)


def test_missing_package_file(bundle, tmp_path):
    records, frame, kwargs = bundle
    files, digest = p.serialize_package(records, frame, **kwargs)
    del files["inputs/streamingqa_control_pools.jsonl"]
    with pytest.raises(s.SchemaError, match="PACKAGE_FILE_SET"):
        p.read_package(dump(tmp_path, files), expected_manifest_sha256=digest)


def test_noncanonical_jsonl_rejected_even_if_rehashed(bundle, tmp_path):
    records, frame, kwargs = bundle
    files, _ = p.serialize_package(records, frame, **kwargs)
    files["pool.jsonl"] = files["pool.jsonl"].replace(b"\n", b"\r\n")
    manifest = p.decode_json(files["manifest.json"])
    manifest["files"]["pool.jsonl"] = {"sha256": p.sha(files["pool.jsonl"]), "bytes": len(files["pool.jsonl"])}
    files["manifest.json"] = p.encode_json(manifest) + b"\n"
    with pytest.raises(s.SchemaError, match="RECONSTRUCTION"):
        p.read_package(dump(tmp_path, files), expected_manifest_sha256=p.sha(files["manifest.json"]))


def test_external_receipt_asset_binding(bundle, tmp_path):
    records, frame, kwargs = bundle
    assets = {"synthetic-tokenizer.json": b"fictional tokenizer bytes"}
    receipt = {"schema_version": "streamingqa_tokenizer_receipt_v1", "scope": "SYNTHETIC_ONLY",
               "model_id": s.TOKENIZER, "revision": s.REVISION,
               "construction_config_sha256": sorted({a["chunking_config_sha256"] for q in records
                                                       for a in q["parent_chunk_audits"]}),
               "asset_sha256": {k: p.sha(v) for k, v in assets.items()},
               "runtime_versions": {"transformers": "synthetic", "tokenizers": "synthetic"},
               "offset_verification": "VERIFIED", "limitations": ["FICTIONAL TEST RECEIPT ONLY"]}
    files, digest = p.serialize_package(records, frame, **kwargs, tokenizer_assets=assets,
        tokenizer_receipt=p.encode_json(receipt), require_tokenizer_verification=True)
    _, manifest = p.read_package(dump(tmp_path, files), expected_manifest_sha256=digest,
                                 require_tokenizer_verification=True)
    assert manifest["tokenizer"]["verification"]["asset_verification"] == "MATCHES_RECEIPT"
    assets["synthetic-tokenizer.json"] += b"changed"
    with pytest.raises(s.SchemaError, match="TOKENIZER_ASSET_HASH"):
        p.serialize_package(records, frame, **kwargs, tokenizer_assets=assets,
                            tokenizer_receipt=p.encode_json(receipt))
