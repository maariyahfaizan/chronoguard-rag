"""Fail-closed development guard. No protected operation is mocked into success."""
import importlib.abc
import sys
import types


class ExecutionBlocked(RuntimeError):
    pass


class Boundary(importlib.abc.MetaPathFinder):
    prefixes = ("torch", "transformers", "sentence_transformers", "huggingface_hub",
                "requests", "urllib.request", "http.client", "src.retrieval",
                "src.generation.generate", "scripts.run_")
    names = {"retrieve_best", "encode_texts", "rerank", "generate_answer", "load_model",
             "load_dense_model", "load_reranker", "from_pretrained", "generate", "predict",
             "apply_attack", "apply_attacks", "_apply_attack_once", "build_pilot_pools"}

    def __init__(self):
        self.denied = {"imports":0, "calls":0, "network_or_process":0}

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p+".") or (p.endswith("_") and fullname.startswith(p))
               for p in self.prefixes):
            self.denied["imports"] += 1
            raise ExecutionBlocked("prohibited module import: " + fullname)

    def profile(self, frame, event, arg):
        if event != "call":
            return
        filename = frame.f_code.co_filename.replace("\\", "/")
        name = frame.f_code.co_name
        safe_helper_comprehension = (name == "<genexpr>" and frame.f_back is not None
            and frame.f_back.f_code.co_name == "build_prompt"
            and frame.f_back.f_code.co_filename == frame.f_code.co_filename)
        safe_test_controller = (filename.endswith("/scripts/run_g2_i3_no_execution_tests.py")
            and name in {"Health", "pytest_runtest_setup", "pytest_runtest_teardown"})
        prohibited = (name in self.names or name.startswith("_apply_")
            or "/src/retrieval/" in filename or ("/scripts/run_" in filename and not safe_test_controller)
            or (filename.endswith("/src/generation/generate.py") and name not in
                {"<module>", "build_prompt", "truncate_passage"} and not safe_helper_comprehension))
        if prohibited:
            self.denied["calls"] += 1
            raise ExecutionBlocked("prohibited call before body execution: " + name)

    def audit(self, event, args):
        if event.startswith(("socket.", "subprocess.", "urllib.Request", "os.system", "os.exec", "os.spawn")):
            self.denied["network_or_process"] += 1
            raise ExecutionBlocked("prohibited network/process event: " + event)

    def report(self):
        return {"guard":"g2-i3-no-execution/v1", "blocked_attempts":dict(self.denied),
                "profile_active":getattr(sys.getprofile(),"__self__",None) is self,
                "retrieval_generation_network_execution":"NOT_PERMITTED",
                "note":"negative tests intentionally trigger denials before operation bodies"}

    def probe(self, operation):
        """Harmless tripwires, never actual retrieval/model/network operations.

        A profile-callback exception clears Python's callback. Rearm in this
        reviewed finally block before returning the expected denial to pytest.
        Unexpected denials elsewhere fail the run; they are never suppressed.
        """
        sys.setprofile(self.profile)
        try:
            if operation == "model_import":
                import importlib
                importlib.import_module("transformers")
            elif operation in ("network", "process"):
                sys.audit("socket.connect" if operation=="network" else "subprocess.Popen", None)
            else:
                file,name={"retrieval":("/src/retrieval/bm25.py","retrieve_best"),
                           "generation":("/src/generation/generate.py","generate_answer"),
                           "attack":("/src/attacks/attack_pool.py","apply_attack")}[operation]
                def tripwire_body():
                    raise AssertionError("tripwire body must never execute")
                code=tripwire_body.__code__.replace(co_name=name,co_filename=file)
                types.FunctionType(code,globals())()
        finally:
            sys.setprofile(self.profile)


def install():
    guard = Boundary()
    if any(name == p or name.startswith(p+".") for name in sys.modules for p in guard.prefixes):
        raise ExecutionBlocked("prohibited backend already imported; boundary cannot be certified")
    sys.meta_path.insert(0, guard)
    sys.addaudithook(guard.audit)
    sys.setprofile(guard.profile)
    return guard
