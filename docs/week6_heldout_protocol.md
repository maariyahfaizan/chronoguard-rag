# Week 6 held-out StreamingQA protocol (PROPOSED v1 — NOT FROZEN)

## Purpose and status
A separate, development-independent, stratified StreamingQA evaluation. This proposal requires supervisor approval and a recorded approval commit before held-out answer inspection. It does not modify the Week 4 baseline or the Week 5 pilot.

## Known source facts
- Original input: `data/raw/streamingqa_eval.jsonl.gz`; 36,378 records, 36,378 unique `qa_id` values.
- Week 4 processed pool: `data/processed/streamingqa_control_pools_chunked.jsonl`; 100 distinct normalized questions, mapping to 101 raw IDs because one question text maps to two IDs.
- Corrected Week 5 pilot IDs: `eval-001639`, `eval-001952`, `eval-005229`; all already covered by Week 4 exclusions.
- Preliminary remaining candidate IDs: 36,277. This is NOT an evidence-validated benchmark.
- Raw temporal labels: 20,071 `recent` and 16,307 `past` before exclusions.
- Original questions all have 2020 question timestamps; evidence years range 2007–2020. A 2008–2014-only evidence corpus would systematically exclude nearly all `recent` questions.

## Proposed sampling design
1. Sampling unit is raw `qa_id`. Normalize question text by NFKC, collapsing whitespace, trimming, and casefolding. Exclude *every* raw ID whose normalized question matches a Week 4 pool question; also exclude the corrected pilot IDs explicitly.
2. Additional development-exposed questions must be identified and excluded before freeze; the 101 known exclusions are not asserted to be exhaustive.
3. Retain only records labeled `recent` or `past`. Sort IDs lexicographically within each stratum. Shuffle each stratum using `random.Random(42)` **separately**; algorithm and Python version must be recorded.
4. Target **150 recent + 150 past** evidence-eligible questions (300 total), provisional pending feasibility. The full shuffled ordering is a reserve sequence, not a final benchmark.
5. Never select or replace questions based on generator answers, retrieval performance, attack success, defense results, or manually preferred content.

## Evidence eligibility and replacement
- Process the predetermined reserve sequence in each stratum. Accept a question for the *primary benchmark* only if its gold article resolves in the reconstructed WMT corpus, at least one passage meets the frozen lexical gold validation rule, and its candidate pool passes schema/chunking/integrity checks.
- Record every considered ID, eligibility decision, reason, evidence provenance, and final rank. Do not silently skip failed cases. If fewer than 150 pass in a stratum, report the shortfall; do not silently alter the target.
- Condition-specific eligibility is distinct: `stale_evidence` requires reviewed stale evidence; `fabricated_fresh` requires a reviewed false-claim key; other conditions have their own predeclared constraints. An ineligible attack condition does not disqualify an otherwise eligible primary question.
- Lexical gold matching is a proxy for answer-bearing evidence, not semantic verification. The chunker currently marks all descendants of a validated passage as gold; individually answer-bearing chunk coverage needs explicit auditing. Oversized chunks from tail merging also need auditing, not silent correction.

## Evidence reconstruction and provenance
- The previous `streamingqa_relevant_passages` shards were lost. Local compressed WMT archives exist for 2008–2014 and a partial 2015 file, but archive integrity has not been verified. Rebuilding full-period evidence may require Kaggle and reacquisition of later archives.
- Original pool-building configuration was reconstructed after loss of the original Kaggle session; report recovered facts versus documented defaults faithfully.
- Maintain Week 4 frozen files unchanged. Use distinct Week 6 input/output paths and preserve `qa_id` through sampling, pool building, preprocessing, and chunking. Existing chunker copies arbitrary top-level fields via `dict(record)`.
- Preserve evidence-source file hashes, source dataset hash, script hashes/commit, configuration, tokenizer revision, Python/library versions, sampling manifest hashes, and run logs.

## Leakage and freeze gates
- This starter creates only an ID-based *reserve manifest*. It does not select final benchmark members, construct evidence, or inspect model outputs.
- Freeze exclusion policy, ordering algorithm, evidence-eligibility rules, attack settings, and answer judge before inspecting held-out generated answers. Supervisor sign-off and freeze commit are outstanding.
- Pilot outcomes may guide pre-freeze design, but not count as independent held-out judge validation. Follow `docs/week6_judging_protocol.md` for outcome definitions and separate attack-eligibility denominators.

## Known implementation risks / outstanding decisions
- Confirm additional development-exposed questions beyond the 100 Week 4 pool.
- Verify full-period WMT evidence availability, including the 2007 evidence-year discrepancy.
- Confirm target N=300, seed=42, Python version and sample algorithm with supervisor.
- Decide whether eligibility screening must be completed before or after approval, and freeze the exact policy before applying it.
- Ensure `qa_id` is required in separate Week 6 pool/preprocessing paths; no edits to frozen Week 4 outputs.
