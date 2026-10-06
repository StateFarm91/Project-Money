"""Marketplace Insights, recorded by the owner, and never asked for twice (#236, #37).

Marketplace Insights has no API. The intake is a person reading Shop Manager and recording
what it said through an authenticated POST, with every row labelled as exactly that. The
budgeter reads the store so a keyword already on file is not spent on again, and the gate
opens only when a real reading exists.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/insights_intake.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"
OPS_TOKEN = "operator-token-for-insights-intake-0123456789"
os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import insights, insights_budget  # noqa: E402

AUTH = {"Authorization": f"Bearer {OPS_TOKEN}"}


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/ins.sqlite")
    db.create_all()
    return db


def test_the_gate_opens_only_on_a_real_reading():
    db = _db()
    assert insights.insights_recorded(db) is False
    insights.record(db, keyword="Crochet Hat Pattern", search_count=1200,
                    listing_count=5400, related_terms=["beanie pattern"],
                    trend_direction="up", geography="CA", recorded_by="owner")
    assert insights.insights_recorded(db) is True
    row = insights.snapshots(db)[0]
    assert row["keyword"] == "crochet hat pattern"
    assert row["basis"] == "owner_recorded_shop_manager" and row["recorded_by"] == "owner"


def test_a_reading_with_nothing_in_it_or_nobody_behind_it_is_refused():
    db = _db()
    bad = [dict(keyword="", search_count=1, recorded_by="owner"),
           dict(keyword="hat", search_count=1, recorded_by=""),
           dict(keyword="hat", recorded_by="owner"),
           dict(keyword="hat", search_count=-4, recorded_by="owner"),
           dict(keyword="hat", search_count=3, trend_direction="sideways",
                recorded_by="owner"),
           dict(keyword="hat", search_count=3, recorded_by="owner",
                observed_on=(date.today() + timedelta(days=5)).isoformat())]
    for kwargs in bad:
        try:
            insights.record(db, **kwargs)
        except insights.InsightsRefused:
            continue
        raise AssertionError(f"accepted {kwargs}")
    assert insights.insights_recorded(db) is False


def test_the_allocator_skips_keywords_already_recorded():
    db = _db()
    insights.record(db, keyword="crochet hat pattern", search_count=900, recorded_by="owner")
    assert "crochet hat pattern" in insights.queried_keywords(db)

    plan = insights_budget.keyword_plan(db, {"hats": 3})
    hats = plan["by_pod"]["hats"]
    assert "crochet hat pattern" in hats["skipped_already_recorded"]
    assert "crochet hat pattern" not in hats["ask"] and len(hats["ask"]) == 3
    # And the snapshot counts as a prior query against the pod it routes to.
    assert insights_budget.prior_queries(db)["hats"] == 1

    # A reading older than the re-query window is worth asking again.
    old = _db()
    insights.record(old, keyword="crochet hat pattern", search_count=900,
                    recorded_by="owner",
                    observed_on=(date.today() - timedelta(days=200)).isoformat())
    assert "crochet hat pattern" not in insights.queried_keywords(old)


def test_the_intake_route_is_authenticated_and_records_the_reading():
    from fastapi.testclient import TestClient

    from brambleloop.app import main as app_main

    app_main.db.create_all()
    with TestClient(app_main.app) as client:
        refused = client.post("/api/insights/snapshot",
                              json={"keyword": "hat", "search_count": 3,
                                    "recorded_by": "owner"})
        assert refused.status_code == 401

        empty = client.post("/api/insights/snapshot", headers=AUTH,
                            json={"keyword": "hat", "recorded_by": "owner"})
        assert empty.status_code == 400

        ok = client.post("/api/insights/snapshot", headers=AUTH, json={
            "keyword": "crochet bag pattern", "search_count": 800, "listing_count": 9000,
            "related_terms": ["tote pattern"], "trend_direction": "flat",
            "geography": "US", "recorded_by": "owner"})
        assert ok.status_code == 200, ok.text
        assert ok.json()["basis"] == "owner_recorded_shop_manager"

        listed = client.get("/api/insights").json()
        assert listed["recorded"] is True
        assert listed["snapshots"][0]["keyword"] == "crochet bag pattern"
    assert insights.insights_recorded(app_main.db) is True


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc!r}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
