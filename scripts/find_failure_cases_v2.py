import csv, glob, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rows = list(csv.DictReader(open(os.path.join(ROOT, "results", "pilot_attack_rows.csv"),
                                encoding="utf-8", newline="")))


def f(x):
    return None if x in ("", None) else float(x)


def sel(r):
    return int(r["n_poison_selected"])


def show(title, hits, n=8):
    print(f"\n=== {title}: {len(hits)} rows ===")
    for r in hits[:n]:
        print(f"  {r['pool']} {r['experiment']} q{r['pilot_index']} | poison ranks {r['poison_ranks_top5']}"
              f" | EM {r['em_clean']}->{r['em_attacked']}"
              f" | '{r['answer_clean']}' -> '{r['answer_attacked']}'")


real = [r for r in rows if r["condition"] in ("fabricated_fresh", "duplicate_fresh")]
show("REAL POISON, selected, EM stays 1 (poison present, answer still correct)",
     [r for r in real if sel(r) > 0 and f(r["em_clean"]) == 1 and f(r["em_attacked"]) == 1])
show("REAL POISON, selected, EM 1->0 (harm)",
     [r for r in real if sel(r) > 0 and f(r["em_clean"]) == 1 and f(r["em_attacked"]) == 0])
show("REAL POISON, selected, EM 0->1 (attack coincided with a correct answer)",
     [r for r in real if sel(r) > 0 and f(r["em_clean"]) == 0 and f(r["em_attacked"]) == 1])
show("REAL POISON, NOT selected, EM 1->0",
     [r for r in real if sel(r) == 0 and f(r["em_clean"]) == 1 and f(r["em_attacked"]) == 0])

# Displacement check for category 6: answer changed, no poison slot in top 5.
clean_logs = {}
for e in ("E1", "E2", "E3", "E4"):
    clean_logs[e] = [json.loads(l) for l in open(
        os.path.join(ROOT, "logs", "pilot_attacks", f"clean__{e}.jsonl"), encoding="utf-8") if l.strip()]

cat6 = [r for r in rows if r["answer_changed"] == "True" and sel(r) == 0]
print(f"\n=== DISPLACEMENT CHECK: answer changed, no poison in top 5: {len(cat6)} rows ===")
n_disp = 0
for r in cat6:
    targets = [int(t) for t in r["poison_slots"].split(";")]
    clean_top5 = clean_logs[r["experiment"]][int(r["pilot_index"])]["retrieved_passage_indices"]
    hit = [t for t in targets if t in clean_top5]
    n_disp += bool(hit)
    print(f"  {r['pool']} {r['experiment']} q{r['pilot_index']} | replaced slots {targets}"
          f" | clean top5 {clean_top5} | replaced slot was in clean top5: {hit or 'no'}")
print(f"\nrows where a replaced slot WAS in the clean top 5: {n_disp} of {len(cat6)}")