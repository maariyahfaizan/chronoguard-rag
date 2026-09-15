import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.bm25 import retrieve_best
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.evaluator import evaluate_query, aggregate_metrics, aggregate_metrics_by_group

# StreamingQA-specific driver for E1 (BM25). Deliberately a separate file
# from run_baseline.py rather than a branch inside it -- run_baseline.py
# stays byte-identical and TriviaQA's existing results (Report_week3.md)
# remain reproducible against unmodified code, per instruction.
#
# The only structural difference from run_baseline.py: StreamingQA's
# candidates are list[{doc_id, text, timestamp}], not list[str], so they
# must be unpacked into parallel lists before being handed to any
# retrieval/eval function -- none of those functions read dicts.

INPUT_PATH = "data/processed/streamingqa_control_pools.jsonl"
LOG_PATH = "logs/streamingqa_baseline_run.jsonl"
TOP_K = 5  # same retrieval depth as the TriviaQA E1 run, per plan Section 6
           # ("identical retrieval depth ... where possible")


def run_baseline_streamingqa(model=None, tokenizer=None, input_path=INPUT_PATH, log_path=LOG_PATH, top_k=TOP_K):
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(input_path) as f:
        rows = [json.loads(line) for line in f]

    results = []
    groups = []  # recent_or_past per query, for aggregate_metrics_by_group

    with open(log_path, "w") as log_file:
        for query_id, row in enumerate(rows):
            query = row["query"]
            gold_answer = row["gold_answer"]
            gold_aliases = row.get("gold_aliases", [])
            question_ts = row["question_ts"]
            recent_or_past = row.get("recent_or_past")

            # Unpack {doc_id, text, timestamp} dicts into parallel lists.
            # retrieve_best/evaluate_query both require plain text -- passing
            # the raw dicts through would fail inside BM25Okapi's tokenization
            # (c.split(" ")) or normalize_answer(), not at this boundary.
            raw_candidates = row["candidates"]
            candidate_texts = [c["text"] for c in raw_candidates]
            candidate_doc_ids = [c["doc_id"] for c in raw_candidates]
            candidate_timestamps = [c["timestamp"] for c in raw_candidates]

            # Retrieve
            retrieved = retrieve_best(query, candidate_texts, top_k=top_k)
            retrieved_indices = [idx for idx, text, score in retrieved]
            retrieved_passages = [text for idx, text, score in retrieved]
            retrieved_scores = [float(score) for idx, text, score in retrieved]
            # Real doc IDs for the retrieved passages -- Section 9 requires
            # logging "retrieved document IDs", and unlike TriviaQA's
            # position-index-only logging, StreamingQA has real doc_ids to log.
            retrieved_doc_ids = [candidate_doc_ids[i] for i in retrieved_indices]

            # Generate
            prompt = build_prompt(query, retrieved_passages)
            start_time = time.time()
            answer = generate_answer(query, retrieved_passages, model, tokenizer)
            latency = time.time() - start_time

            # Token counts
            input_token_count = len(tokenizer(prompt)["input_ids"])
            output_token_count = len(tokenizer(answer)["input_ids"])

            # Score -- pass question_ts/candidate_timestamps so the four
            # temporal metrics get computed; used_candidate_timestamps is left
            # to evaluate_query's default (candidate_timestamps at
            # retrieved_indices[:k]), which matches this loop's flow exactly:
            # retrieve_best already returns exactly top_k, unchanged before
            # generation.
            metrics = evaluate_query(
                answer=answer,
                gold_answer=gold_answer,
                gold_aliases=gold_aliases,
                candidates=candidate_texts,
                retrieved_indices=retrieved_indices,
                k=top_k,
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
                "retriever": "BM25",
                "retrieval_method": "bm25",
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
            print(f"[{query_id+1}/{len(rows)}] EM={metrics['em']} F1={metrics['f1']:.2f} "
                  f"Recall@{top_k}={metrics[f'recall_at_{top_k}']} "
                  f"nDCG@{top_k}={metrics[f'ndcg_at_{top_k}']} "
                  f"TVAA={tva_display}  Q: {query[:60]}")

    summary = aggregate_metrics(results, k=top_k)
    by_group = aggregate_metrics_by_group(results, groups, k=top_k)

    print("\n=== StreamingQA BM25 Baseline Results ===")
    print(f"Examples: {summary['n_examples']}")
    print(f"Average EM: {summary['average_em']:.4f}")
    print(f"Average F1: {summary['average_f1']:.4f}")
    print(f"Average Recall@{top_k}: {summary[f'average_recall_at_{top_k}']}")
    print(f"Average nDCG@{top_k}: {summary[f'average_ndcg_at_{top_k}']}")
    if f"average_fraction_top_{top_k}_violating" in summary:
        print(f"Average fraction top-{top_k} violating: {summary[f'average_fraction_top_{top_k}_violating']}")
        print(f"Average valid-evidence Recall@{top_k}: {summary[f'average_valid_evidence_recall_at_{top_k}']}")
        print(f"Average Time-Valid Answer Accuracy: {summary['average_time_valid_answer_accuracy']}")
    print(f"By recent_or_past: {by_group}")

    return results, summary, by_group


if __name__ == "__main__":
    run_baseline_streamingqa()