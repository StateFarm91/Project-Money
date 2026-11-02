"""OPUS2 (P1-CULTURE-SWEEP-TIMEOUT): a classifier timeout no longer dead-letters the sweep.

Production (2026-10-27 job 34246, 2026-11-01 job 41979): attempt 1's classifier call timed
out. `culture.classify` caught only PermanentError/TransientError, so the TimeoutError escaped,
failed the attempt and left its budget reservation to expire; the paid-call intent was left
UNCERTAIN, so every retry correctly refused to re-send (F-307/F-339) and the job dead-lettered.

Now the timeout is caught in `classify`: nothing is filed, the unknown spend is counted once at
the reservation estimate (never zero), and nothing is re-sent. A later attempt that meets the
UNCERTAIN intent gets `PaidCallUnresolved`, a PermanentError, which `classify` already turns
into "nothing filed" -- so the sweep completes on its fixed topics either way.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_culture_sweep_timeout.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry  # noqa: E402
from brambleloop.culture import classify as C  # noqa: E402


class _Provider:
    model = "claude-haiku-4-5"
    cost_per_1k_input_cad = 0.001
    cost_per_1k_output_cad = 0.005
    calls = 0

    @staticmethod
    def key():
        return "k"

    def complete(self, system, user, *, max_tokens):
        type(self).calls += 1
        raise TimeoutError("The read operation timed out")


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/c.sqlite")
    db.create_all()
    return db


def _reservations(db):
    from brambleloop.core.models import SpendReservation

    with db.session() as s:
        return [(r.amount_cad, r.released_at is not None)
                for r in s.scalars(select(SpendReservation))]


def test_a_timeout_files_nothing_and_raises_nothing():
    out = C.classify(["Wednesday_(TV_series)"], provider=_Provider())
    assert out["filed"] == {} and out["unresolved"] is True
    assert "timed out" in out["reason"] and "not an empty culture" in out["note"]


def test_the_unknown_spend_is_counted_once_at_the_estimate_and_the_reservation_released():
    db = _db()
    _Provider.calls = 0
    out = C.classify(["A_topic", "B_topic"], provider=_Provider(), db=db)
    assert out["unresolved"] is True and _Provider.calls == 1        # sent once, not retried
    with db.session() as s:
        rows = [r for r in s.scalars(select(CostEntry)) if (r.detail or {}).get("billing")
                == "unknown_counted_at_estimate"]
        assert len(rows) == 1, rows
        assert rows[0].amount_cad > 0 and rows[0].amount_cad == rows[0].estimated_cad
        assert rows[0].agent == "market_radar"
    held = _reservations(db)
    assert held and all(released for _amount, released in held)      # never left to expire


def test_a_retry_that_meets_the_unresolved_intent_files_nothing_without_resending():
    from brambleloop.gateway.paid_calls import PaidCallUnresolved

    class _Unresolved(_Provider):
        def complete(self, system, user, *, max_tokens):
            type(self).calls += 1
            raise PaidCallUnresolved("anthropic.messages: earlier attempt has no known outcome")

    out = C.classify(["A_topic"], provider=_Unresolved(), db=_db())
    assert out["filed"] == {} and "no known outcome" in out["reason"]


def _worker_sweep(failure, *, attempts=1, extra=None):
    """The real culture.sweep job, through the real worker and paid-call guard. Only the
    network is faked: `AnthropicProvider._send` (the transport) and the culture feeds."""
    import os

    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Job, JobStatus, Phase
    from brambleloop.culture import feeds
    from brambleloop.gateway import paid_calls
    from brambleloop.gateway.anthropic import AnthropicProvider
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import release  # noqa: F401 - registers handlers
    from brambleloop.runtime.worker import Worker

    os.environ.setdefault("ANTHROPIC_API_KEY", "k")     # presence only; _send is faked
    db = _db()
    Registry(db).seed_defaults()
    sent = []

    def fake_send(self, payload, key, **kw):
        sent.append(1)
        raise failure

    saved = (AnthropicProvider._send, feeds.discover, feeds.sweep, feeds.default_articles,
             feeds.env_override)
    AnthropicProvider._send = fake_send
    feeds.discover = lambda **k: {"topics": [{"article": "A_topic"}, {"article": "B_topic"}]}
    feeds.default_articles = lambda db, **k: ["Crochet"]
    feeds.env_override = lambda *a, **k: []
    feeds.sweep = lambda db, articles, **k: {
        "source": feeds.SOURCE_KEY, "channel": feeds.CHANNEL, "recorded": 0,
        "attempted": len(articles), "readings": [], "failures": [], "measures": "",
        "lag_days": feeds.PIPELINE_LAG_DAYS}
    restore = extra() if extra is not None else (lambda: None)
    try:
        job = JobQueue(db).enqueue("market_radar", "culture.sweep", {},
                                   idempotency_key="sweep-fixture", priority=0)
        for _ in range(attempts):
            with db.session() as s:                      # retries become due immediately
                row = s.get(Job, job.id)
                row.run_after = datetime.now(timezone.utc) - timedelta(seconds=1)
            Worker(db, "w-sweep", phase=Phase.SHADOW, job_types=["culture.sweep"],
                   lease_seconds=900).run_once()
    finally:
        restore()
        (AnthropicProvider._send, feeds.discover, feeds.sweep, feeds.default_articles,
         feeds.env_override) = saved
    with db.session() as s:
        row = s.get(Job, job.id)
        status, attempts, err = row.status, row.attempts, row.last_error
        outcomes = [r.outcome for r in s.scalars(select(paid_calls.PaidCallRecord))]
        costs = [(c.amount_cad, (c.detail or {}).get("billing")) for c in s.scalars(
            select(CostEntry))]
    return status is JobStatus.DONE, attempts, err, sent, outcomes, costs


def test_review_opus2g_c2_c3_every_unknown_outcome_completes_the_sweep_on_attempt_one():
    import http.client

    failures = (TimeoutError("The read operation timed out"),
                ValueError("Expecting value: line 1 column 1 (char 0)"),
                ConnectionResetError(104, "Connection reset by peer"),
                http.client.IncompleteRead(b"partial"))
    assert failures
    for failure in failures:
        done, attempts, err, sent, outcomes, costs = _worker_sweep(failure)
        name = type(failure).__name__
        assert done and attempts == 1, (name, attempts, err)
        assert len(sent) == 1, (name, sent)                       # never re-sent
        assert outcomes == ["UNCERTAIN"], (name, outcomes)        # the guard's verdict kept
        unknown = [a for a, billing in costs if billing == "unknown_counted_at_estimate"]
        assert len(unknown) == 1 and unknown[0] > 0, (name, costs)


def test_review_opus2i_c4_a_pre_send_failure_re_raises_and_bills_nothing():
    """In the real worker, a failure before the transport is reached is not unknown spend."""
    from brambleloop.gateway.anthropic import AnthropicProvider

    real = AnthropicProvider._guarded

    def broken_before_send(self, payload, key, effect, **kw):
        raise RuntimeError("write-ahead failed before any request left the process")

    AnthropicProvider._guarded = broken_before_send
    try:
        done, attempts, err, sent, outcomes, costs = _worker_sweep(TimeoutError("unused"))
    finally:
        AnthropicProvider._guarded = real
    assert not done and "write-ahead failed" in (err or ""), (done, err)   # visible, not swallowed
    assert sent == [] and outcomes == []
    assert not [c for c in costs if c[1] == "unknown_counted_at_estimate"], costs

    # Outside a job, a bug in the prompt builder is never billed either.
    db = _db()
    real_prompt = C.prompt
    C.prompt = lambda topics: (_ for _ in ()).throw(RuntimeError("prompt bug"))
    try:
        try:
            C.classify(["A_topic"], provider=_Provider(), db=db)
            raise AssertionError("a prompt bug was swallowed")
        except RuntimeError:
            pass
    finally:
        C.prompt = real_prompt
    with db.session() as s:
        assert list(s.scalars(select(CostEntry))) == []


def test_review_opus2j_j3_a_pending_record_is_billed_once_across_attempts():
    """M7n: the guard wrote PENDING and then failed to claim the intent. classify must not bill
    it (it is not UNCERTAIN); the guard's orphan rule bills it exactly once on the retry."""
    from brambleloop.queue import effects

    def claim_fails():
        real = effects.claim
        calls = []

        def broken(*a, **k):
            if not calls:
                calls.append(1)
                raise RuntimeError("intent claim failed after the write-ahead record")
            return real(*a, **k)
        effects.claim = broken
        return lambda: setattr(effects, "claim", real)

    done, attempts, err, sent, outcomes, costs = _worker_sweep(
        TimeoutError("unused"), attempts=2, extra=claim_fails)
    billed = [c for c in costs if c[0] > 0]
    assert len(billed) == 1, costs                  # once, never twice
    assert sent == []                               # nothing was ever sent


def test_review_opus2j_j3_m7p_a_prompt_bug_with_no_budget_check_still_raises():
    real_prompt = C.prompt
    C.prompt = lambda topics: (_ for _ in ()).throw(RuntimeError("prompt bug"))
    try:
        try:
            C.classify(["A_topic"], provider=_Provider(), db=None)
            raise AssertionError("a prompt bug was swallowed")
        except RuntimeError:
            pass
    finally:
        C.prompt = real_prompt


def test_review_opus2k_k4_a_pending_record_with_the_key_set_is_not_billed_by_classify():
    """M7n: the call failed, then the guard's outcome write failed, so the record stays PENDING
    with the scope's paid-call key set. classify must re-raise (not UNCERTAIN), never bill."""
    from brambleloop.gateway import paid_calls

    def outcome_write_fails():
        real = paid_calls._update

        def broken(db, key, **fields):
            if fields.get("outcome") == paid_calls.UNCERTAIN:
                raise RuntimeError("outcome write failed after the call")
            return real(db, key, **fields)
        paid_calls._update = broken
        return lambda: setattr(paid_calls, "_update", real)

    done, attempts, err, sent, outcomes, costs = _worker_sweep(
        TimeoutError("read timed out"), attempts=1, extra=outcome_write_fails)
    assert len(sent) == 1 and outcomes == ["PENDING"], (sent, outcomes)
    assert not done and "outcome write failed" in (err or ""), err
    assert not [c for c in costs if c[1] == "unknown_counted_at_estimate"], costs


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
