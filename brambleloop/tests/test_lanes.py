"""#5: two production queues, one gate list, and a floor under each purpose.

The three things worth testing here are the three things that go wrong in real companies.
A flagship-shaped product gets shoved down the fast lane against a deadline. The fast lane
quietly eats the flagship lane, one defensible week at a time. And "both retain all
applicable quality gates" stays true in the README while stopping being true in the code.

The last of those is tested by signature rather than by example, because an example only
ever proves the case somebody thought of.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import lanes as L  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, PatternVersion, Product  # noqa: E402
from brambleloop.gates.certificate import CANONICAL_STAGES  # noqa: E402
from brambleloop.seasonal import fastlane as F  # noqa: E402

STABLE = L.qa_stable(L.QaEvidence(regression_fixtures=9, regression_passed=True,
                                  certified_releases=4, open_halting_incidents=0))


def _ornament(**over):
    base = dict(slug="snow-ornament", pod="ornaments", make_lane="QUICK", risk_class="A",
                components=1, colours=3, closed_form=True, has_listing=True)
    base.update(over)
    return L.Profile(**base)


def _throw(**over):
    base = dict(slug="heirloom-throw", pod="blankets", make_lane="LONG", risk_class="A",
                components=1, colours=4)
    base.update(over)
    return L.Profile(**base)


# --- routing ---------------------------------------------------------------------------

def test_the_requirements_own_examples_reach_the_lane_it_names():
    """Ornaments, dishcloths and a selected hat fast; blankets, ebooks and a graded
    cardigan flagship. If the requirement's own list does not route, nothing else matters."""
    fast = [_ornament(),
            L.Profile("waffle-dishcloth", "kitchen_bath", "QUICK", "A"),
            L.Profile("ribbed-beanie", "hats", "SHORT", "B", sizes=2),
            L.Profile("gift-tag-set", "seasonal_gift", "QUICK", "A")]
    flagship = [_throw(),
                L.Profile("winter-ebook", "collections", "SHORT", "A", pattern_count=5),
                L.Profile("cabled-cardigan", "garments", "FLAGSHIP", "C", components=4,
                          sizes=5)]
    for p in fast:
        assert L.assign(p, qa=STABLE)["lane"] == L.FAST, p.slug
    for p in flagship:
        assert L.assign(p, qa=STABLE)["lane"] == L.FLAGSHIP, p.slug


def test_a_garment_cannot_be_argued_into_the_fast_lane():
    """The deadline failure. Somebody types one component and a SHORT make lane onto a
    cardigan; the pod refuses it anyway, because what a thing is does not change when the
    calendar gets tight."""
    card = L.assign(L.Profile("deadline-cardigan", "garments", "SHORT", "A", components=1,
                              colours=1), qa=STABLE)
    assert card["lane"] != L.FAST
    assert any("not a fast-lane pod" in r for r in card["fast_refusals"])


def test_the_two_lanes_cannot_both_admit_the_same_product():
    """Not a style point: if both could admit, the routing would silently prefer whichever
    branch is written first, and the preference would be an accident."""
    cases = [_ornament(), _throw(),
             L.Profile("advent-calendar", "seasonal_gift", "LONG", "B", components=24),
             L.Profile("winter-ebook", "collections", "SHORT", "A", pattern_count=5),
             L.Profile("mosaic-rug", "home_decor", "MEDIUM", "B", colours=6)]
    for p in cases:
        card = L.assign(p, qa=STABLE)
        both = not card["fast_refusals"] and not card["flagship_refusals"]
        assert not both, p.slug


def test_flagship_is_never_merely_not_fast():
    """A product that missed the fast bar for being awkward has not earned authority. This
    is the shape of the defect this build keeps finding, in a commercial costume: a verdict
    reached by the absence of the other verdict."""
    awkward = L.Profile("six-colour-rug", "home_decor", "MEDIUM", "B", colours=6)
    card = L.assign(awkward, qa=STABLE)
    assert card["fast_refusals"]
    assert card["lane"] is None
    assert "not simple enough" in card["note"] and "not substantial enough" in card["note"]


def test_a_premium_garment_in_one_size_is_not_flagship():
    """Depth where depth is countable. A premium claim made over one body is a claim about
    somebody else's."""
    card = L.assign(L.Profile("one-size-cardigan", "garments", "MEDIUM", "C", components=4,
                              sizes=1), qa=STABLE)
    assert card["lane"] is None
    assert any("range of bodies" in r for r in card["flagship_refusals"])


def test_a_class_b_fast_product_says_the_sample_sets_its_date():
    """Class B is admitted because the requirement names it, and a B needs a physical
    sample. The lane is then fast in engineering and not in wall clock, and saying so is
    what stops it being asked to skip the sample later."""
    card = L.assign(L.Profile("ribbed-beanie", "hats", "SHORT", "B", sizes=2), qa=STABLE)
    assert card["lane"] == L.FAST
    assert "physical sample" in card["paced_by"]
    assert L.assign(_ornament(), qa=STABLE)["paced_by"] == ""


def test_an_invented_pod_is_refused_rather_than_routed():
    try:
        L.assign(L.Profile("x", "quick_wins", "QUICK", "A"), qa=STABLE)
    except L.LaneRefused as exc:
        assert "is not a pod" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented pod routed")


# --- the gate list ---------------------------------------------------------------------

def test_the_gate_list_cannot_take_a_lane_at_all():
    """The structural form of "both retain all applicable quality gates". Comparing two
    outputs proves one case; refusing the argument proves every case, and this is the line
    an edit would have to cross to weaken the guarantee."""
    params = set(inspect.signature(L.applicable_gates).parameters)
    assert params == {"profile"}
    assert "lane" not in params


def test_the_gate_list_is_the_chains_own_and_not_a_copy():
    """A second copy of this list is how the guarantee quietly stops being true."""
    assert set(L.NON_NEGOTIABLE_GATES) | set(L.CONDITIONAL_GATES) == set(CANONICAL_STAGES)
    assert not set(L.NON_NEGOTIABLE_GATES) & set(L.CONDITIONAL_GATES)
    # order preserved: the chain runs these in sequence, and a reordered copy is a copy
    assert L.applicable_gates(_ornament()) == CANONICAL_STAGES


def test_conditional_gates_are_conditional_on_the_product_and_never_on_the_lane():
    flat_no_listing = L.Profile("draft-coaster", "home_decor", "QUICK", "A")
    assert "geometry" not in L.applicable_gates(flat_no_listing)
    assert "policy" not in L.applicable_gates(flat_no_listing)
    closed_listed = _ornament()
    assert {"geometry", "asset_truth", "policy"} <= set(L.applicable_gates(closed_listed))


def test_a_release_missing_a_gate_is_refused_by_name_in_either_lane():
    p = _ornament()
    runs = tuple(L.GateRun(s, True) for s in L.applicable_gates(p) if s != "physical_test")
    for lane in L.LANES:
        try:
            L.check_release(p, runs=runs, lane=lane)
        except L.LaneRefused as exc:
            assert "physical_test" in str(exc) and "never ran" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{lane} released without physical_test")


def test_a_gate_that_ran_and_failed_is_not_a_gate_that_ran():
    p = _ornament()
    runs = tuple(L.GateRun(s, s != "policy") for s in L.applicable_gates(p))
    try:
        L.check_release(p, runs=runs, lane=L.FLAGSHIP)
    except L.LaneRefused as exc:
        assert "failed ['policy']" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a failed gate passed")


def test_a_complete_run_passes_and_names_what_it_ran():
    p = _ornament()
    out = L.check_release(p, runs=tuple(L.GateRun(s, True) for s in L.applicable_gates(p)),
                          lane=L.FAST)
    assert out["ok"] and out["gates"] == list(CANONICAL_STAGES)


def test_a_stage_outside_the_chain_is_refused():
    p = _ornament()
    runs = tuple(L.GateRun(s, True) for s in L.applicable_gates(p)) + (
        L.GateRun("vibes", True),)
    try:
        L.check_release(p, runs=runs, lane=L.FAST)
    except L.LaneRefused as exc:
        assert "vibes" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented stage was accepted")


def test_the_trend_lane_stays_at_least_as_strict_as_the_standing_one():
    """#291 is a tighter bar inside this one. If it ever loosened past the ordinary fast
    lane it would be an exemption wearing a second name, which is exactly the slide both
    modules exist to prevent."""
    assert set(F.ALLOWED_RISK_CLASSES) <= set(L.FAST_RISK_CLASSES)
    assert F.MAX_COMPONENTS <= L.FAST_MAX_COMPONENTS
    assert F.MAX_COLOURS <= L.FAST_MAX_COLOURS
    assert F.MAX_NEW_TECHNIQUES <= L.FAST_MAX_NEW_TECHNIQUES
    assert F.LANE_CEILING == L.FAST_MAKE_CEILING
    # and both run the same list, because neither may shorten it
    assert set(F.NON_NEGOTIABLE_GATES) == set(L.NON_NEGOTIABLE_GATES)


# --- the slide ---------------------------------------------------------------------------

def test_a_mix_that_starves_the_flagship_lane_is_refused_with_the_number():
    out = L.check_mix({L.FAST: 0.85, L.FLAGSHIP: 0.15})
    assert out["ok"] is False
    assert any("15%" in r and "30%" in r for r in out["reasons"])


def test_a_mix_that_starves_the_fast_lane_is_refused_too():
    """The slower ruin. Four magnificent blankets have had four chances to learn what
    sells, and a module that only guarded one floor would push the catalogue into this."""
    out = L.check_mix({L.FAST: 0.10, L.FLAGSHIP: 0.90})
    assert out["ok"] is False
    assert any("four magnificent blankets" in r for r in out["reasons"])


def test_shares_that_are_not_a_split_are_refused():
    assert L.check_mix({L.FAST: 0.6, L.FLAGSHIP: 0.6})["ok"] is False
    try:
        L.check_mix({"medium": 1.0})
    except L.LaneRefused as exc:
        assert "not production lanes" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented lane was allocated capacity")


def test_allocation_is_capacity_and_says_so():
    out = L.allocate(100)
    assert out["units"] == {L.FAST: 60.0, L.FLAGSHIP: 40.0}
    assert "never a count of products" in out["of"]
    try:
        L.allocate(100, {L.FAST: 0.9, L.FLAGSHIP: 0.1})
    except L.LaneRefused as exc:
        assert "flagship at 10%" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a starving split was allocated")


def test_balance_counts_products_and_refuses_to_call_them_capacity():
    cards = [L.assign(p, qa=STABLE) for p in
             (_ornament(), _ornament(slug="b"), _throw(),
              L.Profile("six-colour-rug", "home_decor", "MEDIUM", "B", colours=6))]
    out = L.balance(cards)
    assert out["counts"] == {L.FAST: 2, L.FLAGSHIP: 1, "neither": 1}
    assert "not the capacity shares" in out["note"]
    assert "starves both purposes" in L.balance([])["note"]


# --- after core QA stabilizes -------------------------------------------------------------

def test_two_queues_do_not_open_on_an_unread_signal():
    """The requirement opens with "after core QA stabilizes", and the tempting reading is
    a boolean somebody set. Unmeasured is not stable."""
    verdict = L.qa_stable(L.QaEvidence())
    assert verdict["stable"] is False
    assert len(verdict["reasons"]) == 4
    assert any("unmeasured is not passing" in r for r in verdict["reasons"])


def test_an_unstable_chain_leaves_one_queue_running_the_same_gates():
    card = L.assign(_ornament(), qa=L.qa_stable(L.QaEvidence()))
    assert card["lane"] is None and card["two_queues_open"] is False
    assert card["gates"] == list(CANONICAL_STAGES)
    assert "Nothing about the checking changes" in card["note"]


def test_a_halting_incident_closes_the_split():
    verdict = L.qa_stable(L.QaEvidence(9, True, 4, 1))
    assert verdict["stable"] is False
    assert any("halting" in r for r in verdict["reasons"])


def test_a_flag_is_not_evidence():
    try:
        L.assign(_ornament(), qa={"ok": True})
    except L.LaneRefused as exc:
        assert "not a flag" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a bare flag opened two queues")


def test_observed_evidence_comes_from_the_records_that_hold_it():
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(Product(slug="p1", title="P1"))
        s.flush()
        for v in ("1.0.0", "1.1.0"):
            s.add(PatternVersion(product_id=1, version=v, cir_json={}, certified=True))
        s.add(PatternVersion(product_id=1, version="0.9.0", cir_json={}, certified=False))
        s.add(Incident(severity="P1", signature="sig", halts_publication=True,
                       resolved=False))
    with db.session() as s:
        ev = L.observe(s)
    assert ev.certified_releases == 2
    assert ev.open_halting_incidents == 1
    assert L.qa_stable(ev)["stable"] is False


def test_state_reports_both_purposes_and_the_shared_list():
    out = L.state()
    assert set(out["purpose"]) == set(L.LANES)
    assert out["gates"] == list(L.NON_NEGOTIABLE_GATES)
    assert out["mix"]["floors"] == {L.FAST: L.FAST_FLOOR, L.FLAGSHIP: L.FLAGSHIP_FLOOR}
    assert "B" in out["fast"]["risk_classes_needing_a_sample"]


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
