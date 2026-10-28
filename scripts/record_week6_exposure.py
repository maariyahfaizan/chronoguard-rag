
"""Record the initial Week 6 pre-freeze evidence-audit batch.

This script records exposure only. It does not modify the existing
reserve manifest, sampling order, or frozen Week 4/5 artifacts.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path(
            "results/week6_sampling_draft/"
            "candidate_metadata_first10.jsonl"
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "results/week6_sampling_draft/"
            "prefreeze_exposed_ids.jsonl"
        ),
    )
    args = parser.parse_args()

    if args.out.exists():
        parser.error(f"Output already exists: {args.out}")

    rows = []
    seen = set()

    with args.metadata.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            candidate = json.loads(line)
            qid = candidate["qa_id"]

            if qid in seen:
                raise ValueError(f"Duplicate ID: {qid}")

            seen.add(qid)

            rows.append({
                "qa_id": qid,
                "recent_or_past": candidate["recent_or_past"],
                "exposure_stage": "week6_prefreeze_evidence_audit",
                "exposure_type": "gold_evidence_and_answer_inspection",
                "primary_heldout_eligible": False,
                "allowed_use": "pipeline_development_and_validation",
                "reason": (
                    "Included in initial 10-candidate pre-freeze "
                    "evidence reconstruction and validation batch."
                ),
            })

    if len(rows) != 10:
        raise ValueError(
            f"Expected 10 exposed candidates; found {len(rows)}"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("x", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Recorded {len(rows)} pre-freeze exposed candidates")
    print(f"Output: {args.out}")

    for row in rows:
        print(row["qa_id"], row["recent_or_past"])


if __name__ == "__main__":
    main()
