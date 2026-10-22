#!/usr/bin/env python3
"""Independent integrity check of the built pilot pools (protocol v2).

Run from the repo root after scripts/build_pilot_attack_pools.py:
    python scripts/check_pilot_pools.py

Writes results/pilot_pool_check.json and exits 1 on any failure.
Records are matched to the clean pilot by source_qa_id, never by position.
"""
import glob, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from src.attacks.pilot_protocol import (  # noqa: E402
    POOL_DIR, PROTOCOL_VERSION, nesting_problems,
)

CLEAN = "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
REPORT = "results/pilot_pool_check.json"
POOLS = os.path.join(os.path.relpath(POOL_DIR, ROOT), "*_n*.jsonl")
MANIFEST = os.path.join(os.path.relpath(POOL_DIR, ROOT), "pilot_pools_manifest.json")


def load(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def to_ts(v):
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(v).timestamp()


def sha_lf(path):
    """SHA-256 of the file with CRLF normalised to LF (matches what git stores)."""
    data = open(path, "rb").read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def sha_raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    except Exception:
        return None


clean = {c["source_qa_id"]: c for c in load(CLEAN)}
manifest = json.load(open(MANIFEST, encoding="utf-8"))
manifest_sha = {os.path.basename(p["file"]): p["sha256"] for p in manifest["pools"]}
fails = []
files = []
n_records = 0
targets = {}  # (condition, qa_id) -> {count: target_indices}

if manifest.get("protocol_version") != PROTOCOL_VERSION:
    fails.append(f"manifest protocol_version is {manifest.get('protocol_version')!r}")

for path in sorted(glob.glob(POOLS)):
    name = path.replace("\\", "/").split("/")[-1]
    condition, count_part = name[:-6].rsplit("_n", 1)
    expected_count = int(count_part)
    records = load(path)
    n_records += len(records)
    files.append({"file": name, "n_records": len(records),
                  "expected_poison_count": expected_count,
                  "sha256_lf": sha_lf(path)})
    if manifest_sha.get(name) != sha_raw(path):
        fails.append(f"{name}: sha256 differs from the manifest")
    if condition == "stale_evidence":
        fails.append(f"{name}: stale_evidence pool exists but no stale evidence was reviewed")
    for r in records:
        qa_id = r.get("source_qa_id")
        tag = f"{name} {qa_id}"
        if qa_id not in clean:
            fails.append(f"{tag}: source_qa_id not in the clean pilot"); continue
        c = clean[qa_id]
        meta = r.get("attack_metadata") or {}
        idx = meta.get("target_indices")
        if not idx:
            fails.append(f"{tag}: no target_indices"); continue
        targets.setdefault((condition, qa_id), {})[expected_count] = idx
        if r.get("attack_condition") != condition:
            fails.append(f"{tag}: attack_condition {r.get('attack_condition')!r}")
        if r.get("poison_count") != expected_count or len(idx) != expected_count:
            fails.append(f"{tag}: {len(idx)} targets / poison_count {r.get('poison_count')} "
                         f"but file says n{expected_count}")
        if r.get("attack_protocol_version") != PROTOCOL_VERSION:
            fails.append(f"{tag}: attack_protocol_version {r.get('attack_protocol_version')!r}")
        for k in ("query", "gold_answer", "gold_aliases", "question_ts", "gold_chunk_ids"):
            if r[k] != c[k]:
                fails.append(f"{tag}: {k} changed")
        if [x["doc_id"] for x in r["candidates"]] != [x["doc_id"] for x in c["candidates"]]:
            fails.append(f"{tag}: doc_id list changed")
        changed = [j for j, (a, b) in enumerate(zip(r["candidates"], c["candidates"])) if a != b]
        if sorted(changed) != sorted(idx):
            fails.append(f"{tag}: changed slots {changed} != target_indices {idx}")
        if meta.get("target_doc_ids") != [c["candidates"][j]["doc_id"] for j in idx]:
            fails.append(f"{tag}: target_doc_ids do not match target slots")
        for j in idx:
            if c["candidates"][j]["doc_id"] in c["gold_chunk_ids"]:
                fails.append(f"{tag}: target slot {j} is gold")
            cand = r["candidates"][j]
            if cand.get("is_source_document"):
                fails.append(f"{tag}: slot {j} flagged is_source_document")
            if condition == "fabricated_fresh":
                if cand.get("payload_source_qa_id") != qa_id:
                    fails.append(f"{tag}: slot {j} payload belongs to {cand.get('payload_source_qa_id')!r}")
                if to_ts(cand["timestamp"]) >= to_ts(r["question_ts"]):
                    fails.append(f"{tag}: fabricated timestamp not before question")
            if condition == "future_date" and to_ts(cand["timestamp"]) <= to_ts(r["question_ts"]):
                fails.append(f"{tag}: future_date timestamp not after question")
    print("checked", name)

# Nested poison counts: n=1 subset of n=2 subset of n=5, per question and condition.
for (condition, qa_id), by_count in sorted(targets.items()):
    for problem in nesting_problems(by_count):
        fails.append(f"{condition} {qa_id}: {problem}")

# The 0-day control must use exactly the same slots as the 30-day attack.
for (condition, qa_id), by_count in sorted(targets.items()):
    if condition == "correct_content_wrong_date_30d":
        control = targets.get(("correct_content_wrong_date_0d_control", qa_id), {})
        if control != by_count:
            fails.append(f"{qa_id}: 30d slots {by_count} != 0d control slots {control}")

print("ALL OK" if not fails else "FAILURES:")
for f in fails:
    print(" ", f)

status = git("status", "--porcelain") or ""
report = {
    "protocol_version": PROTOCOL_VERSION,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": git("rev-parse", "HEAD"),
    "git_dirty": bool(status),
    "git_status_porcelain": status.splitlines(),
    "checker_sha256_lf": sha_lf(os.path.abspath(__file__)),
    "clean_pilot_file": CLEAN,
    "clean_pilot_sha256_lf": sha_lf(CLEAN),
    "pool_dir": os.path.relpath(POOL_DIR, ROOT).replace("\\", "/"),
    "n_pool_files": len(files),
    "n_records_checked": n_records,
    "files": files,
    "checks_performed": [
        "records matched to the clean pilot by source_qa_id (not position)",
        "query, gold_answer, gold_aliases, question_ts, gold_chunk_ids unchanged",
        "candidate doc_id list identical to clean (constant count)",
        "changed slots exactly equal target_indices (implies unique slots)",
        "target_doc_ids equal the doc_ids of the target slots",
        "no target slot is gold",
        "no target slot flagged is_source_document",
        "fabricated_fresh slots carry a payload with the record's source_qa_id",
        "fabricated_fresh timestamps before question",
        "future_date timestamps after question",
        "number of targets equals poison count in file name and record",
        "attack_condition and attack_protocol_version recorded on every record",
        "poison counts nested: n=1 subset of n=2 subset of n=5 per question and condition",
        "30d attack and 0d control use identical slots",
        "pool file sha256 matches the build manifest",
        "no stale_evidence pool (no reviewed stale evidence)",
    ],
    "result": "ALL OK" if not fails else "FAILED",
    "failures": fails,
}
os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("saved", REPORT)
sys.exit(1 if fails else 0)
