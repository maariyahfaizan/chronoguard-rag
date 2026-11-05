# G2-I1: adjudicated record to runner projection

Status: DEVELOPMENT ONLY. Successful conversions are limited to the two registered
manual fictional fixtures. Real record conversion is disabled. No real benchmark
record, scientific key, reviewer decision or supervisor approval is created.
No retrieval, attack construction, inference, staging, commit or push occurs.

## G1 compatibility and versioning

The immutable G1 contract A describes a DRAFT_BLOCKED boundary envelope. It uses
`aliases`, permits unknown answers/dates, and cannot itself be passed to the
runner. This adapter defines explicit profiles:

* Input: `chronoguard.adjudicated-to-runner/input-v1`.
* Output: `chronoguard.adjudicated-to-runner/pool-v1`.
* Implementation: `g2_i1_synthetic_adapter_1`.

The adapter pins and verifies G1's checksum manifest and contract A bytes.
It adds `gold_aliases`, `gold_validated`, full candidate dictionaries and stable
source QA identity without editing G1 or historical runner code. Profile changes
are explicit new schemas, not silent reinterpretations of G1's blocked example.
Unknown dates/keys do not become runner-compatible by coercion or default values.

## Actual runner compatibility

`src/attacks/attack_pool.py:_validate_record` requires query, gold_answer,
gold_aliases, candidates, question_ts, gold_chunk_ids and gold_validated.
Candidates require doc_id, text, timestamp and is_source_document. The StreamingQA
runner reads those dictionaries into parallel text/ID/time/source lists;
`src/attacks/pilot_protocol.py:read_jsonl` is the existing UTF-8 JSONL loader.
Tests call that actual validator and loader. Extra lineage fields are preserved
by this adapter; downstream historical runners may ignore them, so later
integration must explicitly carry these fields into logs. No historical input,
runner, loader, evaluator or attack constructor is changed.

Synthetic output is structurally loadable but is not authorized for execution.
The historical runner does not enforce adapter_metadata.execution_authorized;
the marker is an explicit warning, not a security barrier. No automatically
wired runner or executable production manifest is produced here.

## Input authority and mapping

Inputs are plain JSON values with required source references, version, scope and
stable qa_id. `synthetic_fixture_bundle()` returns independent copied source
records plus explicit fixture-only mock approval sidecars. The input record
contains original_source; question_time_answer; ordered evidence/variant refs;
candidate_order; gold_chunk_ids; claim context/key/source; provenance; family
eligibility; exposure policy; two-reviewer/adjudicator sidecar; protocol/benchmark
freeze identities; and gate tokens bound to the complete record's canonical hash.

| Input | Runner output and preservation |
| --- | --- |
| Original stable QA ID and question | source_qa_id and query, unchanged |
| Explicit adjudicated primary | gold_answer; never selected from answers automatically |
| Original aliases | gold_aliases, aliases and original_aliases, unchanged and ordered |
| Original answers/source record | original_answers, original_record and original_source_reference |
| Original question timestamp | question_ts, strict UTC validation without conversion |
| Ordered evidence references | candidates in the exact declared order |
| Evidence doc/source IDs, variant/body hashes and metadata | candidate IDs, source_id, variant_id, text_sha256, source_reference and source_metadata |
| Explicit adjudicated gold document IDs | gold_chunk_ids and per-candidate is_source_document |
| Mock claim/key and approval scope | synthetic_claim_key, distinctly labeled; not a real approved-key registry |
| Eligibility/exposure/adjudication/protocol gates | adapter_metadata with exact source-record fingerprint |

The profile supports unchanged aliases only. Different question-time alias
proposals require another independently reviewed profile rather than rewriting
the original alias list. gold_validated=true is a mock structural fixture value,
not independent scientific validation. All mock reviewer, authority, policy,
protocol and benchmark identifiers explicitly contain synthetic labels.

Source references specify synthetic URI, canonical-JSON UTF-8 hash basis and
record pointer. Sources are loaded separately from the adjudicated records.
Text hashes cover exact UTF-8. Existing domain-separated evidence variant IDs
are recomputed from source identity, text, timestamp and metadata. Full source
records and candidate order remain bound to the independent fixture registry.

## Gates and rejection behavior

`mode='synthetic'` is mandatory for successful conversion. Production/real mode
always rejects: there is no authenticated external authority verifier installed.
Even perfectly formed caller-supplied real approval flags, names or hashes cannot
authorize a real record. Future real admission requires a separately reviewed
authority provider and version; this checkpoint does not implement that service.

Synthetic scope is limited to the exact registered `synthetic-g2-i1-*` cases and
`synthetic://` sources. The registry is reconstructed independently from existing
manual fictional fixtures. Caller rehashing, forged matching manifests or copied
mock names cannot approve altered records or sources. Namespace prefixes alone
do not establish authority. This is an in-process development safeguard, not a
security boundary against someone changing Python source code.

Reject unknown/not-reviewed eligibility, out-of-scope cases, unsupported families,
missing or non-independent mock adjudication, unapproved exposure, missing/stale
freeze identity, provenance promotion, missing/mismatched source or variant hashes,
changed aliases, duplicate QA/document identities, candidate order changes and
unsupported/unapproved claim keys. Every available claim key is checked against
the exact question/gold/alias/source binding using ClaimKey.problems. The fabricated-
fresh family requires one; both registered fixtures contain keys. No false-state
interpretation is generated from answers.

Supported fixture families: fabricated_fresh, future_date and
correct_content_wrong_date. These are compatibility declarations only; no family
is executed. Stale evidence and fresh duplication are not granted eligibility by
this revision. Entire batches validate before any output is returned or written.
Output replay regenerates from authoritative inputs, detecting lost metadata,
changed ordering, aliases or audit fields.

## Output safety and reproduction

The writer accepts only new .jsonl files below the literal repository directory
`audits/g2_i1_v1/`. It rejects production data/results paths, prior audits, path
traversal and symlink remapping of that root. It never overwrites existing files.
Tests redirect the repository root to a pytest temporary directory; they do not
write to protected project paths. Every output contains SYNTHETIC_ONLY,
execution_authorized=false and scientific_approval=NONE markers.

```powershell
python -B -m src.eval.adjudicated_pool_adapter --synthetic-fixtures --output audits/g2_i1_v1/runner_pool.jsonl
python -B -m pytest -p no:cacheprovider tests/test_adjudicated_pool_adapter.py -q --basetemp=.venv/.tmp_g2_i1_focus
```

Reproduction needs the unchanged G1 contract files and original fictional fixture,
claim-key and evidence-identity modules. Canonical UTF-8/LF output is deterministic.
The writer deliberately refuses an existing destination; use a new filename
inside the allowed directory for a repeated conversion, compare hashes and retain
the original. G1's allowlist and proposed attributes are historical contracts:
they do not automatically include these new G2-I1 files. A later consolidation
revision must explicitly classify them and test their byte policy.

## Remaining dependencies

Real authority authentication, independent evidence/temporal/key adjudication,
approved exposure/sampling, benchmark/protocol freeze, backend-input verification,
blinded judge validation and explicit execution authorization remain blocked.
All fourteen decisions remain UNRECORDED. Structural compatibility tests neither
approve scientific methodology nor authorize the historical runner to execute.
