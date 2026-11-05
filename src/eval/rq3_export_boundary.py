"""G2-I4 extension: preserve G2-I3 guard; additionally prohibit all judging/inference."""
import sys
import types
from src.eval.no_execution_boundary import Boundary, ExecutionBlocked


class ExportBoundary(Boundary):
    prefixes = Boundary.prefixes + ("src.eval.answer_judge", "src.eval.answer_judge_v2",
        "src.eval.freshqa_judge", "src.eval.synthetic_analysis")
    names = Boundary.names | {"judge_answer", "judge_batch", "validate_batch", "call_api",
        "factorial_effects", "paired_difference", "rate", "cluster_mean", "holm", "exact_sign_flip"}

    def profile(self, frame, event, arg):
        filename=frame.f_code.co_filename.replace("\\","/")
        if (filename.endswith("/scripts/validate_g2_i4_no_execution.py")
                and frame.f_code.co_name in {"Health","pytest_runtest_setup","pytest_runtest_teardown"}):
            return
        super().profile(frame,event,arg)

    def report(self):
        return {**super().report(),"guard":"g2-i4-no-execution/v1",
                "judging_and_statistical_inference":"NOT_PERMITTED",
                "blocked_backend_modules_loaded":[n for n in sys.modules if any(n==p or n.startswith(p+".")
                    for p in self.prefixes)]}

    def probe(self,operation):
        if operation not in ("judge","statistics"):
            return super().probe(operation)
        sys.setprofile(self.profile)
        try:
            def inert_body():
                raise AssertionError("inert probe must never execute")
            name="judge_answer" if operation=="judge" else "factorial_effects"
            file="/src/eval/answer_judge_v2.py" if operation=="judge" else "/src/eval/synthetic_analysis.py"
            types.FunctionType(inert_body.__code__.replace(co_name=name,co_filename=file),globals())()
        finally:
            sys.setprofile(self.profile)


def install():
    guard=ExportBoundary()
    if any(n==p or n.startswith(p+".") for n in sys.modules for p in guard.prefixes):
        raise ExecutionBlocked("prohibited backend/judge/estimator already imported")
    sys.meta_path.insert(0,guard)
    sys.addaudithook(guard.audit)
    sys.setprofile(guard.profile)
    return guard
