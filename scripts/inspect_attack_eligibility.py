import sys
import json
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

INPUT = PROJECT_ROOT / "data/processed/streamingqa_control_pools_chunked.jsonl"
OUTPUT = PROJECT_ROOT / "results/attack_eligibility_report.json"


def parse_timestamp(value):
    if value is None:
        return None

    # StreamingQA question timestamps may be Unix timestamps.
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

    text = str(value).strip()

    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)

def query_tokens(text):
    tokens = set()

    for token in str(text).lower().split():
        cleaned = "".join(ch for ch in token if ch.isalnum())

        if len(cleaned) >= 3:
            tokens.add(cleaned)

    return tokens


def overlap(query, text):
    query_set = query_tokens(query)
    text_set = query_tokens(text)

    if not query_set:
        return 0.0

    return len(query_set & text_set) / len(query_set)


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Input dataset not found: {INPUT}"
        )

    total_records = 0
    invalid_question_timestamp = 0

    record_counts = {
        "with_older_non_gold_candidate": 0,
        "with_candidate_at_least_30_days_old": 0,
        "with_older_candidate_and_query_overlap": 0,
        "with_30_day_old_candidate_and_query_overlap": 0,
    }

    candidate_counts = {
        "older_non_gold_candidates": 0,
        "candidates_at_least_30_days_old": 0,
        "older_candidates_with_query_overlap": 0,
        "30_day_old_candidates_with_query_overlap": 0,
    }

    examples = []

    with INPUT.open("r", encoding="utf-8") as file:
        for record_index, line in enumerate(file):
            if not line.strip():
                continue

            record = json.loads(line)
            total_records += 1

            question_dt = parse_timestamp(
                record.get("question_ts")
            )

            if question_dt is None:
                invalid_question_timestamp += 1
                continue

            gold_ids = {
                str(value)
                for value in record.get("gold_chunk_ids", [])
            }

            has_old = False
            has_30_day_old = False
            has_old_overlap = False
            has_30_day_old_overlap = False

            record_examples = []

            for candidate in record.get("candidates", []):
                if str(candidate.get("doc_id")) in gold_ids:
                    continue

                candidate_dt = parse_timestamp(
                    candidate.get("timestamp")
                )

                if candidate_dt is None:
                    continue

                age_days = (
                    question_dt - candidate_dt
                ).total_seconds() / 86400.0

                if age_days <= 0:
                    continue

                has_old = True
                candidate_counts["older_non_gold_candidates"] += 1

                has_overlap = (
                    overlap(
                        record.get("query", ""),
                        candidate.get("text", ""),
                    ) > 0
                )

                if has_overlap:
                    has_old_overlap = True
                    candidate_counts[
                        "older_candidates_with_query_overlap"
                    ] += 1

                if age_days >= 30:
                    has_30_day_old = True
                    candidate_counts[
                        "candidates_at_least_30_days_old"
                    ] += 1

                    if has_overlap:
                        has_30_day_old_overlap = True
                        candidate_counts[
                            "30_day_old_candidates_with_query_overlap"
                        ] += 1

                if len(record_examples) < 3:
                    record_examples.append({
                        "age_days": round(age_days, 2),
                        "timestamp": candidate.get("timestamp"),
                        "doc_id": candidate.get("doc_id"),
                        "query_overlap": has_overlap,
                        "text_preview": str(
                            candidate.get("text", "")
                        )[:180],
                    })

            if has_old:
                record_counts["with_older_non_gold_candidate"] += 1

            if has_30_day_old:
                record_counts[
                    "with_candidate_at_least_30_days_old"
                ] += 1

            if has_old_overlap:
                record_counts[
                    "with_older_candidate_and_query_overlap"
                ] += 1

            if has_30_day_old_overlap:
                record_counts[
                    "with_30_day_old_candidate_and_query_overlap"
                ] += 1

            if has_old and len(examples) < 5:
                examples.append({
                    "record_index": record_index,
                    "query": record.get("query"),
                    "question_timestamp": question_dt.isoformat(),
                    "older_candidates": record_examples,
                })

    report = {
        "report_type": "stale_eligibility_diagnostic",
        "input": str(INPUT.relative_to(PROJECT_ROOT)),
        "eligibility_warning": (
            "Age and query overlap do not prove evidence is obsolete. "
            "This diagnostic does not establish stale-evidence eligibility. "
            "The attack still requires stale_evidence_validated == True."
        ),
        "total_records": total_records,
        "records_with_invalid_question_timestamp": (
            invalid_question_timestamp
        ),
        "record_counts": record_counts,
        "candidate_counts": candidate_counts,
        "examples": examples,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print("=== STALE ELIGIBILITY DIAGNOSTIC ===")
    print("Total records:", total_records)
    print(
        "Invalid question timestamps:",
        invalid_question_timestamp,
    )

    print("\nRecord counts:")
    for name, count in record_counts.items():
        print(f"  {name}: {count}")

    print("\nCandidate counts:")
    for name, count in candidate_counts.items():
        print(f"  {name}: {count}")

    print("\nSaved report:", OUTPUT)


if __name__ == "__main__":
    main()