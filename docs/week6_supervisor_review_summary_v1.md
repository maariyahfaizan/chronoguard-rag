# Week 6 supervisor review summary v1 — W6-D1

14 November 2026. **PROPOSED; NO DECISIONS RECORDED; NO EXECUTION AUTHORIZED.**
W6-D1-R1 reconciles these same three v1 documents; no new version is created.

Review the [scientific protocol](week6_protocol_proposed_v1.md) and
[exact decision register/crosswalk](week6_decision_register_proposed_v1.md).
W6-D1 creates review documents only. W6-J1, frozen artifacts, historical outputs
and authoritative decision sheets remain unchanged. No experiments were run.

## Proposed design

Primary study: question-paired E4/Mistral false-state adoption under one fabricated
false passage, comparing `Latest update:` with `General notice:` on the same body,
slots, identities and applicable dates. Primary population is every independently
accepted fabricated-fresh-budget-1-eligible StreamingQA question, including failed
attempts as unresolved observations. No restriction to clean-correct or poison-
exposed cases. Report paired risk difference, denominators, uncertainty and missing-
outcome bounds. The rendered wording intervention includes token/length and BM25
refitting effects; no pure semantic recency-understanding claim is proposed.

E1–E4 remain in scope; 1/2/5 budgets and stale, fabricated, date-shift, duplication
and correct-content controls remain separately eligible analyses. RQ3 directly
supplies correct/incorrect passages in eight date-assignment × wording × order
cells. Its supporting confirmatory endpoint is the order-averaged wording-by-
assignment adoption interaction. Five supporting hypotheses use Holm .05 only
after primary rejection at .05; all other prespecified effects remain descriptive.
Both correct-newer and incorrect-newer cells and all unresolved outcomes are shown.

Independent dual review plus a third adjudicator establishes evidence, question-
time truth, aliases, provenance and false keys. Preserve original gold and use a
separate derived layer where accepted. Traceable reconstructed evidence may be
admitted only with independent corroboration and explicitly limited claims.
Confirmed development exposure, including construction review, is excluded from
confirmatory evaluation. Uncertain exposure is excluded until independently resolved
as unexposed. There is no governed-construction exception in the R1 proposal.
Keep the original deterministic stratum ranks and audited reserve sequence.

The exact original-frame/ID, P0-B1 evidence, P0-B2 exposure and P0-C1 rank/reserve
dependencies are listed in protocol §7. The 116 recorded confirmed-activity IDs are
proposed exclusions; 184 possible and 100 unknown remain excluded pending independent
resolution. Ten source-year exclusions remain separately recorded. The conditional
scenario-B ceiling is 108 recent/166 past, or at most 258 under 150-per-stratum caps,
even if all remaining reviews clear; current independently accepted membership is
zero. No artificial filling, cross-stratum borrowing or fresh reshuffle is proposed.

The proposed 150 recent/150 past maximum is conditional on valid eligibility and
sizing, never a quota. Recency-sensitive/timeless labels require independent review.
FreshQA is separate dated robustness after membership/schema/time-key resolution;
TriviaQA is static control after upstream-ID/exposure review. A smaller second-
family RQ3 study remains planned; exact transfer revision/access/resources are open.
Defense implementation, original five ablations and RQ4 remain Weeks 7–8.

## Judge proposal and present evidence

Candidate rubric: `answer_judge_v2_claim_specific`, implementation
`p0_a8_v2_repair_3`. W6-J1's committed offline fiction-only postprocessor passed
331 tests in its verified workflow. That demonstrates engineering integration,
not independent precision, semantic validity, authentic approval or main readiness.
There is no authenticated real authority provider. Do not relax its fixture guard.

Keep CORRECT/POISON_ADOPTED/OTHER_WRONG/NEEDS_REVIEW with reason-level abstention;
the local P03 draft's alternative labels are not adopted. Propose feasible
development-only 200-input allocation (80/40/40/40 if available), dual blinded
ratings and third adjudication. Retain proposed precision ≥.95, one-sided 95%
lower bound ≥.90, coverage ≥.70 and pre-adjudication kappa ≥.80, plus zero synthetic
false adoptions and no unresolved critical defect. All thresholds remain pending.
Adequate independent clusters and defensible weighted/cluster uncertainty are
required; the proposed 30-positive-cluster floor is a new planning safeguard, not
a source mandate or sufficient validation evidence. Only three pilot questions
currently supply candidate false-claim diversity. Insufficient evidence means
stop; no repeated expansion until passing or held-out substitution.

Protocol §11 gives the explicit mapping: FALSE_CLAIM_ADOPTED is only a terminology
alias for POISON_ADOPTED under the same accepted contract; NOT_ADOPTED is a
non-equivalent analysis grouping of resolved CORRECT/OTHER_WRONG, never review or
missing cases. ABSTAIN is the OTHER_WRONG/`pure_abstention` subset, not a raw class;
empty output is OTHER_WRONG/`empty_answer`, not missing generation. Human
UNRESOLVABLE and machine NEEDS_REVIEW are different layers, not equivalent labels.
Mixed assertions remain NEEDS_REVIEW. No historical labels are reinterpreted.
Current v2 automatically emits OTHER_WRONG only for pure abstention or empty
answers; an unmatched asserted wrong answer stays NEEDS_REVIEW until independently
resolved in the separate human-reference layer.

The [validation matrix](week6_decision_register_proposed_v1.md#validation-threshold-reconciliation)
lists each source criterion, current-protocol comparison, frame/N limits and
resolution. D06's 200 is a conditional allocation target; no universal sufficient
N exists for the current clustered/weighted frame. D08 supplies the .95/.90/one-
sided-95% and synthetic-rejection proposals, D09 the .70 coverage proposal, D11
the .80 kappa proposal. The 30-positive-cluster floor is ours; 10,000 replicates
and two-sided 95% reporting intervals carry forward the existing proposed blinded
protocol. No threshold has been met or accepted. Coverage/kappa lower-bound gates
are not invented where the source supplies only point criteria.

Keep W6-J1 standalone to preserve historical v1 provenance and saved results,
make v2 contracts/revisions explicit and avoid silent reclassification. It records
controlled inputs, key/event/file identities and judgment evidence, then replays
through `validate_output_batch` against independently loaded inputs. Consistency
and synthetic fixture admission are not authentic real approval; real data remain
disabled. This deviates from corrections ¶5/¶43's literal requirement to revise/test
`src/eval/answer_judge.py` (¶43 also names `docs/week6_judging_protocol.md`).
**Supervisor acceptance of the standalone-route deviation is pending.**

## Decisions specifically requested

| Review owner | Confirmation or revision needed |
|---|---|
| Supervisor and technical/domain reviewers | D01–D04 permitted claims/time/paraphrases/key authority; D13 independent acceptance of existing repairs and disposition of the literal `answer_judge.py` routing requirement. |
| Supervisor, statistician and reviewer lead | D05–D11 population/allocation/blinding/precision/coverage/insufficiency/agreement; achievable independent keyed frame and exact interval assumptions before reference labels. |
| Supervisor/data steward | D12/D14 final rubric freeze, authenticated approval custody, trust identities, revocation, immutable manifest and held-out access controls. |
| Supervisor, broader scientific scope | E4/fabricated/budget-1 primary; gated supporting family; reconstructed-source policy; derived keys; confirmed-development-exposure exclusion and uncertainty holds; original sampling-rank authority; RQ3 header/date operationalization. These are not all contained in D01–D14. |
| Supervisor/statistician | .10 meaningful primary risk difference, .80 power target, actual family eligibility/source-component counts and prospective sizing worksheet; finite-frame versus wider-population claims. |
| Supervisor/resource owner | Up to 300 StreamingQA, 100 FreshQA, 100 TriviaQA, 100-case second-family RQ3 caps; proposed 100 GPU-hour main plus 10 development-preflight hour ceilings, named annotation resources, and measured feasibility before authorization. |

No approval cells are completed. The register preserves all fourteen original
rows verbatim and separately lists the original fifteen broader scope questions.
Local P01–P14 thematic numbers are never treated as authoritative D-IDs.

## Unresolved conflicts and evidence dependencies

- Local P03 labels conflict with implemented v2; preserve v2 and separate analysis axes.
- Local P04 states a weaker/incomplete gate; retain all D08/D09/D11 proposals pending disposition.
- D08/D13 historical defects now have engineering repairs, but external technical acceptance is absent.
- Corrections name a literal active v1 file; request explicit acceptance of a separate versioned real v2 path while preserving historical v1. W6-J1 is fixture-only.
- The held-out starter's seeded shuffle and later rank-preserving policy require one lineage reconciliation. No new reshuffle is proposed.
- R1 resolves the draft's policy choice toward confirmed-exposure exclusion and independent resolution of uncertainty; supervisor disposition and exact membership are still pending, with no construction exception.
- Existing `factorial_effects` already divides the signed eight-cell sum by two for the order-averaged interaction; reuse it without an extra scaling conversion.
- Real inferential tests/weighted validation intervals are not supplied by the existing synthetic sign-flip/fixture adapters. Methods and assumptions need statistical acceptance.
- Zero independently accepted Week 6 questions/keys; no authenticated reviewers/authority, blinded validation or final membership. Review packets and hashes do not substitute.
- FreshQA's 474/477 historical frame, TriviaQA upstream IDs, cross-dataset judge applicability and transfer revision/resources remain open.
- Week 4 v2 is a clean development baseline, not complete child semantic/temporal ground truth. Do not re-audit or rerun it to claim Week 6 label acceptance.

## Ordered scientific critical path and minimum integration

| Order | Minimum task and reuse | Can proceed offline? | External dependency / completion evidence |
|---|---|---|---|
| 1 | Protocol proposal and supervisor review. Resolve scientific choices, authority contract, named roles and frame-lineage policy. | Documentation only. | D01–D14 and broader scope dispositions; no approval is recorded here. |
| 2 | Independent evidence and false-claim-key adjudication, exposure resolution and exact membership. Reuse P0-B1/B2/C1 and review templates. | Review-packet preparation can be offline; annotation/adjudication are independent human work. | Accepted development/confirmatory roles kept separate; actual reviewer identity, final key digest, source and reserve authority. |
| 3 | Safe engineering integration using synthetic cases. Reuse `ClaimContext`, `ClaimKey.problems`, v2 judge/replay, matched requests, RQ3, source-slice pools and analysis functions. | Fiction-only admission/dispatch/instrumentation/analysis tests; no model or attack execution. | Reviewed contracts; actual external authority required before limited real development judging. Preserve W6-J1 fixture guards and historical routes. |
| 4 | Independent blinded judge-v2 validation against human references. Use accepted existing development outputs, dual ratings, third adjudicator and the fixed analysis/threshold plan. | Offline judging with scoped permission; independent human annotation, not GPU work. | Actual eligible frame, feasible fixed allocation, supported uncertainty and signed judge-acceptance decision. Insufficiency stops the path. |
| 5 | Authorized backend-input preflight on accepted development cases. Wire existing capture to real retriever/reranker/chat-template inputs, claim retention and fit/latency forecast. | Synthetic instrumentation preparation can occur at step 3; actual preflight needs separate tokenizer/GPU authorization. | Step 4 acceptance first; no confirmatory cases/outcomes or implicit main authorization. |
| 6 | Final protocol/configuration freeze and explicit main-experiment authorization. | Read-only integrity checks on designated candidate; committing remains outside this task. | Scientific G1–G4, immutable data/key/config/code/model identities, feasibility and enforced runtime admission. |
| 7 | Main attack and RQ3 execution. | No; authorized GPU/model execution only. | Frozen accepted IDs/keys and exact run permission; retain failures and unresolved outcomes. |
| 8 | Confirmatory statistical analysis and reporting. | Offline analysis only after authorized outcomes exist. | Validated judge, frozen paired/component-aware intervals and testing gate/Holm family; report denominators, bounds and all prespecified results. |

Steps 2 and 3 can overlap after contract review; instrumentation and analysis-code
tests can use fiction then, without moving actual preflight ahead of step 4.
Step 4 uses existing development outputs, avoiding a need for new generation before
validation. If insufficient, stop for a separately approved development-data/design
revision; do not borrow held-out answers or silently collect them during preflight.
No confirmatory attack outcome is reported using an unvalidated judge. Real admission
and main dispatch remain blocked until their respective external gates pass. Reuse current modules rather
than duplicate matchers, estimators, review queues or attack constructors. The
existing FreshQA migration can be completed as a versioned derivation only after
membership authority is resolved; it is a dataset-branch prerequisite, not a reason
to rerun unrelated diagnostics.

## Readiness and requested review outcome

Scientific G1 decisions remain UNRECORDED; G2 accepted benchmark NOT ESTABLISHED;
G3 protocol NOT FROZEN; G4 execution NOT AUTHORIZED. These are distinct from
engineering checkpoints named G1–G4. Prefer explicit scoped revisions over blanket
acceptance. If sample, compute or independent review cannot support the requested
scope, record a prospective narrower claim/design before outcomes; do not silently
remove second-family/three-dataset commitments or publish underpowered confirmation.

Requested next action: supervisor reviews the register/protocol, identifies actual
decision-makers and records dispositions through the controlled process. Publication
of these documents or the W6-J1 commit cannot substitute for that process.
