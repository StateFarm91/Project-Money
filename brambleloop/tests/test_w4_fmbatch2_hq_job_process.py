"""INTEG7 review R-2: the HQ worker declares itself a job process (AGENTS M-2R) before it runs
anything, so it can never sign a storefront grant and the signing key leaves its environment.

On a line that carries `ops.storefront_authority` the real module is checked; on one that does
not (FMBATCH2 before the INTEG7 merge) a stand-in module proves the call order.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.app import hq_worker  # noqa: E402

MOD = "brambleloop.ops.storefront_authority"


def _run_main(order):
    class _W:
        def __init__(self, *a, **k):
            order.append("worker")

        def run(self):
            order.append("run")

    os.environ[hq_worker.ENV_TYPES] = "ops.heartbeat"
    with patch("brambleloop.runtime.worker.Worker", _W), \
            patch.object(hq_worker, "plan", lambda *a, **k: {"job_types": ["ops.heartbeat"]}), \
            patch("brambleloop.core.db.Database", lambda *a, **k: object()), \
            patch("brambleloop.core.phase.effective_phase", lambda db: "shadow"):
        assert hq_worker.main() == 0


def test_the_hq_worker_marks_itself_a_job_process_before_any_job_runs():
    try:
        import importlib

        real = importlib.import_module(MOD)
    except ImportError:
        real = None
    order: list[str] = []
    if real is not None:
        os.environ[real.SIGNING_KEY_VAR] = "x"
        _run_main(order)
        assert real._JOB_PROCESS["is"] is True
        assert real.SIGNING_KEY_VAR not in os.environ
        assert real.signing_refusal()
        assert order == ["worker", "run"]
        return
    fake = types.ModuleType(MOD)
    fake.mark_job_process = lambda: order.append("marked") or True
    with patch.dict(sys.modules, {MOD: fake}):
        import brambleloop.ops as ops_pkg

        with patch.object(ops_pkg, "storefront_authority", fake, create=True):
            _run_main(order)
    assert order == ["marked", "worker", "run"], order


def _behavioural_scrub(module_name: str):
    """Review 5060fcc7 R9a: the HQ worker really scrubs this family's signing key and marks
    itself a job process -- behaviour, not a substring of the source."""
    import importlib

    mod = importlib.import_module(module_name)
    saved = dict(mod._JOB_PROCESS)
    try:
        mod._JOB_PROCESS["is"] = False
        os.environ[mod.SIGNING_KEY_VAR] = "x"
        _run_main([])
        assert mod._JOB_PROCESS["is"] is True, module_name
        assert mod.SIGNING_KEY_VAR not in os.environ, module_name
        assert mod.signing_refusal() and "runs jobs" in mod.signing_refusal(), module_name
    finally:
        mod._JOB_PROCESS.update(saved)
        os.environ.pop(mod.SIGNING_KEY_VAR, None)


def test_the_hq_worker_scrubs_the_owner_grant_signing_key():
    _behavioural_scrub("brambleloop.core.owner_grant_keys")


def test_the_hq_worker_scrubs_the_standing_policy_signing_key():
    _behavioural_scrub("brambleloop.ops.standing_policy")


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
