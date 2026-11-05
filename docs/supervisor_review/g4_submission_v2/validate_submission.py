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
    assert len({r["path"] for r in allowed_rows}) == len(allowed_rows) == 213
    assert {r["path"] for r in allowed_rows} == set(actual), "allowlist must enumerate every existing/new path"
    selected = [r["path"] for r in allowed_rows if r["proposed_publication"] == "YES_PROPOSED"]
    denied = [r for r in allowed_rows if r["proposed_publication"] != "YES_PROPOSED"]
    assert len(selected) == 185 and len(denied) == 28
    assert sum(r["classification"] == "EXTERNAL_RESTRICTED_ARTIFACT" for r in denied) == 25
    assert sum(r["classification"] == "UNRELATED_EXCLUDED" for r in denied) == 1
    assert [r["path"] for r in denied if r["proposed_publication"] == "HOLD_DATA_MEMBERSHIP_REVIEW"] == [
        "audits/g2_i6_v1/inventory_reconciliation.json"]
    for r in allowed_rows:
        if r["origin"] == "G4_A_BASELINE": assert r["source_sha256"] == baseline[r["path"]]["sha256"]
        else: assert r["origin"] == "NEW_G4_A_V2" and r["source_sha256"] == "SEE_G4_SHA256_MANIFEST"
    audit_rows = [r for r in allowed_rows if r["classification"] == "PUBLICATION_CANDIDATE_AUDIT" and r["origin"] == "G4_A_BASELINE"]
    assert len(audit_rows) == 95
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
    # Incorporation is hash-bound; researcher designation is not independent approval.
    assert snapshot["authoritative_documents"]["original_review_package"] == "PRESENT_RESEARCHER_DESIGNATED_ORIGINAL"
    assert snapshot["authoritative_documents"]["november_3_corrections"] == "MISSING"
    receipt = read(PACKAGE / "authenticity_record.json")
    original = ROOT / receipt["destination"]
    assert sha(original) == receipt["source_sha256"] == receipt["destination_sha256"]
    assert original.stat().st_size == receipt["byte_length"] == 27349
    assert receipt["exact_byte_equality"] and receipt["document_identity"] == "A_ORIGINAL_SUPERVISOR_REVIEW_PACKAGE"
    linked_source = Path(receipt["source_link"])
    if linked_source.exists():
        assert linked_source.read_bytes() == original.read_bytes(), "exact source bytes changed"
    assert not (ROOT / "docs/supervisor_review/source_documents/ChronoGuard_RAG_Student_Required_Corrections_03Nov2026.docx").exists(), "new correction source needs a new version"
    prior = ROOT / "docs/supervisor_review/g4_submission_v1"
    assert sha(prior / "sha256.json") == "983b2604143f26eff2ea53022fa6065fea331293b3b7fa20bc6404886325d49f"
    for name, h in read(prior / "sha256.json").items(): assert sha(prior / name) == h
    assert [r["path"] for r in denied if r["proposed_publication"] == "HOLD_AUTHORITATIVE_SOURCE_REVIEW"] == [receipt["destination"]]
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
    assert coverage and len({r["requirement_id"] for r in coverage}) == len(coverage)
    assert all(r["source_status"] == "PROVISIONAL_SOURCE" and r["scientific_validation"] == "NOT_INDEPENDENTLY_VALIDATED" for r in coverage)
    assert len(coverage) == 32
    for r in coverage:
        assert r["original_package_path"] == receipt["destination"]
        assert r["original_package_sha256"] == receipt["source_sha256"]
        assert r["november_3_correction_status"] == "MISSING_PROVISIONAL_COVERAGE_ONLY"
        assert (ROOT / r["implementation_file"]).is_file()
        assert (ROOT / r["supporting_test_or_audit"]).exists()
    # Exact path attributes, inherited protected attributes unchanged.
    policy = (PACKAGE / "gitattributes.proposed").read_bytes()
    declarations = [l[1:-6] for l in policy.decode().splitlines() if l.startswith("/") and l.endswith(" -text")]
    assert sorted(declarations) == sorted(selected)
    protected = read(ROOT / "docs/consolidation/g1_v1/baseline_inventory.json")["protected_paths"]
    before_hashes = {p: sha(ROOT / p) for p in protected}
    temp = Path(tempfile.mkdtemp(prefix="chronoguard_g4_a_v2_bytes_")).resolve()
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
        baseline_files_verified=199, prior_G4_classified_files_preserved=198, all_classified_paths=213, selected_proposed_publication=185,
        restricted_excluded=25, unrelated_excluded=1, membership_review_hold=1,
        individually_reviewed_audit_candidates=95, new_G4_files=14, original_source_publication_hold=1,
        git_raw_filter_roundtrips=len(selected), tree_checkout_roundtrips=len(selected),
        line_ending_fixture_checks=3, protected_attribute_paths_unchanged=len(protected),
        protected_raw_files_unchanged=len(protected), restored_audit_children_verified=checked_children,
        explicit_external_audit_children_verified=external_children, markdown_links_verified=link_count,
        provisional_coverage_rows=len(coverage), decision_rows_preserved=14,
        original_authoritative_documents="ORIGINAL_SUPPLIED_NOVEMBER_3_MISSING_COVERAGE_INCOMPLETE", source_destination_byte_equality=True, original_source_sha256=receipt["source_sha256"], integrity=integrity,
        project_index_changed=False, attributes_applied=False, commits_created=0,
        inference_judging_estimation_retrieval_network="NOT_EXECUTED",
        test_suites="NOT_RUN; checksum-bound prior results only", temporary_index_created=False,
        byte_test_method="hash-object clean filter; cat-file checkout filter; tree restore; isolated Git only",
        report_hash_rule="sha256.json excludes itself; source_inventory binds 199 prior/source files; final package manifest binds other G4 files")


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
