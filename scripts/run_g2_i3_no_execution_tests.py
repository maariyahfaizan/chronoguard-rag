"""Fixed test allowlist. Review before running; no inherited pytest hooks/plugins."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ALLOWLIST=("tests/g2_i3/test_context_trace_adapter.py",)
SAFE_IMPORTS={"copy","json","sys","pytest","src.eval.no_execution_boundary","src.eval.request_context_traces"}


def preflight():
    checked={}
    for relative in ALLOWLIST:
        path=ROOT/relative
        tree=ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            if any(n not in SAFE_IMPORTS for n in names):
                raise RuntimeError("unreviewed test import")
            if isinstance(node,ast.Call):
                name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ""
                if name in {"retrieve_best","generate_answer","generate","from_pretrained","apply_attack",
                            "urlopen","connect","Popen","system","setprofile","exec","eval","compile"}:
                    raise RuntimeError("prohibited/unreviewed direct test operation")
        checked[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    return checked


if __name__=="__main__":
    reviewed=preflight()
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1"
    os.environ["PYTEST_ADDOPTS"]=""
    os.environ["PYTEST_PLUGINS"]=""
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(ROOT))
    from src.eval.no_execution_boundary import install
    guard=install()
    sys._chronoguard_g2_i3_boundary=guard
    from src.eval.no_execution_boundary import ExecutionBlocked
    # Certify the guard before collecting any test. These are inert tripwires.
    for operation in ("retrieval","generation","attack","model_import","network","process"):
        try:
            guard.probe(operation)
        except ExecutionBlocked:
            pass
        else:
            raise RuntimeError("BLOCKED: boundary self-check did not deny operation")
    if not guard.report()["profile_active"]:
        raise RuntimeError("BLOCKED: profile guard inactive before collection")
    # No project conftest, ancestor config or broad test collection is used.
    temp=Path(tempfile.mkdtemp(prefix="chronoguard_g2_i3_tests_")).resolve()
    config=temp/"pytest.ini"
    config.write_text("[pytest]\n",encoding="utf-8")
    import pytest
    class Health:
        def pytest_runtest_setup(self,item):
            if not guard.report()["profile_active"]:
                raise RuntimeError("BLOCKED: lost boundary enforcement")
        def pytest_runtest_teardown(self,item):
            if not guard.report()["profile_active"]:
                raise RuntimeError("BLOCKED: boundary disabled by unexpected denial")
    args=["-c",str(config),"--rootdir",str(ROOT),"--noconftest","-p","no:cacheprovider","--maxfail=1",
          "--basetemp",str(temp/"cases"),"-q"]+[str(ROOT/p) for p in ALLOWLIST]
    code=pytest.main(args,plugins=[Health()])
    report={"allowlist":list(ALLOWLIST),"test_source_hashes":reviewed,"pytest_exit_code":code,
            "external_plugins_disabled":True,"conftest_disabled":True,"project_test_config_disabled":True,
            "boundary":guard.report()}
    print("BOUNDARY_REPORT_JSON="+json.dumps(report,sort_keys=True))
    raise SystemExit(code)
