import copy

import pytest

from src.attacks.attack_pool import _validate_record
from src.attacks.pilot_protocol import read_jsonl
from src.eval.adjudicated_pool_adapter import (
    convert_records, synthetic_fixture_bundle, validate_output, write_synthetic_pool,
)


def converted(records, sources, **kwargs):
    return convert_records(records, sources=sources, attack_family=kwargs.get("attack_family", "fabricated_fresh"),
                           mode=kwargs.get("mode", "synthetic"))


def test_valid_conversion_preserves_originals_order_and_metadata():
    records, sources = synthetic_fixture_bundle()
    before = copy.deepcopy((records, sources))
    out = converted(records, sources)
    assert len(out) == 2
    assert (records, sources) == before
    assert validate_output(out, records, sources=sources, attack_family="fabricated_fresh", mode="synthetic")
    for row, record in zip(out, records):
        _validate_record(row)  # actual historical validator, not a replacement
        original = sources[record["original_source"]["uri"]]
        assert row["query"] == original["question"]
        assert row["source_qa_id"] == record["qa_id"]
        assert row["gold_answer"] == record["question_time_answer"]["primary"]
        assert row["gold_aliases"] == row["original_aliases"] == original["aliases"]
        assert row["original_answers"] == original["answers"]
        assert [c["doc_id"] for c in row["candidates"]] == record["candidate_order"]
        # Same dictionary projection used by existing StreamingQA runners.
        texts = [c["text"] for c in row["candidates"]]
        assert texts == [sources[e["source"]["uri"]]["text"] for e in record["evidence"]]
        assert row["adapter_metadata"]["execution_authorized"] is False
    out[0]["candidates"][0]["source_metadata"]["origin"] = "mutated"
    assert (records, sources) == before


@pytest.mark.parametrize("status", ["UNKNOWN", "NOT_REVIEWED", "INELIGIBLE"])
def test_unknown_eligibility(status):
    r,s = synthetic_fixture_bundle()
    r[0]["eligibility"]["status"] = status
    with pytest.raises(ValueError):
        converted(r,s)


@pytest.mark.parametrize("field", ["adjudication", "exposure", "protocol", "approvals"])
def test_missing_gate(field):
    r,s = synthetic_fixture_bundle()
    del r[0][field]
    with pytest.raises(ValueError):
        converted(r,s)


@pytest.mark.parametrize("mutation", ["same_reviewers", "unverified_independence", "flag_only", "freeze",
                                      "policy", "protocol_hash", "unapproved_key", "missing_key", "key_digest",
                                      "key_source", "out_of_scope", "promoted_provenance", "forged_token"])
def test_invalid_authority_and_keys(mutation):
    r,s = synthetic_fixture_bundle()
    row = r[0]
    if mutation == "same_reviewers":
        row["adjudication"]["reviewers"] = ["synthetic-reviewer-a"]*2
    elif mutation == "unverified_independence":
        row["adjudication"]["independence"] = "UNKNOWN"
    elif mutation == "flag_only":
        row["adjudication"] = {"human_verified":True}
    elif mutation == "freeze":
        row["protocol"]["freeze_status"] = "UNKNOWN"
    elif mutation == "policy":
        row["exposure"]["policy_id"] = "unapproved"
    elif mutation == "protocol_hash":
        row["protocol"]["sha256"] = "0"*64
    elif mutation == "unapproved_key":
        row["claim"]["key"]["approval_status"] = "candidate"
    elif mutation == "missing_key":
        row["claim"] = None
    elif mutation == "key_digest":
        row["claim"]["key_digest"] = "0"*64
    elif mutation == "key_source":
        row["claim"]["context"]["source_id"] = "different"
    elif mutation == "out_of_scope":
        row["eligibility"]["source_scope"] = "OUT_OF_SCOPE"
    elif mutation == "promoted_provenance":
        row["provenance"]["tier"] = "AUTHENTICATED_ORIGINAL"
    else:
        row["approvals"]["provenance"]["token"] = "matching-hash-is-not-approval"
    with pytest.raises(ValueError):
        converted(r,s)


@pytest.mark.parametrize("mutation", ["source_text", "source_hash", "variant", "body_hash", "candidate_order",
                                      "aliases", "original_answers", "duplicate_doc", "unbound_gold"])
def test_source_bindings_and_identity(mutation):
    r,s = synthetic_fixture_bundle()
    if mutation == "source_text":
        s[r[0]["evidence"][0]["source"]["uri"]]["text"] += "changed"
    elif mutation == "source_hash":
        r[0]["evidence"][0]["source"]["sha256"] = "0"*64
    elif mutation == "variant":
        r[0]["evidence"][0]["variant_id"] = "different"
    elif mutation == "body_hash":
        r[0]["evidence"][0]["text_sha256"] = "0"*64
    elif mutation == "candidate_order":
        r[0]["candidate_order"].reverse()
    elif mutation == "aliases":
        r[0]["question_time_answer"]["aliases"] = ["rewritten"]
    elif mutation == "original_answers":
        s[r[0]["original_source"]["uri"]]["answers"] = ["rewritten"]
    elif mutation == "duplicate_doc":
        r[0]["evidence"][1]["doc_id"] = r[0]["evidence"][0]["doc_id"]
    else:
        r[0]["gold_chunk_ids"] = ["missing"]
    with pytest.raises(ValueError):
        converted(r,s)


def test_rehashing_modified_records_and_sources_cannot_authorize_them():
    from src.attacks.matched_controls import digest
    r,s = synthetic_fixture_bundle()
    source = s[r[0]["original_source"]["uri"]]
    source["answers"] = ["invented primary"]
    r[0]["original_source"]["sha256"] = digest(source)
    core = {k:v for k,v in r[0].items() if k != "approvals"}
    for grant in r[0]["approvals"].values():
        grant["record_sha256"] = digest(core)
    with pytest.raises(ValueError):
        converted(r,s)


@pytest.mark.parametrize("mutation", ["metadata", "order", "aliases", "original", "family"])
def test_output_replay_detects_loss(mutation):
    r,s = synthetic_fixture_bundle()
    out = converted(r,s)
    if mutation == "metadata":
        del out[0]["candidates"][0]["source_metadata"]
    elif mutation == "order":
        out[0]["candidates"].reverse()
    elif mutation == "aliases":
        out[0]["gold_aliases"] = []
    elif mutation == "original":
        out[0]["original_answers"] = []
    else:
        out[0]["adapter_metadata"]["attack_family"] = "stale_evidence"
    with pytest.raises(ValueError):
        validate_output(out,r,sources=s,attack_family="fabricated_fresh",mode="synthetic")


@pytest.mark.parametrize("mode", ["real", None, "production"])
def test_real_mode_never_accepts_mock_credentials(mode):
    r,s = synthetic_fixture_bundle()
    with pytest.raises(ValueError):
        converted(r,s,mode=mode)


def test_namespaces_duplicates_and_unsupported_family():
    r,s = synthetic_fixture_bundle()
    with pytest.raises(ValueError):
        converted(r+[copy.deepcopy(r[0])],s)
    with pytest.raises(ValueError):
        converted(r,s,attack_family="stale_evidence")
    r[0]["qa_id"] = "real-question-001"
    with pytest.raises(ValueError):
        converted(r,s)


def test_writer_and_actual_loader(tmp_path,monkeypatch):
    import src.eval.adjudicated_pool_adapter as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    r,s = synthetic_fixture_bundle()
    path = tmp_path/"audits/g2_i1_v1/pool.jsonl"
    result = write_synthetic_pool(r,sources=s,attack_family="fabricated_fresh",output=path,mode="synthetic")
    assert result["rows"] == 2
    assert read_jsonl(path) == converted(r,s)
    with pytest.raises(FileExistsError):
        write_synthetic_pool(r,sources=s,attack_family="fabricated_fresh",output=path,mode="synthetic")
    for forbidden in (tmp_path/"data/pool.jsonl",tmp_path/"results/pool.jsonl",tmp_path/"audits/p0_b1_v1/pool.jsonl"):
        with pytest.raises(ValueError):
            write_synthetic_pool(r,sources=s,attack_family="fabricated_fresh",output=forbidden,mode="synthetic")
        assert not forbidden.exists()


def test_failed_batch_writes_nothing(tmp_path,monkeypatch):
    import src.eval.adjudicated_pool_adapter as module
    monkeypatch.setattr(module,"ROOT",tmp_path)
    r,s = synthetic_fixture_bundle()
    r[1]["adjudication"] = None
    path = tmp_path/"audits/g2_i1_v1/invalid.jsonl"
    with pytest.raises(ValueError):
        write_synthetic_pool(r,sources=s,attack_family="fabricated_fresh",output=path,mode="synthetic")
    assert not path.exists()


def test_synthetic_determinism_and_family_compatibility():
    r,s = synthetic_fixture_bundle()
    assert converted(r,s) == converted(r,s)
    assert converted(r,s,attack_family="future_date")[0]["adapter_metadata"]["attack_family"] == "future_date"


@pytest.mark.parametrize("case", ["scope", "unregistered"])
def test_synthetic_namespace_not_an_authority_credential(case):
    r,s = synthetic_fixture_bundle()
    if case == "scope":
        r[0]["scope"] = "REAL"
    else:
        r[0]["qa_id"] = "synthetic-g2-i1-999"
    with pytest.raises(ValueError):
        converted(r,s)


@pytest.mark.parametrize("case", ["missing", "stale"])
def test_missing_or_stale_g1_contract_stops_conversion(case,tmp_path,monkeypatch):
    import src.eval.adjudicated_pool_adapter as module
    monkeypatch.setattr(module,"G1_ROOT",tmp_path)
    if case == "stale":
        (tmp_path/"checksums.json").write_text('{}')
    r,s = synthetic_fixture_bundle()
    with pytest.raises(ValueError):
        converted(r,s)
