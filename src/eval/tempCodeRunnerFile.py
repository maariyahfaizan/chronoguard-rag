import json

def preprocess(input_path, outpath):
    cleaned = []
    with open(input_path) as f:
        for line in f:
            row = json.loads(line)

            candidates = []
            if row["entity_pages"]["wiki_context"]:
                candidates.extend(row["entity_pages"]["wiki_context"])
            if row["search_results"]["search_context"]:
                candidates.extend(row["search_results"]["search_context"])

            if not candidates:
                continue # skip examples with nothing to retrieve from

            cleaned.append({
                "query": row["question"],
                "gold_answer": row["answer"]["value"],
                "gold_aliases": row["answer"]["aliases"],
                "candidates": candidates
            })

    with open(outpath, "w") as f:
        for row in cleaned:
            f.write(json.dumps(row) + "\n")



if __name__ == "__main__":
    preprocess("data/raw/triviaqa_control_sample.jsonl", "data/processed/triviaqa_control_clean.jsonl")