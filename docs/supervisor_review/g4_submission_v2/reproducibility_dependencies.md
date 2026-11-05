# Reproduction, missing sources and publication dependencies

Repository commit: `de08db9712292d424e614c5e36e480ca16862128`.
Unpublished candidate identity is the [199-file inventory](source_inventory.json)
plus the [new package manifest](sha256.json). HEAD alone does not identify these
untracked files. Raw-byte SHA-256 differs from a newline-normalized semantic hash;
all package/audit checks use raw bytes unless a descriptor states canonical JSON.
Never change line-ending policy simply to force a source hash match.

## Source incorporation and remaining missing document

The exact researcher-supplied local source is recorded in [authenticity receipt](authenticity_record.json).
The original is now at [the requested Markdown destination](../ChronoGuard_RAG_Supervisor_Review_Package.md)
with unchanged source bytes. Source filename and contents identify an original
pre-approval review package, not the separate November 3 correction document.
Researcher designation/content consistency do not independently authenticate authorship,
supervisor acceptance or historical source claims. No alternate version was searched.

The November 3 correction remains MISSING. When supplied: preserve exact format,
bytes, source path and SHA-256; verify its identity and researcher provenance; place
an actual DOCX at `docs/supervisor_review/source_documents/ChronoGuard_RAG_Student_Required_Corrections_03Nov2026.docx`
only if the supplied original is really DOCX. Otherwise retain its actual extension
and update references. Compare any existing destination first; never overwrite a
differing original. Create v3 or later bound to v2's manifest, extract exact source
section identifiers/requirements, reconcile all 32 provisional rows and explicit
omissions, and rerun scope/link/hash/byte checks. Never reconstruct missing text,
change old artifacts, sign decisions or infer approval from document delivery.

v1 and all its 198 classified paths retain their historical bytes. v2's source
inventory binds those 198 paths plus the incorporated original (199 baseline paths).
Its manifest covers the 14 new v2 files except itself, avoiding recursive self hashes.

## External artifacts and portability

The repository alone is not sufficient to reproduce the complete scientific
evaluation. Restore authorized copies of the 25 restricted P0 artifacts, the
recovery project and recorded source-artifact inventories before revalidation.
The recovery logical root maps to an authorized copy of
`chronoguard-week6-recovered`, originally a sibling project; do not assume an
identical machine path. [G1 dependency ledger](../../../docs/consolidation/g1_v1/external_dependencies.json)
records individual source paths/hashes and logical roots. Its 143 input dependencies
and 56-file recovery digest must match. Matching inventories establish traceability,
not original-source authenticity. Some inherited verification functions still
expect the sibling layout; reproduce it in an authorized workspace or review a
new explicit root-mapping version, never patch historical files silently.

All 25 P0 files remain excluded. Additionally,
`audits/g2_i6_v1/inventory_reconciliation.json` is held for data-steward review
because it lists real FreshQA membership IDs. Its parent checksum manifest remains
a publication candidate, explicitly requiring the held child externally. A clean
public checkout will fail full child verification without that dependency; do not
relax hashes or fabricate missing files. Audit and original dataset licenses and
private review-distribution authority remain external responsibilities.

Three inherited P0 engineering documents contain machine-local path examples;
these are flagged per path in the allowlist. New package links are repository-relative.
No common private-key/token pattern was found by the static candidate scan; this
is not a security certification. Synthetic mock approvals/test labels are flagged
as engineering data, never approval credentials or real observations.

## Offline backend identities and unavailable verification

Primary Mistral: `mistralai/Mistral-7B-Instruct-v0.2`, recorded revision
`63a8b081895390a26e140280378bc85ec8bce07a`.
Contriever: `facebook/contriever`, revision
`2bd46a25019aeea091fd42d1f0fd4801675cf699`.
BGE: `BAAI/bge-reranker-base`, revision
`2cfc18c9415c912f9d8155881c133215df768a70`.
These are recorded configuration identities, not proof of loaded models. The
[P1-A2 inventory](../../../audits/p1_a2_v1/tokenizer_inventory.json) records local
Contriever file evidence, unavailable neural tokenizer runtime, and missing
Mistral/BGE caches. BM25's recorded whitespace tokenizer is known; G4 never calls it.
No downloads, substitutions, package updates or model loads are permitted here.
Proposed Qwen/Llama transfer revisions and measured memory/runtime/GPU fit remain
UNKNOWN. Full execution requires verified backend versions, files and final input.

## Publication and byte verification

The [allowlist](publication_allowlist.csv) classifies 199 prior/source and 14 new
paths: 185 YES_PROPOSED, 25 restricted, one unrelated, one membership-review hold
and one original-document publication hold.
All 92 original audit candidates received individual static content review and
flags; this is neither human scientific adjudication nor publication authorization.
The incorporated original contains names, local paths and historical dataset/review
IDs and remains HOLD_AUTHORITATIVE_SOURCE_REVIEW for publication. Its receipt records
a machine-local source path, flagged for researcher publication review.
Raw hashes for prior/source paths are in the allowlist and source inventory. G4 files
use SEE_G4_SHA256_MANIFEST to avoid recursive CSV/self-hash definitions. sha256.json
covers every other G4 file; its own hash is reported externally.

The [attributes proposal](gitattributes.proposed) retains the JSONL rule and adds
only exact-path -text overrides for the 185 proposed files. It is not applied to
the project. Isolated Git tests use core.autocrlf=true, clean/checkout filters,
a direct tree restore, LF/CRLF/mixed fixtures and all 279 protected path attributes.
They do not stage or commit, even in the temporary repository. Final sealed
verification checks actual completed package bytes, not just initial report placeholders.

Initial creation: `python -B docs/supervisor_review/g4_submission_v2/validate_submission.py --record`.
Sealed re-verification: `python -B docs/supervisor_review/g4_submission_v2/validate_submission.py`.
The latter is read-only in the project; writes stay in OS-temp. It requires the
recorded baseline HEAD and pre-commit untracked layout. Post-commit verification
needs its own explicit candidate identity record; do not silently weaken this check. No broad or guarded
model test suite is required or run. Historical test commands are recorded in the
engineering summary and checksum-bound audits, not presented as new executions.

Scientific gates remain ordered: authenticated/approved evidence and keys;
approved exposure/sampling; approved statistics and experimental design; verified
backend input; independent judge validation; approved benchmark/protocol hashes;
explicit Week 6 execution authorization. None is approved by this package.
