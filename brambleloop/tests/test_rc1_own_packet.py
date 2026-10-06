"""A3-07: the owner's launch packet and the launch.readiness handler reach the same verdict.

Before: packet.build called assess() without providers/storage durability and omitted the
off-device autonomy proof (#195), so it could read READY where the gate said NOT PROVEN.
"""
import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _db(tmp):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{tmp}/p.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _handler(db, tmp):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, Job
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker

    JobQueue(db).enqueue("orchestrator", "launch.readiness", {"artifact_dir": tmp + "/art"})
    Worker(db, "rc1own-pk", job_types=["launch.readiness"]).run_once()
    with db.session() as s:
        job = s.scalars(select(Job).where(Job.job_type == "launch.readiness")).first()
        audit = s.scalars(select(AuditLog).where(AuditLog.action == "launch.assessed")
                          .order_by(AuditLog.id.desc())).first()
        return dict(job.outputs or {}), dict(audit.detail or {})


def test_packet_verdict_equals_handler_verdict():
    from brambleloop.launch import packet as LP

    tmp = tempfile.mkdtemp(prefix="rc1own-pk-")
    saved = {k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "BRAMBLELOOP_PHASE")}
    try:
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-not-a-real-key-000000"  # env read only
        os.environ.pop("BRAMBLELOOP_PHASE", None)
        db = _db(tmp)
        outputs, detail = _handler(db, tmp)
        p = LP.build(db, sha="deadbeef", artifact_dir=tmp + "/art")
        q = p["owner_queue"]
        assert q["ready"] == outputs["ready"] == detail["ready"]
        assert q["readiness_ready_before_off_device_proof"] == \
            detail["ready_before_off_device_proof"]
        assert q["off_device_autonomy_proof"]["status"] == detail["off_device_proof"]["status"]
        assert q["providers"] == ["anthropic"]
        owner_keys = {o["key"] for o in q["owner_actions"]}
        handler_owner = set(detail["blocked_on_owner"])
        # every owner request the packet lists is a requirement the handler holds on the owner
        assert owner_keys <= handler_owner | set(
            detail["owner_actions_queued"]), (owner_keys, handler_owner)
        assert "Off-device autonomy proof" in LP.render_markdown(p)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)


def test_packet_cannot_be_ready_without_the_off_device_proof():
    """Readiness alone ready, autonomy NOT PROVEN: packet and handler both say not ready."""
    from brambleloop.build2 import autonomy
    from brambleloop.launch import packet as LP
    from brambleloop.launch import readiness as rd

    tmp = tempfile.mkdtemp(prefix="rc1own-pk2-")
    orig = rd.assess
    try:
        db = _db(tmp)
        rd.assess = lambda *a, **k: rd.Readiness(requirements=[])  # readiness.ready is True
        a = rd.launch_assessment(db, phase="shadow")
        assert a.readiness.ready is True
        assert a.off_device["status"] != autonomy.PROVEN
        assert a.ready is False
        q, err = LP._owner_queue(db, "shadow")
        assert err is None and q["ready"] is False, q
        assert q["off_device_autonomy_proof"]["status"] == a.off_device["status"]
    finally:
        rd.assess = orig
        shutil.rmtree(tmp, ignore_errors=True)


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
