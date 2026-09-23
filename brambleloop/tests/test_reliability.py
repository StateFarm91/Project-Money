"""The render-reliability standard, tested on its own properties.

The standard was written before the sample was drawn, on purpose. These tests are what
stops it being quietly rewritten afterwards to match whatever the measurement returned.

The properties that matter are not "does it compute a percentage". They are: that one
asset reaching a customer through a gate that did not pass outranks any rate; that a
dimension failing every time it is asked is told apart from one failing sometimes; that a
number is withheld when the sample cannot carry it; and that each of those is judged
against the right denominator.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.publish import model_photography as mp  # noqa: E402
from brambleloop.visual import reliability  # noqa: E402


def _attempt(floors: dict, *, usable: bool = False, cad: float = 0.4) -> dict:
    return {"floors": dict(floors), "usable_as_listing_asset": usable, "spent_cad": cad}


def _gallery(slug: str, *attempts: dict) -> dict:
    return {"slug": slug, "attempts": list(attempts)}


def _won(slug: str, *, cad: float = 0.4) -> dict:
    """A gallery that passed everything on its first attempt."""
    return _gallery(slug, _attempt({"face": "pass", "product_truth": "pass"},
                                   usable=True, cad=cad))


def test_nothing_attempted_is_not_a_measurement():
    """Absence of evidence is the defect family this whole system keeps finding.

    No gallery attempted must not come back as a 0% success rate -- that is a verdict
    computed from nothing, and it reads identically to a pipeline that tried and failed.
    """
    out = reliability.assess([])
    assert out["measured"] is False
    assert "nothing to measure" in out["why"]
    assert "success_rate" not in out


def test_an_asset_marked_usable_with_a_failed_floor_is_unsafe_whatever_the_rate():
    """The one failure that reaches a customer. It outranks a perfect rate."""
    out = reliability.assess([
        _won("a"), _won("b"),
        _gallery("c", _attempt({"face": "pass", "product_truth": "unverifiable"},
                               usable=True)),
    ])
    assert out["verdict"] == "unsafe"
    assert out["correctness_holds"] is False
    assert out["correctness_breaches"][0]["slug"] == "c"
    assert out["correctness_breaches"][0]["floors"] == {"product_truth": "unverifiable"}
    # Every gallery produced a usable asset inside one cheap attempt. The rate is perfect
    # and it does not matter -- that is the whole point of the correctness standard.
    assert out["success_rate"] == 1.0
    assert out["meets_economics"] is True
    assert "blocks launch whatever the rate says" in out["what_to_do"]


def test_a_floor_failing_every_time_it_was_asked_is_systematic_in_a_large_sample():
    """The denominator regression, and the reason this module was rewritten before use.

    `product_truth` is decided by the detail frame, so in a sequence of eleven attempts it
    may be asked three times. Failing all three is an architecture failure -- the generator
    is not being asked for something it can make. Dividing those three failures by all
    eleven attempts reports it as bad luck and sends the next session to retry forever.
    """
    galleries = []
    for slug in ("a", "b", "c", "d"):
        galleries.append(_gallery(
            slug,
            _attempt({"morphology": "pass"}),
            _attempt({"morphology": "pass"}),
        ))
    galleries.append(_gallery(
        "e",
        _attempt({"product_truth": "fail"}),
        _attempt({"product_truth": "fail"}),
        _attempt({"product_truth": "fail"}),
    ))

    out = reliability.assess(galleries)
    assert out["dimensions_asked"] == {"morphology": 8, "product_truth": 3}
    assert out["failed_dimensions"] == {"product_truth": 3}
    assert out["systematic_failures"] == ["product_truth"], (
        "three failures out of three asks is systematic; out of eleven attempts it would "
        "look like a 27% stochastic failure and be retried forever")
    assert out["stochastic_failures"] == []
    assert out["verdict"] == "architecturally blocked"
    assert "retrying cannot fix them" in out["what_to_do"]


def test_a_floor_failing_some_of_the_times_it_was_asked_is_stochastic():
    """The opposite diagnosis, needing the opposite response: retry."""
    out = reliability.assess([
        _gallery("a", _attempt({"face": "fail"}),
                 _attempt({"face": "pass"}, usable=True)),
        _won("b"), _won("c"),
    ])
    assert out["stochastic_failures"] == ["face"]
    assert out["systematic_failures"] == []
    assert out["verdict"] == "production capable"
    assert "retrying fixes the ones that fail" in out["what_to_do"]


def test_a_floor_asked_once_is_not_classified_from_a_single_ask():
    """One ask cannot tell a systematic failure from a stochastic one.

    Calling it systematic would send the next session to rebuild an architecture on a
    sample of one. Calling it stochastic would tell it to retry something that can never
    pass. It is neither, and saying so is the honest answer.
    """
    out = reliability.assess([
        _won("a"), _won("b"),
        _gallery("c", _attempt({"lighting": "fail"}, usable=False)),
    ])
    assert out["unclassified_failures"] == ["lighting"]
    assert out["systematic_failures"] == []
    assert out["stochastic_failures"] == []


def test_a_rate_is_withheld_below_the_sample_floor():
    """A proportion from two samples is not a capability measurement."""
    out = reliability.assess([_won("a"), _won("b")])
    assert out["success_rate"] is None
    assert out["verdict"] == "unproven"
    assert f"floor of {reliability.MIN_GALLERIES_FOR_A_RATE}" in out["rate_withheld_because"]
    # Both galleries passed cheaply on the first attempt. The economics are met and the
    # verdict still refuses to call it capable, because two is not a sample.
    assert out["meets_economics"] is True


def test_a_gallery_that_exhausted_its_attempts_is_unreliable_not_uneconomic():
    """Spending the whole budget without an asset is a failure, not an expense.

    The product behind that gallery cannot be listed. Reporting it as a cost problem
    invites the wrong fix -- raising the budget -- for a gallery no budget would have
    rescued inside its bound.
    """
    out = reliability.assess([
        _won("a"), _won("b"),
        _gallery("c", _attempt({"face": "fail"}), _attempt({"face": "fail"}),
                 _attempt({"face": "fail"})),
    ])
    assert out["exhausted_without_usable"] == ["c"]
    assert out["affordable"] is True, "the two usable galleries cost CA$0.40 each"
    assert out["verdict"] == "unreliable"
    assert out["meets_economics"] is False
    assert "cannot be listed" in out["what_to_do"]


def test_more_attempts_than_the_budget_allows_is_over_budget_even_when_it_wins():
    """A fourth attempt is evidence the method is wrong rather than the sample."""
    over = reliability.MAX_ATTEMPTS_PER_GALLERY + 1
    tries = [_attempt({"face": "fail"}, cad=0.1) for _ in range(over - 1)]
    tries.append(_attempt({"face": "pass"}, usable=True, cad=0.1))
    out = reliability.assess([_won("a"), _won("b"), _gallery("c", *tries)])
    assert out["over_attempt_budget"] == ["c"]
    assert out["galleries_usable"] == 3, "it did produce an asset"
    assert out["verdict"] == "unreliable"


def test_a_pipeline_that_works_and_cannot_be_afforded_is_uneconomic():
    """Distinct from unreliable: every gallery succeeded, at a price we cannot pay."""
    ceiling = reliability.MAX_CAD_PER_USABLE_GALLERY
    out = reliability.assess([_won(s, cad=ceiling + 0.5) for s in ("a", "b", "c")])
    assert out["cad_per_usable_gallery"] == ceiling + 0.5
    assert out["affordable"] is False
    assert out["verdict"] == "uneconomic"
    assert "cheaper rather than the budget larger" in out["what_to_do"]


def test_cost_per_usable_gallery_divides_spend_by_usable_galleries_not_by_attempts():
    """The cost of a listing asset includes the attempts that were thrown away.

    Dividing by attempts would report the price of a render, which is not a number this
    business spends. It spends the price of a gallery it can publish.
    """
    out = reliability.assess([
        _gallery("a", _attempt({"face": "fail"}, cad=0.5),
                 _attempt({"face": "pass"}, usable=True, cad=0.5)),
        _won("b", cad=0.5), _won("c", cad=0.5),
    ])
    assert out["total_spend_cad"] == 2.0
    assert out["cad_per_usable_gallery"] == round(2.0 / 3, 4)
    assert out["verdict"] == "production capable"


def test_the_happy_path_reports_a_rate_and_names_the_standard_it_was_judged_against():
    out = reliability.assess([_won(s) for s in ("a", "b", "c")])
    assert out["verdict"] == "production capable"
    assert out["success_rate"] == 1.0
    assert out["correctness_holds"] is True
    assert out["meets_economics"] is True
    assert out["standard_set_at"] == reliability.STANDARD_SET_AT
    assert out["max_attempts_allowed"] == reliability.MAX_ATTEMPTS_PER_GALLERY
    assert out["ceiling_cad_per_usable_gallery"] == reliability.MAX_CAD_PER_USABLE_GALLERY


def test_a_gallery_with_no_attempts_at_all_is_a_failure_not_a_free_pass():
    """An empty attempt list must not divide into a clean bill of health."""
    out = reliability.assess([_won("a"), _won("b"), _gallery("c")])
    assert out["exhausted_without_usable"] == ["c"]
    assert out["verdict"] == "unreliable"
    assert out["attempts_per_gallery"] == [1, 1, 0]


def test_no_floors_recorded_anywhere_does_not_manufacture_a_systematic_failure():
    """Nothing asked is not everything failed -- the absence-of-evidence defect again."""
    out = reliability.assess([
        _gallery(s, _attempt({}, usable=True)) for s in ("a", "b", "c")])
    assert out["dimensions_asked"] == {}
    assert out["systematic_failures"] == []
    assert out["stochastic_failures"] == []
    assert out["unclassified_failures"] == []
    assert out["correctness_holds"] is True


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _file(db, **detail) -> None:
    """File a sequence record the way the handler does."""
    from brambleloop.agents.registry import Registry

    Registry(db).audit("publishing", mp.ACTION, detail={
        "made": True, "method_version": mp.METHOD_VERSION, **detail})


def test_measure_groups_the_filed_sequences_into_galleries_by_release():
    """Each filed row is one attempt; a gallery is a product at a release.

    A flat count of renders cannot answer "how many attempts did this gallery take",
    which is the unit the whole standard is written in.
    """
    db = _db()
    _file(db, slug="hats-hat-0", version="1.0.0", spent_cad=0.4,
          floors={"face_identity": "pass", "product_truth": "fail"})
    _file(db, slug="hats-hat-0", version="1.0.0", spent_cad=0.4,
          usable_as_listing_asset=True,
          floors={"face_identity": "pass", "product_truth": "pass"})
    _file(db, slug="winter-cardigan", version="1.0.0", spent_cad=0.4,
          usable_as_listing_asset=True,
          floors={"face_identity": "pass", "product_truth": "pass"})

    out = reliability.measure(db)
    assert out["galleries_attempted"] == 2, "three rows, two galleries"
    assert out["galleries_usable"] == 2
    assert sorted(out["attempts_per_gallery"]) == [1, 2]
    assert out["total_spend_cad"] == 1.2
    assert out["cad_per_usable_gallery"] == 0.6
    assert out["stochastic_failures"] == ["product_truth"]
    assert out["method_version"] == mp.METHOD_VERSION


def test_measure_separates_the_same_product_at_two_releases():
    """A re-cut release starts its attempt budget again; sharing one would exhaust it."""
    db = _db()
    for version in ("1.0.0", "1.1.0"):
        for _ in range(2):
            _file(db, slug="hats-hat-0", version=version, spent_cad=0.4,
                  floors={"face_identity": "fail"})
        _file(db, slug="hats-hat-0", version=version, spent_cad=0.4,
              usable_as_listing_asset=True, floors={"face_identity": "pass"})

    out = reliability.measure(db)
    assert out["galleries_attempted"] == 2
    assert out["attempts_per_gallery"] == [3, 3]
    assert out["over_attempt_budget"] == [], "neither release passed its own budget"


def test_measure_counts_only_the_current_method():
    """A rate mixing v8, v10 and v12 measures a history rather than a pipeline."""
    db = _db()
    from brambleloop.agents.registry import Registry

    Registry(db).audit("publishing", mp.ACTION, detail={
        "made": True, "method_version": "v8-superseded", "slug": "old",
        "version": "1.0.0", "spent_cad": 9.0, "floors": {"face_identity": "fail"}})
    _file(db, slug="hats-hat-0", version="1.0.0", spent_cad=0.4,
          usable_as_listing_asset=True, floors={"face_identity": "pass"})

    out = reliability.measure(db)
    assert out["galleries_attempted"] == 1
    assert out["total_spend_cad"] == 0.4, "a superseded method's spend was counted"
    assert out["failed_dimensions"] == {}


def test_measure_on_an_empty_log_measures_nothing_rather_than_reporting_zero():
    out = reliability.measure(_db())
    assert out["measured"] is False
    assert out["method_version"] == mp.METHOD_VERSION


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
