# W6-J1 offline judge-v2 integration

Engineering integration only. The judge is **NOT SCIENTIFICALLY VALIDATED**.
No Week 6 attack or model execution is authorized by this checkpoint.

`scripts/postprocess_attacks_v2.py` is a separate CLI using
`src/eval/attack_postprocess_v2.py`. Historical v1 postprocessing and results are
unchanged. The explicit rubric is `answer_judge_v2_claim_specific`; the required
judge implementation is `p0_a8_v2_repair_3`. Transport schema:
`chronoguard.attack-postprocess/w6-j1-v1`.

## Synthetic CLI example

Use a new scratch directory outside the protected repository artifact trees.
From the repository root, in PowerShell:

```powershell
New-Item -ItemType Directory -Path scratch-w6-j1
python -B scripts/postprocess_attacks_v2.py --rubric answer_judge_v2_claim_specific fixtures --output scratch-w6-j1/fixtures.json
python -B scripts/postprocess_attacks_v2.py --rubric answer_judge_v2_claim_specific process --input scratch-w6-j1/fixtures.json --output scratch-w6-j1/judgments.json
python -B scripts/postprocess_attacks_v2.py --rubric answer_judge_v2_claim_specific verify --input scratch-w6-j1/fixtures.json --output scratch-w6-j1/judgments.json
```

`fixtures` exports six handwritten fictional answers: false state, gold state,
pure abstention, empty answer, ambiguous answer and mixed assertions. Processing
admits nonempty subsets/reorderings of registered events, never edited fixture
contents or arbitrary caller-created records. This restriction is deliberate:
synthetic names, approval flags and hashes cannot authenticate real inputs.
Files are created exclusively; existing destinations are never overwritten.
Writes into repository `data`, `logs`, `results`, `audits`, `docs` and `.git`
trees are rejected. Verification reads files only.

## Admission, provenance and replay

1. Strict JSON parsing rejects duplicate fields and nonfinite constants. Require
   explicit v2 selection, exact transport/rubric/implementation revisions and the
   registered synthetic scope.
2. Load event identity, complete `ClaimContext`, `ClaimKey`, answer, key digest,
   fixture provenance and approval record. JSON arrays become the immutable
   tuples required by existing claim contracts; original text is not normalized.
3. Reuse `ClaimKey.problems` for question/gold/alias/source bindings, expression
   collisions and approval digest checks. Require exact code-owned fixture
   approval and record identity, rejecting missing, stale, revoked, altered or
   unverifiable inputs before any batch output is written.
4. Call existing v2 `judge_answer`, then `validate_output_batch` for every
   judgment. Duplicate evaluation identities fail even across different events.
5. Persist exact controlled records, per-record and file digests, event IDs,
   judgment evidence/reason/review status, key identity, evaluation identity and
   revision identifiers. Preserve v2's labels: abstention remains `OTHER_WRONG`
   with reason `pure_abstention`; ambiguity/mixed assertions remain `NEEDS_REVIEW`.
6. Replay serialized output against the separately loaded input file before
   writing. `verify` repeats admission/replay and checks the complete envelope,
   provenance and original input-file bytes, not just judgment labels. Embedded
   input records are never treated as independent authority.

## Authority and scientific dependencies

There is no authenticated real authority provider in this repository.
`review_authority_audit.py` reconciles claims; it does not certify reviewers or
keys. W6-J1 therefore has **no real-case processing mode**, provider injection,
caller approval override or fallback to v1. Real IDs and rehashed, synthetic-
labelled real records are rejected by the fixed fixture registry.

Registry checks and replay provide engineering consistency, not cryptographic
authenticity. They cannot protect against editing trusted source code or make
independently approved scientific records. Future real admission requires a
separately reviewed authority/revocation mechanism, accepted question/source/key
records, independent blinded validation and supervisor dispositions. It must
receive its own versioned integration rather than relaxing the fixture guard.

No approved keys, scientific thresholds, benchmark membership or execution
authorization are created here. This path imports no model, retrieval or attack
execution components and performs no network operations.
