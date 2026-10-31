"""W6-R19 Checkpoint 2A: strict, target-only, read-only-input 2008 pilot.

No legacy audit status, pool construction, gold adjudication, or other years.
"""
from __future__ import annotations

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import time
import zlib

from src.eval import evidence_identity as identity
from src.eval.audit_week6_evidence import (
    BATCH, WINDOWS_SHA256, HashReader, discover, retention_intervals, sha256,
    utc, validate_audit, validate_inputs,
)

VERSION = "w6-r19-target-index/2a-v1"
PROFILE = "w6-r19-frozen-passages/v1"
INGESTION_PROFILE = {
    "version": PROFILE, "required_fields": {"doc_id": "string", "text": "string", "timestamp": "string"},
    "unknown_fields": "reject", "duplicate_json_keys": "reject", "decoding": "strict UTF-8",
    "text_identity": "exact decoded JSON string encoded as UTF-8", "evidence_fields": [],
    "timestamp": "Checkpoint-1 UTC RFC3339 subset; original spelling retained",
    "source_identity": "physical artifact SHA-256 plus 1-based decompressed physical line",
}
YEAR = 2008
PARENT = re.compile(r"([0-9]{8})000000000000\x00\x01[0-9a-f]{64}\x00\x01\Z")
PID = re.compile(r"(.+)_((?:0|[1-9][0-9]*))\Z", re.DOTALL)
DEFAULT_MAX_LINE = 16 * 1024 * 1024

DDL = """
PRAGMA foreign_keys=ON;
PRAGMA cache_size=-32768;
PRAGMA temp_store=FILE;
CREATE TABLE run (id INTEGER PRIMARY KEY CHECK(id=1), version TEXT, profile TEXT,
 state TEXT NOT NULL, error TEXT);
CREATE TABLE candidates (ordinal INTEGER PRIMARY KEY, qa_id TEXT UNIQUE NOT NULL,
 parent_id TEXT NOT NULL, record_json TEXT NOT NULL);
CREATE TABLE artifacts (id INTEGER PRIMARY KEY, path TEXT NOT NULL, sidecar_path TEXT NOT NULL,
 sidecar_sha256 TEXT NOT NULL, sidecar_raw BLOB NOT NULL, sidecar_json TEXT NOT NULL, state TEXT NOT NULL,
 physical_sha256 TEXT, content_sha256 TEXT, compression TEXT, records INTEGER DEFAULT 0,
 target_records INTEGER DEFAULT 0,
 physical_lines INTEGER DEFAULT 0, bytes INTEGER DEFAULT 0, original_compressed_verified INTEGER DEFAULT 0,
 historical_verified INTEGER DEFAULT 0, verification_basis TEXT, replica_of INTEGER REFERENCES artifacts(id));
CREATE UNIQUE INDEX unique_artifact ON artifacts(physical_sha256) WHERE replica_of IS NULL;
CREATE TABLE aliases (pid TEXT PRIMARY KEY, parent_id TEXT NOT NULL, passage_index TEXT NOT NULL);
CREATE INDEX parent_lookup ON aliases(parent_id);
CREATE TABLE variants (vid TEXT PRIMARY KEY, pid TEXT NOT NULL REFERENCES aliases(pid),
 text BLOB NOT NULL, timestamp TEXT NOT NULL, preimage BLOB NOT NULL);
CREATE TABLE occurrences (artifact INTEGER NOT NULL REFERENCES artifacts(id), line INTEGER NOT NULL,
 vid TEXT NOT NULL REFERENCES variants(vid), raw_sha256 TEXT NOT NULL, raw_line BLOB NOT NULL,
 uncompressed_offset INTEGER NOT NULL, occurrence_id TEXT UNIQUE,
 PRIMARY KEY(artifact,line));
CREATE INDEX variant_occurrences ON occurrences(vid);
CREATE INDEX raw_line_lookup ON occurrences(raw_sha256);
CREATE TABLE observations (artifact INTEGER NOT NULL REFERENCES artifacts(id), start_line INTEGER NOT NULL,
 end_line INTEGER NOT NULL, parent_id TEXT NOT NULL, member_count INTEGER NOT NULL,
 boundary_basis TEXT NOT NULL, membership_status TEXT NOT NULL,
 PRIMARY KEY(artifact,start_line));
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError(f"duplicate JSON key: {key}")
            obj[key] = value
        return obj

    def constant(value):
        raise ValueError(f"non-finite JSON constant: {value}")

    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                      parse_constant=constant)


def parent_id(value):
    if not isinstance(value, str) or not PARENT.fullmatch(value):
        raise ValueError("malformed upstream parent ID")
    datetime.strptime(value[:8], "%Y%m%d")
    return value


def parse_passage(raw, year, intervals):
    record = strict_json(raw)
    if not isinstance(record, dict) or set(record) != set(INGESTION_PROFILE["required_fields"]):
        raise ValueError("frozen passage requires exactly doc_id, text, timestamp")
    evidence = identity.record_from_mapping(record)
    match = PID.fullmatch(evidence.upstream_passage_id)
    if not match:
        raise ValueError("malformed upstream passage ID")
    parent, index = match.groups()
    parent_id(parent)
    when = utc(evidence.timestamp)
    if when.year != year or parent[:4] != str(year):
        raise ValueError("archive_year_mismatch")
    if parent[:8] != when.strftime("%Y%m%d"):
        raise ValueError("passage_id_publication_day_mismatch")
    # Only six merged intervals for the canonical 400; no per-candidate scan.
    if not any(start <= when <= end for start, end in zip(*intervals)):
        raise ValueError("outside_retention_union")
    return evidence, parent, index


def _same_stream(a, b, *, decompress=False):
    """Compare bytes, not just hashes, on artifact/representation digest reuse."""
    def opened(path):
        stream = Path(path).open("rb")
        if decompress:
            magic = stream.read(2)
            stream.seek(0)
            if magic == b"\x1f\x8b":
                stream.close()
                return gzip.open(path, "rb")
        return stream
    with opened(a) as left, opened(b) as right:
        while True:
            x, y = left.read(1024 * 1024), right.read(1024 * 1024)
            if x != y:
                return False
            if not x:
                return True


def _observation(db, artifact, run):
    if run is not None:
        parent, start, end, count, _, _ = run
        db.execute("INSERT INTO observations VALUES (?,?,?,?,?,?,?)", (
            artifact, start, end, parent, count,
            "contiguous_zero_based_passage_run", "original_document_membership_unverified"))


def ingest(db, path, sidecar_path, audit, targets, intervals, *, batch_size, max_line_bytes, sidecar_raw):
    """Stage target rows; bind occurrence IDs only after successful EOF checks."""
    path, sidecar_path = Path(path), Path(sidecar_path)
    before = path.stat()
    if before.st_size == 0:
        raise ValueError("zero-byte source artifact")
    cursor = db.execute("INSERT INTO artifacts(path,sidecar_path,sidecar_sha256,sidecar_raw,sidecar_json,state) "
                        "VALUES(?,?,?,?,?, 'scanning')", (
                            str(path), str(sidecar_path), hashlib.sha256(sidecar_raw).hexdigest(), sidecar_raw, canonical(audit)))
    artifact = cursor.lastrowid
    db.commit()
    content = hashlib.sha256()
    records = line_no = offset = target_records = 0
    observed = None
    with path.open("rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
        source.seek(0)
        hashed = HashReader(source)
        with io.BufferedReader(hashed) as buffered:
            with (gzip.GzipFile(fileobj=buffered) if compressed else nullcontext(buffered)) as stream:
                while True:
                    raw = stream.readline(max_line_bytes + 1)
                    if not raw:
                        break
                    line_no += 1
                    if len(raw) > max_line_bytes:
                        raise ValueError(f"{path}:{line_no}: line exceeds configured limit")
                    content.update(raw)
                    start_offset = offset
                    offset += len(raw)
                    if not raw.strip():
                        _observation(db, artifact, observed)
                        observed = None
                        continue
                    records += 1
                    try:
                        evidence, parent, index = parse_passage(raw, YEAR, intervals)
                    except (ValueError, TypeError, UnicodeError) as exc:
                        raise ValueError(f"{path}:{line_no}: {exc}") from exc
                    if parent in targets:
                        target_records += 1
                        vid, preimage = identity.variant_id(evidence), identity.variant_encoding(evidence)
                        old = db.execute("SELECT preimage FROM variants WHERE vid=?", (vid,)).fetchone()
                        if old is not None and bytes(old[0]) != preimage:
                            raise ValueError("variant SHA-256 collision")
                        db.execute("INSERT OR IGNORE INTO aliases VALUES(?,?,?)", (evidence.upstream_passage_id, parent, index))
                        if old is None:
                            db.execute("INSERT INTO variants VALUES(?,?,?,?,?)", (
                                vid, evidence.upstream_passage_id, evidence.text, evidence.timestamp, preimage))
                        raw_hash = hashlib.sha256(raw).hexdigest()
                        old_raw = db.execute("SELECT raw_line FROM occurrences WHERE raw_sha256=? LIMIT 1", (raw_hash,)).fetchone()
                        if old_raw is not None and bytes(old_raw[0]) != raw:
                            raise ValueError("raw-line SHA-256 collision")
                        db.execute("INSERT INTO occurrences VALUES(?,?,?,?,?,?,NULL)", (
                            artifact, line_no, vid, raw_hash, raw, start_offset))
                        if index == "0":
                            _observation(db, artifact, observed)
                            observed = (parent, line_no, line_no, 1, 1, evidence.timestamp)
                        elif (observed is not None and observed[0] == parent and index == str(observed[4])
                              and observed[5] == evidence.timestamp):
                            p, start, _, count, next_index, timestamp = observed
                            observed = (p, start, line_no, count + 1, next_index + 1, timestamp)
                        else:
                            _observation(db, artifact, observed)
                            observed = None
                    else:
                        _observation(db, artifact, observed)
                        observed = None
                    if records % batch_size == 0:
                        db.execute("UPDATE artifacts SET records=?,target_records=?,physical_lines=? WHERE id=?", (records, target_records, line_no, artifact))
                        db.commit()
                _observation(db, artifact, observed)
        physical, decompressed = hashed.digest.hexdigest(), content.hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("source changed during scan")
    if sidecar_path.read_bytes() != sidecar_raw:
        raise ValueError("sidecar changed during scan")
    if records != audit["passages"]:
        raise ValueError("passage count differs from extraction sidecar")
    if compressed and physical != audit["output_sha256"]:
        raise ValueError("compressed-byte checksum mismatch")
    expected = audit.get("content_sha256", audit.get("decompressed_sha256"))
    if expected is not None and decompressed != expected:
        raise ValueError("decompressed-content checksum mismatch")
    replica = db.execute("SELECT id,path FROM artifacts WHERE physical_sha256=? AND replica_of IS NULL", (physical,)).fetchone()
    if replica and not _same_stream(replica[1], path):
        raise ValueError("artifact SHA-256 collision")
    others = db.execute("SELECT content_sha256,path FROM artifacts WHERE state='verified' AND replica_of IS NULL").fetchall()
    for old_hash, old_path in others:
        if old_hash != decompressed:
            raise ValueError("conflicting representations of the selected 2008 dataset")
        if not _same_stream(old_path, path, decompress=True):
            raise ValueError("decompressed-stream SHA-256 collision")
    if replica:
        db.execute("DELETE FROM observations WHERE artifact=?", (artifact,))
        db.execute("DELETE FROM occurrences WHERE artifact=?", (artifact,))
    else:
        # Cursor iteration keeps occurrence-ID finalization bounded in memory.
        for (line,) in db.execute("SELECT line FROM occurrences WHERE artifact=? ORDER BY line", (artifact,)):
            oid = identity.occurrence_id(identity.SourceOccurrence(physical, line))
            if db.execute("SELECT 1 FROM occurrences WHERE occurrence_id=?", (oid,)).fetchone():
                raise ValueError("occurrence SHA-256 collision")
            db.execute("UPDATE occurrences SET occurrence_id=? WHERE artifact=? AND line=?", (oid, artifact, line))
    historical = compressed or expected is not None
    db.execute("UPDATE artifacts SET state='verified',physical_sha256=?,content_sha256=?,compression=?,"
               "records=?,target_records=?,physical_lines=?,bytes=?,original_compressed_verified=?,historical_verified=?,"
               "verification_basis=?,replica_of=? WHERE id=?", (
                   physical, decompressed, "gzip" if compressed else "plain",
                   records, target_records, line_no, before.st_size, int(compressed), int(historical),
                   "original_gzip" if compressed else ("recorded_content_hash" if expected else "observed_plain_only"),
                   replica[0] if replica else None, artifact))
    db.commit()


def _coverage(candidate, years, *, effective=False):
    start, end = utc(candidate["window_start"]), utc(candidate["window_end"])
    if effective:
        end = min(end, datetime.fromtimestamp(candidate["question_ts"], timezone.utc))
    requested = list(range(start.year, end.year + 1)) if start <= end else []
    return {"start": start.isoformat(), "end": end.isoformat(), "empty": start > end,
            "requested_years": requested, "configured_years": [y for y in requested if 2008 <= y <= 2020],
            "outside_archive_years": [y for y in requested if not 2008 <= y <= 2020],
            "verified_scanned_years": [y for y in requested if y in years],
            "unscanned_configured_years": [y for y in requested if 2008 <= y <= 2020 and y not in years]}


def ledger(db, candidates, *, successful):
    artifacts = db.execute("SELECT count(*),coalesce(min(historical_verified),0) FROM artifacts WHERE state='verified'").fetchone()
    historical = bool(artifacts[0] and artifacts[1])
    years = {YEAR} if successful else set()
    for candidate in candidates:
        parent = candidate["evidence_id"]
        gold_year = int(parent[:4])
        applicable = gold_year == YEAR
        source_status = ("verified" if historical else "provisional_historical_equivalence_unverified") if successful else "rejected_or_incomplete"
        scan = "complete_for_2008_only" if successful and applicable else ("failed_or_interrupted" if not successful and applicable else "not_scanned")
        variant_count = 0
        records = db.execute("SELECT v.timestamp FROM variants v JOIN aliases a ON a.pid=v.pid "
                             "WHERE a.parent_id=? ORDER BY v.vid", (parent,)) if successful else ()
        issues = set()
        for (timestamp,) in records:
            variant_count += 1
            when = utc(timestamp)
            if when.date() != datetime.fromtimestamp(candidate["evidence_ts"], timezone.utc).date():
                issues.add("evidence_day_mismatch")
            if not utc(candidate["window_start"]) <= when <= utc(candidate["window_end"]):
                issues.add("outside_candidate_window")
            if when.timestamp() > candidate["question_ts"]:
                issues.add("publication_after_question")
        conflict = db.execute("SELECT count(*) FROM (SELECT a.pid FROM aliases a JOIN variants v ON v.pid=a.pid "
                              "WHERE a.parent_id=? GROUP BY a.pid HAVING count(*)>1)", (parent,)).fetchone()[0] if successful else 0
        if not 2008 <= gold_year <= 2020:
            availability = "gold_outside_configured_archives"
        elif not successful or not applicable:
            availability = "not_determined"
        else:
            availability = "present" if variant_count else (
                "absent_in_verified_2008_scope" if historical else "absent_in_provisional_2008_scope")
        yield {**candidate, "source_validation": source_status if applicable else "not_scanned",
               "scan_completion": scan, "evidence_availability": availability,
               "rendering_identity": ("ambiguous_passage_variants" if conflict else
                                      "one_variant_per_observed_passage_membership_unverified") if variant_count else "not_determined",
               "ambiguous": True if conflict else None, "conflicting_passage_alias_count": conflict,
               "annotation_identity": "unresolved", "semantic_support": "not_assessed",
               "original_document_membership": "not_established", "variant_count": variant_count,
               "variant_reference": {"file": "variants.jsonl", "parent_id": parent} if successful else None,
               "temporal_issues": sorted(issues), "final_screening_eligibility": "not_assessed",
               "identity_scope_certified": bool(successful and applicable and historical and not issues),
               "canonical_temporal_coverage": _coverage(candidate, years),
               "effective_prequestion_temporal_coverage": _coverage(candidate, years, effective=True)}


def _write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical(value) + "\n")


def _write_rows(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(canonical(row) + "\n")


def export_index(db, out):
    _write_rows(out / "aliases.jsonl", (
        {"upstream_passage_id": pid, "parent_id": parent,
         "variant_count": variants, "variant_reference": {"file": "variants.jsonl", "upstream_passage_id": pid},
         "physical_occurrences": physical, "logical_occurrences": logical,
         "exact_duplicate_extra_occurrences": logical - variants,
         "raw_duplicate_extra_occurrences": logical - raw_variants,
         "conflicting_variants": variants > 1}
        for pid, parent, variants, physical, logical, raw_variants in db.execute(
            "SELECT a.pid,a.parent_id,count(DISTINCT v.vid),count(o.line),"
            "count(DISTINCT f.content_sha256 || ':' || o.line),count(DISTINCT o.raw_sha256) FROM aliases a "
            "JOIN variants v ON v.pid=a.pid JOIN occurrences o ON o.vid=v.vid "
            "JOIN artifacts f ON f.id=o.artifact GROUP BY a.pid ORDER BY a.pid")))
    _write_rows(out / "variants.jsonl", (
        {"variant_id": vid, "upstream_passage_id": pid, "parent_id": parent, "text": bytes(text).decode("utf-8"),
         "timestamp": timestamp, "evidence_fields": {}}
        for vid, pid, parent, text, timestamp in db.execute(
            "SELECT v.vid,v.pid,a.parent_id,v.text,v.timestamp FROM variants v JOIN aliases a ON a.pid=v.pid ORDER BY v.vid")))
    _write_rows(out / "occurrences.jsonl", (
        {"occurrence_id": oid, "artifact_sha256": digest, "physical_line": line,
         "variant_id": vid, "raw_line_sha256": raw, "uncompressed_offset": offset}
        for oid, digest, line, vid, raw, offset in db.execute(
            "SELECT o.occurrence_id,f.physical_sha256,o.line,o.vid,o.raw_sha256,o.uncompressed_offset "
            "FROM occurrences o JOIN artifacts f ON f.id=o.artifact ORDER BY f.physical_sha256,o.line")))
    _write_rows(out / "document_observations.jsonl", (
        {"artifact_sha256": digest, "start_line": start, "end_line": end, "parent_id": parent,
         "member_count": count, "boundary_basis": basis, "membership_status": status}
        for digest, start, end, parent, count, basis, status in db.execute(
            "SELECT f.physical_sha256,d.start_line,d.end_line,d.parent_id,d.member_count,d.boundary_basis,d.membership_status "
            "FROM observations d JOIN artifacts f ON f.id=d.artifact ORDER BY f.physical_sha256,d.start_line")))


def peak_memory():
    """OS process high-water RSS, including native allocations (not an interval delta)."""
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    "peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return counters.peak
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def run_pilot(*, out_dir, sources=None, dataset_root=None, windows_path=BATCH / "evidence_windows_400.jsonl",
              metadata_path=BATCH / "candidate_metadata_400.jsonl", batch_path=BATCH / "screening_batch_ids.jsonl",
              expected_windows_sha=WINDOWS_SHA256, per_stratum=200, batch_size=10000,
              max_line_bytes=DEFAULT_MAX_LINE, parser_path=None):
    """Sources are explicit (payload, sidecar) pairs; only year 2008 is supported."""
    if type(batch_size) is not int or batch_size < 1 or type(max_line_bytes) is not int or max_line_bytes < 1:
        raise ValueError("batch_size and max_line_bytes must be positive integers")
    if sources is not None and dataset_root is not None:
        raise ValueError("select explicit sources or one dataset_root, not both")
    sources = sorted({(Path(p).resolve(), Path(a).resolve()) for p, a in (sources or [])})
    out = Path(out_dir).resolve()
    root = Path(dataset_root).resolve() if dataset_root is not None else None
    if root is not None and (out == root or root in out.parents or out in root.parents):
        raise ValueError("output and selected dataset root must not overlap")
    protected = [p for pair in sources for p in pair] + [Path(p).resolve() for p in (windows_path, metadata_path, batch_path)]
    if any(out == p or out in p.parents for p in protected):
        raise ValueError("output overlaps inputs")
    out.mkdir(parents=True, exist_ok=False)
    parser_path = Path(parser_path) if parser_path else Path(__file__).resolve().parents[2] / "third_party/streamingqa/extraction.py"
    started = time.perf_counter()
    candidates, inputs, error, success, interrupted = [], {}, None, False, False
    db_path = out / "target_index.sqlite"
    with closing(sqlite3.connect(db_path)) as db:
        db.executescript(DDL)
        db.execute("INSERT INTO run VALUES(1,?,?, 'scanning',NULL)", (VERSION, PROFILE))
        db.commit()
        try:
            # Apply strict JSON parsing before using the unchanged canonical validator.
            for file in (windows_path, metadata_path, batch_path):
                with Path(file).open("rb") as stream:
                    for line in stream:
                        if line.strip():
                            strict_json(line)
            candidates, inputs = validate_inputs(windows_path, metadata_path, batch_path,
                                                 expected_sha=expected_windows_sha, per_stratum=per_stratum)
            for i, candidate in enumerate(candidates):
                parent_id(candidate["evidence_id"])
                db.execute("INSERT INTO candidates VALUES(?,?,?,?)", (i, candidate["qa_id"], candidate["evidence_id"], canonical(candidate)))
            db.commit()
            if root is not None:
                # Strictly parse sidecars before unchanged discovery can interpret them.
                for path in root.rglob("*"):
                    if path.is_file() and re.fullmatch(r"\.?2008\.audit\.json(?:\.tmp)?", path.name):
                        strict_json(path.read_bytes())
                items = discover([root], years=(YEAR,), root_scoped=True)[YEAR]
                sources = sorted((i["path"], i["audit_path"]) for i in items)
            if not sources:
                raise ValueError("missing selected 2008 sources")
            targets = {c["evidence_id"] for c in candidates}
            intervals = retention_intervals(candidates)
            signature = None
            for path, sidecar in sources:
                raw = sidecar.read_bytes()
                audit = strict_json(raw)
                validate_audit(audit, YEAR, expected_windows_sha)
                for field in ("content_sha256", "decompressed_sha256"):
                    if field in audit and not isinstance(audit[field], str):
                        raise ValueError(f"{field} must be a string")
                if "config_sha256" in audit and (not isinstance(audit["config_sha256"], str)
                                                   or not re.fullmatch(r"[0-9a-f]{64}", audit["config_sha256"])):
                    raise ValueError("invalid declared config_sha256")
                if audit["deepmind_extraction_sha256"] != sha256(parser_path):
                    raise ValueError("sidecar parser hash differs from pinned parser")
                current = canonical({k: audit.get(k) for k in (
                    "output_sha256", "passages", "windows_sha256", "sorting_keys_md5",
                    "deepmind_extraction_sha256", "prepend_date", "parser", "archive_url",
                    "extraction_config", "config_sha256")})
                if signature is not None and signature != current:
                    raise ValueError("incompatible representation sidecars")
                signature = current
                ingest(db, path, sidecar, audit, targets, intervals,
                       batch_size=batch_size, max_line_bytes=max_line_bytes, sidecar_raw=raw)
            # A verified original gzip counterpart independently verifies plain content.
            if db.execute("SELECT 1 FROM artifacts WHERE original_compressed_verified=1").fetchone():
                db.execute("UPDATE artifacts SET historical_verified=1, verification_basis='verified_gzip_counterpart' "
                           "WHERE compression='plain'")
            if db.execute("SELECT 1 FROM occurrences WHERE occurrence_id IS NULL").fetchone():
                raise ValueError("unfinalized target occurrences")
            if db.execute("SELECT 1 FROM artifacts a WHERE a.replica_of IS NULL AND a.target_records != "
                          "(SELECT count(*) FROM occurrences o WHERE o.artifact=a.id)").fetchone():
                raise ValueError("target occurrence accounting mismatch")
            if db.execute("SELECT 1 FROM variants v WHERE NOT EXISTS (SELECT 1 FROM occurrences o WHERE o.vid=v.vid)").fetchone():
                raise ValueError("unreferenced target variant")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("index foreign key violation")
            success = True
        except (ValueError, TypeError, KeyError, OSError, EOFError, UnicodeError, sqlite3.Error, zlib.error, KeyboardInterrupt) as exc:
            interrupted = isinstance(exc, KeyboardInterrupt)
            error = f"{type(exc).__name__}: {exc}"
            db.rollback()
            db.execute("UPDATE artifacts SET state='incomplete' WHERE state='scanning'")
            # Disallow finalized IDs anywhere in an unsuccessful run's public state.
            db.execute("UPDATE occurrences SET occurrence_id=NULL")
        historical = success and not db.execute("SELECT 1 FROM artifacts WHERE historical_verified=0").fetchone()
        state = ("complete_verified" if historical else "complete_provisional") if success else ("interrupted" if interrupted else "rejected")
        # Completion belongs only to the final manifest; SQLite is never sufficient.
        db.execute("UPDATE run SET state=?,error=? WHERE id=1", (
            "validated_manifest_required" if success else state, error))
        db.commit()
        _write_rows(out / "recovery_ledger.jsonl", ledger(db, candidates, successful=success))
        if success:
            export_index(db, out)
        artifacts = [dict(zip([c[0] for c in cursor.description], row)) for cursor in [db.execute(
            "SELECT path,sidecar_path,sidecar_sha256,state,physical_sha256,content_sha256,compression,records,target_records,physical_lines,bytes,"
            "original_compressed_verified,historical_verified,verification_basis,replica_of FROM artifacts ORDER BY path")]
            for row in cursor]
        counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("candidates", "aliases", "variants", "occurrences", "observations")}
    _write_json(out / "measurements.json", {
        "runtime_seconds": time.perf_counter() - started, "peak_process_rss_bytes": peak_memory(),
        "peak_memory_scope": "OS process lifetime high-water RSS, including SQLite/native allocations",
        "database_bytes": db_path.stat().st_size, "source_record_counts": [
            {"path": a["path"], "records": a["records"], "state": a["state"]} for a in artifacts]})
    # Manifest written last: absent/incomplete manifest never certifies a run.
    report = {"schema_version": VERSION, "ingestion_profile": PROFILE, "profile_definition": INGESTION_PROFILE,
              "profile_sha256": hashlib.sha256(canonical(INGESTION_PROFILE).encode("ascii")).hexdigest(),
              "identity_schema": identity.SCHEMA_VERSION,
              "state": state, "scan_completion": "complete_for_2008_only" if success else "incomplete",
              "target_scope_only": True, "scan_years": [YEAR], "configured_archive_years": list(range(2008, 2021)),
              "identity_scope_certified": bool(historical), "original_audit_status_changed": False,
              "annotation_identity": "unresolved", "semantic_support": "not_assessed", "error": error,
              "inputs": inputs, "selected_dataset_root": str(root) if root else None,
              "artifacts": artifacts, "counts": counts,
              "target_parent_count": len({c["evidence_id"] for c in candidates}),
              "code_sha256": {p.name: sha256(p) for p in (
                  Path(__file__), Path(identity.__file__), Path(__file__).with_name("audit_week6_evidence.py"), parser_path)},
              "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version},
              "parameters": {"batch_size": batch_size, "max_line_bytes": max_line_bytes},
              "output_sha256": {p.name: sha256(p) for p in sorted(out.iterdir()) if p.is_file()}}
    # Atomic, no-overwrite publication; a partial manifest is never a completion marker.
    staged_manifest = out / "manifest.json.tmp"
    with staged_manifest.open("xb") as stream:
        stream.write((canonical(report) + "\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    os.link(staged_manifest, out / "manifest.json")
    staged_manifest.unlink()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True, help="Exact canonical 2008 dataset root only")
    parser.add_argument("--out-dir", type=Path, required=True, help="New directory outside all inputs")
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--max-line-bytes", type=int, default=DEFAULT_MAX_LINE)
    args = parser.parse_args()
    root, out = args.dataset_root.resolve(), args.out_dir.resolve()
    if out == root or root in out.parents or out in root.parents:
        parser.error("output and dataset root must not overlap")
    report = run_pilot(dataset_root=root, out_dir=out,
                       batch_size=args.batch_size, max_line_bytes=args.max_line_bytes)
    print(canonical({"state": report["state"], "counts": report["counts"], "out_dir": str(out)}))
    return 0 if report["state"] == "complete_verified" else (3 if report["state"] == "complete_provisional" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
