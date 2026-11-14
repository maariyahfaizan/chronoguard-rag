# Week 6 decision register proposed v1 — W6-D1

14 November 2026. **PROPOSED; ALL AUTHORITATIVE DECISIONS UNRECORDED.**
W6-D1-R1 reconciles the same v1 register; no new protocol version is introduced.
This is a review crosswalk, not an approval ledger. The authoritative sheet and
all historical documents remain unchanged. No signatures, decision dates or
dispositions have been supplied by W6-D1.

## 1. Source identity and precedence

| Source | Role / identity |
|---|---|
| [P0-A5 decision sheet](supervisor_review/p0_a5/judge_approval_decision_sheet.md) | Sole source of authoritative D01–D14 IDs, original wording, owners and options. Raw SHA-256 `b6d7ec62c7a9df9535b4f2a40055dca74a747cdd5316e6453961761c40a71165`. |
| [Original supervisor package](supervisor_review/ChronoGuard_RAG_Supervisor_Review_Package.md), Documents 1 and 4 | Research questions, STRONG scope, fifteen broader scope questions. These are not the fourteen judge rows. |
| `docs/supervisor_review/source_documents/ChronoGuard_RAG_Student_Required_Corrections_03Nov2026.docx` | November 3 corrections, locally present; SHA-256 `4568d459f4f4b2a2525293fe4410afc7bb26b4300420e50aafe3a2698c5ee076`. Source paragraph references below use one-based Word body paragraph order including tables. |
| [G4 v3 request](supervisor_review/g4_submission_v3/supervisor_decision_request.md), [coverage matrix](supervisor_review/g4_submission_v3/correction_coverage_matrix.csv) | Explicit routing and distinction between judge decisions, broader scope requests and scientific gates. |
| `C:/Users/mofai/Downloads/ChronoGuard_Week6_Proposed_Decisions_Protocol.md` | Local 14 November thematic P01–P14 draft, found/read but not copied or modified. SHA-256 `a0c2a9739da957eb6b55bc5f25b8c1a0a9285d000d2e543bdb491e615cbc6fd4`. Its own scope note disclaims an authoritative D-ID mapping. |
| [W6-J1](w6_j1_offline_postprocessing.md) / baseline `a605d1c4297c0b62ee339f99cd47a06c0590cb8a` | Separate offline fixture admission and replay implemented after G4 v3; real authority remains disabled. |

File identity and researcher-supplied designation do not authenticate authorship,
source truth or scientific approval. Local raw-byte hashes may differ across line-
ending conversions; do not substitute normalized hashes for raw identity silently.

## 2. Exact authoritative fourteen-row decision table

The following table is copied from P0-A5 without rewriting historical findings,
choices, alternatives, required decision-makers, blank fields or UNRECORDED status.
Later repairs and proposed refinements appear separately below.

| ID | Decision | Proposed choice | Scientific justification | Alternatives | Consequences | Required decision-maker | Status | Decision | Date | Signature |
|---|---|---|---|---|---|---|---|---|---|---|
| D01 | Permitted automatic claim types | Restrict to explicitly reviewed complete entity/span, stance and plain signed integer/decimal expressions after technical findings are resolved; no numeric inference. | Limits normalization-based false endorsement. | Human-only judging; narrower claim domain. | Reduced coverage; unsupported domains cannot inherit validation. | Supervisor + independent technical/domain reviewers | UNRECORDED | | | |
| D02 | Temporal qualification | Require question-time reference and evidence-backed scope for each expression; unresolved scope goes to review. | Metadata alone cannot certify time-correct endorsement. | Only timeless claims; separate temporal judge. | May exclude ambiguous temporal questions; no change to benchmark eligibility without approval. | Supervisor + temporal-domain reviewers | UNRECORDED | | | |
| D03 | Paraphrase equivalence | Allow only independently reviewed complete expressions derived before answer inspection; inspect normalized collisions. | Prevents answer-derived success definitions. | Exact literal matching; separately validated semantic judge. | Coverage loss; revised expressions need fresh binding and confirmation. | Supervisor + semantic reviewers | UNRECORDED | | | |
| D04 | Claim-key approval authority | Supervisor or named delegate approves final digest after two reviews and adjudication, with final-digest verification. | Separates authorship, review and authorization. | External review board. | Requires controlled ledger and active manifest; hashes do not authenticate authority. | Supervisor | UNRECORDED | | | |
| D05 | Validation population | Use reconciled existing development StreamingQA only; no held-out or legacy outcomes; decide applicability for benign controls. | Protects independence and target-population meaning. | Pilot-only descriptive study; separately authorized development expansion. | Current false-claim diversity is only three questions. | Supervisor + data steward | UNRECORDED | | | |
| D06 | Sample size/allocation | Target 200 unique inputs, provisional 80/40/40/40 machine strata; census shortages and proportional redistribution before human labels. | Enriches precision evidence while retaining review cases. | Larger fixed sample; pilot census. | Availability not established; no balanced cross-product guarantee. | Supervisor + statistical reviewer | UNRECORDED | | | |
| D07 | Human-review procedure | Two independent blinded raters per input, third adjudicator, retained unresolved cases and pre-adjudication agreement. | Provides an independent reference and reliability audit. | Three initial raters; external panel. | Blinding may be partially inferable; costs reviewer time. | Supervisor + reviewer lead | UNRECORDED | | | |
| D08 | Precision/rejection thresholds | Propose zero synthetic rejection false positives, precision >=.95 and one-sided 95% lower bound >=.90, with unresolved sensitivity bounds. | Limits false claims of poison adoption. | Different error tolerance; larger sample. | Currently open numeric rejection failure; weighted/cluster uncertainty must support gate inference. | Supervisor + statistical/technical reviewers | UNRECORDED | | | |
| D09 | Coverage threshold | Propose population automatic coverage >=.70, estimated from frame or probability weights. | Measures operational usefulness without quota distortion. | Human-assisted workflow; domain-specific coverage target. | Coverage pressure can reduce safety; enriched sample coverage is invalid for population claims. | Supervisor | UNRECORDED | | | |
| D10 | Insufficient predicted positives | Return INSUFFICIENT EVIDENCE for undefined/inadequate positives or independent clusters; preapprove fixed extension before labels, otherwise stop. | Avoids optional stopping and false confidence. | Approved sequential design; descriptive-only validation. | A nominal 200 records does not guarantee a precision claim. | Supervisor + statistical reviewer | UNRECORDED | | | |
| D11 | Agreement threshold | Propose pre-adjudication nominal multiclass human-human kappa >=.80 where estimable, with raw/per-class agreement and uncertainty. | Checks reliability of reference labels. | Class-specific agreement criteria; revised reliability target. | Kappa is prevalence-sensitive and may be undefined. | Supervisor + statistical reviewer | UNRECORDED | | | |
| D12 | Rubric freeze conditions | Resolve technical findings, approve rules/keys/design, complete blinded validation and signed gate decision, then archive exact revisions before any held-out answer access. | Prevents confirmatory tuning and incompatible reuse. | Delay freeze pending additional development evidence. | Changes after confirmation require new revision and independent confirmation. | Supervisor + independent reviewers | UNRECORDED | | | |
| D13 | Technical findings disposition | Authorize separate repair/review of superscript normalization and curly-attribution mismatch before a judge-acceptance decision. | Verified current behavior contradicts supported-form documentation. | Explicitly restricted domain with externally justified safety review. | Scope restriction alone cannot ensure unsupported forms are safely rejected. | Supervisor + independent technical reviewer | UNRECORDED | | | |
| D14 | Provenance and revocation | Controlled evidence/event ledger, final manifest authority, append-only revocation and supersession records. | Replay cannot authenticate inputs or reviewers. | Externally managed registry. | Historical dirty-tree provenance and duplicated signatures remain qualified. | Supervisor + data steward | UNRECORDED | | | |

## 3. Thematic P01–P14 → authoritative entry crosswalk

Mappings below mean substantive overlap supported by the named decision wording,
not that a D-row grants authority over the whole thematic proposal. “Broader only”
means **no direct D01–D14 decision exists for that requirement**; its authority is
the original package/November corrections. IDs P01–P14 refer only to the local
Downloads draft. They are not renumbered as D01–D14.

| Local proposal / subject | Direct D-entry overlap | Requirement outside D01–D14 / reconciliation in proposed protocol |
|---|---|---|
| P01 Research questions, hypotheses, primary contrast, estimands | None directly; D12 only overlaps judge freeze prerequisites | Original Document 1 §§1–3; corrections ¶23,28,35. Protocol §§2,11–13 choose primary E4/fabricated/budget-1 and explicit inference family. Eligible-case scope includes failures but unresolved outcomes are not coded as zero. |
| P02 False-claim keys/provenance | D01 claim types; D02 time; D03 expressions; D04 approval; D14 provenance/revocation | Protocol §§4–5 retain complete reviewed expressions, raw text and independent final-digest authority. General evidence authenticity also requires the broader provenance-policy decision. |
| P03 Judge-v2 rubric | D01–D03 claim/time/paraphrase rules; D12 rubric freeze; D13 technical disposition | Local label taxonomy conflicts with actual v2. Protocol §11 retains CORRECT/POISON_ADOPTED/OTHER_WRONG/NEEDS_REVIEW and separate reason/abstention fields; no implicit matcher expansion. |
| P04 Blinded validation/acceptance | D05 population; D06 allocation; D07 human procedure; D08 precision/rejection; D09 coverage; D10 insufficiency; D11 agreement; D12 freeze | Local lower-bound-only criterion is incomplete. Protocol §6 restores all proposed gates, reports feasibility and requires supported cluster/weighted uncertainty. Human-only main judging would require a distinct prospective decision, not automatic fallback. |
| P05 Evidence authenticity/admissibility | D02 only for time scope of key expressions; D14 only for provenance authority | Entire 400-frame evidence policy is broader: corrections ¶11–15,37,44; Original Document 4 provenance/derived-key questions. Protocol §4 uses explicit reconstructed claims and independent acceptance, not authenticity by hash. |
| P06 Independent review/adjudication | D04 for claim-key approval; D07 for judge-validation raters | General benchmark dual review is separately required by corrections ¶13,15,44. Protocol §5 distinguishes key, evidence and judge-validation review roles. |
| P07 Exposure/leakage exclusions | D05 only for development validation population | Confirmatory benchmark exposure is broader: corrections ¶17,20,35 and Original Document 4 exposure policy. R1 protocol §7 excludes confirmed development exposure, including construction review; uncertain exposure is excluded until independently resolved as unexposed. No scenario-C exception. |
| P08 Benchmark membership/strata/reserves | None directly; D06 is judge-validation allocation, not main-benchmark N | Corrections ¶14,17,20,37 and Original sampling-authority/sample-size questions. Protocol §7 retains existing rank lineage and same-stratum reserves without a fresh shuffle. |
| P09 Family eligibility/temporal intent | D02 overlaps key temporal qualification only | Corrections ¶18–19 and original attack design. Protocol §§4,8 defines family-specific denominators and independent intent labels. |
| P10 Matched/date controls | None directly | Corrections ¶23–24, Original Document 1 §5. Protocol §§8,10 preserves paired identity/body policy, metadata negative controls and BM25-refit qualification. |
| P11 RQ3 factorial | None directly | Corrections ¶26 and Original Document 1 §6. Protocol §9 selects the order-averaged interaction as supporting confirmatory, conditional on sizing; other factorial effects descriptive. |
| P12 Statistical inference | D06,D08–D11 only for validation allocation/uncertainty/thresholds | Main estimands/tests/multiplicity require corrections ¶28,35 and Original inference question. Protocol §12 does not claim synthetic sign-flips or validation thresholds approve real analysis. |
| P13 N/compute/datasets/transfer | D06 only for validation sample size | Main sizing/roles/transfer are broader: corrections ¶17,28–29, Original Document 4 size/transfer/scope questions. Protocol §§13–14 provides conditional workload and sizing scenarios, not accepted N or resources. |
| P14 Freeze/execution authorization | D12 rubric freeze; D14 authority/revocation | Scientific G1–G4 and runtime authorization are broader: corrections ¶35,37,39,41,48. Protocol §15 keeps development/preflight and main authorization separate. |

## 4. D01–D14 proposed disposition requests and closure evidence

These are W6-D1 recommendations for consideration, not entries in the authoritative
Decision/Date/Signature columns. Status for every row remains UNRECORDED.

| ID | W6-D1 recommendation and protocol location | Evidence/decision still required |
|---|---|---|
| D01 | Adopt narrow complete-expression domain, no numerical inference (§§5–6). | Independent technical/domain acceptance of supported forms and rejection suite. |
| D02 | Require explicit question-time/effective-time review; unresolved scope held (§§4–5). | Temporal reviewers establish truth and scope, independent of raw timestamp ordering. |
| D03 | Permit only independently reviewed complete expressions created before confirmation answers (§5). | Collision/paraphrase review and exact frozen expression set; exposed derivation excluded from confirmation. |
| D04 | Supervisor/named delegate approves final digest after two reviews and adjudication (§5). | Named approver, authenticated ledger and final-digest countersignature/verification. |
| D05 | Existing reconciled development StreamingQA only; applicability restricted to genuine keyed claims (§6). | Stable-ID reconciliation and actual eligible frame; separate authorization if expansion needed. |
| D06 | Keep conditional 200 with 80/40/40/40 allocation and deterministic shortage handling (§6). | Actual per-stratum counts and inclusion probabilities n_h/N_h (analysis weights N_h/n_h) before reference labels; no promise of 80 positives. |
| D07 | Independent blinded dual ratings and third adjudicator, retain unresolved (§§5–6). | Named reviewers, independence declarations, calibration, locked initial ratings and audit trail. |
| D08 | Preserve zero synthetic false-adoption criterion, ≥.95 precision and one-sided 95% lower bound ≥.90 (§6). | Repaired-code technical acceptance and defensible unresolved/cluster-aware interval; local P04 alone is insufficient. |
| D09 | Preserve ≥.70 population automatic coverage (§6). | Full admitted frame or defensible weights; no enriched-sample substitution. |
| D10 | Insufficient evidence for inadequate positives/clusters/uncertainty; no optional extension (§6). | Propose ≥30 positive-question clusters as additional planning floor, not an original requirement or guarantee; exact extension authorized before labels. |
| D11 | Preserve pre-adjudication multiclass kappa ≥.80 where estimable, with raw/per-class agreement (§6). | Qualified dual ratings and uncertainty; undefined/unstable reliability cannot pass by assertion. |
| D12 | Sequential rule/key/design acceptance → validation → signed rubric freeze before held-out access (§15). | Signed exact-revision gate and evidence of access separation; separate main execution authorization. |
| D13 | Submit existing A6/A8 repairs and W6-J1 engineering integration for independent technical disposition (§6). | External reviewer accepts or revises repairs and literal active-path requirement; engineering tests do not record this decision. |
| D14 | Controlled ledger, independently provisioned trust and append-only revocation/supersession (§§5,15). | Name actual custodian, trusted approvers and revocation verification before any real provider implementation. |

### Validation threshold reconciliation

Each source below is an authoritative **decision request**, not an accepted
threshold. The original table, owners and alternatives in §2 remain unchanged.
Comparison is against current protocol §6; the local Downloads P04 lower-bound-only
proposal is incomplete and does not override D08/D09/D11. No criterion is claimed met.

| Criterion / source | Current v1 protocol comparison | Frame / required sample size if known | Feasibility limitation and proposed resolution |
|---|---|---|---|
| Supported claim types/time/paraphrases — D01–D03 | Same narrow complete-expression proposal, explicit temporal review and no numerical inference. | Independently reviewed applicable keys/expressions for each intended claim domain; no fixed validation N in these rows. | Unsupported domains cannot inherit acceptance; restrict scope and refer ambiguity to review, or obtain a separate prospective validation decision. |
| 200 unique inputs, 80/40/40/40 allocation — D06; development frame — D05 | Retained as conditional target, with shortages censused and residual allocation fixed before human labels. | Reconciled existing development StreamingQA; exclude legacy/held-out outcomes and answer-informed confirmation keys. 200 inputs and 80 predicted positives are targets, not established availability or sufficient N. | 992 historical rows/298 question-answer pairs are not eligible keyed inputs; only three questions supply candidate false-claim diversity. Publish actual keyed frame/strata/clusters first; report shortfall or seek a fixed authorized development extension under D05/D06/D10. |
| Two independent blinded raters, third adjudicator — D07 | Retained; initial labels, disagreements and unresolved references preserved. | Every sampled input; at target N=200 this means 400 independent initial ratings, plus disjoint calibration and adjudication as needed. | Named independent reviewers and genuine blinding not established. Resource their roles before labeling; no self-review or synthetic labels as reference. |
| Zero synthetic rejection false positives — D08 | Retained; also no unresolved critical false-positive defect, an added safety proposal consistent with D13 review. | Entire prespecified synthetic rejection suite; D08 gives no fixed suite N. Synthetic tests never enter natural precision denominators. | A6/A8 repairs and W6-J1 engineering tests are not independent scientific acceptance. Fix suite/revision scope prospectively and obtain D13 technical disposition; a known critical failure blocks acceptance. |
| Poison precision ≥.95 — D08 | Retained; local P04 did not include this point criterion. Resolvable precision and conservative unresolved-positive bounds are both reported. | Applicable independently keyed development predicted positives with blinded human references; no sufficient N specified in D08. | Repeated questions and unresolved references prevent IID precision claims. Retain point criterion plus interval criterion; unknown reference positives count as errors in conservative gate evaluation. |
| One-sided 95% precision lower bound ≥.90 — D08 | Retained alongside point precision, weighted/cluster dependence and unresolved sensitivity, not substituted by an arbitrary two-sided bound. | No universally sufficient N known for current weighted/clustered frame. Existing blinded protocol's mathematical IID illustration: 29/29 yields lower bound about .9019; at 80 positives 77/80 about .9059, whereas 76/80 about .8892. These are not achieved results or valid three-question evidence. | Interval must be accepted for the actual sampling/dependence structure before unblinding. No row bootstrap, repeated-question binomial bound, favorable post-hoc method or optional expansion. Unsupported/degenerate uncertainty means INSUFFICIENT EVIDENCE. |
| Population automatic coverage ≥.70 — D09 | Retained; enriched-sample non-review fraction is explicitly inadmissible. | Prefer full admitted applicable development frame; otherwise known selection probabilities and weighted estimates. No required frame N or lower-CI coverage threshold is specified in D09. | A 40/200 review quota predetermines .80 sample coverage without estimating population coverage. Use full-frame numerator/denominator, report uncertainty if generalized; do not invent an extra confidence-bound release rule without decision. |
| INSUFFICIENT EVIDENCE / fixed extension only — D10 | Retained for inadequate positives/clusters, unsupported uncertainty and missing required domains. | No numerical minimum in D10; a nominal 200 is not sufficient by itself. | Stop rather than replace positives, borrow holdout data or repeatedly enlarge until passing. Approve any fixed extension before reference labels. |
| Pre-adjudication nominal multiclass kappa ≥.80 where estimable — D11 | Retained, with raw/per-class agreement, uncertainty and unresolved rates. | All independently double-rated sampled inputs, with question dependence respected; no kappa-specific sufficient N or lower-CI gate specified in D11. | Undefined/prevalence-sensitive kappa or sparse classes cannot establish reliability. Report the limitation; obtain prospective alternative criterion/allocation if needed, never report adjudication agreement as independent reliability. |
| At least 30 distinct predicted-positive question clusters — **our proposal**, not D10 wording | Retained as a conservative planning floor additional to, never a substitute for, D08 uncertainty. | At least 30 applicable positive-question clusters in the proposed validation design; source dependence may reduce effective independence further. | Current three-question diversity cannot meet it. Supervisor/statistician may revise the floor prospectively; no claim it guarantees .95 precision or .90 lower bound. |
| 10,000 question-cluster replicates and two-sided 95% reporting intervals — existing proposed P0-A5 blinded protocol, not D01–D14; appropriate survey replication where needed — our implementation specification | Carried forward as computational/reporting specification, not a scientific acceptance threshold. | Accepted sampling frame, inclusion probabilities n_h/N_h, weights N_h/n_h and enough independent clusters; number of replicates is not sample size. | Review weighting/replication assumptions before unblinding. More replicates cannot manufacture information; unsupported intervals remain insufficient. |
| Signed rubric freeze after validation — D12; technical disposition — D13; provenance authority — D14 | Retained as qualitative gates; no reported test count automatically passes them. | Exact revision, accepted keys, authentic authority, independent validation and actual signed decision. | None is established by this document; future real route stays disabled until scoped authority exists. |

The illustrative independent-binomial values above are quoted from
[the existing proposed blinded protocol](supervisor_review/p0_a5/blinded_judge_validation_protocol.md),
not newly computed observations. Main-study .10 meaningful effect, .80 power,
primary/supporting alpha .05 and at least 30 independent analysis components are
separate **our-proposal** planning/inference choices in protocol §§2,12–13; they
are not judge-validation thresholds from D01–D14 and do not establish main-study N.

## 5. Conflicts, omissions and explicit review questions

| Issue | Reconciled proposal / remaining external action |
|---|---|
| Local P numbers resemble authoritative D numbers | Keep both namespaces; exact table in §2 is authoritative. No fabricated one-to-one mapping. |
| P03 proposes FALSE_CLAIM_ADOPTED/NOT_ADOPTED/ABSTAIN | Protocol §11 maps each term explicitly to the canonical v2 schema or flags non-equivalence. Current automatic OTHER_WRONG covers only pure abstention/empty; unmatched wrong assertions remain NEEDS_REVIEW. Human other-wrong and UNRESOLVABLE references remain separate; no historical outcome is rewritten. |
| P04 omits precision point/coverage/agreement thresholds | Retain all original proposed D08/D09/D11 criteria pending supervisor/statistician disposition; neither version is accepted. |
| D08/D13 historical wording says technical failures remain open | A6/A8 provide engineering repairs, not external closure; retain exact historical text and submit repairs for independent review. |
| Literal corrections ¶5 and ¶43 name `src/eval/answer_judge.py` and ¶43 also names `docs/week6_judging_protocol.md`; W6-J1 is standalone fiction-only v2 | Preserve frozen v1 behavior/results and use explicit versioned contracts, input provenance and authoritative replay. Request written supervisor acceptance of this literal-path deviation and future real route, or revised instructions. Acceptance is pending; hashes/fixture admission do not authorize real cases. See protocol §6. |
| Earlier W6-D1 preferred governed-construction scenario C | R1 replaces that choice with confirmed-development-exposure exclusion and uncertainty holds (scenario-B logic). All 116 recorded confirmed-activity IDs are proposed exclusions; the other 284 remain excluded until independently resolved, with source-scope exclusions separately retained. No construction exception or accepted members are invented. |
| Starter seeded shuffle versus later original-rank preservation | Verify lineage once; retain existing order, no reshuffle. Unreconciled order blocks membership until supervisor disposition. |
| RQ3 local P11 says effects exploratory unless powered; original names interaction supporting confirmatory | Propose only the named order-averaged interaction in the gated supporting family; power/cluster feasibility prerequisite. If inadequate, obtain a prospective exploratory-only disposition before execution. |
| P1-B equal allocation versus unequal header token lengths | Preserve concrete rendered intervention, measure lengths/retention; make no pure semantic or equal-token claim. Extra matching study would need a separate prospective definition. |
| P1-C 2,000 bootstrap draws and sign-flip implementation versus proposed real inference | W6-D1 proposes 10,000 draws and valid exact-pair/cluster tests; real statistical adapter and assumption checks remain engineering/review gaps. Existing factorial two-way scaling already matches the order-averaged endpoint and needs no extra division. |
| Existing development frame lacks independent claim diversity | No guarantee of 200 keyed inputs/80 positives/30 positive clusters; do not count repeated answers as independent. Stop or approve new development-only collection before labels. |
| FreshQA 474/477; TriviaQA IDs; new claim domains | Resolve membership/build lineage, ID/exposure and key/judge applicability before those roles execute. No synthetic conversion or three fabricated records. |
| W6-J1 fixes an integration checkpoint, local draft says build it | Update current-state description: fixture offline path is complete; authenticated real admission and production dispatch remain missing. Preserve W6-J1 unchanged. |
| Older README/transition/P1-C3 says original source missing/unseen | Source now exists and was read; treat those statements as historical. Publication/commit status is not approval. Do not rewrite source documents in W6-D1. |
| Resource/power choices lack measured inputs | .10 effect, .80 power, 300/100 caps and 100+10 GPU-hour request are proposals; approve sizing/compute worksheet after authorized development measurement. |

## 6. Broader scope inventory — not additional D-IDs

Original Document 4 contains these fifteen questions. They retain their own source
wording below; no new authoritative IDs or dispositions are assigned.

| Original question | W6-D1 location / requested confirmation |
|---|---|
| Preserve STRONG scope? | Protocol §§1,13–14: three datasets/E1–E4/second family retained with conditional roles/budgets. |
| Approve attack estimand hierarchy? | §§2,11–12: E4 primary and gated supporting family. |
| Primary ASR denominator? | §11: all frozen family-eligible questions; clean-correct secondary, failures retained. |
| Approve RQ3 isolation? | §§9–10: direct eight-cell input and order-averaged interaction. |
| Preserve defense components/ablations? | §1: original five and RQ4 retained for Weeks 7–8. |
| Provenance policy? | §4: independently accepted reconstructed representations with qualified claims. |
| Derived keys? | §§4–5: separate adjudicated layer, immutable originals. |
| Review independence? | §§5–6: separate authors/reviewers, dual review and third adjudicator. |
| Exposure policy? | §7: confirmed development exposure excluded; uncertain exposure excluded until independently resolved as unexposed; accepted evidence/keys also required. |
| Sampling authority? | §7: reconciled original rank, same-stratum reserves, no outcome selection. |
| Sample size? | §13: prospective paired-effect/precision worksheet, actual eligibility/components and caps. |
| Confirmatory inference? | §§2,12: gated family, paired/component-aware methods, missingness bounds. |
| Transfer scope? | §§13–14: smaller second-family RQ3 study and outcome-independent subset. |
| Clean-utility margin? | §§1,12: unresolved defense decision; no noninferiority claim in Week 6. |
| Freeze sequence? | §15: scientific G1–G4 with separate limited development preflight permission. |

Supervisor action requested: separately record actual disposition, scope, rationale,
conditions, named authority and date through the controlled process. Approving one
row does not approve the others, accept the benchmark or authorize a run. This
register does not solicit or fabricate a blanket scientific approval.

The execution sequence is protocol §15's eight-step path: proposal/review → independent
evidence/key adjudication → synthetic engineering → independent blinded judge
validation → authorized accepted-development backend preflight → final freeze/main
authorization → main attacks/RQ3 → confirmatory analysis/reporting. Engineering and
review can overlap safely; no confirmatory reporting uses an unvalidated judge.
