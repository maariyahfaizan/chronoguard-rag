import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.bm25 import retrieve_best
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.evaluator import evaluate_query, aggregate_metrics

INPUT_PATH = "data/processed/triviaqa_control_clean.jsonl"
LOG_PATH = "logs/baseline_run.jsonl"
TOP_K = 5


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
            retrieved_indices = [idx for idx, text, score in retrieved]
            retrieved_passages = [text for idx, text, score in retrieved]
            retrieved_scores = [float(score) for idx, text, score in retrieved]

            # Generate
            prompt = build_prompt(query, retrieved_passages)
            start_time = time.time()
            answer = generate_answer(query, retrieved_passages, model, tokenizer)
            latency = time.time() - start_time

            # Token counts (for logging/compute-cost tracking)
            input_token_count = len(tokenizer(prompt)["input_ids"])
            output_token_count = len(tokenizer(answer)["input_ids"])

            # Score (EM, F1, Recall@k, nDCG@k -- same evaluator every experiment uses)
            metrics = evaluate_query(
                answer=answer,
                gold_answer=gold_answer,
                gold_aliases=gold_aliases,
                candidates=candidates,
                retrieved_indices=retrieved_indices,
                k=top_k,
            )

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
                **metrics,
            }

            log_file.write(json.dumps(record) + "\n")
            log_file.flush()  # write incrementally in case the Kaggle session drops
            results.append(record)

            print(f"[{query_id+1}/{len(rows)}] EM={metrics['em']} F1={metrics['f1']:.2f} "
                  f"Recall@{top_k}={metrics[f'recall_at_{top_k}']} "
                  f"nDCG@{top_k}={metrics[f'ndcg_at_{top_k}']}  Q: {query[:60]}")

    summary = aggregate_metrics(results, k=top_k)

    print("\n=== Baseline Results ===")
    print(f"Examples: {summary['n_examples']}")
    print(f"Average EM: {summary['average_em']:.4f}")
    print(f"Average F1: {summary['average_f1']:.4f}")
    print(f"Average Recall@{top_k}: {summary[f'average_recall_at_{top_k}']}")
    print(f"Average nDCG@{top_k}: {summary[f'average_ndcg_at_{top_k}']}")

    return results, summary


if __name__ == "__main__":
    run_baseline()