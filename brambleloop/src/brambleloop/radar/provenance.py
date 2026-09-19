"""Where a trend number came from, and why that is usually the whole story.

Requirement 38. A trend figure is a measurement of a population over a window, and both get
dropped the moment it is quoted. "Crochet cardigans are up 40%" is a sentence with no
subject — up among whom, compared to when? Etsy's own trend reporting is frequently US-heavy
and frequently describes a window that has closed, and neither fact travels with the number.

The failure is not that anybody lies. It is that a US figure from last December is a perfectly
good number, and reading it as current Canadian demand is a decision nobody consciously makes.
By the time it reaches a product brief it is just "the data".

So three rules.

**A datum with no population and no window is refused**, not discounted. A number that cannot
say who it describes is not evidence about anybody, and discounting it would imply it was
weak evidence rather than none.

**Mismatch is discounted, and the discount is visible on the number.** A US figure is real
evidence about Canada — weaker, not worthless — so it carries a factor and the reason for it,
and the factor cannot be argued away downstream because it is baked into the value the
consumer sees.

**Staleness is measured against the thing's own seasonality.** A figure about Christmas demand
from last January is not eleven months old in any useful sense; it is one cycle old, and it is
about to be relevant again. A figure about a two-week meme from last January is archaeology.
Treating those the same is what a plain age cut-off does.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

# Populations a datum can describe. Closed, because "global" is what an unlabelled number
# gets called when somebody needs it to be global.
POPULATIONS: dict[str, str] = {
    "CA": "Canada",
    "US": "United States",
    "US_CA": "United States and Canada together, not separable",
    "EU": "European Union",
    "UK": "United Kingdom",
    "GLOBAL": "worldwide, genuinely aggregated",
    "UNKNOWN": "the source does not say",
}

# How much a population tells us about Canadian demand. Not zero for the near neighbours:
# a US crochet trend is real evidence about Canada, and calling it worthless would be as
# wrong as calling it equivalent.
RELEVANCE_TO_CA: dict[str, float] = {
    "CA": 1.0,
    "US_CA": 0.95,
    "US": 0.75,
    "GLOBAL": 0.70,
    "UK": 0.55,
    "EU": 0.45,
    "UNKNOWN": 0.0,
}

# Whether the thing measured repeats. A seasonal figure ages in cycles; a fad ages in weeks.
SEASONAL = "seasonal"
EVERGREEN = "evergreen"
FAD = "fad"

SHAPES: tuple[str, ...] = (SEASONAL, EVERGREEN, FAD)

# Days after which a datum of each shape has stopped describing the present.
FRESH_FOR_DAYS: dict[str, int] = {
    SEASONAL: 400,     # one cycle plus a margin: last Christmas is about to be relevant
    EVERGREEN: 270,
    FAD: 30,
}


class ProvenanceRefused(ValueError):
    """A trend number that cannot say who it describes, or when."""


@dataclass(frozen=True)
class TrendDatum:
    """One measurement, with everything needed to know what it is a measurement of."""

    topic: str
    value: float
    source: str
    population: str
    window_from: str
    window_to: str
    shape: str = SEASONAL

    def __post_init__(self) -> None:
        if self.population not in POPULATIONS:
            raise ProvenanceRefused(
                f"{self.topic}: {self.population!r} is not a population: "
                f"{sorted(POPULATIONS)}")
        if self.shape not in SHAPES:
            raise ProvenanceRefused(f"{self.topic}: {self.shape!r} is not a shape: {SHAPES}")
        if not self.source.strip():
            raise ProvenanceRefused(
                f"{self.topic}: a trend number with no source is a number somebody remembers")
        if not (self.window_from and self.window_to):
            raise ProvenanceRefused(
                f"{self.topic}: a measurement describes a window. Without one this is not "
                f"weak evidence about the present, it is no evidence about any time at all")
        if self.population == "UNKNOWN":
            raise ProvenanceRefused(
                f"{self.topic}: the source does not say who it measured, so this cannot be "
                f"evidence about anybody. Discounting it would imply it was weak evidence "
                f"rather than none")

    def age_days(self, today: date | None = None) -> int:
        today = today or date.today()
        return (today - date.fromisoformat(self.window_to)).days

    def freshness(self, today: date | None = None) -> float:
        """1.0 while it still describes the present, falling to 0 as it stops.

        Measured against the thing's own seasonality: a Christmas figure from last January is
        one cycle old and about to matter again, and a two-week meme from last January is
        archaeology. A plain age cut-off treats those the same.
        """
        horizon = FRESH_FOR_DAYS[self.shape]
        age = max(0, self.age_days(today))
        if age <= horizon * 0.5:
            return 1.0
        if age >= horizon:
            return 0.0
        return round(1.0 - (age - horizon * 0.5) / (horizon * 0.5), 3)

    def weight(self, today: date | None = None) -> float:
        return round(RELEVANCE_TO_CA[self.population] * self.freshness(today), 4)

    def discounted(self, today: date | None = None) -> dict:
        """The value as it may actually be used, with the discount attached to it.

        Baked into the number the consumer sees rather than offered alongside it, because a
        caveat beside a figure is read once and the figure travels on alone.
        """
        w = self.weight(today)
        return {
            "topic": self.topic,
            "raw_value": self.value,
            "usable_value": round(self.value * w, 4),
            "weight": w,
            "population": self.population,
            "population_meaning": POPULATIONS[self.population],
            "relevance_to_ca": RELEVANCE_TO_CA[self.population],
            "freshness": self.freshness(today),
            "age_days": self.age_days(today),
            "shape": self.shape,
            "window": f"{self.window_from} to {self.window_to}",
            "source": self.source,
            "why_discounted": _why(self, today),
        }


def _why(datum: TrendDatum, today: date | None) -> str:
    reasons = []
    if datum.population != "CA":
        reasons.append(
            f"measured on {POPULATIONS[datum.population]}, which is real evidence about "
            f"Canadian demand and weaker evidence than a Canadian measurement")
    fresh = datum.freshness(today)
    if fresh < 1.0:
        reasons.append(
            f"{datum.age_days(today)} days old against a {FRESH_FOR_DAYS[datum.shape]}-day "
            f"horizon for a {datum.shape} topic")
    return "; ".join(reasons) or "current Canadian measurement, used at full weight"


def check_presentable_as_current(datum: TrendDatum, *, claim: str,
                                 today: date | None = None) -> None:
    """Refuse presenting a mismatched or stale figure as current Canadian demand (#38).

    The claim text is checked because this is where the drop happens: the number keeps its
    provenance in the database and loses it in the sentence somebody writes.
    """
    low = claim.lower()
    asserts_current = any(w in low for w in ("current", "right now", "today", "this season"))
    asserts_local = any(w in low for w in ("canadian", "canada", "here", "local"))

    if asserts_local and datum.population not in ("CA", "US_CA"):
        raise ProvenanceRefused(
            f"the claim describes Canadian demand and the datum measured "
            f"{POPULATIONS[datum.population]}. Use it at its discounted weight and say what "
            f"it measured, or find a Canadian figure (#38)")
    if asserts_current and datum.freshness(today) <= 0.0:
        raise ProvenanceRefused(
            f"the claim describes current demand and the datum's window closed "
            f"{datum.age_days(today)} days ago, past the {FRESH_FOR_DAYS[datum.shape]}-day "
            f"horizon for a {datum.shape} topic")


def rank(data: list[TrendDatum], today: date | None = None) -> dict:
    """Order topics by usable evidence rather than by headline value.

    The reordering is the point: a large US number from last year routinely outranks a modest
    Canadian one on the raw figure and should not.
    """
    rows = [d.discounted(today) for d in data]
    by_usable = sorted(rows, key=lambda r: -r["usable_value"])
    by_raw = sorted(rows, key=lambda r: -r["raw_value"])
    return {
        "ranked": by_usable,
        "raw_ranking_disagrees": [r["topic"] for r in by_usable] != [r["topic"] for r in by_raw],
        "unusable": [r["topic"] for r in rows if r["weight"] == 0.0],
        "note": ("Ranked on usable evidence, not headline value. A large US figure from last "
                 "year routinely outranks a modest Canadian one on the raw number (#38)."),
    }


def example_window(days_ago: int, length_days: int = 30,
                   today: date | None = None) -> tuple[str, str]:
    """Helper for callers recording a window relative to now."""
    today = today or date.today()
    end = today - timedelta(days=days_ago)
    return (end - timedelta(days=length_days)).isoformat(), end.isoformat()
