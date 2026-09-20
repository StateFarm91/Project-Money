"""The tournament's fifth stage: the release gates, run rather than named.

Requirement 3's last stage, and the funnel states its gate plainly -- *the release gates:
quality director, asset truth, policy*. Those gates already exist and are already the thing
that decides whether a pattern ships. What did not exist was a route from a tournament
survivor to a certificate, so the stage was named as unrun for the same reason prototype was:
nothing assembled the inputs the chain needs.

It needs three things a concept does not carry, and each is built here from something this
company already has rather than from a model.

**A hero asset.** Rendered from the digital twin, whose provenance is `twin` -- Brambleloop's
own arithmetic made visible. That is deliberately not a photograph: photographic imagery
needs the image-generation capability, and a placeholder standing in for one is exactly what
the asset-truth gate refuses.

**A listing draft.** Written deterministically from the concept's own fields. A model is
allowed to write listing copy, but a tournament stage is not the place to spend on one, and
copy assembled from the concept cannot claim anything the concept does not say.

**A price.** The median of what the benchmark's own listings in this department charge. Not
a guess and not a constant: the one number about this market that has been observed.

The gate then does what it always did. This module's whole job is to stop the chain being
something the tournament talks about.
"""
from __future__ import annotations

# A pattern nobody has priced evidence for still needs a price to be policy-checked. This is
# the floor the pricing module already enforces, restated as the fallback rather than a
# plausible-looking number that would read as evidence.
from ..commerce.pricing import MIN_PRICE_CAD

# Tags a pattern listing carries whatever it is. Marketplace furniture, in the sense
# `commerce/intent` uses: words that describe nothing and are most of what a shopper types.
BASE_TAGS: tuple[str, ...] = ("crochet pattern", "pdf pattern", "instant download")


class CertificationRefused(ValueError):
    """A survivor that cannot even be presented to the release chain."""


def observed_price(db, pod: str, *, benchmark_key: str = "") -> dict:
    """What this department's observed listings actually charge.

    The median rather than the mean, because one bundle listed at CA$45 moves a mean and does
    not move what a shopper expects to pay. Reported with the count behind it, so a price
    resting on four listings is visibly resting on four listings.
    """
    from sqlalchemy import select

    from ..core.models import BenchmarkListing
    from ..intel import benchmarks

    benchmark_key = benchmark_key or benchmarks.MJS_KEY
    with db.session() as s:
        prices = sorted(
            float(r.price_cad) for r in s.scalars(select(BenchmarkListing).where(
                BenchmarkListing.benchmark_key == benchmark_key,
                BenchmarkListing.pod == pod))
            if r.price_cad and r.price_cad > 0)

    if not prices:
        return {"measurable": False, "price_cad": MIN_PRICE_CAD, "observed": 0,
                "why": (f"no observed listing in {pod!r} carries a price, so this falls back "
                        f"to the floor rather than to a plausible number that would read as "
                        f"evidence")}
    middle = len(prices) // 2
    median = (prices[middle] if len(prices) % 2
              else (prices[middle - 1] + prices[middle]) / 2.0)
    return {"measurable": True, "price_cad": round(max(median, MIN_PRICE_CAD), 2),
            "observed": len(prices),
            "why": f"the median of {len(prices)} observed listing prices in this department"}


def hero_for(cir, twin):
    """A hero image rendered from the twin: this company's own arithmetic, made visible.

    Not a photograph. Photographic imagery waits on image_generation, and an asset claiming
    to be one is the thing asset truth exists to refuse.
    """
    from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance

    stitches = sorted({op.stitch for component in cir.components for row in component.rows
                       for op in _stitches(row.ops)})
    return Asset(
        asset_id=f"{cir.slug}-twin-hero",
        asset_class=AssetClass.DIGITAL_TWIN_RENDER,
        provenance=Provenance(source="twin", created_by="creative_director",
                              tool="digital_twin@1"),
        depicts_stitches=stitches,
        depicts_colors=sorted(cir.colors),
        is_hero=True,
        claims=Claims(materials=[m.name for m in cir.materials],
                      finished_width_cm=twin.width_cm,
                      finished_height_cm=twin.height_cm),
    )


def _stitches(ops):
    for op in ops:
        inner = getattr(op, "ops", None)
        if inner:
            yield from _stitches(inner)
        elif getattr(op, "stitch", None):
            yield op


def listing_for(concept, cir, price_cad: float):
    """Listing copy assembled from the concept's own fields.

    Deterministic on purpose. A model is permitted to write listing copy, but a tournament
    stage is not where to spend on one, and copy built from the concept cannot claim anything
    the concept does not say -- which is the failure mode the policy gate's proof check
    exists for one level up.
    """
    from ..gates.policy import ListingDraft

    object_name = concept.form.replace("_", " ")
    tags = list(dict.fromkeys(
        list(BASE_TAGS) + [object_name, concept.pod.replace("_", " ")]))[:13]
    return ListingDraft(
        title=f"{cir.title} | Crochet {object_name.title()} Pattern PDF"[:140],
        description=(
            f"{concept.premise} "
            f"Written instructions with stitch counts for every row, in US terms, with "
            f"charts. {concept.function.capitalize()}. "
            f"Drafted and checked with AI assistance and validated by an automated pattern "
            f"compiler before release."),
        tags=[t[:20] for t in tags],
        price_cad=price_cad,
    )


def release(db, concepts: list, *, benchmark_key: str = "") -> dict:
    """Stage five: present each survivor to the release chain and keep what it grants.

    Nothing here decides whether a pattern is good. The chain does, it is adversarial, and a
    refusal is the chain working rather than the stage failing.
    """
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..gates.certificate import certify
    from ..gates.platform_policy import policy_stamp
    from ..quality.physical import calibration_from_db
    from .prototype import PrototypeRefused, author

    survivors, killed, detail = [], {}, {}
    stamp = policy_stamp(db)
    for candidate in concepts:
        concept = getattr(candidate, "concept", candidate)
        try:
            cir = author(concept)
        except PrototypeRefused as e:
            killed[concept.key] = "unverifiable"
            detail[concept.key] = {"refused": str(e)[:300]}
            _mark(candidate, "unverifiable", str(e))
            continue

        result = compile_cir(cir)
        if not result.ok:
            killed[concept.key] = "unverifiable"
            detail[concept.key] = {"compile_errors": [str(f) for f in result.errors][:3]}
            _mark(candidate, "unverifiable", "; ".join(str(f) for f in result.errors))
            continue

        twin = build_twin(cir, result)
        price = observed_price(db, concept.pod, benchmark_key=benchmark_key)
        certificate = certify(
            cir,
            assets=[hero_for(cir, twin)],
            listing=listing_for(concept, cir, price["price_cad"]),
            calibration=calibration_from_db(db, cir),
            platform_policy=stamp,
        )
        detail[concept.key] = {
            "granted": certificate.granted,
            "stages_run": list(certificate.stages_run),
            "price_cad": price["price_cad"],
            "price_basis": price["why"],
            "physical_test_required": certificate.physical_test_required,
            "blocking": certificate.blocking_reasons[:3],
        }
        if not certificate.granted:
            killed[concept.key] = "unverifiable"
            _mark(candidate, "unverifiable",
                  "; ".join(certificate.blocking_reasons)[:400])
            continue
        survivors.append(candidate)

    return {
        "survivors": survivors,
        "killed": killed,
        "detail": detail,
        "assets": ("rendered from the digital twin, which is this company's own arithmetic "
                   "made visible. Photographic imagery waits on image_generation, and an "
                   "asset claiming to be a photograph is what asset truth refuses"),
        "note": ("The release chain decides this, not the stage. A refusal here is the chain "
                 "working: quality, asset truth and policy are adversarial by design, and a "
                 "tournament that certified its own survivors would be marking its own "
                 "homework (#3)."),
    }


def _mark(candidate, cause: str, why: str) -> None:
    if hasattr(candidate, "killed_by"):
        candidate.killed_by = cause
        candidate.detail = why[:400]
