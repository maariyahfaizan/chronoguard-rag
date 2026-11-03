# Development population feasibility

## Verified evidence

Read-only inventory on 2026-11-03; exact text identities unless stated otherwise.
Question clustering uses NFKC, casefolding and collapsed whitespace. Generated
answers are exact strings; no labels were recomputed for real answers.

| Artifact population | Rows | Question clusters | Distinct question/answer pairs | Other evidence |
|---|---:|---:|---:|---|
| `logs/streamingqa*_run*.jsonl` (eight existing files) | 800 | 100 | 277 | 100 records/file; four retrievers, chunked and unchunked variants |
| `logs/pilot_attacks/clean__E*.jsonl` | 12 | 3 | 6 | Four systems |
| `logs/pilot_attacks_v2_nested/*__E*.jsonl` | 180 | 3 | 27 | 60 files, four systems, five conditions, n=1/2/5 |
| Clean plus corrected attack pilot | 192 | 3 | 27 | Clean adds no new question/answer pair |
| StreamingQA plus corrected pilot | 992 | 100 | 298 | Pilot questions are within the 100 development questions |

There are also 277 distinct answer strings in StreamingQA and 27 in the attack
pilot. These counts do not establish distinct generation events or distinct judge
inputs: an identical answer with a different source contract is a different input.
Pilot CSV inventory independently gives 180 attacked rows, 27 question/answer
pairs, and 49 question/condition/answer pairs. Systems each have 45 attack rows;
each of five conditions has 36. Only fabricated_fresh (36 occurrences) supplies
fabricated false-claim exposures; the pilot has no reviewed stale-evidence cases.
Legacy pilot outputs are excluded from this candidate population.

Duplicate signatures: using normalized question + exact JSON prompt + exact
answer gives repeat excess of 7 in StreamingQA, 103 in attacked pilot and 115
in clean-plus-attacked pilot (77 distinct signatures among 192 rows). These are
identical-content signatures, NOT proof of duplicate executions. Systems may
independently produce identical answers; metadata-only controls deliberately reuse
prompts/answers. Event-level duplication cannot be certified without generation
provenance. Within-file/intersystem equality must not be called independent data.

Available source/evidence inventory:

- `data/processed/streamingqa_control_pools_chunked.jsonl`: 100 records; all 100
log question clusters match this pool. It has 2,069 candidate entries and 2,051
unique doc IDs, with text, timestamp, parent ID, source-document flag and chunk
metadata. Stored `gold_validated` flags are 97 true/3 false, not independent
semantic approvals. The unchunked logs require reconciliation to their own pool.
- `streamingqa_attack_pilot.jsonl`: three corrected `source_qa_id` identities
(eval-001639, eval-001952, eval-005229), respectively 20/22/20 candidate chunks and
1/2/2 stored gold chunk IDs.
- `streamingqa_pilot_fabricated_payloads.jsonl`: three payload IDs, one per pilot
question, schema `chronoguard.pilot_payload.v2`, source IDs and query hashes, text
and timestamps. These establish candidate identities, not semantic validity.
- Pilot claim domains are numeric/numeric/stance. General development claim types
have not been independently annotated. Entity/span and temporal-state coverage
cannot be promised from row counts. No approved real keys or v2 strata exist.

Leakage evidence: the held-out proposal and `sampling_audit.json` report the 100
Week 4 question texts map to 101 excluded raw IDs, including all pilot IDs. The
reserve and filtered screening queue have zero overlap with the three pilot IDs
in this inspection. The exposure ledger has ten additional exposed IDs and the
filter audit reports ten exclusions. This is not a completed ID/text overlap
certification for every artifact. Stable-ID reconciliation and normalized-text
exclusion remain mandatory, especially the known one-text/two-ID ambiguity.
No held-out generated answers were opened. Evidence-screening candidates are not
answer records and are not added to the validation population.

Existing human artifacts: `annotation.csv` has 112 binary labels (56 zero/56 one);
`annotation_rater2.csv` has 30 (15/15), all 30 item IDs shared with the first file.
`key.csv` has 112 mappings with system/stratum and judge information. These are
historical FreshQA binary annotations, without repaired v2 key/evaluation binding.
They do not establish blinded multiclass agreement or poison-adoption accuracy.
FreshQA and legacy pilot data are excluded from the proposed primary population.

## Proposed methodology

Potentially eligible after review: the 36 fabricated-fresh occurrences on three
questions, subject to source/gold/alias collision resolution, exposure history,
complete key approval and deduplication. Other development answers can support
correctness/review behavior only under a separately approved applicable contract;
never invent false propositions merely to make benign controls compatible with
the current judge. A proposed no-false-claim control mode would require separate
implementation review. Do not count 298 answer pairs as 298 eligible keyed inputs.

Start with the audited development sources above, then publish actual eligible
input, question and machine-stratum counts BEFORE allocation. A 200-input target
is numerically possible only across the broader development sources; it is not
currently established as scientifically eligible or representative. Eighty
predicted-positive cases cannot be promised; historical v1 labels are not v2 strata.

## Pending human decisions

Approve population scope and contract applicability; reconcile event provenance,
all raw IDs and exposure exclusions; independently classify claim types and review
evidence/keys; decide whether a larger separately authorized development collection
is necessary. Three false-claim question clusters cannot establish general validity
across entities, temporal claims, systems or claim types.
