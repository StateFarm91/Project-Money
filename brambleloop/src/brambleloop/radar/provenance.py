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


# ---------------------------------------------------------------------------
# Stamping the rows (certification repair #38). The rules above had no caller, so every
# trend row in the database travelled without its population, window or freshness. This
# stamps one `trend_provenance` row per datum and restamps freshness as it ages.

# What each recorded source measured. A source not listed here is UNKNOWN and its rows are
# stamped refused rather than guessed at.
SOURCE_POPULATION: dict[str, str] = {
    # English Wikipedia reference reading, all access, all agents: worldwide readers.
    "wikimedia_pageviews": "GLOBAL",
}

# How many days a reading from each source describes, ending on `observed_on`.
SOURCE_WINDOW_DAYS: dict[str, int] = {"wikimedia_pageviews": 28, "benchmark": 7}

# Insights snapshots name their geography in words; the closed vocabulary above is the key.
GEOGRAPHY_POPULATION: dict[str, str] = {
    "ca": "CA", "canada": "CA", "us": "US", "united states": "US", "usa": "US",
    "us_ca": "US_CA", "north america": "US_CA", "uk": "UK", "united kingdom": "UK",
    "eu": "EU", "global": "GLOBAL", "worldwide": "GLOBAL", "all": "GLOBAL",
}

# Marketplace Insights reports a trailing month.
INSIGHTS_WINDOW_DAYS = 30

SHAPE_FOR_HALF_LIFE: dict[str, str] = {
    "flash": FAD, "short_seasonal": SEASONAL, "recurring_seasonal": SEASONAL,
    "multi_season_fashion": EVERGREEN, "evergreen": EVERGREEN,
}


def _source_key(source: str) -> str:
    return (source or "").split(":")[0].strip()


def _stamp_row(s, *, table: str, row_id: int, topic: str, source: str, population: str,
               window_from: str, window_to: str, shape: str, value: float | None,
               today: date) -> dict:
    from sqlalchemy import select

    from ..core.models import TrendProvenance

    stamp = s.scalar(select(TrendProvenance).where(TrendProvenance.source_table == table,
                                                   TrendProvenance.row_id == row_id))
    if stamp is None:
        stamp = TrendProvenance(source_table=table, row_id=row_id)
        s.add(stamp)
    stamp.topic, stamp.source, stamp.population = topic, source, population
    stamp.window_from, stamp.window_to, stamp.shape = window_from, window_to, shape
    stamp.raw_value = value
    try:
        datum = TrendDatum(topic=topic or "unnamed", value=float(value or 0.0),
                           source=source, population=population, window_from=window_from,
                           window_to=window_to, shape=shape)
        used = datum.discounted(today)
        # A datum with no value keeps its weight and has no usable value: the weight is a
        # fact about the source, and a missing count is not a count of zero.
        stamp.weight = used["weight"]
        stamp.usable_value = used["usable_value"] if value is not None else None
        stamp.freshness, stamp.refused_reason = used["freshness"], ""
        return {"refused": False}
    except ProvenanceRefused as exc:
        stamp.weight = stamp.usable_value = stamp.freshness = None
        stamp.refused_reason = str(exc)[:1000]
        return {"refused": True}


def stamp_all(db, *, today: date | None = None, half_lives: dict[str, str] | None = None,
              limit: int = 5000) -> dict:
    """Stamp every culture observation and Insights snapshot with its provenance (#38).

    Idempotent: a row already stamped is restamped, which is how freshness keeps pace with
    age. `half_lives` maps a signal key to its half-life class, which chooses the staleness
    horizon; an unclassified signal is treated as seasonal.
    """
    from sqlalchemy import select

    from ..core.models import CultureObservation, CultureSignal, InsightsSnapshot

    today = today or date.today()
    half_lives = half_lives or {}
    stamped = refused = 0
    by_population: dict[str, int] = {}
    with db.session() as s:
        topics = {r.key: r.topic for r in s.scalars(select(CultureSignal))}
        for obs in s.scalars(select(CultureObservation).order_by(
                CultureObservation.id.desc()).limit(limit)):
            key = _source_key(obs.source) or obs.channel
            population = SOURCE_POPULATION.get(key, "UNKNOWN")
            days = SOURCE_WINDOW_DAYS.get(key, 0)
            end = obs.observed_on or ""
            start = ((date.fromisoformat(end) - timedelta(days=days)).isoformat()
                     if end and days else "")
            shape = SHAPE_FOR_HALF_LIFE.get(half_lives.get(obs.signal_key, ""), SEASONAL)
            got = _stamp_row(s, table="culture_observations", row_id=obs.id,
                             topic=topics.get(obs.signal_key, obs.signal_key),
                             source=obs.source or obs.channel, population=population,
                             window_from=start, window_to=end, shape=shape,
                             value=obs.interest, today=today)
            stamped += 1
            refused += int(got["refused"])
            by_population[population] = by_population.get(population, 0) + 1
        for snap in s.scalars(select(InsightsSnapshot).order_by(
                InsightsSnapshot.id.desc()).limit(limit)):
            population = GEOGRAPHY_POPULATION.get((snap.geography or "").strip().lower(),
                                                  "UNKNOWN")
            end = snap.observed_on.date().isoformat() if snap.observed_on else ""
            start = ((date.fromisoformat(end) - timedelta(days=INSIGHTS_WINDOW_DAYS))
                     .isoformat() if end else "")
            got = _stamp_row(s, table="insights_snapshots", row_id=snap.id,
                             topic=snap.keyword, source=snap.basis or "insights",
                             population=population, window_from=start, window_to=end,
                             shape=SEASONAL,
                             value=(float(snap.search_count)
                                    if snap.search_count is not None else None),
                             today=today)
            stamped += 1
            refused += int(got["refused"])
            by_population[population] = by_population.get(population, 0) + 1
        # C-69 (#38): the API search-index captures are search data too. The index is the
        # marketplace's worldwide listing index (`api_index_score_sort`), so the population is
        # GLOBAL, discounted as evidence about Canada; the window is the capture day.
        from ..core.models import SerpSnapshot

        for snap in s.scalars(select(SerpSnapshot).order_by(SerpSnapshot.id.desc())
                              .limit(limit)):
            end = snap.captured_at.date().isoformat() if snap.captured_at else ""
            got = _stamp_row(s, table="serp_snapshots", row_id=snap.id, topic=snap.query,
                             source=f"etsy_api:{snap.basis}", population="GLOBAL",
                             window_from=end, window_to=end, shape=SEASONAL,
                             value=(float(snap.total_count)
                                    if snap.total_count is not None else None),
                             today=today)
            stamped += 1
            refused += int(got["refused"])
            by_population["GLOBAL"] = by_population.get("GLOBAL", 0) + 1
    return {"stamped": stamped, "refused": refused, "by_population": by_population,
            "note": ("every trend row carries its source, window, population and freshness; "
                     "rows whose population is unknown are stamped refused, not discounted")}


# ---------------------------------------------------------------------------
# #38 in the scorer (C-69): opportunity scores discount stale or mismatched evidence.

# Evidence at zero usable weight still leaves the concept's own priors half their force:
# the pool's scores are not trend data, and stale trend data makes them less sure, not void.
EVIDENCE_FLOOR = 0.5


def _terms_for(seed) -> list[str]:
    words = {w for w in (seed.slug or "").replace("-", " ").split() if len(w) > 3}
    for extra in (seed.category, seed.season):
        if extra:
            words.update(w for w in str(extra).lower().replace("_", " ").split() if len(w) > 3)
    return sorted(words)


def evidence_for(db, seed, *, today: date | None = None) -> dict:
    """The stamped trend evidence about this concept, and the discount it earns.

    Reads `trend_provenance` (the daily stamps): every row whose topic names one of the
    concept's terms. The discount is the mean usable weight -- population relevance times
    freshness -- mapped onto [EVIDENCE_FLOOR, 1]. No matching row is UNMEASURED and leaves the
    score alone; refused rows (no population) are evidence about nobody and are not counted.
    Each row is also put through `check_presentable_as_current`, so what the scorer may say
    is current Canadian demand is decided here, not in a sentence written later.
    """
    from sqlalchemy import select

    from ..core.models import TrendProvenance

    today = today or date.today()
    terms = _terms_for(seed)
    rows = []
    with db.session() as s:
        for r in s.scalars(select(TrendProvenance)):
            topic = (r.topic or "").lower()
            if not any(t in topic for t in terms):
                continue
            rows.append((r.source_table, r.row_id, r.topic, r.source, r.population,
                         r.window_from, r.window_to, r.shape, r.weight, r.refused_reason,
                         r.raw_value))
    usable = [r for r in rows if r[8] is not None and not r[9]]
    if not usable:
        return {"measured": False, "terms": terms, "rows": len(rows), "discount": 1.0,
                "why": "no stamped trend evidence names this concept; UNMEASURED, score "
                       "left on the concept's own priors"}
    mean_weight = sum(r[8] for r in usable) / len(usable)
    presentable, not_presentable = [], []
    for r in usable:
        try:
            datum = TrendDatum(topic=r[2] or "unnamed", value=float(r[10] or 0.0),
                               source=r[3] or "unknown", population=r[4],
                               window_from=r[5], window_to=r[6], shape=r[7] or SEASONAL)
            check_presentable_as_current(datum, claim="current Canadian demand", today=today)
            presentable.append(f"{r[0]}:{r[1]}")
        except ProvenanceRefused as exc:
            not_presentable.append({"row": f"{r[0]}:{r[1]}", "why": str(exc)[:160]})
    discount = round(EVIDENCE_FLOOR + (1 - EVIDENCE_FLOOR) * mean_weight, 4)
    return {"measured": True, "terms": terms, "rows": len(usable),
            "mean_weight": round(mean_weight, 4), "discount": discount,
            "presentable_as_current_canadian": presentable[:10],
            "not_presentable": not_presentable[:10],
            "why": (f"{len(usable)} stamped row(s), mean usable weight {mean_weight:.2f}; "
                    f"the opportunity score is multiplied by {discount}")}
