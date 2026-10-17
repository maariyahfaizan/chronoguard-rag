import json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def row(pool, exp, q):
    p = os.path.join(ROOT, "logs", "pilot_attacks", f"{pool}__{exp}.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()][q]


for pool in ("correct_content_wrong_date_0d_control_n2", "correct_content_wrong_date_30d_n2"):
    c, a = row("clean", "E1", 1), row(pool, "E1", 1)
    print(pool)
    print("  clean    idx", c["retrieved_passage_indices"], [round(s, 2) for s in c["retrieved_scores"]])
    print("  attacked idx", a["retrieved_passage_indices"], [round(s, 2) for s in a["retrieved_scores"]])
    print("  clean answer   :", c["generated_answer"])
    print("  attacked answer:", a["generated_answer"])