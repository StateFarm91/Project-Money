"""Disclosed gallery frames beyond hero/scale/detail, derived only from the certified CIR.

K1 (F-030/F-254) made the gallery a set of *jobs* (`publish.eligibility.gallery_jobs_for`):
every listing answers DESIRE, CONTENTS, SCALE, MATERIALS and DETAIL, and a product category
adds ANGLE, CONSTRUCTION, COLOUR_CONTEXT, LIFESTYLE, FIT or SIZING. The disclosed renderer
(`visual.disclosed_render`) serves DESIRE, SCALE and DETAIL. This module serves the jobs a
deterministic drawing can answer *truthfully*, and only those:

  * MATERIALS -- the yarn colours drawn as stitch chips in the CIR's own colours, the yarn
    weight and fibre the CIR names, the hook size and the gauge. Yardage is lettered only
    when the CIR states it; an unstated amount is left off, never estimated here.
  * COLOUR_CONTEXT -- every yarn colour's share of the finished piece's stitches, counted
    from the compiled pattern and drawn as a proportional band of stitch tiles.
  * CONSTRUCTION -- (shaped/round work) the stitch-count profile: one bar per round or row,
    its length the stitch count, its colour that round's yarn, stacked in working order.
    A multi-piece product (W4-RENDER) gets one such profile per piece, lettered with the
    piece, its make, its row count and widest row, and the number of joins the CIR makes.
  * SIZING -- (a listing selling several sizes) every size's finished outline drawn to one
    common scale with its finished width and height.

What it does NOT serve, and why: LIFESTYLE (a scene a product lives in) and FIT (how a worn
item sits) are claims about the physical world that a drawing cannot evidence; they need a
photograph of a made sample or a gated, protected-product composite (`visual.compose`), so
they stay missing rather than being padded over. ANGLE for a vessel needs a new projection the
independent pixel verifier (`render_verification`) does not yet measure.

Verification (`verify`): the facts are recomputed by a *different* path from the one the
producer uses -- the producer counts the twin's cells, the verifier sums the compiler's row
stitch counts and reads gauge/materials straight off the CIR -- and the frame is redrawn from
the verifier's own facts. A frame passes only when the bytes are identical to that redraw and
the manifest's facts equal the verifier's, so a card can show nothing the CIR does not say.
Every frame carries `render_contract.DISCLOSURE` in its pixels, like every disclosed render.
"""
from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from . import render_contract as K

KIND = "disclosed_gallery_frame"
VERSION = "gallery-frames/2.0.0"   # contract 3: every lettered line legible where shown

MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING = (
    "MATERIALS", "COLOUR_CONTEXT", "CONSTRUCTION", "SIZING")
JOBS = (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION, SIZING)

# Jobs no drawing can answer truthfully, with what would.
NOT_DRAWABLE = {
    "LIFESTYLE": ("a room scene is a claim about a physical object in a place; it needs a "
                  "photograph of a made sample or a protected-product composite whose "
                  "background generation is paid (owner spend approval)"),
    "FIT": "a worn item's fit can only be evidenced by a photograph of it worn",
    "ANGLE": ("a further projection of the 3-D object that the independent pixel verifier "
              "(render_verification) does not yet measure; drawable once it does"),
    "CONTENTS": ("the pattern PDF's pages; not a drawing of the object. Served by "
                 "visual.contents_frame from the release's certified PDF at listing-set "
                 "certification (it needs the assets.built PDF on record)"),
}

# Owner ruling 2026-10-19 (D-W4-VISROLE-LEGIBILITY): the title reads at the 340 px grid
# (11 px needs 65 px here), every other line is essential text read in the 390 px phone
# gallery (57 px). 1.x set 64 / 50 / 40 px: 10.9, 9.8 and 7.8 px where shown. Lines that no
# longer fit wrap; nothing is shrunk below these.
TITLE_PX = 66
BODY_PX = K.TEXT_PX
SMALL_PX = K.TEXT_PX
LINE_H = int(round(K.TEXT_PX * 1.25))


class FrameRefused(ValueError):
    """The CIR does not carry what this job would have to letter, so nothing is drawn."""


@dataclass(frozen=True)
class GalleryFrame:
    job: str
    png: bytes
    manifest: dict


# --------------------------------------------------------------------------- facts

def _compiled(cir):
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    if len(cir.components) != 1:
        raise FrameRefused(f"{cir.slug}: {len(cir.components)} components; one is drawable")
    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile; nothing true to draw")
    return result, build_twin(cir, result, component=cir.components[0].name)


def _yarn(cir) -> dict:
    """Yarn facts read straight off the CIR. Fields the CIR leaves empty stay None."""
    mats = list(cir.materials or [])
    weights = sorted({m.yarn_weight for m in mats if m.yarn_weight})
    names = sorted({m.name for m in mats if m.name})
    metres = [m.metres_estimate for m in mats]
    g = cir.gauge
    return {
        "yarn_weight": weights[0] if len(weights) == 1 else None,
        "fibre": names[0] if len(names) == 1 else None,
        "metres_total": (round(sum(metres), 1) if metres and all(v is not None for v in metres)
                         else None),
        "hook_mm": g.hook_mm if g else None,
        "gauge": ({"stitches_per_10cm": g.stitches_per_10cm, "rows_per_10cm": g.rows_per_10cm,
                   "stitch": g.stitch_type} if g else None),
    }


def _shares(counts: dict[str, int]) -> list[dict]:
    total = sum(counts.values())
    order = sorted(counts, key=lambda c: (-counts[c], c))
    return [{"colour": c, "stitches": counts[c],
             "percent": round(100.0 * counts[c] / total, 1)} for c in order]


MULTI_PIECE_JOBS = (MATERIALS, COLOUR_CONTEXT, CONSTRUCTION)


def _multi_profiles_twins(cir) -> list[dict]:
    """W4-RENDER: every piece's stitch-count profile from its twin cells (producer's path)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile; nothing true to draw")
    out = []
    for comp in cir.components:
        rows: dict[int, list] = {}
        for cell in build_twin(cir, result, component=comp.name).cells:
            rows.setdefault(cell.row, []).append(cell)
        out.append({"piece": comp.name, "construction": comp.construction, "make": comp.make,
                    "profile": [{"row": r, "stitches": len(cs), "colour": cs[0].color}
                                for r, cs in sorted(rows.items())]})
    return out


def _multi_profiles_rows(cir) -> list[dict]:
    """The same from the compiler's row stitch counts (the verifier's path)."""
    from ..cir.compiler import compile_cir

    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile")
    out = []
    for comp in cir.components:
        colour_of = {r.index: r.color for r in comp.rows}
        rows = sorted((r for r in result.rows if r.component == comp.name),
                      key=lambda x: x.index)
        out.append({"piece": comp.name, "construction": comp.construction, "make": comp.make,
                    "profile": [{"row": r.index, "stitches": r.stitch_count,
                                 "colour": colour_of.get(r.index) or r.color} for r in rows]})
    return out


def _multi_counts_twins(cir) -> dict[str, int]:
    """W4-RENDER: a multi-piece product's stitches by colour, every piece times its `make`,
    counted from each piece's twin cells (the producer's path)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile; nothing true to draw")
    counts: dict[str, int] = {}
    for comp in cir.components:
        for cell in build_twin(cir, result, component=comp.name).cells:
            counts[cell.color] = counts.get(cell.color, 0) + comp.make
    return counts


def _multi_counts_rows(cir) -> dict[str, int]:
    """The same from the compiler's row stitch counts (the verifier's path)."""
    from ..cir.compiler import compile_cir

    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile")
    counts: dict[str, int] = {}
    for comp in cir.components:
        colour_of = {r.index: r.color for r in comp.rows}
        for r in result.rows:
            if r.component == comp.name:
                col = colour_of.get(r.index) or r.color
                counts[col] = counts.get(col, 0) + r.stitch_count * comp.make
    return counts


def _multi_facts(cir, job: str, counts: dict[str, int], profiles=None) -> dict:
    if job not in MULTI_PIECE_JOBS:
        raise FrameRefused(f"{cir.slug}: {job} is drawn for one piece; this product has "
                           f"{len(cir.components)}")
    base = {"job": job, "slug": cir.slug, "version": cir.version,
            "cir_fingerprint": cir.fingerprint, "colours": dict(cir.colors or {})}
    if job == MATERIALS:
        return base | {"yarn": _yarn(cir), "colours_used": sorted(c for c, n in counts.items()
                                                                  if n)}
    if job == CONSTRUCTION:
        # Every piece the pattern makes, each with its own stitch-count profile, and how many
        # joins the CIR's finishing makes between them.
        return base | {"construction": "pieces", "pieces": profiles,
                       "joins": len(cir.assembly or [])}
    return base | {"total_stitches": sum(counts.values()), "shares": _shares(counts)}


def facts(cir, job: str, *, siblings=None) -> dict:
    """What a frame of this job states, from the twin (the producer's path)."""
    if len(cir.components) > 1 and not siblings:
        if job == CONSTRUCTION:
            return _multi_facts(cir, job, {}, _multi_profiles_twins(cir))
        return _multi_facts(cir, job, _multi_counts_twins(cir))
    result, twin = _compiled(cir)
    base = {"job": job, "slug": cir.slug, "version": cir.version,
            "cir_fingerprint": cir.fingerprint, "colours": dict(cir.colors or {})}
    if job == MATERIALS:
        used = sorted({c.color for c in twin.cells})
        return base | {"yarn": _yarn(cir), "colours_used": used}
    if job == COLOUR_CONTEXT:
        counts: dict[str, int] = {}
        for cell in twin.cells:
            counts[cell.color] = counts.get(cell.color, 0) + 1
        return base | {"total_stitches": len(twin.cells), "shares": _shares(counts)}
    if job == CONSTRUCTION:
        comp = cir.components[0]
        rows = {}
        for cell in twin.cells:
            rows.setdefault(cell.row, []).append(cell)
        return base | {"construction": comp.construction, "make": comp.make,
                       "profile": [{"row": r, "stitches": len(cs), "colour": cs[0].color}
                                   for r, cs in sorted(rows.items())]}
    if job == SIZING:
        outlines = []
        for c in [cir, *(siblings or [])]:
            _r, t = _compiled(c)
            outlines.append({"slug": c.slug, "size": _size_word(c),
                             "width_cm": round(t.width_cm, 1), "height_cm": round(t.height_cm, 1)})
        outlines.sort(key=lambda o: (o["width_cm"] * o["height_cm"], o["slug"]))
        return base | {"outlines": outlines}
    raise FrameRefused(f"{job!r} is not a job this module draws: {JOBS}")


def independent_facts(cir, job: str, *, siblings=None) -> dict:
    """The same facts by another path: the compiler's row stitch counts, not the twin's cells.

    This is what `verify` redraws from. Kept separate on purpose: a counting slip in one path
    becomes a mismatch, not a confident wrong picture."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    if len(cir.components) > 1 and not siblings:
        if job == CONSTRUCTION:
            return _multi_facts(cir, job, {}, _multi_profiles_rows(cir))
        return _multi_facts(cir, job, _multi_counts_rows(cir))
    if len(cir.components) != 1:
        raise FrameRefused(f"{cir.slug}: {len(cir.components)} components; one is drawable")
    result = compile_cir(cir)
    if not result.ok:
        raise FrameRefused(f"{cir.slug} does not compile")
    comp = cir.components[0]
    rows = [r for r in result.rows if r.component == comp.name]
    colour_of = {r.index: r.color for r in comp.rows}
    base = {"job": job, "slug": cir.slug, "version": cir.version,
            "cir_fingerprint": cir.fingerprint, "colours": dict(cir.colors or {})}
    if job == MATERIALS:
        used = sorted({colour_of.get(r.index) or r.color for r in rows if r.stitch_count})
        return base | {"yarn": _yarn(cir), "colours_used": used}
    if job == COLOUR_CONTEXT:
        counts: dict[str, int] = {}
        for r in rows:
            col = colour_of.get(r.index) or r.color
            counts[col] = counts.get(col, 0) + r.stitch_count
        return base | {"total_stitches": sum(counts.values()), "shares": _shares(counts)}
    if job == CONSTRUCTION:
        return base | {"construction": comp.construction, "make": comp.make,
                       "profile": [{"row": r.index, "stitches": r.stitch_count,
                                    "colour": colour_of.get(r.index) or r.color}
                                   for r in sorted(rows, key=lambda x: x.index)]}
    if job == SIZING:
        outlines = []
        for c in [cir, *(siblings or [])]:
            res = compile_cir(c)
            t = build_twin(c, res, component=c.components[0].name)
            outlines.append({"slug": c.slug, "size": _size_word(c),
                             "width_cm": round(t.width_cm, 1), "height_cm": round(t.height_cm, 1)})
        outlines.sort(key=lambda o: (o["width_cm"] * o["height_cm"], o["slug"]))
        return base | {"outlines": outlines}
    raise FrameRefused(f"{job!r} is not a job this module draws: {JOBS}")


def _size_word(cir) -> str:
    for word in ("small", "medium", "large"):
        if cir.slug.endswith(f"-{word}"):
            return word.capitalize()
    return cir.slug


# --------------------------------------------------------------------------- drawing

def _canvas():
    img = Image.new("RGB", (K.CANVAS_PX, K.CANVAS_PX), K.BACKGROUND)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    return img, d


def _text(d, xy, text: str, px: int, *, max_w: float | None = None,
          slot: str = "row_value") -> int:
    """Letter `text` (wrapped to `max_w` when given) and record each line's box, size and
    slot on the draw (`d._bl_layout`) for the legibility measurement. Returns the height."""
    f = K.font(px)
    lines = K.wrap(text, px, max_w) if max_w else [text]
    step = int(round(px * 1.25))
    x, y = xy
    rec = getattr(d, "_bl_layout", None)
    for i, line in enumerate(lines):
        at = (x, y + i * step)
        d.text(at, line, fill=K.CAPTION, font=f)
        if rec is not None:
            rec.append({"kind": "text", "text": line, "pt": px, "slot": slot,
                        "box": list(d.textbbox(at, line, font=f))})
    return step * len(lines)


def _chip(d, x: float, y: float, w: float, h: float, rgb, *, cols: int, rows: int) -> None:
    """A patch of stitch tiles in one yarn colour."""
    cw, ch = w / cols, h / rows
    for i in range(rows):
        for j in range(cols):
            x0, y0 = x + j * cw, y + i * ch
            d.polygon([(x0, y0), (x0 + cw, y0), (x0 + cw, y0 + ch), (x0, y0 + ch)],
                      fill=rgb, outline=K.GAP, width=K.GAP_PX)


def _disclosure(d) -> None:
    f = K.font(K.CAPTION_PX)
    rec = getattr(d, "_bl_layout", None)
    for line, xy in K.caption_layout():
        d.text(xy, line, fill=K.CAPTION, font=f)
        if rec is not None:
            rec.append({"kind": "text", "text": line, "pt": K.CAPTION_PX,
                        "slot": "disclosure", "box": list(d.textbbox(xy, line, font=f))})


def _n(v) -> str:
    v = float(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def _draw_pieces(d, f: dict, rgb: dict, zone) -> None:
    """W4-RENDER: a multi-piece product's construction -- one small panel per piece, each its
    stitch-count profile (row/round 1 at the bottom, as worked), lettered with the piece, its
    make, its row count and its widest row's stitch count (each panel is drawn to its own
    widest row, so the lettered count is what says how the pieces compare)."""
    x0, y0, x1, y1 = zone
    pieces = f["pieces"]
    y = y0
    joins = f["joins"]
    y += _text(d, (x0, y), f"How it is made: {len(pieces)} pieces, {joins} "
                           f"join{'' if joins == 1 else 's'}", TITLE_PX, max_w=x1 - x0,
               slot="headline") + 20
    cols = math.ceil(math.sqrt(len(pieces) * (x1 - x0) / max(1, (y1 - y))))
    cols = max(1, min(len(pieces), cols))
    grid_rows = math.ceil(len(pieces) / cols)
    gap = 30
    cw = ((x1 - x0) - gap * (cols - 1)) / cols
    ch = ((y1 - y) - gap * (grid_rows - 1)) / grid_rows
    def labels(pc):
        prof = pc["profile"]
        how = "round" if pc["construction"] != "flat_rows" else "row"
        make = f" x{pc['make']}" if pc["make"] > 1 else ""
        n = len(prof)
        most = max(p["stitches"] for p in prof)
        return (f"{pc['piece']}{make}",
                f"{n} {how}{'' if n == 1 else 's'}, widest {most} sts")

    # Each panel's two labels wrap to the panel's width; every panel reserves the tallest.
    label_h = max(sum(len(K.wrap(t, SMALL_PX, cw)) for t in labels(pc)) for pc in pieces
                  ) * LINE_H
    for i, pc in enumerate(pieces):
        px0 = x0 + (i % cols) * (cw + gap)
        py0 = y + (i // cols) * (ch + gap)
        prof = pc["profile"]
        how = "round" if pc["construction"] != "flat_rows" else "row"
        n = len(prof)
        most = max(p["stitches"] for p in prof)
        make = f" x{pc['make']}" if pc["make"] > 1 else ""
        first, second = labels(pc)
        used = _text(d, (round(px0), round(py0)), first, SMALL_PX, max_w=cw,
                     slot="row_label")
        _text(d, (round(px0), round(py0) + used), second, SMALL_PX, max_w=cw)
        top, bottom = py0 + label_h + 6, py0 + ch
        bar_h = (bottom - top) / len(prof)
        cx = px0 + cw / 2
        for k, p in enumerate(prof):
            yb = bottom - (k + 1) * bar_h
            w = max(1.0, cw * p["stitches"] / most)
            d.rectangle([round(cx - w / 2), round(yb), round(cx + w / 2) - 1,
                         round(yb + bar_h) - 1], fill=rgb[p["colour"]], outline=K.GAP,
                        width=1 if bar_h < 8 else K.GAP_PX)


def draw(f: dict, layout: list | None = None) -> bytes:
    """Pixels from facts alone. Both producer and verifier call this; they differ in facts.

    `layout`, when given, receives every lettered line ({text, pt, slot, box}) so the frame's
    legibility can be measured from the record (`frame_role.legibility`); the bytes do not
    depend on it."""
    img, d = _canvas()
    d._bl_layout = layout
    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE)
    width = x1 - x0
    rgb = {k: K.hex_rgb(v) for k, v in f["colours"].items()}
    job = f["job"]

    def lines_h(texts, px=BODY_PX, max_w=width):
        return sum(len(K.wrap(t, px, max_w)) for t in texts) * int(round(px * 1.25))

    if job == MATERIALS:
        y = y0
        y += _text(d, (x0, y), "Materials for this pattern", TITLE_PX, max_w=width,
                   slot="headline") + 20
        used = f["colours_used"]
        yarn = f["yarn"]
        lines = []
        if yarn["yarn_weight"] or yarn["fibre"]:
            lines.append("Yarn: " + " ".join(v for v in (yarn["fibre"],) if v)
                         + (f" ({yarn['yarn_weight']} weight)" if yarn["yarn_weight"] else ""))
        if yarn["metres_total"] is not None:
            lines.append(f"About {_n(yarn['metres_total'])} m of yarn in total")
        if yarn["hook_mm"]:
            lines.append(f"Hook: {_n(yarn['hook_mm'])} mm")
        if yarn["gauge"]:
            g = yarn["gauge"]
            lines.append(f"Gauge: {_n(g['stitches_per_10cm'])} sts x {_n(g['rows_per_10cm'])} "
                         f"rows = 10 cm in {g['stitch']}")
        # Chips sized to compose the card: at 1.0.0 they were 360 x 216 px and the card read
        # 95% background, which layout QA (FRAME_FLAT) rightly refuses for a gallery frame.
        # 2.0.0: they give up height to the legible lines below them, never the reverse.
        chip_w = min(720, (width - 40 * (len(used) - 1)) / max(1, len(used)))
        names_h = max(lines_h([c], BODY_PX, chip_w) for c in used)
        chip_h = min(chip_w, 520, (y1 - y) - names_h - 14 - 40 - lines_h(lines))
        if chip_h < 120:
            raise FrameRefused("the materials card cannot letter its lines legibly and still "
                               "show the yarn chips")
        for i, col in enumerate(used):
            cx = x0 + i * (chip_w + 40)
            _chip(d, cx, y, chip_w, chip_h, rgb[col], cols=max(1, round(chip_w / 80)),
                  rows=max(1, round(chip_h / 80)))
            _text(d, (cx, y + chip_h + 14), col, BODY_PX, max_w=chip_w, slot="colour_name")
        y += int(chip_h) + 14 + names_h + 40
        for line in lines:
            y += _text(d, (x0, y), line, BODY_PX, max_w=width)
    elif job == COLOUR_CONTEXT:
        y = y0
        y += _text(d, (x0, y), "Colour share of the finished piece", TITLE_PX, max_w=width,
                   slot="headline") + 30
        shares = [f"{s['colour']}: {_n(s['percent'])}% of {f['total_stitches']} stitches"
                  for s in f["shares"]]
        note = "Counted from the pattern; on-screen colour varies by display"
        band_h = min(360, (y1 - y) - 40 - lines_h(shares) - 20 - lines_h([note], SMALL_PX))
        if band_h < 120:
            raise FrameRefused("the colour card cannot letter its lines legibly")
        x = float(x0)
        for s in f["shares"]:
            w = width * s["stitches"] / f["total_stitches"]
            cols = max(1, int(round(w / 60)))
            _chip(d, x, y, w, band_h, rgb[s["colour"]], cols=cols, rows=6)
            x += w
        y += band_h + 40
        for line in shares:
            y += _text(d, (x0, y), line, BODY_PX, max_w=width)
        y += 20
        _text(d, (x0, y), note, SMALL_PX, max_w=width, slot="caption")
    elif job == CONSTRUCTION and f.get("construction") == "pieces":
        _draw_pieces(d, f, rgb, (x0, y0, x1, y1))
    elif job == CONSTRUCTION:
        prof = f["profile"]
        y = y0
        how = "rounds" if f["construction"] != "flat_rows" else "rows"
        y += _text(d, (x0, y), f"How it is made: {len(prof)} {how}, stitch count per {how[:-1]}",
                   TITLE_PX, max_w=width, slot="headline") + 20
        first, last = prof[0], prof[-1]
        foot = [f"{how[:-1].capitalize()} 1: {first['stitches']} stitches; "
                f"{how[:-1]} {last['row']}: {last['stitches']} stitches"]
        if f["make"] > 1:
            foot.append(f"Make {f['make']}")
        top, bottom = y, y1 - lines_h(foot, SMALL_PX) - 10
        most = max(p["stitches"] for p in prof)
        bar_h = (bottom - top) / len(prof)
        cx = (x0 + x1) / 2
        for k, p in enumerate(prof):        # round 1 at the bottom, as it is worked
            yb = bottom - (k + 1) * bar_h
            w = (x1 - x0) * p["stitches"] / most
            d.rectangle([round(cx - w / 2), round(yb), round(cx + w / 2) - 1,
                         round(yb + bar_h) - 1], fill=rgb[p["colour"]], outline=K.GAP,
                        width=1 if bar_h < 8 else K.GAP_PX)
        y = bottom + 10
        for line in foot:
            y += _text(d, (x0, y), line, SMALL_PX, max_w=width)
    elif job == SIZING:
        outs = f["outlines"]
        y = y0
        y += _text(d, (x0, y), "Every size, drawn to one scale", TITLE_PX, max_w=width,
                   slot="headline") + 30
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        dims = [f"{_n(o['width_cm'])} x {_n(o['height_cm'])} cm" for o in outs]
        # Each outline's slot is at least as wide as its labels, so a small size's label
        # never runs into the next size (2.0.0: the labels are legible, hence wider).
        lab_w = [max(probe.textlength(o["size"], font=K.font(BODY_PX)),
                     probe.textlength(dm, font=K.font(SMALL_PX))) for o, dm in zip(outs, dims)]
        label_h = 2 * LINE_H
        gap = 60
        avail_h = (y1 - y) - label_h
        px = min((width - gap * (len(outs) - 1)) / sum(o["width_cm"] for o in outs),
                 avail_h / max(o["height_cm"] for o in outs))
        while px > 0.5 and (sum(max(o["width_cm"] * px, lw) for o, lw in zip(outs, lab_w))
                            + gap * (len(outs) - 1)) > width:
            px *= 0.97
        if sum(lab_w) + gap * (len(outs) - 1) > width:
            raise FrameRefused("the size labels do not fit side by side at a legible size")
        ground = y + avail_h
        x = float(x0)
        main = next(iter(rgb.values()))
        for o, dm, lw in zip(outs, dims, lab_w):
            w, h = o["width_cm"] * px, o["height_cm"] * px
            d.rectangle([round(x), round(ground - h), round(x + w) - 1, round(ground) - 1],
                        fill=main, outline=K.GAP, width=K.GAP_PX)
            _text(d, (round(x), round(ground) + 10), o["size"], BODY_PX, slot="row_label")
            _text(d, (round(x), round(ground) + 10 + LINE_H), dm, SMALL_PX,
                  slot="size_label")
            x += max(w, lw) + gap
    else:
        raise FrameRefused(f"{job!r} is not drawable")
    _disclosure(d)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=9)
    return buf.getvalue()


# --------------------------------------------------------------------------- public API

def applicable_jobs(cir, *, siblings=None) -> list[str]:
    jobs = [MATERIALS]
    if len(cir.colors or {}) > 1:
        jobs.append(COLOUR_CONTEXT)
    if (len(cir.components) == 1 and cir.components[0].construction != "flat_rows") or (
            len(cir.components) > 1 and not siblings):
        jobs.append(CONSTRUCTION)
    if siblings:
        jobs.append(SIZING)
    return jobs


def render(cir, job: str, *, siblings=None) -> GalleryFrame:
    f = facts(cir, job, siblings=siblings)
    layout: list = []
    png = draw(f, layout)
    manifest = {"kind": KIND, "version": VERSION, "job": job, "facts": f,
                "text_layout": layout,
                "slug": cir.slug, "cir_version": cir.version,
                "cir_fingerprint": cir.fingerprint,
                "siblings": [c.slug for c in (siblings or [])],
                "disclosure": K.DISCLOSURE,
                "image_sha256": hashlib.sha256(png).hexdigest(),
                "generated": False, "photograph": False, "model_in_path": False}
    return GalleryFrame(job=job, png=png, manifest=manifest)


def verify(png: bytes, cir, manifest: dict, *, siblings=None) -> dict:
    """PASS only when the bytes are exactly the redraw of independently recomputed facts."""
    failed, checks = [], {}
    job = manifest.get("job")
    if manifest.get("kind") != KIND or job not in JOBS:
        return {"status": "FAIL", "failed": ["not_a_gallery_frame"], "checks": {}}
    if manifest.get("cir_fingerprint") != cir.fingerprint:
        failed.append("cir_fingerprint")
    sha = hashlib.sha256(png).hexdigest()
    checks["bound"] = sha == manifest.get("image_sha256")
    try:
        mine = independent_facts(cir, job, siblings=siblings)
    except FrameRefused as exc:
        return {"status": "UNKNOWN", "failed": [], "unknown": [str(exc)], "checks": checks}
    checks["facts_agree"] = mine == manifest.get("facts")
    checks["pixels_are_the_facts"] = hashlib.sha256(draw(mine)).hexdigest() == sha
    img = Image.open(io.BytesIO(png)).convert("RGB")
    allowed = [K.BACKGROUND, K.GAP, *K.ANNOTATION_COLOURS.values(),
               *(K.hex_rgb(v) for v in (cir.colors or {}).values())]
    small = img.resize((200, 200), Image.NEAREST)
    off = sum(1 for p in small.getdata()
              if min(math.dist(p, a) for a in allowed) > K.OFF_PALETTE_DISTANCE)
    checks["on_palette"] = off / (200 * 200) <= K.MAX_OFF_PALETTE_SHARE
    failed += [k for k, ok in checks.items() if not ok]
    return {"status": "PASS" if not failed else "FAIL", "failed": failed, "unknown": [],
            "checks": checks, "verifier": VERSION}
