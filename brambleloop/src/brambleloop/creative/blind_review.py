"""The competitive blind review: the row `visual.parity` reads, written at last (#75, #71).

`visual/parity.py`'s eighth dimension reads an `AuditLog` row with action
`creative.blind_review` carrying `slug` and `materially_inferior`. Until this module existed
nothing in the codebase wrote one. So the COMPETITIVE dimension read `unjudged` on every
publish attempt, and the note beside #75 called that "draining" -- it was not draining, it
was unwritten. A reader with no writer is a gate that can never open, and six requirements
(#71, #67, #76, #218, #315, #126) hung on the same missing row.

This is the writer. It is deterministic on purpose: it judges what this company's listing
renders *are* against what the category-matched benchmark galleries *were observed to be*,
on the closed observation vocabulary a vision model already recorded and paid for. No model is
asked a second question here. The comparison is between facts on file:

  ours     the frames `publish.listing_asset.frames_for` returns -- role, whether the frame
           reads at Etsy search-thumbnail scale, whether the hero was described as finished
  theirs   `BenchmarkObservation` rows of kind `gallery_image_observation` for listings in
           the same pod, plus the API facts the deep audit stored (image count, video)

Three rules, each against a way this verdict could be flattered:

**Absent observations are UNKNOWN, never PASS.** A pod nobody has looked at cannot be a pod
we compare well in. `materially_inferior` is written as `None`, which `parity` reads as "the
comparison did not reach a verdict" -- which blocks. The same for a product with no render on
file: nothing to compare is not a comparison that went well.

**Every verdict cites its evidence.** Observation ids and dates, listing refs, and the frame
record it judged. A verdict whose evidence cannot be pointed at is an opinion with a schema.

**The vocabulary is the recorded one.** The dimensions below map onto `vision.OBSERVATION_FIELDS`
and the API facts, and nothing is inferred from a title or a hunch. Where a dimension cannot
be judged from what is on file it is `unjudged` and named; it never averages into the others.

Competitor observations are merchandising intelligence: what kind of shots, how many, whether
video. Nothing here reads, stores or reproduces a competitor's photograph or design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

ACTION = "creative.blind_review"
# v2 (2026-09-27, certification C-44/C-45): the comparison is made against the dated,
# category-matched benchmark set (`intel.benchmark_set.build`) and refuses a stale or thin
# one; #67's missing dimensions (finished-result clarity, information density, consistency,
# visual polish, physical proof) are compared; the #218 MJs challenge dimensions are carried
# by name; and the reader takes this product's own newest row, refusing one older than
# `MAX_REVIEW_AGE_DAYS`.
METHOD_VERSION = 2

# A review is a reading of the frames and the benchmark as they were on the day it ran. The
# cadence runs daily; a row older than this is a record of a listing that may no longer
# exist in that form, and parity does not read it as a current comparison (C-45).
MAX_REVIEW_AGE_DAYS = 7

INFERIOR = "inferior"
NOT_INFERIOR = "not_inferior"
UNKNOWN = "unknown"

# Below this many judged images in a pod the benchmark side is one photographer's decisions
# about one or two galleries, not a category standard. Reported as UNKNOWN rather than as a
# thin standard, because a thin standard is easy to clear.
MIN_OBSERVATIONS = 6
MIN_LISTINGS = 3

# Fewer than this many dimensions judged and the review has not compared enough to say
# anything. UNKNOWN, with the unjudged dimensions named.
MIN_DIMENSIONS_JUDGED = 3

# Behind on this many judged dimensions is material. Behind on thumbnail readability alone is
# material too, because that is where the buying decision starts.
MATERIAL_BEHIND = 2
DECISIVE = "thumbnail_readability"

# The comparison vocabulary. Each names the recorded field or API fact it is read from on
# their side and the frame field on ours, so the two sides are compared on one thing.
DIMENSIONS: dict[str, dict] = {
    "thumbnail_readability": {
        "theirs": "vision: thumbnail_readability",
        "ours": "frame: readable_at_grid",
        "what": "whether the frame reads at Etsy search-thumbnail scale",
    },
    "gallery_depth": {
        "theirs": "api: media_count of judged listings",
        "ours": "frame count on file",
        "what": "how many frames a buyer gets to judge a pattern they cannot hold",
    },
    "shot_variety": {
        "theirs": "vision: distinct shot_type per listing",
        "ours": "distinct declared frame roles",
        "what": "how many different jobs the gallery's frames do",
    },
    "detail_coverage": {
        "theirs": "vision: detail_macro shot_type or detail_coverage",
        "ours": "a frame with role detail",
        "what": "whether the stitch work is shown close enough to trust",
    },
    "video": {
        "theirs": "api: has_video on audited listings",
        "ours": "no video path exists",
        "what": "whether the technique is shown moving",
    },
    # #67's remaining dimensions. Each reads a recorded observation field on their side and
    # a recorded frame fact on ours; where either side has nothing on file it is unjudged.
    "finished_result_clarity": {
        "theirs": "vision: product_visibility",
        "ours": "hero inspection: finished_or_in_progress_agrees",
        "what": "whether the hero shows the finished object at a glance",
    },
    "information_density": {
        "theirs": "vision: infographic_use / typography",
        "ours": "information-card frames on file (listing_assets INFOGRAPHIC / PATTERN_PREVIEW)",
        "what": "whether the gallery teaches size, materials and contents with cards",
    },
    "consistency": {
        "theirs": "vision: brand_coherence",
        "ours": "one identity pack and one pattern version across the frames",
        "what": "whether the gallery reads as one shop and one product",
    },
    "visual_polish": {
        "theirs": "vision: composition / setting",
        "ours": "photographic_realism verdicts on the frames",
        "what": "lighting, composition and material realism",
    },
    "physical_proof": {
        "theirs": "not recorded: the vocabulary does not ask whether an image is a photograph",
        "ours": "commerce.buyer_trust image provenance: a physical photograph on file",
        "what": "a photograph of a real finished object made from the pattern",
    },
}

# The #218 MJs challenge gate names its own eight dimensions. Each maps onto the comparison
# row that carries its evidence, or onto a recorded benchmark field that no reading of our
# frames exists for -- in which case it is unjudged and says which judge would be needed.
CHALLENGE: dict[str, dict] = {
    "concept_desirability": {"row": None, "theirs_field": "aesthetic_currency",
                             "needs": "a blinded judged reading of our concept (#126 grid "
                                      "panel); no reading of our frames exists"},
    "distinctiveness": {"row": None, "theirs_field": "silhouette_strength",
                        "needs": "a blinded judged reading of our concept (#126 grid panel)"},
    "product_clarity": {"row": "finished_result_clarity"},
    "thumbnail_strength": {"row": "thumbnail_readability"},
    "styling": {"row": "visual_polish"},
    "apparent_craftsmanship": {"row": "detail_coverage"},
    "giftability": {"row": None, "theirs_field": "gift_narrative",
                    "needs": "a blinded judged reading of our gift narrative (#126 grid "
                             "panel); no reading of our frames exists"},
    "purchase_confidence": {"row": "information_density"},
}

# Asset classes of the deterministic listing frames that are information cards.
CARD_CLASSES: tuple[str, ...] = ("INFOGRAPHIC", "PATTERN_PREVIEW")

# How our declared frame roles map onto the recorded shot vocabulary, for shot_variety.
ROLE_SHOT: dict[str, str] = {
    "hero": "hero_product_only", "fit": "full_fit", "detail": "detail_macro",
    "chart": "infographic", "flat": "flat_lay", "scale": "scale_reference",
    "in_use": "in_use", "three_quarter": "three_quarter", "process": "process",
}

# Words in a recorded thumbnail_readability phrase that read as the frame *not* working at
# grid scale. A short closed reading of a short closed phrase; nothing is inferred beyond it.
NEGATIVE_MARKERS: tuple[str, ...] = (
    "not ", "unreadable", "poor", "weak", "low", "unclear", "cluttered", "busy",
    "hard to", "difficult", "illegible", "lost", "muddy",
)


class ReviewRefused(ValueError):
    """A review asked to compare against something it may not, or nothing at all."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def reads_negative(phrase: str) -> bool:
    text = f" {str(phrase or '').strip().lower()} "
    return any(marker in text for marker in NEGATIVE_MARKERS)


def _median(values: list[float]) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


# ---------------------------------------------------------------------------
# Their side: the category standard, from recorded observations


@dataclass
class Standard:
    """What the observed galleries in one pod were seen to be, with the rows that say so."""

    pod: str
    benchmark_key: str
    listings: int = 0
    observations: int = 0
    observation_ids: list[int] = field(default_factory=list)
    listing_refs: list[str] = field(default_factory=list)
    oldest: str | None = None
    newest: str | None = None
    thumbnail_reads: list[str] = field(default_factory=list)
    thumbnail_positive_share: float | None = None
    median_media_count: float | None = None
    median_distinct_shots: float | None = None
    detail_share: float | None = None
    video_share: float | None = None
    video_audited: int = 0
    prominence_positive_share: float | None = None
    cards_positive_share: float | None = None
    brand_positive_share: float | None = None
    polish_positive_share: float | None = None
    challenge_reads: dict = field(default_factory=dict)

    @property
    def sufficient(self) -> bool:
        return self.observations >= MIN_OBSERVATIONS and self.listings >= MIN_LISTINGS

    def to_dict(self) -> dict:
        return {
            "pod": self.pod, "benchmark": self.benchmark_key,
            "listings_judged": self.listings, "observations": self.observations,
            "sufficient": self.sufficient,
            "minimums": {"observations": MIN_OBSERVATIONS, "listings": MIN_LISTINGS},
            "observation_ids": self.observation_ids[:200],
            "listing_refs": self.listing_refs[:100],
            "oldest_evidence": self.oldest, "newest_evidence": self.newest,
            "thumbnail_positive_share": self.thumbnail_positive_share,
            "thumbnail_reads": self.thumbnail_reads[:40],
            "median_media_count": self.median_media_count,
            "median_distinct_shots": self.median_distinct_shots,
            "detail_share": self.detail_share,
            "video_share": self.video_share, "video_audited": self.video_audited,
            "prominence_positive_share": self.prominence_positive_share,
            "cards_positive_share": self.cards_positive_share,
            "brand_positive_share": self.brand_positive_share,
            "polish_positive_share": self.polish_positive_share,
            "challenge_reads": {k: v[:10] for k, v in self.challenge_reads.items()},
        }


def standard_for(db, pod: str, *, benchmark_key: str = "") -> Standard:
    """The category standard for one pod, from what a model actually recorded.

    Nothing about a competitor's design reaches this: the observation vocabulary is closed
    to merchandising facts, and only those facts are read.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, BenchmarkObservation
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    standard = Standard(pod=pod, benchmark_key=benchmark_key)

    with db.session() as s:
        listings = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod,
            BenchmarkListing.audit_state != "withdrawn")))
        refs = [row.listing_ref for row in listings]
        if not refs:
            return standard
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind == "gallery_image_observation",
            BenchmarkObservation.listing_ref.in_(refs))))
        media = {row.listing_ref: int(row.media_count or 0) for row in listings}
        video = {row.listing_ref: (row.detail or {}).get("has_video") for row in listings
                 if (row.detail or {}).get("gallery_audited")}

    by_listing: dict[str, list[dict]] = {}
    dates: list[datetime] = []
    for row in rows:
        observation = (row.detail or {}).get("observation") or {}
        if not observation:
            continue
        by_listing.setdefault(row.listing_ref, []).append(observation)
        standard.observation_ids.append(int(row.id))
        if row.at is not None:
            dates.append(_aware(row.at))

    standard.observations = sum(len(v) for v in by_listing.values())
    standard.listings = len(by_listing)
    standard.listing_refs = sorted(by_listing)
    if dates:
        standard.oldest = min(dates).isoformat()
        standard.newest = max(dates).isoformat()
    if not by_listing:
        return standard

    reads = [str(o.get("thumbnail_readability")) for obs in by_listing.values()
             for o in obs if o.get("thumbnail_readability")]
    standard.thumbnail_reads = reads
    if reads:
        positive = sum(1 for r in reads if not reads_negative(r))
        standard.thumbnail_positive_share = round(positive / len(reads), 3)

    standard.median_media_count = _median(
        [float(media.get(ref, 0)) for ref in by_listing if media.get(ref)])
    standard.median_distinct_shots = _median(
        [float(len({o.get("shot_type") for o in obs if o.get("shot_type")}))
         for obs in by_listing.values()])
    with_detail = sum(
        1 for obs in by_listing.values()
        if any(o.get("shot_type") == "detail_macro" or o.get("detail_coverage")
               for o in obs))
    standard.detail_share = round(with_detail / len(by_listing), 3)

    audited = [ref for ref in by_listing if video.get(ref) is not None]
    standard.video_audited = len(audited)
    if audited:
        standard.video_share = round(
            sum(1 for ref in audited if video[ref]) / len(audited), 3)

    def share(*fields: str) -> float | None:
        reads = [str(o.get(f)) for obs in by_listing.values() for o in obs
                 for f in fields if o.get(f)]
        if not reads:
            return None
        return round(sum(1 for r in reads if not reads_negative(r)) / len(reads), 3)

    standard.prominence_positive_share = share("product_visibility")
    standard.cards_positive_share = share("infographic_use", "typography")
    standard.brand_positive_share = share("brand_coherence")
    standard.polish_positive_share = share("composition", "setting")
    for spec in CHALLENGE.values():
        f = spec.get("theirs_field")
        if f:
            standard.challenge_reads[f] = [str(o.get(f)) for obs in by_listing.values()
                                           for o in obs if o.get(f)]
    return standard


# ---------------------------------------------------------------------------
# Our side: the frames on file


def _realism(frame: dict) -> str | None:
    from ..visual.parity import _realism_of

    got = _realism_of(frame)
    if got is None:
        return None
    return str(got.get("verdict") or "") or None


def our_side(frames: list[dict], *, cards: list[dict] | None = None,
             physical_proof: bool | None = None) -> dict:
    """What this company's listing renders are, read off the asset records.

    `cards` are the deterministic listing frames `assets.build` filed (`ListingAsset` rows);
    `physical_proof` is whether a physical photograph is on file in the image provenance.
    Both None mean nobody looked, which is reported rather than read as zero.
    """
    made = [f for f in frames if f.get("made", True)]
    roles = [str(f.get("role") or "") for f in made]
    grid = [f.get("readable_at_grid") for f in made]
    hero = next((f for f in made if (f.get("role") or "hero") == "hero"), None)
    finished = None
    if hero is not None:
        inspection = hero.get("inspection") or {}
        if inspection.get("described") is True:
            finished = (inspection.get("semantic") or {}).get("finished_or_in_progress_agrees")
    realism = [_realism(f) for f in made]
    if any(r == "blocked" for r in realism):
        polish = False
    elif made and all(r == "clear" for r in realism):
        polish = True
    else:
        polish = None
    modelled = [f for f in made if f.get("carries_model")]
    packs = {(f.get("conditioned_on") or {}).get("pack_version") for f in modelled}
    packs.discard(None)
    versions = {str(f.get("version")) for f in made if f.get("version")}
    if not made:
        consistent = None
    elif len(versions) > 1 or len(packs) > 1:
        consistent = False
    elif modelled and not packs:
        consistent = None
    else:
        consistent = True
    card_rows = None if cards is None else [
        c for c in cards if str(c.get("asset_class") or "") in CARD_CLASSES]
    return {
        "finished_result": finished,
        "polish": polish,
        "consistent": consistent,
        "cards": None if card_rows is None else len(card_rows),
        "card_roles": [] if card_rows is None else [c.get("role") for c in card_rows],
        "physical_proof": physical_proof,
        "frames": len(made),
        "roles": roles,
        "distinct_shots": len({ROLE_SHOT.get(r, r) for r in roles if r}),
        "readable_at_grid": grid,
        "all_readable": (True if grid and all(g is True for g in grid)
                         else False if any(g is False for g in grid)
                         else None),
        "has_detail": any(r == "detail" for r in roles),
        "has_video": False,
        "image_refs": [f.get("image_ref") or f.get("image") for f in made][:12],
        "versions": sorted({str(f.get("version")) for f in made if f.get("version")}),
    }


# ---------------------------------------------------------------------------
# The comparison


def _row(state: str, ours, theirs, why: str) -> dict:
    return {"state": state, "ours": ours, "theirs": theirs, "why": why}


def compare(ours: dict, standard: Standard) -> dict:
    """Every dimension judged from evidence, or `unjudged` with what would be needed."""
    rows: dict[str, dict] = {}

    # thumbnail readability -- the decisive one.
    share = standard.thumbnail_positive_share
    if share is None:
        rows[DECISIVE] = _row("unjudged", ours["all_readable"], None,
                              "no observation in this pod recorded thumbnail_readability")
    elif ours["all_readable"] is None:
        rows[DECISIVE] = _row("unjudged", None, share,
                              "at least one of our frames was never checked at grid scale")
    elif ours["all_readable"] is False:
        rows[DECISIVE] = _row("behind", False, share,
                              "a frame of ours does not read in the mobile grid")
    else:
        rows[DECISIVE] = _row("level" if share >= 0.5 else "ahead", True, share,
                              f"every frame of ours reads at grid scale; {share:.0%} of the "
                              f"observed benchmark frames were read as legible")

    # gallery depth
    if standard.median_media_count is None:
        rows["gallery_depth"] = _row("unjudged", ours["frames"], None,
                                     "no judged listing in this pod carries a media count")
    elif ours["frames"] == 0:
        rows["gallery_depth"] = _row("unjudged", 0, standard.median_media_count,
                                     "no frame of ours is on file")
    else:
        state = ("behind" if ours["frames"] < standard.median_media_count
                 else "ahead" if ours["frames"] > standard.median_media_count else "level")
        rows["gallery_depth"] = _row(
            state, ours["frames"], standard.median_media_count,
            f"{ours['frames']} frame(s) against a median of "
            f"{standard.median_media_count:g} images in the observed galleries")

    # shot variety
    if standard.median_distinct_shots is None:
        rows["shot_variety"] = _row("unjudged", ours["distinct_shots"], None,
                                    "no observation in this pod recorded a shot_type")
    elif ours["frames"] == 0:
        rows["shot_variety"] = _row("unjudged", 0, standard.median_distinct_shots,
                                    "no frame of ours is on file")
    else:
        state = ("behind" if ours["distinct_shots"] < standard.median_distinct_shots
                 else "ahead" if ours["distinct_shots"] > standard.median_distinct_shots
                 else "level")
        rows["shot_variety"] = _row(
            state, ours["distinct_shots"], standard.median_distinct_shots,
            f"{ours['distinct_shots']} distinct frame job(s) against a median of "
            f"{standard.median_distinct_shots:g} distinct shot types observed")

    # detail coverage
    if standard.detail_share is None:
        rows["detail_coverage"] = _row("unjudged", ours["has_detail"], None,
                                       "no judged listing in this pod")
    elif ours["frames"] == 0:
        rows["detail_coverage"] = _row("unjudged", None, standard.detail_share,
                                       "no frame of ours is on file")
    elif ours["has_detail"]:
        rows["detail_coverage"] = _row("level" if standard.detail_share >= 0.5 else "ahead",
                                       True, standard.detail_share,
                                       "a detail frame is on file")
    else:
        rows["detail_coverage"] = _row(
            "behind" if standard.detail_share >= 0.5 else "level", False,
            standard.detail_share,
            f"no detail frame of ours; {standard.detail_share:.0%} of the observed "
            f"galleries show the stitch work close")

    # video
    if standard.video_share is None:
        rows["video"] = _row("unjudged", False, None,
                             "no judged listing in this pod has had its video state audited")
    else:
        rows["video"] = _row(
            "behind" if standard.video_share >= 0.5 else "level", False,
            standard.video_share,
            f"this company has no video; {standard.video_share:.0%} of "
            f"{standard.video_audited} audited benchmark listings carry one")

    # finished-result clarity: our hero read as the finished object, against how prominent
    # the product was observed to be in theirs.
    theirs = standard.prominence_positive_share
    mine = ours.get("finished_result")
    if theirs is None or mine is None:
        rows["finished_result_clarity"] = _row(
            "unjudged", mine, theirs,
            "no observation recorded product_visibility" if theirs is None else
            "our hero was never described, so whether it reads as finished is not known")
    else:
        rows["finished_result_clarity"] = _row(
            "behind" if mine is False and theirs >= 0.5 else "level", mine, theirs,
            f"our hero {'reads' if mine else 'does not read'} as the finished object; "
            f"{theirs:.0%} of observed benchmark frames show the product prominently")

    # information density: cards on file against how often theirs teach with cards.
    theirs = standard.cards_positive_share
    cards = ours.get("cards")
    if theirs is None or cards is None:
        rows["information_density"] = _row(
            "unjudged", cards, theirs,
            "no observation recorded infographic_use or typography" if theirs is None else
            "our information cards were not read")
    else:
        state = ("behind" if cards == 0 and theirs >= 0.5 else
                 "ahead" if cards >= 2 and theirs < 0.5 else "level")
        rows["information_density"] = _row(
            state, cards, theirs,
            f"{cards} information card(s) of ours; {theirs:.0%} of observed benchmark "
            f"card/typography reads were positive")

    # consistency: one identity and one version across our frames, against brand coherence.
    theirs = standard.brand_positive_share
    mine = ours.get("consistent")
    if theirs is None or mine is None:
        rows["consistency"] = _row(
            "unjudged", mine, theirs,
            "no observation recorded brand_coherence" if theirs is None else
            "our frames do not record which identity or version they depict")
    else:
        rows["consistency"] = _row(
            "behind" if mine is False else "level", mine, theirs,
            "our frames mix identities or pattern versions" if mine is False else
            "our frames depict one identity and one pattern version")

    # visual polish: our realism verdicts against observed composition/setting.
    theirs = standard.polish_positive_share
    mine = ours.get("polish")
    if theirs is None or mine is None:
        rows["visual_polish"] = _row(
            "unjudged", mine, theirs,
            "no observation recorded composition or setting" if theirs is None else
            "our frames were not all judged against the photography standard")
    else:
        rows["visual_polish"] = _row(
            "behind" if mine is False and theirs >= 0.5 else "level", mine, theirs,
            "a frame of ours reads as generated" if mine is False else
            "every frame of ours reads as believable photography")

    # physical proof: nothing on their side records whether an image is a photograph.
    rows["physical_proof"] = _row(
        "unjudged", ours.get("physical_proof"), None,
        "the observation vocabulary does not record whether a benchmark image is a "
        "photograph of a real object, so this cannot be compared; ours is reported")

    judged = [d for d, r in rows.items() if r["state"] != "unjudged"]
    behind = [d for d, r in rows.items() if r["state"] == "behind"]
    unjudged = [d for d, r in rows.items() if r["state"] == "unjudged"]
    return {"dimensions": rows, "judged": judged, "behind": behind, "unjudged": unjudged}


def challenge(comparison: dict, standard: Standard) -> dict:
    """#218's eight named dimensions, each from its evidence or unjudged with the judge needed.

    Nothing here is scored: a named dimension reads the comparison row that carries its
    evidence. The three that only a judged reading of our own concept could answer
    (desirability, distinctiveness, giftability) carry the benchmark's recorded reads and
    stay unjudged on our side -- a comparison with one side missing has not been made.
    """
    out: dict[str, dict] = {}
    for name, spec in CHALLENGE.items():
        row = spec.get("row")
        if row:
            got = comparison["dimensions"].get(row) or {}
            out[name] = {"state": got.get("state", "unjudged"), "from": row,
                         "why": got.get("why", "")}
        else:
            reads = standard.challenge_reads.get(spec["theirs_field"], [])
            out[name] = {"state": "unjudged", "from": spec["theirs_field"],
                         "theirs_reads": reads[:5], "why": spec["needs"]}
    behind = [n for n, r in out.items() if r["state"] == "behind"]
    return {"dimensions": out, "behind": behind,
            "unjudged": [n for n, r in out.items() if r["state"] == "unjudged"]}


def verdict_of(comparison: dict, standard: Standard, ours: dict) -> tuple[str, bool | None, str]:
    """(verdict, materially_inferior, why). `None` is UNKNOWN, and UNKNOWN is never a pass."""
    if not standard.sufficient:
        return (UNKNOWN, None,
                f"{standard.observations} judged image(s) across {standard.listings} "
                f"listing(s) in pod {standard.pod!r}, below the floor of "
                f"{MIN_OBSERVATIONS} images and {MIN_LISTINGS} listings. A comparison "
                f"against a standard nobody has observed is not a comparison that went well")
    if ours["frames"] == 0:
        return (UNKNOWN, None,
                "no listing render of ours is on file for this product, so there is nothing "
                "to compare. Nothing to compare is not a favourable comparison")
    if len(comparison["judged"]) < MIN_DIMENSIONS_JUDGED:
        return (UNKNOWN, None,
                f"only {len(comparison['judged'])} of {len(DIMENSIONS)} dimensions could be "
                f"judged from what is on file (unjudged: {comparison['unjudged']}); below "
                f"{MIN_DIMENSIONS_JUDGED} the review has not compared enough to say")
    behind = comparison["behind"]
    if DECISIVE in behind or len(behind) >= MATERIAL_BEHIND:
        return (INFERIOR, True,
                f"materially inferior: behind on {behind} against {standard.listings} "
                f"observed {standard.pod} listings ({standard.observations} judged images, "
                f"{standard.oldest} to {standard.newest})")
    return (NOT_INFERIOR, False,
            f"not materially inferior: behind on {behind or 'nothing'} of "
            f"{len(comparison['judged'])} judged dimensions against {standard.listings} "
            f"observed {standard.pod} listings ({standard.observations} judged images, "
            f"{standard.oldest} to {standard.newest})")


# ---------------------------------------------------------------------------
# Products, pods, and the review itself


def pod_for(slug: str, title: str = "") -> str:
    """The pod our product is judged in, by the same router the benchmark listings use.

    Same router on both sides so "category-matched" means one thing. Falls back to the
    concept the catalogue records when the title routes nowhere.
    """
    from ..intel import pods

    routed = pods.route(title) if title else pods.UNCLASSIFIED
    if routed != pods.UNCLASSIFIED:
        return routed
    try:
        from .audit import catalogue_concepts

        for concept in catalogue_concepts():
            if concept.key == slug:
                return concept.pod
    except Exception:  # noqa: BLE001 - the catalogue is a convenience, not evidence
        pass
    return pods.UNCLASSIFIED


def _cards_on_file(db, slug: str) -> list[dict] | None:
    """The deterministic listing frames `assets.build` filed for this product, newest version."""
    from sqlalchemy import select

    from ..core.models import ListingAsset

    with db.session() as s:
        rows = [{"asset_class": r.asset_class, "role": r.role, "version": r.version,
                 "position": r.position}
                for r in s.scalars(select(ListingAsset).where(
                    ListingAsset.product_slug == slug))]
    if not rows:
        return None
    newest = max(r["version"] for r in rows)
    return [r for r in rows if r["version"] == newest]


def _physical_proof_on_file(db, slug: str) -> bool | None:
    from ..commerce import buyer_trust

    try:
        return buyer_trust.gallery_proof_on_file(db, slug=slug)["has_physical_proof_reading"]
    except Exception:  # noqa: BLE001 - provenance unreadable is not "no proof"
        return None


def current_set(db, pod: str, *, benchmark_key: str = "", now: datetime | None = None) -> dict:
    """#76: the dated, category-matched benchmark set this review compares against.

    Built by `intel.benchmark_set.build`, the Creative Director's set. A thin set is refused
    by the builder and a stale one (#67 asks for a *current* sample) is refused here; both
    come back as `usable: False` with the reason, which the review writes as UNKNOWN.
    """
    from ..intel import benchmark_set

    try:
        built = benchmark_set.build(db, pod, benchmark_key=benchmark_key, now=now)
    except benchmark_set.SetRefused as exc:
        return {"usable": False, "refused": "thin", "why": str(exc), "pod": pod}
    summary = {k: built.get(k) for k in ("pod", "benchmark", "built_at", "listings",
                                         "observations", "oldest_evidence", "newest_evidence",
                                         "age_days", "current", "stale_after_days",
                                         "measured", "unmeasured")}
    if not built.get("current"):
        return {"usable": False, "refused": "stale", "set": summary, "built": built,
                "why": (f"the {pod!r} benchmark set's newest evidence is "
                        f"{built.get('newest_evidence')} ({built.get('age_days')} days old), "
                        f"past {built.get('stale_after_days')} days. #67 and #76 ask for a "
                        f"current sample; last season's galleries are not one")}
    return {"usable": True, "set": summary, "built": built}


def review(db, *, slug: str, title: str = "", pod: str = "", frames: list[dict] | None = None,
           benchmark_key: str = "", now: datetime | None = None,
           cards: list[dict] | None = None, physical_proof: bool | None = None) -> dict:
    """One product's competitive blind review, from evidence on file. Never renders.

    Compared against the dated benchmark set `intel.benchmark_set.build` assembles for the
    product's pod (#76); a thin or stale set is refused and the review is UNKNOWN (#67).
    """
    from ..publish import listing_asset

    now = now or _utcnow()
    pod = pod or pod_for(slug, title)
    reading_db = frames is None
    frames = listing_asset.frames_for(db, slug=slug) if frames is None else list(frames)
    if cards is None and reading_db:
        cards = _cards_on_file(db, slug)
    if physical_proof is None and reading_db:
        physical_proof = _physical_proof_on_file(db, slug)
    ours = our_side(frames, cards=cards, physical_proof=physical_proof)
    standard = standard_for(db, pod, benchmark_key=benchmark_key)
    bench = current_set(db, pod, benchmark_key=benchmark_key, now=now)
    comparison = compare(ours, standard)
    verdict, inferior, why = verdict_of(comparison, standard, ours)
    if verdict != UNKNOWN and not bench["usable"]:
        # The standard cleared its floors but the set is not a current sample: a comparison
        # against it is a comparison against the past, and it is not written as a verdict.
        verdict, inferior, why = UNKNOWN, None, bench["why"]
    set_comparison = None
    if bench["usable"]:
        from ..intel import benchmark_set

        try:
            set_comparison = benchmark_set.compare_listing_set(frames, bench["built"])
        except benchmark_set.SetRefused as exc:  # pragma: no cover - usable means current
            set_comparison = {"refused": str(exc)}
    trial = challenge(comparison, standard)
    return {
        "slug": slug,
        "pod": pod,
        "verdict": verdict,
        "materially_inferior": inferior,
        "why": why,
        "reviewed_at": now.isoformat(),
        "method_version": METHOD_VERSION,
        "ours": ours,
        "standard": standard.to_dict(),
        "benchmark_set": {k: v for k, v in bench.items() if k != "built"},
        "benchmark_set_comparison": set_comparison,
        "comparison": comparison,
        "mjs_challenge": trial,
        # #218: obviously inferior beside the MJs set goes back to creative development
        # rather than shipping. The handler acts on this; the review only states it.
        "returns_to_development": inferior is True,
        "evidence": {
            "observation_ids": standard.observation_ids[:200],
            "observation_dates": {"oldest": standard.oldest, "newest": standard.newest},
            "listing_refs": standard.listing_refs[:100],
            "our_frames": ours["frames"],
            "our_image_refs": ours["image_refs"],
        },
        "never": ("a second model question, a title inference, or a favourable default. "
                  "UNKNOWN blocks exactly as inferior does (#75)"),
    }


def record(db, result: dict, *, actor: str = "creative_director",
           job_id: int | None = None) -> int:
    """Write the row `visual.parity` reads. Refuses a result without the two fields it needs."""
    from ..core.models import AuditLog

    if not result.get("slug") or "materially_inferior" not in result:
        raise ReviewRefused(
            "a blind review row must carry `slug` and `materially_inferior`, because that "
            "is what runtime.pipeline._benchmark_quality reads")
    with db.session() as s:
        row = AuditLog(actor=actor, action=ACTION, artifact=result["slug"], job_id=job_id,
                       detail=dict(result))
        s.add(row)
        s.flush()
        return int(row.id)


def catalogue_slugs() -> list[tuple[str, str]]:
    """(slug, title) for every product this company would list."""
    from ..products.builder import CATALOGUE

    return [(design.slug, design.title) for design in CATALOGUE.values()]


def run(db, *, slugs: list[tuple[str, str]] | None = None, benchmark_key: str = "",
        job_id: int | None = None, now: datetime | None = None) -> dict:
    """Review every product and write one row each. Free: nothing is rendered or asked."""
    slugs = catalogue_slugs() if slugs is None else list(slugs)
    reviews: list[dict] = []
    for slug, title in slugs:
        result = review(db, slug=slug, title=title, benchmark_key=benchmark_key, now=now)
        result["audit_id"] = record(db, result, job_id=job_id)
        reviews.append(result)
    counts = {v: sum(1 for r in reviews if r["verdict"] == v)
              for v in (INFERIOR, NOT_INFERIOR, UNKNOWN)}
    return {
        "reviewed": len(reviews),
        "counts": counts,
        "reviews": [{k: r[k] for k in ("slug", "pod", "verdict", "materially_inferior",
                                       "why", "audit_id", "returns_to_development")}
                    for r in reviews],
        "method_version": METHOD_VERSION,
        "note": ("Deterministic, from recorded observations and asset records. An UNKNOWN "
                 "here is a pod nobody has judged enough of or a product with no render on "
                 "file; both block release under #75 and neither is a pass"),
    }


def current_review(db, *, slug: str, now: datetime | None = None,
                   max_age_days: int = MAX_REVIEW_AGE_DAYS) -> dict | None:
    """The review parity reads for this product: its own newest row, and only if current.

    Filtered by product in the query, not by scanning a window of recent rows -- a window of
    ten with eleven products in the catalogue left one of them permanently unjudged
    (C-45, reproduced on winter-village-graphghan). A row older than `max_age_days` is
    returned as an UNKNOWN reading that names its age rather than as the verdict it once
    was, so parity blocks on it and says why.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    now = now or _utcnow()
    with db.session() as s:
        row = None
        for candidate in s.scalars(select(AuditLog).where(AuditLog.action == ACTION,
                                                          AuditLog.artifact == slug)
                                   .order_by(desc(AuditLog.id))):
            detail = candidate.detail or {}
            if detail.get("slug", slug) == slug and "materially_inferior" in detail:
                row = candidate
                break
        if row is None:
            return None
        detail = dict(row.detail or {})
        at = _aware(row.at) if row.at is not None else None
    stamp = detail.get("reviewed_at")
    try:
        reviewed = _aware(datetime.fromisoformat(stamp)) if stamp else at
    except (TypeError, ValueError):
        reviewed = at
    if reviewed is None:
        return {**detail, "materially_inferior": None, "stale": True,
                "why": "the blind review on file carries no date, so its currency is unknown"}
    age = (now - reviewed).total_seconds() / 86400.0
    if age > max_age_days:
        return {**detail, "materially_inferior": None, "stale": True,
                "recorded_verdict": detail.get("verdict"),
                "age_days": round(age, 1),
                "why": (f"the newest blind review for {slug} is {age:.0f} days old "
                        f"({reviewed.date().isoformat()}), past {max_age_days}. A comparison "
                        f"of frames and benchmark galleries as they were is not a current "
                        f"comparison (C-45)")}
    return {**detail, "stale": False, "age_days": round(age, 1)}


def last_review(db, *, slug: str) -> dict | None:
    """The most recent row for this product, as parity would read it."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == ACTION,
                                                    AuditLog.artifact == slug)
                             .order_by(desc(AuditLog.id)).limit(1)):
            return dict(row.detail or {})
    return None


def state(db, *, benchmark_key: str = "") -> dict:
    """What the review would say today, per product, without writing anything."""
    slugs = catalogue_slugs()
    reviews = [review(db, slug=slug, title=title, benchmark_key=benchmark_key)
               for slug, title in slugs]
    return {
        "products": len(reviews),
        "counts": {v: sum(1 for r in reviews if r["verdict"] == v)
                   for v in (INFERIOR, NOT_INFERIOR, UNKNOWN)},
        "reviews": reviews,
        "dimensions": DIMENSIONS,
        "minimums": {"observations": MIN_OBSERVATIONS, "listings": MIN_LISTINGS,
                     "dimensions_judged": MIN_DIMENSIONS_JUDGED,
                     "material_behind": MATERIAL_BEHIND, "decisive": DECISIVE},
        "last_recorded": {slug: last_review(db, slug=slug) for slug, _ in slugs},
        "runs_on": "the daily `blind_review` cadence (creative.blind_review); free",
    }
