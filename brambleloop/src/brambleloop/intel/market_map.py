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


def build(db, *, benchmark_key: str | None = None, vision_available: bool = False,
          now: datetime | None = None) -> dict:
    """The whole map from what has been observed, with its own staleness reported.

    A catalogue map nobody has refreshed is indistinguishable from a current one right up to
    the moment it is wrong, and it is wrong exactly when the shop changed something.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import benchmarks

    # Defaulted from the constant the scanner writes rather than from a short string that
    # looks like it. They disagreed -- the scanner wrote "mjs_off_the_hook_designs" and this
    # read "mjs" -- so the query matched nothing and the map reported "no benchmark listing
    # has been observed" against a database holding 438 of them. A wrong key does not fail;
    # it returns an empty result that is indistinguishable from the truth.
    benchmark_key = benchmark_key or benchmarks.MJS_KEY

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


# ---------------------------------------------------------------------------
# Coverage gaps (#207, #303)
#
# The map reports `unclassified: 58` and that number, on its own, is not actionable. It says
# 13% of the benchmark catalogue reaches no specialist and gives nobody the evidence to fix
# it. A gap counted is not a gap known.
#
# So this names them. The keyword vocabulary in `pods.py` is only allowed to grow from
# observed titles -- widening it from imagination produces pods that match nothing and a
# router that still drops the same listings, while looking broader.


def gaps(db, *, benchmark_key: str | None = None, limit: int = 200,
         title_chars: int = 200) -> dict:
    """What the map cannot see, listing by listing, with the reason it cannot see it.

    Two kinds of gap, and they have different owners:

      - **Routing gaps**: a listing whose title matched no pod keyword. Ours to close, from
        the titles themselves.
      - **Attribute gaps**: a column absent on some rows. Each one names the capability that
        would fill it, so an absence caused by a missing gallery call is never confused with
        one caused by a missing vision capability.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from . import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        rows = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))
        observed = [{"listing_ref": r.listing_ref, "title": r.title or "",
                     "product_type": r.product_type or "",
                     "stored_pod": r.pod or UNCLASSIFIED,
                     "palette": (r.detail or {}).get("palette")} for r in rows]

    unrouted = [x for x in observed if route(x["title"], x["product_type"]) == UNCLASSIFIED]

    # The words that actually appear in the titles nothing matched. This is the evidence a
    # keyword widening has to be drawn from; a term that appears once is noise, a term that
    # appears across a dozen unrouted listings is a missing pod or a missing keyword.
    counts: dict[str, int] = {}
    for x in unrouted:
        for word in {w.strip(".,!|()-–—\"'") for w in x["title"].lower().split()}:
            if len(word) > 3 and word.isalpha():
                counts[word] = counts.get(word, 0) + 1
    frequent = sorted(((w, c) for w, c in counts.items() if c >= 3),
                      key=lambda wc: (-wc[1], wc[0]))

    missing_palette = [x["listing_ref"] for x in observed if not x["palette"]]

    # The third gap, and the one nobody would have gone looking for. The scanner routes a
    # listing when it first sees it and then short-circuits on an unchanged fingerprint, so a
    # widened vocabulary reaches nothing already in the table: the stored pod is whatever the
    # vocabulary said on the day the listing was discovered. Every improvement to routing is
    # therefore invisible until the benchmark shop happens to edit its own listings.
    # Two of the faults this report found were hidden behind a 120-character truncation --
    # an HTML-escaped possessive and a size range, both past the cut. A report whose own
    # display hides the evidence it exists to show is worse than a shorter list.
    drift = [{"listing_ref": x["listing_ref"], "title": x["title"][:title_chars],
              "stored_pod": x["stored_pod"],
              "current_pod": route(x["title"], x["product_type"])}
             for x in observed
             if route(x["title"], x["product_type"]) != x["stored_pod"]]
    return {
        "benchmark_key": benchmark_key,
        "listings": len(observed),
        "routing": {
            "unclassified": len(unrouted),
            "share": round(len(unrouted) / len(observed), 3) if observed else 0.0,
            "owner": "ours: the pod vocabulary is short, and it is closeable from these titles",
            "listings": [{"listing_ref": x["listing_ref"], "title": x["title"][:title_chars],
                          "product_type": x["product_type"]} for x in unrouted[:limit]],
            "frequent_terms": [{"term": w, "listings": c} for w, c in frequent[:40]],
            "truncated": max(0, len(unrouted) - limit),
        },
        "stored_routing_drift": {
            "listings": len(drift),
            "share": round(len(drift) / len(observed), 3) if observed else 0.0,
            "reason": ("the scanner routes on discovery and skips unchanged listings, so a "
                       "stored pod is the vocabulary of the day it was found"),
            "remedy": "intel.observe.reclassify, which re-routes without re-reading Etsy",
            "moves": [{"from": d["stored_pod"], "to": d["current_pod"],
                       "listing_ref": d["listing_ref"], "title": d["title"]}
                      for d in drift[:limit]],
        },
        "attributes": {
            "palette": {
                "absent_on": len(missing_palette),
                "share": round(len(missing_palette) / len(observed), 3) if observed else 0.0,
                "capability": "a gallery read on the existing read-only credential",
                "note": ("Etsy publishes per-image hex, hue, saturation and brightness, so "
                         "this is an unmade call rather than a missing capability"),
            },
            **{k: {"absent_on": len(observed), "share": 1.0,
                   "capability": "browser/vision", "note": ATTRIBUTES[k][1]}
               for k in VISION_ATTRIBUTES},
        },
        "note": ("A gap counted is not a gap known. Every unrouted listing is named here "
                 "because the pod vocabulary may only grow from observed titles -- widening "
                 "it from imagination produces pods that match nothing while looking "
                 "broader (#207)."),
    }
