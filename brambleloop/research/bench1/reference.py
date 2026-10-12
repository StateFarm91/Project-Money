"""Commercial benchmark 1, phase 3: the finished product as a deterministic flat-lay reference.

Built from `out/product_truth.json` and the compiled CIR only. Every dimension is counts x
gauge; every texture cell is a stitch the compiler counted, drawn with its loop target's
ridge (visual.fabric's rule), with the grain the pattern dictates (rows vertical on the body
and the pockets, lengthwise on the sleeves, across the neckband). The layout is the pattern's
own assembly: fronts laid on the back and joined at the shoulders, the neckband along the
whole neckline, sleeves at the openings, cuffs gathered (slip-stitch rows are shorter than
half-double rows), pockets on the fronts at a DECLARED assumed placement.

Not beautiful, by design. It encodes the commercially material product: silhouette,
proportions, component placement, sleeve length, opening, bands, cuffs, pockets, texture
regions and colour placement. It outputs the RGB reference, its mask, a normal map from the
texture's height field, and a region map with a legend, for conditioning and for the gate.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.cir.model import CIR                    # noqa: E402
from brambleloop.cir import compiler, twin as T          # noqa: E402

SIZE = 1024
# The named colourway's appearance, sampled from the seller's photograph of it (lit median of
# the yarn region, seller photo 3): recorded as evidence about the colourway, not as pattern text.
YARN = (184, 128, 122); RIDGE = (150, 100, 96); INSIDE = (170, 116, 110); BG = (238, 236, 232)
REGIONS = {"back": 1, "front_left": 2, "front_right": 3, "hem_rib": 4, "neckband": 5, "sleeve_left": 6, "sleeve_right": 7, "cuff_left": 8, "cuff_right": 9, "pocket_left": 10, "pocket_right": 11, "back_neck_band": 12}
SLEEVE_ANGLE_DEG = 32.0   # sleeves laid out and down from the shoulders, a flat-lay convention
CUFF_WIDTH_FRACTION = 0.6  # the slip-stitch cuff gathers the sleeve end (rows B are slip stitch: 0.3 vs 1.5 stitch heights)
POCKET_ABOVE_RIB_CM = 5.0  # ASSUMED placement; the pattern leaves it to the maker


def twins():
    # rebuilt from the parse rather than read back from JSON: `CIR.from_dict` does not carry
    # a row's `skips`, so the armhole rows would fail to compile on the round trip (recorded)
    sys.path.insert(0, str(HERE)); import product_truth as PT
    cir = PT.build_cir(PT.parse())
    res = compiler.compile_cir(cir); assert res.ok, res.errors
    return cir, {c.name: T.build_twin(cir, res, c.name) for c in cir.components}


def cells_grid(tw):
    """rows x positions -> loop target ('both'/'front'/'back'), in fabric order."""
    rows = sorted({c.row for c in tw.cells}); grid = {}
    for c in tw.cells:
        grid[(c.row, getattr(c, "fabric_position", c.position))] = getattr(c, "loop", "both")
    return rows, grid


def paint_fabric(img, height, region, box, tw, orient, ppc, cm_st, cm_row, region_id, colour=YARN, rows_slice=None, pos_slice=None, cell_rows=None):
    """Draw a component's cells into `box` (x0,y0,x1,y1 px). orient 'rows_vertical': row index
    runs along x and stitch position along y (up); 'rows_horizontal': row index along y,
    position along x. Ridges: back-loop cells leave a bar at the stitch's lower edge, front-loop
    cells at its upper edge (visual.fabric._ridge)."""
    d = ImageDraw.Draw(img); rows, grid = cells_grid(tw)
    if rows_slice: rows = rows[rows_slice[0]:rows_slice[1]]
    x0, y0, x1, y1 = box; d.rectangle([x0, y0, x1, y1], fill=colour); region[int(y0):int(y1), int(x0):int(x1)] = region_id
    positions = sorted({p for (_, p) in grid});
    if pos_slice: positions = positions[pos_slice[0]:pos_slice[1]]
    # a component whose pattern says "repeat row 2 to the length" (the neckband) is tiled: its
    # last written row repeats for as long as the region is
    def row_at(ri): return rows[ri] if ri < len(rows) else rows[-1]
    if orient == "rows_vertical":
        cw, chh = cm_row * ppc, cm_st * ppc
        for ri in range(int((x1 - x0) / cw) + 1):
            r = row_at(ri); x = x0 + ri * cw
            if x + cw > x1 + 0.5: break
            for pi, p in enumerate(positions):
                y = y1 - (pi + 1) * chh
                if y < y0 - 0.5: break
                loop = grid.get((r, p), "both")
                # rows stack along x, so a stitch grows along x and the unworked loop lies along
                # the row direction (vertical): a bar at the stitch's base edge (toward the
                # previous row) for a back-loop stitch, at its far edge for a front-loop one
                if loop == "back": bar = (x + cw * 0.05, y, x + cw * 0.3, y + chh)
                elif loop == "front": bar = (x + cw * 0.7, y, x + cw * 0.95, y + chh)
                else: continue
                d.rectangle(bar, fill=RIDGE); height[int(bar[1]):int(bar[3]) + 1, int(bar[0]):int(bar[2]) + 1] = 1.0
    else:  # rows_horizontal: rows stack along y, stitches along x
        cw, chh = cm_st * ppc, cm_row * ppc
        for ri in range(int((y1 - y0) / chh) + 1):
            r = row_at(ri); y = y0 + ri * chh
            if y + chh > y1 + 0.5: break
            for pi, p in enumerate(positions):
                x = x0 + pi * cw
                if x + cw > x1 + 0.5: break
                loop = grid.get((r, p), "both")
                # rows stack along y: the unworked loop lies along the row (horizontal)
                if loop == "back": bar = (x, y + chh * 0.05, x + cw, y + chh * 0.3)
                elif loop == "front": bar = (x, y + chh * 0.7, x + cw, y + chh * 0.95)
                else: continue
                d.rectangle(bar, fill=RIDGE); height[int(bar[1]):int(bar[3]) + 1, int(bar[0]):int(bar[2]) + 1] = 1.0


def build(out_dir: Path = OUT, prefix: str = "ref", size=(SIZE, SIZE), angle_deg: float = SLEEVE_ANGLE_DEG, fill: float = 0.90):
    """`prefix` names the output set (ref_*, ref2_*); `size` is (width, height) px; `angle_deg`
    the sleeve angle; `fill` the fraction of the frame the garment's extent occupies. The
    geometry (cm) never changes between versions -- only the framing and the pixel scale."""
    WPX, HPX = size
    pt = json.load(open(out_dir / "product_truth.json")); D = pt["derived_cm"]
    cm_st, cm_row = D["cm_per_stitch"], D["cm_per_row"]
    L, FW, BW = D["body_length_cm"], D["front_panel_width_cm"], D["back_width_cm"]
    HEM, NB, BN = D["hem_rib_height_cm"], D["neckband_width_cm"], D["back_neck_width_cm"]
    SL, SW = D["sleeve_length_cm"], D["sleeve_folded_width_cm"]; CUFF = D["cuff_length_cm_at_hdc_gauge"]
    PW, PH = D["pocket_width_cm"], D["pocket_height_cm"]; SLIT = D["sleeve_opening_slit_cm"]
    cir, tw = twins()
    ang = math.radians(angle_deg)
    extent_w = BW + 2 * (SL * math.cos(ang) + SW * math.sin(ang)); extent_h = max(L, SL * math.sin(ang) + SW * math.cos(ang))
    ppc = min(WPX * fill / extent_w, HPX * fill / extent_h)
    img = Image.new("RGB", (WPX, HPX), BG); height = np.zeros((HPX, WPX), np.float32); region = np.zeros((HPX, WPX), np.uint8)
    d = ImageDraw.Draw(img)
    ox = (WPX - BW * ppc) / 2; oy = (HPX - extent_h * ppc) / 2
    X = lambda cm: ox + cm * ppc; Y = lambda cm: oy + (L - cm) * ppc   # cm from the hem, up
    boxes = {}
    # --- back panel (its inside faces up between the fronts) ---
    box = (X(0), Y(L), X(BW), Y(0)); paint_fabric(img, height, region, box, tw["body"], "rows_vertical", ppc, cm_st, cm_row, REGIONS["back"], colour=INSIDE, rows_slice=(20, 70)); boxes["back"] = box
    # --- fronts laid on the back, outer edges on the back's outer edges ---
    bl = (X(0), Y(L), X(FW), Y(0)); br = (X(BW - FW), Y(L), X(BW), Y(0))
    paint_fabric(img, height, region, bl, tw["body"], "rows_vertical", ppc, cm_st, cm_row, REGIONS["front_left"], rows_slice=(0, 20)); boxes["front_left"] = bl
    paint_fabric(img, height, region, br, tw["body"], "rows_vertical", ppc, cm_st, cm_row, REGIONS["front_right"], rows_slice=(70, 90)); boxes["front_right"] = br
    # hem rib: the first 10 stitches of every body row, so the bottom HEM cm of the fronts and the back read as rib (vertical ridges)
    for bx in (bl, br, (X(FW), Y(L), X(BW - FW), Y(0))):
        hb = (bx[0], Y(HEM), bx[2], Y(0)); region[int(hb[1]):int(hb[3]), int(hb[0]):int(hb[2])] = REGIONS["hem_rib"]
        boxes.setdefault("hem_rib", []).append(hb)
    # --- pockets on the fronts (ASSUMED placement, declared) ---
    for name, bx in (("pocket_left", bl), ("pocket_right", br)):
        cx = (bx[0] + bx[2]) / 2; pb = (cx - PW * ppc / 2, Y(HEM + POCKET_ABOVE_RIB_CM + PH), cx + PW * ppc / 2, Y(HEM + POCKET_ABOVE_RIB_CM))
        paint_fabric(img, height, region, pb, tw["pocket"], "rows_vertical", ppc, cm_st, cm_row, REGIONS[name]); boxes[name] = pb
        d.rectangle(pb, outline=RIDGE, width=2); d.line([(pb[0], pb[1]), (pb[2], pb[1])], fill=RIDGE, width=3)   # the slip-stitch top edge
    # --- neckband: up each front edge and across the back neck ---
    nbw = NB * ppc
    for name, bx, inner in (("neckband", bl, "right"), ("neckband", br, "left")):
        x_in = bx[2] if inner == "right" else bx[0]
        nb_box = (x_in, Y(L), x_in + nbw, Y(0)) if inner == "right" else (x_in - nbw, Y(L), x_in, Y(0))
        paint_fabric(img, height, region, nb_box, tw["neckband"], "rows_horizontal", ppc, cm_st, cm_row, REGIONS["neckband"], cell_rows=None); boxes.setdefault("neckband", []).append(nb_box)
    bn_box = (X(FW) + nbw, Y(L), X(BW - FW) - nbw, Y(L - NB))
    paint_fabric(img, height, region, bn_box, tw["neckband"], "rows_vertical", ppc, cm_st, cm_row, REGIONS["back_neck_band"]); boxes["back_neck_band"] = bn_box
    # --- sleeves: from the opening at the outer edge, out and down; cuff gathered at the far end ---
    def sleeve(side):
        sgn = -1 if side == "left" else 1; x_att = X(0) if side == "left" else X(BW)
        # attachment segment: the slit runs down from the top edge for SLIT cm; the folded sleeve top spans SW
        top = np.array([x_att, Y(L)]); bottom = np.array([x_att, Y(L - SW)])
        u = np.array([sgn * math.cos(ang), math.sin(ang)]) * ppc   # along the sleeve, in px per cm
        v = np.array([-sgn * math.sin(ang), math.cos(ang)]) * ppc   # across the sleeve
        body_len = SL - CUFF
        p0 = top; p1 = top + u * body_len; p2 = p1 + v * SW; p3 = top + v * SW
        poly = [tuple(p0), tuple(p1), tuple(p2), tuple(p3)]
        d.polygon(poly, fill=YARN)
        # ridges lengthwise (rows run along the sleeve): loop-target bars along u at each row's position across the sleeve
        rows, grid = cells_grid(tw["sleeve"]); positions = sorted({p for (_, p) in grid})
        n_rows = len(rows); row_pitch = SW / (n_rows / 2)   # the folded sleeve shows half the rows on this face
        # The sleeve's foundation chain runs its length and the cuff is the FIRST ten fabric
        # positions of every row (BLO slip stitches at one end), so fabric position 0 is the
        # wrist end. Reference versions ref and ref2 drew position 0 at the shoulder, which put
        # the cuff's dense back-loop bars at the upper sleeve: an invented "ribbed insert" that
        # the generator faithfully reproduced and the reader caught in round 3. Fixed in ref3:
        # positions run from the wrist, and the ten cuff positions fall under the cuff itself.
        for ri, r in enumerate(rows[: n_rows // 2]):
            for pi, p in enumerate(positions):
                along = SL - (pi + 1) * cm_st
                if along < 0 or along > body_len - cm_st: continue
                loop = grid.get((r, p), "both")
                if loop == "both": continue
                off = 0.7 if loop == "back" else 0.05
                a = top + u * along + v * ((ri + off) * row_pitch); b = a + u * cm_st + v * (0.25 * row_pitch)
                d.polygon([tuple(a), tuple(a + u * cm_st), tuple(b), tuple(a + v * (0.25 * row_pitch))], fill=RIDGE)
        # cuff: narrower, ribbed across
        c0 = p1 + v * (SW * (1 - CUFF_WIDTH_FRACTION) / 2); c1 = c0 + u * CUFF; c2 = c1 + v * (SW * CUFF_WIDTH_FRACTION); c3 = c0 + v * (SW * CUFF_WIDTH_FRACTION)
        d.polygon([tuple(c0), tuple(c1), tuple(c2), tuple(c3)], fill=YARN)
        for k in range(int(SW * CUFF_WIDTH_FRACTION / cm_row * 2)):
            a = c0 + v * (k * cm_row / 2); d.line([tuple(a), tuple(a + u * CUFF)], fill=RIDGE, width=1)
        return poly, [tuple(c0), tuple(c1), tuple(c2), tuple(c3)]
    for side in ("left", "right"):
        poly, cuff = sleeve(side)
        m = Image.new("L", (WPX, HPX), 0); ImageDraw.Draw(m).polygon(poly, fill=255); region[np.array(m) > 0] = REGIONS[f"sleeve_{side}"]
        m = Image.new("L", (WPX, HPX), 0); ImageDraw.Draw(m).polygon(cuff, fill=255); region[np.array(m) > 0] = REGIONS[f"cuff_{side}"]
        boxes[f"sleeve_{side}"] = poly; boxes[f"cuff_{side}"] = cuff
    # ridge height for the sleeves from the drawn ridge colour
    arr = np.array(img); ridge_px = (np.abs(arr.astype(int) - np.array(RIDGE)).sum(axis=2) < 12); height[ridge_px] = 1.0
    mask = region > 0
    # normal map from the height field (ridges ~1 mm high on a flat lay)
    from scipy.ndimage import gaussian_filter
    h = gaussian_filter(height, 0.8); gy, gx = np.gradient(h * 6.0)
    n = np.stack([-gx, -gy, np.ones_like(h)], axis=-1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = ((n * 0.5 + 0.5) * 255).astype(np.uint8); normal[~mask] = (128, 128, 255)
    img.save(out_dir / f"{prefix}_flatlay.png"); Image.fromarray((mask * 255).astype(np.uint8)).save(out_dir / f"{prefix}_mask.png")
    Image.fromarray(normal).save(out_dir / f"{prefix}_normal.png"); Image.fromarray(region).save(out_dir / f"{prefix}_regions.png")
    meta = {"size_px": [WPX, HPX], "px_per_cm": round(ppc, 4), "regions": REGIONS, "boxes_px": {k: (v if isinstance(v, list) else [round(float(x), 1) for x in v]) for k, v in boxes.items()},
            "layout": {"view": "flat lay, top-down, fronts laid on the back and joined at the shoulders, open at the centre", "sleeve_angle_deg": angle_deg, "fill": fill, "cuff_width_fraction": CUFF_WIDTH_FRACTION,
                       "pocket_placement_ASSUMED": {"centred_on_front": True, "above_hem_rib_cm": POCKET_ABOVE_RIB_CM}},
            "dimensions_cm": {k: D[k] for k in ("body_length_cm", "front_panel_width_cm", "back_width_cm", "hem_rib_height_cm", "neckband_width_cm", "back_neck_width_cm", "sleeve_length_cm", "sleeve_folded_width_cm", "cuff_length_cm_at_hdc_gauge", "pocket_width_cm", "pocket_height_cm", "sleeve_opening_slit_cm")},
            "colour": {"yarn_rgb": YARN, "basis": "named colourway 'Stonewash'; RGB sampled from the seller photograph of it (lit median), not from the pattern text"},
            "region_pixels": {k: int((region == v).sum()) for k, v in REGIONS.items()}, "cir_fingerprint": cir.fingerprint}
    json.dump(meta, open(out_dir / f"{prefix}_meta.json", "w"), indent=1)
    return meta


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "ref"
    if which == "ref3":
        # ref2's framing with the sleeve cuff end corrected (see the sleeve comment above)
        m = build(prefix="ref3", size=(1536, 1024), angle_deg=45.0, fill=0.92)
    elif which == "ref2":
        # v2 framing: landscape 1536x1024, sleeves at 45 degrees, 92 % fill -- the same garment at
        # about 1.6x the pixels per centimetre, so a stitch cell is legible to the generator
        m = build(prefix="ref2", size=(1536, 1024), angle_deg=45.0, fill=0.92)
    else:
        m = build()
    print({k: v for k, v in m["region_pixels"].items()}); print("px/cm", m["px_per_cm"], "cell px", round(m["px_per_cm"] * 10 / 14.5, 2), round(m["px_per_cm"] * 10 / 9.5, 2))
