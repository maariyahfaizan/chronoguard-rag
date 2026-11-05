# P1-A2: offline backend and final-input observer

Status: PARTIAL. Synthetic development evidence only. No inference, downloads,
dependency updates, human review, key approvals or scientific decisions.

## Verified evidence and backend identities

Baseline Git commit: `de08db9712292d424e614c5e36e480ca16862128`.
Model identities come from `configs/model_revisions.yaml`, not cache directory
names. Frozen Week 4 runs did not record revisions; these pins must not be
attributed retroactively to them.

| Backend | Configured identity | Verification available here |
| --- | --- | --- |
| BM25 | `rank-bm25==0.2.2`; `text.split(' ')` | Exact counts; no retriever token cap |
| Contriever | `facebook/contriever@2bd46a25019aeea091fd42d1f0fd4801675cf699` | Tokenizer files match the existing snapshot inventory; runtime unavailable |
| BGE reranker | `BAAI/bge-reranker-base@2cfc18c9415c912f9d8155881c133215df768a70` | Exact cache and runtime unavailable |
| Mistral generator | `mistralai/Mistral-7B-Instruct-v0.2@63a8b081895390a26e140280378bc85ec8bce07a` | Exact cache and runtime unavailable |

The active environment has no Transformers, Tokenizers, Torch or
Sentence-Transformers. Requirements pin Transformers 5.0.0, Torch 2.10.0 and
Sentence-Transformers 5.4.1; the low-level Tokenizers version is not independently
pinned there. No approximate tokenizer substitutes are used. The optional loader
requires Transformers 5.0.0, exact configured model revision, a separately trusted
tokenizer-file manifest, `local_files_only=True`, and `trust_remote_code=False`.
Runtime versions and file hashes are recorded separately. A matching inventory
does not independently authenticate its original source. No new manifest of
cache bytes is promoted into a trust anchor.

The Contriever cache configuration names `BertTokenizer`, lowercases, tokenizes
Chinese characters and sets `strip_accents: null`, with model maximum length
512. Null is retained rather than asserted to be an independently measured
normalization behavior. Dense encoding applies padding and `truncation=True`
without an explicit max length. Actual normalization and special-token counts
require the missing runtime. BGE calls CrossEncoder on query/passage pairs;
its shared budget and special tokens cannot be reconstructed with whitespace
counts. Mistral calls `apply_chat_template` with `add_generation_prompt=True`,
`return_dict=True`, `return_tensors='pt'`. There is no explicit whole-prompt
truncation argument in this path. Missing caches prevent exact chat-token counts
and context-limit verification.

## Reproducible static audit

```powershell
python -B -m src.eval.offline_input_audit --output audits/p1_a2_v1
```

The command verifies fixed B1/B2/C1/P1-A1 checksum-manifest digests, all their
listed outputs, C1's 143 source inputs, P1-A1 source hashes, 23 published candidate
files and the 279-file protected digest before writing any new output. It stops
on a mismatch. It reads historical bytes for integrity hashing, not outcome
analysis. It never changes prior audit outputs. New outputs are canonical UTF-8
with LF; differing existing outputs are rejected. Source inventory and output
SHA-256 maps identify this uncommitted engineering candidate.

All ten P1-A1 pairs are replay-validated against the existing fictional fixtures.
All twenty conditions get candidate-level identities, source metadata, body and
rendered hashes, character/byte counts, BM25 token counts, lengths and unavailable
backend fields. Four header pairs additionally receive exact differing spans and
separate header/body/rendered counts. Six metadata/date pairs have unchanged
text inputs between their arms. No scientific state or claim key is derived.

Default headers are 16 versus 15 characters but two literal-space tokens each.
For the false-claim fixtures: Luma has a 56-character body and 72/71-character
rendered passages, each with 10 BM25 tokens; Cedar has a 48-character body and
64/63-character rendered passages, each with 10 BM25 tokens. Exact per-fixture
values are authoritative in `input_audits.jsonl` (not approximate backend counts).
All fixture claims survive the declared 1,500-character passage cap. Token-level
truncation and whole-model capacity remain UNKNOWN.

## Opt-in instrumentation and evidence levels

`instrument_pair(..., enabled=True)` is restricted to synthetic fixture records.
It uses explicit ordered synthetic retrieved and selected slot plans; those
plans are not observed retrieval results. It records QA/condition/pair IDs,
candidate/retrieved/selected document order, metadata, original passage text,
retained text, truncation boundaries, exact body spans in the assembled prompt,
and model/config/source identities. The existing pure prompt helper is reused.
Its records establish complete-body presence in the assembled character input,
not final tokenized input or model receipt. Raw text is limited to the supplied
synthetic context; no environment variables or credentials are collected.

Validation distinguishes the declared header/date intervention from undeclared
body, metadata, identity, source-slot, order or setting changes. It detects
unequal retrieved/selected allocations, unexpected per-condition passage caps,
missing complete target bodies and asymmetric visibility at truncation
boundaries. A whole-prompt character cap exists only as labeled synthetic fault
injection for testing, never as a claimed production truncation policy.

`capture_generate_boundary` executes only the existing `generate_answer` function
definition with a non-inferencing sink. Its `generate` method captures arguments
and immediately stops, before generation or decoding. Production generation code
is not edited. Synthetic test doubles check exact chat-template arguments and
capture plumbing; their character-token IDs are never reported as verified
Mistral counts.

`capture_verified_trace` can attach real token IDs/counts to a trace if an exact
verified local Mistral tokenizer and tensor runtime are supplied later. It rejects
configuration mismatches with production defaults and checks exact prompt replay.
Captured token IDs establish the call-boundary representation; model receipt
remains NOT_EXECUTED, and complete-body survival in token IDs remains UNKNOWN
until offset or roundtrip validation. This real-backend path cannot run here.

Existing runner `input_token_count` values tokenize the plain prompt, whereas
generation applies a chat template. They cannot establish the final chat-input
length. No historical result is reclassified. No main runner is wired to this
observer, and no real retrieval or generator inference occurs.

## Pending evidence and authority

Exact tokenizer runtime/cache availability, joint-budget and chat-template
verification, token-to-body traceability, and any eventual real-run instrumentation
review remain outstanding. Supplying a cache does not grant scientific approval.
The fourteen decisions remain UNRECORDED, real keys unapproved, scientific judge
validation BLOCKED and Week 6 main attacks NOT AUTHORIZED.

Focused tests:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_offline_input_audit.py tests/test_matched_controls.py -q --basetemp=.venv/.tmp_p1_a2_focus
```
