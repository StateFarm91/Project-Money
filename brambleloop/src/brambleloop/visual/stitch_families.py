"""F-759: the distinctive-stitch benchmark set, as a registry.

Some stitches are read by a buyer as the fabric's identity rather than as a texture: the star
family's lattice of eyes, a cluster's raised bobble, a cable's crossing, a post stitch's
relief. A disclosed render draws one glyph per compiled stitch, and the pixel verifier
counts the glyphs and checks their positions and colours. Neither one proves that what is
drawn reads as that family. So a family is **supported** (an image of it may be certified)
only when an instrument exists for it and every fixture in its benchmark set behaves:
* its positive truth fixture passes the instrument;
* every negative fixture (a wrong texture that a lazy instrument would wave through) is
  rejected.
The benchmark set is maintained here per family and re-run (`support`). The thresholds
belong to the instrument (`visual.stitch_identity` BARS); nothing here moves them.

A CIR that uses a distinctive family with no supported instrument is refused by the disclosed
renderer (`disclosed_render.render` -> `refusal`). A drawing of a stitch family nobody can
verify is a claim about the fabric, so the render is refused and no frame is shipped
unverified. Basic stitches worked into the top of the row below (sc, hdc, dc, inc, slst, ...)
are not distinctive and pass through unchanged.
"""
from __future__ import annotations

from functools import lru_cache

# `cir.stitches.Anatomy.placement` -> distinctive family.
FAMILY_OF_PLACEMENT: dict[str, str] = {
    "star": "star",
    "cluster": "cluster",          # bobble, puff, popcorn
    "crossed": "cable",
    "post_front": "post_relief",
    "post_back": "post_relief",
}

# Star fixtures, at the instrument's own selftest scale.
_STAR_PX, _PAIR_PX, _W, _H = 24.0, 43.0, 480, 400


def _star_fixtures() -> dict:
    import numpy as np

    from . import stitch_identity as S

    def g(img):
        return np.array(img.convert("L")).astype(float)

    return {
        "positive": {
            "truth_star": g(S.draw_star_fabric(_W, _H, _STAR_PX, _PAIR_PX)),
            "truth_star_phase": g(S.draw_star_fabric(_W, _H, _STAR_PX, _PAIR_PX, phase=0.37)),
        },
        "negative": {
            "star_at_twice_the_gauge": g(S.draw_star_fabric(_W, _H, 2 * _STAR_PX, 2 * _PAIR_PX)),
            "checker_half_star_offset": g(S.draw_star_fabric(_W, _H, _STAR_PX, _PAIR_PX,
                                                             column_offset=0.5)),
            "hdc_rows": g(S.draw_hdc_fabric(_W, _H, _STAR_PX / 2, _PAIR_PX / 2)),
            "seed_stitch": g(S.draw_seed_fabric(_W, _H, _STAR_PX / 2, _PAIR_PX / 2)),
            "stockinette_knit": g(S.draw_knit_fabric(_W, _H, _STAR_PX / 2, _PAIR_PX / 2)),
        },
    }


def _star_instrument(gray) -> str:
    from . import stitch_identity as S

    return str(S.diagnose(gray, family="star", star_px_expected=_STAR_PX,
                          pair_px_expected=_PAIR_PX, flat_region=True).get("status"))


# family -> (instrument(gray) -> status, fixtures() -> {"positive": {...}, "negative": {...}})
REGISTRY: dict[str, tuple] = {
    "star": (_star_instrument, _star_fixtures),
    "cluster": (None, None),
    "cable": (None, None),
    "post_relief": (None, None),
}


@lru_cache(maxsize=None)
def support(family: str) -> dict:
    """Run the family's benchmark set. Supported only when every fixture behaves."""
    instrument, fixtures = REGISTRY.get(family, (None, None))
    if instrument is None or fixtures is None:
        return {"family": family, "supported": False, "results": {},
                "why": "no instrument and benchmark set exist for this family"}
    try:
        sets = fixtures()
    except Exception as exc:  # noqa: BLE001 - an unbuildable benchmark supports nothing
        return {"family": family, "supported": False, "results": {},
                "why": f"benchmark set could not be built: {type(exc).__name__}: {exc}"[:200]}
    results: dict[str, dict] = {}
    for kind in ("positive", "negative"):
        for name, gray in (sets.get(kind) or {}).items():
            status = instrument(gray)
            ok = status == "PASS" if kind == "positive" else status != "PASS"
            results[name] = {"kind": kind, "status": status, "behaves": ok}
    positives = [r for r in results.values() if r["kind"] == "positive"]
    negatives = [r for r in results.values() if r["kind"] == "negative"]
    supported = bool(positives) and bool(negatives) and all(r["behaves"]
                                                            for r in results.values())
    return {"family": family, "supported": supported, "results": results,
            "why": ("every positive passes and every negative is rejected" if supported else
                    "a fixture misbehaved: " + ", ".join(n for n, r in results.items()
                                                          if not r["behaves"])
                    if results else "the benchmark set is empty")}


def families_in(cir) -> dict[str, list[str]]:
    """The distinctive families a CIR's compiled stitches use, with the codes that use them."""
    from ..cir import stitches as ST
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    twin = build_twin(cir, compile_cir(cir))
    out: dict[str, set[str]] = {}
    for code in {c.stitch for c in twin.cells}:
        try:
            a = ST.anatomy(code)
        except Exception:  # noqa: BLE001 - an unknown code is the compiler's error, not ours
            a = None
        fam = FAMILY_OF_PLACEMENT.get(getattr(a, "placement", "") or "")
        if fam:
            out.setdefault(fam, set()).add(code)
    return {k: sorted(v) for k, v in sorted(out.items())}


def refusal(cir) -> str | None:
    """Why a render of this CIR may not be certified, or None when every family is supported."""
    used = families_in(cir)
    bad = {f: codes for f, codes in used.items() if not support(f)["supported"]}
    if not bad:
        return None
    return (f"{cir.slug} uses distinctive stitch famil{'y' if len(bad) == 1 else 'ies'} "
            f"{bad} with no verified instrument (F-759); a drawing of a stitch nobody can "
            f"verify would be an unverified claim about the fabric")


def registry_status() -> dict:
    return {f: {k: v for k, v in support(f).items() if k != "results"} for f in REGISTRY}
