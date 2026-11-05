# G2-I2: blocked synthetic matched-control request adapter

Status: SYNTHETIC_ONLY / NOT_AUTHORIZED_FOR_EXECUTION. The adapter performs no
retrieval, generation, attack execution, benchmark selection or scientific approval. All prior artifacts,
historical runners and fourteen UNRECORDED decisions remain unchanged.

## Actual runner interface and compatibility scope

The pilot orchestrator constructs function calls, not a generic request object.
It provides JSONL input_path, log_path, run_metadata and loaded runtime objects:

| System | Existing entrypoint | Explicit retrieval arguments | Runtime bindings |
| --- | --- | --- | --- |
| E1 | scripts/run_baseline_streamingqa.py:run_baseline_streamingqa | top_k | model, tokenizer |
| E2 | scripts/run_dense_streamingqa.py:run_dense_streamingqa | top_k | model, tokenizer, retriever_model, retriever_tokenizer, retriever_device |
| E3 | scripts/run_hybrid_streamingqa.py:run_hybrid_streamingqa | candidate_top_k, final_top_k, rrf_k | same as E2 |
| E4 | scripts/run_hybrid_reranker_streamingqa.py:run_hybrid_cross_encoder_streamingqa | candidate_top_k, fused_top_k, final_top_k, rrf_k | same as E2 plus reranker_model |

Configuration comes from experiment_params/load_eval_config and pinned revisions.
The adapter reads function signatures through AST and uses inspect.Signature.bind
without importing model-bearing runner modules. It validates the actual pool
record with attack_pool._validate_record. Tests serialize payloads to temporary
files and read them using pilot_protocol.read_jsonl. This establishes schema and
keyword-binding compatibility, not executed retrieval/generation behavior.

The new envelope is `chronoguard.matched-runner-request/v1`; it is NOT a new API
that existing runners accept directly. No dispatcher or executable materializer
exists. Input/log paths are non-path sentinel strings, runtime bindings are names
only, and calls never execute. Replacing these tokens requires a future explicitly
authorized adapter. The historical runners do not enforce these authorization
markers themselves; the envelope must not be passed blindly to them.

## Registered inputs and gates

G1 contract A and B remain unchanged. G2-I1 outputs are authoritatively replayed
against its registered fictional records and separate source mapping; copied
synthetic flags, edited identities or caller-rehashed records are insufficient.
G2-I1, P1-A1 and P1-A2 output/source manifests are checked before request building.
The complete earlier chain and protected artifacts are checked at checkpoint
entry and exit. Missing inputs stop construction.

Only mode='synthetic', the two registered fictional cases, supported E1-E4 system
profiles and target slot [1] are accepted. No real QA IDs, unknown eligibility,
provenance promotion, unapproved keys, reordered candidate records or unregistered
pool mutations are admitted. Custom configurations must exactly match the
authoritative loaded configuration. Real execution paths are rejected in call
templates and output writing. No synthetic marker serves as scientific approval.

## Paired construction and invariant proof

For each case/system, the false body comes from the registered synthetic claim
context. The claim's reviewed-body variant is retained separately from original
slot lineage. P1-A1 header_pair/validate_pair perform the shared insertion at the
same nongold slot, with fixed poison budget one and default General notice versus
Latest update headers. No attack_pool.apply_attack or retrieval selection runs.

Question identity, original answers/aliases, candidate document/source identities,
order, timestamps, inherited metadata, slot, body, all settings and evaluation
definition are identical between pool payloads. The proof strips only the declared
header and compares complete canonical pool records. Freshness-dependent retrieval
ranks or generator-selected context are not assumed or fabricated.

Inherited candidate variant_id/source references identify ORIGINAL SLOT lineage,
not the modified rendered text. false_claim_variant_id identifies the registered
claim body without its header. The exact rendered intervention has its own UTF-8
hash. These scopes are explicit in each request; do not treat an inherited slot
variant ID as authentication or a recomputed identity of the rendered poison.

Each request records pair/condition ID, source QA ID, original pool hash, source
and false-claim variant identities, body hash, exact header/body/rendered text,
rendered hash, whole payload hash, configuration/hash, candidate order, slots,
budget, source entrypoint hash, keyword template and legacy logging projection.
The request hash excludes only its own hash field. Output validation independently
rebuilds the full expected request, so caller-rehashed changes are still rejected.
Duplicate pair IDs and duplicate system profiles are rejected.

Pair/condition labels, hashes and run_metadata are trace fields that differ by
design; the pool payload's only cross-condition intervention difference is header
text. Both pool rows use a common matched-header attack_condition marker so the
legacy logger does not silently label the modified pool clean. The actual
attack_log_fields helper verifies that projection. Distinguishing the two headers
requires the condition_id in run_metadata; no historical logger is modified.

## Configuration and prompt boundary

Both arms bind identical explicit retrieval parameters, model revision pins,
generator configuration and evaluator source identity. Current generator defaults
are 1,500 passage characters, 64 new tokens and do_sample=False. The drivers do
not expose these as generation overrides; a configuration differing from these
defaults is rejected as unrepresentable by this unchanged call interface.
The float16 dtype argument is recorded separately from the unconfigured
bitsandbytes compute dtype. Loaded runtime identities remain unverified.

The runner retrieves first, then passes selected passage strings to build_prompt
and generate_answer. No retrieved/selected passage list, prompt or final token IDs
is produced in G2-I2. Final generator visibility is UNKNOWN_NOT_EXECUTED. Existing
tokenizer unavailability and P1-A2 final-input verification gaps remain. Candidate
rank alone cannot establish visibility or complete-body survival.

The evaluation_rule explicitly identifies the legacy StreamingQA evaluator by
source SHA. Claim-specific v2 is not silently wired into the runners; any future
v2 outcome processing needs its own approved keys, rubric and integration. No
adoption labels or efficacy outcomes are computed in this checkpoint.

## Reproduction, outputs and preservation

```powershell
python -B -m src.eval.matched_runner_requests --synthetic-fixtures --output audits/g2_i2_v1/request_pairs.jsonl
python -B -m pytest -p no:cacheprovider tests/test_matched_runner_requests.py -q --basetemp=.venv/.tmp_g2_i2_focus
```

Default output: eight pairs / sixteen blocked requests (two fictional cases,
four systems). Requests are embedded audit data, not executed calls or real pool
files. The writer permits only new JSONL paths under the literal
audits/g2_i2_v1 root; symlink redirection, production/prior-audit paths and existing
destinations fail. Reproduction uses a new filename under that root and compares
raw hashes. Source inventory, validation and integrity reports bind this candidate.

All new JSON is canonical UTF-8/LF. G1's historical allowlist and attributes
proposal do not automatically include G2-I2; future controlled consolidation must
explicitly update that contract. No .gitattributes or prior source/audit changes
are made. Main attacks remain NOT_AUTHORIZED; scientific validation remains blocked.

## Validation deviation

The initial broad regression selection included pre-existing synthetic BM25
retrieval unit tests. Those toy retrieval calls exceeded G2-I2's no-retrieval
restriction even though no generated request, held-out inference or main attack
was executed. This is recorded explicitly in validation.json; the adapter and
CLI themselves did not invoke retrieval. A narrower regression command excluding
retrieval diagnostics was then run and recorded separately. The broader passing
count is not represented as evidence that the no-retrieval boundary was respected.
Future validation must use an explicit no-execution test allowlist.
