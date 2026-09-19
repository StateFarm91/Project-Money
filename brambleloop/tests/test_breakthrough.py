"""What the competitor has not made, and why that is not what we have not made.

v1.4.3 requirement 216. Alongside the same-arena response lane, a benchmark release triggers a
divergent tournament across eight axes. Both lanes run.

The sentence the requirement takes for granted is the one worth testing. "What the competitor
has NOT made" is a claim about their catalogue, and making it requires having looked. With
nothing observed, the honest divergence is against our own catalogue -- a weaker and still
useful statement -- and the moment a brief describes that as a market gap, an assumption has
become a plan.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import breakthrough as B  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/breakthrough.sqlite")
    db.create_all()
    return db


def _observed(db, n: int = 3) -> None:
    from brambleloop.core.models import BenchmarkListing

    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key="mjs", listing_ref=f"l{i}", pod="home",
                                   product_type="stocking", title=f"stocking {i}"))


# ---- the claim a divergence is allowed to make ----------------------------


def test_with_nothing_observed_the_divergence_is_against_our_own_catalogue():
    report = B.diverge(_db(), arena="stocking", ours=("stocking",))

    assert report["diverged_from"] == B.AGAINST_OURSELVES
    assert report["observed_listings"] == 0
    assert all(b["claims_market_gap"] is False for b in report["briefs"])
    assert "turn an assumption into a plan" in report["note"]


def test_observed_listings_upgrade_the_claim():
    db = _db()
    _observed(db)

    report = B.diverge(db, arena="stocking", ours=("stocking",))

    assert report["diverged_from"] == B.AGAINST_MARKET
    assert all(b["claims_market_gap"] is True for b in report["briefs"])
    assert "actually been seen" in report["note"]


def test_a_brief_claiming_a_market_gap_without_a_market_is_refused():
    """The thing nobody has made and the thing we happen not to have made are different
    discoveries, and only one of them is an opportunity."""
    report = B.diverge(_db(), arena="stocking")
    for claim in ("nobody makes this", "an unserved market gap", "no one sells it"):
        try:
            B.check_claim(report["briefs"][0], claim=claim)
        except B.BreakthroughRefused as e:
            assert "different discoveries" in str(e)
        else:
            raise AssertionError(f"{claim!r} was accepted without an observed market")


def test_the_same_claim_is_allowed_once_the_market_has_been_observed():
    db = _db()
    _observed(db)
    report = B.diverge(db, arena="stocking")

    B.check_claim(report["briefs"][0], claim="nobody makes this in the observed set")


def test_an_ordinary_brief_is_not_policed_for_language():
    report = B.diverge(_db(), arena="stocking")
    B.check_claim(report["briefs"][0], claim="worth exploring for the host recipient")


# ---- the axes --------------------------------------------------------------


def test_every_axis_the_requirement_names_produces_a_brief():
    report = B.diverge(_db(), arena="stocking")

    assert {b["axis"] for b in report["briefs"]} == set(B.AXES)
    assert all(b["question"].startswith("in stocking:") for b in report["briefs"])


def test_the_vocabulary_excludes_what_is_already_covered():
    report = B.diverge(_db(), arena="stocking", ours=("stocking", "coaster"),
                       their_forms=("ornament",))
    by_axis = {b["axis"]: b for b in report["briefs"]}

    adjacent = by_axis["adjacent_function"]["vocabulary"]
    assert "stocking" not in adjacent
    assert "coaster" not in adjacent
    assert "ornament" not in adjacent
    assert "basket" in adjacent


def test_the_seasonal_axis_offers_occasions_not_already_worked():
    report = B.diverge(_db(), arena="stocking", ours=("christmas",))
    seasonal = next(b for b in report["briefs"] if b["axis"] == "seasonal_story")

    assert "christmas" not in seasonal["vocabulary"]
    assert "halloween" in seasonal["vocabulary"]


# ---- both lanes run --------------------------------------------------------


def test_a_portfolio_that_is_secretly_one_lane_is_refused():
    """Incremental work has a visible customer and breakthrough work has an argument, so the
    argument loses every planning round unless something stops it."""
    try:
        B.allocate(incremental=0.95, breakthrough=0.05)
    except B.BreakthroughRefused as e:
        assert "commodity the moment somebody else arrives" in str(e)
    else:
        raise AssertionError("a single-lane portfolio was accepted")


def test_an_all_breakthrough_portfolio_is_refused_too():
    try:
        B.allocate(incremental=0.05, breakthrough=0.95)
    except B.BreakthroughRefused as e:
        assert "studio with no revenue" in str(e)
    else:
        raise AssertionError("a shop with no incremental work was accepted")


def test_the_lanes_must_be_the_whole_portfolio():
    try:
        B.allocate(incremental=0.4, breakthrough=0.4)
    except B.BreakthroughRefused as e:
        assert "must sum to one" in str(e)
    else:
        raise AssertionError("a portfolio that does not add up was accepted")


def test_a_balanced_allocation_passes():
    result = B.allocate(incremental=0.7, breakthrough=0.3)
    assert result["floor"] == B.MIN_LANE_SHARE


def test_the_state_says_what_this_company_may_currently_claim():
    report = B.state(_db())

    assert report["can_claim_market_gaps"] is False
    assert len(report["axes"]) == 8
    assert "has not happened" in report["note"]


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
