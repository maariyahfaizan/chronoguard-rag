"""Deterministic diagnostic helpers only; no real-data relabeling or backends."""
import hashlib

import pytest

from scripts.diagnose_streamingqa_coverage import literal_probe, nonwhite, stitch, text_differences


@pytest.mark.parametrize("symbol,codepoint", [("\u2033", "U+2033"), ("\u2122", "U+2122"),
                                           ("\u00bd", "U+00BD"), ("\ufffd", "U+FFFD")])
def test_exact_deletion_is_not_treated_as_equivalence(symbol, codepoint):
    report = text_differences("left" + symbol + " right", ["left right"])
    edit, = report["edits"]
    assert edit["operation"] == "delete" and edit["removed_or_replaced"] == symbol
    assert edit["unicode_characters"][0]["codepoint"] == codepoint
    assert edit["parent_raw_character_span"] == [4, 5]
    assert report["whitespace_only_difference"] is False
    assert report["is_equivalence_proof"] is False


def test_character_offsets_are_distinct_from_utf8_offsets():
    report = text_differences("\u00e9 A\u00bd B", ["\u00e9 A B"])
    edit, = report["edits"]
    assert edit["parent_raw_character_span"] == [3, 4]
    assert edit["parent_utf8_byte_span"] == [4, 6]
    assert edit["parent_context"]["text"] == "\u00e9 A\u00bd B"


def test_whitespace_is_reported_separately():
    report = text_differences("left \n right", ["left right"])
    assert report["edits"] == [] and report["whitespace_only_difference"]
    assert nonwhite("left \n right")[0] == "leftright"


def test_unique_overlap_preserves_both_child_origins():
    report = text_differences("abc\ufffddefghi", ["abcdef", "defghi"])
    assert report["overlaps"][0]["selected_overlap"] == 3
    edit, = report["edits"]
    assert edit["removed_or_replaced"] == "\ufffd"
    assert {c["child_index"] for c in edit["child_contexts_at_edit_boundary"]} == {0, 1}
    assert report["diagnostic_view_sha256"] == hashlib.sha256(b"abcdefghi").hexdigest()


@pytest.mark.parametrize("children", [["aaaa", "aaa"], ["abc", "xyz"], [""]])
def test_ambiguous_missing_or_empty_overlap_is_not_guessed(children):
    with pytest.raises(ValueError):
        stitch(children)


def test_compatibility_replacement_is_not_normalized_into_equality():
    report = text_differences("x\u00bdy", ["x1\u20442y"])
    edit, = report["edits"]
    assert edit["operation"] == "replace"
    assert edit["removed_or_replaced"] == "\u00bd" and edit["replacement"] == "1\u20442"
    assert not report["is_equivalence_proof"]


def test_literal_probe_is_explicitly_not_a_semantic_judge():
    assert literal_probe("not Paris", ["Paris"]) == [0]
    assert literal_probe("unrelated", ["Paris"]) == []
    assert literal_probe("Paris", ["the", "Paris"]) == [1]
