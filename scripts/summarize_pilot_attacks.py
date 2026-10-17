import csv, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "results", "pilot_attack_rows.csv")
OUT = os.path.join(ROOT, "results", "pilot_vulnerability_summary.csv")
EXPS = ["E1", "E2", "E3", "E4"]
METRICS = ["em", "f1", "recall_at_5", "ndcg_at_5", "fraction_top_5_violating",
           "valid_evidence_recall_at_5", "time_valid_answer_accuracy"]

rows = list(csv.DictReader(open(SRC, encoding="utf-8", newline="")))


def num(x):
    return None if x in ("", None) else float(x)


groups = {}
for r in rows:
    groups.setdefault((r["pool"], r["condition"], r["poison_count"], r["experiment"]), []).append(r)

out_rows = []
for (pool, cond, count, exp), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], EXPS.index(kv[0][3]))):
    o = {"pool": pool, "condition": cond, "poison_count": count, "experiment": exp, "n_questions": len(rs)}
    o["n_answer_changed"] = sum(r["answer_changed"] == "True" for r in rs)
    o["n_questions_poison_in_top5"] = sum(int(r["n_poison_selected"]) > 0 for r in rs)
    o["poison_slots_in_top5"] = sum(int(r["n_poison_selected"]) for r in rs)
    o["poison_slots_total"] = sum(int(r["poison_count"]) for r in rs)
    ranks = [int(r["best_poison_rank"]) for r in rs if r["best_poison_rank"] != ""]
    o["mean_best_poison_rank"] = round(sum(ranks) / len(ranks), 3) if ranks else ""
    for m in METRICS:
        pairs = [(num(r[f"{m}_clean"]), num(r[f"{m}_attacked"])) for r in rs]
        pairs = [(c, a) for c, a in pairs if c is not None and a is not None]
        o[f"{m}_n_defined"] = len(pairs)
        if pairs:
            mc = sum(c for c, _ in pairs) / len(pairs)
            ma = sum(a for _, a in pairs) / len(pairs)
            o[f"{m}_clean"], o[f"{m}_attacked"], o[f"{m}_delta"] = round(mc, 4), round(ma, 4), round(ma - mc, 4)
        else:
            o[f"{m}_clean"] = o[f"{m}_attacked"] = o[f"{m}_delta"] = ""
    out_rows.append(o)

with open(OUT, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
    w.writeheader()
    w.writerows(out_rows)

print("rows written:", len(out_rows), "(expect 60 = 15 pools x 4 systems)")
print("saved:", OUT)
print()
print("Cell = answers changed / poison-slot questions in top-5 (of 3 questions)")
print(f"{'pool':44s}" + "".join(f"{e:>10s}" for e in EXPS))
pools = sorted({o["pool"] for o in out_rows})
for p in pools:
    cells = []
    for e in EXPS:
        o = next(x for x in out_rows if x["pool"] == p and x["experiment"] == e)
        cells.append(f"{o['n_answer_changed']}/{o['n_questions_poison_in_top5']}")
    print(f"{p:44s}" + "".join(f"{c:>10s}" for c in cells))