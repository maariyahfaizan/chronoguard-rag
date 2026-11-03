# P0-A9 independent technical review request

DRAFT REQUEST. Prepared by Codex; no independent review or acceptance recorded.

## Verified evidence

Review `p0_a8_v2_repair_3`, rubric `answer_judge_v2_claim_specific`, against
[candidate_manifest.json](candidate_manifest.json). It gives every reviewed path,
raw-byte SHA-256, size, Git state and runtime versions. HEAD is
`f67781806f3a83d26c5a830d695cff83330c3696`; v2 source/tests are untracked, so HEAD alone is insufficient.
The manifest identifies 23 source/test/protocol/proposal/context files. Review the
four judge/key modules, both test modules, conftest and current protocol first;
P0-A5 is a preserved historical proposal, supplemented by the P0-A8 addendum.

Test command: `python -B -m pytest -p no:cacheprovider tests/test_answer_judge.py tests/test_answer_judge_v2.py -q`.
Observed: **252 passed in 1.06s**. `git diff --check` exited 0, with only a
working-copy LF-to-CRLF notice. These results do not establish scientific validity.

Bounded synthetic verification, using existing synthetic fixtures only:

| Input/condition | Observed |
|---|---|
| False 42 / gold 30: ASCII, U+FF01 or U+FE57 `42!` forms | NEEDS_REVIEW |
| Same key: superscript/subscript forms `4\u00b2`, `4\u2082` | NEEDS_REVIEW |
| Same key: scientific `4e1`, fraction `4/2` | NEEDS_REVIEW |
| Reviewed false in balanced curly attribution, then explicit reviewed gold | CORRECT |
| Same attribution, then false endorsement | NEEDS_REVIEW |
| Fullwidth quotation around false expression | NEEDS_REVIEW |

No unlimited edge-case search was undertaken. No contradiction was demonstrated
between the current A8 protocol section and addendum in these bounded checks.
Older sections/P0-A5 intentionally report older revisions and results. They are
not current technical acceptance records. The authoritative researcher-supplied
supervisor package is absent; the [parent index](../README.md) records that gap.

## Supported behavior and limitations

Exact reviewed complete entity/span, stance and simple signed decimal/integer
expressions can match, with distinct signs/decimal spellings and explicit textual
units. Original and NFKC forms share a mathematical rejection policy. No arithmetic,
unit conversion, semantic paraphrase expansion or temporal inference is performed.
Unsupported notation/Unicode units, unknown clauses, mixed assertions, ambiguous
time, unsupported/free/unmatched quotation require review. Narrow ordinary/curly
source attribution plus unambiguous gold can be correct. Fullwidth/guillemet
quotation cannot become supported attribution through normalization. Empty/pure
recognized abstention is OTHER_WRONG. Missing or unapproved well-formed keys route
nontrivial answers to review; malformed runtime fields raise ValueError.

Exact key/context/manifest consistency and implementation fingerprints are checked;
authoritative replay rejects altered results and earlier implementation revisions.
The caller must independently obtain authoritative inputs. Replay and hashes do
not authenticate approvals, reviewers, source truth or generation-event provenance.
Metadata and passing schemas/tests do not certify semantic validity. Coverage and
scientific accuracy remain unvalidated; no real keys have been approved.

## Independent technical acceptance questions

Please assess this exact manifest-bound scope and record evidence, not a general
endorsement of all research claims:

1. Are original AND normalized representations checked before lossy punctuation
processing, including in key-expression validation? Are unsupported forms safely
reviewed within the documented scope?
2. Do quotation boundaries, attribution, explicit gold endorsement and conflicting
assertions follow the documented conservative precedence?
3. Are signs, decimal spellings, units and temporal limitations represented honestly,
without unsupported equivalence or automatic semantic certification?
4. Do schema/context/key/manifest bindings and revisioned fingerprints reject stale
or altered outputs/reviews, including duplicates, with authority limits explicit?
5. Do tests reproduce known defects and preserve v1 behavior, while avoiding any
claim that fixtures are real approvals or that regressions prove scientific safety?
6. Are the manifest, dependencies, runtime and reproduction instructions sufficient?
Please distinguish byte-identical versus newline-equivalent reproduction and
identify any missing dependency or misleading documentation.
7. Are there blocking technical changes before development validation? Specify
scope, evidence and required regression coverage. Technical acceptance must not
approve scientific decisions, real keys, rubric freeze or Week 6 execution.

## Blank independent reviewer record

Reviewer identity: ____________________
Affiliation/qualification: ____________________
Independence from implementation/key authorship; conflicts: ____________________
Candidate manifest SHA-256 and implementation revision: ____________________
Environment and test results independently obtained: ____________________
Evidence examined / findings / limitations: ____________________
Required changes or acceptance scope: ____________________
Decision (choose ACCEPT / REQUEST CHANGES / REJECT): ____________________
Date: ____________________
Signature: ____________________

All fields are intentionally blank. No independent reviewer has been impersonated.
