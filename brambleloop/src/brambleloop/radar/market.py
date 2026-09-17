"""Market Radar: real observed intelligence, not placeholders (Master Plan sections 4, 5).

Everything in COMPETITORS and OBSERVATIONS was observed from public Etsy listings or the
owner's own screenshots on the dates recorded. Nothing here is invented, and nothing here
copies protected expression -- these are commercial signals (price points, review counts,
formats, cadence), which is exactly what section 4 says competitor research is for.

The most important thing this module models is section 5's distinction between SHOPPING DATE
and MAKING DATE. A throw takes 30-40 hours and a full-size blanket 60+; a maker buying a
Christmas blanket pattern must start in September or October. So the demand peak for a
Christmas blanket is *now*, not December, and a radar that sorts by "days until the holiday"
would be wrong by three months.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

OBSERVED_ON = "2026-09-17"


@dataclass(frozen=True)
class CompetitorProfile:
    """A longitudinal profile of a serious competitor (section 4)."""

    shop: str
    url: str
    positioning: str
    observed_price_band_cad: tuple[float, float]
    discount_pattern: str | None
    format_signals: list[str]
    strength: str
    gap: str
    observed_on: str = OBSERVED_ON


# Seeded by the owner in spec/05_Competitor_and_Market_Seeds.txt, plus signals visible in
# the owner's search screenshots. Review/"bought" counts are Etsy's own public badges.
COMPETITORS: list[CompetitorProfile] = [
    CompetitorProfile(
        shop="HanJanCrochet",
        url="https://www.etsy.com/ca/shop/HanJanCrochet",
        positioning="Premium overlay-mosaic blankets, pattern + video, strong seasonal cadence",
        observed_price_band_cad=(8.47, 11.65),
        discount_pattern="50% off displayed with a countdown timer; regular price ~CA$23.30",
        format_signals=["PATTERN + VIDEO", "PDF", "mosaic overlay", "seasonal collections"],
        strength="'Bestseller in Patterns & Blueprints, 200+ bought in the last week' on the "
                 "fall blanket; 8.4k reviews on the hero listing. Photography is warm, styled "
                 "and consistent across the grid.",
        gap="Charts are images rather than interactive; sizing options are limited to one "
            "finished size per pattern.",
    ),
    CompetitorProfile(
        shop="MJsOffTheHookDesigns",
        url="https://www.etsy.com/ca/shop/MJsOffTheHookDesigns",
        positioning="Seasonal mosaic and colourwork blankets ('Autumn's Charm')",
        observed_price_band_cad=(8.47, 11.64),
        discount_pattern="50% off as a standing display price",
        format_signals=["PATTERN + VIDEO", "mosaic", "stockings", "tree skirts", "baskets"],
        strength="Broad seasonal family: blanket, stocking, basket and tree skirt in one "
                 "visual language, which cross-sells.",
        gap="Family members are sold individually; no obvious bundle at a bundle price.",
    ),
    CompetitorProfile(
        shop="FireflyCrochets",
        url="https://www.etsy.com/ca/shop/FireflyCrochets",
        positioning="Character amigurumi (Christmas moose/reindeer)",
        observed_price_band_cad=(2.75, 8.78),
        discount_pattern="frequent deep discounts on older listings",
        format_signals=["PDF", "amigurumi", "no-sew variants"],
        strength="Low price point drives volume and review accumulation.",
        gap="Amigurumi is Class B/C for validation -- harder for us to guarantee early.",
    ),
    CompetitorProfile(
        shop="LoveandStitchDesigns",
        url="https://www.etsy.com/ca/shop/LoveandStitchDesigns",
        positioning="Everyday garments and striped wearables",
        observed_price_band_cad=(9.90, 14.05),
        discount_pattern="55% off from ~CA$22.00",
        format_signals=["PATTERN + VIDEO", "garments", "recurring human model"],
        strength="A single recurring model across the grid makes the shop read as one brand.",
        gap="Garments are Class C: they need physical testing, which is slow for us at first.",
    ),
    CompetitorProfile(
        shop="IvyLoop",
        url="https://www.etsy.com/ca/shop/IvyLoop",
        positioning="Seeded by owner; profile to be filled on first live scan",
        observed_price_band_cad=(0.0, 0.0),
        discount_pattern=None,
        format_signals=[],
        strength="Not yet observed.",
        gap="Not yet observed.",
    ),
]


# Signals observed across the wider category, with the evidence that supports them.
OBSERVATIONS: dict[str, str] = {
    "price_band": "Crochet patterns cluster at CA$4-12; premium pattern+video sits CA$8.50-14. "
                  "Etsy takes 6.5% transaction + 3% + CA$0.25 processing.",
    "discount_norm": "Near-universal '50-60% off' display pricing with a struck-through "
                     "reference price. Section 9 forbids us running a perpetual fake sale, so "
                     "we price honestly at the real number and compete on trust and quality.",
    "video_is_table_stakes": "The top sellers in mosaic/blankets all advertise 'PATTERN + "
                             "VIDEO'. A pattern without a tutorial reads as lower value.",
    "mosaic_demand": "Overlay mosaic Christmas blankets show heavy favouriting (one listing "
                     "at 4,794 favourites, another at 1,789). Nordic/forest/festive motifs "
                     "recur across shops.",
    "seasonal_families": "Winners ship a family -- blanket, stocking, basket, tree skirt, "
                         "ornament -- in one visual language, but rarely bundle them.",
    "amigurumi_volume": "Amigurumi sells at CA$2.75-8.78 with very high review counts "
                        "(43.2k on one collection), but it is Class B/C to validate.",
    "review_moat": "Category leaders hold 8k-43k reviews. We cannot out-review them; we can "
                   "out-specify them on accuracy, sizing options and chart quality.",
}


# ---- seasonality ---------------------------------------------------------


@dataclass(frozen=True)
class SeasonalEvent:
    name: str
    event_date: date
    typical_make_hours: tuple[float, float]  # (fast maker, slow maker)
    gift_lead_days: int = 7


# Make-time evidence: throw 30-40h, full-size 60+h, baby blanket 3-20h, small decor 1-4h.
SEASONAL_EVENTS: list[SeasonalEvent] = [
    SeasonalEvent("Christmas", date(2026, 12, 25), (30.0, 60.0)),
    SeasonalEvent("Halloween", date(2026, 10, 31), (2.0, 8.0)),
    SeasonalEvent("Thanksgiving (CA)", date(2026, 10, 12), (2.0, 10.0)),
    SeasonalEvent("Valentine's", date(2027, 2, 14), (2.0, 8.0)),
    SeasonalEvent("Easter", date(2027, 4, 4), (2.0, 8.0)),
    SeasonalEvent("Mother's Day", date(2027, 5, 9), (4.0, 15.0)),
]


def shopping_window(event: SeasonalEvent, hours_per_week: float = 7.0) -> tuple[date, date]:
    """When a maker must BUY to finish in time.

    Opens when even a slow maker still has enough weeks; closes when a fast maker no longer
    does. This is the window that actually governs demand, not the date of the holiday.
    """
    slow_days = int(event.typical_make_hours[1] / hours_per_week * 7)
    fast_days = int(event.typical_make_hours[0] / hours_per_week * 7)
    # Browsing starts well before the last possible start date, and the bigger the project
    # the further ahead people plan: nobody researches a 60-hour blanket the week they begin
    # it. A flat buffer would put the Christmas-blanket window a week from now, which the
    # evidence contradicts -- shops are already running Christmas collections in September.
    browse_lead = max(28, slow_days)
    opens = event.event_date - timedelta(days=slow_days + event.gift_lead_days + browse_lead)
    closes = event.event_date - timedelta(days=fast_days + event.gift_lead_days)
    return opens, closes


def seasonal_urgency(event: SeasonalEvent, today: date | None = None) -> float:
    """0-1 urgency. Peaks inside the buying window, decays outside it."""
    today = today or date.today()
    opens, closes = shopping_window(event)
    if today < opens:
        days_early = (opens - today).days
        return max(0.0, 0.35 - days_early / 400.0)
    if today > closes:
        return 0.05  # too late to finish; only impulse/next-year buyers remain
    span = max(1, (closes - opens).days)
    progress = (today - opens).days / span
    # Urgency rises through the window and is highest near the middle-to-late portion.
    return round(min(1.0, 0.6 + 0.4 * progress), 3)


def active_events(today: date | None = None, threshold: float = 0.5) -> list[tuple[SeasonalEvent, float]]:
    today = today or date.today()
    scored = [(e, seasonal_urgency(e, today)) for e in SEASONAL_EVENTS]
    return sorted([x for x in scored if x[1] >= threshold], key=lambda x: -x[1])
