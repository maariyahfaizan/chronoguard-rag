# G2-I4: non-executing RQ3 factorial export

Status: SYNTHETIC_ONLY / NOT_AUTHORIZED_FOR_EXECUTION. No retrieval, generation,
judging, numerical statistical inference, network, model loading or real records.
All prior checkpoints, historical runners and fourteen UNRECORDED decisions are
preserved. This is a structural export, not an observed outcome dataset.

## Inspected schemas and mismatches

P1-B1 provides sixteen registered construction cells: two fictional questions,
each with 2 x 2 x 2 factors. Its fields include synthetic_case_id, cell_id,
structured factors, two ordered passages, source body hashes, assigned date cues,
body spans, generator settings, prompt text and hashes. Its source cell ID uses
correct/incorrect date-assignment levels, not the statistical condition labels.

G2-I3 accepts only its registered G2-I2 request envelopes; an RQ3 construction cell
is not that type. This adapter does not impersonate those requests. It reuses
G2-I3's pinned, statically checked pure-helper extraction to assemble the two
directly presented RQ3 passages in the construction order. No runner is imported.
The reconstructed prompt must exactly equal the P1-B1 prompt and its UTF-8 hash.

P1-C1 expects question_id/family/condition/construction/retrieval/generator/outcome
rows, with provenance outside those strict row fields. Its current validator also
requires synthetic-stat-* IDs, whereas construction uses synthetic-smoke-* IDs.
Canonical source IDs remain unchanged here. A new, explicit pending canonical-ID
bundle profile records the field-compatible projection and provenance bindings;
direct ingestion by the legacy validator remains BLOCKED. It would require a
separately reviewed schema revision, not an alias or silent ID rewrite.

Judge v2 uses CORRECT, OTHER_WRONG, POISON_ADOPTED and NEEDS_REVIEW. No judge is
called or imported. No such observed label is assigned by this adapter. The
statistical schema literal is read using AST/literal_eval without importing its
estimators. Model-bearing and judge modules are denied by the execution guard.

## Explicit versioned factor mapping

Mapping version: chronoguard.rq3-factor-mapping/v1.

| Construction field | Allowed source | Analysis value |
| --- | --- | --- |
| newer_looking | correct | correct_newer |
| newer_looking | incorrect | incorrect_newer |
| header_wording | neutral / freshness | unchanged |
| passage_order | correct_first / incorrect_first | unchanged |

The condition string is formed from mapped newer/wording/order enumerations in
that order. It is never inferred from an arbitrary cell-ID substring. Missing,
extra or unsupported factor values fail. The source cell ID and question ID are
retained, while export_id binds source-construction hash, condition and mapping
version. Sorting uses canonical question identity and the explicit Cartesian
condition enumeration, independent of input order.

## Factorial and provenance validation

The full registered two-case synthetic fixture set is required; there is no
benchmark selection interface. Any missing, duplicate, modified, extra or real
cell is rejected before export. Every question must retain exactly eight unique
conditions. Both source role identities/body hashes, passage order, assigned-date
swap and shared two-date pair are checked. Headers and complete bodies must match
the registered rendering. Assigned dates remain experimental cues rather than
authenticated publication dates.

P1-B1 supplies body hashes but no formal evidence-variant ID. Those original
hashes are preserved. A separately labeled body_variant_sha256 is derived from
the synthetic document/body/timestamp/origin descriptor; it is not presented as
an authenticated original variant. Rendered-text hashes separately cover the
header/date/body variant. Source artifact and per-cell construction hashes bind
the exact parent artifact, not independent reviewer authority.

Each output records canonical question/cell IDs, mapped factors, ordered evidence
identities/hashes, date assignments, source construction hash, exact context and
prompt, their hashes, body spans, lengths, char-limit and visibility flags. Both
claims must survive the existing 1,500-character per-passage cap. Token balancing
is UNVERIFIED and actual model visibility UNKNOWN. No tokenizer counts are invented.

## Unobserved outcomes and analysis safety

Every record has outcome_state=UNOBSERVED, missingness_reason=NO_GENERATION_NO_JUDGING,
analysis_eligibility=NOT_ELIGIBLE_UNOBSERVED_AND_UNVERIFIED_INPUT and blocked execution.
Its statistical row projection uses family=rq3, construction=SUCCEEDED (static
construction only), retrieval=NOT_APPLICABLE, generator=UNVERIFIED, outcome=MISSING.
The frame keeps eligibility UNKNOWN and clean baseline MISSING. Character-level
claim presence is not converted to generator=YES.

analysis_bundle preserves strict row fields and places cell/provenance identity
in a separate bindings table. Its status is NOT_ESTIMABLE_UNOBSERVED.
estimator_inputs validates authoritative replay and then rejects unobserved data;
no numerical estimator is invoked. Export mutation cannot turn an unobserved
record into an observed one. There is no complete-case exclusion, zero imputation,
fabricated judgment, eligibility grant or scientific estimate.

## Guarded validation and reproduction

Run only:

```powershell
python -B scripts/validate_g2_i4_no_execution.py
python -B -m src.eval.rq3_analysis_export --output audits/g2_i4_v1/condition_export.jsonl
```

The dedicated test allowlist contains only tests/g2_i4/test_rq3_analysis_export.py.
Its source/imports, new adapter and boundary were inspected before execution.
Project conftest/config, external plugins and broad test collection are disabled.
G2-I3's guard is reused through a new subclass; its original file is not changed.
The extension denies judge/estimator imports and invocation in addition to
retrieval, models, generation, attacks, network and process execution. Eight
inert self-checks run before collection. Tests use harmless before-body tripwires,
not real prohibited operations. Profile rearming, per-test health checks and
maxfail=1 remain in force. This is reviewed-code defense in depth, not a sandbox
against arbitrary modified Python. The CLI runs under the same extended guard.

Tests cover full coverage, mappings, order, body/date/source hashes, missing and
duplicate cells, invalid conditions, unobserved-outcome gating, real IDs, path
escapes, deterministic output and forbidden judge/generator/retriever entry.
No repository-wide regression suite is run.

Outputs are newly versioned under audits/g2_i4_v1; no existing destination is
overwritten. Only new JSONL files under that literal audit root may be written by
the adapter. Production/prior directories and symlink escapes fail. Reproduction
uses a new filename under that root. Source inventory and SHA-256 manifest bind
the candidate; G1's publication/byte policy is not silently extended to it.

Real execution, independent evidence/key approvals, judge validation, token-level
visibility and scientific decision approval remain blocked. Structural condition
export success does not authorize analysis or an experiment.
