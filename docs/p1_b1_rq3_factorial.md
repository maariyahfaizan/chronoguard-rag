# P1-B1: generator-isolated RQ3 factorial preparation

Status: development-only synthetic construction. No inference, scientific
conclusions, key approval, sample selection or attack success rates. Baseline:
`de08db9712292d424e614c5e36e480ca16862128`. Fourteen scientific decisions remain
UNRECORDED. Judge validation remains BLOCKED; main attacks NOT AUTHORIZED.

## Scientific purpose and proposed factors

RQ3 asks whether conflicting evidence presentation cues influence generator
answers when retrieval is removed from the pathway. This design supplies both
passages directly. It cannot measure retrieval susceptibility, ranking, selection
or end-to-end attack effectiveness. Those are different experimental questions.

| Factor | Level 1 | Level 2 |
| --- | --- | --- |
| Newer-looking date assignment | Correct passage newer | Incorrect passage newer |
| Header wording | `General notice:` | `Latest update:` |
| Passage order | Correct first | Incorrect first |

All eight Cartesian-product cells are constructed exactly once per fictional
case. The same header wording is applied to BOTH passages in a cell; this is an
explicit proposed operationalization, not a recorded supervisor decision. It
avoids changing which passage has a header as a hidden fourth factor. Header
wording, its length and its tokenization are a bundled intervention. No claim
of a purely semantic header effect is justified by this construction alone.

Date cues use `2020-01-01` and `2020-01-02`, the same two values in every cell,
swapping their assignment to source identities. Each passage contains the
literal line `Assigned date cue: YYYY-MM-DD`. These are experimental cues, not
authenticated publication dates, temporal-validity adjudications or changes to
the evidence bodies or original fixture timestamps. Date cue policy and header
operationalization require external scientific approval before real evaluation.

Proposed contrasts, conditional on later approval: average the date-assignment
contrast over header/order; average header and order contrasts over the other
factors; use differences of those contrasts for two-factor interactions and a
difference of interactions for the three-factor contrast. No outcome variable,
confirmatory estimand, threshold, sampling policy or multiplicity treatment is
approved here. Any eventual outcome coding requires approved keys and a validated
judge. Effects must retain case pairing/dependence; this checkpoint supplies no
power claim or population generalization.

## Implementation and invariants

`src/attacks/rq3_factorial.py` uses only the two existing fictional smoke fixtures
and the existing pure generator prompt helper. It exposes no retrieval ranking
or selection argument. Every cell has exactly two directly supplied passages.
Stable IDs, question, correct/incorrect bodies and UTF-8 body hashes remain fixed.
Role labels are audit metadata and are not inserted into the model prompt.
Source origin and original fixture timestamps remain separate from assigned cues.

Generation settings are read from the existing evaluation and revision configs:
Mistral revision `63a8b081895390a26e140280378bc85ec8bce07a`, 1,500 characters per
passage, 64 new tokens and deterministic decoding. The template, revision record,
evaluation config and generation settings are hashed. Prompt instructions are
unchanged. Canonical replay against separately supplied authoritative fixtures,
date pair and settings rejects missing/duplicate cells, body/identity/order/date
changes, prompt-template changes and any undeclared setting or allocation change.
Output hashes alone provide no authenticity or independent acceptance.

## Length, visibility and tokenization

Both passages receive the same fixed character cap: total allocated budget is
3,000 characters in every default cell. This is equal context allocation, not
equal rendered length. Neutral headers contain 16 characters, freshness headers
15, so two neutral headers make the assembled prompt two characters longer.
There is no padding intervention or content-dependent truncation/reallocation.
The audit explicitly reports unequal rendered lengths. It never claims token
equivalence from character or BM25 counts.

Each cell reports passage header/body/rendered character and UTF-8 byte lengths,
exact body spans, BM25 literal-space token counts, retained characters and
truncation boundaries, both claims' complete visibility and total prompt length.
Across-cell and within-cell asymmetric claim visibility is detected. Truncated
synthetic constructions fail the complete-evidence visibility check; structural
schema validity is not sufficient for a usable factorial input. No failed input
is repaired by silent body edits or condition-specific budget changes.

All default synthetic claims fit within the configured cap. Final neural
tokenization, chat-template token budgets and token-to-body visibility remain
UNKNOWN; token-level balancing is UNVERIFIED. The P1-A2 inventory shows cached
Contriever tokenizer files consistent with the existing inventory but unavailable
runtime, and unavailable BGE/Mistral caches/runtimes. BM25 counts are diagnostics
only in this generator-isolated experiment; no BM25 retrieval is performed.

The existing P1-A2 capture boundary was inspected: it stops before inference and
can later verify the real tokenizer/tensor representation. This checkpoint
assembles the pre-chat-template prompt only. It does not call that boundary with
substitute tokenizers or claim real model receipt. Existing generator code and
all prior audit/source files are preserved.

## Reproduction and audit files

```powershell
python -B -m src.eval.rq3_factorial_audit --output audits/p1_b1_v1
python -B -m pytest -p no:cacheprovider tests/test_rq3_factorial.py tests/test_offline_input_audit.py tests/test_matched_controls.py -q --basetemp=.venv/.tmp_p1_b1_focus
```

The writer verifies P1-A2 output/source hashes and the earlier P1/B1/B2/C1 checks,
143 recorded source inputs, 23 published candidate files and all 279 protected
files before writing. It stops on any mismatch. Historical bytes are read for
hashing only, not for outcome analysis. It writes sixteen cells, two case audits,
tokenizer inventory, integrity record, source inventory, summary and checksum
map under a new versioned directory. Canonical UTF-8/LF output is deterministic
for unchanged sources/runtime; differing existing output is not overwritten.

Tests cover coverage, date swapping, wording/order, direct presentation,
unchanged bodies and IDs, deterministic rendering, missing/duplicate cells,
confounds, truncation and explicit unavailable-tokenizer status. No source,
test, frozen artifact or audit from an earlier checkpoint is modified.

## Pending decisions and verification

Independent review must approve the scientific operationalization, date-cue
interpretation, contrasts and eventual outcome coding. Exact offline generator
tokenizer/chat-template verification and final-input traceability are still
required. Real answer/claim keys, temporal evidence and judge validation require
their own independent approval. No such approval or judgment is generated here.
