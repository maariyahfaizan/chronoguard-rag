# Reproducibility and publication dependencies ? G4-B v3

Baseline Git HEAD: `de08db9712292d424e614c5e36e480ca16862128`, master. This uncommitted
candidate is identified by the [214-path source inventory](source_inventory.json)
and [new package hashes](sha256.json), not HEAD alone. V1 and v2 remain sealed.
Their missing-document states are historical; v3 references both supplied originals.

[Receipts](authenticity_record.json) record exact source paths, formats, SHA-256,
destination hashes and byte equality. Original review Markdown stays at its requested
path; the correction stays DOCX, never converted/edited in place. The exact supplied
DOCX path lacks the task prose's (1) suffix; no alternate was substituted. Metadata
modification date matches November 3, 2026, but editable metadata/template creation
date/user designation do not independently prove authorship or approve decisions.

Requirement locators are exact section identifiers plus one-based `word/document.xml`
body `w:p` indices, including table paragraphs. Page numbers are not invented without
Word layout. Paragraph hashes bind original Unicode text without storing a rewritten
replacement of the DOCX. Full originals remain available for controlled local review.

The public repository alone cannot reproduce the complete scientific evaluation.
Authorized restricted P0 artifacts, the 56-file recovery project and its recorded
143 source inputs must be restored with exact raw hashes. Use the logical-root
[G1 dependency ledger](../../consolidation/g1_v1/external_dependencies.json), not
assumed machine paths. Some inherited verification code still expects the sibling
recovery layout; reproduce that authorized layout or review a new mapping revision,
never silently modify historical source. Matching hashes prove traceability, not
historical source authenticity. The held FreshQA membership inventory remains an
explicit external child dependency of its selected checksum manifest.

Primary generator/retriever/reranker model and tokenizer revisions remain recorded
configuration identities, not loaded-backend proof. [P1-A2 inventory](../../../audits/p1_a2_v1/tokenizer_inventory.json)
records Contriever file evidence but unavailable exact tokenizer runtime and missing
Mistral/BGE caches. No model/tokenizer is downloaded, replaced or run. Transfer-family
exact revisions/runtime/GPU fit remain UNKNOWN pending an authorized resource check.

[Publication allowlist](publication_allowlist.csv) enumerates all 228 paths: 199
YES_PROPOSED, 25 restricted, one unrelated exclusion, one FreshQA membership hold,
and two authentic-document holds. Inclusion of either authentic document needs
explicit publication/staging approval; the DOCX's eventual-commit directive does
not override this task's no-staging/no-commit rule. Derived requirement summaries
omit personal source metadata and do not substitute for the held originals. Source
receipt paths are machine-local metadata flagged for review. Earlier source/path
flags and the synthetic-BM25 restriction deviation remain visible.

[Attributes proposal](gitattributes.proposed) retains the existing JSONL policy and
adds exact-path -text only for 199 proposed files. It is not installed. Isolated
Git clean/checkout filters and tree restoration test raw bytes with core.autocrlf=true,
LF/CRLF/mixed fixtures and unchanged attributes for all 279 protected paths. No
index, commit or network is involved, even in the temporary repository.

Initial report generation:
`python -B docs/supervisor_review/g4_submission_v3/validate_submission.py --record`.
Final sealed verification:
`python -B docs/supervisor_review/g4_submission_v3/validate_submission.py`.
This validates the exact pre-commit HEAD/untracked layout. A future authorized
commit requires its own candidate-commit identity and pre-execution record; do not
weaken this validator silently. No broad test suite or scientific estimator runs.

All fourteen existing decisions remain UNRECORDED. Independent evidence/key review,
approved exposure/sampling, justified statistical design, real-backend visibility,
independent blinded judge validation, final immutable protocol/data/config hashes
and explicit execution authorization remain prerequisites, not results of this package.
