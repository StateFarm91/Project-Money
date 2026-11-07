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
* colour and typography of live images cannot be read from any API: reported UNMEASURED;
  the brand assets we hold (marks) are checked for palette and outlined type by
  `brand.asset_consistency.sweep` and their findings join the list (WIRE1).
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
    # F-527 (WIRE1): the colour and typography half, on every brand asset we hold before it
    # reaches Etsy (marks: palette and outlined type). Live Etsy colour/type stays UNMEASURED.
    try:
        from ..brand import asset_consistency

        held = asset_consistency.sweep()
        out.extend(held["findings"])
        held_summary = {"marks_checked": held["marks_checked"], "fixes": held["fix_count"]}
    except Exception as exc:  # noqa: BLE001 - an unreadable sweep is UNKNOWN, never clean
        held_summary = {"state": UNKNOWN, "why": f"{type(exc).__name__}"}
    return {"findings": out, "icon_state": icon.get("state", UNKNOWN),
            "banner": banner_state, "live_colour_typography": UNMEASURED,
            "held_brand_assets": held_summary,
            "routes": sorted({f["route_to"] for f in out}),
            "fix_count": sum(1 for f in out if f["severity"] == "fix"), "writes": 0}


# ---- P0-STOREFRONT-ASSET-FIX: findings become work --------------------------------------

# Listing-image findings a re-render of the certified release can fix. ASSET_BLOCKED is not
# here: a frame a gate blocked is blocked by what it shows, and rendering it again from the
# same release shows the same thing; its own gate's finding says what to change.
REBUILD_CODES = ("HERO_MISSING", "ASSETS_STALE", "ASSET_LOW_RESOLUTION")
# Findings with no API: the owner does them in Shop Manager (icon) or the brand mark needs a
# designer's correction. One open card per finding.
OWNER_CODES = ("ICON_MISSING",)
ROUTED = "storefront.asset_fix_routed"


def route(ctx, health: dict) -> dict:
    """Turn asset-health findings into keyed work. Returns what was queued and what was not.

    * Each certified product with a rebuildable listing-image finding gets ONE `assets.build`
      for its current release, keyed `asset-fix:<slug>:<release hash>`. A rerun against the
      same release queues nothing; a new release can be rebuilt again.
    * A missing shop icon, or a held brand-mark finding routed to the storefront director,
      becomes one owner card (`storefront.asset:<code>:<subject>`). Nothing is written to Etsy.
    * Every other finding is reported `not_routed`, with why; none is dropped silently.
    """
    from ..ops import owner_queue
    from ..runtime.quality_ops import certified_releases

    findings = list(health.get("findings") or [])
    current = {r["slug"]: r for r in certified_releases(ctx.db)}
    rebuilds: dict[str, list[str]] = {}
    cards, not_routed = [], []
    for f in findings:
        code, subject = f.get("code"), f.get("subject")
        if code in REBUILD_CODES and subject in current:
            rebuilds.setdefault(subject, []).append(code)
        elif code in OWNER_CODES or (f.get("route_to") == "storefront_director"
                                     and f.get("severity") == "fix"):
            cards.append(f)
        else:
            not_routed.append({"code": code, "subject": subject,
                               "why": ("not a re-render fix" if code not in REBUILD_CODES
                                       else "no certified release to rebuild")})
    queued, already = [], []
    for slug, codes in sorted(rebuilds.items()):
        rel = current[slug]
        token = (rel["release_hash"] or rel["version"])[:16]
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": rel["version"],
                           "release": rel["release_hash"],
                           "rebuild": f"asset-health:{token}"},
                          idempotency_key=f"asset-fix:{slug}:{token}")
        (queued if job is not None else already).append(
            {"slug": slug, "version": rel["version"], "codes": sorted(set(codes)),
             "job": getattr(job, "id", None)})
    raised = []
    for f in cards:
        key = f"storefront.asset:{f['code']}:{f['subject']}"
        with ctx.db.session() as s:
            row = owner_queue.ensure(
                s, key,
                action=f"Fix the storefront asset {f['subject']}: {f['why']}",
                reason=("brand asset health (F-527) found it; there is no API for this "
                        "change, so it is an owner step or a designer's correction"),
                max_cost_cad=0.0, minutes=10,
                consequence_of_delay="the shop keeps showing the asset as it is",
                blocks=f"storefront asset {f['subject']}")
            raised.append({"key": key, "id": row.id})
    report = {"queued": queued, "already_queued": already, "owner_cards": raised,
              "not_routed": not_routed}
    ctx.audit(ROUTED, detail=report)
    return report
