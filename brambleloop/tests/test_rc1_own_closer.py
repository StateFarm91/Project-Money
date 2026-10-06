"""A3-03: launch.readiness closes only the owner actions it owns, on a condition re-check.

Repro of the independent audit (audit3/close.py): seven owner actions raised by other
subsystems, whose conditions still hold, were all marked done by one readiness run.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

FOREIGN_KEYS = [
    "correction_notice:foo@v1",
    "etsy.exercise.stranded_draft.123",
    "search_visibility:launch_week",
    "ads.scale:foo",
    "club:launch_decision",
    "reinvestment:2026-10",
    "spend.ceiling.2026-10",
]


def _run(keys):
    from sqlalchemy import select

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import Job, OwnerAction
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    tmp = tempfile.mkdtemp(prefix="rc1own-close-")
    try:
        db = Database(f"sqlite:///{tmp}/c.db")
        db.create_all()
        Registry(db).seed_defaults()
        with db.session() as s:
            for k in keys:
                s.add(OwnerAction(requirement_key=k, action="x " + k, reason="r",
                                  max_cost_cad=0, minutes=5, consequence_of_delay="c",
                                  blocks=""))
        JobQueue(db).enqueue("orchestrator", "launch.readiness", {"artifact_dir": tmp + "/art"})
        Worker(db, "rc1own", job_types=["launch.readiness"]).run_once()
        with db.session() as s:
            job = s.scalars(select(Job).where(Job.job_type == "launch.readiness")).first()
            outputs = dict(job.outputs or {})
            status = str(job.status)
            done = {a.requirement_key: a.done for a in s.scalars(select(OwnerAction))}
        return status, outputs, done
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_foreign_owner_actions_stay_open():
    status, outputs, done = _run(FOREIGN_KEYS + ["physical_calibration"])
    assert "DONE" in status.upper(), status
    closed = outputs.get("owner_actions_closed", [])
    for k in FOREIGN_KEYS:
        assert k not in closed, f"readiness closed {k}, which it does not own"
        assert done[k] is False, k
    # A readiness-owned key whose condition re-check passes still closes: the ask for the
    # calibration sample is withdrawn (owner parked it), so its row is satisfied.
    assert "physical_calibration" in closed
    assert done["physical_calibration"] is True


def test_readiness_owned_key_whose_condition_holds_stays_open():
    # `brand_clearance` is readiness-owned but still requested (no trademark screen), so it is
    # in `wanted`; and a credential still rotation-required must not be closed either.
    from brambleloop.ops import credential_register as cr
    from brambleloop.runtime.release import readiness_may_close

    pending = [e for e in cr.REGISTER if e.status == cr.ROTATION_REQUIRED]
    for e in pending:  # vacuity-ok: an empty register is covered by the not-in-register line
        assert readiness_may_close(cr.KEY_PREFIX + e.name, None) is False
    assert readiness_may_close(cr.KEY_PREFIX + "NOT_IN_REGISTER", None) is False
    # Not assessed => not provably cleared.
    assert readiness_may_close("etsy_shop", None) is False
    for k in FOREIGN_KEYS:
        assert readiness_may_close(k, None) is False


if __name__ == "__main__":
    # One `OK  <name>` / `FAIL <name>` line per test, in definition order, and a nonzero exit
    # on any failure: run_tests.sh counts ^OK lines, so a bare trailing "suite: OK" line would
    # leave every pass here out of the total.
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
