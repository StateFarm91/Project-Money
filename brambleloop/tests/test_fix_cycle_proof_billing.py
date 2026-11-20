"""FIX-CYCLE-PROOF-BILLING: seasonal.cycle_proof re-billed the same request and died unclassified.

Production a4952711 / Batch 18, 2026-11-20 22:05Z:

* `paid_call_dedupe` FAIL -- `anthropic.messages` fingerprint db5496af2005 billed 6 times
  across seasonal.cycle_proof jobs 70594, 70762, 72111, 72527; `model.probe` fingerprint
  beff7c26565a billed twice (jobs 72529, 72706).
* `weekly_jobs`: seasonal.cycle_proof dead after its last success.
* dead letters `seasonal.cycle_proof:unclassified` x7.

What these prove, through the real worker, queue and paid-call guard (only the HTTP transport
`AnthropicProvider._send` and the cycle body are stubs):

1. a redriven dead letter and a re-enqueued proof job serve the paid answer again (replay)
   and bill CA$0 -- per job (checkpoint) and across jobs (paid-call store);
2. the error that read `unclassified` -- the reclaim path's " | lease expired, retries
   exhausted", which carries no class -- is now `LeaseExpired`, legacy rows included, and a
   paid-call refusal inside the cycle is an audited refusal, never a dead letter;
3. weekly completion holds: a proof that failed after its paid step completes on its retry
   and `weekly_jobs` reads it completing;
4. a spending dead letter with billed-but-unresolved spend and no checkpoint is not redriven;
5. model.probe is not re-billed because another job's call timed out;
6. mutations: with the cross-job replay switched off, or the redrive guard bypassed, the
   assertions above fail (each mutation is killed).
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _tmp; _tmp.install()  # noqa: E402,E702

from r2_autonomy_harness import SRC, run_tests  # noqa: E402,F401
from r2_autonomy_harness import boot as _sqlite_boot  # noqa: E402

_MAKE_DB = None   # set to a Postgres factory for the production-shaped leg


def boot(prefix: str = "fixcp-"):
    return _MAKE_DB() if _MAKE_DB is not None else _sqlite_boot(prefix)

os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-not-a-secret")

from brambleloop.runtime import release  # noqa: E402,F401 - registers the handlers

JT = "seasonal.cycle_proof"
REPORT = {"steps": [{"step": "assets", "state": "ran", "evidence": {"slug": "cycle-x"}}],
          "complete": True, "weakest_link": None, "customer_can_finish_in_time": True}


class _Transport:
    def __init__(self):
        self.sent = 0

    def __call__(self, provider, payload, key):
        from brambleloop.gateway.model_gateway import ModelResponse

        self.sent += 1
        return ModelResponse(text='{"concepts": [{"title": "Fern"}]}', provider=provider.name,
                             model=provider.model, input_tokens=900, output_tokens=700,
                             latency_ms=1.0)


class _Patch:
    def __init__(self):
        self.saved = []

    def set(self, obj, name, value):
        self.saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self.saved):
            setattr(obj, name, value)


def _install(p: _Patch, *, fail_after_paid: list):
    """Real ModelGateway + AnthropicProvider; fake HTTP; a cycle that asks one paid question
    and then (while `fail_after_paid` holds items) raises a defect after paying."""
    from brambleloop.gateway import failover
    from brambleloop.gateway.anthropic import AnthropicProvider
    from brambleloop.gateway.model_gateway import ModelGateway
    from brambleloop.seasonal import cycle

    transport = _Transport()
    p.set(AnthropicProvider, "_send",
          lambda self, payload, key, **kw: transport(self, payload, key))

    def job_gateway(db, *a, registry=None, job_id=None, **k):
        return ModelGateway([AnthropicProvider()], registry=registry, job_id=job_id)

    p.set(failover, "job_gateway", job_gateway)

    def run(db, *, gateway, asset_maker):
        gateway.complete_json(_prompt_ref(),
                              agent="creative_director", values=_values(),
                              required=("concepts",))
        if fail_after_paid:
            raise fail_after_paid.pop(0)
        return dict(REPORT)

    p.set(cycle, "run", run)
    return transport


def _prompt_ref():
    from brambleloop.creative import prospecting

    return prospecting.PROMPT


def _values():
    from brambleloop.gateway import prompts as prompt_registry

    prompt = prompt_registry.get(_prompt_ref())
    names = getattr(prompt, "variables", None) or ()
    vals = {n: "x" for n in names}
    vals.update({"form": "hat", "occasion": "Christmas", "make_lane": "quick", "count": 6,
                 "evidence": "e", "constructions": "top_down", "feelings": "warm",
                 "recipients": "her", "occasions": "christmas", "motif_grammar": "m",
                 "silhouette": "s", "brief": "b"})
    return vals


def _queue(db):
    from brambleloop.queue.durable import JobQueue

    return JobQueue(db, lease_seconds=60)


def _agent():
    from brambleloop.runtime.worker import CADENCES

    return next(a for _n, a, jt, _p in CADENCES if jt == JT)


def _drive(db, job_id, worker):
    from brambleloop.core.models import Job

    with db.session() as s:
        s.get(Job, job_id).run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    worker.run_once()
    with db.session() as s:
        row = s.get(Job, job_id)
        s.expunge(row)
    return row


def _billed_for(db, job_id) -> float:
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        return sum(float(r.amount_cad or 0) for r in s.scalars(
            select(CostEntry).where(CostEntry.job_id == job_id))
            if (r.detail or {}).get("billing") != "replayed_not_billed")


def _evidence(db):
    from brambleloop.ops import production_evidence as pe

    return pe.paid_calls(db, now=datetime.now(timezone.utc))


# --- 1. a redrive serves a replay and bills 0 -------------------------------------------------

def _scenario(cross_job: bool = True):
    from brambleloop.core.models import JobStatus
    from brambleloop.gateway import paid_calls
    from brambleloop.runtime.worker import Worker

    db = boot("fixcp-")
    p = _Patch()
    saved_windows = dict(paid_calls.CROSS_JOB_REPLAY)
    if not cross_job:
        paid_calls.CROSS_JOB_REPLAY.clear()
    try:
        # three defects after the paid step: attempts 1..3 fail, the job dead-letters
        transport = _install(p, fail_after_paid=[RuntimeError("defect after paying")] * 3)
        q = _queue(db)
        job = q.enqueue(_agent(), JT, {}, idempotency_key="cadence:cp:1")
        w = Worker(db, "w1")
        for _ in range(3):
            row = _drive(db, job.id, w)
        assert row.status == JobStatus.DEAD, (row.status, row.last_error)
        assert transport.sent == 1, f"retries repaid: {transport.sent}"
        moved = q.requeue_dead(ids=[job.id])
        assert moved["requeued"] == [job.id], moved     # OK spend + checkpoint: replayable
        row = _drive(db, job.id, w)
        assert row.status == JobStatus.DONE, (row.status, row.last_error)
        after_redrive = transport.sent
        # a NEW proof job for the same work (recovery rerun / cadence re-enqueue)
        job2 = q.enqueue(_agent(), JT, {}, idempotency_key="cadence:cp:2")
        row2 = _drive(db, job2.id, w)
        assert row2.status == JobStatus.DONE, (row2.status, row2.last_error)
        return db, transport.sent, after_redrive, job.id, job2.id
    finally:
        p.undo()
        paid_calls.CROSS_JOB_REPLAY.clear()
        paid_calls.CROSS_JOB_REPLAY.update(saved_windows)


def test_redrive_and_rerun_serve_the_replay_and_bill_zero():
    db, sent, after_redrive, j1, j2 = _scenario()
    assert after_redrive == 1, f"the redrive repaid ({after_redrive} sends)"
    assert sent == 1, f"the second proof job repaid ({sent} sends)"
    assert _billed_for(db, j2) == 0.0, _billed_for(db, j2)
    ev = _evidence(db)
    assert ev["repeated_billed_requests"] == 0, ev["repeated"]
    assert ev["replays_served_in_window"] >= 1, ev


# --- 2. the error that read `unclassified` is classified ---------------------------------------

def test_lease_exhaustion_dead_letter_names_its_class():
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.ops.production_evidence import error_class

    db = boot("fixcp-lease-")
    q = _queue(db)
    job = q.enqueue(_agent(), JT, {})
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    with db.session() as s:   # a redriven job (last_error NULL) on its last attempt, lease lost
        row = s.get(Job, job.id)
        row.status, row.attempts, row.max_attempts = JobStatus.RUNNING, 3, 3
        row.lease_expires_at, row.leased_by, row.last_error = past, "dead-worker", None
    q.claim("w2")
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DEAD, row.status
        err = row.last_error
    assert err.startswith("LeaseExpired:"), err
    assert error_class(err) == "LeaseExpired", error_class(err)
    # the seven production rows: the legacy text, no class
    assert error_class(" | lease expired, retries exhausted") == "LeaseExpired"
    # a previous error is kept after the class
    job2 = q.enqueue(_agent(), JT, {}, idempotency_key="lease-2")
    with db.session() as s:
        row = s.get(Job, job2.id)
        row.status, row.attempts, row.max_attempts = JobStatus.RUNNING, 3, 3
        row.lease_expires_at, row.leased_by = past, "dead-worker"
        row.last_error = "TransientError: anthropic 529"
    q.claim("w2")
    with db.session() as s:
        err2 = s.get(Job, job2.id).last_error
    assert err2.startswith("LeaseExpired:") and "previous: TransientError" in err2, err2


def test_classifier_does_not_depend_on_what_the_reader_imported():
    code = ("import sys; sys.path.insert(0, %r)\n"
            "from brambleloop.ops.production_evidence import error_class\n"
            "print(error_class('PaidCallUnresolved: x'))\n" % str(SRC))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         timeout=120)
    assert out.stdout.strip().splitlines()[-1] == "PaidCallUnresolved", (out.stdout,
                                                                          out.stderr[-400:])


def test_a_paid_call_refusal_in_the_cycle_is_an_audited_refusal_not_a_dead_letter():
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, JobStatus
    from brambleloop.gateway.paid_calls import PaidCallUnresolved
    from brambleloop.runtime.worker import Worker

    db = boot("fixcp-ref-")
    p = _Patch()
    try:
        _install(p, fail_after_paid=[PaidCallUnresolved("job 1's call has no known outcome")])
        job = _queue(db).enqueue(_agent(), JT, {})
        row = _drive(db, job.id, Worker(db, "w"))
    finally:
        p.undo()
    assert row.status == JobStatus.DONE, (row.status, row.last_error)
    assert row.outputs["refused"] == "paid_call_reconciliation", row.outputs
    with db.session() as s:
        audits = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "seasonal.cycle_proof_refused")))
    assert audits and audits[-1].detail["waiting_on"] == "paid_call_reconciliation"


def test_a_real_defect_still_dead_letters_with_its_class():
    """Never a silent pass: an unknown exception is not swallowed by the refusal paths."""
    from brambleloop.core.models import JobStatus
    from brambleloop.ops.production_evidence import error_class
    from brambleloop.runtime.worker import Worker

    db = boot("fixcp-defect-")
    p = _Patch()
    try:
        _install(p, fail_after_paid=[KeyError("steps")] * 3)
        job = _queue(db).enqueue(_agent(), JT, {})
        w = Worker(db, "w")
        for _ in range(3):
            row = _drive(db, job.id, w)
    finally:
        p.undo()
    assert row.status == JobStatus.DEAD, row.status
    assert error_class(row.last_error) == "KeyError", row.last_error[:120]


# --- 3. weekly completion holds -----------------------------------------------------------------

def test_weekly_completion_holds_after_a_failed_paid_attempt():
    from brambleloop.core.models import JobStatus
    from brambleloop.ops import production_evidence as pe
    from brambleloop.runtime.worker import Worker

    db = boot("fixcp-weekly-")
    p = _Patch()
    try:
        transport = _install(p, fail_after_paid=[RuntimeError("defect after paying")])
        job = _queue(db).enqueue(_agent(), JT, {})
        w = Worker(db, "w")
        first = _drive(db, job.id, w)
        assert first.status == JobStatus.FAILED, first.status
        row = _drive(db, job.id, w)
    finally:
        p.undo()
    assert row.status == JobStatus.DONE, (row.status, row.last_error)
    assert transport.sent == 1, transport.sent
    weekly = pe.weekly_jobs(db, now=datetime.now(timezone.utc))
    mine = next(r for r in weekly["weekly_job_types"] if r["job_type"] == JT)
    assert mine["completing"] is True and mine["dead_after_last_success"] is False, mine


# --- 4. a spending dead letter with unreplayable spend is not redriven --------------------------

def _dead_spender(db, outcome="UNCERTAIN"):
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.gateway import paid_calls

    paid_calls.ensure_table(db)
    job = _queue(db).enqueue(_agent(), JT, {}, idempotency_key=f"dead-{outcome}")
    with db.session() as s:
        row = s.get(Job, job.id)
        row.status, row.last_error = JobStatus.DEAD, "RuntimeError: died"
        s.add(paid_calls.PaidCallRecord(key=f"k-{job.id}", effect="anthropic.messages",
                                        job_id=job.id, job_type=JT, fingerprint="f" * 64,
                                        outcome=outcome, error="TimeoutError: read"))
    return job.id


def test_spending_dead_letter_without_a_replayable_checkpoint_is_not_redriven():
    from brambleloop.queue import checkpoints

    db = boot("fixcp-guard-")
    jid = _dead_spender(db)
    out = _queue(db).requeue_dead(ids=[jid])
    assert out["requeued"] == [] and "no checkpoint" in out["skipped"][0]["reason"], out
    checkpoints.ensure_table(db)
    with db.session() as s:   # what an earlier attempt checkpointed while it ran
        s.add(checkpoints.JobCheckpoint(job_id=jid, key="cycle_report",
                                        state={"report": REPORT}))
    out = _queue(db).requeue_dead(ids=[jid])
    assert out["requeued"] == [jid], out


def test_recovery_rerun_refuses_the_same_spending_dead_letter():
    from brambleloop.ops import recovery
    from brambleloop.runtime.worker import CADENCES

    db = boot("fixcp-rec-")
    _dead_spender(db)
    cadence = next(n for n, _a, jt, _p in CADENCES if jt == JT)
    try:
        out = recovery.rerun_department_cycle(db, cadence, actor="owner", request_id="r1")
    except recovery.RecoveryRefused as exc:
        assert "pay again" in str(exc), exc
        return
    assert "pay again" in str(out) and "redrove_dead_letter" not in str(out), out


# --- 5. model.probe is not re-billed by another job's timeout ----------------------------------

def test_probe_reuse_survives_another_jobs_timeout():
    from brambleloop.core.models import AuditLog
    from brambleloop.gateway import anthropic as gw
    from brambleloop.gateway.paid_calls import PaidCallRecord, ensure_table

    db = boot("fixcp-probe-")
    ensure_table(db)
    calls = []

    def fake(db_, *, job_id=None, now=None, **kw):
        calls.append(now)
        record = {"at": now.isoformat(), "model": gw.PROBE_MODEL,
                  "key_fp": gw.key_fingerprint(), "ok": True, "reason": ""}
        with db_.session() as s:
            s.add(AuditLog(actor="orchestrator", action="model.probe", artifact="stub",
                           detail=record))
        return record

    real = gw.probe
    gw.probe = fake
    t0 = datetime.now(timezone.utc) - timedelta(hours=10)
    try:
        gw.probe_if_due(db, now=t0)
        with db.session() as s:   # a cycle_proof generation timed out after the probe
            s.add(PaidCallRecord(key="k-to", effect="anthropic.messages", job_id=72527,
                                 job_type=JT, fingerprint="d" * 64, outcome="UNCERTAIN",
                                 error="TimeoutError: The read operation timed out",
                                 at=t0 + timedelta(hours=1)))
        out = gw.probe_if_due(db, now=t0 + timedelta(hours=6))
        assert len(calls) == 1 and out.get("reused"), (calls, out)
        with db.session() as s:   # the account refused: that does contradict
            s.add(PaidCallRecord(key="k-pu", effect="anthropic.messages", job_id=72528,
                                 job_type=JT, fingerprint="e" * 64, outcome="DECLINED",
                                 error="ProviderUnusable: anthropic 400: credit balance",
                                 at=t0 + timedelta(hours=7)))
        gw.probe_if_due(db, now=t0 + timedelta(hours=8))
        assert len(calls) == 2, calls
    finally:
        gw.probe = real


# --- 6. mutations are killed --------------------------------------------------------------------

def test_mutation_cross_job_replay_off_is_killed():
    """With the cross-job replay removed, the second proof job pays again: the assertion in
    test 1 (`sent == 1`) would fail, so the mutation is detected."""
    _db, sent, after_redrive, _j1, _j2 = _scenario(cross_job=False)
    assert after_redrive == 1, "the per-job checkpoint/replay still serves the redrive"
    assert sent == 2, f"mutation survived: the new job did not repay ({sent})"


def test_mutation_redrive_guard_bypassed_is_killed():
    from brambleloop.queue import durable

    db = boot("fixcp-mut-")
    jid = _dead_spender(db, outcome="UNCERTAIN")
    real = durable.unreplayable_spend
    durable.unreplayable_spend = lambda s, job: None
    try:
        out = _queue(db).requeue_dead(ids=[jid])
    finally:
        durable.unreplayable_spend = real
    assert out["requeued"] == [jid], "mutation survived: the guard was not what refused"


PG_TESTS = ("test_redrive_and_rerun_serve_the_replay_and_bill_zero",
            "test_lease_exhaustion_dead_letter_names_its_class",
            "test_spending_dead_letter_without_a_replayable_checkpoint_is_not_redriven",
            "test_recovery_rerun_refuses_the_same_spending_dead_letter",
            "test_weekly_completion_holds_after_a_failed_paid_attempt")


def _postgres_leg() -> int:
    """The reclaim SQL (substr/coalesce concatenation) and the redrive guard's savepoints run
    on Postgres in production; run those tests there too when a local toolchain exists."""
    global _MAKE_DB
    try:
        from test_codex_v0_postgres import _disposable_cluster
        from test_eng_stale_rebuild_loop import _pg_factory
    except Exception:  # noqa: BLE001
        print("SKIP [postgres] helpers unavailable")
        return 0
    fails = 0
    with _disposable_cluster():
        raw = os.environ.get("CODEX_V0_TEST_DATABASE_URL")
        if not (raw and os.environ.get("CODEX_V0_DISPOSABLE_DATABASE") == "yes"):
            print("SKIP [postgres] no local PostgreSQL toolchain: ran on SQLite only")
            return 0
        _MAKE_DB = _pg_factory(raw)
        try:
            for name in PG_TESTS:
                try:
                    globals()[name]()
                    print("OK   [postgres]", name)
                except Exception as e:  # noqa: BLE001
                    import traceback
                    traceback.print_exc()
                    fails += 1
                    print("FAIL [postgres]", name, repr(e))
        finally:
            _MAKE_DB = None
    return fails


if __name__ == "__main__":
    pg_fails = _postgres_leg()
    print(f"[postgres] {pg_fails} failing")
    if pg_fails:
        sys.exit(1)
    run_tests(globals())
