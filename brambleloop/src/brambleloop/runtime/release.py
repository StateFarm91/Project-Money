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
from ..commerce import launch as launch_mod
from ..commerce import pricing as pricing_mod
from ..commerce import seo as seo_mod
from ..core.artifacts import ArtifactStore
from ..core.models import PatternVersion, Product
from ..gates.policy import ListingDraft, check_listing
from ..publish.charts import ChartSpec, render_chart, render_legend
from ..publish.pdf import build_pattern_pdf
from ..radar.market import shopping_window
from ..radar.opportunity import POOL, _event
from .worker import JobContext, handlers

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
    render_chart(cir, twin, ChartSpec(cell_px=26)).save(chart_png, format="PNG")
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

    payload = {"slug": slug, "version": version, "pages": doc.pages,
               "size_label": doc.size_label(),
               "finished_size_cm": list(doc.finished_size_cm) if doc.finished_size_cm else None,
               "yardage": doc.yardage_by_color, "tolerance": doc.yardage_tolerance,
               "calibrated": doc.calibrated,
               "pdf_sha256": pdf.sha256, "chart_sha256": chart.sha256,
               "legend_sha256": legend.sha256}
    ctx.enqueue("pricing", "pricing.position", payload,
                idempotency_key=f"price:{slug}:{version}")
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
    ctx.enqueue("listing", "listing.seo", i, idempotency_key=f"seo:{slug}:{i['version']}")
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

    copy = seo_mod.ListingCopy(
        title=seo_mod.build_title(cir.title, category, motifs, season,
                                  sizes=len(i.get("sizes") or []) or 1),
        tags=seo_mod.build_tags(category, motifs, season),
        description=seo_mod.build_description(
            cir.title, size_label=size_label, yardage_lines=yardage_lines,
            tolerance_pct=tolerance_pct, difficulty=_difficulty(twin, cir),
            colors=sorted(c for c in twin.colors_used if c), terminology="US",
            gauge_line=gauge_line, stitches=sorted(twin.stitch_types_used),
            season=season, pages=i.get("pages")),
        materials=[m.name for m in cir.materials],
        price_cad=float(i.get("price_cad", 0.0)),
        supported_claims=[c for c in (size_label, gauge_line) if c],
    )

    structural = seo_mod.check_listing_limits(copy)
    policy = check_listing(ListingDraft(title=copy.title, description=copy.description,
                                        tags=copy.tags, price_cad=copy.price_cad))
    blocking = structural + [str(f) for f in policy if f.severity == "error"]

    ctx.audit("listing.seo_drafted" if not blocking else "listing.seo_blocked",
              artifact=f"{slug}@{version}",
              detail={"title_len": len(copy.title), "tags": len(copy.tags),
                      "blocking": blocking[:5]})
    if blocking:
        return {"slug": slug, "version": version, "ok": False, "blocking": blocking}

    i.update({"listing": copy.to_dict()})
    ctx.enqueue("growth", "launch.plan", i, idempotency_key=f"launch:{slug}:{version}")
    return {"slug": slug, "version": version, "ok": True, "listing": copy.to_dict()}


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
    ctx.enqueue("store_operator", "store.publish",
                {"slug": slug, "version": i["version"]},
                idempotency_key=f"publish:{slug}:{i['version']}")
    return plan.to_dict()


@handlers.register("support.reply")
def handle_support_reply(ctx: JobContext) -> dict:
    """Answer a customer from the exact released version they bought.

    The version is an input, not a lookup of "the current one". A customer who bought 1.0.0
    must be answered from 1.0.0; answering from 1.1.0 because it happens to be newer is how a
    support system tells someone their correct work is wrong.
    """
    from ..support.concierge import Concierge

    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs["version"]
    question = ctx.job.inputs["question"]
    cir = _load_cir(ctx, slug, version)

    answer = Concierge(cir).answer(question)
    ctx.audit("support.replied", artifact=f"{slug}@{version}",
              detail={"escalated": answer.escalated, "confident": answer.confident})
    return answer.to_dict()


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
