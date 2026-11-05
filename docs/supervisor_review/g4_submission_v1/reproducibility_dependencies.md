# Reproduction, missing sources and publication dependencies

Repository commit: `de08db9712292d424e614c5e36e480ca16862128`.
Unpublished candidate identity is the [185-file inventory](source_inventory.json)
plus the [new package manifest](sha256.json). HEAD alone does not identify these
untracked files. Raw-byte SHA-256 differs from a newline-normalized semantic hash;
all package/audit checks use raw bytes unless a descriptor states canonical JSON.
Never change line-ending policy simply to force a source hash match.

## Missing authoritative documents and later incorporation

- Original `ChronoGuard_RAG_Supervisor_Review_Package.md`: MISSING locally. Required
  source is the researcher's authentic original text/file or a verified original
  export; expected destination is `docs/supervisor_review/ChronoGuard_RAG_Supervisor_Review_Package.md`.
- Authentic November 3 supervisor-correction document: MISSING. Its original
  filename/version is UNKNOWN. Obtain it from the researcher/supervisor; do not
  manufacture authoritative wording or rename a derivative checkpoint report.
- Search covered repository/relevant local project filename inventories, relevant
  derivative references and existing Git history for the original package. The
  researcher reports separate text transmission of the original package; no local
  original or external acceptance is independently established. Missing sources
  do not prevent preparing this engineering packet, but coverage stays incomplete.

When authentic sources arrive: (1) preserve exact original bytes, received source,
channel, date/version and raw SHA-256; (2) have the researcher establish authenticity,
not merely a matching filename; (3) decide confidential distribution before any
repository copy; (4) create a new g4_submission_v2 or later, bound to v1's manifest;
(5) record exact source section/requirement identifiers and resolve provisional
rows, recording additions and gaps without inventing missing wording; (6) re-run
coverage, allowlist, byte/link/hash checks; (7) request actual independent decisions.
Do not overwrite v1, prior audits or unsigned decisions, or infer approval from receipt.
If publication is restricted, include the controlled source reference/hash instead
of public content. This procedure grants no automatic staging or approval.

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

The [allowlist](publication_allowlist.csv) classifies 185 existing and 13 new
paths: 171 YES_PROPOSED, 25 restricted, one unrelated and one membership-review hold.
All 92 original audit candidates received individual static content review and
flags; this is neither human scientific adjudication nor publication authorization.
Raw hashes for original paths are in the allowlist and source inventory. G4 files
use SEE_G4_SHA256_MANIFEST to avoid recursive CSV/self-hash definitions. sha256.json
covers every other G4 file; its own hash is reported externally.

The [attributes proposal](gitattributes.proposed) retains the JSONL rule and adds
only exact-path -text overrides for the 171 proposed files. It is not applied to
the project. Isolated Git tests use core.autocrlf=true, clean/checkout filters,
a direct tree restore, LF/CRLF/mixed fixtures and all 279 protected path attributes.
They do not stage or commit, even in the temporary repository. Final sealed
verification checks actual completed package bytes, not just initial report placeholders.

Initial creation: `python -B docs/supervisor_review/g4_submission_v1/validate_submission.py --record`.
Sealed re-verification: `python -B docs/supervisor_review/g4_submission_v1/validate_submission.py`.
The latter is read-only in the project; writes stay in OS-temp. No broad or guarded
model test suite is required or run. Historical test commands are recorded in the
engineering summary and checksum-bound audits, not presented as new executions.

Scientific gates remain ordered: authenticated/approved evidence and keys;
approved exposure/sampling; approved statistics and experimental design; verified
backend input; independent judge validation; approved benchmark/protocol hashes;
explicit Week 6 execution authorization. None is approved by this package.
