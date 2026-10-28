
"""Regression tests for Week 6 reserve exposure filtering."""

import pytest

from scripts.filter_week6_reserve import filter_reserve


def reserve_rows():
    return [
        {"qa_id": "r1", "recent_or_past": "recent", "reserve_rank": 1},
        {"qa_id": "r2", "recent_or_past": "recent", "reserve_rank": 2},
        {"qa_id": "r3", "recent_or_past": "recent", "reserve_rank": 3},
        {"qa_id": "p1", "recent_or_past": "past", "reserve_rank": 1},
        {"qa_id": "p2", "recent_or_past": "past", "reserve_rank": 2},
    ]


def exposed_row(qid, stratum):
    return {
        "qa_id": qid,
        "recent_or_past": stratum,
        "primary_heldout_eligible": False,
    }


def test_exclusions_preserve_original_ranks():
    original = reserve_rows()

    kept, excluded = filter_reserve(
        original,
        [
            exposed_row("r2", "recent"),
            exposed_row("p1", "past"),
        ],
    )

    assert [r["qa_id"] for r in kept] == ["r1", "r3", "p2"]
    assert [r["reserve_rank"] for r in kept] == [1, 3, 2]

    assert [r["qa_id"] for r in excluded] == ["r2", "p1"]
    assert [r["original_reserve_rank"] for r in excluded] == [2, 1]

    assert original == reserve_rows()


def test_rejects_duplicate_exposed_ids():
    with pytest.raises(ValueError, match="Duplicate exposed ID"):
        filter_reserve(
            reserve_rows(),
            [
                exposed_row("r2", "recent"),
                exposed_row("r2", "recent"),
            ],
        )


def test_rejects_unknown_exposed_id():
    with pytest.raises(ValueError, match="absent from reserve"):
        filter_reserve(
            reserve_rows(),
            [exposed_row("unknown", "recent")],
        )


def test_rejects_exposure_stratum_mismatch():
    with pytest.raises(ValueError, match="does not match reserve"):
        filter_reserve(
            reserve_rows(),
            [exposed_row("r2", "past")],
        )


def test_rejects_duplicate_reserve_id():
    rows = reserve_rows()
    rows.append({
        "qa_id": "r1",
        "recent_or_past": "recent",
        "reserve_rank": 4,
    })

    with pytest.raises(ValueError, match="Duplicate reserve ID"):
        filter_reserve(
            rows,
            [exposed_row("r2", "recent")],
        )


def test_rejects_nonsequential_rank():
    rows = reserve_rows()
    rows[1]["reserve_rank"] = 7

    with pytest.raises(ValueError, match="nonsequential reserve rank"):
        filter_reserve(
            rows,
            [exposed_row("r2", "recent")],
        )


def test_rejects_exposure_not_explicitly_ineligible():
    with pytest.raises(ValueError, match="primary_heldout_eligible"):
        filter_reserve(
            reserve_rows(),
            [{
                "qa_id": "r2",
                "recent_or_past": "recent",
                "primary_heldout_eligible": True,
            }],
        )
