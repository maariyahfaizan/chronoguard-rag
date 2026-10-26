
"""Build a draft Week 6 evidence-window manifest without downloading WMT."""
import argparse
import datetime as dt
import gzip
import json
from pathlib import Path

UTC = dt.timezone.utc
WINDOW_DAYS = 7
RETENTION_MULTIPLIER = 8


def read_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def build_windows(raw_path, reserve_path, per_stratum):
    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")

    selected = {"recent": [], "past": []}
    seen_ids = set()
    seen_ranks = {"recent": set(), "past": set()}

    for row in read_jsonl(reserve_path):
        stratum = row["recent_or_past"]
        qid = row["qa_id"]
        rank = row["reserve_rank"]

        if stratum not in selected:
            raise ValueError(f"Unexpected stratum: {stratum}")

        if qid in seen_ids:
            raise ValueError(f"Duplicate reserve qa_id: {qid}")

        if type(rank) is not int or rank < 1:
            raise ValueError(f"Invalid reserve rank for {qid}: {rank}")

        if rank in seen_ranks[stratum]:
            raise ValueError(
                f"Duplicate reserve rank {rank} in stratum {stratum}"
            )

        seen_ids.add(qid)
        seen_ranks[stratum].add(rank)
        selected[stratum].append(row)
    for stratum, rows in selected.items():
        actual_ranks = sorted(row["reserve_rank"] for row in rows)
        expected_ranks = list(range(1, len(rows) + 1))

        if actual_ranks != expected_ranks:
            raise ValueError(
                f"Non-contiguous reserve ranks in {stratum}: "
                f"expected 1..{len(rows)}"
            )
    chosen = []
    for stratum, rows in selected.items():
        rows.sort(key=lambda r: r["reserve_rank"])
        if len(rows) < per_stratum:
            raise ValueError(f"Insufficient reserve IDs in {stratum}")
        chosen.extend(rows[:per_stratum])

    chosen_ids = {row["qa_id"] for row in chosen}
    raw_lookup = {}

    for row in read_jsonl(raw_path):
        qid = row.get("qa_id")
        if qid in chosen_ids:
            if qid in raw_lookup:
                raise ValueError(f"Duplicate qa_id in raw data: {qid}")
            raw_lookup[qid] = row

    missing = chosen_ids - raw_lookup.keys()
    if missing:
        raise ValueError(f"Missing raw IDs: {sorted(missing)}")

    margin = dt.timedelta(days=WINDOW_DAYS * RETENTION_MULTIPLIER)
    result = []

    for entry in chosen:
        raw = raw_lookup[entry["qa_id"]]
        if raw["recent_or_past"] != entry["recent_or_past"]:
            raise ValueError(f"Stratum mismatch: {entry['qa_id']}")

        evidence_ts = raw["evidence_ts"]
        center = dt.datetime.fromtimestamp(evidence_ts, tz=UTC)

        result.append({
            "qa_id": entry["qa_id"],
            "recent_or_past": entry["recent_or_past"],
            "reserve_rank": entry["reserve_rank"],
            "evidence_ts": evidence_ts,
            "evidence_id": raw["evidence_id"],
            "window_start": (center - margin).isoformat(),
            "window_end": (center + margin).isoformat(),
        })

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--reserve", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-stratum", type=int, default=5)
    args = parser.parse_args()

    if args.out.exists():
        raise FileExistsError(args.out)

    rows = build_windows(args.raw, args.reserve, args.per_stratum)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Draft windows written: {len(rows)}")
    print(f"Retention margin: +/-{WINDOW_DAYS * RETENTION_MULTIPLIER} days")
    print(f"Output: {args.out}")


if __name__ == "__main__":
    main()
