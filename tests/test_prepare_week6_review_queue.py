"""Closed synthetic snapshots only; no archive mounts or semantic judgments."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pytest

from src.eval import prepare_week6_review_queue as queue
from test_index_week6_target_evidence import CANDIDATES, source


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    base = tmp_path_factory.mktemp("review-snapshot")
    roots = []
    for year in range(2008, 2021):
        records = {c["evidence_id"]: {"doc_id": c["evidence_id"] + "_0", "text": "No lexical answer judgment.",
                   "timestamp": datetime.fromtimestamp(c["evidence_ts"], timezone.utc).replace(hour=0, minute=0, second=0).isoformat()}
                   for c in CANDIDATES if c["evidence_id"].startswith(str(year))}
        passages = list(records.values())
        passages.append({**passages[0], "text": "Another rendering; no preferred variant."})
        payload, sidecar = source(base, passages, name=f"source-{year}", mode="plain")
        audit = json.loads(sidecar.read_text())
        audit.update(year=year, archive_url=f"https://data.statmt.org/news-crawl/doc/en/news-docs.{year}.en.filtered.gz")
        sidecar.rename(sidecar.parent / f"{year}.audit.json")
        (sidecar.parent / f"{year}.audit.json").write_text(json.dumps(audit))
        if year == 2008:
            imported = base / "import"
            queue.pilot.run_pilot(dataset_root=payload.parent, out_dir=imported)
        else:
            payload.rename(payload.parent / payload.name.replace("2008", str(year)))
            roots.append(payload.parent)
    root = base / "consolidated"
    report = queue.checkpoint.run(dataset_roots=roots, import_index=imported, out_dir=root)
    assert report["state"] == "complete_provisional", report["years"]
    return root


def run(root, out):
    return queue.run(manifest_path=root / "manifest.json", out_dir=out,
                     windows=queue.pilot.BATCH / "evidence_windows_400.jsonl",
                     metadata=queue.pilot.BATCH / "candidate_metadata_400.jsonl",
                     batch=queue.pilot.BATCH / "screening_batch_ids.jsonl")


def test_order_exclusions_ambiguity_and_reproducibility(snapshot, tmp_path):
    before = {p.name: queue.pilot.sha256(p) for p in snapshot.iterdir() if p.is_file()}
    summary = run(snapshot, tmp_path / "one")
    run(snapshot, tmp_path / "two")
    assert all(p.read_bytes() == (tmp_path / "two" / p.name).read_bytes() for p in (tmp_path / "one").iterdir())
    assert before == {p.name: queue.pilot.sha256(p) for p in snapshot.iterdir() if p.is_file()}
    review = queue.rows(tmp_path / "one/review_queue.jsonl")
    audit = queue.rows(tmp_path / "one/screening_audit.jsonl")
    assert len(review) == 390 and len(audit) == 400
    for stratum, count in (("recent", 200), ("past", 190)):
        selected = [r for r in review if r["recent_or_past"] == stratum]
        expected = [r for r in CANDIDATES if r["recent_or_past"] == stratum and not r["evidence_id"].startswith("2007")]
        assert [r["reserve_rank"] for r in selected] == [r["reserve_rank"] for r in expected]
        assert [r["queue_status"] for r in selected] == ["provisional_priority"] * 150 + ["reserve"] * (count - 150)
    excluded = [r for r in audit if r["ineligibility_reason"]]
    assert len(excluded) == 10
    assert {r["ineligibility_reason"] for r in excluded} == {"gold_outside_configured_archives"}
    assert any(r["ambiguous"] and len(r["evidence_variants"]) > 1 for r in review)
    assert all(r["preferred_variant_id"] is None and r["semantic_support"] == "not_assessed" for r in audit)
    assert summary["counts_by_stratum_and_status"]["past"]["ineligible_configured_source_scope"] == 10


@pytest.mark.parametrize("corruption", ["checksum", "state", "rank", "duplicate", "variant", "schema", "input"])
def test_corrupt_inputs_rejected(snapshot, tmp_path, corruption):
    root = tmp_path / "bad"
    shutil.copytree(snapshot, root)
    manifest = json.loads((root / "manifest.json").read_text())
    if corruption == "state":
        manifest["state"] = "incomplete"
    elif corruption == "input":
        manifest["inputs"]["metadata_sha256"] = "0" * 64
    elif corruption in {"rank", "duplicate"}:
        ledger = queue.rows(root / "recovery_ledger.jsonl")
        if corruption == "rank":
            ledger[0]["reserve_rank"] += 1
        else:
            ledger[1] = ledger[0]
        (root / "recovery_ledger.jsonl").unlink()
        queue.pilot._write_rows(root / "recovery_ledger.jsonl", ledger)
        manifest["output_sha256"]["recovery_ledger.jsonl"] = queue.pilot.sha256(root / "recovery_ledger.jsonl")
    elif corruption == "schema":
        import sqlite3
        with sqlite3.connect(root / "target_index.sqlite") as db:
            db.execute("CREATE TABLE unexpected(x)")
        manifest["output_sha256"]["target_index.sqlite"] = queue.pilot.sha256(root / "target_index.sqlite")
    else:
        (root / "variants.jsonl").write_text("" if corruption == "variant" else "corrupt")
        if corruption == "variant":
            manifest["output_sha256"]["variants.jsonl"] = queue.pilot.sha256(root / "variants.jsonl")
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        run(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_missing_evidence_fails_closed(snapshot):
    ledger = queue.rows(snapshot / "recovery_ledger.jsonl")
    with pytest.raises(ValueError, match="missing evidence"):
        queue.build(ledger, [], [], [], {})
