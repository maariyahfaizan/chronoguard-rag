# Week-6 development screening queue

From the repository root, supply the completed provisional Checkpoint 2B
snapshot's manifest and a new, non-overlapping output directory:

```powershell
python -m src.eval.prepare_week6_review_queue --manifest "D:/checkpoint2b/manifest.json" --out-dir "results/week6_sampling_draft/development_review_v1"
```

The canonical inputs default to `results/week6_sampling_draft/screening_batch_v1/`.
To locate copies explicitly, append:

```powershell
--windows "PATH/evidence_windows_400.jsonl" --metadata "PATH/candidate_metadata_400.jsonl" --batch "PATH/screening_batch_ids.jsonl"
```

This reads the closed consolidated database and its published exports, verifies
input/output checksums, schema, completion, candidate identity, reserve ranks,
variant identities and database/export agreement. It never opens archive mounts.
An incompatible snapshot or counts other than 200 recovered recent and 190
recovered past fail before output creation. Existing output directories are refused.

Outputs are UTF-8 with LF endings:

- `review_queue.jsonl` and `review_queue.csv`: all 390 recovered candidates,
  preserving canonical order within each stratum. The first 150 recovered in
  each stratum are provisional priorities; 50 recent and 40 past are reserves.
  Nested CSV fields contain canonical JSON.
- `screening_audit.jsonl`: all 400 original candidate records with derived
  queue status. The ten unrecovered past candidates retain explicit source-scope
  exclusion reasons. The input ledger is unchanged.
- `summary.json`: counts by stratum/status, source provenance, input hashes,
  snapshot hashes and review artifact hashes.
- `sha256.json`: hashes of every other generated artifact, including summary.
  A checksum file does not contain its own hash.

Every rendering and observation remains visible. Variant ID sorting only orders
the displayed evidence list; it neither changes candidate priority nor chooses
a preferred rendering. No lexical answer matching or semantic judgment is run.

Humans must review semantic support, variant ambiguity and document membership,
temporal suitability and coverage, historical source equivalence, and original
annotation identity. Priority status is a review scheduling label, not semantic
acceptance. This checkpoint does not select or freeze the final 300 examples.

Focused validation:

```powershell
python -B -m pytest tests/test_prepare_week6_review_queue.py -q
```
