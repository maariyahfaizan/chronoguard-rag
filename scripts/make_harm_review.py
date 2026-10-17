import csv, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rows = list(csv.DictReader(open(os.path.join(ROOT, "results", "pilot_attack_rows.csv"),
                                encoding="utf-8", newline="")))


def sel(r):
    return int(r["n_poison_selected"])


clean_logs = {e: [json.loads(l) for l in open(
    os.path.join(ROOT, "logs", "pilot_attacks", f"clean__{e}.jsonl"), encoding="utf-8") if l.strip()]
    for e in ("E1", "E2", "E3", "E4")}

harm = [r for r in rows
        if r["condition"] in ("fabricated_fresh", "duplicate_fresh")
        and sel(r) > 0 and r["em_clean"] == "1" and r["em_attacked"] == "0"]

out = []
for r in harm:
    gold = clean_logs[r["experiment"]][int(r["pilot_index"])]["gold_answer"]
    out.append({"pool": r["pool"], "experiment": r["experiment"], "pilot_index": r["pilot_index"],
                "poison_ranks_top5": r["poison_ranks_top5"], "gold_answer": gold,
                "answer_clean": r["answer_clean"], "answer_attacked": r["answer_attacked"],
                "manual_label": "", "manual_notes": ""})
    print(f"{r['pool']} {r['experiment']} q{r['pilot_index']} | ranks {r['poison_ranks_top5']}"
          f" | gold '{gold}'\n    clean   : {r['answer_clean']}\n    attacked: {r['answer_attacked']}\n")

path = os.path.join(ROOT, "results", "pilot_harm_review.csv")
with open(path, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
    w.writeheader()
    w.writerows(out)
print(len(out), "rows saved to", path)