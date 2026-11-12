"""WS5 E5: learning safety -- separate caps, decay, paid traffic excluded, and the whole chain.

* Internal (jury, defects, research) and buyer (measured commercial) lessons are capped
  separately, each at +-0.06, so one kind cannot use up the other's room.
* A lesson's weight halves every `consume.HALF_LIFE_DAYS`.
* A paid-traffic period never moves a buyer lesson.
* The chain: a real-provenance measured period -> a buyer lesson -> a bounded ranking change
  -> a different next concept. The same row marked synthetic changes nothing.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws5_e5_learning_safety.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.improve import commercial_lessons as CL  # noqa: E402
from brambleloop.improve import consume  # noqa: E402
from brambleloop.radar.opportunity import POOL  # noqa: E402
import test_opus2_commercial_lessons as TCL  # noqa: E402

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _l(subject, direction, days_old=0):
    return {"subject": subject, "direction": direction,
            "at": (NOW - timedelta(days=days_old)).isoformat()}


def test_internal_and_buyer_lessons_have_separate_caps():
    internal = [_l("construction_preference", 1) for _ in range(10)]
    buyer = [_l("commercial_demand", 1) for _ in range(10)]
    parts = consume.adjustment_parts(internal + buyer, now=NOW)
    assert parts == {"internal": 0.06, "buyer": 0.06, "total": 0.12}, parts
    # Internal opinions cannot use up a buyer signal's room, nor cancel it beyond their cap.
    against = [_l("creative_rejection", -1) for _ in range(10)] + [_l("commercial_demand", 1)]
    parts = consume.adjustment_parts(against, now=NOW)
    assert parts["internal"] == -0.06 and parts["buyer"] == 0.02, parts
    assert consume.kind_of({"subject": "commercial_underperformance"}) == "buyer"
    assert consume.kind_of({"subject": "defect"}) == "internal"


def test_a_lessons_weight_decays_with_age():
    fresh = consume.score_adjustment([_l("commercial_demand", 1, 0)], now=NOW)
    half = consume.score_adjustment([_l("commercial_demand", 1, consume.HALF_LIFE_DAYS)],
                                    now=NOW)
    old = consume.score_adjustment([_l("commercial_demand", 1, 365)], now=NOW)
    assert fresh == 0.02 and half == 0.01 and 0 < old < 0.001, (fresh, half, old)
    assert consume.decay({"at": None}) == 1.0 and consume.decay({"at": "garbage"}) == 1.0


def test_paid_traffic_never_moves_a_buyer_lesson():
    db = TCL._db()
    TCL._three_categories(db)
    base = CL.measured_groups(db)["basket"]
    with db.session() as s:
        s.add(TCL.ListingOutcome(product_slug="market-basket-small", version="1.2.0",
                                 period_start="2026-10-01", period_end="2026-10-31",
                                 impressions=50000, visits=5000, favourites=1, orders=500,
                                 source=TCL.EXPORT_SOURCE + "ads",
                                 detail={"provenance": "real", "paid": True}))
    after = CL.measured_groups(db)["basket"]
    assert (after.visits, after.orders) == (base.visits, base.orders)


def _next_concept(db, slugs):
    """The order radar.scan now uses: base score plus the bounded lesson nudge."""
    from brambleloop.radar.opportunity import score_concept

    seeds = [s for s in POOL if s.slug in slugs]
    nudges = consume.rank_adjustments(db, seeds)
    scored = sorted(((round(score_concept(s).score + nudges[s.slug], 4), s.slug)
                     for s in seeds), key=lambda x: (-x[0], x[1]))
    return scored[0][1], nudges


def _pair():
    """A basket concept and a non-basket concept the base score orders the other way, close
    enough that a bounded nudge can reorder them."""
    from brambleloop.radar.opportunity import score_concept

    baskets = [s for s in POOL if s.category == "basket" and s.slug != "market-basket-trio"]
    others = [s for s in POOL if s.category not in ("basket", "baby", "coaster")]
    best = None
    for b in baskets:
        for o in others:
            gap = score_concept(o).score - score_concept(b).score
            if 0 < gap < 0.05 and (best is None or gap < best[0]):
                best = (gap, b.slug, o.slug)
    assert best is not None, "no concept pair within the nudge's reach"
    return best[1], best[2]


def test_the_chain_real_outcome_to_lesson_to_ranking_to_a_different_next_concept():
    basket, other = _pair()
    db = TCL._db()
    first, _ = _next_concept(db, {basket, other})
    assert first == other                            # before: the base order
    TCL._three_categories(db)                        # real-provenance measured periods
    TCL._run(db, "analyst", "improve.commercial_lessons")
    after, nudges = _next_concept(db, {basket, other})
    assert 0 < nudges[basket] <= consume.BUYER_CAP, nudges      # bounded
    assert after == basket, (after, nudges)                      # a different next concept


def test_the_same_chain_with_synthetic_rows_changes_nothing():
    basket, other = _pair()
    db = TCL._db()
    for slug, visits, orders in (("market-basket-small", 400, 20),
                                 ("hexagon-coaster-set", 400, 4),
                                 ("cloudline-baby-blanket", 600, 2)):
        TCL._outcome(db, slug, visits, orders, provenance="synthetic")
    out = TCL._run(db, "analyst", "improve.commercial_lessons")
    assert out["published"] == 0, out
    first, nudges = _next_concept(db, {basket, other})
    assert first == other and nudges[basket] == 0.0, nudges


def test_radar_scan_ranks_with_the_nudge():
    import inspect

    from brambleloop.runtime import pipeline

    src = inspect.getsource(pipeline.handle_radar_scan)
    assert "rank_adjustments" in src and "select_portfolio(steered" in src


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
