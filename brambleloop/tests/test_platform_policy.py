"""Platform policy, AI disclosure and customer-use terms.

v1.4.3 requirements 35, 39, 40. Three requirements that look like paperwork and are the ones
that close a shop.

The shape they share is that each fails silently and in the future. A policy encoded in code
is true the day it is written; a generated lifestyle image is a compliance problem only once
somebody complains; and terms that were never decided are correct until the first customer
asks the question they actually have. None of the three produces a failing test on the day the
mistake is made, which is why they are mechanical here.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import terms as T  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gates import platform_policy as P  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/policy.sqlite")
    db.create_all()
    return db


def _read_all(db, *, checked_on: str = "", text: str = "policy body") -> None:
    for source in P.POLICY_SOURCES:
        P.record_snapshot(db, source, text=f"{source}: {text}",
                          checked_on=checked_on or date.today().isoformat())


# ---- the freshness watch (#39) --------------------------------------------


def test_never_checked_is_not_the_same_as_unchanged():
    """A watch reporting 'no material changes' from an empty table is confidently wrong."""
    db = _db()
    f = P.freshness(db)
    assert f["all_fresh"] is False
    assert sorted(f["never_checked"]) == sorted(P.POLICY_SOURCES)
    assert f["current"] == [] and f["stale"] == []
    # Every workflow those policies govern is blocked, named individually so the block is
    # actionable rather than total.
    assert "publishing" in f["blocked_workflows"]
    assert "paid_media" in f["blocked_workflows"]


def test_a_stale_reading_blocks_only_the_workflows_its_policy_governs():
    """One 'Etsy policy' blob would block everything or nothing; five sources block precisely."""
    db = _db()
    _read_all(db)
    assert P.freshness(db)["all_fresh"] is True

    old = (date.today() - timedelta(days=P.MAX_AGE_DAYS + 5)).isoformat()
    db2 = _db()
    for source in P.POLICY_SOURCES:
        when = old if source == "advertising_rules" else date.today().isoformat()
        P.record_snapshot(db2, source, text="body", checked_on=when)
    f = P.freshness(db2)
    assert [e["source"] for e in f["stale"]] == ["advertising_rules"]
    assert f["blocked_workflows"] == ["growth", "paid_media"]
    assert "publishing" not in f["blocked_workflows"]


def test_a_material_change_is_a_digest_difference_rather_than_a_judgement():
    """'Does this change matter?' is the judgement somebody makes quickly on a Friday."""
    db = _db()
    first = P.record_snapshot(db, "creativity_standards", text="version one of the rules")
    assert first["first_reading"] is True
    assert first["material_change"] is False

    same = P.record_snapshot(db, "creativity_standards", text="version one of the rules")
    assert same["material_change"] is False

    changed = P.record_snapshot(db, "creativity_standards",
                                text="version one of the rules, plus a new disclosure clause")
    assert changed["material_change"] is True
    assert "creative_assets" in changed["affects"]

    try:
        P.record_snapshot(db, "instagram_rules", text="x")
    except P.PolicyRefused as e:
        assert "not a watched policy" in str(e)
    else:
        raise AssertionError("an unwatched policy source was recorded")


def test_a_new_product_class_cannot_be_enabled_against_a_policy_nobody_has_read():
    """#35. A new class is exactly when the old reading is least likely to cover the case."""
    db = _db()
    try:
        P.check_new_class(db, product_class=P.AI_ASSISTED_DESIGN)
    except P.PolicyRefused as e:
        assert "have not been read within" in str(e)
    else:
        raise AssertionError("a new class was enabled against an unread policy")

    _read_all(db)
    enabled = P.check_new_class(db, product_class=P.AI_ASSISTED_DESIGN,
                                asset_roles=("mood_frame",))
    assert enabled["enabled"] is True
    assert enabled["policy"]["certified_against_current_policy"] is True


def test_the_certificate_stamp_says_which_version_of_etsys_rules_it_was_read_against():
    """POLICY_VERSION answers which version of *our* rules; this answers the other one."""
    db = _db()
    unread = P.policy_stamp(db)
    assert unread["certified_against_current_policy"] is False
    assert len(unread["unread_sources"]) == len(P.POLICY_SOURCES)
    assert "only time anybody wants to re-examine it" in unread["note"]

    _read_all(db)
    stamped = P.policy_stamp(db)
    assert stamped["certified_against_current_policy"] is True
    assert set(stamped["sources"]) == set(P.POLICY_SOURCES)


# ---- the creativity and disclosure gate (#35) -----------------------------


def test_a_generated_image_cannot_do_a_photographs_job_and_a_label_does_not_fix_it():
    """The spec's own sentence, made mechanical.

    Disclosure and misrepresentation are different problems. The label tells a buyer the
    picture is not real; they are looking at it to find out what they are buying.
    """
    for role in ("primary_listing_image", "finished_object_photo", "detail_photo",
                 "scale_reference"):
        result = P.classify(
            product_class=P.SELLER_DESIGNED_DIGITAL,
            assets=[P.AssetClaim("img", role, generated=True, labelled=True)])
        assert result.ok is False, role
        assert "does not exist" in result.problems[0]

    # A deterministic render of our own artefact is a different thing: it *is* what is sold.
    chart = P.classify(
        product_class=P.SELLER_DESIGNED_DIGITAL,
        assets=[P.AssetClaim("chart", "chart_render", generated=True,
                             deterministic_render=True, labelled=True)])
    assert chart.ok is True
    assert P.DISCLOSURES["deterministic_render"] in chart.disclosures


def test_a_permitted_generated_image_must_still_be_labelled():
    unlabelled = P.classify(
        product_class=P.SELLER_DESIGNED_DIGITAL,
        assets=[P.AssetClaim("mood", "mood_frame", generated=True, labelled=False)])
    assert unlabelled.ok is False
    assert "must be labelled where it appears" in unlabelled.problems[0]

    labelled = P.classify(
        product_class=P.SELLER_DESIGNED_DIGITAL,
        assets=[P.AssetClaim("mood", "mood_frame", generated=True, labelled=True)])
    assert labelled.ok is True
    assert P.DISCLOSURES["generated_imagery"] in labelled.disclosures


def test_ai_assisted_design_owes_a_disclosure_and_a_release_with_no_assets_has_skipped_the_gate():
    assisted = P.classify(
        product_class=P.SELLER_DESIGNED_DIGITAL,
        assets=[P.AssetClaim("hero", "primary_listing_image")],
        ai_assisted_design=True)
    assert assisted.ok is True
    assert P.DISCLOSURES["ai_assisted_design"] in assisted.disclosures
    assert P.DISCLOSURES["digital_download"] in assisted.disclosures

    empty = P.classify(product_class=P.SELLER_DESIGNED_DIGITAL, assets=[])
    assert empty.ok is False
    assert "skipped it" in empty.problems[0]


def test_the_gate_states_that_it_is_not_legal_advice_where_somebody_would_read_it():
    described = P.describe()
    assert "conservative reading" in described["not_legal_advice"]
    assert set(described["policy_sources"]) == set(P.POLICY_SOURCES)
    classified = P.classify(product_class=P.SELLER_DESIGNED_DIGITAL,
                            assets=[P.AssetClaim("hero", "primary_listing_image")]).to_dict()
    assert "not_legal_advice" in classified


# ---- customer-use terms (#40) ---------------------------------------------


def test_an_undecided_term_is_refused_rather_than_defaulted():
    """An undecided term is answered for the first time in a support reply, by whoever is on."""
    try:
        T.Terms(choices={T.PDF_USE: "personal_single_user"})
    except T.TermsRefused as e:
        assert "becomes the terms" in str(e)
        assert "finished_item_sale" in str(e)
    else:
        raise AssertionError("a partial set of terms was accepted")

    try:
        T.Terms(choices={**T.BRAMBLELOOP_TERMS.choices,
                         T.FINISHED_ITEM_SALE: "sure, go ahead"})
    except T.TermsRefused as e:
        assert "Options are closed" in str(e)
    else:
        raise AssertionError("free-text terms were accepted")


def test_the_three_surfaces_render_from_one_decision():
    """The PDF, the listing and the FAQ are allowed different headings, not different answers."""
    terms = T.BRAMBLELOOP_TERMS
    pdf, listing, faq = (T.render(terms, s) for s in T.SURFACES)
    assert pdf.startswith("What you may do with this pattern")
    assert faq.startswith("Can I sell what I make?")
    assert T.consistency(pdf, listing, faq)["consistent"] is True

    # One surface written by hand is the only way this drifts, and it is caught.
    drifted = T.consistency(pdf, "Sell as many finished items as you like!", faq)
    assert drifted["consistent"] is False
    axes = {d["axis"] for d in drifted["divergences"]}
    assert T.FINISHED_ITEM_SALE in axes
    assert all(d["surface"] == "listing" for d in drifted["divergences"])


def test_the_terms_answer_the_question_customers_actually_ask():
    """Not 'do not redistribute', which every pattern says. The craft-fair question."""
    terms = T.BRAMBLELOOP_TERMS
    sentence = terms.sentence(T.FINISHED_ITEM_SALE)
    assert "finished items may be sold" in sentence
    assert "not manufactured at scale" in sentence
    for surface in T.SURFACES:
        assert sentence in T.render(terms, surface)


def test_decided_is_not_the_same_as_enforceable():
    """A term nobody reviewed is a promise, not a protection -- which is fine until relied on."""
    terms = T.BRAMBLELOOP_TERMS
    assert terms.enforceable is False
    assert "not yet been through legal review" in T.render(terms, "pdf")

    try:
        T.record_legal_review(terms, reviewed_by="", reviewed_on="2026-10-01", scope="all")
    except T.TermsRefused as e:
        assert "more confident label" in str(e)
    else:
        raise AssertionError("a legal review was recorded with nobody reviewing it")

    reviewed = T.record_legal_review(
        terms, reviewed_by="an Ontario solicitor", reviewed_on="2026-10-01",
        scope="customer-use terms for digital patterns sold to Canadian and US buyers")
    assert reviewed.enforceable is True
    assert "not yet been through legal review" not in T.render(reviewed, "pdf")
    # And the substance is unchanged: a review records that somebody looked, not a rewrite.
    assert reviewed.choices == terms.choices


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
