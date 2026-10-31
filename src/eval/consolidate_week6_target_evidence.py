"""Checkpoint 2B: validated year snapshots and one authoritative target ledger."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import time

from src.eval import index_week6_target_evidence as pilot

VERSION = "w6-r19-target-index/2b-v1"
EXPORTS = ("aliases.jsonl", "variants.jsonl", "occurrences.jsonl",
           "document_observations.jsonl", "recovery_ledger.jsonl")
REQUIRED = {*EXPORTS, "target_index.sqlite", "measurements.json"}


def configuration(audit):
    return {k: audit.get(k) for k in ("windows_sha256", "sorting_keys_md5", "deepmind_extraction_sha256",
                                    "prepend_date", "parser", "extraction_config", "config_sha256")}


def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def verify_snapshot(root, candidates, inputs, *, year=2008):
    """Verify published snapshot without reading historical source mounts."""
    root = Path(root).resolve()
    if any((root / ("target_index.sqlite" + suffix)).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("import must be a closed snapshot without SQLite side files")
    raw_manifest = (root / "manifest.json").read_bytes()
    report = pilot.strict_json(raw_manifest)
    parser_path = Path(pilot.__file__).resolve().parents[2] / "third_party/streamingqa/extraction.py"
    if (report["schema_version"] != pilot.VERSION or report["ingestion_profile"] != pilot.PROFILE
            or report["identity_schema"] != pilot.identity.SCHEMA_VERSION
            or report["state"] not in {"complete_verified", "complete_provisional"}
            or report["scan_years"] != [year]
            or report["scan_completion"] != f"complete_for_{year}_only"
            or report["profile_definition"] != pilot.INGESTION_PROFILE
            or report["profile_sha256"] != hashlib.sha256(pilot.canonical(pilot.INGESTION_PROFILE).encode("ascii")).hexdigest()
            or report["target_scope_only"] is not True or report["error"] is not None
            or report["configured_archive_years"] != list(range(2008,2021))
            or report["target_parent_count"] != len({c["evidence_id"] for c in candidates})):
        raise ValueError("incompatible or incomplete import manifest")
    if (report["code_sha256"]["extraction.py"] != pilot.sha256(parser_path)
            or report["annotation_identity"] != "unresolved" or report["semantic_support"] != "not_assessed"
            or report["original_audit_status_changed"] is not False):
        raise ValueError("import parser or scientific provenance state mismatch")
    for key in ("windows_raw_sha256", "windows_lf_sha256", "metadata_sha256", "batch_sha256"):
        if report["inputs"][key] != inputs[key]:
            raise ValueError(f"import candidate input mismatch: {key}")
    hashes = report["output_sha256"]
    if not REQUIRED <= hashes.keys():
        raise ValueError("import missing required published outputs")
    for name, digest in hashes.items():
        if (Path(name).name != name or (root / name).resolve().parent != root
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("unsafe import output hash entry")
        if pilot.sha256(root / name) != digest:
            raise ValueError(f"import output checksum mismatch: {name}")
    with closing(readonly(root / "target_index.sqlite")) as db:
        with closing(sqlite3.connect(":memory:")) as schema:
            schema.executescript(pilot.DDL)
            query = "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"
            if db.execute(query).fetchall() != schema.execute(query).fetchall():
                raise ValueError("import SQLite schema mismatch")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("import SQLite integrity/foreign key failure")
        if db.execute("SELECT version,profile,state,error FROM run").fetchall() != [(pilot.VERSION, pilot.PROFILE, "validated_manifest_required", None)]:
            raise ValueError("import database provenance state mismatch")
        actual = db.execute("SELECT ordinal,qa_id,parent_id,record_json FROM candidates ORDER BY ordinal").fetchall()
        expected = [(i, c["qa_id"], c["evidence_id"], pilot.canonical(c)) for i, c in enumerate(candidates)]
        if actual != expected:
            raise ValueError("import candidate rows mismatch")
        if set(report["counts"]) != {"candidates", "aliases", "variants", "occurrences", "observations"}:
            raise ValueError("import incomplete table counts")
        for table, count in report["counts"].items():
            if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] != count:
                raise ValueError("import count mismatch")
        artifacts = db.execute("SELECT * FROM artifacts").fetchall()
        if not artifacts:
            raise ValueError("import has no sources")
        columns = [c[1] for c in db.execute("PRAGMA table_info(artifacts)")]
        published_columns = ("path", "sidecar_path", "sidecar_sha256", "state", "physical_sha256", "content_sha256", "compression", "records", "target_records", "physical_lines", "bytes", "original_compressed_verified", "historical_verified", "verification_basis", "replica_of")
        published = [dict(zip(published_columns, row)) for row in db.execute(f"SELECT {','.join(published_columns)} FROM artifacts ORDER BY path")]
        if published != report["artifacts"]:
            raise ValueError("import manifest/database source provenance mismatch")
        historical = True
        signature = None
        content_hashes = set()
        targets = {c["evidence_id"] for c in candidates}
        intervals = pilot.retention_intervals(candidates)
        for values in artifacts:
            a = dict(zip(columns, values))
            audit = pilot.strict_json(a["sidecar_raw"])
            pilot.validate_audit(audit, year, inputs["windows_lf_sha256"])
            current = {**configuration(audit), "output_sha256": audit["output_sha256"], "passages": audit["passages"], "archive_url": audit["archive_url"]}
            if signature is not None and current != signature:
                raise ValueError("import incompatible representation sidecars")
            signature = current
            content_hashes.add(a["content_sha256"])
            if (a["state"] != "verified" or a["records"] != audit["passages"]
                    or not 0 <= a["target_records"] <= a["records"] <= a["physical_lines"] or a["bytes"] <= 0
                    or a["sidecar_sha256"] != hashlib.sha256(a["sidecar_raw"]).hexdigest()
                    or a["sidecar_json"] != pilot.canonical(audit)
                    or audit["deepmind_extraction_sha256"] != report["code_sha256"]["extraction.py"]):
                raise ValueError("import source provenance mismatch")
            for key in ("physical_sha256", "content_sha256"):
                if not isinstance(a[key], str) or not re.fullmatch(r"[0-9a-f]{64}", a[key]):
                    raise ValueError("import invalid source hash")
            expected_hash = audit.get("content_sha256", audit.get("decompressed_sha256"))
            if expected_hash is not None and expected_hash != a["content_sha256"]:
                raise ValueError("import recorded content hash mismatch")
            basis = a["verification_basis"]
            if a["compression"] == "gzip":
                valid = (a["original_compressed_verified"] == 1 and a["historical_verified"] == 1
                         and basis == "original_gzip" and a["physical_sha256"] == audit["output_sha256"])
            else:
                expected_hash = audit.get("content_sha256", audit.get("decompressed_sha256"))
                counterpart = any(dict(zip(columns, x))["original_compressed_verified"] == 1
                                  and dict(zip(columns, x))["content_sha256"] == a["content_sha256"] for x in artifacts)
                valid = (a["compression"] == "plain" and a["original_compressed_verified"] == 0
                         and a["physical_sha256"] == a["content_sha256"] and (
                             (basis == "observed_plain_only" and a["historical_verified"] == 0 and expected_hash is None)
                             or (basis == "recorded_content_hash" and a["historical_verified"] == 1 and expected_hash == a["content_sha256"])
                             or (basis == "verified_gzip_counterpart" and a["historical_verified"] == 1 and counterpart)))
            if not valid:
                raise ValueError("import historical verification mismatch")
            historical &= bool(a["historical_verified"])
            count = db.execute("SELECT count(*) FROM occurrences WHERE artifact=?", (a["id"],)).fetchone()[0]
            if a["replica_of"] is None:
                if count != a["target_records"]:
                    raise ValueError("import target occurrence accounting mismatch")
            else:
                original = db.execute("SELECT physical_sha256,replica_of FROM artifacts WHERE id=?", (a["replica_of"],)).fetchone()
                if count or original != (a["physical_sha256"], None):
                    raise ValueError("import replica accounting mismatch")
        if len(content_hashes) != 1:
            raise ValueError("import conflicting representation content hashes")
        if (report["state"] == "complete_verified") != historical or report["identity_scope_certified"] != historical:
            raise ValueError("import manifest verification state mismatch")
        for vid, pid, text, timestamp, preimage in db.execute("SELECT * FROM variants"):
            record = pilot.identity.EvidenceRecord(pid, bytes(text), timestamp)
            if vid != pilot.identity.variant_id(record) or bytes(preimage) != pilot.identity.variant_encoding(record):
                raise ValueError("import variant identity mismatch")
            if not db.execute("SELECT 1 FROM occurrences WHERE vid=?", (vid,)).fetchone():
                raise ValueError("import unreferenced variant")
        for pid, parent, suffix in db.execute("SELECT * FROM aliases"):
            if pid != parent + "_" + suffix or parent not in targets or not pilot.PID.fullmatch(pid):
                raise ValueError("import alias mismatch")
        for digest, line, vid, raw_hash, raw, offset, oid, physical_lines in db.execute(
                "SELECT a.physical_sha256,o.line,o.vid,o.raw_sha256,o.raw_line,o.uncompressed_offset,o.occurrence_id,a.physical_lines "
                "FROM occurrences o JOIN artifacts a ON a.id=o.artifact"):
            record, _, _ = pilot.parse_passage(bytes(raw), year, intervals)
            if (oid != pilot.identity.occurrence_id(pilot.identity.SourceOccurrence(digest, line))
                    or hashlib.sha256(raw).hexdigest() != raw_hash or pilot.identity.variant_id(record) != vid
                    or not 1 <= line <= physical_lines or offset < 0):
                raise ValueError("import occurrence identity/accounting mismatch")
    # Detect concurrent replacement during validation; input snapshots must remain immutable.
    if (root / "manifest.json").read_bytes() != raw_manifest:
        raise ValueError("import changed during verification")
    report["_verified_manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()
    return report


def merge_snapshot(db, root, year):
    """Copy all source rows; remap only database-local artifact coordinates."""
    with closing(readonly(Path(root) / "target_index.sqlite")) as source:
        mapping = {}
        columns = [c[1] for c in source.execute("PRAGMA table_info(artifacts)")]
        for row in source.execute("SELECT * FROM artifacts ORDER BY replica_of IS NOT NULL,id"):
            a = dict(zip(columns, row))
            values = [a[c] for c in columns if c not in {"id", "replica_of"}]
            names = [c for c in columns if c not in {"id", "replica_of"}]
            replica = mapping[a["replica_of"]] if a["replica_of"] is not None else None
            cursor = db.execute(f"INSERT INTO artifacts({','.join(names)},year,replica_of) VALUES({','.join('?' for _ in values)},?,?)", (*values, year, replica))
            mapping[a["id"]] = cursor.lastrowid
        for table in ("aliases", "variants"):
            for row in source.execute(f"SELECT * FROM {table}"):
                db.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", row)
        for table in ("occurrences", "observations"):
            for row in source.execute(f"SELECT * FROM {table}"):
                db.execute(f"INSERT INTO {table} VALUES({','.join('?' for _ in row)})", (mapping[row[0]], *row[1:]))


def consolidated_ledger(db, candidates, states):
    completed = {y for y, s in states.items() if s["state"].startswith("complete_")}
    for candidate in candidates:
        year = int(candidate["evidence_id"][:4])
        state = states.get(year, {})
        success = year in completed
        # Override the pilot's database-wide historical qualifier with annual state.
        historical = state.get("state") == "complete_verified"
        row = next(pilot.ledger(db, [candidate], successful=success, year=year))
        failed = state.get("state") in {"rejected", "interrupted"}
        row["scan_completion"] = "complete_for_gold_year" if success else ("failed_or_interrupted" if failed else "not_scanned")
        row["source_validation"] = ("verified" if historical else "provisional_historical_equivalence_unverified") if success else ("rejected_or_incomplete" if failed else "not_scanned")
        if success and not row["variant_count"]:
            row["evidence_availability"] = f"absent_in_{'verified' if historical else 'provisional'}_{year}_scope"
        row["identity_scope_certified"] = bool(success and historical and not row["temporal_issues"])
        row["canonical_temporal_coverage"] = pilot._coverage(candidate, completed)
        row["effective_prequestion_temporal_coverage"] = pilot._coverage(candidate, completed, effective=True)
        for key in ("canonical_temporal_coverage", "effective_prequestion_temporal_coverage"):
            coverage = row[key]
            coverage["historically_verified_years"] = [y for y in coverage["verified_scanned_years"] if states[y]["state"] == "complete_verified"]
            coverage["historical_equivalence_unverified_years"] = [y for y in coverage["verified_scanned_years"] if states[y]["state"] == "complete_provisional"]
            coverage["complete_within_configured_archives"] = not coverage["unscanned_configured_years"]
            coverage["full_requested_coverage"] = not coverage["unscanned_configured_years"] and not coverage["outside_archive_years"]
        yield row


def selected_years(roots, *, validate=True):
    resolved = [Path(r).resolve() for r in roots]
    if len(set(resolved)) != len(resolved) or any(a in b.parents for a in resolved for b in resolved if a != b):
        raise ValueError("selected roots must be distinct and non-overlapping")
    result = {}
    for root in sorted(resolved):
        if not root.is_dir():
            raise ValueError(f"missing dataset mount: {root}")
        years = set()
        for path in root.rglob("*"):
            match = re.fullmatch(r"\.?(\d{4})\.audit\.json(?:\.tmp)?", path.name)
            if path.is_file() and match:
                year = int(match[1])
                if validate:
                    audit = pilot.strict_json(path.read_bytes())
                    pilot.validate_audit(audit, year, pilot.WINDOWS_SHA256)
                years.add(year)
        if len(years) != 1 or not years <= set(range(2008, 2021)):
            raise ValueError(f"root must identify exactly one configured year: {root}")
        year = years.pop()
        if year in result:
            raise ValueError(f"select one canonical root for year {year}")
        result[year] = root
    return result


def run(*, dataset_roots, import_index, out_dir, batch_size=10000, max_line_bytes=pilot.DEFAULT_MAX_LINE):
    started = time.perf_counter()
    roots = [Path(r).resolve() for r in dataset_roots]
    if type(batch_size) is not int or batch_size < 1 or type(max_line_bytes) is not int or max_line_bytes < 1:
        raise ValueError("batch_size and max_line_bytes must be positive integers")
    imported = Path(import_index).resolve() if import_index else None
    out = Path(out_dir).resolve()
    for protected in roots + ([imported] if imported else []) + [pilot.BATCH.resolve()]:
        if out == protected or out in protected.parents or protected in out.parents:
            raise ValueError("output and inputs must not overlap")
    candidates, inputs = pilot.validate_inputs(pilot.BATCH / "evidence_windows_400.jsonl", pilot.BATCH / "candidate_metadata_400.jsonl", pilot.BATCH / "screening_batch_ids.jsonl")
    imported_report = verify_snapshot(imported, candidates, inputs) if imported else None
    selection = selected_years(roots, validate=False)
    if imported and 2008 in selection:
        raise ValueError("2008 already imported; do not select a 2008 source root")
    if not imported and set(selection) == {2008}:
        # Preserve Checkpoint 2A CLI compatibility.
        return pilot.run_pilot(dataset_root=selection[2008], out_dir=out, batch_size=batch_size, max_line_bytes=max_line_bytes)
    if not imported or not selection:
        raise ValueError("2B requires the completed 2008 import and selected remaining years")
    out.mkdir(parents=True, exist_ok=False)
    states = {}
    with closing(sqlite3.connect(out / "target_index.sqlite")) as db:
        db.executescript(pilot.DDL)
        db.execute("ALTER TABLE artifacts ADD COLUMN year INTEGER NOT NULL DEFAULT 2008")
        db.execute("DROP INDEX unique_artifact")
        db.execute("CREATE UNIQUE INDEX unique_year_artifact ON artifacts(year,physical_sha256) WHERE replica_of IS NULL")
        db.execute("CREATE TABLE years(year INTEGER PRIMARY KEY,state TEXT NOT NULL,error TEXT,snapshot_manifest_sha256 TEXT)")
        db.execute("INSERT INTO run VALUES(1,?,?,'scanning',NULL)", (VERSION, pilot.PROFILE))
        db.executemany("INSERT INTO candidates VALUES(?,?,?,?)", [(i,c["qa_id"],c["evidence_id"],pilot.canonical(c)) for i,c in enumerate(candidates)])
        merge_snapshot(db, imported, 2008)
        # Recheck transferred snapshot hashes after copying, before accepting the import.
        for name, digest in imported_report["output_sha256"].items():
            if pilot.sha256(imported / name) != digest:
                raise ValueError("import changed while copying")
        if pilot.sha256(imported / "manifest.json") != imported_report["_verified_manifest_sha256"]:
            raise ValueError("import manifest changed while copying")
        states[2008] = {"state": imported_report["state"], "error": None, "snapshot_manifest_sha256": imported_report["_verified_manifest_sha256"]}
        baseline = configuration(pilot.strict_json(db.execute("SELECT sidecar_raw FROM artifacts LIMIT 1").fetchone()[0]))
        db.commit()
        snapshots = out / "year_snapshots"
        snapshots.mkdir()
        for year, root in sorted(selection.items()):
            snapshot = snapshots / str(year)
            try:
                report = pilot.run_pilot(dataset_root=root, out_dir=snapshot, year=year, batch_size=batch_size, max_line_bytes=max_line_bytes)
                info = {"state": report["state"], "error": report["error"], "snapshot_manifest_sha256": pilot.sha256(snapshot / "manifest.json")}
                if report["state"].startswith("complete_"):
                    verify_snapshot(snapshot, candidates, inputs, year=year)
                    with closing(readonly(snapshot / "target_index.sqlite")) as staged_db:
                        if any(configuration(pilot.strict_json(raw)) != baseline for (raw,) in staged_db.execute("SELECT sidecar_raw FROM artifacts")):
                            raise ValueError("cross-year extraction configuration mismatch")
                    with db:
                        merge_snapshot(db, snapshot, year)
                states[year] = info
            except (ValueError, OSError, KeyError, TypeError, sqlite3.Error, KeyboardInterrupt) as exc:
                db.rollback()
                states[year] = {"state": "interrupted" if isinstance(exc, KeyboardInterrupt) else "rejected", "error": f"{type(exc).__name__}: {exc}", "snapshot_manifest_sha256": None}
            if states[year]["state"] == "interrupted":
                break
        for year in selection:
            states.setdefault(year, {"state": "not_scanned", "error": "not attempted after interruption", "snapshot_manifest_sha256": None})
        for year in range(2008, 2021):
            states.setdefault(year, {"state": "not_scanned", "error": "dataset root not selected", "snapshot_manifest_sha256": None})
        complete = all(s["state"].startswith("complete_") for s in states.values()) and set(states) == set(range(2008, 2021))
        historical = complete and all(s["state"] == "complete_verified" for s in states.values())
        state = ("complete_verified" if historical else "complete_provisional") if complete else "incomplete"
        for year, info in sorted(states.items()):
            db.execute("INSERT INTO years VALUES(?,?,?,?)", (year, info["state"], info["error"], info["snapshot_manifest_sha256"]))
        db.execute("UPDATE run SET state=?", ("validated_manifest_required" if complete else "incomplete",))
        db.commit()
        if db.execute("PRAGMA foreign_key_check").fetchall() or db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("consolidated SQLite integrity/foreign key failure")
        if (db.execute("SELECT 1 FROM occurrences WHERE occurrence_id IS NULL").fetchone()
                or db.execute("SELECT 1 FROM artifacts a WHERE replica_of IS NULL AND target_records != (SELECT count(*) FROM occurrences o WHERE o.artifact=a.id)").fetchone()
                or db.execute("SELECT 1 FROM variants v WHERE NOT EXISTS (SELECT 1 FROM occurrences o WHERE o.vid=v.vid)").fetchone()
                or db.execute("SELECT count(*) FROM candidates").fetchone()[0] != 400):
            raise ValueError("consolidated occurrence/candidate accounting failure")
        pilot.export_index(db, out)
        pilot._write_rows(out / "recovery_ledger.jsonl", consolidated_ledger(db, candidates, states))
        counts = {t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("candidates", "aliases", "variants", "occurrences", "observations")}
        cursor = db.execute("SELECT * FROM artifacts ORDER BY year,path")
        artifact_columns = [c[0] for c in cursor.description]
        # Raw sidecar bytes are retained in SQLite, not duplicated as JSON blobs.
        artifacts = [{k:v for k,v in zip(artifact_columns,row) if k != "sidecar_raw"} for row in cursor]
    pilot._write_json(out / "measurements.json", {"runtime_seconds": time.perf_counter()-started, "peak_process_rss_bytes": pilot.peak_memory(), "database_bytes": (out / "target_index.sqlite").stat().st_size})
    report = {"schema_version": VERSION, "ingestion_profile": pilot.PROFILE, "identity_schema": pilot.identity.SCHEMA_VERSION,
              "profile_definition": pilot.INGESTION_PROFILE,
              "profile_sha256": hashlib.sha256(pilot.canonical(pilot.INGESTION_PROFILE).encode("ascii")).hexdigest(),
              "state": state, "scan_completion": "complete_for_2008_2020" if complete else "incomplete",
              "identity_scope_certified": historical, "target_scope_only": True, "inputs": inputs,
              "scan_years": sorted(y for y,s in states.items() if s["state"].startswith("complete_")),
              "configured_archive_years": list(range(2008,2021)), "years": {str(y):s for y,s in sorted(states.items())},
              "selected_dataset_roots": [str(r) for r in roots], "import_index": str(imported),
              "import_manifest_sha256": imported_report["_verified_manifest_sha256"], "counts": counts, "artifacts": artifacts,
              "target_parent_count": len({c["evidence_id"] for c in candidates}),
              "annotation_identity": "unresolved", "semantic_support": "not_assessed", "original_audit_status_changed": False,
              "code_sha256": {p.name: pilot.sha256(p) for p in (
                  Path(__file__), Path(pilot.__file__), Path(pilot.identity.__file__),
                  Path(pilot.__file__).with_name("audit_week6_evidence.py"),
                  Path(pilot.__file__).resolve().parents[2] / "third_party/streamingqa/extraction.py")},
              "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "parameters": {"batch_size": batch_size, "max_line_bytes": max_line_bytes},
              "output_sha256": {p.name:pilot.sha256(p) for p in sorted(out.iterdir()) if p.is_file()}}
    # Same atomic, no-overwrite publication contract as 2A.
    staged = out / "manifest.json.tmp"
    with staged.open("xb") as stream:
        stream.write((pilot.canonical(report)+"\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    os.link(staged, out / "manifest.json")
    staged.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, action="append", required=True)
    parser.add_argument("--import-index", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--max-line-bytes", type=int, default=pilot.DEFAULT_MAX_LINE)
    parser.add_argument("--preflight", action="store_true", help="Read-only mount/import/disk validation; never scan payloads")
    parser.add_argument("--min-free-gib", type=float, default=2)
    args = parser.parse_args()
    if not args.preflight and args.import_index is None and len(args.dataset_root) == 1:
        report = pilot.run_pilot(dataset_root=args.dataset_root[0], out_dir=args.out_dir,
                                 batch_size=args.batch_size, max_line_bytes=args.max_line_bytes)
        print(pilot.canonical({"state": report["state"], "counts": report["counts"], "out_dir": str(args.out_dir)}))
        return 0 if report["state"] == "complete_verified" else 3 if report["state"] == "complete_provisional" else 2
    if args.preflight:
        selection = selected_years(args.dataset_root)
        candidates, inputs = pilot.validate_inputs(pilot.BATCH / "evidence_windows_400.jsonl", pilot.BATCH / "candidate_metadata_400.jsonl", pilot.BATCH / "screening_batch_ids.jsonl")
        if args.import_index is None or set(selection) != set(range(2009,2021)):
            parser.error("preflight requires 2008 import and exactly years 2009–2020")
        verify_snapshot(args.import_index, candidates, inputs)
        with closing(readonly(args.import_index / "target_index.sqlite")) as imported_db:
            baseline = configuration(pilot.strict_json(imported_db.execute("SELECT sidecar_raw FROM artifacts LIMIT 1").fetchone()[0]))
        sources = pilot.discover(list(selection.values()), years=tuple(sorted(selection)), root_scoped=True)
        if any(configuration(item["audit"]) != baseline for items in sources.values() for item in items):
            parser.error("cross-year extraction configuration mismatch")
        ancestor = args.out_dir.resolve()
        for protected in list(selection.values()) + [args.import_index.resolve(), pilot.BATCH.resolve()]:
            if ancestor == protected or ancestor in protected.parents or protected in ancestor.parents:
                parser.error("output and inputs must not overlap")
        if ancestor.exists():
            parser.error("output must be a new directory")
        while not ancestor.exists():
            ancestor = ancestor.parent
        free = shutil.disk_usage(ancestor).free
        if (not 0 < args.min_free_gib < float("inf") or free < args.min_free_gib * 1024**3
                or args.batch_size < 1 or args.max_line_bytes < 1):
            parser.error("insufficient free disk space")
        records = {str(y): sources[y][0]["audit"]["passages"] for y in sorted(sources)}
        print(pilot.canonical({"preflight": "passed", "years": sorted(selection), "free_bytes": free,
                               "disk_floor_gib": args.min_free_gib, "payload_records_scanned": 0,
                               "declared_records_by_year": records,
                               "estimated_scan_seconds_at_pilot_rate": sum(records.values()) * 133.8 / 2458630}))
        return 0
    report = run(dataset_roots=args.dataset_root, import_index=args.import_index, out_dir=args.out_dir, batch_size=args.batch_size, max_line_bytes=args.max_line_bytes)
    print(pilot.canonical({"state":report["state"], "counts":report["counts"], "out_dir":str(args.out_dir)}))
    return 0 if report["state"] == "complete_verified" else 3 if report["state"] == "complete_provisional" else 2


if __name__ == "__main__":
    raise SystemExit(main())
