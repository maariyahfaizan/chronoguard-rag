# Proposed claim-key approval workflow

## Verified evidence

`ClaimContext` binds original question text, primary gold, ordered aliases and
source identity/content. `ClaimKey` adds subject/relation/false state, units,
polarity, temporal qualifiers, complete expressions, provenance and approval
metadata. Canonical JSON SHA-256 binds the full key. Runtime checks reject
malformed fields and mutable sequence containers. Full approval enforcement
requires an approved status, reviewer text and matching external manifest digest.
This is consistency enforcement, not proof of evidence quality or independence.
The schema has only one reviewer string; structured dual reviews, adjudication,
revocation and authority records must live in an external controlled ledger.

## Proposed methodology

1. A named candidate author derives a single target proposition from the original
question, question timestamp, original gold/aliases and identified evidence or
payload. Preserve original text and alias order. Record dataset version, raw ID,
source/payload ID, text hashes, evidence locations, claim time, polarity, units
and derivation rationale. Do not derive expressions from validation answers.
Record any prior author exposure to pilot answers; historical independence cannot
be retroactively asserted. Treat answer-informed keys as exploratory.
2. Assign a candidate revision and parent revision. Record complete gold and false
expressions, their normalized forms, lexical/semantic collision audit and temporal
scope. Keep candidate status pending; never manufacture approval to pass checks.
3. Mechanical review runs type, schema, identity, expression-support and collision
checks. `validate_types()` alone checks runtime types. `problems()` also enforces
approval, so an otherwise valid candidate still reports unapproved/stale status.
Record that expected approval failure separately from mechanical defects. Current
normalizer has the open findings in the integrity record; do not call it safe for
unsupported numeric forms merely because an expression passes.
4. Two qualified reviewers, independent of authorship and each other, inspect the
same immutable candidate and evidence without generated validation answers or
machine outcomes. Each records identity, independence/conflicts, evidence,
rationale, decision and date. Choices: ACCEPT_CANDIDATE, REQUEST_REVISION, REJECT,
UNRESOLVABLE. These are reviewer recommendations, not approval-manifest entries.
5. A third reviewer adjudicates disagreement with evidence and a dated rationale.
Any changed expression/evidence requires a new candidate revision and renewed
review. Agreement cannot override ambiguous or contradictory gold/false identity.
6. The supervisor or explicitly designated authority records authorization for the
exact reviewed proposition and scope. Because changing approval metadata changes
the key digest, reviewers must countersign or verify the final serialized key and
final digest after authorized metadata are set. Only then may that authority
publish a manifest entry. No automatic self-approval by the candidate author.
7. Retain schema/rubric/implementation versions, final key ID/digest, source hashes,
review-ledger IDs, manifest revision/hash, approval authority/date and decision.
Verify exact digest immediately before judging; independently load authoritative
inputs for batch replay. A supplied hash is not authentication.
8. Revocation removes authorization from the active manifest and appends a dated
reason/authority record. Preserve old keys/manifests/results for audit; do not
rewrite historical outputs. Supersession uses a new revision/digest and explicit
parent link, renewed review/authorization, and separately versioned outputs.
An added manifest entry also changes evaluation fingerprints because the entire
manifest is bound. Record this compatibility consequence.

Mechanical validity, semantically valid candidacy, and independent approval are
three separate states. Approval does not follow from schema validation or tests.
One source field cannot represent all provenance: retain separate evidence and
payload identities in the external ledger. The code does not interpret question
time or establish semantic equivalence; reviewers must assess both explicitly.

## Pending human decisions

Authority, reviewer qualifications, permitted claim types, temporal rules,
paraphrase equivalence, collision policy and revocation governance require the
UNRECORDED decisions in [the decision sheet](judge_approval_decision_sheet.md).
The CSV template is header-only: use one future row per role/decision/revision.
Blank cells are unrecorded facts, not consent. No real keys are created here.
