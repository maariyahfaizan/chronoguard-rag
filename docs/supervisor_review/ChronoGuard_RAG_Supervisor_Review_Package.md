# A. Supervisor Cover Summary

## ChronoGuard-RAG: Pre-Approval Research Submission

Researcher: Mariyah Anjum Faizan
Status: Supervisor review requested. All scientific decisions remain UNRECORDED.
Scope authority: Original RESEARCH EXPERIMENT PLAN, with the scheduling correction specified below.

ChronoGuard-RAG investigates whether stale evidence, fabricated updates and manipulated dates cause RAG systems to override correct evidence. It then evaluates a proposed verification method combining temporal intent, date normalization, claim conflict detection and cross-document support. The STRONG target retains three datasets, four retrieval architectures, a smaller second-generator-family study, robustness analyses, ablations, cost evaluation and reproducible public artifacts.

### Verified progress

Week 5 development work is scientifically closable. The corrected pilot comprises 60 attack runs and 180 rows across three development questions, four retrieval systems and poison counts 1/2/5. Five conditions were executed; stale amplification was ineligible. Saved hashes, report tables, summary calculations and checked execution metadata reconcile. The execution tree was dirty, limiting historical source-code reproducibility. Results remain development-only.

Existing matched-header diagnostics use two fictional examples. They distinguish scoring effects from semantic understanding and generator adoption; they should be reused, not rerun without a concrete defect.

Week 6 remains incomplete. The reconciled frame contains 400 candidates, of which 390 have recovered evidence representations. The 300 priorities are provisional review candidates, not a frozen or certified benchmark. Independent semantic/temporal adjudication, source-claim policy, eligibility, exposure decisions and main attack experiments remain outstanding.

### Immediate supervisor decisions

Approval or revision is requested for:

- confirmatory hypotheses, contrasts and ASR populations;
- reconstructed-source claims and derived answer-key policy;
- independent review and held-out exposure rules;
- sampling authority, eligibility and reserve replacement;
- sample-size justification, statistical families and generator-isolated RQ3 design;
- Week 6 execution configurations and validation gates.

Every decision-sheet approval field remains UNRECORDED.

### Corrected schedule

- Week 5: Attack construction, development pilot and initial attack evaluation.
- Week 6: Benchmark validation, main attack experiments and attack analysis.
- Week 7: ChronoGuard implementation and initial defense evaluation.
- Week 8: Defense experiments, ablations, robustness and comparative evaluation.

Defense implementation or completed defense evaluation is not a Week 6 completion criterion. Week 6 attack execution nevertheless requires approved attack protocols and validated inputs before outcomes are inspected.

### Requested next action

Review the decision sheet, record dispositions and identify which Week 6 gates must be satisfied before execution. Internal review readiness does not constitute supervisor approval, benchmark freeze or execution authorization.

———

# B. Final Five Supervisor-Facing Documents

# Document 1 — Research Experiment Protocol v1

## PRE-FREEZE — PROPOSED, NOT APPROVED

### 1. Authority, objectives and schedule

The original RESEARCH EXPERIMENT PLAN governs scientific scope. The corrected schedule places main attack experiments in Week 6, defense implementation and initial evaluation in Week 7, and full defense comparisons in Week 8.

The study separates retrieval preference, generator adoption, temporal correctness and source authenticity.

The original research questions are:

1. RQ1. How vulnerable are RAG systems to stale evidence, fabricated “newer” evidence, and timestamp manipulation?
2. RQ2. Do dense and hybrid retrievers respond differently to recency wording and date tokens?
3. RQ3. When correct and incorrect passages conflict, how strongly does the generator prefer newer-looking evidence?
4. RQ4. Can query-time constraints and cross-document temporal consistency reduce attack success without hurting ordinary factual QA?

The original hypotheses remain:

- Recency-sensitive questions show greater poisoning effects than timeless factual questions.
- Relevance-only reranking overvalues semantically close but temporally invalid passages.
- Temporal validity combined with evidence agreement reduces false recency preference with limited clean-accuracy loss.

The STRONG target retains three or more datasets, multiple retrieval architectures, full robustness slices, compute/cost evaluation and public reproducibility artifacts. A smaller second-family generator study remains part of the minimum core.

### 2. Proposed hypothesis and estimand hierarchy

Let:

- E: questions eligible for an attack family before system outcomes;
- A_{c}: answer adopts its prespecified false state under condition c;
- C_{c}: answer is correct under the approved question-time key;
- S_{c}: poison is visible in the generator’s actual context.

| Level | PROPOSED contrast | Scientific interpretation |
|---|---|---|
| Primary attack confirmatory | Mean paired A_{freshness}-A_{matched neutral} over E | Textual-freshness intervention effect |
| Defense confirmatory, Weeks 7–8 | Adoption reduction versus no defense, accompanied by clean-utility noninferiority | Defense effectiveness and acceptable utility retention |
| Supporting confirmatory | Differences between architectures’ within-question intervention effects | RQ2 architecture interaction |
| Supporting confirmatory | Wording-by-newer-assignment interaction in generator-isolated trials | RQ3 generator preference |
| Supporting confirmatory | Poisoning-effect differences across validated temporal-intent groups | Temporal-versus-timeless hypothesis |
| Supporting outcomes | Vulnerability, clean-correct compromise, exposure and temporal metrics | Magnitude and mechanism |
| Exploratory | Additional phrases, unplanned slices and error-derived mechanisms | Hypothesis generation |

The final systems, budgets, datasets and multiplicity family remain PROPOSED.

Causal wording applies to the controlled intervention within the evaluated pipeline. It does not establish general recency understanding or open-corpus attacker effectiveness.

### 3. Outcomes and denominators

PROPOSED main-study definitions:

- Eligible-case ASR: ∑ A_{c}/|E|.
- Clean-correct compromise: adoption among eligible cases correctly answered under clean conditions; secondary, with system-specific denominators.
- Exposure-conditional adoption: adoption among S_{c}=1; descriptive because exposure changes under treatment.
- Correctness loss: mean C_{clean}-C_{c}.
- Freshness-specific correctness loss: mean Cₙₑᵤₜᵣₐₗ-C_{freshness}.
- Defense benefit: mean A_{no defense}-A_{ChronoGuard}.
- Clean-utility difference: mean C_{ChronoGuard}-C_{no defense}.

Poison-consistent output is an operational outcome, not individual-level proof of document causation.

Retain EM/F1 or benchmark accuracy, TVAA, query-date correctness, poison-selection rates, Recall@k, nDCG@k, valid-evidence Recall@k, temporal violations, filter precision/recall and cost metrics.

Zero denominators remain undefined. Unresolved judgments and technical failures remain visible. Retrieved poison is not necessarily generator-visible poison or adopted poison.

Week 5 metric names and denominators remain unchanged.

### 4. Systems, datasets and threat model

| Component | Commitment |
|---|---|
| E1 | BM25 |
| E2 | Contriever dense bi-encoder |
| E3 | BM25–Contriever hybrid RRF |
| E4 | Hybrid plus BGE cross-encoder |
| StreamingQA | Primary historical, question-time-grounded evaluation |
| FreshQA | Frozen dated current-knowledge evaluation |
| Static control | TriviaQA or Natural Questions; ordinary utility unless authentic dates support temporal use |
| Primary generator | Existing open Mistral-7B instruction model |
| Transfer | Prespecified smaller second-family generator study |

PROPOSED attacker: query-aware, bounded replacement of non-gold candidate slots, with timestamp changes restricted to declared surfaces. The attacker cannot modify questions, original labels, model weights, instructions or protected correct evidence.

Researcher access to gold labels does not imply attacker access. The knowledge assumption requires approval.

Candidate-pool replacement does not demonstrate full-index injection, open-corpus discoverability or adaptive defense evasion.

### 5. Week 6 end-to-end attack/control design

Retain the five original families:

- stale amplification;
- fabricated-fresh evidence;
- future-date shift;
- duplicate fresh-looking evidence;
- correct-content/wrong-date controls.

| Condition | Purpose |
|---|---|
| Clean | Reference |
| False/stale claim without artificial header | Content/amplification |
| Same claim with matched neutral header | Generic header |
| Same claim with freshness header | Textual freshness |
| Correct claim with neutral/freshness headers | Valid-evidence preference or distrust |
| Timestamp-only unchanged/shifted pair | Metadata sensitivity |
| Correct-content duplication at 0d/offset | Duplication versus timestamp |
| Recent-content duplication | Repetition |

Budgets 1/2/5 remain proposed nested levels where eligible. The confirmatory budget requires approval.

Paired conditions preserve question, claim body, evidence identities, slots, ordering policy, applicable metadata, model settings and judge.

Check length and retained body content under retrieval tokenization and prompt truncation. The current 1,500-character cap can otherwise change claim visibility.

BM25 corpus refitting remains part of the end-to-end intervention; token/length/IDF traces support mechanism analysis.

### 6. Week 6 generator-isolated RQ3 design

This experiment directly supplies conflicting evidence and is separate from retrieval evaluation.

| Factor | Levels |
|---|---|
| Newer-looking assignment | Correct newer / incorrect newer |
| Wording | Matched neutral / freshness |
| Order | Correct first / incorrect first |

Both passages remain visible with matched claim/source presentation and fixed context allocation. Date assignments are held constant within wording comparisons. Experimental date assignments must not be called authenticated publication dates.

Answer categories:

1. Correct state.
2. Prespecified incorrect state.
3. Abstention.
4. Other wrong state.
5. Ambiguous/unresolved answer.

PROPOSED primary RQ3 contrast: wording-by-newer-assignment interaction in incorrect-state adoption. Report both correct-newer and incorrect-newer results, including order sensitivity.

Repeated conditions remain grouped by question.

### 7. Weeks 7–8 defense design and comparisons

No completed defense implementation is claimed.

ChronoGuard retains temporal-intent classification, date normalization, claim conflict detection, temporal validity, cross-document support, relevance integration and bounded recency preference.

Historical/as-of constraints and retrospective exceptions require approved rules.

Baselines:

- no defense;
- relevance-only reranking;
- simple date filtering;
- full ChronoGuard.

All five original ablations remain:

1. Remove temporal-intent classification.
2. Date filtering without conflict detection.
3. Unbounded recency bonus.
4. Remove cross-document support.
5. Explicit metadata versus text-inferred dates.

A practical date-filter baseline and the date-filter ablation may share results only when their components and parameters are identical. Otherwise they require separate names and comparisons.

Component claims require controlled full-method-versus-removal comparisons. Interactions must not be assumed additive.

### 8. Robustness, utility, cost and error analysis

Preserve recent/historical, explicit/implicit dates, single/conflicting-source evidence, poison counts and a declared difficulty-related slice.

Evaluate legitimate updates and retrospective questions alongside ordinary factual QA. Rejecting all recent evidence cannot satisfy RQ4.

Record latency, tokens, extra calls, hardware, batching and preprocessing costs.

Inspect 50–100 representative errors across conditions, separating retrieval, selection, generation and evaluation ambiguity. Include defense regressions.

### 9. Statistics, validation and freeze

Pair by question and account for repeated conditions and shared-source dependence where material. Use 95% bootstrap intervals, appropriate paired tests and direct interaction comparisons.

McNemar testing applies to suitable binary paired comparisons; factorial repetitions need a question-level summary or repeated-measures model.

Holm is the preferred multiplicity proposal. Final families, meaningful effects, sample sizes and clean-utility margins remain undecided. Nonsignificant degradation does not establish noninferiority.

Retain at least five seeds for lightweight learned components and representative repeat runs for expensive deterministic generation.

Week 6 attack-execution prerequisites: approved attack estimands/design, evidence policy, keys, review, exposure, sampling, judge and attack configurations, followed by validated and frozen attack-evaluation inputs.

Weeks 7–8 defense prerequisites: development-only tuning, approved defense configuration and ablations, utility margins and defense analysis plan before held-out defense evaluation.

Defense implementation or completed defense evaluation is not required to close Week 6.

———

# Document 2 — Week 5 Pilot Validation Report

## VERIFIED DEVELOPMENT EVIDENCE — CLOSURE DRAFT

Protocol week5_pilot_v2_nested comprises:

- 60 attack runs;
- 180 raw and analysis rows;
- three development IDs: eval-001639, eval-001952, eval-005229;
- poison counts 1/2/5;
- E1–E4.

Executed conditions were fabricated_fresh, future_date, duplicate_fresh, correct_content_wrong_date_30d and correct_content_wrong_date_0d_control.

Stale amplification was ineligible, not a failed attack.

### Verification

Sources include logs/pilot_attacks_v2_nested/run_manifest.json and the results/pilot_* analysis, summary, review and consistency files.

Completed audits found:

- recorded attack-log/pool and four reused clean-log hashes matched;
- 180 unique analysis keys;
- 240 report metric cells matched;
- 36 count-specific slot selections matched;
- 1,296 summary comparisons matched;
- 180 rows matched checked execution-manifest fields;
- audited negative-control retrieval/prompt/answer comparisons matched;
- saved consistency status was OK.

### Adjudication and denominators

fabricated_fresh_n2|E3|eval-005229|attacked was labelled OTHER_WRONG. Its ASR is 0.6667, with no unresolved review.

Historical denominators remain:

- eligible attacked: three per executed cell;
- paired metric observations: three;
- conditional ASR: poison-selected questions;
- gold displacement: two or three clean gold-exposed questions.

Non-false-claim controls have ASR not applicable. Ineligible stale metrics are undefined.

### Provenance and conclusion

Execution commit was cc7d6fff8641f3b82112278a477df180e1af6b2f, with git.dirty=true. Exact uncommitted source reconstruction remains unavailable.

The pilot supports development case studies, not generalizable attack efficacy, freshness-specific causation or defense effectiveness.

Week 5 is scientifically closable. Week 6 main attack evaluation remains outstanding.

Existing report §8.4’s Week 4 document-update checklist is obsolete. It has not been edited. No pilot rerun is recommended.

———

# Document 3 — Week 6 Construction and Validation Report

## INCOMPLETE — PROVISIONAL CANDIDATES, MAIN ATTACKS OUTSTANDING

### Verified accounting

| Stage | Total | Recent | Past |
|---|---:|---:|---:|
| Original frame | 400 | 200 | 200 |
| Recovered | 390 | 200 | 190 |
| Provisional priorities | 300 | 150 | 150 |
| Reserves | 90 | 50 | 40 |
| Source-scope exclusions | 10 | 0 | 10 |

The ten exclusions concern 2007 evidence outside configured recovery years. Priority is a scheduling status, not eligibility.

### Integrity and provenance

Recovery outputs reside under:

C:\Users\mofai\Projects\chronoguard-week6-recovered\development_backup\

Audited exports contain 1,316 variants, 1,417 occurrences, 1,316 aliases and 416 document observations.

Recorded consolidated/review hashes matched. All 22 backup-inventory entries matched size and SHA-256.

These verify inventory consistency, not historical authenticity. The recovery manifest remains provisional and uncertified. Original-compressed/historical verification is absent for the 13 source-artifact entries; original document membership remains unverified.

### Annotation

Annotation CSVs cover the 300 provisional priorities.

Two unique records explicitly carry human_verified=true: eval-025610 and eval-023086. Both remain pending provenance/alias requirements. Independent dual review, reviewer authentication and agreement measurement are not established.

Other records are preliminary assessments or automated screens. The 238-row consolidated status omits the separate Round 3 semantic-assessment layer.

Referenced packet hashes and checked supporting-variant membership reconcile; semantic certification does not follow.

### Provenance policy pending approval

- Reconstructed-source policy: permits controlled evaluation on identified recovered representations, with explicit limitations.
- Authenticated historical-source policy: requires independent evidence connecting source identity, representation and relevant historical date.

Neither policy substitutes for semantic or temporal validation.

### Outstanding Week 6 work

- Approve scientific and evidence policies.
- Validate questions, aliases, temporal keys and attack claims.
- Complete independent review/adjudication.
- Resolve exposure, sampling authority and reserve rules.
- Validate/freeze attack-evaluation inputs and configurations.
- Execute main attacks and generator-isolated RQ3 trials.
- Analyze attacks, robustness and failures.

Week 6 is not complete. Recovery and screening do not satisfy its main experimental obligations. Defense implementation and evaluation belong to Weeks 7–8.

———

# Document 4 — Supervisor Decision Sheet

## ALL APPROVAL FIELDS UNRECORDED

For every row: APPROVE / REVISE / DEFER — UNRECORDED.

### A. Scientific scope, hypotheses and estimands

| Question | Preferred proposal / alternative | Rationale | Deadline |
|---|---|---|---|
| Preserve STRONG scope? | Three datasets, E1–E4, transfer, robustness/cost / explicit downgrade | Protects original commitments | Now |
| Approve attack estimand hierarchy? | Freshness paired effect plus supporting interactions / narrower family | Determines Week 6 claims | Before sizing and attack freeze |
| Primary ASR denominator? | Eligible-case primary, clean-correct secondary / reverse hierarchy | Prevents population ambiguity | Before attack analysis freeze |
| Approve RQ3 isolation? | Assignment × wording × order / end-to-end-only narrower claims | Separates retrieval and generation | Before Week 6 execution |
| Preserve defense components/ablations? | Original method and five ablations / approved revised contribution | Protects RQ4 and novelty | Scope now; configuration before defense testing |

### B. Evidence validity and independence

| Question | Preferred proposal / alternative | Rationale | Deadline |
|---|---|---|---|
| Provenance policy? | Reconstructed evaluation with tiers / authenticated-only | Feasibility versus claim strength | Before eligibility |
| Derived keys? | Separate adjudicated layer, originals preserved / exclude unresolved keys | Prevents invalid scoring | Before annotation |
| Review independence? | Dual review plus adjudication / single review with independent audit | Label validity and resources | Before review |
| Exposure policy? | Permit governed construction review, exclude tuning/outcome-driven use / exclude all inspected cases | Protects test independence | Before final membership |
| Sampling authority? | Reconciled existing order, rule-based reserves / new approved order | Prevents selective replacement | Before eligibility selection |

### C. Resources, statistics and freeze

| Question | Preferred proposal / alternative | Rationale | Deadline |
|---|---|---|---|
| Sample size? | Meaningful paired effects and precision/power / feasibility-limited narrower claims | Priorities do not prove adequate N | Before Week 6 freeze |
| Confirmatory inference? | Paired/cluster-aware tests, bootstrap and Holm / alternative valid prespecified framework | Controls dependence/multiplicity | Before outcomes |
| Transfer scope? | Smaller second-family generator study / larger matrix | Minimum core retained | Scope now; details before transfer |
| Clean-utility margin? | Prospective justified margin / descriptive utility only | Determines RQ4 claim strength | Before defense sizing/testing |
| Freeze sequence? | Approval → validation → artifact freeze → execution check / combined gate | Separates readiness states | Now |

Implementation details may be delegated after approval: configuration formatting, hashing, balanced-order code, logging, tokenizer checks and regeneration tooling. Delegation cannot alter hypotheses, populations, margins or eligibility policy.

———

# Document 5 — Reproducibility and Artifact Manifest

## AUDITED REFERENCES — NO NEW FREEZE

### Repository identity

| Item | Audited value |
|---|---|
| Main | C:\Users\mofai\Projects\chronoguard-rag |
| Recovery | C:\Users\mofai\Projects\chronoguard-week6-recovered — not Git |
| Main branch/HEAD at A0 | master / 87487f66f50c75d2f0efa82eb73678c1dc9366e5 |
| Week 4 tag | week4-frozen |
| Peeled commit | d995f832c6ab81aea9c9fe8da993e1fe8a138914 |
| Nested StreamingQA HEAD | 18dc327429333750fbeca32fd4e27f328127774a |

These are prior audited snapshots, not a fresh working-tree certification. Modified/untracked documents and inaccessible cache/test directories were recorded.

### Evidence locations

| Category | Location |
|---|---|
| Week 5 execution | logs/pilot_attacks_v2_nested/run_manifest.json and associated logs |
| Week 5 analyses | results/pilot_* |
| BM25 diagnostic | results/smoke_diagnostics/bm25_header_controls_v1/ |
| Contriever diagnostic | results/smoke_diagnostics/contriever_header_controls_v1/ |
| Draft 400-frame | results/week6_sampling_draft/screening_batch_v1/ |
| Recovery | R development_backup/consolidated_evidence/ |
| Review queue | R development_backup/development_review/ |
| Backup inventory | R development_backup/BACKUP_FILE_MANIFEST.json |

Verified diagnostic results hashes:

- BM25: 343cf43e883780003247a3adc46d55eef1fd1ade07c4d623b2a1136d8a928527
- Contriever: d2ad73f91e7d3af730243a1b2ca74843a5a93a1a4fe944c8d7e69ccc92dd21fd

These fictional diagnostics do not establish general attack success or generator adoption.

### Authority and limitations

Recovery ledger: provisional recovery disposition.
Review queue: provisional scheduling.
Individual assessments: preliminary layers.
Calibration decisions: two explicit verification records.
Consolidated 238 status: incomplete aggregation.
Final benchmark labels: NOT ESTABLISHED.

Historical equivalence, authentic publication timing and complete original document membership remain NOT VERIFIED. Week 5’s dirty-tree limitation remains.

### Required future outputs

Week 6 attack package: approved protocol/decisions, exposure and eligibility manifests, original/derived key identities, reviews/adjudications, evidence and attack hashes, model/environment/configuration records, prompts, judge validation, attack analysis plan, raw logs/failures and reproducible attack tables.

Weeks 7–8 defense package: development tuning records, frozen defense and ablation configurations, utility-margin specification, defense/transfer logs, cost study, robustness/error analyses and final paper-regeneration scripts.

No future output is claimed complete merely because its schema is proposed.

———

# C. Week-by-Week Completion and Dependency Table

| Week | Required work | Verified state | Dependencies and exit evidence |
|---|---|---|---|
| 5 | Attack construction, development pilot, initial evaluation | Scientifically closable; 60 runs/180 rows verified | Retain development-only scope and dirty-tree limitation |
| 6 | Benchmark validation, main attacks, generator-isolated RQ3, attack analysis | Incomplete; recovery/accounting done, eligibility and main execution pending | Supervisor dispositions; validated keys/evidence; exposure and sampling decisions; attack freeze; raw logs and analyses |
| 7 | ChronoGuard implementation, development tuning, initial evaluation | Pending; no completed implementation claimed | Approved method/baselines; development data; component tests; initial utility/attack evaluation |
| 8 | Defense experiments, five ablations, robustness and comparisons | Pending | Frozen defense settings; utility margin; validated evaluation inputs; statistical/cost/error analyses |

Week 6 does not require completed defense implementation. Weeks 7–8 must not use held-out attack outcomes to tune the defense around individual test cases.

———

# D. Immediate Decisions Needed to Unblock Week 6

1. Approve attack hypotheses, estimands, denominators and confirmatory comparisons.
2. Approve provenance and derived-key policies.
3. Commit independent review/adjudication resources.
4. Resolve exposure, ordering, exclusions and reserve replacement.
5. Approve sample-size rationale and dataset-specific evaluation roles.
6. Approve RQ3 factorial and position/length invariants.
7. Approve judge-validation and attack-execution gates.

Approval alone does not complete these gates; validated artifacts must follow before execution.

———

# E. Tasks Specifically Assigned to Weeks 7–8

Week 7: implement ChronoGuard components, practical defense baselines, development-only tuning, component validation and initial evaluation.

Week 8: full defense comparisons, all five ablations, clean-utility and legitimate-update/retrospective evaluation, defense robustness, cost analysis and comparative statistical assessment.

Second-family transfer scope must be approved now; its execution placement should be coordinated with the relevant attack and defense evaluations rather than silently omitted.

———

# F. Final Consistency Assessment

PASS — supervisor-submission readiness.

The package:

- preserves STRONG scope and unresolved decisions;
- keeps every approval field UNRECORDED;
- places main attack work in Week 6;
- separates Weeks 7–8 defense milestones;
- does not call the 300 priorities a frozen benchmark;
- distinguishes reconstructed representations from authenticated historical sources;
- preserves Week 5 findings and limitations.

Week 6 completion, scientific approval and execution readiness are not claimed. No files, membership, annotations or artifacts were changed.

# G. Exactly One Recommended Next Checkpoint

W5–W6-A3a — Supervisor Disposition and Week 6 Execution-Gate Review: record decisions and identify the remaining validation evidence required before main attack execution.