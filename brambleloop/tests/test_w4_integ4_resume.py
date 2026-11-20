"""W4-INTEG4: security review of 17bc373, M1 -- a resumed experiment never resends a paid render.

The paid-call guard keys a call by its occurrence within ONE execution. A reclaimed experiment
job that resumed at attempt N reused attempt 1's key: with attempt 1 DECLINED (refused before
the provider accepted it) and attempt 2 accepted and in flight when the worker was lost, the
resumed execution matched the DECLINED record, was "asked again", and sent a second paid
render while attempt 2's billing was still unknown. Now the guard's own records decide: a
resumed run sends a new attempt only if every earlier paid call of the job was DECLINED.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_integ4_resume.py
"""
from __future__ import annotations

import sys

import test_w4_credhealth as CH  # noqa: E402 - sets up the app, DB and BFL stand-in

from brambleloop.core.resilience import TransientError  # noqa: E402

C, CE, PC, DB = CH.C, CH.CE, CH.PC, CH.DB


def test_m1_declined_then_in_flight_is_never_resent_on_resume():
    out, job, inputs = CH._claimed_run()

    class DeclinedThenKilled(CE.Transport):
        def post(self, *a, **k):
            if not self.posts:
                self.posts.append({"declined": True})
                raise TransientError("BFL 503 before acceptance")   # attempt 1: DECLINED
            return super().post(*a, **k)                             # attempt 2: accepted

        def get(self, *a, **k):
            raise KeyboardInterrupt("worker lost while polling attempt 2")

    t = DeclinedThenKilled()
    with t, PC.job_scope(DB, job):
        try:
            C.run_job(DB, inputs, job_id=job.id)
            raise AssertionError("the simulated kill did not happen")
        except KeyboardInterrupt:
            pass
    assert len(t.posts) == 2, t.posts                        # attempt 2 reached the provider
    outcomes = [r["outcome"] for r in PC.rows(DB, job_id=job.id)]
    assert outcomes[0] == PC.DECLINED and outcomes[1] in (PC.PENDING, PC.UNCERTAIN), outcomes
    mid = C.get_run(DB, out["run_id"])
    assert mid["status"] == "running" and mid["attempts"] == 2 and not mid["image_sha256"]

    t2 = CE.Transport()
    with t2, PC.job_scope(DB, job):
        got = C.run_job(DB, inputs, job_id=job.id)
    assert t2.posts == [], "a resumed run resent a paid render while billing was unknown"
    assert got["settled"] == "billing_unknown" and got["image"] is False, got
    run = C.get_run(DB, out["run_id"])
    assert run["status"] == "failed" and "not resent" in run["why"], run
    after = [r for r in PC.rows(DB, job_id=job.id)]
    assert all(r["outcome"] != PC.PENDING for r in after), after   # an in-flight call counted
    CE._settle_active()


def test_m1_unreadable_records_never_resend():
    out, job, inputs = CH._claimed_run()
    C._update(DB, out["run_id"], status="running", job_id=job.id, attempts=1,
              generation_spent_cad=0.14)
    real = PC.ensure_table

    def broken(db):
        raise RuntimeError("paid_call_records unreadable")

    PC.ensure_table = broken
    try:
        t = CE.Transport()
        with t, PC.job_scope(DB, job):
            got = C.run_job(DB, inputs, job_id=job.id)
    finally:
        PC.ensure_table = real
    assert t.posts == [] and got["settled"] == "billing_unknown", got
    CE._settle_active()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:1500])
            traceback.print_exc(limit=6)
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
