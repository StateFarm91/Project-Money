"""The concept board an expensive concept is gridded with before engineering (#126).

#126 renders "concept boards/thumbnails into a simulated Etsy-style grid" before CIR
engineering. The grid tournament and the pre-engineering gate existed; what nothing made was
the board, so `request_grid` never fired from the running system.

The board is made deterministically, without any image provider: the concept's own prototype
CIR (`creative.prototype.author`) is compiled, its digital twin is built, and the fabric is
drawn stitch by stitch (`visual.render.fabric_raster`) into a square thumbnail. It is a
`DIGITAL_TWIN_RENDER` -- the company's own arithmetic, never presented as a photograph -- and
it is exactly what a concept can honestly show before anybody has made it. A concept whose
form has no prototype geometry gets no board, with the prototype's own reason.
"""
from __future__ import annotations

import io

BOARD_PX = 570
KIND = "digital_twin_render"


def _catalogue_cir(concept):
    """The product's own certified CIR when the concept is a catalogue design, else None.

    W4-VISUAL: a prototype is authored from the concept's form and size alone, so five
    different catalogue designs produced byte-identical boards (one plain throw for a
    graphghan, a mosaic throw, a runner, a wall hanging and a baby blanket). A taste
    judgement on such a board would judge none of them. A design that exists is drawn from
    its own CIR: its motif, its palette, its stitch counts."""
    try:
        from ..products.builder import for_slug

        return for_slug(getattr(concept, "key", "") or "")
    except Exception:  # noqa: BLE001 - no catalogue CIR is an answer, not a failure
        return None


def _disclosed_hero(cir):
    """The verified disclosed hero of a real CIR (PNG bytes, sha256), or (None, why)."""
    import hashlib

    from ..visual import disclosed_render as DR
    from ..visual import render_verification as RV

    try:
        frame = DR.render(cir, "hero")
    except DR.RenderRefused as exc:
        return None, str(exc)[:200]
    verdict = RV.verify(frame.png, cir=cir, view="hero")
    if verdict["status"] != "PASS":
        return None, f"the hero did not verify: {verdict['failed'] or verdict['unknown']}"
    return (frame.png, hashlib.sha256(frame.png).hexdigest()), ""


def make_board(db, concept) -> dict:
    from PIL import Image

    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..core.artifacts import ArtifactStore
    from ..visual.render import fabric_raster
    from .prototype import PrototypeRefused, author

    cir = _catalogue_cir(concept)
    source, extra = "prototype", {}
    if cir is not None:
        hero, why = _disclosed_hero(cir)
        if hero is not None:
            png, hero_sha = hero
            image = Image.open(io.BytesIO(png)).convert("RGB").resize(
                (BOARD_PX, BOARD_PX), Image.LANCZOS)
            source = "catalogue_cir_disclosed_hero"
            extra = {"from_verified_hero_sha256": hero_sha}
        else:
            # `fabric_raster` draws one yarn colour, so a fallback would show none of the
            # design's palette or motif: a board that does not depict the design is refused,
            # with the renderer's own reason, rather than judged.
            return {"board_image": None, "slug": cir.slug, "source": "catalogue_cir",
                    "why": f"the design's verified hero could not be drawn: {why}"[:300]}
    else:
        try:
            cir = author(concept)
        except (PrototypeRefused, ValueError) as exc:
            return {"board_image": None, "why": f"no prototype to render: {exc}"[:300]}
    if source == "prototype":
        result = compile_cir(cir)
        if not result.ok:
            return {"board_image": None,
                    "why": "the prototype does not compile, so there is no fabric to draw"}
        twin = build_twin(cir, result)
        image = fabric_raster(twin, cir.gauge, px_per_stitch=26, max_rows=40, max_cols=40,
                              seed=0, fibre=True)
        side = min(image.size)
        image = image.crop((0, 0, side, side)).resize((BOARD_PX, BOARD_PX))
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    stored = ArtifactStore().put(f"board/{concept.key}.png", buf.getvalue(), "image/png",
                                 db=db, keep="concept board for the #126 search-grid "
                                             "tournament")
    what = {"prototype": "the concept's prototype fabric",
            "catalogue_cir_disclosed_hero": "the product's verified disclosed hero"}[source]
    return {"board_image": f"artifact:{stored.sha256}", "sha256": stored.sha256,
            "kind": KIND, "slug": cir.slug, "source": source, **extra,
            "disclosure": (f"a deterministic render of {what} from its compiled digital "
                           f"twin, not a photograph")}
