"""Dedicated capacity per event, and the failure that looks like an org chart.

v1.4.3 requirement 287. Major events get persistent strike teams; additional events get one
when demand evidence supports it.

The failure is not that somebody creates a bad team. It is that six teams exist, each holding
a slice of the same finite capacity, and every one of them is under-resourced by exactly as
much as the others are notional. So the tests are about capacity being real: a team is a share
or it is a name, an extra team brings rows, and a team whose occasion has passed releases what
it held without anybody remembering.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.seasonal import teams as T  # noqa: E402

TODAY = date(2026, 9, 19)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/teams.sqlite")
    db.create_all()
    return db


def _observe(db, text: str, times: int = 1) -> None:
    from datetime import datetime, timezone

    from brambleloop.core.models import LearningObservation

    with db.session() as s:
        for i in range(times):
            s.add(LearningObservation(
                domain="seasonal_behaviour", source=f"a named publication {i}",
                citation=f"https://example.invalid/{i}", summary=text,
                observed_on=datetime(2026, 8, 1, tzinfo=timezone.utc)))


# ---- who gets a team ------------------------------------------------------


def test_the_named_events_have_standing_teams():
    db = _db()
    for event in T.STANDING_EVENTS:
        permission = T.may_create(db, event)
        assert permission["allowed"] is True
        assert permission["standing"] is True


def test_a_fourth_team_brings_rows_rather_than_enthusiasm():
    db = _db()

    refused = T.may_create(db, "Diwali")
    assert refused["allowed"] is False
    assert refused["evidence"] == 0
    assert "rather than enthusiasm" in refused["why"]

    _observe(db, "diwali decor searches rose across the category", T.DEMAND_EVIDENCE_FLOOR)
    allowed = T.may_create(db, "Diwali")
    assert allowed["allowed"] is True
    assert allowed["evidence"] >= T.DEMAND_EVIDENCE_FLOOR


def test_an_unearned_team_is_named_in_the_allocation_rather_than_dropped():
    allocation = T.allocate(_db(), today=TODAY, extra_events=("Diwali",))

    assert "Diwali" not in [t["event"] for t in allocation["teams"]]
    assert "Diwali" in [r["event"] for r in allocation["refused"]]


# ---- capacity is real -----------------------------------------------------


def test_every_team_holds_a_share_and_the_shares_fit():
    db = _db()
    allocation = T.allocate(db, today=TODAY)
    T.check(allocation)

    assert allocation["teams"]
    assert all(t["share"] > 0 for t in allocation["teams"])
    assert allocation["allocated_total"] <= 1.0 - T.EVERGREEN_RESERVE + 1e-6


def test_evergreen_work_keeps_its_reserve():
    """A seasonal programme that consumes everything leaves a shop excellent in December and
    absent in February."""
    allocation = T.allocate(_db(), today=TODAY)

    assert allocation["evergreen_reserve"] == T.EVERGREEN_RESERVE
    assert allocation["allocated_total"] + T.EVERGREEN_RESERVE <= 1.0 + 1e-6


def test_overlapping_occasions_scale_rather_than_overrun():
    allocation = T.allocate(_db(), today=TODAY)

    assert allocation["requested_total"] > allocation["allocated_total"]
    assert allocation["scaled_by"] < 1.0
    assert "occasions overlap" in allocation["note"]


def test_the_priority_programme_keeps_the_largest_share():
    allocation = T.allocate(_db(), today=TODAY)
    shares = {t["event"]: t["share"] for t in allocation["teams"]}

    assert shares["Christmas"] == max(shares.values())


def test_a_team_with_no_capacity_is_refused_as_an_org_chart_entry():
    allocation = T.allocate(_db(), today=TODAY)
    allocation["teams"][0]["share"] = 0.0
    try:
        T.check(allocation)
    except T.TeamRefused as e:
        assert "nowhere a product comes from" in str(e)
    else:
        raise AssertionError("a team with no capacity was accepted")


def test_teams_that_would_overrun_the_company_are_refused():
    allocation = T.allocate(_db(), today=TODAY)
    allocation["allocated_total"] = 0.99
    try:
        T.check(allocation)
    except T.TeamRefused as e:
        assert "notional" in str(e)
    else:
        raise AssertionError("teams were allowed to hold the whole company")


# ---- disbanding -----------------------------------------------------------


def test_a_team_whose_occasion_has_passed_releases_its_capacity_by_itself():
    """Without anybody remembering, which is how the next occasion gets staffed."""
    allocation = T.allocate(_db(), today=date(2026, 12, 20))

    disbanded = [d["event"] for d in allocation["disbanded"]]
    assert "Christmas" in disbanded
    assert "Christmas" not in [t["event"] for t in allocation["teams"]]
    assert "returns to the pool automatically" in allocation["disbanded"][0]["why"]


def test_a_priority_programme_with_neither_a_team_nor_a_reason_is_refused():
    allocation = T.allocate(_db(), today=TODAY)
    allocation["teams"] = [t for t in allocation["teams"] if t["event"] != "Christmas"]
    try:
        T.check(allocation)
    except T.TeamRefused as e:
        assert "no recorded reason" in str(e)
    else:
        raise AssertionError("a priority programme silently lost its team")


def test_capacity_released_by_one_occasion_is_available_to_the_next():
    early = T.allocate(_db(), today=TODAY)
    late = T.allocate(_db(), today=date(2026, 12, 20))

    assert late["allocated_total"] <= early["allocated_total"]
    assert "Christmas" in [d["event"] for d in late["disbanded"]]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
