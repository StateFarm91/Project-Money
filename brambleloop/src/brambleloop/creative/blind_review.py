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
METHOD_VERSION = 1

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
}

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
    return standard


# ---------------------------------------------------------------------------
# Our side: the frames on file


def our_side(frames: list[dict]) -> dict:
    """What this company's listing renders are, read off the asset records."""
    made = [f for f in frames if f.get("made", True)]
    roles = [str(f.get("role") or "") for f in made]
    grid = [f.get("readable_at_grid") for f in made]
    return {
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

    judged = [d for d, r in rows.items() if r["state"] != "unjudged"]
    behind = [d for d, r in rows.items() if r["state"] == "behind"]
    unjudged = [d for d, r in rows.items() if r["state"] == "unjudged"]
    return {"dimensions": rows, "judged": judged, "behind": behind, "unjudged": unjudged}


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


def review(db, *, slug: str, title: str = "", pod: str = "", frames: list[dict] | None = None,
           benchmark_key: str = "", now: datetime | None = None) -> dict:
    """One product's competitive blind review, from evidence on file. Never renders."""
    from ..publish import listing_asset

    pod = pod or pod_for(slug, title)
    frames = listing_asset.frames_for(db, slug=slug) if frames is None else list(frames)
    ours = our_side(frames)
    standard = standard_for(db, pod, benchmark_key=benchmark_key)
    comparison = compare(ours, standard)
    verdict, inferior, why = verdict_of(comparison, standard, ours)
    now = now or _utcnow()
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
        "comparison": comparison,
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
                                       "why", "audit_id")} for r in reviews],
        "method_version": METHOD_VERSION,
        "note": ("Deterministic, from recorded observations and asset records. An UNKNOWN "
                 "here is a pod nobody has judged enough of or a product with no render on "
                 "file; both block release under #75 and neither is a pass"),
    }


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
