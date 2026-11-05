# P0-B1: 400-question evidence-admissibility foundation

This is a development/audit artifact, not independent adjudication, an accepted
benchmark, an attack run, or a benchmark freeze. No scientific decisions change.

## Authoritative inputs and inventory

The fixed audit frame is the 400 IDs in
`results/week6_sampling_draft/screening_batch_v1/screening_batch_ids.jsonl`:
200 recent and 200 past. The corresponding `evidence_windows_400.jsonl` and
`candidate_metadata_400.jsonl` bind frame identity, original metadata and windows.
`data/raw/streamingqa_eval.jsonl.gz` is the local original dataset authority for
QA ID, exact question, question timestamp, complete answers/answers_additional,
evidence ID/timestamp and stratum. All 400 are joined by stable QA ID and checked
against raw records; no answer is selected from the list or aliases rewritten.
VERIFIED here means byte/record binding, not semantic truth or authenticated
upstream dataset origin. There is no newly inferred primary answer.

The explicitly selected recovered root is the sibling project
`C:/Users/mofai/Projects/chronoguard-week6-recovered`. Its
`development_backup/consolidated_evidence/manifest.json` and closed SQLite/exports
are the authority for reconstruction accounting. The existing
`prepare_week6_review_queue.validate` validates the complete provisional snapshot,
schema, database/exports, hashes, frame and annual completion. The local frame
files have CRLF bytes; their LF hashes match the published snapshot. Temporary LF
copies are used for that validator only; raw files are unchanged. Both byte hashes
and the explicit equivalence basis are retained in the new source inventory.

The snapshot contains 400 ledger rows, 1,316 variants, 1,417 occurrences and 416
document observations. Thirteen annual source-artifact records are all
`observed_plain_only`, with historical equivalence unverified. Each variant ID
and occurrence ID is recomputed; source artifact membership is checked. Backup
inventory entries, published review export checksums and snapshot binding are
checked. Original WMT corpus paths refer to earlier Kaggle mounts; source hashes
are declared provenance, not proof that those original bytes are available here.
The two saved ZIP archives are hashed as backup artifacts, not original evidence.

Existing review inputs are CSVs/Markdown in `calibration/` and `remaining_280/`.
They include claimed human review, assistant preliminary semantic adjudications,
exception screens, literal-match triage and unreviewed forms. Duplicate exports
remain separately traceable, not independent votes. The output preserves every
matched CSV claim, its source hash, record hash and starting physical CSV line
(including multiline records). Markdown ID mentions are pointers, not judgments.
No named independent reviewer/date/authority is established by a filename or
`human_verified=true`. Such claims are preserved without accepting their authority.

Repository gold/stale/pilot review files and FreshQA binary annotation CSVs are
inventoried separately. A row without a stable QA ID is not silently text-matched
to this frame. Original answer lists are available for all 400; an authoritative
derived-key registry and frame-specific approved false-claim keys are not supplied.
The original exposure ledger is pinned. Its lack of a frame ID does not prove
that ID is unexposed; prior review artifacts require exposure reconciliation.

Existing eligibility documentation is `docs/week6_heldout_protocol.md`,
`docs/w6_r19_inventory.md`, `docs/w6_r19_target_index_2b.md`, and
`docs/week6_development_review_queue.md`. None certifies the 300 priorities.
Current adjudication/alias notes remain source claims, not approved replacements.

## Schema, field authorities and provenance rules

Schema: `chronoguard-evidence-admissibility/p0-b1-v1`.

| Manifest fields | Authority/basis |
|---|---|
| QA ID, stratum, reserve rank | Fixed frame, checked against metadata/ledger |
| Original question, time, answers and aliases | Raw dataset record plus metadata equality |
| Original-key identity | Canonical hash of unchanged answer lists; semantic status separate |
| Derived answer/false claim/claim key | Explicit UNKNOWN/NOT_REVIEWED and null references; no invented key |
| Variant IDs, text hashes, occurrences | Validated snapshot exports; identity recomputation |
| Artifact/sidecar hashes and declared source paths | Pinned reconstruction manifest; original authentication UNKNOWN |
| Publication dates/date basis | Exact reconstructed variant timestamps, individually linked; independent publication verification UNKNOWN |
| Dataset evidence time | Original numeric evidence_ts, separate from reconstructed passage times |
| Semantic/temporal verdicts | NOT_REVIEWED; imported assertions retained separately |
| Reviewer IDs/decisions, adjudicator/date/rationale | Empty/null and NOT_REVIEWED until a future authorized review importer exists |
| Development exposure | Explicit source-ledger exclusions if any; otherwise UNKNOWN; prior artifacts flagged |
| Queue status | Original screening audit claim only; priority does not mean ACCEPTED |
| Attack-family eligibility | NOT_REVIEWED, or explicit engineering source/exposure ineligibility; no approval |
| Final disposition | Engineering UNRESOLVED or scoped INELIGIBLE only |
| Traceability | Logical source ID + artifact byte hash + physical line/canonical record hash |

Provenance tiers are separate:

- `AUTHENTICATED_ORIGINAL`: reserved vocabulary, but B1 cannot emit or authorize
  this tier. Future independently supported authentication is required.
- `TRACEABLE_RECONSTRUCTED`: available variants tied to the validated closed
  snapshot and source occurrences. Internal traceability may be VERIFIED while
  original authenticity remains UNKNOWN.
- `UNVERIFIED_OR_UNUSABLE`: no admissible evidence in the current configured
  source scope; the reason must be explicit. This does not prove global absence.

Statuses are not synonyms: UNKNOWN means an authoritative value or authority is
unestablished; NOT_REVIEWED means a required independent assessment has not been
validated/imported; NOT_APPLICABLE is used for unavailable variant traceability
on the out-of-scope rows; VERIFIED applies only to an identified mechanical fact.
It never implies a scientific verdict. Questions with preliminary review claims
still have NOT_REVIEWED independent semantic/temporal/adjudication fields.

All ten out-of-scope rows are past questions with original dataset evidence time
in 2007 and ledger status `gold_outside_configured_archives`. The archive years
come from the validated manifest (2008–2020), never filenames. They remain in the
400-row manifest and receive INELIGIBLE_SOURCE_SCOPE, with no silent replacements.
The other 390 are REVIEW_REQUIRED/UNRESOLVED, not provisionally ACCEPTED.

## Determinism and validation

`src/eval/evidence_admissibility.py` uses only explicit local inputs and no clock,
randomness, network, model or outcome-based sampling. Records sort by QA ID;
variants/occurrences sort by stable identity. Outputs use canonical sorted-key
ASCII JSON and LF. Original Unicode values round-trip through JSON escapes.
Input files are rehashed before publication. Output paths cannot overlap any
protected source tree; existing output directories are refused.

Source-file hashes cover exact bytes. Record/key/question identity hashes use
canonical JSON; variant text hashes cover exact UTF-8 text. Sidecar/physical
artifact hashes retain their declared scopes. Hash matches establish internal
consistency, never original-source authentication or reviewer authenticity.

The validator reloads the pinned inputs, recomputes the expected row for each of
the exact 400 frame IDs, checks recursive required fields/types, vocabularies,
source/key/variant identity and consistency, and compares every field. It rejects
invented reviewer authority, adjudications, provenance promotion and ACCEPTED.
Rows do not share mutable references with pinned context. Validate-only also
rederives ordering, reports, source inventory and the complete checksum set.
A future human-review ingestion contract is deliberately not implemented here.

From repository root:

```powershell
python -B -m src.eval.evidence_admissibility --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_b1_v1
python -B -m src.eval.evidence_admissibility --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_b1_v1 --validate-only
```

The first command requires a fresh output directory. Use a new path for a
reproduction; do not overwrite frozen inputs or prior audits. Two independent
builds are compared byte-for-byte in checkpoint verification. Source roots use
logical labels in outputs; no temporary paths or invocation timestamps are added.

Outputs under `audits/p0_b1_v1/`:

- `manifest.jsonl`: exactly 400 row-level records, including unreviewed/ineligible.
- `source_inventory.json`: input byte hashes, raw/LF equivalence, declared source
  artifacts, code hashes, annotation inventory and authority limitations.
- `summary.json`: stratum/provenance/availability/review/provisional/disposition
  counts and missing-data counts; no scientific acceptance claimed.
- `missing_data.jsonl`: unresolved field/evidence requirements for every ID.
- `ineligible_unresolved.jsonl`: all 400 dispositions and explicit reasons.
- `validation.json`: engineering structural result, scientific acceptance false.
- `sha256.json`: hashes of the six other files (no recursive self-hash).

## Review requirements and disposition

Expected engineering accounting: 200 recent/200 past; 390 reconstructed and ten
out-of-scope; 390 unresolved and ten scoped ineligible; zero authenticated-original
or independently verified admissible cases. All 400 original question/key bindings
are mechanically verified, but all semantic/temporal/adjudication states remain
NOT_REVIEWED. The reported 300 priority/90 reserve labels stay scheduling claims.

Prior review artifacts touch 300 questions; two questions have imported
human-verified claims without validated reviewer identity/authority. Preserve
these facts and investigate their provenance; do not silently discard the claims,
promote them to independent approval, or treat absence of a claim as no exposure.
No fabricated-fresh or stale-evidence attack eligibility is granted by this audit.

Remaining evidence: original-source authentication, document/annotation identity,
independent named/date-stamped semantic and temporal reviews, original/derived
key and alias adjudication, exposure reconciliation, false-claim/key review,
attack-family decisions and approved final disposition. A scientifically adequate
benchmark/sample and statistical policy remain separate pending decisions.

Engineering foundation can pass while scientific evidence admissibility remains
PARTIAL. No held-out inference, main attacks, human judgments, benchmark selection,
scientific-decision changes, staging, commit or push is performed.

## Checkpoint verification

Command (synthetic B1, existing recovery/identity and published judge regressions):

```powershell
python -B -m pytest -p no:cacheprovider tests/test_evidence_admissibility.py tests/test_prepare_week6_review_queue.py tests/test_evidence_identity.py tests/test_answer_judge.py tests/test_answer_judge_v2.py -q --basetemp=.venv/.tmp_p0_b1_tests
```

Result: **347 passed in 67.76s**. Both new generated copies were byte-identical;
the final 400-row manifest and all reports passed authoritative re-derivation and
checksum validation. Tests cover duplicate/missing/extra IDs, hashes, keys,
provenance claims, fabricated/conflicting reviews, adjudication, source references,
ineligible cases, mutable-context isolation, multiline CSV coordinates and ordering.

Before/after integrity: 279 existing repository protected files retained inventory
SHA-256 `5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310`.
All 56 sibling recovered-project files retained inventory SHA-256
`f24c89901d5e525192fec1d7b3aae3d6badab50139171e62ad4d3713e15aa79f`.
All 23 published engineering-candidate raw file hashes also remained unchanged.
The new outputs are separate under `audits/`, outside frozen data/logs/results.

Exactly one recommended next checkpoint: **P0-B2 — verify authority and reconcile
the existing review, exposure and key records against this pinned 400-ID manifest.**
