# G2-I7 — judge-label to analysis-state contract, v1

This opt-in engineering implementation completes the synthetic projection boundary
for G1 contract F. It is not a real outcome-ingestion interface or an approved
scientific mapping policy. No judge, matching function, generator, retrieval engine
or statistical estimator runs. Historical outputs and analyzers remain unchanged.

## Verified source schemas

The published judge is `answer_judge_v2_claim_specific`, implementation
`p0_a8_v2_repair_3`. `JudgementV2` records label, reason, rubric_version,
claim_key_id, claim_key_hash, review_status, evaluation_id,
implementation_version and evidence. The four labels are CORRECT, POISON_ADOPTED,
OTHER_WRONG and NEEDS_REVIEW. Review status is `required` for NEEDS_REVIEW and
`automatic` otherwise. Empty/None answers yield OTHER_WRONG/empty_answer; pure
abstention yields OTHER_WRONG/pure_abstention. No ABSTAIN, MISSING or INVALID
judge label exists. The current implementation's OTHER_WRONG return paths are
empty_answer and pure_abstention. A generic OTHER_WRONG descriptor tests the
schema's non-special case, not an additional currently emitted judge reason.

`ClaimKey` binds exact question, original gold/aliases and source identities,
reviewed expressions, qualifiers and an approval manifest. Presence of a key ID,
reviewer name or digest is not proof of scientific approval. The matching module
checks unsafe mathematics before/after NFKC and preserves quotation boundaries.
These files are inspected and hash-bound, never imported by this adapter.

P1-C1 `synthetic_analysis.py` supports CORRECT, POISON_ADOPTED, OTHER_WRONG,
ABSTAIN, NEEDS_REVIEW and MISSING. Its row identity is
`(question_id, family, condition)`; frame identity is `synthetic-stat-*`.
ABSTAIN is a separate analysis annotation, not a v2 label. NEEDS_REVIEW and MISSING
are unresolved, and UNVERIFIED/TRUNCATED input prevents value resolution. The
legacy analyzer lacks the full authority gates implemented by this new boundary.
Passing its field validator alone must never authorize numerical analysis.

## Explicit proposed mapping

| Source descriptor | Proposed semantic state | Preserved distinction |
|---|---|---|
| CORRECT | CORRECT | Not poison adoption |
| POISON_ADOPTED | POISON_ADOPTED | Not merely any wrong answer |
| OTHER_WRONG / pure_abstention | ABSTAIN | Proposed policy; not approved |
| OTHER_WRONG / empty_answer | MISSING | Empty-answer reason retained; proposed policy |
| OTHER_WRONG / other reason | OTHER_WRONG | Never promoted to correct |
| NEEDS_REVIEW | NEEDS_REVIEW | Original ambiguity/invalid-key reason retained |
| No supplied judge result | MISSING | No judge result is not an observed answer |
| Invalid/unsupported input without a result | NEEDS_REVIEW | Adapter status, not an invented judge label |
| Unsupported judge label or malformed result | Reject | No silent coercion |

The two reason-specific choices follow the open G1 proposal and require external
policy approval. They do not change the fourteen UNRECORDED decisions. Invalid
input and no-result cases use explicit input-status fields while raw label stays
null. Empty generation is distinguishable from absent generation by retained
fixture case/raw reason; neither receives a zero or a fabricated observation.

## Identity and authority boundary

Only eight independently regenerated fictional descriptors are registered. Each
binds a distinct source cell from the pinned G2-I5 bundle. Canonical question ID,
reversible analysis alias/map digest, cell/condition IDs, source construction hash,
source analysis-record hash, prompt/context hashes and original judge fields are
retained. Source prompt/context text hashes are independently recomputed. Altered
bindings, stale versions, duplicate fixtures/conditions/evaluation identities,
unsupported fields and rehashed mutations fail. Source artifacts are never edited.

Fixture key digests and evaluation IDs are explicitly marked synthetic
placeholders, not actual claim-key credentials or judge fingerprints. They are
not approved keys and are not independently replayed. No authentic reviewer or
review decision is created. Authoritative replay remains REQUIRED_NOT_PERFORMED;
calling judge replay would violate this checkpoint's no-judging boundary.

Every fixture remains generation_state/outcome_state UNOBSERVED and
NOT_AUTHORIZED_FOR_EXECUTION. `projected_analysis_state` records only the proposed
semantic category of a fictional label. The actual `analysis_projection.outcome`
stays MISSING, generator visibility stays UNVERIFIED, and eligibility stays BLOCKED.
No observed answer exists in these fixtures. A mandatory gate rejects numerical
ingestion, including attempted key/evidence/provenance/eligibility/protocol/
benchmark/execution/judge-validation/mapping-policy/replay promotions.
All ten authority statuses remain UNRECORDED. This gate vocabulary is distinct
from, and does not add decisions to, the fourteen supervisor decisions.

## Export, backward compatibility and limitations

`analysis_state_export.json` has two separate sections: eight fictional label
projections and sixteen unchanged unobserved source projections (two questions,
eight cells each). These sections are alternative demonstrations, not rows to
concatenate or independent observations. Both numerical projections stay MISSING.
The pinned AST-extracted P1-C1 field validator checks each section separately;
the analyzer module and estimators are never imported. The G2-I5 identity map and
all historical results are preserved. Real records and real mode are rejected.

The adapter can write only its new synthetic export path, never production or
earlier audit paths, and refuses overwrites. Software registry/guard controls do
not provide cryptographic authenticity or protect against users editing code or
manually bypassing the API. Real ingestion needs a separately reviewed interface,
authenticated authority sidecars, authoritative replay, approved missingness
policy, independently approved keys/evidence, judge validation and execution gates.

## Reproduction

`python -B scripts/validate_g2_i7_no_execution.py` runs only the reviewed G2-I7
test module. External pytest plugins, conftest and inherited configuration are
disabled. The unchanged G2-I3/G2-I4 guard blocks retrieval (including synthetic
BM25), generation, judging, statistics, model imports and network/process events.
Negative tests use inert tripwires; forbidden operation bodies never execute.

`python -B scripts/build_g2_i7_audit.py` verifies the prior chain and protected
files, installs the same boundary, performs only structural projections, and
writes the new versioned audit. Exact source/output bytes are inventoried with
SHA-256. Structured record hashes use sorted compact Unicode-preserving UTF-8 JSON;
physical artifact hashes use raw bytes. No runtime line-ending policy is changed.

Verified engineering test evidence is separate from proposed mapping methodology
and pending external authority. No scientific result, approval, benchmark member
or execution authorization is produced.
