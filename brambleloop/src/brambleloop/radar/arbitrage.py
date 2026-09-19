"""Scoring a micro-market on nine dimensions, and refusing to pretend the absent ones are zero.

Requirement 2. Each micro-market is scored on demand, listing density, the quality of the
offers already there, pricing and order value, season timing, Brambleloop differentiation,
machine verifiability, support burden and expected contribution -- and the requirement's own
emphasis is on hunting meaningful demand where the incumbents are weak: thumbnails that do not
read, thin PDFs, no video, recurring complaints.

Two things make this honest rather than a weighted average of guesses.

**A dimension nobody can measure is excluded, not defaulted.** Filling an unmeasured dimension
with a neutral value is the standard way a score becomes fiction: the number keeps its shape,
loses its meaning, and nobody can tell by looking. Here an unmeasured dimension drops out of
the arithmetic and is named, and the score carries the share of its own weight that was
actually measured.

**Markets scored at different confidences are not ranked against each other.** A market scored
on two dimensions and one scored on eight produce numbers that look comparable and are not.
That comparison is refused rather than presented with a caveat, because the caveat is read
once and the ranking is read every week.

Today most dimensions are unmeasured: the competitor half needs the benchmark credential and
the commercial half needs orders. That is the state this reports, rather than a tidy number.
"""
from __future__ import annotations

from dataclasses import dataclass

MEASURED, UNMEASURED = "measured", "unmeasured"

# Two markets may only be ranked against each other when their measured weight is within
# this of each other. Wider than that and the numbers are about different things.
COMPARABLE_WITHIN = 0.15

# Below this share of the weight, a score is not a score. Reported, never ranked.
SCORE_FLOOR = 0.40


@dataclass(frozen=True)
class Dimension:
    key: str
    what: str
    weight: float
    needs: str
    higher_is_better: bool


DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("demand", "how many people are looking", 0.18,
              "observed search or marketplace evidence", True),
    Dimension("listing_density", "how many answers already exist", 0.12,
              "a count of competing listings", False),
    Dimension("offer_quality", "how good those answers are", 0.14,
              "observed competitor listings: media, thumbnails, deliverables", False),
    Dimension("price_and_aov", "what the market pays and buys together", 0.10,
              "observed competitor prices, and our own order values", True),
    Dimension("season_timing", "whether the window is open", 0.10,
              "the seasonal calendar, which this company has", True),
    Dimension("differentiation", "what we can do here that they cannot", 0.12,
              "our own catalogue and capabilities, which this company has", True),
    Dimension("verifiability", "whether a pattern here can be machine-checked", 0.10,
              "the risk class of the construction, which this company has", True),
    Dimension("support_burden", "how many questions a sale here produces", 0.07,
              "support cases per order, which needs orders", False),
    Dimension("expected_contribution", "what a sale is worth after fees", 0.07,
              "the ledger, which needs sales", True),
)

DIMENSION_BY_KEY: dict[str, Dimension] = {d.key: d for d in DIMENSIONS}

# The weaknesses the requirement names. Each is a thing an incumbent listing can visibly lack,
# and each is a reason a well-made entrant can take share without out-spending anybody.
WEAKNESS_SIGNALS: dict[str, str] = {
    "thin_media": "fewer images than a buyer needs to judge a pattern they cannot hold",
    "no_video": "no video where the technique is the thing being sold",
    "unclear_deliverable": "the listing does not say what arrives, which is the most "
                           "preventable refund in the category",
    "complaints": "recurring complaints in the reviews about the same thing",
}

# Fewer images than this and a buyer cannot judge a pattern they will never hold.
THIN_MEDIA_BELOW = 5


class ArbitrageRefused(ValueError):
    """A ranking across incomparable confidences, or a dimension nobody defined."""


def score_market(market: str, *, values: dict[str, float] | None = None) -> dict:
    """Score one micro-market, excluding what nobody has measured.

    `values` carries whatever is genuinely known, each in 0..1 and already oriented so that
    higher is better for that dimension. Anything absent is unmeasured and leaves the
    arithmetic rather than defaulting to the middle.
    """
    values = values or {}
    unknown = [k for k in values if k not in DIMENSION_BY_KEY]
    if unknown:
        raise ArbitrageRefused(
            f"{unknown} are not scoring dimensions: {sorted(DIMENSION_BY_KEY)}")

    rows, measured_weight, total = [], 0.0, 0.0
    for dimension in DIMENSIONS:
        total += dimension.weight
        value = values.get(dimension.key)
        if value is None:
            rows.append({"dimension": dimension.key, "what": dimension.what,
                         "weight": dimension.weight, "basis": UNMEASURED,
                         "value": None, "needs": dimension.needs})
            continue
        if not 0.0 <= float(value) <= 1.0:
            raise ArbitrageRefused(
                f"{dimension.key}={value} is outside 0..1; a dimension that can exceed its "
                f"own scale silently outweighs the others")
        measured_weight += dimension.weight
        rows.append({"dimension": dimension.key, "what": dimension.what,
                     "weight": dimension.weight, "basis": MEASURED,
                     "value": round(float(value), 4), "needs": dimension.needs})

    confidence = round(measured_weight / total, 3) if total else 0.0
    score = (round(sum(r["weight"] * r["value"] for r in rows if r["basis"] == MEASURED)
                   / measured_weight, 4) if measured_weight else None)
    return {
        "market": market,
        "score": score,
        "confidence": confidence,
        "measured": [r["dimension"] for r in rows if r["basis"] == MEASURED],
        "unmeasured": [r["dimension"] for r in rows if r["basis"] == UNMEASURED],
        "dimensions": rows,
        "rankable": confidence >= SCORE_FLOOR,
        "note": (
            "no dimension of this market has been measured, so it has no score -- which is "
            "not a score of zero" if score is None else
            f"scored on {confidence:.0%} of the weight. Below {SCORE_FLOOR:.0%} a score is "
            f"reported and not ranked, because the dimensions that are missing are the ones "
            f"that would decide it" if confidence < SCORE_FLOOR else
            f"scored on {confidence:.0%} of the weight; the rest is named rather than "
            f"assumed"),
    }


def rank(scores: list[dict]) -> dict:
    """Order markets, refusing to rank numbers that are about different things.

    A market scored on two dimensions and one scored on eight produce numbers that look
    comparable. Presenting them together with a caveat does not work: the caveat is read once
    and the ranking is read every week.
    """
    rankable = [s for s in scores if s["rankable"]]
    withheld = [{"market": s["market"], "confidence": s["confidence"],
                 "why": "scored on too little of the weight to be ranked"}
                for s in scores if not s["rankable"]]

    if len(rankable) > 1:
        spread = max(s["confidence"] for s in rankable) - min(
            s["confidence"] for s in rankable)
        if spread > COMPARABLE_WITHIN:
            raise ArbitrageRefused(
                f"these markets were scored at confidences {spread:.0%} apart, which is "
                f"wider than {COMPARABLE_WITHIN:.0%}. Ranking a market scored on two "
                f"dimensions against one scored on eight is arithmetic on different things, "
                f"and the ranking is what everybody reads")

    rankable.sort(key=lambda s: -(s["score"] or 0.0))
    return {
        "ranked": [{"market": s["market"], "score": s["score"],
                    "confidence": s["confidence"]} for s in rankable],
        "withheld": withheld,
        "note": ("nothing is rankable yet: every market is scored on too little of its own "
                 "weight, which is the honest state of a shop with no market evidence"
                 if not rankable else
                 f"{len(rankable)} ranked, {len(withheld)} withheld for insufficient "
                 f"measurement"),
    }


def weakness_hunt(db, *, pod: str = "") -> dict:
    """Where the incumbents are visibly weak, counted from observed listings.

    The requirement's own emphasis, and the half that needs the credential. With no observed
    listing this reports unmeasurable with the reason instead of an empty opportunity list,
    which would read as "no weaknesses found".
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        query = select(BenchmarkListing)
        if pod:
            query = query.where(BenchmarkListing.pod == pod)
        listings = [{"ref": r.listing_ref, "title": r.title, "pod": r.pod,
                     "media_count": r.media_count, "price_cad": r.price_cad}
                    for r in s.scalars(query)]

    if not listings:
        return {
            "measurable": False,
            "listings": 0,
            "reason": ("no competitor listing has been observed, so where the incumbents are "
                       "weak is unknown. An empty list of weaknesses would read as 'none "
                       "found', which is the opposite of what is true"),
            "signals": WEAKNESS_SIGNALS,
        }

    thin = [row for row in listings if row["media_count"] < THIN_MEDIA_BELOW]
    return {
        "measurable": True,
        "listings": len(listings),
        "thin_media": [{"ref": r["ref"], "media_count": r["media_count"]} for r in thin],
        "thin_media_share": round(len(thin) / len(listings), 3),
        "signals": WEAKNESS_SIGNALS,
        "note": (f"{len(thin)} of {len(listings)} observed listings carry fewer than "
                 f"{THIN_MEDIA_BELOW} images, which is fewer than a buyer needs to judge a "
                 f"pattern they will never hold. Video, deliverable clarity and complaint "
                 f"themes need fields the observation does not yet carry, and are named "
                 f"rather than scored"),
    }


def state(db) -> dict:
    """What this company can currently score, and what each missing dimension waits on."""
    hunt = weakness_hunt(db)
    return {
        "dimensions": [{"dimension": d.key, "what": d.what, "weight": d.weight,
                        "needs": d.needs} for d in DIMENSIONS],
        "weakness_hunt": hunt,
        "score_floor": SCORE_FLOOR,
        "comparable_within": COMPARABLE_WITHIN,
        "note": ("An unmeasured dimension leaves the arithmetic and is named. Filling it "
                 "with a neutral value keeps the number's shape and loses its meaning, and "
                 "nobody can tell by looking (#2)."),
    }
