# W6-R19 Checkpoint 2B: consolidated target recovery

Checkpoint 2B imports the completed 2008 Checkpoint 2A snapshot, scans explicitly
selected canonical 2009–2020 roots, and publishes one authoritative 400-row
`recovery_ledger.jsonl`. It does not screen semantic support or select a development
set. Review the consolidated results before choosing 150 recent + 150 past.

The consolidated schema is `w6-r19-target-index/2b-v1`. The ingestion profile remains
`w6-r19-frozen-passages/v1`; the Checkpoint-1 identity contract remains
`chronoguard-evidence-identity/v1`. The original auditor, legacy pool builder,
frozen evidence, failed audit outputs, Week-4/Week-5 artifacts, and heldout protocol
are unchanged by this checkpoint.

## Architecture and schema

The existing indexer CLI delegates consolidation to
`src/eval/consolidate_week6_target_evidence.py`. The Python `run_pilot` API and
single-root, no-import 2008 CLI remain compatible. A 2B run requires
`--import-index` and repeated `--dataset-root` selections. Year identity comes
from validated sidecars, not directory names. Select exactly one root per year;
multiple representations inside a root are still validated, never silently
discarded. Roots must be distinct and non-overlapping. There is no recursive
search of unrelated `/kaggle/input` mounts.

The new database retains the seven 2A tables and adds:

- `artifacts.year`: explicit source year, with primary-representation uniqueness
  scoped to `(year, physical_sha256)`.
- `years(year, state, error, snapshot_manifest_sha256)`: independent annual
  completion/provenance state and lineage.

Artifacts retain raw sidecar BLOBs, sidecar hashes/JSON, physical and decompressed
hashes, verification basis, original source paths, all counters, and replica links.
All aliases, variant preimages/text, raw target lines, offsets, finalized occurrence
IDs, and observations are copied unchanged. Artifact IDs and referencing foreign
keys are remapped. Occurrence IDs continue to depend only on physical artifact
hash and physical line; they are never regenerated with database-local IDs.

Each new year first produces an isolated snapshot in `year_snapshots/YYYY/`, using
the existing streaming validator and 2A table layout. These are annual diagnostic
snapshots, with annual manifests and ledgers; only the ledger at the consolidated
output root is authoritative across years. Equivalence checks, replica detection,
gzip/plain byte comparisons, and historical verification promotion operate inside
one annual database. No corpus records are rescanned during import or merge.
One selected representation per year takes one payload pass; additional selected
representations require their own passes and equivalence comparisons.

A successful annual snapshot is validated and copied in a single consolidated
SQLite transaction. Rejected/interrupted snapshots never enter the consolidated
tables. Previously accepted years keep their IDs and verification states. Rejected
years allow later years to proceed; a caught interruption stops new scans and marks
the remaining requested years `not_scanned`. Failed staging databases may retain
diagnostic records and must not be consumed as completed evidence.

The consolidated manifest is written last using the existing fsync/atomic
no-overwrite publication contract. All thirteen years must complete to publish
`complete_verified` or `complete_provisional`; otherwise its state is `incomplete`.
Accepted-year exports remain available in an incomplete run, explicitly qualified
by annual states. A hard kill/export failure can leave no final manifest; database
contents alone never certify completion. There is no automatic resume or overwrite.

## Import verification

`--import-index` names the original complete 2008 output directory, including its
manifest, SQLite database, measurements, and all five JSONL exports. An imported
source mount is unnecessary. Before accepting the snapshot, 2B checks:

1. Strict manifest JSON; exact supported 2A schema, ingestion profile definition
   and hash, identity schema, year/scope, completion state, and unassessed scientific
   provenance. The pinned extraction parser hash must match local parser bytes.
2. All required published outputs and **every** manifest-listed output SHA-256.
   Hash entries must be simple filenames resolving inside the snapshot directory.
3. A closed snapshot without unhashed SQLite journal/WAL/SHM side files; exact
   SQLite table/index schema, `integrity_check`, foreign keys, and run state
   `validated_manifest_required`. That database state alone is not a certificate.
4. All four canonical candidate input hashes (including raw and LF-normalized
   windows hashes), exact candidate rows/ordinals/JSON, and manifest table counts.
5. Manifest/database source provenance agreement, strict sidecar parsing and
   validation, raw sidecar hashes, physical/content hash format, record accounting,
   replica links, and justified compression/historical-verification states.
6. Recomputed variant IDs/preimages; target alias membership; raw-line hashes and
   parsed target records; finalized occurrence IDs, physical line bounds and offsets;
   referenced variants and per-artifact target occurrence accounting.
7. Manifest stability during validation and all published output hashes again
   after copying the 2008 import. Keep inputs immutable throughout the run.

Import verifies a published snapshot's internal integrity and provenance; it does
not independently authenticate a rewritten manifest or recreate unavailable source
bytes. The 2008 `complete_provisional` result stays provisional. Exact source paths
may refer to an earlier Kaggle session and are preserved as provenance.

New years must share the imported extraction configuration declarations. Within
each year, original-output/count/representation disagreements reject that year.
Nothing upgrades historical equivalence because a different year has a verified
gzip source. The old failed auditor remains failed.

## Ledger interpretation

All 400 candidates, 397 target parents, original metadata, canonical ordering,
and all observed variants are retained. No first/last/longest/answer-based rendering
selection occurs. A completed gold year can establish presence or scoped absence
without establishing complete coverage of its cross-year evidence window.

Each row retains separate source validation, gold-year completion, availability,
rendering conflicts, annotation identity, semantic support, temporal issues, and
screening eligibility. Annual historical state determines that row's source status
and whether an absence is verified or provisional. The ten 2007 gold candidates
remain `gold_outside_configured_archives`; unscanned or failed configured gold
years remain `not_determined`.

Both canonical ±56-day and question-time-capped coverage are preserved. Coverage
includes requested/configured/outside years, structurally validated completed years,
unscanned configured years, `historically_verified_years`, and
`historical_equivalence_unverified_years`. The inherited field
`verified_scanned_years` means structurally validated completed scans, including
provisional historical equivalence; use the two new fields for historical status.
`complete_within_configured_archives` and `full_requested_coverage` distinguish
missing scans from archive boundaries. Neither boolean certifies semantic evidence.
The 40 canonical boundary windows remain visible; the 29 extending into 2021 have
no effective post-2020 component because question timestamps are in 2020.

`identity_scope_certified` qualifies mechanical gold-year source/index validation
and candidate temporal checks only. Original document membership stays unestablished,
annotation identity unresolved, and semantic support/final eligibility unassessed.
Unique observed passage variants do not prove original annotation identity.

## Exact Kaggle preflight and scan

From the repository root, attach all twelve remaining canonical datasets and make
the **whole published 2008 pilot directory** available at the import path below.
If transferred as an attached output dataset, substitute its actual mounted pilot
directory for `--import-index`; do not recreate the pilot or point to SQLite alone.

Use this Bash array once so preflight and execution receive identical paths:

```bash
args=(
  --import-index /kaggle/working/w6_r19_2008_target_pilot_2a_v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2009-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2010-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2011-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2012-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2013-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2014-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2015-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2016-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2017-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2018-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2019-v1
  --dataset-root /kaggle/input/datasets/maariyahanjum/chronoguard-week6-screening400-2020-canonical-v1
  --out-dir /kaggle/working/w6_r19_2008_2020_target_index_2b_v1
  --batch-size 10000
  --max-line-bytes 16777216
)

# Read-only: validate mounts/sidecars/payload discovery, entire import, and disk.
python -B -m src.eval.index_week6_target_evidence "${args[@]}" \
  --preflight --min-free-gib 2

# Run only after the preflight exits successfully.
python -B -m src.eval.index_week6_target_evidence "${args[@]}"
```

Preflight never scans evidence payload records and creates no output directory.
It reads the small target-only 2008 database/exports and source sidecars, checks all
twelve year mounts and payload associations, cross-year configuration declarations,
new output location, and destination filesystem free space. It prints source-declared
passage counts and a pilot-rate runtime estimate. A 2 GiB free-space floor is an
operational allowance, not a proved disk requirement; raise it when needed.

Exit codes: `0` complete verified; `3` complete provisional; `2` incomplete.
Preflight failures exit nonzero; exceptions before publication do not certify a run.
A provisional exit code is expected if 2008 remains historically unverifiable.

At the 133.8-second/2,458,630-record pilot rate, allow about 54.4 seconds per million
remaining records; twelve equally sized years would take about 26.8 minutes plus
snapshot verification/merge/export overhead. Counts, record lengths, storage, and
compression affect actual time. Memory remains streaming, with the scanner's 32 MiB
SQLite cache and 16 MiB line limit. Roughly 100–200 MB RSS is a planning estimate;
provide 512 MB–1 GiB headroom. Peak RSS includes native allocations and process
lifetime history. Disk holds annual target-only snapshots plus the consolidated
database and exports, journals/temp files, and the original imported snapshot.

## Acceptance and local validation

- All thirteen annual states complete, exact source counts matching sidecars, and
  all expected input/output hashes present. Preserve provisional qualifications.
- Exactly 400 ordered ledger rows and 397 target parents; original metadata and
  all target variants/raw occurrences retained; no ID changes to imported evidence.
- Correct physical replicas versus logical multiplicity, per-year equivalence,
  foreign keys, and failure isolation; missing years never reported as absent gold.
- Both temporal windows and outside-archive portions visible; mixed verification
  and conflicts explicitly qualified. No semantic or benchmark certification.
- Compare deterministic evidence exports across identical runs; database bytes,
  runtime/RSS, absolute paths, and manifest hashes need not be reproducible.
- Review recovery counts, ambiguity, provisional evidence admissibility, temporal
  exclusions, and semantic/chunk policy before screening or selecting any members.

```bash
python -B -m pytest -q -p no:cacheprovider \
  tests/test_consolidate_week6_target_evidence.py \
  tests/test_index_week6_target_evidence.py \
  tests/test_evidence_identity.py \
  tests/test_audit_week6_evidence.py
```

No canonical multi-year scan is part of these local tests. Coverage uses tiny
synthetic source shards. Recovery alone cannot guarantee 150 eligible examples
per stratum. There is no semantic screening, development-set selection, automatic
historical-equivalence repair, source download, or automatic failed-run resume.
