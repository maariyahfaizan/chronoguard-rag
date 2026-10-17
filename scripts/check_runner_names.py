import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.eval.config_loader import experiment_params
for e in ("E1", "E2", "E3", "E4"):
    p = experiment_params(e)
    print(e, sorted(p.keys()))
print("generator_model:", experiment_params("E4").get("generator_model"))
print("reranker_model:", experiment_params("E4").get("reranker_model"))

from src.retrieval.reranker import load_reranker
print("load_reranker import OK")