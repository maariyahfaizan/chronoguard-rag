# W6-R19 Checkpoint 2A: target-only 2008 evidence pilot

This checkpoint implements `src/eval/index_week6_target_evidence.py`, ingestion
profile `w6-r19-frozen-passages/v1`, and SQLite/output schema
`w6-r19-target-index/2a-v1`. The Checkpoint-1 identity contract remains
`chronoguard-evidence-identity/v1` without modification.

Only the selected retained **2008 passage dataset** is read. This command does
not read original WMT archives, download evidence, index other years, build
pools, select benchmark members, or assess semantic support. The canonical 400
candidate inputs reference 397 distinct parents; only target-parent passage
text and occurrence data are retained. Every source record is nevertheless
validated. Non-target aliases/conflicts are outside this index's identity scope.
The original auditor, its failed outputs, frozen artifacts, legacy pool builder,
and `docs/week6_heldout_protocol.md` remain unchanged.

## Exact ingestion profile

The profile definition and its canonical-JSON SHA-256 are embedded in each run
manifest. Passage objects require exactly three string fields:

| Field | Treatment |
| --- | --- |
| `doc_id` | Exact upstream passage ID; date sorting key, lowercase SHA-256 unsplit-field digest, original control separators, canonical nonnegative decimal passage suffix |
| `text` | Exact decoded JSON string, strictly encoded as UTF-8 for Checkpoint-1 byte identity |
| `timestamp` | Checkpoint-1 UTC RFC3339 subset; preserve accepted original spelling |

No extra field, including `evidence_fields`, is accepted by this frozen-input
profile. Designated additional identity fields are empty. Parsing rejects
duplicate JSON keys, NaN/Infinity, malformed UTF-8, unpaired Unicode surrogates,
invalid field types, invalid Gregorian dates, malformed IDs, non-UTC or malformed
timestamps, archive-year/day disagreement, and records outside the inclusive
merged canonical retention union. Publication time is preserved, not rounded.
There is no whitespace stripping, Unicode normalization, case folding, length
selection, or answer-based identity choice. Different JSON token spellings can
represent the same decoded text; original target raw lines are stored as BLOBs.
Bytes already replaced by the frozen extractor cannot be recovered here.

Physical lines use LF delimiters and count blank lines. Blank lines do not count
as passage records and break an observed passage run. A final unterminated
record is accepted. The default maximum physical line is 16 MiB; a larger line
rejects the run instead of being truncated. The limit is explicit in the
manifest and can be increased in a new run.

The unchanged canonical candidate validator checks windows checksum, ordering,
strata, reserve ranks, candidate metadata agreement, and exact evidence-centered
plus/minus 56-day windows. Inputs are strictly JSON-parsed first. The LF windows
checksum is `99da0f327616a1725ddf3a323d459868ebac9d498aa94cd2acf332c5638f8cab`;
only that existing checksum comparison normalizes CRLF. Candidate text and
evidence bytes are never normalized. All original candidate fields are copied
into the recovery ledger, including shared evidence IDs and additional answers.

## Source provenance and validation

Use an exact selected dataset root, not a recursive `/kaggle/input` root.
Discovery reuses the existing sidecar association rules, including nested
temporary-looking payloads, but strictly parses sidecars before interpreting
them. Output directories must be new and outside the selected dataset root.

Required extraction sidecar fields remain: `year`, `status`, `passages`,
`archive_url`, `windows_sha256`, `sorting_keys_md5`,
`deepmind_extraction_sha256`, `output_sha256`, `prepend_date`, and `parser`.
The profile requires year 2008, complete extraction status, the canonical
windows checksum, official sorting-key checksum, exact archive URL, date
prepending disabled, and the original parser label. The parser hash must match
the pinned local `third_party/streamingqa/extraction.py` bytes. An LF/CRLF parser
hash difference is not silently normalized. Sidecar raw bytes and hash are kept.
Optional content hashes are checked when present. Configuration declarations
must agree among representations; they remain declarations where original
configuration bytes are unavailable. The sidecar alone does not pin the exact
historical writer/adapter or certify original document boundaries.

Compression is determined from magic bytes. The scanner hashes physical
artifact bytes and exact decompressed-stream bytes separately in one pass,
checks full EOF/decompression and record count, and checks available sidecar
hashes. A zero-byte artifact is rejected. File size/mtime and sidecar bytes are
checked for changes during ingestion; the input mount must remain immutable.

Occurrence identity uses the **actual physical artifact SHA-256**, finalized
only after successful EOF and checks. A gzip and its plain counterpart have
different physical occurrence IDs. A plain-only Kaggle mount with no trusted
recorded content hash is `complete_provisional`: a new observed plain hash
cannot verify its declared historical gzip hash.

A matching verified original gzip counterpart can independently establish the
plain representation's historical equivalence. The scanner compares decompressed
bytes as well as hashes for multiple representations. Byte-identical physical
replicas retain separate provenance rows but share occurrences. Distinct gzip
and plain occurrences are retained; logical multiplicity counts equivalent
decompressed-stream line coordinates only once. This distinction prevents
mount duplication from inflating evidence multiplicity. Different declared
original outputs/counts/configurations or different representation contents
reject the run; no preferred representation is selected to hide a conflict.

Variant digest reuse compares complete Checkpoint-1 preimages. Raw-line digest
reuse compares actual bytes; physical/decompressed digest reuse compares actual
streams. Occurrence-ID reuse across distinct coordinates fails closed.

## SQLite schema and publication

SQLite uses a 32 MiB cache, file-backed temporary storage, foreign keys, and
incremental transactions (default: 10,000 validated records). Text/preimages and
raw target records are stored on disk, not accumulated in a corpus-sized list.
Record memory is bounded by the line limit, candidate metadata, and SQLite
buffers. Exports stream SQL cursors and contain references rather than unbounded
lists of variant IDs. Multiple representations require extra byte comparisons;
the normal one-representation pilot is a single source pass.

| Table | Contents |
| --- | --- |
| `run` | Version, profile, processing state, error |
| `candidates` | Canonical ordinal, unique QA ID, parent ID, complete candidate JSON |
| `artifacts` | Source and sidecar locations, raw sidecar/hash, staging/verified state, physical/content hashes, compression, record/line/target counts, byte size, historical verification basis, replica link |
| `aliases` | Upstream passage ID, exact parent ID, decimal passage index |
| `variants` | Checkpoint-1 variant ID, alias, exact text BLOB, timestamp string, canonical preimage BLOB |
| `occurrences` | Artifact/physical-line key, variant ID, exact raw line BLOB/hash, uncompressed offset, initially null occurrence ID |
| `observations` | Contiguous zero-based target passage runs, source line span, member count, explicit unverified original membership |

On successful validation the database run state is
`validated_manifest_required`, not a completion certificate. The final manifest
alone records `complete_verified` or `complete_provisional`, after outputs have
been written and hashed. Failed ingestion records `rejected` or `interrupted`.

The alias-to-variant relation is `variants.pid -> aliases.pid`; all alternatives
are retained. Observation membership can be queried through the same artifact
and inclusive line span. No document-variant identity is minted. A `_0` reset,
parent switch, timestamp change, gap, blank line, or EOF closes a run; a nonzero-starting sequence
does not establish a document start. Runs are observations of adjacency, not
proof of complete original articles. Alternative passages are never combined
into synthetic documents. A conflict at passage index 5 alone creates no
document observation.

Staging occurrences have null IDs. At EOF the scanner validates and finalizes
IDs incrementally; replicas are coalesced. Final checks require complete target
occurrence accounting, referenced variants, finalized IDs, and valid foreign
keys. A failed/interrupted ingestion clears finalized IDs for the run and emits
no successful index exports. Committed diagnostic staging rows may remain and
must not be used as certified evidence.

`manifest.json` is written last through an fsynced temporary file and an atomic
no-overwrite hard link. **The database alone, temporary manifest, partial exports,
or a directory without a complete manifest never certifies a run.** A hard kill
may leave staging data or temporary files; restart in a new output directory.
There is no automatic resume/overwrite. Validate published output hashes before
consuming a transferred run. The database physical checksum is an artifact
checksum, not a promise of cross-platform SQLite byte reproducibility.

## Outputs and recovery meaning

| File | Contents |
| --- | --- |
| `target_index.sqlite` | Disk-backed index and exact target bytes |
| `aliases.jsonl` | Ordered aliases, variant references/counts, physical/logical multiplicity, evidence/raw duplicate-extra counts, conflicts |
| `variants.jsonl` | Every distinct target variant and exact decoded text; ordered by variant ID |
| `occurrences.jsonl` | Finalized occurrence IDs, artifact digest, line, variant, raw hash, byte offset; ordered by digest/line |
| `document_observations.jsonl` | Source-supported contiguous runs, explicitly unverified membership |
| `recovery_ledger.jsonl` | All 400 candidates in canonical order, with separate recovery dimensions |
| `measurements.json` | Runtime, OS peak process RSS, closed database size, per-source record counts |
| `manifest.json` | Completion/provisional/rejection state, scope, profile, provenance, code/runtime/input/output hashes, measurements reference |

The five evidence/recovery JSONL exports are deterministic for fixed input
bytes. Runtime/RSS measurements and their manifest hashes naturally vary.
Peak RSS is the operating system's process-lifetime high-water mark, includes
native/SQLite memory, and is not an interval delta. Use a fresh CLI process for
the pilot. Failed-source counters may describe the last committed batch rather
than a completed source; only completed sources establish record accounting.

Duplicate-extra counts use `logical_occurrences - variant_count` for evidence
equality and `logical_occurrences - distinct_raw_line_hash_count` for raw bytes.
Both can coexist with conflicting variants. Neither indicates semantic truth.

Each ledger row separates source validation, scan completion, availability,
rendering identity, passage conflicts, annotation identity, semantic support,
canonical temporal coverage, effective pre-question coverage, and candidate
temporal issues. Effective coverage intersects the unchanged canonical window
with publication no later than question time. Archive-year, publication-day,
window inclusion, and publication-before-question checks are retained.

- Only 2008 is scanned. Other configured gold years are `not_determined` and
  `not_scanned`, never “missing gold”.
- Ten 2007-gold candidates remain `gold_outside_configured_archives`.
- Absent 2008 targets are distinguished from incomplete scans; provisional
  absence is explicitly labelled as such.
- All 40 canonical boundary windows remain reported as partially covered by
  configured archives. The 29 extending into 2021 have no effective post-2020
  portion because all question timestamps are in 2020. Other configured years
  remain unscanned even where the archive range would cover them.
- Rendering conflicts set `ambiguous=true`. Otherwise ambiguity remains null:
  absence of passage-level conflicts does not prove document membership or
  exact original annotation identity.
- Annotation identity remains `unresolved`, semantic support and final screening
  eligibility remain `not_assessed`. A certified identity scope is mechanical
  source/index validation only, never gold or benchmark certification.

## Exact Kaggle pilot command

From the repository root, with only the canonical 2008 dataset selected:

```bash
python -B -m src.eval.index_week6_target_evidence \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2008-v1 \
  --out-dir /kaggle/working/w6_r19_2008_target_pilot_2a_v1 \
  --batch-size 10000 \
  --max-line-bytes 16777216
```

The selected root must match the actual canonical mount; do not substitute a
backup automatically. Use a new output directory for a repeat. The command has
no option to process other years. Exit codes:

- `0`: complete, historically verified source/index scope.
- `3`: complete but provisional historical equivalence; not certified.
- `2`: rejected or caught interruption; discovery/ingestion failures preserve a
  400-row diagnostic ledger when canonical candidate validation succeeds.

An uncaught process termination or output-publication error may leave no final
manifest and must always be treated as incomplete.

## Pilot acceptance and next review

Inspect the manifest, measurements, source verification basis, and target ledger:

1. Exactly 400 candidate rows in canonical order, 397 distinct target parents,
   and all original metadata preserved. Only 2008 input is scanned.
2. Completed source counts match sidecars; all structural/temporal validations
   pass; hashes have correctly qualified verification states.
3. Every target occurrence is accounted for, all variants retained, aliases and
   duplicate/conflict counts consistent, and IDs independently reproducible.
4. Gzip/plain/replica multiplicity is explicit; provisional plain evidence is
   never certified. Provisional completion is reviewable, not a verified PASS.
5. No exact annotation identity or semantic support is claimed; no candidate is
   selected, silently excluded, or replaced.
6. Review the 11 candidates whose gold year is 2008, all ambiguous/absent cases,
   boundary coverage, runtime, peak RSS, database size, and persistent output
   checksums before considering remaining years.

The known 2008 conflict is covered by a targeted synthetic regression using its
transcribed real passage pair. If that parent is not among the canonical target
parents, this target-only pilot will not store or claim to inventory its variants.
Pilot acceptance must not require a particular conflict count or manufacture one.

Local tests (small synthetic shards only):

```bash
python -B -m pytest -q -p no:cacheprovider \
  tests/test_index_week6_target_evidence.py \
  tests/test_evidence_identity.py \
  tests/test_audit_week6_evidence.py
```

Remaining scientific decisions: ambiguous-annotation eligibility, sufficiency of
a unique observed rendering, admissibility of historically unverifiable sources,
document-boundary promotion, semantic/chunk review, retrieval multiplicity, and
pool temporal/coverage policy. Those decisions and the 2008 results need review
before expanding scope. The original failed audit remains failed.
