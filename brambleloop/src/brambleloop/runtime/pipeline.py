"""Shadow-mode release pipeline (Master Plan section 36, acceptance Gate F).

Wires the release chain into real queued jobs so one product can travel from a market brief to
a release certificate with no human intervention:

    radar.scan -> radar.score -> cir.draft -> cir.compile -> gate.asset_truth
        -> gate.policy -> gate.certify -> listing.draft -> (store.publish blocked in shadow)

In SHADOW the store operator refuses to publish, by design: section 26 forbids connecting a
newly built autonomous system to live listings on day one. The refusal is the feature.

Pattern authoring here is deliberately deterministic template code, not a model call. A model
proposes *concepts*; the CIR that gets compiled is constructed by code whose output is
reproducible. That is what section 2 means by "never ask an LLM to guess instructions".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func

from ..cir.compiler import compile_cir
from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..core.models import Phase, Product, PatternVersion
from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance
from ..gates.certificate import DOC_VERSION, certify
from ..gates.incidents import IncidentTracker
from ..gates.policy import ListingDraft
from ..radar.opportunity import POOL, ConceptSeed, score_concept, select_portfolio
from .worker import CapabilityNotEnabled, JobContext, handlers

PROMOTION_THRESHOLD = 0.55
"""Below this a concept is not worth engineering time. Set from the pool: roughly the top
third clears it, which is the intake rate the release chain can actually absorb."""


class ShadowModeRefusal(CapabilityNotEnabled):
    """A production-only action attempted before its gate has passed.

    Subclasses CapabilityNotEnabled so the worker treats it as terminal rather than retrying
    against a mode that will not change between attempts.
    """


# ---- concept -> CIR ------------------------------------------------------


@dataclass
class Concept:
    slug: str
    title: str
    category: str
    stitch_repeat: list[tuple[str, int]]   # e.g. [("sc", 3), ("dc", 1)]
    width_stitches: int
    rows: int
    colors: dict[str, str]
    opportunity_score: float = 0.0
    season: str | None = None
    risk_class: str = "A"


def concept_to_cir(c: Concept, version: str = "1.0.0") -> CIR:
    """Build a machine-verifiable CIR from a concept.

    Only produces geometry the compiler can check: a flat two-colour panel worked over a
    foundation that the repeat divides evenly. If the repeat does not divide the width, this
    returns a CIR that will *fail* compilation rather than quietly fudging the numbers.
    """
    unit = sum(n for _, n in c.stitch_repeat)
    palette = list(c.colors)
    rows: list[Row] = []
    for i in range(1, c.rows + 1):
        color = palette[(i - 1) % len(palette)] if palette else None
        if i == 1:
            ops = [Op("sc", c.width_stitches)]
        elif i % 2 == 0:
            ops = [Repeat([Op(code, n) for code, n in c.stitch_repeat], times=None)]
        else:
            ops = [Op("sc", c.width_stitches)]
        rows.append(Row(index=i, ops=ops, declared_count=c.width_stitches,
                        turning_chain=1, color=color))

    return CIR(
        slug=c.slug,
        title=c.title,
        version=version,
        construction="flat_rows",
        risk_class=c.risk_class,
        colors=dict(c.colors),
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=14, stitch_type="sc", hook_mm=5.0),
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", color_id=p)
                   for p in palette],
        components=[Component(name="panel", construction="flat_rows", rows=rows,
                              foundation=c.width_stitches, foundation_kind="chain")],
        designer_notes=f"{c.category} concept, unit repeat {unit} sts",
    )


# Per-category geometry. Deliberately a lookup table rather than a model call: the stitch
# structure of a product is an engineering decision that must be reproducible, and section 2
# forbids asking a model to supply instructions. Every entry is a repeat whose unit divides
# the stated width, so the compiler's divisibility check passes for a reason rather than by
# luck.
_GEOMETRY: dict[str, dict] = {
    "mosaic_blanket": {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 160, "rows": 24},
    "blanket":        {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 160, "rows": 24},
    "graphghan":      {"stitch_repeat": [["sc", 4]],            "width": 140, "rows": 24},
    "baby":           {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 100, "rows": 20},
    "seasonal_decor": {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 40,  "rows": 12},
    "runner":         {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 60,  "rows": 16},
    "placemat":       {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 48,  "rows": 14},
    "coaster":        {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 24,  "rows": 8},
    "basket":         {"stitch_repeat": [["sc", 4]],            "width": 48,  "rows": 14},
    "pillow":         {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 72,  "rows": 20},
    "wall_decor":     {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 44,  "rows": 16},
    "flower":         {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 24,  "rows": 8},
    "pet":            {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 60,  "rows": 18},
    "scarf":          {"stitch_repeat": [["dc", 2], ["sc", 2]], "width": 40,  "rows": 20},
    "ornament":       {"stitch_repeat": [["sc", 2], ["dc", 2]], "width": 24,  "rows": 8},
}
_DEFAULT_GEOMETRY = {"stitch_repeat": [["sc", 3], ["dc", 1]], "width": 40, "rows": 12}

_PALETTES: dict[str, dict[str, str]] = {
    "nordic-forest": {"forest": "#244A3A", "cream": "#FAF6EB"},
    "autumn-oak": {"wine": "#6E1F2A", "gold": "#C49545"},
    "cloudline": {"cream": "#FAF6EB", "ink": "#1A2B3C"},
}
_DEFAULT_PALETTE = {"forest": "#244A3A", "cream": "#FAF6EB"}


def concept_geometry(seed: ConceptSeed) -> dict:
    """Turn a market concept into the numbers the CIR builder needs."""
    g = _GEOMETRY.get(seed.category, _DEFAULT_GEOMETRY)
    unit = sum(n for _, n in g["stitch_repeat"])
    width = g["width"]
    if width % unit:
        # Round up to a multiple of the repeat rather than emitting a CIR we know will fail.
        width += unit - (width % unit)
    return {
        "stitch_repeat": [list(x) for x in g["stitch_repeat"]],
        "width_stitches": width,
        "rows": g["rows"],
        "colors": dict(_PALETTES.get(seed.family or "", _DEFAULT_PALETTE)),
    }


def _seed_for(slug: str) -> ConceptSeed | None:
    return next((s for s in POOL if s.slug == slug), None)


# ---- job handlers --------------------------------------------------------


@handlers.register("radar.scan")
def handle_radar_scan(ctx: JobContext) -> dict:
    """Score the real opportunity pool and emit the release candidates.

    Section 33: the pool is at least 30 concepts across several categories, scored before any
    SKU is committed. `select_portfolio` applies the structural constraints -- flagship
    seasonal, several fast low-price makes, a bundle-ready family, an evergreen search
    product, Class C capped -- so a run cannot quietly become ten Christmas blankets.
    """
    today = _scan_date(ctx)
    target = int(ctx.job.inputs.get("target", 10))
    portfolio = select_portfolio(target=target, today=today)

    ctx.audit("radar.scanned", detail={
        "pool": len(portfolio.selected) + len(portfolio.rejected),
        "selected": len(portfolio.selected),
        "constraints_met": portfolio.constraints_met,
        "as_of": today.isoformat(),
    })
    if not portfolio.ok:
        # Never silently ship a portfolio that violates section 33; say which rule broke.
        unmet = [k for k, v in portfolio.constraints_met.items() if not v]
        ctx.audit("radar.portfolio_constraints_unmet", detail={"unmet": unmet,
                                                              "reasons": portfolio.reasons})

    for c in portfolio.selected:
        ctx.enqueue("market_radar", "radar.score", c.to_dict(),
                    idempotency_key=f"score:{c.slug}:{today.isoformat()}")

    return {
        "pool_size": len(portfolio.selected) + len(portfolio.rejected),
        "selected": [c.slug for c in portfolio.selected],
        "constraints_met": portfolio.constraints_met,
        "swaps": portfolio.reasons,
        "as_of": today.isoformat(),
    }


def _scan_date(ctx: JobContext) -> date:
    raw = ctx.job.inputs.get("as_of")
    return date.fromisoformat(raw) if raw else date.today()


@handlers.register("radar.score")
def handle_radar_score(ctx: JobContext) -> dict:
    """Re-score the candidate on its own and promote it only if it still clears the bar.

    Scoring happens twice on purpose. `radar.scan` scores to *rank* a pool; this re-scores a
    single candidate at the moment it is about to consume engineering effort, because a job
    can sit in the queue for days and a seasonal window can close underneath it.
    """
    c = dict(ctx.job.inputs)
    seed = _seed_for(c["slug"])
    if seed is None:
        ctx.audit("radar.unknown_concept", artifact=c.get("slug"))
        return {"slug": c.get("slug"), "promoted": False, "reason": "not in the pool"}

    today = _scan_date(ctx)
    rescored = score_concept(seed, today)
    promote = rescored.score >= PROMOTION_THRESHOLD and seed.risk_class in ("A", "B")

    ctx.audit("radar.scored", artifact=seed.slug, detail={
        "score": rescored.score, "components": rescored.components,
        "promoted": promote,
    })
    if promote:
        payload = rescored.to_dict()
        payload.update(concept_geometry(seed))
        ctx.enqueue("crochet_engineer", "cir.draft", payload,
                    idempotency_key=f"draft:{seed.slug}")
    return {"slug": seed.slug, "score": rescored.score, "promoted": promote,
            "components": rescored.components,
            "reason": None if promote else (
                "Class C requires physical testing that does not exist yet"
                if seed.risk_class == "C" else
                f"score {rescored.score} below promotion threshold {PROMOTION_THRESHOLD}")}


# Concepts whose pattern is engineered rather than templated. The generic builder below makes
# a striped panel, which proves the machinery and is not a product; where a real design exists
# it wins. A slug absent from here is not a failure -- it means that concept has not been
# through design yet, and the templated geometry stands in until it has.
# Concepts whose pattern is engineered rather than templated. The generic builder below makes
# a striped panel, which proves the machinery and is not a product. A slug absent from here is
# not a failure -- it means that concept has not been through design yet, and the templated
# geometry stands in until it has.
#
# `nordic_forest` stays a module of its own because it is the flagship and its motif was
# hand-placed; everything else is generated from the motif library by `products.builder`,
# which is how twelve exceptional products are achievable without twelve chances to slip.
# "module" or "module:function", so one module can hold several engineered designs.
ENGINEERED: dict[str, str] = {
    "nordic-forest-mosaic-throw": "brambleloop.products.nordic_forest",
    # Both of these were flat rectangles named for shapes they did not make: the basket was a
    # side panel with no seaming instructions, the "hexagon" coaster had the same stitch
    # count on every row. They are worked in the round now (B-059).
    "market-basket-trio": "brambleloop.products.vessels:build",
    "hexie-coaster-set": "brambleloop.products.vessels:build_hexagon_coaster",
}


def _engineered_cir(slug: str, version: str = "1.0.0") -> CIR | None:
    module_path = ENGINEERED.get(slug)
    if module_path:
        import importlib

        name, _, function = module_path.partition(":")
        module = importlib.import_module(name)
        cir = getattr(module, function or "build")(version=version)
        # Keep the concept's slug so the radar, the portfolio and the product row agree on the
        # name; the size-specific slugs are for the variants, not the headline product.
        return CIR.from_dict({**cir.to_dict(), "slug": slug})

    from ..products.builder import for_slug

    return for_slug(slug, version)


@handlers.register("cir.draft")
def handle_cir_draft(ctx: JobContext) -> dict:
    slug = ctx.job.inputs["slug"]

    # A bundle is not a pattern. Drafting one produced a certified "Nordic Forest Collection
    # Bundle" whose PDF was a twelve-row striped panel -- a product that would have been sold
    # as three patterns and delivered as one invented swatch. Bundles route to collection
    # assembly instead, which builds the listing out of its members' real releases.
    seed = _seed_for(slug)
    if seed is not None and seed.is_bundle:
        ctx.audit("cir.skipped_bundle", artifact=slug,
                  detail={"reason": "a bundle has no pattern of its own; it is its members"})
        from .release import chain_key

        ctx.enqueue("listing", "collection.assemble",
                    {"slug": slug, "family": seed.family},
                    idempotency_key=chain_key("collection", slug, "collection"))
        return {"artifact": slug, "drafted": False, "is_bundle": True}

    engineered = _engineered_cir(slug)
    if engineered is not None:
        ctx.audit("cir.drafted", artifact=f"{engineered.slug}@{engineered.version}",
                  detail={"source": "engineered design", "rows": sum(
                      len(c.rows) for c in engineered.components)})
        ctx.enqueue("validator", "cir.compile", {"cir": engineered.to_dict()},
                    idempotency_key=f"compile:{engineered.slug}:{engineered.version}")
        return {"artifact": f"{engineered.slug}@{engineered.version}",
                "rows": len(engineered.components[0].rows), "engineered": True}

    i = ctx.job.inputs
    concept = Concept(
        slug=i["slug"], title=i["title"], category=i["category"],
        stitch_repeat=[(s, n) for s, n in i["stitch_repeat"]],
        width_stitches=i["width_stitches"], rows=i["rows"], colors=i["colors"],
        opportunity_score=i.get("score", i.get("opportunity_score", 0.0)),
        season=i.get("season"), risk_class=i.get("risk_class", "A"),
    )
    cir = concept_to_cir(concept)
    ctx.audit("cir.drafted", artifact=f"{cir.slug}@{cir.version}")
    ctx.enqueue("validator", "cir.compile", {"cir": cir.to_dict()},
                idempotency_key=f"compile:{cir.slug}:{cir.version}")
    return {"artifact": f"{cir.slug}@{cir.version}", "rows": len(cir.components[0].rows)}


@handlers.register("cir.compile")
def handle_cir_compile(ctx: JobContext) -> dict:
    cir = CIR.from_dict(ctx.job.inputs["cir"])
    result = compile_cir(cir)
    ctx.audit("cir.compiled", artifact=f"{cir.slug}@{cir.version}",
              detail={"ok": result.ok, "errors": len(result.errors)})
    if not result.ok:
        # A failing compile is a real outcome, not an exception: the concept dies here.
        return {"artifact": f"{cir.slug}@{cir.version}", "compiled": False,
                "errors": [str(f) for f in result.errors]}
    ctx.enqueue("quality_director", "gate.certify", {"cir": ctx.job.inputs["cir"]},
                idempotency_key=f"certify:{cir.slug}:{cir.version}:d{DOC_VERSION}")
    return {"artifact": f"{cir.slug}@{cir.version}", "compiled": True,
            "counts": result.counts(cir.components[0].name)}


@handlers.register("gate.certify")
def handle_certify(ctx: JobContext) -> dict:
    cir = CIR.from_dict(ctx.job.inputs["cir"])

    # Publication is halted while a P0/P1 defect is open against this product.
    tracker = IncidentTracker(ctx.db)
    if tracker.publication_halted(cir.slug):
        ctx.audit("gate.halted", artifact=f"{cir.slug}@{cir.version}",
                  detail={"reason": "open P0/P1 incident"})
        return {"artifact": f"{cir.slug}@{cir.version}", "granted": False,
                "halted_by_incident": True}

    hero = Asset(
        asset_id=f"{cir.slug}-hero",
        asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="asset_truth", tool="digital_twin@1"),
        depicts_stitches=sorted({op.stitch for c in cir.components for r in c.rows
                                 for op in _flatten_stitches(r.ops)}),
        depicts_colors=sorted(cir.colors),
        is_hero=True,
        claims=Claims(materials=[m.name for m in cir.materials]),
    )
    listing = ListingDraft(
        title=f"{cir.title} | Crochet Pattern PDF with Charts",
        description=(f"{cir.title}. Written pattern with stitch counts for every row, "
                     f"US and UK terminology. Drafted and checked with AI assistance and "
                     f"validated by an automated pattern compiler before release."),
        tags=["crochet pattern", "mosaic blanket", "pdf pattern"],
        price_cad=11.99,
    )

    cert = certify(cir, assets=[hero], listing=listing)
    ctx.audit("gate.certified" if cert.granted else "gate.blocked",
              artifact=f"{cir.slug}@{cir.version}",
              policy_version=cert.policy_version,
              detail={"granted": cert.granted, "reasons": cert.blocking_reasons[:5]})

    if cert.granted:
        _persist_release(ctx, cir, cert.to_dict(), cert.release_hash)
        from .release import chain_key

        ctx.enqueue("listing", "listing.draft",
                    {"slug": cir.slug, "version": cir.version},
                    idempotency_key=chain_key("listing", cir.slug, cir.version))
    else:
        _withdraw_listing(ctx, cir)

    return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
            "release_hash": cert.release_hash,
            "reasons": cert.blocking_reasons[:5]}


def _withdraw_listing(ctx: JobContext, cir: CIR) -> None:
    """A product that no longer certifies must not keep a listing marked ready to publish.

    Refusing the certificate and leaving the storefront untouched means the store still holds
    a draft for something the release chain has just rejected -- and the only thing standing
    between that draft and a customer is shadow mode, which is a phase, not a guarantee.
    """
    from sqlalchemy import select

    from ..core.models import Listing

    with ctx.db.session() as s:
        listings = list(s.scalars(
            select(Listing).where(Listing.product_slug == cir.slug,
                                  Listing.state != "withdrawn")))
        for listing in listings:
            listing.state = "withdrawn"
    if listings:
        ctx.audit("listing.withdrawn", artifact=f"{cir.slug}@{cir.version}",
                  detail={"listings": len(listings),
                          "reason": "certification refused for this product"})


def _flatten_stitches(ops) -> list:
    out = []
    for o in ops:
        if isinstance(o, Repeat):
            out.extend(_flatten_stitches(o.ops))
        else:
            out.append(o)
    return out


def _persist_release(ctx: JobContext, cir: CIR, certificate: dict, release_hash: str) -> None:
    from sqlalchemy import select

    with ctx.db.session() as s:
        product = s.scalar(select(Product).where(Product.slug == cir.slug))
        if product is None:
            product = Product(slug=cir.slug, title=cir.title, status="certified",
                              risk_class=cir.risk_class)
            s.add(product)
            s.flush()
        else:
            product.status = "certified"
        existing = s.scalar(
            select(PatternVersion).where(PatternVersion.product_id == product.id,
                                         PatternVersion.version == cir.version)
        )
        if existing is None:
            s.add(PatternVersion(product_id=product.id, version=cir.version,
                                 cir_json=cir.to_dict(), release_hash=release_hash,
                                 certified=True, certificate=certificate))
        elif existing.release_hash != release_hash:
            # Re-certification of a version that already exists. Insert-if-absent was how the
            # agent-permission fix failed to reach production (B-027), and it would fail the
            # same way here: the stored certificate would keep describing a document the
            # writer no longer produces, while the PDF regenerates from the new one. The
            # record is replaced and the change is audited rather than left to be discovered.
            previous = existing.release_hash
            existing.cir_json = cir.to_dict()
            existing.release_hash = release_hash
            existing.certificate = certificate
            existing.certified = True
            ctx.audit("gate.recertified", artifact=f"{cir.slug}@{cir.version}",
                      detail={"previous_release_hash": previous,
                              "release_hash": release_hash,
                              "doc_version": DOC_VERSION})


@handlers.register("listing.draft")
def handle_listing_draft(ctx: JobContext) -> dict:
    """Hand a certified pattern to the second half of the chain.

    Asset rendering comes before listing copy, not after, because the listing quotes the
    assets: page count, finished size, yardage range. Writing the copy first and rendering
    afterwards is how a description ends up promising a PDF that does not exist.
    """
    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs["version"]
    ctx.audit("listing.drafted", artifact=slug)
    from .release import chain_key

    ctx.enqueue("publishing", "assets.build", {"slug": slug, "version": version},
                idempotency_key=chain_key("assets", slug, version))
    return {"artifact": slug, "drafted": True}


@handlers.register("store.publish")
def handle_store_publish(ctx: JobContext) -> dict:
    """In SHADOW this must refuse. Publishing is a production capability with its own gate."""
    if ctx.phase is Phase.SHADOW:
        ctx.audit("store.publish_refused", artifact=ctx.job.inputs.get("slug"),
                  detail={"reason": "shadow mode: no live publication"})
        raise ShadowModeRefusal(
            "store.publish is a production capability; the system is in SHADOW mode and has "
            "no live Etsy connection. Draft retained for review."
        )
    raise ShadowModeRefusal("live publishing is not yet enabled; no Etsy integration exists")


@handlers.register("ops.heartbeat")
def handle_heartbeat(ctx: JobContext) -> dict:
    q = ctx.queue.counts()
    dead = len(ctx.queue.dead_letters())
    ctx.audit("ops.heartbeat", detail={"queue": q, "dead_letters": dead})
    return {"queue": q, "dead_letters": dead}


@handlers.register("ops.queue_check")
def handle_queue_check(ctx: JobContext) -> dict:
    dead = ctx.queue.dead_letters()
    if dead:
        ctx.audit("ops.dead_letters_present", detail={"ids": [d.id for d in dead][:20]})
    return {"dead_letters": len(dead)}


@handlers.register("plan.cycle")
def handle_plan_cycle(ctx: JobContext) -> dict:
    """One planning cycle: re-run the radar over the whole pool and re-select the portfolio.

    Re-running rather than freezing matters. The pool does not change often, but the date
    does, and a concept that was three weeks early last month is in its window this month.
    """
    today = _scan_date(ctx)
    ctx.enqueue("market_radar", "radar.scan",
                {"target": 10, "as_of": today.isoformat()},
                idempotency_key=f"radar.scan:{today.isoformat()}")
    return {"planned": True, "as_of": today.isoformat()}


@handlers.register("portfolio.review")
def handle_portfolio_review(ctx: JobContext) -> dict:
    """Classify every SKU and say what to do next (section 12).

    Two questions, answered separately. Which products *should* exist, which is the radar's
    portfolio re-run against today's calendar; and how the products that *do* exist are
    actually performing, which is section 12's classification.

    The second question currently has no evidence behind it, and the classifier says so rather
    than guessing. Every SKU has zero impressions, and a system that read that as
    "underperforming" would retire a catalogue nobody has been shown.
    """
    from sqlalchemy import select

    from ..core.models import Incident, PortfolioReview, SupportCase
    from ..growth.portfolio import SkuMetrics, review_portfolio

    today = _scan_date(ctx)
    portfolio = select_portfolio(today=today)
    should_exist = {c.slug for c in portfolio.selected}

    with ctx.db.session() as s:
        products = list(s.scalars(select(Product)))
        built = {p.slug for p in products}
        cases: dict[str, int] = {}
        for case in s.scalars(select(SupportCase)):
            if case.product_slug:
                cases[case.product_slug] = cases.get(case.product_slug, 0) + 1
        p1: dict[str, int] = {}
        for inc in s.scalars(select(Incident).where(Incident.resolved == False)):  # noqa: E712
            if inc.product_slug and inc.severity in ("P0", "P1"):
                p1[inc.product_slug] = p1.get(inc.product_slug, 0) + 1

    # Impressions, clicks and orders are all zero and stay zero until something is published.
    # They are read from the ledger rather than assumed, so that the day they are non-zero
    # this code needs no change.
    metrics = [SkuMetrics(slug=p.slug, support_cases=cases.get(p.slug, 0),
                          open_p1_incidents=p1.get(p.slug, 0))
               for p in products]
    verdict = review_portfolio(metrics, today=today)

    missing = sorted(should_exist - built)
    off_portfolio = sorted(built - should_exist)

    with ctx.db.session() as s:
        s.add(PortfolioReview(as_of=today.isoformat(),
                              classifications=verdict.summary(),
                              actions=list(verdict.actions),
                              evidence_available=verdict.evidence_available))

    ctx.audit("portfolio.reviewed", detail={
        "as_of": today.isoformat(),
        "in_portfolio": len(should_exist),
        "built": len(built),
        "missing": missing[:20],
        "off_portfolio": off_portfolio[:20],
        "constraints_met": portfolio.constraints_met,
        "classifications": verdict.summary(),
        "evidence_available": verdict.evidence_available,
    })
    for slug in missing:
        ctx.enqueue("market_radar", "radar.score",
                    next(c.to_dict() for c in portfolio.selected if c.slug == slug),
                    idempotency_key=f"score:{slug}:{today.isoformat()}")

    return {"as_of": today.isoformat(), "missing": missing,
            "off_portfolio": off_portfolio,
            "constraints_met": portfolio.constraints_met,
            "classifications": verdict.summary(),
            "evidence_available": verdict.evidence_available,
            "actions": verdict.actions}


@handlers.register("finance.reconcile")
def handle_finance_reconcile(ctx: JobContext) -> dict:
    """The books, section 15's full list, from observed entries only.

    Reports zero revenue because revenue is zero. Building the accounting before there is
    anything to flatter is the point: a P&L that first appears alongside the first sale is a
    P&L nobody has checked.
    """
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion
    from ..finance.books import Books

    books = Books(ctx.db)
    pl = books.profit_and_loss()

    with ctx.db.session() as s:
        validated = s.scalar(select(func.count()).select_from(PatternVersion).where(
            PatternVersion.certified == True)) or 0  # noqa: E712
        listings = s.scalar(select(func.count()).select_from(Listing)) or 0

    economics = books.unit_economics(products_validated=validated, listings_drafted=listings)
    ctx.audit("finance.reconciled", detail={"pl": pl.to_dict(), "unit": economics})
    ctx.enqueue("cfo", "finance.challenge", {}, idempotency_key=None)
    return {"pl": pl.to_dict(), "unit_economics": economics}


@handlers.register("finance.challenge")
def handle_finance_challenge(ctx: JobContext) -> dict:
    """The CFO/Skeptic (section 14), as a function rather than a personality.

    It reports concerns even when everything is nominally fine, because a reviewer who only
    speaks up during a crisis is a reviewer nobody has calibrated.
    """
    from sqlalchemy import select

    from ..core.models import SpendLimit
    from ..finance.books import Books, cfo_challenge, trajectory

    infra = float(ctx.job.inputs.get("infra_monthly_cad", 7.0))
    ceiling = float(ctx.job.inputs.get("infra_ceiling_cad", 20.0))

    books = Books(ctx.db)
    pl = books.profit_and_loss()
    with ctx.db.session() as s:
        limits = list(s.scalars(select(SpendLimit)))

    challenges = cfo_challenge(pl, limits=limits, infra_monthly_cad=infra,
                               infra_ceiling_cad=ceiling)
    blocks = [c for c in challenges if c.severity == "block"]
    ctx.audit("finance.challenged", detail={
        "challenges": [c.to_dict() for c in challenges],
        "blocking": len(blocks)})
    return {"challenges": [c.to_dict() for c in challenges],
            "blocking": len(blocks),
            "trajectory": trajectory(pl)}


@handlers.register("plan.strategy")
def handle_plan_strategy(ctx: JobContext) -> dict:
    """Monthly strategy recalibration and CA$100K trajectory (section 13).

    Deliberately produces a refusal today rather than a forecast: with no orders there is no
    run rate, and the CA$100K figure is the one most likely to be quoted back as though it
    were a projection.
    """
    from ..finance.books import Books, trajectory

    today = _scan_date(ctx)
    pl = Books(ctx.db).profit_and_loss()
    traj = trajectory(pl, today=today)
    portfolio = select_portfolio(today=today)

    ctx.audit("plan.strategy_reviewed", detail={
        "as_of": today.isoformat(),
        "trajectory": traj,
        "portfolio_size": len(portfolio.selected),
        "constraints_met": portfolio.constraints_met})
    ctx.enqueue("orchestrator", "portfolio.review", {"as_of": today.isoformat()},
                idempotency_key=f"portfolio.review:{today.isoformat()}")
    return {"as_of": today.isoformat(), "trajectory": traj,
            "is_forecast": traj["is_forecast"]}




# Importing the back half registers its handlers. Kept at the bottom because `release` imports
# job-context helpers from this module's neighbours, and a top-of-file import would be a cycle.
from . import release  # noqa: E402,F401
