"""Only reviewed G2-I5 tests; no inherited configuration or broad collection."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ALLOWLIST=("tests/g2_i5/test_canonical_analysis_input.py",)
SAFE_IMPORTS={"copy","json","sys","pytest","src.eval.no_execution_boundary","src.eval.canonical_analysis_input"}


def preflight():
    hashes={}
    for relative in ALLOWLIST:
        p=ROOT/relative;tree=ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            imports=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module] if isinstance(n,ast.ImportFrom) else []
            if any(name not in SAFE_IMPORTS for name in imports):raise RuntimeError("unreviewed test import")
            if isinstance(n,ast.Call):
                name=n.func.id if isinstance(n.func,ast.Name) else n.func.attr if isinstance(n.func,ast.Attribute) else ""
                if name in {"retrieve_best","generate_answer","generate","judge_answer","from_pretrained","apply_attack",
                    "urlopen","connect","Popen","system","setprofile","exec","eval","compile","factorial_effects",
                    "rate","paired_difference","cluster_mean","holm","exact_sign_flip"}:
                    raise RuntimeError("prohibited or unreviewed test call")
        hashes[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


if __name__=="__main__":
    hashes=preflight()
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1";os.environ["PYTEST_ADDOPTS"]="";os.environ["PYTEST_PLUGINS"]=""
    sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT))
    from src.eval.rq3_export_boundary import install
    from src.eval.no_execution_boundary import ExecutionBlocked
    guard=install();sys._chronoguard_g2_i5_boundary=guard
    for operation in ("retrieval","generation","attack","model_import","network","process","judge","statistics"):
        try:guard.probe(operation)
        except ExecutionBlocked:pass
        else:raise RuntimeError("BLOCKED: failed boundary self-check")
    if not guard.report()["profile_active"]:raise RuntimeError("BLOCKED: inactive guard")
    temp=Path(tempfile.mkdtemp(prefix="chronoguard_g2_i5_tests_")).resolve()
    config=temp/"pytest.ini";config.write_text("[pytest]\n",encoding="utf-8")
    import pytest
    class Health:
        def pytest_runtest_setup(self,item):
            if not guard.report()["profile_active"]:raise RuntimeError("BLOCKED: lost guard")
        def pytest_runtest_teardown(self,item):
            if not guard.report()["profile_active"]:raise RuntimeError("BLOCKED: disabled guard")
    args=["-c",str(config),"--rootdir",str(ROOT),"--noconftest","-p","no:cacheprovider","--maxfail=1",
          "--basetemp",str(temp/"cases"),"-q"]+[str(ROOT/p) for p in ALLOWLIST]
    result=pytest.main(args,plugins=[Health()])
    print("BOUNDARY_REPORT_JSON="+json.dumps({"allowlist":list(ALLOWLIST),"test_hashes":hashes,
        "pytest_exit_code":result,"boundary":guard.report(),"external_plugins_disabled":True,
        "conftest_disabled":True,"project_test_config_disabled":True},sort_keys=True))
    raise SystemExit(result)
