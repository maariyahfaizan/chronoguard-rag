import glob, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)

CLEAN = "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"
REPORT = "results/pilot_pool_check.json"


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


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=ROOT).stdout.strip()
    except Exception:
        return None


clean = load(CLEAN)
fails = []
files = []
n_records = 0

for path in sorted(glob.glob("data/processed/attack_pools/pilot/*_n*.jsonl")):
    name = path.replace("\\", "/").split("/")[-1]
    expected_count = int(name.rsplit("_n", 1)[1].split(".")[0])
    records = load(path)
    n_records += len(records)
    files.append({"file": name, "n_records": len(records),
                  "expected_poison_count": expected_count,
                  "sha256_lf": sha_lf(path)})
    for r in records:
        i = r["pilot_index"]
        c = clean[i]
        meta = r.get("attack_metadata") or {}
        idx = meta.get("target_indices")
        tag = f"{name} pilot {i}"
        if not idx:
            fails.append(f"{tag}: no target_indices"); continue
        # NEW check: number of targets must match the count in the file name
        if len(idx) != expected_count:
            fails.append(f"{tag}: {len(idx)} targets but file says n{expected_count}")
        for k in ("query", "gold_answer", "gold_aliases", "question_ts", "gold_chunk_ids"):
            if r[k] != c[k]:
                fails.append(f"{tag}: {k} changed")
        if [x["doc_id"] for x in r["candidates"]] != [x["doc_id"] for x in c["candidates"]]:
            fails.append(f"{tag}: doc_id list changed")
        changed = [j for j, (a, b) in enumerate(zip(r["candidates"], c["candidates"])) if a != b]
        if sorted(changed) != sorted(idx):
            fails.append(f"{tag}: changed slots {changed} != target_indices {idx}")
        for j in idx:
            if c["candidates"][j]["doc_id"] in c["gold_chunk_ids"]:
                fails.append(f"{tag}: target slot {j} is gold")
            cand = r["candidates"][j]
            if cand.get("is_source_document"):
                fails.append(f"{tag}: slot {j} flagged is_source_document")
            if name.startswith("fabricated_fresh") and to_ts(cand["timestamp"]) >= to_ts(r["question_ts"]):
                fails.append(f"{tag}: fabricated timestamp not before question")
            if name.startswith("future_date") and to_ts(cand["timestamp"]) <= to_ts(r["question_ts"]):
                fails.append(f"{tag}: future_date timestamp not after question")
    print("checked", name)

print("ALL OK" if not fails else "FAILURES:")
for f in fails:
    print(" ", f)

status = git("status", "--porcelain") or ""
report = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "git_commit": git("rev-parse", "HEAD"),
    "git_dirty": bool(status),
    "git_status_porcelain": status.splitlines(),
    "checker_sha256_lf": sha_lf(os.path.abspath(__file__)),
    "clean_pilot_file": CLEAN,
    "clean_pilot_sha256_lf": sha_lf(CLEAN),
    "n_pool_files": len(files),
    "n_records_checked": n_records,
    "files": files,
    "checks_performed": [
        "query, gold_answer, gold_aliases, question_ts, gold_chunk_ids unchanged",
        "candidate doc_id list identical to clean (constant count)",
        "changed slots exactly equal target_indices (implies unique slots)",
        "no target slot is gold",
        "no target slot flagged is_source_document",
        "fabricated_fresh timestamps before question",
        "future_date timestamps after question",
        "number of targets equals poison count in file name (added check)",
    ],
    "result": "ALL OK" if not fails else "FAILED",
    "failures": fails,
}
os.makedirs(os.path.dirname(REPORT), exist_ok=True)
with open(REPORT, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("saved", REPORT)
sys.exit(1 if fails else 0)