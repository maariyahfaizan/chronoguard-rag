import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.dense import load_dense_model, retrieve_best
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.metrics import exact_match, f1_score


INPUT_PATH = "data/processed/triviaqa_control_clean.jsonl"
LOG_PATH = "logs/dense_run.jsonl"

TOP_K = 5


def run_dense(
    model=None,
    tokenizer=None,
    retriever_model=None,
    retriever_tokenizer=None,
    retriever_device=None,
    input_path=INPUT_PATH,
    log_path=LOG_PATH,
    top_k=TOP_K
):

    # Load Mistral generator
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    # Load Contriever retriever
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

            # -------------------------
            # Dense retrieval
            # -------------------------

            retrieved = retrieve_best(
                query,
                candidates,
                retriever_model,
                retriever_tokenizer,
                retriever_device,
                top_k=top_k
            )

            retrieved_passages = [
                text for text, score in retrieved
            ]

            retrieved_scores = [
                float(score) for text, score in retrieved
            ]

            retrieved_indices = [
                candidates.index(p)
                for p in retrieved_passages
            ]

            # -------------------------
            # Generation
            # -------------------------

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

            # -------------------------
            # Token counts
            # -------------------------

            input_token_count = len(
                tokenizer(prompt)["input_ids"]
            )

            output_token_count = len(
                tokenizer(answer)["input_ids"]
            )

            # -------------------------
            # Evaluation
            # -------------------------

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

            # -------------------------
            # Logging
            # -------------------------

            record = {
                "query_id": query_id,
                "query": query,
                "gold_answer": gold_answer,
                "gold_aliases": gold_aliases,
                "retriever": "facebook/contriever",
                "retrieval_method": "dense_dot_product",
                "top_k": top_k,
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

            log_file.write(
                json.dumps(record) + "\n"
            )

            log_file.flush()

            results.append(record)

            print(
                f"[{query_id + 1}/{len(rows)}] "
                f"EM={em} F1={f1:.2f} "
                f"Q: {query[:60]}"
            )

    # -------------------------
    # Final results
    # -------------------------

    avg_em = sum(
        r["em"] for r in results
    ) / len(results)

    avg_f1 = sum(
        r["f1"] for r in results
    ) / len(results)

    print("\n=== Dense Retrieval Results ===")
    print(f"Examples: {len(results)}")
    print(f"Retriever: facebook/contriever")
    print(f"Top-K: {top_k}")
    print(f"Average EM: {avg_em:.4f}")
    print(f"Average F1: {avg_f1:.4f}")

    return results


if __name__ == "__main__":
    run_dense()