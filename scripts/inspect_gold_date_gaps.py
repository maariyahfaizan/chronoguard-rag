import json
from datetime import datetime, timezone
from pathlib import Path

path = Path("data/processed/streamingqa_control_pools_chunked.jsonl")

def parse_date(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        text = str(value).strip()
        if text.isdigit():
            return datetime.fromtimestamp(int(text), tz=timezone.utc)
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None

rows = []
with path.open("r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        r = json.loads(line)
        qdate = parse_date(r.get("question_ts"))
        gold_ids = set(r.get("gold_chunk_ids", []))
        gold = [
            c for c in r.get("candidates", [])
            if c.get("doc_id") in gold_ids
        ]
        gold_dates = [parse_date(c.get("timestamp")) for c in gold]
        gold_dates = [d for d in gold_dates if d is not None]

        if qdate and gold_dates:
            gap_days = min(abs((qdate - d).days) for d in gold_dates)
            rows.append({
                "query": r.get("query", ""),
                "question_date": qdate.date().isoformat(),
                "gold_dates": [d.date().isoformat() for d in gold_dates],
                "nearest_gap_days": gap_days,
            })

rows.sort(key=lambda x: x["nearest_gap_days"], reverse=True)
print("Records with parseable question and gold dates:", len(rows))
print("Records with nearest gold passage over 30 days away:",
      sum(r["nearest_gap_days"] > 30 for r in rows))
print("Records with nearest gold passage over 365 days away:",
      sum(r["nearest_gap_days"] > 365 for r in rows))

print("\n10 largest date gaps:")
for r in rows[:10]:
    print("\nGap (days):", r["nearest_gap_days"])
    print("Question date:", r["question_date"])
    print("Gold passage date(s):", r["gold_dates"])
    print("Query:", r["query"])

out = Path("results/gold_date_gap_report.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nFull report saved to:", out)
