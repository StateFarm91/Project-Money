"""F-527 Brand Asset Health (W4-AGENTS cluster C3).

"Maintain logo/icon, banner, color, typography and listing-image consistency across Etsy.
Detect stale, missing, low-resolution or off-brand assets and route fixes to Brand/Visual."

`check(db)` reads what we already hold -- the live shop snapshot (`live_state.snapshot`) and
our listing asset rows -- and returns findings, each with the agent its fix routes to:
* shop icon missing, or the live reading stale -> `storefront_director` (owner step: no API);
* banner: Etsy's `image_url_760x100` may not show a big banner (LISTREADY E7), so a blank field
  is UNKNOWN, never "missing";
* listing images: a certified product with no approved hero, assets made for an older version
  than the certified one (stale), assets blocked by a gate (off-brand / untrue), or a recorded
  size under Etsy's 2000 px recommendation (low resolution) -> `publishing`;
* colour and typography of live images cannot be read from any API: reported UNMEASURED.
Read-only, deterministic, CA$0. Routing is a recorded finding, never a paid render.
"""
from __future__ import annotations

UNKNOWN = "UNKNOWN"
UNMEASURED = "UNMEASURED"
MIN_PX = 2000   # integrations.etsy_constraints listing_image_recommended_px


def _f(code, subject, route, why, severity="fix"):
    return {"code": code, "subject": subject, "route_to": route, "why": why,
            "severity": severity}


def check(db) -> dict:
    from sqlalchemy import select

    from ..core.models import ListingAsset, PatternVersion, Product
    from . import live_state

    out: list[dict] = []
    snap = live_state.snapshot(db)
    icon, banner = snap.get("shop_icon") or {}, snap.get("shop_banner") or {}
    if icon.get("state") == UNKNOWN:
        out.append(_f("ICON_UNREAD", "shop_icon", "storefront_director",
                      "no live reading of the shop icon", "unknown"))
    elif icon.get("state") == live_state.STALE:
        out.append(_f("ICON_READING_STALE", "shop_icon", "storefront_director",
                      f"the shop reading is stale ({icon.get('observed_at')})", "unknown"))
    elif not icon.get("value"):
        out.append(_f("ICON_MISSING", "shop_icon", "storefront_director",
                      "the live shop has no icon (owner step in Shop Manager; no API)"))
    banner_state = (UNKNOWN if not banner.get("value") else "PRESENT")
    with db.session() as s:
        certified = {slug: ver for slug, ver in s.execute(
            select(Product.slug, PatternVersion.version)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .where(PatternVersion.certified == True)  # noqa: E712
            .order_by(PatternVersion.id)).all()}
        assets = s.execute(select(ListingAsset.product_slug, ListingAsset.version,
                                  ListingAsset.role, ListingAsset.approved,
                                  ListingAsset.blocked_reasons, ListingAsset.claims)).all()
    by_slug: dict[str, list] = {}
    for a in assets:
        by_slug.setdefault(a.product_slug, []).append(a)
    for slug, ver in sorted(certified.items()):
        mine = by_slug.get(slug, [])
        current = [a for a in mine if a.version == ver]
        if not any(a.approved and a.role == "hero" for a in current):
            out.append(_f("HERO_MISSING", slug, "publishing",
                          f"no approved hero image for the certified {slug}@{ver}"))
        if any(a.version != ver for a in mine) and not current:
            out.append(_f("ASSETS_STALE", slug, "publishing",
                          f"listing images exist only for older versions than {ver}"))
        for a in current:
            if a.blocked_reasons:
                out.append(_f("ASSET_BLOCKED", slug, "publishing",
                              f"{a.role}: {str(a.blocked_reasons[0])[:160]}"))
            claims = a.claims or {}
            w, h = claims.get("width_px"), claims.get("height_px")
            if isinstance(w, int) and isinstance(h, int) and min(w, h) < MIN_PX:
                out.append(_f("ASSET_LOW_RESOLUTION", slug, "publishing",
                              f"{a.role}: {w}x{h} px is under Etsy's {MIN_PX} px recommendation"))
    return {"findings": out, "icon_state": icon.get("state", UNKNOWN),
            "banner": banner_state, "live_colour_typography": UNMEASURED,
            "routes": sorted({f["route_to"] for f in out}),
            "fix_count": sum(1 for f in out if f["severity"] == "fix"), "writes": 0}
