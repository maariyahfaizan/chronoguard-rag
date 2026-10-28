
import pytest

from scripts.prepare_week6_screening_batch import make_batch


def sample_queue():
    return [
        {"qa_id": "r1", "recent_or_past": "recent", "reserve_rank": 1},
        {"qa_id": "r2", "recent_or_past": "recent", "reserve_rank": 3},
        {"qa_id": "r3", "recent_or_past": "recent", "reserve_rank": 4},
        {"qa_id": "p1", "recent_or_past": "past", "reserve_rank": 1},
        {"qa_id": "p2", "recent_or_past": "past", "reserve_rank": 2},
        {"qa_id": "p3", "recent_or_past": "past", "reserve_rank": 5},
    ]


def test_preserves_original_order_and_ranks():
    rows = sample_queue()
    result = make_batch(rows, per_stratum=2)

    assert [r["qa_id"] for r in result] == [
        "r1", "r2", "p1", "p2"
    ]
    assert [r["reserve_rank"] for r in result] == [
        1, 3, 1, 2
    ]
    assert rows == sample_queue()


def test_rejects_duplicate_ids():
    rows = sample_queue()
    rows.append(dict(rows[0]))

    with pytest.raises(ValueError, match="Duplicate qa_id"):
        make_batch(rows, per_stratum=2)


def test_rejects_nonincreasing_rank():
    rows = sample_queue()
    rows[1]["reserve_rank"] = 1

    with pytest.raises(ValueError, match="Non-increasing"):
        make_batch(rows, per_stratum=2)


def test_rejects_insufficient_candidates():
    with pytest.raises(ValueError, match="Insufficient candidates"):
        make_batch(sample_queue(), per_stratum=4)


def test_rejects_invalid_stratum():
    rows = sample_queue()
    rows[0]["recent_or_past"] = "unknown"

    with pytest.raises(ValueError, match="Unexpected stratum"):
        make_batch(rows, per_stratum=2)


def test_rejects_invalid_batch_size():
    with pytest.raises(ValueError, match="per_stratum must be positive"):
        make_batch(sample_queue(), per_stratum=0)


def test_deterministic_output():
    assert make_batch(sample_queue(), 2) == make_batch(sample_queue(), 2)
