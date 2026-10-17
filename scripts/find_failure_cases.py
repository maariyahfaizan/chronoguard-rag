import csv, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rows = list(csv.DictReader(open(os.path.join(ROOT, "results", "pilot_attack_rows.csv"),
                                encoding="utf-8", newline="")))


def f(x):
    return None if x in ("", None) else float(x)


def sel(r):
    return int(r["n_poison_selected"])


cats = {
    "1 poison selected + answer correct (EM=1)":
        lambda r: sel(r) > 0 and f(r["em_attacked"]) == 1,
    "2 poison selected + answer wrong (EM=0)":
        lambda r: sel(r) > 0 and f(r["em_attacked"]) == 0,
    "3 poison NOT selected + answer wrong (EM=0)":
        lambda r: sel(r) == 0 and f(r["em_attacked"]) == 0,
    "4 duplicate amplification (duplicate_fresh, 2+ poison slots in top 5)":
        lambda r: r["condition"] == "duplicate_fresh" and sel(r) >= 2,
    "5 metadata-only, no answer change (future_date)":
        lambda r: r["condition"] == "future_date" and r["answer_changed"] == "False",
    "6 UNEXPECTED: answer changed but no poison slot in top 5":
        lambda r: r["answer_changed"] == "True" and sel(r) == 0,
}

for name, test in cats.items():
    hits = [r for r in rows if test(r)]
    print(f"\n=== {name}: {len(hits)} rows ===")
    for r in hits[:4]:
        print(f"  {r['pool']} {r['experiment']} q{r['pilot_index']} | poison ranks {r['poison_ranks_top5']}"
              f" | retrieved same as clean: {r['same_retrieved_as_clean']}"
              f" | EM {r['em_clean']}->{r['em_attacked']}"
              f" | '{r['answer_clean']}' -> '{r['answer_attacked']}'")

same_em = [r for r in rows if r["answer_changed"] == "True" and r["em_clean"] == r["em_attacked"]]
print(f"\nAnswer text changed but EM unchanged: {len(same_em)} of "
      f"{sum(r['answer_changed'] == 'True' for r in rows)} changed rows")