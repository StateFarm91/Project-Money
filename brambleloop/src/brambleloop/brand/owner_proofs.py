"""Proof sheets and small-size measurements for the owner-concept identity (O1, D-FB-16).

    PYTHONPATH=src python -m brambleloop.brand.owner_proofs research/final_build/w3/evidence

Writes <= 6 small PNGs (A3_*.png) and A3_measurements.json. Every measurement uses the existing
procedure in `brand.comparison` (500 px icon, Lanczos down-sample, ink = RGB distance > 0.18
from the ground, WCAG contrast of each ink pixel against the ground), so the owner's raw concept
and the production micro-mark are measured identically. The raw concept is used only as
supplied (cropped + resampled), never traced or embedded in the repository.

Labels are set with the identity's own outlined Work Sans (no system font dependency).
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from . import comparison as C
from . import identity_system as I
from . import owner_identity as O
from . import typeset as T
from .vector import Fill, Mark, rasterize, to_png_bytes

SIZES = (40, 48, 70)
MAX_BYTES = 300_000


def _img(arr):
    from PIL import Image

    return Image.open(io.BytesIO(to_png_bytes(arr))).convert("RGB")


def render(kind: str, variant: str, width: int, *, ss: int = 3):
    d = I.direction()
    m = I._mark(I.DIRECTION_ID, kind, None)
    return _img(rasterize(m, d.colours(variant), width, ground=d.ground(variant), ss=ss))


def label(text: str, size: float, colour: str = "#2F3E33", ground: str = "#FFFFFF",
          font: str = "worksans"):
    text = "".join(ch for ch in text if T.has_glyphs(font, ch))  # e.g. '#' is not in the set
    w = T.measure(font, text, size) + 8
    met = T.font_metrics(font)
    h = (met["ascender"] - met["descender"]) * size / met["upm"] + 6
    m = Mark("label", w, h)
    m.add(Fill(T.set_text(font, text, size, 4, 3 + met["ascender"] * size / met["upm"]), "ink",
               "nonzero"))
    return _img(rasterize(m, {"ink": colour}, int(w), int(h), ground=ground, ss=2))


# ---- measurement ----------------------------------------------------------------------------


def candidates() -> list[C.Candidate]:
    out = [C.Candidate("O1", "O1 micro-mark (production)", "vector", I.DIRECTION_ID)]
    owner = [c for c in C.candidates() if c.key == "OWNER"]
    return out + owner


def small_metrics(c: C.Candidate, px: int) -> dict:
    """The comparison module's 40 px procedure, at `px`."""
    import numpy as np

    from .judge import _hex, ink_mask

    g = C.ground(c)
    lg = float(C._lum(np.array(_hex(g), np.float32)))
    a = np.asarray(C.small_icon(c, px)).astype(np.float32) / 255
    m = ink_mask(a, g)
    ink = C._lum(a)[m]
    if not ink.size:
        return {"px": px, "ink_coverage": 0.0, "ink_at_3to1_share": 0.0, "contrast_median": 0.0}
    ratios = (np.maximum(ink, lg) + 0.05) / (np.minimum(ink, lg) + 0.05)
    return {"px": px, "ink_coverage": round(float(m.mean()), 3),
            "ink_at_3to1_share": round(float((ratios >= 3.0).mean()), 3),
            "contrast_median": round(float(np.median(ratios)), 2)}


def measurements() -> dict:
    out = {"procedure": "brand.comparison: 500 px icon -> Lanczos to px; ink = RGB distance "
                        "> 0.18 from ground; WCAG ratio per ink pixel vs ground",
           "candidates": {}}
    for c in candidates():
        rec = {"label": c.label, "kind": c.kind,
               "sizes": {str(px): small_metrics(c, px) for px in SIZES}}
        full = C.measure(c)
        rec["comparison_measure"] = {k: v for k, v in full.items()
                                     if k not in ("label", "basis", "mono_basis")}
        out["candidates"][c.key] = rec
    return out


# ---- sheets ----------------------------------------------------------------------------------


def _sheet(w: int, h: int, colour: str = "#FFFFFF"):
    from PIL import Image

    return Image.new("RGB", (w, h), colour)


def sheet_micro_vs_concept(meas: dict):
    """Micro-mark vs the raw concept at 40/48/70 px (actual pixels, then 3x nearest)."""
    from PIL import Image

    cands = candidates()
    W, H = 1100, 120 + 260 * len(cands)
    im = _sheet(W, H)
    im.paste(label("Micro-mark vs raw owner concept at Etsy shop-icon sizes (actual px, then "
                   "shown 3x nearest-neighbour)", 22), (20, 16))
    y = 70
    for c in cands:
        im.paste(label(c.label, 22), (20, y))
        x = 20
        for px in SIZES:
            small = C.small_icon(c, px)
            im.paste(small, (x, y + 40))
            big = small.resize((px * 3, px * 3), Image.NEAREST)
            im.paste(big, (x + px + 12, y + 40))
            mt = meas["candidates"][c.key]["sizes"][str(px)]
            im.paste(label(f"{px}px  ink at 3:1+ {mt['ink_at_3to1_share']:.0%}  median "
                           f"{mt['contrast_median']:.2f}:1", 15), (x, y + 40 + px * 3 + 8))
            x += px * 4 + 90
        y += 260
    return im


def sheet_lockups_cream_forest():
    hero_c = render("lockup_stacked", "colour", 520)
    hero_r = render("lockup_stacked", "reversed", 520)
    W = 1120
    H = max(hero_c.size[1], hero_r.size[1]) + 120
    im = _sheet(W, H)
    im.paste(label("Hero lockup -- colour on cream / reversed on forest", 22), (20, 14))
    im.paste(hero_c, (20, 60))
    im.paste(hero_r, (580, 60))
    return im


def sheet_horizontal():
    rows = [("Horizontal lockup -- colour", render("lockup_horizontal", "colour", 900)),
            ("reversed", render("lockup_horizontal", "reversed", 900)),
            ("one-ink (mono)", render("lockup_horizontal", "mono", 900)),
            ("phone header size (36 px tall, actual pixels)", None),
            ("Wordmark", render("wordmark", "colour", 900))]
    from PIL import Image

    H = 40 + sum((r.size[1] if r is not None else 40) + 50 for _, r in rows)
    im = _sheet(940, H)
    y = 14
    for name, r in rows:
        im.paste(label(name, 18), (20, y))
        y += 32
        if r is None:
            h = render("lockup_horizontal", "colour", 900)
            s = 36 / h.size[1]
            im.paste(h.resize((int(h.size[0] * s), 36), Image.LANCZOS), (20, y))
            y += 54
        else:
            im.paste(r, (20, y))
            y += r.size[1] + 18
    return im


def sheet_marks_variants():
    W = 1120
    im = _sheet(W, 820)
    im.paste(label("Full monogram (160 px+) and micro-mark (40-96 px): colour / one-ink / "
                   "reversed", 20), (20, 14))
    x = 20
    for v in I.VARIANTS:
        mg = render("emblem", v, 340)
        im.paste(mg, (x, 56))
        x += 365
    x = 20
    y = 56 + render("emblem", "colour", 340).size[1] + 30
    for v in I.VARIANTS:
        ic = render("icon", v, 220)
        im.paste(ic, (x, y))
        x += 365
    return im.crop((0, 0, W, min(820, y + 240)))


def sheet_palette_type():
    from PIL import Image

    pal = I.PALETTE
    names = ["paper", "forest", "taupe", "rose", "rose_deep", "yarn", "yarn_deep", "leaf",
             "sage", "berry", "petal", "pollen"]
    W, H = 1120, 780
    im = _sheet(W, H)
    im.paste(label("Palette (sampled from the owner's concept) and type system", 22), (20, 14))
    for i, n in enumerate(names):
        x, y = 20 + (i % 6) * 180, 60 + (i // 6) * 150
        sw = Image.new("RGB", (160, 80), pal[n])
        im.paste(sw, (x, y))
        im.paste(label(n.replace("_", " "), 16), (x, y + 86))
        im.paste(label(pal[n], 14, "#5B5A4E"), (x, y + 108))
    y = 380
    specimens = [("cormorant_semibold", "BRAMBLELOOP", 44, "Wordmark / display -- Cormorant "
                  "Garamond SemiBold, caps +0.17em"),
                 ("worksans", "CROCHET PATTERNS", 22, "Descriptor / UI -- Work Sans, caps "
                  "+0.32em, taupe"),
                 ("allison", "Patterns for a More Handmade Life", 64, "Tagline -- Allison "
                  "(OFL), 32 px minimum"),
                 ("lora", "Warm clear pattern notes for every maker", 24, "Body -- Lora")]
    for font, text, size, note in specimens:
        im.paste(label(note, 14, "#5B5A4E"), (20, y))
        tr = 0.17 if font == "cormorant_semibold" else (0.32 if text.isupper() else 0.0)
        w = T.measure(font, text, size, tr) + 10
        met = T.font_metrics(font)
        h = (met["ascender"] - met["descender"]) * size / met["upm"] + 4
        m = Mark("s", w, h)
        m.add(Fill(T.set_text(font, text, size, 4, met["ascender"] * size / met["upm"],
                              tracking=tr), "ink", "nonzero"))
        col = pal["taupe"] if font == "worksans" else pal["forest"]
        im.paste(_img(rasterize(m, {"ink": col}, int(w), int(h), ground="#FFFFFF", ss=2)),
                 (20, y + 22))
        y += int(h) + 40
    return im.crop((0, 0, W, min(H, y + 10)))


def _clear_box(im, x, y, w, h, pad, colour=(166, 115, 114)):
    from PIL import ImageDraw

    dr = ImageDraw.Draw(im)
    dr.rectangle([x - pad, y - pad, x + w + pad, y + h + pad], outline=colour, width=2)
    dr.rectangle([x, y, x + w, y + h], outline=(180, 180, 170), width=1)


def sheet_clearspace_minsize():
    """Clear space (outer box) around each mark, and the minimum sizes at actual pixels."""
    from PIL import Image

    W, H = 1120, 760
    im = _sheet(W, H)
    im.paste(label("Clear space (rose box) and minimum sizes", 22), (20, 14))
    hero = render("lockup_stacked", "colour", 300)
    mg_cap = 0.5 * 300 * 0.42 * 0.56          # 0.5 x B cap (B cap = 56% of monogram width)
    pad = int(mg_cap)
    im.paste(hero, (20 + pad, 80 + pad))
    _clear_box(im, 20 + pad, 80 + pad, *hero.size, pad)
    im.paste(label("hero lockup: 0.5 B on all sides; 320 px wide minimum", 15),
             (20, 80 + hero.size[1] + 2 * pad + 10))
    hz = render("lockup_horizontal", "colour", 560)
    cap = int(hz.size[1] * 0.42)
    x0, y0 = 460 + cap, 80 + cap
    im.paste(hz, (x0, y0))
    _clear_box(im, x0, y0, *hz.size, cap)
    im.paste(label("horizontal lockup: 1 cap height; 28 px tall minimum", 15),
             (460, y0 + hz.size[1] + cap + 10))
    ic = render("icon", "colour", 200)
    x0, y0 = 460 + 25, 330 + 25
    im.paste(ic, (x0, y0))
    _clear_box(im, x0, y0, 200, 200, 25)
    im.paste(label("micro-mark: 1/8 of its square", 15), (460, 590))
    im.paste(label("micro-mark at 40 / 48 / 70 / 96 px (40 px minimum)", 15), (720, 370))
    x = 720
    for px in (40, 48, 70, 96):
        im.paste(render("icon", "colour", 500).resize((px, px), Image.LANCZOS), (x, 400))
        im.paste(label(f"{px}", 14), (x, 400 + px + 6))
        x += px + 30
    mg = render("emblem", "colour", 160)
    im.paste(mg, (720, 520))
    im.paste(label("monogram at its", 15), (720 + 170, 560))
    im.paste(label("160 px minimum", 15), (720 + 170, 582))
    return im


def build_all(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meas = measurements()
    sheets = {"A3_micro_vs_concept.png": sheet_micro_vs_concept(meas),
              "A3_lockups_cream_forest.png": sheet_lockups_cream_forest(),
              "A3_horizontal_wordmark.png": sheet_horizontal(),
              "A3_marks_variants.png": sheet_marks_variants(),
              "A3_palette_type.png": sheet_palette_type(),
              "A3_clearspace_minsize.png": sheet_clearspace_minsize()}
    written = {}
    for name, im in sheets.items():
        p = out_dir / name
        im.save(p, "PNG", optimize=True)
        if p.stat().st_size > MAX_BYTES:
            im.quantize(colors=128).save(p, "PNG", optimize=True)
        written[name] = p.stat().st_size
    (out_dir / "A3_measurements.json").write_text(json.dumps(meas, indent=1, sort_keys=True))
    return {"pngs": written, "measurements": meas}


if __name__ == "__main__":  # pragma: no cover
    res = build_all(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(json.dumps(res["pngs"], indent=1))
    for k, v in res["measurements"]["candidates"].items():
        print(k, v["sizes"])
