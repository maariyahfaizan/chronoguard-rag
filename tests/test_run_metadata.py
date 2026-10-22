"""Tests for run provenance: attack fields in log rows, pinned revisions,
and the E1 driver no longer hardcoding attack_condition "clean".

The E1 driver test stubs transformers / torch / rank_bm25 when they are not
installed (they only exist in the Kaggle environment), and replaces the
generator with a fixed answer. It checks logging, not retrieval quality.
"""

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml

from src.eval.config_loader import model_revisions
from src.eval.run_metadata import attack_log_fields, build_run_metadata, sha256_json

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "data/processed/attack_pools/pilot_v2_nested/fabricated_fresh_n2.jsonl"
CLEAN = ROOT / "data/processed/attack_sources/streamingqa_attack_pilot.jsonl"


class TestAttackLogFields(unittest.TestCase):
    def test_clean_row_logs_only_clean(self):
        self.assertEqual(attack_log_fields({"query": "q"}), {"attack_condition": "clean"})

    def test_attacked_row_logs_real_condition_and_slots(self):
        row = {
            "source_qa_id": "eval-1",
            "attack_condition": "correct_content_wrong_date_0d_control",
            "attack_protocol_version": "v2",
            "poison_count": 2,
            "attack_metadata": {"attack_type": "correct_content_wrong_date", "seed": 123,
                                "target_indices": [4, 7], "target_doc_ids": ["a", "b"],
                                "actual_poison_count": 2},
        }
        fields = attack_log_fields(row)
        self.assertEqual(fields["attack_condition"], "correct_content_wrong_date_0d_control")
        self.assertEqual(fields["source_qa_id"], "eval-1")
        self.assertEqual(fields["attack_seed"], 123)
        self.assertEqual(fields["poison_count"], 2)
        self.assertEqual(fields["poison_target_doc_ids"], ["a", "b"])


class TestModelRevisions(unittest.TestCase):
    def test_all_three_models_are_pinned_to_full_shas(self):
        revisions = model_revisions()
        self.assertEqual(set(revisions), {"mistralai/Mistral-7B-Instruct-v0.2",
                                          "facebook/contriever", "BAAI/bge-reranker-base"})
        for rev in revisions.values():
            self.assertEqual(len(rev), 40)

    def test_branch_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "revs.yaml"
            path.write_text(yaml.safe_dump({"models": {"x/y": {"revision": "main"}}}))
            with self.assertRaises(ValueError):
                model_revisions(path)


class TestRunMetadata(unittest.TestCase):
    def test_config_hash_changes_with_revision(self):
        def meta(rev):
            return build_run_metadata(
                experiment="E1", pool_name="p", pool_path=CLEAN, params={"top_k": 5},
                models={"generator": {"name": "m", "pinned_revision": rev, "loaded_revision": rev}},
                config_files={}, torch_seed=0, attack_base_seed=42, protocol_version="v2",
                git={"commit": "x", "dirty": False}, environment={})
        self.assertNotEqual(meta("a" * 40)["config_hash"], meta("b" * 40)["config_hash"])
        self.assertEqual(meta("a" * 40)["pool_sha256"], meta("a" * 40)["pool_sha256"])

    def test_json_hash_is_key_order_independent(self):
        self.assertEqual(sha256_json({"a": 1, "b": 2}), sha256_json({"b": 2, "a": 1}))


def _stub_missing_modules():
    """Install minimal stand-ins for Kaggle-only packages that are missing."""
    stubs = {}
    for name in ("transformers", "torch", "rank_bm25"):
        try:
            importlib.import_module(name)
        except ImportError:
            stubs[name] = types.ModuleType(name)
    if "transformers" in stubs:
        for attr in ("AutoModelForCausalLM", "AutoTokenizer", "BitsAndBytesConfig", "AutoModel"):
            setattr(stubs["transformers"], attr, object)
    if "torch" in stubs:
        stubs["torch"].float16 = None
    if "rank_bm25" in stubs:
        class BM25Okapi:
            def __init__(self, corpus):
                self.corpus = corpus

            def get_scores(self, query):
                return [len(set(query) & set(doc)) for doc in self.corpus]
        stubs["rank_bm25"].BM25Okapi = BM25Okapi
    return stubs


@unittest.skipUnless(POOL.exists(), "v2 pilot pools not built")
class TestDriverLogsRealCondition(unittest.TestCase):
    def run_e1(self, input_path, run_metadata=None):
        stubs = _stub_missing_modules()
        with mock.patch.dict(sys.modules, stubs):
            sys.path.insert(0, str(ROOT / "scripts"))
            try:
                for name in [m for m in sys.modules if m in ("run_baseline_streamingqa",
                             "src.retrieval.bm25", "src.generation.generate",
                             "src.eval.evaluator")]:
                    del sys.modules[name]
                driver = importlib.import_module("run_baseline_streamingqa")
            finally:
                sys.path.pop(0)

            def tokenizer(text):
                return {"input_ids": text.split()}

            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(driver, "generate_answer", return_value="Five."):
                log = Path(tmp) / "log.jsonl"
                driver.run_baseline_streamingqa(model=object(), tokenizer=tokenizer,
                                                input_path=str(input_path), log_path=str(log),
                                                run_metadata=run_metadata)
                rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        for name in ("run_baseline_streamingqa", "src.retrieval.bm25",
                     "src.generation.generate", "src.eval.evaluator"):
            sys.modules.pop(name, None)
        return rows

    def test_attacked_pool_rows_record_condition_and_metadata(self):
        rows = self.run_e1(POOL, run_metadata={"config_hash": "abc", "pool": "fabricated_fresh_n2"})
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row["attack_condition"], "fabricated_fresh")
            self.assertEqual(row["poison_count"], 2)
            self.assertEqual(len(row["poison_target_doc_ids"]), 2)
            self.assertTrue(row["source_qa_id"].startswith("eval-"))
            self.assertEqual(row["run_metadata"]["config_hash"], "abc")

    def test_clean_input_still_logs_clean_without_extra_fields(self):
        rows = self.run_e1(CLEAN)
        for row in rows:
            self.assertEqual(row["attack_condition"], "clean")
            self.assertNotIn("run_metadata", row)
            self.assertNotIn("attack_seed", row)


if __name__ == "__main__":
    unittest.main()
