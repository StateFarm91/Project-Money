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


class ParityRefusal(CapabilityNotEnabled):
    """Listing export blocked by the eight-part creative parity gate (#75).

    Terminal for the same reason as a shadow refusal: re-running the same job against the
    same frames asks the same question. What changes a parity verdict is a different frame
    or a comparison that has not been made, neither of which a retry produces.
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
    # C-60 (#2): the observed market scores -- the nine-dimension arbitrage card and its
    # weakness hunt -- steer the pool before selection, so the hunt decides what gets made.
    from ..radar import arbitrage
    from ..radar.opportunity import score_pool

    steered, steering = arbitrage.steer_concepts(ctx.db, score_pool(today=today))
    portfolio = select_portfolio(steered, target=target, today=today)

    ctx.audit("radar.scanned", detail={
        "pool": len(portfolio.selected) + len(portfolio.rejected),
        "selected": len(portfolio.selected),
        "constraints_met": portfolio.constraints_met,
        "as_of": today.isoformat(),
        "arbitrage": steering,
    })
    if not portfolio.ok:
        # Never silently ship a portfolio that violates section 33; say which rule broke.
        unmet = [k for k, v in portfolio.constraints_met.items() if not v]
        ctx.audit("radar.portfolio_constraints_unmet", detail={"unmet": unmet,
                                                              "reasons": portfolio.reasons})

    # #114: a wave is segmented by skill level, or it is one kind of work that looks busy.
    # Measured on the wave actually selected, and a missing level is written as a creative
    # brief -- the gap is filled by ideation, never by relabelling a product's difficulty.
    from ..creative import preengineering

    skills = preengineering.wave_skill_portfolio([c.seed for c in portfolio.selected])
    ctx.audit("radar.skill_portfolio", detail={**skills, "as_of": today.isoformat()})
    missing = preengineering.missing_skill_levels(skills["wave"])
    excess = [g["level"] for g in skills["wave"]["gaps"] if "want_at_most" in g]
    if missing or excess:
        ctx.audit("radar.skill_gap", detail={
            "missing": missing, "over": excess, "gaps": skills["wave"]["gaps"],
            "brief": (f"ideate new concepts at {missing} for this wave; they enter "
                      f"engineering only through the pre-engineering gate"
                      if missing else "the wave leans on one level; ideate the others"),
            "as_of": today.isoformat()})

    for c in portfolio.selected:
        ctx.enqueue("market_radar", "radar.score", c.to_dict(),
                    idempotency_key=f"score:{c.slug}:{today.isoformat()}")

    return {
        "pool_size": len(portfolio.selected) + len(portfolio.rejected),
        "selected": [c.slug for c in portfolio.selected],
        "constraints_met": portfolio.constraints_met,
        "swaps": portfolio.reasons,
        "arbitrage_steered": [m["slug"] for m in steering["steered"]],
        "skill_portfolio": {"segmented": skills["wave"]["segmented"],
                            "shares": skills["wave"]["shares"], "missing": missing,
                            "over": excess},
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
    # The same steering as the scan (#2), so a concept is promoted on the score it was
    # selected on rather than on a base score the market evidence has already moved.
    from ..radar import arbitrage
    rescored = arbitrage.steer_concepts(ctx.db, [rescored])[0][0]
    promote = rescored.score >= PROMOTION_THRESHOLD and seed.risk_class in ("A", "B")

    # The pre-engineering gate (#83, #87, #88, #108, #110, #115, #125, #126). An opportunity
    # score says a slot is worth filling; it says nothing about whether *this idea* deserves
    # engineering. A design the catalogue already has is a rebuild and passes as one; anything
    # else is a new concept and must clear the whole deterministic sequence, or it is not
    # engineered -- refused back to creative development, or left waiting, unpassed, on a
    # judgement nobody can make yet.
    gate = None
    exempt = None
    if promote:
        from ..creative import preengineering

        exempt = (preengineering.established(ctx.db, seed.slug)
                  or ("a bundle is assembled from its members' releases, not engineered"
                      if seed.is_bundle else None))
        if exempt:
            ctx.audit("concept.gate_exempt", artifact=seed.slug,
                      detail={"reason": exempt, "source": "radar.score"})
        else:
            gate = preengineering.gate_concept(ctx.db, c, today=today)
            preengineering.record(ctx, gate, source="radar.score")
            promote = gate["engineer"]

    ctx.audit("radar.scored", artifact=seed.slug, detail={
        "score": rescored.score, "components": rescored.components,
        "promoted": promote,
        "gate": (gate or {}).get("decision") or ("exempt" if exempt else None),
    })
    if promote:
        payload = rescored.to_dict()
        payload.update(concept_geometry(seed))
        if gate is not None:
            payload["gate"] = {"decision": gate["decision"], "as_of": gate["as_of"]}
        ctx.enqueue("crochet_engineer", "cir.draft", payload,
                    idempotency_key=f"draft:{seed.slug}")
    return {"slug": seed.slug, "score": rescored.score, "promoted": promote,
            "components": rescored.components,
            "gate": (None if gate is None else
                     {k: gate[k] for k in ("decision", "failed", "unmeasured", "reasons",
                                           "waiting_on", "consequence")}),
            "gate_exempt": exempt,
            "reason": None if promote else (
                "Class C requires physical testing that does not exist yet"
                if seed.risk_class == "C" else
                gate["consequence"] if gate is not None else
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
    # And three more named for techniques their patterns could not contain: a cable throw
    # with no crossing, a bobble pillow with no bobble, a ribbed scarf with no rib. All three
    # were plain sc/dc colourwork (B-080).
    "heirloom-cable-blanket": "brambleloop.products.texture:build_cable_throw",
    "bobble-floor-pillow": "brambleloop.products.texture:build_bobble_pillow",
    "chunky-ribbed-scarf": "brambleloop.products.texture:build_ribbed_scarf",
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

    # The engineering entry point holds the same gate `radar.score` applies, so a new concept
    # cannot reach engineering by being enqueued here directly. A rebuild of an established
    # design (chain.rebuild re-drafting a certified product) is not a new concept and passes.
    # A payload that is neither a radar slot nor a creative concept is raw test geometry with
    # no idea attached; it is compiled so the compiler's refusals stay reachable.
    from ..creative import preengineering

    if (not preengineering.established(ctx.db, slug)
            and (seed is not None or isinstance(ctx.job.inputs.get("concept"), dict))):
        gate = preengineering.gate_concept(ctx.db, dict(ctx.job.inputs))
        if not gate["engineer"]:
            effects = preengineering.record(ctx, gate, source="cir.draft")
            return {"artifact": slug, "drafted": False, "gate": gate["decision"],
                    "reasons": gate["reasons"][:5], "unmeasured": gate["unmeasured"],
                    "consequence": gate["consequence"], "effects": effects}

    engineered = _engineered_cir(slug)
    if engineered is not None:
        ctx.audit("cir.drafted", artifact=f"{engineered.slug}@{engineered.version}",
                  detail={"source": "engineered design", "rows": sum(
                      len(c.rows) for c in engineered.components)})
        ctx.enqueue("validator", "cir.compile", {"cir": engineered.to_dict()},
                    idempotency_key=(f"compile:{engineered.slug}:{engineered.version}"
                                     f":{engineered.fingerprint}"))
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
                idempotency_key=(f"certify:{cir.slug}:{cir.version}:{cir.fingerprint}"
                                 f":d{DOC_VERSION}"))
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
                     f"as two PDFs -- one written throughout in US terms and one in UK "
                     f"terms. Drafted and checked with AI assistance and validated by an "
                     f"automated pattern compiler before release."),
        tags=["crochet pattern", "mosaic blanket", "pdf pattern"],
        price_cad=11.99,
    )

    from ..quality.physical import calibration_from_db

    from ..gates.platform_policy import policy_stamp

    cert = certify(cir, assets=[hero], listing=listing,
                   calibration=calibration_from_db(ctx.db, cir),
                   # #39: the certificate records which reading of the platform's rules it
                   # was issued under, so it can be re-examined when they change.
                   platform_policy=policy_stamp(ctx.db))
    ctx.audit("gate.certified" if cert.granted else "gate.blocked",
              artifact=f"{cir.slug}@{cir.version}",
              policy_version=cert.policy_version,
              detail={"granted": cert.granted, "reasons": cert.blocking_reasons[:5]})

    if cert.granted:
        _persist_release(ctx, cir, cert.to_dict(), cert.release_hash)
        # #70: a revision that changes geometry or claims invalidates the listing-set
        # certificate issued against the old ones, recomputed here rather than remembered,
        # and the affected frames lose their approval until the chain re-certifies them.
        _recheck_listing_certificates(ctx, cir)
        # Lane routing for the newly certified release (cadence and grant integrated).
        ctx.enqueue("quality_director", "gate.lanes", {},
                    idempotency_key=f"lanes:{cir.slug}:{cert.release_hash}")

        # #163 / #169: the teardown lab's QA of our own product. A product class that can
        # name no evidenced advantage beyond the purchased benchmarks is withheld here, with
        # the reason audited, before anything downstream is built for it.
        from ..teardown import lab as teardown_lab

        seed = _seed_for(cir.slug)
        teardown = teardown_lab.product_qa(
            ctx.db, cir.slug,
            product_class=(getattr(cir, "category", "") or (seed.category if seed else "")))
        if teardown.get("blocks_release"):
            ctx.audit("gate.release_withheld", artifact=f"{cir.slug}@{cir.version}",
                      detail={"reason": "teardown QA (#163): "
                                        + str(teardown["unique_value"].get("reason", ""))[:300],
                              "product_class": teardown.get("product_class")})
            return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
                    "release_hash": cert.release_hash, "withheld": True,
                    "reasons": [teardown["unique_value"].get("reason", "")][:1]}
        from .release import chain_key

        ctx.enqueue("listing", "listing.draft",
                    {"slug": cir.slug, "version": cir.version,
                     "release": cert.release_hash},
                    idempotency_key=chain_key("listing", cir.slug, cir.version,
                                              cert.release_hash or ""))
    else:
        _withdraw_listing(ctx, cir)

    return {"artifact": f"{cir.slug}@{cir.version}", "granted": cert.granted,
            "release_hash": cert.release_hash,
            "reasons": cert.blocking_reasons[:5]}


def _recheck_listing_certificates(ctx: JobContext, cir: CIR) -> list[dict]:
    """Run `listing_set.still_valid` over this release's certificates against the new design."""
    from ..gates.policy import POLICY_VERSION
    from ..publish import release_gates as gates_mod

    frames = gates_mod._frames(ctx.db, cir.slug, cir.version)
    listing = gates_mod._listing(ctx.db, cir.slug, cir.version)
    twin = gates_mod._twin(ctx.db, cir)
    results = gates_mod.recheck(ctx.db, slug=cir.slug, version=cir.version,
                                geometry=gates_mod.geometry_of(twin, cir),
                                claims=gates_mod.claims_of(listing, frames),
                                policy_version=POLICY_VERSION)
    for r in results:
        ctx.audit("listing_set.valid" if r["valid"] else "listing_set.invalidated",
                  artifact=f"{cir.slug}@{cir.version}",
                  detail={k: r[k] for k in ("record_id", "valid", "invalidated_by",
                                            "affected_assets", "why")})
    return results


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
            existing = PatternVersion(product_id=product.id, version=cir.version,
                                      cir_json=cir.to_dict(), release_hash=release_hash,
                                      certified=True, certificate=certificate)
            s.add(existing)
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
        s.flush()

        # The certificate is the first derived artefact of a release, and it is recorded
        # against the *stored* design rather than the CIR in hand: `current_from_db`
        # fingerprints `cir_json`, and a second spelling of the same design would make every
        # certificate read stale the moment it was issued (#171). No `chain:release` input
        # on purpose -- the certificate is a fact about the design and the gates, not about
        # the post-certification chain, and a chain bump must not revoke it.
        from ..ops import artefacts as provenance

        inputs = {f"cir:{cir.slug}": provenance.fingerprint(existing.cir_json)}
        if release_hash:
            inputs[f"release:{cir.slug}"] = release_hash[:16]
        provenance.record_lineage(
            s, artefact_class="certificate",
            artefact_key=provenance.release_key(cir.slug, cir.version),
            product_slug=cir.slug, inputs=inputs, chain_version=str(DOC_VERSION),
            lineage=provenance.Lineage(
                created_by=ctx.job.agent, job_id=ctx.job.id,
                sha256=release_hash if len(release_hash or "") == 64 else "",
                validation_status="certified",
                publication_authority=ctx.phase.value if ctx.phase else "shadow"))


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

    release = ctx.job.inputs.get("release", "")
    token = ctx.job.inputs.get("rebuild", "")
    ctx.enqueue("publishing", "assets.build",
                {"slug": slug, "version": version, "release": release, "rebuild": token},
                idempotency_key=chain_key("assets", slug, version, release, token))
    # #41: an owed purchase disclosure missing from the draft's copy is a finding on it.
    # On a first release there is no stored copy yet and this reads UNMEASURED (C-47); the
    # check that measures runs in `listing.seo` right after the Listing row is written, and
    # again at publish. This one still catches a re-draft whose stored copy has drifted.
    from ..commerce.buyer_trust import listing_disclosure_finding

    disclosure = listing_disclosure_finding(ctx.db, slug=slug, version=version)
    if disclosure.get("finding"):
        ctx.audit("listing.disclosure_finding", artifact=f"{slug}@{version}", detail=disclosure)
    return {"artifact": slug, "drafted": True, "disclosures": disclosure}


def _certified_pdf_hashes(db, slug: str, version: str, release: str) -> dict | None:
    """The per-terminology PDF hashes `assets.build` recorded for (slug, version, release).

    Read from the `assets.built` audit row and the job that wrote it: the row carries the
    stored files (`pdfs`), the job's inputs carry the release and its outputs carry
    `pdf_sha256_by_terminology`. Newest first; a release given must match the job's release.
    None when nothing on record certifies a file for this release.
    """
    from sqlalchemy import desc, select

    from ..core.models import AuditLog, Job

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "assets.built", AuditLog.artifact == f"{slug}@{version}")
            .order_by(desc(AuditLog.id))))
        for row in rows:
            job = s.get(Job, row.job_id) if row.job_id else None
            inputs = (job.inputs or {}) if job is not None else {}
            outputs = (job.outputs or {}) if job is not None else {}
            if release and (inputs.get("release") or outputs.get("release") or "") != release:
                continue
            detail = row.detail or {}
            hashes = (detail.get("pdf_sha256_by_terminology")
                      or outputs.get("pdf_sha256_by_terminology")
                      or {t: (v or {}).get("sha256")
                          for t, v in (detail.get("pdfs") or {}).items()})
            hashes = {t: h for t, h in (hashes or {}).items() if h}
            if hashes:
                return hashes
    return None


def check_pdf_hashes(db, *, slug: str, version: str, release: str,
                     rendered: dict[str, bytes]) -> dict:
    """Refuse an upload whose re-rendered PDF is not the file `assets.build` certified.

    `store.publish` renders the customer's documents again at upload time. The release date
    is pinned so the bytes should be identical; if they are not, something changed between
    certification and upload (the writer, the renderer, the design) and the buyer would
    download a file nobody certified. That is `PDF_HASH_DRIFT`, a PermanentError, because
    retrying renders the same drifted bytes.
    """
    import hashlib

    from ..core.resilience import PermanentError

    certified = _certified_pdf_hashes(db, slug, version, release)
    if not certified:
        raise PermanentError(
            f"PDF_HASH_DRIFT: no assets.built hash is on record for {slug}@{version} "
            f"release {release or '(none)'}, so the file about to be uploaded cannot be shown "
            f"to be the certified one")
    actual = {t: hashlib.sha256(b).hexdigest() for t, b in rendered.items()}
    drift = {t: {"certified": certified.get(t), "rendered": h}
             for t, h in actual.items() if certified.get(t) != h}
    if drift:
        raise PermanentError(
            f"PDF_HASH_DRIFT: the re-rendered PDF for {slug}@{version} differs from the "
            f"certified file for {sorted(drift)}: {drift}")
    return {"verified": sorted(actual), "certified": certified}


@handlers.register("store.publish")
def handle_store_publish(ctx: JobContext) -> dict:
    """In SHADOW this must refuse. Publishing is a production capability with its own gate.

    Past shadow, this is where the Etsy client is asked -- and the client has its own three
    refusals in front of it, so "the phase allows it" is the first of four conditions rather
    than the only one. Nothing in this environment satisfies the others: there are no
    credentials and no owner grant.
    """
    # The eight-part creative parity gate (#75). *Computed* before the phase check and
    # *enforced* after it, and the split is deliberate.
    #
    # Computed first, because a gate that only runs once the phase allows publishing is a
    # gate nobody has ever seen run, and the first listing it judged would be a live one.
    # This reads evidence already on file -- no render, no model call, no network -- so
    # running it on every refused attempt costs nothing and produces the record of it
    # working that Shadow Mode otherwise makes impossible to gather.
    #
    # Enforced after, because Shadow Mode is the outermost boundary and must stay the
    # reason. A system that refuses to publish for a creative reason before establishing
    # that it is allowed to publish at all has inverted its own gates, and the refusal
    # `/api/verify` counts as evidence of Shadow Mode working would start saying something
    # else.
    parity_verdict = _listing_parity(ctx)
    ctx.audit("listing.parity", artifact=ctx.job.inputs.get("slug"), detail=parity_verdict)

    # The release-chain publish gates (#58, #60, #65, #66, #70, #80, #172, #173, #297), on
    # the same split as parity: computed on every attempt from evidence on file, so Shadow
    # Mode produces the record of them working, and enforced below after the capability
    # gates and before anything is uploaded.
    release_gates = _release_gates(ctx)
    ctx.audit("store.release_gates", artifact=ctx.job.inputs.get("slug"),
              detail=release_gates)

    if ctx.phase is Phase.SHADOW:
        ctx.audit("store.publish_refused", artifact=ctx.job.inputs.get("slug"),
                  detail={"reason": "shadow mode: no live publication",
                          "creative_parity": parity_verdict["verdict"],
                          "parity_would_block": parity_verdict["blocks_release"],
                          "release_gates_would_block": release_gates["blocks_release"],
                          "release_gate_reasons": release_gates["reasons"][:5]})
        raise ShadowModeRefusal(
            "store.publish is a production capability; the system is in SHADOW mode and has "
            "no live Etsy connection. Draft retained for review."
        )


    import os

    from sqlalchemy import select

    from ..core.models import Listing
    from ..integrations.etsy import Credentials, EtsyClient, build_payload
    from ..integrations.http import UrllibTransport

    slug = ctx.job.inputs["slug"]
    version = ctx.job.inputs.get("version", "1.0.0")

    transport = UrllibTransport()
    client = EtsyClient(
        transport,
        # The transport is handed to the credentials so that an OAuth token which has
        # expired -- Etsy's access tokens live one hour -- is refreshed rather than sent.
        # Without it this job works for an hour after a human pasted a token and then fails
        # with a 401 that looks exactly like a revoked app.
        #
        # The database is handed over for the other half of the same problem. Etsy issues a
        # **new refresh token on every refresh** and spends the old one, so a refresh that is
        # not written down survives exactly as long as this container does. With `db` the
        # provider reads the sealed credential from `oauth_credentials` and writes each
        # rotation back under compare-and-set, which is what makes an unattended publish job
        # still authenticated next week.
        credentials=Credentials.from_env(transport=transport, db=ctx.db),
        phase=ctx.phase.value,
        # A separate fact from having a key: publishing is RED in the authority matrix.
        owner_authorised=os.environ.get("BRAMBLELOOP_PUBLISH_AUTHORISED", "") == "1")

    refusal = client.refusal()
    if refusal is not None:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": refusal})
        raise ShadowModeRefusal(refusal)

    # Enforced here: after every question about whether this system may publish at all,
    # and before anything is sent. Phase, credentials and the authority matrix are
    # capability gates and stay outermost; parity is the question of whether *this listing*
    # is good enough, which is only worth asking of a system that could publish it.
    if parity_verdict["blocks_release"]:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": f"creative parity (#75): {parity_verdict['why']}"})
        raise ParityRefusal(
            f"listing export is blocked by the eight-part creative parity gate: "
            f"{parity_verdict['why']}")

    with ctx.db.session() as s:
        listing = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
        if listing is None:
            raise ValueError(f"no drafted listing for {slug}@{version}: publishing cannot "
                             f"precede the listing the gates checked")
        copy = dict(title=listing.title, description=listing.description,
                    price_cad=listing.price_cad, tags=list(listing.tags))
        already = listing.etsy_listing_id
        release = ctx.job.inputs.get("release") or listing.release_hash or ""

    if already:
        # Publishing twice must not create a second listing. Updating an existing one is a
        # different operation with a different risk profile, so it is refused here rather
        # than guessed at.
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": f"already on Etsy as listing {already}"})
        return {"slug": slug, "version": version, "published": False,
                "etsy_listing_id": already, "reason": "already published"}

    # C-49: both names live in their own modules; importing them here is what lets a
    # non-shadow publish run at all rather than die with NameError on its first line.
    from ..cir.twin import build_twin
    from ..quality.physical import calibration_from_db
    from .release import _load_cir

    cir = _load_cir(ctx, slug, version)
    payload = build_payload(materials=[m.name for m in cir.materials], **copy)

    # The bytes have to exist. Without durable storage they may not, and the client refuses
    # an empty upload rather than creating a listing that delivers nothing.
    from ..core.artifacts import ArtifactStore
    from ..core.resilience import PermanentError, TransientError
    from ..publish.pdf import TERMINOLOGIES, build_pattern_pdf, pattern_filename

    result = compile_cir(cir)
    # C-50: the calibration `assets.build` rendered with, or the yardage lines differ and the
    # certified file and the uploaded file are two different documents.
    twin = build_twin(cir, result, calibration=calibration_from_db(ctx.db, cir))
    # Pinned to the release date, not to the day of the upload. This render is the file the
    # customer actually downloads, and `assets.build` recorded a hash for it earlier; left to
    # default, the release date printed on the cover would be today's and the two would be
    # different files for no reason connected to the pattern.
    from .release import _released_on

    released_on = _released_on(ctx, slug, version)
    docs = {t: build_pattern_pdf(cir, twin=twin, terminology=t, released_on=released_on)
            for t in TERMINOLOGIES}
    doc = docs["US"]
    # The file uploaded must be the file certified: compared per terminology against the
    # `assets.built` hashes for this release, before anything is stored or sent.
    try:
        hash_check = check_pdf_hashes(
            ctx.db, slug=slug, version=version, release=release,
            rendered={t: d.pdf_bytes for t, d in docs.items()})
    except PermanentError as e:
        ctx.audit("store.publish_refused", artifact=f"{slug}@{version}",
                  detail={"reason": str(e)[:500], "code": "PDF_HASH_DRIFT"})
        raise
    ctx.audit("store.pdf_hash_verified", artifact=f"{slug}@{version}", detail=hash_check)
    # #126, release half (after parity and the hash check, before anything is stored or
    # sent): the product must have cleared the blind search-grid tournament.
    # No recorded verdict reads as not cleared -- a threshold cleared by default is the
    # favouritism the requirement forbids -- and the refusal is an audited block.
    from ..creative import preengineering

    grid = preengineering.release_grid_verdict(ctx.db, slug)
    if not grid["cleared"]:
        ctx.audit("store.publish_blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": [f"search-grid tournament (#126): {grid.get('why')}"],
                          "grid": grid})
        return {"slug": slug, "version": version, "published": False, "blocked": True,
                "reasons": [f"search-grid tournament (#126): {grid.get('why')}"]}

    # The release-chain gates, enforced after the file to be uploaded
    # has been shown to be the certified one and before anything is stored or sent. An
    # audited, reasoned block rather than an exception: the job completes, says it did not
    # publish and why, and the reasons are what a rebuild or re-certification has to clear.
    if release_gates["blocks_release"]:
        ctx.audit("store.publish_blocked", artifact=f"{slug}@{version}",
                  detail={"reasons": release_gates["reasons"][:10],
                          "certificate": (release_gates.get("listing_set") or {})
                          .get("certificate")})
        return {"slug": slug, "version": version, "published": False, "blocked": True,
                "reasons": release_gates["reasons"]}

    store = ArtifactStore(ctx.job.inputs.get("artifact_dir"))
    stored_by_terminology = {
        t: store.put(f"{slug}/{version}/{pattern_filename(t)}", d.pdf_bytes,
                     "application/pdf")
        for t, d in docs.items()}
    stored = stored_by_terminology["US"]

    # The uploaded name comes from the same place as the stored one. It was spelled out here,
    # so the file in the buyer's downloads folder and the file in the artifact store could have
    # been named by two different rules.
    outcome = client.publish(payload=payload,
                             filename=f"{slug}-{pattern_filename('US')}",
                             data=doc.pdf_bytes)

    # The second file, attached after the first.
    #
    # `assets.build` renders both terminologies and the listing claims both, so a listing that
    # delivers only the US document takes money for something it did not sell. `client.publish`
    # creates the draft and attaches one file, which is the right shape for the transaction it
    # names; the rest are ordinary `attach_file` calls against a listing that now exists.
    #
    # Recorded per file rather than folded into one boolean: a listing with the US pattern and
    # no UK pattern is a real, deliverable, partly-wrong state, and "published: true" would
    # hide it. That is the half-done case this handler already refuses to round off.
    extra_files: dict[str, bool] = {}
    extra_problems: list[str] = []
    if outcome.listing_id and outcome.file_uploaded:
        for terminology in TERMINOLOGIES[1:]:
            try:
                extra_files[terminology] = client.attach_file(
                    outcome.listing_id,
                    filename=f"{slug}-{pattern_filename(terminology)}",
                    data=docs[terminology].pdf_bytes)
            except (TransientError, PermanentError) as e:
                extra_files[terminology] = False
                extra_problems.append(
                    f"listing {outcome.listing_id} has the US pattern attached and not the "
                    f"{terminology} one, which the listing copy promises: {e}")
            else:
                if not extra_files[terminology]:
                    extra_problems.append(
                        f"listing {outcome.listing_id} accepted the {terminology} pattern "
                        f"upload without returning a file id, so the buyer may receive only "
                        f"the US document the listing copy promises alongside it")

    if outcome.listing_id:
        with ctx.db.session() as s:
            row = s.scalar(select(Listing).where(Listing.product_slug == slug,
                                                 Listing.version == version))
            if row is not None:
                row.etsy_listing_id = outcome.listing_id
                row.state = "published" if outcome.published else "incomplete_on_etsy"

    ctx.audit("store.published" if outcome.published else "store.publish_incomplete",
              artifact=f"{slug}@{version}",
              detail={"etsy_listing_id": outcome.listing_id,
                      "file_uploaded": outcome.file_uploaded,
                      "pdf_sha256": stored.sha256,
                      "pdf_sha256_by_terminology": {
                          t: art.sha256
                          for t, art in sorted(stored_by_terminology.items())},
                      "files_attached_by_terminology": {
                          "US": outcome.file_uploaded, **extra_files},
                      "problems": (outcome.problems + extra_problems)[:5]})

    if outcome.needs_completion:
        # A listing on Etsy with no file attached would take money and deliver nothing.
        from ..gates.incidents import DefectReport, IncidentTracker

        IncidentTracker(ctx.db).report(DefectReport(
            product_slug=slug, pattern_version=version, component=None, row=None,
            customer_ref=f"etsy:{outcome.listing_id}",
            text=(f"Etsy listing {outcome.listing_id} exists with no digital file attached. "
                  f"It must be completed or deleted before it can take an order.")))

    return {"slug": slug, "version": version, "published": outcome.published,
            "etsy_listing_id": outcome.listing_id,
            "file_uploaded": outcome.file_uploaded,
            "files_attached_by_terminology": {"US": outcome.file_uploaded, **extra_files},
            "problems": outcome.problems + extra_problems}


def _release_gates(ctx: JobContext) -> dict:
    """The publish gates for the listing this job would export, never raising.

    A gate that crashed has not passed, so an error is reported as a block with its reason
    rather than raised -- raising here would replace the Shadow Mode refusal with a stack
    trace and publish nothing either way, but say so less clearly.
    """
    from datetime import date as _date

    from ..publish import release_gates as gates_mod

    i = ctx.job.inputs or {}
    slug, version = i.get("slug", ""), i.get("version", "1.0.0")
    try:
        verdict = gates_mod.for_publish(
            ctx.db, slug=slug, version=version,
            today=_date.fromisoformat(i["as_of"]) if i.get("as_of") else None,
            positioning=i.get("positioning"), store_root=i.get("artifact_dir"))
    except Exception as e:  # noqa: BLE001 - a crashed gate is a closed gate
        return {"slug": slug, "version": version, "blocks_release": True,
                "reasons": [f"release gates could not be evaluated: "
                            f"{type(e).__name__}: {str(e)[:300]}"]}
    return verdict


@handlers.register("ops.heartbeat")
def handle_heartbeat(ctx: JobContext) -> dict:
    q = ctx.queue.counts()
    dead = len(ctx.queue.dead_letters())
    ctx.audit("ops.heartbeat", detail={"queue": q, "dead_letters": dead})
    return {"queue": q, "dead_letters": dead}


# What a cadence reports when it did something. A handler that ran and moved none of these
# did no work, whatever its `ran` flag says -- and the flag is the unreliable half: the
# discovery cadence reported `ran: true, proposed: 0, cost_cad: 0` for two consecutive runs
# because a truncated prompt returned no concepts, and a rule reading only the flag left it
# waiting a week for a window it had already spent.
WORK_COUNTERS: tuple[str, ...] = (
    "proposed", "survivors", "judged", "requeued", "recadenced", "new", "reclassified",
    "inspected", "moved", "enqueued", "listings_known", "dead_letters",
    # A tournament that generated eighty concepts and kept none of them did its job. Reading
    # only `survivors` would call the most informative possible result a no-op and re-drive
    # it, which would pay for the same answer again.
    "generated", "reviews_read",
)


def did_no_work(outputs: dict) -> bool:
    """True when a completed job reports that nothing happened.

    Two shapes, because handlers were written at different times: an explicit `ran: false`,
    and a `ran: true` whose every work counter is zero. The second is the one that hides --
    it reads as a successful run in every dashboard, and it is what a defect upstream of the
    work produces.
    """
    if outputs.get("ran") is False:
        return True
    if outputs.get("ran") is not True:
        return False
    counters = [outputs.get(key) for key in WORK_COUNTERS if key in outputs]
    return bool(counters) and not any(counters)


@handlers.register("ops.queue_check")
def handle_queue_check(ctx: JobContext) -> dict:
    """Re-drive what a deploy fixed: dead letters, and cadences that wrongly said "nothing".

    Two failure shapes, one bound. A dead letter caused by a defect is work the company still
    owes. And a cadence that *completed* reporting nothing to do is the same debt wearing a
    success: the weekly discovery run reported "no proven-and-unserved arena is observed"
    against a matrix holding twenty-seven of them, because a reader had the wrong key. It
    consumed its window, so without this it would sit idle for seven days after the fix, and
    the dead-letter re-drive cannot help because the job did not fail.

    The fix for a defect is a deploy, so a deploy is the event that retries it -- once. A
    commit that did not fix it produces the same no-op or the same failure and waits for the
    next one, which is what stops this being a loop. A cadence whose last run *succeeded*
    with real work is never re-enqueued, so a run that costs money costs it once.

    Deliberate refusals are never re-driven: `requeue_dead` skips anything whose error carries
    a refusal marker, so Shadow Mode's publication refusals stay refused.
    """
    from sqlalchemy import desc, select

    from ..core import build
    from ..core.models import AuditLog, Job
    from ..queue.durable import DuplicateJob
    from .worker import CADENCES

    dead = ctx.queue.dead_letters()
    if dead:
        ctx.audit("ops.dead_letters_present", detail={"ids": [d.id for d in dead][:20]})

    here = build.commit() or "unknown"
    if here == "unknown":
        return {"dead_letters": len(dead), "requeued": 0, "recadenced": 0,
                "reason": ("the deployed commit is unknown, so 'once per deploy' has no "
                           "meaning and a retry here would be an unbounded loop")}

    with ctx.db.session() as s:
        seen = list(s.scalars(
            select(AuditLog).where(AuditLog.action == "ops.requeued_for_commit")
            .order_by(desc(AuditLog.id)).limit(20)))
    if any((row.detail or {}).get("commit") == here for row in seen):
        return {"dead_letters": len(dead), "requeued": 0, "recadenced": 0,
                "reason": "this commit has already re-driven them"}

    requeued: list[int] = []
    if dead:
        result = ctx.queue.requeue_dead(
            job_types=sorted({j.job_type for j in dead if j.job_type != "store.publish"}))
        requeued = list(result.get("requeued") or [])

    # The no-op half. Only the last attempt matters: a cadence that has since run properly
    # is finished with, and one still reporting nothing gets exactly one more chance.
    recadenced: list[str] = []
    with ctx.db.session() as s:
        for name, agent, job_type, _period in CADENCES:
            last = list(s.scalars(select(Job).where(Job.job_type == job_type)
                                  .order_by(desc(Job.id)).limit(1)))
            if not last:
                continue
            if did_no_work(last[0].outputs or {}):
                recadenced.append(name)

    for name, agent, job_type, _period in CADENCES:
        if name not in recadenced:
            continue
        try:
            ctx.enqueue(agent, job_type, {"cadence": name, "retry_for_commit": here},
                        idempotency_key=f"cadence:{name}:retry:{here}")
        except DuplicateJob:
            continue

    ctx.audit("ops.requeued_for_commit",
              detail={"commit": here, "requeued": requeued, "recadenced": recadenced})
    return {"dead_letters": len(dead), "requeued": len(requeued),
            "recadenced": len(recadenced), "cadences": recadenced, "commit": here}


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
    from ..finance.spend_policy import INFRA_CEILING_CAD, INFRA_MONTHLY_CAD

    # Declared by the owner, not observed from a bill: `spend_policy.INFRA_BASIS` says so.
    infra = float(ctx.job.inputs.get("infra_monthly_cad", INFRA_MONTHLY_CAD))
    ceiling = float(ctx.job.inputs.get("infra_ceiling_cad", INFRA_CEILING_CAD))

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


@handlers.register("finance.escalation_check")
def handle_finance_escalation_check(ctx: JobContext) -> dict:
    """Tell the owner at four-fifths of the month, as a job rather than as a page.

    `spend_policy.escalation` carried the six fields the owner asked for and was computed in
    exactly one place: the GET handler for /api/spend-report. An escalation that exists only
    when somebody fetches it is a report, not an escalation -- a month that reached 80% with
    nobody looking reached the first refusal with nobody told, which is the outcome the
    policy's "approaching the ceiling is a report, never a quiet downgrade" exists to
    prevent.

    One owner action per calendar month, keyed `spend.ceiling.<YYYY-MM>`. A rerun in the same
    month restates the figures on the open row rather than adding a second; a row the owner
    has already closed is left closed, because "done" is their decision and not this job's to
    re-open. Under the line it writes nothing but the audit of having looked.

    `as_of` in the inputs pins the instant for a deterministic run; production passes none.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from ..core.models import OwnerAction
    from ..finance import spend_policy

    raw = ctx.job.inputs.get("as_of")
    now = datetime.fromisoformat(raw) if raw else datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    report = spend_policy.escalation(ctx.db, now=now)
    key = spend_policy.escalation_key(now)
    result = {"as_of": now.isoformat(), "required": bool(report["required"]),
              "share_of_ceiling": report.get("share_of_ceiling", report.get("share")),
              "requirement_key": key, "owner_action": None}

    if not report["required"]:
        ctx.audit("finance.escalation_checked", detail={**result, "why": report.get("why")})
        return result

    fields = spend_policy.owner_action_fields(report)
    with ctx.db.session() as s:
        existing = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key))
        if existing is None:
            s.add(OwnerAction(requirement_key=key, **fields))
            result["owner_action"] = "queued"
        elif existing.done:
            result["owner_action"] = "already_decided"
        else:
            for name, value in fields.items():
                setattr(existing, name, value)
            result["owner_action"] = "restated"

    ctx.audit("finance.escalation_checked", detail={
        **result, "current_spend_cad": report["current_spend_cad"],
        "ceiling_cad": report["ceiling_cad"],
        "proposed_ceiling_cad": report["proposed_ceiling_cad"],
        "what_is_constrained": report["what_is_constrained"]})
    return result


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
from . import commerce_readings  # noqa: E402,F401  (C-59: gated machinery, run daily)


def _listing_parity(ctx: JobContext) -> dict:
    """#75 for the listing this job would export, from evidence already on file.

    Never renders and never asks a model anything: every dimension is a reading of an
    asset record that exists, or `unjudged`. The benchmark comparison is passed through
    when one has been made and left absent when none has -- assuming this company compares
    well beside MJs is the one answer nobody has evidence for.
    """
    from ..publish import listing_asset
    from ..visual import parity

    slug = ctx.job.inputs.get("slug", "")
    version = ctx.job.inputs.get("version", "1.0.0")
    frames = listing_asset.frames_for(ctx.db, slug=slug)
    # #81: the deterministic rung is available when a certified CIR exists to render the
    # chart and twin from -- which is what `assets.build` does, free and truthful.
    deterministic = _certified_release(ctx.db, slug, version)
    try:
        verdict = parity.assess(frames, benchmark_quality=_benchmark_quality(ctx.db, slug),
                                deterministic_available=(
                                    deterministic is not None
                                    or parity._deterministic_available(frames)))
    except parity.ParityRefused as exc:
        # A partial set cannot satisfy #75, and the refusal is the gate working. Reported
        # as blocking rather than raised, so the publish attempt records why.
        return {"verdict": parity.UNJUDGED, "blocks_release": True,
                "why": str(exc)[:300], "dimensions": {}, "slug": slug}
    verdict = {**verdict, "slug": slug, "frames_judged": len(frames)}

    # #81: a ladder that is only recorded is a plan nobody executes. When the deterministic
    # rung is taken, the render it names is enqueued -- once per failure and evidence state,
    # so a refused publish retried on the same evidence does not queue it again. Gated rungs
    # (generation, physical proof) are never started from here, and release stays blocked
    # until parity passes on the new frames.
    escalation = verdict.get("escalation") or {}
    if escalation.get("taken") == "deterministic_representation" and deterministic:
        import hashlib

        from .release import chain_key

        release = ctx.job.inputs.get("release") or (
            deterministic if deterministic != "certified" else "")
        state = hashlib.sha256(repr((sorted(verdict.get("failed") or []), sorted(
            str(f.get("image_ref") or f.get("image") or "") for f in frames))).encode()
        ).hexdigest()[:16]
        token = f"parity-escalation:{state}"
        job = ctx.enqueue("publishing", "assets.build",
                          {"slug": slug, "version": version, "release": release,
                           "rebuild": token},
                          idempotency_key=chain_key("assets", slug, version, release, token))
        escalation["enqueued"] = {"job_type": "assets.build", "rebuild": token,
                                  "job_id": getattr(job, "id", None),
                                  "already_queued": job is None}
        ctx.audit("creative.escalation_taken", artifact=f"{slug}@{version}",
                  detail={"failed": verdict.get("failed"), "rung": escalation["taken"],
                          **escalation["enqueued"]})

    # #41 re-checked at publish: an owed purchase disclosure missing from the stored copy
    # blocks export, whatever parity says. UNMEASURED (no copy) is reported; publication
    # itself refuses a listing that was never drafted.
    from ..commerce.buyer_trust import listing_disclosure_finding

    disclosure = listing_disclosure_finding(ctx.db, slug=slug, version=version)
    verdict["disclosures"] = disclosure
    if disclosure.get("finding"):
        verdict["blocks_release"] = True
        missing = [m["disclosure"] for m in disclosure.get("missing", [])] + [
            m["disclosure"] for m in disclosure.get("misplaced", [])]
        verdict["why"] = (f"{verdict['why']}; listing disclosures (#41) missing or "
                          f"misplaced: {missing}")

    # #35 re-checked at publish: the release must have been classified when its listing was
    # written, with no refused asset and its class enabled against a current policy reading.
    classified = _release_classification(ctx.db, slug, version)
    verdict["classification"] = classified
    if not classified.get("ok"):
        verdict["blocks_release"] = True
        verdict["why"] = f"{verdict['why']}; Etsy creativity/AI classification (#35): " \
                         f"{classified.get('why')}"
    return verdict


def _release_classification(db, slug: str, version: str) -> dict:
    """The newest `listing.classified` row for this release, read as a publish condition."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..gates import platform_policy

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(
            AuditLog.action == platform_policy.CLASSIFIED_ACTION,
            AuditLog.artifact == f"{slug}@{version}").order_by(desc(AuditLog.id)).limit(1))
        detail = dict(row.detail or {}) if row is not None else None
    if detail is None:
        return {"ok": False, "reading": "UNMEASURED",
                "why": "this release was never classified, so its disclosures are unknown"}
    problems = list(detail.get("problems") or [])
    enabled = (detail.get("class_enablement") or {}).get("enabled")
    if problems:
        return {"ok": False, "why": f"classification refused assets: {problems[:3]}",
                "audit": detail}
    if not enabled:
        return {"ok": False, "why": ("the product class was not enabled against a current "
                                     "policy reading: "
                                     + str((detail.get("class_enablement") or {}).get("why"))[:300]),
                "audit": {k: detail.get(k) for k in ("classification", "class_enablement")}}
    return {"ok": True, "why": "classified, disclosures generated, class enabled",
            "disclosures": (detail.get("classification") or {}).get("disclosures")}


def _certified_release(db, slug: str, version: str) -> str | None:
    """The release hash of a certified version of this product, or None."""
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        row = s.scalar(select(PatternVersion).join(Product, Product.id == PatternVersion.product_id)
                       .where(Product.slug == slug, PatternVersion.version == version,
                              PatternVersion.certified.is_(True)))
        return (row.release_hash or "certified") if row is not None else None


def _benchmark_quality(db, slug: str) -> dict | None:
    """The blind comparison against observed benchmark listings, if one has been made.

    None rather than a favourable default. `parity` reads the absence as `unjudged`, which
    blocks -- which is correct: #75 asks for a comparison, and a comparison nobody made is
    not a comparison that went well.
    """
    # C-45: this product's own newest row, filtered in the query, and only while current.
    # It read the newest ten rows of any product, so with eleven in the catalogue one was
    # permanently unjudged, and a months-old verdict counted as today's.
    from ..creative import blind_review

    return blind_review.current_review(db, slug=slug)
