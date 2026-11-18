"""WS4 LOWs from verdict 6979645791 (before Stage D relies on the G-SHADOW reading).

* the three surviving mutants: experiment exclusion; the stop watch ignoring readings from
  before the approval; activation rejecting a MET for a different approval;
* the reading is pure: G-SHADOW writes no `experiment.refused` (or any other) row;
* the per-run load is bounded in SQL, with the same result.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
from datetime import timedelta
from unittest.mock import patch

from sqlalchemy import func, select  # noqa: E402

from brambleloop.core.models import AuditLog  # noqa: E402
from brambleloop.ops import standing_boundary as SB  # noqa: E402
from brambleloop.ops import standing_policy as sp  # noqa: E402
from brambleloop.ops import standing_shadow_gate as G  # noqa: E402
from brambleloop.ops import standing_stop as ST  # noqa: E402
from brambleloop.visual import experiment  # noqa: E402
from test_ws4_g_shadow import (LATER, NOW, _met_db, _owner_keys, _readings,  # noqa: E402
                               _restore_all)
from test_ws4_policy_object import _approve, _db, content  # noqa: E402


def _audit_count(db):
    with db.session() as s:
        return s.scalar(select(func.count(AuditLog.id)))


def _mark_experiment(db, slug):
    with db.session() as s:
        s.add(AuditLog(actor=experiment.ACTOR, action=experiment.ACTION_CONTROLLED,
                       artifact=f"{slug}@1.0.0", detail={"release": "e" * 64}))


def test_an_experiment_never_counts_and_the_reading_writes_nothing():
    try:
        db, c, a = _met_db()
        assert G.g_shadow(db, now=LATER, record=False)["verdict"] == "MET"
        _mark_experiment(db, "p5")                      # 10 candidates -> 9 real ones
        before = _audit_count(db)
        out = G.g_shadow(db, now=LATER, record=False)
        assert out["verdict"] == "NOT_MET", out["criteria"]
        assert "9 distinct candidate" in out["criteria"]["shadow_period"]["why"]
        # A reading is pure: no experiment.refused row, nothing else either.
        assert _audit_count(db) == before
        with db.session() as s:
            assert not s.scalars(select(AuditLog).where(
                AuditLog.action == "experiment.refused")).first()
        # Unreadable registrations are not a candidate (fail closed), not "no experiment".
        with patch.object(experiment, "experiment_rows",
                          lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))):
            assert G._certified(db, "p1", "1.0.0", f"{1:064d}") is False
    finally:
        _restore_all()


def test_stop_watch_readings_from_before_the_approval_never_count():
    try:
        db, c = _db(), content()
        _owner_keys()
        _approve(db, c)                                 # signed approved_at = NOW
        now = NOW + timedelta(days=3)
        # Readings every 5 minutes for 8 days, five of them before the approval at NOW,
        # stored in time order (an honest stop watch).
        _readings(db, c, start=NOW - timedelta(days=5), end=now)
        fact = G._stop_watch(db, c["policy_id"], now, approved_at=NOW)
        assert fact["state"] == SB.FAIL and "has not read this policy for 7 days" in fact["why"]
        # The same readings with no approval floor would have passed: the floor is what bites.
        assert G._stop_watch(db, c["policy_id"], now, approved_at=None)["state"] == SB.PASS
    finally:
        _restore_all()


def test_a_reading_minutes_before_the_approval_cannot_open_the_seven_day_window():
    """Inside CLOCK_SKEW of the approval the SQL bound still loads a pre-approval row; the
    approval floor in `_trusted` is what refuses it."""
    try:
        db, c = _db(), content()
        _owner_keys()
        _approve(db, c)                                 # signed approved_at = NOW
        now = NOW + timedelta(days=7, minutes=2)        # the window starts 2 min after it
        with db.session() as s:
            t = NOW - timedelta(minutes=5)              # one reading just before approval
            s.add(AuditLog(actor=ST.ACTOR, action=ST.READING, artifact=c["policy_id"], at=t,
                           detail={"policy_id": c["policy_id"], "read_at": t.isoformat()}))
        _readings(db, c, start=NOW + timedelta(minutes=5), end=now)
        fact = G._stop_watch(db, c["policy_id"], now, approved_at=NOW)
        assert fact["state"] == SB.FAIL, fact
    finally:
        _restore_all()


def test_activation_rejects_a_met_reading_for_another_approval():
    try:
        db, c, a = _met_db()

        def met_for(aid):
            return lambda db_, now=None, record=False: {
                "verdict": "MET", "approval_id": aid, "criteria": {}}
        with patch.object(G, "g_shadow", met_for(a + 1)):
            why = sp.activation_refusals(db, a, now=LATER)
        assert any("G-SHADOW is not MET for this approval" in w for w in why), why
        with patch.object(G, "g_shadow", met_for(a)):
            why = sp.activation_refusals(db, a, now=LATER)
        assert not any("G-SHADOW" in w for w in why), why
    finally:
        _restore_all()


def test_the_load_is_bounded_in_sql_and_the_reading_is_unchanged():
    try:
        db, c, a = _met_db()
        expected = G.g_shadow(db, now=LATER, record=False)
        # Old readings, stored long before the approval: never evidence, so never loaded.
        _readings(db, c, start=NOW - timedelta(days=60), end=NOW - timedelta(days=50),
                  every_minutes=60)
        everything = G._rows(db, ST.READING, c["policy_id"], ST.ACTOR)
        bounded = G._rows(db, ST.READING, c["policy_id"], ST.ACTOR, since=NOW, now=LATER)
        assert len(bounded) < len(everything)
        assert all(r[1].replace(tzinfo=None) >= (NOW - G.CLOCK_SKEW).replace(tzinfo=None)
                   for r in bounded)
        got = G.g_shadow(db, now=LATER, record=False)
        assert got["verdict"] == expected["verdict"] == "MET"
        assert got["criteria"] == expected["criteria"]
    finally:
        _restore_all()


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
