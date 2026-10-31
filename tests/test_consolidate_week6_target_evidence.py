"""Checkpoint 2B uses tiny synthetic source records only."""
import json
import sqlite3

import pytest

from src.eval import consolidate_week6_target_evidence as consolidate
from src.eval import index_week6_target_evidence as index
from test_index_week6_target_evidence import CANDIDATES, passage, source


def imported(tmp_path, *, mode="plain", replicas=False):
    a = source(tmp_path, [passage(), passage(text="alternative")], mode=mode, name="pilot-source")
    specs = [a]
    if replicas:
        specs += [source(tmp_path, [passage(), passage(text="alternative")], name="replica", mode=mode)]
    root = tmp_path / "pilot"
    index.run_pilot(sources=specs, out_dir=root)
    return root


def year_source(tmp_path, year=2009, *, mode="gzip", bad=False, name=None):
    gold = next(c for c in CANDIDATES if c["evidence_id"].startswith(str(year)))
    when = index.datetime.fromtimestamp(gold["evidence_ts"], index.timezone.utc).replace(hour=0,minute=0,second=0)
    record = {"doc_id": gold["evidence_id"] + "_0", "text": "year evidence", "timestamp": when.isoformat()}
    p, a = source(tmp_path, [record, b"invalid\n"] if bad else [record], mode=mode, name=name or str(year))
    audit = json.loads(a.read_text())
    audit.update(year=year, archive_url=f"https://data.statmt.org/news-crawl/doc/en/news-docs.{year}.en.filtered.gz")
    target = a.parent / f"{year}.audit.json"
    a.rename(target)
    target.write_text(json.dumps(audit))
    p.rename(p.parent / p.name.replace("2008", str(year)))
    return p.parent


def candidates_inputs():
    return index.validate_inputs(index.BATCH / "evidence_windows_400.jsonl", index.BATCH / "candidate_metadata_400.jsonl", index.BATCH / "screening_batch_ids.jsonl")


def load(root, name):
    return [json.loads(line) for line in (root / name).read_text().splitlines()]


def run(tmp_path, pilot, roots, name="out"):
    return consolidate.run(import_index=pilot, dataset_roots=roots, out_dir=tmp_path / name, batch_size=1)


def test_valid_import_preserves_exact_rows_and_occurrence_ids_without_source_mount(tmp_path):
    pilot = imported(tmp_path, replicas=True)
    for directory in (tmp_path / "pilot-source", tmp_path / "replica"):
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()
    report = run(tmp_path, pilot, [year_source(tmp_path)])
    assert report["schema_version"] == consolidate.VERSION
    assert report["state"] == "incomplete"  # Unselected 2010–2020 must remain visible.
    assert report["years"]["2008"]["state"] == "complete_provisional"
    assert report["years"]["2009"]["state"] == "complete_verified"
    old = load(pilot, "occurrences.jsonl")
    new = load(tmp_path / "out", "occurrences.jsonl")
    assert all(row in new for row in old)
    with sqlite3.connect(pilot / "target_index.sqlite") as before, sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as after:
        for table, columns in (("variants", "*"), ("occurrences", "line,vid,raw_sha256,raw_line,uncompressed_offset,occurrence_id")):
            assert set(before.execute(f"SELECT {columns} FROM {table}")) <= set(after.execute(f"SELECT {columns} FROM {table}"))
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
        assert after.execute("SELECT count(*) FROM artifacts WHERE replica_of IS NOT NULL").fetchone() == (1,)


@pytest.mark.parametrize("corruption", ["manifest", "database", "export", "state", "candidate", "occurrence", "provenance", "schema", "input", "foreign_key", "variant", "raw_hash", "run"])
def test_corrupted_import_is_rejected(tmp_path, corruption):
    pilot = imported(tmp_path)
    path = pilot / "manifest.json"
    report = json.loads(path.read_text())
    if corruption == "manifest":
        path.write_text('{"state":')
    elif corruption == "database":
        (pilot / "target_index.sqlite").write_bytes(b"not a database")
        report["output_sha256"]["target_index.sqlite"] = index.sha256(pilot / "target_index.sqlite")
        path.write_text(json.dumps(report))
    elif corruption == "export":
        (pilot / "variants.jsonl").write_text("corrupted")
    elif corruption in {"state", "input"}:
        if corruption == "state":
            report["state"] = "complete_verified"
        else:
            report["inputs"]["batch_sha256"] = "0" * 64
        path.write_text(json.dumps(report))
    else:
        with sqlite3.connect(pilot / "target_index.sqlite") as db:
            if corruption == "candidate":
                db.execute("UPDATE candidates SET record_json='{}' WHERE ordinal=0")
            elif corruption == "occurrence":
                db.execute("UPDATE occurrences SET occurrence_id=NULL")
            elif corruption == "provenance":
                db.execute("UPDATE artifacts SET historical_verified=1")
            elif corruption == "foreign_key":
                db.execute("UPDATE occurrences SET vid='nonexistent'")
            elif corruption == "variant":
                db.execute("UPDATE variants SET preimage=x'00'")
            elif corruption == "raw_hash":
                db.execute("UPDATE occurrences SET raw_sha256=?", ("0" * 64,))
            elif corruption == "run":
                db.execute("UPDATE run SET state='scanning'")
            else:
                db.execute("CREATE TABLE unexpected(id)")
        report["output_sha256"]["target_index.sqlite"] = index.sha256(pilot / "target_index.sqlite")
        path.write_text(json.dumps(report))
    with pytest.raises((ValueError, KeyError, sqlite3.Error)):
        consolidate.verify_snapshot(pilot, *candidates_inputs())


def test_cross_year_provisional_and_verified_do_not_promote_each_other(tmp_path):
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, 2009), year_source(tmp_path, 2010, mode="plain")]
    report = run(tmp_path, pilot, roots)
    assert report["years"]["2008"]["state"] == report["years"]["2010"]["state"] == "complete_provisional"
    assert report["years"]["2009"]["state"] == "complete_verified"
    ledger = load(tmp_path / "out", "recovery_ledger.jsonl")
    assert len(ledger) == 400
    assert [r["qa_id"] for r in ledger] == [c["qa_id"] for c in CANDIDATES]
    for year, verified in ((2008, False), (2009, True), (2010, False)):
        row = next(r for r in ledger if r["evidence_id"].startswith(str(year)) and r["variant_count"])
        assert (row["source_validation"] == "verified") == verified
        assert row["semantic_support"] == "not_assessed"
    assert all({k:r[k] for k in c} == c for r,c in zip(ledger, CANDIDATES))


@pytest.mark.parametrize("interrupt", [False, True])
def test_failed_year_does_not_invalidate_import_or_completed_year(tmp_path, monkeypatch, interrupt):
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, 2009), year_source(tmp_path, 2010, bad=not interrupt), year_source(tmp_path, 2011)]
    original = index.parse_passage
    if interrupt:
        def parse(raw, year, intervals):
            if year == 2010:
                raise KeyboardInterrupt()
            return original(raw, year, intervals)
        monkeypatch.setattr(index, "parse_passage", parse)
    report = run(tmp_path, pilot, roots)
    assert report["state"] == "incomplete"
    assert report["years"]["2009"]["state"] == "complete_verified"
    assert report["years"]["2010"]["state"] == ("interrupted" if interrupt else "rejected")
    assert report["years"]["2011"]["state"] == ("not_scanned" if interrupt else "complete_verified")
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        assert db.execute("SELECT count(*) FROM occurrences WHERE occurrence_id IS NULL").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM artifacts WHERE year=2010").fetchone() == (0,)
    assert all(r in load(tmp_path / "out", "occurrences.jsonl") for r in load(pilot, "occurrences.jsonl"))


def test_representations_within_year_and_reproducible_exports(tmp_path):
    pilot = imported(tmp_path)
    root = tmp_path / "combined"
    root.mkdir()
    year_source(root, 2009, name="a")
    year_source(root, 2009, mode="plain", name="b")
    year_source(root, 2009, name="c")
    other = year_source(tmp_path, 2010)
    one = run(tmp_path, pilot, [root,other], "one")
    two = consolidate.run(import_index=pilot, dataset_roots=[other,root], out_dir=tmp_path / "two", batch_size=2)
    assert one["years"]["2009"]["state"] == two["years"]["2009"]["state"] == "complete_verified"
    for name in consolidate.EXPORTS:
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()
    with sqlite3.connect(tmp_path / "one" / "target_index.sqlite") as db:
        assert db.execute("SELECT count(*) FROM occurrences o JOIN artifacts a ON a.id=o.artifact WHERE a.year=2009").fetchone() == (2,)
        assert db.execute("SELECT historical_verified FROM artifacts WHERE year=2008").fetchall() == [(0,)]


def test_cross_year_windows_and_missing_coverage(tmp_path):
    pilot = imported(tmp_path)
    run(tmp_path, pilot, [year_source(tmp_path, 2009)])
    ledger = load(tmp_path / "out", "recovery_ledger.jsonl")
    assert sum(r["evidence_availability"] == "gold_outside_configured_archives" for r in ledger) == 10
    assert sum(bool(r["canonical_temporal_coverage"]["outside_archive_years"]) for r in ledger) == 40
    assert all(2021 not in r["effective_prequestion_temporal_coverage"]["requested_years"] for r in ledger)
    assert any(2009 in r["canonical_temporal_coverage"]["verified_scanned_years"] and 2010 in r["canonical_temporal_coverage"]["unscanned_configured_years"] for r in ledger)
    for row in ledger:
        coverage = row["canonical_temporal_coverage"]
        assert coverage["historically_verified_years"] == [y for y in coverage["requested_years"] if y == 2009]
        assert coverage["historical_equivalence_unverified_years"] == [y for y in coverage["requested_years"] if y == 2008]


def test_all_years_complete_and_preflight_read_only(tmp_path, monkeypatch, capsys):
    import sys
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, year) for year in range(2009,2021)]
    argv = ["index", "--import-index", str(pilot), "--out-dir", str(tmp_path / "out")]
    for root in roots:
        argv += ["--dataset-root", str(root)]
    before = {str(p):index.sha256(p) for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "argv", argv + ["--preflight", "--min-free-gib", "0.001"])
    assert consolidate.main() == 0
    assert not (tmp_path / "out").exists()
    assert before == {str(p):index.sha256(p) for p in tmp_path.rglob("*") if p.is_file()}
    monkeypatch.setattr(sys, "argv", argv)
    assert consolidate.main() == 3
    report = json.loads((tmp_path / "out" / "manifest.json").read_text())
    assert report["state"] == "complete_provisional"
    assert report["scan_years"] == list(range(2008,2021))
    for name, digest in report["output_sha256"].items():
        assert index.sha256(tmp_path / "out" / name) == digest


def test_preflight_disk_failure_and_no_payload_read(tmp_path, monkeypatch):
    import sys
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, y) for y in range(2009,2021)]
    argv = ["index", "--import-index", str(pilot), "--out-dir", str(tmp_path / "out"), "--preflight", "--min-free-gib", "999999999"]
    for root in roots:
        argv += ["--dataset-root", str(root)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        consolidate.main()
    assert not (tmp_path / "out").exists()


def test_verified_import_and_verified_all_years(tmp_path):
    pilot = imported(tmp_path, mode="gzip")
    roots = [year_source(tmp_path, year) for year in range(2009,2021)]
    report = run(tmp_path, pilot, roots)
    assert report["state"] == "complete_verified"
    assert report["identity_scope_certified"]
    assert all(s["state"] == "complete_verified" for s in report["years"].values())


def test_bad_year_sidecar_is_isolated(tmp_path):
    pilot = imported(tmp_path)
    a = year_source(tmp_path, 2009)
    b = year_source(tmp_path, 2010)
    (a / "2009.audit.json").write_text('{"year":2009,"year":2009}')
    report = run(tmp_path, pilot, [a,b])
    assert report["years"]["2009"]["state"] == "rejected"
    assert report["years"]["2010"]["state"] == "complete_verified"


def test_identical_empty_streams_across_years_are_not_replicas(tmp_path):
    pilot = imported(tmp_path)
    roots = []
    for year in (2009,2010):
        p,a = source(tmp_path, [b"\n"], name=str(year))
        audit = json.loads(a.read_text())
        audit.update(year=year, archive_url=f"https://data.statmt.org/news-crawl/doc/en/news-docs.{year}.en.filtered.gz")
        a.rename(a.parent / f"{year}.audit.json")
        (a.parent / f"{year}.audit.json").write_text(json.dumps(audit))
        p.rename(p.parent / f"{year}.jsonl")
        roots.append(p.parent)
    report = run(tmp_path, pilot, roots)
    assert all(report["years"][str(y)]["state"] == "complete_verified" for y in (2009,2010))
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        assert db.execute("SELECT count(*) FROM artifacts WHERE year>2008 AND replica_of IS NULL").fetchone() == (2,)


def test_merge_rollback_preserves_previous_years(tmp_path, monkeypatch):
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, y) for y in (2009,2010,2011)]
    original = consolidate.merge_snapshot
    def merge(db, root, year):
        original(db, root, year)
        if year == 2010:
            raise sqlite3.IntegrityError("simulated merge failure after copying rows")
    monkeypatch.setattr(consolidate, "merge_snapshot", merge)
    report = run(tmp_path, pilot, roots)
    assert report["years"]["2010"]["state"] == "rejected"
    assert report["years"]["2011"]["state"] == "complete_verified"
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        assert db.execute("SELECT DISTINCT year FROM artifacts ORDER BY year").fetchall() == [(2008,), (2009,), (2011,)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_preflight_rejects_missing_mount_and_corrupt_manifest(tmp_path, monkeypatch):
    import sys
    pilot = imported(tmp_path)
    argv = ["index", "--import-index", str(pilot), "--out-dir", str(tmp_path / "out"), "--preflight"]
    monkeypatch.setattr(sys, "argv", argv + ["--dataset-root", str(tmp_path / "missing")])
    with pytest.raises(ValueError, match="missing dataset mount"):
        consolidate.main()
    roots = [year_source(tmp_path, y) for y in range(2009,2021)]
    (pilot / "manifest.json").write_text("{}")
    for root in roots:
        argv += ["--dataset-root", str(root)]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(KeyError):
        consolidate.main()
    assert not (tmp_path / "out").exists()


def test_publication_failure_never_certifies_consolidation(tmp_path, monkeypatch):
    pilot = imported(tmp_path)
    root = year_source(tmp_path)
    original = index.os.link
    def fail(source, target):
        if target == tmp_path / "out" / "manifest.json":
            raise OSError("simulated root publication failure")
        return original(source,target)
    monkeypatch.setattr(index.os, "link", fail)
    with pytest.raises(OSError, match="root publication"):
        run(tmp_path, pilot, [root])
    assert not (tmp_path / "out" / "manifest.json").exists()


def test_unhashed_sqlite_side_files_rejected(tmp_path):
    pilot = imported(tmp_path)
    (pilot / "target_index.sqlite-wal").write_bytes(b"unpublished pages")
    with pytest.raises(ValueError, match="closed snapshot"):
        consolidate.verify_snapshot(pilot, *candidates_inputs())


def test_import_artifact_ids_are_remapped_with_foreign_keys(tmp_path):
    pilot = imported(tmp_path, replicas=True)
    with sqlite3.connect(pilot / "target_index.sqlite") as db:
        db.execute("UPDATE artifacts SET id=id+100")
        db.execute("UPDATE artifacts SET replica_of=replica_of+100 WHERE replica_of IS NOT NULL")
        db.execute("UPDATE occurrences SET artifact=artifact+100")
        db.execute("UPDATE observations SET artifact=artifact+100")
        cursor = db.execute("SELECT path,sidecar_path,sidecar_sha256,state,physical_sha256,content_sha256,compression,records,target_records,physical_lines,bytes,original_compressed_verified,historical_verified,verification_basis,replica_of FROM artifacts ORDER BY path")
        columns = [c[0] for c in cursor.description]
        artifacts = [dict(zip(columns,row)) for row in cursor]
    path = pilot / "manifest.json"
    report = json.loads(path.read_text())
    report["artifacts"] = artifacts
    report["output_sha256"]["target_index.sqlite"] = index.sha256(pilot / "target_index.sqlite")
    path.write_text(json.dumps(report))
    run(tmp_path, pilot, [year_source(tmp_path)])
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        assert db.execute("SELECT id,replica_of FROM artifacts WHERE year=2008 ORDER BY id").fetchall() == [(1,None),(2,1)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert all(r in load(tmp_path / "out", "occurrences.jsonl") for r in load(pilot, "occurrences.jsonl"))


def test_preflight_never_opens_year_payloads(tmp_path, monkeypatch):
    import sys
    from pathlib import Path
    pilot = imported(tmp_path)
    roots = [year_source(tmp_path, y) for y in range(2009,2021)]
    payloads = {p for root in roots for p in root.iterdir() if not p.name.endswith("audit.json")}
    original = Path.open
    def opened(path, *args, **kwargs):
        if path in payloads:
            raise AssertionError("preflight opened a payload")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"open",opened)
    argv = ["index", "--import-index", str(pilot), "--out-dir", str(tmp_path / "out"), "--preflight", "--min-free-gib", "0.001"]
    for root in roots:
        argv += ["--dataset-root",str(root)]
    monkeypatch.setattr(sys,"argv",argv)
    assert consolidate.main() == 0
