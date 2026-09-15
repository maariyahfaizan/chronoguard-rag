import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.dense import load_dense_model
from src.retrieval.hybrid import retrieve_hybrid
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.evaluator import evaluate_query, aggregate_metrics, aggregate_metrics_by_group

# StreamingQA-specific driver for E3 (hybrid RRF, no reranker). See
# run_baseline_streamingqa.py's header comment for the rationale.

INPUT_PATH = "data/processed/streamingqa_control_pools.jsonl"
LOG_PATH = "logs/streamingqa_hybrid_run.jsonl"

CANDIDATE_TOP_K = 20
FINAL_TOP_K = 5
RRF_K = 60


def run_hybrid_streamingqa(
    model=None,
    tokenizer=None,
    retriever_model=None,
    retriever_tokenizer=None,
    retriever_device=None,
    input_path=INPUT_PATH,
    log_path=LOG_PATH,
    candidate_top_k=CANDIDATE_TOP_K,
    final_top_k=FINAL_TOP_K,
    rrf_k=RRF_K,
):
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    if retriever_model is None or retriever_tokenizer is None or retriever_device is None:
        retriever_model, retriever_tokenizer, retriever_device = load_dense_model()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(input_path) as f:
        rows = [json.loads(line) for line in f]

    results = []
    groups = []

    with open(log_path, "w") as log_file:
        for query_id, row in enumerate(rows):
            query = row["query"]
            gold_answer = row["gold_answer"]
            gold_aliases = row.get("gold_aliases", [])
            question_ts = row["question_ts"]
            recent_or_past = row.get("recent_or_past")

            raw_candidates = row["candidates"]
            candidate_texts = [c["text"] for c in raw_candidates]
            candidate_doc_ids = [c["doc_id"] for c in raw_candidates]
            candidate_timestamps = [c["timestamp"] for c in raw_candidates]

            bm25_results, dense_results, fused_results = retrieve_hybrid(
                query=query,
                candidates=candidate_texts,
                retriever_model=retriever_model,
                retriever_tokenizer=retriever_tokenizer,
                retriever_device=retriever_device,
                candidate_top_k=candidate_top_k,
                final_top_k=final_top_k,
                rrf_k=rrf_k,
            )

            retrieved_indices = [idx for idx, text, score in fused_results]
            retrieved_passages = [text for idx, text, score in fused_results]
            retrieved_scores = [float(score) for idx, text, score in fused_results]
            retrieved_doc_ids = [candidate_doc_ids[i] for i in retrieved_indices]

            prompt = build_prompt(query, retrieved_passages)
            start_time = time.time()
            answer = generate_answer(query, retrieved_passages, model, tokenizer)
            latency = time.time() - start_time

            input_token_count = len(tokenizer(prompt)["input_ids"])
            output_token_count = len(tokenizer(answer)["input_ids"])

            metrics = evaluate_query(
                answer=answer,
                gold_answer=gold_answer,
                gold_aliases=gold_aliases,
                candidates=candidate_texts,
                retrieved_indices=retrieved_indices,
                k=final_top_k,
                question_ts=question_ts,
                candidate_timestamps=candidate_timestamps,
            )

            record = {
                "query_id": query_id,
                "query": query,
                "gold_answer": gold_answer,
                "gold_aliases": gold_aliases,
                "question_ts": question_ts,
                "recent_or_past": recent_or_past,
                "retriever": ["BM25", "facebook/contriever"],
                "retrieval_method": "hybrid_rrf",
                "candidate_top_k": candidate_top_k,
                "final_top_k": final_top_k,
                "rrf_k": rrf_k,
                "retrieved_passage_indices": retrieved_indices,
                "retrieved_doc_ids": retrieved_doc_ids,
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
            log_file.flush()
            results.append(record)
            groups.append(recent_or_past)

            tva_display = metrics.get("time_valid_answer_accuracy", "N/A")
            print(f"[{query_id + 1}/{len(rows)}] EM={metrics['em']} F1={metrics['f1']:.2f} "
                  f"Recall@{final_top_k}={metrics[f'recall_at_{final_top_k}']} "
                  f"nDCG@{final_top_k}={metrics[f'ndcg_at_{final_top_k}']} "
                  f"TVAA={tva_display} Q: {query[:60]}")

    summary = aggregate_metrics(results, k=final_top_k)
    by_group = aggregate_metrics_by_group(results, groups, k=final_top_k)

    print("\n=== StreamingQA Hybrid RRF Results ===")
    print(f"Examples: {summary['n_examples']}")
    print("Retrievers: BM25 + facebook/contriever")
    print(f"Candidate Top-K: {candidate_top_k}")
    print(f"Final Top-K: {final_top_k}")
    print(f"RRF K: {rrf_k}")
    print(f"Average EM: {summary['average_em']:.4f}")
    print(f"Average F1: {summary['average_f1']:.4f}")
    print(f"Average Recall@{final_top_k}: {summary[f'average_recall_at_{final_top_k}']}")
    print(f"Average nDCG@{final_top_k}: {summary[f'average_ndcg_at_{final_top_k}']}")
    if f"average_fraction_top_{final_top_k}_violating" in summary:
        print(f"Average fraction top-{final_top_k} violating: {summary[f'average_fraction_top_{final_top_k}_violating']}")
        print(f"Average valid-evidence Recall@{final_top_k}: {summary[f'average_valid_evidence_recall_at_{final_top_k}']}")
        print(f"Average Time-Valid Answer Accuracy: {summary['average_time_valid_answer_accuracy']}")
    print(f"By recent_or_past: {by_group}")

    return results, summary, by_group


if __name__ == "__main__":
    run_hybrid_streamingqa()