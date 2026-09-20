"""#4: testing a concept before engineering it, without implying it can be bought.

The value and the hazard are the same act. A picture of a thing that does not exist, posted
where people buy things, is a pre-order somebody will try to place. These tests are about the
refusals, and about the prohibition that has to be structural rather than promised.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import preproduction as P  # noqa: E402
from brambleloop.creative.concept import Concept  # noqa: E402

TODAY = date(2026, 9, 20)


def _concept(key="k"):
    return Concept(
        key=key, title="Lantern Brim Beanie",
        premise="a folded brim that stands proud of the crown so it reads across a room",
        pod="hats", form="hat", construction="in_the_round", motif="lantern",
        palette_story="ember and soot", recipient="self", occasion="everyday",
        feeling="cosy", function="warmth", make_lane="SHORT", provenance="test")


def test_a_post_that_does_not_say_it_is_a_concept_is_refused():
    """In the words a scroller reads, not in a hashtag at the end."""
    problems = P.check_post("Our newest hat design, coming together nicely")
    assert any("does not say it is a concept" in p["problem"] for p in problems)
    assert any("pre-order somebody will try to place" in p["why"] for p in problems)

    assert P.check_post(
        "A concept we are thinking about making. Not yet available. Would you make this?"
    ) == []


def test_every_phrase_that_promises_a_purchase_is_refused():
    """Each is a promise about a thing that does not exist."""
    for text, fragment in (
            ("A concept — shop now", "shop now"),
            ("A concept. Get yours today", "get yours"),
            ("A concept, link in bio", "link in bio"),
            ("A concept, pre-order open", "pre-order"),
            ("A concept, available now", "available now"),
            ("A concept for CA$12", "ca$1")):
        problems = P.check_post(text)
        assert any(fragment in p["problem"] for p in problems), (text, problems)


def test_a_price_is_an_offer():
    """The most quietly damaging one: nothing says 'purchasable' like a number with a
    currency in front of it."""
    problems = P.check_post("A concept we are thinking about. $14 if we make it.")
    assert any("a price is an offer" in p["why"] for p in problems), problems


def test_a_concept_shown_with_somebody_elses_photograph_is_refused():
    raised = None
    try:
        P.prepare(_concept(), channel="pinterest",
                  body="A concept we are thinking about making. Not yet available.",
                  image_source="benchmark_listing")
    except P.PreProductionRefused as e:
        raised = e
    assert raised is not None
    assert "competitor's work presented as a plan" in str(raised)


def test_the_generated_body_passes_its_own_check():
    """A module whose own output would be refused by its own gate is a module nobody can
    use, and the gate would be quietly loosened to fix it."""
    out = P.validate([_concept()], today=TODAY)
    assert out["refused"] == [], out["refused"]
    assert len(out["prepared"]) == 1
    body = out["prepared"][0]["body"]
    assert P.check_post(body) == []
    assert "not yet available" in body.lower()
    assert out["prepared"][0]["detail"]["engineered"] is False


def test_no_code_path_can_author_an_engagement_number():
    """"We would never" is not a control, and the whole category does this.

    The prohibition is checked by reading the source, because the only reliable form of this
    rule is the absence of a way to break it.
    """
    source = (ROOT / "src/brambleloop/commerce/preproduction.py").read_text()
    # No literal metric assignment anywhere in the module.
    for metric in P.NEVER_FABRICATED:
        assert f'"{metric}":' not in source.replace('NEVER_FABRICATED', ''), metric
    post = P.prepare(_concept(), channel="pinterest",
                     body="A concept we are thinking about making. Not yet available.",
                     today=TODAY)
    silent = P.record_interest(post, observed=None, source="")
    assert silent["measurable"] is False
    assert "forbidden outright" in silent["why"]


def test_interest_with_no_named_source_cannot_be_told_from_invented_interest():
    post = P.prepare(_concept(), channel="pinterest",
                     body="A concept we are thinking about making. Not yet available.",
                     today=TODAY)
    raised = None
    try:
        P.record_interest(post, observed={"saves": 40}, source="  ")
    except P.PreProductionRefused as e:
        raised = e
    assert raised is not None
    assert "invented" in str(raised)

    real = P.record_interest(post, observed={"saves": 40}, source="pinterest analytics")
    assert real["measurable"] is True
    assert real["observed"]["saves"] == 40
    assert "no code path that can author one" in real["why"]


def test_publishing_is_gated_and_the_refusals_run_anyway():
    """The safe state and the honest one: the gate is tested before the day it matters."""
    out = P.validate([_concept()], today=TODAY)
    assert out["publishing"]["state"] == "gated"
    assert out["publishing"]["gated_on"] == "social_credentials"
    assert "tested before the day they matter" in out["publishing"]["why"]
    assert set(out["never"]) == {"fake_listings", "fake_purchases", "fake_engagement"}


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
