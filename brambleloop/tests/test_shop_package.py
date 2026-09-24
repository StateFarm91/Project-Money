"""The shop's customer-facing package: one licence, one disclosure, one set of answers.

Requirement 40's failure had already happened in this repository before a single sale. The
licence a buyer would read existed three times -- `commerce.terms` said finished items may be
sold by individual makers and small businesses, `brand.storefront` said "sell the items you
make from it" with no limit, and `commerce.seo`'s description block said a third thing. Three
answers to the most-asked question in the craft-pattern market, each written at a different
time by a different part of the system, and none of them wrong on its own.

What these tests defend:

- **The shop shows the licence that was decided.** The storefront no longer holds prose; it
  renders from the decision. This is asserted rather than trusted, because the failure mode
  is a future edit that types a friendlier sentence into one surface.
- **A primary claim was read, not merely cited.** Etsy's help centre refuses automated
  readers, so several claims here are secondary and say so. A citation is not a reading, and
  the difference is what keeps a stale assumption distinguishable from a checked one.
- **The things that need a lawyer say so** instead of being answered confidently by software.
- **The About is checked on substance.** Length is a proxy that four hundred characters of
  atmosphere passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.brand import storefront  # noqa: E402
from brambleloop.commerce import shop_package as P  # noqa: E402
from brambleloop.commerce import terms as T  # noqa: E402
from brambleloop.gates import platform_policy  # noqa: E402


# ---- the evidence ----------------------------------------------------------


def test_a_primary_claim_must_have_been_read_and_not_merely_cited():
    """Etsy's help centre refuses automated readers. A URL is not evidence anybody looked."""
    try:
        P.Claim("wishful", "Etsy says so", P.PRIMARY, "etsy_help", "we act on it")
    except P.PackageRefused as e:
        assert "never fetched" in str(e)
    else:
        raise AssertionError("a primary claim rested on a source nobody could read")

    # The same claim, labelled honestly, is accepted -- which is the point of having the
    # label rather than a rule against citing unreadable pages.
    honest = P.Claim("honest", "Etsy says so", P.SECONDARY, "etsy_help", "we act on it")
    assert honest.basis == P.SECONDARY


def test_every_primary_claim_keeps_the_sentence_it_rests_on():
    primary = [c for c in P.CLAIMS if c.basis == P.PRIMARY]
    assert primary, "nothing here was read from the document that governs it"
    for claim in primary:
        source = P.SOURCES[claim.source_key]
        assert source.fetched, claim.key
        assert source.quote.strip(), claim.key
    for claim in P.CLAIMS:
        assert claim.consequence.strip(), (
            f"{claim.key} is a fact with no consequence, which is a fact in a document "
            f"nobody reads")


def test_the_claims_that_need_a_lawyer_say_so_rather_than_being_answered():
    flagged = {c.key for c in P.CLAIMS if c.needs_professional_advice}
    assert "pattern_copyright_not_the_finished_object" in flagged
    assert "etsy_collects_canadian_tax" in flagged
    assert "eu_withdrawal_waived_on_consent" in flagged
    # And the terms themselves stay unenforceable until somebody qualified has looked.
    assert T.BRAMBLELOOP_TERMS.enforceable is False
    assert any(d["key"] == "legal_review_of_terms" for d in P.owner_decisions())


def test_the_tax_position_is_a_threshold_somebody_watches_not_a_guess():
    claim = P.CLAIMS_BY_KEY["cra_small_supplier_threshold"]
    assert claim.basis == P.PRIMARY
    assert "30,000" in claim.claim and "29 days" in claim.claim
    assert "canada.ca" in P.SOURCES[claim.source_key].url


# ---- one licence, everywhere ----------------------------------------------


def test_the_shop_shows_the_licence_that_was_decided():
    """The storefront used to say something more generous than the decision. It does not."""
    decided = T.BRAMBLELOOP_TERMS.sentence(T.FINISHED_ITEM_SALE)
    assert decided in storefront.POLICIES["licence"], storefront.POLICIES["licence"]
    assert storefront.POLICIES["licence"] == P.policies()["licence"]
    # The old wording granted an unlimited right to sell finished items. If it comes back,
    # it comes back here.
    assert "sell the items you make from it" not in storefront.POLICIES["licence"]


def test_the_three_surfaces_agree_on_all_five_axes():
    verdict = P.surface_consistency(
        pdf_text=T.render(T.BRAMBLELOOP_TERMS, "pdf"),
        listing_text=P.policies()["licence"],
        faq_text=P.faq_text())
    assert verdict["consistent"] is True, verdict["divergences"]


def test_a_surface_written_by_hand_is_caught():
    """The check has to fail on a divergence, or it is decoration."""
    verdict = P.surface_consistency(
        pdf_text=T.render(T.BRAMBLELOOP_TERMS, "pdf"),
        listing_text="Use it for yourself and sell whatever you make.",
        faq_text=P.faq_text())
    assert verdict["consistent"] is False
    axes = {d["axis"] for d in verdict["divergences"]}
    assert T.FINISHED_ITEM_SALE in axes, verdict["divergences"]


def test_the_finished_item_question_is_first_and_answered_in_the_decided_words():
    entries = P.faq()
    assert entries[0]["key"] == "sell_what_i_make"
    assert "sell" in entries[0]["question"].lower()
    assert T.BRAMBLELOOP_TERMS.sentence(T.FINISHED_ITEM_SALE) in entries[0]["answer"]
    assert T.BRAMBLELOOP_TERMS.sentence(T.REDISTRIBUTION) in entries[0]["answer"], (
        "the permission and its limit belong in the same answer; separating them is how a "
        "buyer reads one and not the other")
    assert len(entries) == len(P.FAQ_ORDER)


# ---- the policies a digital shop is judged on -----------------------------


def test_the_returns_policy_says_the_word_before_the_sale():
    returns = P.policies()["returns"].lower()
    assert "cannot be returned" in returns
    # Etsy's own position, and the reason the shop cannot simply choose to be generous.
    assert "does not allow" in returns
    # A refusal with no remedy is a refusal. These are the two that cost nothing and work.
    assert "correct the pattern" in returns
    assert P.CLAIMS_BY_KEY["etsy_goodwill_refund_remains"].basis == P.PRIMARY


def test_the_delivery_policy_answers_when_it_arrives():
    delivery = P.policies()["delivery"].lower()
    assert "digital" in delivery and "no processing time" in delivery
    assert "nothing is posted" in delivery
    assert "will not open" in delivery, "the failure case is the policy's real job"


def test_the_ai_disclosure_is_the_gates_disclosure_and_not_a_friendlier_one():
    disclosure = P.ai_disclosure()
    for key in ("digital_download", "ai_assisted_design", "deterministic_render"):
        assert platform_policy.DISCLOSURES[key] in disclosure, key
    # And the FAQ answers the question with the same sentences rather than its own.
    answer = {e["key"]: e["answer"] for e in P.faq()}["was_ai_used"]
    assert answer == disclosure


def test_the_ai_disclosure_is_a_storefront_policy_section():
    """Not one of Etsy's original sections, which is exactly why a hand-kept list loses it."""
    assert "ai" in P.POLICY_SECTIONS
    store = storefront.build_storefront()
    assert store.policies["ai"].strip()
    assert store.ok, store.problems


def test_a_missing_policy_section_is_caught_by_the_storefront_check():
    store = storefront.build_storefront()
    store.policies["ai"] = ""
    problems = storefront.check_storefront(store)
    assert any("STORE_POLICY_MISSING: ai" in p for p in problems), problems


# ---- the About -------------------------------------------------------------


def test_the_about_is_checked_on_substance_rather_than_length():
    assert P.check_about(storefront.ABOUT) == []
    atmospheric = ("We are a small studio in Canada. We love yarn and we love the quiet "
                   "hours of the evening. " * 6)
    assert len(atmospheric) > storefront.ABOUT_MIN
    problems = P.check_about(atmospheric)
    assert any("HOW_IT_IS_MADE" in p for p in problems), problems
    assert any("HOW_AI_IS_USED" in p for p in problems), problems


# ---- the package as a whole ------------------------------------------------


def test_the_package_has_nothing_wrong_with_it_and_says_what_it_measured():
    assert P.check_package() == []
    described = P.describe()
    assert described["problems"] == []
    assert set(described["policies"]) == set(P.POLICY_SECTIONS)
    assert described["researched_on"] == P.RESEARCHED_ON
    assert described["needs_professional_advice"], (
        "a package with nothing flagged for a lawyer has answered legal questions itself")


def test_a_licence_that_stops_answering_the_craft_fair_question_is_caught():
    silent = T.Terms(choices={**T.BRAMBLELOOP_TERMS.choices,
                              T.FINISHED_ITEM_SALE: "not_permitted"},
                     decided_on=T.BRAMBLELOOP_TERMS.decided_on, decided_by="test")
    # Still consistent, because it is still one decision rendered everywhere -- which is the
    # property #40 asks for. What changes is the answer, and every surface changes with it.
    assert P.check_package(silent) == []
    assert "may not be sold" in P.faq(silent)[0]["answer"]


def test_the_api_can_write_five_fields_and_a_person_types_the_rest():
    """Preparing the rest as an integration would be preparing something that cannot exist."""
    text = P.shop_text()
    assert set(text) == set(P.SHOP_TEXT_FIELDS)
    assert text["digital_sale_message"].strip(), (
        "the message that reaches every customer at the moment they are reading")
    # The half with a write endpoint must say what the half a person typed says.
    assert T.BRAMBLELOOP_TERMS.sentence(T.FINISHED_ITEM_SALE) in text["policy_additional"]
    where = dict(P.MANUAL_ONLY)
    assert "shop_policies_returns" in where and "Shop Manager" in where["about_story"]
    assert P.CLAIMS_BY_KEY["most_of_the_shop_is_typed_by_a_person"].basis == P.PRIMARY


def test_the_research_says_how_old_it_is():
    state = P.state()
    assert state["researched_on"] == P.RESEARCHED_ON
    assert state["primary"] + state["secondary"] + state["inferred"] == state["claims"]
    assert state["stale"] is False, "the sources were read too long ago to be current"


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
