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
#
# Review STOREFRONT d8b2754b (F1-F7) bounds this routing:
# * F1/F2: every rebuild is `fix_only` (W6 I-FIX-ONLY-REBUILD). It re-renders the images,
#   refreshes nothing on a live listing, records no price point and stops before
#   `launch.plan`, so `marketing.schedule` and `store.publish` are never reached. A live
#   listing gets an owner card to upload the new images by hand.
# * F3: a release whose own chain (gate.certify -> listing.draft -> assets.build) is queued,
#   running, retrying or did not finish is skipped; "no hero yet" is then that chain's job.
# * F4: a gallery holding any frame the renderer does not make (an owner photograph, a
#   lifestyle concept) is not rebuilt, because `_persist_frames` writes by position and would
#   overwrite it. That finding is reported, not routed.
# * F5: ASSET_LOW_RESOLUTION is NOT a rebuild code. It fires only when a ListingAsset's claims
#   record `width_px`/`height_px`, which no production writer records today, and a re-render
#   records none either, so a rebuild could never show the resolution was fixed.
# * F6: a `storefront.asset:*` card closes (SATISFIED) when its finding clears in a reading
#   that measured it; a card the owner closed is not re-opened unless the evidence changed.

# Listing-image findings a re-render of the certified release can fix. ASSET_BLOCKED is not
# here: a frame a gate blocked is blocked by what it shows, and rendering it again from the
# same release shows the same thing; its own gate's finding says what to change.
REBUILD_CODES = ("HERO_MISSING", "ASSETS_STALE")
# Findings with no API: the owner does them in Shop Manager (icon) or the brand mark needs a
# designer's correction. One open card per finding.
OWNER_CODES = ("ICON_MISSING",)
ICON_UNMEASURED = ("ICON_UNREAD", "ICON_READING_STALE")
ROUTED = "storefront.asset_fix_routed"
CARD_PREFIX = "storefront.asset:"
LIVE_CARD_PREFIX = "storefront.live_images:"
AUTO_CLOSED = "the finding cleared in a storefront review that measured it"
# The frame classes `publish.listing_assets.build_frames` renders. Any other class in a
# release's gallery was put there by something else and a re-render would overwrite it.
RENDER_CLASSES = frozenset({"DIGITAL_TWIN_RENDER", "INFOGRAPHIC", "PATTERN_PREVIEW"})
# The chain stages up to the images; a job of these for the slug that is not finished means
# the release's own build is still coming.
CHAIN_STAGES = ("gate.certify", "listing.draft", "assets.build")
LOW_RES_WHY = ("fires only when a listing image's pixel size is recorded; no writer records "
               "it and a re-render would not, so a rebuild cannot fix or verify it")


def _evidence(f: dict) -> str:
    import hashlib

    return hashlib.sha256(repr((f.get("code"), f.get("subject"), f.get("why"))).encode()
                          ).hexdigest()[:12]


def _card_text(f: dict) -> dict:
    if f["code"] == "ICON_MISSING":
        action = ("In Etsy Shop Manager, open Settings > Info & Appearance and upload the "
                  "Brambleloop shop icon (a square image; Etsy asks for 500 x 500 px), then "
                  "save. The next storefront review closes this card when it reads the icon.")
        why_not = "Etsy's Open API has no endpoint that sets the shop icon"
    else:
        action = (f"Correct the brand asset {f['subject']}: {f['why']}. The next storefront "
                  f"review closes this card when the brand-asset check passes.")
        why_not = "a brand mark is a design decision; software must not redraw it"
    return {"action": action[:900], "why_software_cannot": why_not}


def _chain_in_flight(s, slug: str, version: str, release: str) -> str | None:
    """Why this release's own build is still coming, or None when it is not."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..runtime.release import chain_key

    live = (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)
    for j in s.scalars(select(Job).where(Job.job_type.in_(CHAIN_STAGES),
                                         Job.status.in_(live))):
        inputs = j.inputs or {}
        if str(j.idempotency_key or "").startswith("asset-fix:"):
            continue
        if (inputs.get("slug") or (inputs.get("cir") or {}).get("slug")) == slug:
            return f"its own {j.job_type} (job {j.id}) is {j.status.value}"
    for stage in ("listing", "assets"):
        key = chain_key(stage, slug, version, release)
        j = s.scalar(select(Job).where(Job.idempotency_key == key))
        if j is not None and j.status != JobStatus.DONE:
            return f"its own {j.job_type} ({key}) is {j.status.value}"
    drafted = s.scalar(select(Job).where(Job.idempotency_key ==
                                         chain_key("listing", slug, version, release)))
    if drafted is not None and s.scalar(select(Job.id).where(
            Job.idempotency_key == chain_key("assets", slug, version, release))) is None:
        return "its own listing.draft built no images for this release (withheld or vetoed)"
    return None


def _foreign_frames(s, slug: str, version: str) -> list[str]:
    from sqlalchemy import select

    from ..core.models import ListingAsset

    return sorted({f"{a.position}:{a.asset_class}" for a in s.scalars(select(ListingAsset).where(
        ListingAsset.product_slug == slug, ListingAsset.version == version))
        if a.asset_class not in RENDER_CLASSES})


def _live_listing(s, slug: str, version: str):
    from sqlalchemy import select

    from ..core.models import Listing
    from ..runtime.release import _is_live

    row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                         Listing.version == version))
    return row if row is not None and _is_live(row) else None


def route(ctx, health: dict) -> dict:
    """Turn asset-health findings into keyed work. Returns what was queued and what was not.

    * Each certified product with a rebuildable listing-image finding gets ONE fix-only
      `assets.build` for its current release, keyed `asset-fix:<slug>:<release hash>`,
      unless its own chain is still in flight or its gallery holds frames a render would
      overwrite. A rerun against the same release queues nothing.
    * A live listing whose images are rebuilt gets an owner card to upload them by hand.
    * A missing shop icon, or a held brand-mark finding routed to the storefront director,
      becomes one owner card (`storefront.asset:<code>:<subject>`), closed when it clears.
    * Every other finding is reported `not_routed`, with why; none is dropped silently.
    Nothing is written to Etsy.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
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
                               "why": (LOW_RES_WHY if code == "ASSET_LOW_RESOLUTION"
                                       else "not a re-render fix" if code not in REBUILD_CODES
                                       else "no certified release to rebuild")})
    queued, already, live_cards = [], [], []
    for slug, codes in sorted(rebuilds.items()):
        rel = current[slug]
        codes = sorted(set(codes))
        with ctx.db.session() as s:
            in_flight = _chain_in_flight(s, slug, rel["version"], rel["release_hash"])
            foreign = [] if in_flight else _foreign_frames(s, slug, rel["version"])
        if in_flight or foreign:
            for code in codes:
                not_routed.append({"code": code, "subject": slug, "why": (
                    f"the release's own chain is not finished: {in_flight}" if in_flight
                    else "the gallery holds frames a re-render would overwrite: "
                         + ", ".join(foreign[:5]))})
            continue
        token = (rel["release_hash"] or rel["version"])[:16]
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": rel["version"],
                           "release": rel["release_hash"],
                           "rebuild": f"asset-health:{token}", "fix_only": True},
                          idempotency_key=f"asset-fix:{slug}:{token}")
        (queued if job is not None else already).append(
            {"slug": slug, "version": rel["version"], "codes": codes,
             "job": getattr(job, "id", None)})
        if job is None:
            continue
        with ctx.db.session() as s:
            live = _live_listing(s, slug, rel["version"])
            if live is not None:
                key = f"{LIVE_CARD_PREFIX}{slug}@{rel['version']}:{token}"[:200]
                row = owner_queue.ensure(
                    s, key,
                    action=(f"When assets.build job {job.id} for {slug}@{rel['version']} is "
                            f"done (audit assets.listing_images_built), replace the photos "
                            f"of live Etsy listing {live.etsy_listing_id or '(id not stored)'} "
                            f"in Shop Manager with the rebuilt frames, in their order. The "
                            f"system never edits a live listing."),
                    reason=(f"brand asset health (F-527) found {', '.join(codes)}; the "
                            f"images were rebuilt locally only"),
                    why_software_cannot="live listings are never changed autonomously",
                    max_cost_cad=0.0, minutes=15,
                    consequence_of_delay="the live listing keeps showing its current images",
                    blocks=f"listing images {slug}@{rel['version']}")
                live_cards.append({"key": key, "id": row.id})
    icon_measured = (health.get("icon_state") not in (None, UNKNOWN, "STALE")
                     and not any(f.get("code") in ICON_UNMEASURED for f in findings))
    brand_measured = (health.get("held_brand_assets") or {}).get("state") != UNKNOWN
    raised, held_closed, closed = [], [], []
    wanted = {}
    for f in cards:
        wanted[f"{CARD_PREFIX}{f['code']}:{f['subject']}"[:200]] = f
    with ctx.db.session() as s:
        for key, f in sorted(wanted.items()):
            ev = _evidence(f)
            last = s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)
                             .order_by(OwnerAction.id.desc())).first()
            if (last is not None and last.done and AUTO_CLOSED not in (last.state_reason or "")
                    and f"[evidence {ev}]" in (last.reason or "")):
                held_closed.append({"key": key, "id": last.id})
                continue
            text = _card_text(f)
            row = owner_queue.ensure(
                s, key, action=text["action"],
                reason=(f"brand asset health (F-527): {f['why']}"[:600]
                        + f" [evidence {ev}]"),
                why_software_cannot=text["why_software_cannot"],
                max_cost_cad=0.0, minutes=10,
                consequence_of_delay="the shop keeps showing the asset as it is",
                blocks=f"storefront asset {f['subject']}")
            raised.append({"key": key, "id": row.id})
        for row in list(s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key.like(f"{CARD_PREFIX}%"),
                OwnerAction.done == False))):  # noqa: E712
            if row.requirement_key in wanted:
                continue
            code = row.requirement_key[len(CARD_PREFIX):].split(":", 1)[0]
            if not (icon_measured if code in OWNER_CODES else brand_measured):
                continue
            owner_queue.close(row, owner_queue.SATISFIED, AUTO_CLOSED)
            closed.append({"key": row.requirement_key, "id": row.id})
    report = {"queued": queued, "already_queued": already, "owner_cards": raised,
              "live_image_cards": live_cards, "cards_closed": closed,
              "owner_closed_same_evidence": held_closed, "not_routed": not_routed}
    ctx.audit(ROUTED, detail=report)
    return report
