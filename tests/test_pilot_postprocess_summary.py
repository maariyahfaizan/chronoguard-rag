"""End-to-end check of postprocess_pilot_attacks.py + summarize_pilot_attacks.py
on SYNTHETIC v2 logs written to a temporary folder.

Each synthetic log row copies the real clean pilot row and adds the attack
fields the drivers now log. For fabricated_fresh x E2 the answers and top-1
slot are replaced so ASR, NEEDS_REVIEW handling and gold displacement are
exercised. Nothing under results/ or logs/ is written.
"""

import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOLS = ROOT / "data/processed/attack_pools/pilot_v2_nested"
CLEAN = ROOT / "logs/pilot_attacks/clean__{exp}.jsonl"

sys.path.insert(0, str(ROOT))
from src.eval.config_loader import model_revisions  # noqa: E402
from src.eval.run_metadata import attack_log_fields  # noqa: E402

ATTACKED_E2 = {"eval-001639": "Five.", "eval-001952": "Forty.",
               "eval-005229": "I. Have. No. Idea. he is still undecided"}


def write_synthetic_logs(log_dir):
    generator = "mistralai/Mistral-7B-Instruct-v0.2"
    pin = model_revisions()[generator]
    for exp in ("E1", "E2", "E3", "E4"):
        clean = {}
        for line in open(str(CLEAN).format(exp=exp), encoding="utf-8"):
            row = json.loads(line)
            clean[row["query"]] = row
        for pool in glob.glob(str(POOLS / "*_n*.jsonl")):
            name = os.path.basename(pool)[:-6]
            with open(os.path.join(log_dir, f"{name}__{exp}.jsonl"), "w", encoding="utf-8") as out:
                for line in open(pool, encoding="utf-8"):
                    rec = json.loads(line)
                    row = dict(clean[rec["query"]])
                    row.update(attack_log_fields(rec))
                    row["run_metadata"] = {
                        "attack_protocol_version": rec["attack_protocol_version"],
                        "config_hash": "synthetic",
                        "models": {"generator": {"name": generator, "pinned_revision": pin,
                                                 "loaded_revision": None}}}
                    if name.startswith("fabricated_fresh") and exp == "E2":
                        row["generated_answer"] = ATTACKED_E2[rec["source_qa_id"]]
                        t = rec["attack_metadata"]["target_indices"][0]
                        row["retrieved_passage_indices"] = [t] + row["retrieved_passage_indices"][:4]
                        row["retrieved_doc_ids"] = ([rec["candidates"][t]["doc_id"]]
                                                    + row["retrieved_doc_ids"][:4])
                    out.write(json.dumps(row) + "\n")


@unittest.skipUnless(POOLS.exists() and Path(str(CLEAN).format(exp="E1")).exists(),
                     "v2 pools or clean pilot logs not present")
class TestPostprocessAndSummary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        logs, results = Path(cls.tmp.name, "logs"), Path(cls.tmp.name, "results")
        logs.mkdir()
        results.mkdir()
        write_synthetic_logs(logs)
        cls.post = subprocess.run(
            [sys.executable, str(ROOT / "scripts/postprocess_pilot_attacks.py"),
             "--log-dir", str(logs), "--results-dir", str(results)],
            capture_output=True, text=True, cwd=ROOT)
        cls.summ = subprocess.run(
            [sys.executable, str(ROOT / "scripts/summarize_pilot_attacks.py"),
             "--results-dir", str(results)],
            capture_output=True, text=True, cwd=ROOT)
        cls.results = results

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def summary(self, condition, count, exp, results=None):
        path = (results or self.results) / "pilot_vulnerability_summary.csv"
        rows = csv.DictReader(open(path, encoding="utf-8"))
        return next(r for r in rows if r["condition"] == condition
                    and r["poison_count"] == str(count) and r["experiment"] == exp)

    def test_postprocess_passes_integrity_checks(self):
        self.assertEqual(self.post.returncode, 0, self.post.stdout + self.post.stderr)
        report = json.load(open(self.results / "pilot_consistency_check.json", encoding="utf-8"))
        self.assertEqual(report["n_rows"], 180)
        self.assertEqual(report["log_problems"], [])
        self.assertEqual(report["future_date_rows_differing_from_clean"], [])

    def test_needs_review_blocks_asr_until_a_human_labels_it(self):
        self.assertEqual(self.summ.returncode, 0, self.summ.stdout + self.summ.stderr)
        cell = self.summary("fabricated_fresh", 1, "E2")
        self.assertEqual(cell["n_needs_review_unresolved"], "1")
        self.assertEqual(cell["asr"], "")
        self.assertEqual(cell["poison_selection_rate"], "1.0")

    def test_asr_after_human_review(self):
        reviewed = Path(self.tmp.name, "reviewed")
        shutil.copytree(self.results, reviewed)
        review = reviewed / "pilot_judge_review.csv"
        rows = list(csv.DictReader(open(review, encoding="utf-8")))
        for row in rows:
            row["human_label"] = "CORRECT"
        with open(review, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        subprocess.run([sys.executable, str(ROOT / "scripts/summarize_pilot_attacks.py"),
                        "--results-dir", str(reviewed)], check=True, capture_output=True, cwd=ROOT)
        cell = self.summary("fabricated_fresh", 1, "E2", reviewed)
        self.assertEqual(cell["asr"], str(round(2 / 3, 4)))
        self.assertEqual(cell["conditional_asr"], str(round(2 / 3, 4)))

    def test_controls_and_stale_rows(self):
        self.assertEqual(self.summary("future_date", 5, "E4")["asr"], "not_applicable")
        stale = self.summary("stale_evidence", 1, "E1")
        self.assertEqual(stale["n_eligible_attacked"], "0")
        self.assertEqual(stale["n_ineligible"], "3")
        self.assertEqual(stale["ineligible_reason"], "no reviewed stale evidence available")
        self.assertEqual(stale["asr"], "")


if __name__ == "__main__":
    unittest.main()
