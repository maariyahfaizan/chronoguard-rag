# ChronoGuard-RAG

Clean RAG baselines for a study of **freshness poisoning** in retrieval-augmented generation: how stale, fabricated-"newer", or timestamp-shifted evidence can override correct evidence, and how a recency-aware verification layer (ChronoGuard-RAG) can defend against it.

**Current phase:** Weeks 3-4 (clean baselines) are in their closure cycle. Gate A is complete. Gate B is in progress. No attack conditions and no ChronoGuard defense have been implemented yet. Week 5 (attack construction) starts once Week 4 is signed off.

**Frozen baseline commit:** `<FILL IN LAST: git rev-parse HEAD after final commit; tag week4-frozen>`

---

## 1. Datasets and roles

| Dataset | Role | Sample | Notes |
|---|---|---|---|
| **StreamingQA** | Primary time-sensitive benchmark | Seeded n=100 (seed=42) from the eval subset | Per-document timestamps by construction; official clean reference after Gate A |
| **FreshQA** | Current / fast-changing knowledge | Full TEST split, 477 of 500 questions | Temporal metrics mostly undefined (sparse evidence dates) |
| **TriviaQA** | Static, non-temporal control | Seeded n=100 (seed=42) from the validation split | Answer-first evidence construction inflates absolute retrieval metrics |

StreamingQA and TriviaQA at n=100 are dev-scale, pipeline-validated samples. They are not yet at the 300-500+ scale intended for paper numbers.

## 2. Systems under test

All four share one generator, one prompt template and one evaluation path, so retrieval is the only variable.

| ID | Retrieval |
|---|---|
| E1 | BM25 |
| E2 | Dense bi-encoder (Contriever) |
| E3 | Hybrid RRF (BM25 + Contriever, RRF-k=60) |
| E4 | Hybrid RRF + BGE cross-encoder reranker (`BAAI/bge-reranker-base`) |

Generator: `mistralai/Mistral-7B-Instruct-v0.2`, 4-bit, greedy decoding (`do_sample=False`). Final context: top-k = 5, from a 20-candidate pool.

## 3. Results

### 3.1 StreamingQA (official clean reference, post-Gate-A)

n=100, Recall@5 / nDCG@5 / valid-evidence Recall@5 defined on 97/100 queries.

| | EM | F1 | Recall@5 | nDCG@5 | Frac. top-5 violating | TVAA |
|---|---:|---:|---:|---:|---:|---:|
| E1 BM25 | 0.620 | 0.781 | 0.930 | 0.926 | 0.026 | 0.55 |
| E2 Contriever | 0.610 | 0.782 | 0.982 | 0.992 | 0.036 | 0.53 |
| E3 Hybrid RRF | 0.590 | 0.770 | 0.946 | 0.952 | 0.032 | 0.51 |
| E4 Hybrid + Reranker | 0.590 | 0.776 | 0.982 | 0.977 | 0.024 | 0.53 |

TVAA = time-valid answer accuracy. The pre-Gate-A run used a different gold mapping and an unchunked pool (74/100 queries with defined retrieval metrics), so its numbers are not comparable with this table. They are retained in `configs/streamingqa_eval_config.yaml` for audit only.

**Paired statistics (Holm-Bonferroni, 10,000 bootstrap resamples).** Correction was applied within each metric (6 pairwise comparisons) and, as a sensitivity check, across all 42 comparisons.

- Robust across both corrections: **E2 beats E1** on Recall@5, nDCG@5 and valid-evidence Recall@5. E1 vs E3 and E2 vs E3 differ on nDCG@5.
- **No EM, F1, TVAA or violation-rate difference survives correction** (all-metrics Holm p = 1.0). At n=100 no generation-level claim is supported.
- E4 is not distinguishable from E2 on any checked metric.

### 3.2 FreshQA (full 477, final configuration)

| Metric | E1 | E2 | E3 | E4 |
|---|---:|---:|---:|---:|
| FreshEval accuracy (headline) | 0.5304 | **0.5807** | 0.5597 | 0.5660 |
| EM (diagnostic) | 0.1258 | 0.1551 | 0.1488 | **0.1656** |
| F1 (diagnostic) | 0.2955 | 0.3438 | 0.3311 | **0.3510** |
| Recall@5 | 0.7977 | **0.9990** | 0.8843 | 0.9822 |
| nDCG@5 | 0.7290 | **0.9766** | 0.8249 | 0.9516 |

**Caveats.**
- FreshEval accuracy is judged by the same Mistral-7B that generates the answers. It is a development metric. It is **not comparable to published GPT-4-judged FreshQA numbers**, and judge validation is pending (Gate B item 9).
- Time-valid answer accuracy is undefined for all 477 questions. Fraction-violating (42-88 questions) and valid-evidence Recall@5 (15 questions) are defined for only a small subset, because per-passage `source_date` coverage is sparse. Any FreshQA temporal average must be read with its `n_defined`. StreamingQA carries the temporal analysis.
- E2 outperforms E4 on Recall@5/nDCG@5. This is unexplained and not yet investigated.

### 3.3 TriviaQA (static control, n=100)

| | EM | F1 | Recall@5 | nDCG@5 |
|---|---:|---:|---:|---:|
| E1 BM25 | 0.530 | 0.676 | 0.808 | 0.830 |
| E2 Contriever | 0.550 | 0.693 | 0.836 | 0.928 |
| E3 Hybrid RRF | 0.530 | 0.681 | 0.816 | 0.860 |
| E4 Hybrid + Reranker | 0.540 | 0.680 | 0.842 | 0.932 |

Retrieval metrics are averaged over 85/100 queries with at least one relevant candidate. No pairwise EM/F1 difference is significant (all p >= 0.15). E2 and E4 significantly beat E1 and E3 on Recall@5/nDCG@5, and E2 beats E3.

An earlier version of this project reported identical, saturated Recall@5/nDCG@5 across all systems. That was mostly caused by a substring-matching bug in relevance labelling, which is now fixed with word-boundary matching. TriviaQA's answer-first construction still raises absolute retrieval levels.

## 4. What Gate A fixed (StreamingQA)

| Gate A item | Change | Outcome |
|---|---|---|
| A1 gold evidence | Article-level `evidence_id` is expanded to all passages; every passage that matches the gold answer/aliases (using the evaluator's `normalize_answer()`) is marked gold. Passage 0 is no longer assumed gold. | 97/100 queries have validated gold chunks (3 unvalidated, manual inspection open) |
| A2 one evidence unit | Passages are chunked to 320 reranker-tokens with 64-token overlap, used by all four systems | Max chunk 320 tokens (avg 171.6); 5 of 2,051 chunks exceed the 1500-character generator cap (max overshoot 20 characters among retrieved chunks) |
| A3 rerun | E1-E4 rerun on the corrected, chunked pool | Table 3.1 |
| A4 statistics | Bootstrap CIs, paired tests, Holm-Bonferroni | `logs/statistics_results_streamingqa.json` |
| A5 config as source of truth | All four drivers read parameters from `configs/streamingqa_eval_config.yaml`; a missing key raises an error | E1 smoke test byte-identical to the pre-A5 run. E2-E4 import-tested only |

Chunking applies to StreamingQA only. The shared retrieval/generation modules (`bm25.py`, `dense.py`, `hybrid.py`, `reranker.py`, `generate.py`) are unchanged, so TriviaQA and FreshQA behaviour is unaffected.

## 5. Status

| Item | Status |
|---|---|
| Week 3 | Complete |
| Week 4 Gate A (items 1-5) | Complete |
| A1: manual inspection of the 3 unvalidated queries | Open (2020 shards being re-fetched) |
| B-6 README | This document; update after final numbers are committed |
| B-7 pin environment | In progress (see Section 6) |
| B-8 tracked artifacts / filenames | In progress: untrack `__pycache__`/`.pyc`, standardise FreshQA reranker log name |
| B-9 FreshQA judge validation | Not started (100+ blind human judgments and/or a second judge) |
| B-10 frozen summary artifact | Partial: `results/summary.csv` covers StreamingQA only |
| StreamingQA E2-E4 config-driven smoke tests | Open |
| Scale TriviaQA/StreamingQA beyond n=100 | Planned before paper-level evaluation |
| Failure analysis (50-100 errors) | Partial |

## 6. Environments

Two environments produced the frozen results. Reproduce each stage in the environment listed for it.

| Stage | Environment | Package files |
|---|---|---|
| Retrieval, generation, E1-E4 runs | Kaggle, Python 3.12.13, torch 2.10.0 (CUDA 12.8), Tesla T4 | `requirements.txt`, `requirements.lock.txt` |
| Paired statistics, summary generation, tests | Local Windows machine, Python `<3.13.x: FILL IN>`, numpy 2.4.6, pandas 3.0.5, scipy 1.18.0 | `requirements.local.txt`, `requirements.local.lock.txt` |

Kaggle versions were recorded on `<DATE>` from the Kaggle image and may differ slightly from the image at the time of the earliest runs.

Model revisions (commit SHAs) are recorded in the config files under `revision:` for the generator, Contriever and the reranker. `<TODO: fill in>`

Local setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.local.txt
python -m pytest
```

## 7. Reproducing the frozen StreamingQA baseline

Steps that need a GPU (`run_*`) run on Kaggle. Steps after them run locally. Script paths follow the repository layout; adjust if yours differ.

```bash
# 1. Snapshot (seeded n=100)
python save_snapshot.py

# 2. Build candidate pools from the WMT news archive (13 yearly gzip shards; large download)
python build_streamingqa_pools.py

# 3. Freeze the evidence unit: chunk pools and validate gold chunks (Gate A 1-2)
python src/eval/chunk_streamingqa_pools.py

# 4. Check chunking uniformity across the run logs
python verify_chunking_a3.py

# 5. Clean baselines E1-E4 (Kaggle GPU). Parameters come from configs/streamingqa_eval_config.yaml
python scripts/run_baseline_streamingqa.py          # E1 BM25
python scripts/run_dense_streamingqa.py             # E2 Contriever
python scripts/run_hybrid_streamingqa.py            # E3 Hybrid RRF
python scripts/run_hybrid_reranker_streamingqa.py   # E4 Hybrid + reranker

# 6. Paired statistics with Holm-Bonferroni (local)
python scripts/run_statistics_streamingqa.py

# 7. Summary table (local): results/summary.csv
python scripts/build_summary_csv.py
```

Reproducing TriviaQA and FreshQA:

```bash
# FreshQA (full TEST split)
python preprocess.py --split TEST
python fetch_freshqa_sources.py          # evidence snapshot (committed)
python build_freshqa_pools.py            # regenerate pools; not tracked (about 646 MB), deterministic with seed=42
# then the E1-E4 FreshQA runners  <TODO: list exact script names>

# TriviaQA
# <TODO: list exact preprocessing and E1-E4 script names>
```

Long Kaggle runs use `resumable_log.py` (skips already-completed `query_id`s on restart) and `git_checkpoint.py` (periodic commit and push), because a full 477-question FreshQA run was once lost to an unsaved session.

## 8. Evaluation

One code path serves all datasets: `src/eval/evaluator.py` (`evaluate_query`, `aggregate_metrics`, `aggregate_metrics_by_group`) and `src/eval/metrics.py`.

- **QA:** EM, F1 (SQuAD-style normalisation). FreshQA also uses a FreshEval-style LLM judge.
- **Retrieval:** Recall@5, nDCG@5, valid-evidence Recall@5. Undefined values (no relevant candidate) are excluded from averages and never coerced to 0. `n_defined` is reported alongside.
- **Temporal (need `question_ts`, return `None` otherwise):** fraction of top-k violating the query-time constraint, valid-evidence Recall@k, time-valid answer accuracy.
- **Statistics:** 95% bootstrap CIs, paired bootstrap, exact McNemar for binary metrics, Wilcoxon as a secondary check, Holm-Bonferroni across comparisons.

Known limitation: the generator caps each passage at 1500 characters, while StreamingQA chunks are sized in reranker tokens. This affects 5 of 2,051 chunks by at most a few hundred characters and is documented rather than corrected.

## 9. Repository layout

```
PROJECT_ROOT/
│
├── configs/
│   ├── baseline_config.yaml
│   ├── freshqa_config.yaml
│   ├── streamingqa_config.yaml
│   └── streamingqa_eval_config.yaml
│
├── data/
│   ├── processed/
│   │   ├── freshqa_control_pools.jsonl
│   │   ├── freshqa_questions.jsonl
│   │   ├── streamingqa_control_pools.jsonl
│   │   ├── streamingqa_control_pools_chunked.jsonl
│   │   └── triviaqa_control_clean.jsonl
│   │
│   └── raw/
│       ├── freshqa.csv
│       ├── freshqa_clean.csv
│       ├── freshqa_evidence_snapshot.jsonl
│       ├── streamingqa_control_sample.jsonl
│       ├── streamingqa_eval.jsonl.gz
│       ├── streamingqa_pools_raw.jsonl
│       ├── triviaqa_control_sample.jsonl
│       ├── wmt_sorting_key_ids.txt.gz
│       └── wmt/
│
├── logs/
│   ├── baseline_run.jsonl
│   ├── dense_run.jsonl
│   ├── hybrid_run.jsonl
│   ├── hybrid_reranker_run.jsonl
│   ├── freshqa_*.jsonl
│   ├── streamingqa_*.jsonl
│   └── statistics_results*.json
│
├── notebooks/
│
├── scripts/
│   ├── run_baseline.py
│   ├── run_baseline_freshqa.py
│   ├── run_baseline_streamingqa.py
│   ├── run_dense.py
│   ├── run_dense_freshqa.py
│   ├── run_dense_streamingqa.py
│   ├── run_hybrid.py
│   ├── run_hybrid_freshqa.py
│   ├── run_hybrid_reranker.py
│   ├── run_hybrid_reranker_freshqa.py
│   ├── run_hybrid_reranker_streamingqa.py
│   ├── run_hybrid_streamingqa.py
│   ├── run_statistics.py
│   └── run_statistics_streamingqa.py
│
├── src/
│   ├── attacks/
│   ├── chronoguard/
│   │
│   ├── eval/
│   │   ├── build_freshqa_pools.py
│   │   ├── build_streamingqa_pools.py
│   │   ├── chunk_streamingqa_pools.py
│   │   ├── config_loader.py
│   │   ├── evaluator.py
│   │   ├── fetch_freshqa_sources.py
│   │   ├── fetch_wmt_archives.py
│   │   ├── freshqa_judge.py
│   │   ├── inspect_data.py
│   │   ├── metrics.py
│   │   ├── preprocess.py
│   │   ├── preprocess_freshqa.py
│   │   ├── preprocess_streamingqa.py
│   │   ├── resumable_log.py
│   │   ├── save_snapshot.py
│   │   ├── save_snapshot_streamingqa.py
│   │   └── statistics.py
│   │
│   ├── generation/
│   │   └── generate.py
│   │
│   └── retrieval/
│       ├── bm25.py
│       ├── dense.py
│       ├── hybrid.py
│       └── reranker.py
│
└── tests/
    ├── conftest.py
    ├── test_evaluator.py
    ├── test_metrics.py
    └── test_retrieval.py
```

## 10. Next: Week 5

After Week 4 sign-off the clean baseline is read-only except for documented bug fixes. Week 5 constructs the attack conditions (stale amplification, fabricated-fresh evidence, future-date shift, duplicate fresh-looking poison, correct-content/wrong-date controls) and measures them across E1-E4 before designing the ChronoGuard defense.