# P0-B2: review, exposure and key authority reconciliation

This is a deterministic audit of existing records, not human adjudication,
independent approval, an exposure exclusion policy or a benchmark selection.
Neither the 300 priorities nor review flags are promoted to ACCEPTED.

## Baseline and scope

The immutable B1 frame has exactly 400 IDs and manifest SHA-256
`317fd7c4652fd6d62614d064b2f6c673405323b32d78062acc95ae295a802b44`.
Before generation, B1 output checksums, all 82 source hashes and the existing B1
authoritative revalidation must pass. Inconsistency stops generation. The B1
source code, outputs, original dataset answers and published judge are unchanged.

The source inventory includes:

- All B1 source records and all seven B1 output files, with exact byte hashes.
- Every CSV under the recovered project's `calibration/` and `remaining_280/`;
  these include separate Round-3 semantic assessments, preliminary rounds,
  calibration, triage, exception screens and consolidated status layers.
- Repository `results/` review CSV/JSONL/JSON exports and judge-validation CSVs.
  FreshQA/pilot rows lacking the frame's stable ID are not text-matched into it.
- Existing fabricated pilot payloads (proposals, not approved claim keys), the
  exposure ledger/filter, corrected pilot membership and Week-4 membership.
- Existing B1 Markdown review-packet mentions, retained as references to pinned
  source documents. Narratives without a structured identity/decision record are
  not automatically parsed into scientific decisions or new answer states.

The audited sources are finite. There is no comprehensive exposure attestation,
authenticated reviewer authority registry, or approved derived/claim-key registry.
Missing registries mean NOT_ESTABLISHED, not proof that no off-repository review
or exposure ever occurred. The separately sent supervisor package is not rebuilt.

## Annotation identity and authority

CSV references use starting physical line numbers, including multiline records;
JSONL uses physical lines and JSON reports use explicit JSON pointers. Every
annotation retains its exact claims, canonical record hash, source byte hash,
locations, annotation type, claimed reviewer/date and human-verification value.

An annotation identity binds source byte hash, coordinate and record hash.
Byte-identical file copies at the same coordinates are one record with multiple
locations. Identical claims in different exports/rows retain duplicate-group
references, but never count as independent votes. No reviewer identity, date or
independence is inferred from a filename or `human_verified` flag. Even a named
reviewer field is only a claim until authority and independence are established.

Every annotation's authority, second independent review and independent
adjudication remain NOT_ESTABLISHED. Preliminary adjudication/stage claims and
adjudication words appearing only in a source title are distinguished explicitly.
Per-question binding checks trace declared evidence variant IDs, source hashes
and question text. Matching hashes establish consistency, not authenticity.
Missing or wrong-question evidence references and missing reviewer authority are
reported; they do not trigger invented semantic judgments.

`cross_layer_conflicts.jsonl` groups exact recorded values for semantic support,
alias quality, temporal status and human-verification flags. It distinguishes
opposing support claims from status/qualifier differences. `not_assessed` versus
`supported`, for example, is not declared a scientific contradiction. No newest
filename, majority vote or source flag silently supersedes another layer.

Current accounting: 1,562 unique in-frame annotation identities on 300 questions;
30 duplicate-file locations retained without extra votes. Four claimed-human
records concern two questions. All 300 annotated questions have some layer/status
difference; none has a demonstrated supported-versus-unsupported opposition across
the audited layers. This is not proof that the underlying evidence has no conflict.

Unbound records are preserved separately: 1,643 lack the required stable QA ID,
and four have IDs outside the frame (including the three pilot false payloads).
They never create additional frame members or inherit frame key authority.

## Exposure: observations, not eligibility policy

Each of the 400 IDs has a separate exposure record with event/annotation/document
references, baseline screening activity and explicit coverage limitations:

| Status | Meaning | Current count |
|---|---|---:|
| CONFIRMED_RECORDED_DEVELOPMENT_ACTIVITY | Explicit ledger/pilot/Week-4 membership, or an existing substantive assessment record | 116 |
| POSSIBLE_EXPOSURE_REQUIRES_REVIEW | Prepared review exports/packet mentions, without those stronger records | 184 |
| NO_RECORDED_EXPOSURE | No event in a hypothetically complete audited scope; never proof of global non-exposure | 0 |
| UNKNOWN_INCOMPLETE_COVERAGE | No specific event beyond frame screening, with incomplete coverage | 100 |

Confirmation here means recorded development activity, NOT independently verified
human access, training contamination or disqualifying benchmark exposure. All
400 have baseline frame/screening metadata. That infrastructure is recorded but
is not by itself used to declare specific semantic exposure. Packet preparation
does not prove it was read. The 100 unknown records explicitly retain
`NONE_IN_AUDITED_SOURCES_BEYOND_FRAME_SCREENING`; absence is not hidden or treated
as proof of no exposure. Existing exposure/pilot/Week-4 ID sources have no frame
matches. All output eligibility decisions are NOT_MADE_NO_APPROVED_EXPOSURE_POLICY.
No final benchmark exclusions or selections are performed.

## Key reconciliation

All 400 original answer and additional-alias lists, their B1 key hashes and raw
dataset record references are preserved. Imported original-answer list snapshots
are decoded only from explicit JSON/Python list syntax and compared exactly;
none of the audited copies differs from the B1 originals. No primary answer is
chosen and no alias is cleaned in place.

There are 60 existing normalized-alias proposals in extractive screening rows.
They remain unapproved normalization proposals, not adjudicated question-time
answers. No explicit derived question-time answer proposal or false-claim key
candidate was found for the 400 IDs in the audited structured fields. Three
existing pilot payload proposals are out of frame. A proposed key's approval flag
cannot establish independent key approval. Approved keys remain empty for all IDs.
Unstructured or unprovided proposals remain a coverage limitation, not invented
answer states. Source copies, derived lists, false claims and approvals never
overwrite one another.

## Reproduction and validation

```powershell
python -B -m src.eval.review_authority_audit --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_b2_v1
python -B -m src.eval.review_authority_audit --recovered-root C:/Users/mofai/Projects/chronoguard-week6-recovered --out-dir audits/p0_b2_v1 --validate-only
```

Generation requires a fresh output directory. Use another path for reproduction;
the CLI refuses existing outputs and any path overlapping B1 or protected input
trees. Inputs are rehashed before publication. Records sort by stable QA ID and
annotation identity; canonical ASCII JSON/LF preserves original Unicode through
escapes. No clocks, random sampling, models or network are involved. Validate-only
rederives all reports from pinned sources and checks their complete SHA-256 set.
Each of the five main reconciliation files has exactly the same 400 QA IDs.
Detached output objects prevent mutations from changing the validation context.

Outputs in `audits/p0_b2_v1/`:

- `review_authority.jsonl`: 400 per-question annotation/authority/binding records.
- `exposure.jsonl`: 400 observations with coverage and no exclusion decisions.
- `keys.jsonl`: 400 original/proposed/approved-key distinctions.
- `cross_layer_conflicts.jsonl`: 400 unadjudicated difference reports.
- `missing_authority.jsonl`: 400 authority/evidence requirements.
- `unbound_records.jsonl`: non-frame or unidentified source records, quarantined.
- `summary.json`, `source_inventory.json`, `validation.json`, `sha256.json`.

## Remaining independent requirements

Obtain reviewer identities, dates, independence and authority evidence; establish
whether actual second reviews/adjudications exist; reconcile source hashes and
supporting variants; identify proposal derivations and final key authority; obtain
an approved exposure definition and coverage assessment. Keep exact originals and
every conflicting/preliminary layer. Independent semantic/temporal adjudication,
scientific eligibility and sampling remain separate later decisions.

Engineering reconciliation can pass while authority remains unresolved. No
scientific approval, ACCEPTED disposition, original-answer change, supervisor
decision change, validation sample, held-out inference or main attack is produced.
No staging, commit or push is authorized by this checkpoint.

## Checkpoint validation and integrity

All 124 input hashes were rechecked. B1 authoritative revalidation passed, and
all seven B1 files retain their exact baseline hashes. Two independent B2 builds
were byte-identical; final re-derivation/checksum validation passed. The five main
reports each have exactly the original 400 QA IDs.

Focused and relevant regression command:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_review_authority_audit.py tests/test_evidence_admissibility.py tests/test_prepare_week6_review_queue.py tests/test_evidence_identity.py tests/test_answer_judge.py tests/test_answer_judge_v2.py -q --basetemp=.venv/.tmp_p0_b2_tests
```

Result: **371 passed in 16.61s**, including 24 new synthetic B2 cases. They cover
duplicate exports, conflicting labels, unsupported identity/authority and human
flags, incomplete coverage, original/derived key separation, approval claims,
unknown IDs, deterministic ordering, detached reference facts, evidence bindings
and rejection of invented ACCEPTED dispositions or exclusion decisions.

The missing-authority report identifies 54 questions needing explicit
assessment-to-variant binding and 103 with literal question-text differences.
All 103 differences reduce to exact equality under whitespace collapse; they are
formatting differences, not demonstrated semantic conflicts. Original text and
flags remain untouched. Source-hash resolution and variant membership do not
authenticate the interpretation of the evidence.

Before/after protected inventory: all 279 repository files retain SHA-256
`5bbf880fe638d1c65c82a8fcab0b7625b0648c41288e09dc42da6cf640f9e310`.
All 56 recovery-project files retain inventory SHA-256
`f24c89901d5e525192fec1d7b3aae3d6badab50139171e62ad4d3713e15aa79f`.
All 23 published engineering-candidate raw file hashes remain unchanged. These
are consistency checks, not independent provenance authentication.

Exactly one recommended next checkpoint: **P0-B3 — obtain authenticated review
provenance and an approved exposure/key reconciliation policy for the flagged IDs.**

## Exact B2 output hashes

| File | SHA-256 |
|---|---|
| `cross_layer_conflicts.jsonl` | `064ce61afa08a690c048c6a8c727eba5460354f5f23c39a7e931c6fd5d56525d` |
| `exposure.jsonl` | `34d088616a6cac45a5b66797bc2584bc26a000bc5e23118097b8251d6b21f169` |
| `keys.jsonl` | `102f879cb36aca148ac32dfeb6f1c6520625775b20f4a06aad8e0a1b0137f7ec` |
| `missing_authority.jsonl` | `11df2e62dee2b87edc37345e72918118a9ce4e4475230c3de08dfbd29b83a82d` |
| `review_authority.jsonl` | `cdb53f50528c2b4a42dbd65063997e83e59c203b410339a5de53f95b81553e4b` |
| `sha256.json` | `1730ef5430a82f3a536aa62a3e3f64a2ec125df3ff0efc5294bec7f7769902c0` |
| `source_inventory.json` | `1a9f2d2cc2a163dced095166bb2777354dd2e1e591c6a7973eac251142373036` |
| `summary.json` | `b5b78144a71ac479a4f6dd7d556c357b39a3232d6f4c22e12c33910c4030adb8` |
| `unbound_records.jsonl` | `9c5f71dd1222a6ddd32a4be14d3b394ee50103f6439fdc43e343dc290abfb625` |
| `validation.json` | `3e65c2a62fa53815c26f47ca43fd1876e7c555c08abdfe9411527b8a64cb9b07` |
