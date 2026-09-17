"""Gate A (infrastructure) and Gate D (commercial safety).

These simulate the failures that actually happen to an unattended system: a worker dying
mid-job, the same job being enqueued twice, a provider failing repeatedly, an agent reaching
for authority it should not have, and an ad budget being breached.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brambleloop.agents.registry import (  # noqa: E402
    BudgetExceeded, PermissionDenied, Registry, SpendGuard,
)
from brambleloop.core.db import Database  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import Agent, Job, JobStatus, Phase, utcnow  # noqa: E402
from brambleloop.queue.durable import DuplicateJob, JobQueue  # noqa: E402


def fresh() -> Database:
    db = Database("sqlite://")  # in-memory, isolated per test
    db.create_all()
    return db


# ---- Gate A --------------------------------------------------------------


def test_enqueue_and_claim_roundtrip():
    q = JobQueue(fresh())
    job = q.enqueue("market_radar", "radar.scan", {"category": "blankets"})
    claimed = q.claim("worker-1")
    assert claimed and claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING and claimed.leased_by == "worker-1"
    q.complete(claimed.id, {"found": 12})
    assert q.get(job.id).status == JobStatus.DONE
    assert q.get(job.id).outputs == {"found": 12}


def test_claim_respects_priority_then_age():
    q = JobQueue(fresh())
    q.enqueue("market_radar", "radar.scan", priority=200)
    urgent = q.enqueue("market_radar", "radar.scan", priority=1)
    assert q.claim("w").id == urgent.id


def test_worker_death_does_not_strand_a_job():
    """Gate A: 'worker restart does not lose durable jobs'."""
    db = fresh()
    q = JobQueue(db, lease_seconds=60)
    job = q.enqueue("validator", "cir.compile")
    claimed = q.claim("worker-that-dies")
    assert claimed.id == job.id
    # Nothing else can take it while the lease is live.
    assert q.claim("worker-2") is None

    # The worker dies; its lease expires.
    with db.session() as s:
        s.get(Job, job.id).lease_expires_at = utcnow() - timedelta(seconds=1)

    reclaimed = q.claim("worker-2")
    assert reclaimed and reclaimed.id == job.id
    assert reclaimed.leased_by == "worker-2"
    assert reclaimed.attempts == 2


def test_duplicate_job_is_refused_by_idempotency_key():
    """Gate A: 'duplicate job execution cannot duplicate publication/messages/spend'."""
    q = JobQueue(fresh())
    q.enqueue("store_operator", "store.publish", {"slug": "evergreen"},
              idempotency_key="publish:evergreen:v1")
    try:
        q.enqueue("store_operator", "store.publish", {"slug": "evergreen"},
                  idempotency_key="publish:evergreen:v1")
        assert False, "second publish of the same release must be refused"
    except DuplicateJob as e:
        assert "publish:evergreen:v1" in str(e)
    assert q.counts()["pending"] == 1


def test_retry_uses_backoff_then_dead_letters():
    """Gate A: 'dead-letter queue and retry/backoff work'."""
    q = JobQueue(fresh())
    job = q.enqueue("market_radar", "radar.scan", max_attempts=3)

    c1 = q.claim("w")
    failed = q.fail(c1.id, "provider timeout")
    assert failed.status == JobStatus.FAILED
    assert failed.run_after > utcnow()  # backed off, not retried instantly

    # Let the backoff elapse for the test rather than sleeping.
    for _ in range(2):
        with q.db.session() as s:
            s.get(Job, job.id).run_after = utcnow() - timedelta(seconds=1)
        c = q.claim("w")
        assert c is not None
        q.fail(c.id, "provider timeout")

    dead = q.get(job.id)
    assert dead.status == JobStatus.DEAD
    assert dead.attempts == 3
    assert [j.id for j in q.dead_letters()] == [job.id]


def test_permanent_failure_skips_retries():
    q = JobQueue(fresh())
    job = q.enqueue("validator", "cir.compile", max_attempts=5)
    c = q.claim("w")
    q.fail(c.id, "CIR is structurally invalid", retry=False)
    assert q.get(job.id).status == JobStatus.DEAD


def test_audit_log_identifies_actor_action_and_artifact():
    """Gate A: 'audit logs identify actor, action and artifact'."""
    db = fresh()
    reg = Registry(db)
    reg.seed_defaults()
    reg.audit("quality_director", "release.certify", artifact="evergreen-blanket@1.0.0",
              phase=Phase.SHADOW, policy_version="v1.2", detail={"gates": ["B", "C"]})
    trail = reg.audit_trail(artifact="evergreen-blanket@1.0.0")
    assert len(trail) == 1
    entry = trail[0]
    assert entry.actor == "quality_director"
    assert entry.action == "release.certify"
    assert entry.artifact == "evergreen-blanket@1.0.0"
    assert entry.phase == Phase.SHADOW and entry.at is not None


# ---- Gate D --------------------------------------------------------------


def test_agent_cannot_run_job_type_it_lacks():
    reg = Registry(fresh())
    reg.seed_defaults()
    reg.authorize("market_radar", "radar.scan")  # allowed
    try:
        reg.authorize("market_radar", "store.publish")
        assert False, "market radar must not be able to publish"
    except PermissionDenied as e:
        assert "may not run" in str(e)


def test_listing_agent_cannot_spend_ad_money():
    """Section 14: 'Listing cannot spend ad money.' Enforced structurally."""
    reg = Registry(fresh())
    reg.seed_defaults()
    try:
        reg.authorize("listing", "ads.campaign")
        assert False, "listing must never reach ad spend"
    except PermissionDenied as e:
        assert "forbidden" in str(e)


def test_support_cannot_patch_canonical_patterns():
    reg = Registry(fresh())
    reg.seed_defaults()
    for forbidden in ("cir.revise", "store.publish"):
        try:
            reg.authorize("support", forbidden)
            assert False, f"support must not be able to {forbidden}"
        except PermissionDenied:
            pass


def test_agent_daily_cost_ceiling_is_enforced():
    """Gate D: 'Agent API/token ceilings work.'"""
    reg = Registry(fresh())
    reg.seed_defaults()
    reg.record_cost("validator", 0.60)
    reg.record_cost("validator", 0.30)
    assert abs(reg.spend_today("validator") - 0.90) < 1e-6
    try:
        reg.record_cost("validator", 0.50)  # ceiling is 1.00
        assert False, "cost ceiling must refuse the overrun"
    except BudgetExceeded as e:
        assert "daily ceiling" in str(e)
    assert abs(reg.spend_today("validator") - 0.90) < 1e-6  # refused spend is not recorded


def test_ad_budget_breach_is_prevented_and_pauses_the_scope():
    """Gate D: 'Ad budget breach is prevented or automatically paused.'"""
    guard = SpendGuard(fresh())
    guard.set_limit("ads:meta", daily_cap_cad=15.0, lifetime_cap_cad=150.0)
    guard.authorize_spend("ads:meta", 10.0)
    try:
        guard.authorize_spend("ads:meta", 9.0)  # 19 > 15
        assert False, "daily ad cap must not be breachable"
    except BudgetExceeded as e:
        assert "daily cap breached" in str(e)

    st = guard.status("ads:meta")
    assert st.paused is True
    assert abs(st.spent_today_cad - 10.0) < 1e-6  # the refused spend never landed

    try:
        guard.authorize_spend("ads:meta", 1.0)
        assert False, "a paused scope must refuse further spend"
    except BudgetExceeded as e:
        assert "paused" in str(e)


def test_spending_without_a_configured_limit_is_refused():
    guard = SpendGuard(fresh())
    try:
        guard.authorize_spend("ads:unconfigured", 1.0)
        assert False, "spending with no configured cap must be refused, not defaulted"
    except BudgetExceeded as e:
        assert "no spend limit configured" in str(e)

# ---- Gate A: backup and proven restore ----------------------------------


def test_backup_and_restore_drill_proves_the_backup_works():
    """Gate A: 'Database backup and tested restore succeed.'

    Section 28: a backup that has never been restored is unproven, so the drill restores and
    compares row counts rather than trusting that a file appeared.
    """
    import tempfile
    from brambleloop.core.backup import drill
    from brambleloop.agents.registry import Registry

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/live.sqlite")
        db.create_all()
        reg = Registry(db)
        reg.seed_defaults()
        q = JobQueue(db)
        for i in range(5):
            q.enqueue("market_radar", "radar.scan", {"i": i})
        reg.audit("orchestrator", "plan.cycle", artifact="cycle-1")

        result = drill(db, f"{tmp}/backups")
        assert result.ok, result.mismatches
        assert result.backup.bytes_written > 0
        assert result.restored_counts["jobs"] == 5
        assert result.restored_counts["agents"] == len(reg.all())
        assert result.restored_counts["audit_log"] == 1


def test_seeding_reconciles_permissions_that_changed_in_code():
    """A permission that lives in code and cannot reach the database is a comment.

    Production proved this one. The heartbeat's missing permission was fixed in
    DEFAULT_AGENTS, the fix deployed, and the heartbeat kept failing, because the agent row
    already existed and insert-if-absent never revisited it.
    """
    db = Database("sqlite://")
    db.create_all()
    reg = Registry(db)
    reg.seed_defaults()

    # Simulate the old row: an agent that predates a permission added later in code.
    with db.session() as s:
        a = s.scalar(select(Agent).where(Agent.name == "orchestrator"))
        a.allowed_job_types = ["plan.cycle"]
        a.daily_cost_ceiling_cad = 0.5

    changes = reg.seed_defaults()
    assert changes, "reconciliation reported nothing despite a drifted row"
    reg.authorize("orchestrator", "ops.heartbeat")
    assert reg.get("orchestrator").daily_cost_ceiling_cad == 3.0
    assert any("allowed_job_types" in c for c in changes), changes


def test_reconciliation_leaves_runtime_state_alone():
    """Declared fields are the code's; whether an agent is switched off is the system's."""
    db = Database("sqlite://")
    db.create_all()
    reg = Registry(db)
    reg.seed_defaults()
    with db.session() as s:
        s.scalar(select(Agent).where(Agent.name == "ads")).enabled = False

    reg.seed_defaults()
    assert reg.get("ads").enabled is False, "a deploy silently re-enabled a disabled agent"


def test_seeding_twice_with_no_drift_changes_nothing():
    db = Database("sqlite://")
    db.create_all()
    reg = Registry(db)
    reg.seed_defaults()
    assert reg.seed_defaults() == []


def test_a_column_added_in_code_reaches_a_database_that_already_exists():
    """create_all does not touch a table that exists, so a new column never lands.

    This is the third instance of one problem in this system: code changed, the deployed
    database did not. The first was an agent permission, the second a pipeline upgrade that
    could not reach shipped products. Naming it is the point.
    """
    import tempfile

    from sqlalchemy import inspect, text

    from brambleloop.core.migrate import apply, plan

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/schema.sqlite"
        db = Database(url)
        assert db.create_all() == [], "a fresh database needed a migration"

        # Simulate a database created before the column existed.
        with db.engine.begin() as conn:
            conn.execute(text("DROP INDEX IF EXISTS ix_listings_chain_version"))
            conn.execute(text("ALTER TABLE listings DROP COLUMN chain_version"))

        again = Database(url)
        assert plan(again.engine), "the missing column was not detected"
        changes = again.create_all()
        assert any("chain_version" in c for c in changes), changes

        insp = inspect(again.engine)
        cols = {c["name"] for c in insp.get_columns("listings")}
        idx = {i["name"] for i in insp.get_indexes("listings")}
        assert "chain_version" in cols
        assert "ix_listings_chain_version" in idx, "the column came back without its index"
        assert Database(url).create_all() == [], "the migration is not idempotent"


def test_an_added_column_is_backfilled_with_the_models_default():
    """Otherwise a fresh database and a migrated one hold two different shapes.

    A NULL where the model promises a value means the comparison that decides whether a row is
    stale quietly compares against None — which is how a fix reaches nothing.
    """
    import tempfile

    from sqlalchemy import select, text

    from brambleloop.core.models import Listing

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/backfill.sqlite"
        db = Database(url)
        db.create_all()
        with db.session() as s:
            s.add(Listing(product_slug="x", version="1.0.0", title="t", description="d"))
        with db.engine.begin() as conn:
            conn.execute(text("DROP INDEX IF EXISTS ix_listings_chain_version"))
            conn.execute(text("ALTER TABLE listings DROP COLUMN chain_version"))

        again = Database(url)
        changes = again.create_all()
        assert any("backfilled" in c for c in changes), changes
        with again.session() as s:
            rows = list(s.scalars(select(Listing)))
        assert rows and all(r.chain_version == "1" for r in rows), \
            [r.chain_version for r in rows]


def test_the_migration_refuses_a_change_it_cannot_make_safely():
    """Additive only. A NOT NULL column with no default cannot be added to a table with rows."""
    import tempfile

    from sqlalchemy import Column, String, Table

    from brambleloop.core.db import Base
    from brambleloop.core.migrate import UnsafeMigration, plan

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/unsafe.sqlite")
        db.create_all()
        table: Table = Base.metadata.tables["listings"]
        column = Column("mandatory_thing", String(10), nullable=False)
        table.append_column(column)
        try:
            plan(db.engine)
        except UnsafeMigration as e:
            assert "write a real migration" in str(e)
        else:
            raise AssertionError("an unbackfillable NOT NULL column was accepted")
        finally:
            table._columns.remove(column)


def test_every_scheduled_cadence_can_actually_run():
    """A cadence its agent may not run dead-letters forever, silently.

    Found in production: the operational heartbeat was scheduled against the orchestrator,
    which had no permission for it, so it failed every fifteen minutes from the first boot and
    the queue-health signal never once fired. Nothing caught it because every other test
    enqueued jobs directly instead of going through the schedule. This checks the two things
    that must be true of every cadence: an agent allowed to run it, and a handler to run.
    """
    from brambleloop.runtime import pipeline  # noqa: F401  -- registers handlers
    from brambleloop.runtime.worker import CADENCES, handlers

    db = Database("sqlite://")
    db.create_all()
    reg = Registry(db)
    reg.seed_defaults()

    problems = []
    for name, agent, job_type, _period in CADENCES:
        try:
            reg.authorize(agent, job_type)
        except PermissionDenied as e:
            problems.append(f"cadence {name!r}: {e}")
        if handlers.get(job_type) is None:
            problems.append(f"cadence {name!r}: no handler registered for {job_type!r}")
    assert not problems, problems


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
