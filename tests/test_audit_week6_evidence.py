"""Small offline fixtures: no archives, downloads, extraction or model calls."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from src.eval import audit_week6_evidence as auditor
from src.eval.audit_week6_evidence import (
    BATCH, KEYS_MD5, PARSER, WINDOWS_SHA256, discover, run, validate_inputs,
)


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj) + "\n", encoding="utf-8")


def candidate(qid, stratum, date, rank=1):
    center = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    return {"qa_id": qid, "recent_or_past": stratum, "reserve_rank": rank,
            "evidence_id": center.strftime("%Y%m%d") + "000000000000\x00\x01hash_with_underscore\x00\x01",
            "evidence_ts": int(center.timestamp()),
            "window_start": (center - timedelta(days=56)).isoformat(),
            "window_end": (center + timedelta(days=56)).isoformat(),
            "question_ts": int((center + timedelta(days=10)).timestamp()),
            "question": f"Question {qid}?", "answers": ["An answer."]}


def inputs(tmp_path, candidates):
    directory = tmp_path / "inputs"
    directory.mkdir()
    windows, metadata, batch = (directory / n for n in ("windows.jsonl", "metadata.jsonl", "batch.jsonl"))
    fields = ("qa_id", "recent_or_past", "reserve_rank", "evidence_id", "evidence_ts", "window_start", "window_end")
    w = [{k: c[k] for k in fields} for c in candidates]
    for path, rows in [(windows, w), (metadata, candidates),
                       (batch, [{k: c[k] for k in ("qa_id", "recent_or_past", "reserve_rank")} for c in candidates])]:
        path.write_bytes(b"".join((json.dumps(r) + "\n").encode() for r in rows))
    return windows, metadata, batch, hashlib.sha256(windows.read_bytes()).hexdigest()


def passage(c, suffix=0, **extra):
    day = datetime.fromtimestamp(c["evidence_ts"], timezone.utc).replace(hour=0)
    return {"doc_id": c["evidence_id"] + f"_{suffix}", "text": "An answer.", "timestamp": day.isoformat(), **extra}


def shard(directory, year, rows, windows_hash, *, mode="gzip", changes=None, content_hash=False):
    directory.mkdir(parents=True, exist_ok=True)
    data = b"".join((json.dumps(r) + "\n").encode() for r in rows)
    compressed = gzip.compress(data, mtime=0)
    if mode in ("nested", "nested-gzip"):
        path = directory / f"{year}.jsonl" / f".{year}.attempt1.jsonl.gz.tmp"
    else:
        path = directory / (f"{year}.jsonl.gz" if mode == "gzip" else f"{year}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(compressed if mode in ("gzip", "nested-gzip") else data)
    audit = {"year": year, "status": "complete", "passages": len(rows),
             "archive_url": f"https://data.statmt.org/news-crawl/doc/en/news-docs.{year}.en.filtered.gz",
             "windows_sha256": windows_hash, "sorting_keys_md5": KEYS_MD5,
             "deepmind_extraction_sha256": "a" * 64,
             "output_sha256": hashlib.sha256(compressed).hexdigest(),
             "prepend_date": False, "parser": PARSER, "attempt": 1}
    if content_hash:
        audit["content_sha256"] = hashlib.sha256(data).hexdigest()
    audit.update(changes or {})
    dump(directory / f"{year}.audit.json", audit)
    return path


def fixture(tmp_path, *, mode="gzip", duplicate=None, changes=None, years=(2019, 2020)):
    cs = [candidate("recent", "recent", "2020-12-20"), candidate("past", "past", "2019-12-20")]
    w, m, b, digest = inputs(tmp_path, cs)
    root = tmp_path / "mounts"
    for year, c in zip((2020, 2019), cs):
        rows = [passage(c)]
        if duplicate and year == 2019:
            rows.append(passage(c, text="Conflicting answer" if duplicate == "conflict" else "An answer."))
        shard(root / f"private-dataset-{year}" / "arbitrary-subdir", year, rows, digest,
              mode=mode, changes=changes if year == 2019 else None)
    return cs, root, dict(windows_path=w, metadata_path=m, batch_path=b,
                          out_dir=tmp_path / "outputs", expected_sha=digest, per_stratum=1, years=years)


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_explicit_kaggle_selection_all_13_years(tmp_path):
    cs = [candidate("recent", "recent", "2020-06-20"), candidate("past", "past", "2015-06-20")]
    w, m, b, digest = inputs(tmp_path, cs)
    root = tmp_path / "kaggle/input"
    owner = root / "datasets/maariyahanjum"
    selected = []
    for year in range(2008, 2021):
        suffix = "canonical-v1" if year == 2020 else "v1"
        dataset = owner / f"chronoguard-week6-screening400-{year}-{suffix}"
        selected.append(dataset)
        rows = [passage(c) for c in cs if str(c["evidence_id"]).startswith(str(year))]
        shard(dataset, year, rows, digest, mode="nested-gzip" if not rows else "nested")
        if year == 2015:
            nested = dataset / "week6_2015_backup"
            nested.mkdir()
            (dataset / "2015.audit.json").rename(nested / "2015.audit.json")
    obsolete = owner / "chronoguard-week6-wmt-backup"
    empty = obsolete / "2009.jsonl/.2009.attempt1.jsonl.gz.tmp"
    empty.parent.mkdir(parents=True)
    empty.touch()
    report = run([root], w, m, b, tmp_path / "out", expected_sha=digest,
                 per_stratum=1, dataset_roots=selected)
    assert report["status"] == "complete"
    selection = report["dataset_selection"]
    assert selection["selected_dataset_roots"] == [str(p.resolve()) for p in selected]
    assert selection["ignored_external_mounts"] == [
        {"path": str(obsolete.resolve()), "reason": "outside_explicit_selection"}]
    manifest = json.loads((tmp_path / "out/integrity_provenance.json").read_text())
    assert manifest["dataset_selection"] == selection
    assert len(read(tmp_path / "out/evidence_inventory.jsonl")) == 13
    assert all(row["status"] == "recovered_pending_semantic_review"
               for row in read(tmp_path / "out/recovery_ledger.jsonl"))


@pytest.mark.parametrize("failure", ["empty", "missing_sidecar", "conflict", "metadata", "ambiguous"])
def test_selected_dataset_rejections(tmp_path, failure):
    cs, root, kw = fixture(tmp_path, mode="nested")
    selected = sorted(root.iterdir())
    dataset = root / "private-dataset-2019"
    payload = next(dataset.rglob("*.tmp"))
    audit = next(dataset.rglob("*.audit.json"))
    if failure == "empty":
        payload.write_bytes(b"")
    elif failure == "missing_sidecar":
        audit.unlink()
    elif failure == "metadata":
        record = json.loads(audit.read_text())
        record["deepmind_extraction_sha256"] = "b" * 64
        dump(audit, record)
    elif failure == "conflict":
        shard(dataset / "other", 2019, [passage(cs[1], text="Changed")], kw["expected_sha"])
    else:
        record = json.loads(audit.read_text())
        audit.unlink()
        dump(dataset / "a/2019.audit.json", record)
        dump(dataset / "b/2019.audit.json", record)
    report = run([root], dataset_roots=selected, **kw)
    assert report["status"] == "rejected"
    expected = {"empty": "zero-byte evidence", "missing_sidecar": "Missing extraction audit",
                "conflict": "conflicting duplicate dataset versions",
                "metadata": "incompatible extraction configurations", "ambiguous": "ambiguous dataset sidecars"}
    assert expected[failure] in report["summary"]["failures"][0]["message"]


@pytest.mark.parametrize("mode", ["gzip", "plain", "nested", "nested-gzip"])
def test_discovery_and_recovery_formats(tmp_path, mode):
    cs, root, kw = fixture(tmp_path, mode=mode)
    report = run([root], **kw)
    assert report["status"] == "complete"
    inventory = read(kw["out_dir"] / "evidence_inventory.jsonl")
    assert [r["year"] for r in inventory] == [2019, 2020]
    assert all(r["primary"]["original_compressed_hash_verified"] == (mode in ("gzip", "nested-gzip")) for r in inventory)
    assert len(report["summary"]["warnings"]) == (0 if mode in ("gzip", "nested-gzip") else 2)
    ledger = read(kw["out_dir"] / "recovery_ledger.jsonl")
    assert [r["qa_id"] for r in ledger] == [r["qa_id"] for r in cs]
    assert all(r["status"] == "recovered_pending_semantic_review" for r in ledger)
    assert all(r["semantic_support"] == "not_assessed" for r in ledger)
    gold = read(kw["out_dir"] / "recovered_gold_passages.jsonl")
    assert gold[0]["doc_id"] == passage(cs[0])["doc_id"]
    assert gold[0]["evidence_ts"] == cs[0]["evidence_ts"]
    assert gold[0]["source"]["line"] == 1


def test_cross_year_recovery_and_partial_2021(tmp_path):
    _, root, kw = fixture(tmp_path)
    run([root], **kw)
    ledger = read(kw["out_dir"] / "recovery_ledger.jsonl")
    past = ledger[1]
    assert past["requested_years"] == [2019, 2020]
    assert past["sources"][0]["archive_year"] == 2019
    recent = ledger[0]
    assert recent["outside_configured_range"] == [2021]
    assert recent["gold_year_in_configured_range"]
    assert recent["status"] == "recovered_pending_semantic_review"


def test_missing_2007_and_missing_in_archive_never_dropped(tmp_path):
    cs = [candidate("recent", "recent", "2020-04-01"), candidate("old", "past", "2007-12-20")]
    w, m, b, digest = inputs(tmp_path, cs)
    root = tmp_path / "mounts"
    shard(root, 2020, [], digest)
    report = run([root], w, m, b, tmp_path / "out", expected_sha=digest, per_stratum=1, years=(2020,))
    ledger = read(tmp_path / "out/recovery_ledger.jsonl")
    assert [r["status"] for r in ledger] == ["missing_gold_in_archive", "gold_outside_archive"]
    assert report["summary"]["gold_outside_archive_ids"] == ["old"]
    assert ledger[1]["outside_configured_range"] == [2007, 2008]


@pytest.mark.parametrize("kind", ["identical", "conflict"])
def test_duplicate_ids_fail_integrity(tmp_path, kind):
    _, root, kw = fixture(tmp_path, duplicate=kind)
    report = run([root], **kw)
    assert report["status"] == "integrity_failed"
    inv = read(kw["out_dir"] / "evidence_inventory.jsonl")[0]["primary"]
    assert inv["duplicate_records"] == 1
    assert inv["conflicting_records"] == int(kind == "conflict")
    issue = "conflicting_passage_id" if kind == "conflict" else "duplicate_passage_id"
    diagnostic = inv["integrity_diagnostics"]["first_failure_by_predicate"][issue]
    assert diagnostic["expected"] == {"previous_occurrences": 0}
    assert diagnostic["observed"]["canonical_json_equal"] == (kind == "identical")
    assert diagnostic["observed"]["first_source"]["line"] == 1
    assert diagnostic["source"]["line"] == 2
    ledger = read(kw["out_dir"] / "recovery_ledger.jsonl")
    assert len(ledger) == 2
    assert ledger[1]["passage_count"] == 2  # Preserve both original occurrences.
    assert all(r["status"] == "inventory_rejected" for r in ledger)


def test_cli_integrity_failure_persists_diagnostics_before_exit(tmp_path, monkeypatch, capsys):
    """Exercise the real writer and CLI exit using only tiny synthetic shards."""
    _, root, kw = fixture(tmp_path, duplicate="conflict")
    real_run = auditor.run
    monkeypatch.setattr(auditor, "run", lambda *args, **kwargs: real_run([root], **kw))
    monkeypatch.setattr("sys.argv", ["audit_week6_evidence"])
    with pytest.raises(SystemExit) as exit_info:
        auditor.main()
    assert exit_info.value.code == 2
    capsys.readouterr()  # All assertions below use files, independent of stdout.

    out = kw["out_dir"]
    inventory = read(out / "evidence_inventory.jsonl")
    assert [row["year"] for row in inventory] == [2019, 2020]
    diagnostics = inventory[0]["primary"]["integrity_diagnostics"]
    assert diagnostics["failed_predicate_counts"] == {"conflicting_passage_id": 1}
    assert list(diagnostics["first_failure_by_predicate"]) == ["conflicting_passage_id"]
    example = diagnostics["first_failure_by_predicate"]["conflicting_passage_id"]
    assert example["source"]["line"] == 2
    assert example["observed"]["first_source"]["line"] == 1
    assert example["observed"]["canonical_json_equal"] is False
    summary = json.loads((out / "summary.json").read_text())
    assert summary["status"] == "integrity_failed"
    assert summary["failures"] == [{"type": "passage_integrity_failure", "year": 2019,
                                    "failed_predicate_counts": {"conflicting_passage_id": 1}}]
    assert all(row["status"] == "inventory_rejected" for row in read(out / "recovery_ledger.jsonl"))
    provenance = json.loads((out / "integrity_provenance.json").read_text())
    assert provenance["status"] == "integrity_failed"
    assert provenance["original_hash_verification_complete"] is False
    for name, digest in provenance["output_sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest


def test_equivalent_compressed_and_decompressed_replicas(tmp_path):
    cs, root, kw = fixture(tmp_path)
    shard(root / "replica", 2019, [passage(cs[1])], kw["expected_sha"], mode="nested")
    report = run([root, root / "replica"], **kw)  # Overlapping discovery roots are deduplicated.
    assert report["status"] == "complete"
    inv = read(kw["out_dir"] / "evidence_inventory.jsonl")[0]
    assert len(inv["representations"]) == 2
    assert inv["primary"]["duplicate_records"] == 0
    assert len(read(kw["out_dir"] / "recovered_gold_passages.jsonl")) == 2


def test_conflicting_dataset_versions_rejected_preflight(tmp_path):
    cs, root, kw = fixture(tmp_path)
    shard(root / "other-version", 2019, [passage(cs[1], text="Changed")], kw["expected_sha"])
    report = run([root], **kw)
    assert report["status"] == "rejected"
    assert "conflicting duplicate dataset versions" in report["summary"]["failures"][0]["message"]
    assert len(read(kw["out_dir"] / "recovery_ledger.jsonl")) == 2


def test_forged_decompressed_replica_rejected(tmp_path):
    cs, root, kw = fixture(tmp_path)
    p = shard(root / "replica", 2019, [passage(cs[1])], kw["expected_sha"], mode="plain")
    p.write_text(json.dumps(passage(cs[1], text="Tampered")) + "\n")
    report = run([root], **kw)
    assert report["status"] == "rejected"
    assert "conflicting duplicate dataset contents" in report["summary"]["failures"][0]["message"]


@pytest.mark.parametrize("changes", [
    {"prepend_date": True}, {"windows_sha256": "b" * 64}, {"status": "partial"},
    {"sorting_keys_md5": "b" * 32}, {"deepmind_extraction_sha256": "b" * 64},
    {"extraction_config": {"different": True}},
])
def test_incompatible_audits_rejected(tmp_path, changes):
    _, root, kw = fixture(tmp_path, changes=changes)
    assert run([root], **kw)["status"] == "rejected"


def test_missing_year_rejected(tmp_path):
    _, root, kw = fixture(tmp_path, years=(2018, 2019, 2020))
    report = run([root], **kw)
    assert "2018" in report["summary"]["failures"][0]["message"]


def test_content_hash_verifies_plain_mount(tmp_path):
    cs, root, kw = fixture(tmp_path, mode="plain")
    shard(root / "private-dataset-2019/arbitrary-subdir", 2019, [passage(cs[1])], kw["expected_sha"],
          mode="plain", content_hash=True)
    report = run([root], **kw)
    assert report["summary"]["warnings"] == [{"type": "original_hash_unverifiable_after_decompression", "year": 2020}]


def test_crlf_canonical_validation_does_not_write(tmp_path):
    _, _, kw = fixture(tmp_path)
    p = kw["windows_path"]
    data = p.read_bytes().replace(b"\n", b"\r\n")
    p.write_bytes(data)
    _, provenance = validate_inputs(p, kw["metadata_path"], kw["batch_path"],
                                    expected_sha=kw["expected_sha"], per_stratum=1)
    assert provenance["crlf_count"] == 2
    assert p.read_bytes() == data


@pytest.mark.parametrize("field,value", [("reserve_rank", 2), ("evidence_ts", 0),
    ("evidence_id", "wrong"), ("window_start", "2000-01-01T00:00:00+00:00"),
    ("recent_or_past", "past"), ("question_ts", 0)])
def test_metadata_mismatch_rejected(tmp_path, field, value):
    _, _, kw = fixture(tmp_path)
    rows = read(kw["metadata_path"])
    rows[0][field] = value
    kw["metadata_path"].write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError):
        validate_inputs(kw["windows_path"], kw["metadata_path"], kw["batch_path"],
                        expected_sha=kw["expected_sha"], per_stratum=1)


def test_timestamp_inconsistency_is_reported(tmp_path):
    cs, root, kw = fixture(tmp_path)
    shard(root / "private-dataset-2019/arbitrary-subdir", 2019,
          [passage(cs[1], timestamp="2019-12-21T00:00:00+00:00")], kw["expected_sha"])
    report = run([root], **kw)
    assert report["status"] == "integrity_failed"
    assert read(kw["out_dir"] / "recovery_ledger.jsonl")[1]["issues"] == [
        "evidence_day_mismatch", "global_inventory_integrity_failure", "passage_id_publication_day_mismatch"]


def test_canonical_repository_inputs():
    cs, provenance = validate_inputs(BATCH / "evidence_windows_400.jsonl",
        BATCH / "candidate_metadata_400.jsonl", BATCH / "screening_batch_ids.jsonl")
    assert len(cs) == 400
    assert sum(c["evidence_id"].startswith("2007") for c in cs) == 10
    assert provenance["windows_lf_sha256"] == WINDOWS_SHA256


def test_no_overwrite_and_no_input_mutation(tmp_path):
    _, root, kw = fixture(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    run([root], **kw)
    with pytest.raises(FileExistsError):
        run([root], **kw)
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("changes,message", [({"passages": 2}, "passage count"),
    ({"output_sha256": "b" * 64}, "compressed-byte checksum"),
    ({"content_sha256": "b" * 64}, "decompressed-content checksum")])
def test_bad_payload_hash_and_count_rejected(tmp_path, changes, message):
    _, root, kw = fixture(tmp_path, changes=changes)
    report = run([root], **kw)
    assert message in report["summary"]["failures"][0]["message"]


def test_full_400_ledger_over_13_synthetic_shards(tmp_path):
    """Real canonical metadata, synthetic evidence only; no real corpus scanning."""
    cs = read(BATCH / "candidate_metadata_400.jsonl")
    root = tmp_path / "mounts"
    for year in range(2008, 2021):
        parents = {c["evidence_id"]: c for c in cs if c["evidence_id"].startswith(str(year))}
        shard(root / f"dataset-{year}", year, [passage(c) for c in parents.values()], WINDOWS_SHA256)
    report = run([root], out_dir=tmp_path / "outputs")
    assert report["status"] == "complete"
    assert report["original_hash_verification_complete"]
    ledger = read(tmp_path / "outputs/recovery_ledger.jsonl")
    assert len(ledger) == len({r["qa_id"] for r in ledger}) == 400
    assert len(read(tmp_path / "outputs/evidence_inventory.jsonl")) == 13
    assert sum(r["status"] == "gold_outside_archive" for r in ledger) == 10
    assert sum(2007 in r["outside_configured_range"] for r in ledger) == 11
    assert sum(2021 in r["outside_configured_range"] for r in ledger) == 29
    assert sum(r["status"] == "recovered_pending_semantic_review" for r in ledger) == 390
    provenance = json.loads((tmp_path / "outputs/integrity_provenance.json").read_text())
    for name, digest in provenance["output_sha256"].items():
        assert hashlib.sha256((tmp_path / "outputs" / name).read_bytes()).hexdigest() == digest


def test_non_gold_duplicates_are_audited(tmp_path):
    _, root, kw = fixture(tmp_path)
    unrelated = candidate("unrelated", "past", "2019-12-21")
    shard(root / "private-dataset-2019/arbitrary-subdir", 2019,
          [passage(unrelated), passage(unrelated)], kw["expected_sha"])
    report = run([root], **kw)
    assert report["status"] == "integrity_failed"
    assert read(kw["out_dir"] / "evidence_inventory.jsonl")[0]["primary"]["duplicate_records"] == 1


def test_corrupt_gzip_produces_rejected_report_and_complete_ledger(tmp_path):
    _, root, kw = fixture(tmp_path)
    p = next(root.rglob("2019.jsonl.gz"))
    p.write_bytes(p.read_bytes()[:-8])
    report = run([root], **kw)
    assert report["status"] == "rejected"
    assert len(read(kw["out_dir"] / "recovery_ledger.jsonl")) == 2


def test_outside_union_is_integrity_failure(tmp_path):
    cs, root, kw = fixture(tmp_path)
    shard(root / "private-dataset-2019/arbitrary-subdir", 2019,
          [passage(cs[1], timestamp="2019-01-01T00:00:00+00:00")], kw["expected_sha"])
    report = run([root], **kw)
    assert report["status"] == "integrity_failed"
    assert "outside_candidate_window" in read(kw["out_dir"] / "recovery_ledger.jsonl")[1]["issues"]


def test_orphan_shard_is_rejected(tmp_path):
    cs, root, kw = fixture(tmp_path)
    orphan = root / "orphan/2019.jsonl"
    dump(orphan, passage(cs[1]))
    with pytest.raises(ValueError, match="without associated sidecar"):
        discover([root], years=kw["years"], windows_hash=kw["expected_sha"])


@pytest.mark.parametrize("mode", ["gzip", "nested"])
def test_failed_predicates_have_expected_observed_values(tmp_path, mode):
    cs, root, kw = fixture(tmp_path, mode=mode)
    shard(root / "private-dataset-2019/arbitrary-subdir", 2019,
          [passage(cs[1], timestamp="2018-01-01T00:00:00+00:00")],
          kw["expected_sha"], mode=mode)
    report = run([root], **kw)
    assert report["status"] == "integrity_failed"
    inv = read(kw["out_dir"] / "evidence_inventory.jsonl")[0]["primary"]
    diagnostics = inv["integrity_diagnostics"]
    expected = {"archive_year_mismatch", "passage_id_publication_day_mismatch", "outside_retention_union"}
    assert diagnostics["failed_predicate_counts"] == dict.fromkeys(expected, 1)
    for issue in expected:
        example = diagnostics["first_failure_by_predicate"][issue]
        assert example["predicate"] and example["expected"] and example["observed"]
        assert example["source"]["line"] == 1
    event = read(kw["out_dir"] / "integrity_events.jsonl")[0]
    assert {d["issue"] for d in event["failed_predicates"]} == expected
    assert report["summary"]["failures"][0]["failed_predicate_counts"] == dict.fromkeys(expected, 1)
    assert diagnostics["compressed_hash"]["evaluated"] == (mode == "gzip")
    assert all(r["status"] == "inventory_rejected" for r in read(kw["out_dir"] / "recovery_ledger.jsonl"))
