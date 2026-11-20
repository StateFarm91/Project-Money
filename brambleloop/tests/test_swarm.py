"""Elastic capacity, and the four rules that stop a swarm becoming a crowd.

v1.4.3 requirements 34, 174, 175, 176, 186, 187, 192, 302. The spec wants dozens or hundreds
of specialists when they earn their place, and is equally explicit that redundant and weak
ones get merged or retired. A swarm that only grows is a cost centre wearing an org chart.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.swarm import orchestrate as orc  # noqa: E402


def test_a_band_is_never_traded_away_for_value():
    """#187. A large opportunity does not outrank a customer incident.

    Collapsing the ordering into one score is the tempting implementation, and it lets a
    CA$4,000 opportunity with a near deadline jump ahead of somebody's broken download.
    """
    incident = orc.WorkItem("inc", "customer_incident")
    lucrative = orc.WorkItem("opp", "new_opportunity", value_cad=5000, deadline_days=1)

    ordered = orc.schedule([lucrative, incident])
    assert [w.key for w in ordered] == ["inc", "opp"]
    assert incident.priority() < lucrative.priority()

    # Within a band, deadline and value do decide.
    soon = orc.WorkItem("a", "new_opportunity", deadline_days=5, value_cad=4000)
    later = orc.WorkItem("b", "new_opportunity", deadline_days=80, value_cad=100)
    assert orc.schedule([later, soon])[0].key == "a"

    # Unbanded work is refused: otherwise the enqueue call decides the priority.
    try:
        orc.WorkItem("x", "whenever")
    except orc.SwarmRefused as e:
        assert "priority band" in str(e)
    else:
        raise AssertionError("unbanded work was scheduled")


def test_fan_out_is_bounded_by_money_rather_than_by_a_headcount_constant():
    """#174 and #188 are the same requirement seen twice.

    The real ceiling is spend. A constant in the code is the artificial scarcity the spec
    objects to, and it is wrong in both directions: idle during a catalogue baseline and
    expensively awake on a quiet Tuesday.
    """
    plenty = orc.fan_out(open_work=400, budget_remaining_cad=25.0)
    assert plenty["granted"] == plenty["wanted"] == 50
    assert plenty["bounded_by"] == "work"

    broke = orc.fan_out(open_work=400, budget_remaining_cad=0.40)
    assert broke["granted"] == 8
    assert broke["bounded_by"] == "budget"

    quiet = orc.fan_out(open_work=1, budget_remaining_cad=25.0)
    assert quiet["granted"] == orc.MIN_SPECIALISTS

    pressed = orc.fan_out(open_work=40, budget_remaining_cad=25.0, deadline_pressure=True)
    assert pressed["wanted"] > orc.fan_out(open_work=40, budget_remaining_cad=25.0)["wanted"]

    # A free specialist makes the ceiling meaningless.
    try:
        orc.fan_out(open_work=10, budget_remaining_cad=5.0, cost_per_specialist_cad=0.0)
    except orc.SwarmRefused:
        pass
    else:
        raise AssertionError("a costless specialist was allowed")


def test_unowned_work_is_a_query_with_a_name():
    """#176. Work nobody owns is work nobody is watching — that is what unowned means."""
    items = [
        orc.WorkItem("a", "truth_defect", owner="quality_director"),
        orc.WorkItem("b", "new_opportunity"),
        orc.WorkItem("c", "housekeeping", state="done"),
        orc.WorkItem("d", "seasonal_deadline"),
    ]
    found = {o["key"] for o in orc.orphans(items)}
    assert found == {"b", "d"}, "an orphan was missed or a finished item was flagged"


def test_an_idle_agent_takes_the_backlog_rather_than_polling_or_stopping():
    """#186. Polling to look alive spends money to produce a heartbeat; stopping is a lie."""
    urgent = [orc.WorkItem("x", "truth_defect", owner="quality")]
    assert orc.next_work(urgent)["source"] == "queue"
    assert orc.next_work(urgent)["work"]["key"] == "x"

    idle = orc.next_work([])
    assert idle["source"] == "standing_backlog"
    assert idle["work"]["kind"] in orc.BAND_BY_KIND
    assert "look alive" in idle["why"]
    assert len(idle["backlog"]) >= 5
    # The backlog is real work, ordered: the benchmark check leads, housekeeping trails.
    assert idle["backlog"][0]["kind"] == "benchmark_change"


def test_three_identical_observations_stop_the_loop():
    """#34. A poll whose answer never changes is a loop; one whose answer changes is progress."""
    detector = orc.ThrashDetector()

    first = detector.observe("GET /api/status", {"pending": 0})
    second = detector.observe("GET /api/status", {"pending": 0})
    assert first["continue"] and second["continue"]

    third = detector.observe("GET /api/status", {"pending": 0})
    assert third["continue"] is False
    assert third["action"] == "replan"
    assert "stopped working and started spending" in third["why"]

    # A changing result is progress, and does not trip.
    moving = orc.ThrashDetector()
    for pending in (3, 2, 1, 0):
        assert moving.observe("GET /api/status", {"pending": pending})["continue"] is True

    # Same result, different call is also not a loop.
    mixed = orc.ThrashDetector()
    for call in ("a", "b", "c"):
        assert mixed.observe(call, {"same": True})["continue"] is True


def test_retirement_preserves_what_a_cell_learned_before_retiring_it():
    """#192. Discarding the knowledge costs more than the cell did."""
    now = datetime(2026, 9, 19, tzinfo=timezone.utc)
    old = (now - timedelta(days=40)).isoformat()
    recent = (now - timedelta(days=2)).isoformat()

    review = orc.retirement_review([
        {"key": "garments_a", "scope": "garments", "tasks": 40, "last_success_at": recent,
         "lessons": ["yoke depth drives returns"]},
        {"key": "garments_b", "scope": "garments", "tasks": 2, "last_success_at": recent,
         "lessons": ["cropped fits photograph better"]},
        {"key": "dormant", "scope": "wreaths", "tasks": 0, "last_success_at": old,
         "lessons": ["wreath forms need a rigid base"]},
        {"key": "busy", "scope": "stockings", "tasks": 12, "last_success_at": recent,
         "lessons": []},
    ], now=now)

    assert "garments_a" in review["keep"] and "busy" in review["keep"]
    merged = {m["cell"]: m for m in review["merge"]}
    assert "garments_b" in merged
    assert merged["garments_b"]["into"] == "garments_a"
    assert merged["garments_b"]["preserve"] == ["cropped fits photograph better"]

    retired = {r["cell"]: r for r in review["retire"]}
    assert "dormant" in retired
    assert retired["dormant"]["preserve"] == ["wreath forms need a rigid base"]


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
