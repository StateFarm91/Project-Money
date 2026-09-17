"""Chaos and failure-injection suite.

Every failure the owner listed, injected deliberately:
worker death, expired leases, duplicate jobs/events, API 429/500, timeouts, malformed AI
output, model-provider outage, database interruption, storage failure, corrupted artifact
hashes, restart mid-pipeline, and exhausted agent/spend budgets.

The bar for each: detect, contain, retry *safely*, preserve state, escalate only if necessary.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import (  # noqa: E402
    BudgetExceeded, Registry, SpendGuard,
)
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    Agent, AuditLog, Job, JobStatus, Product, utcnow,
)
from brambleloop.core.resilience import (  # noqa: E402
    CircuitBreaker, CorruptArtifact, MalformedModelOutput, PermanentError, TransientError,
    artifact_hash, classify_http, parse_model_json, retry_after_seconds, verify_artifact,
    with_retries,
)
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: F401,E402
from brambleloop.runtime.worker import Worker, handlers  # noqa: E402


def boot(url: str = "sqlite://") -> Database:
    db = Database(url)
    db.create_all()
    Registry(db).seed_defaults()
    return db


def allow(db: Database, agent: str, job_type: str) -> None:
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == agent))
        a.allowed_job_types = list(a.allowed_job_types) + [job_type]


# ---- transient vs permanent ---------------------------------------------


def test_http_status_classification():
    assert classify_http(429) is TransientError
    assert classify_http(500) is TransientError
    assert classify_http(503) is TransientError
    assert classify_http(400) is PermanentError
    assert classify_http(401) is PermanentError
    assert classify_http(404) is PermanentError


def test_rate_limit_honours_retry_after_header():
    """Ignoring Retry-After is how a rate limit becomes a ban."""
    assert retry_after_seconds({"retry-after": "42"}, attempt=1) == 42.0
    # Without the header, back off with jitter but stay bounded.
    d = retry_after_seconds(None, attempt=3, base=2.0, cap=300)
    assert 6.0 <= d <= 10.0


def test_permanent_errors_are_not_retried():
    calls = []

    def boom():
        calls.append(1)
        raise PermanentError("400 bad request")

    try:
        with_retries(boom, attempts=5, sleep=lambda _: None)
        assert False, "permanent errors must surface immediately"
    except PermanentError:
        pass
    assert len(calls) == 1, "a 400 must not be retried five times"


def test_transient_errors_are_retried_then_surface():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("429 slow down")
        return "ok"

    assert with_retries(flaky, attempts=5, sleep=lambda _: None) == "ok"
    assert len(calls) == 3


# ---- provider outage -----------------------------------------------------


def test_circuit_breaker_opens_on_sustained_provider_outage():
    """A dead provider must stop being called, not called ten thousand times."""
    cb = CircuitBreaker("model-provider", threshold=3, reset_after_seconds=60)
    calls = []

    def down():
        calls.append(1)
        raise TransientError("connection refused")

    for _ in range(3):
        try:
            cb.call(down)
        except TransientError:
            pass
    assert cb.is_open

    try:
        cb.call(down)
        assert False, "an open circuit must fail fast"
    except TransientError as e:
        assert "is open" in str(e)
    assert len(calls) == 3, "no further calls should reach a downed provider"


def test_circuit_breaker_recovers_after_cooldown():
    cb = CircuitBreaker("model-provider", threshold=1, reset_after_seconds=0.0)
    try:
        cb.call(lambda: (_ for _ in ()).throw(TransientError("down")))
    except TransientError:
        pass
    assert cb.is_open is False  # cooldown elapsed -> half-open probe allowed
    assert cb.call(lambda: "recovered") == "recovered"
    assert cb.failures == 0


# ---- malformed model output ---------------------------------------------


def test_malformed_model_output_is_rejected():
    for bad in ("", "   ", "I think the pattern should have 40 stitches",
                '{"slug": "x", ', "[1,2,3]"):
        try:
            parse_model_json(bad)
            assert False, f"should have rejected {bad!r}"
        except MalformedModelOutput:
            pass


def test_model_output_missing_required_field_is_rejected():
    try:
        parse_model_json('{"slug": "x"}', required=("slug", "rows"))
        assert False, "missing field must be caught before it travels downstream"
    except MalformedModelOutput as e:
        assert "rows" in str(e)


def test_model_output_in_code_fence_is_accepted():
    out = parse_model_json('```json\n{"slug": "x", "rows": 4}\n```', required=("slug", "rows"))
    assert out == {"slug": "x", "rows": 4}


# ---- corrupted artifacts -------------------------------------------------


def test_corrupted_artifact_is_detected():
    payload = {"cir": {"rows": 40}}
    h = artifact_hash(payload)
    verify_artifact(payload, h)  # clean

    tampered = {"cir": {"rows": 41}}
    try:
        verify_artifact(tampered, h, label="pattern release")
        assert False, "a tampered artifact must not verify"
    except CorruptArtifact as e:
        assert "integrity check" in str(e)


def test_truncated_binary_artifact_is_detected():
    blob = b"%PDF-1.4 ... full document ..."
    h = artifact_hash(blob)
    try:
        verify_artifact(blob[:10], h, label="pattern PDF")
        assert False, "a truncated PDF must not verify"
    except CorruptArtifact:
        pass


# ---- duplicate events ----------------------------------------------------


def test_duplicate_webhook_event_cannot_double_process():
    """The same inbound event delivered twice must produce one job, not two."""
    q = JobQueue(boot())
    event_id = "etsy-order-evt-7781"
    q.enqueue("support", "support.triage", {"event": event_id},
              idempotency_key=f"event:{event_id}")
    try:
        q.enqueue("support", "support.triage", {"event": event_id},
                  idempotency_key=f"event:{event_id}")
        assert False, "a replayed event must be refused"
    except DuplicateJob:
        pass
    assert q.counts()["pending"] == 1


def test_duplicate_spend_job_cannot_double_charge():
    q = JobQueue(boot())
    key = "ads:campaign:evergreen:2026-09-17"
    q.enqueue("ads", "ads.campaign", {"budget_cad": 15.0}, idempotency_key=key)
    try:
        q.enqueue("ads", "ads.campaign", {"budget_cad": 15.0}, idempotency_key=key)
        assert False, "a duplicate spend job must never be queued twice"
    except DuplicateJob:
        pass


# ---- database interruption ----------------------------------------------


def test_database_interruption_surfaces_and_does_not_corrupt_state():
    """If the database disappears mid-flight, the failure is visible, not silent."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = boot(url)
        q = JobQueue(db)
        q.enqueue("market_radar", "radar.scan", {"n": 1})

        # Point a second handle at a path that cannot be opened (directory, not a file).
        broken = Database(f"sqlite:///{tmp}")
        try:
            broken.create_all()
            with broken.session() as s:
                s.execute(select(Job))
            raised = False
        except Exception:
            raised = True
        assert raised, "an unusable database must raise, not silently no-op"

        # The real database is untouched and still holds the work.
        assert JobQueue(Database(url)).counts()["pending"] == 1


def test_handler_failure_rolls_back_cleanly_and_preserves_the_job():
    db = boot()
    allow(db, "validator", "test.halfwrite")

    @handlers.register("test.halfwrite")
    def _half(ctx):
        with ctx.db.session() as s:
            s.add(Product(slug="ghost", title="should not persist", status="concept"))
            raise RuntimeError("storage failure mid-write")

    JobQueue(db).enqueue("validator", "test.halfwrite", {})
    w = Worker(db, "w")
    w.run_once()

    with db.session() as s:
        assert s.scalar(select(Product).where(Product.slug == "ghost")) is None, \
            "a failed handler must not leave a half-written record behind"
        job = s.scalar(select(Job))
    assert job.status == JobStatus.FAILED  # queued for retry, not lost
    assert "storage failure" in job.last_error


# ---- timeouts and stuck workers -----------------------------------------


def test_expired_lease_is_reclaimed_and_eventually_dead_letters():
    """A job whose worker keeps vanishing must not loop forever."""
    db = boot()
    q = JobQueue(db, lease_seconds=1)
    job = q.enqueue("market_radar", "radar.scan", {}, max_attempts=2)

    for _ in range(3):
        claimed = q.claim("flaky-worker")
        if claimed is None:
            break
        with db.session() as s:
            s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)

    final = q.get(job.id)
    assert final.status == JobStatus.DEAD, final.status
    assert "retries exhausted" in (final.last_error or "")


def test_worker_survives_a_handler_that_hangs_then_is_reclaimed():
    db = boot()
    q = JobQueue(db, lease_seconds=1)
    job = q.enqueue("validator", "cir.compile", {})
    q.claim("stuck-worker")  # claimed and never completed

    with db.session() as s:
        s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)

    assert q.claim("healthy-worker") is not None


# ---- budget exhaustion ---------------------------------------------------


def test_exhausted_agent_budget_stops_work_without_crashing_the_worker():
    db = boot()
    allow(db, "validator", "test.expensive")

    @handlers.register("test.expensive")
    def _spend(ctx):
        ctx.registry.record_cost("validator", 5.0)  # ceiling is 1.00
        return {"spent": True}

    JobQueue(db).enqueue("validator", "test.expensive", {})
    w = Worker(db, "w")
    assert w.run_once() is True
    assert w.stats.failed == 1

    with db.session() as s:
        job = s.scalar(select(Job))
        audits = {a.action for a in s.scalars(select(AuditLog))}
    assert job.status == JobStatus.DEAD, "a budget breach is terminal, not retried forever"
    assert "budget exceeded" in job.last_error
    assert "job.budget_exceeded" in audits, "budget breaches must be escalatable"


def test_exhausted_ad_budget_pauses_the_scope_and_stays_paused():
    db = boot()
    guard = SpendGuard(db)
    guard.set_limit("ads:meta", daily_cap_cad=10.0, lifetime_cap_cad=20.0)
    guard.authorize_spend("ads:meta", 9.0)
    for _ in range(3):
        try:
            guard.authorize_spend("ads:meta", 5.0)
        except BudgetExceeded:
            pass
    st = guard.status("ads:meta")
    assert st.paused is True
    assert abs(st.spent_today_cad - 9.0) < 1e-6, "no refused spend may leak through"


# ---- mid-pipeline restart ------------------------------------------------


def test_restart_mid_pipeline_completes_without_duplicating_the_product():
    """Restart between every step; the product is produced exactly once."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = boot(url)
        JobQueue(db).enqueue("orchestrator", "plan.cycle", {})

        # Each iteration is a brand-new Database handle and Worker: a full cold restart.
        for i in range(40):
            w = Worker(Database(url), f"worker-{i}")
            if not w.run_once():
                break

        fresh = Database(url)
        with fresh.session() as s:
            products = list(s.scalars(select(Product)))
            versions = [p.slug for p in products]
        assert len(products) == 1, f"expected exactly one product, got {versions}"
        assert products[0].status == "certified"


def test_replayed_pipeline_does_not_recertify_or_duplicate_versions():
    """Running the same cycle twice must not create a second release of the same version."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/live.sqlite"
        db = boot(url)
        q = JobQueue(db)
        q.enqueue("orchestrator", "plan.cycle", {})
        w = Worker(db, "w")
        for _ in range(40):
            if not w.run_once():
                break

        # Same cycle again: idempotency keys should collapse the duplicate work.
        q.enqueue("orchestrator", "plan.cycle", {})
        for _ in range(40):
            if not w.run_once():
                break

        from brambleloop.core.models import PatternVersion
        with db.session() as s:
            versions = list(s.scalars(select(PatternVersion)))
            products = list(s.scalars(select(Product)))
        assert len(products) == 1, "a replay must not duplicate the product"
        assert len(versions) == 1, "a replay must not create a second release row"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
