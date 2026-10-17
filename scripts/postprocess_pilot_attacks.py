import csv, glob, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POOL_DIR = os.path.join(ROOT, "data", "processed", "attack_pools", "pilot")
LOG_DIR = os.path.join(ROOT, "logs", "pilot_attacks")
OUT_CSV = os.path.join(ROOT, "results", "pilot_attack_rows.csv")
EXPS = ["E1", "E2", "E3", "E4"]
METRICS = ["em", "f1", "recall_at_5", "ndcg_at_5", "fraction_top_5_violating",
           "valid_evidence_recall_at_5", "time_valid_answer_accuracy"]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def norm(s):
    return " ".join((s or "").split())


clean_logs = {e: read_jsonl(os.path.join(LOG_DIR, f"clean__{e}.jsonl")) for e in EXPS}
rows, problems, hidden = [], [], {}

for pool_path in sorted(glob.glob(os.path.join(POOL_DIR, "*_n*.jsonl"))):
    pool = os.path.basename(pool_path)[:-6]
    records = read_jsonl(pool_path)
    for exp in EXPS:
        logs = read_jsonl(os.path.join(LOG_DIR, f"{pool}__{exp}.jsonl"))
        if len(logs) != len(records):
            problems.append(f"{pool} {exp}: {len(logs)} log rows vs {len(records)} records")
            continue
        for i, (rec, row) in enumerate(zip(records, logs)):
            if row["query_id"] != i:
                problems.append(f"{pool} {exp}: query_id {row['query_id']} at line {i}")
            clean = clean_logs[exp][rec["pilot_index"]]
            if row["gold_answer"] != clean["gold_answer"]:
                problems.append(f"{pool} {exp} row {i}: gold differs from clean")
            targets = rec["attack_metadata"]["target_indices"]
            retrieved = row["retrieved_passage_indices"]
            ranks = [retrieved.index(t) + 1 if t in retrieved else None for t in targets]
            chosen = [r for r in ranks if r is not None]
            out = {
                "pool": pool,
                "condition": rec["attack_condition"],
                "experiment": exp,
                "pilot_index": rec["pilot_index"],
                "poison_count": len(targets),
                "poison_slots": ";".join(str(t) for t in targets),
                "poison_ranks_top5": ";".join("NA" if r is None else str(r) for r in ranks),
                "n_poison_selected": len(chosen),
                "best_poison_rank": min(chosen) if chosen else "",
                "answer_clean": clean["generated_answer"],
                "answer_attacked": row["generated_answer"],
                "answer_changed": norm(clean["generated_answer"]) != norm(row["generated_answer"]),
                "same_retrieved_as_clean": retrieved == clean["retrieved_passage_indices"],
                "same_prompt_as_clean": row["prompt"] == clean["prompt"],
            }
            for m in METRICS:
                for tag, src in (("clean", clean), ("attacked", row)):
                    v = src.get(m)
                    out[f"{m}_{tag}"] = "" if v is None else v
            rows.append(out)
            hidden[(pool, exp, rec["pilot_index"])] = (retrieved, row["prompt"], norm(row["generated_answer"]))

os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

# Negative control: future_date must equal clean in retrieval, prompt and answer.
bad_future = [r for r in rows if r["condition"] == "future_date" and
              (r["answer_changed"] or not r["same_retrieved_as_clean"] or not r["same_prompt_as_clean"])]
# 30-day vs 0-day control: same content, so must be identical.
bad_ctrl = []
for r in rows:
    if r["condition"] == "correct_content_wrong_date_30d":
        ctrl = hidden[(r["pool"].replace("30d", "0d_control"), r["experiment"], r["pilot_index"])]
        if ctrl != hidden[(r["pool"], r["experiment"], r["pilot_index"])]:
            bad_ctrl.append((r["pool"], r["experiment"], r["pilot_index"]))

print("rows written:", len(rows), "(expect 180)")
print("problems:", problems or "none")
print("future_date rows differing from clean:", len(bad_future))
for r in bad_future:
    print("  ", r["pool"], r["experiment"], "q", r["pilot_index"])
print("30d vs 0d control mismatches:", len(bad_ctrl), bad_ctrl)
print("saved:", OUT_CSV)