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

from datetime import date

from ..cir.compiler import compile_cir
from ..cir.model import CIR
from ..cir.twin import build_twin
from ..cir.writer import collapses_rows
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
CHAIN_VERSION = "5"


def chain_key(stage: str, slug: str, version: str) -> str:
    return f"{stage}:{slug}:{version}:c{CHAIN_VERSION}"


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
    twin = build_twin(cir, result)

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
    blocking = (structural + [str(f) for f in truth if f.severity == "error"]
                + hero.problems)

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
                      "hero_thumbnail": hero.to_dict()})
    if blocking:
        # A listing whose imagery misrepresents the pattern does not proceed to pricing. The
        # chain stops here rather than producing a price for something that cannot ship.
        return {"slug": slug, "version": version, "ok": False,
                "blocking_image_problems": blocking}

    payload = {"slug": slug, "version": version, "pages": doc.pages,
               "size_label": doc.size_label(),
               "finished_size_cm": list(doc.finished_size_cm) if doc.finished_size_cm else None,
               "yardage": doc.yardage_by_color, "tolerance": doc.yardage_tolerance,
               "calibrated": doc.calibrated,
               "pdf_sha256": pdf.sha256, "chart_sha256": chart.sha256,
               "legend_sha256": legend.sha256,
               "frames": stored_frames}
    ctx.enqueue("pricing", "pricing.position", payload,
                idempotency_key=chain_key("price", slug, version))
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
    ctx.enqueue("listing", "listing.seo", i, idempotency_key=chain_key("seo", slug, i["version"]))
    return decision.to_dict()


@handlers.register("listing.seo")
def handle_listing_seo(ctx: JobContext) -> dict:
    """Assemble the listing from computed facts, then let the Policy Gate try to break it."""
    i = dict(ctx.job.inputs)
    slug, version = i["slug"], i["version"]
    cir = _load_cir(ctx, slug, version)
    result = compile_cir(cir)
    twin = build_twin(cir, result)
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
    blocking = structural + [str(f) for f in policy if f.severity == "error"]

    ctx.audit("listing.seo_drafted" if not blocking else "listing.seo_blocked",
              artifact=f"{slug}@{version}",
              detail={"title_len": len(copy.title), "tags": len(copy.tags),
                      "search_share": coverage.share, "gaps": coverage.gaps[:5],
                      "blocking": blocking[:5]})
    if blocking:
        return {"slug": slug, "version": version, "ok": False, "blocking": blocking}

    i.update({"listing": copy.to_dict(), "attributes": attributes,
              "search_coverage": coverage.to_dict()})
    _persist_listing(ctx, slug, version, copy, coverage.share)
    ctx.enqueue("growth", "launch.plan", i, idempotency_key=chain_key("launch", slug, version))
    return {"slug": slug, "version": version, "ok": True, "listing": copy.to_dict(),
            "attributes": attributes, "search_coverage": coverage.to_dict()}


def _persist_listing(ctx: JobContext, slug: str, version: str, copy, share: float) -> None:
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
                idempotency_key=chain_key("content", slug, i["version"]))
    ctx.enqueue("store_operator", "store.publish",
                {"slug": slug, "version": i["version"]},
                idempotency_key=chain_key("publish", slug, i["version"]))
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
    twin = build_twin(cir, compile_cir(cir))
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

    queued: list[str] = []
    with ctx.db.session() as s:
        existing = {a.action for a in s.scalars(
            select(OwnerAction).where(OwnerAction.done == False))}  # noqa: E712
        for request in readiness.owner_requests():
            if request.action in existing:
                continue
            s.add(OwnerAction(action=request.action, reason=request.reason,
                              max_cost_cad=request.max_cost_cad, minutes=request.minutes,
                              consequence_of_delay=request.consequence_of_delay,
                              blocks=request.blocks))
            queued.append(request.action[:60])

    ctx.audit("launch.assessed", detail={
        "ready": readiness.ready,
        "ours_to_do": [r.key for r in readiness.buildable],
        "blocked_on_owner": [r.key for r in readiness.blocked_on("owner")],
        "blocked_on_integration": [r.key for r in readiness.blocked_on("integration")],
        "owner_actions_added": len(queued)})

    return {"ready": readiness.ready, "owner_actions_added": len(queued),
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

    with ctx.db.session() as s:
        products = {p.id: p.slug for p in s.scalars(select(Product))}
        certified = [pv for pv in s.scalars(
            select(PatternVersion).where(PatternVersion.certified == True))]  # noqa: E712
        # Current, not merely present. An earlier version of this looked only for *missing*
        # listings and so left every stale one exactly as it was: the fix reached nothing, and
        # a stuttering title stayed on every shipped product through two deploys.
        current = {(l.product_slug, l.version) for l in s.scalars(select(Listing))
                   if l.chain_version == CHAIN_VERSION}

    started: list[str] = []
    for pv in certified:
        slug = products.get(pv.product_id)
        if not slug or (slug, pv.version) in current:
            continue
        job = ctx.enqueue("listing", "listing.draft",
                          {"slug": slug, "version": pv.version},
                          idempotency_key=chain_key("listing", slug, pv.version))
        if job is not None:
            started.append(f"{slug}@{pv.version}")

    # Collections are listed under the pseudo-version "collection" rather than a
    # PatternVersion, so they need their own line here or a rebuild leaves the bundle behind.
    collections_started: list[str] = []
    for seed in POOL:
        if not seed.is_bundle or (seed.slug, "collection") in current:
            continue
        job = ctx.enqueue("listing", "collection.assemble",
                          {"slug": seed.slug, "family": seed.family},
                          idempotency_key=chain_key("collection", seed.slug, "collection"))
        if job is not None:
            collections_started.append(seed.slug)

    ctx.audit("chain.rebuilt", detail={"chain_version": CHAIN_VERSION,
                                       "certified": len(certified),
                                       "restarted": started[:20],
                                       "restarted_count": len(started),
                                       "collections_restarted": collections_started})
    return {"chain_version": CHAIN_VERSION, "certified": len(certified),
            "restarted": started, "collections_restarted": collections_started}
