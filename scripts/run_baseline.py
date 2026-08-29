import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.bm25 import retrieve_best
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.metrics import exact_match, f1_score

INPUT_PATH = "data/processed/triviaqa_control_clean.jsonl"
LOG_PATH = "logs/baseline_run.jsonl"
TOP_K = 3


def run_baseline(model=None, tokenizer=None, input_path=INPUT_PATH, log_path=LOG_PATH, top_k=TOP_K):
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(input_path) as f:
        rows = [json.loads(line) for line in f]

    results = []
    with open(log_path, "w") as log_file:
        for query_id, row in enumerate(rows):
            query = row["query"]
            gold_answer = row["gold_answer"]
            gold_aliases = row.get("gold_aliases", [])
            candidates = row["candidates"]

            # Retrieve
            retrieved = retrieve_best(query, candidates, top_k=top_k)
            retrieved_passages = [text for text, score in retrieved]
            retrieved_scores = [float(score) for text, score in retrieved]
            retrieved_indices = [candidates.index(p) for p in retrieved_passages]

            # Generate
            prompt = build_prompt(query, retrieved_passages)
            start_time = time.time()
            answer = generate_answer(query, retrieved_passages, model, tokenizer)
            latency = time.time() - start_time

            # Token counts (for logging/compute-cost tracking)
            input_token_count = len(tokenizer(prompt)["input_ids"])
            output_token_count = len(tokenizer(answer)["input_ids"])

            # Score
            em = exact_match(answer, gold_answer, gold_aliases)
            f1 = f1_score(answer, gold_answer, gold_aliases)

            record = {
                "query_id": query_id,
                "query": query,
                "gold_answer": gold_answer,
                "gold_aliases": gold_aliases,
                "retrieved_passage_indices": retrieved_indices,
                "retrieved_scores": retrieved_scores,
                "prompt": prompt,
                "generated_answer": answer,
                "latency_seconds": latency,
                "input_token_count": input_token_count,
                "output_token_count": output_token_count,
                "attack_condition": "clean",
                "em": em,
                "f1": f1,
            }

            log_file.write(json.dumps(record) + "\n")
            log_file.flush()  # write incrementally in case the Kaggle session drops
            results.append(record)

            print(f"[{query_id+1}/{len(rows)}] EM={em} F1={f1:.2f}  Q: {query[:60]}")

    avg_em = sum(r["em"] for r in results) / len(results)
    avg_f1 = sum(r["f1"] for r in results) / len(results)

    print("\n=== Baseline Results ===")
    print(f"Examples: {len(results)}")
    print(f"Average EM: {avg_em:.4f}")
    print(f"Average F1: {avg_f1:.4f}")

    return results


if __name__ == "__main__":
    run_baseline()