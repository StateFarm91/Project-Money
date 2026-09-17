"""Pricing Intelligence, Search Domination and Thumbnail Warfare (sections 7, 8, 9).

These three departments share one failure mode, which is why they share a test file: each of
them is easy to build as something that always returns a confident answer, and each of them is
only useful if it refuses when the evidence is not there. A price test read at fifty visitors,
a hero ranked on invented CTR, or a tag set covering head terms a new shop cannot place for
are all worse than no system at all, because they produce decisions that feel earned.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from brambleloop.commerce import paid_media as pm  # noqa: E402
from brambleloop.commerce import pricing_intel as pi  # noqa: E402
from brambleloop.commerce import search, thumbnail  # noqa: E402
from brambleloop.commerce.pricing import DeceptivePricing  # noqa: E402


# ---- market price scanner --------------------------------------------------


def test_the_scanner_reads_the_shelf_from_dated_observations():
    band = pi.scan_band(pi.observations_from_competitors(), "mosaic_blanket")
    assert band.observations >= 6
    assert 0 < band.low_cad <= band.median_cad <= band.high_cad
    assert band.high_cad < 20.0, "the observed shelf does not reach CA$20"


def test_a_shop_with_no_observed_price_is_skipped_not_counted_as_zero():
    """A placeholder averaged into a band looks like data, which is worse than a small sample."""
    obs = pi.observations_from_competitors()
    assert all(o.price_cad > 0 for o in obs)
    assert not any(o.shop == "IvyLoop" for o in obs), "an unobserved shop entered the band"


def test_the_scanner_measures_the_discount_theatre_without_copying_it():
    band = pi.scan_band(pi.observations_from_competitors(), "mosaic_blanket")
    assert band.discount_prevalence > 0
    assert any("do not match that" in n for n in band.notes), band.notes


def test_an_empty_shelf_produces_a_refusal_not_a_number():
    band = pi.scan_band([], "nothing")
    assert band.observations == 0
    assert any("empty shelf" in n for n in band.notes)


# ---- revenue optimizer -----------------------------------------------------


def test_optimisation_is_on_contribution_per_visitor_not_gross():
    out = pi.optimise_price(candidates=[6.0, 9.99, 12.5, 16.0],
                            reference_price_cad=11.99, reference_conversion=0.03)
    assert "contribution per visitor" in out["basis"]
    assert out["is_estimate"] is True, "a model must not present itself as a measurement"
    assert len(out["curve"]) == 4
    best = max(out["curve"], key=lambda v: v["contribution_per_visitor_cad"])
    assert best["price_cad"] == out["recommended_price_cad"]


def test_a_higher_price_does_not_automatically_win():
    """Gross revenue rises with price long after contribution per visitor stops rising."""
    cheap = pi.contribution_per_visitor(6.0, pi.expected_conversion(
        6.0, reference_price_cad=11.99, reference_conversion=0.03))
    dear = pi.contribution_per_visitor(30.0, pi.expected_conversion(
        30.0, reference_price_cad=11.99, reference_conversion=0.03))
    assert cheap.contribution_per_visitor_cad > dear.contribution_per_visitor_cad


def test_fees_are_deducted_before_anything_is_compared():
    econ = pi.contribution_per_visitor(12.5, 0.03)
    assert econ.net_per_sale_cad < 12.5
    assert abs(econ.contribution_per_visitor_cad - econ.net_per_sale_cad * 0.03) < 1e-9


# ---- bundle economist ------------------------------------------------------


def test_a_bundle_states_the_attach_rate_it_has_to_earn():
    v = pi.price_bundle([12.5, 5.5, 6.5])
    assert v.saving_pct >= pi.MIN_BUNDLE_SAVING_PCT
    assert 0 < v.breakeven_attach_rate < 2
    assert any("pays for itself" in r for r in v.reasons), v.reasons


def test_a_token_saving_is_not_a_bundle():
    """Section 9 requires obvious customer value, and 6% changes nobody's decision."""
    try:
        pi.price_bundle([12.5, 5.5, 6.5], target_saving_pct=0.06)
    except DeceptivePricing as e:
        assert "rounding error" in str(e)
    else:
        raise AssertionError("a 6% 'bundle' was accepted")


def test_a_bundle_needs_at_least_two_real_members():
    try:
        pi.price_bundle([12.5])
    except DeceptivePricing:
        pass
    else:
        raise AssertionError("a one-item bundle was accepted")


# ---- price experiments -----------------------------------------------------


def test_the_stopping_rule_is_fixed_before_the_test_runs():
    d = pi.design_price_experiment("x", control_cad=12.5, variant_cad=9.99)
    assert "Do not stop early" in d.stop_rule
    assert d.min_observations >= pi.MIN_OBSERVATIONS_PER_ARM
    assert d.max_loss_cad > 0


def test_an_unmeasurable_price_difference_is_refused_at_design_time():
    try:
        pi.design_price_experiment("x", control_cad=12.50, variant_cad=12.90)
    except ValueError as e:
        assert "unmeasurable" in str(e)
    else:
        raise AssertionError("a 3% price difference was accepted as a test")


def test_a_thin_experiment_is_not_decided():
    d = pi.design_price_experiment("x", control_cad=12.5, variant_cad=9.99)
    r = pi.read_experiment(d, {"control": {"visitors": 60, "orders": 2},
                               "variant": {"visitors": 55, "orders": 4}})
    assert r.decided is False and r.winner is None
    assert "noise" in r.reason


def test_a_well_powered_experiment_is_decided_on_contribution():
    d = pi.design_price_experiment("x", control_cad=12.5, variant_cad=9.99)
    r = pi.read_experiment(d, {"control": {"visitors": 4000, "orders": 100},
                               "variant": {"visitors": 4000, "orders": 130}})
    assert r.decided is True and r.winner in ("control", "variant")
    assert "contribution per visitor" in r.reason


def test_a_losing_variant_is_stopped_at_the_loss_cap():
    d = pi.design_price_experiment("x", control_cad=14.0, variant_cad=6.0, max_loss_cad=5.0)
    r = pi.read_experiment(d, {"control": {"visitors": 3000, "orders": 90},
                               "variant": {"visitors": 3000, "orders": 60}})
    assert r.decided and r.winner == "control"
    assert "loss cap" in r.reason


# ---- promotions ------------------------------------------------------------


def test_a_permanent_sale_is_not_a_promotion():
    problems = search and pi.check_promotion("launch_window", price_cad=9.99,
                                             was_price_cad=None, ever_charged=True,
                                             duration_days=365)
    assert any("TOO_LONG" in p for p in problems), problems


def test_a_reference_price_never_charged_is_refused():
    problems = pi.check_promotion("launch_window", price_cad=9.99, was_price_cad=23.30,
                                  ever_charged=False, duration_days=7)
    assert any("FAKE_REFERENCE" in p for p in problems), problems


def test_a_genuine_bounded_promotion_passes():
    assert pi.check_promotion("launch_window", price_cad=9.99, was_price_cad=12.50,
                              ever_charged=True, duration_days=7) == []


# ---- search domination -----------------------------------------------------


def test_head_terms_are_marked_unreachable_for_a_shop_with_no_history():
    queries = search.build_query_set("mosaic_blanket", ["nordic", "forest"], "Christmas",
                                     ["mosaic"])
    head = next(q for q in queries if q.phrase == "mosaic blanket pattern")
    assert head.reachable is False, "a new shop is not placing for the head term"
    assert any(q.reachable for q in queries), "nothing is reachable at all"


def test_coverage_is_scored_against_what_we_can_reach():
    queries = search.build_query_set("basket", ["market"], None)
    tags = search.choose_tags(queries)
    report = search.score_coverage(queries, title="Market Basket Trio | Crochet Pattern PDF",
                                   tags=tags, description="a basket pattern")
    assert report.total_reachable_value > 0
    assert 0 < report.share <= 1.0
    assert report.reachable <= report.queries


def test_tags_fit_the_platform_and_are_still_phrases():
    for category, motifs, season, tech in (
            ("mosaic_blanket", ["nordic", "forest"], "Christmas", ["mosaic"]),
            ("ornament", ["nordic", "star"], "Christmas", ["mosaic"]),
            ("basket", ["market"], None, None)):
        tags = search.choose_tags(search.build_query_set(category, motifs, season, tech))
        assert len(tags) <= search.TAG_SLOTS
        for t in tags:
            assert len(t) <= search.TAG_MAX_CHARS, t
            assert len(t.split()) >= 2, f"single-word tag wastes a slot: {t!r}"
            assert t.split()[-1] not in search._TRAILING_STOPWORDS, t


def test_the_tag_set_is_not_one_concept_restated():
    tags = search.choose_tags(search.build_query_set(
        "mosaic_blanket", ["nordic", "forest"], "Christmas", ["mosaic"]))
    import collections

    counts = collections.Counter(w for t in tags for w in t.split())
    assert counts.most_common(1)[0][1] <= 4, counts.most_common(3)
    for a in tags:
        for b in tags:
            if a is not b:
                assert not set(a.split()) <= set(b.split()), f"{a!r} is contained in {b!r}"


def test_a_technique_the_pattern_does_not_use_is_never_tagged():
    """Ranking for something we are not is a bounce, not a win."""
    tags = search.choose_tags(search.build_query_set("basket", ["market"], None))
    assert not any("mosaic" in t for t in tags), tags
    mosaic = search.choose_tags(search.build_query_set(
        "mosaic_blanket", ["nordic"], None, ["mosaic"]))
    assert any("mosaic" in t for t in mosaic)


def test_a_title_never_stutters_its_own_category():
    """"Pet Snuggle Mat | ... | Pet Pet | ..." shipped to production before this guard."""
    from brambleloop.commerce.seo import build_title

    title = build_title("Pet Snuggle Mat", "pet", ["pet"], None, 1)
    assert "Pet Pet" not in title, title
    for case in (("Market Basket Trio", "basket", ["market"]),
                 ("Hexagon Coaster Set", "coaster", ["hexie"]),
                 ("Heirloom Cable Throw", "blanket", ["heirloom"])):
        t = build_title(case[0], case[1], case[2], None, 1)
        words = [w.strip().lower() for w in t.split("|")]
        assert len(words) == len(set(words)), f"duplicate segment in {t!r}"
        assert "pattern" in t.lower()


def test_attributes_come_from_pattern_data():
    attrs = search.listing_attributes(category="mosaic_blanket", difficulty="confident beginner",
                                      colors=["cream", "forest"], season="Christmas")
    assert search.check_attributes(attrs) == []
    assert attrs["primary_color"] == "cream"
    assert attrs["includes_chart"] is True


def test_missing_attributes_are_reported():
    problems = search.check_attributes({"digital": True})
    assert any("file_type" in p for p in problems)
    assert any("primary_color" in p for p in problems)


# ---- thumbnail warfare -----------------------------------------------------


def _square(fill, subject=None, box=None) -> Image.Image:
    img = Image.new("RGB", (1200, 1200), fill)
    if subject and box:
        Image.Image.paste(img, Image.new("RGB", (box[2] - box[0], box[3] - box[1]), subject),
                          (box[0], box[1]))
    return img


def test_a_hero_is_judged_at_the_size_a_shopper_sees_it():
    img = _square((250, 246, 235), (36, 74, 58), (120, 120, 1080, 1080))
    v = thumbnail.evaluate_thumbnail(img)
    assert v.measurements["grid_px"] == thumbnail.GRID_PX
    assert v.ok, v.problems


def test_a_low_contrast_hero_is_flagged():
    img = _square((250, 246, 235), (246, 242, 231), (120, 120, 1080, 1080))
    v = thumbnail.evaluate_thumbnail(img)
    assert any("LOW_CONTRAST" in p for p in v.problems), v.problems


def test_a_hero_that_is_mostly_background_is_flagged():
    img = _square((250, 246, 235), (36, 74, 58), (540, 540, 660, 660))
    v = thumbnail.evaluate_thumbnail(img)
    assert any("SUBJECT_TOO_SMALL" in p for p in v.problems), v.problems


def test_coverage_is_the_subjects_footprint_not_its_dark_pixels():
    """A two-colour crochet fabric is half cream, and cream is also the background.

    Counting non-background pixels scored a well-composed hero at 9% and blocked six products
    for a problem none of them had. The measurement is the object's footprint.
    """
    striped = Image.new("RGB", (1200, 1200), (250, 246, 235))
    d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(striped)
    for y in range(150, 1050, 40):
        d.rectangle([150, y, 1050, y + 20], fill=(36, 74, 58))
    v = thumbnail.evaluate_thumbnail(striped)
    assert v.measurements["subject_coverage"] > 0.5, v.measurements
    assert v.ok, v.problems


def test_an_elongated_product_is_not_held_to_a_square_products_standard():
    """A table runner cannot fill a square crop however well it is composed."""
    img = _square((250, 246, 235), (36, 74, 58), (100, 520, 1100, 680))
    strict = thumbnail.evaluate_thumbnail(img)
    fair = thumbnail.evaluate_thumbnail(img, subject_aspect=6.0)
    assert any("SUBJECT_TOO_SMALL" in p for p in strict.problems), strict.problems
    assert fair.ok, fair.problems


def test_illegible_thumbnail_text_is_flagged():
    img = _square((250, 246, 235), (36, 74, 58), (120, 120, 1080, 1080))
    v = thumbnail.evaluate_thumbnail(img, text_pt_on_canvas=30, canvas_px=2000)
    assert any("TEXT_ILLEGIBLE" in p for p in v.problems), v.problems


def test_a_grid_of_identical_heroes_scores_low_on_distinctiveness():
    same = [_square((250, 246, 235), (36, 74, 58), (120, 120, 1080, 1080)) for _ in range(3)]
    different = [_square((250, 246, 235), c, (120, 120, 1080, 1080))
                 for c in ((36, 74, 58), (110, 31, 42), (196, 149, 69))]
    assert thumbnail.distinctiveness(same) < 0.01
    assert thumbnail.distinctiveness(different) > thumbnail.distinctiveness(same)


def test_ranking_heroes_without_impressions_is_refused():
    """Section 8 forbids fabricated engagement, including our own metrics."""
    try:
        thumbnail.rank_by_evidence([])
    except thumbnail.NotEnoughEvidence as e:
        assert "invented" in str(e)
    else:
        raise AssertionError("a hero was ranked with no data at all")


def test_ranking_on_thin_impressions_is_refused():
    obs = [thumbnail.VariantObservation("a", 80, 8, 2, 1),
           thumbnail.VariantObservation("b", 90, 4, 1, 0)]
    try:
        thumbnail.rank_by_evidence(obs)
    except thumbnail.NotEnoughEvidence as e:
        assert "noise" in str(e)
    else:
        raise AssertionError("a winner was called at 80 impressions")


def test_a_variant_that_wins_clicks_and_loses_conversions_does_not_win():
    """A hero that over-promises costs more than the clicks are worth."""
    clickbait = thumbnail.VariantObservation("clickbait", 5000, 500, 40, 5)
    honest = thumbnail.VariantObservation("honest", 5000, 250, 60, 30)
    out = thumbnail.rank_by_evidence([clickbait, honest])
    assert out["winner"] == "honest", out["ranking"]


# ---- paid media guard rails ------------------------------------------------


def test_paid_media_is_refused_in_shadow_mode_whatever_the_numbers_say():
    """A cap is not permission. The gate is the phase, not the money."""
    from brambleloop.core.models import Phase

    try:
        pm.authorise_spend(pm.CampaignState("x"), pm.CONSERVATIVE_CAPS, 0.50,
                           phase=Phase.SHADOW, owner_granted=True)
    except pm.PaidMediaNotAuthorised as e:
        assert "the gate is the phase" in str(e)
    else:
        raise AssertionError("an ad spend was authorised in shadow mode")


def test_paid_media_is_refused_without_the_owners_authority():
    from brambleloop.core.models import Phase

    try:
        pm.authorise_spend(pm.CampaignState("x"), pm.CONSERVATIVE_CAPS, 0.50,
                           phase=Phase.PRODUCTION, owner_granted=False)
    except pm.PaidMediaNotAuthorised as e:
        assert "not the owner's consent" in str(e)
    else:
        raise AssertionError("ad spend proceeded without owner authority")


def test_caps_must_nest_or_they_are_not_caps():
    bad = pm.Caps(daily_cad=50.0, campaign_cad=25.0, monthly_cad=60.0,
                  max_test_loss_cad=25.0, max_cac_cad=6.0)
    try:
        bad.validate()
    except ValueError as e:
        assert "not a cap" in str(e)
    else:
        raise AssertionError("a daily cap above the campaign cap validated")


def test_broken_tracking_pauses_before_any_budget_question():
    """A campaign nobody can measure is worse than one that is losing money visibly."""
    d = pm.should_pause(pm.CampaignState("x", tracking_healthy=False), pm.CONSERVATIVE_CAPS)
    assert d.paused
    assert d.reasons[0].startswith("TRACKING_FAILURE")


def test_an_unavailable_listing_pauses_the_campaign():
    d = pm.should_pause(pm.CampaignState("x", listing_available=False),
                        pm.CONSERVATIVE_CAPS)
    assert any(r.startswith("LISTING_UNAVAILABLE") for r in d.reasons), d.reasons


def test_each_cap_pauses_on_its_own():
    caps = pm.CONSERVATIVE_CAPS
    for field, value, code in (("spend_today_cad", caps.daily_cad, "DAILY_CAP"),
                               ("spend_campaign_cad", caps.campaign_cad, "CAMPAIGN_CAP"),
                               ("spend_month_cad", caps.monthly_cad, "MONTHLY_CAP")):
        state = pm.CampaignState("x", **{field: value})
        d = pm.should_pause(state, caps)
        assert any(r.startswith(code) for r in d.reasons), (code, d.reasons)


def test_the_test_loss_cap_stops_a_losing_experiment():
    """Tested against its own caps so the campaign cap does not trip first and mask it."""
    caps = pm.Caps(daily_cad=3.0, campaign_cad=25.0, monthly_cad=60.0,
                   max_test_loss_cad=8.0, max_cac_cad=6.0)
    state = pm.CampaignState("x", spend_campaign_cad=12.0, contribution_cad=2.0,
                             clicks=50, conversions=1)
    d = pm.should_pause(state, caps)
    assert any(r.startswith("TEST_LOSS_CAP") for r in d.reasons), d.reasons
    assert not any(r.startswith("CAMPAIGN_CAP") for r in d.reasons), d.reasons


def test_a_cac_breach_pauses_but_only_once_there_is_data():
    caps = pm.CONSERVATIVE_CAPS
    thin = pm.CampaignState("x", spend_campaign_cad=9.0, clicks=10, conversions=1,
                            contribution_cad=9.0)
    assert not any("CAC_BREACH" in r for r in pm.should_pause(thin, caps).reasons),         "a CAC was judged on ten clicks"

    real = pm.CampaignState("x", spend_campaign_cad=20.0, clicks=400, conversions=2,
                            contribution_cad=20.0)
    assert any("CAC_BREACH" in r for r in pm.should_pause(real, caps).reasons)


def test_a_refund_anomaly_pauses_the_campaign():
    """Buying traffic for a product people return pays to make the problem bigger."""
    state = pm.CampaignState("x", clicks=300, conversions=20, refunds=4,
                             spend_campaign_cad=10.0, contribution_cad=14.0)
    assert any("REFUND_ANOMALY" in r for r in pm.should_pause(state, pm.CONSERVATIVE_CAPS)
               .reasons)


def test_scaling_requires_profitable_evidence_not_a_good_week():
    caps = pm.CONSERVATIVE_CAPS
    lucky = pm.CampaignState("x", spend_campaign_cad=3.0, clicks=250, conversions=3,
                             contribution_cad=9.0)
    allowed, why = pm.may_scale(lucky, caps)
    assert not allowed and "lucky week" in why

    proven = pm.CampaignState("x", spend_campaign_cad=10.0, clicks=300, conversions=20,
                              contribution_cad=18.0)
    allowed, why = pm.may_scale(proven, caps)
    assert allowed, why


def test_the_status_report_says_plainly_that_nothing_is_live():
    out = pm.status(pm.CampaignState("x"), pm.CONSERVATIVE_CAPS)
    assert out["live"] is False
    assert "no ad integration exists" in out["why_not_live"]


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
