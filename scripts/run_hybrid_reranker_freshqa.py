import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.dense import load_dense_model
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.retrieval.bm25 import retrieve_best as bm25_retrieve
from src.retrieval.dense import retrieve_best as dense_retrieve
from src.retrieval.reranker import load_reranker, rerank
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.evaluator import evaluate_query, aggregate_metrics, aggregate_metrics_by_group
from src.eval.freshqa_judge import judge_answer
from src.eval.resumable_log import load_existing_results

# FreshQA-specific driver for E4 (hybrid RRF + BGE cross-encoder
# reranker). See run_baseline_freshqa.py's header comment for the
# general rationale.

INPUT_PATH = "data/processed/freshqa_control_pools.jsonl"
LOG_PATH = "logs/freshqa_hybrid_reranker_run.jsonl"

CANDIDATE_TOP_K = 20
FUSED_TOP_K = 20
FINAL_TOP_K = 5
RRF_K = 60

RERANKER_MODEL = "BAAI/bge-reranker-base"


def run_hybrid_cross_encoder_freshqa(
    model=None,
    tokenizer=None,
    retriever_model=None,
    retriever_tokenizer=None,
    retriever_device=None,
    reranker_model=None,
    judge_model=None,
    input_path=INPUT_PATH,
    log_path=LOG_PATH,
    candidate_top_k=CANDIDATE_TOP_K,
    fused_top_k=FUSED_TOP_K,
    final_top_k=FINAL_TOP_K,
    rrf_k=RRF_K,
):
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    if retriever_model is None or retriever_tokenizer is None or retriever_device is None:
        retriever_model, retriever_tokenizer, retriever_device = load_dense_model()

    if reranker_model is None:
        reranker_model, reranker_device = load_reranker(RERANKER_MODEL)

    if judge_model is None:
        judge_model = (model, tokenizer)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(input_path, "r") as f:
        rows = [json.loads(line) for line in f]

    results, groups, completed_ids = load_existing_results(log_path, group_key="fact_type")
    log_mode = "a" if completed_ids else "w"

    with open(log_path, log_mode) as log_file:
        for query_id, row in enumerate(rows):
            if query_id in completed_ids:
                continue
            query = row["query"]
            gold_answer = row["gold_answer"]
            gold_aliases = row.get("gold_aliases", [])
            question_ts = row.get("question_ts")
            false_premise = row.get("false_premise")
            fact_type = row.get("fact_type")

            raw_candidates = row["candidates"]
            candidate_texts = [c["text"] for c in raw_candidates]
            candidate_doc_ids = [c["doc_id"] for c in raw_candidates]
            candidate_timestamps = [c["timestamp"] for c in raw_candidates]
            candidate_is_source = [
                int(bool(c.get("is_source_document"))) for c in raw_candidates
            ]

            # 1. BM25 top-candidate_top_k
            bm25_results = bm25_retrieve(query, candidate_texts, top_k=candidate_top_k)

            # 2. Contriever top-candidate_top_k
            dense_results = dense_retrieve(
                query, candidate_texts, retriever_model, retriever_tokenizer,
                retriever_device, top_k=candidate_top_k
            )

            # 3. RRF fusion -> top-fused_top_k
            fused_results = reciprocal_rank_fusion(
                bm25_results, dense_results, top_k=fused_top_k, rrf_k=rrf_k
            )

            # 4. BGE cross-encoder reranker -> top-final_top_k
            reranked_results = rerank(
                query=query, candidates=fused_results, model=reranker_model,
                top_k=final_top_k, batch_size=8
            )

            retrieved_indices = [idx for idx, text, score in reranked_results]
            retrieved_passages = [text for idx, text, score in reranked_results]
            retrieved_scores = [float(score) for idx, text, score in reranked_results]
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
                true_relevance_labels=candidate_is_source,
            )

            judge_result = judge_answer(
                question=query,
                model_answer=answer,
                gold_answer=gold_answer,
                gold_aliases=gold_aliases,
                false_premise=false_premise,
                judge_model=judge_model,
            )

            record = {
                "query_id": query_id,
                "query": query,
                "gold_answer": gold_answer,
                "gold_aliases": gold_aliases,
                "question_ts": question_ts,
                "false_premise": false_premise,
                "fact_type": fact_type,
                "retriever": ["BM25", "facebook/contriever"],
                "retrieval_method": "hybrid_rrf_cross_encoder",
                "candidate_top_k": candidate_top_k,
                "fused_top_k": fused_top_k,
                "final_top_k": final_top_k,
                "rrf_k": rrf_k,
                "reranker": RERANKER_MODEL,
                "retrieved_passage_indices": retrieved_indices,
                "retrieved_doc_ids": retrieved_doc_ids,
                "retrieved_scores": retrieved_scores,
                "prompt": prompt,
                "generated_answer": answer,
                "latency_seconds": latency,
                "input_token_count": input_token_count,
                "output_token_count": output_token_count,
                "attack_condition": "clean",
                "fresheval_correct": judge_result["correct"],
                "fresheval_rationale": judge_result["rationale"],
                **metrics,
            }

            log_file.write(json.dumps(record) + "\n")
            log_file.flush()
            results.append(record)
            groups.append(fact_type)

            recall_display = (
                f"{metrics[f'recall_at_{final_top_k}']:.4f}"
                if metrics[f"recall_at_{final_top_k}"] is not None else "N/A"
            )
            ndcg_display = (
                f"{metrics[f'ndcg_at_{final_top_k}']:.4f}"
                if metrics[f"ndcg_at_{final_top_k}"] is not None else "N/A"
            )
            tva_display = metrics.get("time_valid_answer_accuracy", "N/A")

            print(f"[{query_id + 1}/{len(rows)}] Recall@{final_top_k}={recall_display} "
                  f"nDCG@{final_top_k}={ndcg_display} EM={metrics['em']} F1={metrics['f1']:.2f} "
                  f"FreshEval={judge_result['correct']} "
                  f"TVAA={tva_display} Q: {query[:60]}")

    summary = aggregate_metrics(results, k=final_top_k)
    by_group = aggregate_metrics_by_group(results, groups, k=final_top_k)

    n_judged = sum(1 for r in results if r["fresheval_correct"] is not None)
    avg_fresheval = sum(r["fresheval_correct"] for r in results if r["fresheval_correct"] is not None)

    print(f"Recall@{final_top_k}: {summary[f'average_recall_at_{final_top_k}']}")
    print(f"nDCG@{final_top_k}: {summary[f'average_ndcg_at_{final_top_k}']}")
    print(f"Average FreshEval accuracy: {avg_fresheval / n_judged if n_judged else 'N/A'}  (headline metric)")
    print(f"Average EM: {summary['average_em']:.4f}  (diagnostic only)")
    print(f"Average F1: {summary['average_f1']:.4f}  (diagnostic only)")
    if f"average_fraction_top_{final_top_k}_violating" in summary:
        print(f"Average fraction top-{final_top_k} violating: {summary[f'average_fraction_top_{final_top_k}_violating']}")
        print(f"Average valid-evidence Recall@{final_top_k}: {summary[f'average_valid_evidence_recall_at_{final_top_k}']}")
        print(f"Average Time-Valid Answer Accuracy: {summary['average_time_valid_answer_accuracy']}")
    else:
        print("Temporal metrics: not computed for any question (no question_ts available)")
    print(f"By fact_type: {by_group}")

    return results, summary, by_group


if __name__ == "__main__":
    run_hybrid_cross_encoder_freshqa()