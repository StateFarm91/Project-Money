"""Customer Experience, content ecosystem and portfolio management (sections 10, 11, 12).

Each of these departments is defined as much by what it refuses to do as by what it produces.
Support refuses to invent a stitch correction or to trade a review. Marketing refuses to buy
engagement or to state a size the pattern does not produce. Portfolio refuses to classify a
SKU nobody has seen. Those refusals are the tests.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import SupportCase  # noqa: E402
from brambleloop.gates.incidents import IncidentTracker  # noqa: E402
from brambleloop.growth import content as content_mod  # noqa: E402
from brambleloop.growth import portfolio as pf  # noqa: E402
from brambleloop.products import nordic_forest as nf  # noqa: E402
from brambleloop.support import department as dept  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _facts(**over) -> content_mod.ProductFacts:
    base = dict(slug="nordic-forest-mosaic-throw",
                title="Nordic Forest Overlay Mosaic Throw", category="mosaic_blanket",
                size_label="90 x 122 cm", difficulty="confident beginner",
                stitches=["dc", "sc"], colors=["cream", "forest"],
                yardage_line="cream about 328-492 m; forest about 320-480 m",
                maker_hours=(30.0, 60.0), season="Christmas", price_cad=12.5,
                siblings=["Nordic Star Ornament Set (6)"])
    base.update(over)
    return content_mod.ProductFacts(**base)


# ---- triage ----------------------------------------------------------------


def test_every_message_reaches_the_right_desk():
    cases = [
        ("I want a chargeback, this is a scam", dept.ESCALATE),
        ("can you delete my data please", dept.ESCALATE),
        ("the PDF will not open", dept.DOWNLOAD),
        ("my download link is broken", dept.DOWNLOAD),
        ("row 12 does not add up", dept.TROUBLESHOOTER),
        ("I ran out of stitches on row 8", dept.TROUBLESHOOTER),
        ("how much yarn do I need?", dept.MATERIALS),
        ("what does dc mean?", dept.CROCHET_HELP),
        ("thank you, it turned out beautifully", dept.HAPPINESS),
    ]
    for message, expected in cases:
        assert dept.triage(message) == expected, (message, dept.triage(message))


def test_a_legal_matter_is_never_absorbed_by_the_materials_desk():
    """Routing order is a safety property, not a convenience."""
    assert dept.triage("I am starting a chargeback, also how much yarn is this") == dept.ESCALATE
    assert dept.triage("my lawyer says the download is broken") == dept.ESCALATE


def test_routine_questions_do_not_wake_the_owner():
    """Section 10 is explicit. A department that escalates everything does nothing."""
    db = _db()
    cx = dept.CustomerExperience(db)
    cir = nf.build("baby")
    for message in ("how many stitches at the end of row 6?", "what gauge is this?",
                    "how much yarn do I need?", "is this in UK terms?"):
        reply = cx.handle(customer_ref="c", message=message, cir=cir,
                          product_slug="x", version="1.0.0")
        assert not reply.escalated, (message, reply.body)


def test_legal_and_privacy_always_escalate():
    db = _db()
    cx = dept.CustomerExperience(db)
    reply = cx.handle(customer_ref="c", message="I am filing a chargeback")
    assert reply.escalated
    assert "person" in reply.body.lower()
    assert "chargeback" in reply.escalation_reason


def test_nothing_is_ever_sent_in_shadow_mode():
    db = _db()
    cx = dept.CustomerExperience(db)
    cx.handle(customer_ref="c", message="the PDF will not open")
    with db.session() as s:
        cases = list(s.scalars(select(SupportCase)))
    assert cases and all(c.sent is False for c in cases)


def test_support_will_not_answer_without_knowing_which_version():
    db = _db()
    reply = dept.CustomerExperience(db).handle(
        customer_ref="c", message="what should row 9 come to?")
    assert reply.escalated
    assert "which pattern" in reply.body.lower()


def test_a_reply_may_never_trade_or_steer_a_review():
    """Asking for a review is fine. Asking for a *good* one is fabricated engagement."""
    for bad in ("leave us a five star review and we will refund you",
                "discount if you review", "a positive review would really help"):
        try:
            dept.check_reply(bad)
        except dept.ReviewSolicitationViolation as e:
            assert "earned by the product" in str(e)
        else:
            raise AssertionError(f"accepted review solicitation: {bad!r}")
    dept.check_reply(dept.HAPPINESS_REPLY)


def test_repeated_questions_about_one_row_surface_as_a_candidate_defect():
    """The third person to ask about row 48 is evidence about the pattern."""
    db = _db()
    cx = dept.CustomerExperience(db)
    cir = nf.build("baby")
    for i in range(3):
        cx.handle(customer_ref=f"c{i}", message="what should row 6 come to?", cir=cir,
                  product_slug="nordic-baby", version="1.0.0")
    mined = cx.mine_cases()
    assert mined["cases"] == 3
    hotspot = next(h for h in mined["row_hotspots"] if h["row"] == 6)
    assert hotspot["mentions"] == 3
    assert "not confirmed" in mined["note"]


def test_support_still_cannot_change_a_pattern():
    db = _db()
    cx = dept.CustomerExperience(db)
    tracker = IncidentTracker(db)
    for i in range(3):
        cx.report_defect(product_slug="p", version="1.0.0", component="blanket", row=4,
                         customer_ref=f"c{i}", description="row 4 count is wrong")
    assert tracker.publication_halted("p"), "three reports did not halt publication"


# ---- content ecosystem -----------------------------------------------------


def test_a_product_gets_a_full_content_ecosystem():
    pieces = content_mod.build_ecosystem(_facts(), launch_on=date(2026, 9, 24))
    channels = {p.channel for p in pieces}
    for required in ("article", "pinterest", "video", "email", "teaser"):
        assert required in channels, required
    assert content_mod.check_ecosystem(pieces, _facts()) == []


def test_content_is_scheduled_backwards_from_launch_with_time_to_index():
    pieces = content_mod.build_ecosystem(_facts(), launch_on=date(2026, 9, 24))
    article = next(p for p in pieces if p.channel == "article")
    assert article.scheduled_for <= "2026-09-03", "search indexing takes weeks, not days"
    video = next(p for p in pieces if p.channel == "video")
    assert video.scheduled_for > "2026-09-24", "the tutorial follows the launch"


def test_four_pins_say_four_different_things():
    pieces = content_mod.build_ecosystem(_facts(), launch_on=date(2026, 9, 24))
    pins = [p for p in pieces if p.channel == "pinterest"]
    assert len(pins) == content_mod.PINS_PER_PRODUCT
    assert len({p.detail["angle"] for p in pins}) == len(pins)
    for p in pins:
        assert len(p.title) <= content_mod.PIN_TITLE_MAX
        assert len(p.body) <= content_mod.PIN_DESCRIPTION_MAX


def test_engagement_bait_is_rejected():
    facts = _facts()
    pieces = content_mod.build_ecosystem(facts, launch_on=date(2026, 9, 24))
    pieces[0].body += "\n\nTag five friends to win a free pattern!"
    problems = content_mod.check_ecosystem(pieces, facts)
    assert any("ENGAGEMENT_BAIT" in p for p in problems), problems


def test_content_may_not_state_a_size_the_pattern_does_not_produce():
    facts = _facts()
    pieces = content_mod.build_ecosystem(facts, launch_on=date(2026, 9, 24))
    pieces[0].body += "\n\nFinished size: 150 x 200 cm."
    problems = content_mod.check_ecosystem(pieces, facts)
    assert any("SIZE_DRIFT" in p for p in problems), problems


def test_a_commercial_email_without_an_unsubscribe_is_blocked():
    """CASL applies. This is illegal in Canada, not merely rude."""
    facts = _facts()
    pieces = content_mod.build_ecosystem(facts, launch_on=date(2026, 9, 24))
    email = next(p for p in pieces if p.channel == "email")
    email.body = email.body.replace("Unsubscribe any time — one click, no questions.", "")
    problems = content_mod.check_ecosystem(pieces, facts)
    assert any("CASL" in p for p in problems), problems


def test_a_crochet_along_is_only_proposed_for_something_long_enough_to_need_one():
    big = content_mod.build_ecosystem(_facts(maker_hours=(30.0, 60.0)),
                                      launch_on=date(2026, 9, 24))
    small = content_mod.build_ecosystem(_facts(maker_hours=(1.0, 3.0)),
                                        launch_on=date(2026, 9, 24))
    assert any(p.channel == "cal" for p in big)
    assert not any(p.channel == "cal" for p in small)


def test_the_free_teaser_must_be_a_real_validated_motif():
    pieces = content_mod.build_ecosystem(_facts(), launch_on=date(2026, 9, 24))
    teaser = next(p for p in pieces if p.channel == "teaser")
    assert teaser.detail["must_be_validated"] is True
    teaser.detail["must_be_validated"] = False
    problems = content_mod.check_ecosystem(pieces, _facts())
    assert any("TEASER_UNVALIDATED" in p for p in problems), problems


# ---- portfolio -------------------------------------------------------------


def test_a_catalogue_nobody_has_seen_is_not_underperforming():
    """The most expensive mistake this classifier could make."""
    verdict = pf.review_portfolio([pf.SkuMetrics(f"p{i}") for i in range(11)])
    assert not verdict.evidence_available
    assert all(c.label == pf.NO_EVIDENCE for c in verdict.classifications)
    assert any("distribution, not product changes" in a for a in verdict.actions)


def test_high_impressions_and_low_clicks_is_a_listing_problem():
    c = pf.classify(pf.SkuMetrics("x", impressions=5000, clicks=20, orders=1))
    assert c.label == pf.SEO_PROBLEM
    assert "shown and not chosen" in c.reason
    assert any("tag slots" in i for i in c.interventions)


def test_high_clicks_and_low_conversion_is_an_offer_problem():
    c = pf.classify(pf.SkuMetrics("x", impressions=5000, clicks=200, orders=1))
    assert c.label == pf.CONVERSION_PROBLEM
    assert any("frames 2-4" in i for i in c.interventions)


def test_a_long_lived_conversion_problem_becomes_rework_not_another_listing_tweak():
    c = pf.classify(pf.SkuMetrics("x", impressions=5000, clicks=200, orders=1, days_live=200))
    assert c.label == pf.REWORK
    assert "the product itself is now the variable" in c.reason


def test_high_sales_with_high_support_is_a_quality_emergency():
    c = pf.classify(pf.SkuMetrics("x", impressions=9000, clicks=400, orders=40,
                                  support_cases=6))
    assert c.label == pf.QUALITY_PROBLEM
    assert c.interventions[0].startswith("stop selling it")


def test_an_open_p1_outranks_every_commercial_signal():
    great = pf.SkuMetrics("x", impressions=20000, clicks=900, orders=200,
                          open_p1_incidents=1)
    assert pf.classify(great).label == pf.QUALITY_PROBLEM


def test_a_closed_seasonal_window_is_not_a_product_failure():
    c = pf.classify(pf.SkuMetrics("x", impressions=5000, clicks=150, orders=2,
                                  season="Christmas", window_open=False))
    assert c.label == pf.SEASONAL
    assert any("product problem" in i for i in c.interventions), c.interventions


def test_a_winner_is_classified_as_something_to_build_from():
    c = pf.classify(pf.SkuMetrics("x", impressions=8000, clicks=250, orders=30))
    assert c.label == pf.STAR
    assert any("matching products" in i for i in c.interventions)


def test_retirement_comes_after_the_ladder_not_instead_of_it():
    c = pf.classify(pf.SkuMetrics("x", impressions=5000, clicks=120, orders=2, days_live=200))
    assert c.label in (pf.RETIRE, pf.REWORK)
    if c.label == pf.RETIRE:
        assert "interventions have been tried" in c.reason


def test_every_class_has_an_intervention_ladder():
    for label in (pf.STAR, pf.PROMISING, pf.SEO_PROBLEM, pf.CONVERSION_PROBLEM,
                  pf.QUALITY_PROBLEM, pf.SEASONAL, pf.REWORK, pf.RETIRE, pf.NO_EVIDENCE):
        assert pf.LADDERS[label], label
        assert len(pf.LADDERS[label]) >= 2


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
