"""Deterministic development review queue from a closed Checkpoint 2B snapshot.

Reads published target records only; never opens archive/source mounts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import csv
import hashlib
import io
from pathlib import Path
import re
import sqlite3
import tempfile

from src.eval import consolidate_week6_target_evidence as checkpoint

pilot = checkpoint.pilot
VERSION = "week6-development-review/1"


def rows(path):
    return [pilot.strict_json(line) for line in Path(path).read_bytes().splitlines()]


def validate(root, windows, metadata, batch):
    root = Path(root).resolve()
    candidates, inputs = pilot.validate_inputs(windows, metadata, batch)
    manifest = pilot.strict_json((root / "manifest.json").read_bytes())
    if (manifest["schema_version"] != checkpoint.VERSION
            or manifest["state"] != "complete_provisional"
            or manifest["scan_completion"] != "complete_for_2008_2020"
            or manifest["scan_years"] != list(range(2008, 2021))
            or manifest["configured_archive_years"] != list(range(2008, 2021))
            or manifest["annotation_identity"] != "unresolved"
            or manifest["semantic_support"] != "not_assessed"
            or manifest["identity_scope_certified"] is not False
            or manifest["target_scope_only"] is not True
            or manifest["original_audit_status_changed"] is not False
            or manifest["ingestion_profile"] != pilot.PROFILE
            or manifest["identity_schema"] != pilot.identity.SCHEMA_VERSION
            or manifest["profile_definition"] != pilot.INGESTION_PROFILE
            or manifest["profile_sha256"] != hashlib.sha256(pilot.canonical(pilot.INGESTION_PROFILE).encode("ascii")).hexdigest()):
        raise ValueError("incompatible provisional Checkpoint 2B manifest")
    for key in ("windows_raw_sha256", "windows_lf_sha256", "metadata_sha256", "batch_sha256"):
        if manifest["inputs"][key] != inputs[key]:
            raise ValueError(f"candidate input checksum mismatch: {key}")
    hashes = manifest["output_sha256"]
    if not checkpoint.REQUIRED <= hashes.keys():
        raise ValueError("missing required snapshot outputs")
    for name, digest in hashes.items():
        if (Path(name).name != name or (root / name).resolve().parent != root
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or pilot.sha256(root / name) != digest):
            raise ValueError(f"snapshot output checksum mismatch: {name}")
    if any((root / ("target_index.sqlite" + s)).exists() for s in ("-wal", "-shm", "-journal")):
        raise ValueError("snapshot must be closed")
    with closing(checkpoint.readonly(root / "target_index.sqlite")) as db:
        with closing(sqlite3.connect(":memory:")) as expected:
            expected.executescript(pilot.DDL)
            expected.executescript("ALTER TABLE artifacts ADD COLUMN year INTEGER NOT NULL DEFAULT 2008; DROP INDEX unique_artifact; CREATE UNIQUE INDEX unique_year_artifact ON artifacts(year,physical_sha256) WHERE replica_of IS NULL; CREATE TABLE years(year INTEGER PRIMARY KEY,state TEXT NOT NULL,error TEXT,snapshot_manifest_sha256 TEXT)")
            query = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"
            if db.execute(query).fetchall() != expected.execute(query).fetchall():
                raise ValueError("consolidated schema mismatch")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("database integrity failure")
        if db.execute("SELECT version,profile,state,error FROM run").fetchall() != [(checkpoint.VERSION, pilot.PROFILE, "validated_manifest_required", None)]:
            raise ValueError("database run state mismatch")
        actual = db.execute("SELECT ordinal,qa_id,parent_id,record_json FROM candidates ORDER BY ordinal").fetchall()
        if actual != [(i, c["qa_id"], c["evidence_id"], pilot.canonical(c)) for i, c in enumerate(candidates)]:
            raise ValueError("canonical candidate identity/order mismatch")
        states = {y: {"state": s, "error": e, "snapshot_manifest_sha256": h}
                  for y, s, e, h in db.execute("SELECT * FROM years")}
        if ({str(y): s for y, s in states.items()} != manifest["years"]
                or set(states) != set(range(2008, 2021))
                or any(s["state"] not in {"complete_verified", "complete_provisional"} or s["error"] is not None for s in states.values())
                or not any(s["state"] == "complete_provisional" for s in states.values())):
            raise ValueError("annual completion state mismatch")
        for table in ("candidates", "aliases", "variants", "occurrences", "observations"):
            if manifest["counts"][table] != db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]:
                raise ValueError("manifest count mismatch")
        for vid, pid, text, timestamp, preimage in db.execute("SELECT * FROM variants"):
            record = pilot.identity.EvidenceRecord(pid, bytes(text), timestamp)
            if vid != pilot.identity.variant_id(record) or bytes(preimage) != pilot.identity.variant_encoding(record):
                raise ValueError("variant identity mismatch")
            if not db.execute("SELECT 1 FROM occurrences WHERE vid=?", (vid,)).fetchone():
                raise ValueError("variant missing occurrence")
        # Regenerate published records in a temporary output, never in the snapshot.
        with tempfile.TemporaryDirectory() as temp:
            pilot.export_index(db, Path(temp))
            for name in checkpoint.EXPORTS:
                if name != "recovery_ledger.jsonl" and rows(Path(temp) / name) != rows(root / name):
                    raise ValueError(f"database/export mismatch: {name}")
        ledger = rows(root / "recovery_ledger.jsonl")
        if ledger != list(checkpoint.consolidated_ledger(db, candidates, states)):
            raise ValueError("recovery ledger mismatch")
        cursor = db.execute("SELECT * FROM artifacts ORDER BY year,path")
        columns = [c[0] for c in cursor.description]
        artifacts = [{k: v for k, v in zip(columns, row) if k != "sidecar_raw"} for row in cursor]
        if artifacts != manifest["artifacts"]:
            raise ValueError("source provenance mismatch")
    return manifest, ledger


def build(ledger, variants, observations, occurrences, manifest):
    counts = Counter(r["recent_or_past"] for r in ledger if r["variant_count"])
    if len(ledger) != 400 or counts != Counter(recent=200, past=190):
        raise ValueError("expected 400 audited and 390 recovered candidates (200 recent, 190 past)")
    queue, audit = [], []
    positions = Counter()
    for row in ledger:
        recovered = row["variant_count"] > 0
        reason = None
        if not recovered:
            availability = row["evidence_availability"]
            if row["recent_or_past"] != "past" or not (availability == "gold_outside_configured_archives" or availability.startswith("absent_in_")):
                raise ValueError("unexplained missing evidence")
            reason = availability
        stratum = row["recent_or_past"]
        if recovered:
            positions[stratum] += 1
        selected = sorted((v for v in variants if v["parent_id"] == row["evidence_id"]), key=lambda v: v["variant_id"])
        if len(selected) != row["variant_count"]:
            raise ValueError("missing evidence variants")
        ids = {v["variant_id"] for v in selected}
        status = ("provisional_priority" if positions[stratum] <= 150 else "reserve") if recovered else "ineligible_configured_source_scope"
        record = {**row, "queue_status": status, "ineligibility_reason": reason,
                  "stratum_queue_position": positions[stratum] if recovered else None,
                  "semantic_support": "not_assessed", "preferred_variant_id": None,
                  "evidence_variants": selected,
                  "document_observations": [o for o in observations if o["parent_id"] == row["evidence_id"]],
                  "evidence_occurrences": [o for o in occurrences if o["variant_id"] in ids],
                  "source_provenance_reference": "summary.json#/source_provenance"}
        audit.append(record)
        if recovered:
            queue.append(record)
    return queue, audit


def run(*, manifest_path, out_dir, windows, metadata, batch):
    manifest_path, out = Path(manifest_path).resolve(), Path(out_dir).resolve()
    root = manifest_path.parent
    if manifest_path.name != "manifest.json":
        raise ValueError("expected consolidated manifest.json")
    for protected in (root, Path(windows).resolve().parent, Path(metadata).resolve().parent, Path(batch).resolve().parent):
        if out == protected or out in protected.parents or protected in out.parents:
            raise ValueError("output must not overlap input directories")
    before = pilot.sha256(manifest_path)
    manifest, ledger = validate(root, windows, metadata, batch)
    queue, audit = build(ledger, rows(root / "variants.jsonl"), rows(root / "document_observations.jsonl"), rows(root / "occurrences.jsonl"), manifest)
    # Recheck after consuming exports to reject concurrent snapshot replacement.
    if pilot.sha256(manifest_path) != before or any(pilot.sha256(root / n) != h for n, h in manifest["output_sha256"].items()):
        raise ValueError("snapshot changed during queue generation")
    out.mkdir(parents=True, exist_ok=False)
    pilot._write_rows(out / "review_queue.jsonl", queue)
    pilot._write_rows(out / "screening_audit.jsonl", audit)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(queue[0]), lineterminator="\n")
    writer.writeheader()
    for row in queue:
        writer.writerow({k: pilot.canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    (out / "review_queue.csv").write_bytes(buffer.getvalue().encode("utf-8"))
    summary = {"schema_version": VERSION, "manifest_sha256": before,
               "input_sha256": manifest["inputs"], "snapshot_output_sha256": manifest["output_sha256"],
               "counts_by_stratum_and_status": {s: dict(sorted(Counter(r["queue_status"] for r in audit if r["recent_or_past"] == s).items())) for s in ("recent", "past")},
               "source_provenance": manifest["artifacts"], "annotation_identity": "unresolved",
               "semantic_support": "not_assessed", "final_selection_frozen": False,
               "review_requirements": ["Assess semantic support against every relevant rendering; lexical answer overlap is not a support judgment.", "Resolve variant ambiguity, temporal suitability, source equivalence and annotation identity before final selection."],
               "output_sha256": {p.name: pilot.sha256(p) for p in sorted(out.iterdir())}}
    pilot._write_json(out / "summary.json", summary)
    pilot._write_json(out / "sha256.json", {p.name: pilot.sha256(p) for p in sorted(out.iterdir())})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--windows", type=Path, default=pilot.BATCH / "evidence_windows_400.jsonl")
    parser.add_argument("--metadata", type=Path, default=pilot.BATCH / "candidate_metadata_400.jsonl")
    parser.add_argument("--batch", type=Path, default=pilot.BATCH / "screening_batch_ids.jsonl")
    args = parser.parse_args()
    try:
        summary = run(manifest_path=args.manifest, out_dir=args.out_dir, windows=args.windows, metadata=args.metadata, batch=args.batch)
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"queue generation failed: {exc}\n")
    print(pilot.canonical(summary["counts_by_stratum_and_status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
