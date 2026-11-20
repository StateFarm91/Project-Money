"""W4-CCNOTIFY: F-897 Smart Notification Policy -- deadlines and commercial events.

Criterion (registry F-897, quoted): "Notify the owner for decisions, risk, deadlines,
meaningful commercial events and anomalies - not routine machine chatter. Alerts are
deduplicated, severity-ranked and actionable."

Decisions, risk, anomalies, dedupe, ranking and quiet hours were already covered; this adds
deadlines (incident detail.deadline, open owner actions' expires_at) and commercial events
(first order, per-day orders, refunds) from durable state, and checks every alert is
actionable. The external channel stays GATED (CASL + owner authority): in-app only.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_ccnotify.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccnotify_")


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _now():
    return datetime.now(timezone.utc)


def _by_key(listing):
    return {n["dedupe_key"]: n for n in listing["notifications"] + listing["digest"]}


def test_no_orders_means_no_commercial_alert_and_routine_jobs_stay_suppressed():
    from brambleloop.app.command_center import notifications as N
    from brambleloop.core.models import Job, JobStatus

    db = _db()
    with db.session() as s:
        for i in range(5):
            s.add(Job(agent="validator", job_type="routine.tick", status=JobStatus.DONE, finished_at=_now()))
    out = N.listing(db)
    keys = _by_key(out)
    assert not [k for k in keys if k.startswith("commercial:")], keys
    assert not [n for n in keys.values() if "routine" in n["title"].lower()], keys
    assert out["suppressed_count"] >= 5, out["suppressed_count"]
    assert "orders" in out["sources"]


def test_commercial_events_are_aggregated_ranked_and_deduplicated():
    from brambleloop.app.command_center import notifications as N
    from brambleloop.core.models import Customer, Order

    db = _db()
    with db.session() as s:
        c = Customer(customer_ref="c1")
        s.add(c)
        s.flush()
        for i in range(3):
            s.add(Order(customer_id=c.id, external_ref=f"o{i}", product_slug="placemat",
                        version="1.0.0", at=_now(), revenue_cad=10.0,
                        refunded=(i == 2)))
    keys = _by_key(N.listing(db))
    first = keys["commercial:first_order"]
    assert first["severity"] == "high" and first["category"] == "commercial", first
    day = [k for k in keys if k.startswith("commercial:orders:")]
    assert len(day) == 1, keys  # one per day, never one alert per sale
    assert keys[day[0]]["occurrences"] == 3 and keys[day[0]]["severity"] == "low"
    refund = keys["commercial:refund:o2"]
    assert refund["severity"] == "high" and refund["evidence"], refund
    # A second refresh deduplicates rather than adding rows.
    again = N.listing(db)
    assert again["refresh"]["created"] == 0 and again["refresh"]["deduplicated"] >= 3, again
    # Ranking: the low daily summary never outranks the high refund in the active list.
    sev = [n["severity"] for n in again["notifications"]]
    assert sev == sorted(sev, key=lambda v: N.RANK[v]), sev


def test_deadlines_from_incidents_and_owner_actions_are_attached_and_escalate():
    from brambleloop.app.command_center import notifications as N
    from brambleloop.core.models import Incident, OwnerAction

    db = _db()
    soon = _now() + timedelta(hours=20)
    later = _now() + timedelta(days=10)
    beyond = _now() + timedelta(days=N.DEADLINE_HORIZON_DAYS + 5)
    with db.session() as s:
        s.add(Incident(signature="etsy.policy:1", severity="P2", summary="policy flag",
                       detail={"deadline": soon.isoformat()}))
        s.add(OwnerAction(requirement_key="k.soon", action="Answer the bank", reason="r",
                          consequence_of_delay="payouts stop", expires_at=soon))
        s.add(OwnerAction(requirement_key="k.later", action="Renew the domain",
                          expires_at=later))
        s.add(OwnerAction(requirement_key="k.beyond", action="Far future", expires_at=beyond))
        s.add(OwnerAction(requirement_key="k.done", action="Already done", done=True,
                          expires_at=soon))
    out = N.listing(db)
    keys = _by_key(out)
    inc = [n for k, n in keys.items() if k.startswith("incident:")][0]
    assert inc["deadline"] and inc["severity"] == "high", inc  # P2 raised: due within 48 h
    dl = {k: n for k, n in keys.items() if k.startswith(("owner_deadline:", "approval:"))
          and n["deadline"]}
    titles = " | ".join(n["title"] for n in dl.values())

    def _has(due):
        return any(abs(datetime.fromisoformat(n["deadline"]) - due).total_seconds() < 2
                   for n in dl.values())

    # Each open owner deadline inside the horizon surfaces exactly once (on its own, or on
    # the approval card that merges it).
    assert _has(soon) and _has(later), dl
    assert not _has(beyond), dl
    assert "Far future" not in titles and "Already done" not in titles, titles
    assert dl, keys  # INTEG3 (test_vacuity): the loop below must have something to check
    for n in dl.values():
        due = datetime.fromisoformat(n["deadline"])
        if due - _now() <= timedelta(hours=N.DEADLINE_SOON_HOURS):
            assert N.RANK[n["severity"]] <= N.RANK["high"], n
    # Within one severity the nearest deadline comes first.
    act = out["notifications"]
    assert len(act) >= 2, act  # INTEG3 (test_vacuity): an ordering needs two to compare
    for a, b in zip(act, act[1:]):
        if a["severity"] == b["severity"] and a["acked_at"] is None and b["acked_at"] is None \
                and a["deadline"] and b["deadline"]:
            assert a["deadline"] <= b["deadline"], (a, b)
    # Satisfying the owner action resolves its deadline notification.
    with db.session() as s:
        from sqlalchemy import select
        for row in s.scalars(select(OwnerAction)):
            row.done = True
    keys2 = _by_key(N.listing(db))
    assert not [k for k in keys2 if k.startswith("owner_deadline:")], keys2


def test_every_alert_is_actionable():
    from brambleloop.app.command_center import notifications as N
    from brambleloop.core.models import Customer, Incident, Order, OwnerAction

    db = _db()
    with db.session() as s:
        c = Customer(customer_ref="c9")
        s.add(c)
        s.flush()
        s.add(Order(customer_id=c.id, external_ref="x1", product_slug="p", version="1.0.0",
                    at=_now(), refunded=True))
        s.add(Incident(signature="sig", severity="P1", summary="something broke"))
        s.add(OwnerAction(requirement_key="k", action="Do it",
                          expires_at=_now() + timedelta(days=3)))
    out = N.listing(db)
    allv = out["notifications"] + out["digest"]
    assert len(allv) >= 4, allv
    for n in allv:
        assert n["deep_link"].startswith("/cc/#/"), n
        assert n["consequence"], n
        assert n["evidence"], n
        assert n["severity"] in N.SEVERITIES, n
        assert n["delivered"] == "in_app", n  # external channel GATED
    assert N.get_policy(db)["channels"] == ["in_app"]


def test_view_sorts_by_deadline_within_severity():
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/notifications.js").read_text()
    assert "function dueMs(n)" in js and "(dueMs(a) - dueMs(b))" in js
    assert "meaningful sales events" in js


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc()
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
