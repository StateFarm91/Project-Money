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



def test_a_readiness_assessment_can_be_started_on_demand_and_is_idempotent_per_minute():
    """A daily cadence is right unattended and too slow after a deploy.

    The owner queue's wording comes from the assessment, so when a deploy changes what an
    action should say, the queue holds the old wording until midnight. The one time that
    mattered it was holding a fee figure costed for nine listings against a catalogue of
    sixteen, and there was no way to ask for a fresh assessment without waiting.

    Keyed to the minute like the chain rebuild, so a burst of clicks collapses into one.
    """
    with _client() as c:
        first = c.post("/api/launch-readiness").json()
        second = c.post("/api/launch-readiness").json()

    assert first["enqueued"] is True, first
    assert second["enqueued"] is False, second
    assert "idempotent" in second["reason"], second


def test_a_just_started_runner_reads_as_starting_and_a_silent_one_still_reads_as_dead():
    """Observed in production: /api/verify failed for ninety seconds after a deploy.

    The worker waits 25s before its first pass and the scheduler ticks every 60s, so a
    freshly deployed container genuinely has no tick to report for the first minute and a
    half. Reporting that as a dead worker means every deploy opens a window where the
    verification endpoint says the system is broken -- and the operator loop tells whoever
    sees it that a failing check is the highest-value thing to work on, so the cost is a
    session chasing a phantom or "fixing" something that is fine.

    The grace is bounded and derived from the runner's own knobs. The cases that must still
    fail are the point of the test: a worker that started long ago and never ticked, and one
    that ticked and then went quiet.
    """
    from datetime import datetime, timedelta, timezone

    from brambleloop.app.runner import RunnerState, startup_grace_seconds

    grace = startup_grace_seconds()
    assert grace > 0
    now = datetime.now(timezone.utc)

    just_started = RunnerState(enabled=True, worker_started_at=now - timedelta(seconds=5))
    assert just_started.starting is True
    assert just_started.to_dict()["worker_starting"] is True

    # Bounded: the moment the grace expires, a worker with no tick is dead again.
    long_silent = RunnerState(enabled=True,
                              worker_started_at=now - timedelta(seconds=grace + 60))
    assert long_silent.starting is False, "the grace does not expire, so it hides a dead worker"
    assert long_silent.to_dict()["worker_alive"] is False

    # Ticking is not starting, and a worker that stopped ticking is neither.
    ticking = RunnerState(enabled=True, worker_started_at=now - timedelta(seconds=5),
                          worker_last_tick=now)
    assert ticking.starting is False
    assert ticking.to_dict()["worker_alive"] is True

    went_quiet = RunnerState(enabled=True,
                             worker_started_at=now - timedelta(seconds=900),
                             worker_last_tick=now - timedelta(seconds=600))
    assert went_quiet.starting is False
    assert went_quiet.to_dict()["worker_alive"] is False

    # A runner that never started at all is not "starting".
    never = RunnerState(enabled=True)
    assert never.starting is False


def test_verify_reports_whether_the_runner_is_starting_rather_than_deciding_silently():
    """A check that passes has to say why, or nobody can tell a pass from a pardon.

    Deliberately not stubbed: this suite runs a live embedded worker, and setting
    `runner.STATE` by hand races the thread that is ticking it -- the first attempt at this
    test failed because the worker ticked microseconds after the assignment, which is the
    worker being healthy rather than the check being wrong. So this asserts the two things
    that cannot race: the endpoint surfaces the flag, and it agrees with the runner at the
    moment it answered. `RunnerState.starting` itself is covered exhaustively by the test
    above, including the cases that must still read as dead.
    """
    from brambleloop.app import runner as runner_mod

    with _client() as c:
        body = c.get("/api/verify").json()

    checks = {x["check"]: x for x in body["checks"]}
    for name in ("worker_is_alive", "scheduler_has_ticked"):
        assert "starting" in checks[name]["evidence"], checks[name]["evidence"]
        assert isinstance(checks[name]["evidence"]["starting"], bool)

    # A live worker in this suite is either ticking or within its grace; either way the
    # check must pass, and it must not pass for both reasons at once.
    state = runner_mod.STATE.to_dict()
    assert checks["worker_is_alive"]["ok"] is True, checks["worker_is_alive"]
    assert not (state["worker_alive"] and state["worker_starting"]), state


def test_the_command_centre_shows_every_build_2_subsystem():
    """The owner asked not to have to infer progress from code logs.

    Seven blocks, each answering a question the owner actually has: how much of Build 2
    exists, can the mission see anything, what is about to miss its window, how likely the
    revenue target is, whether the creative standard is being met, what is improving, and
    what capabilities and spend are live.
    """
    body = _client().get("/").text

    for block in ("Build 2 coverage", "MJs mission", "Seasonal deadlines",
                  "CA$5,000/month model", "Creative standard", "Improvement",
                  "Capabilities and spend"):
        assert block in body, f"{block} is missing from the command centre"

    # The numbers are rendered, not just the headings.
    assert "executable left" in body
    assert "modelled probability" in body
    assert "binding layer" in body


def test_one_unhappy_subsystem_does_not_take_the_whole_dashboard_down():
    """A page that fails to render because one block raised tells the owner nothing about
    the twelve that are fine — and it fails at exactly the moment they most need to look.
    """
    import brambleloop.app.main as main

    body = _client().get("/").text
    assert "unavailable:" not in body, "a block is already failing on a healthy system"

    # Break one block's data source and confirm the page still renders everything else.
    original = main.JobQueue
    try:
        from brambleloop.scale import confidence

        def explode(*args, **kwargs):
            raise RuntimeError("deliberate")

        real = confidence.probability
        confidence.probability = explode
        try:
            broken = _client().get("/")
            assert broken.status_code == 200
            assert "unavailable: RuntimeError" in broken.text
            # Everything else still rendered.
            assert "Build 2 coverage" in broken.text
            assert "MJs mission" in broken.text
            assert "Owner action required" in broken.text or "Launch readiness" in broken.text
        finally:
            confidence.probability = real
    finally:
        main.JobQueue = original


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
