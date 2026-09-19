"""The benchmark catalogue as a living map, and what a map is allowed to claim.

Requirement 303. Full discoverable catalogue coverage: every listing assigned to a specialist
pod and represented in the coverage matrix, with product family, generic product type,
silhouette, palette, seasonal positioning, merchandising mechanisms, visible pricing, gallery
structure and dated evidence.

Ten attributes, and they do not come from the same place — which is the whole design problem.
Four are in the marketplace API: product type, pricing and promotion, gallery structure, and
palette (Etsy publishes per-image hex, hue, saturation and brightness, so colour is free).
Three are judgements about a photograph: silhouette, merchandising mechanism, styling. The
rest are derived.

A map that filled the judgement columns from the title would look complete and be fiction, and
it would be *persuasive* fiction because nine of ten columns would be right. So an attribute
that needs a capability this company does not have is recorded as **absent with the capability
named**, never inferred, and the map reports its own completeness as a fraction of what it
could observe rather than of what it did.

"Living" is the other word doing work. A map is living if it knows how stale it is, so every
row carries the date of its evidence and the map reports the oldest — because a catalogue map
nobody has refreshed is indistinguishable from a current one right up to the moment it is
wrong, and it is wrong exactly when the shop changed something.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .pods import UNCLASSIFIED, route

# Where each attribute can come from. `api` is observable today with the read-only
# credential; `vision` needs the browser/vision gate; `derived` is computed from the others.
API = "api"
VISION = "vision"
DERIVED = "derived"

ATTRIBUTES: dict[str, tuple[str, str]] = {
    "product_family": (DERIVED, "the pod's product grouping"),
    "generic_product_type": (API, "what the listing says it is"),
    "silhouette": (VISION, "the outline of the finished object in the photograph"),
    "palette": (API, "per-image hex, hue, saturation and brightness, published by Etsy"),
    "seasonal_positioning": (API, "seasonal language in the title, tags and attributes"),
    "merchandising_mechanism": (VISION, "how the gallery sells it, judged from the images"),
    "visible_pricing": (API, "price, sale state and any displayed promotion"),
    "gallery_structure": (API, "how many images, in what order, of what kinds"),
    "dated_evidence": (API, "when this row was observed"),
    "change_state": (DERIVED, "new, changed or unchanged since the last scan"),
}

API_ATTRIBUTES: tuple[str, ...] = tuple(
    k for k, (source, _) in ATTRIBUTES.items() if source == API)
VISION_ATTRIBUTES: tuple[str, ...] = tuple(
    k for k, (source, _) in ATTRIBUTES.items() if source == VISION)

# Beyond this, a row is a historical record rather than a map.
STALE_AFTER_HOURS = 36

NEW = "new"
CHANGED = "changed"
UNCHANGED = "unchanged"


class MapRefused(ValueError):
    """An attribute inferred from something that cannot support it."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


@dataclass
class Row:
    listing_ref: str
    pod: str
    observed_on: str
    attributes: dict
    absent: dict
    change_state: str = UNCHANGED

    def to_dict(self) -> dict:
        return {"listing_ref": self.listing_ref, "pod": self.pod,
                "observed_on": self.observed_on, "change_state": self.change_state,
                "attributes": self.attributes, "absent": self.absent,
                "completeness": round(len(self.attributes) / len(ATTRIBUTES), 3)}


def describe_listing(listing: dict, *, vision_available: bool = False,
                     previous_fingerprint: str = "") -> Row:
    """One catalogue row, filling only what the available capabilities can actually see.

    The judgement columns are left absent with the capability named rather than inferred from
    the title. A map that inferred them would look complete and be fiction — and persuasive
    fiction, because nine columns of ten would be right.
    """
    title = str(listing.get("title") or "")
    product_type = str(listing.get("product_type") or listing.get("taxonomy") or "")
    pod = route(title, product_type) or UNCLASSIFIED

    attributes: dict = {}
    absent: dict = {}

    attributes["product_family"] = pod
    attributes["generic_product_type"] = product_type or "unstated"
    attributes["visible_pricing"] = {
        "price_cad": listing.get("price_cad"),
        "on_sale": bool(listing.get("on_sale")),
    }
    attributes["gallery_structure"] = {
        "images": int(listing.get("media_count") or 0),
        "has_video": bool(listing.get("has_video")),
    }
    palette = listing.get("palette")
    if palette:
        attributes["palette"] = palette
    else:
        absent["palette"] = ("no gallery has been read for this listing yet; Etsy publishes "
                             "per-image colour, so this needs a gallery call, not a model")
    attributes["seasonal_positioning"] = listing.get("seasonal") or "none stated"
    observed_on = str(listing.get("observed_on") or "")
    if observed_on:
        attributes["dated_evidence"] = observed_on
    else:
        absent["dated_evidence"] = "the row carries no observation date, so it is not evidence"

    for key in VISION_ATTRIBUTES:
        value = listing.get(key)
        if vision_available and value:
            attributes[key] = value
        else:
            absent[key] = (
                f"needs the browser/vision capability: {ATTRIBUTES[key][1]}. Inferring it "
                f"from the title would make this row look complete and be fiction")

    fingerprint = str(listing.get("fingerprint") or "")
    if not previous_fingerprint:
        change_state = NEW
    elif fingerprint and fingerprint != previous_fingerprint:
        change_state = CHANGED
    else:
        change_state = UNCHANGED
    attributes["change_state"] = change_state

    return Row(listing_ref=str(listing.get("listing_ref") or listing.get("listing_id") or ""),
               pod=pod, observed_on=observed_on, attributes=attributes, absent=absent,
               change_state=change_state)


def build(db, *, benchmark_key: str = "mjs", vision_available: bool = False,
          now: datetime | None = None) -> dict:
    """The whole map from what has been observed, with its own staleness reported.

    A catalogue map nobody has refreshed is indistinguishable from a current one right up to
    the moment it is wrong, and it is wrong exactly when the shop changed something.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing

    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        listings = [{
            "listing_ref": r.listing_ref, "title": r.title, "product_type": r.product_type,
            "price_cad": r.price_cad, "on_sale": r.on_sale, "media_count": r.media_count,
            "seasonal": r.seasonal, "fingerprint": r.fingerprint, "pod": r.pod,
            "observed_on": _aware(r.last_seen).isoformat()
            if getattr(r, "last_seen", None) else "",
        } for r in s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key))]

    if not listings:
        return {
            "mapped": False,
            "reason": ("no benchmark listing has been observed, so there is no catalogue to "
                       "map. An empty map is not a map of an empty shop"),
            "attributes": {k: {"source": v[0], "meaning": v[1]}
                           for k, v in ATTRIBUTES.items()},
            "needs_vision": list(VISION_ATTRIBUTES),
            "rows": [], "by_pod": {}, "listings": 0,
        }

    rows = [describe_listing(x, vision_available=vision_available,
                             previous_fingerprint=x.get("fingerprint", ""))
            for x in listings]

    by_pod: dict[str, int] = {}
    for row in rows:
        by_pod[row.pod] = by_pod.get(row.pod, 0) + 1

    dated = [_aware(datetime.fromisoformat(r.observed_on))
             for r in rows if r.observed_on]
    oldest = min(dated) if dated else None
    stale = [r.listing_ref for r in rows if r.observed_on
             and (now - _aware(datetime.fromisoformat(r.observed_on)))
             > timedelta(hours=STALE_AFTER_HOURS)]

    observable = len(ATTRIBUTES) - (0 if vision_available else len(VISION_ATTRIBUTES))
    filled = sum(len(r.attributes) for r in rows)
    return {
        "mapped": True,
        "listings": len(rows),
        "rows": [r.to_dict() for r in rows],
        "by_pod": dict(sorted(by_pod.items(), key=lambda kv: -kv[1])),
        "unclassified": by_pod.get(UNCLASSIFIED, 0),
        "change_counts": {state: sum(1 for r in rows if r.change_state == state)
                          for state in (NEW, CHANGED, UNCHANGED)},
        # Completeness against what could be observed, not against all ten columns: a map
        # that scored itself against the vision columns would look permanently broken rather
        # than correctly limited.
        "completeness_of_observable": round(filled / (len(rows) * observable), 3)
        if rows and observable else 0.0,
        "observable_attributes": observable,
        "needs_vision": list(VISION_ATTRIBUTES),
        "oldest_evidence": oldest.isoformat() if oldest else None,
        "stale_rows": stale,
        "stale_after_hours": STALE_AFTER_HOURS,
        "living": not stale,
        "note": ("Completeness is measured against what the available capabilities can "
                 "observe. Filling the judgement columns from the title would make every row "
                 "look complete and be fiction -- persuasive fiction, because nine of ten "
                 "columns would be right (#303)."),
    }
