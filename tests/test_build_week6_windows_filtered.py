
import json
import datetime as dt

import pytest

from src.eval.build_week6_windows import build_windows


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def make_data(tmp_path):
    reserve = [
        {"qa_id": "r1", "recent_or_past": "recent", "reserve_rank": 1},
        {"qa_id": "r2", "recent_or_past": "recent", "reserve_rank": 3},
        {"qa_id": "p1", "recent_or_past": "past", "reserve_rank": 2},
        {"qa_id": "p2", "recent_or_past": "past", "reserve_rank": 5},
    ]

    raw = [
        {
            "qa_id": row["qa_id"],
            "recent_or_past": row["recent_or_past"],
            "evidence_ts": 1609459200,
            "evidence_id": f"doc-{row['qa_id']}",
        }
        for row in reserve
    ]

    reserve_path = tmp_path / "reserve.jsonl"
    raw_path = tmp_path / "raw.jsonl"

    write_jsonl(reserve_path, reserve)
    write_jsonl(raw_path, raw)

    return raw_path, reserve_path, reserve


def test_gapped_ranks_are_accepted(tmp_path):
    raw_path, reserve_path, _ = make_data(tmp_path)

    result = build_windows(raw_path, reserve_path, 2)

    assert len(result) == 4
    assert [r["reserve_rank"] for r in result] == [1, 3, 2, 5]
    assert [r["qa_id"] for r in result] == ["r1", "r2", "p1", "p2"]


def test_window_is_plus_minus_56_days(tmp_path):
    raw_path, reserve_path, _ = make_data(tmp_path)

    result = build_windows(raw_path, reserve_path, 2)

    center = dt.datetime.fromtimestamp(
        1609459200, tz=dt.timezone.utc
    )

    for row in result:
        start = dt.datetime.fromisoformat(row["window_start"])
        end = dt.datetime.fromisoformat(row["window_end"])

        assert center - start == dt.timedelta(days=56)
        assert end - center == dt.timedelta(days=56)


def test_reordered_ranks_are_rejected(tmp_path):
    raw_path, reserve_path, reserve = make_data(tmp_path)

    reserve[0], reserve[1] = reserve[1], reserve[0]
    write_jsonl(reserve_path, reserve)

    with pytest.raises(ValueError, match="Non-increasing"):
        build_windows(raw_path, reserve_path, 2)


def test_duplicate_reserve_ids_are_rejected(tmp_path):
    raw_path, reserve_path, reserve = make_data(tmp_path)

    reserve.append({
        "qa_id": "r1",
        "recent_or_past": "recent",
        "reserve_rank": 8,
    })
    write_jsonl(reserve_path, reserve)

    with pytest.raises(ValueError, match="Duplicate reserve qa_id"):
        build_windows(raw_path, reserve_path, 2)


def test_duplicate_ranks_are_rejected(tmp_path):
    raw_path, reserve_path, reserve = make_data(tmp_path)

    reserve[1]["reserve_rank"] = 1
    write_jsonl(reserve_path, reserve)

    with pytest.raises(ValueError, match="Duplicate reserve rank"):
        build_windows(raw_path, reserve_path, 2)


def test_missing_raw_id_is_rejected(tmp_path):
    raw_path, reserve_path, _ = make_data(tmp_path)

    raw = [
        {
            "qa_id": "r1",
            "recent_or_past": "recent",
            "evidence_ts": 1609459200,
            "evidence_id": "doc-r1",
        }
    ]
    write_jsonl(raw_path, raw)

    with pytest.raises(ValueError, match="Missing raw IDs"):
        build_windows(raw_path, reserve_path, 2)
