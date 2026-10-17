import json

d = "data/processed/attack_pools/pilot/"
for n in (1, 2, 5):
    a = [json.loads(l) for l in open(f"{d}correct_content_wrong_date_0d_control_n{n}.jsonl", encoding="utf-8")]
    b = [json.loads(l) for l in open(f"{d}correct_content_wrong_date_30d_n{n}.jsonl", encoding="utf-8")]
    for i, (x, y) in enumerate(zip(a, b)):
        ma, mb = x["attack_metadata"], y["attack_metadata"]
        print(n, i,
              "indices same:", ma["target_indices"] == mb["target_indices"],
              "doc_ids same:", ma["target_doc_ids"] == mb["target_doc_ids"])