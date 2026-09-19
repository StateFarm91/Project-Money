"""Scoring a micro-market, and the two ways a score stops meaning anything.

v1.4.3 requirement 2. Nine dimensions, and an explicit instruction to hunt meaningful demand
where the incumbents are weak.

The failures held here are the ones that leave the number looking exactly the same. Filling an
unmeasured dimension with a neutral value keeps the score's shape and loses its meaning, and
nobody can tell by looking. And ranking a market scored on two dimensions against one scored
on eight is arithmetic on different things, presented in the one place everybody reads.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.radar import arbitrage as A  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/arb.sqlite")
    db.create_all()
    return db


def _full(market: str, value: float = 0.6) -> dict:
    return A.score_market(market, values={d.key: value for d in A.DIMENSIONS})


# ---- unmeasured leaves the arithmetic -------------------------------------


def test_an_unmeasured_dimension_is_named_rather_than_defaulted():
    report = A.score_market("christmas ornaments",
                            values={"demand": 0.8, "season_timing": 0.9})

    assert set(report["measured"]) == {"demand", "season_timing"}
    assert "support_burden" in report["unmeasured"]
    row = next(r for r in report["dimensions"] if r["dimension"] == "support_burden")
    assert row["value"] is None
    assert row["needs"]


def test_a_market_nobody_has_measured_has_no_score_not_a_zero():
    report = A.score_market("garments")

    assert report["score"] is None
    assert report["confidence"] == 0.0
    assert "not a score of zero" in report["note"]


def test_the_score_carries_the_share_of_weight_that_was_measured():
    report = A.score_market("ornaments", values={"demand": 1.0})

    assert report["confidence"] == round(
        A.DIMENSION_BY_KEY["demand"].weight / sum(d.weight for d in A.DIMENSIONS), 3)
    assert report["score"] == 1.0, "the score is over the measured weight, not the whole"


def test_a_fully_measured_market_is_confident():
    report = _full("ornaments")
    assert report["confidence"] == 1.0
    assert report["unmeasured"] == []
    assert report["rankable"] is True


def test_a_dimension_outside_its_own_scale_is_refused():
    """A dimension that can exceed its scale silently outweighs the others."""
    try:
        A.score_market("ornaments", values={"demand": 4.0})
    except A.ArbitrageRefused as e:
        assert "outside 0..1" in str(e)
    else:
        raise AssertionError("a dimension was allowed past its own scale")


def test_an_invented_dimension_is_refused():
    try:
        A.score_market("ornaments", values={"vibes": 0.9})
    except A.ArbitrageRefused as e:
        assert "not scoring dimensions" in str(e)
    else:
        raise AssertionError("an invented dimension was scored")


# ---- ranking ---------------------------------------------------------------


def test_a_market_scored_on_too_little_weight_is_withheld_from_the_ranking():
    thin = A.score_market("blankets", values={"season_timing": 0.9})
    report = A.rank([_full("ornaments"), thin])

    assert [r["market"] for r in report["ranked"]] == ["ornaments"]
    assert [w["market"] for w in report["withheld"]] == ["blankets"]


def test_markets_scored_at_different_confidences_are_not_ranked_together():
    """The caveat is read once and the ranking is read every week."""
    wide = _full("ornaments")
    narrower = A.score_market(
        "stockings", values={d.key: 0.7 for d in A.DIMENSIONS[:5]})

    assert narrower["rankable"] is True
    try:
        A.rank([wide, narrower])
    except A.ArbitrageRefused as e:
        assert "arithmetic on different things" in str(e)
    else:
        raise AssertionError("two incomparable scores were ranked against each other")


def test_comparable_confidences_rank_normally():
    a = _full("ornaments", 0.8)
    b = _full("stockings", 0.5)

    report = A.rank([a, b])

    assert [r["market"] for r in report["ranked"]] == ["ornaments", "stockings"]


def test_nothing_rankable_says_so_rather_than_returning_an_empty_list():
    report = A.rank([A.score_market("blankets", values={"season_timing": 0.9})])

    assert report["ranked"] == []
    assert "honest state of a shop with no market evidence" in report["note"]


# ---- the weakness hunt -----------------------------------------------------


def test_with_no_observed_listing_the_hunt_is_unmeasurable_not_empty():
    """An empty list of weaknesses would read as 'none found', which is the opposite of
    what is true."""
    report = A.weakness_hunt(_db())

    assert report["measurable"] is False
    assert report["listings"] == 0
    assert "would read as 'none found'" in report["reason"]
    assert set(report["signals"]) >= {"thin_media", "no_video", "complaints"}


def test_thin_media_is_counted_from_observed_listings():
    db = _db()
    from brambleloop.core.models import BenchmarkListing

    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs", listing_ref="a", pod="home",
                               media_count=2))
        s.add(BenchmarkListing(benchmark_key="mjs", listing_ref="b", pod="home",
                               media_count=9))

    report = A.weakness_hunt(db)

    assert report["measurable"] is True
    assert [r["ref"] for r in report["thin_media"]] == ["a"]
    assert report["thin_media_share"] == 0.5


def test_the_signals_the_requirement_names_are_carried_even_when_unscored():
    """Video, deliverable clarity and complaint themes need fields the observation does not
    carry yet, so they are named rather than quietly dropped."""
    report = A.state(_db())

    assert "no_video" in report["weakness_hunt"]["signals"]
    assert "unclear_deliverable" in report["weakness_hunt"]["signals"]
    assert len(report["dimensions"]) == 9


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
