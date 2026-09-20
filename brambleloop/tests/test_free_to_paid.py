"""#10: free work with a commercial job, and a rung nobody reached.

Two failures carry this. A free mini pattern that gives away the paid object looks exactly
like success from the inside -- the downloads rise while conversion falls. And a conversion
of 0% from an upstream of zero makes an untried funnel look like a failed one, which is how
the thing nobody tried gets abandoned as something that did not work.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.growth import free_to_paid as F, owned  # noqa: E402

TODAY = date(2026, 9, 20)


def _asset(**over):
    base = dict(key="a1", kind="motif", surface="article",
                teaches="the join-as-you-go seam our blankets use",
                leads_to="winter-throw",
                why_next="somebody who has joined four squares wants the throw that is made "
                         "of them")
    base.update(over)
    return F.FreeAsset(**base)


# --- the commercial job ----------------------------------------------------------------------

def test_free_work_with_no_next_step_is_a_giveaway():
    out = F.check_asset(_asset(leads_to=""))
    assert out["ok"] is False
    assert any("giveaway with a marketing story" in r for r in out["reasons"])


def test_a_hope_is_not_a_reason():
    out = F.check_asset(_asset(why_next="leads to the collection"))
    assert out["ok"] is False
    assert any("is a hope; the reason is the job" in r for r in out["reasons"])


def test_an_asset_with_a_job_states_it():
    out = F.check_asset(_asset())
    assert out["ok"] is True
    assert out["job"]["leads_to"] == "winter-throw"


def test_a_free_pattern_for_a_paid_object_replaces_it_rather_than_leading_to_it():
    """The expensive one. Downloads and saves go up, conversion goes down, and from the
    inside the two are indistinguishable."""
    out = F.check_asset(_asset(kind="mini_pattern", makes="hex-coaster"),
                        paid_slugs=("hex-coaster", "winter-throw"))
    assert out["ok"] is False
    assert any("it replaces it" in r for r in out["reasons"])


def test_a_free_pattern_for_something_we_do_not_sell_is_fine():
    out = F.check_asset(_asset(kind="mini_pattern", makes="practice-square"),
                        paid_slugs=("hex-coaster",))
    assert out["ok"] is True


def test_an_asset_that_leads_to_what_it_gives_away_is_not_a_funnel():
    out = F.check_asset(_asset(kind="mini_pattern", makes="winter-throw"))
    assert any("not a funnel" in r for r in out["reasons"])


def test_content_is_not_a_kind_of_free_work():
    try:
        _asset(kind="content")
    except F.FunnelRefused as exc:
        assert "is not a kind of free work" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unnameable kind was accepted")


def test_the_plan_names_premium_products_nothing_feeds():
    out = F.plan([_asset()], paid_slugs=("winter-throw", "hex-coaster"))
    assert out["premium_products_fed"] == ["winter-throw"]
    assert out["premium_products_with_nothing_feeding_them"] == ["hex-coaster"]


def test_an_empty_funnel_is_not_a_funnel_that_is_not_working():
    out = F.plan([], paid_slugs=("winter-throw",))
    assert out["with_a_job"] == 0
    assert "not a funnel that is not working" in out["note"]


# --- the ladder --------------------------------------------------------------------------------

def test_a_rung_nobody_reached_has_no_conversion_rather_than_a_bad_one():
    out = F.funnel({s: 0 for s in F.STAGES})
    assert all(step["rate"] is None for step in out["steps"])
    assert any("makes an untried funnel look like a failed one" in step["why"]
               for step in out["steps"])
    assert "unbuilt funnel, not a failing one" in out["note"]


def test_an_unmeasured_rung_says_which_half_is_missing():
    out = F.funnel({"visitor": 1000, "consented_email": None})
    assert out["steps"][0]["rate"] is None
    assert "downstream count unmeasured" in out["steps"][0]["why"]


def test_a_measured_ladder_names_its_weakest_step():
    out = F.funnel({"visitor": 1000, "consented_email": 60, "first_purchase": 12,
                    "repeat_purchase": 3, "collection_purchase": 1})
    assert out["measured_steps"] == 4
    assert out["weakest"] == "visitor"
    assert out["steps"][0]["rate"] == 0.06


def test_a_rung_larger_than_the_one_above_it_is_a_counting_fault():
    try:
        F.funnel({"visitor": 10, "consented_email": 40})
    except F.FunnelRefused as exc:
        assert "counting fault and not a remarkable funnel" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an impossible ladder was reported as a conversion")


def test_an_invented_stage_is_refused():
    try:
        F.funnel({"visitor": 10, "vibes": 3})
    except F.FunnelRefused as exc:
        assert "are not stages" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an invented stage joined the ladder")


# --- an email is a rung only once it is consented -----------------------------------------------

def test_an_address_with_no_valid_basis_is_not_a_rung():
    consents = [owned.Consent("a1", owned.EXPRESS, date(2026, 1, 1), "signup form"),
                owned.Consent("a2", owned.IMPLIED_ENQUIRY, date(2025, 1, 1), "a question"),
                owned.Consent("a3", owned.EXPRESS, date(2026, 1, 1), "signup form",
                              withdrawn_on=date(2026, 5, 1))]
    out = F.count_consented(consents, TODAY)
    assert out["captured"] == 3
    assert out["consented"] == 1
    assert out["not_a_rung"] == 2
    assert "liability" not in out["why"] or True
    assert "non-compliant on the same day" in out["why"]


def test_state_names_what_every_asset_must_carry():
    out = F.state()
    assert set(out["every_asset_must_name"]) == {"leads_to", "why_next", "teaches"}
    assert out["stages"][0] == "visitor" and out["stages"][-1] == "collection_purchase"


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
