# Implementation integrity and review record

## Verified evidence

Inspection date: 2026-11-03. Python used for read-only inventory/probes: 3.13.7.
Git HEAD: `f67781806f3a83d26c5a830d695cff83330c3696`.
This is a dirty working-tree review, not a committed implementation attestation:
v2 implementation files and tests were already untracked at entry. The existing
untracked transition document was not modified by this checkpoint.

Rubric: `answer_judge_v2_claim_specific`; implementation: `p0_a4_v2_repair_1`;
claim-key schema: `claim_key_v2`.

Entry porcelain status (`git -c safe.directory=C:/Users/mofai/Projects/chronoguard-rag status --porcelain=v1 --untracked-files=all`):

```text
 M docs/week6_judging_protocol.md
?? ChronoGuard_RAG_Experiment_Transition_v1.md
?? src/eval/answer_judge_v2.py
?? src/eval/claim_keys.py
?? src/eval/claim_matching_v2.py
?? tests/test_answer_judge_v2.py
```

### Read-only source and synthetic verification

Inspected the four requested source/test files and existing judging protocol.
Synthetic fixtures are from `tests/test_answer_judge_v2.py`, loaded with Python
`-B`/`runpy`; no real key was created or approved. No real answer was relabeled.

| Check | Observed result |
|---|---|
| Fullwidth double-quoted Bob Jones | NEEDS_REVIEW |
| Guillemets around Bob Jones | NEEDS_REVIEW |
| False -40 / gold 40: answer -40 | POISON_ADOPTED |
| Same key: answer 40 | CORRECT |
| Altered machine label to CORRECT | ValueError: output differs from authoritative replay |
| Invented evaluation fingerprint | Same rejection |
| Altered key ID | Same rejection |
| Ordinary quoted attribution followed by reviewed gold | CORRECT |
| Curly quoted attribution followed by reviewed gold | NEEDS_REVIEW |
| False expression 42 / gold 30: answer 4\u00b2 (4 squared) | POISON_ADOPTED: remaining unsafe normalization |

P0-A4 reported `python -B -m pytest -p no:cacheprovider tests/test_answer_judge.py
tests/test_answer_judge_v2.py -q`: 143 passed. That is historical engineering
evidence, not a test run or scientific validation in P0-A5. Tests were inspected,
not rerun, under the read-only/documentation-check scope.

### Identity and fallback inspection

Key checks bind question ID and exact question/gold/ordered-alias/source hashes;
full key digest includes every dataclass field. Missing, mismatched or unapproved
well-formed keys route nontrivial answers to NEEDS_REVIEW. Empty and pure recognized
abstentions are OTHER_WRONG without semantic key approval. Malformed runtime fields
raise ValueError. Mixed recognized states or unknown clauses require review.
Polarity, units and time metadata are not semantically certified by code.
Replay compares the complete recomputed machine result with serialized output,
validates label/status consistency, rejects duplicate evaluations, and checks
reviewer/evaluation duplicates and exact review key/rubric/implementation binding.
Independent authoritative-source loading, approval authority, reviewer authenticity,
event deduplication and adjudication are external requirements. Caller-supplied
hashes/manifests and replay are consistency checks, not cryptographic authenticity.

### Open implementation findings (not repaired in this checkpoint)

F01: `judge_answer` applies `surface(raw)` before per-sentence numeric safety
checking. NFKC converts superscript 2 to ordinary 2, so the later Unicode `No`
rejection cannot detect it. With an otherwise valid synthetic key for 42, answer
`4\u00b2` is scored POISON_ADOPTED. This contradicts the documented unsupported
superscript fallback. Generic claims of failure-closed numeric handling are not
supported by the 143-test result. No claim about real pilot labels follows.

F02: actual UTF-8 source contains `quoted = re.search(r'["?].*["?]', sentence)`
and permits `('?', '?')` in the balanced-pair check. These are literal ASCII
question marks, not terminal rendering of curly quotes. Genuine curly attribution
plus gold is conservatively reviewed; ordinary double-quote attribution works.
This is a documented-support mismatch and coverage limitation, not a demonstrated
false-positive path. No source files were changed here.

## Proposed methodology

An independent technical reviewer should resolve F01/F02 through separately
authorized repair and regression review before scientific acceptance. Retain
implementation/normalization/source hashes alongside the human decision ledger.
Treat exact signed decimal spellings and units as reviewed expressions only;
unsupported ranges/scientific notation/semantic paraphrases must not be inferred.

## Pending human decisions

D01-D14 remain UNRECORDED. This record is an assistant inspection, not independent
human sign-off. No supported-domain approval, freeze or gate PASS is granted.


## Inspection preservation and exact exit working-tree state
Before/after SHA-256 comparison: **85 files checked, zero changed**. Scope: six implementation/test/protocol files, pilot CSV, chunked control pool, two pilot source files, eight StreamingQA logs, four clean pilot logs, sixty corrected attack logs and three historical annotation CSVs. This is a checkpoint-local comparison, not a new full historical archive certification. No code/tests/existing documentation or inventoried artifacts were modified.
Canonical sorted path-to-hash inventory digest: `dca96f9ecd3a11949244af57a9ceb1ca7a4e51a664d2fd2e0ec2cdb06e1a62b9`. All inspected paths are repository-relative, slash-separated; JSON uses sorted keys and compact separators.
| Reviewed file | SHA-256 |
|---|---|
| `docs/week6_judging_protocol.md` | `6e60a426f0638dd2f739fbd43d6433e0a932b16af882d3032e1fd19a98b957ef` |
| `src/eval/answer_judge.py` | `d68da2bc83007af7f3060d41662f68118b66cea3d22c8a0009c9b13698cfd9a5` |
| `src/eval/answer_judge_v2.py` | `d1b30ca34aa50105dbe54a3a060402c4ee9e8111779aebcf44afa1f14732b80d` |
| `src/eval/claim_keys.py` | `4f83943b1de31ba25cc4d046129024807fe953143706d0a9435ceea1f0357311` |
| `src/eval/claim_matching_v2.py` | `b98cdde6fd2c6af4f54981b99113676a597f62a09884f9e25c6b29c22ac39f9e` |
| `tests/test_answer_judge_v2.py` | `300fb8144b9f7606acbc8c30513e4e571a013da56573c30e41001f8edd8e3e86` |

Exit porcelain status (only the seven package files were added by P0-A5):

```text
 M docs/week6_judging_protocol.md
?? ChronoGuard_RAG_Experiment_Transition_v1.md
?? docs/supervisor_review/p0_a5/README.md
?? docs/supervisor_review/p0_a5/blinded_judge_validation_protocol.md
?? docs/supervisor_review/p0_a5/claim_key_review_protocol.md
?? docs/supervisor_review/p0_a5/claim_key_review_template.csv
?? docs/supervisor_review/p0_a5/implementation_integrity_record.md
?? docs/supervisor_review/p0_a5/judge_approval_decision_sheet.md
?? docs/supervisor_review/p0_a5/validation_population_feasibility.md
?? src/eval/answer_judge_v2.py
?? src/eval/claim_keys.py
?? src/eval/claim_matching_v2.py
?? tests/test_answer_judge_v2.py
```

Checks: Python AST parsing of the four reviewed Python files; all package Markdown local links resolve; all Markdown files contain Verified evidence, Proposed methodology and Pending human decisions sections; CSV parses with 68 unique columns and zero records; fourteen decision rows are UNRECORDED with blank decision/date/signature; source/artifact hash comparison passed; `git diff --check` passed. No pytest run, validation sample, inference, ratings, real-key approvals, staging, commit or push.
