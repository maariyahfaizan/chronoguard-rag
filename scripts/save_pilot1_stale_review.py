import json
from pathlib import Path

REVIEWER = "Maariyah"

root = Path(__file__).resolve().parents[1]
pilot = [json.loads(l) for l in open(
    root / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl",
    encoding="utf-8") if l.strip()]
rec = pilot[1]

# pool slots read in show_pilot1_stale.py, with the first words of each text as a check
expected = {
    10: "EU news: Germany's Angela Merkel",
    16: "The Science Behind Feeling Rested",
    1: "When arteries narrow",
}
reason = ("Old and shares only filler words with the query; does not mention "
          "coronavirus or a count of countries, so it is not answer-bearing "
          "stale evidence.")

reviews = []
for slot, start in expected.items():
    cand = rec["candidates"][slot]
    assert cand["text"].startswith(start), f"slot {slot} text changed"
    reviews.append({
        "query_index": 1,
        "pilot_index": 1,
        "pool_slot": slot,
        "doc_id": cand["doc_id"],
        "validated": False,
        "reviewer": REVIEWER,
        "reason": reason,
    })

out = root / "results/pilot_stale_review.json"
out.write_text(json.dumps({"query": rec["query"], "reviews": reviews},
                          indent=2, ensure_ascii=False), encoding="utf-8")
print("saved", out, "with", len(reviews), "reviews, all validated=False")