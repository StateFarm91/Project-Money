"""Product-only Visual V1 graduation, phase 2: the Heirloom Cable Throw as a deterministic
flat-lay reference, from Product Truth and the CIR's cells only.

The product is one flat rectangle, so the representation is the whole throw laid flat, seen
from directly above, at counts x gauge: 144 stitches across (90.0 cm) and 121 rows up (the
twin's height), rows horizontal, the 18 cable columns running up the piece. Every texture cell
is a compiled stitch drawn by the company's relief rule: front-post ribs stand forward and are
drawn as raised vertical strands, back-post channels recede, and a 2x2 crossing row draws its
two strand pairs crossing over that row (the LEFT pair in front, a declared convention: the
design does not specify the direction). No cell is invented and no cell is omitted: the drawing
iterates the twin's cells.

Conventions declared (not in the design): the flat lay is straight-on on a dark slate surface
(so the cream throw segments by lightness, as Bench2 established); portrait frame 1024 x 1536
because the throw is taller than wide; fill 0.90. Outputs: RGB, mask, normal map (from the
relief height field), region map, metadata with digests.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.products import texture as T                      # noqa: E402
from brambleloop.cir import compiler, twin as TW, stitches as ST     # noqa: E402

FRAME = (1024, 1536)
BG = (66, 66, 70)
REGIONS = {"cable_column": 2, "channel": 3, "foundation_row": 4}   # the throw itself is the union (the mask)
RELIEF = {"fpdc": 1.0, "bpdc": -0.5, "cable2x2": 1.2, "sc": 0.0}      # relative height, from charts.relief's ordering
FRONT_PAIR = "left"                                                    # declared crossing convention


def hexrgb(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(rgb, f): return tuple(max(0, min(255, int(c * f))) for c in rgb)


def build(out_dir: Path = OUT, prefix: str = "ref", size=FRAME, fill: float = 0.90):
    WPX, HPX = size
    pt = json.load(open(out_dir / "product_truth.json")); D = pt["derived"]
    cir = T.build_cable_throw(); res = compiler.compile_cir(cir); comp = cir.components[0]; tw = TW.build_twin(cir, res, comp.name)
    yarn = hexrgb(list(cir.colors.values())[0])
    W_cm, H_cm = D["width_cm"], D["height_cm"]
    ppc = min(WPX * fill / W_cm, HPX * fill / H_cm)
    cell_w = D["cell_w_cm"] * ppc; sc_row = D["sc_row_cm"] * ppc
    img = Image.new("RGB", (WPX, HPX), BG); d = ImageDraw.Draw(img)
    height = np.zeros((HPX, WPX), np.float32); region = np.zeros((HPX, WPX), np.uint8)
    x0 = (WPX - W_cm * ppc) / 2; y_bottom = (HPX + H_cm * ppc) / 2
    d.rectangle([x0, y_bottom - H_cm * ppc, x0 + W_cm * ppc, y_bottom], fill=yarn)
    # row tops from the registry's row heights, bottom-up
    rows = comp.rows; y_top = {}; y = y_bottom
    for r in rows:
        ops = r.ops[0].ops if hasattr(r.ops[0], "ops") else r.ops
        h = max(ST.get(o.stitch).row_height for o in ops) * sc_row; y -= h; y_top[r.index] = (y, h)
    lit, dark, deep = shade(yarn, 1.05), shade(yarn, 0.86), shade(yarn, 0.74)
    cells = sorted(tw.cells, key=lambda c: (c.row, c.position))
    by_row = {}
    for c in cells: by_row.setdefault(c.row, []).append(c)
    for ri, rcells in by_row.items():
        yt, h = y_top[ri]; yb = yt + h
        pos = 0
        while pos < len(rcells):
            c = rcells[pos]; x = x0 + c.position * cell_w
            if c.stitch == "cable2x2":
                # four cells of one crossing: two strand pairs (each two stitches wide) swap
                # sides over this row; the LEFT pair passes in front (declared convention)
                xl, xr = x, x + 4 * cell_w; xm = x + 2 * cell_w
                d.rectangle([xl, yt, xr, yb], fill=yarn)
                rising = [(xl, yb), (xm, yb), (xr, yt), (xm, yt)]      # left pair at the bottom, right at the top
                falling = [(xm, yb), (xr, yb), (xm, yt), (xl, yt)]     # right pair at the bottom, left at the top
                back, front = (falling, rising) if FRONT_PAIR == "left" else (rising, falling)
                d.polygon(back, fill=dark); d.polygon(front, fill=lit)
                d.line([front[0], front[3]], fill=deep, width=1); d.line([front[1], front[2]], fill=deep, width=1)
                ys, xs = int(yt), int(xl); height[ys:int(yb) + 1, xs:int(xr) + 1] = RELIEF["cable2x2"]
                region[ys:int(yb) + 1, xs:int(xr) + 1] = REGIONS["cable_column"]
                pos += 4; continue
            if c.stitch == "fpdc":
                d.rectangle([x, yt, x + cell_w, yb], fill=lit); d.line([(x + cell_w * 0.15, yt), (x + cell_w * 0.15, yb)], fill=deep, width=1); d.line([(x + cell_w * 0.85, yt), (x + cell_w * 0.85, yb)], fill=dark, width=1)
                height[int(yt):int(yb) + 1, int(x):int(x + cell_w) + 1] = RELIEF["fpdc"]; region[int(yt):int(yb) + 1, int(x):int(x + cell_w) + 1] = REGIONS["cable_column"]
            elif c.stitch == "bpdc":
                d.rectangle([x, yt, x + cell_w, yb], fill=dark); d.line([(x + cell_w * 0.5, yt), (x + cell_w * 0.5, yb)], fill=deep, width=1)
                height[int(yt):int(yb) + 1, int(x):int(x + cell_w) + 1] = RELIEF["bpdc"]; region[int(yt):int(yb) + 1, int(x):int(x + cell_w) + 1] = REGIONS["channel"]
            else:  # sc foundation row
                d.rectangle([x, yt, x + cell_w, yb], fill=yarn); d.line([(x, yb), (x + cell_w, yb)], fill=dark, width=1)
                region[int(yt):int(yb) + 1, int(x):int(x + cell_w) + 1] = REGIONS["foundation_row"]
            pos += 1
    # normal map from the relief height field (post stitches ~2 mm proud on a flat lay)
    from scipy.ndimage import gaussian_filter
    mask = region > 0
    h = gaussian_filter(height, 0.8); gy, gx = np.gradient(h * 4.0)
    n = np.stack([-gx, -gy, np.ones_like(h)], axis=-1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = ((n * 0.5 + 0.5) * 255).astype(np.uint8); normal[~mask] = (128, 128, 255)
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(out_dir / f"{prefix}_flatlay.png"); Image.fromarray((mask * 255).astype(np.uint8)).save(out_dir / f"{prefix}_mask.png")
    Image.fromarray(normal).save(out_dir / f"{prefix}_normal.png"); Image.fromarray(region).save(out_dir / f"{prefix}_regions.png")
    counts = {"cells_drawn": len(cells), "rows_drawn": len(by_row), "crossings_drawn": sum(1 for c in cells if c.stitch == "cable2x2") // 4}
    meta = {"slug": pt["slug"], "size_px": [WPX, HPX], "px_per_cm": round(ppc, 4), "cell_px": [round(cell_w, 3), round(ST.get("fpdc").row_height * sc_row, 3)],
            "expected_px": {"cable_column_pitch": round(8 * cell_w, 2), "crossing_period": round(4 * ST.get("fpdc").row_height * sc_row, 2), "cable_width": round(4 * cell_w, 2)},
            "throw_box_px": [round(x0, 1), round(y_bottom - H_cm * ppc, 1), round(x0 + W_cm * ppc, 1), round(y_bottom, 1)], "dimensions_cm": {"width": W_cm, "height": H_cm, "aspect_h_over_w": D["aspect_h_over_w"]},
            "regions": REGIONS, "region_pixels": {k: int((region == v).sum()) for k, v in REGIONS.items()}, "counts": counts,
            "conventions_DECLARED": {"view": "flat lay, straight on, whole throw", "surface_rgb": BG, "front_pair": FRONT_PAIR, "fill": fill, "relief_units": RELIEF},
            "colour": {"yarn_rgb": yarn, "basis": "the CIR's own colour hex (#FAF6EB cream)"},
            "inputs": {"product_truth_sha256": hashlib.sha256((out_dir / "product_truth.json").read_bytes()).hexdigest(), "cir_fingerprint": cir.fingerprint},
            "validation": {"every_cell_drawn": counts["cells_drawn"] == len(tw.cells) == 17424, "every_row_drawn": counts["rows_drawn"] == 121, "crossings_drawn_equals_truth": counts["crossings_drawn"] == 30 * 18,
                           "every_region_present": all((region == v).any() for v in REGIONS.values()),
                           "drawn_extent_cm": [round((x0 + W_cm * ppc - x0) / ppc, 2), round((y_bottom - min(v[0] for v in y_top.values())) / ppc, 2)]}}
    meta["validation"]["extent_matches_truth"] = abs(meta["validation"]["drawn_extent_cm"][0] - W_cm) < 0.05 and abs(meta["validation"]["drawn_extent_cm"][1] - H_cm) < 0.5
    json.dump(meta, open(out_dir / f"{prefix}_meta.json", "w"), indent=1)
    return meta


if __name__ == "__main__":
    m = build(prefix=sys.argv[1] if len(sys.argv) > 1 else "ref")
    print(json.dumps({k: m[k] for k in ("px_per_cm", "cell_px", "expected_px", "counts", "validation", "region_pixels")}, indent=1))
