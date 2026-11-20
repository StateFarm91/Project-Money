"""#254: customisation that does not fork the pattern.

The failure this prevents is the one every shop makes: offering "custom initials", delivering
a hand-edited PDF, and shipping an uncompiled pattern under a certified product's name. The
buyer's copy is the only one nobody checked, and it is the one most likely to be wrong,
because it is the only one edited by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.gates.certificate import CANONICAL_STAGES  # noqa: E402
from brambleloop.products import personalisation as P  # noqa: E402


# --- the line ------------------------------------------------------------------------------

def test_a_colour_or_size_or_layout_choice_leaves_the_instructions_alone():
    for option in ("colour_plan", "size_selection", "printable_variant"):
        assert P.OPTIONS[option]["level"] == P.PRESENTATION, option
        assert P.check(P.Offer("throw", option))["ok"] is True, option


def test_letters_are_stitches():
    spec = P.OPTIONS["initials_or_name"]
    assert spec["level"] == P.CONSTRUCTION
    assert "letters are stitches" in spec["why"]


def test_a_construction_choice_sold_under_the_originals_certificate_is_refused():
    out = P.check(P.Offer("throw", "initials_or_name", price_cad=8.0))
    assert out["ok"] is False
    assert "the only one edited by hand" in out["reasons"][0]
    assert out["route"].startswith("route it through the chain")


def test_it_is_routed_rather_than_refused():
    """A construction customisation becomes a product and gets its own certificate."""
    out = P.check(P.Offer("throw", "initials_or_name", price_cad=8.0, own_certificate=True))
    assert out["ok"] is True
    assert out["route"] == "sell it"


def test_what_it_needs_is_the_chains_own_stages():
    out = P.check(P.Offer("throw", "motif_arrangement", price_cad=8.0))
    assert set(out["needs"]) <= set(CANONICAL_STAGES) | {"certificate"}
    assert "compile" in out["needs"] and "twin" in out["needs"]


def test_a_presentation_choice_needs_nothing():
    assert P.check(P.Offer("throw", "colour_plan"))["needs"] == []


# --- the pricing asymmetry ----------------------------------------------------------------------

def test_charging_for_a_presentation_choice_is_charging_for_the_listing():
    out = P.check(P.Offer("throw", "colour_plan", price_cad=3.0))
    assert any("charging for the listing rather than for work" in r for r in out["reasons"])


def test_giving_away_a_construction_choice_is_the_expensive_complexity():
    out = P.check(P.Offer("throw", "motif_arrangement", own_certificate=True))
    assert any("expensive complexity" in r for r in out["reasons"])


def test_the_catalogue_splits_by_what_it_costs_to_honour():
    out = P.catalogue("throw")
    assert set(out["included"]) == {"colour_plan", "size_selection", "printable_variant"}
    assert set(out["needs_its_own_certificate"]) == {"initials_or_name", "motif_arrangement",
                                                     "added_component"}
    assert "at any volume" in out["why"]


def test_an_option_nobody_named_is_refused():
    try:
        P.Offer("throw", "anything_you_like")
    except P.PersonalisationRefused as exc:
        assert "is not a customisation" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unbounded customisation was offered")


def test_every_option_says_why_it_is_on_its_side_of_the_line():
    for option, spec in P.OPTIONS.items():
        assert spec["level"] in (P.PRESENTATION, P.CONSTRUCTION), option
        assert len(spec["why"].split()) >= 8, option


def test_state_names_the_failure_it_prevents():
    out = P.state()
    assert "hand-edited PDF" in out["note"] or "edited by hand" in out["note"]
    assert set(out["levels"]) == {P.PRESENTATION, P.CONSTRUCTION}


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
