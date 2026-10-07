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
VERSION = "gallery-frames/1.1.0"

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
    "CONTENTS": ("the pattern PDF's pages; served by the pattern/PDF preview path "
                 "(publish.pdf), not by a drawing of the object"),
}

TITLE_PX = 64
BODY_PX = 50
SMALL_PX = 40


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


def facts(cir, job: str, *, siblings=None) -> dict:
    """What a frame of this job states, from the twin (the producer's path)."""
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


def _text(d, xy, text: str, px: int) -> int:
    d.text(xy, text, fill=K.CAPTION, font=K.font(px))
    return int(round(px * 1.35))


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
    w = d.textlength(K.DISCLOSURE, font=f)
    d.text((round((K.CANVAS_PX - w) / 2), round(K.CAPTION_TOP * K.CANVAS_PX)), K.DISCLOSURE,
           fill=K.CAPTION, font=f)


def _n(v) -> str:
    v = float(v)
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def draw(f: dict) -> bytes:
    """Pixels from facts alone. Both producer and verifier call this; they differ in facts."""
    img, d = _canvas()
    x0, y0, x1, y1 = K.zone_px(K.PRODUCT_ZONE)
    rgb = {k: K.hex_rgb(v) for k, v in f["colours"].items()}
    job = f["job"]
    if job == MATERIALS:
        y = y0
        y += _text(d, (x0, y), "Materials for this pattern", TITLE_PX) + 20
        used = f["colours_used"]
        # Chips sized to compose the card: at 1.0.0 they were 360 x 216 px and the card read
        # 95% background, which layout QA (FRAME_FLAT) rightly refuses for a gallery frame.
        chip_w = min(720, (x1 - x0 - 40 * (len(used) - 1)) / max(1, len(used)))
        chip_h = min(chip_w, 520)
        for i, col in enumerate(used):
            cx = x0 + i * (chip_w + 40)
            _chip(d, cx, y, chip_w, chip_h, rgb[col], cols=max(1, round(chip_w / 80)),
                  rows=max(1, round(chip_h / 80)))
            _text(d, (cx, y + chip_h + 14), col, BODY_PX)
        y += int(chip_h) + 14 + int(BODY_PX * 1.35) + 40
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
        for line in lines:
            y += _text(d, (x0, y), line, BODY_PX)
    elif job == COLOUR_CONTEXT:
        y = y0
        y += _text(d, (x0, y), "Colour share of the finished piece", TITLE_PX) + 30
        band_h = 360
        x = float(x0)
        width = x1 - x0
        for s in f["shares"]:
            w = width * s["stitches"] / f["total_stitches"]
            cols = max(1, int(round(w / 60)))
            _chip(d, x, y, w, band_h, rgb[s["colour"]], cols=cols, rows=6)
            x += w
        y += band_h + 40
        for s in f["shares"]:
            y += _text(d, (x0, y), f"{s['colour']}: {_n(s['percent'])}% of "
                                   f"{f['total_stitches']} stitches", BODY_PX)
        y += 20
        _text(d, (x0, y), "Counted from the pattern; on-screen colour varies by display",
              SMALL_PX)
    elif job == CONSTRUCTION:
        prof = f["profile"]
        y = y0
        how = "rounds" if f["construction"] != "flat_rows" else "rows"
        y += _text(d, (x0, y), f"How it is made: {len(prof)} {how}, stitch count per {how[:-1]}",
                   BODY_PX) + 20
        top, bottom = y, y1 - 2 * int(SMALL_PX * 1.35)
        most = max(p["stitches"] for p in prof)
        bar_h = (bottom - top) / len(prof)
        cx = (x0 + x1) / 2
        for k, p in enumerate(prof):        # round 1 at the bottom, as it is worked
            yb = bottom - (k + 1) * bar_h
            w = (x1 - x0) * p["stitches"] / most
            d.rectangle([round(cx - w / 2), round(yb), round(cx + w / 2) - 1,
                         round(yb + bar_h) - 1], fill=rgb[p["colour"]], outline=K.GAP,
                        width=1 if bar_h < 8 else K.GAP_PX)
        first, last = prof[0], prof[-1]
        y = bottom + 10
        y += _text(d, (x0, y), f"{how[:-1].capitalize()} 1: {first['stitches']} stitches; "
                               f"{how[:-1]} {last['row']}: {last['stitches']} stitches",
                   SMALL_PX)
        if f["make"] > 1:
            _text(d, (x0, y), f"Make {f['make']}", SMALL_PX)
    elif job == SIZING:
        outs = f["outlines"]
        y = y0
        y += _text(d, (x0, y), "Every size, drawn to one scale", TITLE_PX) + 30
        label_h = int(BODY_PX * 1.35) * 2
        gap = 60
        avail_w = (x1 - x0) - gap * (len(outs) - 1)
        avail_h = (y1 - y) - label_h
        px = min(avail_w / sum(o["width_cm"] for o in outs),
                 avail_h / max(o["height_cm"] for o in outs))
        ground = y + avail_h
        x = float(x0)
        main = next(iter(rgb.values()))
        for o in outs:
            w, h = o["width_cm"] * px, o["height_cm"] * px
            d.rectangle([round(x), round(ground - h), round(x + w) - 1, round(ground) - 1],
                        fill=main, outline=K.GAP, width=K.GAP_PX)
            _text(d, (round(x), round(ground) + 10), o["size"], BODY_PX)
            _text(d, (round(x), round(ground) + 10 + int(BODY_PX * 1.35)),
                  f"{_n(o['width_cm'])} x {_n(o['height_cm'])} cm", SMALL_PX)
            x += w + gap
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
    if cir.components and cir.components[0].construction != "flat_rows":
        jobs.append(CONSTRUCTION)
    if siblings:
        jobs.append(SIZING)
    return jobs


def render(cir, job: str, *, siblings=None) -> GalleryFrame:
    f = facts(cir, job, siblings=siblings)
    png = draw(f)
    manifest = {"kind": KIND, "version": VERSION, "job": job, "facts": f,
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
