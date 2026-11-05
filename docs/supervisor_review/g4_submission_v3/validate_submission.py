"""Local read-only verification; Git writes only to an isolated OS-temp repository.

No project index/staging, commits, network, models, judging or estimation.
The sole project write is publication_validation.json with --record, then sha256.json
with --record. Re-running without --record only verifies and prints evidence.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
PREFIX = PACKAGE.relative_to(ROOT).as_posix() + "/"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def project_git(*args):
    return subprocess.check_output(["git", "-c", "safe.directory=" + ROOT.as_posix(), "-C", str(ROOT), *args])


def verify():
    snapshot = read(PACKAGE / "source_inventory.json")
    assert project_git("rev-parse", "HEAD").decode().strip() == snapshot["git_head"]
    assert project_git("branch", "--show-current").decode().strip() == "master"
    assert not project_git("diff", "--name-only").strip()
    assert not project_git("diff", "--cached", "--name-only").strip()
    project_git("diff", "--check")
    actual = project_git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    baseline = snapshot["baseline_files"]
    assert {p for p in actual if not p.startswith(PREFIX)} == set(baseline), "unexpected baseline paths"
    for name, entry in baseline.items(): assert sha(ROOT / name) == entry["sha256"], name
    assert hashlib.sha256(json.dumps({p: r["sha256"] for p, r in baseline.items()}, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest() == snapshot["baseline_path_hash_map_sha256"]
    allowed_rows = list(csv.DictReader((PACKAGE / "publication_allowlist.csv").open(encoding="utf-8", newline="")))
    assert len({r["path"] for r in allowed_rows}) == len(allowed_rows) == 228
    assert {r["path"] for r in allowed_rows} == set(actual), "allowlist must enumerate every existing/new path"
    selected = [r["path"] for r in allowed_rows if r["proposed_publication"] == "YES_PROPOSED"]
    denied = [r for r in allowed_rows if r["proposed_publication"] != "YES_PROPOSED"]
    assert len(selected) == 199 and len(denied) == 29
    assert sum(r["classification"] == "EXTERNAL_RESTRICTED_ARTIFACT" for r in denied) == 25
    assert sum(r["classification"] == "UNRELATED_EXCLUDED" for r in denied) == 1
    assert [r["path"] for r in denied if r["proposed_publication"] == "HOLD_DATA_MEMBERSHIP_REVIEW"] == [
        "audits/g2_i6_v1/inventory_reconciliation.json"]
    for r in allowed_rows:
        if r["origin"] == "G4_B_BASELINE": assert r["source_sha256"] == baseline[r["path"]]["sha256"]
        else: assert r["origin"] == "NEW_G4_B_V3" and r["source_sha256"] == "SEE_G4_SHA256_MANIFEST"
    audit_rows = [r for r in allowed_rows if r["classification"] == "PUBLICATION_CANDIDATE_AUDIT" and r["origin"] == "G4_B_BASELINE"]
    assert len(audit_rows) == 99
    # Parse every audit file independently and check the recorded per-path review.
    for r in audit_rows:
        path = ROOT / r["path"]
        if path.suffix == ".jsonl": values = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
        elif path.suffix == ".json": values = [read(path)]
        else:
            assert path.suffix == ".md"
            values = [path.read_text(encoding="utf-8")]
        assert values and r["content_review"] == "STATIC_CONTENT_REVIEW_ENGINEERING_ONLY"
    # Reuse only pinned, already reviewed integrity definitions; never builders/runners.
    verify_script = ROOT / "scripts/build_g2_i7_audit.py"
    assert sha(verify_script) == "cb2205d4380c130354fc6440f9f7e9e603f46c7e1ba2cbf9e2e012675d278a84"
    old = runpy.run_path(str(verify_script))
    integrity = old["prerequisites"]()
    last = ROOT / "audits/g2_i7_v1"
    assert sha(last / "sha256.json") == "97f94a6cf52c5c7b1550d31072655ea1c401ab65d8d6c7c8fcc5773135604905"
    for p, h in read(last / "sha256.json").items(): assert sha(last / p) == h
    for p, h in read(last / "source_inventory.json").items(): assert sha(ROOT / p) == h
    # Originals are exact researcher-designated source files; source identity is not approval.
    assert set(snapshot["authoritative_documents"].values()) == {"PRESENT_RESEARCHER_DESIGNATED_ORIGINAL"}
    receipts = read(PACKAGE / "authenticity_record.json")
    receipt = receipts["documents"]["original_review_package"]
    correction = receipts["documents"]["november_3_corrections"]
    assert receipt["source_sha256"] == "aa668a652407cf72619cf91753268cf8887beff02ea353f4bb344823f29ff063"
    assert correction["source_sha256"] == "4568d459f4f4b2a2525293fe4410afc7bb26b4300420e50aafe3a2698c5ee076"
    for source in (receipt, correction):
        destination = ROOT / source["destination"]
        assert sha(destination) == source["source_sha256"] == source["destination_sha256"]
        assert destination.stat().st_size == source["byte_length"] and source["exact_byte_equality"]
        linked = Path(source["source_link"])
        if linked.exists(): assert linked.read_bytes() == destination.read_bytes(), "source bytes changed"
    assert correction["format"].startswith("Office Open XML")
    ns = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(ROOT / correction["destination"]) as archive:
        assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" in archive.read("[Content_Types].xml").decode()
        body = ET.fromstring(archive.read("word/document.xml"))
        paragraphs = ["".join(n.text or "" for n in e.findall(".//w:t", ns)) for e in body.findall(".//w:body//w:p", ns)]
    assert len(paragraphs) == correction["body_paragraphs"] == 48
    for name, pin in (("g4_submission_v1", "983b2604143f26eff2ea53022fa6065fea331293b3b7fa20bc6404886325d49f"),
                      ("g4_submission_v2", "8b65608e10e166b4fb955662201257c37e8c8b413c36b35acea1fb185ec5c0a3")):
        prior = ROOT / "docs/supervisor_review" / name
        assert sha(prior / "sha256.json") == pin
        for child, h in read(prior / "sha256.json").items(): assert sha(prior / child) == h
    assert sorted(r["path"] for r in denied if r["proposed_publication"] == "HOLD_AUTHORITATIVE_SOURCE_REVIEW") == sorted([receipt["destination"], correction["destination"]])
    decisions_path = ROOT / "docs/supervisor_review/p0_a5/judge_approval_decision_sheet.md"
    original_rows = [l for l in decisions_path.read_text().splitlines() if re.match(r"\| D\d\d \|", l)]
    copied_rows = [l for l in (PACKAGE / "supervisor_decision_request.md").read_text().splitlines() if re.match(r"\| D\d\d \|", l)]
    assert len(original_rows) == 14 and original_rows == copied_rows
    assert all("UNRECORDED" in l and l.endswith("| | | |") for l in copied_rows)
    # Local Markdown links only; missing authentic sources are plain text, never fake links.
    link_count = 0
    for path in PACKAGE.glob("*.md"):
        for href in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            assert not href.startswith(("http:", "https:", "file:")), "offline local links only"
            target = (path.parent / href.split("#", 1)[0]).resolve()
            assert target.is_relative_to(ROOT) and target.is_file(), (path.name, href)
            link_count += 1
    coverage = list(csv.DictReader((PACKAGE / "correction_coverage_matrix.csv").open(encoding="utf-8", newline="")))
    assert len(coverage) == len({r["requirement_id"] for r in coverage}) == 63
    required = {2,5,6,7,8,9,11,12,13,14,15,17,18,19,20,23,24,26,28,29,31,35,37,39,41,43,44,45,46,47,48}
    normative = [r for r in coverage if r["row_role"] == "AUTHORITATIVE_REQUIREMENT"]
    alignments = [r for r in coverage if r["row_role"] == "PRIOR_CHECKPOINT_ALIGNMENT"]
    assert len(normative) == 31 and {int(r["source_paragraph"]) for r in normative} == required
    assert len(alignments) == 32
    assert sum(r["source_status"] == "PROVISIONAL_SOURCE" for r in alignments) == 9
    assert sum(r["source_status"] == "AUTHORITATIVE_SOURCE" for r in alignments) == 23
    previous = list(csv.DictReader((ROOT / "docs/supervisor_review/g4_submission_v2/correction_coverage_matrix.csv").open(encoding="utf-8", newline="")))
    assert {r["requirement_id"] for r in alignments} == {r["requirement_id"] for r in previous}
    for r in coverage:
        assert r["source_document"] == correction["destination"] and r["source_document_sha256"] == correction["source_sha256"]
        assert r["work_class"] in {"A", "B", "C", "D"}
        assert r["scientific_validation"] == "NOT_INDEPENDENTLY_VALIDATED"
        refs = [int(n) for n in r["source_paragraph"].split(",")]
        hashes = r["source_paragraph_sha256"].split(";")
        assert [hashlib.sha256(paragraphs[n-1].encode()).hexdigest() for n in refs] == hashes
        assert (ROOT / r["implementation_file"]).is_file()
        assert (ROOT / r["supporting_test_or_audit"]).exists()
    assert all(r["source_status"] == "AUTHORITATIVE_SOURCE" for r in normative)
    # Exact path attributes, inherited protected attributes unchanged.
    policy = (PACKAGE / "gitattributes.proposed").read_bytes()
    declarations = [l[1:-6] for l in policy.decode().splitlines() if l.startswith("/") and l.endswith(" -text")]
    assert sorted(declarations) == sorted(selected)
    protected = read(ROOT / "docs/consolidation/g1_v1/baseline_inventory.json")["protected_paths"]
    before_hashes = {p: sha(ROOT / p) for p in protected}
    temp = Path(tempfile.mkdtemp(prefix="chronoguard_g4_b_v3_bytes_")).resolve()
    assert temp.parent == Path(tempfile.gettempdir()).resolve() and not temp.is_relative_to(ROOT)
    def git(*args, data=None):
        return subprocess.run(["git", "-C", str(temp), *args], input=data, capture_output=True, check=True).stdout
    git("init", "--quiet"); git("config", "core.autocrlf", "true")
    (temp / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    attr_input = ("\n".join(protected)+"\n").encode()
    before = git("check-attr", "text", "eol", "filter", "--stdin", data=attr_input)
    (temp / ".gitattributes").write_bytes(policy)
    after = git("check-attr", "text", "eol", "filter", "--stdin", data=attr_input)
    assert before == after
    objects = {}; original_hashes = {}
    for name in selected:
        data = (ROOT / name).read_bytes()
        original_hashes[name] = hashlib.sha256(data).hexdigest()
        oid = git("hash-object", "-w", "--path="+name, "--stdin", data=data).decode().strip()
        assert git("cat-file", "--filters", "--path="+name, oid) == data
        objects[name] = oid
    objects[".gitattributes"] = git("hash-object", "-w", "--stdin", data=policy).decode().strip()
    nested = {}
    for name, oid in objects.items():
        parts = name.split("/"); node = nested
        for part in parts[:-1]: node = node.setdefault(part, {})
        node[parts[-1]] = oid
    def make_tree(node):
        lines = []
        for name, value in sorted(node.items()):
            lines.append(("040000 tree "+make_tree(value) if isinstance(value, dict) else "100644 blob "+value)+"\t"+name+"\n")
        return git("mktree", data="".join(lines).encode()).decode().strip()
    tree = make_tree(nested)
    git("restore", "--source="+tree, "--worktree", "--", ".")
    for name in selected: assert sha(temp / name) == original_hashes[name]
    fixtures = [b"LF\nUnicode \xce\xb2\n", b"CRLF\r\n", b"mixed\r\nLF\n"]
    fixture_path = "src/eval/judge_outcome_adapter.py"
    for data in fixtures:
        oid = git("hash-object", "-w", "--path="+fixture_path, "--stdin", data=data).decode().strip()
        assert git("cat-file", "--filters", "--path="+fixture_path, oid) == data
    # Verify restored audit children; held child is explicitly an external dependency.
    checked_children = external_children = 0
    for name in selected:
        if name.startswith("audits/") and name.endswith("/sha256.json"):
            for child, expected in read(temp / name).items():
                relative = (Path(name).parent / child).as_posix()
                if relative in selected:
                    assert sha(temp / relative) == expected; checked_children += 1
                else:
                    assert relative == "audits/g2_i6_v1/inventory_reconciliation.json"
                    assert sha(ROOT / relative) == expected; external_children += 1
    assert not (temp / ".git/index").exists()
    assert {p: sha(ROOT / p) for p in protected} == before_hashes
    for name, entry in baseline.items(): assert sha(ROOT / name) == entry["sha256"]
    assert not project_git("diff", "--name-only").strip() and not project_git("diff", "--cached", "--name-only").strip()
    if (PACKAGE / "sha256.json").exists():
        for name, h in read(PACKAGE / "sha256.json").items(): assert sha(PACKAGE / name) == h
    return dict(status="PASS_ENGINEERING_CHECKS_ONLY", scientific_gate="BLOCKED", submission="CONDITIONAL_GO",
        baseline_files_verified=214, prior_G4_classified_files_preserved=213, all_classified_paths=228, selected_proposed_publication=199,
        restricted_excluded=25, unrelated_excluded=1, membership_review_hold=1,
        individually_reviewed_audit_candidates=99, new_G4_files=14, original_source_publication_hold=2,
        git_raw_filter_roundtrips=len(selected), tree_checkout_roundtrips=len(selected),
        line_ending_fixture_checks=3, protected_attribute_paths_unchanged=len(protected),
        protected_raw_files_unchanged=len(protected), restored_audit_children_verified=checked_children,
        explicit_external_audit_children_verified=external_children, markdown_links_verified=link_count,
        coverage_matrix_rows=len(coverage), authoritative_requirement_blocks=31, prior_checkpoint_alignment_rows=32, directly_supported_checkpoint_rows=23, provisional_technical_extensions=9, source_coverage="ALL_NORMATIVE_PARAGRAPH_BLOCKS_MAPPED_NOT_FULL_COMPLIANCE", work_class_counts=dict(collections.Counter(r["work_class"] for r in normative)), decision_rows_preserved=14,
        original_authoritative_documents="BOTH_RESEARCHER_SUPPLIED_ORIGINALS_PRESENT", source_destination_byte_equality=True, original_source_sha256=receipt["source_sha256"], correction_source_sha256=correction["source_sha256"], integrity=integrity,
        project_index_changed=False, attributes_applied=False, commits_created=0,
        inference_judging_estimation_retrieval_network="NOT_EXECUTED",
        test_suites="NOT_RUN; checksum-bound prior results only", temporary_index_created=False,
        byte_test_method="hash-object clean filter; cat-file checkout filter; tree restore; isolated Git only",
        report_hash_rule="sha256.json excludes itself; source_inventory binds 214 prior/source files; final package manifest binds other G4 files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="write only this new package's validation result and final hashes")
    args = parser.parse_args()
    if args.record:
        assert (PACKAGE / "sha256.json").read_bytes() == b"{}\n", "sealed package is read-only; use a new version"
    result = verify()
    if args.record:
        (PACKAGE / "publication_validation.json").write_bytes((canonical(result)+"\n").encode())
        hashes = {p.name: sha(p) for p in PACKAGE.iterdir() if p.is_file() and p.name != "sha256.json"}
        (PACKAGE / "sha256.json").write_bytes((canonical(hashes)+"\n").encode())
    print(canonical(result))
