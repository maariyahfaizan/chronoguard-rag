import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

SAMPLE_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "streamingqa_control_sample.jsonl"
)


def parse_ts(value):
    return datetime.fromtimestamp(
        float(value),
        tz=timezone.utc,
    )


records = []

with SAMPLE_PATH.open("r", encoding="utf-8") as f:
    for line in f:
        if line.strip():
            records.append(json.loads(line))


print("Loaded records:", len(records))
print()

differences = []

for i, record in enumerate(records):
    evidence_ts = parse_ts(record["evidence_ts"])
    question_ts = parse_ts(record["question_ts"])

    delta_days = (
        question_ts - evidence_ts
    ).total_seconds() / 86400.0

    differences.append(delta_days)

    print(
        f"{i:03d} | "
        f"evidence={evidence_ts.isoformat()} | "
        f"question={question_ts.isoformat()} | "
        f"question-evidence={delta_days:+.1f} days"
    )


print()
print("=" * 80)
print("TEMPORAL COVERAGE SUMMARY")
print("=" * 80)

print("min question-evidence days:",
      min(differences))

print("max question-evidence days:",
      max(differences))

print("mean:",
      statistics.mean(differences))

print("median:",
      statistics.median(differences))

print("records with question >= evidence:",
      sum(x >= 0 for x in differences))

print("records with question > evidence + 26 days:",
      sum(x > 26 for x in differences))

print("records with question > evidence + 56 days:",
      sum(x > 56 for x in differences))

print()
print("Existing extraction margin: +/-56 days around evidence_ts")
print("Current stale threshold: >=30 days before question_ts")