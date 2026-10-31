"""Tiny local 2008 pilot fixtures only: never scan the real WMT archives."""
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from src.eval import index_week6_target_evidence as index
from src.eval.audit_week6_evidence import BATCH, KEYS_MD5, PARSER, WINDOWS_SHA256
from src.eval.evidence_identity import SourceOccurrence, occurrence_id

PARSER_PATH = Path(__file__).resolve().parents[1] / "third_party/streamingqa/extraction.py"
CANDIDATES = [json.loads(line) for line in (BATCH / "candidate_metadata_400.jsonl").read_text(encoding="utf-8").splitlines()]
GOLD = next(c for c in CANDIDATES if c["evidence_id"].startswith("2008"))


def passage(**changes):
    when = datetime.fromtimestamp(GOLD["evidence_ts"], timezone.utc).replace(hour=0, minute=0, second=0)
    return {"doc_id": GOLD["evidence_id"] + "_0", "text": " Exact evidence.\n", "timestamp": when.isoformat(), **changes}


def payload(rows):
    return b"".join(r if isinstance(r, bytes) else (json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8") for r in rows)


def source(tmp_path, rows, *, name="source", mode="gzip", content_hash=False, changes=None):
    root = tmp_path / name
    root.mkdir()
    data = payload(rows)
    compressed = gzip.compress(data, mtime=0)
    # Deliberately misleading extension: magic bytes must determine compression.
    path = root / ("2008.jsonl" if mode == "gzip" else "2008.jsonl.gz")
    path.write_bytes(compressed if mode == "gzip" else data)
    audit = {"year": 2008, "status": "complete", "passages": sum(bool(line.strip()) for line in data.split(b"\n")),
             "archive_url": "https://data.statmt.org/news-crawl/doc/en/news-docs.2008.en.filtered.gz",
             "windows_sha256": WINDOWS_SHA256, "sorting_keys_md5": KEYS_MD5,
             "deepmind_extraction_sha256": hashlib.sha256(PARSER_PATH.read_bytes()).hexdigest(),
             "output_sha256": hashlib.sha256(compressed).hexdigest(), "prepend_date": False, "parser": PARSER,
             **(changes or {})}
    if content_hash:
        audit["content_sha256"] = hashlib.sha256(data).hexdigest()
    sidecar = root / "2008.audit.json"
    sidecar.write_text(json.dumps(audit), encoding="utf-8")
    return path, sidecar


def run(tmp_path, sources, **kwargs):
    return index.run_pilot(sources=sources, out_dir=tmp_path / "out", batch_size=1, **kwargs)


def rows(tmp_path, name):
    return [json.loads(line) for line in (tmp_path / "out" / name).read_text(encoding="utf-8").splitlines()]


def query(tmp_path, sql):
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        return db.execute(sql).fetchall()


def test_duplicates_conflicts_and_all_400_candidates(tmp_path):
    spec = source(tmp_path, [passage(), passage(), passage(text="Different.")])
    report = run(tmp_path, [spec])
    assert report["state"] == "complete_verified"
    assert report["target_parent_count"] == 397
    assert report["counts"] == {"candidates": 400, "aliases": 1, "variants": 2, "occurrences": 3, "observations": 3}
    alias, = rows(tmp_path, "aliases.jsonl")
    assert alias["exact_duplicate_extra_occurrences"] == 1
    assert alias["conflicting_variants"]
    assert alias["logical_occurrences"] == 3
    assert {r["text"] for r in rows(tmp_path, "variants.jsonl")} == {passage()["text"], "Different."}
    ledger = rows(tmp_path, "recovery_ledger.jsonl")
    assert [r["qa_id"] for r in ledger] == [c["qa_id"] for c in CANDIDATES]
    gold = next(r for r in ledger if r["qa_id"] == GOLD["qa_id"])
    assert gold["ambiguous"] is True
    assert gold["annotation_identity"] == "unresolved"
    assert gold["semantic_support"] == "not_assessed"
    assert gold["final_screening_eligibility"] == "not_assessed"
    assert all({k: r[k] for k in c} == c for r, c in zip(ledger, CANDIDATES))


def test_physical_lines_raw_bytes_and_finalized_ids(tmp_path):
    original = payload([passage()]).rstrip(b"\n") + b"\r\n"
    spec = source(tmp_path, [b"\n", original, payload([passage(text="e\u0301\x00🙂")]).rstrip(b"\n")])
    report = run(tmp_path, [spec])
    assert report["state"] == "complete_verified"
    occurrences = rows(tmp_path, "occurrences.jsonl")
    assert [r["physical_line"] for r in occurrences] == [2, 3]
    digest = hashlib.sha256(spec[0].read_bytes()).hexdigest()
    assert occurrences[0]["occurrence_id"] == occurrence_id(SourceOccurrence(digest, 2))
    assert occurrences[0]["raw_line_sha256"] == hashlib.sha256(original).hexdigest()
    assert occurrences[0]["uncompressed_offset"] == 1
    assert query(tmp_path, "SELECT raw_line FROM occurrences WHERE line=2")[0][0] == original


@pytest.mark.parametrize("baseline", [False, True])
def test_plain_provenance_is_provisional_without_recorded_baseline(tmp_path, baseline):
    spec = source(tmp_path, [passage()], mode="plain", content_hash=baseline)
    report = run(tmp_path, [spec])
    assert report["state"] == ("complete_verified" if baseline else "complete_provisional")
    assert report["artifacts"][0]["original_compressed_verified"] == 0
    assert report["artifacts"][0]["physical_sha256"] == report["artifacts"][0]["content_sha256"]
    gold = next(r for r in rows(tmp_path, "recovery_ledger.jsonl") if r["qa_id"] == GOLD["qa_id"])
    assert gold["identity_scope_certified"] is baseline
    assert ("provisional" in gold["source_validation"]) is not baseline


def test_gzip_plain_and_physical_replicas(tmp_path):
    a = source(tmp_path, [passage()], name="a-gzip")
    b = source(tmp_path, [passage()], name="b-plain", mode="plain")
    c = source(tmp_path, [passage()], name="c-replica")
    report = run(tmp_path, [c, b, a])
    assert report["state"] == "complete_verified"
    assert report["counts"]["occurrences"] == 2
    assert len({r["occurrence_id"] for r in rows(tmp_path, "occurrences.jsonl")}) == 2
    alias, = rows(tmp_path, "aliases.jsonl")
    assert alias["physical_occurrences"] == 2
    assert alias["logical_occurrences"] == 1
    assert alias["exact_duplicate_extra_occurrences"] == 0
    assert sum(a["replica_of"] is not None for a in report["artifacts"]) == 1
    plain = next(a for a in report["artifacts"] if a["compression"] == "plain")
    assert plain["verification_basis"] == "verified_gzip_counterpart"
    assert plain["original_compressed_verified"] == 0


@pytest.mark.parametrize("bad", [
    b'{"doc_id":"a","doc_id":"b","text":"x","timestamp":"x"}\n',
    b'{"doc_id":"a","text":"\xff","timestamp":"x"}\n',
    b'{"doc_id":"a","text":NaN,"timestamp":"x"}\n',
    {**passage(), "unexpected": "must fail"},
    {**passage(), "evidence_fields": {}},
    {**passage(), "text": 3},
    {**passage(), "text": "\ud800"},
    {"doc_id": passage()["doc_id"], "text": "missing timestamp"},
    [],
    {**passage(), "doc_id": GOLD["evidence_id"] + "_00"},
    {**passage(), "doc_id": GOLD["evidence_id"] + "_-1"},
    {**passage(), "doc_id": "20080230000000000000\x00\x01" + "a" * 64 + "\x00\x01_0"},
    {**passage(), "timestamp": "2008-02-30T00:00:00Z"},
    {**passage(), "timestamp": "2008-01-01"},
    {**passage(), "timestamp": "2008-01-01T00:00:00+01:00"},
    {**passage(), "timestamp": "2009-01-01T00:00:00Z"},
])
def test_strict_invalid_records_fail_closed(tmp_path, bad):
    # Escape surrogate fixtures as JSON rather than attempting invalid Python UTF-8 encoding.
    raw = bad if isinstance(bad, bytes) else (json.dumps(bad) + "\n").encode()
    report = run(tmp_path, [source(tmp_path, [passage(), raw])])
    assert report["state"] == "rejected"
    assert not report["identity_scope_certified"]
    assert not (tmp_path / "out" / "variants.jsonl").exists()
    assert query(tmp_path, "SELECT count(*) FROM occurrences WHERE occurrence_id IS NOT NULL") == [(0,)]
    assert len(rows(tmp_path, "recovery_ledger.jsonl")) == 400


def test_publication_day_mismatch(tmp_path):
    when = index.utc(passage()["timestamp"]) + timedelta(days=1)
    report = run(tmp_path, [source(tmp_path, [passage(timestamp=when.isoformat())])])
    assert report["state"] == "rejected"
    assert "publication_day" in report["error"]


@pytest.mark.parametrize("change", [
    {"passages": 2}, {"output_sha256": "0" * 64}, {"content_sha256": "0" * 64},
    {"status": "partial"}, {"year": 2009}, {"deepmind_extraction_sha256": "a" * 64},
    {"prepend_date": True}, {"sorting_keys_md5": "0" * 32}, {"archive_url": "https://wrong"},
])
def test_sidecar_validation(tmp_path, change):
    report = run(tmp_path, [source(tmp_path, [passage()], changes=change)])
    assert report["state"] == "rejected"
    assert not report["identity_scope_certified"]


def test_duplicate_sidecar_keys(tmp_path):
    p, a = source(tmp_path, [passage()])
    a.write_bytes(b'{"year":2008,"year":2008}')
    report = run(tmp_path, [(p, a)])
    assert report["state"] == "rejected"
    assert "duplicate JSON key" in report["error"]


def test_interrupted_scan_no_completed_or_finalized_results(tmp_path, monkeypatch):
    original = index.parse_passage
    count = 0
    def interrupt(*args):
        nonlocal count
        count += 1
        if count == 2:
            raise KeyboardInterrupt()
        return original(*args)
    monkeypatch.setattr(index, "parse_passage", interrupt)
    report = run(tmp_path, [source(tmp_path, [passage(), passage()])])
    assert report["state"] == "interrupted"
    assert report["scan_completion"] == "incomplete"
    assert query(tmp_path, "SELECT count(*) FROM occurrences WHERE occurrence_id IS NOT NULL") == [(0,)]
    assert not (tmp_path / "out" / "aliases.jsonl").exists()
    gold = next(r for r in rows(tmp_path, "recovery_ledger.jsonl") if r["qa_id"] == GOLD["qa_id"])
    assert gold["evidence_availability"] == "not_determined"


def test_missing_years_and_effective_temporal_coverage(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage()])])
    assert report["state"] == "complete_verified"
    ledger = rows(tmp_path, "recovery_ledger.jsonl")
    assert sum(r["evidence_availability"] == "gold_outside_configured_archives" for r in ledger) == 10
    other = next(r for r in ledger if r["evidence_id"].startswith("2020"))
    assert other["scan_completion"] == "not_scanned"
    assert other["evidence_availability"] == "not_determined"
    missing = next(r for r in ledger if r["evidence_id"].startswith("2008") and r["qa_id"] != GOLD["qa_id"])
    assert missing["evidence_availability"] == "absent_in_verified_2008_scope"
    assert sum(bool(r["canonical_temporal_coverage"]["outside_archive_years"]) for r in ledger) == 40
    assert all(2021 not in r["effective_prequestion_temporal_coverage"]["requested_years"] for r in ledger)


def test_missing_source_preserves_candidates(tmp_path):
    report = run(tmp_path, [])
    assert report["state"] == "rejected"
    assert len(rows(tmp_path, "recovery_ledger.jsonl")) == 400


def test_non_target_rows_validated_not_indexed(tmp_path):
    non_target = passage(doc_id=GOLD["evidence_id"].split("\x00\x01")[0] + "\x00\x01" + "f" * 64 + "\x00\x01_0")
    report = run(tmp_path, [source(tmp_path, [non_target] * 300 + [passage()])])
    assert report["state"] == "complete_verified"
    assert report["artifacts"][0]["records"] == 301
    assert report["counts"]["occurrences"] == 1


def test_temporal_boundaries_and_retention():
    r = passage()
    when = index.utc(r["timestamp"])
    index.parse_passage(payload([r]), 2008, ([when], [when]))
    with pytest.raises(ValueError, match="retention"):
        index.parse_passage(payload([r]), 2008, ([when + timedelta(microseconds=1)], [when + timedelta(days=1)]))
    # Publication after the question is a candidate-specific blocker, not identity recovery.
    candidate = {**GOLD, "question_ts": int(when.timestamp()) - 1}
    assert index._coverage(candidate, {2008}, effective=True)["end"] == datetime.fromtimestamp(candidate["question_ts"], timezone.utc).isoformat()


def test_deterministic_exports_and_source_order(tmp_path):
    a = source(tmp_path, [passage(), passage(text="é"), passage()], name="a")
    b = source(tmp_path, [passage(), passage(text="é"), passage()], name="b")
    first = index.run_pilot(sources=[a, b], out_dir=tmp_path / "one", batch_size=1)
    second = index.run_pilot(sources=[b, a], out_dir=tmp_path / "two", batch_size=2)
    assert first["state"] == second["state"] == "complete_verified"
    for name in ("aliases.jsonl", "variants.jsonl", "occurrences.jsonl", "document_observations.jsonl", "recovery_ledger.jsonl"):
        assert (tmp_path / "one" / name).read_bytes() == (tmp_path / "two" / name).read_bytes()


def test_variant_collision_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(index.identity, "variant_id", lambda _: "forced")
    report = run(tmp_path, [source(tmp_path, [passage(), passage(text="different")])])
    assert report["state"] == "rejected"
    assert "variant SHA-256 collision" in report["error"]


def test_occurrence_collision_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(index.identity, "occurrence_id", lambda _: "forced")
    report = run(tmp_path, [source(tmp_path, [passage(), passage()])])
    assert report["state"] == "rejected"
    assert "occurrence SHA-256 collision" in report["error"]


def test_supported_runs_never_synthesize_documents(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage(), passage(doc_id=GOLD["evidence_id"] + "_1"),
                                           passage(), passage(text="alternative")])])
    assert report["state"] == "complete_verified"
    observations = rows(tmp_path, "document_observations.jsonl")
    assert [o["member_count"] for o in observations] == [2, 1, 1]
    assert all(o["membership_status"] == "original_document_membership_unverified" for o in observations)
    assert query(tmp_path, "SELECT name FROM sqlite_master WHERE name='document_variants'") == []


def test_bounded_line_limit_and_no_overwrite(tmp_path):
    spec = source(tmp_path, [passage()])
    report = run(tmp_path, [spec], max_line_bytes=10)
    assert report["state"] == "rejected"
    with pytest.raises(FileExistsError):
        run(tmp_path, [spec])


def test_measurements_and_manifest_hashes(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage()])])
    metrics = json.loads((tmp_path / "out" / "measurements.json").read_text())
    assert metrics["peak_process_rss_bytes"] > 0
    assert metrics["runtime_seconds"] > 0
    assert metrics["database_bytes"] > 0
    for name, digest in report["output_sha256"].items():
        assert hashlib.sha256((tmp_path / "out" / name).read_bytes()).hexdigest() == digest


def test_known_2008_conflict_is_retained_when_targeted(tmp_path):
    fixture = json.loads((Path(__file__).parent / "fixtures" / "w6_r19_2008_identity_conflict.json").read_text(encoding="utf-8"))
    longer, shorter = fixture["records"]
    center = index.utc(longer["timestamp"]) + timedelta(hours=1)
    replacement = {**GOLD, "evidence_id": longer["doc_id"].rpartition("_")[0],
                   "evidence_ts": int(center.timestamp()),
                   "window_start": (center - timedelta(days=56)).isoformat(),
                   "window_end": (center + timedelta(days=56)).isoformat()}
    candidates = [replacement if c["qa_id"] == GOLD["qa_id"] else c for c in CANDIDATES]
    windows = tmp_path / "windows.jsonl"
    metadata = tmp_path / "metadata.jsonl"
    fields = ("qa_id", "recent_or_past", "reserve_rank", "evidence_id", "evidence_ts", "window_start", "window_end")
    windows.write_bytes(payload([{k: c[k] for k in fields} for c in candidates]))
    metadata.write_bytes(payload(candidates))
    digest = hashlib.sha256(windows.read_bytes()).hexdigest()
    spec = source(tmp_path, [longer, shorter], changes={"windows_sha256": digest})
    report = run(tmp_path, [spec], windows_path=windows, metadata_path=metadata, expected_windows_sha=digest)
    assert report["state"] == "complete_verified"
    assert report["counts"]["variants"] == 2
    assert {r["text"] for r in rows(tmp_path, "variants.jsonl")} == {longer["text"], shorter["text"]}
    assert rows(tmp_path, "aliases.jsonl")[0]["conflicting_variants"]
    # Index 5 alone cannot establish a document boundary; no inferred full document.
    assert rows(tmp_path, "document_observations.jsonl") == []


def test_same_text_different_timestamp_is_a_conflict(tmp_path):
    a = passage()
    b = passage(timestamp=a["timestamp"].replace("00:00:00", "01:00:00"))
    report = run(tmp_path, [source(tmp_path, [a, b])])
    assert report["state"] == "complete_verified"
    assert report["counts"]["variants"] == 2
    assert rows(tmp_path, "aliases.jsonl")[0]["conflicting_variants"]


def test_publication_after_question_blocks_candidate_identity_scope(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage()])])
    assert report["state"] == "complete_verified"
    candidate = {**GOLD, "question_ts": int(index.utc(passage()["timestamp"]).timestamp()) - 1}
    with sqlite3.connect(tmp_path / "out" / "target_index.sqlite") as db:
        result, = index.ledger(db, [candidate], successful=True)
    assert result["temporal_issues"] == ["publication_after_question"]
    assert not result["identity_scope_certified"]


def test_later_invalid_representation_invalidates_earlier_public_ids(tmp_path):
    a = source(tmp_path, [passage()], name="a")
    declared = json.loads(a[1].read_text())["output_sha256"]
    b = source(tmp_path, [passage(text="conflicting replica")], name="b", mode="plain", changes={"output_sha256": declared})
    report = run(tmp_path, [a, b])
    assert report["state"] == "rejected"
    assert "conflicting representations" in report["error"]
    assert query(tmp_path, "SELECT count(*) FROM occurrences WHERE occurrence_id IS NOT NULL") == [(0,)]
    assert not (tmp_path / "out" / "occurrences.jsonl").exists()


def test_dataset_discovery_and_cli(tmp_path, monkeypatch):
    import sys
    spec = source(tmp_path, [passage()])
    monkeypatch.setattr(sys, "argv", ["pilot", "--dataset-root", str(spec[0].parent), "--out-dir", str(tmp_path / "out")])
    assert index.main() == 0
    assert len(rows(tmp_path, "recovery_ledger.jsonl")) == 400


def test_cli_provisional_exit_and_discovery_failure(tmp_path, monkeypatch):
    import sys
    spec = source(tmp_path, [passage()], mode="plain")
    monkeypatch.setattr(sys, "argv", ["pilot", "--dataset-root", str(spec[0].parent), "--out-dir", str(tmp_path / "out")])
    assert index.main() == 3
    empty = tmp_path / "empty"
    empty.mkdir()
    report = index.run_pilot(dataset_root=empty, out_dir=tmp_path / "missing-out")
    assert report["state"] == "rejected"
    assert report["counts"]["candidates"] == 400


def test_duplicate_sidecar_discovery_keeps_400_failure_ledger(tmp_path):
    p, a = source(tmp_path, [passage()])
    a.write_bytes(b'{"year":2008,"year":2008}')
    report = index.run_pilot(dataset_root=p.parent, out_dir=tmp_path / "out")
    assert report["state"] == "rejected"
    assert len(rows(tmp_path, "recovery_ledger.jsonl")) == 400


def test_truncated_gzip_cannot_complete(tmp_path):
    p, a = source(tmp_path, [passage()])
    p.write_bytes(p.read_bytes()[:-5])
    report = run(tmp_path, [(p, a)])
    assert report["state"] == "rejected"
    assert report["scan_completion"] == "incomplete"


def test_document_observations_do_not_join_across_blank_lines(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage(), b"\n", passage(doc_id=GOLD["evidence_id"] + "_1")])])
    assert report["state"] == "complete_verified"
    observation, = rows(tmp_path, "document_observations.jsonl")
    assert observation["start_line"] == observation["end_line"] == 1
    assert observation["membership_status"] == "original_document_membership_unverified"


def test_output_cannot_overlap_selected_root(tmp_path):
    spec = source(tmp_path, [passage()])
    with pytest.raises(ValueError, match="overlap"):
        index.run_pilot(dataset_root=spec[0].parent, out_dir=spec[0].parent / "out")


def test_export_interruption_never_marks_database_complete(tmp_path, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt()
    monkeypatch.setattr(index, "export_index", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(tmp_path, [source(tmp_path, [passage()])])
    assert not (tmp_path / "out" / "manifest.json").exists()
    assert query(tmp_path, "SELECT state FROM run") == [("validated_manifest_required",)]


def test_manifest_publication_failure_leaves_no_completion_marker(tmp_path, monkeypatch):
    def fail_link(*args):
        raise OSError("simulated publication failure")
    monkeypatch.setattr(index.os, "link", fail_link)
    with pytest.raises(OSError, match="publication failure"):
        run(tmp_path, [source(tmp_path, [passage()])])
    assert not (tmp_path / "out" / "manifest.json").exists()
    assert (tmp_path / "out" / "manifest.json.tmp").exists()
    assert query(tmp_path, "SELECT state FROM run") == [("validated_manifest_required",)]


def test_raw_and_evidence_duplicate_classifications_are_separate(tmp_path):
    literal = payload([passage(text="é")])
    escaped = (json.dumps(passage(text="é"), ensure_ascii=True) + "\n").encode()
    report = run(tmp_path, [source(tmp_path, [literal, escaped])])
    assert report["state"] == "complete_verified"
    alias, = rows(tmp_path, "aliases.jsonl")
    assert alias["variant_count"] == 1
    assert alias["exact_duplicate_extra_occurrences"] == 1
    assert alias["raw_duplicate_extra_occurrences"] == 0


def test_representation_hash_collision_check_fails_closed(tmp_path, monkeypatch):
    a = source(tmp_path, [passage()], name="a")
    b = source(tmp_path, [passage()], name="b", mode="plain")
    monkeypatch.setattr(index, "_same_stream", lambda *args, **kwargs: False)
    report = run(tmp_path, [a, b])
    assert report["state"] == "rejected"
    assert "decompressed-stream SHA-256 collision" in report["error"]


def test_document_observations_do_not_join_different_timestamps(tmp_path):
    report = run(tmp_path, [source(tmp_path, [passage(), passage(
        doc_id=GOLD["evidence_id"] + "_1",
        timestamp=passage()["timestamp"].replace("00:00:00", "01:00:00"))])])
    assert report["state"] == "complete_verified"
    observation, = rows(tmp_path, "document_observations.jsonl")
    assert observation["member_count"] == 1
    assert observation["start_line"] == observation["end_line"] == 1
