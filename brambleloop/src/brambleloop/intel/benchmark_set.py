"""The dated, category-matched benchmark set per pod (#76), and the release comparison (#67).

#76 asks the Creative Director to maintain a *dated* benchmark set of strong legitimate
listings in each target micro-market -- wearables against wearables, blankets against
comparable blankets -- on ten named dimensions. #67 asks that the listing set be compared
against a *current* sample of that set on measurable dimensions before release.

Both notes said "needs browser/vision". The vision half has been recording gallery
observations since 2026-09-20; nothing had assembled them into a set anybody could point at.
This does, from three sources and no invention:

  market_map     the pod routing, and the rule that a judgement column is absent rather than
                 inferred from a title
  vision         the recorded per-image observations, on the closed vocabulary, each with the
                 date it was made
  the deep audit image count, video presence and palette, which Etsy's API states outright

**A set below its minimum is refused, not thinned.** A benchmark set of two listings is one
seller's two decisions, and comparing against it is comparing against noise. `build` raises
`SetRefused` below `MIN_OBSERVATIONS` judged images or `MIN_LISTINGS` judged listings, and
`all_pods` reports the refusal per pod rather than papering it into an empty set.

**Every dimension names where it came from, or that it cannot.** Two of the ten -- realism
and lighting -- have no recorded field: the observation vocabulary does not ask about them,
and a benchmark photograph's realism is not in question anyway. They are carried as
`unmeasured` with the reason, because a ten-dimension set reported as eight is the averaging
#75 warns against, one file over.

**Dated, and stale by its own admission.** Every set carries the oldest and newest observation
it was built from and says whether that is inside `STALE_AFTER_DAYS`. #76 says "current";
a set that cannot say how current it is cannot claim to be.

Nothing here stores a competitor image, description or design. Reads are merchandising facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Floors. Below these a set is refused rather than built thin.
MIN_OBSERVATIONS = 6
MIN_LISTINGS = 3

# A benchmark set older than this is a historical record, not a current sample (#67, #76).
STALE_AFTER_DAYS = 45

UNMEASURED = "unmeasured"
MEASURED = "measured"

# The ten dimensions #76 names, each with where it is read from. `fields` are recorded
# observation fields; `api` is a deep-audit fact; `None` is honestly unmeasured.
DIMENSIONS: dict[str, dict] = {
    "thumbnail_clarity": {"fields": ("thumbnail_readability",), "api": None,
                          "what": "whether the hero reads at search-thumbnail scale"},
    "realism": {"fields": (), "api": None,
                "what": "photographic realism -- a benchmark photograph is one; not asked"},
    "styling": {"fields": ("setting", "emotional_merchandising"), "api": None,
                "what": "how the scene is dressed and what it makes the buyer feel"},
    "crop": {"fields": ("composition",), "api": None,
             "what": "how the frame is cut around the object"},
    "lighting": {"fields": (), "api": None,
                 "what": "light quality -- the vocabulary does not record it; not asked"},
    "product_prominence": {"fields": ("product_visibility", "scale_communication"),
                           "api": None, "what": "how much of the frame the product owns"},
    "gallery_storytelling": {"fields": ("shot_type",), "api": "media_count",
                             "what": "the sequence of jobs the gallery's frames do"},
    "information_cards": {"fields": ("infographic_use", "typography"), "api": None,
                          "what": "whether the gallery teaches with cards"},
    "video_support": {"fields": (), "api": "has_video",
                      "what": "whether the technique is shown moving"},
    "brand_consistency": {"fields": ("brand_coherence",), "api": None,
                          "what": "whether the set reads as one shop"},
}


class SetRefused(ValueError):
    """A benchmark set below its stated minimum, or for a pod nothing was observed in."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class Member:
    """One listing in the set, with its dated evidence and nothing protected."""

    listing_ref: str
    pod: str
    observed_dates: list[str] = field(default_factory=list)
    observation_ids: list[int] = field(default_factory=list)
    images_judged: int = 0
    media_count: int = 0
    has_video: bool | None = None
    palette_present: bool = False
    reads: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "listing_ref": self.listing_ref, "pod": self.pod,
            "observed_dates": self.observed_dates, "observation_ids": self.observation_ids,
            "images_judged": self.images_judged, "media_count": self.media_count,
            "has_video": self.has_video, "palette_present": self.palette_present,
            "reads": self.reads,
        }


def _members(db, pod: str, benchmark_key: str) -> list[Member]:
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, BenchmarkObservation

    with db.session() as s:
        listings = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key,
            BenchmarkListing.pod == pod,
            BenchmarkListing.audit_state != "withdrawn")))
        refs = [row.listing_ref for row in listings]
        rows = list(s.scalars(select(BenchmarkObservation).where(
            BenchmarkObservation.benchmark_key == benchmark_key,
            BenchmarkObservation.kind == "gallery_image_observation",
            BenchmarkObservation.listing_ref.in_(refs)))) if refs else []
        facts = {row.listing_ref: {
            "media_count": int(row.media_count or 0),
            "has_video": ((row.detail or {}).get("has_video")
                          if (row.detail or {}).get("gallery_audited") else None),
            "palette": bool((row.detail or {}).get("palette")),
        } for row in listings}

    members: dict[str, Member] = {}
    for row in rows:
        observation = (row.detail or {}).get("observation") or {}
        if not observation:
            continue
        member = members.get(row.listing_ref)
        if member is None:
            fact = facts.get(row.listing_ref, {})
            member = members[row.listing_ref] = Member(
                listing_ref=row.listing_ref, pod=pod,
                media_count=fact.get("media_count", 0),
                has_video=fact.get("has_video"),
                palette_present=fact.get("palette", False))
        member.images_judged += 1
        member.observation_ids.append(int(row.id))
        if row.at is not None:
            member.observed_dates.append(_aware(row.at).isoformat())
        for name, spec in DIMENSIONS.items():
            for observation_field in spec["fields"]:
                value = str(observation.get(observation_field) or "").strip()
                if value:
                    seen = member.reads.setdefault(name, [])
                    if value not in seen:
                        seen.append(value)
    for member in members.values():
        member.observed_dates.sort()
    return sorted(members.values(), key=lambda m: m.listing_ref)


def _dimension(name: str, members: list[Member]) -> dict:
    spec = DIMENSIONS[name]
    out: dict = {"what": spec["what"], "from_fields": list(spec["fields"]),
                 "from_api": spec["api"]}
    reads: list[str] = []
    listings_with_a_read = 0
    for member in members:
        got = member.reads.get(name) or []
        if got:
            listings_with_a_read += 1
        for value in got:
            if value not in reads:
                reads.append(value)
    if spec["api"] == "has_video":
        audited = [m for m in members if m.has_video is not None]
        if audited:
            out.update({"basis": MEASURED,
                        "video_share": round(sum(1 for m in audited if m.has_video)
                                             / len(audited), 3),
                        "audited": len(audited)})
        else:
            out.update({"basis": UNMEASURED,
                        "reason": "no member's video state has been audited"})
        return out
    if spec["api"] == "media_count":
        counts = sorted(m.media_count for m in members if m.media_count)
        if counts:
            out["median_media_count"] = (
                float(counts[len(counts) // 2]) if len(counts) % 2
                else (counts[len(counts) // 2 - 1] + counts[len(counts) // 2]) / 2.0)
    if not spec["fields"]:
        out.update({"basis": UNMEASURED,
                    "reason": ("the observation vocabulary does not record this; it is "
                               "carried so the set is ten dimensions, not eight")})
        return out
    if not reads:
        out.update({"basis": UNMEASURED,
                    "reason": f"no member's observations recorded {list(spec['fields'])}"})
        return out
    out.update({"basis": MEASURED, "reads": reads[:40],
                "listings_with_a_read": listings_with_a_read})
    return out


def build(db, pod: str, *, benchmark_key: str = "", now: datetime | None = None,
          min_observations: int = MIN_OBSERVATIONS, min_listings: int = MIN_LISTINGS) -> dict:
    """The dated benchmark set for one pod, or a refusal that says why.

    `min_observations` may be raised by a caller and never lowered below the module floor:
    a floor that a call site can step under is a suggestion.
    """
    from . import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    min_observations = max(int(min_observations), MIN_OBSERVATIONS)
    min_listings = max(int(min_listings), MIN_LISTINGS)
    now = now or _utcnow()

    members = _members(db, pod, benchmark_key)
    observations = sum(m.images_judged for m in members)
    if len(members) < min_listings or observations < min_observations:
        raise SetRefused(
            f"pod {pod!r}: {observations} judged image(s) across {len(members)} listing(s), "
            f"below the stated minimum of {min_observations} images and {min_listings} "
            f"listings. A benchmark set this thin is one seller's few decisions, and "
            f"comparing against it would be comparing against noise (#76)")

    dates = sorted(d for m in members for d in m.observed_dates)
    oldest, newest = (dates[0], dates[-1]) if dates else (None, None)
    age_days = ((now - datetime.fromisoformat(newest)).days if newest else None)
    dimensions = {name: _dimension(name, members) for name in DIMENSIONS}
    measured = [n for n, d in dimensions.items() if d["basis"] == MEASURED]
    return {
        "pod": pod,
        "benchmark": benchmark_key,
        "built_at": now.isoformat(),
        "members": [m.to_dict() for m in members],
        "listings": len(members),
        "observations": observations,
        "minimums": {"observations": min_observations, "listings": min_listings},
        "oldest_evidence": oldest,
        "newest_evidence": newest,
        "age_days": age_days,
        "current": age_days is not None and age_days <= STALE_AFTER_DAYS,
        "stale_after_days": STALE_AFTER_DAYS,
        "dimensions": dimensions,
        "measured": measured,
        "unmeasured": [n for n in DIMENSIONS if n not in measured],
        "category_matched": (f"every member routes to pod {pod!r} by the same router our "
                             f"products are routed with; wearables compare with wearables"),
        "never": ("a competitor image, description or design. Reads are merchandising "
                  "facts on a closed vocabulary; the set learns standards, not expression"),
    }


def all_pods(db, *, benchmark_key: str = "", now: datetime | None = None) -> dict:
    """A set per pod, or the refusal per pod, over every pod the router knows."""
    from . import pods

    sets: dict[str, dict] = {}
    refused: dict[str, str] = {}
    for key in pods.POD_KEYS:
        if key == pods.UNCLASSIFIED:
            continue
        try:
            sets[key] = build(db, key, benchmark_key=benchmark_key, now=now)
        except SetRefused as exc:
            refused[key] = str(exc)
    return {
        "sets": sets,
        "refused": refused,
        "pods_with_a_set": sorted(sets),
        "pods_without": sorted(refused),
        "minimums": {"observations": MIN_OBSERVATIONS, "listings": MIN_LISTINGS},
        "dimensions": {n: d["what"] for n, d in DIMENSIONS.items()},
        "note": ("A pod without a set is a pod whose galleries have not been judged enough, "
                 "and it is reported that way rather than given an empty set that looks "
                 "like a department with nothing to learn from (#76)"),
    }


def compare_listing_set(frames: list[dict], benchmark_set: dict) -> dict:
    """#67: the release comparison of our frames against a current set, dimension by dimension.

    Only the dimensions both sides can state are compared; the others are `unjudged` with
    the reason. Refuses a stale set outright: #67 says *current*, and a comparison against
    last season's galleries is not the comparison the requirement asks for.
    """
    if not benchmark_set.get("current"):
        raise SetRefused(
            f"the {benchmark_set.get('pod')!r} set's newest evidence is "
            f"{benchmark_set.get('newest_evidence')} ({benchmark_set.get('age_days')} days), "
            f"past {STALE_AFTER_DAYS}. #67 asks for a current sample and this is not one")
    from ..creative import blind_review

    ours = blind_review.our_side(frames)
    dims = benchmark_set["dimensions"]
    rows: dict[str, dict] = {}

    clarity = dims["thumbnail_clarity"]
    if clarity["basis"] != MEASURED or ours["all_readable"] is None:
        rows["thumbnail_clarity"] = {"state": "unjudged",
                                     "why": "one side has no thumbnail reading"}
    else:
        positive = [r for r in clarity["reads"] if not blind_review.reads_negative(r)]
        rows["thumbnail_clarity"] = {
            "state": "behind" if ours["all_readable"] is False else "level",
            "ours": ours["all_readable"],
            "theirs": f"{len(positive)} of {len(clarity['reads'])} reads legible"}

    story = dims["gallery_storytelling"]
    median = story.get("median_media_count")
    if median is None or not ours["frames"]:
        rows["gallery_storytelling"] = {"state": "unjudged",
                                        "why": "no media count or no frame of ours"}
    else:
        rows["gallery_storytelling"] = {
            "state": ("behind" if ours["frames"] < median else
                      "ahead" if ours["frames"] > median else "level"),
            "ours": ours["frames"], "theirs": median}

    video = dims["video_support"]
    if video["basis"] != MEASURED:
        rows["video_support"] = {"state": "unjudged", "why": video.get("reason")}
    else:
        rows["video_support"] = {
            "state": "behind" if video["video_share"] >= 0.5 else "level",
            "ours": False, "theirs": video["video_share"]}

    for name in DIMENSIONS:
        if name not in rows:
            rows[name] = {"state": "unjudged",
                          "why": ("our frame records carry no reading on this dimension; a "
                                  "judge would have to be asked, and none has been")}

    behind = [n for n, r in rows.items() if r["state"] == "behind"]
    judged = [n for n, r in rows.items() if r["state"] != "unjudged"]
    return {
        "pod": benchmark_set["pod"],
        "rows": rows,
        "judged": judged,
        "behind": behind,
        "unjudged": [n for n in DIMENSIONS if n not in judged],
        "substandard": bool(behind),
        "verdict": ("reject: obviously substandard beside the current set" if behind else
                    "not rejected on the judged dimensions" if judged else
                    "unjudged: nothing could be compared"),
        "against": {"listings": benchmark_set["listings"],
                    "observations": benchmark_set["observations"],
                    "newest_evidence": benchmark_set["newest_evidence"]},
        "note": ("#67 uses the benchmark to reject substandard presentation and never to "
                 "copy it. Unjudged dimensions are named, not averaged"),
    }
