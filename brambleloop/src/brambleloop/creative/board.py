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


def make_board(db, concept) -> dict:
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin
    from ..core.artifacts import ArtifactStore
    from ..visual.render import fabric_raster
    from .prototype import PrototypeRefused, author

    try:
        cir = author(concept)
    except (PrototypeRefused, ValueError) as exc:
        return {"board_image": None, "why": f"no prototype to render: {exc}"[:300]}
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
    return {"board_image": f"artifact:{stored.sha256}", "sha256": stored.sha256,
            "kind": KIND, "slug": cir.slug,
            "disclosure": ("a deterministic render of the concept's prototype fabric from "
                           "its compiled digital twin, not a photograph")}
