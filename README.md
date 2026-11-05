# ChronoGuard-RAG

Clean RAG baselines for a study of freshness poisoning in retrieval-augmented generation: how stale, fabricated-"newer", or timestamp-shifted evidence can override correct evidence, and how a recency-aware verification layer (ChronoGuard-RAG) can defend against it.

**Current phase (5 November 2026): Week 6 pre-execution scientific review and engineering integration.** The frozen Week 3–4 clean baselines and corrected Week 5 development-only pilot remain the historical reference. A supervisor-correction engineering package was published on `master` at [`d371020`](https://github.com/maariyahfaizan/chronoguard-rag/commit/d371020e6a9dd91edb0fd2114e9dbe34c5e25c76). This publication does **not** validate the provisional Week 6 benchmark, resolve the **14 UNRECORDED supervisor decisions**, or authorize the main attacks. Independent evidence adjudication, judge validation, protocol freeze and execution authorization are outstanding. The 300 provisional priority candidates are **not** an approved benchmark. See [Supervisor review and decision documents](#11-supervisor-corrections-and-review-checkpoint).

**Research timeline:** Week 5: attack construction, development pilot and initial attack evaluation. Week 6: benchmark validation, main attack experiments and attack analysis. Week 7: ChronoGuard implementation and initial defense evaluation. Week 8: defense experiments, ablations, robustness and comparative evaluation. Defense completion is not a Week 6 exit criterion. Reconstructed evidence does not establish authenticated historical-source equivalence.

**Freeze:** the git tag `week4-frozen` marks the Week 4 freeze commit for the clean baselines and has not been moved. This README has been updated for Week 5 after that tag, so the README at the tag differs from this one. The summary artifacts were committed in `18edada` and generated at commit `4e1fc4c` (`git_dirty: false` in `results/summary.json`).

## 1. Datasets and roles

| **Dataset** | **Role**                          | **Sample**                                       | **Notes**                                                                      |
| ----------- | --------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------ |
| StreamingQA | Primary time-sensitive benchmark  | Seeded n=100 (seed=42) from the eval subset      | Per-document timestamps by construction; official clean reference after Gate A |
| FreshQA     | Current / fast-changing knowledge | Full TEST split, 477 of 500 questions            | Temporal metrics mostly undefined (sparse evidence dates)                      |
| TriviaQA    | Static, non-temporal control      | Seeded n=100 (seed=42) from the validation split | Answer-first evidence construction inflates absolute retrieval metrics         |

StreamingQA and TriviaQA at n=100 are dev-scale, pipeline-validated samples. They are not yet at the 300-500+ scale intended for paper numbers.

## 2. Systems under test

All four share one generator, one prompt template and one evaluation path, so retrieval is the only variable.

| **ID** | **Retrieval**                                                      |
| ------ | ------------------------------------------------------------------ |
| E1     | BM25                                                               |
| E2     | Dense bi-encoder (Contriever)                                      |
| E3     | Hybrid RRF (BM25 + Contriever, RRF-k=60)                           |
| E4     | Hybrid RRF + BGE cross-encoder reranker (`BAAI/bge-reranker-base`) |

Generator: `mistralai/Mistral-7B-Instruct-v0.2`, 4-bit, greedy decoding (`do_sample=False`). Final context: top-k = 5, from a 20-candidate pool. The generator configuration and the E1-E4 drivers are frozen and were not changed for Week 5.

## 3. Results

All numbers below are reproduced by `scripts/make_summary.py` from the raw logs (`results/summary.json`).

### 3.1 StreamingQA (official clean reference, post-Gate-A)

n=100, Recall\@5 / nDCG\@5 / valid-evidence Recall\@5 defined on 97/100 queries.

|                      | **EM** | **F1** | **Recall\@5** | **nDCG\@5** | **Frac. top-5 violating** | **TVAA** |
| -------------------- | ------ | ------ | ------------- | ----------- | ------------------------- | -------- |
| E1 BM25              | 0.620  | 0.781  | 0.930         | 0.926       | 0.026                     | 0.55     |
| E2 Contriever        | 0.610  | 0.782  | 0.982         | 0.992       | 0.036                     | 0.53     |
| E3 Hybrid RRF        | 0.590  | 0.770  | 0.946         | 0.952       | 0.032                     | 0.51     |
| E4 Hybrid + Reranker | 0.590  | 0.776  | 0.982         | 0.977       | 0.024                     | 0.53     |

TVAA = time-valid answer accuracy. The pre-Gate-A run used a different gold mapping and an unchunked pool (74/100 queries with defined retrieval metrics), so its numbers are not comparable with this table. They are retained in `configs/streamingqa_eval_config.yaml` for audit only.

**Paired statistics** (Holm-Bonferroni, 10,000 bootstrap resamples). Correction was applied within each metric (6 pairwise comparisons) and, as a sensitivity check, across all 42 comparisons.

- Robust across both corrections: E2 beats E1 on Recall\@5, nDCG\@5 and valid-evidence Recall\@5. E1 vs E3 and E2 vs E3 differ on nDCG\@5.
- No EM, F1, TVAA or violation-rate difference survives correction (all-metrics Holm p = 1.0). At n=100 no generation-level claim is supported.
- E4 is not distinguishable from E2 on any checked metric.

### 3.2 FreshQA (full 477, final configuration)

| **Metric**                                                   | **E1** | **E2** | **E3** | **E4** |
| ------------------------------------------------------------ | ------ | ------ | ------ | ------ |
| FreshEval accuracy, Qwen2.5-14B judge (headline)             | 0.3312 | 0.4004 | 0.3920 | 0.4088 |
| FreshEval accuracy, Mistral-7B self-judge (development only) | 0.5304 | 0.5807 | 0.5597 | 0.5660 |
| EM (diagnostic)                                              | 0.1258 | 0.1551 | 0.1488 | 0.1656 |
| F1 (diagnostic)                                              | 0.2955 | 0.3438 | 0.3311 | 0.3510 |
| Recall\@5                                                    | 0.7977 | 0.9990 | 0.8843 | 0.9822 |
| nDCG\@5                                                      | 0.7290 | 0.9766 | 0.8249 | 0.9516 |

**Caveats.**

- The headline judged accuracy comes from Qwen2.5-14B-Instruct, chosen after validating both judges against human labels (section 3.4). The Mistral-7B self-judge is lenient (it overstated accuracy on the validation sample) and is shown for development only. Neither is comparable to published GPT-4-judged FreshQA numbers.
- The ordering of E2, E3 and E4 depends on the judge, and the three are within about 2 points of each other under both. Only E1 (BM25) being lowest holds under both judges. Do not rank E2-E4 by judged accuracy alone; paired tests have not yet been run on FreshQA.
- Time-valid answer accuracy is undefined for all 477 questions. Fraction-violating (42-88 questions) and valid-evidence Recall\@5 (15 questions) are defined for only a small subset, because per-passage `source_date` coverage is sparse. Any FreshQA temporal average must be read with its `n_defined`. StreamingQA carries the temporal analysis.
- E2 outperforms E4 on Recall\@5/nDCG\@5. This is unexplained and not yet investigated.

### 3.3 TriviaQA (static control, n=100)

|                      | **EM** | **F1** | **Recall\@5** | **nDCG\@5** |
| -------------------- | ------ | ------ | ------------- | ----------- |
| E1 BM25              | 0.530  | 0.676  | 0.808         | 0.830       |
| E2 Contriever        | 0.550  | 0.693  | 0.836         | 0.928       |
| E3 Hybrid RRF        | 0.530  | 0.681  | 0.816         | 0.860       |
| E4 Hybrid + Reranker | 0.540  | 0.680  | 0.842         | 0.932       |

Retrieval metrics are averaged over 85/100 queries with at least one relevant candidate. No pairwise EM/F1 difference is significant (all p >= 0.15). E2 and E4 significantly beat E1 and E3 on Recall\@5/nDCG\@5, and E2 beats E3.

An earlier version of this project reported identical, saturated Recall\@5/nDCG\@5 across all systems. That was mostly caused by a substring-matching bug in relevance labelling, which is now fixed with word-boundary matching. TriviaQA's answer-first construction still raises absolute retrieval levels.

### 3.4 FreshQA judge validation

The Mistral-7B judge also generates the answers, so it was validated against human labels and compared with a second judge. 112 clean answers were sampled (seed 42), stratified over E1-E4 and four question types (never-changing, slow-changing, fast-changing, false-premise), 28 per system and per type. They were labelled blind to every judge verdict, using the judge's own rubric. A second person labelled a 30-item subset (agreement 96.7%, kappa 0.93). Human accuracy on the sample is 0.500.

| **Judge**                             | **Agreement with human** | **Kappa (95% CI)** | **Accuracy on the sample** | **Lenient / strict errors** | **Sign-test p** |
| ------------------------------------- | ------------------------ | ------------------ | -------------------------- | --------------------------- | --------------- |
| Mistral-7B (development judge)        | 0.875                    | 0.750 (0.63-0.87)  | 0.625                      | 14 / 0                      | 0.0001          |
| Qwen2.5-14B-Instruct (headline judge) | 0.911                    | 0.821 (0.71-0.91)  | 0.482                      | 4 / 6                       | 0.75            |

- Mistral is systematically lenient. Qwen shows no detectable bias, but its higher agreement is not statistically distinguishable from Mistral's at n=112 (errors only Mistral makes: 10, only Qwen makes: 6, p = 0.45). The supported claim is about calibration, not agreement.
- Qwen's 10 disagreements with the human labels were reviewed: nine are judge errors and one is a borderline label. In four it overrides the gold answer with its own beliefs, and in three it reasons from the wrong current year. Its knowledge appears to end around 2023, so it can penalise correct, fresh answers. This is a validity threat and is stated as one.
- The 112-item sample was easier than average, so the human accuracy on it is not an estimate of true accuracy. The judge comparison is paired and is not affected.
- Qwen setup: `Qwen/Qwen2.5-14B-Instruct`, revision `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` (also recorded in `results/summary.json`), 4-bit NF4 with fp16 compute, greedy decoding, 300 new tokens (Mistral's limit was 80), the same FreshEval prompt and code path. All 1,908 verdicts parsed.
- Raw files are in `results/judge_validation/` (`annotation.csv`, `key.csv`, `judge2_raw.jsonl`, `judge2_all.jsonl`).

## 4. What Gate A fixed (StreamingQA)

| **Gate A item**              | **Change**                                                                                                                                                                                                    | **Outcome**                                                                                                                                      |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| A1 gold evidence             | Article-level `evidence_id` is expanded to all passages; every passage that matches the gold answer/aliases (using the evaluator's `normalize_answer()`) is marked gold. Passage 0 is no longer assumed gold. | 97/100 queries have validated gold chunks (3 unvalidated, manual inspection open)                                                                |
| A2 one evidence unit         | Passages are chunked to 320 reranker-tokens with 64-token overlap, used by all four systems                                                                                                                   | Max chunk 320 tokens (avg 171.6); 5 of 2,051 chunks exceed the 1500-character generator cap (max overshoot 20 characters among retrieved chunks) |
| A3 rerun                     | E1-E4 rerun on the corrected, chunked pool                                                                                                                                                                    | Table 3.1                                                                                                                                        |
| A4 statistics                | Bootstrap CIs, paired tests, Holm-Bonferroni                                                                                                                                                                  | `logs/statistics_results_streamingqa.json`                                                                                                       |
| A5 config as source of truth | All four drivers read parameters from `configs/streamingqa_eval_config.yaml`; a missing key raises an error                                                                                                   | E1 smoke test byte-identical to the pre-A5 run. E2-E4 import-tested only (config-driven smoke tests open)                                        |

Chunking applies to StreamingQA only (TriviaQA and FreshQA are control/secondary datasets and are intentionally not rechunked). The shared retrieval/generation modules (`bm25.py`, `dense.py`, `hybrid.py`, `reranker.py`, `generate.py`) are unchanged, so TriviaQA and FreshQA behaviour is unaffected. Any later cross-dataset attack comparison must document these preprocessing differences.

## 5. Status

| **Item**                                                             | **Status**                                                                                                                                                                              |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Week 3                                                               | Complete                                                                                                                                                                                |
| Week 4 Gate A (items 1-5)                                            | Complete                                                                                                                                                                                |
| A1: manual inspection of the 3 unvalidated queries                   | 2 of 3 answer-bearing on manual reading (Ferne McCann, Germany); Colm O'Rourke pending. Supervisor decision: Option A (document only; frozen labels and the 97/100 basis are unchanged) |
| B-6 README                                                           | Updated through 5 November 2026; see sections 10–12                                                                                                                                               |
| B-7 pin environment                                                  | Done (see section 6)                                                                                                                                                                    |
| B-8 tracked artifacts / filenames                                    | Done                                                                                                                                                                                    |
| B-9 FreshQA judge validation                                         | Done: 112 blind human labels, second judge on the sample and on all 1,908 verdicts (section 3.4)                                                                                        |
| B-10 frozen summary artifact                                         | Done: `results/summary.csv` and `results/summary.json` (commit `18edada`, generated at `4e1fc4c`, clean tree)                                                                           |
| StreamingQA E2-E4 config-driven smoke tests                          | Completed post-freeze; limitations in `docs/week4_post_freeze_validation.md`                                                                                                            |
| Scale TriviaQA/StreamingQA beyond n=100                              | Planned before paper-level evaluation                                                                                                                                                   |
| Failure analysis (50-100 errors)                                     | Partial                                                                                                                                                                                 |
| Week 5 attack validation (tests, validator, saved integrity reports) | Done (section 10)                                                                                                                                                                       |
| Week 5 development pilot (3 questions, E1-E4)                        | Scientifically closable as development-only; stale evidence ineligible; dirty-tree limitation (section 10)                                                                              |
| Week 6 validation and main attacks                                   | Engineering package published; 14 decisions UNRECORDED, independent evidence/judge validation and main attacks outstanding                                                                                 |
| Weeks 7-8 ChronoGuard defense                                        | Implementation and evaluation pending; separate from Week 6 completion                                                                                                                  |

## 6. Environments

Two environments produced the frozen results. Reproduce each stage in the environment listed for it.

| **Stage**                                                                                       | **Environment**                                                               | **Package files**                                       |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------- |
| Retrieval, generation, E1-E4 runs (including the Week 5 pilot runs)                             | Kaggle, Python 3.12.13, torch 2.10.0 (CUDA 12.8), Tesla T4                    | `requirements.txt`                                      |
| Paired statistics, summary generation, tests, pilot pool building, checking and post-processing | Local Windows machine, Python 3.13.7, numpy 2.4.6, pandas 3.0.5, scipy 1.18.0 | `requirements.local.txt`, `requirements.local.lock.txt` |

Kaggle package versions were read from the Kaggle image used for the runs and may differ slightly from the image at the time of the earliest runs. No full lock file is committed for the Kaggle environment. The second FreshQA judge (Qwen2.5-14B-Instruct) ran in the same Kaggle environment on a single T4; `bitsandbytes` had to be reinstalled in that session (`pip install -U "bitsandbytes>=0.46.1"`).

The local environment does not include `torch`. The E1-E4 drivers must therefore run on Kaggle (they also open input files with the platform default encoding, so they should not be run on Windows).

**Model revisions.** The baseline code loads the generator, Contriever and the reranker by model name (`from_pretrained(model_name)`), and no revision was pinned in the configs or recorded in the run logs. Those three models therefore ran at whatever revision the Hugging Face Hub served at run time, and their commit hashes are not recorded for the frozen baseline runs. This is a known reproducibility limitation. The Week 5 pilot runs inherit it: revisions were still unpinned when the pilot was run. The only recorded revision is the second judge's:

| **Model**                            | **Role**                     | **Revision**                               |
| ------------------------------------ | ---------------------------- | ------------------------------------------ |
| `mistralai/Mistral-7B-Instruct-v0.2` | Generator, development judge | Not recorded                               |
| `facebook/contriever`                | Dense retrieval (E2-E4)      | Not recorded                               |
| `BAAI/bge-reranker-base`             | Reranker (E4)                | Not recorded                               |
| `Qwen/Qwen2.5-14B-Instruct`          | Headline FreshQA judge       | `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` |

A subsequent engineering configuration pins model revisions in `configs/model_revisions.yaml` (reported verified 2026-10-21). These pins **do not retroactively establish the model revisions used in the frozen baseline or earlier pilot runs**. The Week 6 protocol still requires supervisor decisions and approval before it can be frozen.

Local setup:

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.local.txt
python -m pytest tests/test_metrics.py
```

## 7. Reproducing the frozen baselines

Steps that need a GPU (`run_*`) were run on Kaggle. Steps after them run locally. Script paths follow the repository layout in section 9; adjust the invocation (`python path/to/script.py` or `python -m ...`) if your setup differs.

### StreamingQA (primary)

```
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

```
python src/eval/preprocess_freshqa.py
python src/eval/fetch_freshqa_sources.py     # evidence snapshot (committed)
python src/eval/build_freshqa_pools.py       # regenerate pools; not tracked (about 646 MB), deterministic with seed=42

python scripts/run_baseline_freshqa.py              # E1
python scripts/run_dense_freshqa.py                 # E2
python scripts/run_hybrid_freshqa.py                # E3
python scripts/run_hybrid_reranker_freshqa.py       # E4
```

### TriviaQA (static control)

```
python src/eval/preprocess.py
python src/eval/save_snapshot.py

python scripts/run_baseline.py                # E1
python scripts/run_dense.py                   # E2
python scripts/run_hybrid.py                  # E3
python scripts/run_hybrid_reranker.py         # E4
python scripts/run_statistics.py              # paired statistics (local)
```

### FreshQA judge validation (after the FreshQA E1-E4 logs exist)

```
python scripts/judge_validation_sample.py       # seeded, stratified sample + blind annotation sheet
# label results/judge_validation/annotation.csv by hand (1 = correct, 0 = incorrect); do not open key.csv
python scripts/judge2_run.py                    # second judge on the 112 items (GPU)
python scripts/judge_validation_agreement.py    # agreement, kappa, sign tests, breakdowns
python scripts/show_disagreements.py --judge 2  # disagreements, for the error analysis
python scripts/judge2_run.py --all              # second judge on all 1,908 verdicts (GPU)
```

### Frozen summary (local, run last, on a clean working tree)

```
python scripts/make_summary.py     # writes results/summary.csv and results/summary.json
```

`make_summary.py` recomputes every number from the raw logs (plus the second judge's raw verdict file) and records the git commit, a dirty-tree flag, and SHA-256 hashes of the configs, dataset snapshots and logs. Delete any previous `results/summary.*` before rerunning, because untracked files make the tree dirty. It uses `configs/streamingqa_eval_config.yaml` for StreamingQA, `configs/freshqa_config.yaml` for FreshQA and `configs/baseline_config.yaml` for TriviaQA.

Long GPU runs use `resumable_log.py` (skips already-completed `query_id`s on restart) and `git_checkpoint.py` (periodic commit and push), because a full 477-question FreshQA run was once lost to an unsaved session.

### Week 5 development pilot (attacks, 3 questions)

Run order. Steps marked local run on Windows; the Kaggle step needs a GPU. The attack code never modifies the clean pools or the frozen drivers.

```
# 1. Validate the attack code and payloads (local)
python -m unittest discover -s tests -p "test_attack_pool*.py"       # 47 tests
python scripts/validate_pilot_attacks.py                              # writes results/pilot_attack_validation.json

# 2. Build the attacked pilot pools: 5 conditions x poison counts 1, 2, 5 = 15 files (local)
python scripts/build_pilot_attack_pools.py                            # data/processed/attack_pools/pilot/

# 3. Check the pools; writes results/pilot_pool_check.json (local, run on a clean tree)
python scripts/check_pilot_pools.py

# 4. E1-E4 on the clean pilot file plus all 15 attacked pools = 64 runs (Kaggle, GPU)
#    In a notebook cell, from the repository root (shell commands need a leading !):
#    !python scripts/run_pilot_attacks_kaggle.py
#    Writes logs/pilot_attacks/<pool>__<E>.jsonl and run_manifest.json; skips existing logs.

# 5. Post-process and summarise (local)
python scripts/postprocess_pilot_attacks.py                           # results/pilot_attack_rows.csv (180 rows)
python scripts/summarize_pilot_attacks.py                             # results/pilot_vulnerability_summary.csv
python scripts/find_failure_cases_v2.py                               # failure-analysis categories
```

The drivers hard-code `"attack_condition": "clean"` in their logs and drop attack metadata, so post-processing joins each log row to its pool record: the log `query_id` equals the line index in the pool file, and poison slots are read from `attack_metadata.target_indices`. Document ids in the pilot pools contain `\x00\x01` control characters, which are real data, so joins use target indices, not doc ids.

## 8. Evaluation

One code path serves all datasets: `src/eval/evaluator.py` (`evaluate_query`, `aggregate_metrics`, `aggregate_metrics_by_group`) and `src/eval/metrics.py`.

- **QA:** EM, F1 (SQuAD-style normalisation). FreshQA also uses a FreshEval-style LLM judge: Qwen2.5-14B-Instruct is the headline judge and Mistral-7B a development judge (section 3.4).
- **Retrieval:** Recall\@5, nDCG\@5, valid-evidence Recall\@5. Undefined values (no relevant candidate) are excluded from averages and never coerced to 0. `n_defined` is reported alongside.
- **Temporal** (need `question_ts`, return `None` otherwise): fraction of top-k violating the query-time constraint, valid-evidence Recall\@k, time-valid answer accuracy.
- **Statistics:** 95% bootstrap CIs, paired bootstrap, exact McNemar for binary metrics, Wilcoxon as a secondary check, Holm-Bonferroni across comparisons.
- **Known limitation:** the generator caps each passage at 1500 characters, while StreamingQA chunks are sized in reranker tokens. This affects 5 of 2,051 chunks by at most a few hundred characters and is documented rather than corrected.
- **Known limitation (Week 5):** EM and F1 can mislead on attacked answers. EM penalises phrasing (hedges, full sentences), and for one pilot question a frozen alias rewards the poisoned answer, so adopted answers can score higher F1 than correct ones. Pilot failure analysis therefore uses manual labels (section 10).

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
│   │   ├── triviaqa_control_clean.jsonl
│   │   ├── attack_sources/             # Week 5: clean 3-question pilot file and poison payloads
│   │   └── attack_pools/pilot/         # Week 5: 15 attacked pilot pools + pilot_pools_manifest.json
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
│   ├── statistics_results_streamingqa.json
│   └── pilot_attacks/                  # Week 5: 64 pilot logs + run_manifest.json
│
├── notebooks/
│
├── results/
│   ├── summary.csv                     # frozen clean-baseline summary (from raw logs)
│   ├── summary.json
│   ├── pilot_attack_validation.json    # Week 5: real-pool attack validation
│   ├── pilot_pool_check.json           # Week 5: saved pool integrity report
│   ├── pilot_attack_rows.csv           # Week 5: per-question rows (180)
│   ├── pilot_vulnerability_summary.csv # Week 5: attack x system summary (60 rows)
│   ├── pilot_harm_review.csv           # Week 5: manual labels, EM-drop rows
│   ├── pilot_djokovic_review.csv       # Week 5: manual labels, Djokovic question
│   ├── pilot_stale_review.json         # Week 5: stale-candidate review record
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
│   ├── show_disagreements.py
│   │
│   │   # Week 5 pilot (attack validation, pools, runner, analysis)
│   ├── validate_pilot_attacks.py
│   ├── build_pilot_attack_pools.py
│   ├── check_pilot_pools.py
│   ├── run_pilot_attacks_kaggle.py     # Kaggle runner, E1-E4 on 16 pools
│   ├── postprocess_pilot_attacks.py
│   ├── summarize_pilot_attacks.py
│   ├── find_failure_cases.py
│   ├── find_failure_cases_v2.py
│   ├── make_harm_review.py
│   ├── save_djokovic_review.py
│   ├── save_pilot1_stale_review.py
│   └── (stale-review and small inspection helpers: build_stale_review.py, rank_stale_review.py,
│        inspect_stale_*.py, count_pilot_stale_candidates.py, show_pilot1_stale.py,
│        show_djokovic_rows.py, check_e1_q1_shift.py, check_runner_names.py,
│        compare_control_targets.py)
│
├── src/
│   ├── attacks/                        # attack_pool.py: five attacks, poison counts 1/2/5, stale review gate
│   ├── chronoguard/                    # reserved for the defense (not started)
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
│   ├── test_retrieval.py
│   ├── test_attack_pool.py                      # Week 5 attack tests
│   ├── test_attack_pool_poison_counts.py
│   ├── test_attack_pool_regressions.py
│   └── test_attack_pool_week5_additions.py
│
├── verify_chunking_a3.py
├── requirements.txt                    # Kaggle environment
├── requirements.local.txt              # local environment
└── requirements.local.lock.txt

```

| **Directory**      | **Purpose**                                                                                                                                                                                                                             |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `configs/`         | Experiment and dataset configuration files.                                                                                                                                                                                             |
| `data/processed/`  | Processed question pools and evaluation-ready datasets, plus the Week 5 attack sources and attacked pilot pools.                                                                                                                        |
| `data/raw/`        | Frozen dataset snapshots and source evidence, including WMT News Crawl data.                                                                                                                                                            |
| `logs/`            | Retrieval, evaluation, and statistical experiment logs, plus the Week 5 pilot logs.                                                                                                                                                     |
| `notebooks/`       | Exploratory and experiment notebooks.                                                                                                                                                                                                   |
| `results/`         | Frozen summary artifacts, human/judge validation outputs, and the Week 5 pilot results.                                                                                                                                                 |
| `scripts/`         | Experiment runners, validation scripts, summary generation, and Week 5 pilot scripts.                                                                                                                                                   |
| `src/attacks/`     | Attack-pool construction and attack specifications (Week 5).                                                                                                                                                                            |
| `src/chronoguard/` | Core ChronoGuard components (not started).                                                                                                                                                                                              |
| `src/eval/`        | Dataset preparation, evidence fetching, preprocessing, evaluation, metrics, and statistics.                                                                                                                                             |
| `src/generation/`  | Answer-generation components.                                                                                                                                                                                                           |
| `src/retrieval/`   | BM25, dense, hybrid, and reranker retrieval implementations.                                                                                                                                                                            |
| `tests/`           | Automated tests for evaluation, metrics, retrieval and the five attacks, including regression tests (duplicate passage identity, RRF duplicates, truncation, undefined metrics, source/target slots, poison counts, stale review gate). |

## 10. Week 5: attack development pilot

**Status: corrected pilot completed and reconciled; scientifically closable as development-only evidence.** The pilot covers three development questions (Rangers game count, countries with coronavirus in February 2020, Djokovic and the US Open). Its dirty-tree provenance limitation remains. Main Week 6 attack experiments and protocol approval are outstanding; the clean baseline above is unchanged. See `docs/week5_pilot_validation_report.md` and the [supervisor review index](https://github.com/maariyahfaizan/chronoguard-rag/blob/master/docs/supervisor_review/README.md).

**Attack conditions (5 types, poison counts 1, 2, 5)**

| **Condition**                                | **Role**                                                                    | **Pilot status**                                                                                                                      |
| -------------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `fabricated_fresh`                           | Attack: inserts a flagged synthetic passage that contradicts gold           | Run                                                                                                                                   |
| `duplicate_fresh`                            | Attack: copies one existing non-gold passage into other non-gold slots      | Run                                                                                                                                   |
| `future_date`                                | Negative control: changes only timestamps (metadata-only)                   | Run; no answer changed in any cell                                                                                                    |
| `correct_content_wrong_date` (30 days)       | Metadata perturbation, confounded: duplicates gold text with a shifted date | Run; identical to its control                                                                                                         |
| `correct_content_wrong_date` (0-day control) | Duplication-only control                                                    | Run                                                                                                                                   |
| `stale_evidence`                             | Attack: amplifies a reviewed obsolete or conflicting passage                | **Ineligible for the pilot**: no reviewed stale passage exists for the three questions. Not forced. A supervisor decision is pending. |

**Design points**

- Timestamp metadata is invisible to BM25, Contriever, the BGE reranker and Mistral, so timestamp-only conditions cannot change E1-E4 rankings or answers. They are negative controls here and become meaningful against ChronoGuard, which will consume timestamps. The optional date-visible baseline is not built.
- A stale example must be genuinely obsolete or conflicting with the gold state, or explicitly validated as answer-bearing stale evidence. Age plus word overlap is not enough. `stale_evidence_validated` can only be set through `merge_stale_reviews`, which needs a reviewer and a reason. The three in-pool pilot-1 candidates were reviewed and none is stale evidence (`results/pilot_stale_review.json`).
- Poison counts 1, 2 and 5 use unique non-gold target slots. Copy attacks amplify one source passage, which is never overwritten and never reused as a copy slot.
- Pools are built so that the only differences from the clean pilot file are the target slots. This is checked by `scripts/check_pilot_pools.py` and saved in `results/pilot_pool_check.json`.

**Integrity evidence (all saved)**

- 47 attack unit tests pass.
- Real-pool validator: 54 cases, 45 applied and passed, 9 not applied (stale_evidence), 0 failed.
- Pool integrity report: ALL OK, 15 files, 45 records, clean tree.
- Pilot run: 16 pools x 4 systems = 64 runs (192 generations) on Kaggle with the frozen Mistral configuration and frozen drivers; 64 logs, no partial files.

**What the pilot shows (n = 3, case studies only)**

- Controls behave as predicted: `future_date` changed no answer (retrieval, prompt and answer identical to clean), and the 30-day wrong-date pools match their 0-day controls.
- `fabricated_fresh` is the strongest condition. Of 14 Rangers/countries rows where EM fell from 1 to 0, 13 adopted the fake value and 1 was phrasing only. On the Djokovic question, 8 of 12 attacked rows adopted the poison.
- Poison selected but answer still correct: 5 rows (Rangers).
- Answers can change without a poison in the top 5: 7 of 9 such rows are explained by displacement of a replaced slot that was in the clean top 5; the other 2 by BM25 corpus-statistics shift (the BM25 index is built from each query's candidate list, so changing any passage shifts all scores).
- EM/F1 can mislead: for the Djokovic question a frozen alias rewards the poisoned answer (F1 up to 0.71 for an adopted answer against 0.26 for a correct one), so that question is labelled manually. Frozen labels and aliases were not changed (Option A).
- No ranking of E1-E4 or vulnerability rate is claimed.

**Open before Week 6**

- Supervisor decision on stale evidence for the pilot (accept as ineligible, require a stale case from the raw shards, or another approach).
- Supervisor decision on scoring when an alias rewards poison adoption.
- Freeze of attack definitions, eligibility rules, metrics and the development protocol (only after those decisions).
- Confirm pinned revisions for all future runs; historical frozen baseline/pilot revision provenance cannot be retroactively repaired.
- Supervisor approval for Week 6 (held-out benchmark).
## 11. Supervisor corrections and review checkpoint

**Published review checkpoint:** [`d371020e6a9dd91edb0fd2114e9dbe34c5e25c76`](https://github.com/maariyahfaizan/chronoguard-rag/commit/d371020e6a9dd91edb0fd2114e9dbe34c5e25c76) (5 November 2026), parent `de08db9712292d424e614c5e36e480ca16862128`.

The normal, non-force push to `origin/master` was verified. The commit contains **201 reviewed paths**: 199 engineering/documentation candidates, the original supervisor-review package, and root `.gitattributes`. All 200 source blobs matched their approved raw SHA-256 values at publication. This is **publication integrity**, not scientific validation.

### Review entry points

| What to read | Repository location | Interpretation |
| --- | --- | --- |
| Original submitted package | [`docs/supervisor_review/ChronoGuard_RAG_Supervisor_Review_Package.md`](docs/supervisor_review/ChronoGuard_RAG_Supervisor_Review_Package.md) | Authentic original submission; includes 15 scope questions |
| G4 v3 submission overview | [`docs/supervisor_review/g4_submission_v3/`](docs/supervisor_review/g4_submission_v3/) | Publication/review package, not execution authorization |
| Correction coverage | [`correction_coverage_matrix.csv`](docs/supervisor_review/g4_submission_v3/correction_coverage_matrix.csv) | Maps correction requirements to artifacts and evidence |
| Decision requests | [`supervisor_decision_request.md`](docs/supervisor_review/g4_submission_v3/supervisor_decision_request.md) | Supervisor decisions needed |
| Engineering checks | [`engineering_verification_summary.md`](docs/supervisor_review/g4_submission_v3/engineering_verification_summary.md) | Tested engineering claims |
| Scientific caveats | [`scientific_limitations.md`](docs/supervisor_review/g4_submission_v3/scientific_limitations.md) | Unresolved validity and approval constraints |
| Reproduction dependencies | [`reproducibility_dependencies.md`](docs/supervisor_review/g4_submission_v3/reproducibility_dependencies.md) | Inputs, environment and reproduction limitations |
| Exact publication scope | [`publication_allowlist.csv`](docs/supervisor_review/g4_submission_v3/publication_allowlist.csv) | 199 approved engineering paths |

**Not published:** the authentic 3 November supervisor-corrections DOCX (`docs/supervisor_review/source_documents/ChronoGuard_RAG_Student_Required_Corrections_03Nov2026.docx`), 25 restricted P0 audit files, one unrelated transition draft, one held FreshQA membership inventory, and ten local G4-H verifier files. These **38 untracked files** were intentionally not committed. The correction DOCX must be shared separately if the supervisor needs it; its omission is not evidence that the requirements were waived.

### Correction workstreams

| Workstream | Engineering progress | Still required |
| --- | --- | --- |
| **P0-A — Claim-specific answer judge** | Revised `src/eval/answer_judge_v2.py`, `claim_keys.py`, `claim_matching_v2.py`, protocol and tests; historical v1 preserved | Active pipeline integration; approved false-claim keys; blind human validation, confusion counts and thresholds |
| **P0-B — Evidence provenance and adjudication** | 400-ID inventory and annotation reconciliation; reconstructed candidates and quarantined unbound annotations | Authenticate historical evidence, independent dual review, adjudication, agreement and accepted benchmark IDs |
| **P0-C — Sampling and exposure** | Provisional deterministic scenarios, exposure/sampling infrastructure | Approve exclusions, recent/past eligibility, reserves, sample size and precision rationale |
| **P1-A — Matched controls** | Synthetic neutral/freshness requests, context traces and offline audits | Verify real tokenizer/model-visible context and exact matched conditions |
| **P1-B — Generator-isolated RQ3** | Synthetic 2×2×2 factorial requests and export | Authorized real-model outcomes; balance and validate visibility |
| **P1-C — Statistics and transfer** | Proposed paired/cluster-aware analysis, canonical IDs and transfer plan | Approved estimands, denominators, multiplicity, power/precision and second-model budget |

**Important distinctions:** The previously validated 112-answer FreshQA clean-answer judge comparison (section 3.4) does **not** validate the new attack-outcome judge-v2. Synthetic test passes do **not** replace independent blind validation. The original package's **15 scope questions** are distinct from the **14 currently UNRECORDED scientific decisions**.

## 12. Open decisions, scientific gates and next work

### Decisions awaiting supervisor disposition

The authoritative decision request and its decision ledger govern the exact fourteen entries. The topics below summarize the required areas; they are **not** a substitute for recording each original decision identifier:

1. Claim-key provenance, false-answer matching, ambiguity/abstention rubric and blinded judge-validation thresholds.
2. Evidence authenticity tiers, historical answer/date basis, independent reviewer assignment and adjudication.
3. Development exposure exclusions, eligible benchmark membership, recent/past strata, deterministic reserves and attack-specific denominators.
4. Neutral-versus-freshness matching, metadata-only negative controls, duplication controls and BM25-refitting interpretation.
5. RQ3's 2×2×2 generator-isolated design and visibility balancing.
6. Primary estimands, paired uncertainty, multiplicity, sample size, precision/power and transfer budget.
7. Final frozen protocol, artifact hashes and explicit authorization for the Week 6 main experiments.

Every decision needs a **dated, written disposition** (approved, revise or defer) with any conditions. **All fourteen remain UNRECORDED.**

### Pre-execution gates

| Gate | Requirement | Current disposition |
| --- | --- | --- |
| **G1 — Scientific decisions** | Written approvals/revisions of judge, benchmark, controls, estimands and thresholds | **BLOCKED** |
| **G2 — Independent evidence validation** | Authenticated/adjudicated evidence, approved false keys, accepted IDs, exclusions and reserves | **BLOCKED** |
| **G3 — Protocol freeze** | Approved configurations, matched controls, models, seeds, analysis and hashes | **BLOCKED** |
| **G4 — Execution authorization** | Read-only readiness verification and explicit permission to execute | **BLOCKED** |

The **G4-named submission and Git publication workflow** is an engineering review process, **not** satisfaction of scientific execution Gate G4.

### Remaining engineering tasks that do not require main experiments

- Connect judge-v2 to a version-selected active evaluation path while preserving frozen v1 behavior; prohibit silent fallback.
- Add fail-closed authorization checks to real runners so an unapproved Week 6 held-out/main run cannot start.
- Restrict analysis to explicitly admitted real IDs, approved claim keys and valid denominators.
- Reconcile FreshQA membership counts (**474 versus 477**) against hashed source snapshots and documented filters; do not silently replace the historical 477-question baseline table.
- Draft a feasible blind judge-validation allocation and precision/sample-size justification for supervisor approval.
- Complete synthetic tokenizer/context-trace checks and independent-review forms; real-backend validation must respect authorization boundaries.
- Prepare a **proposed**, not approved, frozen protocol and Week 7–8 defense plan.

**Stop condition:** No Week 6 main attacks, headline attack-success estimates or claims of validated temporal poisoning effects until the relevant scientific gates pass. Weeks 7–8 remain the planned defense implementation and evaluation period.

### Reproducibility notes

- The Week 4 `week4-frozen` tag and historical results remain reference artifacts; do not rewrite them to match later model pins or judge changes.
- The Week 5 pilot is development-only, n=3 case studies, and has a recorded dirty-tree limitation.
- The 400-question screening pool, 300 provisional priority candidates and reconstructed evidence are **not** an independently accepted benchmark.
- At publication, the index was empty with no tracked modifications, but 38 intentionally excluded files remained untracked. Avoid `git add .` / `git add -A` when preparing follow-up commits.
- Any new work should be committed as a separately reviewed follow-up; `d371020e...` is the stable supervisor-review checkpoint.
