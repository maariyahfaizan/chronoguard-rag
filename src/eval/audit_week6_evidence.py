"""W6-R19 mounted evidence inventory and gold recovery; no downloads or models.

Run from the repository root with ``python -m src.eval.audit_week6_evidence``.
Inputs are read-only. Outputs are exclusive, UTF-8/LF, and never select questions.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import closing, nullcontext
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import platform
import re
import sqlite3
import subprocess
import tempfile
import zlib

from src.eval.build_week6_archive_coverage import build_coverage

YEARS = tuple(range(2008, 2021))
WINDOWS_SHA256 = "99da0f327616a1725ddf3a323d459868ebac9d498aa94cd2acf332c5638f8cab"
KEYS_MD5 = "3356d7e38e43b7bf4338e2003ab92f36"
PARSER = "DeepMind StreamingQA get_deduplicated_wmt_docs/get_wmt_passages_from_docs"
BASE = Path("results/week6_sampling_draft")
BATCH = BASE / "screening_batch_v1"
DEFAULT_OUT = BASE / "w6_r19_inventory"
VERSION = "w6_r19_v1"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def write_jsonl(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json_bytes(row).decode("utf-8") + "\n")


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError(f"Expected UTC timestamp: {value!r}")
    return dt


def unique_rows(rows, label):
    result = {}
    for row in rows:
        qid = row["qa_id"]
        if not isinstance(qid, str) or not qid or qid in result:
            raise ValueError(f"{label}: invalid or duplicate qa_id {qid!r}")
        result[qid] = row
    return result


def validate_inputs(windows_path, metadata_path, batch_path, *, expected_sha=WINDOWS_SHA256,
                    per_stratum=200):
    """Only CRLF is normalized for the canonical checksum; inputs are never written."""
    raw = Path(windows_path).read_bytes()
    lf_hash = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    if lf_hash != expected_sha:
        raise ValueError("Canonical LF windows checksum mismatch")
    windows = read_rows(windows_path)
    wm = unique_rows(windows, "windows")
    metadata = unique_rows(read_rows(metadata_path), "metadata")
    batch = unique_rows(read_rows(batch_path), "batch")
    if wm.keys() != metadata.keys() or wm.keys() != batch.keys():
        raise ValueError("Candidate ID sets differ")
    if Counter(r["recent_or_past"] for r in windows) != Counter(recent=per_stratum, past=per_stratum):
        raise ValueError("Expected balanced canonical candidate strata")
    previous = {"recent": 0, "past": 0}
    for w in windows:
        qid = w["qa_id"]
        m, b = metadata[qid], batch[qid]
        for key in ("recent_or_past", "reserve_rank"):
            if w[key] != b[key] or type(w[key]) is not type(b[key]):
                raise ValueError(f"{qid}: batch {key} mismatch")
        for key in ("recent_or_past", "reserve_rank", "evidence_id", "evidence_ts", "window_start", "window_end"):
            if w[key] != m[key] or type(w[key]) is not type(m[key]):
                raise ValueError(f"{qid}: metadata {key} mismatch")
        rank, stratum = w["reserve_rank"], w["recent_or_past"]
        if type(rank) is not int or rank <= previous[stratum]:
            raise ValueError(f"{qid}: invalid reserve rank")
        previous[stratum] = rank
        if type(w["evidence_ts"]) is not int or type(m["question_ts"]) is not int:
            raise ValueError(f"{qid}: timestamps must be integer epoch seconds")
        center = datetime.fromtimestamp(w["evidence_ts"], timezone.utc)
        if (utc(w["window_start"]) != center - timedelta(days=56)
                or utc(w["window_end"]) != center + timedelta(days=56)):
            raise ValueError(f"{qid}: window is not canonical +/-56 days")
        eid = w["evidence_id"]
        if not isinstance(eid, str) or not re.match(r"^\d{20}", eid) or eid[:8] != center.strftime("%Y%m%d"):
            raise ValueError(f"{qid}: evidence ID date disagrees with timestamp")
        if m["question_ts"] < w["evidence_ts"]:
            raise ValueError(f"{qid}: evidence follows question timestamp")
        if not isinstance(m.get("question"), str) or not m["question"].strip():
            raise ValueError(f"{qid}: missing question")
        if not isinstance(m.get("answers"), list) or not all(isinstance(a, str) for a in m["answers"]):
            raise ValueError(f"{qid}: invalid answers")
    if [r["qa_id"] for r in windows] != list(batch):
        raise ValueError("Batch and canonical window ordering differ")
    return [metadata[w["qa_id"]] for w in windows], {
        "windows_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "windows_lf_sha256": lf_hash, "crlf_count": raw.count(b"\r\n"),
        "metadata_sha256": sha256(metadata_path), "batch_sha256": sha256(batch_path),
        "paths": {"windows": str(windows_path), "metadata": str(metadata_path), "batch": str(batch_path)},
    }


def validate_audit(audit, year, windows_hash):
    if not isinstance(audit, dict):
        raise ValueError(f"{year}: extraction audit must be a JSON object")
    required = {"year", "status", "passages", "archive_url", "windows_sha256", "sorting_keys_md5",
                "deepmind_extraction_sha256", "output_sha256", "prepend_date", "parser"}
    if required - audit.keys():
        raise ValueError(f"{year}: missing audit fields {sorted(required - audit.keys())}")
    if (type(audit["year"]) is not int or audit["year"] != year or audit["status"] != "complete"
            or type(audit["passages"]) is not int or audit["passages"] < 0
            or audit["windows_sha256"] != windows_hash or audit["sorting_keys_md5"] != KEYS_MD5
            or audit["prepend_date"] is not False or audit["parser"] != PARSER):
        raise ValueError(f"{year}: incompatible extraction metadata")
    for key in ("deepmind_extraction_sha256", "output_sha256"):
        if not isinstance(audit[key], str) or not re.fullmatch(r"[0-9a-f]{64}", audit[key]):
            raise ValueError(f"{year}: invalid {key}")
    if audit["archive_url"] != f"https://data.statmt.org/news-crawl/doc/en/news-docs.{year}.en.filtered.gz":
        raise ValueError(f"{year}: incompatible archive URL")
    for key in ("content_sha256", "decompressed_sha256"):
        if key in audit and not re.fullmatch(r"[0-9a-f]{64}", str(audit[key])):
            raise ValueError(f"{year}: invalid {key}")
    if ("content_sha256" in audit and "decompressed_sha256" in audit
            and audit["content_sha256"] != audit["decompressed_sha256"]):
        raise ValueError(f"{year}: conflicting content checksum fields")


def discover(roots, *, years=YEARS, windows_hash=WINDOWS_SHA256, root_scoped=False):
    """Associate shards with the nearest ancestor's year sidecar, never by mount name.

    A .jsonl directory may contain an extracted gzip member with a temporary-looking
    name. Such members are accepted only with a complete compatible sidecar.
    """
    roots = [Path(r).resolve() for r in roots]
    files = set()
    for root in roots:
        root = Path(root).resolve()
        if not root.is_dir():
            raise ValueError(f"Evidence root is not a directory: {root}")
        files.update(p.resolve() for p in root.rglob("*") if p.is_file())
    if root_scoped and any(not any(root in p.parents for root in roots) for p in files):
        raise ValueError("Evidence resolves outside selected dataset roots")
    audits = defaultdict(list)
    for path in sorted(files):
        match = re.fullmatch(r"\.?(\d{4})\.audit\.json(?:\.tmp)?", path.name)
        if match and int(match[1]) in years:
            year = int(match[1])
            record = json.loads(path.read_text(encoding="utf-8"))
            validate_audit(record, year, windows_hash)
            audits[year].append((path, record))
    result = {}
    compatibility = None
    for year in years:
        sidecars = audits[year]
        if not sidecars:
            raise ValueError(f"Missing extraction audit for year {year}")
        for path, record in sidecars:
            signature = {k: record.get(k) for k in ("windows_sha256", "sorting_keys_md5",
                "deepmind_extraction_sha256", "prepend_date", "parser", "extraction_config", "config_sha256")}
            if compatibility is None:
                compatibility = signature
            if signature != compatibility:
                raise ValueError(f"{year}: incompatible extraction configurations at {path}")
        identity = {(r["output_sha256"], r["passages"]) for _, r in sidecars}
        if len(identity) != 1:
            raise ValueError(f"{year}: conflicting duplicate dataset versions")
        shards = []
        for path in sorted(files):
            if not any(re.fullmatch(rf"\.?{year}(?:\.attempt\d+)?\.jsonl(?:\.gz)?(?:\.tmp)?", part)
                       for part in path.parts):
                continue
            # Do not mistake sidecars or metadata inside a .jsonl directory for evidence.
            if not re.search(r"\.jsonl(?:\.gz)?(?:\.tmp)?$", path.name):
                continue
            if path.stat().st_size == 0:
                raise ValueError(f"{year}: zero-byte evidence: {path}")
            owners = [(p, r) for p, r in sidecars if p.parent in path.parents]
            if root_scoped:
                dataset = next(root for root in roots if root in path.parents)
                owners = [(p, r) for p, r in owners if dataset in p.parents]
                if not owners:
                    # A nested sidecar may describe a sibling payload, but only
                    # within one explicitly selected dataset, with no ambiguity.
                    owners = [(p, r) for p, r in sidecars if dataset in p.parents]
                    if len(owners) > 1:
                        raise ValueError(f"{year}: ambiguous dataset sidecars for {path}")
            if not owners:
                raise ValueError(f"{year}: shard without associated sidecar: {path}")
            owner, audit = max(owners, key=lambda pair: len(pair[0].parent.parts))
            shards.append({"path": path, "audit_path": owner, "audit": audit})
        if not shards:
            raise ValueError(f"Missing evidence shard for year {year}")
        # Every discovered sidecar must have a payload in its own subtree.
        if any(not any(p == s["audit_path"] for s in shards) for p, _ in sidecars):
            raise ValueError(f"{year}: orphan extraction audit")
        result[year] = shards
    return result


def dataset_selection(roots, selected):
    """List excluded directory subtrees without traversing external mounts."""
    selected = [Path(p).resolve() for p in selected]
    if len(set(selected)) != len(selected) or any(
            a in b.parents for a in selected for b in selected if a != b):
        raise ValueError("Canonical dataset roots must be distinct and non-overlapping")
    for path in selected:
        if not path.is_dir():
            raise ValueError(f"Canonical dataset root is not a directory: {path}")
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError(f"Canonical dataset root is outside evidence roots: {path}")
    ignored = set()
    def visit(path):
        if path in selected:
            return
        if not any(path in p.parents for p in selected):
            ignored.add(path)
            return
        for child in sorted(path.iterdir()):
            if child.is_dir():
                visit(child.resolve())
    for root in roots:
        visit(root)
    return {"mode": "explicit_canonical_dataset_roots",
            "selected_dataset_roots": [str(p) for p in selected],
            "ignored_external_mounts": [{"path": str(p), "reason": "outside_explicit_selection"}
                                        for p in sorted(ignored)]}


class HashReader(io.RawIOBase):
    """Hash physical bytes beneath buffering and gzip in the same sequential pass."""
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.source.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
        return count


def retention_intervals(candidates):
    merged = []
    for start, end in sorted((utc(c["window_start"]), utc(c["window_end"])) for c in candidates):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return [a for a, _ in merged], [b for _, b in merged]


def scan_shard(item, year, parents, db, intervals, emit, recovered, bad_parents, *, primary=True):
    path, audit = item["path"], item["audit"]
    content = hashlib.sha256()
    count = 0
    duplicate_count = conflict_count = invalid_count = 0
    starts, ends = intervals
    if primary:
        db.execute("INSERT INTO sources VALUES (?, ?)", (year, str(path)))
    with path.open("rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
        source.seek(0)
        hashed = HashReader(source)
        with io.BufferedReader(hashed) as buffered:
            with (gzip.GzipFile(fileobj=buffered) if compressed else nullcontext(buffered)) as stream:
                for line_number, line in enumerate(stream, 1):
                    content.update(line)
                    if not line.strip():
                        continue
                    count += 1
                    try:
                        passage = json.loads(line.decode("utf-8"))
                        pid, text, timestamp = passage["doc_id"], passage["text"], passage["timestamp"]
                        if not isinstance(pid, str) or not isinstance(text, str) or not isinstance(timestamp, str):
                            raise ValueError("Passage fields must be strings")
                        parent, sep, index = pid.rpartition("_")
                        if (not sep or not index.isascii() or not index.isdecimal()
                                or not re.match(r"^\d{20}", parent)):
                            raise ValueError("Invalid passage ID suffix")
                        when = utc(timestamp)
                        slot = bisect_right(starts, when) - 1
                        issues = []
                        if when.year != year or parent[:4] != str(year):
                            issues.append("archive_year_mismatch")
                        if parent[:8] != when.strftime("%Y%m%d"):
                            issues.append("passage_id_publication_day_mismatch")
                        if slot < 0 or when > ends[slot]:
                            issues.append("outside_retention_union")
                    except (ValueError, TypeError, KeyError) as exc:
                        raise ValueError(f"{path}:{line_number}: malformed passage: {exc}") from exc
                    ref = {"shard": str(path), "audit": str(item["audit_path"]),
                           "archive_year": year, "line": line_number}
                    if primary:
                        fingerprint = hashlib.sha256(json_bytes(passage)).digest()
                        try:
                            db.execute("INSERT INTO passages VALUES (?, ?, ?, ?)", (pid, fingerprint, year, line_number))
                        except sqlite3.IntegrityError:
                            old = db.execute("SELECT p.fingerprint, s.path, p.line FROM passages p "
                                             "JOIN sources s ON p.source=s.year WHERE p.id=?", (pid,)).fetchone()
                            conflict = old[0] != fingerprint
                            duplicate_count += 1
                            conflict_count += int(conflict)
                            issues.append("conflicting_passage_id" if conflict else "duplicate_passage_id")
                            emit({"type": issues[-1], "doc_id": pid, "source": ref,
                                  "first_source": {"shard": old[1], "line": old[2]}})
                        if count % 50000 == 0:
                            db.commit()
                        if issues:
                            invalid_count += 1
                            if parent in parents:
                                bad_parents[parent].update(issues)
                            emit({"type": "passage_integrity", "doc_id": pid, "issues": issues, "source": ref})
                        if parent in parents:
                            recovered[parent].append({**passage, "source": ref})
    physical_hash, content_hash = hashed.digest.hexdigest(), content.hexdigest()
    if count != audit["passages"]:
        raise ValueError(f"{path}: passage count differs from extraction audit")
    if compressed and physical_hash != audit["output_sha256"]:
        raise ValueError(f"{path}: compressed-byte checksum mismatch")
    expected_content = audit.get("content_sha256", audit.get("decompressed_sha256"))
    if expected_content is not None and content_hash != expected_content:
        raise ValueError(f"{path}: decompressed-content checksum mismatch")
    return {"path": str(path), "audit_path": str(item["audit_path"]), "audit_sha256": sha256(item["audit_path"]),
            "compression": "gzip" if compressed else "plain", "physical_sha256": physical_hash,
            "decompressed_content_sha256": content_hash, "original_compressed_sha256": audit["output_sha256"],
            "original_compressed_hash_verified": compressed,
            "content_hash_verified_against_sidecar": expected_content is not None,
            "passages": count, "duplicate_records": duplicate_count, "conflicting_records": conflict_count,
            "invalid_records": invalid_count, "extraction_audit": audit}


def recovery_ledger(candidates, recovered, bad_parents, *, years=YEARS, blocked=None):
    coverage = build_coverage(candidates, archive_years=list(years))
    ledger = []
    for c, cov in zip(candidates, coverage):
        passages = recovered.get(c["evidence_id"], [])
        issues = set(bad_parents.get(c["evidence_id"], set()))
        expected_day = datetime.fromtimestamp(c["evidence_ts"], timezone.utc).date()
        for p in passages:
            when = utc(p["timestamp"])
            if when.date() != expected_day:
                issues.add("evidence_day_mismatch")
            if not utc(c["window_start"]) <= when <= utc(c["window_end"]):
                issues.add("outside_candidate_window")
            if when.timestamp() > c["question_ts"]:
                issues.add("publication_after_question")
        if blocked:
            status = "inventory_rejected"
            issues.add(blocked)
        elif not cov["gold_year_in_configured_range"]:
            status = "gold_outside_archive"
        elif not passages:
            status = "missing_gold_in_archive"
        elif issues:
            status = "recovered_with_integrity_issues"
        else:
            status = "recovered_pending_semantic_review"
        ledger.append({**c, **cov, "status": status, "issues": sorted(issues),
                       "passage_count": len(passages), "passage_ids": sorted({p["doc_id"] for p in passages}),
                       "sources": [p["source"] for p in passages], "semantic_support": "not_assessed"})
    return ledger


def code_provenance():
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        commit, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
    except OSError:
        commit = status = None
    paths = [Path(__file__), root / "src/eval/build_week6_archive_coverage.py",
             root / "third_party/streamingqa/extraction.py"]
    return {"commit": commit, "dirty": None if status is None else bool(status),
            "source_sha256": {str(p.relative_to(root)): sha256(p) for p in paths if p.is_file()},
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version}


def run(roots, windows_path=BATCH / "evidence_windows_400.jsonl",
        metadata_path=BATCH / "candidate_metadata_400.jsonl", batch_path=BATCH / "screening_batch_ids.jsonl",
        out_dir=DEFAULT_OUT, scratch_dir=None, *, expected_sha=WINDOWS_SHA256, per_stratum=200, years=YEARS,
        dataset_roots=None):
    """Return the report; failed runs remain explicitly rejected, never certified."""
    out_dir = Path(out_dir)
    roots = [Path(r).resolve() for r in roots]
    # Fail before creating outputs if the output would overlap any read-only input root.
    out = out_dir.resolve()
    for root in roots:
        root = Path(root).resolve()
        if out == root or root in out.parents or out in root.parents:
            raise ValueError("Output and evidence roots must not overlap")
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": VERSION, "status": "rejected", "roots": [str(Path(r).resolve()) for r in roots],
              "code": code_provenance(), "semantic_support_assessed": False,
              "started_utc": datetime.now(timezone.utc).isoformat(), "archive_years": list(years),
              "per_stratum": per_stratum,
              "hash_policy": "physical bytes and exact decompressed bytes; only canonical windows normalize CRLF to LF"}
    candidates, inventory, recovered, bad = [], [], defaultdict(list), defaultdict(set)
    failures, warnings = [], []
    try:
        report["dataset_selection"] = {"mode": "recursive_evidence_roots",
                                       "selected_dataset_roots": [], "ignored_external_mounts": []}
        discovery_roots = roots
        if dataset_roots is not None:
            report["dataset_selection"]["selected_dataset_roots"] = [str(Path(p).resolve()) for p in dataset_roots]
            if not dataset_roots:
                raise ValueError("Canonical dataset selection must not be empty")
            report["dataset_selection"] = dataset_selection(roots, dataset_roots)
            discovery_roots = dataset_roots
        candidates, report["inputs"] = validate_inputs(windows_path, metadata_path, batch_path,
                                                       expected_sha=expected_sha, per_stratum=per_stratum)
        mounted = discover(discovery_roots, years=years, windows_hash=expected_sha,
                           root_scoped=dataset_roots is not None)
        intervals = retention_intervals(candidates)
        parents = {c["evidence_id"] for c in candidates}
        with (out_dir / "integrity_events.jsonl").open("x", encoding="utf-8", newline="\n") as events:
            def emit(value):
                events.write(json_bytes(value).decode("utf-8") + "\n")
            with tempfile.TemporaryDirectory(prefix="w6_r19_", dir=scratch_dir) as scratch:
                with closing(sqlite3.connect(str(Path(scratch) / "passages.sqlite"))) as db:
                    db.execute("PRAGMA cache_size=-32768")
                    db.execute("CREATE TABLE sources (year INTEGER PRIMARY KEY, path TEXT)")
                    # WITHOUT ROWID stores each long canonical ID once. Source paths are
                    # stored once per year; only 32 fingerprint bytes per passage.
                    db.execute("CREATE TABLE passages (id TEXT PRIMARY KEY, fingerprint BLOB, source INTEGER, line INTEGER) WITHOUT ROWID")
                    for year, items in mounted.items():
                        print(f"Auditing {year}: {len(items)} mounted representation(s)", flush=True)
                        representations = []
                        for i, item in enumerate(items):
                            representations.append(scan_shard(item, year, parents, db, intervals, emit, recovered, bad, primary=i == 0))
                        if len({r["decompressed_content_sha256"] for r in representations}) != 1:
                            raise ValueError(f"{year}: conflicting duplicate dataset contents")
                        record = {"year": year, "primary": representations[0], "representations": representations}
                        inventory.append(record)
                        if not any(r["original_compressed_hash_verified"] or r["content_hash_verified_against_sidecar"] for r in representations):
                            warnings.append({"type": "original_hash_unverifiable_after_decompression", "year": year})
                        if representations[0]["invalid_records"]:
                            failures.append({"type": "passage_integrity_failure", "year": year})
        report["status"] = "integrity_failed" if failures else "complete"
    except (ValueError, KeyError, TypeError, OSError, EOFError, sqlite3.Error, zlib.error) as exc:
        failures.append({"type": "audit_rejected", "message": str(exc)})
    blocked = "global_inventory_integrity_failure" if failures else None
    ledger = recovery_ledger(candidates, recovered, bad, years=years, blocked=blocked)
    write_jsonl(out_dir / "evidence_inventory.jsonl", inventory)
    write_jsonl(out_dir / "recovery_ledger.jsonl", ledger)
    write_jsonl(out_dir / "recovered_gold_passages.jsonl", (
        {**p, "qa_id": c["qa_id"], "evidence_id": c["evidence_id"], "evidence_ts": c["evidence_ts"],
         "question_ts": c["question_ts"], "semantic_support": "not_assessed"}
        for c in candidates for p in recovered.get(c["evidence_id"], [])))
    summary = {"status": report["status"], "failures": failures, "warnings": warnings,
               "candidate_count": len(ledger), "inventory_years": [r["year"] for r in inventory],
               "outcomes": dict(Counter(r["status"] for r in ledger)),
               "gold_outside_archive_ids": [r["qa_id"] for r in ledger if not r["gold_year_in_configured_range"]],
               "partial_window_ids": [r["qa_id"] for r in ledger if r["outside_configured_range"]],
               "recovery_failures": [{"qa_id": r["qa_id"], "status": r["status"], "issues": r["issues"]}
                                     for r in ledger if r["status"] != "recovered_pending_semantic_review"],
               "unresolved_ids": [r["qa_id"] for r in ledger],
               "unresolved_reason": "Semantic support has not been assessed for any candidate"}
    write_json(out_dir / "summary.json", summary)
    report["summary"] = summary
    report["original_hash_verification_complete"] = not failures and not warnings
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    report["output_sha256"] = {p.name: sha256(p) for p in sorted(out_dir.iterdir()) if p.is_file()}
    write_json(out_dir / "integrity_provenance.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, action="append", help="Repeatable recursive mount root; default /kaggle/input")
    parser.add_argument("--dataset-root", type=Path, action="append",
                        help="Exact canonical dataset root; repeat for every dataset. Restricts discovery and records excluded mounts.")
    parser.add_argument("--windows", type=Path, default=BATCH / "evidence_windows_400.jsonl")
    parser.add_argument("--metadata", type=Path, default=BATCH / "candidate_metadata_400.jsonl")
    parser.add_argument("--batch", type=Path, default=BATCH / "screening_batch_ids.jsonl")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--scratch-dir", type=Path, help="Disk for temporary exact duplicate-ID index")
    args = parser.parse_args()
    report = run(args.evidence_root or [Path("/kaggle/input")], args.windows, args.metadata,
                 args.batch, args.out_dir, args.scratch_dir, dataset_roots=args.dataset_root)
    print(json.dumps(report["summary"], indent=2))
    raise SystemExit(0 if report["status"] == "complete" else 2)


if __name__ == "__main__":
    main()
