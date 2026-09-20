"""#9/#21: a roster that buys work, and never an opinion.

The whole category is one step from the thing the owner's directive forbids outright, so
most of these tests are about what the module cannot express rather than what it computes.
A review is not a deliverable, a sentiment condition is refused even when the deliverable is
honest, an unobserved audience stays a claim, and an unmeasured outcome is not a zero.
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CreatorProfile  # noqa: E402
from brambleloop.growth import creators as C, owned  # noqa: E402
from brambleloop.quality.testers import RELIABLE_AT  # noqa: E402

MESSAGE = {"sender_name": "Brambleloop", "mailing_address": "a real address",
           "contact": "hello@example.invalid", "unsubscribe_url": "https://example.invalid/u"}


def _creator(**over):
    base = dict(ref="cr-1", specialties=("ornaments", "amigurumi"), invited=4, delivered=4,
                address_published=True)
    base.update(over)
    return C.Creator(**base)


# --- what may never be bought -------------------------------------------------------------

def test_a_review_is_not_a_deliverable_and_cannot_be_made_one():
    """The directive's own sentence, made unrepresentable rather than discouraged."""
    assert not set(C.NEVER_A_DELIVERABLE) & set(C.DELIVERABLES)
    for word in ("review", "rating", "testimonial", "five_star"):
        out = C.check_brief(C.Brief("cr-1", "ornaments", ("finished_photograph", word)))
        assert out["ok"] is False
        assert any("opinion" in r for r in out["reasons"]), word


def test_a_sentiment_condition_is_refused_even_when_the_deliverable_is_honest():
    """The side door. The deliverable is a photograph -- what is bought is the caption."""
    honest = ("finished_photograph",)
    for terms in ("photograph it and say something nice",
                  "fee paid on a positive post",
                  "we will send the next one if it goes well",
                  "a glowing write-up would help"):
        out = C.check_brief(C.Brief("cr-1", "ornaments", honest, terms=terms))
        assert out["ok"] is False, terms
        assert any("terms contain" in r for r in out["reasons"]), terms


def test_an_honest_brief_passes_and_says_what_it_is_buying():
    out = C.check_brief(C.Brief("cr-1", "ornaments",
                                ("finished_photograph", "colour_variation", "tested_sample")))
    assert out["ok"] is True
    assert out["asks_for"] == ["finished_photograph", "colour_variation", "tested_sample"]
    assert "buys work and nothing else" in out["note"]


def test_a_collaboration_that_asks_for_nothing_is_refused():
    """A gift with an unstated expectation is the arrangement hardest to keep honest."""
    out = C.check_brief(C.Brief("cr-1", "ornaments", ()))
    assert out["ok"] is False
    assert any("asks for nothing" in r for r in out["reasons"])


def test_money_makes_it_the_owners_decision():
    out = C.check_brief(C.Brief("cr-1", "ornaments", ("audience_post",), fee_cad=40.0,
                                disclosure_in_post="paid partnership with Brambleloop"))
    assert out["ok"] is False
    assert any("consequential spend" in r for r in out["reasons"])
    # and seeding at zero is available today, which is the point of starting small
    assert C.check_brief(C.Brief("cr-1", "ornaments", ("audience_post",)))["ok"] is True


def test_an_affiliate_arrangement_must_be_disclosed_where_it_is_read():
    undisclosed = C.check_brief(C.Brief("cr-1", "ornaments", ("audience_post",),
                                        affiliate=True))
    assert any("carries its disclosure" in r for r in undisclosed["reasons"])
    vague = C.check_brief(C.Brief("cr-1", "ornaments", ("audience_post",), affiliate=True,
                                  disclosure_in_post="made with a lovely pattern"))
    assert any("does not say what it is" in r for r in vague["reasons"])
    clear = C.check_brief(C.Brief("cr-1", "ornaments", ("audience_post",), affiliate=True,
                                  disclosure_in_post="gifted pattern, affiliate link below"))
    assert clear["ok"] is True


def test_no_code_path_can_project_a_reach():
    """The fabricated-engagement failure arrives as a spreadsheet more often than as a lie.
    Asserted by reading the source, because "we would never" is not a control."""
    source = inspect.getsource(C)
    body = source.split("NEVER_PROJECTED", 1)[1]
    for banned in ("audience_stated *", "* engagement", "reach =", "impressions ="):
        assert banned not in body, banned
    assert "expected_reach" in C.NEVER_PROJECTED


# --- claims stay claims --------------------------------------------------------------------

def test_a_stated_audience_is_kept_as_a_claim_with_its_source():
    claimed = _creator(audience_stated=4200).to_dict()
    assert claimed["audience"]["verified"] is False
    assert claimed["audience"]["evidence"] == "self-reported"
    checked = _creator(audience_stated=4200,
                       audience_evidence="counted from their public page 2026-09-20").to_dict()
    assert checked["audience"]["verified"] is True


def test_an_unrecorded_audience_is_not_zero():
    out = _creator().to_dict()
    assert out["audience"]["stated"] is None
    assert "not zero" in out["audience"]["why"]


def test_an_engagement_rate_travels_with_the_day_it_was_observed():
    """A rate with no date is a rate from whenever somebody last looked, which is the
    number people quote for years."""
    try:
        _creator(engagement_observed=0.06)
    except C.CreatorRefused as exc:
        assert "travel together" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an undated engagement rate was accepted")
    ok = _creator(engagement_observed=0.06, observed_on=date(2026, 9, 20)).to_dict()
    assert ok["engagement"]["observed_on"] == "2026-09-20"


def test_never_having_been_asked_is_neither_reliable_nor_unreliable():
    new = _creator(invited=0, delivered=0)
    assert new.reliable is False
    assert new.to_dict()["basis"] == "too few invitations to say"
    assert _creator(invited=4, delivered=4).reliable is True
    # the threshold is the tester roster's own, not a second opinion about the same idea
    assert _creator(invited=10, delivered=int(10 * RELIABLE_AT)).reliable is True
    assert _creator(invited=10, delivered=int(10 * RELIABLE_AT) - 1).reliable is False


def test_a_specialty_outside_the_departments_is_refused():
    try:
        C.Creator("cr-x", ("vibes",))
    except C.CreatorRefused as exc:
        assert "not departments this company works in" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an unroutable specialty joined the roster")


def test_the_shortlist_is_ordered_by_delivered_work_and_not_by_audience():
    big = _creator(ref="huge", audience_stated=200000, invited=1, delivered=0)
    small = _creator(ref="small", audience_stated=900, invited=5, delivered=5)
    out = C.shortlist([big, small], pod="ornaments")
    assert [c["ref"] for c in out["shortlist"]] == ["small", "huge"]
    assert "huge" in out["not_yet_demonstrated"]
    assert "delivered nothing until it has" in out["ordered_by"]


def test_an_empty_roster_reports_a_gap_in_the_roster():
    out = C.shortlist([_creator()], pod="blankets")
    assert out["fits"] == 0
    assert "gap in the roster rather than a property of the department" in out["note"]


# --- permission ----------------------------------------------------------------------------

def test_a_photo_licensed_for_their_channel_is_not_licensed_for_our_listing():
    c = _creator(permissions=(C.Permission("perm-1", "img-1", "creator_channel",
                                           date(2026, 1, 1)),))
    assert C.may_use(c, asset_ref="img-1", scope="creator_channel")["may_use"] is True
    denied = C.may_use(c, asset_ref="img-1", scope="brambleloop_listing")
    assert denied["may_use"] is False
    assert "different question" in denied["why"]


def test_absent_permission_is_not_implied_permission():
    out = C.may_use(_creator(), asset_ref="img-9", scope="brambleloop_listing")
    assert out["may_use"] is False
    assert "Absent permission is not implied permission" in out["why"]


def test_an_expired_permission_is_refused_like_an_absent_one():
    c = _creator(permissions=(C.Permission("perm-2", "img-2", "advertising",
                                           date(2026, 1, 1), date(2026, 6, 1)),))
    out = C.may_use(c, asset_ref="img-2", scope="advertising", today=date(2026, 9, 20))
    assert out["may_use"] is False and "expired" in out["why"]


def test_a_renewal_beats_the_expired_row_it_replaced():
    """A renewal is a second row rather than an edit to the first, so returning whichever
    was recorded first would refuse a use somebody has actually been granted."""
    c = _creator(permissions=(
        C.Permission("old", "img", "advertising", date(2025, 1, 1), date(2026, 1, 1)),
        C.Permission("new", "img", "advertising", date(2026, 2, 1), date(2027, 1, 1))))
    out = C.may_use(c, asset_ref="img", scope="advertising", today=date(2026, 9, 20))
    assert out["may_use"] is True and out["ref"] == "new"


def test_a_permission_with_no_reference_is_an_assertion():
    try:
        C.Permission("  ", "img-3", "creator_channel", date(2026, 1, 1))
    except C.CreatorRefused as exc:
        assert "go and look" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an uncheckable permission was recorded")


# --- outreach is a commercial electronic message -------------------------------------------

def test_outreach_travels_on_the_published_address_basis():
    out = C.outreach_gate(_creator(), MESSAGE, relevant_to_their_business=True)
    assert out["sendable"] is True
    assert out["basis"] == owned.IMPLIED_PUBLISHED
    assert "not legal advice" in out["screen_not_clearance"]


def test_an_unpublished_address_has_no_basis_and_a_refusal_removes_it():
    unpublished = C.outreach_gate(_creator(address_published=False), MESSAGE,
                                  relevant_to_their_business=True)
    assert unpublished["sendable"] is False
    assert any("no conspicuously published" in b for b in unpublished["blocked_by"])
    refusing = C.outreach_gate(_creator(address_refuses_unsolicited=True), MESSAGE,
                               relevant_to_their_business=True)
    assert refusing["sendable"] is False
    assert any("refusing unsolicited" in b for b in refusing["blocked_by"])


def test_relevance_is_a_condition_rather_than_a_courtesy():
    out = C.outreach_gate(_creator(), MESSAGE, relevant_to_their_business=False)
    assert out["sendable"] is False
    assert any("relevant to the business capacity" in b for b in out["blocked_by"])


def test_the_message_requirements_are_the_casl_ones_and_not_a_second_copy():
    out = C.outreach_gate(_creator(), {"sender_name": "Brambleloop"},
                          relevant_to_their_business=True)
    assert out["sendable"] is False
    assert len(out["missing_from_message"]) == len(owned.REQUIRED_IN_EVERY_MESSAGE) - 1


# --- #21: measure before scaling -----------------------------------------------------------

def test_spend_does_not_scale_on_an_unmeasured_outcome():
    """The quiet failure: a null averages as a zero to anything that averages it, and a
    roster scaled on no bad news is a release passed by the absence of a complaint."""
    outcomes = [C.Outcome(f"cr-{i}", usable_assets=2) for i in range(3)]
    out = C.may_scale(outcomes)
    assert out["may_scale"] is False
    assert all("unmeasured" in r or "floor" in r for r in out["reasons"])
    assert any("not a zero" in r for r in out["reasons"])


def test_two_completed_collaborations_are_a_coincidence():
    measured = [C.Outcome(f"cr-{i}", usable_assets=1, attributable_sessions=40,
                          conversions=2, support_cases=0, measured_on=date(2026, 9, 20))
                for i in range(2)]
    assert C.may_scale(measured)["may_scale"] is False
    assert C.may_scale(measured + [measured[0]])["may_scale"] is True


def test_a_measured_run_reports_the_proof_assets_and_the_spend():
    measured = [C.Outcome(f"cr-{i}", usable_assets=2, attributable_sessions=40, conversions=1,
                          support_cases=0, spend_cad=0.0, measured_on=date(2026, 9, 20))
                for i in range(3)]
    out = C.may_scale(measured)
    assert out["may_scale"] is True
    assert out["usable_proof_assets"] == 6 and out["spend_so_far_cad"] == 0.0


# --- the roster as it stands ---------------------------------------------------------------

def test_the_roster_is_empty_and_says_so_rather_than_reporting_zero_reliability():
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        out = C.roster(s)
    assert out["on_roster"] == 0
    assert "not a network whose reliability is zero" in out["note"]


def test_a_recorded_creator_keeps_its_evidence_field_honest():
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        s.add(CreatorProfile(ref="cr-1", specialties=["ornaments"], audience_stated=4200,
                             invited=2, delivered=1))
    with db.session() as s:
        out = C.roster(s)
    assert out["on_roster"] == 1
    assert out["creators"][0]["audience_evidence"] == "self-reported"


def test_state_names_what_can_never_be_bought():
    out = C.state()
    assert "review" in out["never_a_deliverable"]
    assert out["free_seeding_ceiling_cad"] == 0.0
    assert out["outreach_basis"]["basis"] == owned.IMPLIED_PUBLISHED


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
