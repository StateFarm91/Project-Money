"""OPUS2-P0: measured listing performance into the next product decision.

Every outcome row here is a TEST FIXTURE written with the export-intake source prefix; no
customer, order or visit is real.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_commercial_lessons.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.commerce.listing_outcomes import EXPORT_SOURCE  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Lesson, ListingOutcome  # noqa: E402
from brambleloop.improve import bus, consume  # noqa: E402
from brambleloop.improve import commercial_lessons as CL  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.radar.opportunity import POOL, score_concept  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

TODAY = date(2026, 10, 20)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='opus2_cl_')}/c.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _outcome(db, slug, visits, orders, *, source=EXPORT_SOURCE + "fixture-1",
             start="2026-09-01", end="2026-09-30", favourites=10):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, version="1.2.0", period_start=start,
                             period_end=end, impressions=visits * 10, visits=visits,
                             favourites=favourites, orders=orders, source=source))


def _three_categories(db, basket_visits=400):
    _outcome(db, "market-basket-small", basket_visits, 20)     # basket: 5%
    _outcome(db, "hexagon-coaster-set", 400, 4)                # coaster: 1%
    _outcome(db, "cloudline-baby-blanket", 600, 2)             # baby: 0.33%


def _run(db, agent, job_type, inputs=None):
    q = JobQueue(db)
    job = q.enqueue(agent, job_type, inputs or {}, idempotency_key=f"t:{os.urandom(4).hex()}")
    return handlers.get(job_type)(JobContext(job=job, db=db, queue=q, registry=Registry(db),
                                             phase=None))


def _concept_text(slug):
    seed = next(s for s in POOL if s.slug == slug)
    return " ".join(str(x) for x in (seed.slug.replace("-", " "), seed.title, seed.category,
                                     seed.season or "", seed.rationale))


def _lessons(db):
    with db.session() as s:
        return [(r.id, r.subject, r.withdrawn_at is not None, list(r.routed_to))
                for r in s.scalars(select(Lesson).order_by(Lesson.id))]


def test_the_job_is_wired_daily_permitted_and_routed():
    assert ("commercial_lessons", "analyst", "improve.commercial_lessons", 86400) in CADENCES
    assert handlers.get("improve.commercial_lessons") is not None
    Registry(_db()).authorize("analyst", "improve.commercial_lessons")
    for subject in CL.SUBJECTS:
        assert "market_radar" in bus.route_for(subject)
    assert CL.DEMAND in consume.FAVOURS and CL.UNDERPERFORMANCE in consume.DISFAVOURS


def test_nothing_measured_publishes_nothing_and_is_no_work():
    db = _db()
    out = _run(db, "analyst", "improve.commercial_lessons")
    assert out["measurable"] is False and out["published"] == 0
    assert pipeline.did_no_work(out, "improve.commercial_lessons")
    _outcome(db, "market-basket-small", 900, 30)               # one category is not a shop
    out = _run(db, "analyst", "improve.commercial_lessons")
    assert out["measurable"] is False and "needs two" in out["why"] and _lessons(db) == []


def test_rows_the_intake_did_not_write_or_without_orders_measure_nothing():
    db = _db()
    _outcome(db, "market-basket-small", 900, 30, source="hand-inserted")
    _outcome(db, "hexagon-coaster-set", 900, None)
    v = CL.verdicts(db)
    assert v["categories"].get("basket") is None
    assert v["categories"].get("coaster") is None and v["measurable"] is False


def test_demand_and_underperformance_verdicts_from_measured_rates():
    db = _db()
    _three_categories(db)
    v = CL.verdicts(db)
    assert v["measurable"] and v["shop"]["orders"] == 26 and v["shop"]["visits"] == 1400
    cats = v["categories"]
    assert cats["basket"]["verdict"] == CL.DEMAND
    assert cats["coaster"]["verdict"] is None
    assert cats["baby"]["verdict"] == CL.UNDERPERFORMANCE
    # Follow-ons are uncertified pool concepts of that category or family, never the product
    # that sold (market-basket-small is the radar's market-basket-trio).
    assert "nordic-forest-basket" in cats["basket"]["follow_ons"]
    assert "market-basket-trio" not in cats["basket"]["follow_ons"]
    assert "cloudline-baby-hat" in cats["baby"]["follow_ons"]


def test_the_lessons_reach_market_radar_and_tie_to_the_concepts_they_name():
    db = _db()
    _three_categories(db)
    out = _run(db, "analyst", "improve.commercial_lessons")
    assert out["published"] == 2 and out["work_done"] == 2
    assert not pipeline.did_no_work(out, "improve.commercial_lessons")
    up = consume.matching(db, "market_radar", _concept_text("nordic-forest-basket"))
    assert any(l["subject"] == CL.DEMAND and l["direction"] == 1 for l in up), up
    down = consume.matching(db, "market_radar", _concept_text("cloudline-baby-hat"))
    assert any(l["subject"] == CL.UNDERPERFORMANCE and l["direction"] == -1 for l in down)
    # A concept in a category nobody measured is not touched.
    other = consume.matching(db, "market_radar", _concept_text("chunky-ribbed-scarf"))
    assert not [l for l in other if l["subject"] in CL.SUBJECTS]


def test_radar_score_moves_the_named_concept_by_the_bounded_nudge_only():
    seed = next(s for s in POOL if s.slug == "nordic-forest-basket")
    payload = score_concept(seed, TODAY).to_dict() | {"as_of": TODAY.isoformat()}
    before = _run(_db(), "market_radar", "radar.score", dict(payload))
    db = _db()
    _three_categories(db)
    _run(db, "analyst", "improve.commercial_lessons")
    after = _run(db, "market_radar", "radar.score", dict(payload))
    assert after["lesson_adjustment"] > before["lesson_adjustment"]
    assert after["lesson_adjustment"] <= 0.06                 # the bus's own cap
    # The gate still decides: a nudge never makes a new concept engineerable by itself.
    assert (after["gate"] or {}).get("decision") != "passed" or after["promoted"]


def test_publishing_is_idempotent_and_new_evidence_supersedes_the_old_lesson():
    db = _db()
    _three_categories(db)
    _run(db, "analyst", "improve.commercial_lessons")
    first = _lessons(db)
    again = _run(db, "analyst", "improve.commercial_lessons")
    assert _lessons(db) == first and again["withdrawn"] == 0
    _outcome(db, "market-basket-small", 300, 15, start="2026-10-01", end="2026-10-31")
    out = _run(db, "analyst", "improve.commercial_lessons")
    rows = _lessons(db)
    assert out["withdrawn"] >= 1
    old_demand = [r for r in rows if r[0] in {x[0] for x in first} and r[1] == CL.DEMAND]
    assert old_demand and all(r[2] for r in old_demand)        # withdrawn
    live = [r for r in rows if not r[2] and r[1] == CL.DEMAND]
    assert len(live) == 1 and live[0][0] not in {x[0] for x in first}
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(ListingOutcome)) == 4


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
