# P0-A5 draft approval package

Prepared 2026-11-03. DRAFT FOR EXTERNAL REVIEW. No approvals or human judgments recorded.

## Verified evidence

The opt-in rubric is `answer_judge_v2_claim_specific`, implementation
`p0_a4_v2_repair_1`. P0-A4 reported 143 passing focused tests; this checkpoint
inspected their source and performed read-only synthetic probes, without rerunning
the suite. The three reported repair cases behaved as intended. Two additional
findings prevent an unconditional implementation endorsement: superscript numeric
normalization can produce false adoption; curly attribution differs from the
documented behavior. See [integrity record](implementation_integrity_record.md).
Development inventory contains 298 distinct question/answer pairs across 100
question-text clusters, but only three fabricated-payload questions and no
independently approved real claim keys. Counts are not v2 outcome strata.

## Proposed methodology

Read in order:

1. [Implementation and working-tree evidence](implementation_integrity_record.md).
2. [Claim-key workflow](claim_key_review_protocol.md) and [empty CSV template](claim_key_review_template.csv).
3. [Population feasibility](validation_population_feasibility.md).
4. [Blinded validation proposal](blinded_judge_validation_protocol.md).
5. [Supervisor decision sheet](judge_approval_decision_sheet.md).

No sampling, eligibility, estimand or acceptance policy becomes authoritative by
appearing here. This package proposes decisions; it does not amend frozen inputs
or the existing judge. Machine NEEDS_REVIEW and human UNRESOLVABLE remain explicit.

## Pending human decisions

All decision-sheet statuses are UNRECORDED. No real key is approved; no sample
has been drawn and no validation judgments collected. Package preparation is
PARTIAL because implementation findings and population feasibility remain open.
The scientific judge-validation gate is BLOCKED. Week 6 main attacks remain
NOT AUTHORIZED. Passing that gate would still require separate experimental
authorization.

Required gate evidence: resolved technical findings with regression evidence;
recorded protocol and threshold decisions; independent key review and authorized
revision-bound manifest; reconciled leakage-free eligible frame; approved actual
allocation; locked blinded dual ratings and adjudications; full confusion,
uncertainty and dependence-aware results; external signed gate decision.

Recommended next checkpoint: **P0-A6 ? resolve the P0-A5 implementation findings
under separately authorized repair scope and independent technical review.**
