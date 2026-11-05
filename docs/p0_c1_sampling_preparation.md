# P0-C1: deterministic sampling and exposure-policy preparation

PRE-FREEZE engineering preparation. Every scenario and simulated record is
**NOT_FINAL_NOT_APPROVED**. No exposure policy, eligibility rule, sample, reserve
replacement, temporal-intent label or scientific decision is approved here.

## Pinned inputs

The original frame and B1 manifest contain exactly the same 400 IDs and original
stratum/reserve rank: 200 recent and 200 past. B1 manifest SHA-256 is
`317fd7c4652fd6d62614d064b2f6c673405323b32d78062acc95ae295a802b44`.
B2 checksums-file SHA-256 is
`1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0`.
Generation stops on a mismatch. All B1/B2 source and output hashes are checked;
the existing authoritative B2 revalidation also revalidates B1 and the closed
reconstruction snapshot. Existing artifacts remain unchanged.

Source scope excludes the ten past questions already explicitly marked 2007 /
outside configured 2008–2020 archives. This is not a new global inadmissibility
judgment and does not silently replace those rows. All 400 remain in the outputs.
There are 150 original provisional priorities per stratum, 50 recent reserves,
40 past reserves and ten scoped-out cases. These are review roles, not accepted
benchmark members. Original answer/alias lists, key hashes and source IDs persist.

## Three PROPOSED exposure alternatives

| Scenario | Proposed treatment | Actual C1 consequence |
|---|---|---|
| A_STRICT | Exclude confirmed recorded activity, possible exposure and unknown coverage conservatively | No policy-surviving cases |
| B_CONFIRMED_EXCLUSION_REVIEW_HOLDS | Exclude confirmed recorded activity; independently review possible/unknown cases | 274 source-available cases held, not eligible |
| C_GOVERNED_CONSTRUCTION_REVIEW | Distinguish governed construction-only review from outcome-driven tuning through independent purpose/authority evidence | All 390 source-available cases held pending that evidence |

Recorded development activity does not inherently establish disqualifying exposure.
A and B make that choice only inside their unapproved scenario. C does not infer
outcome-driven tuning from a screening label or infer construction-only use from
absence of outcome records. Its proposed future contract would exclude verified
outcome-driven tuning and permit governed construction-only activity through the
policy gate only with independent purpose evidence, no-outcome-access controls and
role/rule-tuning separation. The current CLI imports no purpose attestations;
every actual purpose is UNKNOWN. Synthetic tests exercise the future contract,
not real reviewer records or authority authentication.

NO_RECORDED_EXPOSURE is not proof of global non-exposure. B2 currently has no such
complete-coverage cases. Its 116 confirmed activity records split 92 recent / 24
past; possible cases split 58 / 126; unknown cases split 50 / 50, including the ten
scoped-out past cases. No row is excluded from a final benchmark by this preparation.

## Ordering, seats and reserves

No randomization is used: seed is NOT_APPLICABLE. Frame rows sort by original
stratum order (recent, past), original positive reserve rank, then stable QA ID.
Duplicate IDs/ranks are rejected. Within each stratum, the existing 150 priority
seats retain their identity/order. Replacements may use only the existing reserve
list, ordered by the same rank/ID rule. A past reserve never fills a recent seat.
No model answer, judge label, attack outcome, ASR or preferred semantic result is
an ordering input. Tests inject unused outcome fields and verify identical outputs.

Each simulation logs original seat ID, simulated ID or null, blocking reason,
every examined reserve, explicit replacement event and unused reserves. Source
scope exclusions are listed explicitly even when they were never priority seats.
An empty seat is reported with a same-stratum reserve shortfall, never silently
dropped or borrowed from the other stratum. The original frame is preserved.

Two cases are emitted per scenario:

1. CURRENT_REVIEW_READY: policy holds and unknown primary evidence admissibility
   remain blocked. All three scenarios have zero currently review-ready cases.
2. CONDITIONAL_ALL_HOLDS_CLEARED_AND_PRIMARY_ADMISSIBLE: a counterfactual ceiling
   assuming all held purpose/exposure reviews pass and all source-available primary
   unknowns become admissible. Hard scenario exclusions and source scope remain.
   For C, this additionally assumes independently established governed
   construction-only purpose. These assumptions are not review decisions.

No family is required to be eligible merely to count primary membership; primary
and condition-specific denominators remain separate pending scientific approval.

## Capacity, shortfalls and sensitivity

All capacities below are conditional engineering ceilings, not scientifically
available or statistically adequate sample sizes. Target 150 recent + 150 past
remains PROVISIONAL.

| Scenario | Conditional recent/past pool | Conditional priority recent/past | Conditional reserves recent/past | Target-bounded simulated recent/past | Shortfall recent/past |
|---|---|---|---|---|---|
| A | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 150 / 150 |
| B | 108 / 166 | 58 / 126 | 50 / 40 | 108 / 150 | 42 / 0 |
| C | 200 / 190 | 150 / 150 | 50 / 40 | 150 / 150 | 0 / 0 |

B's conditional simulation records 50 recent and 24 past reserve replacements;
42 recent seats remain unfilled and 16 past reserves remain unused. Its 274-case
pool cannot meet the stratified target: only 258 fit the two 150-seat caps.
C conditionally retains the original 300 priorities without replacements; this
does not approve their membership. Current simulations fill zero seats and have
150/150 shortfalls under every scenario. Current scientific evidence cannot
support a confirmed eligible sample even where a conditional capacity is large.

Missing semantic/temporal/provenance/key/pool review leaves all 390 source-available
primary cases UNKNOWN. Their primary usable-size range starts at zero. For each
attack family, the same conditional policy pool is only a loose upper bound if
every unknown family prerequisite also passes; it is not a claim that those
requirements can actually be met. No statistical power or adequacy is assessed:
there is no approved effect model, estimand, variance model or target precision.

## Separate attack-family schemas (PROPOSED rules only)

Every family has distinct prerequisite fields and an UNKNOWN/INELIGIBLE scope
status. Shared prerequisites are question-time gold/alias adjudication, semantic
support, temporal validity, source-provenance policy and candidate-pool integrity.

| Family | Additional proposed evidence requirements |
|---|---|
| Stale amplification | Reviewed obsolete claim, temporal contrast and approved false-claim key |
| Fabricated-fresh evidence | Reviewed false proposition, approved claim key, payload identity/threat model |
| Future-date metadata shift | Reviewed correct source, permitted date transformation, metadata-only pair integrity |
| Fresh-looking duplication | Reviewed correct source, duplication/date policy, duplicate identity integrity |
| Correct-content/wrong-date controls | Reviewed correct source, paired zero-day/wrong-date controls, matched content/slots/generation conditions |

For EACH family: 390 UNKNOWN, ten INELIGIBLE_CURRENT_SOURCE_SCOPE, zero verified
ELIGIBLE. `attack_success` is NOT_EVALUATED. Eligibility is not success; passing a
proposed exposure mask does not establish primary or family eligibility. Recent/
past is the original stratum, while independent temporal-intent labels remain
UNKNOWN/null for all 400. No temporal intent is inferred from those strata.

## Reproduction and output validation

```powershell
python -B -m src.eval.sampling_preparation --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_c1_v1
python -B -m src.eval.sampling_preparation --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_c1_v1 --validate-only
```

Generation refuses existing output directories and overlap with protected inputs.
Use a new path for reproduction. Source bytes are rehashed before publication.
Canonical ASCII JSON/LF, fixed role/rank/ID order and no clock make builds
reproducible; Unicode originals round-trip through escapes without alteration.
Validate-only rederives every record/report and validates the complete output
checksum set. It rejects changed IDs, keys, labels, eligibility, replacements or
approval flags. Output objects cannot mutate the pinned input context.

B2 prerequisite validation rereads historical review exports; the C1 sampling
rule projects only whitelisted frame/order/scope/exposure metadata. No held-out
attack outcomes are inspected and no new inference is performed.

Outputs under `audits/p0_c1_v1/`:

- `frame_order.jsonl`: all 400 IDs, original keys/source IDs, order and review roles.
- `eligibility.jsonl`: 400 primary/five-family readiness schemas and separate intent.
- `policy_scenarios.jsonl`: 1,200 records, one per frame ID per proposed scenario.
- `simulations.jsonl`: six labeled cases with explicit 300-seat/reserve ledgers.
- `feasibility.json`: scenario/stratum/family bounds and explicit shortfalls.
- `source_inventory.json`, `validation.json`, `sha256.json`.

Required scientific decisions include exposure definitions and governance evidence,
purpose attestations, semantic/temporal/key authority, provenance admissibility,
family-specific requirements, primary and condition-specific denominators,
stratified targets, stopping/replacement rules and a justified adequacy model.
The fourteen existing supervisor decisions remain UNRECORDED and unchanged.
No original key, B1/B2 artifact, scientific policy or frozen record is modified.
No final sample, human judgment, main attack, staging, commit or push is produced.

## Checkpoint checks and integrity

The final source inventory pins 143 input records. Both independent builds were
byte-identical; final authoritative re-derivation, all output checksums and the
400/400/1,200/six row counts passed. Every simulated row is labeled
NOT_FINAL_NOT_APPROVED. All B1/B2 source/output hashes remain unchanged.

```powershell
python -B -m pytest -p no:cacheprovider tests/test_sampling_preparation.py tests/test_review_authority_audit.py tests/test_evidence_admissibility.py tests/test_prepare_week6_review_queue.py tests/test_evidence_identity.py tests/test_answer_judge.py tests/test_answer_judge_v2.py -q --basetemp=.venv/.tmp_p0_c1_final_tests
```

Result: **396 passed in 20.04s**, including 25 new C1 cases. They cover ordering,
duplicates/ranks, source-scope exclusion, shortfalls, explicit reserve events,
unapproved labels, UNKNOWN handling, exposure/eligibility separation, outcome
independence, preserved keys/IDs, synthetic future-governance contracts and
rejection of unsupported approval or temporal-intent promotions.

Before/after integrity: all 279 protected repository files retain inventory SHA-256
`5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310`.
All 56 recovery-project files retain inventory SHA-256
`f24c89901d5e525192fec1d7b3aae3d6badab50139171e62ad4d3713e15aa79f`.
All 23 published engineering-candidate raw hashes, B1/B2 outputs and fourteen
UNRECORDED decision rows remain unchanged. No Git mutation was performed.

Exactly one recommended next checkpoint: **P0-C2 — supervisor disposition of the
proposed exposure/governance and eligibility rules, with explicit review and
feasibility requirements before any final selection.**

## Exact output hashes

| File | SHA-256 |
|---|---|
| `eligibility.jsonl` | `48fcdc9a2e7fe73cc2d851fa9f2cccde077512b579f07716011235027907a323` |
| `feasibility.json` | `18b9fb008874071fd283d44013deb12a52f2d6c2b117afff2ed0264a3f3a7154` |
| `frame_order.jsonl` | `24810ceeffdb4771fb7f1074d16957e6fc31c50a3b29ef978a4238584662113c` |
| `policy_scenarios.jsonl` | `bfe10ed83a4e10ce37c1a91f9fd6f02af928266d17996552357d977c2920e06f` |
| `sha256.json` | `df70bbdacffd7304d6f2f661e08c445eb4301cd44ceb9ffd384c6a1d1fcacacb` |
| `simulations.jsonl` | `4ac9828c5b5c889b004053dde0270fe3d7528b3cb56f9186df02504887b49b07` |
| `source_inventory.json` | `9523e69cfbdb61fcf1ad00fcd4f7da50fa3d18dacf1ccf720219cf416d421f7d` |
| `validation.json` | `3f9c685e23deeb5779ee1d846cf550374c66ec3393da44b282b9fa57bccd34cf` |
