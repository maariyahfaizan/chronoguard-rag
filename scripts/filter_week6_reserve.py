
"""Filter a frozen-order Week 6 reserve without reshuffling.

The original reserve manifest is never modified.
Exposed IDs remain documented in a separate exclusion audit.

Example:
    python scripts/filter_week6_reserve.py \
        --reserve results/week6_sampling_draft/reserve_ids.jsonl \
        --exposed results/week6_sampling_draft/prefreeze_exposed_ids.jsonl \
        --out-dir results/week6_sampling_draft/filtered_reserve_v1
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

STRATA = ("recent", "past")


def read_jsonl(path):
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON"
                ) from exc


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filter_reserve(reserve_rows, exposed_rows):
    exposed = {}

    for row in exposed_rows:
        qid = row["qa_id"]

        if qid in exposed:
            raise ValueError(f"Duplicate exposed ID: {qid}")

        if row.get("primary_heldout_eligible") is not False:
            raise ValueError(
                f"{qid}: exposure record must explicitly mark "
                "primary_heldout_eligible=false"
            )

        exposed[qid] = row

    if not exposed:
        raise ValueError("Exposure record is empty")

    kept = []
    excluded = []
    seen = set()
    last_rank = {s: 0 for s in STRATA}

    for row in reserve_rows:
        qid = row["qa_id"]
        stratum = row["recent_or_past"]
        rank = row["reserve_rank"]

        if qid in seen:
            raise ValueError(f"Duplicate reserve ID: {qid}")
        seen.add(qid)

        if stratum not in STRATA:
            raise ValueError(f"Unexpected stratum: {stratum}")

        if type(rank) is not int or rank != last_rank[stratum] + 1:
            raise ValueError(
                f"{qid}: nonsequential reserve rank in {stratum}"
            )

        last_rank[stratum] = rank

        if qid in exposed:
            if exposed[qid]["recent_or_past"] != stratum:
                raise ValueError(
                    f"{qid}: exposure stratum does not match reserve"
                )

            excluded.append({
                "qa_id": qid,
                "recent_or_past": stratum,
                "original_reserve_rank": rank,
                "exclusion_reason": "week6_prefreeze_evidence_audit",
            })
        else:
            kept.append(dict(row))

    missing = set(exposed) - seen
    if missing:
        raise ValueError(
            f"Exposed IDs absent from reserve: {sorted(missing)}"
        )

    return kept, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reserve", type=Path, required=True)
    parser.add_argument("--exposed", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    outputs = {
        "reserve": args.out_dir / "screening_queue.jsonl",
        "exclusions": args.out_dir / "exposure_exclusions.jsonl",
        "audit": args.out_dir / "filter_audit.json",
    }

    if any(path.exists() for path in outputs.values()):
        parser.error(
            "Output already exists; choose a new --out-dir"
        )

    kept, excluded = filter_reserve(
        read_jsonl(args.reserve),
        read_jsonl(args.exposed),
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for name, rows in (
        ("reserve", kept),
        ("exclusions", excluded),
    ):
        with outputs[name].open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(
                    json.dumps(row, sort_keys=True) + "\n"
                )

    audit = {
        "status": "DRAFT_SCREENING_QUEUE_NOT_FINAL_BENCHMARK",
        "source_reserve_sha256": sha256(args.reserve),
        "exposure_record_sha256": sha256(args.exposed),
        "kept_count": len(kept),
        "excluded_count": len(excluded),
        "kept_by_stratum": dict(
            Counter(row["recent_or_past"] for row in kept)
        ),
        "excluded_by_stratum": dict(
            Counter(row["recent_or_past"] for row in excluded)
        ),
        "screening_queue_sha256": sha256(outputs["reserve"]),
        "exposure_exclusions_sha256": sha256(
            outputs["exclusions"]
        ),
    }

    with outputs["audit"].open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, indent=2, sort_keys=True)
        stream.write("\n")

    print(json.dumps(audit, indent=2))
    print("\nOriginal reserve manifest unchanged.")


if __name__ == "__main__":
    main()
