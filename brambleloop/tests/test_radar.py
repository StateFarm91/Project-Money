"""Market Radar and opportunity-pool tests (Master Plan sections 4, 5, 33).

Two things are being tested here that are easy to get wrong and expensive to get wrong.

The first is the SHOPPING DATE / MAKING DATE distinction. A radar that ranks by "days until
the holiday" would tell us to build Christmas blankets in December, by which time every buyer
who could actually finish one has already bought. These tests pin the arithmetic that stops
that happening.

The second is portfolio composition. Ranking by score alone produces a portfolio of whatever
category happens to score best, which is exactly the single-demand-pattern concentration
section 33 forbids.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.radar.market import (  # noqa: E402
    COMPETITORS, OBSERVATIONS, OBSERVED_ON, SEASONAL_EVENTS, SeasonalEvent,
    active_events, seasonal_urgency, shopping_window,
)
from brambleloop.radar.opportunity import (  # noqa: E402
    CATEGORY_COMPETITION, CATEGORY_DEMAND, MAX_CLASS_C, MAX_PER_CATEGORY, POOL, WEIGHTS,
    ConceptSeed, ready_date, score_concept, score_pool, select_portfolio,
)

TODAY = date(2026, 9, 17)   # the date the competitor observations were taken


def _seed(slug: str) -> ConceptSeed:
    return next(s for s in POOL if s.slug == slug)


# ---- observations are real and attributable -------------------------------


def test_every_competitor_profile_is_dated_and_sourced():
    """Section 4 profiles are evidence. Undated evidence rots silently."""
    assert len(COMPETITORS) >= 5
    for c in COMPETITORS:
        assert c.observed_on == OBSERVED_ON
        assert c.url.startswith("https://www.etsy.com/"), c.url
        assert c.positioning and c.strength and c.gap
        lo, hi = c.observed_price_band_cad
        assert lo <= hi, c.shop


def test_observations_cover_the_signals_pricing_depends_on():
    for key in ("price_band", "discount_norm", "video_is_table_stakes", "review_moat"):
        assert key in OBSERVATIONS and len(OBSERVATIONS[key]) > 40


def test_we_do_not_plan_to_copy_the_discount_theatre():
    """Section 9 forbids deceptive discounting. The observation must say so, not just note it."""
    assert "forbids" in OBSERVATIONS["discount_norm"]


# ---- shopping window vs making date ---------------------------------------


def test_a_christmas_blanket_is_bought_in_autumn_not_in_december():
    """The whole point of section 5. A 60-hour throw cannot be started in December."""
    christmas = next(e for e in SEASONAL_EVENTS if e.name == "Christmas")
    opens, closes = shopping_window(christmas)
    assert opens < date(2026, 9, 17) < closes, (opens, closes)
    assert closes < date(2026, 12, 1), "the window must close well before the holiday"
    assert seasonal_urgency(christmas, TODAY) >= 0.6
    # By December the window is long gone.
    assert seasonal_urgency(christmas, date(2026, 12, 10)) <= 0.1


def test_window_scales_with_the_size_of_the_project():
    """A stocking and a throw share a holiday and not a deadline."""
    throw = SeasonalEvent("Christmas", date(2026, 12, 25), (30.0, 60.0))
    stocking = SeasonalEvent("Christmas", date(2026, 12, 25), (4.0, 9.0))
    assert shopping_window(throw)[0] < shopping_window(stocking)[0]
    assert shopping_window(throw)[1] < shopping_window(stocking)[1]


def test_urgency_decays_before_the_window_and_collapses_after_it():
    e = next(x for x in SEASONAL_EVENTS if x.name == "Christmas")
    opens, closes = shopping_window(e)
    assert seasonal_urgency(e, opens - timedelta(days=200)) < \
        seasonal_urgency(e, opens - timedelta(days=5))
    assert seasonal_urgency(e, closes + timedelta(days=1)) < 0.1


def test_active_events_ranks_by_urgency_not_by_calendar_distance():
    ranked = active_events(TODAY, threshold=0.0)
    names = [e.name for e, _ in ranked]
    assert names[0] in ("Christmas", "Halloween", "Thanksgiving (CA)"), names
    assert "Mother's Day" not in names[:2], "May cannot outrank an open autumn window"
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


# ---- the pool --------------------------------------------------------------


def test_pool_meets_section_33_breadth():
    assert len(POOL) >= 30, f"section 33 requires at least 30 concepts, pool has {len(POOL)}"
    assert len({s.category for s in POOL}) >= 10, "a pool of one category is not a pool"
    assert len({s.slug for s in POOL}) == len(POOL), "duplicate slugs"


def test_pool_is_not_all_blankets():
    """We were told explicitly not to assume blankets are the answer."""
    blanketish = {"mosaic_blanket", "blanket", "graphghan"}
    share = sum(s.category in blanketish for s in POOL) / len(POOL)
    assert share < 0.25, f"blanket-family concepts are {share:.0%} of the pool"


def test_every_concept_has_evidence_and_a_priced_position():
    for s in POOL:
        assert len(s.rationale) > 60, f"{s.slug} has no real rationale"
        assert 3.0 <= s.price_cad <= 30.0, s.slug
        assert s.risk_class in ("A", "B", "C"), s.slug
        assert s.maker_hours[0] <= s.maker_hours[1], s.slug
        assert s.design_hours > 0, s.slug
        assert s.category in CATEGORY_DEMAND and s.category in CATEGORY_COMPETITION, s.category


def test_seasonal_concepts_name_a_real_event():
    known = {e.name for e in SEASONAL_EVENTS}
    for s in POOL:
        if s.season is not None:
            assert s.season in known, f"{s.slug} points at unknown event {s.season!r}"


# ---- scoring ---------------------------------------------------------------


def test_weights_sum_to_one_so_scores_are_comparable():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_score_decomposes_into_its_named_components():
    """An unexplainable score is a score nobody can overrule."""
    c = score_concept(_seed("nordic-forest-mosaic-throw"), TODAY)
    assert set(c.components) == set(WEIGHTS)
    recomputed = sum(WEIGHTS[k] * v for k, v in c.components.items())
    assert abs(recomputed - c.score) < 1e-3
    assert 0.0 <= c.score <= 1.0


def test_scoring_is_deterministic():
    a = [(c.slug, c.score) for c in score_pool(today=TODAY)]
    b = [(c.slug, c.score) for c in score_pool(today=TODAY)]
    assert a == b, "the same pool on the same date must produce the same ranking"


def test_class_c_is_penalised_because_we_cannot_verify_it_yet():
    """Section 33: favour Class A/B while physical calibration data does not exist."""
    tee = score_concept(_seed("boxy-summer-tee"), TODAY)
    assert tee.components["verifiability"] < 0.3
    assert any("physical testing" in n for n in tee.notes)
    # Despite the best price in the pool it must not out-rank verifiable work.
    top = score_pool(today=TODAY)[0]
    assert top.seed.risk_class in ("A", "B")


def test_seasonal_fit_is_judged_at_our_ready_date_not_today():
    seed = _seed("nordic-star-ornaments")
    assert ready_date(seed, TODAY) > TODAY
    scored = score_concept(seed, TODAY)
    # A one-evening make for Christmas is not bought in September, and the score says so.
    assert scored.components["seasonal_fit"] < 0.35
    assert "early" in scored.notes[0]


def test_a_closed_window_is_scored_as_closed():
    scored = score_concept(_seed("autumn-oak-mosaic-throw"), TODAY)
    assert scored.components["seasonal_fit"] <= 0.1
    assert "missed" in scored.notes[0]


def test_an_open_flagship_window_beats_a_distant_one():
    christmas_throw = score_concept(_seed("nordic-forest-mosaic-throw"), TODAY)
    mothers_day = score_concept(_seed("mothers-day-shawlette"), TODAY)
    assert christmas_throw.components["seasonal_fit"] > \
        mothers_day.components["seasonal_fit"]


def test_the_same_concept_rises_as_its_window_approaches():
    seed = _seed("valentine-heart-garland")
    september = score_concept(seed, TODAY).components["seasonal_fit"]
    january = score_concept(seed, date(2027, 1, 20)).components["seasonal_fit"]
    assert january > september, (september, january)


# ---- portfolio -------------------------------------------------------------


def test_portfolio_satisfies_every_section_33_constraint():
    p = select_portfolio(today=TODAY)
    unmet = [k for k, v in p.constraints_met.items() if not v]
    assert not unmet, f"unmet section 33 constraints: {unmet}; reasons={p.reasons}"
    assert p.ok


def test_portfolio_is_between_eight_and_twelve_skus():
    for target in (8, 10, 12):
        p = select_portfolio(target=target, today=TODAY)
        assert 8 <= len(p.selected) <= 12, (target, len(p.selected))
        standalone = [c for c in p.selected if not c.seed.is_bundle]
        assert len(standalone) == target, "the target counts designs, not derived bundles"


def test_a_bundle_is_never_selected_without_the_products_it_bundles():
    """A bundle of patterns we never built is a listing we cannot fulfil."""
    p = select_portfolio(today=TODAY)
    chosen = {c.slug for c in p.selected}
    for c in p.selected:
        if c.seed.is_bundle:
            members = [s for s in POOL if s.family == c.seed.family
                       and not s.is_bundle and s.slug in chosen]
            assert len(members) >= 2, f"{c.slug} bundles {len(members)} selected products"
    assert p.constraints_met["bundles_have_members"]


def test_an_unbacked_bundle_is_held_and_says_so():
    """Squeeze the portfolio until the bundle's family cannot earn two places."""
    family = {s for s in POOL if s.family == "nordic-forest"}
    thin = [s for s in POOL if s not in family or s.slug == "nordic-forest-bundle"]
    p = select_portfolio(score_pool(thin, TODAY), target=8, today=TODAY)
    assert not any(c.seed.is_bundle for c in p.selected)
    assert any("cannot be listed" in r for r in p.reasons), p.reasons


def test_portfolio_is_not_a_single_demand_pattern():
    p = select_portfolio(today=TODAY)
    categories = [c.seed.category for c in p.selected]
    assert len(set(categories)) >= 5, categories
    for cat in set(categories):
        assert categories.count(cat) <= MAX_PER_CATEGORY, cat
    seasons = [c.seed.season for c in p.selected]
    assert seasons.count("Christmas") <= 4, "the portfolio must not be one holiday"


def test_portfolio_caps_unverifiable_products():
    p = select_portfolio(today=TODAY)
    assert sum(c.seed.risk_class == "C" for c in p.selected) <= MAX_CLASS_C


def test_portfolio_carries_a_bundle_ready_family():
    p = select_portfolio(today=TODAY)
    families: dict[str, int] = {}
    for c in p.selected:
        if c.seed.family:
            families[c.seed.family] = families.get(c.seed.family, 0) + 1
    assert any(n >= 2 for n in families.values()), families


def test_portfolio_has_a_flagship_and_fast_movers_and_an_evergreen():
    p = select_portfolio(today=TODAY)
    assert any(c.seed.season and c.seed.maker_hours[1] >= 20 for c in p.selected)
    assert sum(c.seed.price_cad <= 6.5 and c.seed.maker_hours[1] <= 6 for c in p.selected) >= 3
    assert any(c.seed.evergreen for c in p.selected)


def test_rejected_concepts_are_kept_not_discarded():
    """A concept rejected in September may be the right build in January."""
    p = select_portfolio(today=TODAY)
    assert len(p.selected) + len(p.rejected) == len(POOL)
    assert any(c.slug == "valentine-heart-garland" for c in p.rejected)


def test_portfolio_shifts_with_the_calendar():
    september = {c.slug for c in select_portfolio(today=TODAY).selected}
    january = {c.slug for c in select_portfolio(today=date(2027, 1, 20)).selected}
    assert september != january, "a radar that ignores the date is not a radar"


def test_every_selector_decision_is_explained():
    """A portfolio nobody can interrogate is a portfolio nobody can overrule."""
    p = select_portfolio(today=TODAY)
    assert p.reasons, "the selector made no recorded decisions at all"
    for reason in p.reasons:
        assert any(k in reason for k in
                   ("to satisfy", "could not satisfy", "added ", "held ")), reason


# ---- the review cadence ----------------------------------------------------


def test_portfolio_review_reports_drift_without_acting_on_no_evidence():
    """The weekly cadence must produce a dated divergence report, not a dead letter."""
    import tempfile

    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, JobStatus
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import Worker
    from sqlalchemy import select

    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{tmp}/r.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        job = JobQueue(db).enqueue("orchestrator", "portfolio.review",
                                   {"as_of": TODAY.isoformat()})
        w = Worker(db, "reviewer")
        assert w.run_once() is True

        done = JobQueue(db).get(job.id)
        assert done.status == JobStatus.DONE, done.last_error
        assert done.outputs["as_of"] == TODAY.isoformat()
        # Nothing is built yet, so the whole portfolio is missing -- and it must say so.
        assert len(done.outputs["missing"]) >= 8
        assert done.outputs["off_portfolio"] == []
        with db.session() as s:
            actions = {a.action for a in s.scalars(select(AuditLog))}
        assert "portfolio.reviewed" in actions


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
