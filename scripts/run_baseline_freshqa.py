import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.retrieval.bm25 import retrieve_best
from src.generation.generate import load_model, generate_answer, build_prompt
from src.eval.evaluator import evaluate_query, aggregate_metrics, aggregate_metrics_by_group
from src.eval.freshqa_judge import judge_answer  # see freshqa_judge.py -- needs a judge model wired in

# FreshQA-specific driver for E1 (BM25). Separate file from
# run_baseline_streamingqa.py / run_baseline.py for the same reason those
# are separate from each other: existing results stay reproducible against
# unmodified code.
#
# Candidate shape (per build_freshqa_pools.py 2a patch): list[{doc_id,
# text, timestamp, is_source_document, url, final_url, title}] -- same
# unpack-before-use pattern as StreamingQA, plus one extra field
# (is_source_document) that StreamingQA's shape doesn't have.
#
# question_ts here is snapshot_retrieved_at-derived (see
# build_freshqa_pools.py's compute_question_ts), NOT a real per-question
# timestamp the way StreamingQA's question_ts is -- it's a query-time
# reference of last resort per freshqa_report.md 2d. Keep that distinction
# in mind when comparing StreamingQA's and FreshQA's temporal-metric
# numbers; they are not measuring the same kind of ground truth.

INPUT_PATH = "data/processed/freshqa_control_pools.jsonl"
LOG_PATH = "logs/freshqa_baseline_run.jsonl"
TOP_K = 5  # same retrieval depth as the other E1 runs, per plan Section 6


def run_baseline_freshqa(
    model=None,
    tokenizer=None,
    judge_model=None,
    input_path=INPUT_PATH,
    log_path=LOG_PATH,
    top_k=TOP_K,
):
    if model is None or tokenizer is None:
        model, tokenizer = load_model()

    # Default judge is the SAME (model, tokenizer) used for generation --
    # see freshqa_judge.py's module docstring for why, and for the caveat
    # this means FreshEval numbers are "Mistral-7B-judged," not directly
    # comparable to FreshQA's own GPT-4-judged published numbers. Pass a
    # different judge_model=(other_model, other_tokenizer) explicitly to
    # use a separate/stronger judge instead.
    if judge_model is None:
        judge_model = (model, tokenizer)

    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(input_path) as f:
        rows = [json.loads(line) for line in f]

    results = []
    groups = []  # fact_type per query, for aggregate_metrics_by_group

    with open(log_path, "w") as log_file:
        for query_id, row in enumerate(rows):
            query = row["query"]
            gold_answer = row["gold_answer"]
            gold_aliases = row.get("gold_aliases", [])
            question_ts = row.get("question_ts")  # may be None -- see module docstring
            false_premise = row.get("false_premise")
            fact_type = row.get("fact_type")

            # Unpack {doc_id, text, timestamp, is_source_document, ...}
            # dicts into parallel lists -- retrieve_best/evaluate_query
            # both require plain text, exactly as for StreamingQA.
            raw_candidates = row["candidates"]
            candidate_texts = [c["text"] for c in raw_candidates]
            candidate_doc_ids = [c["doc_id"] for c in raw_candidates]
            candidate_timestamps = [c["timestamp"] for c in raw_candidates]
            candidate_is_source = [
                int(bool(c.get("is_source_document"))) for c in raw_candidates
            ]

            # Retrieve
            retrieved = retrieve_best(query, candidate_texts, top_k=top_k)
            retrieved_indices = [idx for idx, text, score in retrieved]
            retrieved_passages = [text for idx, text, score in retrieved]
            retrieved_scores = [float(score) for idx, text, score in retrieved]
            retrieved_doc_ids = [candidate_doc_ids[i] for i in retrieved_indices]

            # Generate
            prompt = build_prompt(query, retrieved_passages)
            start_time = time.time()
            answer = generate_answer(query, retrieved_passages, model, tokenizer)
            latency = time.time() - start_time

            input_token_count = len(tokenizer(prompt)["input_ids"])
            output_token_count = len(tokenizer(answer)["input_ids"])

            # Score -- true_relevance_labels uses is_source_document (2b)
            # instead of the word-overlap fallback; question_ts/
            # candidate_timestamps are passed so the four temporal metrics
            # get computed whenever question_ts is available for this
            # question (it may legitimately be None -- see module
            # docstring), in which case evaluate_query omits those keys.
            metrics = evaluate_query(
                answer=answer,
                gold_answer=gold_answer,
                gold_aliases=gold_aliases,
                candidates=candidate_texts,
                retrieved_indices=retrieved_indices,
                k=top_k,
                question_ts=question_ts,
                candidate_timestamps=candidate_timestamps,
                true_relevance_labels=candidate_is_source,
            )

            # FreshEval-style judged correctness -- the HEADLINE accuracy
            # number for FreshQA per freshqa_report.md 2c/plan Section 7
            # ("benchmark accuracy"); metrics["em"]/["f1"] above are kept
            # as secondary/diagnostic only, per the same decision. See
            # freshqa_judge.py for the rubric and judge-model wiring this
            # currently depends on (NOT YET CONNECTED -- see that file).
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
                "fresheval_correct": judge_result["correct"],
                "fresheval_rationale": judge_result["rationale"],
                **metrics,
            }

            log_file.write(json.dumps(record) + "\n")
            log_file.flush()
            results.append(record)
            groups.append(fact_type)

            tva_display = metrics.get("time_valid_answer_accuracy", "N/A")
            print(
                f"[{query_id+1}/{len(rows)}] EM={metrics['em']} F1={metrics['f1']:.2f} "
                f"FreshEval={judge_result['correct']} "
                f"Recall@{top_k}={metrics[f'recall_at_{top_k}']} "
                f"nDCG@{top_k}={metrics[f'ndcg_at_{top_k}']} "
                f"TVAA={tva_display}  Q: {query[:60]}"
            )

    summary = aggregate_metrics(results, k=top_k)
    by_group = aggregate_metrics_by_group(results, groups, k=top_k)

    n = len(results)
    avg_fresheval = sum(r["fresheval_correct"] for r in results if r["fresheval_correct"] is not None)
    n_judged = sum(1 for r in results if r["fresheval_correct"] is not None)

    print("\n=== FreshQA BM25 Baseline Results ===")
    print(f"Examples: {summary['n_examples']}")
    print(f"Average FreshEval accuracy: {avg_fresheval / n_judged if n_judged else 'N/A'}  (headline metric)")
    print(f"Average EM: {summary['average_em']:.4f}  (diagnostic only, see freshqa_report.md 2c)")
    print(f"Average F1: {summary['average_f1']:.4f}  (diagnostic only, see freshqa_report.md 2c)")
    print(f"Average Recall@{top_k}: {summary[f'average_recall_at_{top_k}']}")
    print(f"Average nDCG@{top_k}: {summary[f'average_ndcg_at_{top_k}']}")
    if f"average_fraction_top_{top_k}_violating" in summary:
        print(f"Average fraction top-{top_k} violating: {summary[f'average_fraction_top_{top_k}_violating']}")
        print(f"Average valid-evidence Recall@{top_k}: {summary[f'average_valid_evidence_recall_at_{top_k}']}")
        print(f"Average Time-Valid Answer Accuracy: {summary['average_time_valid_answer_accuracy']}")
    else:
        print("Temporal metrics: not computed for any question (no question_ts available)")
    print(f"By fact_type: {by_group}")

    return results, summary, by_group


if __name__ == "__main__":
    run_baseline_freshqa()