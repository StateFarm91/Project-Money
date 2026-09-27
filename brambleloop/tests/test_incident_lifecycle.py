"""Incidents close when their condition stops holding, and they say what closed them.

Production on 2026-09-26 held seventeen open incidents, nearly all of them conditions that
had stopped being true. These tests hold `ops.incident_lifecycle` to its two rules: a
condition that still holds is restated on one row, and one that stopped is resolved with a
sentence and a time -- never with a bare checkbox.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident  # noqa: E402
from brambleloop.ops import incident_lifecycle as L  # noqa: E402

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _rows(db, prefix=""):
    with db.session() as s:
        rows = [r for r in s.scalars(select(Incident)) if r.signature.startswith(prefix)]
        for r in rows:
            s.expunge(r)
        return rows


def test_a_condition_that_still_holds_is_restated_on_one_row():
    db = _db()
    with db.session() as s:
        _, new = L.open_or_restate(s, signature="x:a", severity="P2", summary="a",
                                   detail={"n": 1}, now=NOW)
        assert new is True
    with db.session() as s:
        _, new = L.open_or_restate(s, signature="x:a", severity="P2", summary="a",
                                   detail={"n": 2}, now=NOW + timedelta(hours=1))
        assert new is False
    rows = _rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row.report_count == 2
    assert row.detail["n"] == 2, "the open row shows today's reading, not the first one"
    assert row.detail["first_seen"] == NOW.isoformat()
    assert row.detail["last_seen"] == (NOW + timedelta(hours=1)).isoformat()


def test_reconcile_resolves_only_what_stopped_and_says_why():
    db = _db()
    with db.session() as s:
        for sig in ("x:a", "x:b", "y:c"):
            L.open_or_restate(s, signature=sig, severity="P2", summary=sig, now=NOW)
    later = NOW + timedelta(hours=2)
    with db.session() as s:
        out = L.reconcile(s, "x:", lambda row: row.signature == "x:a",
                          resolution=lambda row: f"{row.signature} stopped", now=later)
    assert out == {"prefix": "x:", "resolved": ["x:b"], "still_open": ["x:a"]}
    by = {r.signature: r for r in _rows(db)}
    assert by["x:b"].resolved is True
    assert by["x:b"].detail["resolution"] == "x:b stopped"
    assert by["x:b"].detail["resolved_at"] == later.isoformat()
    assert by["x:a"].resolved is False and by["x:a"].detail["last_seen"] == later.isoformat()
    # Outside the prefix is untouched -- not resolved, and not restated either.
    assert by["y:c"].resolved is False and by["y:c"].report_count == 1


def test_a_resolution_without_words_is_refused():
    db = _db()
    with db.session() as s:
        L.open_or_restate(s, signature="x:a", severity="P2", summary="a", now=NOW)
    try:
        with db.session() as s:
            L.reconcile(s, "x:", lambda row: False, resolution="  ")
    except ValueError as e:
        assert "checkbox" in str(e)
    else:
        raise AssertionError("an incident was closed without saying what closed it")
    assert _rows(db)[0].resolved is False


def test_a_prefix_is_matched_exactly_rather_than_as_a_like_pattern():
    """`_` is a LIKE wildcard, so `seasonal.at_risk:` would also match its neighbours."""
    db = _db()
    with db.session() as s:
        L.open_or_restate(s, signature="seasonal.at_risk:a", severity="P2", summary="a")
        L.open_or_restate(s, signature="seasonal.atXrisk:b", severity="P2", summary="b")
    with db.session() as s:
        out = L.reconcile(s, "seasonal.at_risk:", lambda row: False, resolution="gone")
    assert out["resolved"] == ["seasonal.at_risk:a"]


def test_resolving_named_signatures_touches_nothing_else():
    db = _db()
    with db.session() as s:
        for sig in ("x:a", "x:b"):
            L.open_or_restate(s, signature=sig, severity="P2", summary=sig, now=NOW)
    with db.session() as s:
        assert L.resolve_signatures(s, ["x:a"], resolution="fixed by deploy") == ["x:a"]
    by = {r.signature: r for r in _rows(db)}
    assert by["x:a"].resolved and by["x:a"].detail["resolution"] == "fixed by deploy"
    assert by["x:b"].resolved is False and by["x:b"].report_count == 1


def test_the_snapshot_groups_by_kind_and_keeps_a_day_of_resolutions():
    db = _db()
    with db.session() as s:
        for sig in ("health:queue_age", "seasonal.at_risk:a:Halloween:2026",
                    "seasonal.at_risk:b:Christmas:2026", "build.stalled"):
            L.open_or_restate(s, signature=sig, severity="P2", summary=sig, now=NOW)
        L.reconcile(s, "build.stalled", lambda row: False, resolution="moving",
                    now=NOW - timedelta(hours=1))
        L.reconcile(s, "seasonal.at_risk:a", lambda row: False, resolution="missed",
                    now=NOW - timedelta(hours=30))
        # Closed by older code with no reason: counted, never shown as closed-with-evidence.
        s.add(Incident(severity="P3", signature="old:thing", summary="x", resolved=True,
                       detail={}))
    with db.session() as s:
        snap = L.snapshot(s, now=NOW)
    assert snap["open_total"] == 2
    assert set(snap["by_kind"]) == {"health", "seasonal.at_risk", "build.stalled"}
    assert [r["signature"] for r in snap["by_kind"]["build.stalled"]["resolved"]] == \
        ["build.stalled"]
    assert snap["by_kind"]["build.stalled"]["resolved"][0]["resolution"] == "moving"
    # Resolved thirty hours ago: outside the day, so not listed.
    assert snap["by_kind"]["seasonal.at_risk"]["resolved"] == []
    assert len(snap["by_kind"]["seasonal.at_risk"]["open"]) == 1
    assert snap["resolved_without_evidence_in_sample"] == 1


def test_the_incidents_endpoint_serves_the_snapshot():
    tmp = tempfile.mkdtemp()
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tmp}/incidents.sqlite"
    os.environ.setdefault("BRAMBLELOOP_EMBEDDED_WORKER", "0")
    from fastapi.testclient import TestClient

    from brambleloop.app import main as app_main

    app_main.db.create_all()
    with app_main.db.session() as s:
        L.open_or_restate(s, signature="health:disk", severity="P1", summary="disk")
        L.open_or_restate(s, signature="build.stalled", severity="P2", summary="s")
        L.reconcile(s, "build.stalled", lambda row: False, resolution="moving again")
    body = TestClient(app_main.app).get("/api/incidents").json()
    assert "health" in body["by_kind"] and "build.stalled" in body["by_kind"]
    assert body["by_kind"]["build.stalled"]["resolved"][0]["resolution"] == "moving again"
    assert any(r["signature"] == "health:disk"
               for r in body["by_kind"]["health"]["open"])


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
