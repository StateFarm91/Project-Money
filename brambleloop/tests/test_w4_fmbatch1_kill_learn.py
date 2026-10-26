"""B2 #23: the scale/kill table learns its funnel thresholds from this shop's own listing
outcomes; defect ceilings are never loosened; too little data keeps the defaults."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.commerce import kill_table as K  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import ListingOutcome  # noqa: E402
from brambleloop.scale import runrate  # noqa: E402


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _listing(db, slug, impressions, visits, orders):
    with db.session() as s:
        s.add(ListingOutcome(product_slug=slug, period_start="2026-10-01",
                             period_end="2026-10-31", impressions=impressions, visits=visits,
                             orders=orders, source="test"))


def test_too_little_data_keeps_every_default_unlearned():
    db = _db()
    floor = int(K.THRESHOLDS["min_visits_to_judge"].value)
    for i in range(K.MIN_LISTINGS_TO_LEARN - 1):
        _listing(db, f"p{i}", 10 * floor, floor, 2)
    _listing(db, "thin", 1000, floor - 1, 0)               # below the visit floor
    out = K.learn(db)
    assert out["learned"] == []
    assert all(t.status == K.UNLEARNED for t in out["thresholds"].values())
    assert out["baselines"]["listings_with_fair_sample"] == K.MIN_LISTINGS_TO_LEARN - 1


def test_enough_listings_learn_ctr_and_conversion_from_the_median():
    db = _db()
    floor = int(K.THRESHOLDS["min_visits_to_judge"].value)
    v = floor * 2
    for i, (ctr, conv) in enumerate([(0.01, 0.01), (0.02, 0.02), (0.03, 0.03),
                                     (0.04, 0.04), (0.05, 0.05)]):
        _listing(db, f"p{i}", int(v / ctr), v, int(round(v * conv)))
    out = K.learn(db)
    t = out["thresholds"]
    assert set(out["learned"]) == {"ctr_strong_at", "ctr_weak_below",
                                   "conversion_strong_at", "conversion_weak_below"}
    assert abs(t["ctr_strong_at"].value - 0.03) < 1e-3
    assert abs(t["ctr_weak_below"].value - 0.015) < 1e-3
    assert t["ctr_strong_at"].status == K.LEARNED and "median CTR of 5" in t["ctr_strong_at"].source
    # Defect ceilings are policy: identical to the defaults, never loosened.
    for k in ("support_high_above", "refund_high_above", "min_visits_to_judge"):
        assert t[k] == K.THRESHOLDS[k]
    # Routing reads the learned table: a 2% CTR listing is above the learned weak line.
    obs = runrate.Observed(impressions=100 * floor, visits=2 * floor, orders=0)
    routed = K.route(obs, thresholds=t)
    assert routed["thresholds"]["ctr_weak_below"]["status"] == K.LEARNED
    assert "LEARNED" in routed["note"]


def test_unknown_orders_do_not_learn_conversion():
    db = _db()
    floor = int(K.THRESHOLDS["min_visits_to_judge"].value)
    for i in range(K.MIN_LISTINGS_TO_LEARN):
        _listing(db, f"p{i}", 10 * floor, floor, None)
    out = K.learn(db)
    assert "ctr_strong_at" in out["learned"] and "conversion_strong_at" not in out["learned"]
    assert out["baselines"]["conversion_median"] == K.UNMEASURED
    assert out["baselines"]["paid_cac_cad"] == K.UNMEASURED


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
