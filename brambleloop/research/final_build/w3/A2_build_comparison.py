"""Lane A2: build the identity comparison boards (evidence/A2_*.png + A2_measurements.json).

    cd brambleloop && PYTHONPATH=src /home/user/Project-Money/brambleloop/.venv/bin/python \
        research/final_build/w3/A2_build_comparison.py [scratch_dir]

Needs the preinstalled Chromium (node + playwright, PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers)
for the storefront/banner/header shots; never installs anything; makes no network request
(A2_shoot.mjs aborts any non-file, non-data request). Every PNG is kept <= 300 KB.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from brambleloop.brand import comparison as C  # noqa: E402

EV = HERE / "evidence"
MAX_BYTES = 300_000
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PAGE = "#FFFFFF"          # marketplace page white, the ground the icon actually sits on
INK = "#1D1D1B"
FOOT = ("Lane A2 identity comparison, 2026-10-06. Owner decides; no recommendation. "
        "Not uploaded anywhere.")


def font(size: int, bold: bool = False):
    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()


def text(draw, xy, s, size=14, bold=False, fill=INK):
    draw.text(xy, s, font=font(size, bold), fill=fill)


def save(im: Image.Image, name: str) -> Path:
    out = EV / name
    im = im.convert("RGB")
    im.save(out, "PNG", optimize=True)
    if out.stat().st_size > MAX_BYTES:
        im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
            out, "PNG", optimize=True)
    s = 1.0
    while out.stat().st_size > MAX_BYTES and s > 0.4:
        s -= 0.1
        small = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
        small.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                       dither=Image.Dither.NONE).save(out, "PNG", optimize=True)
    assert out.stat().st_size <= MAX_BYTES, (name, out.stat().st_size)
    print("OK wrote", out.relative_to(ROOT), Image.open(out).size, out.stat().st_size)
    return out


def header(im: Image.Image, title: str, sub: str) -> ImageDraw.ImageDraw:
    d = ImageDraw.Draw(im)
    text(d, (20, 14), title, 22, True)
    text(d, (20, 44), sub, 13, fill="#555")
    text(d, (20, im.height - 22), FOOT, 11, fill="#777")
    return d


def circle(im: Image.Image, bg=PAGE) -> Image.Image:
    n = im.width
    big = Image.new("L", (n * 4, n * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, n * 4 - 1, n * 4 - 1), fill=255)
    out = Image.new("RGB", im.size, bg)
    out.paste(im, (0, 0), big.resize((n, n), Image.LANCZOS))
    return out


# ---- sheets -----------------------------------------------------------------------------------

def sheet_owner_reference():
    src = Image.open(C.owner_path()).convert("RGB")
    return save(src.resize((768, 512), Image.LANCZOS), "A2_0_owner_concept_as_supplied.png")


def sheet_icons(cs, meas):
    row, W = 190, 1240
    im = Image.new("RGB", (W, 90 + row * len(cs) + 40), PAGE)
    d = header(im, "Shop icon at Etsy display sizes (500 px upload, resampled)",
               "Columns: 40 px | 70 px | 40 px in a circle (a design margin; Etsy does not "
               "state a circle mask) | the 40 px icon magnified 4x so its pixels are visible")
    for i, c in enumerate(cs):
        y = 80 + i * row
        text(d, (20, y + 6), c.label, 16, True)
        if c.kind == "raster":
            text(d, (20, y + 28), "monogram cropped from the supplied raster", 11, fill="#555")
        s40, s70 = C.small_icon(c, 40), C.small_icon(c, 70)
        x = 20
        im.paste(s40, (x, y + 60)); x += 70
        im.paste(s70, (x, y + 45)); x += 100
        im.paste(circle(s40), (x, y + 60)); x += 70
        im.paste(s40.resize((160, 160), Image.NEAREST), (x, y + 20)); x += 190
        m = meas[c.key]
        lines = [f"ink pixels at 3:1 or more vs ground (40 px): {m['ink_at_3to1_share_40']:.0%}",
                 f"median-ink contrast at 40 px: {m['contrast_median_ink_40']}:1  "
                 f"(darkest ink {m['contrast_darkest_ink_40']}:1)",
                 f"detail retained 40 vs 160 px (edge corr.): {m['detail_retained_40']}",
                 f"stroke survival at 40 px: {m['stroke_survival_40']}",
                 f"ink outside inscribed circle: {m['ink_outside_circle']:.1%}"]
        for k, s in enumerate(lines):
            text(d, (x, y + 30 + k * 22), s, 13)
    return save(im, "A2_1_icon_small_sizes.png")


def sheet_header(cs, shots, meas):
    rows = []
    for c in cs:
        mob = Image.open(shots[c.key]["mhead"]).convert("RGB")
        desk = Image.open(shots[c.key]["dhead"]).convert("RGB")
        desk = desk.resize((round(desk.width * 0.62), round(desk.height * 0.62)), Image.LANCZOS)
        lk = C.fit(C.lockup_image(c, 1200, header=True), 280, 40)
        rows.append((c, mob, desk, lk))
    hrow = [max(m.height, d.height, 60) + 90 for _, m, d, _ in rows]
    W = 20 + 390 + 30 + max(d.width for _, _, d, _ in rows) + 20
    im = Image.new("RGB", (W, 90 + sum(hrow) + 30), PAGE)
    d = header(im, "Seller / store header scale",
               "Left: phone header from lane B's v2 storefront at 390 px (1:1). Right: desktop "
               "header at 1280 px, shown at 62%. Top right of each row: header lockup fitted "
               "in 280x40 px (1:1).")
    y = 80
    for (c, mob, desk, lk), h in zip(rows, hrow):
        text(d, (20, y), c.label, 15, True)
        lkbg = Image.new("RGB", (284, 44), C.ground(c))
        lkbg.paste(lk, ((284 - lk.width) // 2, (44 - lk.height) // 2))
        x2 = 20 + 390 + 30
        text(d, (x2 + 300, y + 30), f"280x40 lockup: wordmark letters {meas[c.key]['header_letter_px']} px"
             + (" (stacked crop; no horizontal lockup supplied)" if c.kind == "raster" else ""),
             12, fill="#555")
        im.paste(lkbg, (x2, y + 20))
        im.paste(mob, (20, y + 70))
        im.paste(desk, (x2, y + 70))
        y += h
    return save(im, "A2_2_header_scale.png")


def _grid(cs, shots, key, scale, cols, title, sub, name):
    tiles = []
    for c in cs:
        t = Image.open(shots[c.key][key]).convert("RGB")
        tiles.append((c, t.resize((round(t.width * scale), round(t.height * scale)),
                                  Image.LANCZOS)))
    tw, th = tiles[0][1].size
    rows = (len(tiles) + cols - 1) // cols
    im = Image.new("RGB", (20 + cols * (tw + 20), 80 + rows * (th + 40) + 30), PAGE)
    d = header(im, title, sub)
    for i, (c, t) in enumerate(tiles):
        x = 20 + (i % cols) * (tw + 20)
        y = 76 + (i // cols) * (th + 40)
        text(d, (x, y), c.label, 14, True)
        im.paste(t, (x, y + 22))
        ImageDraw.Draw(im).rectangle((x - 1, y + 21, x + tw, y + 22 + th), outline="#BBB")
    return save(im, name)


def sheet_mono(cs, meas):
    row, W = 200, 1240
    im = Image.new("RGB", (W, 90 + row * len(cs) + 40), PAGE)
    d = header(im, "Monochrome: one ink, black on cream and cream on forest",
               "Colour | black on cream 160 px | cream on forest 160 px | both at 40 px. Vectors: "
               "designed one-colour variant; owner raster: DERIVED luminance threshold.")
    for i, c in enumerate(cs):
        y = 80 + i * row
        text(d, (20, y), c.label, 15, True)
        x = 20
        y2 = y + 24
        im.paste(C.small_icon(c, 160), (x, y2)); x += 180
        bk = C.mono_image(c, 160, C.BLACK, C.CREAM)
        rv = C.mono_image(c, 160, C.CREAM, C.FOREST)
        im.paste(bk, (x, y2)); x += 180
        im.paste(rv, (x, y2)); x += 180
        im.paste(C.mono_image(c, 40, C.BLACK, C.CREAM), (x, y2 + 60)); x += 60
        im.paste(C.mono_image(c, 40, C.CREAM, C.FOREST), (x, y2 + 60)); x += 70
        m = meas[c.key]
        for k, s in enumerate([f"one-ink basis: {m['mono_basis']}",
                               f"colour ink still inked in one-ink version: {m['mono_ink_kept']:.0%}",
                               f"edge correlation colour vs one-ink at 70 px: "
                               f"{m['mono_edge_correlation_70']}"]):
            text(d, (x, y2 + 40 + k * 22), s, 12)
    return save(im, "A2_6_monochrome.png")


# ---- main -------------------------------------------------------------------------------------

def shoot(cs, tmp: Path) -> dict:
    jobs, shots = [], {}
    for c in cs:
        k = c.key
        paths = {}
        for vp, (w, h) in (("mobile", (390, 844)), ("desktop", (1280, 800))):
            p = tmp / f"{k}_{vp}.html"
            p.write_text(C.storefront_html(c, vp), encoding="utf-8")
            paths[vp[0] + "fold"] = str(tmp / f"{k}_{vp}.png")
            jobs.append({"html": str(p), "out": paths[vp[0] + "fold"], "w": w, "h": h})
            paths[vp[0] + "head"] = str(tmp / f"{k}_{vp}_head.png")
            jobs.append({"html": str(p), "out": paths[vp[0] + "head"], "w": w, "h": h,
                         "selector": "header.sh", "pad_top": 60})
        p = tmp / f"{k}_banner.html"
        p.write_text(C.banner_html(c), encoding="utf-8")
        paths["banner"] = str(tmp / f"{k}_banner.png")
        jobs.append({"html": str(p), "out": paths["banner"], "w": 1600, "h": 400})
        shots[k] = paths
    jf = tmp / "jobs.json"
    jf.write_text(json.dumps(jobs))
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH="/opt/pw-browsers")
    r = subprocess.run(["node", str(HERE / "A2_shoot.mjs"), str(jf)], capture_output=True,
                       text=True, env=env, timeout=600)
    print(r.stdout[-2000:], r.stderr[-2000:])
    if r.returncode != 0 or "BLOCKED_TOTAL 0" not in r.stdout:
        raise SystemExit("screenshot step failed or a page made a network request")
    for k, v in shots.items():
        b = Image.open(v["banner"])
        assert b.size == (1600, 400), b.size
    return shots


def main():
    scratch = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.gettempdir())
    tmp = Path(tempfile.mkdtemp(prefix="a2_", dir=scratch))
    EV.mkdir(parents=True, exist_ok=True)
    try:
        cs = C.candidates()
        if not any(c.kind == "raster" for c in cs):
            raise SystemExit("owner concept raster not found (sha256 must match)")
        rec = C.summary()
        meas = rec["measurements"]
        (EV / "A2_measurements.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
        sheet_owner_reference()
        sheet_icons(cs, meas)
        shots = shoot(cs, tmp)
        sheet_header(cs, shots, meas)
        _grid(cs, shots, "mfold", 0.72, 4, "Mobile storefront, first screen (390x844)",
              "Lane B's v2 storefront with each candidate's icon and banner lockup injected; "
              "layout, copy, palette and type held constant. Shown at 72%.",
              "A2_3_mobile_fold.png")
        _grid(cs, shots, "banner", 0.5, 1, "Shop banner at Etsy's recommended 1600x400",
              "Whole canvas at 50%. Laura: internal preview, not publication-approved.",
              "A2_4_banner_1600x400.png")
        _grid(cs, shots, "dfold", 0.45, 2, "Desktop storefront, first screen (1280x800)",
              "Same renderer at 1280 px, shown at 45%.", "A2_5_desktop_1280.png")
        sheet_mono(cs, meas)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
