# Week 5 Development Pilot: Validation Report (protocol v2)

**Student:** Maariyah Anjum Faizan
**Date:** 2026-10-21
**Status:** the corrected pools are built and validated. The E1-E4 rerun on the corrected pools has **not** been run yet (it needs a Kaggle GPU). Sections 7-8 list what is still pending.

> **Scope.** The pilot has three questions. It is a **development case study, not a statistical benchmark**. No rate in this report or in the regenerated pilot CSVs supports a general claim. The held-out Week-6 benchmark has not been started.

This report answers supervisor items 1, 2, 3, 5 (pilot part), 8 and 9 of "Mandatory Updates Before Starting Week 6". The answer-scoring rule (item 4) is in `docs/week6_judging_protocol.md`. Model pinning (item 6) is in section 6.

## 1. Question and payload identity (item 1)

**What was wrong (v1).** The pilot records had no question identifier. `validate_pilot_attacks.py` and `build_pilot_attack_pools.py` paired each fabricated payload with a question by **file order** (`zip(records, payloads)`, `payloads[index]`). The payloads also carried the wrong IDs. Their `question_id`s (`eval-007296`, `eval-001639`, `eval-018024`) are the qa_ids of raw StreamingQA records 0-2 (outages, Celtic, Tolkien), not the pilot questions. For example, payload `eval-007296-fabricated_fresh-1` (the Rangers claim) was paired with the Celtic question, whose real ID is `eval-001639`. The payload *texts* were on the right questions; only the IDs were wrong.

**How the true IDs were established.** `scripts/fix_pilot_identity.py` matches each pilot record to the frozen StreamingQA source `data/raw/streamingqa_eval.jsonl.gz` on question text, `question_ts` and the full answers list. Each record had exactly one match. The script also checks that each pilot record is byte-equal to the frozen chunked-pool record at that qa_id's position in `data/raw/streamingqa_control_sample.jsonl`.

| Question | `source_qa_id` | Chunked-pool index | Payload |
|---|---|---|---|
| Celtic have 5 games before the split, how many do rangers possible have? | `eval-001639` | 1 | `eval-001639-fabricated_fresh-1` (was `eval-007296-...`) |
| How many countries have had coronavirus in February 2020? | `eval-001952` | 11 | `eval-001952-fabricated_fresh-1` (was `eval-001639-...`) |
| According to Serbia's daily Sportski Zurnal, will Djokovic play in this year's US Open? | `eval-005229` | 52 | `eval-005229-fabricated_fresh-1` (was `eval-018024-...`) |

**What changed in the data.**
- Pilot records gained `source_qa_id` and `source_chunked_pool_index`. All other fields are byte-identical to before.
- Payloads gained `source_qa_id`, `query_sha256` (secondary check) and `payload_schema: chronoguard.pilot_payload.v2`. Their old IDs are kept as `legacy_payload_id` / `legacy_question_id`.
- Payload `text` and `timestamp` are unchanged, which is verified. The frozen chunked pool, the gold answers and the aliases are untouched.

**Enforcement in code.**
- `src/attacks/identity.py`: `check_payload_matches_record` raises `PayloadIdentityError` unless `payload.source_qa_id == record.source_qa_id`. If `query_sha256` is present it must also match. Missing, duplicate or unpaired IDs also raise.
- `apply_attack` runs this check for every `fabricated_fresh` call, so the builder and validator fail immediately on a mismatch.
- `generate_attacked_records` takes payloads keyed by `source_qa_id`. Per-question seeds come from `source_qa_id` instead of file position.
- The validator runs a deliberately mismatched pair on every run and stops if it is not rejected. Result: **rejected**.
- Tests in `tests/test_identity_and_nesting.py`:
  - mismatched pair, at every poison count;
  - missing IDs;
  - query-hash mismatch;
  - missing, extra and duplicate payloads;
  - shuffled payload order;
  - shuffled record order giving identical attacks;
  - swapping two real pilot payloads.

## 2. Nested poison counts (item 2)

**What was wrong (v1).** n=1 used a separate code path from n=2 and n=5, so P1 ⊄ P2. For example, fabricated q0 was n1 `[19]`, n2 `[7, 4]`, n5 `[7, 4, 2, 18, 12]`. Copy attacks even used a different source passage at n=1.

**Fix.** `apply_attack` now runs one deterministic sequence of operations for every count. Operation *k* depends only on the seed and operations 0..*k*-1, so n=1 → [A], n=2 → [A, B], n=5 → [A, B, C, D, E] for the same question and condition. The 30-day attack and its 0-day control share the seed, so they use identical slots and sources.

Selected slots (saved in `pilot_pools_manifest.json` → `nested_selections` with seeds and doc_ids):

| Condition | eval-001639 | eval-001952 | eval-005229 |
|---|---|---|---|
| fabricated_fresh | 12 / 12,18 / 12,18,17,6,8 | 7 / 7,14 / 7,14,9,16,19 | 16 / 16,5 / 16,5,13,14,19 |
| future_date | 9 / 9,19 / 9,19,12,8,13 | 20 / 20,5 / 20,5,6,12,15 | 13 / 13,10 / 13,10,5,4,11 |
| duplicate_fresh | 13 / 13,14 / 13,14,18,15,4 | 17 / 17,6 / 17,6,5,11,20 | 8 / 8,7 / 8,7,13,16,12 |
| ccwd 30d and 0d control (identical) | 16 / 16,5 / 16,5,7,2,0 | 5 / 5,20 / 5,20,13,0,12 | 13 / 13,2 / 13,2,15,17,9 |

Seed rule: `sha256("42|<source_qa_id>|<attack_type>")[:16]`.

Nestedness is checked in three independent places:
- the validator (18/18 question × condition groups nested);
- the builder, which refuses to write non-nested pools;
- the pool checker.

`tests/test_identity_and_nesting.py` tests every attack type over 25 seeds. It also checks that the shared slots hold identical poison content and that the 30d attack and 0d control use the same slots. The nesting tests fail on the v1 code (120 failures) and pass on v2.

## 3. Stale evidence (item 3, Option A)

stale_evidence is **ineligible** for all three pilot questions, with the reason: *no reviewed stale evidence available*. It is not forced, no stale pool is built, and the 9 stale cases (3 questions × 3 counts) are reported as ineligible, not as attack failures. The only stale reviews (`results/pilot_stale_review.json`, pilot question `eval-001639`, slots 10/16/1) are all `validated: false`. The Week-6 stale-eligible subset is specified in the Week-6 protocol.

## 4. Controls (item 5, pilot part)

- **future_date** is a metadata-only negative control. E1-E4 do not read timestamps, so retrieval, prompt and answer must equal clean. Only the evaluator-side temporal metrics may change. `postprocess_pilot_attacks.py` checks this per row and saves the result in `results/pilot_consistency_check.json`. No claim is made that a timestamp shift attacks BM25, Contriever, BGE or Mistral.
- **correct_content_wrong_date (30d)** is always compared with its **0-day duplication control**. Both use the same slots and copied gold text and differ only in the timestamp. A clean-vs-attacked change is attributed to the date only if the 30d run differs from its 0d control.

## 5. Authoritative payload file (item 8)

**Authoritative:** `data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl` (schema `chronoguard.pilot_payload.v2`, sha256 `8b57695c8f6cc9d7c7cc86b7408ae7e00ce41ce9f5d997eab4762719a4230336`). It is the only payload file any active script reads.

**Legacy, audit only:** `data/processed/attack_sources/legacy/` (see the README there).
- `streamingqa_pilot_poison_payloads.LEGACY_AUDIT_ONLY.jsonl`: never read by any script, wrong `question_id`s, and descriptive rows for attacks whose text is generated by code.
- `streamingqa_week5_attack_manifest.LEGACY_AUDIT_ONLY.jsonl`: an unreferenced planning file.
- The pre-fix copies of the pilot and payload files.

**Silent misreads are blocked.** `src/attacks/pilot_protocol.load_authoritative_payloads` refuses any path other than the authoritative file and any row that is not schema v2 with a `source_qa_id` and `query_sha256`.

## 6. Model revisions and run logs (item 6)

`configs/model_revisions.yaml` pins full commit SHAs. Each was verified on 2026-10-21 against the Hugging Face API: the SHA resolves, `config.json` downloads at it, and it is the newest commit on `main`.

| Model | Revision |
|---|---|
| mistralai/Mistral-7B-Instruct-v0.2 | `63a8b081895390a26e140280378bc85ec8bce07a` |
| facebook/contriever | `2bd46a25019aeea091fd42d1f0fd4801675cf699` |
| BAAI/bge-reranker-base | `2cfc18c9415c912f9d8155881c133215df768a70` |

**Loaders.** `load_model`, `load_dense_model` and `load_reranker` take an optional `revision`. `None` keeps the Week-4 behaviour. The v2 runner always passes the pins, and it stops if the revision transformers resolved differs from the pin.

**What the drivers log.** The four E1-E4 drivers no longer hardcode `attack_condition: "clean"`. Each row records the pool's real `attack_condition`, `source_qa_id`, `poison_count`, `attack_seed` and poison target indices/doc_ids. Rows also carry a `run_metadata` block with:
- model names and pinned/loaded revisions;
- the config hash (over params, pins and config-file bytes);
- the pool sha256;
- git commit and dirty flag;
- the torch seed and attack base seed;
- package versions, CUDA and GPU.

Clean inputs still log `attack_condition: "clean"` with no extra fields. Frozen Week-4 logs and results were not altered, and they did not record revisions (documented in `docs/week4_closure.md`, section 7).

## 7. Regenerated artifacts (item 9)

The v1 outputs are kept for comparison and are **not combined** with v2:
- results: `results/legacy/week5_pilot_v1_nonnested/`
- pools: `data/processed/attack_pools/legacy/pilot_v1_nonnested/`
- attacked logs: `logs/legacy/pilot_attacks_v1_nonnested/`

The clean pilot logs `logs/pilot_attacks/clean__E*.jsonl` are unchanged and are reused (not rerun) as the clean reference.

| Artifact | Status |
|---|---|
| `results/pilot_attack_validation.json` | Regenerated. 54 cases: 45 applied and passed, 9 ineligible (stale, not forced), **0 failed**, 0 nesting failures, 0 payload problems; mismatch self-test rejected |
| `data/processed/attack_pools/pilot_v2_nested/` (15 pools + manifest) | Regenerated; 3 records each, 0 skipped; LF line endings so hashes match on Kaggle |
| `results/pilot_pool_check.json` | Regenerated. **ALL OK**: 15 files, 45 records, 16 checks (incl. nesting, 30d = 0d slots, payload identity, manifest hashes) |
| `results/legacy/.../pilot_v1_judge_vs_manual.csv` | New. Rule judge vs the v1 manual labels: 25/26 consistent, 1 flagged NEEDS_REVIEW (development check only) |
| `results/pilot_attack_rows.csv`, `results/pilot_consistency_check.json`, `results/pilot_judge_review.csv`, `results/pilot_vulnerability_summary.csv` | **Pending the Kaggle rerun.** Scripts are updated and tested end-to-end on synthetic logs |

All three generated reports record `git.dirty: true`, because the corrections are not committed yet. After committing, rerun the three CPU commands in section 8 on the clean tree and commit the outputs. Pool bytes are deterministic and will not change.

## 8. Remaining steps

1. Commit the code and data corrections. Then on a clean tree run:
   - `python scripts/validate_pilot_attacks.py`
   - `python scripts/build_pilot_attack_pools.py`
   - `python scripts/check_pilot_pools.py`

   Commit the outputs.
2. On Kaggle, run `python scripts/run_pilot_attacks_kaggle.py` (15 pools × E1-E4 → `logs/pilot_attacks_v2_nested/`) and `python scripts/smoke_test_e2_e4_post_freeze.py` (W4-F1).
3. Locally, run:
   - `python scripts/postprocess_pilot_attacks.py`;
   - label any `NEEDS_REVIEW` rows in `results/pilot_judge_review.csv`;
   - `python scripts/summarize_pilot_attacks.py`.
4. Add the v2 results tables to this report (section 9) and record the smoke-test results in `docs/week4_post_freeze_validation.md`.

## 9. Corrected pilot results

*To be filled in from `results/pilot_vulnerability_summary.csv` after step 3.* Every quantity goes in its own column: poison selection rate, ASR, conditional ASR, correctness drop, gold displacement rate, mean/median best poison rank, and Δ Recall@5, Δ nDCG@5, Δ valid-evidence Recall@5, Δ TVAA and Δ fraction violating. Undefined values stay blank. n=3 is a development case study, not a statistical benchmark.
