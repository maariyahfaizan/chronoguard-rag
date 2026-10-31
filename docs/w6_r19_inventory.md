# W6-R19 evidence inventory and gold recovery

## Investigation of the 13-year integrity failure

The lost Kaggle output prevents attribution to a particular record predicate.
All 13 `passage_integrity_failure` entries establish that each primary year had
at least one invalid record; they do not identify the cause. The 400
`inventory_rejected` outcomes follow from the global fail-closed policy, rather
than establishing 400 independently corrupt gold articles.

The exact record failure conditions are:

- `archive_year_mismatch`: timestamp year differs from the sidecar year OR
  parent ID's first four characters differ from that year.
- `passage_id_publication_day_mismatch`: parent ID's first eight characters
  differ from the UTC timestamp formatted as YYYYMMDD.
- `outside_retention_union`: timestamp lies outside every inclusive merged
  canonical retention interval.
- `duplicate_passage_id` / `conflicting_passage_id`: the full passage ID was
  already encountered in a primary representation. Conflict means different
  SHA-256 hashes of canonical JSON records (including all fields).

Malformed records, bad counts, bad available checksums, incompatible sidecars,
or unequal replica content reject the audit separately. The checked-in
DeepMind parser derives both the sorting-key date and publication timestamp
from the same publication-date field. The extractor writes that timestamp and
appends a passage index to the sorting key. Those date comparisons are therefore
compatible; no predicate relaxation is supported by the available evidence.

Gzip detection uses magic bytes, including for temporary names in Kaggle's
`.jsonl` directories. `output_sha256` hashes the original gzip bytes and is
checked only against gzip bytes. Plain mounts lacking a previously recorded
content hash produce `original_hash_unverifiable_after_decompression`, not
`passage_integrity_failure`. Recompressing a mount or recording its current
hash cannot retrospectively verify the original artifact.

Duplicate IDs require a separate investigation: the upstream
`get_deduplicated_wmt_docs` uses set membership in the sorting-key allowlist,
without a seen-record set. Repeated eligible archive rows can therefore yield
repeated passage IDs. This is a possible mechanism, not a diagnosis of the lost
run. Distinct passage suffixes remain distinct IDs; equivalent mounted replicas
are compared by content and only the primary enters the global duplicate index.
No duplicates are silently removed or accepted.

The smallest supported correction is diagnostic: year inventory entries now
include `integrity_diagnostics` with failed-predicate counts and one exact
expected/observed example per predicate, plus count and hash comparisons.
`integrity_events.jsonl` includes the predicate evidence for every invalid
record. Duplicate examples preserve first/current source locations and record
hashes. Summary year failures include predicate counts. All existing rejection,
provenance, and incomplete-hash-verification behavior is retained. Use these
diagnostics to establish the actual data defect before choosing a data or
extraction correction; a PASS is not justified by the missing historical output.

`src/eval/audit_week6_evidence.py` audits existing mounted evidence. It never
downloads, extracts, samples, selects final benchmark members, or runs models.
The existing extraction scripts and frozen Week-4/Week-6 inputs remain unchanged.

## Kaggle invocation

From the repository root in `/kaggle/working`, with all 13 evidence datasets
attached:

```bash
python -m src.eval.audit_week6_evidence \
  --evidence-root /kaggle/input \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2008-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2009-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2010-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2011-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2012-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2013-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2014-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2015-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2016-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2017-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2018-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2019-v1 \
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2020-canonical-v1 \
  --out-dir /kaggle/working/w6_r19_inventory_canonical_v1 \
  --scratch-dir /kaggle/working
```

`--dataset-root` explicitly selects the exact canonical dataset roots. Only those
roots are recursively searched and their evidence bytes read. Roots must exist,
be distinct and non-overlapping, and lie under an `--evidence-root`. Excluded
directory subtrees are enumerated without descending into them. The inventory
manifest `integrity_provenance.json` records `dataset_selection`, including the
resolved selected roots and ignored external mounts with reasons. Selection is
by exact path, never by size, slug heuristics, or apparent validity. A zero-byte
selected payload fails the audit; an excluded backup is never a fallback.

Without `--dataset-root`, the existing recursive `--evidence-root` discovery
remains available and rejects invalid duplicate mounts. No particular dataset
slug is assumed by the code. Defaults for `--windows`, `--metadata`,
and `--batch` point to `results/week6_sampling_draft/screening_batch_v1/`.
Outputs default to `results/week6_sampling_draft/w6_r19_inventory/`.
The output directory must not already exist and must not overlap evidence roots.
Use a new `--out-dir` for a subsequent audit; never overwrite a previous report.

This is a full sequential read of the mounted retained-passage shards, not of
the original WMT archives. It uses no GPU or network. Gold recovery uses a set
of parent IDs. Retention checks use binary search over merged UTC intervals,
rather than comparing each passage with 400 windows. An on-disk SQLite index
checks every passage ID, including non-gold passages and cross-shard duplicates.
RAM is bounded by the SQLite cache, discovery metadata, and recovered gold
documents; temporary disk use grows with the number and length of passage IDs.
Provide sufficient scratch space. The index is closed and removed on exit.
Each mounted representation is streamed once, with physical and decompressed
hashing performed in the same pass. Equivalent replicas are verified but do not
duplicate recovered gold records.

## Discovery and trust rules

The auditor recognizes `YEAR.jsonl.gz`, `YEAR.jsonl`, and nested extracted
members such as `2020.jsonl/.2020.attempt1.jsonl.gz.tmp`. Gzip magic bytes, not
the filename extension, determine decompression. A payload must have a complete
`YEAR.audit.json` (or `.YEAR.audit.json.tmp`) in its nearest applicable ancestor
directory. A temporary-looking payload is never trusted without that sidecar.
With explicit dataset roots, a payload lacking an ancestor sidecar may use the
unique same-year sidecar anywhere within its selected dataset root. This covers
the 2015 `week6_2015_backup/2015.audit.json` layout. Multiple possible sidecars
are rejected; sidecars never cross selected dataset boundaries. Unused sidecars
remain errors, and all existing metadata, count and hash checks still apply.
Sidecars must use the existing `fetch_week6_wmt_evidence.run_year` schema.

All years 2008–2020 are required. Audit status, canonical windows hash, official
sorting-key checksum, parser, parser-code hash, date-prepending setting, archive
URL, and passage counts are checked. Parser hashes and optional extraction
configuration fields must agree across years. Duplicate datasets must declare
the same original output hash and passage count, and their actual decompressed
bytes must agree. Different gzip encodings with different declared compressed
hashes are conservatively rejected as conflicting versions.

`physical_sha256` hashes the mounted file's exact bytes.
`decompressed_content_sha256` hashes the exact uncompressed JSONL bytes, with
no newline normalization. `original_compressed_sha256` is the extraction
sidecar's `output_sha256`; it is directly verified only when original gzip
bytes are mounted. Optional `content_sha256` or `decompressed_sha256` fields
allow comparison with a previously recorded uncompressed checksum.

An automatically decompressed mount with only a compressed-byte sidecar hash
cannot prove equality to those unavailable original compressed bytes. The run
records `original_hash_unverifiable_after_decompression` and sets
`original_hash_verification_complete=false` unless a verifiable equivalent
representation or recorded content hash is available. A new content hash is
an inventory observation, not retrospective proof of the backup verification.
`status=complete` means scanning completed; inspect warnings and recovery
outcomes before using the result. No semantic support is certified.

## Canonical validation and boundaries

The CLI requires the canonical LF windows SHA-256
`99da0f327616a1725ddf3a323d459868ebac9d498aa94cd2acf332c5638f8cab`.
Only CRLF-to-LF normalization is allowed, in memory, for that comparison.
Raw and LF hashes are both reported. Candidate ID sets, batch ordering, strata,
reserve ranks, evidence IDs/timestamps, metadata agreement, question timestamps,
and exact evidence-centered ±56-day UTC windows are validated.

The ledger preserves the canonical order and contains exactly one outcome per
validated candidate, including all ten 2007-gold candidates. It records all
requested/configured/out-of-archive window years. A 2019 gold document is
recovered from 2019 even when its window includes 2020. Partial 2007/2021 window
coverage is reported separately from missing in-archive gold. No boundary case
is silently excluded, and no eligibility policy is applied.

Original publication timestamps are preserved. Publication-day agreement is
checked against `evidence_ts`, because canonical question metadata may have an
hour offset from WMT's midnight publication date. Exact timestamp equality is
not claimed. Passage timestamp UTC, archive year, ID date, retention union,
candidate window, and publication-before-question checks are also recorded.

## Outputs and failure behavior

| File | Contents |
|---|---|
| `evidence_inventory.jsonl` | One entry per scanned year; all mount representations, hashes, counts, sidecars, duplicate/conflict totals |
| `recovery_ledger.jsonl` | One row per validated candidate; original metadata, boundaries, outcome, passage IDs and source references |
| `recovered_gold_passages.jsonl` | Gold descendant passage occurrences, question/evidence IDs and original timestamps; mount/audit paths and line numbers |
| `integrity_events.jsonl` | Streaming duplicate, conflict, and passage-integrity diagnostics |
| `integrity_provenance.json` | Input and output hashes, code hashes/revision/dirty state, runtime, parameters, summary, hash-verification limits |
| `summary.json` | Inventory failures, hash warnings, recovery failures, counts, boundary IDs, unresolved cases |

Exit code 0 means the inventory scan completed without corpus integrity failures;
missing gold, boundaries, content-hash warnings, and semantic review still require
attention. Exit code 2 means rejected inputs/inventory or passage-integrity
failure. On inventory rejection, all validated candidates get an explicit
`inventory_rejected` outcome; already recovered text is diagnostic only. A
rejected scan may have a partial inventory, clearly identified by the report.
If canonical input validation fails, no candidate ledger can be certified; the
report records that failure and the ledger is empty. Interrupted processes
without a final provenance report must not be treated as completed runs.

Recovered evidence is always marked `semantic_support=not_assessed`. Identical
and conflicting duplicate passage IDs both fail corpus integrity; occurrences
and their source references remain available for investigation. Successful
recovery means only that evidence was recovered and passed these mechanical
checks. Semantic review and final 150/150 selection remain later milestones.

## Offline validation

```bash
python -B -m pytest -q tests/test_audit_week6_evidence.py
```

Tests use tiny synthetic passage shards. One integration fixture uses the real
400 canonical metadata records with synthetic evidence across all 13 years; it
checks all 400 outcomes, ten 2007-gold cases, 11 windows touching 2007, and 29
touching 2021. It is not a verification of the private Kaggle datasets.
