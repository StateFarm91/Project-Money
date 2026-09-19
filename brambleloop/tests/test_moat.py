"""Testing as a constrained resource, and a brand that is not just its most visible asset.

v1.4.3 requirements 43, 44, 54. Testing is the only constraint where wanting it faster changes
nothing, which is why it is the one discovered late. And the recurring model is the most
visible brand asset, which feels like the most valuable and is the most copyable.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.brand import moat as M  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.quality import testers as T  # noqa: E402

TODAY = date(2026, 9, 19)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/moat.sqlite")
    db.create_all()
    return db


# ---- tester capacity (#43) ------------------------------------------------


def test_demand_is_forecast_from_the_calendar_rather_than_the_request_queue():
    """A queue tells you what has been asked for; the lead time lives in the difference."""
    demands = [T.Demand("cardigan", "C", "garments", 90.0, date(2026, 12, 1)),
               T.Demand("throw", "B", "blankets", 30.0, date(2026, 11, 1)),
               T.Demand("coaster", "A", "home_decor", 3.0, date(2026, 11, 1))]
    result = T.forecast(demands, today=TODAY)

    # Class A needs no sample and does not appear.
    assert [r["product_slug"] for r in result["demands"]] == ["cardigan", "throw"]
    assert all(r["already_late"] for r in result["demands"])
    assert result["tester_days_required"] > 100
    assert "discovered late" in result["note"]


def test_a_tester_who_has_not_finished_anything_is_not_capacity():
    unproven = T.Tester("new", ("garments",), accepted=0, completed=0)
    flaky = T.Tester("flaky", ("garments",), accepted=5, completed=1)
    solid = T.Tester("solid", ("garments",), accepted=4, completed=4)

    assert unproven.reliable is False
    assert flaky.reliable is False
    assert solid.reliable is True
    # Never having been asked is not unreliability, and the report says which it is.
    assert "too few assignments to say" in unproven.to_dict()["basis"]
    assert flaky.to_dict()["basis"] == "completed against accepted"


def test_one_tester_doing_every_garment_is_a_network_of_one_for_garments():
    demands = [T.Demand("cardigan", "C", "garments", 40.0, date(2026, 12, 1))]
    single = T.capacity([T.Tester("solid", ("garments",), accepted=4, completed=4)],
                        demands, today=TODAY)
    assert single["single_points_of_failure"] == ["garments"]
    assert single["schedulable"] is False
    assert "counts as four" in single["note"]

    paired = T.capacity([T.Tester("a", ("garments",), accepted=4, completed=4),
                         T.Tester("b", ("garments",), accepted=3, completed=3)],
                        demands, today=TODAY)
    assert paired["single_points_of_failure"] == []


def test_an_assignment_outside_a_specialty_is_a_slow_way_to_discover_that():
    tester = T.Tester("solid", ("blankets",), accepted=4, completed=4)
    demand = T.Demand("cardigan", "C", "garments", 40.0, date(2026, 12, 1))
    try:
        T.assign(tester, demand)
    except T.TesterRefused as e:
        assert "slow way to discover that" in str(e)
    else:
        raise AssertionError("a tester was assigned outside their specialty")

    # An unproven tester may take a first job: that is how they stop being unproven.
    first_timer = T.Tester("new", ("garments",))
    assigned = T.assign(first_timer, demand)
    assert "stop being unproven" in assigned["note"]

    unreliable = T.Tester("flaky", ("garments",), accepted=5, completed=1)
    try:
        T.assign(unreliable, demand)
    except T.TesterRefused as e:
        assert "not what they accepted" in str(e)
    else:
        raise AssertionError("an unreliable tester was assigned")


def test_no_recorded_tests_means_unreleasable_rather_than_delayed():
    db = _db()
    result = T.from_db(db)
    assert result["count"] == 0
    assert "unreleasable rather than delayed" in result["note"]


# ---- the brand moat (#44) -------------------------------------------------


def test_the_model_is_the_most_visible_asset_and_the_most_copyable():
    assert M.BY_KEY["canonical_model"].replication == M.DAYS
    inventory = M.inventory()
    assert "canonical_model" not in inventory["structural_advantages"]
    assert "most valuable and is the most copyable" in inventory["note"]


def test_an_asset_nobody_has_built_is_not_counted_as_a_moat():
    """Listing a plan beside the real ones says the company is defensible when it is aspiring."""
    inventory = M.inventory()
    assert set(inventory["built"]).isdisjoint(inventory["planned"])
    assert inventory["planned"], "nothing is planned; this proves little"
    for band, keys in inventory["built_by_replication"].items():
        for key in keys:
            assert M.BY_KEY[key].exists is True, key


def test_a_signature_states_why_it_would_take_that_long_for_somebody_else():
    try:
        M.Signature("x", "a thing", M.STRUCTURAL, "it is hard", exists=True)
    except M.MoatRefused as e:
        assert "how proud we are of it" in str(e)
    else:
        raise AssertionError("a replication band was accepted with no reasoning")


def test_the_brand_survives_losing_the_model():
    """The requirement's whole point is that the answer should not be 'not much'."""
    result = M.without("canonical_model")
    assert result["brand_survives"] is True
    assert "deterministic_validation" in result["remaining_structural"]
    assert "version_aware_support" in result["remaining_structural"]


def test_structural_means_it_cannot_be_bought_later_at_any_speed():
    assert "cannot be bought later at any speed" in M.REPLICATION_MEANING[M.STRUCTURAL]
    version_support = M.BY_KEY["version_aware_support"]
    assert version_support.replication == M.STRUCTURAL
    assert "cannot be backfilled" in version_support.why


# ---- the launch gate additions (#54) --------------------------------------


def test_the_launch_gate_carries_the_v14_additions():
    from brambleloop.launch import readiness

    db = _db()
    assessed = {r.key: r for r in readiness.assess(db, phase="shadow").requirements}
    for key in ("brand_moat", "rollback_plan", "analytics_baseline", "brand_clearance"):
        assert key in assessed, key

    # A baseline taken after the change is the change measured against itself.
    assert assessed["analytics_baseline"].ready is False
    assert "measured against itself" in assessed["analytics_baseline"].evidence["why"]
    # The moat gate passes because two structural advantages already exist.
    assert assessed["brand_moat"].ready is True
    assert assessed["rollback_plan"].ready is True


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
