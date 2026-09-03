import json
import os
import sys
import time

sys.path.append(
    os.path.join(os.path.dirname(__file__), "..")
)

from src.retrieval.dense import load_dense_model
from src.retrieval.hybrid import (
    reciprocal_rank_fusion
)
from src.retrieval.bm25 import (
    retrieve_best as bm25_retrieve
)
from src.retrieval.dense import (
    retrieve_best as dense_retrieve
)
from src.retrieval.reranker import (
    load_reranker,
    rerank
)

from src.generation.generate import (
    load_model,
    generate_answer,
    build_prompt
)

from src.eval.metrics import (
    exact_match,
    f1_score,
    get_relevance_labels,
    recall_at_k,
    ndcg_at_k
)


INPUT_PATH = "data/processed/triviaqa_control_clean.jsonl"
LOG_PATH = "logs/hybrid_reranker_run.jsonl"

CANDIDATE_TOP_K = 20
FUSED_TOP_K = 20
FINAL_TOP_K = 5
RRF_K = 60

RERANKER_MODEL = "BAAI/bge-reranker-base"



def run_hybrid_cross_encoder(
    model=None,
    tokenizer=None,
    retriever_model=None,
    retriever_tokenizer=None,
    retriever_device=None,
    reranker_model=None,
    input_path=INPUT_PATH,
    log_path=LOG_PATH,
    candidate_top_k=CANDIDATE_TOP_K,
    fused_top_k=FUSED_TOP_K,
    final_top_k=FINAL_TOP_K,
    rrf_k=RRF_K
):

    # -----------------------------------------------------
    # Load Mistral
    # -----------------------------------------------------

    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    # -----------------------------------------------------
    # Load Contriever
    # -----------------------------------------------------

    if (
        retriever_model is None
        or retriever_tokenizer is None
        or retriever_device is None
    ):
        (
            retriever_model,
            retriever_tokenizer,
            retriever_device
        ) = load_dense_model()

    # -----------------------------------------------------
    # Load BGE reranker
    # -----------------------------------------------------

    if reranker_model is None:
        reranker_model, reranker_device = load_reranker(
            RERANKER_MODEL
        )

    # -----------------------------------------------------
    # Create log directory
    # -----------------------------------------------------

    os.makedirs(
        os.path.dirname(log_path),
        exist_ok=True
    )

    # -----------------------------------------------------
    # Load dataset
    # -----------------------------------------------------

    with open(input_path, "r") as f:
        rows = [
            json.loads(line)
            for line in f
        ]

    results = []

    # -----------------------------------------------------
    # Run examples
    # -----------------------------------------------------

    with open(log_path, "w") as log_file:

        for query_id, row in enumerate(rows):

            query = row["query"]

            gold_answer = row["gold_answer"]

            gold_aliases = row.get(
                "gold_aliases",
                []
            )

            candidates = row["candidates"]

            # =================================================
            # 1. BM25 TOP-20
            # =================================================

            bm25_results = bm25_retrieve(
                query,
                candidates,
                top_k=candidate_top_k
            )

            # =================================================
            # 2. CONTRIEVER TOP-20
            # =================================================

            dense_results = dense_retrieve(
                query,
                candidates,
                retriever_model,
                retriever_tokenizer,
                retriever_device,
                top_k=candidate_top_k
            )

            # =================================================
            # 3. RRF -> TOP-20
            # =================================================

            fused_results = reciprocal_rank_fusion(
                bm25_results,
                dense_results,
                top_k=fused_top_k,
                rrf_k=rrf_k
            )

            # =================================================
            # 4. BGE CROSS-ENCODER -> TOP-5
            # =================================================

            reranked_results = rerank(
                query=query,
                candidates=fused_results,
                model=reranker_model,
                top_k=final_top_k,
                batch_size=8
            )

            # =================================================
            # Final passages
            # =================================================

            retrieved_passages = [
                text
                for text, score in reranked_results
            ]

            # BGE scores
            retrieved_scores = [
                float(score)
                for text, score in reranked_results
            ]

            # =================================================
            # Original candidate indices
            # =================================================

            retrieved_indices = [
                candidates.index(passage)
                for passage in retrieved_passages
            ]

            # =================================================
            # Retrieval relevance labels
            # =================================================

            relevance_labels = get_relevance_labels(
                candidates,
                gold_answer,
                gold_aliases
            )

            # =================================================
            # Recall@5
            # =================================================

            recall = recall_at_k(
                retrieved_indices,
                relevance_labels,
                k=FINAL_TOP_K
            )

            # =================================================
            # nDCG@5
            # =================================================

            ndcg = ndcg_at_k(
                retrieved_indices,
                relevance_labels,
                k=FINAL_TOP_K
            )

            # =================================================
            # Generation
            # =================================================

            prompt = build_prompt(
                query,
                retrieved_passages
            )

            start_time = time.time()

            answer = generate_answer(
                query,
                retrieved_passages,
                model,
                tokenizer
            )

            latency = time.time() - start_time

            # =================================================
            # Token counts
            # =================================================

            input_token_count = len(
                tokenizer(prompt)["input_ids"]
            )

            output_token_count = len(
                tokenizer(answer)["input_ids"]
            )

            # =================================================
            # Evaluation
            # =================================================

            em = exact_match(
                answer,
                gold_answer,
                gold_aliases
            )

            f1 = f1_score(
                answer,
                gold_answer,
                gold_aliases
            )

            # =================================================
            # Logging
            # =================================================

            record = {
                "query_id": query_id,
                "query": query,
                "gold_answer": gold_answer,
                "gold_aliases": gold_aliases,

                "retriever": [
                    "BM25",
                    "facebook/contriever"
                ],

                "retrieval_method":
                    "hybrid_rrf_cross_encoder",

                "candidate_top_k":
                    candidate_top_k,

                "fused_top_k":
                    fused_top_k,

                "final_top_k":
                    final_top_k,

                "rrf_k":
                    rrf_k,

                "reranker":
                    RERANKER_MODEL,

                "retrieved_passage_indices":
                    retrieved_indices,

                "retrieved_scores":
                    retrieved_scores,

                "recall_at_5":
                    recall,

                "ndcg_at_5":
                    ndcg,

                "prompt":
                    prompt,

                "generated_answer":
                    answer,

                "latency_seconds":
                    latency,

                "input_token_count":
                    input_token_count,

                "output_token_count":
                    output_token_count,

                "attack_condition":
                    "clean",

                "em":
                    em,

                "f1":
                    f1
            }

            log_file.write(
                json.dumps(record) + "\n"
            )

            log_file.flush()

            results.append(record)

            recall_display = (
    f"{recall:.4f}"
    if recall is not None
    else "N/A"
)

            ndcg_display = (
                f"{ndcg:.4f}"
                if ndcg is not None
                else "N/A"
            )

            print(
                f"[{query_id + 1}/{len(rows)}] "
                f"Recall@5={recall_display} "
                f"nDCG@5={ndcg_display} "
                f"EM={em} "
                f"F1={f1:.2f} "
                f"Q: {query[:60]}"
            )

    # =====================================================
    # Final results
    # =====================================================

    valid_recall = [
        r["recall_at_5"]
        for r in results
        if r["recall_at_5"] is not None
    ]

    valid_ndcg = [
        r["ndcg_at_5"]
        for r in results
        if r["ndcg_at_5"] is not None
    ]

    avg_recall = (
        sum(valid_recall) / len(valid_recall)
        if valid_recall
        else 0.0
    )

    avg_ndcg = (
        sum(valid_ndcg) / len(valid_ndcg)
        if valid_ndcg
        else 0.0
    )

    avg_em = (
        sum(r["em"] for r in results)
        / len(results)
    )

    avg_f1 = (
        sum(r["f1"] for r in results)
        / len(results)
    )

    # =====================================================
    # Print final results
    # =====================================================

    print(
        "\n=== Hybrid RRF + BGE Reranker Results ==="
    )

    print(
        f"Examples: {len(results)}"
    )

    print(
        "Retrievers: BM25 + facebook/contriever"
    )

    print(
        f"Candidate Top-K: {candidate_top_k}"
    )

    print(
        f"Fused Top-K: {fused_top_k}"
    )

    print(
        f"RRF K: {rrf_k}"
    )

    print(
        f"Reranker: {RERANKER_MODEL}"
    )

    print(
        f"Final Top-K: {final_top_k}"
    )

    print(
        f"Recall@5: {avg_recall:.4f}"
    )

    print(
        f"nDCG@5: {avg_ndcg:.4f}"
    )

    print(
        f"Average EM: {avg_em:.4f}"
    )

    print(
        f"Average F1: {avg_f1:.4f}"
    )

    return results


if __name__ == "__main__":
    run_hybrid_cross_encoder()