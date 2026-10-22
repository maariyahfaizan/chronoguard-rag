# Week 4 Post-Freeze Validation (W4-F1)

**Status:** NOT YET RUN. The script is ready; the results below are to be filled in from `results/week4_post_freeze_smoke.json`.

These E2, E3 and E4 config-driven smoke tests are **post-freeze validation**. They do not change the frozen Week-4 baseline:
- the `week4-frozen` tag (annotated tag `f26a389` → commit `d995f83`) is not moved or recreated;
- no frozen config, log or result is edited;
- no Week-4 baseline rerun is performed.

## What is run

`python scripts/smoke_test_e2_e4_post_freeze.py` (Kaggle GPU) does the following:
- Runs E2, E3 and E4 on the first 5 queries of the frozen pool `data/processed/streamingqa_control_pools_chunked.jsonl`.
- Calls each driver without retrieval parameters, so they come from `configs/streamingqa_eval_config.yaml`.
- Loads models at the revisions in `configs/model_revisions.yaml`.
- Writes only to `logs/week4_post_freeze_smoke/` and `results/week4_post_freeze_smoke.json`.

**Pass criteria (per system):**
- every query is logged;
- logged `top_k` / `candidate_top_k` / `fused_top_k` / `final_top_k` / `rrf_k` / `reranker` equal the YAML;
- each query retrieves exactly the configured number of passages.

**Reported, not pass criteria:** whether retrieved indices and answers equal the frozen Week-4 logs for the same queries. The frozen runs did not record model revisions, so a difference is not a failure.

## Results

| System | Pass | Same retrieval as frozen (of 5) | Same answer as frozen (of 5) |
|---|---|---|---|
| E2 | pending | pending | pending |
| E3 | pending | pending | pending |
| E4 | pending | pending | pending |

Run commit: pending. Report sha256: pending.
