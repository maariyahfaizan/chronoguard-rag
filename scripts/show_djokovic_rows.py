import csv, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
rows = list(csv.DictReader(open(os.path.join(ROOT, "results", "pilot_attack_rows.csv"),
                                encoding="utf-8", newline="")))
for r in rows:
    if r["condition"] == "fabricated_fresh" and r["pilot_index"] == "2":
        print(f"{r['pool']} {r['experiment']} | F1 {r['f1_clean']}->{r['f1_attacked']}"
              f" | EM {r['em_clean']}->{r['em_attacked']}\n    attacked: {r['answer_attacked']}")