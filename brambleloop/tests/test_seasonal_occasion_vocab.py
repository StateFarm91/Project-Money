"""seasonal.cycle_proof dead-lettered on every run: the calendar's "Valentine's" had no occasion.

Production, 2026-11-19 (release 5496bc4a): eight `ProspectingRefused` dead letters in 24 h.
The arenas come from `radar.market.SEASONAL_EVENTS`, which names the event "Valentine's";
`prospecting.EVENT_OCCASION` knew only "Valentine's Day". The wheel picks the soonest
non-priority arena at cycle 0, which is a Valentine's one while Christmas is under six weeks
away, so `propose` refused it and the job died every time -- no seasonal concept was made.

The fix is the vocabulary entry, not a looser gate: an event the vocabulary cannot express is
still refused (`test_prospecting`), and nothing about Product Truth or the spend limits moved.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _tmp  # noqa: E402

_tmp.install()

from brambleloop.core.models import BenchmarkListing  # noqa: E402
from brambleloop.creative import prospecting as P  # noqa: E402
from brambleloop.intel import benchmarks  # noqa: E402
from brambleloop.seasonal import cycle  # noqa: E402
from test_prospecting import _WideGateway, _db  # noqa: E402

# The production date: Christmas 36 days out, so the wheel's first pick is Valentine's.
TODAY = date(2026, 11, 19)


def _valentines_db():
    db = _db()
    with db.session() as s:
        for pod, title, n in (("ornaments", "Crochet Heart Garland Ornament Pattern", 30),
                              ("home_decor", "Crochet Heart Wall Hanging Pattern", 30)):
            for i in range(n):
                s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY,
                                       listing_ref=f"{pod}{i}", title=title, pod=pod))
    return db


def test_every_calendar_event_has_an_occasion():
    """The guard that would have caught it: arenas carry the calendar's names verbatim."""
    from brambleloop.radar.market import SEASONAL_EVENTS
    from brambleloop.seasonal.calendar import EVENT_DEPARTMENTS

    names = {e.name for e in SEASONAL_EVENTS} | set(EVENT_DEPARTMENTS)
    missing = sorted(n for n in names if n not in P.EVENT_OCCASION)
    assert missing == [], f"calendar events with no concept occasion: {missing}"
    assert P.occasion_for("Valentine's") == "valentines"
    assert P.occasion_for("Valentine's Day") == "valentines"


def test_the_cycle_at_the_production_date_makes_valentines_concepts():
    db = _valentines_db()
    arena = P.choose(P.arenas(db, today=TODAY), cycle=0, today=TODAY)
    assert arena.event == "Valentine's", "fixture no longer exercises the failing arena"
    out = cycle.run(db, today=TODAY, gateway=_WideGateway())  # raised ProspectingRefused
    steps = {s["step"]: s for s in out["steps"]}
    assert steps["choose_event"]["evidence"]["event"] == "Valentine's"
    assert steps["generate"]["state"] == "ran", steps["generate"]
    assert steps["generate"]["evidence"]["proposed"] >= 2
    assert steps["engineer"]["state"] == "ran", steps["engineer"]


def test_an_unknown_event_is_still_refused_not_defaulted():
    """The fix widened the vocabulary by one real event, not the gate."""
    try:
        P.occasion_for("Diwali")
    except P.ProspectingRefused as e:
        assert "everyday" in str(e)
    else:
        raise AssertionError("an event outside the vocabulary was accepted")


def test_a_calendar_refusal_at_choose_is_a_verdict_not_a_dead_letter():
    db = _valentines_db()
    real = P.choose

    def nothing_reachable(found, **_kw):
        raise P.ProspectingRefused("none of 2 proven arena(s) has a form that can still be "
                                   "made in time. That is a statement about the calendar")

    P.choose = nothing_reachable
    try:
        out = cycle.run(db, today=TODAY, gateway=_WideGateway())
    finally:
        P.choose = real
    assert out["complete"] is False
    step = next(s for s in out["steps"] if s["step"] == "choose_event")
    assert step["state"] != "ran" and "calendar" in step["why"], step
    assert out["weakest_link"] == "choose_event", out["weakest_link"]


def test_the_proof_job_files_a_valentines_cycle_instead_of_raising():
    from brambleloop.agents.registry import Registry
    from brambleloop.gateway.anthropic import AnthropicProvider
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.release import JobContext, handle_seasonal_cycle_proof
    from brambleloop.gateway import failover

    db = _valentines_db()
    Registry(db).seed_defaults()
    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("publishing", "seasonal.cycle_proof", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    real_key, real_gw, real_today = (AnthropicProvider.key, failover.job_gateway,
                                     cycle.date)
    AnthropicProvider.key = staticmethod(lambda: "a-key")
    failover.job_gateway = lambda *a, **k: _WideGateway()

    class _D(date):
        @classmethod
        def today(cls):
            return TODAY

    cycle.date = _D
    try:
        out = handle_seasonal_cycle_proof(ctx)  # raised ProspectingRefused in production
    finally:
        AnthropicProvider.key, failover.job_gateway, cycle.date = (real_key, real_gw,
                                                                   real_today)
    assert out["ran"] is True
    assert out["weakest_link"] != "choose_event", out


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
