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

from ..cir.compiler import compile_cir
from ..cir.model import CIR, Component, Gauge, Material, Op, Repeat, Row
from ..core.models import Phase, Product, PatternVersion
from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance
from ..gates.certificate import certify
from ..gates.incidents import IncidentTracker
from ..gates.policy import ListingDraft
from .worker import CapabilityNotEnabled, JobContext, handlers


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
        risk_class="A",
        colors=dict(c.colors),
        gauge=Gauge(stitches_per_10cm=16, rows_per_10cm=14, stitch_type="sc", hook_mm=5.0),
        materials=[Material(name="worsted acrylic", yarn_weight="worsted", color_id=p)
                   for p in palette],
        components=[Component(name="panel", construction="flat_rows", rows=rows,
                              foundation=c.width_stitches, foundation_kind="chain")],
        designer_notes=f"{c.category} concept, unit repeat {unit} sts",
    )


# ---- job handlers --------------------------------------------------------


@handlers.register("radar.scan")
def handle_radar_scan(ctx: JobContext) -> dict:
    """Shadow-mode radar: emits concepts from seeded categories.

    Real market data lands here once the radar integrations exist; the shape of the output is
    what the rest of the pipeline depends on.
    """
    seeds = ctx.job.inputs.get("categories") or ["mosaic_blanket", "seasonal_decor"]
    concepts = []
    for cat in seeds:
        concepts.append({
            "slug": f"{cat}-concept",
            "title": f"{cat.replace('_', ' ').title()} Pattern",
            "category": cat,
            "stitch_repeat": [["sc", 3], ["dc", 1]],
            "width_stitches": 40,
            "rows": 6,
            "colors": {"forest": "#244A3A", "cream": "#FAF6EB"},
        })
    ctx.audit("radar.scanned", detail={"count": len(concepts)})
    for c in concepts:
        ctx.enqueue("market_radar", "radar.score", c,
                    idempotency_key=f"score:{c['slug']}")
    return {"concepts": len(concepts)}


@handlers.register("radar.score")
def handle_radar_score(ctx: JobContext) -> dict:
    """Opportunity score. Deterministic and explainable, not a model's vibe."""
    c = dict(ctx.job.inputs)
    demand = {"mosaic_blanket": 0.8, "seasonal_decor": 0.7}.get(c.get("category", ""), 0.4)
    competition_penalty = 0.2
    machine_verifiable = 0.2  # Class A work the compiler can fully check
    score = round(demand - competition_penalty + machine_verifiable, 3)
    c["opportunity_score"] = score
    ctx.audit("radar.scored", artifact=c["slug"], detail={"score": score})
    if score >= 0.5:
        ctx.enqueue("crochet_engineer", "cir.draft", c,
                    idempotency_key=f"draft:{c['slug']}")
    return {"slug": c["slug"], "score": score, "promoted": score >= 0.5}


@handlers.register("cir.draft")
def handle_cir_draft(ctx: JobContext) -> dict:
    i = ctx.job.inputs
    concept = Concept(
        slug=i["slug"], title=i["title"], category=i["category"],
        stitch_repeat=[(s, n) for s, n in i["stitch_repeat"]],
        width_stitches=i["width_stitches"], rows=i["rows"], colors=i["colors"],
        opportunity_score=i.get("opportunity_score", 0.0),
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
    slug = ctx.job.inputs["slug"]
    ctx.audit("listing.drafted", artifact=slug)
    ctx.enqueue("store_operator", "store.publish",
                {"slug": slug, "version": ctx.job.inputs["version"]},
                idempotency_key=f"publish:{slug}:{ctx.job.inputs['version']}")
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
    ctx.enqueue("market_radar", "radar.scan", {"categories": ["mosaic_blanket"]})
    return {"planned": True}


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
