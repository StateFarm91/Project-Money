"""Canada is not the world, and the shop this company learns from is not Canadian.

Requirement 268. Where the platform's data and policy permit, distinguish Canada, the United
States and other meaningful buyer markets for terminology, holidays, timing and pricing --
and the requirement's own closing instruction, which is the one that bites: *do not assume
Canadian search behavior represents Etsy globally.*

It bites in an unexpected direction here. This company is Canadian, its calendar is Canadian,
and CASL governs its email -- but the benchmark it learns its language from is
MJsOffTheHookDesigns, which is a United States shop. So the observed term frequencies are not
Canadian search behaviour being mistaken for global behaviour; they are **American** search
behaviour being mistaken for ours. The error the requirement warns about is present and
pointing the other way, and a module that only guarded the stated direction would miss it.

The two differences that are real for a digital pattern:

**Terminology.** US and UK crochet terms name different stitches with the same words -- a
US double crochet is a UK treble, and a pattern that does not say which it uses produces
fabric of the wrong gauge for half its buyers. Canada follows US terms. The writer already
emits both; what was missing is the market lens that says which buyer needs which.

**Holidays.** Canadian Thanksgiving is the second Monday of October and American Thanksgiving
is the fourth Thursday of November: six weeks apart, different shopping windows, and a
seasonal product merchandised to one is merchandised away from the other. The calendar
carries the Canadian date, which is correct for this company and incomplete for its market.

Timing and shipping do not differ: a digital file arrives the same day everywhere, which is
the one cross-border advantage this business has and is worth stating rather than assuming.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CA, US, OTHER = "CA", "US", "other"


@dataclass(frozen=True)
class Market:
    key: str
    what: str
    crochet_terms: str
    currency: str
    notes: str


MARKETS: tuple[Market, ...] = (
    Market(CA, "Canada: where this company is, banks and is regulated",
           "US", "CAD",
           "CASL governs commercial email here, and the seasonal calendar this system "
           "carries is this market's"),
    Market(US, "the United States: the largest Etsy buyer market, and the benchmark's own",
           "US", "USD",
           "the shop this company learns its language from sells here, so observed term "
           "frequencies describe this market rather than ours"),
    Market(OTHER, "everywhere else, including the UK and Australia",
           "UK", "mixed",
           "UK terms name different stitches with the same words, so a pattern that does "
           "not say which it uses makes the wrong fabric for these buyers"),
)

MARKET_BY_KEY: dict[str, Market] = {m.key: m for m in MARKETS}

# Where two markets put the same holiday. Only the ones that actually differ are listed; a
# table repeating the dates that agree would hide the two that do not.
HOLIDAYS_THAT_DIFFER: dict[str, dict[str, str]] = {
    "Thanksgiving": {
        CA: "the second Monday of October",
        US: "the fourth Thursday of November",
        "why_it_matters": ("six weeks apart, with different shopping windows. A product "
                           "merchandised to one is merchandised away from the other, and "
                           "the calendar this system carries holds the Canadian date"),
    },
    "Mother's Day": {
        CA: "the second Sunday of May",
        US: "the second Sunday of May",
        OTHER: "the fourth Sunday of Lent in the UK, which is usually March",
        "why_it_matters": ("Canada and the United States agree and the UK does not, by "
                           "roughly two months. A single Mother's Day launch date is right "
                           "for two markets and late for the third"),
    },
}


class MarketRefused(ValueError):
    """A claim about a market this company has no evidence for."""


def terminology_for(market: str) -> dict:
    """Which crochet terms a buyer in this market expects, and what happens if we guess.

    Not a preference. A US double crochet is a UK treble; the same words name different
    stitches, so a pattern that does not state its terminology produces fabric of the wrong
    gauge for half its buyers, and they will say the pattern is wrong.
    """
    entry = MARKET_BY_KEY.get(market)
    if entry is None:
        raise MarketRefused(f"{market!r} is not a market: {sorted(MARKET_BY_KEY)}")
    return {
        "market": entry.key,
        "terms": entry.crochet_terms,
        "why": ("the same words name different stitches in US and UK terms -- a US double "
                "crochet is a UK treble -- so a pattern that does not state which it uses "
                "makes the wrong fabric for the buyers who read it the other way"),
        "both_required": True,
        "note": ("the writer emits both terminologies already; what this adds is which "
                 "buyer needs which, so a listing can say so rather than leaving it to be "
                 "discovered at row forty"),
    }


def holiday_split(event: str) -> dict:
    """Whether this occasion is on the same day in every market this company sells to."""
    entry = HOLIDAYS_THAT_DIFFER.get(event.split(" (")[0])
    if entry is None:
        return {"event": event, "differs": False,
                "why": ("this occasion falls on the same date in the markets this company "
                        "sells to, so one launch date serves all of them")}
    return {"event": event, "differs": True,
            "dates": {k: v for k, v in entry.items() if k != "why_it_matters"},
            "why": entry["why_it_matters"]}


def whose_language_is_this(db, *, benchmark_key: str = "") -> dict:
    """Which market the observed term frequencies actually describe.

    The requirement says not to assume Canadian behaviour is global. The error present here
    points the other way and is easier to miss: the benchmark is a United States shop, so
    every term frequency this system has measured is American, and reading it as Canadian --
    or as global -- is the same mistake with the countries swapped.
    """
    from sqlalchemy import func, select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        observed = s.scalar(select(func.count(BenchmarkListing.id)).where(
            BenchmarkListing.benchmark_key == benchmark_key)) or 0

    return {
        "benchmark": benchmark_key,
        "listings_observed": observed,
        "describes_market": US,
        "measurable": bool(observed),
        "why": (f"{observed} listings observed, all from a United States shop. Term "
                f"frequencies drawn from them describe how that market is sold to, not how "
                f"Canadian buyers search and not how Etsy behaves globally"
                if observed else
                "no listing has been observed, so there is no language to attribute to any "
                "market"),
        "what_would_fix_it": ("a benchmark in another market, which is an owner decision "
                              "about which shops to observe rather than a capability"),
        "not_an_argument_to_ignore_it": (
            "American search behaviour is still the largest Etsy buyer market's, and this "
            "company sells digital files across borders. The finding is that it is labelled "
            "correctly, not that it is worthless"),
    }


def lens(db, *, today: date | None = None, benchmark_key: str = "") -> dict:
    """The cross-border picture: language, holidays, currency and what does not differ."""
    from ..finance.currency import ASSUMED_USD_PER_CAD, REPORTING_CURRENCY

    return {
        "as_of": (today or date.today()).isoformat(),
        "markets": [
            {"market": m.key, "what": m.what, "crochet_terms": m.crochet_terms,
             "currency": m.currency, "notes": m.notes} for m in MARKETS],
        "language": whose_language_is_this(db, benchmark_key=benchmark_key),
        "holidays_that_differ": {
            event: holiday_split(event) for event in HOLIDAYS_THAT_DIFFER},
        "currency": {"reporting": REPORTING_CURRENCY,
                     "assumed_usd_per_cad": ASSUMED_USD_PER_CAD,
                     "handled_by": "finance/currency.py (#269)"},
        "does_not_differ": {
            "delivery": ("a digital file arrives the same day everywhere. That is the one "
                         "cross-border advantage this business has, and it is worth saying "
                         "rather than assuming"),
        },
    }
