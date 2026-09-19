"""Whether a concept seeds a family, and whether the buyer still has time to make it.

v1.4.3 requirements 111 and 112. Both are checks that get skipped because the concept in
front of you is good: the family test because the hero is strong, and the window test because
the design work feels productive right up until the buyer cannot finish it.

The failures held here are the two ways each check stops working. A family test that counts
roles rather than proving them invents members, which is the derivative-forcing it exists to
prevent arrived at from the other side. And a window test graded on a point estimate calls a
season impossible on the strength of an assumed number, which is the correction the owner
made after exactly that happened.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.creative import family  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402
from brambleloop.creative.jury import Context, judge  # noqa: E402

TODAY = date(2026, 9, 19)


def _concept(**over) -> Concept:
    base = dict(
        key="nordic-throw", title="Nordic Forest Mosaic Throw",
        premise="a pine forest silhouette marching across a deep cream field",
        pod="home", form="rectangle_throw", construction="mosaic_overlay",
        motif="pine forest", palette_story="cream and spruce", recipient="host",
        occasion="christmas", feeling="nostalgic", function="warms a sofa",
        make_lane="LONG")
    base.update(over)
    return Concept(**base)


# ---- #111: does the idea actually seed a family? --------------------------


def test_a_family_member_is_never_the_hero_in_another_palette():
    """A recolour is the canonical fake family member, so the hero's own form cannot fill a
    role in its own family."""
    hero = _concept(form="pillow", construction="granny_square", make_lane="SHORT")

    report = family.family_test(hero)

    for role in report["viable_roles"]:
        assert all(f["form"] != hero.form for f in role["forms"]), role


def test_a_motif_that_cannot_shrink_does_not_get_a_quick_companion():
    """A mosaic throw does not become a coaster; it becomes four stitches of a motif nobody
    can see, which is the forced derivative #111 names."""
    report = family.family_test(_concept())

    blocked = {b["role"]: b for b in report["blocked_roles"]}
    assert "quick_companion" in blocked
    assert any("below the size its motif reads at" in r
               for r in blocked["quick_companion"]["would_force_a_derivative"])
    assert report["verdict"] == "no_entry_price"
    assert report["seeds_a_family"] is False


def test_a_family_without_an_entry_price_is_named_as_such_not_called_a_family():
    report = family.family_test(_concept())
    assert len(report["viable_roles"]) >= family.MIN_VIABLE_ROLES
    assert report["verdict"] == "no_entry_price"
    assert "entered at the cheap end" in report["note"]


def test_size_compatibility_alone_does_not_invent_a_member():
    """An amigurumi robin and a scarf are both small objects, and no amount of shaping turns
    one into the other. Without the construction check the family test invents members."""
    robin = _concept(key="robin", form="toy", construction="amigurumi_shaping",
                     make_lane="QUICK", premise="a round robin with a bright orange breast")

    report = family.family_test(robin)

    blocked = {b["role"]: b["would_force_a_derivative"] for b in report["blocked_roles"]}
    assert "wearable" in blocked
    assert any("is not built by amigurumi_shaping" in r for r in blocked["wearable"])


def test_an_idea_that_carries_into_three_roles_with_an_entry_price_seeds_a_family():
    robin = _concept(key="robin", form="toy", construction="amigurumi_shaping",
                     make_lane="QUICK", premise="a round robin with a bright orange breast")

    report = family.family_test(robin)

    assert report["seeds_a_family"] is True
    assert report["verdict"] == "seeds_a_family"
    assert any(r["role"] == "quick_companion" for r in report["viable_roles"])
    assert report["bundle_possible"] is True


def test_a_single_product_is_reported_not_refused():
    """A brilliant single product is a legitimate thing to build. It is a bad thing to
    discover after engineering three derivatives out of it."""
    garment = _concept(key="yoke-sweater", form="fitted_garment",
                       construction="top_down_yoke", make_lane="FLAGSHIP",
                       premise="a colourwork yoke of winter branches meeting at the shoulder")

    report = family.family_test(garment)

    assert report["seeds_a_family"] is False
    assert report["verdict"] == "single_product"
    assert "legitimate thing to build" in report["note"]


def test_a_bundle_is_derived_from_members_rather_than_asserted():
    lonely = _concept(key="yoke-sweater", form="fitted_garment",
                      construction="top_down_yoke", make_lane="FLAGSHIP",
                      premise="a colourwork yoke of winter branches meeting at the shoulder")
    report = family.family_test(lonely)
    assert report["bundle_possible"] is (len(report["viable_roles"]) >= 2)


# ---- #112: can the buyer still finish it? ---------------------------------


def test_a_quick_make_is_comfortable_where_a_flagship_is_not():
    quick = _concept(key="ornament", form="ornament", construction="amigurumi_shaping",
                     make_lane="QUICK", premise="a small robin with a bright orange breast")

    near = family.window_fit(quick, days_to_event=60, today=TODAY)
    heavy = family.window_fit(_concept(make_lane="FLAGSHIP"), days_to_event=60, today=TODAY)

    assert near["verdict"] == "comfortable"
    assert near["score_multiplier"] == 1.0
    assert heavy["score_multiplier"] < near["score_multiplier"]


def test_an_uncalibrated_estimate_says_so_rather_than_reading_as_precise():
    fit = family.window_fit(_concept(), days_to_event=200, today=TODAY)
    assert fit["calibrated"] is False
    assert "no maker has been timed" in fit["note"]


def test_insufficient_runway_is_not_impossibility():
    """The owner's correction: impossible means the optimistic bound has passed, and
    everything short of that is an instruction to hurry rather than to stop."""
    verdicts = {}
    for days in (400, 200, 120, 95, 70, 30):
        verdicts[days] = family.window_fit(_concept(make_lane="LONG"), days_to_event=days,
                                           today=TODAY)["verdict"]

    assert verdicts[400] == "comfortable"
    assert "high_risk" in verdicts.values(), verdicts
    # High risk carries a real multiplier rather than a zero: the department is told to
    # hurry, and a zero would tell it to stop.
    assert 0 < family.WINDOW_MULTIPLIER["high_risk"] < family.WINDOW_MULTIPLIER["tight"]
    assert family.WINDOW_MULTIPLIER["infeasible"] == 0.0


def test_late_window_capacity_is_pointed_at_what_can_still_be_finished():
    heavy = _concept(key="throw", make_lane="FLAGSHIP")
    quick = _concept(key="ornament", form="ornament", construction="amigurumi_shaping",
                     make_lane="QUICK", premise="a small robin with a bright orange breast")

    plan = family.shift_capacity([heavy, quick], days_to_event=60, today=TODAY)

    assert [c["concept"] for c in plan["continue"]] == ["ornament"]
    assert [c["concept"] for c in plan["stand_down"]] == ["throw"]
    assert plan["new_work_should_be_no_heavier_than"] == "SHORT"
    assert "SHORT makes or faster" in plan["note"]


def test_a_window_with_no_lane_left_says_start_next_season_rather_than_nothing():
    """The grading covers our launch runway as well as the buyer's make time -- a listing
    nobody can find in time is as useless as a blanket nobody can finish -- so close to an
    event every lane closes, and the useful instruction is about the next season."""
    quick = _concept(key="ornament", form="ornament", construction="amigurumi_shaping",
                     make_lane="QUICK", premise="a small robin with a bright orange breast")

    plan = family.shift_capacity([quick], days_to_event=30, today=TODAY)

    assert plan["new_work_should_be_no_heavier_than"] is None
    assert plan["continue"] == []
    assert "next season" in plan["note"]


def test_a_window_that_has_closed_is_refused_rather_than_graded():
    try:
        family.window_fit(_concept(), days_to_event=-3, today=TODAY)
    except family.FamilyRefused as e:
        assert "has closed" in str(e)
    else:
        raise AssertionError("a fit was graded against a date that has passed")


# ---- the wiring: creative scoring actually reads the window (#112) --------


def test_the_jury_judges_nothing_when_nobody_said_how_long_is_left():
    """An unknown window is not a comfortable one, and inferring a date here would fire the
    critic on every everyday product."""
    verdict = judge(_concept(), Context())
    assert all(f.critic != "shopping_window" for f in verdict.findings)


def test_the_jury_rejects_a_concept_the_buyer_cannot_finish_in_time():
    verdict = judge(_concept(make_lane="FLAGSHIP"), Context(days_to_event=30))
    assert any(f.critic == "shopping_window" for f in verdict.findings)
    assert verdict.decision == "rejected"


def test_the_jury_does_not_reject_a_concept_that_is_merely_tight():
    verdict = judge(_concept(make_lane="LONG"), Context(days_to_event=400))
    assert all(f.critic != "shopping_window" for f in verdict.findings)


def test_the_autopsy_can_name_a_window_death():
    from brambleloop.creative import tournament

    result = tournament.Result(opportunity="christmas", at="2026-09-19T00:00:00Z",
                               field_size=1, spread=0.0, duplicate_pairs=[])
    result.rejected.append(judge(_concept(make_lane="FLAGSHIP"), Context(days_to_event=30)))

    report = tournament.autopsy(result)

    assert report["dominant_cause"] == "shopping_window"
    assert "late-window capacity" in report["diagnosis"]


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
