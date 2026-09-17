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

from ..cir.compiler import compile_cir
from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..core.models import Phase, Product, PatternVersion
from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance
from ..gates.certificate import certify
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
ENGINEERED: dict[str, str] = {
    "nordic-forest-mosaic-throw": "brambleloop.products.nordic_forest",
}


def _engineered_cir(slug: str, version: str = "1.0.0") -> CIR | None:
    module_path = ENGINEERED.get(slug)
    if not module_path:
        return None
    import importlib

    module = importlib.import_module(module_path)
    cir = module.build(version=version)
    # Keep the concept's slug so the radar, the portfolio and the product row agree on the
    # name; the size-specific slugs are for the variants, not the headline product.
    return CIR.from_dict({**cir.to_dict(), "slug": slug})


@handlers.register("cir.draft")
def handle_cir_draft(ctx: JobContext) -> dict:
    engineered = _engineered_cir(ctx.job.inputs["slug"])
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
                idempotency_key=f"certify:{cir.slug}:{cir.version}")
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
        ctx.enqueue("listing", "listing.draft",
                    {"slug": cir.slug, "version": cir.version},
                    idempotency_key=f"listing:{cir.slug}:{cir.version}")

    return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
            "release_hash": cert.release_hash,
            "reasons": cert.blocking_reasons[:5]}


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
    ctx.enqueue("publishing", "assets.build", {"slug": slug, "version": version},
                idempotency_key=f"assets:{slug}:{version}")
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
    """Re-run the portfolio decision against today's calendar and today's catalogue.

    Section 12 classifies SKUs and retires persistent losers; section 33 says which products
    should exist. Both change with the date rather than with the catalogue: a product that
    was the right build in September is a dead listing in December, and a concept that scored
    too early last month may be in its window now.

    This reports drift. It does not retire or launch anything by itself -- there is no live
    performance data to classify against yet, and a review that acts on no evidence is not a
    review. What it does guarantee is that the divergence is visible and dated rather than
    discovered a season late.
    """
    from sqlalchemy import select

    today = _scan_date(ctx)
    portfolio = select_portfolio(today=today)
    should_exist = {c.slug for c in portfolio.selected}

    with ctx.db.session() as s:
        built = {p.slug for p in s.scalars(select(Product))}

    missing = sorted(should_exist - built)      # earned a place, not built yet
    off_portfolio = sorted(built - should_exist)  # built, no longer earns a place

    ctx.audit("portfolio.reviewed", detail={
        "as_of": today.isoformat(),
        "in_portfolio": len(should_exist),
        "built": len(built),
        "missing": missing[:20],
        "off_portfolio": off_portfolio[:20],
        "constraints_met": portfolio.constraints_met,
    })
    for slug in missing:
        ctx.enqueue("market_radar", "radar.score",
                    next(c.to_dict() for c in portfolio.selected if c.slug == slug),
                    idempotency_key=f"score:{slug}:{today.isoformat()}")

    return {"as_of": today.isoformat(), "missing": missing,
            "off_portfolio": off_portfolio,
            "constraints_met": portfolio.constraints_met}


@handlers.register("finance.reconcile")
def handle_finance_reconcile(ctx: JobContext) -> dict:
    from sqlalchemy import select

    from ..core.models import CostEntry, LedgerEntry

    with ctx.db.session() as s:
        revenue = sum(e.gross_cad for e in s.scalars(select(LedgerEntry)))
        fees = sum(e.fees_cad for e in s.scalars(select(LedgerEntry)))
        expense = sum(e.expense_cad for e in s.scalars(select(LedgerEntry)))
        opex = sum(e.amount_cad for e in s.scalars(select(CostEntry)))
    contribution = round(revenue - fees - expense - opex, 2)
    ctx.audit("finance.reconciled",
              detail={"revenue": revenue, "fees": fees, "expense": expense,
                      "agent_opex": round(opex, 4), "contribution": contribution})
    return {"revenue_cad": revenue, "agent_opex_cad": round(opex, 4),
            "contribution_cad": contribution}


# Importing the back half registers its handlers. Kept at the bottom because `release` imports
# job-context helpers from this module's neighbours, and a top-of-file import would be a cycle.
from . import release  # noqa: E402,F401
