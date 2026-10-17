import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pilot_path = root / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
review_path = root / "results/stale_evidence_review_ranked.jsonl"

def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

pilot, rows = read(pilot_path), read(review_path)

for i, rec in enumerate(pilot):
    mine = [r for r in rows if r["query"] == rec["query"]]
    pool_ids = {c["doc_id"] for c in rec["candidates"]}
    print(f"pilot {i}: {rec['query'][:60]}")
    print("  review rows:", len(mine))
    print("  doc_id in pilot pool:", sum(r["doc_id"] in pool_ids for r in mine))
    print("  matched >=2 query terms:", sum(r["matched_term_count"] >= 2 for r in mine))
    print("  already validated:", sum(r["stale_evidence_validated"] for r in mine))
    if mine:
        ages = [r["age_days"] for r in mine]
        print("  age_days min/max:", min(ages), max(ages))