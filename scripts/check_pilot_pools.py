import glob, json, sys
from datetime import datetime

CLEAN = "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"

def load(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def to_ts(v):
    if isinstance(v, (int, float)):
        return float(v)
    return datetime.fromisoformat(v).timestamp()

clean = load(CLEAN)
fails = []
for path in sorted(glob.glob("data/processed/attack_pools/pilot/*_n*.jsonl")):
    name = path.replace("\\", "/").split("/")[-1]
    for r in load(path):
        i = r["pilot_index"]
        c = clean[i]
        meta = r.get("attack_metadata") or {}
        idx = meta.get("target_indices")
        tag = f"{name} pilot {i}"
        if not idx:
            fails.append(f"{tag}: no target_indices"); continue
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
sys.exit(1 if fails else 0)