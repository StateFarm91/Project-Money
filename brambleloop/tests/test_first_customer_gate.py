"""The first customer's gate: the states that are not passes, and the yes it cannot give.

The owner's rule is that Launch-0 is not beta quality -- the first paid products carry
disproportionate weight because early reviews decide a new shop's next six months. So this
file is mostly about the ways a quality gate lies: by passing an area nobody measured, by
counting "could not check" as "checked", by letting an automated green authorise a human
decision, and by marking a physical fact resolved because resolving it is inconvenient.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.gates import first_customer as fc  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

_GATE: dict = {}


def _launch0() -> dict:
    """One run, cached: it renders ten PDFs and the suite is not ten identical gates."""
    if not _GATE:
        _GATE["r"] = fc.gate_launch0()
    return _GATE["r"]


# ---- the states that are not passes ---------------------------------------


def test_unverifiable_and_unresolved_are_not_passes():
    """The defect this whole repository keeps meeting, in the place it would cost most.

    A gate whose "could not check" counts as "checked" reports green on a listing nobody
    looked at. Both states block, and the module says so in one frozen set rather than in
    four scattered comparisons.
    """
    assert fc.BLOCKING_STATES == {fc.FAIL, fc.UNVERIFIABLE, fc.UNRESOLVED}
    for state in (fc.FAIL, fc.UNVERIFIABLE, fc.UNRESOLVED):
        assert fc.Check("imagery", state, "d", "m").blocks, state
    assert not fc.Check("imagery", fc.PASS, "d", "m").blocks


def test_a_gate_with_a_silent_area_refuses_to_exist():
    """Nine minus the ones nobody reported is not nine."""
    one = (fc.Check("final_pdf", fc.PASS, "d", "m"),)
    try:
        fc.ProductGate("x", one)
    except ValueError as e:
        assert "passes by omission" in str(e), e
    else:
        raise AssertionError("a gate reported on one area of nine and was accepted")

    # And the same area twice is not two areas.
    doubled = tuple(fc.Check(a, fc.PASS, "d", "m") for a in fc.AREAS) + one
    try:
        fc.ProductGate("x", doubled)
    except ValueError as e:
        assert "twice" in str(e), e
    else:
        raise AssertionError("one area was reported twice and counted as coverage")


def test_a_check_must_say_what_it_read_and_where():
    """A state with no instrument is an opinion. The dataclass refuses to hold one."""
    for bad in (("final_pdf", fc.PASS, "", "m"), ("final_pdf", fc.PASS, "d", "")):
        try:
            fc.Check(*bad)
        except ValueError as e:
            assert "not a check" in str(e), e
        else:
            raise AssertionError(f"a check with no {'detail' if not bad[2] else 'instrument'}")
    try:
        fc.Check("not_an_area", fc.PASS, "d", "m")
    except ValueError as e:
        assert "nine areas" in str(e), e
    else:
        raise AssertionError("an area outside the owner's nine was accepted")


# ---- the yes it cannot give ------------------------------------------------


def test_the_gate_never_authorises_publication_however_green_it_gets():
    """Owner rule: automated PASS alone does not authorize publication.

    Encoded as a field with its reason rather than as a sentence in a document, so a caller
    that wants a yes has to go and ask a person. Asserted on an all-PASS gate, because the
    interesting case is the one where everything passed.
    """
    perfect = fc.ProductGate("x", tuple(
        fc.Check(a, fc.PASS, "measured", "instrument") for a in fc.AREAS))
    assert perfect.ready_for_owner_review is True
    assert perfect.to_dict()["authorises_publication"] is False
    assert "not a substitute" in perfect.to_dict()["why"]
    assert _launch0()["authorises_publication"] is False

    # There is no argument, flag or state that flips it.
    assert "authorises_publication" not in fc.gate_product.__code__.co_varnames
    source = (ROOT / "src/brambleloop/gates/first_customer.py").read_text()
    assert source.count("\"authorises_publication\": False") == 2
    assert "authorises_publication\": True" not in source


def test_physical_validation_is_reported_unresolved_and_cannot_be_marked_otherwise():
    """`twin.calibrated` is False catalogue-wide and this module cannot set it True.

    The owner's instruction is explicit -- do not falsely mark twin.calibrated True; physical
    validation remains unresolved and must be explicitly resolved for claims requiring
    measurement before publication. So it reads UNRESOLVED, which blocks, and the word
    "calibrated" appears in this module only as something read.
    """
    report = _launch0()
    assert "unresolved" in report["physical_validation"]
    for product in report["products"]:
        gauge = [c for c in product["checks"] if c["area"] == "gauge_and_size_claims"][0]
        assert gauge["state"] == fc.UNRESOLVED, (product["slug"], gauge)
        assert gauge["blocks"] is True

    source = (ROOT / "src/brambleloop/gates/first_customer.py").read_text()
    assert "calibrated = True" not in source and "calibrated=True" not in source


# ---- what it actually measures --------------------------------------------


def test_every_launch0_variant_is_gated_and_none_is_ready_today():
    """Driven by LAUNCH0_SLUGS, so a product cannot join Launch-0 unchecked."""
    report = _launch0()
    expected = sum(len(l0.candidate(s).variants) for s in l0.LAUNCH0_SLUGS)
    assert report["variants_checked"] == expected, report["variants_checked"]
    assert report["ready_for_owner_review"] == [], (
        "nothing should be ready while the store is ephemeral, no listing or image set has "
        "been built, and nothing has authenticated against Etsy")
    assert set(report["blocking"]) == {p["slug"] for p in report["products"]}


def test_the_four_areas_that_pass_pass_on_measured_evidence():
    """The document, its terminology, its arithmetic and its licence are genuinely clean.

    Stated as a check so that a regression in any of them shows up here as a first-customer
    failure rather than only as a unit-test failure three modules away.
    """
    for product in _launch0()["products"]:
        states = {c["area"]: c["state"] for c in product["checks"]}
        for area in ("final_pdf", "terminology", "counts_and_construction",
                     "licence_and_safety_statements"):
            assert states[area] == fc.PASS, (product["slug"], area, states[area])


def test_an_unbuilt_listing_and_an_unbuilt_image_set_read_unverifiable_not_clean():
    """A listing nobody wrote is unchecked. The distinction is the point of the state."""
    cir = l0.cir_for(l0.candidate("hexagon-coaster-set").variants[0].build)
    gate = fc.gate_product(cir, listing=None, frames=None)
    states = {c.area: c.state for c in gate.checks}
    assert states["listing_claims"] == fc.UNVERIFIABLE
    assert states["imagery"] == fc.UNVERIFIABLE
    assert all(c.blocks for c in gate.checks
               if c.area in ("listing_claims", "imagery"))


def test_a_listing_that_over_claims_fails_rather_than_being_absent():
    """And the same area reads FAIL once something exists to be wrong.

    An UNVERIFIABLE that never becomes a FAIL would mean the check is decorative, so this
    feeds it a draft whose title claims a technique the fabric does not work.
    """
    from brambleloop.gates.policy import ListingDraft

    cir = l0.cir_for(l0.candidate("hexagon-coaster-set").variants[0].build)
    bad = ListingDraft(title="Heirloom Cable Coaster Set Pattern",
                       description="A cabled coaster set. Not a finished item.",
                       tags=["crochet pattern"], price_cad=4.0)
    gate = fc.gate_product(cir, listing=bad, frames=None)
    claim = [c for c in gate.checks if c.area == "listing_claims"][0]
    assert claim.state == fc.FAIL, claim
    assert "CLAIM_TECHNIQUE_UNSUPPORTED" in claim.detail, claim.detail


def test_the_download_is_a_first_customer_failure_while_the_store_is_ephemeral():
    """Found by building this gate: a paid download can resolve to nothing.

    The artifact store announces its own ephemerality and the release chain audits it every
    time, but nothing had ever called it a blocker to a first sale. It is the worst available
    first-customer outcome -- worse than a wrong stitch count, because it looks like theft.
    """
    class _Ephemeral:
        durable = False

    class _Durable:
        durable = True

    assert fc.check_fulfilment_and_download(_Ephemeral()).state == fc.FAIL
    assert fc.check_fulfilment_and_download(_Durable()).state == fc.PASS
    for product in _launch0()["products"]:
        row = [c for c in product["checks"] if c["area"] == "fulfilment_and_download"][0]
        assert row["state"] == fc.FAIL, product["slug"]


def test_etsy_remote_state_is_unverifiable_rather_than_passing_on_a_local_fake():
    """One successful fake-shop run is not evidence of Etsy behaviour.

    The transport is exercised end to end against a faithful local model of Etsy, and that is
    a claim about our side of the wire. This area is about the remote state, and nothing has
    ever authenticated, so it cannot be anything but UNVERIFIABLE today.
    """
    check = fc.check_etsy_remote_state()
    assert check.state == fc.UNVERIFIABLE
    assert "never authenticated" in check.detail or "authenticated" in check.detail
    assert check.blocks


def test_a_pattern_that_does_not_compile_fails_every_area_for_one_stated_reason():
    """Eight failures from one cause read as eight problems. They are one."""
    import fixtures
    from brambleloop.cir.model import CIR

    broken = fixtures.broken_stitch_count()
    gate = fc.gate_product(broken)
    assert len(gate.checks) == len(fc.AREAS)
    assert {c.state for c in gate.checks} == {fc.FAIL}
    assert len({c.detail for c in gate.checks}) == 1, "one cause, stated once"
    assert isinstance(broken, CIR)


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
    print(f"\n  {len([n for n in globals() if n.startswith('test_')]) - fails} passing, "
          f"{fails} failing")
    sys.exit(1 if fails else 0)
