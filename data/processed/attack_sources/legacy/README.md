# Legacy attack-source files (audit only)

Nothing in this folder is read by any active script. The pilot builder and
validator load only the authoritative payload file, and they reject any file
that is not the `chronoguard.pilot_payload.v2` schema with a `source_qa_id`.

| File | What it was | Why it is legacy |
|---|---|---|
| `streamingqa_pilot_poison_payloads.LEGACY_AUDIT_ONLY.jsonl` | 13-row descriptive payload sheet (fabricated, future_date, duplicate_fresh, correct_content_wrong_date, stale marker) | Never read by any script. Its `question_id` values (`eval-007296`, `eval-001639`, `eval-018024`) are the qa_ids of raw records 0-2, not the pilot questions. Its non-fabricated rows describe texts that the attack code does not insert. |
| `streamingqa_week5_attack_manifest.LEGACY_AUDIT_ONLY.jsonl` | 45-row Week-5 planning manifest ("Attack pool has not yet been generated") | Never read by any script; superseded by `data/processed/attack_pools/pilot*/pilot_pools_manifest.json`. |
| `streamingqa_attack_pilot.pre_source_qa_id.jsonl` | The 3 pilot records before `source_qa_id` was added | Kept to show that only the identity fields changed. |
| `streamingqa_pilot_fabricated_payloads.pre_source_qa_id.jsonl` | The 3 fabricated payloads before the identity fix | Kept to show the wrong `question_id`s and that text/timestamps were not changed. |

The authoritative payload file is
`data/processed/attack_sources/streamingqa_pilot_fabricated_payloads.jsonl`.
See `docs/week5_pilot_validation_report.md`, section "Authoritative payload file".
