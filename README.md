# ChronoGuard-RAG

Clean RAG baselines for a study of **freshness poisoning** in retrieval-augmented generation: how stale, fabricated-"newer", or timestamp-shifted evidence can override correct evidence, and how a recency-aware verification layer (ChronoGuard-RAG) can defend against it.

**Current phase:** Weeks 3-4 (clean baselines) are in their closure cycle. Gate A is complete apart from one manual-review item. Gate B is complete: the frozen summary (`results/summary.csv`, `results/summary.json`) was generated from the raw logs on a clean tree and committed. Still open before the freeze tag: StreamingQA E2-E4 config-driven smoke tests and the third A1 manual-review case (documentation only). No attack results and no ChronoGuard defense are part of the frozen baseline (see section 9 for the Week 5 scaffolding that is present in the repository).

**Freeze:** the git tag `week4-frozen` marks the commit that contains this README. The summary artifacts were committed in `18edada` and generated at commit `4e1fc4c` (`git_dirty: false` in `results/summary.json`).

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

All numbers below are reproduced by `scripts/make_summary.py` from the raw logs (`results/summary.json`).

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
| FreshEval accuracy, Qwen2.5-14B judge (headline) | 0.3312 | 0.4004 | 0.3920 | **0.4088** |
| FreshEval accuracy, Mistral-7B self-judge (development only) | 0.5304 | **0.5807** | 0.5597 | 0.5660 |
| EM (diagnostic) | 0.1258 | 0.1551 | 0.1488 | **0.1656** |
| F1 (diagnostic) | 0.2955 | 0.3438 | 0.3311 | **0.3510** |
| Recall@5 | 0.7977 | **0.9990** | 0.8843 | 0.9822 |
| nDCG@5 | 0.7290 | **0.9766** | 0.8249 | 0.9516 |

**Caveats.**
- The headline judged accuracy comes from Qwen2.5-14B-Instruct, chosen after validating both judges against human labels (section 3.4). The Mistral-7B self-judge is lenient (it overstated accuracy on the validation sample) and is shown for development only. Neither is **comparable to published GPT-4-judged FreshQA numbers**.
- The ordering of E2, E3 and E4 depends on the judge, and the three are within about 2 points of each other under both. Only E1 (BM25) being lowest holds under both judges. Do not rank E2-E4 by judged accuracy alone; paired tests have not yet been run on FreshQA.
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

### 3.4 FreshQA judge validation

The Mistral-7B judge also generates the answers, so it was validated against human labels and compared with a second judge. 112 clean answers were sampled (seed 42), stratified over E1-E4 and four question types (never-changing, slow-changing, fast-changing, false-premise), 28 per system and per type. They were labelled blind to every judge verdict, using the judge's own rubric. A second person labelled a 30-item subset (agreement 96.7%, kappa 0.93). Human accuracy on the sample is 0.500.

| | Agreement with human | Kappa (95% CI) | Accuracy on the sample | Lenient / strict errors | Sign-test p |
|---|---:|---:|---:|---:|---:|
| Mistral-7B (development judge) | 0.875 | 0.750 (0.63-0.87) | 0.625 | 14 / 0 | 0.0001 |
| Qwen2.5-14B-Instruct (headline judge) | 0.911 | 0.821 (0.71-0.91) | 0.482 | 4 / 6 | 0.75 |

- Mistral is systematically lenient. Qwen shows no detectable bias, but its higher agreement is not statistically distinguishable from Mistral's at n=112 (errors only Mistral makes: 10, only Qwen makes: 6, p = 0.45). The supported claim is about calibration, not agreement.
- Qwen's 10 disagreements with the human labels were reviewed: nine are judge errors and one is a borderline label. In four it overrides the gold answer with its own beliefs, and in three it reasons from the wrong current year. Its knowledge appears to end around 2023, so it can penalise correct, fresh answers. This is a validity threat and is stated as one.
- The 112-item sample was easier than average, so the human accuracy on it is not an estimate of true accuracy. The judge comparison is paired and is not affected.
- Qwen setup: `Qwen/Qwen2.5-14B-Instruct`, revision `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` (also recorded in `results/summary.json`), 4-bit NF4 with fp16 compute, greedy decoding, 300 new tokens (Mistral's limit was 80), the same FreshEval prompt and code path. All 1,908 verdicts parsed.
- Raw files are in `results/judge_validation/` (`annotation.csv`, `key.csv`, `judge2_raw.jsonl`, `judge2_all.jsonl`).

## 4. What Gate A fixed (StreamingQA)

| Gate A item | Change | Outcome |
|---|---|---|
| A1 gold evidence | Article-level `evidence_id` is expanded to all passages; every passage that matches the gold answer/aliases (using the evaluator's `normalize_answer()`) is marked gold. Passage 0 is no longer assumed gold. | 97/100 queries have validated gold chunks (3 unvalidated, manual inspection open) |
| A2 one evidence unit | Passages are chunked to 320 reranker-tokens with 64-token overlap, used by all four systems | Max chunk 320 tokens (avg 171.6); 5 of 2,051 chunks exceed the 1500-character generator cap (max overshoot 20 characters among retrieved chunks) |
| A3 rerun | E1-E4 rerun on the corrected, chunked pool | Table 3.1 |
| A4 statistics | Bootstrap CIs, paired tests, Holm-Bonferroni | `logs/statistics_results_streamingqa.json` |
| A5 config as source of truth | All four drivers read parameters from `configs/streamingqa_eval_config.yaml`; a missing key raises an error | E1 smoke test byte-identical to the pre-A5 run. E2-E4 import-tested only (config-driven smoke tests open) |

Chunking applies to StreamingQA only (TriviaQA and FreshQA are control/secondary datasets and are intentionally not rechunked). The shared retrieval/generation modules (`bm25.py`, `dense.py`, `hybrid.py`, `reranker.py`, `generate.py`) are unchanged, so TriviaQA and FreshQA behaviour is unaffected. Any later cross-dataset attack comparison must document these preprocessing differences.

## 5. Status

| Item | Status |
|---|---|
| Week 3 | Complete |
| Week 4 Gate A (items 1-5) | Complete |
| A1: manual inspection of the 3 unvalidated queries | 2 of 3 answer-bearing on manual reading (Ferne McCann, Germany); Colm O'Rourke pending. Supervisor decision: Option A (document only; frozen labels and the 97/100 basis are unchanged) |
| B-6 README | Done |
| B-7 pin environment | Done (see section 6) |
| B-8 tracked artifacts / filenames | Done |
| B-9 FreshQA judge validation | Done: 112 blind human labels, second judge on the sample and on all 1,908 verdicts (section 3.4) |
| B-10 frozen summary artifact | Done: `results/summary.csv` and `results/summary.json` (commit `18edada`, generated at `4e1fc4c`, clean tree) |
| StreamingQA E2-E4 config-driven smoke tests | Open |
| Scale TriviaQA/StreamingQA beyond n=100 | Planned before paper-level evaluation |
| Failure analysis (50-100 errors) | Partial |

## 6. Environments

Two environments produced the frozen results. Reproduce each stage in the environment listed for it.

| Stage | Environment | Package files |
|---|---|---|
| Retrieval, generation, E1-E4 runs | Kaggle, Python 3.12.13, torch 2.10.0 (CUDA 12.8), Tesla T4 | `requirements.txt` |
| Paired statistics, summary generation, tests | Local Windows machine, Python 3.13.7, numpy 2.4.6, pandas 3.0.5, scipy 1.18.0 | `requirements.local.txt`, `requirements.local.lock.txt` |

Kaggle package versions were read from the Kaggle image used for the runs and may differ slightly from the image at the time of the earliest runs. No full lock file is committed for the Kaggle environment. The second FreshQA judge (Qwen2.5-14B-Instruct) ran in the same Kaggle environment on a single T4; `bitsandbytes` had to be reinstalled in that session (`pip install -U "bitsandbytes>=0.46.1"`).

**Model revisions.** The baseline code loads the generator, Contriever and the reranker by model name (`from_pretrained(model_name)`), and no revision was pinned in the configs or recorded in the run logs. Those three models therefore ran at whatever revision the Hugging Face Hub served at run time, and their commit hashes are not recorded for the frozen baseline runs. This is a known reproducibility limitation. The only recorded revision is the second judge's:

| Model | Role | Revision |
|---|---|---|
| `mistralai/Mistral-7B-Instruct-v0.2` | Generator, development judge | Not recorded |
| `facebook/contriever` | Dense retrieval (E2-E4) | Not recorded |
| `BAAI/bge-reranker-base` | Reranker (E4) | Not recorded |
| `Qwen/Qwen2.5-14B-Instruct` | Headline FreshQA judge | `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` |

From Week 5 onward, model revisions are to be pinned explicitly in the configs.

Local setup:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.local.txt
python -m pytest
```

## 7. Reproducing the frozen baselines

Steps that need a GPU (`run_*`) were run on Kaggle. Steps after them run locally. Script paths follow the repository layout in section 9; adjust the invocation (`python path/to/script.py` or `python -m ...`) if your setup differs.

### StreamingQA (primary)

```bash
# 1. Preprocess and snapshot (seeded n=100)
python src/eval/preprocess_streamingqa.py
python src/eval/save_snapshot_streamingqa.py

# 2. Build candidate pools from the WMT news archive (13 yearly gzip shards; large download)
python src/eval/fetch_wmt_archives.py
python src/eval/build_streamingqa_pools.py

# 3. Freeze the evidence unit: chunk pools and validate gold chunks (Gate A 1-2)
python src/eval/chunk_streamingqa_pools.py

# 4. Check chunking uniformity across the run logs
python verify_chunking_a3.py

# 5. Clean baselines E1-E4 (GPU). Parameters come from configs/streamingqa_eval_config.yaml
python scripts/run_baseline_streamingqa.py          # E1 BM25
python scripts/run_dense_streamingqa.py             # E2 Contriever
python scripts/run_hybrid_streamingqa.py            # E3 Hybrid RRF
python scripts/run_hybrid_reranker_streamingqa.py   # E4 Hybrid + reranker

# 6. Paired statistics with Holm-Bonferroni (local)
python scripts/run_statistics_streamingqa.py
```

### FreshQA (full TEST split)

```bash
python src/eval/preprocess_freshqa.py
python src/eval/fetch_freshqa_sources.py     # evidence snapshot (committed)
python src/eval/build_freshqa_pools.py       # regenerate pools; not tracked (about 646 MB), deterministic with seed=42

python scripts/run_baseline_freshqa.py              # E1
python scripts/run_dense_freshqa.py                 # E2
python scripts/run_hybrid_freshqa.py                # E3
python scripts/run_hybrid_reranker_freshqa.py       # E4
```

### TriviaQA (static control)

```bash
python src/eval/preprocess.py
python src/eval/save_snapshot.py

python scripts/run_baseline.py                # E1
python scripts/run_dense.py                   # E2
python scripts/run_hybrid.py                  # E3
python scripts/run_hybrid_reranker.py         # E4
python scripts/run_statistics.py              # paired statistics (local)
```

### FreshQA judge validation (after the FreshQA E1-E4 logs exist)

```bash
python scripts/judge_validation_sample.py       # seeded, stratified sample + blind annotation sheet
# label results/judge_validation/annotation.csv by hand (1 = correct, 0 = incorrect); do not open key.csv
python scripts/judge2_run.py                    # second judge on the 112 items (GPU)
python scripts/judge_validation_agreement.py    # agreement, kappa, sign tests, breakdowns
python scripts/show_disagreements.py --judge 2  # disagreements, for the error analysis
python scripts/judge2_run.py --all              # second judge on all 1,908 verdicts (GPU)
```

### Frozen summary (local, run last, on a clean working tree)

```bash
python scripts/make_summary.py     # writes results/summary.csv and results/summary.json
```

`make_summary.py` recomputes every number from the raw logs (plus the second judge's raw verdict file) and records the git commit, a dirty-tree flag, and SHA-256 hashes of the configs, dataset snapshots and logs. Delete any previous `results/summary.*` before rerunning, because untracked files make the tree dirty. It uses `configs/streamingqa_eval_config.yaml` for StreamingQA, `configs/freshqa_config.yaml` for FreshQA and `configs/baseline_config.yaml` for TriviaQA.

Long GPU runs use `resumable_log.py` (skips already-completed `query_id`s on restart) and `git_checkpoint.py` (periodic commit and push), because a full 477-question FreshQA run was once lost to an unsaved session.

## 8. Evaluation

One code path serves all datasets: `src/eval/evaluator.py` (`evaluate_query`, `aggregate_metrics`, `aggregate_metrics_by_group`) and `src/eval/metrics.py`.

- **QA:** EM, F1 (SQuAD-style normalisation). FreshQA also uses a FreshEval-style LLM judge: Qwen2.5-14B-Instruct is the headline judge and Mistral-7B a development judge (section 3.4).
- **Retrieval:** Recall@5, nDCG@5, valid-evidence Recall@5. Undefined values (no relevant candidate) are excluded from averages and never coerced to 0. `n_defined` is reported alongside.
- **Temporal (need `question_ts`, return `None` otherwise):** fraction of top-k violating the query-time constraint, valid-evidence Recall@k, time-valid answer accuracy.
- **Statistics:** 95% bootstrap CIs, paired bootstrap, exact McNemar for binary metrics, Wilcoxon as a secondary check, Holm-Bonferroni across comparisons.

Known limitation: the generator caps each passage at 1500 characters, while StreamingQA chunks are sized in reranker tokens. This affects 5 of 2,051 chunks by at most a few hundred characters and is documented rather than corrected.

## 9. Repository layout

```
chronoguard-rag/
├── configs/
│   ├── baseline_config.yaml            # TriviaQA baseline settings
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
│           ├── news-docs.2008.en.filtered.gz
│           ├── ...
│           └── news-docs.2015.en.filtered.gz.partial
│
├── logs/
│   ├── baseline_run.jsonl              # TriviaQA E1-E4: baseline/dense/hybrid/hybrid_reranker
│   ├── dense_run.jsonl
│   ├── hybrid_run.jsonl
│   ├── hybrid_reranker_run.jsonl
│   ├── freshqa_*.jsonl
│   ├── streamingqa_*.jsonl
│   ├── statistics_results.json
│   └── statistics_results_streamingqa.json
│
├── notebooks/
│
├── results/
│   ├── summary.csv                     # frozen clean-baseline summary (from raw logs)
│   ├── summary.json
│   └── judge_validation/
│       ├── annotation.csv
│       ├── annotation_rater2.csv
│       ├── disagreements.txt
│       ├── disagreements_judge2.txt
│       ├── judge2_all.jsonl
│       ├── judge2_raw.jsonl
│       └── key.csv
│
├── scripts/
│   ├── judge2_run.py
│   ├── judge_validation_agreement.py
│   ├── judge_validation_sample.py
│   ├── make_summary.py
│   ├── run_baseline.py                 # TriviaQA E1
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
│   ├── run_statistics_streamingqa.py
│   └── show_disagreements.py
│
├── src/
│   ├── attacks/                        # Week 5 scaffolding; no results in the frozen baseline
│   ├── chronoguard/                    # reserved for the defense
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
│   ├── generation/
│   │   └── generate.py
│   └── retrieval/
│       ├── bm25.py
│       ├── dense.py
│       ├── hybrid.py
│       └── reranker.py
│
├── tests/
│   ├── conftest.py
│   ├── test_evaluator.py
│   ├── test_metrics.py
│   └── test_retrieval.py
│
├── verify_chunking_a3.py
├── requirements.txt                    # Kaggle environment
├── requirements.local.txt              # local environment
└── requirements.local.lock.txt
```

The repository also contains Week 5 attack-construction scaffolding (`src/attacks/`, `src/eval/build_streamingqa_attack_sources.py` and attack inspection scripts under `scripts/`). It is work in progress and none of it contributes to the frozen clean-baseline results above.

| Directory          | Purpose                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------- |
| `configs/`         | Experiment and dataset configuration files.                                                 |
| `data/processed/`  | Processed question pools and evaluation-ready datasets.                                     |
| `data/raw/`        | Frozen dataset snapshots and source evidence, including WMT News Crawl data.                |
| `logs/`            | Retrieval, evaluation, and statistical experiment logs.                                     |
| `notebooks/`       | Exploratory and experiment notebooks.                                                       |
| `results/`         | Frozen summary artifacts and human/judge validation outputs.                                |
| `scripts/`         | Experiment runners, validation scripts, and summary generation.                             |
| `src/attacks/`     | Attack-pool construction and attack specifications (Week 5, in development).                |
| `src/chronoguard/` | Core ChronoGuard components (not started).                                                  |
| `src/eval/`        | Dataset preparation, evidence fetching, preprocessing, evaluation, metrics, and statistics. |
| `src/generation/`  | Answer-generation components.                                                               |
| `src/retrieval/`   | BM25, dense, hybrid, and reranker retrieval implementations.                                |
| `tests/`           | Automated tests for evaluation, metrics, and retrieval, including regression tests (duplicate passage identity, RRF duplicates, truncation, undefined metrics). |

## 10. Next: Week 5

After Week 4 sign-off the clean baseline is read-only except for documented bug fixes. Week 5 constructs the attack conditions (stale amplification, fabricated-fresh evidence, future-date shift, duplicate fresh-looking poison, correct-content/wrong-date controls) and measures them across E1-E4 before designing the ChronoGuard defense. Per the supervisor review, timestamp-only attacks cannot change the current baselines' rankings or generations because none of the baseline components consume timestamp metadata; they are treated as negative controls and as ChronoGuard attacks, or evaluated under a separate date-visible representation.