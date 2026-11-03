# P0-A9 exact candidate and unsigned handoff

Prepared 2026-11-03. DRAFT FOR EXTERNAL REVIEW. No external acceptance recorded.

## Verified candidate and reproduction evidence

Implementation: `p0_a8_v2_repair_3`; rubric: `answer_judge_v2_claim_specific`.
Git base: `f67781806f3a83d26c5a830d695cff83330c3696`.
HEAD alone does NOT reproduce the candidate: three v2 modules and its test file
are untracked; the judging protocol is modified; P0-A5 and A8 are untracked.
The unrelated transition draft is excluded. No index, branch or commit state was changed here.

[candidate_manifest.json](candidate_manifest.json) records all 23 reviewed paths,
raw-byte SHA-256, LF-normalized diagnostic hashes, sizes, Git state and runtime:

- Four judge/key modules, two test modules and tracked `tests/conftest.py`.
- Current protocol, all seven historical P0-A5 files, and the A8 addendum.
- Parent supervisor index/integrity record, held-out proposal, three requirements
  records and `.gitattributes` as provenance/environment context.

The focused suite uses Python standard-library judge code and pytest, with no
datasets, model weights, GPU, credentials or inference. Conftest adds the repository
root to the import path. Runtime: Python 3.13.7, Unicode database 15.1.0, pytest
9.1.1; the manifest records exact pytest dependency versions and no entry-point
plugins. The local requirements file is not a complete transitive lock; use the
recorded Python/Unicode and pytest package versions. Production requirements contain
heavy model dependencies that are unnecessary for this suite. No other untracked
or modified runtime/test dependencies were found among the required files.

Observed command and result:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_answer_judge.py tests/test_answer_judge_v2.py -q
# 252 passed in 1.06s
```

`git -c safe.directory=C:/Users/mofai/Projects/chronoguard-rag diff --check` exited 0
with only the LF-to-CRLF notice. Entry porcelain status is in the manifest.
The known punctuation, superscript/subscript, scientific/fraction and quotation
cases match current documentation. No unlimited edge-case search was performed;
no new contradiction was demonstrated by these bounded checks. This is not proof
of universal safety or independent acceptance.

Obtain the base checkout plus every manifest-listed candidate file and this packet,
use the recorded environment, verify file hashes, then run the command above.
A future commit containing the proposed files would make candidate content
Git-addressable; no such commit exists yet.

Strict byte verification from repository root (read-only):

```powershell
python -B -c "import hashlib,json,pathlib; m=json.loads(pathlib.Path('docs/supervisor_review/p0_a9/candidate_manifest.json').read_text()); bad=[r['path'] for r in m['files'] if hashlib.sha256(pathlib.Path(r['path']).read_bytes()).hexdigest()!=r['sha256']]; print('Byte mismatches:',bad); assert not bad"
```

Git can normalize CRLF/LF on staging/checkout; `.gitattributes` sets LF only for
JSONL. The raw hashes identify exact current working-copy bytes. If strict
verification fails solely from newlines, compare SHA-256 after replacing CRLF
with LF against `lf_sha256`, and report a newline-equivalent reproduction rather
than a byte-identical copy. Before calling a future commit the exact reviewed
candidate, preserve the byte snapshot or authorize a canonical-LF candidate with
refreshed hashes and rerun checks. Do not silently rewrite historical files or
the manifest. Hashes prove consistency, not authenticity or scientific authority.

## External technical review request

[technical_review_request.md](technical_review_request.md) supplies bounded evidence,
supported/unsupported behavior, limitations and seven acceptance questions.
ACCEPT / REQUEST CHANGES / REJECT, independence, evidence, date and signature fields
are blank. Codex checks are not independent acceptance. No request was sent to an
external reviewer or service.

## Supervisor decision handoff

[supervisor_decision_request.md](supervisor_decision_request.md) covers every original
decision ID without selecting answers. All fourteen decisions remain UNRECORDED.
The proposed 200 inputs and 80 predicted positives are NOT established as feasible.

The original authoritative researcher-supplied package is NOT present at
`docs/supervisor_review/ChronoGuard_RAG_Supervisor_Review_Package.md`; the filename
inspection found no matching file elsewhere. The parent index records this gap.
The P0-A5 decision inventory and Codex addenda are not substitutes. Obtaining the
original remains a submission dependency; its contents have not been invented.

## Proposed staging and commit plan (NOT executed)

1. Verify the manifest and protected inventory; resolve/document line-ending
   reproduction and inspect candidate changes against the base.
2. Stage only these 17 exact paths. Unchanged tracked v1, original tests, conftest,
   requirements and context documents are inherited from HEAD, not restaged.

```powershell
git -c safe.directory=C:/Users/mofai/Projects/chronoguard-rag add -- `
  "src/eval/claim_keys.py" `
  "src/eval/claim_matching_v2.py" `
  "src/eval/answer_judge_v2.py" `
  "tests/test_answer_judge_v2.py" `
  "docs/week6_judging_protocol.md" `
  "docs/supervisor_review/p0_a5/README.md" `
  "docs/supervisor_review/p0_a5/blinded_judge_validation_protocol.md" `
  "docs/supervisor_review/p0_a5/claim_key_review_protocol.md" `
  "docs/supervisor_review/p0_a5/claim_key_review_template.csv" `
  "docs/supervisor_review/p0_a5/implementation_integrity_record.md" `
  "docs/supervisor_review/p0_a5/judge_approval_decision_sheet.md" `
  "docs/supervisor_review/p0_a5/validation_population_feasibility.md" `
  "docs/supervisor_review/p0_a8_current_revision_addendum.md" `
  "docs/supervisor_review/p0_a9/README.md" `
  "docs/supervisor_review/p0_a9/candidate_manifest.json" `
  "docs/supervisor_review/p0_a9/technical_review_request.md" `
  "docs/supervisor_review/p0_a9/supervisor_decision_request.md"
```

3. Inspect `git diff --cached --name-status`, `git diff --cached --check` and the
   complete staged patch. Confirm the allowlist and no scientific decision changes;
   rerun focused tests. Verify committed blobs/checkout against explicit raw/LF
   hashes and record any normalization before external acceptance.
4. Only after separately authorized execution, proposed commit title:
   `Prepare v2 judge repair candidate and unsigned review handoff`. Record its new
   hash. A commit records content, not scientific or technical approval.
5. No push until separately authorized. No staging, commit or push occurred here.

Do not use broad staging or force-add. Exclude the unrelated
`ChronoGuard_RAG_Experiment_Transition_v1.md`, all data/logs/results, model caches,
`.venv`, credentials, `.aws`, `.codex`, `.git` internals and unrelated drafts.
The missing authoritative package cannot be staged before it is supplied and
inspected. The manifest records file sizes; no large/sensitive files are included.

## Separate readiness and outstanding gates

| Area | Status |
|---|---|
| Engineering readiness | READY FOR EXTERNAL REVIEW within tested scope; candidate not committed |
| Independent technical acceptance | UNRECORDED |
| Supervisor decision approval | D01-D14 UNRECORDED |
| Scientific judge-validation gate | BLOCKED |
| Week 6 main attack authorization | NOT AUTHORIZED |

The missing authoritative package, external acceptance, supervisor decisions,
source/event reconciliation, eligible strata and positive/cluster feasibility
remain outstanding. No real keys are approved and no blinded validation occurred.

Exactly one recommended next checkpoint: **P0-A10: researcher/supervisor-led
external disposition of this hash-bound candidate and the fourteen open decisions,
with the original authoritative package supplied.**

## Integrity results

All 279 protected files match the recorded A8 inventory SHA-256:
`5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310`.
Scope: unchanged v1, all data/logs/results and the entire seven-file P0-A5 package.
This is a content-consistency check, not authentication of the historical source.
No source, tests, existing protocols, scientific artifacts or decisions were edited.
