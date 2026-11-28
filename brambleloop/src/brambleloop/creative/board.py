"""The concept board an expensive concept is gridded with before engineering (#126).

#126 renders "concept boards/thumbnails into a simulated Etsy-style grid" before CIR
engineering. The grid tournament and the pre-engineering gate existed; what nothing made was
the board, so `request_grid` never fired from the running system.

The board is made deterministically, without any image provider: the concept's own prototype
CIR (`creative.prototype.author`) is compiled, its digital twin is built, and the fabric is
drawn stitch by stitch in its own colours (`products.moment_candidates.board_png`) into a square thumbnail. It is a
`DIGITAL_TWIN_RENDER` -- the company's own arithmetic, never presented as a photograph -- and
it is exactly what a concept can honestly show before anybody has made it. A concept whose
form has no prototype geometry gets no board, with the prototype's own reason.
"""
from __future__ import annotations

import io

BOARD_PX = 570
KIND = "digital_twin_render"
# D5 (CATALOGUE-UNBLOCK, 2026-11-22): the prototype board used to be a top-left 40x40-stitch
# crop of the fabric drawn in `fabric_raster`'s default pink, whatever the concept's colours:
# a texture swatch with no outline, which no judge can read at grid size. Version 2 draws the
# whole piece in the CIR's own colours, letterboxed (never cropped), downscaled with Lanczos
# (`products.moment_candidates.board_png`). A board filed by an older renderer is re-drawn
# before its concept is judged again (`creative.intake.reboard_stale_radar`).
BOARD_RENDERER = "twin-board/2"


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
    from ..core.artifacts import ArtifactStore
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
        from ..products.moment_candidates import board_png

        image = Image.open(io.BytesIO(board_png(cir))).convert("RGB")
        if image.size != (BOARD_PX, BOARD_PX):
            image = image.resize((BOARD_PX, BOARD_PX), Image.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    stored = ArtifactStore().put(f"board/{concept.key}.png", buf.getvalue(), "image/png",
                                 db=db, keep="concept board for the #126 search-grid "
                                             "tournament")
    what = {"prototype": "the concept's prototype fabric",
            "catalogue_cir_disclosed_hero": "the product's verified disclosed hero"}[source]
    return {"board_image": f"artifact:{stored.sha256}", "sha256": stored.sha256,
            "kind": KIND, "slug": cir.slug, "source": source, "renderer": BOARD_RENDERER,
            **extra,
            "disclosure": (f"a deterministic render of {what} from its compiled digital "
                           f"twin, not a photograph")}


# ---- NEXT-FIXES #2: the board of a concept the prototype cannot size ------------------------
#
# Production 15:00Z (release 5297dbba): the concept gate held concepts at
# `board_missing/prototype_refused`. `radar.intake` admits a concept only into a family whose
# engine is verified end to end (`construction_families.route`): a ball-body bear or a lovey
# (form `toy`), a shawl or wrap (`draped_garment`), socks, slippers and baby dresses
# (wearable `fitted_garment`). But the board above was drawn from `creative.prototype.author`,
# which sizes flat and round forms only, so every one of those admitted concepts was refused a
# board, never judged, and waited at the gate forever while a pattern engine for it existed.
#
# This draws the board from the engine's OWN draft instead: the same inputs `radar.score`
# offers `cir.draft` (`toy_board.draft_inputs`), the same route, the same builder. The draft
# must compile; the fabric is drawn from its digital twin exactly as above. CA$0, no image
# provider. The stuffed-animal family keeps its own board route (`creative.toy_board`), and a
# family whose engine is not admitted gets no board (unknown never admits).
ENGINE_BOARD_SOURCE = "engine_draft"


# TOY-BOARD: why `engine_draft_cir` / `make_engine_board` drew no board, as one fixed code, so
# a `board_missing/engine_draft_refused` hold says which step refused (`engine_why`).
ENGINE_WHY_CODES = ("not_approved", "route_not_admitted", "engine_refused",
                    "audience_mismatch", "no_size", "stuffed_animal_route", "no_engine_board",
                    "engine_not_admitted", "not_compiling", "twin_undrawable", "other")


class EngineDraftRefused(ValueError):
    """No engine draft to draw for this concept, and why. Nothing was spent. `code` is one
    of ENGINE_WHY_CODES."""

    def __init__(self, message: str, code: str = "other"):
        super().__init__(message)
        self.code = code if code in ENGINE_WHY_CODES else "other"


def engine_draft_cir(db, slug: str, *, today=None):
    """(cir, family, compiled) as `cir.draft` will build them for an approved radar concept, compiled
    clean; or EngineDraftRefused naming why not."""
    from types import SimpleNamespace

    from ..cir.compiler import compile_cir
    from ..runtime.pipeline import Concept
    from . import baby
    from . import construction_families as CF
    from . import fallback_constructions as FC
    from . import homedecor as HD
    from .toy_board import draft_inputs

    i = draft_inputs(db, slug, today=today)
    if i is None:
        raise EngineDraftRefused("not an approved research concept", "not_approved")
    seed = i.pop("_seed")
    title, category = str(i.get("title") or ""), str(i.get("category") or "")
    form, construction = str(i.get("form") or ""), str(i.get("construction") or "")
    if CF.is_wearable(form, title):
        from ..products import wearables as WB

        route = CF.route(category=category, title=title, form=form,
                         construction=construction, slug=slug,
                         premise=str(i.get("premise") or ""))
        if not route["admitted"]:
            raise EngineDraftRefused(route["reason"][:240], "route_not_admitted")
        try:
            spec = WB.spec_for(SimpleNamespace(
                key=slug, title=title, form=form, category=category,
                construction=construction, premise=str(i.get("premise") or ""),
                notes=str(i.get("notes") or ""), recipient=str(i.get("recipient") or "self")))
            if spec.audience != route.get("audience"):
                raise EngineDraftRefused(f"the concept's recipient sizes it for {spec.audience} "
                                         f"but its title and category say {route.get('audience')}",
                                         "audience_mismatch")
            built = WB.build(spec)
        except (WB.WearableRefused, ValueError) as exc:
            code = getattr(exc, "code", None) or "engine_refused"
            raise EngineDraftRefused(f"the {route['family']} engine will not draft it: "
                                     f"{exc}"[:240], code) from None
        sizes = list(built.cirs)
        if not sizes:
            raise EngineDraftRefused(f"the {route['family']} engine drafted no size",
                                     "no_size")
        cir, family = built.cirs[sizes[len(sizes) // 2]], route["family"]
    else:
        concept = Concept(slug=i["slug"], title=i["title"], category=i["category"],
                          stitch_repeat=[(s, n) for s, n in i["stitch_repeat"]],
                          width_stitches=i["width_stitches"], rows=i["rows"],
                          colors=i["colors"], season=i.get("season"),
                          risk_class=i.get("risk_class", "A"))
        route = FC.plan(category=concept.category, title=concept.title,
                        is_bundle=bool(seed.is_bundle), slug=concept.slug,
                        rationale=seed.rationale or "")
        family = route["family"]
        builders = {FC.AMIGURUMI: FC.amigurumi, FC.LOVEY: baby.lovey,
                    FC.TRIANGLE: FC.triangle, FC.POUCH: FC.pouch, FC.TOTE: FC.tote,
                    FC.COSY: FC.cosy, FC.STOCKING: FC.stocking, FC.VESSEL: FC.vessel,
                    **{v: (lambda c, _v=v: HD.build(_v, c)) for v in HD.VARIANTS}}
        if family == FC.AMIGURUMI_ANIMAL:
            raise EngineDraftRefused("a stuffed animal's board is creative.toy_board's",
                                     "stuffed_animal_route")
        if family not in builders:
            raise EngineDraftRefused(f"no engine board for the {family!r} route: "
                                     f"{route.get('why') or ''}"[:240], "no_engine_board")
        if CF.status_of(family) not in CF.ADMITTED_STATUSES:
            raise EngineDraftRefused(f"the {family} engine is not admitted "
                                     f"({CF.status_of(family)})", "engine_not_admitted")
        try:
            cir = builders[family](concept)
        except (ValueError, KeyError) as exc:
            raise EngineDraftRefused(f"the {family} engine will not draft it: "
                                     f"{type(exc).__name__}: {exc}"[:240],
                                     "engine_refused") from None
    result = compile_cir(cir)
    if not result.ok:
        codes = sorted({f.code for f in result.findings if f.is_error})
        raise EngineDraftRefused(f"the engine's draft does not compile: {codes}"[:240],
                                 "not_compiling")
    return cir, family, result


def make_engine_board(db, slug: str, *, today=None) -> dict:
    """The board drawn from the engine's own draft (see above), in `make_board`'s shape."""
    from ..cir.twin import build_twin
    from ..core.artifacts import ArtifactStore
    from ..visual.render import fabric_raster

    try:
        cir, family, result = engine_draft_cir(db, slug, today=today)
    except EngineDraftRefused as exc:
        return {"board_image": None, "why": f"no engine draft to render: {exc}"[:300],
                "engine_why": exc.code}
    try:
        twin = build_twin(cir, result)
        image = fabric_raster(twin, cir.gauge, px_per_stitch=26, max_rows=40, max_cols=40,
                              seed=0, fibre=True)
    except Exception as exc:  # noqa: BLE001 - an undrawable twin is no board, never a crash
        return {"board_image": None,
                "why": f"the engine's draft could not be drawn ({type(exc).__name__})",
                "engine_why": "twin_undrawable"}
    side = min(image.size)
    image = image.crop((0, 0, side, side)).resize((BOARD_PX, BOARD_PX))
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    stored = ArtifactStore().put(f"board/{slug}-engine.png", buf.getvalue(), "image/png",
                                 db=db, keep="concept board drawn from the engine's draft")
    return {"board_image": f"artifact:{stored.sha256}", "sha256": stored.sha256,
            "kind": KIND, "slug": slug, "source": ENGINE_BOARD_SOURCE, "family": family,
            "disclosure": (f"a deterministic render of the {family} engine's draft fabric "
                           f"from its compiled digital twin, not a photograph")}
