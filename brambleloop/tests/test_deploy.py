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
                "owner_actions_open", "runner"):
        assert key in body, key


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

        # The scheduler's own cadence enqueues the planning cycle; wait for it to land.
        deadline = time.time() + 40
        products: list[str] = []
        while time.time() < deadline:
            with app_main.db.session() as s:
                products = [p.slug for p in s.scalars(select(Product))]
            if products:
                break
            time.sleep(0.5)

        assert products, "the embedded runner produced no products unattended"
        body = c.get("/api/status").json()
        assert body["runner"]["worker_alive"] is True
        assert body["certified_versions"] >= 1
        # Shadow mode still refuses to publish, even running unattended in a container.
        assert body["dead_letters"] >= 1


def test_scheduler_tick_endpoint_is_idempotent_within_a_window():
    with _client() as c:
        first = c.post("/api/scheduler/tick").json()["enqueued"]
        second = c.post("/api/scheduler/tick").json()["enqueued"]
    assert second == [], f"a repeated tick re-enqueued {second} (first was {first})"


def test_runner_state_is_honest_about_a_worker_that_is_not_running():
    from brambleloop.app.runner import RunnerState

    st = RunnerState()
    assert st.to_dict()["worker_alive"] is False
    assert st.to_dict()["enabled"] is False


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
