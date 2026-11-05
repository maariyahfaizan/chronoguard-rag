# G2-I6 — fictional FreshQA normalization drafts, v1

Verified engineering scope: `src/eval/freshqa_candidate_normalization.py` accepts
only four independently regenerated fictional fixtures. No real record has a
successful conversion path in this version. No historical file, loader, runner,
configuration, dataset or prior audit is changed. This is an additive, opt-in
compatibility layer; historical readers and dictionary inputs remain unchanged.
Dictionary candidates are deliberately rejected by the legacy-string adapter.

## Mapping and integrity

The source `query_id`, question, answer, alias list and all other top-level fields
are copied without coercion. Candidate position i joins only metadata position i;
an explicit index must agree. Each string becomes `text`, recorded `doc_id` becomes
`doc_id`, recorded `source_date` becomes `timestamp`, and the boolean source flag
remains `is_source_document`. Original metadata and the full original record are
retained. Original text uses raw UTF-8 SHA-256; record/metadata bindings use sorted,
compact, Unicode-preserving JSON UTF-8 (`allow_nan=False`), not physical JSONL bytes.
Source artifact SHA-256 is separately recorded in the inventory.

An unavailable date/identity is `null` with MISSING status. An unavailable flag is
`null` with UNKNOWN status. An empty metadata dictionary is retained; positional
alignment without an explicit index is UNVERIFIED. No effective-year, URL,
snapshot retrieval time, filename or neighboring date supplies missing metadata.
Recorded dates are unauthenticated ISO dates or timezone-bearing ISO datetimes;
unsupported/contradictory dates fail rather than being guessed or reformatted.
Source flags describe a recorded marking, never independent semantic support.

Every output retains SYNTHETIC_ONLY, NOT_AUTHORIZED_FOR_EXECUTION,
NOT_REVIEWED benchmark eligibility and UNKNOWN_NOT_AUTHENTICATED provenance.
The independent fixed fixture registry rejects caller-rehashed mutations.
Hashes are identity checks and are not credentials. `authorize_execution` always
rejects. The writer permits only the new synthetic audit JSONL path, refuses
overwrites and rejects production paths. These software gates are not an OS
sandbox against users who edit code or manually bypass the adapter.

## Actual runner compatibility and limits

`scripts/run_baseline_freshqa.py` requires dictionary candidate text/doc_id/
timestamp/source-flag fields. It is read as source, never imported or executed.
The existing pure `_validate_record` function in `src/attacks/attack_pool.py` is
AST-extracted from its SHA-pinned source. Only its two field sets and single
field-presence validation function execute; no attack constructor or runner does.
Synthetic outputs also contain `question_ts=null`, `gold_chunk_ids=[]` and
`gold_validated=null` with explicit missing/unknown/not-reviewed statuses. These
are compatibility placeholders, not derived gold identities or approval.
The validator permits unknown values because it only checks field presence.

The FreshQA runner converts missing source flags with `bool(...)`; executing an
unknown flag there would collapse uncertainty into false. This adapter prevents
execution and preserves the unknown instead. Actual runtime compatibility,
tokenizer visibility, temporal scoring and independently approved data gates
remain unverified. The runner also logs its enumerated row identity; no runner
identity repair is performed here. No successful model-bearing path is claimed.

## Read-only discrepancy reconciliation

The pool contains 474 unique IDs and 9,480 string candidates, with 474 aligned
parallel metadata arrays. Configuration requests 477. The preprocessed question
file contains 500 IDs; 26 are absent from the pool. These 26 are specifically
relative to the 500-question artifact, not the unknown membership of the 477
configuration. No authoritative 477-ID membership list or historical build ledger
identifies any particular three missing records. The cause is UNKNOWN.

The current builder skips questions with no matched successful evidence and
emits dictionaries; the historical artifact contains strings. Current code is
therefore not proof of this artifact's historical processing or exclusion cause.
No pools are reconstructed, filtered, normalized in place or promoted. Inventory
reports contain IDs and metadata counts, not real normalized candidate bodies.

## Reproduction and pending authority

Run only `python -B scripts/validate_g2_i6_no_execution.py` (explicit reviewed test
allowlist, no conftest, inherited pytest configuration or external plugins).
The unchanged G2-I3/G2-I4 boundary blocks retrieval, generation, attacks, model
imports, network/process events, judging and statistical estimation. Negative
tests use inert tripwires; operation bodies do not execute.

`python -B scripts/build_g2_i6_audit.py` verifies pinned prior manifests, source
inventories, published candidate, protected repository/recovery files and the
fourteen UNRECORDED decisions before writing the new audit. It installs the same
boundary before normalization/inventory work. Existing audit bytes are never
overwritten with different contents. It does not launch tests; the independently
reported test command/result are recorded separately.

Real normalization, authenticated dates and provenance, the 477 membership
authority, eligibility/exposure policy, key adjudication, judge validation,
protocol freeze and execution authorization remain pending external decisions.
No scientific approval or result is produced. All fourteen decisions remain
UNRECORDED. Engineering tests do not pass the scientific judge-validation gate.
