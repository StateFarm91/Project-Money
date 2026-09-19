"""Ecosystem gaps turned into briefs, and the ways a gap report stops producing work.

v1.4.3 requirement 288: do not reduce an event to one blanket. The coverage matrix already
measures depth against the departments an event spans. What it could not do is say what to do
about a gap, and the failures worth holding tests on are the three ways that step goes wrong:
inventing a department the event does not have, briefing work whose launch window has already
closed, and counting the briefs themselves as depth.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.seasonal import depth  # noqa: E402

TODAY = date(2026, 9, 19)


def test_a_department_the_event_does_not_span_is_refused():
    """A brief for stockings at Easter is work invented to fill a queue, which is how a
    never-idle loop stops meaning anything."""
    try:
        depth.department_brief(event="Easter", department="stockings", days_away=200,
                               today=TODAY)
    except depth.DepthRefused as e:
        assert "does not span" in str(e)
    else:
        raise AssertionError("a brief was written for a department the event does not have")


def test_a_brief_names_forms_lanes_and_the_last_date_they_can_launch():
    brief = depth.department_brief(event="Christmas", department="ornaments",
                                   days_away=300, today=TODAY)

    assert brief["recommended"] is not None
    first = brief["startable_now"][0]
    assert first["form"] in depth.DEPARTMENT_FORMS["ornaments"]
    assert first["implied_lane"] in depth.LANE_ORDER
    assert first["latest_optimistic_launch"]
    assert first["fills_family_roles"], "a form that fills no family role is not a brief"


def test_a_department_past_its_window_is_next_season_not_this_one():
    """Spending the runway that is left on something nobody can buy in time is the expensive
    version of looking busy."""
    brief = depth.department_brief(event="Christmas", department="blankets", days_away=30,
                                   today=TODAY)

    assert brief["startable_now"] == []
    assert brief["recommended"] is None
    assert brief["past_the_window"]
    assert "next season's gap" in brief["note"]


def test_hurry_and_stop_are_kept_apart():
    """A high-risk lane belongs in its own bucket: a department told to hurry and one told to
    stop do different things, and collapsing them loses the season that was still winnable."""
    brief = depth.department_brief(event="Christmas", department="blankets", days_away=120,
                                   today=TODAY)

    assert brief["startable_now"] == []
    assert [o["form"] for o in brief["only_with_hurry"]] == ["rectangle_throw"]
    assert "hurry rather than a new plan" in brief["note"]


def test_the_plan_leads_with_what_can_still_be_started():
    plan = depth.depth_plan(today=TODAY, limit=20)

    startable = [b for b in plan["briefs"] if b["startable_now"]]
    assert startable, plan["brief_count"]
    assert plan["briefs"][0]["startable_now"], "the plan led with work nobody can start"


def test_briefs_are_never_counted_as_coverage():
    """A queue that counted its own briefs would report depth it does not have."""
    plan = depth.depth_plan(today=TODAY)
    empty = depth.depth_plan(today=TODAY, covered={})

    assert plan["ecosystem_depth"] == empty["ecosystem_depth"]
    assert plan["brief_count"] > 0
    assert "nothing here counts as coverage" in plan["note"]


def test_covering_a_department_removes_its_brief():
    before = depth.depth_plan(today=TODAY, limit=100)
    event = next(b["event"] for b in before["briefs"])
    department = next(b["department"] for b in before["briefs"] if b["event"] == event)

    after = depth.depth_plan(today=TODAY, limit=100,
                             covered={event: (department,)})

    assert not any(b["event"] == event and b["department"] == department
                   for b in after["briefs"])
    assert after["ecosystem_depth"] > before["ecosystem_depth"]


def test_an_uncalibrated_plan_says_so():
    plan = depth.depth_plan(today=TODAY)
    assert plan["calibrated"] is False


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
