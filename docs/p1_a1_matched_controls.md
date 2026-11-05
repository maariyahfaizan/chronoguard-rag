# P1-A1: development-only matched-control framework

Status: engineering construction and audit only. NOT FINAL / NOT APPROVED.
No attack execution, benchmark selection, scientific claim-key creation, human
judgment or supervisor decision is part of this checkpoint.

## Existing implementation evidence

Published baseline: `de08db9712292d424e614c5e36e480ca16862128`.
`src/attacks/attack_pool.py` implements Week 5 atomic/nested 1/2/5-poison
replacement, protects gold IDs and preserves candidate count and document-ID
sets. Independent random target selection across conditions is unsuitable for a
matched comparison. Some constructors copy source metadata or rebuild target
dictionaries; preserving an ID set alone does not establish unchanged ordering.
`src/attacks/pilot_protocol.py` defines fabricated-fresh, future-date,
duplicate-fresh, and correct-content/wrong-date (30-day and zero-day) conditions;
stale evidence requires reviewed inputs. These historical conditions are not
reinterpreted as approved matched controls.

The new framework reuses stable-ID validation from `src/attacks/identity.py`,
strict UTC date validation from `src/eval/evidence_identity.py`, the two manually
authored fictional fixtures in `src/attacks/freshness_smoke.py`, and the literal
BM25 tokenizer in `src/eval/bm25_header_diagnostic.py`. It leaves the existing
attack runner, generators and historical files unchanged. Prompt auditing uses
only the existing pure `truncate_passage` and `build_prompt` function definitions
from `src/generation/generate.py`, extracted through AST to avoid importing
model runtimes. Their source hash is recorded. This is local trusted-source
execution, not a sandbox for arbitrary code.

## Construction and authoritative validation

`header_pair(base, slots, settings, body)` requires an explicit stable QA ID,
original question, gold answer/aliases, gold document references, unique ordered
candidate identities, explicit UTC timestamps, sorted unique nongold target
slots, and retrieval/generation/evaluation settings. Inputs are deep-copied.
No random slot choice or outcome-dependent ordering occurs. Poison budget is
exactly the number of declared slots; identical placement is used in both arms.

The default arms are `General notice:\n` and `Latest update:\n` followed by the
exact same caller-supplied body. These have matched BM25 token counts, not
necessarily matched character or generator-token lengths. Custom explicit header
wording is permitted and audited; token matching is not presumed. Candidate
metadata, dates, source identities, document identities, ordering, gold answers,
aliases and settings remain identical. Rendered content hashes necessarily
change; the shared body and original record digest are recorded separately.
Original metadata is retained as source metadata, not relabeled as the hash of
the new rendered variant. A `false_claim` declaration is not semantic validation
or an approved claim key. Correct-content controls must copy an exact original
gold-source body; even that check is mechanical, not independent semantic review.

Call `validate_pair` with the original base, slots, settings and authoritative
construction arguments. It replays the complete construction and compares
canonical JSON, rejecting every undeclared difference, including altered bodies,
dates, settings, budgets, identity, ordering and output declarations. Never derive
those authoritative arguments from an untrusted pair. Digests detect changes;
they do not authenticate a caller or scientific authority. Plain JSON containers
only; no nonfinite floats or custom mutable objects.

## Token, length, truncation and visibility evidence

`audit_header_pair` reports exact differing header spans (Unicode code-point,
half-open offsets), body spans, character/UTF-8 lengths and separate header,
body and full-rendered token counts. Counts are not additive across boundaries:
the frozen BM25 tokenizer splits literal spaces and retains newlines in tokens.
Whitespace splitting is explicitly a sensitivity diagnostic, not the production
BM25 tokenizer. Optional caller-supplied offline tokenizer adapters must be named;
their counts do not establish an input truncation policy or authenticity.

The declared generator passage limit is used by default (current pipeline:
1,500 characters). An explicit audit override is labeled as differing from the
configuration. Full-body survival is checked using its exact known span, not a
substring elsewhere in the prompt. Caller-supplied retrieved slots preserve
retrieval order when reproducing prompt assembly. The target can be absent from
retrieved context or partly truncated even when ranked in the candidate pool.
An exact context log must bind pair digest, QA ID, ordered slots and complete
prompt. It establishes only logged pretokenization context; it does not prove
the actual model received the claim. Final input-token instrumentation is still
required. Actual model visibility stays UNKNOWN here.

Local verified availability: BM25 tokenization and rank-bm25 are available.
Transformers, tokenizers and Torch are absent from the active Python environment.
A pinned Contriever tokenizer configuration is cached locally, but cached files
alone cannot supply verified counts without its runtime. No model/tokenizer was
downloaded. Dense, reranker and generator token counts and token-limit risk are
reported UNAVAILABLE/UNKNOWN. The existing dense encoder uses tokenizer
truncation with an implicit backend limit; the reranker has a joint query/passage
budget. These cannot be replaced with whitespace counts or inferred limits.
The generator calls its chat template without an explicit input truncation
argument; passage-character survival is distinct from whole-chat token capacity
and possible model input errors. No actual context logs were collected or real
held-out outcomes inspected.

## Negative-control invariants

`date_pair` supports three explicitly declared transformations:

* Future metadata only: original target date versus
  `max(question timestamp, original target timestamp) + positive days`.
* Unchanged-content timestamp shift: original target date versus original target
  date plus a nonzero signed number of days.
* Correct-content duplication: exact original gold-source text in the same
  nongold target slots in both arms, source timestamp at zero days versus source
  timestamp minus a positive offset (the synthetic audit uses 30 days).

Only target timestamps differ between these arms. Duplication preserves target
IDs/metadata rather than pretending a copied passage is a newly authenticated
source. Source slot and exact original source record remain traceable through
the authoritative base and declarations. No dates are inferred from filenames
or prose; naive/non-UTC dates are rejected. Header pairs also support correct
content with identical metadata and dates. Unexpected changes fail replay.

E1–E4 BM25/dense/hybrid/reranker interfaces take text, not timestamp metadata.
Metadata-only pairs therefore have identical text inputs to those interfaces.
`metadata_visibility` records this interface distinction and NOT_MEASURED
effects; it never asserts empirical score changes. A future metadata-aware
adapter can observe dates, but its behavior must be measured separately.

## Retrieval interpretation and remaining limits

`src/retrieval/bm25.py` fits BM25Okapi anew on each candidate pool. Header tokens
can change document lengths, average length, document frequencies, vocabulary,
IDF and the epsilon floor, changing scores even for unchanged documents. Literal
space splitting can attach a newline to the first body word. Matching header
token counts does not remove lexical/DF effects. Dense truncation, reranker
joint-budget truncation and generator passage truncation introduce additional
mechanisms. End-to-end score/rank changes are not proof of semantic freshness
preference. This checkpoint runs no inference or new attack evaluation.

The framework does not automatically approve neutral semantics, false-state
equivalence, evidence validity, exposure policy, eligibility, estimands or any of
the fourteen UNRECORDED supervisor decisions. It cannot certify scientific
correctness of a gold flag, caller-supplied settings, or final model receipt.
Backend-tokenizer audits and authenticated final-context instrumentation remain
required before any authorized evaluation. Main attacks remain NOT AUTHORIZED;
the scientific judge-validation gate remains BLOCKED.

## Reproduction

From the repository root:

```powershell
python -B -m src.eval.matched_control_audit --output audits/p1_a1_v1
python -B -m pytest -p no:cacheprovider tests/test_matched_controls.py -q
```

The first command emits ten synthetic pairs (four header pairs, six date pairs),
their audits, a source SHA-256 inventory, summary and output checksum map. It
refuses to overwrite differing existing output. Identical reruns are byte-stable
in the same source/runtime environment. JSON is canonical UTF-8 with LF endings.
No B1/B2/C1 artifact is rewritten. Raw-byte source hashes can differ after Git
newline conversion; preserve bytes or explicitly verify separately normalized
hashes without claiming raw equivalence. Integrity checking of historical logs
reads bytes for hashing only, not held-out scientific outcomes.
