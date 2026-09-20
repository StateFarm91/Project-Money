"""Internal baselines, one funnel at a time.

Requirement 14. A conversion rate with no segment attached is a number about a shop, and
every decision it is used for is a decision about a listing. The requirement says the
dangerous case outright -- do not compare a CA$6 ornament and a CA$15 blanket as if they
share the same funnel -- and it is dangerous precisely because both numbers are real. An
ornament is an impulse at a price nobody thinks about; a blanket is a project somebody
decides to start. They differ in every stage, and the shop-wide average sits between two
truths and describes neither.

So a baseline here belongs to a cell: a category, a traffic source, a price band and the
maturity of the shop when it was measured. Four axes because those are the four the
requirement names, and each of them moves a funnel on its own.

Three rules make this a benchmark rather than a table of averages.

**A cell with too little in it is not a baseline.** Two listings and a fortnight is the
shape of a baseline and none of its content, and a thin cell is more dangerous than an empty
one because it answers. Below the floor the cell reports that it cannot be read, and the
number is not produced at all rather than produced with a caveat nobody will re-read.

**An unmeasured metric is absent, never zero.** A refund rate of zero on a shop with no
orders is not good performance; there is nothing there. Every metric states what it needs
before it means anything, and a metric whose inputs are missing is reported as missing.

**A comparison across cells is refused by name, with the axes that differ.** Not discouraged
in a docstring: `compare()` returns the refusal and the list, because the whole failure mode
is somebody reading two numbers side by side and being right about the arithmetic.

Nothing in this module has any data yet, and that is not a defect to be smoothed over. This
company has no listings, no impressions and no orders, so every cell is empty and says so.
The floors and refusals run anyway, which is how they are tested before the day they matter.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..intel.pods import POD_KEYS

# Price bands, in CAD, from what the observed market actually charges rather than from round
# numbers: crochet patterns cluster at CA$4-12 and pattern-plus-video sits CA$8.50-14, so the
# boundary that matters most falls inside the cluster rather than at CA$10.
PRICE_BANDS: tuple[tuple[str, float, float], ...] = (
    ("under_6", 0.0, 6.0),
    ("6_to_10", 6.0, 10.0),
    ("10_to_20", 10.0, 20.0),
    ("over_20", 20.0, float("inf")),
)
PRICE_BAND_KEYS: tuple[str, ...] = tuple(b[0] for b in PRICE_BANDS)

# Where the visit came from. A shopper who typed a phrase into Etsy and one who arrived from
# a pin are at different distances from a decision, and averaging them describes neither.
TRAFFIC_SOURCES: tuple[str, ...] = (
    "etsy_search", "etsy_ads", "pinterest", "email", "social", "direct", "referral")

# Shop maturity, defined by things that can be counted rather than by how established the
# shop feels. A new shop converts differently because it is new, and a baseline that forgets
# that reads its own growth as an improvement in its listings.
MATURITY: tuple[str, ...] = ("new", "establishing", "established")
ESTABLISHING_AFTER_ORDERS = 25
ESTABLISHED_AFTER_ORDERS = 250
ESTABLISHED_AFTER_DAYS = 365

# The five funnels the requirement names, and what each needs before it means anything.
METRICS: dict[str, dict] = {
    "impressions_to_click": {"needs": ("impressions", "clicks"), "higher_is_better": True,
                             "why": "whether the thumbnail and title earn the click"},
    "favourite_rate": {"needs": ("clicks", "favourites"), "higher_is_better": True,
                       "why": "whether the page is wanted but not yet bought"},
    "conversion": {"needs": ("clicks", "orders"), "higher_is_better": True,
                   "why": "whether the page closes"},
    "refund_or_support_rate": {"needs": ("orders", "refunds_and_support"),
                               "higher_is_better": False,
                               "why": "what the sale cost after it was made"},
    "contribution_per_visitor": {"needs": ("clicks", "contribution_cad"),
                                 "higher_is_better": True,
                                 "why": "the only one that can be compared to a cost"},
}

# What a cell needs before it is a baseline rather than the shape of one.
MIN_LISTINGS_PER_CELL = 3
MIN_IMPRESSIONS_PER_CELL = 500
MIN_ORDERS_FOR_REFUND_RATE = 20


class BenchmarkRefused(ValueError):
    """A comparison across funnels, or a baseline claimed from too little."""


@dataclass(frozen=True)
class Cell:
    """One funnel. A baseline belongs to one of these and to nothing wider."""

    category: str
    traffic_source: str
    price_band: str
    maturity: str

    def __post_init__(self) -> None:
        for value, allowed, name in ((self.category, POD_KEYS, "category"),
                                     (self.traffic_source, TRAFFIC_SOURCES, "traffic source"),
                                     (self.price_band, PRICE_BAND_KEYS, "price band"),
                                     (self.maturity, MATURITY, "shop maturity")):
            if value not in allowed:
                raise BenchmarkRefused(
                    f"{value!r} is not a {name}: {list(allowed)}. A cell keyed on a typo is "
                    f"a cell nothing ever matches, and it fails by looking empty")

    def key(self) -> str:
        return "|".join((self.category, self.traffic_source, self.price_band, self.maturity))

    def differences(self, other: "Cell") -> list[str]:
        return [name for name in ("category", "traffic_source", "price_band", "maturity")
                if getattr(self, name) != getattr(other, name)]


@dataclass
class Observation:
    """One listing's funnel over one window. `None` is unmeasured, never zero."""

    listing_ref: str
    cell: Cell
    impressions: int | None = None
    clicks: int | None = None
    favourites: int | None = None
    orders: int | None = None
    refunds_and_support: int | None = None
    contribution_cad: float | None = None


def band_for(price_cad: float) -> str:
    """Which price band a price falls in. Lower bound inclusive, upper exclusive."""
    if price_cad < 0:
        raise BenchmarkRefused("a negative price is not a price")
    for name, low, high in PRICE_BANDS:
        if low <= price_cad < high:
            return name
    return PRICE_BAND_KEYS[-1]


def maturity_for(*, days_live: int, orders: int) -> str:
    """How mature the shop was, from two counts rather than from a judgement."""
    if orders >= ESTABLISHED_AFTER_ORDERS and days_live >= ESTABLISHED_AFTER_DAYS:
        return "established"
    if orders >= ESTABLISHING_AFTER_ORDERS:
        return "establishing"
    return "new"


def _ratio(numerator, denominator) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _metric_values(metric: str, rows: list[Observation]) -> list[float]:
    values: list[float] = []
    for r in rows:
        if metric == "impressions_to_click":
            v = _ratio(r.clicks, r.impressions)
        elif metric == "favourite_rate":
            v = _ratio(r.favourites, r.clicks)
        elif metric == "conversion":
            v = _ratio(r.orders, r.clicks)
        elif metric == "refund_or_support_rate":
            v = (_ratio(r.refunds_and_support, r.orders)
                 if (r.orders or 0) >= MIN_ORDERS_FOR_REFUND_RATE else None)
        else:
            v = _ratio(r.contribution_cad, r.clicks)
        if v is not None:
            values.append(v)
    return values


def baseline(observations: list[Observation], cell: Cell) -> dict:
    """The baseline for one cell, or the reason there is not one.

    The median rather than the mean: one listing that a pin sent thirty thousand impressions
    moves a mean and does not move what an ordinary listing in this cell does.
    """
    rows = [o for o in observations if o.cell.key() == cell.key()]
    impressions = sum(o.impressions or 0 for o in rows)

    reasons: list[str] = []
    if len(rows) < MIN_LISTINGS_PER_CELL:
        reasons.append(
            f"{len(rows)} listing(s) in this cell against a floor of "
            f"{MIN_LISTINGS_PER_CELL}. Two listings and a fortnight is the shape of a "
            f"baseline and none of its content, and a thin cell answers, which makes it more "
            f"dangerous than an empty one")
    if impressions < MIN_IMPRESSIONS_PER_CELL:
        reasons.append(f"{impressions} impressions against a floor of "
                       f"{MIN_IMPRESSIONS_PER_CELL}")

    metrics: dict[str, dict] = {}
    for metric, spec in METRICS.items():
        values = _metric_values(metric, rows)
        if not values or reasons:
            orders = sum(o.orders or 0 for o in rows)
            if reasons:
                why = "this cell cannot be read yet"
            elif metric == "refund_or_support_rate" and 0 < orders < MIN_ORDERS_FOR_REFUND_RATE:
                # Distinguished from the absent case on purpose: one refund against three
                # orders is 33%, and a rate computed from three orders is a rumour.
                why = (f"{orders} order(s) against a floor of {MIN_ORDERS_FOR_REFUND_RATE} "
                       f"before a refund rate means anything: one refund against three "
                       f"orders reads as 33% and is a rumour")
            else:
                why = (f"nothing in this cell carries {list(spec['needs'])}. Absent is not "
                       f"zero: a refund rate of zero on a shop with no orders is not good "
                       f"performance, it is nothing")
            metrics[metric] = {"value": None, "n": len(values), "why": why}
        else:
            metrics[metric] = {"value": round(median(values), 5), "n": len(values),
                               "higher_is_better": spec["higher_is_better"],
                               "basis": "median across the listings in this cell"}

    return {
        "cell": cell.key(), "listings": len(rows), "impressions": impressions,
        "readable": not reasons, "reasons": reasons, "metrics": metrics,
        "floors": {"listings": MIN_LISTINGS_PER_CELL,
                   "impressions": MIN_IMPRESSIONS_PER_CELL},
    }


def compare(a: Cell, b: Cell) -> dict:
    """Whether two cells may be read against each other, and what differs when they may not.

    A refusal rather than a caveat. The failure this guards is somebody putting two real
    numbers side by side and drawing a conclusion that is arithmetically correct and about
    two different businesses.
    """
    differences = a.differences(b)
    if not differences:
        return {"comparable": True, "a": a.key(), "b": b.key(),
                "why": "the same funnel, measured twice"}
    return {
        "comparable": False, "a": a.key(), "b": b.key(), "differs_on": differences,
        "why": (f"these are different funnels: they differ on {differences}. A CA$6 ornament "
                f"is an impulse at a price nobody thinks about and a CA$15 blanket is a "
                f"project somebody decides to start; both numbers are real and neither is "
                f"about the other"),
    }


def overall(observations: list[Observation]) -> dict:
    """The shop-wide figures, labelled as what they are: a description, not a baseline."""
    metrics = {}
    for metric in METRICS:
        values = _metric_values(metric, observations)
        metrics[metric] = ({"value": round(median(values), 5), "n": len(values)}
                           if values else {"value": None, "n": 0})
    return {
        "listings": len(observations),
        "metrics": metrics,
        "comparable_to_a_cell": False,
        "why": ("a shop-wide number sits between two truths and describes neither. It is "
                "reported because somebody will ask, and it may not be used as a baseline "
                "for any cell"),
    }


def cells(observations: list[Observation]) -> dict:
    """Which cells have anything in them, and which of those can be read."""
    seen: dict[str, Cell] = {}
    for o in observations:
        seen.setdefault(o.cell.key(), o.cell)
    read = {key: baseline(observations, cell) for key, cell in sorted(seen.items())}
    return {
        "occupied": len(seen),
        "readable": sum(1 for r in read.values() if r["readable"]),
        "cells": read,
        "note": ("no cell has anything in it. This company has no listings, no impressions "
                 "and no orders, so there is no baseline anywhere -- which is different from "
                 "a baseline of zero, and is reported as the first rather than the second"
                 if not seen else ""),
    }


def state() -> dict:
    """The axes, the metrics and the floors, for a reader asking what a baseline is here."""
    return {
        "axes": {"category": list(POD_KEYS), "traffic_source": list(TRAFFIC_SOURCES),
                 "price_band": [{"key": k, "from_cad": lo,
                                 "to_cad": None if hi == float("inf") else hi}
                                for k, lo, hi in PRICE_BANDS],
                 "maturity": list(MATURITY)},
        "metrics": {k: {"needs": list(v["needs"]), "higher_is_better": v["higher_is_better"],
                        "why": v["why"]} for k, v in METRICS.items()},
        "floors": {"listings_per_cell": MIN_LISTINGS_PER_CELL,
                   "impressions_per_cell": MIN_IMPRESSIONS_PER_CELL,
                   "orders_before_a_refund_rate": MIN_ORDERS_FOR_REFUND_RATE},
        "note": ("A baseline belongs to a cell -- category, traffic source, price band, shop "
                 "maturity -- and a comparison across cells is refused by name with the axes "
                 "that differ. A thin cell answers, which makes it more dangerous than an "
                 "empty one, so below the floor the number is not produced at all (#14)."),
    }
