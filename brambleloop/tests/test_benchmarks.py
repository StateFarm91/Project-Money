"""#14: one funnel at a time, and a thin cell that refuses to answer.

The requirement names the dangerous case itself -- do not compare a CA$6 ornament and a
CA$15 blanket as if they share the same funnel -- and it is dangerous because both numbers
are real. The refusal is returned rather than written in a docstring, because the failure is
somebody putting two correct numbers side by side.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import benchmarks as B  # noqa: E402

ORNAMENT = B.Cell("ornaments", "etsy_search", "under_6", "new")
BLANKET = B.Cell("blankets", "etsy_search", "10_to_20", "new")


def _rows(cell, n=3, **over):
    base = dict(impressions=400, clicks=20, favourites=3, orders=1, contribution_cad=6.0)
    base.update(over)
    return [B.Observation(f"L{i}", cell, **base) for i in range(n)]


# --- the comparison the requirement names ---------------------------------------------------

def test_an_ornament_and_a_blanket_are_not_the_same_funnel():
    out = B.compare(ORNAMENT, BLANKET)
    assert out["comparable"] is False
    assert out["differs_on"] == ["category", "price_band"]
    assert "neither is about the other" in out["why"]


def test_the_same_cell_measured_twice_is_comparable():
    assert B.compare(ORNAMENT, ORNAMENT)["comparable"] is True


def test_one_axis_is_enough_to_make_two_funnels_different():
    """A pin and a search phrase are different distances from a decision."""
    pinned = B.Cell("ornaments", "pinterest", "under_6", "new")
    assert B.compare(ORNAMENT, pinned)["differs_on"] == ["traffic_source"]


def test_a_shop_wide_number_may_not_be_used_as_a_baseline():
    out = B.overall(_rows(ORNAMENT) + _rows(BLANKET))
    assert out["comparable_to_a_cell"] is False
    assert "sits between two truths" in out["why"]


# --- a thin cell answers, which is worse than an empty one ----------------------------------

def test_a_cell_below_the_listing_floor_produces_no_number_at_all():
    out = B.baseline(_rows(ORNAMENT, n=2), ORNAMENT)
    assert out["readable"] is False
    assert any("shape of a baseline and none of its content" in r for r in out["reasons"])
    assert all(m["value"] is None for m in out["metrics"].values())


def test_a_cell_below_the_impression_floor_is_refused_too():
    out = B.baseline(_rows(ORNAMENT, n=3, impressions=50), ORNAMENT)
    assert out["readable"] is False
    assert any("impressions against a floor" in r for r in out["reasons"])


def test_a_readable_cell_reports_the_median_rather_than_the_mean():
    """One listing a pin sent thirty thousand impressions moves a mean and does not move
    what an ordinary listing in this cell does."""
    rows = _rows(ORNAMENT, n=3)
    rows.append(B.Observation("viral", ORNAMENT, impressions=30000, clicks=30000,
                              favourites=1, orders=0, contribution_cad=0.0))
    out = B.baseline(rows, ORNAMENT)
    assert out["readable"] is True
    ctr = out["metrics"]["impressions_to_click"]
    assert ctr["basis"].startswith("median")
    assert ctr["value"] < 1.0


# --- absent is not zero -----------------------------------------------------------------------

def test_a_refund_rate_of_zero_on_no_orders_is_not_good_performance():
    out = B.baseline(_rows(ORNAMENT, n=3, orders=None), ORNAMENT)
    refunds = out["metrics"]["refund_or_support_rate"]
    assert refunds["value"] is None
    assert "Absent is not" in refunds["why"] or "is a rumour" in refunds["why"]


def test_a_refund_rate_from_three_orders_is_a_rumour():
    out = B.baseline(_rows(ORNAMENT, n=3, orders=1, refunds_and_support=0), ORNAMENT)
    why = out["metrics"]["refund_or_support_rate"]["why"]
    assert "is a rumour" in why
    assert str(B.MIN_ORDERS_FOR_REFUND_RATE) in why


def test_an_empty_shop_has_no_baseline_anywhere_and_says_which_that_is():
    out = B.cells([])
    assert out["occupied"] == 0
    assert "different from a baseline of zero" in out["note"]


def test_occupied_cells_are_counted_apart_from_readable_ones():
    out = B.cells(_rows(ORNAMENT, n=3) + _rows(BLANKET, n=1))
    assert out["occupied"] == 2
    assert out["readable"] == 1


# --- the axes --------------------------------------------------------------------------------

def test_a_cell_keyed_on_a_typo_is_refused_rather_than_silently_empty():
    for bad in (("ornament", "etsy_search", "under_6", "new"),
                ("ornaments", "google", "under_6", "new"),
                ("ornaments", "etsy_search", "cheap", "new"),
                ("ornaments", "etsy_search", "under_6", "mature")):
        try:
            B.Cell(*bad)
        except B.BenchmarkRefused as exc:
            assert "fails by looking empty" in str(exc), bad
        else:  # pragma: no cover
            raise AssertionError(f"{bad} was accepted as a cell")


def test_price_bands_split_inside_the_observed_cluster():
    """Patterns cluster at CA$4-12, so the boundary that matters falls inside the cluster
    rather than at a round CA$10."""
    assert B.band_for(5.99) == "under_6"
    assert B.band_for(6.0) == "6_to_10"
    assert B.band_for(9.99) == "6_to_10"
    assert B.band_for(10.0) == "10_to_20"
    assert B.band_for(1000.0) == "over_20"


def test_maturity_is_two_counts_rather_than_a_judgement():
    assert B.maturity_for(days_live=10, orders=0) == "new"
    assert B.maturity_for(days_live=10, orders=30) == "establishing"
    assert B.maturity_for(days_live=400, orders=300) == "established"
    # a shop with the orders but not the age is still establishing: both, or neither
    assert B.maturity_for(days_live=30, orders=300) == "establishing"


def test_every_metric_states_what_it_needs_before_it_means_anything():
    for name, spec in B.METRICS.items():
        assert spec["needs"], name
        assert isinstance(spec["higher_is_better"], bool), name
        assert spec["why"], name
    assert B.METRICS["refund_or_support_rate"]["higher_is_better"] is False


def test_state_reports_the_axes_and_the_floors():
    out = B.state()
    assert set(out["axes"]) == {"category", "traffic_source", "price_band", "maturity"}
    assert out["floors"]["listings_per_cell"] == B.MIN_LISTINGS_PER_CELL
    assert "refused by name" in out["note"]


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
