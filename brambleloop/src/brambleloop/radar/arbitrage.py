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

from ..intel import deliverable, pods

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
    "limited_sizes": "a garment or hat graded to two sizes or fewer, which most of the "
                     "people who wanted it cannot make",
    "no_bundle": "a department where almost nothing is sold as a set, so the buyer who "
                 "wants two has to buy twice",
}

# The two weaknesses the requirement names that no amount of text can answer. Kept in the
# vocabulary rather than dropped, because a list quietly shortened to what is measurable
# today is how a requirement gets reported as met.
NEEDS_VISION: dict[str, str] = {
    "weak_branding": "whether the shop and its listings read as one coherent thing, which "
                     "is a judgement about rendered pages and photographs",
    "stale_aesthetics": "whether the styling looks like this year, which is a judgement "
                        "about photographs",
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


def _recurring_complaints(db) -> dict:
    """The newest recorded complaint reading, or an honest statement that none exists.

    Read from a stored observation rather than recomputed, because the reviews behind it are
    not kept: what is stored is the count, which is the only part this company is entitled to
    keep and the only part it needs.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkObservation

    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkObservation)
                              .order_by(desc(BenchmarkObservation.id)).limit(50)))
    for row in rows:
        reading = (row.detail or {}).get("reviews")
        if reading:
            return {**reading, "measurable": True,
                    "observed_at": row.at.isoformat() if getattr(row, "at", None) else ""}
    return {
        "measurable": False,
        "reason": ("no review has been read, so what buyers complain about in this category "
                   "is unknown. An empty complaint list would read as a category with no "
                   "complaints, which no category is"),
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
                     "media_count": r.media_count, "price_cad": r.price_cad,
                     "has_video": (r.detail or {}).get("has_video"),
                     "deliverable": (r.detail or {}).get("deliverable"),
                     "size_range": (r.detail or {}).get("size_range"),
                     "gallery_audited": bool((r.detail or {}).get("gallery_audited"))}
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

    # Video, measured only where a gallery was actually read. A listing nobody audited has
    # an unknown video state, and counting unknown as "no video" would turn an unfinished
    # backfill into a competitive weakness.
    audited = [r for r in listings if r["gallery_audited"] and r["has_video"] is not None]
    with_video = [r for r in audited if r["has_video"]]
    video = {
        "audited": len(audited),
        "with_video": len(with_video),
        "share": round(len(with_video) / len(audited), 3) if audited else None,
        "measurable": bool(audited),
        "reason": ("no gallery has been audited, so whether these listings carry video is "
                   "unknown -- which is not the same as no video"
                   if not audited else ""),
    }

    complaints = _recurring_complaints(db)

    # What the listing says arrives, read from the description during the scan and stored as
    # facts rather than text. Listings nobody has read are excluded by summarise(), for the
    # reason video is: our unread backlog is not their weakness.
    clarity = deliverable.summarise([r["deliverable"] for r in listings])
    unclear_refs = sorted(
        r["ref"] for r in listings
        if deliverable.unclear(r["deliverable"]) is True)

    # Size range, asked only of the departments where size is a variable. A blanket has
    # dimensions, not sizes, and counting it as one size would invent a weakness.
    sized = [r for r in listings if r["size_range"]]
    stated_sizes = [r for r in sized if r["size_range"]["stated"]]
    sizes = {
        "measurable": bool(sized),
        "sized_listings": len(sized),
        "stated": len(stated_sizes),
        "silent": len(sized) - len(stated_sizes),
        "limited": sum(1 for r in stated_sizes if r["size_range"]["limited"]),
        "threshold": deliverable.LIMITED_SIZES_AT_OR_BELOW,
        "reason": ("no observed listing is in a department where size is a variable, so a "
                   "size range is not a weakness this catalogue can have"
                   if not sized else ""),
    }

    # Bundles, read from the incumbent's own title: a listing that counts its patterns is
    # selling a set. A department where nothing does is one where the buyer who wants two
    # has to buy twice, which is an opening rather than a fact about us.
    bundled = [r for r in listings if pods.counts_its_own_patterns(r["title"])]
    bundles = {
        "measurable": True,
        "bundled": len(bundled),
        "share": round(len(bundled) / len(listings), 3),
    }

    return {
        "measurable": True,
        "listings": len(listings),
        "thin_media": [{"ref": r["ref"], "media_count": r["media_count"]} for r in thin],
        "thin_media_share": round(len(thin) / len(listings), 3),
        "video": video,
        "complaints": complaints,
        "deliverable": {**clarity, "refs": unclear_refs[:50]},
        "sizes": sizes,
        "bundles": bundles,
        "signals": WEAKNESS_SIGNALS,
        "needs_vision": NEEDS_VISION,
        "note": (f"{len(thin)} of {len(listings)} observed listings carry fewer than "
                 f"{THIN_MEDIA_BELOW} images, which is fewer than a buyer needs to judge a "
                 f"pattern they will never hold. Video and recurring complaints are "
                 f"measured where they have been observed and report unmeasurable where "
                 f"they have not. Deliverable clarity is now read too: "
                 f"{clarity.get('unclear', 0)} of {clarity.get('read', 0)} descriptions "
                 f"read state fewer than "
                 f"{int(deliverable.UNCLEAR_BELOW * 100)}% of the facts that apply to them, "
                 f"and a description nobody has read is excluded rather than counted "
                 f"unclear"),
    }


# ---------------------------------------------------------------------------
# Scoring from what has actually been observed
#
# score_market() is a pure function and was never called with anything. A scorer nobody feeds
# is the same defect as a credential nobody has used: the capability is present, the
# arithmetic is right, and it has never once produced a number about this business. What
# follows feeds it the four dimensions first-party observation genuinely supports, leaves the
# other five named and empty, and says plainly which shop's catalogue every number came from.

# The dimensions an observed benchmark catalogue can honestly fill.
OBSERVED_DIMENSIONS = ("demand", "offer_quality", "price_and_aov", "verifiability")

# Below this many observed listings a department's medians are one or two sellers' decisions
# rather than a department, and normalising them against other pods gives them a weight they
# have not earned.
MIN_LISTINGS_TO_SCORE = 5


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return 0.0
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _relative(value: float, ceiling: float) -> float | None:
    """A pod's value against the strongest pod observed. None when there is no ceiling.

    Relative on purpose, and named as such everywhere it surfaces. There is no absolute
    scale for "how much demand" that this company has access to, and inventing one would be
    the neutral-default failure wearing a different hat.
    """
    if ceiling <= 0:
        return None
    return max(0.0, min(1.0, value / ceiling))


def _opportunity(hunt: dict) -> float | None:
    """How weak the incumbents are here, oriented so that weaker is a higher number.

    `offer_quality` is a lower-is-better dimension and score_market() takes values already
    oriented, so what is passed is the opening, not the quality. Only the signals that were
    actually measurable contribute; a signal nobody could read leaves this average rather
    than entering it as zero weakness, which would read as a strong incumbent.
    """
    openings: list[float] = []
    if hunt.get("listings"):
        openings.append(hunt["thin_media_share"])
    clarity = hunt.get("deliverable") or {}
    if clarity.get("measurable"):
        openings.append(clarity["unclear_share"])
    video = hunt.get("video") or {}
    if video.get("measurable") and video.get("share") is not None:
        openings.append(1.0 - video["share"])
    sizes = hunt.get("sizes") or {}
    if sizes.get("measurable") and sizes.get("stated"):
        openings.append(sizes["limited"] / sizes["stated"])
    bundles = hunt.get("bundles") or {}
    if bundles.get("measurable"):
        openings.append(1.0 - bundles["share"])
    if not openings:
        return None
    return round(sum(openings) / len(openings), 4)


def _buildable_share(db, pod: str, benchmark_key: str) -> float | None:
    """The share of this department's observed forms the compiler can actually build.

    `verifiability` asks whether a pattern here can be machine-checked, and the honest
    answer is a property of the forms this department contains, read from listings somebody
    observed rather than from a table of what a hat pod is.
    """
    from ..creative.family import FORM_CONSTRUCTIONS
    from ..creative.prospecting import arena_forms

    forms = arena_forms(db, pod, benchmark_key=benchmark_key)
    counts = forms.get("forms") or {}
    total = sum(counts.values())
    if not total:
        return None
    buildable = sum(n for form, n in counts.items() if FORM_CONSTRUCTIONS.get(form))
    return round(buildable / total, 4)


def score_observed(db, *, benchmark_key: str = "") -> dict:
    """Score every observed department on the dimensions observation supports.

    This is #2's scoring half actually run, rather than available. Four of the nine
    dimensions are filled -- demand, the opening in the incumbents' offers, what the market
    charges, and whether the construction can be machine-checked -- which is 52% of the
    weight, above the floor and comparable across departments because every department is
    scored from the same source. The other five are named: listing density needs more than
    one catalogue, season timing belongs to a chosen occasion, differentiation is a claim
    about us rather than them, and the last two need orders.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = [{"pod": r.pod, "price_cad": r.price_cad,
                 "favourites": (r.detail or {}).get("num_favorers")}
                for r in s.scalars(select(BenchmarkListing).where(
                    BenchmarkListing.benchmark_key == benchmark_key))]

    by_pod: dict[str, list[dict]] = {}
    for row in rows:
        if row["pod"]:
            by_pod.setdefault(row["pod"], []).append(row)

    eligible = {pod: rs for pod, rs in by_pod.items()
                if len(rs) >= MIN_LISTINGS_TO_SCORE}
    too_thin = sorted(pod for pod in by_pod if pod not in eligible)
    if not eligible:
        return {
            "benchmark": benchmark_key, "scored": [], "ranking": None,
            "measurable": False,
            "reason": (f"no observed department carries {MIN_LISTINGS_TO_SCORE} listings, so "
                       f"every median would be one or two sellers' decisions rather than a "
                       f"department"),
            "departments_too_thin_to_score": too_thin,
        }

    raw: dict[str, dict] = {}
    for pod, rs in eligible.items():
        favourites = [float(r["favourites"]) for r in rs if r["favourites"] is not None]
        prices = [float(r["price_cad"]) for r in rs if r["price_cad"]]
        raw[pod] = {
            "listings": len(rs),
            "median_favourites": _median(favourites) if favourites else None,
            "median_price_cad": round(_median(prices), 2) if prices else None,
            "opportunity": _opportunity(weakness_hunt(db, pod=pod)),
            "buildable_share": _buildable_share(db, pod, benchmark_key),
        }

    favourite_ceiling = max((v["median_favourites"] or 0.0) for v in raw.values())
    price_ceiling = max((v["median_price_cad"] or 0.0) for v in raw.values())

    scored = []
    for pod in sorted(raw):
        measured = raw[pod]
        values: dict[str, float] = {}
        if measured["median_favourites"] is not None:
            demand = _relative(measured["median_favourites"], favourite_ceiling)
            if demand is not None:
                values["demand"] = demand
        if measured["median_price_cad"] is not None:
            price = _relative(measured["median_price_cad"], price_ceiling)
            if price is not None:
                values["price_and_aov"] = price
        if measured["opportunity"] is not None:
            values["offer_quality"] = measured["opportunity"]
        if measured["buildable_share"] is not None:
            values["verifiability"] = measured["buildable_share"]
        card = score_market(pod, values=values)
        card["observed"] = measured
        scored.append(card)

    # The ranking is refused rather than caveated when the departments were scored at
    # different confidences -- the existing rule, reported here as data because this is an
    # endpoint and an exception would read as an outage.
    ranking, refused = None, ""
    try:
        ranking = rank(scored)
    except ArbitrageRefused as e:
        refused = str(e)

    return {
        "benchmark": benchmark_key,
        "measurable": True,
        "scored": scored,
        "ranking": ranking,
        "ranking_refused": refused,
        "departments_too_thin_to_score": too_thin,
        "relative_to": {
            "median_favourites": favourite_ceiling,
            "median_price_cad": price_ceiling,
            "what_this_means": ("demand and price are each a department's median against the "
                                "strongest department in the one catalogue observed. There is "
                                "no absolute scale for either that this company can reach, "
                                "and inventing one would be the neutral-default failure "
                                "wearing a different hat"),
        },
        "note": ("Scored from one benchmark catalogue. That is first-party evidence about "
                 "where a proven seller concentrates and what it charges, and it is not the "
                 "whole market -- which is why listing density stays unmeasured rather than "
                 "being taken from a single shop's shelf space"),
    }


def state(db, *, pod: str = "") -> dict:
    """What this company can currently score, and what each missing dimension waits on.

    `pod` narrows the weakness hunt to one department, which is how it is actually used: a
    weakness averaged over twelve departments is nobody's opening. The dimensions themselves
    are the same either way.
    """
    hunt = weakness_hunt(db, pod=pod)
    return {
        "pod": pod,
        "dimensions": [{"dimension": d.key, "what": d.what, "weight": d.weight,
                        "needs": d.needs} for d in DIMENSIONS],
        "weakness_hunt": hunt,
        "score_floor": SCORE_FLOOR,
        "comparable_within": COMPARABLE_WITHIN,
        "note": ("An unmeasured dimension leaves the arithmetic and is named. Filling it "
                 "with a neutral value keeps the number's shape and loses its meaning, and "
                 "nobody can tell by looking (#2)."),
    }
