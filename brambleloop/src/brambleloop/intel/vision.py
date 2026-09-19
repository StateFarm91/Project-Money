"""Image-level observation: the work the API cannot do, queued for when it can.

Requirements 209, 304. The sanctioned Etsy API gives every gallery image's URL and Etsy's own
per-image colour statistics, which answers palette questions outright. What it cannot answer is
whether the shot works: shot type, composition, product visibility, how the model relates to
the product, how the scale is communicated, whether it reads at thumbnail size.

That needs a model with eyes, and the owner approved one at CA$25 a month. The key is not set
yet, so this builds the queue rather than the excuse: every audited gallery becomes pending
analysis work with a stable identity, and the moment the credential exists the backlog drains
in cost order. Nothing here invents an observation in the meantime.

The vocabulary is closed for the same reason the pods' mechanism list is: an open field accepts
"nice photo", and a competitive intelligence system whose evidence is "nice photo" has learned
nothing it can act on.
"""
from __future__ import annotations

from dataclasses import dataclass

# What a gallery observation is allowed to conclude (#209). Each is something a different
# Brambleloop decision depends on.
OBSERVATION_FIELDS: tuple[str, ...] = (
    "shot_type", "composition", "product_visibility", "model_product_relationship",
    "setting", "scale_communication", "detail_coverage", "infographic_use", "typography",
    "palette_role", "thumbnail_readability", "emotional_merchandising",
)

SHOT_TYPES: tuple[str, ...] = (
    "hero_product_only", "hero_styled", "full_fit", "three_quarter", "detail_macro",
    "flat_lay", "in_use", "scale_reference", "infographic", "process", "packaging",
)

PENDING = "pending"
ANALYSED = "analysed"
BLOCKED = "blocked"


class AnalysisRefused(ValueError):
    """An observation that is not one of the things a gallery observation may conclude."""


@dataclass(frozen=True)
class PendingAnalysis:
    benchmark_key: str
    listing_ref: str
    image_url: str
    rank: int

    @property
    def key(self) -> str:
        """Stable identity, so the same image is never paid for twice."""
        return f"{self.benchmark_key}:{self.listing_ref}:{self.rank}"

    def to_dict(self) -> dict:
        return {"benchmark": self.benchmark_key, "listing_ref": self.listing_ref,
                "rank": self.rank, "image_url": self.image_url, "key": self.key}


def pending(db, benchmark_key: str, *, limit: int = 200) -> list[PendingAnalysis]:
    """Gallery images that have been inventoried and not yet judged.

    Ordered by listing recency so a release run is analysed before an eighteen-month-old
    listing, which is the order the commercial value arrives in.
    """
    from sqlalchemy import desc, select

    from ..core.models import BenchmarkListing

    with db.session() as s:
        rows = list(s.scalars(
            select(BenchmarkListing)
            .where(BenchmarkListing.benchmark_key == benchmark_key,
                   BenchmarkListing.audit_state == "audited")
            .order_by(desc(BenchmarkListing.last_seen))))

    out: list[PendingAnalysis] = []
    for row in rows:
        detail = row.detail or {}
        if detail.get("gallery_analysed"):
            continue
        for rank, url in enumerate(detail.get("image_urls") or [], start=1):
            if url:
                out.append(PendingAnalysis(benchmark_key, row.listing_ref, url, rank))
            if len(out) >= limit:
                return out
    return out


def check_observation(observation: dict) -> None:
    """Refuse an observation that is not about anything actionable."""
    unknown = [k for k in observation if k not in OBSERVATION_FIELDS]
    if unknown:
        raise AnalysisRefused(
            f"{sorted(unknown)} are not gallery observation fields. The vocabulary is closed "
            f"because an open one accepts 'nice photo', and intelligence whose evidence is "
            f"'nice photo' has taught the company nothing it can act on")
    shot = observation.get("shot_type")
    if shot is not None and shot not in SHOT_TYPES:
        raise AnalysisRefused(f"{shot!r} is not a shot type: {sorted(SHOT_TYPES)}")
    if not observation:
        raise AnalysisRefused("an empty observation is not an observation")


def plan(db, benchmark_key: str, env: dict[str, str] | None = None) -> dict:
    """What image work is outstanding, what it would cost, and whether it can run.

    Reports the backlog whether or not the capability exists, because "how much would this
    cost once the key is set" is exactly the question the owner will ask tomorrow, and it is
    answerable today.
    """
    from ..gateway import routing
    from ..launch import access

    queue = pending(db, benchmark_key)
    per_call = routing.estimate_cad("gallery_observation")
    capable = access.available("model_provider", env)
    budget = routing.budget(db)

    affordable = int(budget.remaining_cad / per_call) if per_call else 0
    return {
        "state": PENDING if capable else BLOCKED,
        "pending_images": len(queue),
        "estimated_cad_per_image": per_call,
        "estimated_cad_total": round(len(queue) * per_call, 4),
        "affordable_this_month": affordable,
        "capability_available": capable,
        "next": [p.to_dict() for p in queue[:10]],
        "note": ("Ready to run: the backlog drains in listing-recency order, newest first, "
                 "because that is the order commercial value arrives in."
                 if capable else
                 "No model provider is configured, so no image has been judged and none has "
                 "been guessed at. The backlog is real work waiting, not a gap being "
                 "papered over (#224)."),
    }


def record(db, analysis: PendingAnalysis, observation: dict,
           *, env: dict[str, str] | None = None) -> int:
    """Store one judged image, and never store one nobody judged."""
    from ..launch import access
    from . import mission

    if not access.available("model_provider", env):
        raise AnalysisRefused(
            "no model provider is configured, so this observation was not produced by looking "
            "at the image. Recording it would be the silent downgrade #224 forbids")
    check_observation(observation)

    got = mission.record(
        db, benchmark_key=analysis.benchmark_key, kind="gallery_image_observation",
        listing_ref=analysis.listing_ref,
        detail={"image": analysis.to_dict(), "observation": observation},
        env=env)
    return got.observation_id
