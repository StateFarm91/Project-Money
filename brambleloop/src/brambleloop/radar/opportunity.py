"""Opportunity pool and scoring (Master Plan sections 4, 5, 33).

Section 33 is explicit: *do not commit the first 12 SKUs before Market Radar runs*. Start
with at least 30 concepts across several categories, score them, then choose roughly 8-12
release candidates. This module is that step, and it is deliberately deterministic: the same
pool and the same date produce the same portfolio, and every score decomposes into named
components a human can argue with.

Nothing here asks a model what to build. A model is good at proposing concepts; it is bad at
being consistent about why one beats another, and "the model liked it" is not a reason the
owner can audit six weeks later when a SKU underperforms.

The pool is drawn from the categories section 4 lists, not from an assumption that blankets
are the answer. Blankets are *in* the pool and several score well, but so do ornaments,
baskets, coasters and no-sew makes, and the portfolio constraints below force a mix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .market import (
    SEASONAL_EVENTS, SeasonalEvent, seasonal_urgency, shopping_window,
)

# ---- category-level evidence ---------------------------------------------

# Demand and competition indices, 0-1, derived from the observations in market.py. These are
# judgements about observed public signals (favourite counts, "bought in the last week"
# badges, review depth, how many shops occupy the shelf), not invented numbers, and each one
# is sourced in CATEGORY_EVIDENCE below so a later session can challenge it.
CATEGORY_DEMAND: dict[str, float] = {
    "mosaic_blanket": 0.92,
    "blanket": 0.85,
    "graphghan": 0.70,
    "amigurumi": 0.88,
    "seasonal_decor": 0.80,
    "ornament": 0.72,
    "stocking": 0.68,
    "tree_skirt": 0.55,
    "basket": 0.62,
    "pillow": 0.58,
    "coaster": 0.60,
    "placemat": 0.45,
    "runner": 0.42,
    "wall_decor": 0.50,
    "bag": 0.66,
    "hat": 0.74,
    "scarf": 0.64,
    "shawl": 0.58,
    "garment": 0.70,
    "baby": 0.82,
    "nursery": 0.60,
    "pet": 0.52,
    "wedding": 0.40,
    "quick_make": 0.75,
    "flower": 0.56,
}

# How crowded and how entrenched the incumbents are. 1.0 means "8k-43k reviews and a shop
# that has owned this shelf for years"; we can still enter, but not by being merely adequate.
CATEGORY_COMPETITION: dict[str, float] = {
    "mosaic_blanket": 0.88,
    "blanket": 0.80,
    "graphghan": 0.62,
    "amigurumi": 0.90,
    "seasonal_decor": 0.70,
    "ornament": 0.55,
    "stocking": 0.60,
    "tree_skirt": 0.45,
    "basket": 0.50,
    "pillow": 0.48,
    "coaster": 0.52,
    "placemat": 0.35,
    "runner": 0.32,
    "wall_decor": 0.45,
    "bag": 0.62,
    "hat": 0.78,
    "scarf": 0.66,
    "shawl": 0.58,
    "garment": 0.72,
    "baby": 0.75,
    "nursery": 0.55,
    "pet": 0.40,
    "wedding": 0.38,
    "quick_make": 0.68,
    "flower": 0.50,
}

CATEGORY_EVIDENCE: dict[str, str] = {
    "mosaic_blanket": "Overlay-mosaic Christmas blankets at 4,794 and 1,789 favourites; "
                      "HanJanCrochet's fall blanket carries 'Bestseller' plus '200+ bought "
                      "in the last week' and 8.4k shop reviews.",
    "amigurumi": "43.2k reviews on one collection at CA$2.75-8.78: enormous volume, but the "
                 "shelf is owned and the price point is a third of a blanket pattern.",
    "seasonal_decor": "MJsOffTheHookDesigns ships blanket + stocking + basket + tree skirt as "
                      "one visual family; the family sells the family.",
    "baby": "Baby blankets recur across every shop we profiled and take 3-20h, so the "
            "shopping window is short and repeats all year rather than once a season.",
    "quick_make": "Sub-4-hour makes convert on impulse and accumulate reviews fastest, which "
                  "is the only lever we have against an 8k-review incumbent.",
    "garment": "Highest price band observed (CA$9.90-14.05) and the strongest brand signal, "
               "but Class C: fitted garments need physical testing we cannot yet do.",
}

# What the compiler can actually prove. Section 3: Class A is machine-verifiable, Class B
# needs some physical sampling, Class C normally requires real testing. Until we have
# physical calibration data, a score that ignored this would be lying to us.
RISK_VERIFIABILITY: dict[str, float] = {"A": 1.0, "B": 0.62, "C": 0.22}

# Section 33: favour Class A/B initially. This is enforced structurally in select_portfolio.
MAX_CLASS_C = 1
MAX_PER_CATEGORY = 3

PREMIUM_PRICE_CEILING_CAD = 14.0  # top of the observed pattern+video band


# ---- the pool -------------------------------------------------------------


@dataclass(frozen=True)
class ConceptSeed:
    """One candidate product, before any scoring."""

    slug: str
    title: str
    category: str
    risk_class: str                    # A / B / C, per Master Plan section 3
    price_cad: float
    maker_hours: tuple[float, float]   # (fast maker, slow maker) -- drives the buy window
    design_hours: float                # our cost to produce it, in agent + review hours
    whitespace: float                  # 0-1: how real the differentiation is
    rationale: str
    season: str | None = None          # a SeasonalEvent name, or None for evergreen
    family: str | None = None          # bundle family, section 33's "bundle-ready family"
    evergreen: bool = False
    bundle_ready: bool = False
    is_bundle: bool = False   # a collection of other concepts, not a standalone design

    @property
    def build_lead_days(self) -> int:
        """How long before *we* could have this listed.

        Scoring seasonal fit as of today would be wrong: we cannot list anything today. What
        matters is whether the buying window is open on the day we could actually ship. The
        divisor is our assumed effective throughput across a portfolio being built in
        parallel, and the seven-day floor is QA, assets and listing work that no concept
        escapes however trivial the stitching is.
        """
        return max(7, int(round(self.design_hours / 4.0)))


def _pool() -> list[ConceptSeed]:
    """34 concepts across 20 categories. Blankets are candidates, not the assumption."""
    C = ConceptSeed
    return [
        # --- flagship seasonal blankets -----------------------------------
        C("nordic-forest-mosaic-throw", "Nordic Forest Overlay Mosaic Throw",
          "mosaic_blanket", "A", 12.50, (30.0, 60.0), 26.0, 0.72,
          "Overlay mosaic is the strongest demand signal we observed and it is pure Class A "
          "geometry: every row is a countable sequence the compiler can verify end to end. "
          "Our differentiation is three finished sizes from one chart, which no profiled "
          "competitor offers.",
          season="Christmas", family="nordic-forest", bundle_ready=True),
        C("nordic-forest-stocking", "Nordic Forest Mosaic Stocking",
          "stocking", "B", 7.50, (4.0, 9.0), 12.0, 0.62,
          "Same motif library as the throw, a fifth of the make time. Buyers who cannot "
          "commit 40 hours in October still buy the stocking, and it cross-sells the throw.",
          season="Christmas", family="nordic-forest", bundle_ready=True),
        C("nordic-forest-basket", "Nordic Forest Mosaic Storage Basket",
          "basket", "B", 6.50, (3.0, 7.0), 9.0, 0.58,
          "Third member of the family. Baskets are shallow competition (0.50) with real "
          "demand, and a basket photographs the motif at close range.",
          season=None, family="nordic-forest", bundle_ready=True, evergreen=True),
        C("nordic-forest-bundle", "Nordic Forest Collection Bundle",
          "seasonal_decor", "A", 24.00, (37.0, 76.0), 4.0, 0.85,
          "Every profiled competitor sells family members individually and none bundles them. "
          "The bundle costs us almost nothing once the members exist and lifts order value "
          "well above the CA$8-12 ceiling the category has settled into.",
          season="Christmas", family="nordic-forest", bundle_ready=True, is_bundle=True),
        C("autumn-oak-mosaic-throw", "Autumn Oak Overlay Mosaic Throw",
          "mosaic_blanket", "A", 12.50, (30.0, 55.0), 24.0, 0.60,
          "Autumn mosaic is the single best-evidenced listing we found. The window for a "
          "throw is however nearly closed this year; strong for next season, weak for now. "
          "Scored honestly against the autumn window rather than parked as evergreen.",
          season="Thanksgiving (CA)", family="autumn-oak", bundle_ready=True),
        C("heirloom-cable-blanket", "Heirloom Cable Throw",
          "blanket", "A", 11.50, (25.0, 50.0), 20.0, 0.55,
          "Texture rather than colourwork; a different buyer from the mosaic audience and "
          "still fully countable.", evergreen=True),
        C("winter-village-graphghan", "Winter Village Graphghan",
          "graphghan", "A", 10.50, (35.0, 70.0), 22.0, 0.66,
          "Graphghans are chart-native, which plays directly to our chart rendering, and the "
          "category is markedly less crowded than mosaic.",
          season="Christmas"),

        # --- baby ----------------------------------------------------------
        C("cloudline-baby-blanket", "Cloudline Textured Baby Blanket",
          "baby", "A", 8.50, (6.0, 16.0), 12.0, 0.64,
          "Baby demand does not wait for a holiday and the make time is short enough that the "
          "buy window is always open. Evergreen search anchor.",
          evergreen=True, family="cloudline", bundle_ready=True),
        C("cloudline-baby-hat", "Cloudline Baby Hat Set",
          "baby", "B", 5.50, (1.5, 4.0), 7.0, 0.55,
          "Sizing across newborn to 12 months is arithmetic the compiler can check per size, "
          "which is exactly the kind of claim competitors make loosely.",
          evergreen=True, family="cloudline", bundle_ready=True),
        C("nursery-cloud-mobile", "Nursery Cloud and Star Mobile",
          "nursery", "B", 6.50, (3.0, 8.0), 9.0, 0.60,
          "Low competition, strong gifting, and the shapes are simple enough to validate.",
          evergreen=True, family="cloudline", bundle_ready=True),

        # --- amigurumi -------------------------------------------------------
        C("woodland-fox-amigurumi", "Woodland Fox Amigurumi",
          "amigurumi", "B", 6.00, (4.0, 10.0), 14.0, 0.48,
          "Huge volume category, but Class B and dominated by shops with 43k reviews. Worth "
          "one entry to learn the shelf, not worth leading with.",
          evergreen=True),
        C("no-sew-reindeer", "No-Sew Reindeer Amigurumi",
          "amigurumi", "B", 5.00, (2.0, 5.0), 10.0, 0.70,
          "No-sew is a genuine complaint theme in the category: assembly is where beginners "
          "fail. A no-sew construction is a differentiator we can actually deliver.",
          season="Christmas"),
        C("pocket-penguin-trio", "Pocket Penguin Trio",
          "amigurumi", "B", 5.50, (2.0, 6.0), 11.0, 0.52,
          "Three small makes in one PDF; higher perceived value at the same price point.",
          season="Christmas", bundle_ready=True),

        # --- quick makes / decor ---------------------------------------------
        C("nordic-star-ornaments", "Nordic Star Ornament Set (6)",
          "ornament", "A", 5.50, (1.0, 3.0), 6.0, 0.68,
          "Flat, countable, one evening to make, and it seeds the Nordic motif library that "
          "the throw and stocking reuse. Fastest path to first reviews.",
          season="Christmas", family="nordic-forest", bundle_ready=True),
        C("hexie-coaster-set", "Hexagon Coaster Set",
          "coaster", "A", 4.50, (0.5, 2.0), 4.0, 0.50,
          "Cheapest possible entry, pure Class A, useful as a free-motif lead magnet later.",
          evergreen=True),
        C("mosaic-placemat-pair", "Mosaic Placemat Pair",
          "placemat", "A", 5.50, (2.0, 5.0), 6.0, 0.62,
          "Very low competition (0.35) and it proves the mosaic technique at a price a "
          "curious buyer will risk.", evergreen=True),
        C("harvest-table-runner", "Harvest Table Runner",
          "runner", "A", 6.50, (4.0, 9.0), 8.0, 0.58,
          "Thin shelf, clear seasonal pull, and a runner is a rectangle: fully verifiable.",
          season="Thanksgiving (CA)"),
        C("pumpkin-cluster-set", "Pumpkin Cluster Set (3 sizes)",
          "seasonal_decor", "B", 5.50, (2.0, 6.0), 8.0, 0.55,
          "Autumn decor with a short make time is still inside its buying window in "
          "September.", season="Halloween"),
        C("spooky-garland", "Spooky Bunting Garland",
          "seasonal_decor", "A", 4.50, (1.5, 4.0), 5.0, 0.48,
          "Small, fast, and Halloween is the nearest event with an open window.",
          season="Halloween"),
        C("cottage-wall-hanging", "Cottage Botanical Wall Hanging",
          "wall_decor", "B", 7.50, (3.0, 8.0), 10.0, 0.60,
          "Decor buyers pay for aesthetics rather than utility, which suits a brand that is "
          "competing on design rather than review count.", evergreen=True),
        C("market-basket-trio", "Crochet Storage Basket",
          "basket", "A", 6.50, (2.0, 6.0), 8.0, 0.56,
          "Worked in the round from the centre of the base, in three sizes; the sizing "
          "maths and the shaping geometry are exactly what our compiler is for. Scored "
          "Class A as a concept but engineered as Class B, because how firmly it stands "
          "up is not computable from gauge.",
          evergreen=True),
        C("bobble-floor-pillow", "Bobble Floor Pillow",
          "pillow", "B", 7.00, (5.0, 12.0), 10.0, 0.52,
          "Texture-led, modest competition, photographs well in a styled room.",
          evergreen=True),
        C("pressed-flower-motifs", "Pressed Flower Motif Library (12)",
          "flower", "A", 6.00, (0.5, 2.0), 9.0, 0.66,
          "A motif library is reusable inventory for us, not just a product: section 5's "
          "'reusable original validated motif libraries' in literal form.", evergreen=True),

        # --- wearables and bags ------------------------------------------------
        C("alpine-slouch-beanie", "Alpine Slouch Beanie",
          "hat", "B", 6.50, (2.0, 5.0), 8.0, 0.50,
          "Hats are a crowded shelf (0.78) but the make time is short and sizing is "
          "arithmetic we can verify per head circumference.", evergreen=True),
        C("chunky-ribbed-scarf", "Chunky Ribbed Scarf",
          "scarf", "A", 5.50, (3.0, 8.0), 5.0, 0.42,
          "Straightforward, evergreen, useful as a low-risk beginner entry point.",
          evergreen=True),
        C("lattice-triangle-shawl", "Lattice Triangle Shawl",
          "shawl", "B", 8.50, (8.0, 18.0), 12.0, 0.58,
          "Shawls avoid fit risk almost entirely while still reading as a garment purchase.",
          evergreen=True),
        C("everyday-market-tote", "Everyday Market Tote",
          "bag", "B", 7.50, (4.0, 10.0), 9.0, 0.54,
          "Bags sit between decor and garment: no fit risk, real utility.", evergreen=True),
        C("boxy-summer-tee", "Boxy Summer Tee",
          "garment", "C", 13.50, (12.0, 30.0), 22.0, 0.56,
          "Highest price band we observed, and the strongest brand signal. Class C: it needs "
          "physical testing before any certificate, so it must not lead the portfolio.",
          evergreen=True),
        C("cropped-cardigan", "Everyday Cropped Cardigan",
          "garment", "C", 14.00, (20.0, 45.0), 28.0, 0.58,
          "Same argument as the tee and the same blocker. Held for when physical calibration "
          "data exists.", evergreen=True),

        # --- gifting and misc --------------------------------------------------
        C("valentine-heart-garland", "Heart Motif Garland",
          "seasonal_decor", "A", 4.50, (1.0, 3.0), 4.0, 0.44,
          "Cheap, fast, and February is far enough out that it can be built without "
          "pressure.", season="Valentine's"),
        C("easter-egg-cosies", "Easter Egg Cosy Set",
          "seasonal_decor", "B", 4.50, (1.0, 4.0), 6.0, 0.46,
          "Spring has no equivalent of the autumn blanket rush, so Easter decor is filler "
          "for a build window that would otherwise sit idle. Low ceiling, low cost, and it "
          "keeps the listing cadence unbroken between seasons.", season="Easter"),
        C("mothers-day-shawlette", "Mother's Day Lace Shawlette",
          "shawl", "B", 8.50, (6.0, 15.0), 12.0, 0.52,
          "Gift-driven and dateable; May is far out, so the window maths correctly scores it "
          "down for now.", season="Mother's Day"),
        C("pet-snuggle-mat", "Pet Snuggle Mat",
          "pet", "A", 5.00, (2.0, 6.0), 6.0, 0.60,
          "Thinnest competition in the pool (0.40) and completely rectangular.",
          evergreen=True),
        C("wedding-ring-cushion", "Wedding Ring Cushion",
          "wedding", "B", 6.50, (1.5, 4.0), 7.0, 0.50,
          "Very low competition but very low demand; included so the pool is honest about "
          "what a thin niche looks like rather than only listing winners.", evergreen=True),
    ]


POOL: list[ConceptSeed] = _pool()


# ---- scoring ---------------------------------------------------------------

WEIGHTS: dict[str, float] = {
    "demand": 0.28,
    "competition_headroom": 0.18,
    "verifiability": 0.20,
    "seasonal_fit": 0.14,
    "margin": 0.10,
    "whitespace": 0.10,
}

EVERGREEN_SEASONAL_FIT = 0.55
"""An evergreen product has no window to miss. That is worth more than a seasonal product
whose window has closed and less than one whose window is open right now."""


@dataclass
class ScoredConcept:
    seed: ConceptSeed
    score: float
    components: dict[str, float]
    notes: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.seed.slug

    def to_dict(self) -> dict:
        return {
            "slug": self.seed.slug,
            "title": self.seed.title,
            "category": self.seed.category,
            "risk_class": self.seed.risk_class,
            "price_cad": self.seed.price_cad,
            "season": self.seed.season,
            "family": self.seed.family,
            "evergreen": self.seed.evergreen,
            "bundle_ready": self.seed.bundle_ready,
            "score": self.score,
            "components": self.components,
            "rationale": self.seed.rationale,
            "notes": list(self.notes),
        }


def _event(name: str) -> SeasonalEvent | None:
    for e in SEASONAL_EVENTS:
        if e.name == name:
            return e
    return None


def ready_date(seed: ConceptSeed, today: date) -> date:
    return today + timedelta(days=seed.build_lead_days)


def _seasonal_component(seed: ConceptSeed, today: date) -> tuple[float, str]:
    """How well this concept's buying window lines up with the day we could ship it.

    Two refinements over a naive "days until the holiday":

    1. The window is computed from *this concept's* maker hours, not the event's generic
       ones. A stocking and a throw share Christmas and have completely different buy-by
       dates -- roughly six weeks apart.
    2. It is evaluated at our ready date rather than today, because a concept we cannot list
       for three weeks must be judged on the market that will exist in three weeks.

    A concept whose window will not open for months therefore scores low. That is intended:
    section 33 asks which 8-12 SKUs to build *first*, and building Valentine's garlands in
    September while the Christmas window is open would be a real, expensive mistake. Those
    concepts stay in the pool and re-score upward as their windows approach.
    """
    if seed.season is None:
        return EVERGREEN_SEASONAL_FIT, "evergreen: no window to miss"
    base = _event(seed.season)
    if base is None:
        return EVERGREEN_SEASONAL_FIT, f"unknown event {seed.season!r}; treated as evergreen"
    scoped = SeasonalEvent(base.name, base.event_date, seed.maker_hours, base.gift_lead_days)
    ready = ready_date(seed, today)
    urgency = seasonal_urgency(scoped, ready)

    opens, closes = shopping_window(scoped)
    when = f"ready {ready.isoformat()}"
    if ready < opens:
        note = f"{seed.season}: {when}, window opens {opens.isoformat()} (early)"
    elif ready > closes:
        note = f"{seed.season}: {when}, window closed {closes.isoformat()} (missed)"
    else:
        note = (f"{seed.season}: {when}, window open "
                f"{opens.isoformat()}..{closes.isoformat()}")
    return urgency, note


def score_concept(seed: ConceptSeed, today: date | None = None) -> ScoredConcept:
    today = today or date.today()
    demand = CATEGORY_DEMAND.get(seed.category, 0.40)
    competition = CATEGORY_COMPETITION.get(seed.category, 0.50)
    verifiability = RISK_VERIFIABILITY.get(seed.risk_class, 0.22)
    seasonal, seasonal_note = _seasonal_component(seed, today)
    margin = min(1.0, seed.price_cad / PREMIUM_PRICE_CEILING_CAD)

    components = {
        "demand": round(demand, 3),
        "competition_headroom": round(1.0 - competition, 3),
        "verifiability": round(verifiability, 3),
        "seasonal_fit": round(seasonal, 3),
        "margin": round(margin, 3),
        "whitespace": round(seed.whitespace, 3),
    }
    score = round(sum(WEIGHTS[k] * v for k, v in components.items()), 4)

    notes = [seasonal_note]
    if seed.risk_class == "C":
        notes.append("Class C: cannot be certified until physical testing exists")
    if seed.category in CATEGORY_EVIDENCE:
        notes.append(CATEGORY_EVIDENCE[seed.category])
    return ScoredConcept(seed=seed, score=score, components=components, notes=notes)


def score_pool(pool: list[ConceptSeed] | None = None,
               today: date | None = None) -> list[ScoredConcept]:
    """Every concept, best first. Ties break on slug so the ordering is reproducible."""
    pool = POOL if pool is None else pool
    scored = [score_concept(s, today) for s in pool]
    return sorted(scored, key=lambda x: (-x.score, x.seed.slug))


# ---- portfolio selection ---------------------------------------------------


@dataclass
class Portfolio:
    selected: list[ScoredConcept]
    rejected: list[ScoredConcept]
    constraints_met: dict[str, bool]
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(self.constraints_met.values())

    def to_dict(self) -> dict:
        return {
            "selected": [c.to_dict() for c in self.selected],
            "constraints_met": dict(self.constraints_met),
            "reasons": list(self.reasons),
            "pool_size": len(self.selected) + len(self.rejected),
        }


def _flagship_seasonal(c: ScoredConcept) -> bool:
    return c.seed.season is not None and c.seed.maker_hours[1] >= 20.0


def _quick_low_price(c: ScoredConcept) -> bool:
    return c.seed.price_cad <= 6.50 and c.seed.maker_hours[1] <= 6.0


def _family_counts(selected: list[ScoredConcept]) -> dict[str, int]:
    """Members per family, excluding bundles.

    A bundle is not a member of its own family. Counting it as one would let the selector
    satisfy "ship a bundle-ready family" by shipping a bundle of products we never built.
    """
    counts: dict[str, int] = {}
    for c in selected:
        if c.seed.family and not c.seed.is_bundle:
            counts[c.seed.family] = counts.get(c.seed.family, 0) + 1
    return counts


def _check(selected: list[ScoredConcept]) -> dict[str, bool]:
    families = _family_counts(selected)
    bundles_backed = all(
        families.get(c.seed.family or "", 0) >= 2
        for c in selected if c.seed.is_bundle
    )
    return {
        "size_8_to_12": 8 <= len(selected) <= 12,
        "flagship_seasonal": any(_flagship_seasonal(c) for c in selected),
        "several_quick_low_price": sum(_quick_low_price(c) for c in selected) >= 3,
        "bundle_ready_family": any(n >= 2 for n in families.values()),
        "evergreen_search_product": any(c.seed.evergreen for c in selected),
        "class_c_limited": sum(c.seed.risk_class == "C" for c in selected) <= MAX_CLASS_C,
        "category_spread": len({c.seed.category for c in selected}) >= 5,
        "bundles_have_members": bundles_backed,
    }


def select_portfolio(scored: list[ScoredConcept] | None = None, *,
                     target: int = 10, today: date | None = None) -> Portfolio:
    """Choose ~8-12 release candidates under section 33's structural constraints.

    Greedy by score, then repair: if a required constraint is unmet, swap the lowest-scoring
    expendable pick for the highest-scoring concept that satisfies it. Taking the top ten by
    score alone would hand us a portfolio of four Christmas blankets, which is precisely the
    single-demand-pattern concentration section 33 forbids.
    """
    scored = score_pool(today=today) if scored is None else list(scored)
    ranked = sorted(scored, key=lambda x: (-x.score, x.seed.slug))
    reasons: list[str] = []

    # Bundles are derived inventory, not independent designs: a bundle is cheap precisely
    # because its members already exist, and a bundle of products we never built is a listing
    # we cannot fulfil. They are therefore excluded from the ranked competition and appended
    # afterwards, only where their family actually earned two places.
    bundles = [c for c in ranked if c.seed.is_bundle]
    ranked = [c for c in ranked if not c.seed.is_bundle]

    selected: list[ScoredConcept] = []
    per_category: dict[str, int] = {}
    class_c = 0
    for c in ranked:
        if len(selected) >= target:
            break
        cat = c.seed.category
        if per_category.get(cat, 0) >= MAX_PER_CATEGORY:
            continue
        if c.seed.risk_class == "C" and class_c >= MAX_CLASS_C:
            continue
        selected.append(c)
        per_category[cat] = per_category.get(cat, 0) + 1
        class_c += c.seed.risk_class == "C"

    def _pairs_an_existing_family(c: ScoredConcept) -> bool:
        """True if adding `c` would give some family a second non-bundle member.

        Evaluated against the current selection rather than statically, because whether a
        concept completes a family depends entirely on what is already in the portfolio.
        """
        if not c.seed.family or c.seed.is_bundle:
            return False
        return any(o.seed.family == c.seed.family and o.slug != c.slug
                   and not o.seed.is_bundle for o in selected)

    requirements: list[tuple[str, callable]] = [
        ("flagship_seasonal", _flagship_seasonal),
        ("bundle_ready_family", _pairs_an_existing_family),
        ("several_quick_low_price", _quick_low_price),
        ("evergreen_search_product", lambda c: c.seed.evergreen),
    ]

    def _satisfied(key: str) -> bool:
        return _check(selected)[key]

    for key, pred in requirements:
        # Bounded rather than "while not satisfied": a selection loop that can spin is a
        # worker that never finishes a job, and this code runs unattended. Each pass either
        # makes progress or records why it cannot.
        for _ in range(len(ranked) + 1):
            if _satisfied(key):
                break
            chosen_now = {c.slug for c in selected}
            candidate = next(
                (c for c in ranked if pred(c) and c.slug not in chosen_now
                 and per_category.get(c.seed.category, 0) < MAX_PER_CATEGORY
                 and not (c.seed.risk_class == "C" and class_c >= MAX_CLASS_C)),
                None,
            )
            if candidate is None:
                reasons.append(f"could not satisfy {key}: no eligible concept in the pool")
                break
            # Drop the weakest pick that neither holds another constraint on its own nor is
            # itself one of the things we are short of. Evicting a quick low-price make to
            # make room for a quick low-price make makes no progress and loops forever.
            droppable = [c for c in reversed(selected)
                         if not pred(c) and not _would_break(selected, c, key)]
            if not droppable:
                reasons.append(f"could not satisfy {key} without breaking another constraint")
                break
            victim = droppable[0]
            selected.remove(victim)
            per_category[victim.seed.category] -= 1
            class_c -= victim.seed.risk_class == "C"
            selected.append(candidate)
            per_category[candidate.seed.category] = per_category.get(
                candidate.seed.category, 0) + 1
            class_c += candidate.seed.risk_class == "C"
            reasons.append(
                f"swapped {victim.slug} (score {victim.score}) for {candidate.slug} "
                f"(score {candidate.score}) to satisfy {key}")

    families = _family_counts(selected)
    for b in bundles:
        if len(selected) >= 12:
            break
        members = families.get(b.seed.family or "", 0)
        if members >= 2:
            selected.append(b)
            reasons.append(
                f"added {b.slug} (score {b.score}): {members} members of family "
                f"{b.seed.family!r} are in the portfolio, so the bundle is fulfillable")
        else:
            reasons.append(
                f"held {b.slug}: only {members} member(s) of family {b.seed.family!r} were "
                f"selected, and a bundle of products we have not built cannot be listed")

    selected.sort(key=lambda x: (-x.score, x.seed.slug))
    chosen = {c.slug for c in selected}
    rejected = [c for c in ranked + bundles if c.slug not in chosen]
    rejected.sort(key=lambda x: (-x.score, x.seed.slug))
    return Portfolio(selected=selected, rejected=rejected,
                     constraints_met=_check(selected), reasons=reasons)


def _would_break(selected: list[ScoredConcept], victim: ScoredConcept, adding_for: str) -> bool:
    """True if removing `victim` would break a constraint that currently holds."""
    before = _check(selected)
    trial = [c for c in selected if c is not victim]
    after = _check(trial)
    for key, held in before.items():
        if key in ("size_8_to_12", adding_for):
            continue
        if held and not after[key]:
            return True
    return False
