import copy

import pytest

from src.attacks.freshness_smoke import SYNTHETIC_EXAMPLES, build_conditions
from src.attacks.matched_controls import (
    STATUS, date_pair, digest, header_pair, metadata_visibility, validate_pair,
)
from src.eval.matched_control_audit import audit_header_pair, generator_prompt


@pytest.fixture
def inputs():
    ex = SYNTHETIC_EXAMPLES[0]
    base = build_conditions(ex)[1]
    settings = {"retrieval": {"system": "BM25", "top_k": 2},
                "generation": {"max_passage_chars": 1500, "max_new_tokens": 64},
                "evaluation_rule": "synthetic-only-no-scientific-labels"}
    return base, [1], settings, ex.incorrect_claim


def test_deterministic_isolated_and_header_only(inputs):
    base, slots, settings, body = inputs
    original = copy.deepcopy(inputs)
    pair = header_pair(*inputs)
    assert pair == header_pair(*inputs)
    assert validate_pair(pair, base, slots, settings, body=body)
    assert inputs == original
    assert pair["status"] == STATUS
    a, b = [copy.deepcopy(x) for x in pair["conditions"].values()]
    for name, record in zip(("neutral", "freshness"), (a, b)):
        assert record["candidates"][1]["text"].endswith(body)
        record["candidates"][1]["text"] = body
    assert a == b
    pair["conditions"]["neutral"]["gold_aliases"].append("mutation")
    assert inputs == original
    assert "mutation" not in pair["conditions"]["freshness"]["gold_aliases"]


@pytest.mark.parametrize("field", ["timestamp", "doc_id", "source_metadata", "text"])
@pytest.mark.parametrize("condition", ["neutral", "freshness"])
def test_reject_candidate_differences(inputs, field, condition):
    base, slots, settings, body = inputs
    pair = header_pair(*inputs)
    pair["conditions"][condition]["candidates"][1][field] = "unexpected"
    with pytest.raises(ValueError):
        validate_pair(pair, base, slots, settings, body=body)


@pytest.mark.parametrize("field,value", [
    ("query", "different question"), ("source_qa_id", "other"),
    ("gold_answer", "changed"), ("gold_aliases", []),
    ("question_ts", "2099-01-01T00:00:00+00:00"),
])
def test_reject_question_and_key_changes(inputs, field, value):
    base, slots, settings, body = inputs
    pair = header_pair(*inputs)
    pair["conditions"]["neutral"][field] = value
    # The fixture may have no aliases; make this mutation unconditionally distinct.
    if field == "gold_aliases":
        pair["conditions"]["neutral"][field] = ["unapproved alias"]
    with pytest.raises(ValueError):
        validate_pair(pair, base, slots, settings, body=body)


@pytest.mark.parametrize("mutation", ["order", "settings", "slots", "budget", "body", "hash"])
def test_replay_rejects_mutable_contract_tampering(inputs, mutation):
    base, slots, settings, body = inputs
    p = header_pair(*inputs)
    if mutation == "order":
        p["conditions"]["freshness"]["candidates"].reverse()
    elif mutation == "settings":
        p["settings"]["retrieval"]["top_k"] = 999
    elif mutation == "slots":
        p["target_slots"] = [0]
    elif mutation == "budget":
        p["poison_budget"] = 99
    elif mutation == "body":
        p["declarations"]["body"] = "another claim"
    else:
        p["base_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_pair(p, base, slots, settings, body=body)


@pytest.mark.parametrize("slots", [[], [0], [1, 1], [-1], [99], [True], (1,)])
def test_invalid_slots(inputs, slots):
    base, _, settings, body = inputs
    with pytest.raises(ValueError):
        header_pair(base, slots, settings, body)


def test_missing_identity_and_duplicate_ids(inputs):
    base, slots, settings, body = inputs
    del base["source_qa_id"]
    with pytest.raises(ValueError):
        header_pair(*inputs)
    base["source_qa_id"] = "synthetic-only"
    base["candidates"][1]["doc_id"] = base["candidates"][0]["doc_id"]
    with pytest.raises(ValueError):
        header_pair(base, slots, settings, body)


@pytest.mark.parametrize("kind,offset", [("future_metadata_only", 30),
                                          ("timestamp_shift", -30),
                                          ("timestamp_shift", 7)])
def test_timestamp_only_controls(inputs, kind, offset):
    base, slots, settings, _ = inputs
    args = dict(kind=kind, offset_days=offset)
    p = date_pair(base, slots, settings, **args)
    assert validate_pair(p, base, slots, settings, **args)
    a, b = copy.deepcopy(list(p["conditions"].values()))
    assert a["candidates"][1]["timestamp"] != b["candidates"][1]["timestamp"]
    b["candidates"][1]["timestamp"] = a["candidates"][1]["timestamp"]
    assert a == b
    assert metadata_visibility(p)["text_inputs_identical"]
    assert not metadata_visibility(p)["metadata_intervention_visible_to_interface"]
    assert metadata_visibility(p, metadata_aware=True)["retrieval_effect"] == "NOT_MEASURED"


def test_zero_offset_duplication_preserves_target_identity(inputs):
    base, slots, settings, _ = inputs
    args = dict(kind="correct_duplication", offset_days=30, source_slot=0)
    p = date_pair(base, slots, settings, **args)
    assert validate_pair(p, base, slots, settings, **args)
    zero, offset = p["conditions"].values()
    source = base["candidates"][0]
    assert zero["candidates"][1]["timestamp"] == source["timestamp"]
    for record in (zero, offset):
        assert record["candidates"][1]["text"] == source["text"]
        assert record["candidates"][1]["doc_id"] == base["candidates"][1]["doc_id"]
    p["conditions"]["offset"]["candidates"][1]["text"] += "change"
    with pytest.raises(ValueError):
        validate_pair(p, base, slots, settings, **args)


def test_correct_header_control_requires_source_text(inputs):
    base, slots, settings, body = inputs
    with pytest.raises(ValueError):
        header_pair(base, slots, settings, body, kind="correct_content")
    correct = base["candidates"][0]["text"]
    pair = header_pair(base, slots, settings, correct, kind="correct_content")
    assert validate_pair(pair, base, slots, settings, body=correct, kind="correct_content")


@pytest.mark.parametrize("limit", [1, 15, 40, 1500])
def test_counts_diff_spans_and_truncation(inputs, limit):
    pair = header_pair(*inputs)
    audit = audit_header_pair(pair, max_passage_chars=limit, retrieved_slots=[0, 1])
    assert audit["exact_header_diff_spans"]
    for name, row in audit["conditions"].items():
        text = pair["conditions"][name]["candidates"][1]["text"]
        assert row["rendered"]["characters"] == len(text)
        assert row["token_counts"]["frozen_space_split"]["rendered"] == len(text.split(" "))
        assert row["full_claim_survives_passage_truncation"] == (len(text) <= limit)
        assert row["claim_in_selected_context"] == (len(text) <= limit)
        assert row["actual_model_input_visibility"] == "UNKNOWN"
        assert row["generator_token_count"] == "UNAVAILABLE"


def test_unicode_lengths_and_token_counts_not_additive(inputs):
    base, slots, settings, _ = inputs
    p = header_pair(base, slots, settings, "Fictional \u03b2 claim.")
    row = audit_header_pair(p)["conditions"]["neutral"]
    assert row["body"]["utf8_bytes"] > row["body"]["characters"]
    counts = row["token_counts"]["frozen_space_split"]
    assert counts["rendered"] != counts["header"] + counts["body"]


def test_visibility_is_not_rank_or_pre_token_prompt(inputs):
    p = header_pair(*inputs)
    assert audit_header_pair(p)["conditions"]["neutral"]["claim_in_selected_context"] == "UNKNOWN"
    assert audit_header_pair(p, retrieved_slots=[0])["conditions"]["neutral"]["claim_in_selected_context"] is False
    logs = {name: {"pair_sha256": digest(p), "source_qa_id": p["source_qa_id"],
                   "retrieved_slots": [0, 1],
                   "prompt": generator_prompt(r["query"], [c["text"] for c in r["candidates"]])}
            for name, r in p["conditions"].items()}
    a = audit_header_pair(p, retrieved_slots=[0, 1], context_log=logs)
    assert a["conditions"]["neutral"]["logged_context_evidence"] == "EXACT_LOGGED_PRETOKENIZATION_PROMPT"
    assert a["conditions"]["neutral"]["actual_model_input_visibility"] == "UNKNOWN"
    logs["neutral"]["prompt"] += "tampered"
    with pytest.raises(ValueError):
        audit_header_pair(p, retrieved_slots=[0, 1], context_log=logs)


def test_injected_offline_tokenizer_is_explicit(inputs):
    row = audit_header_pair(header_pair(*inputs), extra_tokenizers={"generator": list})["conditions"]["neutral"]
    assert row["generator_token_count"]["body"] == len(inputs[3])
    assert row["actual_model_input_visibility"] == "UNKNOWN"


def test_multislot_and_json_type_rejection(inputs):
    base, _, settings, body = inputs
    target = copy.deepcopy(base["candidates"][1])
    target["doc_id"] += "-second"
    base["candidates"].append(target)
    p = header_pair(base, [1, 2], settings, body)
    assert p["poison_budget"] == 2
    assert validate_pair(p, base, [1, 2], settings, body=body)
    settings["retrieval"]["nonjson"] = {1, 2}
    with pytest.raises(ValueError):
        header_pair(base, [1], settings, body)


@pytest.mark.parametrize("kind,offset,source", [
    ("unknown", 30, None), ("future_metadata_only", -1, None),
    ("timestamp_shift", 0, None), ("correct_duplication", 30, 1),
    ("timestamp_shift", 30, 0), ("timestamp_shift", True, None),
])
def test_unsupported_date_changes(inputs, kind, offset, source):
    base, slots, settings, _ = inputs
    with pytest.raises(ValueError):
        date_pair(base, slots, settings, kind=kind, offset_days=offset, source_slot=source)


def test_configured_limit_and_malformed_dates(inputs):
    base, slots, settings, body = inputs
    settings["generation"]["max_passage_chars"] = 20
    row = audit_header_pair(header_pair(*inputs))["conditions"]["neutral"]
    assert row["passage_truncated"]
    assert row["audit_limit_matches_declared_configuration"]
    base["candidates"][1]["timestamp"] = "2020-01-01"
    with pytest.raises(ValueError):
        header_pair(base, slots, settings, body)


def test_output_bytes_and_checksum_determinism(tmp_path):
    from src.eval.matched_control_audit import write_synthetic_audit
    write_synthetic_audit(tmp_path / "a")
    write_synthetic_audit(tmp_path / "b")
    for file in (tmp_path / "a").iterdir():
        assert file.read_bytes() == (tmp_path / "b" / file.name).read_bytes()
    write_synthetic_audit(tmp_path / "a")
    (tmp_path / "a" / "summary.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError):
        write_synthetic_audit(tmp_path / "a")
