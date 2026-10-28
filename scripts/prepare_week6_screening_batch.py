
"""Prepare a deterministic Week 6 evidence-screening batch.

Reads the exposure-filtered reserve queue without changing its order.
Does not inspect answers, retrieve evidence, or select final benchmark IDs.
Refuses to overwrite outputs.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

STRATA = ("recent", "past")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def make_batch(rows, per_stratum=200):
    if per_stratum < 1:
        raise ValueError("per_stratum must be positive")

    selected = []
    counts = Counter()
    seen = set()
    previous_rank = {s: 0 for s in STRATA}

    for row in rows:
        qid = row["qa_id"]
        stratum = row["recent_or_past"]
        rank = row["reserve_rank"]

        if qid in seen:
            raise ValueError(f"Duplicate qa_id: {qid}")
        seen.add(qid)

        if stratum not in STRATA:
            raise ValueError(f"Unexpected stratum: {stratum}")

        if type(rank) is not int or rank <= previous_rank[stratum]:
            raise ValueError(
                f"Non-increasing reserve rank for {qid}"
            )
        previous_rank[stratum] = rank

        if counts[stratum] < per_stratum:
            selected.append(dict(row))
            counts[stratum] += 1

    if any(counts[s] < per_stratum for s in STRATA):
        raise ValueError(
            f"Insufficient candidates: {dict(counts)}"
        )

    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--per-stratum", type=int, default=200)
    args = parser.parse_args()

    outputs = {
        "batch": args.out_dir / "screening_batch_ids.jsonl",
        "audit": args.out_dir / "screening_batch_audit.json",
    }

    if any(path.exists() for path in outputs.values()):
        parser.error("Output exists; choose a new --out-dir")

    batch = make_batch(
        read_jsonl(args.queue),
        per_stratum=args.per_stratum,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    with outputs["batch"].open("x", encoding="utf-8") as stream:
        for row in batch:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    audit = {
        "status": "DRAFT_SCREENING_BATCH_NOT_FINAL_BENCHMARK",
        "source_queue_sha256": sha256(args.queue),
        "per_stratum": args.per_stratum,
        "total": len(batch),
        "counts": dict(Counter(
            row["recent_or_past"] for row in batch
        )),
        "batch_sha256": sha256(outputs["batch"]),
    }

    with outputs["audit"].open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, indent=2, sort_keys=True)
        stream.write("\n")

    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
