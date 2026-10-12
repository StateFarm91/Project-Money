"""The free work that exists, built and certified like a product (#10, company half).

W4-B2CLOSE, 2026-10-10 (BUILD2_VERIFY finding 1). `growth.free_to_paid` was a complete
library planned over an empty list: `/api/free-to-paid` called `plan([])`, because no free
asset existed. This module is the company half of #10's split -- one real free asset, drafted
through the same deterministic chain as every product, and the plan read against it.

**Patterns are software releases, free ones included.** The asset is not a description of a
swatch; it is a CIR built by `products.builder.build` from a motif already in the library
(`diamond-lattice`, the motif of the Cloudline blanket and the placemat pair), at the gauge
its declared yarn holds (`creative.prototype.gauge_for`), in the Cloudline palette. It is
then put through `gates.certificate.certify` -- compile, specification, twin, assembly,
written pattern, independent reverse compile, originality -- and it counts as an asset only
while that certificate is granted. No new pattern content was invented: the motif grid, the
palette, the builder and the gate are all the ones the catalogue already uses.

**It is free work with a commercial job, checked, not asserted.** `free_to_paid.check_asset`
runs against the catalogue's paid slugs: the swatch leads to the Cloudline Textured Baby
Blanket and makes nothing the company sells.

**Nothing is published or sent.** The surface it would be placed on (an article on an owned
site) is the owner half of #10 and waits on `owned_surfaces`; the funnel stays empty and is
reported as empty. No consent is captured and no message goes to anybody (CASL), and the
phase stays SHADOW.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache

from .free_to_paid import FreeAsset, plan

# The released version of the free asset's content. Content may not change under it.
VERSION = "1.0.0"

SURFACE_GATE = "owned_surfaces"


@lru_cache(maxsize=1)
def _lattice_swatch_design():
    """Two lattice repeats across and two up, at worsted's own gauge, in Cloudline colours."""
    from ..creative.prototype import gauge_for
    from ..products.builder import Design, get

    gauge = gauge_for("worsted")
    motif = get("diamond-lattice")
    design = Design(
        slug="diamond-lattice-relief-swatch", title="Diamond Lattice Relief Swatch",
        motif=motif.slug, palette="cloudline", width_stitches=2 * motif.width,
        motif_repeats=2, yarn_weight="worsted",
        note=("A free practice swatch: the Cloudline blanket's lattice relief, double "
              "crochet standing above a single-crochet ground, worked at the blanket's "
              "gauge and in its colours."))
    return replace(design, stitches_per_10cm=gauge.stitches_per_10cm,
                   rows_per_10cm=gauge.rows_per_10cm, hook_mm=gauge.hook_mm)


# One entry per free asset: the asset's commercial job, and the builder of its CIR.
ASSETS: dict[str, FreeAsset] = {
    "diamond-lattice-relief-swatch": FreeAsset(
        key="diamond-lattice-relief-swatch", kind="motif", surface="article",
        teaches=("the lattice relief -- placing double crochet above a single-crochet ground "
                 "so a diamond stands out in texture -- and the worsted gauge it is worked at"),
        leads_to="cloudline-baby-blanket",
        # Not "the same rows": the blanket changes colour every two rows inside a border,
        # the swatch every row. What carries over is the motif, the relief and the gauge.
        why_next=("a maker who has finished the swatch has already worked the blanket's "
                  "lattice motif in relief at its gauge and in its colours, so the blanket "
                  "asks for a technique they have made rather than a new one"),
        makes="diamond-lattice-relief-swatch"),
}


def cir_for(key: str):
    """The free asset's CIR, built by the catalogue's own builder (never a catalogue design)."""
    from ..products.builder import build

    if key != "diamond-lattice-relief-swatch":
        raise KeyError(f"no free asset {key!r}; have {sorted(ASSETS)}")
    return build(_lattice_swatch_design(), VERSION, derive=False)


@lru_cache(maxsize=1)
def paid_slugs() -> tuple[str, ...]:
    """What this company sells, from the catalogue code: every flat design and every
    Launch-0 build's CIR slug. A free asset that makes one of these replaces it."""
    from ..products import builder, launch0

    slugs = set(builder.CATALOGUE)
    for key in launch0.BUILDERS:
        slugs.add(launch0.cir_for(key).slug)
    return tuple(sorted(slugs))


@lru_cache(maxsize=None)
def certificate(key: str) -> dict:
    """The release chain's verdict on one free asset, deterministic for its content."""
    from ..gates.certificate import certify

    cir = cir_for(key)
    cert = certify(cir)
    errors = [f"{f.code}: {f.message}" for f in cert.findings
              if str(getattr(f, "severity", "")).upper() == "ERROR"]
    twin = cert.twin_summary or {}
    return {"slug": cert.slug, "version": cert.version, "granted": bool(cert.granted),
            "content_hash": cert.content_hash, "release_hash": cert.release_hash,
            "stages_run": list(cert.stages_run), "errors": errors[:10],
            "size_statement": twin.get("size_statement"),
            "stitch_total": twin.get("stitch_total"),
            "yarn_metres": twin.get("yarn_metres"),
            "physical_test_passed": bool(cert.physical_test_passed),
            "confidence_weakest": (cert.confidence or {}).get("weakest")}


def real_assets() -> list[FreeAsset]:
    """The free assets that exist: built, and granted a certificate by the release chain."""
    return [a for k, a in ASSETS.items() if certificate(k)["granted"]]


def reading(*, extra_paid: tuple[str, ...] = ()) -> dict:
    """The free-to-paid plan over the free work that actually exists, and its state.

    `extra_paid` adds slugs the database knows are sold (the daily cadence passes its
    certified catalogue), so the replacement check reads the shop as well as the code.
    """
    paid = tuple(sorted(set(paid_slugs()) | set(extra_paid)))
    assets = real_assets()
    out = plan(assets, paid_slugs=paid)
    out["certificates"] = {k: certificate(k) for k in ASSETS}
    out["published"] = []
    out["publication"] = {
        "state": "unpublished (shadow)", "waits_on": SURFACE_GATE,
        "why": ("an article needs an owned site; the owner half of #10 "
                "(owner_queue owned_surfaces) has not opened one. Nothing is published, "
                "no email is captured and no message is sent (CASL)")}
    out["funnel_counts"] = "none measured: nothing is published, so no rung has a count"
    return out
