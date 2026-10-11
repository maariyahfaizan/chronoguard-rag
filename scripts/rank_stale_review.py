import json
import re
from pathlib import Path

path = Path("results/stale_evidence_review.jsonl")
rows = [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

stopwords = {
    "what", "when", "where", "which", "who", "whom", "whose",
    "why", "how", "is", "was", "were", "are", "the", "a", "an",
    "of", "in", "on", "at", "to", "for", "from", "by", "did",
    "do", "does", "this", "that", "these", "those", "name", "year",
}

for row in rows:
    query_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9]+", row["query"])
        if len(term) >= 3 and term.lower() not in stopwords
    }
    text_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9]+", row["text"])
    }
    matched = sorted(query_terms & text_terms)
    row["meaningful_query_terms"] = sorted(query_terms)
    row["matched_query_terms"] = matched
    row["matched_term_count"] = len(matched)

rows.sort(
    key=lambda row: (
        row["matched_term_count"],
        row["overlap_score"],
        row["age_days"],
    ),
    reverse=True,
)

output = Path("results/stale_evidence_review_ranked.jsonl")
with output.open("w", encoding="utf-8") as f:
    for row in rows:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

print("Candidates ranked:", len(rows))
print("Candidates matching at least 2 meaningful query terms:",
      sum(row["matched_term_count"] >= 2 for row in rows))
print("Saved:", output)

for i, row in enumerate(rows[:10], start=1):
    print(f"\n--- Candidate {i} ---")
    print("Query:", row["query"])
    print("Matched terms:", row["matched_query_terms"])
    print("Age in days:", row["age_days"])
    print("Text:", row["text"][:500])
