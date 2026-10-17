import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]

def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]

pilot = read(root / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl")
rows = read(root / "results/stale_evidence_review_ranked.jsonl")

rec = pilot[1]
print("record keys:", sorted(rec.keys()))
print("query:", rec["query"])
print("gold_answer:", rec.get("gold_answer"), "| aliases:", rec.get("gold_aliases"))
print("question_ts:", rec["question_ts"])
print()
print("GOLD-FLAGGED CANDIDATES")
for i, c in enumerate(rec["candidates"]):
    if c.get("is_source_document"):
        print(f"[pool {i}] {c['timestamp']} :: {c['text'][:500]}")
print()
print("STALE REVIEW CANDIDATES")
for r in [r for r in rows if r["query"] == rec["query"]]:
    idxs = [i for i, c in enumerate(rec["candidates"]) if c["doc_id"] == r["doc_id"]]
    print(f"[pool {idxs}] age={r['age_days']} matched={r['matched_query_terms']}")
    print("  doc_id tail:", repr(r["doc_id"][-30:]))
    print("  text:", r["text"][:700].replace("\n", " "))
    print()