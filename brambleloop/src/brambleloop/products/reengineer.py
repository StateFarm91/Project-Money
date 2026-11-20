"""Re-engineer worthy legacy products (F-114) -- W4-C07.

"Worthy concepts go through current yarn-band gauge derivation, compiler, twin, reverse
compiler and release chain."

Worthiness is not decided here. It is F-113's verdict: `creative.salvage.review` re-runs
today's creative, MJs-market, seasonal, novelty and portfolio gates and names a legacy product
`rescue_candidate` only when nothing fails and the creative verdict is known. `plan` refuses
anything else.

For a rescue candidate, deterministically and in this order:

1. **Yarn-band gauge.** The declared yarn weight's published single-crochet band
   (`publish.substitution`, Craft Yarn Council). A gauge inside the band is kept; one its own
   yarn cannot hold is replaced by `creative.prototype.gauge_for` (the middle of the band).
   A pattern whose gauge is not stated in single crochet cannot be placed in that band, so it
   is NEEDS_ENGINEER rather than converted by a guessed ratio. An unknown yarn weight is the
   same.
2. **Compiler.** `cir.compiler.compile_cir` must pass on the re-engineered CIR.
3. **Twin.** `cir.twin.build_twin`, whose finished size at the derived gauge is reported beside
   the legacy size, so the change a buyer would see is stated, not hidden.
4. **Reverse compiler.** The written US pattern (`cir.writer.write_pattern`) must reverse-
   compile (`cir.reverse.compare`) to the same CIR with no error finding.
5. **Release chain.** A new minor version is handed to `cir.compile`, which runs
   `gate.certify` and every gate a new product meets. Nothing here certifies: a plan is
   READY_FOR_RELEASE_CHAIN, and only the chain can make it a release.

No model is asked anything, and the legacy release is never modified.
"""
from __future__ import annotations

from dataclasses import replace

READY = "READY_FOR_RELEASE_CHAIN"


def _bump(version: str) -> str:
    parts = (str(version).split(".") + ["0", "0", "0"])[:3]
    major, minor = int(parts[0] or 0), int(parts[1] or 0)
    return f"{major}.{minor + 1}.0"


def _latest(db, slug: str):
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product

    with db.session() as s:
        row = s.execute(select(PatternVersion.version, PatternVersion.cir_json)
                        .join(Product, Product.id == PatternVersion.product_id)
                        .where(Product.slug == slug, PatternVersion.certified.is_(True))
                        .order_by(PatternVersion.id.desc())).first()
    return (row[0], row[1]) if row else (None, None)


def plan(db, slug: str, *, salvage: dict | None = None) -> dict:
    from ..cir.compiler import compile_cir
    from ..cir.model import CIR
    from ..cir.reverse import compare
    from ..cir.twin import build_twin
    from ..cir.writer import write_pattern
    from ..creative.prototype import gauge_for
    from ..publish.substitution import WEIGHT_BY_KEY, normalise

    if salvage is None:
        from ..creative.salvage import review

        salvage = next((r for r in review(db)["legacy"] if r["slug"] == slug), None)
    if not salvage or salvage.get("recommendation") != "rescue_candidate":
        return {"slug": slug, "state": "NOT_WORTHY",
                "why": (f"F-113 says {salvage.get('recommendation')!r}" if salvage else
                        "not a legacy product the salvage test reviewed")}
    version, cir_json = _latest(db, slug)
    if cir_json is None:
        return {"slug": slug, "state": "NO_RELEASE", "why": "no certified legacy release"}
    cir = CIR.from_dict(cir_json)
    weights = {normalise(m.yarn_weight) for m in cir.materials if m.yarn_weight}
    if len(weights) != 1 or "" in weights:
        return {"slug": slug, "state": "NEEDS_ENGINEER",
                "why": f"yarn weight(s) {sorted(m.yarn_weight for m in cir.materials)} do not "
                       f"name one standard weight, so there is no band to derive from"}
    weight = weights.pop()
    g = cir.gauge
    if g is None or g.stitch_type != "sc":
        return {"slug": slug, "state": "NEEDS_ENGINEER",
                "why": "the published band is a single-crochet gauge; this pattern's gauge is "
                       f"stated in {getattr(g, 'stitch_type', None)!r}, and a converted ratio "
                       f"would be a guess"}
    low, high = WEIGHT_BY_KEY[weight].sc_per_10cm
    in_band = low <= g.stitches_per_10cm <= high
    new_gauge = g if in_band else gauge_for(weight)
    new = replace(cir, gauge=new_gauge, version=_bump(version))
    result = compile_cir(new)
    checks = {"gauge": {"legacy_sc_per_10cm": g.stitches_per_10cm, "band": [low, high],
                        "kept" if in_band else "derived": new_gauge.stitches_per_10cm,
                        "basis": "publish.substitution yarn band (Craft Yarn Council)"},
              "compiler": {"ok": result.ok, "errors": [str(e) for e in result.errors][:10]}}
    if not result.ok:
        return {"slug": slug, "state": "REFUSED", "checks": checks,
                "why": "the re-engineered CIR does not compile"}
    old_twin, twin = build_twin(cir, compile_cir(cir)), build_twin(new, result)
    checks["twin"] = {"legacy_cm": [old_twin.width_cm, old_twin.height_cm],
                      "reengineered_cm": [twin.width_cm, twin.height_cm]}
    written = write_pattern(new, result, "US")
    errors = [f"{f.code}: {f.message}" for f in compare(new, written, "US") if f.is_error]
    checks["reverse"] = {"ok": not errors, "errors": errors[:10]}
    if errors:
        return {"slug": slug, "state": "REFUSED", "checks": checks,
                "why": "the written pattern does not reverse-compile to the CIR"}
    return {"slug": slug, "state": READY, "from_version": version, "version": new.version,
            "cir": new.to_dict(), "checks": checks,
            "next": "cir.compile -> gate.certify (every gate a new release meets)"}
