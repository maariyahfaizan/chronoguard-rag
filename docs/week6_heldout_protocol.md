# Week 6 held-out StreamingQA protocol (PROPOSED v1 — NOT FROZEN)

## Purpose and status
Editorial status (GIT-A2): this is an unapproved implementation proposal.
Its sampling and eligibility choices are not made authoritative by this edit.
The recovery narrative below preserves an earlier investigation state; later
audits reconciled 390 recovered candidates and verified backup inventories.
That does not authenticate historical sources or certify the 300 priorities.
Week 6 still requires validation, main attack experiments and attack analysis;
defense implementation/evaluation belongs to Weeks 7-8. See the
[supervisor review index](supervisor_review/README.md) for the package dependency.

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
3. Retain only records labeled `recent` or `past`. Sort IDs lexicographically within each stratum. Independently shuffle each stratum using a Python pseudorandom generator initialized as `random.Random(f"week6-v1:{seed}:{s}")`, where `seed = 42` and `s` is the stratum label (`recent` or `past`). Record the Python version, exact algorithm, and generated reserve-manifest checksum. The resulting ordering is deterministic for the recorded environment.
4. Target **150 recent + 150 past** evidence-eligible questions (300 total), provisional pending feasibility. The full shuffled ordering is a reserve sequence, not a final benchmark.
5. Never select or replace questions based on generator answers, retrieval performance, attack success, defense results, or manually preferred content.

## Evidence eligibility and replacement
- Process the predetermined reserve sequence in each stratum. Accept a question for the *primary benchmark* only if its gold article resolves in the reconstructed WMT corpus, at least one recovered passage supports the correct answer under a predeclared semantic evidence-review policy, and its candidate pool passes schema, chunking, and integrity checks. Normalized lexical gold matching is used as an automated screening signal, not as conclusive evidence of semantic correctness. Record the reviewer decision and rationale separately from the automated audit.
- Record every considered ID, eligibility decision, reason, evidence provenance, and final rank. Do not silently skip failed cases. If fewer than 150 pass in a stratum, report the shortfall; do not silently alter the target.
- Condition-specific eligibility is distinct: `stale_evidence` requires reviewed stale evidence; `fabricated_fresh` requires a reviewed false-claim key; other conditions have their own predeclared constraints. An ineligible attack condition does not disqualify an otherwise eligible primary question.
- Lexical gold matching is a proxy for answer-bearing evidence, not semantic verification. The chunker currently marks all descendants of a validated passage as gold; individually answer-bearing chunk coverage needs explicit auditing. Oversized chunks from tail merging also need auditing, not silent correction.

## Evidence reconstruction and provenance
- The original `streamingqa_relevant_passages` shards were lost. A separate Week 6 reconstruction pipeline was subsequently implemented using the official WMT News Crawl document archives. An initial ten-candidate extraction recovered all ten gold parent documents across the relevant years. The extracted passage shards were subsequently lost when the Kaggle session ended, and reconstruction is being repeated. Persistent storage and checksum verification remain outstanding. The initial 2009 extraction produced zero passages and requires investigation before corpus completeness can be asserted.
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
