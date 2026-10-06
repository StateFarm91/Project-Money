"""Wave-3 lane SPEND: a reclaimed or retried job never pays twice (F-307, F-339, F-474, F-659).

Every paid model/image call made inside a job is keyed write-ahead by (job, request,
occurrence) through `gateway.paid_calls` + `queue.effects`. No test here reaches a network:
the provider transport (`AnthropicProvider._send`) and the render call are fakes.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_spend_paid_calls.py
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from r2_autonomy_harness import SRC, boot, run_tests

os.environ.setdefault("ANTHROPIC_API_KEY", "k")   # presence only; `_send` is always faked

AGENT = "orchestrator"


class FakeTransport:
    """Counts what would have left the process. Never touches a socket."""

    def __init__(self, text='{"names": ["Fern", "Moss", "Bramble"]}', fail=None):
        self.sent, self.text, self.fail = 0, text, list(fail or [])

    def __call__(self, provider, payload, key):
        from brambleloop.gateway.model_gateway import ModelResponse

        self.sent += 1
        if self.fail:
            raise self.fail.pop(0)
        return ModelResponse(text=self.text, provider=provider.name, model=provider.model,
                             input_tokens=120, output_tokens=40, latency_ms=1.0)


def _install(fake):
    from brambleloop.gateway.anthropic import AnthropicProvider

    original = AnthropicProvider._send
    AnthropicProvider._send = lambda self, payload, key: fake(self, payload, key)
    return lambda: setattr(AnthropicProvider, "_send", original)


def _job(db, key):
    from brambleloop.queue.durable import JobQueue

    q = JobQueue(db, lease_seconds=60)
    q.enqueue(AGENT, "ops.queue_check", {"x": 1}, idempotency_key=key)
    return q.claim("W1")


def _gateway(db, job):
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway import anthropic as gw
    from brambleloop.gateway.anthropic import AnthropicProvider
    from brambleloop.gateway.model_gateway import ModelGateway

    return ModelGateway([AnthropicProvider(model=gw.PROBE_MODEL)], registry=Registry(db),
                        job_id=job.id)


def _ask(gateway):
    return gateway.complete_json("concept.naming@1", agent=AGENT,
                                 values={"category": "throw", "motifs": "fern",
                                         "season": "autumn"})


def _cost_rows(db, job_id=None):
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry

    with db.session() as s:
        q = select(CostEntry)
        if job_id is not None:
            q = q.where(CostEntry.job_id == job_id)
        return [(float(r.amount_cad), dict(r.detail or {})) for r in s.scalars(q)]


def _audits(db, action):
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog

    with db.session() as s:
        return list(s.scalars(select(AuditLog.detail).where(AuditLog.action == action)))


def test_outside_a_job_nothing_changes():
    from brambleloop.gateway import paid_calls

    db = boot()
    fake = FakeTransport()
    restore = _install(fake)
    try:
        job = _job(db, "spend-outside")
        gateway = _gateway(db, job)
        _ask(gateway)
        _ask(gateway)
    finally:
        restore()
    assert fake.sent == 2, "with no job scope every call is a plain call"
    assert paid_calls.rows(db) == [], paid_calls.rows(db)


def test_a_retried_attempt_replays_the_paid_answer_and_is_not_billed_again():
    from brambleloop.finance import spend_report
    from brambleloop.gateway import paid_calls

    db = boot()
    fake = FakeTransport()
    restore = _install(fake)
    try:
        job = _job(db, "spend-retry")
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            first = _ask(_gateway(db, job))
        job.attempts += 1                       # the queue's retry / reclaim: same job
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            second = _ask(_gateway(db, job))
    finally:
        restore()
    assert fake.sent == 1, f"the provider was asked {fake.sent} times for one job"
    assert first["names"] == second["names"]
    billed = [c for c in _cost_rows(db, job.id) if c[0] > 0]
    assert len(billed) == 1, _cost_rows(db, job.id)
    assert billed[0][1].get("paid_call_key"), "the bill names its write-ahead intent"
    assert second["_meta"]["cost_cad"] == 0.0
    rows = paid_calls.rows(db, job_id=job.id)
    assert len(rows) == 1 and rows[0]["outcome"] == "OK" and rows[0]["replays"] == 1, rows
    assert _audits(db, paid_calls.REPLAY_ACTION), "the replay is audited"
    assert _audits(db, "effect.duplicate_refused"), "the guard counted the duplicate"
    # The reservation the replayed attempt took came back: nothing is left held.
    from brambleloop.finance import reservations

    assert reservations.outstanding(db)["count"] == 0, reservations.outstanding(db)


def test_a_declined_call_may_be_asked_again_but_an_unknown_one_is_not():
    from brambleloop.core.resilience import TransientError
    from brambleloop.finance import spend_report
    from brambleloop.gateway import paid_calls

    db = boot()
    # Attempt 1: both tries are declined by the provider (HTTP 529) -> never billed.
    fake = FakeTransport(fail=[TransientError("anthropic 529: overloaded"),
                               TransientError("anthropic 529: overloaded")])
    restore = _install(fake)
    try:
        job = _job(db, "spend-declined")
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            try:
                _ask(_gateway(db, job))
                raise AssertionError("both tries were declined")
            except TransientError:
                pass
        assert {r["outcome"] for r in paid_calls.rows(db, job_id=job.id)} == {"DECLINED"}
        job.attempts += 1
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            _ask(_gateway(db, job))
    finally:
        restore()
    assert fake.sent == 3, "a declined request never billed, so the retry may ask"

    # A timeout: whether it billed is UNKNOWN -> counted at the estimate by the gateway,
    # and a later attempt does not re-send it (F-339).
    db = boot()
    fake = FakeTransport(fail=[TimeoutError("read timed out")])
    restore = _install(fake)
    try:
        job = _job(db, "spend-timeout")
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            _ask(_gateway(db, job))             # try 1 times out, try 2 answers
        sent_first = fake.sent
        job.attempts += 1
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            again = _ask(_gateway(db, job))     # replays both: the unknown and the answer
    finally:
        restore()
    assert sent_first == 2 and fake.sent == 2, fake.sent
    assert again["names"], again
    outcomes = sorted(r["outcome"] for r in paid_calls.rows(db, job_id=job.id))
    assert outcomes == ["OK", "UNCERTAIN"], outcomes
    from sqlalchemy import select

    from brambleloop.core.models import Incident

    with db.session() as s:
        sigs = [i for (i,) in s.execute(select(Incident.signature))]
    assert any(sig.startswith("paid_call.unresolved:") for sig in sigs), sigs


def test_a_stale_worker_stops_before_it_pays():
    from brambleloop.finance import spend_report
    from brambleloop.queue.effects import LeaseLost

    db = boot()
    fake = FakeTransport()
    restore = _install(fake)
    try:
        job = _job(db, "spend-stale")
        job.lease_token = "not-the-current-token"
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            try:
                _ask(_gateway(db, job))
                raise AssertionError("a stale lease must not pay")
            except LeaseLost:
                pass
    finally:
        restore()
    assert fake.sent == 0


def test_a_render_is_replayed_from_disk_and_a_billed_failure_is_not_rebought():
    from brambleloop.finance import spend_report
    from brambleloop.gateway import images, paid_calls

    db = boot()
    provider = next(iter(images.BY_KEY.values()))
    job = _job(db, "spend-render")
    tmp = Path(tempfile.mkdtemp(prefix="w3spend-"))
    calls = []

    def render(work_dir):
        def go():
            calls.append(1)
            Path(work_dir).mkdir(parents=True, exist_ok=True)
            p = Path(work_dir) / "render-1.png"
            p.write_bytes(b"\x89PNG fake")
            return {"provider": provider.key, "path": str(p), "image_ref": str(p),
                    "cad": provider.cad_per_image, "cost_entry_id": 7}
        return go

    budget = {"estimate_cad": provider.cad_per_image, "reservation_id": None}
    for attempt, wd in enumerate([tmp / "a1", tmp / "a2"]):
        job.attempts = attempt
        with spend_report.attributed_to(spend_report.job_product(db, job)):
            out = images._guarded_render(provider, "a fern throw", [], "1024x1024", None,
                                         str(wd), budget, "gateway", {"accepted": False},
                                         render(wd))
    assert len(calls) == 1, "the second attempt got the picture already paid for"
    assert out["replayed"] is True and Path(out["path"]).parent == tmp / "a2", out
    assert Path(out["path"]).read_bytes() == b"\x89PNG fake"

    # Accepted then failed: billed, so the failure is replayed rather than re-bought.
    job2 = _job(db, "spend-render-fail")
    billing = {"accepted": False}

    def accepted_then_fails():
        calls.append(2)
        billing["accepted"] = True
        raise images.ImagesRefused("provider answered without an image")

    for attempt in range(2):
        job2.attempts = attempt
        with spend_report.attributed_to(spend_report.job_product(db, job2)):
            try:
                images._guarded_render(provider, "a moss throw", [], "1024x1024", None,
                                       str(tmp / f"b{attempt}"), budget, "gateway", billing,
                                       accepted_then_fails)
                raise AssertionError("must raise")
            except (images.ImagesRefused, paid_calls.PaidCallReplayedFailure) as exc:
                if attempt == 1:
                    assert isinstance(exc, paid_calls.PaidCallReplayedFailure), exc
    assert calls.count(2) == 1, calls


def test_a_budget_refusal_survives_the_callers_rollback():
    """F-109: the refusal row is written in its own session, so an outer rollback keeps it."""
    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, CostEntry
    from brambleloop.finance import spend_report
    from brambleloop.gateway import anthropic as gw

    db = boot()
    try:
        with db.session() as s:
            # Pending, unflushed work of the caller (SQLite's single writer would otherwise
            # make the budget lock wait on this very session).
            s.add(CostEntry(agent=AGENT, amount_cad=0.0, kind="probe-marker"))
            gw.check_budget_cad(db, estimate_cad=10_000.0, agent=AGENT, purpose="w3.f109")
        raise AssertionError("over-ceiling estimate must be refused")
    except gw.BudgetExceeded:
        pass
    with db.session() as s:
        marker = s.scalar(select(CostEntry.id).where(CostEntry.kind == "probe-marker"))
        refused = list(s.scalars(select(AuditLog).where(
            AuditLog.action == spend_report.REFUSED_ACTION)))
    assert marker is None, "the surrounding work rolled back"
    assert refused and refused[0].detail["purpose"] == "w3.f109", refused


CHILD = r'''
import os, sys, time
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ["ANTHROPIC_API_KEY"] = "k"
sys.path.insert(0, SRC)
from brambleloop.core.db import Database
from brambleloop.core.models import Phase
from brambleloop.runtime.worker import Worker, handlers
from brambleloop.agents.registry import Registry
from brambleloop.gateway import anthropic as gw
from brambleloop.gateway.anthropic import AnthropicProvider
from brambleloop.gateway.model_gateway import ModelGateway, ModelResponse
mode, name = sys.argv[1], sys.argv[2]
db = Database(DB)

def fake_send(self, payload, key):
    open(SENT, "a").write(f"sent by {name}\n")
    if mode == "hang_in_call":
        time.sleep(120)                 # killed while the provider "has" the request
    return ModelResponse(text='{"names": ["Fern", "Moss", "Bramble"]}', provider=self.name,
                         model=self.model, input_tokens=120, output_tokens=40, latency_ms=1.0)
AnthropicProvider._send = fake_send

@handlers.register("ops.queue_check")
def h(ctx):
    g = ModelGateway([AnthropicProvider(model=gw.PROBE_MODEL)], registry=ctx.registry,
                     job_id=ctx.job.id)
    out = g.complete_json("concept.naming@1", agent="orchestrator",
                          values={"category": "throw", "motifs": "fern", "season": "autumn"})
    if mode == "hang_after_call":
        open(SENT, "a").write("answered\n")
        time.sleep(120)                 # killed after paying, before completing the job
    return {"ran": True, "names": out["names"]}
Worker(db, name, phase=Phase.SHADOW, lease_seconds=2).run_once()
'''


def _sigkill(mode: str):
    from brambleloop.core.models import Job
    from brambleloop.queue.durable import JobQueue

    tmp = tempfile.mkdtemp(prefix="w3spend-kill-")
    db_url, sent = f"sqlite:///{tmp}/k.sqlite", Path(tmp) / "sent.txt"
    child = Path(tmp) / "child.py"
    child.write_text(f"SRC={SRC!r}\nDB={db_url!r}\nSENT={str(sent)!r}\n" + CHILD)
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    db = Database(db_url)
    db.create_all()
    Registry(db).seed_defaults()
    job = JobQueue(db, lease_seconds=2).enqueue(AGENT, "ops.queue_check", {"x": 1},
                                                idempotency_key=f"w3-spend-{mode}")
    env = dict(os.environ, PYTHONPATH=SRC)
    p = subprocess.Popen([sys.executable, str(child), mode, "W1"], env=env)
    marker = "answered" if mode == "hang_after_call" else "sent by W1"
    for _ in range(600):
        if sent.exists() and marker in sent.read_text():
            break
        time.sleep(0.1)
    assert sent.exists() and marker in sent.read_text(), "first worker never reached the call"
    os.kill(p.pid, signal.SIGKILL)
    p.wait()
    time.sleep(2.5)                                         # the 2 s lease expires
    r = subprocess.run([sys.executable, str(child), "ok", "W2"], env=env,
                       capture_output=True, text=True, timeout=300)
    with db.session() as s:
        row = s.get(Job, job.id)
        status, outputs, err = row.status.value, row.outputs, row.last_error or ""
    return db, job.id, sent.read_text().count("sent by"), status, outputs, err, r


def test_runtime_sigkill_after_payment_replays_and_completes():
    db, jid, sends, status, outputs, err, r = _sigkill("hang_after_call")
    assert sends == 1, f"provider asked {sends} times across a reclaim; {r.stderr[-800:]}"
    assert status == "done", (status, err[:400], r.stderr[-800:])
    assert outputs["names"] == ["Fern", "Moss", "Bramble"], outputs
    billed = [c for c in _cost_rows(db, jid) if c[0] > 0]
    assert len(billed) == 1, _cost_rows(db, jid)


def test_runtime_sigkill_during_the_call_is_not_blindly_restarted():
    from brambleloop.gateway import paid_calls

    db, jid, sends, status, outputs, err, r = _sigkill("hang_in_call")
    assert sends == 1, f"provider asked {sends} times; {r.stderr[-800:]}"
    assert status in ("dead", "failed"), (status, err[:300])
    assert "PaidCallUnresolved" in err, err[:400]
    orphan = [c for c in _cost_rows(db, jid)
              if c[1].get("billing") == paid_calls.ORPHAN_BILLING]
    assert len(orphan) == 1 and orphan[0][0] > 0, _cost_rows(db, jid)
    summary = paid_calls.summary(db)
    assert summary["status"] == "DEGRADED" and summary["unresolved"] == 1, summary


if __name__ == "__main__":
    run_tests(globals())
