"""The second half of the release chain: assets, pricing, listing, launch, support.

`pipeline.py` carries a concept as far as a Quality Release Certificate. This carries the
certified pattern the rest of the way to something that could actually be sold: the PDF and
charts a customer downloads, a price that survives Etsy's fees, a listing whose every claim
is checkable, a launch plan anchored on the buying window, and a support surface that can
answer from the released version without being able to change it.

The ordering is not cosmetic. Assets are rendered from the certified CIR, the listing's
claims are taken from the rendered assets, and the policy check runs on what was actually
written. Nothing downstream is allowed to assert something nothing upstream computed.
"""
from __future__ import annotations

import hashlib
from datetime import date

from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import build_twin
from ..cir.writer import collapses_rows
from ..quality.physical import calibration_from_db
from ..commerce import launch as launch_mod
from ..commerce import pricing as pricing_mod
from ..commerce import pricing_intel as pricing_mod_intel
from ..commerce import search as search_mod
from ..commerce import seo as seo_mod
from ..commerce import thumbnail as thumb_mod
from ..core.artifacts import ArtifactStore
from ..core.models import PatternVersion, Product
from ..gates.policy import ListingDraft, check_listing
from ..core.models import ListingAsset
from ..gates.asset_truth import check_assets
from ..publish.charts import ChartSpec, render_any_chart, render_legend
from ..publish.listing_assets import build_frames, check_frame_plan
from ..publish.pdf import build_pattern_pdf
from ..radar.market import shopping_window
from ..radar.opportunity import POOL, _event
from .worker import JobContext, handlers

# The release chain's own version, stamped into every downstream idempotency key.
#
# Without it a pipeline upgrade cannot reach products that already shipped. Production proved
# this: fifteen products were certified before listing imagery, search coverage and the
# content ecosystem existed, and the next cycle silently collapsed every downstream job
# against keys like "assets:slug:1.0.0" that were already taken. The cycle reported success
# and produced nothing.
#
# "Build assets for slug@1.0.0 with chain v2" is genuinely different work from doing it with
# v1, so it gets a different key. Bump this whenever a stage after certification changes what
# it produces.
CHAIN_VERSION = "7"

# How much of an owner action's opening clause identifies it, for adopting rows queued
# before `OwnerAction.requirement_key` existed. Long enough to be unambiguous, short enough
# that no action's derived figure reaches it. A test asserts the prefixes are distinct.
ADOPT_PREFIX = 40


def chain_key(stage: str, slug: str, version: str, release: str = "",
              token: str = "") -> str:
    """The idempotency key for one post-certification stage.

    Three things identify the work, and leaving any of them out has cost a delivery:

    - `slug` and `version` say which product. Alone they meant a code change could never
      reach a product that had already shipped, which is what CHAIN_VERSION fixed.
    - `release` says *what was certified*. Without it a re-engineered design re-certifies
      and then finds every downstream key taken, so production issued new certificates and
      kept serving the old listings.
    - `token` says which rebuild asked. A rebuild exists precisely for the case where the
      work already ran and its result is no longer right, so the trigger has to be part of
      the key or the rebuild cannot re-drive a single stage of the chain. It rides the whole
      chain in the job inputs, so every stage re-runs once for that rebuild and not once per
      cadence.
    """
    parts = [stage, slug, version]
    if release:
        parts.append(release[:12])
    if token:
        parts.append(token[:12])
    parts.append(f"c{CHAIN_VERSION}")
    return ":".join(parts)


CATEGORY_BANDS_CAD: dict[str, tuple[float, float]] = {
    "mosaic_blanket": (8.50, 14.00),
    "blanket": (8.50, 14.00),
    "graphghan": (7.50, 12.00),
    "baby": (6.00, 10.00),
    "seasonal_decor": (4.00, 9.00),
    "ornament": (4.00, 7.50),
    "basket": (4.50, 8.00),
    "runner": (5.00, 9.00),
    "flower": (4.00, 8.00),
    "pet": (4.00, 7.50),
}
DEFAULT_BAND = (4.50, 9.50)


def _load_cir(ctx: JobContext, slug: str, version: str) -> CIR:
    from sqlalchemy import select

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == slug))
        if product is None:
            raise ValueError(f"no product {slug!r}: assets cannot precede certification")
        pv = s.scalar(select(PatternVersion).where(
            PatternVersion.product_id == product.id, PatternVersion.version == version))
        if pv is None or not pv.certified:
            raise ValueError(
                f"{slug}@{version} has no certified release; refusing to render customer "
                f"assets for a pattern that did not pass the gates")
        return CIR.from_dict(pv.cir_json)


def _seed_for(slug: str):
    return next((s for s in POOL if slug.startswith(s.slug) or s.slug == slug), None)


@handlers.register("assets.build")
def handle_assets_build(ctx: JobContext) -> dict:
    """Render the customer PDF and charts from the certified CIR, and record their hashes.

    The hash is the point. A PDF is the only artefact the customer ever sees, so the system
    has to be able to prove that the file it is about to ship is the one that was certified
    and not a re-render that drifted.
    """
    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs["version"]
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))

    doc = build_pattern_pdf(cir, twin=twin, terminology="US")
    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))
    pdf = store.put(f"{slug}/{version}/pattern-us.pdf", doc.pdf_bytes, "application/pdf")

    import io

    chart_png = io.BytesIO()
    render_any_chart(cir, twin, ChartSpec(cell_px=26)).save(chart_png, format="PNG")
    chart = store.put(f"{slug}/{version}/chart.png", chart_png.getvalue(), "image/png")

    legend_png = io.BytesIO()
    render_legend(cir, twin).save(legend_png, format="PNG")
    legend = store.put(f"{slug}/{version}/legend.png", legend_png.getvalue(), "image/png")

    ctx.audit("assets.built", artifact=f"{slug}@{version}", detail={
        "pdf": pdf.to_dict(), "chart": chart.to_dict(), "legend": legend.to_dict(),
        "pages": doc.pages, "size_label": doc.size_label(),
        "storage_durable": pdf.durable,
    })
    if not pdf.durable:
        ctx.audit("assets.storage_not_durable", artifact=f"{slug}@{version}", detail={
            "reason": "no object storage is provisioned; artifact bytes do not survive a "
                      "container restart. Hashes are durable and assets re-render from the "
                      "certified CIR."})

    # Listing imagery is part of the release, not an afterthought bolted on before publish.
    # It is rendered from the same twin as the PDF, so no frame can assert something the
    # pattern does not produce, and then checked by Asset Truth like any other asset.
    from ..cir.writer import write_pattern

    siblings = _collection_siblings(slug)
    frames = build_frames(cir, twin, pattern_text=write_pattern(cir, result),
                          difficulty=_difficulty(twin, cir), pages=doc.pages,
                          siblings=siblings)
    structural = check_frame_plan(frames)
    truth = check_assets([f.to_asset(slug) for f in frames], cir, twin)
    # A hero is judged at the size a shopper actually sees it, not in the editor.
    aspect = ((twin.width_cm / twin.height_cm)
              if twin.width_cm and twin.height_cm else None)
    hero = thumb_mod.evaluate_thumbnail(frames[0].image, text_pt_on_canvas=0.056 * 2000,
                                        canvas_px=2000, subject_aspect=aspect)
    # #201: a model-bearing frame whose identity cannot be verified does not ship. Today no
    # frame carries the model, so this is `not_applicable` and changes nothing -- which is
    # the point of wiring it now rather than on the day the first model frame is built, when
    # the temptation to let it through is at its highest.
    from ..visual import model_registry

    identity_gate = model_registry.gate_frames(ctx.db, [
        {"role": f.role, "has_model": bool(getattr(f, "has_model", False)),
         "image_ref": ""} for f in frames])

    blocking = (structural + [str(f) for f in truth if f.is_error] + hero.problems
                + list(identity_gate["blocking"]))

    stored_frames = []
    for frame in frames:
        art = store.put(f"{slug}/{version}/frame-{frame.position}.png", frame.png(),
                        "image/png")
        stored_frames.append({"position": frame.position, "role": frame.role,
                              "asset_class": frame.asset_class.value,
                              "sha256": art.sha256})
    _persist_frames(ctx, slug, version, frames, stored_frames, blocking)

    ctx.audit("assets.listing_images_built" if not blocking else "assets.listing_images_blocked",
              artifact=f"{slug}@{version}",
              detail={"frames": len(frames), "blocking": blocking[:5],
                      "identity_gate": {k: identity_gate[k]
                                        for k in ("checked", "verdict") if k in identity_gate},
                      "hero_thumbnail": hero.to_dict()})
    if blocking:
        # A listing whose imagery misrepresents the pattern does not proceed to pricing. The
        # chain stops here rather than producing a price for something that cannot ship.
        return {"slug": slug, "version": version, "ok": False,
                "blocking_image_problems": blocking}

    release = ctx.job.inputs.get("release", "")
    token = ctx.job.inputs.get("rebuild", "")
    payload = {"slug": slug, "version": version, "release": release, "rebuild": token,
               "pages": doc.pages,
               "size_label": doc.size_label(),
               "finished_size_cm": list(doc.finished_size_cm) if doc.finished_size_cm else None,
               "yardage": doc.yardage_by_color, "tolerance": doc.yardage_tolerance,
               "calibrated": doc.calibrated,
               "pdf_sha256": pdf.sha256, "chart_sha256": chart.sha256,
               "legend_sha256": legend.sha256,
               "frames": stored_frames}
    ctx.enqueue("pricing", "pricing.position", payload,
                idempotency_key=chain_key("price", slug, version, release, token))
    return payload


@handlers.register("pricing.position")
def handle_pricing_position(ctx: JobContext) -> dict:
    i = dict(ctx.job.inputs)
    slug = i["slug"]
    seed = _seed_for(slug)
    category = seed.category if seed else "mosaic_blanket"
    band = CATEGORY_BANDS_CAD.get(category, DEFAULT_BAND)
    proposed = seed.price_cad if seed else band[1]

    sizes = len(ctx.job.inputs.get("sizes") or []) or 1
    is_bundle = bool(seed and seed.is_bundle)
    members = ctx.job.inputs.get("bundle_members_cad")
    if is_bundle and not members:
        # A bundle's saving has to be measured against the prices we actually charge for its
        # members, so they are read from the pool rather than guessed or passed in by a
        # caller who might pass anything.
        members = [m.price_cad for m in POOL
                   if m.family == seed.family and not m.is_bundle]
    decision = pricing_mod.decide_price(
        slug, category_band_cad=band, proposed_cad=proposed,
        has_video=False, sizes_offered=sizes,
        is_bundle=is_bundle, bundle_members_cad=members)

    # The category's standing "50% off" is not available to us; assert that explicitly rather
    # than relying on nobody adding it later.
    pricing_mod.check_no_fake_discount(decision.price_cad, None, ever_charged=False)

    ctx.audit("pricing.positioned", artifact=slug, detail=decision.to_dict())
    i.update({"price_cad": decision.price_cad, "net_cad": decision.net_cad,
              "pricing_reasons": decision.reasons, "pricing_warnings": decision.warnings,
              "category": category})
    ctx.enqueue("listing", "listing.seo", i,
                idempotency_key=chain_key("seo", slug, i["version"], i.get("release", ""),
                                          i.get("rebuild", "")))
    return decision.to_dict()


@handlers.register("listing.seo")
def handle_listing_seo(ctx: JobContext) -> dict:
    """Assemble the listing from computed facts, then let the Policy Gate try to break it."""
    i = dict(ctx.job.inputs)
    slug, version = i["slug"], i["version"]
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))
    seed = _seed_for(slug)
    category = i.get("category") or (seed.category if seed else "mosaic_blanket")
    season = seed.season if seed else None
    motifs = _motifs_for(slug)

    tolerance_pct = int(twin.yardage_tolerance * 100)
    yardage_lines = [
        f"{name}: about {m * (1 - twin.yardage_tolerance):.0f}-"
        f"{m * (1 + twin.yardage_tolerance):.0f} m"
        for name, m in sorted(twin.yarn_metres_by_color.items())
    ]
    gauge_line = (f"{cir.gauge.stitches_per_10cm} sts x {cir.gauge.rows_per_10cm} rows = 10 cm "
                  f"in {cir.gauge.stitch_type}, {cir.gauge.hook_mm:g} mm hook"
                  if cir.gauge else None)
    size_label = (f"{twin.width_cm:.0f} x {twin.height_cm:.0f} cm"
                  if twin.width_cm and twin.height_cm else None)

    # Tags come from the query model rather than a fixed template: thirteen slots are
    # scarce, and spending them on head terms a shop with no history cannot place for is the
    # most common way a new listing is invisible.
    techniques = ["mosaic"] if "mosaic" in (category + " " + cir.slug) else ["texture"]
    queries = search_mod.build_query_set(category, motifs, season, techniques)
    title = seo_mod.build_title(cir.title, category, motifs, season,
                                sizes=len(i.get("sizes") or []) or 1)
    tags = search_mod.choose_tags(queries)

    copy = seo_mod.ListingCopy(
        title=title,
        tags=tags,
        description=seo_mod.build_description(
            cir.title, size_label=size_label, yardage_lines=yardage_lines,
            tolerance_pct=tolerance_pct, difficulty=_difficulty(twin, cir),
            colors=sorted(c for c in twin.colors_used if c), terminology="US",
            gauge_line=gauge_line, stitches=sorted(twin.stitch_types_used),
            season=season, pages=i.get("pages"),
            collapsed_repeats=collapses_rows(cir)),
        materials=[m.name for m in cir.materials],
        price_cad=float(i.get("price_cad", 0.0)),
        supported_claims=[c for c in (size_label, gauge_line) if c],
    )

    coverage = search_mod.score_coverage(queries, title=copy.title, tags=copy.tags,
                                         description=copy.description)
    attributes = search_mod.listing_attributes(
        category=category, difficulty=_difficulty(twin, cir),
        colors=sorted(c for c in twin.colors_used if c), season=season)

    structural = (seo_mod.check_listing_limits(copy)
                  + search_mod.check_attributes(attributes))
    policy = check_listing(ListingDraft(title=copy.title, description=copy.description,
                                        tags=copy.tags, price_cad=copy.price_cad))
    blocking = structural + [str(f) for f in policy if f.is_error]

    ctx.audit("listing.seo_drafted" if not blocking else "listing.seo_blocked",
              artifact=f"{slug}@{version}",
              detail={"title_len": len(copy.title), "tags": len(copy.tags),
                      "search_share": coverage.share, "gaps": coverage.gaps[:5],
                      "blocking": blocking[:5]})
    if blocking:
        return {"slug": slug, "version": version, "ok": False, "blocking": blocking}

    i.update({"listing": copy.to_dict(), "attributes": attributes,
              "search_coverage": coverage.to_dict()})
    _persist_listing(ctx, slug, version, copy, coverage.share, i.get("release", ""))
    ctx.enqueue("growth", "launch.plan", i,
                idempotency_key=chain_key("launch", slug, version, i.get("release", ""),
                                          i.get("rebuild", "")))
    return {"slug": slug, "version": version, "ok": True, "listing": copy.to_dict(),
            "attributes": attributes, "search_coverage": coverage.to_dict()}


def _persist_listing(ctx: JobContext, slug: str, version: str, copy, share: float,
                     release: str = "") -> None:
    """Drafted, never published. Shadow mode holds the whole shop ready rather than open."""
    from sqlalchemy import select

    from ..core.models import Listing

    with ctx.db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                             Listing.version == version))
        if row is None:
            row = Listing(product_slug=slug, version=version)
            s.add(row)
        row.title = copy.title
        row.description = copy.description
        row.tags = list(copy.tags)
        row.price_cad = copy.price_cad
        row.seo_score = share
        row.state = "draft"
        row.chain_version = CHAIN_VERSION
        row.release_hash = release or ""


@handlers.register("launch.plan")
def handle_launch_plan(ctx: JobContext) -> dict:
    i = dict(ctx.job.inputs)
    slug = i["slug"]
    seed = _seed_for(slug)
    today = (date.fromisoformat(i["as_of"]) if i.get("as_of") else date.today())

    window = None
    if seed and seed.season:
        base = _event(seed.season)
        if base is not None:
            from ..radar.market import SeasonalEvent

            scoped = SeasonalEvent(base.name, base.event_date, seed.maker_hours,
                                   base.gift_lead_days)
            window = shopping_window(scoped)

    plan = launch_mod.plan_launch(slug, today=today, window=window,
                                  build_lead_days=seed.build_lead_days if seed else 7)
    ctx.audit("launch.planned", artifact=slug, detail={
        "launch_on": plan.launch_on.isoformat(), "compressed": plan.compressed,
        "warnings": plan.warnings[:3]})

    i["launch"] = plan.to_dict()
    ctx.enqueue("growth", "marketing.schedule", i,
                idempotency_key=chain_key("content", slug, i["version"],
                                          i.get("release", ""), i.get("rebuild", "")))
    ctx.enqueue("store_operator", "store.publish",
                {"slug": slug, "version": i["version"]},
                idempotency_key=chain_key("publish", slug, i["version"],
                                          i.get("release", ""), i.get("rebuild", "")))
    return plan.to_dict()


@handlers.register("marketing.schedule")
def handle_marketing_schedule(ctx: JobContext) -> dict:
    """Draft the product's content ecosystem and hold it (section 11).

    Nothing is scheduled to publish itself. There is no Pinterest, email, video or social
    integration in this system, and shadow mode means the plan is built and reviewable before
    any account exists rather than after.
    """
    from ..core.models import ContentPiece
    from ..growth import content as content_mod

    i = dict(ctx.job.inputs)
    slug, version = i["slug"], i["version"]
    seed = _seed_for(slug)
    listing = i.get("listing") or {}
    launch_on = date.fromisoformat(i["launch"]["launch_on"])

    cir = _load_cir(ctx, slug, version)
    twin = build_twin(cir, compile_cir(cir),
                      calibration=calibration_from_db(ctx.db, cir))
    tol = twin.yardage_tolerance
    yardage_line = "; ".join(
        f"{name} about {m * (1 - tol):.0f}-{m * (1 + tol):.0f} m"
        for name, m in sorted(twin.yarn_metres_by_color.items())) or "see the pattern"

    facts = content_mod.ProductFacts(
        slug=slug, title=cir.title,
        category=seed.category if seed else "mosaic_blanket",
        size_label=i.get("size_label"),
        difficulty=_difficulty(twin, cir),
        stitches=sorted(twin.stitch_types_used),
        colors=sorted(c for c in twin.colors_used if c),
        yardage_line=yardage_line,
        maker_hours=seed.maker_hours if seed else (4.0, 12.0),
        season=seed.season if seed else None,
        price_cad=float(listing.get("price_cad") or i.get("price_cad") or 0.0),
        siblings=_collection_siblings(slug))

    pieces = content_mod.build_ecosystem(facts, launch_on=launch_on)
    problems = content_mod.check_ecosystem(pieces, facts)

    with ctx.db.session() as s:
        from sqlalchemy import select

        for piece in pieces:
            existing = s.scalar(select(ContentPiece).where(
                ContentPiece.product_slug == slug,
                ContentPiece.channel == piece.channel,
                ContentPiece.title == piece.title))
            if existing is not None:
                continue
            s.add(ContentPiece(product_slug=slug, channel=piece.channel, title=piece.title,
                               body=piece.body, scheduled_for=piece.scheduled_for,
                               state="drafted", detail=piece.detail))

    ctx.audit("marketing.scheduled" if not problems else "marketing.blocked",
              artifact=f"{slug}@{version}",
              detail={"pieces": len(pieces), "channels": sorted({p.channel for p in pieces}),
                      "problems": problems[:5], "published": False})
    return {"slug": slug, "version": version, "pieces": len(pieces),
            "problems": problems, "published": False}


@handlers.register("support.reply")
def handle_support_reply(ctx: JobContext) -> dict:
    """Triage a customer message and draft a reply from the exact released version.

    The version is an input, not a lookup of "the current one". A customer who bought 1.0.0
    must be answered from 1.0.0; answering from 1.1.0 because it happens to be newer is how a
    support system tells someone their correct work is wrong.

    Nothing is sent. There is no messaging integration, and the case is recorded as unsent
    rather than relying on that absence.
    """
    from ..support.department import CustomerExperience

    slug = ctx.job.inputs.get("slug")
    version = ctx.job.inputs.get("version")
    question = ctx.job.inputs["question"]
    customer = ctx.job.inputs.get("customer_ref", "unknown")

    cir = _load_cir(ctx, slug, version) if slug and version else None
    reply = CustomerExperience(ctx.db).handle(
        customer_ref=customer, message=question, cir=cir,
        product_slug=slug, version=version)

    ctx.audit("support.replied", artifact=f"{slug}@{version}" if slug else None,
              detail={"specialist": reply.specialist, "escalated": reply.escalated,
                      "sent": reply.sent})
    return reply.to_dict()


@handlers.register("support.triage")
def handle_support_triage(ctx: JobContext) -> dict:
    """Mine real support cases for themes and candidate defects (section 10)."""
    from ..support.department import CustomerExperience

    out = CustomerExperience(ctx.db).mine_cases(ctx.job.inputs.get("slug"))
    ctx.audit("support.mined", detail={"cases": out["cases"],
                                       "hotspots": out["row_hotspots"][:5]})
    for hotspot in out["row_hotspots"]:
        if hotspot["mentions"] >= 3:
            ctx.audit("support.defect_candidate", artifact=hotspot["product"],
                      detail=hotspot)
    return out


def _collection_siblings(slug: str) -> list[str]:
    """Other products in this product's family, for the cross-sell frame."""
    seed = _seed_for(slug)
    if seed is None or not seed.family:
        return []
    return [m.title for m in POOL
            if m.family == seed.family and m.slug != seed.slug and not m.is_bundle][:4]


def _persist_frames(ctx: JobContext, slug: str, version: str, frames, stored, blocking):
    """Record the frame plan so a later session can see what a listing was going to show."""
    from sqlalchemy import select

    reasons = list(blocking)
    with ctx.db.session() as s:
        for frame, meta in zip(frames, stored):
            row = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == slug, ListingAsset.version == version,
                ListingAsset.position == frame.position))
            if row is None:
                row = ListingAsset(product_slug=slug, version=version,
                                   position=frame.position)
                s.add(row)
            row.asset_class = frame.asset_class.value
            row.role = frame.role
            row.sha256 = meta["sha256"]
            row.claims = {"width_cm": frame.claims.finished_width_cm,
                          "height_cm": frame.claims.finished_height_cm,
                          "difficulty": frame.claims.difficulty,
                          "colors": list(frame.claims.colors)}
            row.approved = not reasons
            row.blocked_reasons = reasons[:10]


def _motifs_for(slug: str) -> list[str]:
    words = [w for w in slug.replace("_", "-").split("-")
             if w not in {"mosaic", "pattern", "concept", "throw", "blanket", "set",
                          "trio", "pair", "library", "bundle"} and not w.isdigit()]
    return words[:3]


def _difficulty(twin, cir) -> str:
    advanced = {"tr", "dc_inc", "dc_dec"}
    colors_used = len([c for c in twin.colors_used if c])
    if twin.stitch_types_used & advanced or colors_used > 3:
        return "intermediate"
    if colors_used > 1 or cir.construction != "flat_rows":
        return "confident beginner"
    return "beginner"


@handlers.register("collection.assemble")
def handle_collection_assemble(ctx: JobContext) -> dict:
    """Build a collection listing out of its members' real, certified releases.

    A bundle has no pattern of its own, so it has nothing to compile, nothing to reverse
    compile and nothing to render a chart from. What it has is members — and it may only be
    listed once every one of them has a certificate, because a bundle is a promise to deliver
    each of those patterns.

    When the members are not ready yet this raises a transient error rather than assembling a
    partial collection. The queue's backoff then retries it, which is exactly right: the
    bundle is not broken, it is early.
    """
    from sqlalchemy import select

    from ..core.models import Collection, Listing, PatternVersion, Product
    from ..core.resilience import TransientError
    from ..brand import bible

    slug = ctx.job.inputs["slug"]
    family = ctx.job.inputs.get("family")
    seed = _seed_for(slug)
    members = [m for m in POOL if m.family == family and not m.is_bundle]
    if not members:
        raise ValueError(f"{slug}: a bundle with no members cannot be assembled")

    with ctx.db.session() as s:
        certified: list[tuple[str, str]] = []
        for m in members:
            product = s.scalar(select(Product).where(Product.slug == m.slug))
            if product is None:
                continue
            pv = s.scalar(select(PatternVersion).where(
                PatternVersion.product_id == product.id,
                PatternVersion.certified == True))  # noqa: E712
            if pv is not None:
                certified.append((m.slug, pv.version))

    # The collection is the members that actually shipped, not every concept in the family.
    # The pool holds more Nordic Forest concepts than the portfolio selected, and a bundle
    # advertising a stocking nobody engineered would be a promise we cannot keep. Two is the
    # floor: one pattern is not a collection.
    ready = {c[0] for c in certified}
    members = [m for m in members if m.slug in ready]
    if len(members) < 2:
        waiting = sorted(ready)
        ctx.audit("collection.waiting", artifact=slug,
                  detail={"certified_members": waiting})
        raise TransientError(
            f"{slug} cannot be listed yet: only {len(members)} of its patterns are certified. "
            f"A bundle is a promise to deliver each of its patterns, so it waits for them.")

    prices = [m.price_cad for m in members]
    verdict = pricing_mod_intel.price_bundle(prices)

    titles = [m.title for m in members]
    collection_name = (seed.family or slug).replace("-", " ").title()
    name_problems = bible.check_collection_name(collection_name)

    description = (
        f"{collection_name}: {len(members)} crochet patterns that share one motif library and "
        f"one palette, sold together.\n\n"
        + "\n".join(f"- {t}" for t in titles)
        + f"\n\nBuying them together saves CA${verdict.saving_cad:.2f} "
          f"({verdict.saving_pct:.0%}) against CA${verdict.member_total_cad:.2f} for the same "
          f"patterns bought separately. That is a saving against the prices we actually "
          f"charge, not against a reference price we invented.\n\n"
          f"Every pattern in this collection was compiled and checked row by row before "
          f"release, and each one's chart is generated from the same data as its written "
          f"instructions.")

    with ctx.db.session() as s:
        row = s.scalar(select(Collection).where(Collection.slug == slug))
        if row is None:
            row = Collection(slug=slug, family=family or slug)
            s.add(row)
        row.title = collection_name
        row.season = seed.season if seed else None
        row.palette = dict(bible.PALETTE)
        row.story = description

        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == "collection"))
        if listing is None:
            listing = Listing(product_slug=slug, version="collection")
            s.add(listing)
        listing.title = f"{collection_name} Collection | {len(members)} Crochet Patterns | PDF"
        listing.description = description
        listing.tags = [f"{collection_name.split()[0].lower()} collection",
                        "crochet pattern set", "pattern bundle pdf"]
        listing.price_cad = verdict.price_cad
        listing.state = "draft"
        listing.seo_score = 0.0
        listing.chain_version = CHAIN_VERSION

    ctx.audit("collection.assembled", artifact=slug, detail={
        "members": [m[0] for m in certified], "price_cad": verdict.price_cad,
        "saving_cad": verdict.saving_cad, "name_problems": name_problems,
        "published": False})
    return {"slug": slug, "members": [m[0] for m in certified],
            "price_cad": verdict.price_cad, "saving_cad": verdict.saving_cad,
            "saving_pct": verdict.saving_pct, "name_problems": name_problems}


@handlers.register("physical.record")
def handle_physical_record(ctx: JobContext) -> dict:
    """Take one real crocheted sample and let it change what the company claims.

    The only measured input in the system. It does two different things and the difference is
    the point: the yarn figure is *calibrated* against it, and the finished size is
    *falsified* by it. Folding a size disagreement into the calibration factor would turn the
    one check that can catch a wrong geometry model into a number that quietly absorbs it.

    A sample that disagrees about size raises a defect against the product, which halts its
    publication. That is the correct outcome: the listing's size claim is wrong, and no
    amount of yarn arithmetic fixes a basket that is not the size we said.
    """
    from ..gates.incidents import DefectReport, IncidentTracker
    from ..quality.physical import BallBand, SampleReport, assess, calibration_from_db, record

    i = ctx.job.inputs
    slug, version = i["slug"], i.get("version", "1.0.0")
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result)   # uncalibrated on purpose: this is what we predicted

    report = SampleReport(
        product_slug=slug, version=version, tester_ref=i.get("tester_ref", "owner"),
        grams_by_color={str(k): float(v) for k, v in (i.get("grams_by_color") or {}).items()},
        ball_band=BallBand(grams=float(i["ball_band_grams"]),
                           metres=float(i["ball_band_metres"])),
        hook_mm=i.get("hook_mm"),
        measured_width_cm=i.get("measured_width_cm"),
        measured_height_cm=i.get("measured_height_cm"),
        measured_around_cm=i.get("measured_around_cm"),
        hours=i.get("hours"),
        notes=i.get("notes", ""),
        instructions_followed=bool(i.get("instructions_followed", True)))

    assessment = assess(report, twin, cir)
    row_id = record(ctx.db, assessment)
    ctx.audit("physical.recorded", artifact=f"{slug}@{version}",
              detail={"row": row_id, **assessment.to_dict()})

    if assessment.size_agrees is False:
        tracker = IncidentTracker(ctx.db)
        for finding in assessment.findings:
            if finding.code != "SAMPLE_SIZE_DISAGREES":
                continue
            tracker.report(DefectReport(
                product_slug=slug, pattern_version=version, component=None, row=None,
                customer_ref=f"physical-test:{row_id}", text=finding.message))
        ctx.audit("physical.size_disagreement", artifact=f"{slug}@{version}",
                  detail={"measured": assessment.to_dict()["measured_metres"],
                          "findings": [f.code for f in assessment.findings]})

    # A usable sample changes every yardage figure for its yarn and stitch, which means the
    # PDFs and listings built from the old estimate are now stale. Keyed on the factor, so
    # the rebuild happens once per calibration rather than once per rebuild cadence.
    factor = calibration_from_db(ctx.db, cir)
    rebuilt: list[str] = []
    if assessment.usable_for_calibration and factor != 1.0:
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": version,
                           "release": i.get("release", "")},
                          idempotency_key=chain_key("assets", slug, version,
                                                    f"cal{factor}"))
        if job is not None:
            rebuilt.append(f"{slug}@{version}")

    return {"slug": slug, "version": version, "physical_test_id": row_id,
            "factor": assessment.factor, "calibration_now": factor,
            "size_agrees": assessment.size_agrees,
            "usable": assessment.usable_for_calibration,
            "findings": [f.code for f in assessment.findings],
            "rebuilt": rebuilt}



@handlers.register("model.probe")
def handle_model_probe(ctx: JobContext) -> dict:
    """Ask the model provider whether it can actually serve a request, and record the answer.

    A key is not a capability. The key the owner supplied on 2026-09-19 authenticates and the
    account behind it cannot serve a request, so the build executor's model gate reads this
    probe rather than an environment variable -- and when credits arrive, the next run of this
    cadence opens the gate with nobody having to remember.

    The probe is the smallest call the API accepts, on the cheapest model, checked against the
    monthly ceiling first like every other call. GREEN by the authority matrix: no
    publication, no customer contact, and spend bounded before the request is made.
    """
    from ..gateway import anthropic

    record = anthropic.probe(ctx.db, job_id=ctx.job.id)
    ctx.audit("model.probe.ok" if record["ok"] else "model.probe.unavailable",
              detail={k: v for k, v in record.items() if k != "key"})
    return record


@handlers.register("ops.continuity")
def handle_continuity(ctx: JobContext) -> dict:
    """Export the database portably and prove the export can be restored.

    Requirement 51, and the gap Build 1 wrote into its own baseline: production state was not
    backed up from the application environment. The proof is the point -- a backup nobody has
    restored is a hope, and the previous drill was honest that it had never verified a
    Postgres restore because it needed a scratch database to do it.

    This runs against whatever database it is pointed at, including production, because the
    export format is engine-independent and the scratch target is a local SQLite file. It
    reads; it never writes to the source.

    GREEN by the authority matrix: no publication, no spend, no customer contact. The
    connection string is redacted before anything is recorded.
    """
    import tempfile

    from ..core import continuity

    work = ctx.job.inputs.get("work_dir") or tempfile.mkdtemp(prefix="continuity-")
    proof = continuity.prove_restore(ctx.db, work)
    detail = proof.to_dict()
    detail["source"] = proof.export.source          # already redacted
    detail["bytes"] = proof.export.bytes_written
    detail["work_dir_is_durable"] = False

    ctx.audit("continuity.verified" if proof.ok else "continuity.failed", detail=detail)

    if not proof.ok:
        # A continuity failure is not a log line to scroll past: it means the company's
        # unrecoverable history is not actually recoverable. Raised as a correlated incident
        # so it re-uses the existing P1 machinery -- one incident that counts repeats rather
        # than a new row every scheduled run.
        from sqlalchemy import select

        from ..core.models import Incident

        signature = "continuity.restore_unproven"
        with ctx.db.session() as s:
            existing = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved == False))  # noqa: E712
            if existing is None:
                s.add(Incident(
                    severity="P1", signature=signature,
                    summary="the continuity export could not be restored, so the "
                            "company's non-rederivable history is not recoverable",
                    detail=detail, halts_publication=False))
            else:
                existing.report_count += 1
                existing.detail = detail

    # Only a proved export is retained. Keeping one that failed its own restore would put a
    # file nobody can use where the next operator will find it and believe it.
    if proof.ok:
        retained = continuity.retain(ctx.db, proof.export.path, proof.export)
        detail["retained"] = retained
        ctx.audit("continuity.retained", detail=retained)

    # Recorded every run. The archive now survives the container -- it is held in the
    # database, which is what a redeploy and a crash cannot take away. It does not survive
    # the provider disappearing, which is the failure #51 actually names, so the claim stops
    # exactly where the evidence does and the owner queue carries the off-provider decision.
    ctx.audit("continuity.storage_not_offsite", detail={
        "reason": "the retained archive lives in the database it describes, so it survives "
                  "a container replacement, a redeploy and a crash, and not the loss of the "
                  "provider. An off-provider copy needs a bucket and a credential, which is "
                  "an owner decision and is not claimed here.",
        "retained_archives": continuity.RETAINED_ARCHIVES,
    })
    return detail


@handlers.register("seasonal.sentinel")
def handle_seasonal_sentinel(ctx: JobContext) -> dict:
    """Recompute every certified pattern's launch dates and escalate what is at risk.

    Requirements 283, 296, 310, 311, and the owner's instruction after the first run of this
    engine found something: use it continuously rather than rediscovering seasonal timing
    manually. Timing is not a fact anybody establishes once -- a date that was comfortable in
    September is missed in October without anything changing except the date.

    GREEN by the authority matrix: it computes dates and writes audit records. It publishes
    nothing, spends nothing and contacts nobody.
    """
    from datetime import date as _date

    from ..seasonal.leadtime import catalogue_plans

    # `as_of` lets an operator ask what the room looked like, or will look like, on a given
    # day -- and lets a test drive the at-risk branch deterministically instead of waiting for
    # the calendar to produce one. Absent, it is today.
    as_of = ctx.job.inputs.get("as_of")
    room = catalogue_plans(ctx.db, today=_date.fromisoformat(as_of) if as_of else None)
    counts = room["counts"]
    at_risk = [r for r in room["at_risk_or_missed"] if r["status"] == "at_risk"]
    missed = [r for r in room["at_risk_or_missed"] if r["status"] == "missed"]

    ctx.audit("seasonal.assessed", detail={
        "products_scheduled": room["products_scheduled"],
        "counts": counts,
        "calibration": room["calibration"],
        # The rows somebody can still act on, named. A count is not an action.
        "at_risk": [{"slug": r["slug"], "event": r["event"],
                     "days_to_latest": r["days_to_latest"]} for r in at_risk[:20]],
        "missed": [{"slug": r["slug"], "event": r["event"],
                    "recommendation": r["recommendation"]} for r in missed[:20]],
    })

    # An at-risk window is the last one in which reallocating effort changes the outcome, so
    # it is raised rather than logged. Missed windows are not incidents: #297 already decided
    # what happens to them, and an incident per missed product every day is noise that trains
    # everyone to ignore the channel.
    if at_risk:
        from ..core.models import Incident

        soonest = min(at_risk, key=lambda r: r["days_to_latest"])
        signature = f"seasonal.at_risk:{soonest['slug']}:{soonest['event']}"
        with ctx.db.session() as s:
            from sqlalchemy import select

            existing = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved == False))  # noqa: E712
            if existing is None:
                s.add(Incident(
                    severity="P2", signature=signature,
                    product_slug=soonest["slug"],
                    summary=(f"{soonest['slug']} has {soonest['days_to_latest']} days of "
                             f"runway left for {soonest['event']}: past its preferred launch "
                             f"date and inside the last window where reallocating effort "
                             f"still changes whether a customer can finish the object in "
                             f"time. After the latest effective date the only honest options "
                             f"are pivot, simplify or hold (#297)."),
                    halts_publication=False,
                    detail={"slug": soonest["slug"], "event": soonest["event"],
                            "days_to_latest": soonest["days_to_latest"],
                            "latest_effective_launch": soonest["latest_effective_launch"]},
                ))

    # #123: the collection calendar's dated commitments, checked on the same cadence. The
    # launch-date work above answers "can a customer still finish this"; this answers "did
    # the work that had to happen by now happen", which slips silently -- a phase that is
    # late does not announce itself, it becomes the next phase.
    from ..seasonal.calendar import collection_calendar
    from ..radar.market import SEASONAL_EVENTS

    today = _date.fromisoformat(as_of) if as_of else _date.today()
    behind: list[dict] = []
    for event in SEASONAL_EVENTS:
        event_date = event.event_date
        if event_date < today:
            try:
                event_date = event_date.replace(year=event_date.year + 1)
            except ValueError:  # pragma: no cover - 29 February
                continue
        calendar = collection_calendar(event.name, event_date, today=today)
        if calendar["missed"]:
            behind.append({"event": event.name,
                           "event_date": event_date.isoformat(),
                           "missed": [m["milestone"] for m in calendar["missed"]],
                           "next_due": calendar["next_due"]})

    if behind:
        from sqlalchemy import select

        from ..core.models import Incident
        from ..seasonal.calendar import MILESTONES

        # One incident for the worst-affected event rather than one per missed milestone:
        # eight rows about one Christmas is the noise that trains everybody to close the
        # channel, and the event is the unit somebody can actually act on.
        worst = max(behind, key=lambda b: len(b["missed"]))
        signature = f"seasonal.calendar_behind:{worst['event']}"
        with ctx.db.session() as s:
            existing = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved == False))  # noqa: E712
            if existing is None:
                s.add(Incident(
                    severity="P2", signature=signature,
                    summary=(f"{worst['event']}: {len(worst['missed'])} of "
                             f"{len(MILESTONES)} collection milestones are already past "
                             f"({', '.join(worst['missed'][:3])}). A missed date is a "
                             f"portfolio failure rather than a scheduling detail, and the "
                             f"failure is silent -- a phase that slips becomes the next "
                             f"phase, and the first visible symptom is a product that lists "
                             f"in December (#123)."),
                    halts_publication=False,
                    detail={"behind": behind, "as_of": today.isoformat()}))

    ctx.audit("seasonal.calendar_checked", detail={
        "as_of": today.isoformat(),
        "events_behind": [b["event"] for b in behind],
        "events_checked": len(SEASONAL_EVENTS)})

    # The compression programme for every priority occasion, recomputed on the same cadence.
    # This is the half that makes the owner's correction automatic rather than remembered: as
    # a lane's runway closes, the mix moves into the fastest lane still open and the
    # departments that can no longer be finished drop out by themselves. A retirement is
    # recorded as a transition, because "FLAGSHIP closed today" is the sentence a reader
    # needs and "FLAGSHIP is closed" is the one they will misread a fortnight later.
    from ..seasonal import uncertainty
    from ..seasonal.compression import priority_shares, programme

    samples = uncertainty.sample_count(ctx.db)
    programmes = []
    overdue_prep: list[dict] = []
    for name in priority_shares()["shares"]:
        try:
            plan = programme(name, today=today, samples=samples)
        except Exception as exc:  # noqa: BLE001 - a calendar fault must not stop the sentinel
            ctx.audit("seasonal.compression_failed",
                      detail={"event": name, "error": str(exc)[:300]})
            continue
        late = [row for row in plan["preparation"] if row["overdue"]]
        overdue_prep.extend(late)
        programmes.append({
            "event": name, "days_away": plan["days_away"], "mode": plan["mode"]["mode"],
            "leading_lane": plan["mix"]["leading_lane"],
            "shares": plan["mix"]["shares"],
            "retired_classes": [r["lane"] for r in plan["retired_classes"]],
            "departments": [a["department"] for a in plan["arenas"]],
            "capacity_share": plan["capacity"]["share"],
            "overdue_preparation": [f"{r['lane']}:{r['stream']}" for r in late][:10],
        })
        ctx.audit("seasonal.compression", detail=programmes[-1])

    if overdue_prep:
        from sqlalchemy import select

        from ..core.models import Incident

        soonest = min(overdue_prep, key=lambda r: r["days_until"])
        signature = f"seasonal.preparation_late:{soonest['lane']}:{soonest['stream']}"
        with ctx.db.session() as s:
            existing = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved == False))  # noqa: E712
            if existing is None:
                s.add(Incident(
                    severity="P3", signature=signature,
                    summary=(f"{soonest['stream']} for the {soonest['lane']} lane should "
                             f"have started {abs(soonest['days_until'])} days ago. "
                             f"{soonest['why']} A product ready on its launch date is late: "
                             f"indexing is not instant, and a listing nobody can find is "
                             f"not a launch."),
                    halts_publication=False,
                    detail={"overdue": overdue_prep[:20], "as_of": today.isoformat()}))

    return {"products_scheduled": room["products_scheduled"], "counts": counts,
            "at_risk": len(at_risk), "missed": len(missed),
            "collection_calendar_behind": behind,
            "compression": programmes}


@handlers.register("etsy.probe")
def handle_etsy_probe(ctx: JobContext) -> dict:
    """Ask the Etsy API whether these credentials can actually serve a request.

    The owner's condition on the credentials: the gate opens from a successful read, not from
    the variables existing. Etsy v3 refuses the keystring alone -- "Shared secret is required
    in x-api-key header" -- so a half-configured credential is indistinguishable from a
    working one until something asks.

    The smallest sanctioned read: an application ping, which returns an application id and
    nothing about anybody's shop. GREEN by the authority matrix -- read-only, public, no
    publication, no spend, no customer contact.
    """
    from ..intel import etsy_public

    record = etsy_public.probe(ctx.db)
    ctx.audit("etsy.probe.ok" if record["ok"] else "etsy.probe.unavailable",
              detail=record)
    return record


@handlers.register("mjs.scan")
def handle_mjs_scan(ctx: JobContext) -> dict:
    """Scan the named benchmark catalogue: baseline once, then only what changed.

    The owner's top-priority mandate (#301). Runs whether or not the credential exists: with
    one it observes, without one it reports precisely why it could not and which requirements
    stay unmet. It never substitutes search snippets or fixtures for observation (#224).

    GREEN by the authority matrix: it reads public marketplace data, writes observations and
    queues internal work. It publishes nothing, spends nothing and contacts nobody.
    """
    from ..intel.observe import reclassify, scan_or_explain

    outcome = scan_or_explain(ctx.db)
    if not outcome["ran"]:
        ctx.audit("mjs.scan_blocked", detail=outcome)
        return {"ran": False, "reason": outcome["reason"][:200]}

    # Every scan re-routes the whole stored catalogue through the current pod vocabulary.
    # The scan itself only routes what it read, and it deliberately skips anything whose
    # fingerprint is unchanged -- so without this, widening the vocabulary would reach only
    # the listings the benchmark shop edits afterwards, which is close to none of them. It
    # reads stored titles, makes no Etsy call and usually moves nothing.
    routing = reclassify(ctx.db)
    if routing["moved"]:
        ctx.audit("mjs.reclassified", detail=routing)

    # #98: four of the eight learning domains are answerable from a catalogue somebody has
    # actually read, and until now nothing fed any of them. Recorded here because this is
    # the moment the evidence exists; the other four stay unobserved and say why.
    from ..intel.learning import ingest_benchmark

    learned = ingest_benchmark(ctx.db)
    if learned.get("recorded"):
        ctx.audit("learning.ingested", detail=learned)

    report = outcome["report"]
    ctx.audit("mjs.scanned", detail=report)
    return {"ran": True,
            "listings_known": report["catalogue_coverage"]["listings_known"],
            "new": len(report["changes"]),
            "reclassified": routing["moved"],
            "learning_domains": len(learned.get("recorded") or []),
            "inspected": report["catalogue_coverage"]["listings_inspected"]}


@handlers.register("improve.retrospective")
def handle_improvement_retrospective(ctx: JobContext) -> dict:
    """The weekly machine-readable business retrospective (#100).

    Reports what regressed as prominently as what improved, and names the bottleneck. A
    retrospective that lists only wins is a newsletter, and a newsletter is what a company
    reads instead of noticing.

    GREEN: reads rows and writes an audit record. It changes nothing.
    """
    from ..improve.bus import compounding
    from ..improve.cells import raise_plateau_defect, retrospective

    report = retrospective(ctx.db)
    report["compounding"] = compounding(ctx.db)
    # #104: a creative plateau is a top-level business defect, so it opens an incident
    # rather than appearing in a paragraph. Opened and closed here, because a defect that
    # never resolves becomes furniture and a company learns to read past it.
    plateau = raise_plateau_defect(ctx.db)
    report["creative_plateau"] = plateau
    ctx.audit("improvement.retrospective", detail=report)
    return {"bottleneck": report["bottleneck"],
            "regressed": report["regressed_cells"],
            "unmeasured": len(report["unmeasured_cells"]),
            "creative_plateau": plateau["verdict"],
            "plateau_incident": plateau["incident"]}

@handlers.register("launch.readiness")
def handle_launch_readiness(ctx: JobContext) -> dict:
    """Assess what stands between this shop and a live customer, and queue what is owner-only.

    The owner-action table has had the directive's columns -- action, reason, maximum cost,
    minutes, consequence of delay -- since the first build, and nothing had ever written to
    them. That was correct: until the catalogue, the imagery, the pricing and the copy
    existed, every blocker was ours, and asking the owner for an Etsy account because it
    would eventually be needed is exactly what the directive forbids. Now the remaining
    blockers really are the owner's, so the system says so itself, on a cadence, instead of
    waiting for someone to ask.
    """
    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..gateway.model_gateway import available_providers
    from ..launch.readiness import assess

    try:
        providers = available_providers()
    except Exception:  # noqa: BLE001 - a gateway problem must not stop the assessment
        providers = []

    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))
    readiness = assess(ctx.db, phase=ctx.phase.value, providers=providers,
                       storage_durable=store.durable)

    # Build-2 access gates join the same queue rather than starting a second one beside it.
    # Section 14 is explicit that there is one owner queue, and the reason is arithmetic: two
    # queues means the owner reads whichever they remember. These are capability requests
    # (#223), not launch requirements, so they are queued but do not move `readiness.ready`.
    from ..launch import access

    requests = list(readiness.owner_requests()) + access.owner_requests()

    queued: list[str] = []
    restated: list[str] = []
    with ctx.db.session() as s:
        # Keyed on the requirement, not on the action's wording. Comparing text worked only
        # while every action was a frozen string: as soon as one derived its figure from the
        # catalogue, a changed number read as a new request and the owner got two entries
        # for one decision. An owner queue that grows by seven a day is a queue nobody reads,
        # and one that lists the same decision twice with different numbers is worse.
        open_actions = {
            a.requirement_key: a for a in s.scalars(
                select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if a.requirement_key
        }
        # Actions queued before this column existed are adopted rather than duplicated. The
        # first version of this matched them on their full text, which protects every action
        # whose wording is unchanged and fails for the one that made this fix necessary: the
        # fee request's text moved with the catalogue, so it would have matched nothing and
        # been added beside the row it replaces. Production held exactly that row.
        #
        # So a keyless row is matched on a prefix that no derived figure reaches. The
        # prefixes are asserted distinct by a test, because a prefix match that hit two
        # requests would adopt one row into the wrong decision.
        keyless = [a for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))  # noqa: E712
            if not a.requirement_key]
        for request in requests:
            if request.key in open_actions:
                continue
            for row in keyless:
                if row.action[:ADOPT_PREFIX] == request.action[:ADOPT_PREFIX]:
                    row.requirement_key = request.key
                    open_actions[request.key] = row
                    break

        for request in requests:
            existing = open_actions.get(request.key)
            if existing is not None:
                # Same decision, possibly a different figure. Restate it in place: the owner
                # should see the number they would actually be charged, not two of them.
                if (existing.action != request.action
                        or existing.max_cost_cad != request.max_cost_cad):
                    existing.action = request.action
                    existing.reason = request.reason
                    existing.max_cost_cad = request.max_cost_cad
                    existing.minutes = request.minutes
                    existing.consequence_of_delay = request.consequence_of_delay
                    existing.blocks = request.blocks
                    restated.append(request.key)
                continue
            s.add(OwnerAction(requirement_key=request.key, action=request.action,
                              reason=request.reason,
                              max_cost_cad=request.max_cost_cad, minutes=request.minutes,
                              consequence_of_delay=request.consequence_of_delay,
                              blocks=request.blocks))
            queued.append(request.key)

        # Close what is no longer asked for. Without this the queue only ever grows: a
        # request stops being generated the moment its requirement is satisfied, but the row
        # it created stays open forever, so the owner opens the queue and is asked again for
        # the Etsy shop that exists, the developer app that is working and the model key that
        # is spending money. The owner's standing instruction is "do not ask me to repeat an
        # action already completed", and production was breaking it in four of ten rows.
        #
        # Guarded, because "not requested" and "not assessed" look identical from here. An
        # assessment that produced no requests at all is far more likely to be an assessment
        # that failed than a company with nothing left for its owner to do, and closing the
        # whole queue on that would destroy the record of what was asked.
        closed: list[str] = []
        if requests:
            wanted = {r.key for r in requests}
            for key, row in open_actions.items():
                if key in wanted:
                    continue
                row.done = True
                closed.append(key)

    ctx.audit("launch.assessed", detail={
        "ready": readiness.ready,
        "ours_to_do": [r.key for r in readiness.buildable],
        "blocked_on_owner": [r.key for r in readiness.blocked_on("owner")],
        "blocked_on_integration": [r.key for r in readiness.blocked_on("integration")],
        "owner_actions_added": len(queued),
        "owner_actions_queued": queued,
        "owner_actions_restated": restated,
        "owner_actions_closed": closed,
        "capabilities_unavailable": access.unmet_report()["unmet_capabilities"]})

    return {"ready": readiness.ready, "owner_actions_added": len(queued),
            "owner_actions_closed": closed,
            "outstanding": [r.key for r in readiness.outstanding]}


@handlers.register("chain.rebuild")
def handle_chain_rebuild(ctx: JobContext) -> dict:
    """Re-drive the post-certification chain for releases the current chain never reached.

    Certification is keyed per slug and version, correctly: a pattern is certified once. But
    everything *after* certification — assets, pricing, listing, launch, content — can change
    when the code changes, and a product certified under an older chain would otherwise never
    receive any of it.

    Production proved the need. Fifteen products were certified before listing imagery, search
    coverage and the content ecosystem existed. The next cycle ran, reported success, and
    produced nothing, because `gate.certify` had already run for those versions and so the
    downstream work was never enqueued.

    This looks for certified releases with no listing at the current chain version and starts
    them at `listing.draft`. It is idempotent: a release that already has one is left alone.
    """
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..gates.certificate import DOC_VERSION
    from .pipeline import _engineered_cir

    with ctx.db.session() as s:
        products = {p.id: p.slug for p in s.scalars(select(Product))}
        certified = [pv for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))]  # noqa: E712
        # Current, not merely present. An earlier version of this looked only for *missing*
        # listings and so left every stale one exactly as it was: the fix reached nothing, and
        # a stuttering title stayed on every shipped product through two deploys.
        # Current means built by this chain *from this release*. The chain version catches a
        # code change; the release hash catches a design change, which keeps the same slug
        # and the same version and so is invisible to the chain version alone.
        # What each existing listing was actually built from. Staleness is then a comparison
        # rather than a guess, and the comparison is recorded: a rebuild that says "nothing
        # to do" without showing its reasoning is unfalsifiable from outside the process,
        # and this decision has now been wrong twice.
        built_from = {
            (l.product_slug, l.version): f"c{l.chain_version}:{l.release_hash or 'none'}"
            for l in s.scalars(select(Listing))
        }

    started: list[str] = []
    reasons: dict[str, str] = {}
    for pv in certified:
        slug = products.get(pv.product_id)
        if not slug:
            continue
        wanted = f"c{CHAIN_VERSION}:{pv.release_hash or 'none'}"
        actual = built_from.get((slug, pv.version), "missing")
        if actual == wanted:
            reasons[slug] = "current"
            continue
        token = hashlib.sha256(f"{actual}->{wanted}".encode()).hexdigest()[:12]
        # The key names the *transition*, not the destination. Keying it on the destination
        # alone is what stopped the previous fix from delivering itself: the listing had
        # already been built from this release once, so the key was taken, and a listing
        # that went stale for any other reason could never be rebuilt. Keyed this way the
        # job is enqueued once per stale state rather than once per cadence.
        job = ctx.enqueue("listing", "listing.draft",
                          {"slug": slug, "version": pv.version,
                           "release": pv.release_hash or "", "rebuild": token},
                          idempotency_key=chain_key("listing", slug, pv.version,
                                                    pv.release_hash or "", token))
        if job is not None:
            started.append(f"{slug}@{pv.version}")
            reasons[slug] = f"{actual} -> {wanted}: restarted"
        else:
            # Stale, and this exact transition has already been attempted: the key is taken
            # by a job that ran and did not deliver the transition. That is a different
            # situation from a stale listing nobody has tried yet, and reporting them
            # identically is what made this invisible -- the rebuild said "stale" for a
            # product whose rebuild had already run twice and been refused downstream, and
            # from the audit record alone the two were indistinguishable.
            #
            # It is not an error. `assets.build` stopping on blocked imagery is the system
            # working: a listing whose pictures misrepresent the pattern must not proceed.
            # But it means this rebuild cannot fix it, and the thing that can is a code
            # change -- which arrives as a CHAIN_VERSION bump, changing `wanted`, the
            # transition and therefore the key.
            reasons[slug] = (f"{actual} -> {wanted}: already attempted under this chain "
                             f"version and not delivered; a downstream stage refused it")

    # A stored design the code no longer produces, or a certificate issued against a
    # document the writer no longer writes. Restarting at `listing.draft` cannot fix either,
    # because both live *above* certification: the CIR in the database is the stale thing.
    # This is the fifth face of "code changed, the deployed database did not", and the one
    # that broke the previous four fixes' own delivery mechanism.
    redrafted: list[str] = []
    for pv in certified:
        slug = products.get(pv.product_id)
        if not slug:
            continue
        try:
            fresh = _engineered_cir(slug, pv.version)
        except Exception:  # noqa: BLE001 - a design that no longer builds is not a rebuild
            continue
        if fresh is None:
            continue
        stale_design = fresh.to_dict() != pv.cir_json
        stale_document = (pv.certificate or {}).get("doc_version") != DOC_VERSION
        if not (stale_design or stale_document):
            continue
        job = ctx.enqueue("crochet_engineer", "cir.draft", {"slug": slug},
                          idempotency_key=(f"redraft:{slug}:{fresh.fingerprint}"
                                           f":d{DOC_VERSION}"))
        if job is not None:
            redrafted.append(f"{slug}@{pv.version}"
                             f"{' design' if stale_design else ''}"
                             f"{' document' if stale_document else ''}")

    # Collections are listed under the pseudo-version "collection" rather than a
    # PatternVersion, so they need their own line here or a rebuild leaves the bundle behind.
    collections_started: list[str] = []
    for seed in POOL:
        if not seed.is_bundle:
            continue
        # A collection has no release of its own -- it is its members -- so "built by this
        # chain" is the whole of the check.
        if built_from.get((seed.slug, "collection"), "missing").startswith(
                f"c{CHAIN_VERSION}:"):
            continue
        job = ctx.enqueue("listing", "collection.assemble",
                          {"slug": seed.slug, "family": seed.family},
                          idempotency_key=chain_key("collection", seed.slug, "collection"))
        if job is not None:
            collections_started.append(seed.slug)

    ctx.audit("chain.rebuilt", detail={"chain_version": CHAIN_VERSION,
                                       "doc_version": DOC_VERSION,
                                       "certified": len(certified),
                                       "restarted": started[:20],
                                       "restarted_count": len(started),
                                       "redrafted": redrafted[:20],
                                       "redrafted_count": len(redrafted),
                                       "collections_restarted": collections_started,
                                       "listings": reasons})
    return {"chain_version": CHAIN_VERSION, "doc_version": DOC_VERSION,
            "certified": len(certified), "restarted": started,
            "redrafted": redrafted, "collections_restarted": collections_started}


@handlers.register("ops.policy_watch")
def handle_policy_watch(ctx: JobContext) -> dict:
    """Check how old this company's reading of Etsy's rules is, and block what it must.

    Requirement 39. Deliberately does *not* fetch: no policy fetcher is connected, and a
    cadence that fails on every run because a dependency is absent is a dead letter with a
    schedule. What it does is the part that does not need the network — notice that a reading
    is stale or missing, and open a blocking incident for the workflows that reading governs.

    The incident is per source and opened once. A blocking incident re-raised every six hours
    is an alert people filter, which is the same as no alert but with more rows.

    GREEN by the authority matrix: it reads its own tables, writes audit rows and opens
    incidents. It fetches nothing, publishes nothing and spends nothing.
    """
    from sqlalchemy import select

    from ..core.models import Incident
    from ..gates.platform_policy import MAX_AGE_DAYS, POLICY_SOURCES, freshness

    report = freshness(ctx.db)
    unread = list(report["never_checked"])
    stale = [e["source"] for e in report["stale"]]
    needs_attention = unread + stale

    opened: list[str] = []
    with ctx.db.session() as s:
        open_signatures = {
            i.signature for i in s.scalars(select(Incident).where(
                Incident.resolved == False))  # noqa: E712
        }
        for source in needs_attention:
            signature = f"policy_stale:{source}"
            if signature in open_signatures:
                continue
            affects = ", ".join(POLICY_SOURCES[source][1])
            why = ("has never been read" if source in unread
                   else f"was last read more than {MAX_AGE_DAYS} days ago")
            s.add(Incident(
                severity="P2", signature=signature,
                summary=(f"Etsy {source.replace('_', ' ')} {why}. Until it is, "
                         f"{affects} cannot be certified against current policy, and a new "
                         f"asset or product class cannot be enabled (#35, #39)."),
                halts_publication=False,
                detail={"source": source, "url": POLICY_SOURCES[source][0],
                        "affects": list(POLICY_SOURCES[source][1]),
                        "owner_action": ("connect a policy reader, or read the page and "
                                         "record the snapshot by hand"),
                        "freshness": report}))
            opened.append(source)

    ctx.audit("policy.watched", detail={
        "all_fresh": report["all_fresh"], "never_checked": unread, "stale": stale,
        "incidents_opened": opened, "blocked_workflows": report["blocked_workflows"]})

    return {"all_fresh": report["all_fresh"], "never_checked": unread, "stale": stale,
            "incidents_opened": opened,
            "blocked_workflows": report["blocked_workflows"],
            "note": ("This cadence does not fetch. No policy reader is connected, and a "
                     "cadence that fails every run because a dependency is absent is a dead "
                     "letter with a schedule.")}


@handlers.register("build.tick")
def handle_build_tick(ctx: JobContext) -> dict:
    """The never-idle build loop's heartbeat, running in the deployed worker.

    Reconciles the task graph against the registry and the owner gates, then reports what is
    ready, what is parked and whether the loop is actually moving. It deliberately does *not*
    write code -- that is what a session does. What it does is make the decision about *what
    to work on next* survive the session ending, which is the part that used to live in a
    conversation and evaporate with it.

    A gate that opened since the last tick un-parks its requirements here, with nobody having
    to remember. A loop that has completed nothing while work is ready raises an incident; a
    loop that has completed nothing because everything is parked does not, because those are
    opposite situations that look identical from outside.

    GREEN by the authority matrix: it reads the registry, writes its own tables and may open
    an incident. It publishes nothing, spends nothing and contacts nobody.
    """
    from sqlalchemy import select

    from ..build2 import executor
    from ..core.models import Incident

    synced = executor.sync(ctx.db)
    snapshot = executor.queue(ctx.db)
    health = executor.watchdog(ctx.db)

    if synced["unparked"]:
        executor.record(
            ctx.db, kind="unpark",
            summary=(f"{len(synced['unparked'])} requirements un-parked because their gate "
                     f"opened: {synced['unparked'][:10]}"),
            detail={"requirement_ids": synced["unparked"],
                    "gates_open": synced["gates_open"]})

    if health.get("alarm"):
        signature = "build.stalled"
        with ctx.db.session() as s:
            existing = s.scalar(select(Incident).where(
                Incident.signature == signature, Incident.resolved == False))  # noqa: E712
            if existing is None:
                s.add(Incident(
                    severity="P2", signature=signature,
                    summary=(f"The build loop has completed nothing in "
                             f"{health['window_hours']} hours while "
                             f"{health['ready_total']} requirements are ready. Idle with "
                             f"ready work is a stalled loop; idle with everything parked "
                             f"would be correct, and the two look identical from outside."),
                    halts_publication=False,
                    detail={"watchdog": health, "next": health.get("next")}))
    else:
        # A loop that started moving again resolves its own stall, rather than leaving a red
        # row somebody has to notice and close.
        with ctx.db.session() as s:
            stale = s.scalar(select(Incident).where(
                Incident.signature == "build.stalled",
                Incident.resolved == False))  # noqa: E712
            if stale is not None and health.get("moving"):
                stale.resolved = True

    ctx.audit("build.ticked", detail={
        "ready": snapshot["ready_total"], "parked": snapshot["parked_total"],
        "blocked": snapshot["blocked_total"], "done": snapshot["done_total"],
        "unparked": synced["unparked"], "verdict": health["verdict"],
        "next": (snapshot["next"] or {}).get("requirement_id")})

    return {"ready": snapshot["ready_total"], "parked": snapshot["parked_total"],
            "blocked": snapshot["blocked_total"], "done": snapshot["done_total"],
            "parked_by_gate": snapshot["parked_by_capability"],
            "unparked": synced["unparked"],
            "next": snapshot["next"], "watchdog": health}


@handlers.register("creative.blinded")
def handle_creative_blinded(ctx: JobContext) -> dict:
    """Judge this catalogue against the observed human one, blinded (#94).

    Monthly rather than weekly. Creative capability does not change in a week, and a
    measurement that costs real money every seven days becomes a line item somebody
    eventually switches off -- which is worse than a slower measurement that survives.

    GREEN: it reads its own catalogue and an already-observed benchmark, spends model budget
    bounded by the monthly ceiling, and writes a row. It publishes nothing and contacts
    nobody. If the ceiling is close it judges fewer pairs and says so; a run that reports
    `unmeasured` because it could not afford the floor is the correct outcome, not a failure.
    """
    from ..creative import blinded
    from ..creative.audit import catalogue_concepts
    from ..gateway import routing
    from ..gateway.anthropic import AnthropicProvider
    from ..gateway.model_gateway import ModelGateway

    # The tier the task is routed to, rather than a model named here. Routing decides which
    # model answers which question and prices it; a handler picking its own would make the
    # ceiling's estimate a guess about a different call than the one being made.
    _task, tier = routing.route(blinded.TASK)
    gateway = ModelGateway([AnthropicProvider(model=tier.model)], registry=ctx.registry,
                           job_id=ctx.job.id)

    concepts = catalogue_concepts()
    try:
        result = blinded.run(ctx.db, concepts, gateway=gateway,
                             agent="creative_director",
                             max_pairs=blinded.MIN_PAIRS)
    except blinded.RunRefused as e:
        ctx.audit("creative.blinded_refused", detail={"reason": str(e)[:300]})
        return {"ran": False, "reason": str(e)[:200]}

    ctx.audit("creative.blinded", detail=result)
    return {"ran": True, "verdict": result["verdict"], "judged": result["pairs_judged"],
            "cost_cad": result["cost_cad"], "valid": result["valid"],
            "gateway_spend_cad": gateway.spend_cad()}


TOURNAMENT_ACTION = "creative.tournament"


@handlers.register("creative.tournament")
def handle_creative_tournament(ctx: JobContext) -> dict:
    """#3's staged tournament, run at its specified scale against one proven arena.

    The expedition asks "what could we make for this occasion" with a handful of deep
    concepts. This asks the harder question the owner put: **is there a Brambleloop answer to
    a proven arena we have no answer to at all**, and it asks it with a field wide enough
    that the answer is not an artefact of the sample.

    Three things make the number mean something this time.

    **The field is wide and cheap.** Roughly eighty concepts at the cheap tier, about CA$0.27,
    because the funnel's whole shape is to spend little across a wide field and concentrate
    cost after it has been cut. Eighty deep-tier concepts would cost nine times as much to
    learn the same thing.

    **It is one arena, not twelve.** A field spread across every department puts two or three
    concepts against each of them, which cannot support a comparison against anything.
    Breadth comes from the wheel moving the arena between cycles -- and the wheel reserves
    45% of its slots for Christmas, so the priority programme gets depth rather than a turn.

    **The gauntlet has something to fire on.** Our catalogue has no garments, so novelty
    against *us* is automatic and `sameness` cannot fire -- which is why the first
    expedition survived 18 of 18 and why that number meant "we have never made one of these"
    rather than "these are good". Screening against the benchmark's own listings is the half
    that can fail, and in a proven arena there are enough of them for it to.

    GREEN: reads observed listings and its own history, bounds spend before every batch,
    writes one row. Publishes nothing, contacts nobody. A tournament that survives nothing is
    stored exactly like one that survives ten.
    """
    from ..core.models import utcnow
    from ..creative import prospecting
    from ..creative.audit import catalogue_concepts
    from ..gateway import routing
    from ..gateway.anthropic import AnthropicProvider
    from ..gateway.model_gateway import ModelGateway

    found = prospecting.arenas(ctx.db)
    if not found:
        return {"ran": False, "reason": "no benchmark listing has been observed yet"}

    week = int(utcnow().timestamp() // (7 * 24 * 3600))
    arena = prospecting.choose(found, cycle=week)

    _task, tier = routing.route(prospecting.IDEATION_TASK)
    gateway = ModelGateway([AnthropicProvider(model=tier.model)], registry=ctx.registry,
                           job_id=ctx.job.id)
    catalogue = catalogue_concepts() + prospecting.discovered(ctx.db)

    try:
        result = prospecting.tournament(
            ctx.db, gateway=gateway, catalogue=catalogue,
            only=(arena.event, arena.pod))
    except prospecting.ProspectingRefused as e:
        ctx.audit("creative.tournament_blocked",
                  detail={"arena": arena.to_dict(), "reason": str(e)[:400]})
        return {"ran": False, "arena": f"{arena.event}/{arena.pod}",
                "reason": str(e)[:200]}

    with ctx.db.session() as s:
        from ..core.models import AuditLog
        s.add(AuditLog(actor="creative_director", action=TOURNAMENT_ACTION,
                       artifact=f"{arena.event}/{arena.pod}",
                       detail={k: v for k, v in result.items()
                               if k not in ("survivor_objects",)}))

    generated = result["field"]["generated"]
    attempted = generated > 0 or result["cost_cad"] > 0
    return {"ran": attempted, "arena": f"{arena.event}/{arena.pod}",
            "generated": generated, "survivors": len(result["survivors"]),
            "research_kill_rate": result["research_kill_rate"],
            "causes": result["causes"], "cost_cad": result["cost_cad"],
            "novelty_measurable": result["novelty_measurable"],
            "stages_run": result["stages_run"],
            "stages_not_run": result["stages_not_run"],
            "proposition_refused": result["proposition_refused"],
            "research_survivors": len(result["research_survivors"]),
            **({} if attempted else
               {"reason": "every batch came back malformed; nothing was generated or spent"})}


@handlers.register("creative.expedition")
def handle_creative_expedition(ctx: JobContext) -> dict:
    """Discovery into one proven-and-unserved arena (#104).

    Weekly, and it rotates: the arena is picked from the top proven gaps by the week number,
    so the catalogue broadens across departments instead of deepening in whichever one ranked
    first the day the cadence was written. Cost is roughly CA$0.32 a run at four slots, which
    is about 6% of the monthly ceiling a month.

    GREEN: it reads an already-observed benchmark and its own history, spends model budget
    bounded before each field, and writes a row. It publishes nothing and contacts nobody.
    An expedition that comes back empty is recorded as such -- that is evidence about this
    system's creative reach, and only keeping the successful runs would leave a record that
    flatters it.
    """
    from ..creative import prospecting
    from ..creative.audit import catalogue_concepts
    from ..gateway import routing
    from ..gateway.anthropic import AnthropicProvider
    from ..gateway.model_gateway import ModelGateway

    # Deliberately not caught. `NoArenasContradictsEvidence` means the matrix disagrees with
    # the catalogue of listings behind it, and a defect that makes discovery report "nothing
    # to do" must fail loudly rather than complete: a job that fails is re-driven by the next
    # deploy, and a job that succeeds with a false negative consumes its window.
    found = prospecting.arenas(ctx.db)
    if not found:
        ctx.audit("creative.expedition_blocked",
                  detail={"reason": "no benchmark listing has been observed yet"})
        return {"ran": False, "reason": "no benchmark listing has been observed yet"}

    from ..core.models import utcnow

    week = int(utcnow().timestamp() // (7 * 24 * 3600))
    arena = prospecting.choose(found, cycle=week)

    _task, tier = routing.route(prospecting.GENERATION_TASK)
    gateway = ModelGateway([AnthropicProvider(model=tier.model)], registry=ctx.registry,
                           job_id=ctx.job.id)
    catalogue = catalogue_concepts() + prospecting.discovered(ctx.db)

    try:
        result = prospecting.expedition(ctx.db, arena, gateway=gateway, catalogue=catalogue)
    except prospecting.ProspectingRefused as e:
        ctx.audit("creative.expedition_blocked",
                  detail={"arena": arena.to_dict(), "reason": str(e)[:400]})
        return {"ran": False, "arena": f"{arena.event}/{arena.pod}", "reason": str(e)[:200]}

    prospecting.store(ctx.db, result)

    # A run that proposed nothing and spent nothing did not happen, whatever it returned.
    # The first live expedition reported `ran: true` while both of its fields came back as
    # truncated JSON -- a false success, and the per-deploy re-drive only picks up `ran:
    # false`, so a fixed prompt would have waited a week for its next window. "Ran" means
    # work was attempted, not that the function returned.
    attempted = result["proposed"] > 0 or result["cost_cad"] > 0
    return {"ran": attempted, "arena": f"{arena.event}/{arena.pod}",
            "proposed": result["proposed"], "survivors": len(result["survivors"]),
            "forms": result["forms_discovered"], "cost_cad": result["cost_cad"],
            "answered_the_arena": result["answered_the_arena"],
            **({} if attempted else
               {"reason": "every field came back malformed; nothing was proposed or spent"})}


@handlers.register("seasonal.remerchandising")
def handle_remerchandising_review(ctx: JobContext) -> dict:
    """The periodic inspection #292 asks for, against the nearest priority occasion.

    Weekly. "Periodically inspect proven evergreen products" is a cadence, not a function
    somebody remembers to call, and a re-merchandising review that never runs is the same as
    one that does not exist.

    GREEN: it reads certified products, recorded sales and an already-observed benchmark
    catalogue. It changes no listing, publishes nothing and spends nothing -- and it cannot
    increment the catalogue by construction, because a re-merchandising move that changed
    construction, form, rows, stitch counts, gauge or the release hash is refused as a new
    product wearing a re-merchandising label.
    """
    from ..creative import prospecting
    from ..seasonal import remerchandising

    try:
        found = prospecting.arenas(ctx.db)
    except prospecting.NoArenasContradictsEvidence:
        found = []
    # The occasion to inspect against is the soonest proven one, because a review aimed at
    # an occasion nobody is shopping for yet is a report nobody can act on.
    arena = min(found, key=lambda a: a.days_away) if found else None
    event = arena.event if arena else "Christmas"
    pod = arena.pod if arena else ""

    report = remerchandising.review(ctx.db, event=event, pod=pod)
    ctx.audit("seasonal.remerchandising", detail=report)
    return {"event": event, "pod": pod or None,
            "candidates": len(report["candidates"]),
            "ready_moves": report["ready_moves"],
            "available": list(report["capabilities"]["available"]),
            "catalogue_growth": report["catalogue_growth"]}


@handlers.register("improve.role_work")
def handle_role_work(ctx: JobContext) -> dict:
    """One meta-agent's pass over the rows it answers for (#179).

    The agent *is* the role, so `ctx.job.agent` dispatches. Each pass reads and reports; none
    of them promotes anything, because proposing runs through #190's pipeline and promotion
    through #178's tiers, and a meta-agent that could promote would be the company rewriting
    itself faster than it can observe the results.

    What comes back is a count of rows read and things found, never a count of changes made.
    On an empty database most of these find nothing and say so, which is the correct output
    for a company with no customers: a swarm reporting activity here would be reporting on
    work it invented.

    GREEN: reads rows, writes an audit record, spends nothing.
    """
    from sqlalchemy import func, select

    from ..core.models import (Incident, Job, JobStatus, LedgerEntry, Lesson,
                               ConfigVersion, ListingAsset)
    from ..improve import roles

    role_key = ctx.job.agent
    try:
        role = roles.role(role_key)
    except roles.RoleRefused as exc:
        raise ValueError(
            f"{role_key!r} ran {roles.ROLE_JOB_TYPE} and is not a meta-agent role. The agent "
            f"is the role here, so an agent with no role has no rows it answers for") from exc

    read = found = 0
    with ctx.db.session() as session:
        if role_key == "evaluator":
            rows = list(session.scalars(select(ConfigVersion)))
            read = len(rows)
            found = sum(1 for r in rows if r.incumbent and not (r.measured_outcome or {}))
        elif role_key == "failure_miner":
            incidents = list(session.scalars(
                select(Incident).where(Incident.resolved.is_(False))))
            dead = session.scalar(select(func.count()).select_from(Job)
                                  .where(Job.status == JobStatus.DEAD)) or 0
            read = len(incidents) + dead
            found = len(incidents)
        elif role_key == "lesson_router":
            lessons = list(session.scalars(select(Lesson)))
            read = len(lessons)
            found = sum(1 for r in lessons if r.routed_to and not r.acted_on_by)
        elif role_key == "prompt_tool_challenger":
            configs = list(session.scalars(select(ConfigVersion)))
            read = len(configs)
            keys = {(r.kind, r.key) for r in configs}
            challenged = {(r.kind, r.key) for r in configs if not r.incumbent}
            found = len(keys - challenged)
        elif role_key == "cost_optimiser":
            entries = list(session.scalars(select(LedgerEntry)))
            read = len(entries)
            found = sum(1 for r in entries if (r.gross_cad or 0) > 0)
        elif role_key == "reliability_engineer":
            dead = session.scalar(select(func.count()).select_from(Job)
                                  .where(Job.status == JobStatus.DEAD)) or 0
            total = session.scalar(select(func.count()).select_from(Job)) or 0
            read = total
            found = dead
        elif role_key == "creative_critic":
            assets = list(session.scalars(select(ListingAsset)))
            read = len(assets)
            found = sum(1 for r in assets if not r.approved)
        else:  # experiment_designer
            # Experiments live in the growth portfolio, which has no rows in shadow mode.
            read = 0
            found = 0

    activity = roles.Activity(role_key=role_key, proposals_made=0, proposals_kept=0,
                              realised_uplift=0.0)
    card = roles.scorecard(activity)
    detail = {
        "role": role_key, "reads": roles.ROLE_READS[role_key],
        "rows_read": read, "found": found,
        "measured_by": role.measured_by,
        "scorecard": card,
        "proposed": 0,
        "why": (f"read {read} row(s) and found {found}. This pass reports; proposing runs "
                f"through the upgrade pipeline and promotion through the tiers"),
    }
    ctx.audit("improve.role_work", detail=detail)
    return detail


@handlers.register("improve.nightly")
def handle_nightly_improvement(ctx: JobContext) -> dict:
    """The nightly improvement sweep, whose verdict is computed rather than asserted (#193).

    Seven stages. Each returns what it read and what it found, and a stage that read nothing
    reports `did_not_run` rather than a clean result -- because finding nothing in nothing has
    not established that there was nothing to find. A sweep is `complete` only when every
    stage ran, never because this handler returned without raising.

    In shadow mode several stages genuinely have nothing to read: there are no customers, no
    live listings and no challenger runs. The delta says so, night after night, and that is
    the correct output. A sweep that reported success on this state would be describing a
    company that does not exist.

    GREEN: it reads rows, writes an audit record and queues nothing that promotes itself.
    """
    from sqlalchemy import desc, func, select

    from ..core.models import AuditLog, CapabilityPoint, ConfigVersion, Incident, Lesson
    from ..improve import freshness, nightly

    results = []
    with ctx.db.session() as session:
        evidence = session.scalar(select(func.count()).select_from(CapabilityPoint)) or 0
        results.append(nightly.stage_ran(nightly.INGEST, read=evidence,
                                         found=evidence))

        incidents = list(session.scalars(select(Incident).where(Incident.resolved.is_(False))))
        results.append(nightly.stage_ran(nightly.MINE, read=len(incidents),
                                         found=len(incidents)))

        lessons = list(session.scalars(select(Lesson)))
        unacted = [row for row in lessons if row.routed_to and not row.acted_on_by]
        results.append(nightly.stage_ran(nightly.LESSONS, read=len(lessons),
                                         found=len(unacted)))

        configs = list(session.scalars(select(ConfigVersion)))
        challengers = [row for row in configs if not row.incumbent]
        results.append(nightly.stage_ran(nightly.CHALLENGERS, read=len(configs),
                                         found=len(challengers)))

    sweep = freshness.sweep(ctx.db)
    stuck = sorted(set(sweep["stale_learning"]) | set(sweep["churning"])
                   | set(sweep["never_measured"]))
    results.append(nightly.stage_ran(nightly.BOTTLENECKS,
                                     read=len(sweep["departments"]), found=len(stuck),
                                     stale=sweep["stale_learning"],
                                     churning=sweep["churning"],
                                     never_measured=sweep["never_measured"]))

    # Queueing is where this sweep deliberately stops. It opens nothing that promotes itself;
    # #190's pipeline and #178's tiers decide that, and a nightly job that could promote is a
    # company rewriting itself faster than it can observe the results.
    results.append(nightly.stage_skipped(
        nightly.QUEUE,
        "no safe improvement was queued: bottlenecks here are unmeasured departments, which "
        "need instrumenting rather than a proposal"
        if stuck else "nothing was stuck, so there was nothing to queue"))

    previous = None
    with ctx.db.session() as session:
        row = session.scalar(select(AuditLog).where(AuditLog.action == "improve.nightly")
                             .order_by(desc(AuditLog.id)).limit(1))
        if row is not None:
            previous = (row.detail or {}).get("delta")

    results.append(nightly.stage_ran(nightly.DELTA, read=len(results), found=len(results)))
    delta = nightly.delta(results, previous=previous)

    detail = {"verdict": delta["verdict"], "did_not_run": delta["did_not_run"],
              "total_read": delta["total_read"], "total_found": delta["total_found"],
              "delta": delta}
    ctx.audit("improve.nightly", detail=detail)
    return detail


@handlers.register("improve.weekly")
def handle_weekly_evolution(ctx: JobContext) -> dict:
    """The weekly deep cycle, and the architecture review that must be able to subtract (#194).

    Eight domains, each audited rather than visited: a domain with nothing read is
    `not_audited`, and the cycle will not call itself complete while one remains. The
    architecture half proposes nothing on its own here -- it reports what the freshness sweep
    and the velocity review found, and a week that only added would be asked why.

    GREEN: it reads rows and writes an audit record.
    """
    from sqlalchemy import func, select

    from ..core.models import CapabilityPoint, Incident, LedgerEntry, SupportCase
    from ..improve import freshness, weekly

    readings = []
    with ctx.db.session() as session:
        points = session.scalar(select(func.count()).select_from(CapabilityPoint)) or 0
        incidents = session.scalar(select(func.count()).select_from(Incident)) or 0
        cases = session.scalar(select(func.count()).select_from(SupportCase)) or 0
        ledger = session.scalar(select(func.count()).select_from(LedgerEntry)) or 0

    sweep = freshness.sweep(ctx.db)
    stuck = sorted(set(sweep["stale_learning"]) | set(sweep["churning"]))

    # Each domain reports the rows it actually read. Several are zero in shadow mode, and a
    # zero here reads `not_audited` rather than clean, which is what keeps the weekly report
    # from describing a healthy business nobody has looked at.
    for domain, read, found in (
            ("product_creativity", points, len(stuck)),
            ("pattern_correctness", points, 0),
            ("competitor_intelligence", len(sweep["departments"]),
             len(sweep["stale_learning"])),
            ("conversion", 0, 0),
            ("ads", 0, 0),
            ("support", cases, 0),
            ("infrastructure", incidents, incidents),
            ("cost", ledger, 0)):
        readings.append(weekly.DomainReading(domain=domain, read=read, findings=found))

    cycle = weekly.cycle(readings, [])
    plan = weekly.roadmap(cycle)
    detail = {"complete": cycle["complete"], "not_audited": cycle["not_audited"],
              "total_read": cycle["total_read"], "total_findings": cycle["total_findings"],
              "roadmap": plan}
    ctx.audit("improve.weekly", detail=detail)
    return detail


@handlers.register("ops.health")
def handle_health_sweep(ctx: JobContext) -> dict:
    """The continuous health sweep, and the repairs this system can actually perform (#185).

    Every fifteen minutes. The verdict this produces is deliberately allowed to say `idle`:
    a container can serve 200s, tick a worker, run a scheduler, hold an empty queue and
    complete nothing for a week, with every liveness signal green, because none of them is
    about work.

    It repairs nothing itself, and that is the finding rather than a gap. Both obvious
    repairs already happen: a lease is reclaimed on every queue claim, and a dead letter is
    re-driven once per deploy -- which is the right trigger, because a dead letter is fixed
    by a code change and a fifteen-minute timer would re-run a failure nothing has fixed,
    ninety-six times a day. What cannot be fixed at all -- a container restart, a missing
    credential, money already spent -- is escalated by name rather than attempted, because a
    repair that is announced and does not happen is worse than none: nobody looks.

    Escalation waits for persistence. One bad sweep is a blip and a deploy produces several;
    the same signal failing across consecutive sweeps is a condition, and only that raises an
    incident. The escalation carries the readings that produced it, because the first
    question anybody asks about an alert is what it actually saw.

    GREEN: it reads records, re-drives jobs the queue already permits, writes audit rows and
    incidents, and spends nothing.
    """
    import os

    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Incident
    from ..ops import health

    with ctx.db.session() as session:
        readings = health.read(
            session, runner_state=_runner_state(), env=dict(os.environ),
            # Both are facts about this moment rather than about a shared variable: this
            # handler is running inside a worker's job, and the job arrived from a cadence.
            executing_worker=True,
            from_cadence=bool((ctx.job.inputs or {}).get("cadence")))
        verdict = health.verdict(readings)
        remediation = health.remediation(session, readings)

    # History for the persistence rule, from this handler's own audit trail. A record that
    # lives only in memory forgets every condition each time the container is replaced,
    # which is exactly when conditions happen.
    with ctx.db.session() as session:
        rows = list(session.scalars(
            select(AuditLog).where(AuditLog.action == "ops.health")
            .order_by(desc(AuditLog.id)).limit(health.ESCALATE_AFTER_SWEEPS - 1)))
    history = []
    for row in reversed(rows):
        bad = ((row.detail or {}).get("bad") or [])
        history.append([health.Reading(sig, health.DOWN) for sig in bad
                        if sig in health.SIGNALS])
    history.append(readings)
    persistence = health.persistence(history)

    detail = {
        "state": verdict["state"],
        "bad": sorted(set(verdict["down"]) | set(verdict["degraded"])),
        "why": verdict["why"],
        "repaired_elsewhere": remediation["repaired_elsewhere"],
        "must_escalate": remediation["must_escalate"],
        "persistent": persistence["persistent"],
    }
    ctx.audit("ops.health", detail=detail)

    raised = []
    with ctx.db.session() as session:
        for signal in persistence["persistent"]:
            signature = f"health:{signal}"
            existing = session.scalar(select(Incident)
                                      .where(Incident.signature == signature)
                                      .where(Incident.resolved.is_(False)))
            if existing is not None:
                continue
            reading = next((r for r in readings if r.signal == signal), None)
            session.add(Incident(
                signature=signature, product_slug=None, severity="P1",
                halts_publication=False,
                summary=(f"{signal} has been bad for "
                         f"{health.ESCALATE_AFTER_SWEEPS} consecutive sweeps")[:500],
                detail={"signal": signal,
                        "reading": reading.to_dict() if reading else None,
                        "consecutive": persistence["consecutive"].get(signal),
                        "escalation": [e for e in remediation["must_escalate"]
                                       if e["signal"] == signal]}))
            raised.append(signature)
    detail["escalated"] = raised
    return detail


def _runner_state() -> dict:
    """What the in-process runner knows, when there is one."""
    try:
        from ..app import runner
    except Exception:  # pragma: no cover - the worker can run without the web app
        return {}
    return runner.STATE.to_dict()


@handlers.register("ops.sentinel")
def handle_stale_artefact_sentinel(ctx: JobContext) -> dict:
    """The permanent sentinel #173 asks for, against the artefacts that actually exist.

    Hourly. It compares every recorded artefact against the fingerprints the system holds
    now, and it also accounts for the artefacts that exist downstream with no provenance row
    at all -- because a sweep of the instrumented estate is not a sweep of the estate, and an
    artefact nobody fingerprinted has no mismatch to report.

    A mismatch raises a blocking incident against the product's own slug, which is the flag
    the publish path already consults, and asks for a rebuild. An absence raises a
    non-blocking one and joins the instrumentation backlog: blocking on absence today would
    halt the whole catalogue over instrumentation nobody fitted, which is a different problem
    from a stale artefact. `provenance.graduation()` says when that backlog is closed.

    GREEN: it reads records, writes incidents and audit rows, changes no artefact and spends
    nothing.
    """
    from ..ops import artefacts as provenance

    with ctx.db.session() as session:
        current = provenance.current_from_db(session)
        expected = provenance.expected_from_db(session)
        report = provenance.sweep(session, current=current, expected=expected)
        gate = provenance.graduation(session, current=current, expected=expected)

    detail = {
        "checked": report["checked"], "fresh": report["fresh"],
        "stale": report["stale"], "unproven": report["unproven"],
        "publication_blocked": report["publication_blocked"],
        "rebuild": report["rebuild"],
        "may_enforce_unproven": gate["may_enforce_unproven"],
    }
    ctx.audit("ops.sentinel", detail=detail)

    # A stale artefact is re-derivable, so the sentinel asks for the rebuild rather than
    # only reporting it. The rebuild is the existing chain stage; nothing new publishes.
    for slug in report["rebuild"]:
        ctx.enqueue("listing", "chain.rebuild", {"product_slug": slug},
                    idempotency_key=f"sentinel-rebuild:{slug}:{current.get(f'cir:{slug}', '')}")
    return detail


@handlers.register("ops.capacity")
def handle_capacity_review(ctx: JobContext) -> dict:
    """This week's allocation, recorded rather than remembered (#30, #5).

    Weekly. The whole argument of #30 is that the mix has to arrive as a number, because the
    default for a system with no audience is to do more engineering -- engineering is the
    work that is here, it always finishes, and it never requires anybody outside this
    company. A module nobody calls *is* "whatever was easiest to pick up", so the allocation
    is a cadence on the same reasoning as #292's re-merchandising review: one that never
    runs is the same as one that does not exist.

    It also records whether the two production queues are open, because that condition and
    the allocation's phase read the same evidence and should be seen to agree.

    GREEN: it reads the regression corpus, certified releases and open incidents, writes an
    audit row, and changes nothing. It spends nothing -- no model call is made.
    """
    from ..commerce import lanes
    from ..scale import allocation, runrate

    with ctx.db.session() as session:
        qa = lanes.qa_stable(lanes.observe(session))

    # The bottleneck, where it can be identified at all. It cannot today: the funnel's terms
    # need traffic and orders. `constraint()` says so itself rather than being asked to
    # guess, and the allocation stays on the untilted mix.
    observed = runrate.Observed()
    binding = runrate.constraint(observed)

    plan = allocation.allocate(qa=qa, constraint=binding if binding["identifiable"] else None)
    detail = {
        "mix": plan["mix"],
        "phase": plan["phase"],
        "tilted_toward": plan.get("tilted_toward"),
        "constraint": plan.get("constraint"),
        "two_queues_open": qa["stable"],
        "qa_reasons": qa["reasons"],
    }
    ctx.audit("ops.capacity", detail=detail)
    return detail


@handlers.register("mjs.reviews")
def handle_mjs_reviews(ctx: JobContext) -> dict:
    """Read the benchmark shop's reviews and record which complaints recur (#2, #98).

    Weekly. Reviews move slowly and this is the one observation that reaches the
    `customer_pain` domain without this company having customers.

    GREEN by the authority matrix: a sanctioned read-only call to an endpoint already in the
    allowlist. Nothing is published, nobody is contacted, and no review text, reviewer or
    quotation is stored -- what is kept is a count per theme, because a complaint theme is a
    fact about this category and a review is somebody's words.
    """
    from ..intel import learning
    from ..intel.etsy_public import NotConfigured, ReadFailed
    from ..intel.observe import scan_reviews

    try:
        themes = scan_reviews(ctx.db)
    except (NotConfigured, ReadFailed) as e:
        ctx.audit("mjs.reviews_blocked", detail={"reason": str(e)[:300]})
        return {"ran": False, "reason": str(e)[:200]}

    learned = learning.ingest_complaints(ctx.db, themes=themes)
    ctx.audit("mjs.reviews", detail={"themes": themes, "learning": learned})
    return {"ran": True, "reviews_read": themes["reviews_read"],
            "recurring": len(themes["recurring"]),
            "learning_domains": len(learned.get("recorded") or [])}


@handlers.register("ops.capability_probes")
def handle_capability_probes(ctx: JobContext) -> dict:
    """Ask each capability whether it still works, and write down the answer.

    Six-hourly. Three of the build executor's gates now read a recorded successful use
    rather than a configured variable, and this is what records one. The rendered-page
    worker, the model's eyes and the culture source each fail in ways configuration cannot
    see: a worker answered with a bot-protection challenge, a vision call that returns a
    polite apology instead of a description, a free API that rate-limited us.

    Run on a cadence rather than once because a capability proven in March is not a
    capability. The gate this pattern replaced -- an environment variable holding
    twenty-eight requirements -- needed nobody to keep checking, which was the fault.

    GREEN by the authority matrix: three reads. The vision probe spends a fraction of a cent
    and is checked against the monthly ceiling first like every other model call.
    """
    from ..culture import feeds
    from ..gateway import anthropic as gw
    from ..gateway import images
    from ..intel import browser

    results = {
        "rendered_pages": browser.probe(ctx.db),
        "image_vision": gw.vision_probe(ctx.db, job_id=ctx.job.id),
        "culture_feed": feeds.probe(ctx.db),
        # `image_generation` was missing from this list, which is why the gate could not
        # open on its own. The probe existed, the gate read it, and nothing on any cadence
        # ever called it -- so a capability that had been demonstrably working for hours was
        # recorded nowhere, and twelve requirements stayed parked on the absence of a row
        # nobody was writing. A gate that reads evidence needs something that produces it.
        "image_generation": images.probe(ctx.db, job_id=ctx.job.id),
    }
    opened = sorted(k for k, v in results.items() if v.get("ok"))
    ctx.audit("ops.capability_probes", detail={
        "results": {k: {"ok": v.get("ok"), "reason": v.get("reason", "")[:200]}
                    for k, v in results.items()},
        "working": opened})
    return {"probed": sorted(results), "working": opened,
            "note": ("a capability proven once is not a capability. Each of these writes a "
                     "row a gate reads, and a gate whose evidence has gone stale closes")}


@handlers.register("culture.sweep")
def handle_culture_sweep(ctx: JobContext) -> dict:
    """Read reference interest for the topics this catalogue is merchandised against (#133).

    Daily. The radar has refused to report trends since it was written, correctly, because a
    source-less radar reporting nothing looks exactly like a radar with a quiet week. This
    connects the first of the two series #140 needs; the second is marketplace demand and
    arrives with listings, which is stated rather than papered over.

    GREEN: a free, keyless, sanctioned read with an identifying user agent, no spend and no
    account. Courtesy limits live in the module rather than in configuration.
    """
    from ..core.resilience import PermanentError, TransientError
    from ..culture import classify, demand, feeds, radar

    # Discovery first, so the radar can find what nobody thought to ask about (#133). A
    # hand-written topic list reflects its author rather than the culture, which is the
    # opposite of early discovery -- so the day's most-read articles are the candidates and
    # the fixed list is the floor.
    discovered: list[str] = []
    discovery_error = ""
    try:
        found = feeds.discover()
        discovered = [t["article"] for t in found["topics"]]
    except (PermanentError, TransientError) as exc:
        discovery_error = str(exc)[:300]

    filed = classify.classify(discovered, db=ctx.db) if discovered else {"filed": {}}
    # Sensitive topics are dropped here rather than filed and filtered later. The most-read
    # article on a given day is frequently a death or a disaster, and a radar that carries
    # those forward as opportunities is a radar nobody should have built.
    placed = {t: d for t, d in (filed.get("placed") or {}).items()
              if not classify.sensitive(t)}

    topics = feeds.env_override() or feeds.default_articles(ctx.db)
    watched = topics + [t for t in placed if t not in topics]
    result = feeds.sweep(ctx.db, watched[:feeds.MAX_ARTICLES_PER_SWEEP])

    # The marketplace half of #140's two series. Without it `lead_lag` has one series, and
    # one series cannot lead anything.
    demand_recorded = 0
    for reading in result["readings"]:
        got = demand.record(ctx.db, reading["article"], signal_key=reading["signal_key"])
        demand_recorded += got.get("recorded", 0)

    # Delivering the findings, not just listing where they could go (#147).
    routed = radar.route_findings(ctx.db)

    ctx.audit("culture.sweep", detail={
        "routed": routed["recorded"], "routed_skipped": routed["skipped"][:5],
        "source": result["source"], "recorded": result["recorded"],
        "attempted": result["attempted"], "failures": result["failures"][:5],
        "discovered": len(discovered), "placed": len(placed),
        "sensitive_dropped": len(filed.get("sensitive") or []),
        "discovery_error": discovery_error,
        "demand_points": demand_recorded})
    return {"ran": True, "recorded": result["recorded"],
            "attempted": result["attempted"],
            "failures": len(result["failures"]),
            "discovered": len(discovered), "placed": len(placed),
            "demand_points": demand_recorded, "routed": routed["recorded"],
            "channel": result["channel"], "measures": result["measures"]}


# Images judged per run. Raised from ten on 2026-09-20: see the cadence comment in
# `runtime.worker` for why the old number was a ceiling decision rather than a depth one.
GALLERY_BATCH = 25


@handlers.register("intel.gallery_analysis")
def handle_gallery_analysis(ctx: JobContext) -> dict:
    """Judge a batch of observed gallery images, once the capability has been proven (#209).

    Two-hourly, twenty-five images a run, in listing-recency order because that is the order
    commercial value arrives in. It was ten every four hours, set against the old CA$25
    ceiling, which put the benchmark's visual evidence nineteen days away; the owner's
    quality-first policy names MJs analysis depth as something not to reduce for cost, so the
    rate is now set by how fast the evidence is worth having.

    Self-limiting by construction: once the backlog empties this judges only new and changed
    listings, so the standing cost falls to whatever the benchmark shop publishes. A rate
    that stayed high against an empty queue would be waste rather than depth.

    Refuses to run before a vision probe has succeeded. Writing the call is not the same as
    the call working, and an analysis run against a broken vision path would record a batch
    of refusals as though the backlog had been attempted.

    GREEN: reads observed URLs, spends inside the ceiling, stores observations and never a
    picture or a description of the depicted design.
    """
    from ..finance import spend_policy
    from ..gateway.anthropic import vision_usable
    from ..intel import benchmarks, vision

    if not vision_usable(ctx.db):
        ctx.audit("intel.gallery_analysis_blocked",
                  detail={"reason": "no vision probe has succeeded"})
        return {"ran": False,
                "reason": ("no vision.probe has succeeded, so nothing has proven it can "
                           "look at an image. The backlog waits rather than filling with "
                           "refusals")}

    # This purpose's share of the month, checked before the batch rather than discovered at
    # the ceiling. Measured at about CA$0.029 an image, the raised cadence is CA$8.70 a day
    # while the backlog drains -- fine for four days and CA$260 a month if the queue never
    # empties, and a capability whose safety depends on an assumption about a queue has no
    # guard at all.
    allowance = spend_policy.may_spend(ctx.db, vision.TASK)
    if not allowance["may_spend"]:
        ctx.audit("intel.gallery_analysis_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"], "allowance": allowance,
                "constrained": ("benchmark gallery analysis stopped at its share of the "
                                "month rather than being run on a weaker model")}

    result = vision.analyse(ctx.db, benchmarks.MJS_KEY, limit=GALLERY_BATCH,
                            job_id=ctx.job.id)
    ctx.audit("intel.gallery_analysis", detail={
        "judged": result["judged"], "attempted": result["attempted"],
        "remaining": result["remaining"], "cost_cad": result["cost_cad"],
        "failures": result["failures"][:5]})
    return {"ran": True, "judged": result["judged"], "attempted": result["attempted"],
            "remaining": result["remaining"], "cost_cad": result["cost_cad"],
            "failures": len(result["failures"])}


@handlers.register("ops.offsite_archive")
def handle_offsite_archive(ctx: JobContext) -> dict:
    """Write the day's archive off this hosting provider, and prove it restores.

    Requirement 51's second half. `ops.continuity` proves the export restores; this proves a
    copy of it exists somewhere that losing Railway does not take with it. They are separate
    jobs because they answer separate questions, and a single job reporting one verdict would
    let a healthy local restore stand in for an archive that was never written.

    An unconfigured destination is recorded as a failed archive, not skipped. The gate reads
    these rows: a job that returned early on a missing variable would leave the last row
    saying `ok` from whenever the credential last worked, which is the shape of defect this
    build keeps finding.

    GREEN by the authority matrix: it reads the database, writes one object to a bucket the
    owner provisioned, and reads it back. No publication, no model spend, no customer
    contact.
    """
    import tempfile

    from ..core import offsite

    work = ctx.job.inputs.get("work_dir") or tempfile.mkdtemp(prefix="offsite-")
    record = offsite.archive(ctx.db, work_dir=work)

    pruned: dict = {"skipped": "the archive did not complete, so nothing was aged out"}
    if record.get("ok"):
        # Only after a good write. Pruning on the day the upload failed would remove the
        # oldest copy at exactly the moment the newest one does not exist.
        pruned = offsite.prune(ctx.db)

    ctx.audit("offsite.archived" if record.get("ok") else "offsite.failed",
              detail={"ok": record.get("ok"), "stage": record.get("stage"),
                      "reason": record.get("reason", "")[:300],
                      "key": record.get("key", ""),
                      "rows_restored": record.get("rows_restored"),
                      "pruned": pruned.get("deleted")})

    if not record.get("ok") and offsite.configured():
        # Configured and failing is an incident; unconfigured is a gate the owner has not
        # opened yet and is already reported as an owner action.
        from ..core.models import Incident

        with ctx.db.session() as s:
            s.add(Incident(kind="offsite_archive_failed", severity="high",
                           summary=f"off-provider archive failed at {record.get('stage')}",
                           detail={"reason": record.get("reason", "")[:400]}))

    return {"ok": bool(record.get("ok")), "stage": record.get("stage"),
            "reason": record.get("reason", "")[:300], "pruned": pruned}


@handlers.register("creative.image_benchmark")
def handle_image_benchmark(ctx: JobContext) -> dict:
    """Render the same six Brambleloop trials on every credentialled candidate and score
    them blind (owner decision 2026-09-20: measure before locking a provider).

    Runs on a cadence rather than on a button because the button needs a credential nobody
    in a session holds, and because the benchmark is genuinely re-runnable: a provider's key
    arrives weeks after another's, and a candidate already measured under this exact rubric
    is reused rather than re-rendered. What that leaves is only the new work.

    It refuses to start when the month's allocation is spent rather than running on a
    cheaper judge, which is the policy stated as code: quality first, cost second, waste
    never.
    """
    import os

    from ..finance import spend_policy
    from ..gateway import image_bench

    # The approved benchmark budget as a stop, not as a number in a report. It was being
    # applied per run, so four runs each stayed inside a figure the owner approved once and
    # the cumulative total passed it while every individual run looked compliant.
    spent = image_bench.spent_to_date(ctx.db)
    if spent >= image_bench.BENCHMARK_CEILING_CAD:
        from ..core.models import OwnerAction

        with ctx.db.session() as s:
            from sqlalchemy import select

            already = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == "image_benchmark_budget",
                OwnerAction.done == False))  # noqa: E712
            if already is None:
                s.add(OwnerAction(
                    requirement_key="image_benchmark_budget",
                    action=("Decide whether to raise the image-provider benchmark budget "
                            "above CA$%.2f, or to stop the benchmark and choose from what "
                            "has been measured." % image_bench.BENCHMARK_CEILING_CAD),
                    reason=("The benchmark has spent CA$%.2f of an approved CA$%.2f and has "
                            "not finished. The overrun bought no measurement: it went to "
                            "defects in the benchmark itself -- an identity trial that ran "
                            "without its reference image, two providers whose reference "
                            "conditioning was wired wrong, a judge token budget too small "
                            "for the rubric, and a production ceiling variable still set to "
                            "CA$25. All are fixed; the runs that hit them are not "
                            "refundable." % (spent, image_bench.BENCHMARK_CEILING_CAD)),
                    max_cost_cad=10.0, minutes=2,
                    consequence_of_delay=("The image-provider choice stays unmade and the "
                                          "twelve requirements behind it stay parked."),
                    blocks="the canonical model pack and every listing image"))
        ctx.audit("image.benchmark_budget_reached", detail={
            "spent_to_date_cad": spent,
            "approved_cad": image_bench.BENCHMARK_CEILING_CAD})
        return {"ran": False, "reason": "the approved benchmark budget is spent",
                "spent_to_date_cad": spent,
                "approved_cad": image_bench.BENCHMARK_CEILING_CAD,
                "owner_action": "image_benchmark_budget"}

    allowance = spend_policy.may_spend(ctx.db, image_bench.JUDGE_TASK)
    if not allowance["may_spend"]:
        ctx.audit("image.benchmark_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"],
                "constrained": ("the image-provider benchmark stopped at its share of the "
                                "month rather than being judged on a weaker model")}

    result = image_bench.run(ctx.db, env=dict(os.environ))
    decision = result.get("decision") or {}
    ctx.audit("image.benchmark" if result.get("ran") else "image.benchmark_blocked", detail={
        "ran": result.get("ran"),
        "reason": result.get("reason", "")[:300],
        "spent_cad": result.get("spent_cad"),
        "reused": result.get("reused"),
        "unmeasured": result.get("unmeasured"),
        "decided": decision.get("decided"),
        "locked": decision.get("locked"),
        "winner": decision.get("winner"),
        "why": str(decision.get("why") or "")[:400],
    })
    # An incomplete benchmark tries again soon; a complete one waits for the weekly cadence.
    #
    # Learned the hard way within an hour of shipping this: a deploy went out while the first
    # run was working through its second candidate, the container was replaced, and the
    # durable queue re-drove the job -- which worked only because each candidate's scores are
    # stored as it finishes. Had it not been, the weekly cadence would have left a half-
    # measured benchmark sitting for seven days with a winner it must not name.
    #
    # The re-enqueue is conditional on *progress*, not on incompleteness. A candidate that
    # holds a credential and fails every time -- which is exactly the state of the Google
    # project denied access on 2026-09-21 -- would otherwise re-queue this job for ever.
    from ..gateway import images

    # Progress means a *stored* measurement, which means a complete schedule. Computing it
    # from the run's own results instead put this job in a paid loop: a candidate that
    # scored but did not finish its schedule counted as progress, was never stored, so the
    # outstanding set never shrank and the job re-queued itself every few minutes at about
    # CA$1.85 a time. A follow-up condition that cannot become false is a spend with no
    # stopping rule.
    from ..gateway import image_bench

    measured_now = {c.key for c in image_bench.CANDIDATES
                    if c.can_hold_an_identity
                    and image_bench.stored_result(ctx.db, c) is not None}
    credentialled = set(images.available(dict(os.environ)))
    outstanding = credentialled - measured_now
    progressed = bool(measured_now - {r["model"] for r in (result.get("reused") or [])})
    if outstanding and progressed and result.get("ran"):
        ctx.enqueue("creative_director", "creative.image_benchmark",
                    {"because": sorted(outstanding)},
                    idempotency_key=f"image-benchmark-{sorted(outstanding)}")

    return {"ran": result.get("ran"), "spent_cad": result.get("spent_cad"),
            "winner": decision.get("winner"), "locked": decision.get("locked"),
            "outstanding": sorted(outstanding),
            "unmeasured": [u["model"] for u in result.get("unmeasured") or []]}


@handlers.register("creative.model_tournament")
def handle_model_tournament(ctx: JobContext) -> dict:
    """Run the canonical-model tournament and stop before choosing (#199).

    The owner's direction is the design: do not generate one woman and make her canonical
    because she happened to be first. So this generates a field, screens it, stress-tests the
    survivors across materially different scenes, and presents them. There is no branch in
    here that selects, and `visual.tournament` contains no function that could.

    Runs once: `already_run` is keyed on the brief, so a re-deploy does not re-render
    twenty-four faces, and a changed brief does.
    """
    import os
    import tempfile

    from ..finance import spend_policy
    from ..visual import brief, tournament

    if brief.owner_candidate_supplied():
        # The owner saw the field, rejected all five finalists and supplied their own
        # candidate. A tournament now would render twenty more women to answer a question
        # that has been answered -- and it would do it again every time the brief changed,
        # because the brief is what this job is keyed on.
        return {"ran": False,
                "reason": ("the owner supplied a canonical-model candidate on "
                           f"{brief.CANDIDATE_GIVEN_AT} and rejected the finalists. "
                           "The pack is built by creative.model_reference_pack"),
                "rejected_finalists": brief.REJECTED_FINALISTS_NOTE}

    allowance = spend_policy.may_spend(ctx.db, "model_tournament")
    if not allowance["may_spend"]:
        ctx.audit("model.tournament_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"]}

    previous = _tournament_on_file(ctx.db)
    if previous is not None:
        return {"ran": False, "reason": "this brief's tournament has already run",
                "finalists": previous.get("clear_both_floors", []),
                "awaiting": "owner selection"}

    env = dict(os.environ)
    work = ctx.job.inputs.get("work_dir") or tempfile.mkdtemp(prefix="tournament-")
    field = tournament.generate_candidates(
        ctx.db, count=ctx.job.inputs.get("count") or tournament.DEFAULT_CANDIDATES,
        env=env, work_dir=work)
    if not field.get("ran") or not field.get("candidates"):
        # A field of nothing is recorded with its reasons rather than returned quietly. The
        # first live run produced no candidates and the only trace was a job-completed
        # count; why every render or screen failed was not readable from anywhere.
        detail = {**field, "brief_fingerprint": _brief_fingerprint(), "finalists": [],
                  "clear_both_floors": [],
                  "why_empty": ("no candidate survived generation and screening. The "
                                "per-candidate reasons are in `failures`")}
        ctx.audit(tournament.TOURNAMENT_ACTION, detail=detail)
        return {"ran": bool(field.get("ran")), "candidates": 0,
                "failures": field.get("failures", [])[:5]}

    finalists = field["candidates"][:brief.TARGET_FINALISTS]
    results = [tournament.stress_test(ctx.db, f, env=env, work_dir=work) for f in finalists]
    package = tournament.present(ctx.db, results)
    package["field"] = {"generated": field["generated"], "excluded": field["excluded"],
                        "failures": field["failures"][:5], "provider": field["provider"]}
    package["spent_cad"] = round(
        float(field.get("spent_cad") or 0.0)
        + sum(float(r.get("spent_cad") or 0.0) for r in results), 4)
    package["brief_fingerprint"] = _brief_fingerprint()

    ctx.audit(tournament.TOURNAMENT_ACTION, detail=package)

    # The owner asked to be shown the finalists. That is a consequential decision, so it
    # goes in the one owner queue rather than into a log somebody might read.
    from sqlalchemy import select

    from ..core.models import OwnerAction

    with ctx.db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "canonical_model_selection",
            OwnerAction.done == False))  # noqa: E712
        if open_row is None:
            s.add(OwnerAction(
                requirement_key="canonical_model_selection",
                action=("Choose the permanent Brambleloop model from the finalists at "
                        "/api/model-tournament, then confirm the selection."),
                reason=(f"{len(results)} finalists were stress-tested across "
                        f"{len(brief.STRESS_SCENES)} controlled scenes; "
                        f"{len(package['clear_both_floors'])} cleared both hard floors "
                        f"(facial identity and whole-person morphology, independently). "
                        f"Nothing selects itself: a candidate that became canonical by "
                        f"topping a table is an identity nobody chose."),
                max_cost_cad=0.0, minutes=10,
                consequence_of_delay=("Every model-bearing frame stays blocked, because a "
                                      "drift check with no reference pack is unavailable "
                                      "rather than passing."),
                blocks="all model-led listing imagery and the creative parity gate"))

    return {"ran": True, "finalists": len(results),
            "clear_both_floors": package["clear_both_floors"],
            "spent_cad": package["spent_cad"], "selected": None}


@handlers.register("creative.model_reference_pack")
def handle_model_reference_pack(ctx: JobContext) -> dict:
    """Build the reference pack from the owner's candidate and stop before freezing it.

    The owner rejected all five tournament finalists and supplied their own concept. What
    that changes is *which* woman; what it does not change is that she is not canonical
    until she is proven and approved. So this renders the two reference frames and the
    controlled scenes, measures face and whole-person morphology separately, and raises the
    approval as an owner action. There is no branch in here that selects.
    """
    import os
    import tempfile

    from ..finance import spend_policy
    from ..visual import reference_pack

    allowance = spend_policy.may_spend(ctx.db, "model_reference_pack")
    if not allowance["may_spend"]:
        ctx.audit("model.reference_pack_capped", detail=allowance)
        return {"ran": False, "reason": allowance["why"]}

    previous = _pack_on_file(ctx.db)
    if previous is not None:
        return {"ran": False, "reason": "this candidate's pack has already been built",
                "ready_for_owner_approval": previous.get("ready_for_owner_approval"),
                "awaiting": "owner approval"}

    env = dict(os.environ)
    work = ctx.job.inputs.get("work_dir") or tempfile.mkdtemp(prefix="reference-pack-")
    package = reference_pack.build(ctx.db, env=env, work_dir=work)
    package["candidate_fingerprint"] = _candidate_fingerprint()
    ctx.audit(reference_pack.PACK_ACTION, detail=package)

    if not package.get("built"):
        return {"ran": True, "built": False, "stage": package.get("stage"),
                "why": package.get("why")}

    from sqlalchemy import select

    from ..core.models import OwnerAction

    with ctx.db.session() as s:
        open_row = s.scalar(select(OwnerAction).where(
            OwnerAction.requirement_key == "canonical_model_approval",
            OwnerAction.done == False))  # noqa: E712
        if open_row is None:
            floors = (f"face {package['face_floor']}, whole-person morphology "
                      f"{package['morphology_floor']}")
            s.add(OwnerAction(
                requirement_key="canonical_model_approval",
                action=("Approve or reject the canonical Brambleloop model at "
                        "/api/model-pack: the neutral portrait, the full-length body "
                        "reference, the stress set and the measured results."),
                reason=(f"The pack is built from your supplied candidate and measured: "
                        f"{floors}. Approval freezes the identity, versions the reference "
                        f"pack and makes it the conditioning source for every "
                        f"model-bearing frame; nothing is frozen until you say so."),
                max_cost_cad=0.0, minutes=10,
                consequence_of_delay=("Every model-bearing frame stays blocked, because a "
                                      "drift check with no reference pack is unavailable "
                                      "rather than passing."),
                blocks="all model-led listing imagery and the creative parity gate"))

    return {"ran": True, "built": True,
            "face_floor": package["face_floor"],
            "morphology_floor": package["morphology_floor"],
            "required_morphology_ok": package["required_morphology_ok"],
            "ready_for_owner_approval": package["ready_for_owner_approval"],
            "spent_cad": package["spent_cad"], "frozen": False}


def _candidate_fingerprint() -> str:
    """Identity of the run: the brief, the pack method, and the candidate's own bytes.

    The candidate image is part of it because a different concept is a different woman, and
    an audit row from the previous candidate is exactly the row that would read as "already
    built" for the next one.
    """
    import hashlib
    import json
    from pathlib import Path

    from ..visual import brief, reference_pack

    concept = Path(brief.candidate_reference())
    digest = (hashlib.sha256(concept.read_bytes()).hexdigest()[:16]
              if concept.is_file() else "absent")
    material = json.dumps({"brief": brief.state(), "pack": reference_pack.PACK_VERSION,
                           "candidate": digest}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def pack_boot_key(now) -> str:
    """The idempotency key a deploy uses to enqueue the reference-pack build."""
    return f"boot-pack-{_candidate_fingerprint()}-{now:%Y%m%d%H}"


def _pack_attempts(db, limit: int = 5) -> list[dict]:
    """The recent pack builds, successful or not.

    Reported because the endpoint that showed only successes could not tell "never ran"
    from "ran and could not finish" -- which is the same defect the tournament endpoint had
    and the same one `_pack_on_file`'s own comment warns about, one layer up.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import reference_pack

    out: list[dict] = []
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == reference_pack.PACK_ACTION)
                             .order_by(desc(AuditLog.id)).limit(limit)):
            detail = row.detail or {}
            out.append({"at": str(row.created_at), "built": detail.get("built"),
                        "stage": detail.get("stage"), "why": detail.get("why"),
                        "pack_version": detail.get("pack_version"),
                        "candidate_fingerprint": detail.get("candidate_fingerprint"),
                        "spent_cad": detail.get("spent_cad")})
    return out


def _pack_on_file(db) -> dict | None:
    """A completed pack for the candidate as it now stands, if there is one."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import reference_pack

    want = _candidate_fingerprint()
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == reference_pack.PACK_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            # A build that ran and failed is a different fact from one that never ran, and
            # both are different from one that succeeded -- but only a successful build is
            # a reason not to try again.
            if detail.get("candidate_fingerprint") == want and detail.get("built"):
                return detail
    return None


def _brief_fingerprint() -> str:
    import hashlib
    import json

    from ..visual import brief, tournament

    material = json.dumps({"brief": brief.state(), "seeds": list(tournament.SEED_NOTES),
                           "presentation": tournament.PRESENTATION_VERSION},
                          sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def tournament_boot_key(now) -> str:
    """The idempotency key a deploy uses to enqueue the canonical-model tournament.

    It carries the brief fingerprint because that is what the work is keyed on. A key made
    only of the hour guards the clock instead, and the difference showed up the first time a
    corrected brief was deployed twice in one hour: the second deploy found the hour's key
    already spent, enqueued nothing, and the endpoint went on reporting that the corrected
    tournament had not run.

    The hour stays in the key so a run that fails is retried next hour rather than locked out
    for the life of the brief.
    """
    return f"boot-tourney-{_brief_fingerprint()}-{now:%Y%m%d%H}"


def _tournament_on_file(db) -> dict | None:
    """A completed tournament for the brief as it now stands, if there is one."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..visual import tournament

    want = _brief_fingerprint()
    with db.session() as s:
        for row in s.scalars(select(AuditLog)
                             .where(AuditLog.action == tournament.TOURNAMENT_ACTION)
                             .order_by(desc(AuditLog.id)).limit(20)):
            detail = row.detail or {}
            # Not `and detail.get("finalists")`. A tournament that ran and produced nothing
            # is a different fact from one that never ran, and reading an empty finalist
            # list as "not yet run" hid exactly that: the job completed, the audit row was
            # written, and the endpoint reported it had not happened -- so the reason it
            # produced nothing was unreachable from outside the database.
            if detail.get("brief_fingerprint") == want:
                return detail
    return None
