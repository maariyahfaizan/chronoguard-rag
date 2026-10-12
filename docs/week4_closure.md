# Week 4 Closure Note: ChronoGuard-RAG

**Student:** Maariyah Anjum Faizan
**Date:** `<FILL: date of closure>`
**Scope:** Clean baselines E1-E4 on StreamingQA (primary), FreshQA and TriviaQA (secondary / control)

## 1. Freeze record

| Item | Value |
|---|---|
| Freeze tag | `week4-frozen` |
| Freeze commit | `d995f832c6ab81aea9c9fe8da993e1fe8a138914` |
| Summary commit | `18edada` ("Week 4: final summary artifacts") |
| Summary generated at commit | `4e1fc4c` (`git_dirty: false`, `partial_run: false`) |
| `results/summary.csv` SHA-256 | `C2F67D284EDF945B51EE5C5F33477376B4E03D5580571ED1C1FD5986895DE0FE` |
| `results/summary.json` SHA-256 | `96F8686F220FFE40B69CD9AB36BEFA49D87D0EB616A2E01FD67572ACEC8A9823` |
| Local environment | Python 3.13.7; numpy 2.4.6, pandas 3.0.5, scipy 1.18.0 (`requirements.local.txt`, `requirements.local.lock.txt`) |

The summary was computed by `scripts/make_summary.py` from the raw per-query logs only. Config, dataset-snapshot and log SHA-256 hashes are recorded per row in `results/summary.json`.

## 2. Dataset snapshots

| Dataset | Snapshot / pool | Size | Config used by the summary |
|---|---|---|---|
| StreamingQA | `data/processed/streamingqa_control_pools_chunked.jsonl` (chunked 320 BGE-reranker tokens, 64 overlap) | 100 queries; 97/100 with validated gold chunks | `configs/streamingqa_eval_config.yaml` |
| FreshQA | `data/raw/freshqa.csv`, `freshqa_clean.csv`, `freshqa_evidence_snapshot.jsonl` | 477 TEST questions | `configs/freshqa_config.yaml` |
| TriviaQA | `data/processed/triviaqa_control_clean.jsonl` | 100 queries (seed 42) | `configs/baseline_config.yaml` |

Snapshot file hashes are in `results/summary.json` under `snapshot_sha256`. Chunking scope is StreamingQA only (supervisor-approved); TriviaQA and FreshQA are intentionally not rechunked, and any later cross-dataset attack comparison must document the preprocessing differences.

## 3. Final clean-baseline decision

**StreamingQA clean reference (post-Gate-A, chunked pool):**

| System | EM | F1 | Recall@5 | nDCG@5 | TVAA |
|---|---:|---:|---:|---:|---:|
| E1 BM25 | 0.620 | 0.781 | 0.930 | 0.926 | 0.55 |
| E2 Contriever | 0.610 | 0.782 | 0.982 | 0.992 | 0.53 |
| E3 Hybrid RRF | 0.590 | 0.770 | 0.946 | 0.952 | 0.51 |
| E4 Hybrid + Reranker | 0.590 | 0.776 | 0.982 | 0.977 | 0.53 |

These values were verified against `results/summary.json`.

**Supported claims**
- Retrieval level only: Contriever (E2) has a robust advantage over BM25 (E1) on Recall@5, nDCG@5 and valid-evidence Recall@5, surviving Holm-Bonferroni correction.
- No generation-level claim (EM, F1, TVAA) is made from the n=100 clean StreamingQA data; those differences do not survive correction.

**FreshQA judging:** the headline judge is Qwen2.5-14B-Instruct (revision `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8`), validated against blind human labels (112 items) with a second judge comparison; Mistral-7B is development-only. Reported validity threats: Qwen's knowledge cutoff (it can penalise correct fresh answers) and the sample being easier than average. A stronger commercial judge is not a Week 6 blocker.

## 4. Week 4 freeze items (W4-F1 to W4-F6)

| ID | Item | Status | Evidence |
|---|---|---|---|
| W4-F1 | E2, E3, E4 config-driven smoke tests | `OPEN` | `DONE` |
| W4-F2 | Third A1 manual-review case (Colm O'Rourke), Option A | WAIVED by supervisor | `DONE` |
| W4-F3 | `make_summary.py` on a clean tree; summary committed for all three datasets | DONE | Commit `18edada` |
| W4-F4 | README complete (placeholders removed, environment, reproduction commands, status) | DONE | `README.md` |
| W4-F5 | Freeze commit and tag `week4-frozen` | DONE | Section 1 (commit `d995f83`, tag pushed to origin) |
| W4-F6 | This closure note | DONE once committed | `docs/week4_closure.md` |

**A1 manual review (Option A, document only):** Ferne McCann and Germany were judged answer-bearing on manual reading. Colm O'Rourke: not reviewed (waived by the supervisor). Frozen labels are not altered and the 97/100 lexically validated basis is unchanged; no E1-E4 rerun was performed.

## 5. Known limitations carried forward

- StreamingQA and TriviaQA clean baselines are n=100 (dev-scale), not yet the 300-500+ scale intended for paper numbers.
- Model revisions for the generator (Mistral-7B-Instruct-v0.2), Contriever and the BGE reranker were not pinned in the configs or recorded in the run logs; only the Qwen judge revision is recorded. Revisions are to be pinned explicitly from Week 5.
- No full lock file is committed for the Kaggle environment (`requirements.txt` only).
- FreshQA temporal metrics are defined for only a small subset of questions (sparse `source_date`); StreamingQA carries the temporal analysis.
- FreshQA E2-E4 judged-accuracy ordering depends on the judge; paired tests on FreshQA have not been run. E2 outperforming E4 on FreshQA Recall@5/nDCG@5 is unexplained.
- Judge validity threats as described in the README (section 3.4).

## 6. Open items carried to Week 5

- Week 5 corrections W5-1 to W5-7 (stale source/target no-op, duplicate-fresh target selection, tests for all five attacks, committed or reproducible poison payloads, poison counts 1/2/5, stricter stale eligibility, saved attack validation report).
- Redefinition of the timestamp-only attacks (future date, wrong date) as metadata negative controls / ChronoGuard attacks, or as a separate date-visible baseline.
- Three-question development pilot across E1-E4 and a preliminary vulnerability matrix, before touching the held-out benchmark.
- ChronoGuard defense work has not started, as required.