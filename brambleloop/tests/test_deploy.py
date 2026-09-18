"""Deployment-surface tests: the container must be able to run the company by itself.

These exercise the exact code path a hosted container runs -- app startup, embedded worker
and scheduler threads, health and status endpoints -- rather than a test-only wiring of the
same objects. A deployment that only works when a test constructs the pieces by hand is not a
deployment.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/app.sqlite"
os.environ.setdefault("BRAMBLELOOP_EMBEDDED_WORKER", "1")
os.environ["BRAMBLELOOP_SCHEDULER_INTERVAL"] = "2"
os.environ["BRAMBLELOOP_IDLE_SLEEP"] = "0.2"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.app import main as app_main, runner  # noqa: E402
from brambleloop.core.models import Product  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402


def _client() -> TestClient:
    return TestClient(app_main.app)


def test_health_reports_a_real_database_check():
    with _client() as c:
        r = c.get("/health")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["db"] == "ok"
        assert body["version"]


def test_status_endpoint_exposes_what_an_absent_owner_needs():
    with _client() as c:
        body = c.get("/api/status").json()
    for key in ("queue", "dead_letters", "products", "certified_versions",
                "open_incidents", "agent_opex_cad", "revenue_cad",
                "owner_actions_open", "runner", "model_providers"):
        assert key in body, key
    # No API key is configured here, and the status endpoint must say so rather than imply a
    # model integration that does not exist.
    assert body["model_providers"] == []


def test_dashboard_renders_without_a_build_step():
    with _client() as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "BRAMBLELOOP STUDIO" in r.text
        assert "Runner:" in r.text


def test_the_container_runs_the_company_by_itself():
    """Start the app, enqueue nothing by hand, and let the embedded runner do the work.

    This is the whole claim of a 24/7 deployment: the process is started by the platform and
    the company runs. If this passes only because a test called a worker directly, the claim
    is false.
    """
    with _client() as c:
        assert runner.wait_for_tick(timeout=15), "embedded worker never ticked"
        assert c.get("/health").json()["runner"]["enabled"] is True

        # The scheduler's own cadence enqueues the planning cycle; wait for the chain to
        # reach the far end of itself, which is the publish refusal, not merely the first
        # product. Waiting on the first product would declare victory a dozen steps early.
        from brambleloop.core.models import AuditLog

        deadline = time.time() + 180
        products: list[str] = []
        refusals: list = []
        while time.time() < deadline:
            with app_main.db.session() as s:
                products = [p.slug for p in s.scalars(select(Product))]
                refusals = [a.id for a in s.scalars(select(AuditLog))
                            if a.action == "store.publish_refused"]
            if refusals:
                break
            time.sleep(0.5)

        assert products, "the embedded runner produced no products unattended"
        body = c.get("/api/status").json()
        assert body["runner"]["worker_alive"] is True
        assert body["certified_versions"] >= 1

    # Shadow mode still refuses to publish, even running unattended in a container. Asserted
    # against the audit trail rather than the dead-letter count: a refusal is retried with
    # backoff before it dead-letters, so a dead-letter count is a slow and ambiguous proxy --
    # it was previously satisfied by an unrelated cadence failing, which is how this test
    # passed for years-worth of the wrong reason.
    with app_main.db.session() as s:
        refusals = [a for a in s.scalars(select(AuditLog))
                    if a.action == "store.publish_refused"]
        published = [a for a in s.scalars(select(AuditLog))
                     if a.action == "store.published"]
    assert refusals, "nothing attempted to publish, so the refusal proved nothing"
    assert not published, "shadow mode published something"


def test_a_planning_cycle_can_be_started_on_demand_and_is_idempotent_per_date():
    with _client() as c:
        first = c.post("/api/plan-cycle?as_of=2027-01-20").json()
        second = c.post("/api/plan-cycle?as_of=2027-01-20").json()
    assert first["enqueued"] is True and first["job_id"]
    assert second["enqueued"] is False, "the same date enqueued twice"


def test_the_catalogue_endpoint_is_explicit_that_nothing_is_published():
    with _client() as c:
        body = c.get("/api/catalogue").json()
    assert body["published"] is False
    assert "shadow" in body["why"]
    assert "no Etsy" in body["why"]
    for key in ("listings", "collections", "totals"):
        assert key in body, key


def test_the_finance_endpoint_reports_observed_figures_and_no_forecast():
    with _client() as c:
        body = c.get("/api/finance").json()
    assert body["profit_and_loss"]["all_figures_observed"] is True
    assert body["profit_and_loss"]["gross_sales_cad"] == 0.0
    assert body["trajectory"]["is_forecast"] is False
    assert body["unit_economics"]["cost_per_acquired_customer_cad"] is None
    assert isinstance(body["cfo_challenges"], list)


def test_the_support_endpoint_shows_that_nothing_was_sent():
    with _client() as c:
        body = c.get("/api/support").json()
    assert body["nothing_sent"] is True
    assert all(case["sent"] is False for case in body["cases"])


def test_a_chain_rebuild_can_be_started_on_demand():
    """The cadence is hourly, which is slow when a deploy has just landed a fix."""
    with _client() as c:
        first = c.post("/api/chain-rebuild").json()
        second = c.post("/api/chain-rebuild").json()
    assert first["enqueued"] is True
    assert second["enqueued"] is False, "two rebuilds queued at once"


def test_verify_endpoint_reports_the_standing_safety_assertions():
    """"Railway says deployed" is not "the company is alive and behaving"."""
    with _client() as c:
        body = c.get("/api/verify").json()
    names = {ch["check"] for ch in body["checks"]}
    for expected in ("phase_is_shadow", "nothing_published", "no_paid_advertising",
                     "no_revenue_claimed", "every_agent_has_a_cost_ceiling",
                     "state_is_in_a_durable_database", "worker_is_alive",
                     "no_unexpected_dead_letters_in_24h"):
        assert expected in names, expected
    by_name = {ch["check"]: ch for ch in body["checks"]}
    assert by_name["phase_is_shadow"]["ok"] is True
    assert by_name["nothing_published"]["ok"] is True
    assert by_name["no_revenue_claimed"]["ok"] is True
    # Every check carries the evidence it used, so a green result can be argued with.
    assert all(ch["evidence"] for ch in body["checks"])


def test_verify_fails_loudly_rather_than_reporting_green_on_ephemeral_storage():
    """A SQLite-backed container must not be able to report itself durably deployed."""
    with _client() as c:
        body = c.get("/api/verify").json()
    durable = next(ch for ch in body["checks"]
                   if ch["check"] == "state_is_in_a_durable_database")
    assert durable["ok"] is False, "a SQLite test container claimed durable state"
    assert durable["evidence"]["engine"] == "sqlite"
    assert body["ok"] is False


def test_scheduler_tick_endpoint_is_idempotent_within_a_window():
    with _client() as c:
        first = c.post("/api/scheduler/tick").json()["enqueued"]
        second = c.post("/api/scheduler/tick").json()["enqueued"]
    assert second == [], f"a repeated tick re-enqueued {second} (first was {first})"


def test_platform_database_url_is_normalised():
    """Railway injects the historical postgres:// form that SQLAlchemy 2.x rejects."""
    from brambleloop.core.db import resolve_url

    assert resolve_url("postgres://u:p@h:5432/db") == "postgresql+psycopg2://u:p@h:5432/db"
    assert resolve_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert resolve_url("sqlite://") == "sqlite://"


def test_a_hosted_container_refuses_to_run_on_ephemeral_storage():
    """Silently falling back to SQLite on a container disk loses the entire company."""
    from brambleloop.core.db import EphemeralStorageRefused, resolve_url

    saved = dict(os.environ)
    try:
        os.environ.pop("BRAMBLELOOP_DATABASE_URL", None)
        os.environ.pop("DATABASE_URL", None)
        os.environ["BRAMBLELOOP_REQUIRE_POSTGRES"] = "1"
        try:
            resolve_url()
        except EphemeralStorageRefused as e:
            assert "ephemeral" in str(e).lower()
        else:
            raise AssertionError("a hosted container accepted ephemeral storage")
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_runner_state_is_honest_about_a_worker_that_is_not_running():
    from brambleloop.app.runner import RunnerState

    st = RunnerState()
    assert st.to_dict()["worker_alive"] is False
    assert st.to_dict()["enabled"] is False



def test_the_launch_endpoint_separates_what_is_ours_from_what_is_the_owners():
    """The distinction is the point: a requirement blocked on build is never an owner action.

    Asking the owner for an Etsy account because it will eventually be needed is exactly what
    the Execution Directive forbids, so the report has to be able to tell the difference.
    """
    with _client() as c:
        body = c.get("/api/launch").json()

    assert body["ready"] is False, "shadow mode cannot be launch-ready"
    keys = {r["key"]: r for r in body["requirements"]}
    assert keys["etsy_shop"]["blocked_by"] == "owner"
    assert keys["etsy_integration"]["blocked_by"] == "integration"
    assert keys["phase"]["blocked_by"] == "owner"

    # Every unmet requirement names who it is waiting on.
    unattributed = [r["key"] for r in body["requirements"]
                    if not r["ready"] and not r["blocked_by"]]
    assert not unattributed, unattributed

    # And nothing blocked on build reaches the owner queue.
    build_blocked = {r["description"] for r in body["requirements"]
                     if r["blocked_by"] == "build"}
    owner_actions = {a["action"] for a in body["owner_actions"]}
    assert not (build_blocked & owner_actions)

    for action in body["owner_actions"]:
        assert action["reason"] and action["consequence_of_delay"] and action["blocks"]
        assert action["minutes"] > 0
        assert action["max_cost_cad"] >= 0


def test_the_owner_queue_is_written_by_the_system_not_by_hand():
    from brambleloop.core.models import OwnerAction

    with _client() as c:
        c.post("/api/scheduler/tick")
        JobQueue(app_main.db).enqueue("orchestrator", "launch.readiness", {},
                                      idempotency_key="test:launch-readiness")
        deadline = time.time() + 30
        while time.time() < deadline:
            with app_main.db.session() as s:
                rows = list(s.scalars(select(OwnerAction)))
            if rows:
                break
            time.sleep(0.5)

    assert rows, "the readiness job queued no owner actions"
    # Running it again must not duplicate them: an owner queue that grows by seven a day is
    # a queue nobody reads.
    before = len(rows)
    JobQueue(app_main.db).enqueue("orchestrator", "launch.readiness", {},
                                 idempotency_key="test:launch-readiness-2")
    with _client() as c:
        deadline = time.time() + 30
        while time.time() < deadline:
            with app_main.db.session() as s:
                again = list(s.scalars(select(OwnerAction)))
            if len(again) != before:
                break
            time.sleep(0.5)
    assert len(again) == before, f"owner actions duplicated: {before} -> {len(again)}"


def test_the_status_endpoint_says_which_commit_is_running():
    """The only field that can tell whether a fix reached production.

    `version` is hand-maintained, so it proves nothing: three separate idempotency bugs each
    cost a diagnosis round to "the code is fixed and production disagrees", because the
    question had no answer.
    """
    from brambleloop.core import build

    with _client() as c:
        body = c.get("/api/status").json()
    assert "build" in body, "status does not report which code it is running"
    assert set(body["build"]) == {"commit", "commit_short", "branch", "known"}
    # In a test environment there is usually no build commit, and `unknown` is the honest
    # answer -- but it must never be reported as a known one.
    if not body["build"]["known"]:
        assert body["build"]["commit"] == build.UNKNOWN

    with _client() as c:
        health = c.get("/health").json()
    assert health["build"]["commit"] == body["build"]["commit"]


def test_an_unknown_build_never_matches_a_commit():
    """"I cannot tell" must not be reported as "yes".

    A deploy check that treated a missing environment variable as a match would report
    success for every commit ever asked about, which is exactly the false confidence this
    field exists to remove.
    """
    from brambleloop.core import build

    assert build.serves("2006c37", {"RAILWAY_GIT_COMMIT_SHA": "2006c37abcdef0123456"})
    assert build.serves("2006c37abcdef0123456", {"RAILWAY_GIT_COMMIT_SHA": "2006c37"})
    assert not build.serves("2006c37", {})
    assert not build.serves("2006c37", {"RAILWAY_GIT_COMMIT_SHA": ""})
    assert not build.serves("", {"RAILWAY_GIT_COMMIT_SHA": "2006c37abcdef0123456"})
    assert not build.serves("deadbee", {"RAILWAY_GIT_COMMIT_SHA": "2006c37abcdef0123456"})
    assert build.identity({})["known"] is False


def test_a_reworded_owner_action_is_restated_in_place_not_queued_twice():
    """The owner reads a queue, so one decision must appear once, with the live figure.

    The fee approval derives its figure from the catalogue. When the catalogue grows the
    sentence changes, and a queue that compares sentences shows the owner two entries asking
    approval for two different amounts for the same decision. The row is restated instead.
    """
    import time

    from sqlalchemy import select

    from brambleloop.core.models import Listing, OwnerAction

    def fee_rows() -> list:
        with app_main.db.session() as s:
            return [(a.id, a.action) for a in s.scalars(select(OwnerAction))
                    if a.requirement_key == "listing_fees"]

    def assessments() -> int:
        """How many times the readiness job has actually run.

        Waiting for "a fee row exists" is not enough after the first run: it is already
        true, so the wait returns before the second assessment has touched anything and the
        test then reports a restate that never had a chance to happen.
        """
        from brambleloop.core.models import AuditLog

        with app_main.db.session() as s:
            return len([r for r in s.scalars(select(AuditLog))
                        if r.action == "launch.assessed"])

    def run_readiness(key: str) -> None:
        before = assessments()
        JobQueue(app_main.db).enqueue("orchestrator", "launch.readiness", {},
                                     idempotency_key=key)
        with _client() as c:
            deadline = time.time() + 40
            while time.time() < deadline:
                if assessments() > before:
                    return
                time.sleep(0.5)
        raise AssertionError("the readiness job never ran")

    run_readiness("test:restate-1")
    first = fee_rows()
    assert len(first) == 1, first
    row_id, before = first[0]

    # Grow the catalogue, which is what changes the figure. Built from scratch rather than
    # cloned, because this suite's warehouse may hold no listings at all when this runs and
    # the fee approval is queued regardless of the count.
    with app_main.db.session() as s:
        for i in range(6):
            s.add(Listing(product_slug=f"restate-extra-{i}", version="1.0.0",
                          title=f"Restate Extra {i}", description="a drafted listing",
                          price_cad=9.5, tags=["crochet"], state="draft"))

    run_readiness("test:restate-2")
    after = fee_rows()
    assert len(after) == 1, [a for _, a in after]
    assert after[0][0] == row_id, "the action was replaced instead of restated"
    assert after[0][1] != before, \
        "the figure did not follow the catalogue, so the restate path never ran"


def test_an_owner_action_queued_before_it_had_an_identity_is_adopted_not_duplicated():
    """The upgrade path, tested against the shape production was actually in.

    Production held seven owner actions queued before `requirement_key` existed, one of
    which -- the fee approval -- had since changed its wording because the figure now comes
    from the catalogue. Matching on full text would have adopted the six unchanged rows and
    added an eighth beside the one that moved, which is the duplicate this whole fix exists
    to prevent.

    Both assessments run inside one client, because the embedded worker stops when a client
    context exits and a later test cannot assume an earlier one left it running.
    """
    import time

    from sqlalchemy import select

    from brambleloop.core.models import AuditLog, OwnerAction

    stale_fee = (
        "Confirm you accept Etsy's listing fees for the opening catalogue: US$0.20 per "
        "listing for 4 months, so about US$1.80 (CA$2.50) for nine listings, plus 6.5% "
        "transaction fee and payment processing on each sale.")

    def assessments() -> int:
        with app_main.db.session() as s:
            return len([r for r in s.scalars(select(AuditLog))
                        if r.action == "launch.assessed"])

    with _client() as c:
        def run_readiness(key: str) -> None:
            before = assessments()
            JobQueue(app_main.db).enqueue("orchestrator", "launch.readiness", {},
                                         idempotency_key=key)
            deadline = time.time() + 60
            while time.time() < deadline:
                if assessments() > before:
                    return
                time.sleep(0.5)
            raise AssertionError(f"the readiness job never ran for {key}")

        run_readiness("test:adopt-1")

        # Put the queue back into the pre-upgrade shape: no identities, and the fee row
        # carrying the wording it had before the figure was derived.
        with app_main.db.session() as s:
            rows = list(s.scalars(select(OwnerAction)))
            assert rows, "the readiness job queued nothing"
            for row in rows:
                if row.requirement_key == "listing_fees":
                    row.action = stale_fee
                row.requirement_key = ""
            count_before = len(rows)

        run_readiness("test:adopt-2")

    with app_main.db.session() as s:
        after = list(s.scalars(select(OwnerAction)))
    assert len(after) == count_before, \
        f"owner actions duplicated across the upgrade: {count_before} -> {len(after)}"
    assert all(a.requirement_key for a in after), \
        [a.action[:50] for a in after if not a.requirement_key]
    fee = [a for a in after if a.requirement_key == "listing_fees"]
    assert len(fee) == 1, [f.action[:60] for f in fee]
    assert fee[0].action != stale_fee, "the adopted row kept its stale figure"


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
    runner.stop()
    sys.exit(1 if fails else 0)
