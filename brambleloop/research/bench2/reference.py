"""Commercial benchmark 2, phase 4: the finished Mini Star Stitch Cardigan as a deterministic
flat-lay reference, at the frozen benchmark size (2-3T), from Product Truth only.

Construction the pattern makes (p4, p7-12): one piece, bottom-up. A sc-blo back band (ribbing,
rows perpendicular to the hem), the back body in star stitch, then sleeve chains added at both
sides so the yoke rows run the whole wingspan (the sleeves are built in); a neck opening left
at the shoulder row; two fronts worked down from the shoulder with their own sleeve halves,
increasing at the neck edge (the front neck slopes from the opening width at the shoulder to
the band at the underarm); the front panels down to the hem; a hood worked up from the
neckline, folded and seamed across the top; sc-blo cuffs and a sc-blo collar band joined
along the whole front/hood edge, buttonholes on the right front, buttons sewn on the left.

Laid out here as the designer's own flat lay shows it: front up, buttoned, hood spread flat
above the shoulders, sleeves angled down from the shoulders. Every dimension is Product
Truth's derived centimetres times one pixel scale; every fabric region carries the star
texture at the pattern's gauge (star pitch 1.13 cm, row pair 2.03 cm), drawn by the same
deterministic model the identity instrument was self-tested on, rows horizontal on body and
hood and along the sleeve on the sleeves; bands and cuffs carry sc-blo ridges perpendicular to
their edge. Outputs: RGB, mask, normal map, region map with legend, metadata.

Conventions declared (not in the pattern text): sleeve angle 32 degrees below the shoulder
line (flat-lay convention, as Bench1); the hood spread open behind the neck with its top
seam drawn as a short centre line; the centre gap between the closed fronts drawn as the
back width minus two front widths (3.3 cm) and read as the overlapped button band (7 sts of
sc-blo = 3.6 cm); five buttons evenly spaced from just above the hem band to the neck point;
the cuff gathered to 0.5 of the sleeve face (24 sc-blo sts = 12.2 cm round, a 6.1 cm face);
yarn colour Oat Milk as sampled from the designer's photograph (lit median, declared).
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; OUT = HERE / "out"
sys.path.insert(0, str(HERE))
import star_identity as SI   # noqa: E402

SIZE_NAME = "2-3T"
FRAME = (1536, 1024)
YARN = (236, 224, 212); SHADE = (198, 184, 168); DARK = (152, 138, 122); INSIDE = (222, 210, 198)
BUTTON = (122, 84, 52); BUTTON_RIM = (96, 64, 38); BG = (66, 66, 70)   # dark slate surface: the cream garment segments by lightness
REGIONS = {"back_inside": 1, "front_left": 2, "front_right": 3, "hem_band": 4, "button_band": 5, "neck_band": 6, "sleeve_left": 7, "sleeve_right": 8,
           "cuff_left": 9, "cuff_right": 10, "hood": 11, "hood_band": 12, "button": 13}
SLEEVE_ANGLE_DEG = 32.0; CUFF_FACE_FRACTION = 0.5; BUTTONS = 5; BUTTON_MM = 19.0
ROW_CM = 4 * 2.54 / 10.0; RIB_ROW_CM = 2 * 2.54 / 10.0; RIB_ST_CM = 2 * 2.54 / 10.0


def truth(size=SIZE_NAME):
    pt = json.load(open(OUT / "product_truth.json"))
    row = next(r for r in pt["derived"]["per_size"] if r["size"] == size)
    return pt, row


def geometry(row):
    """All in cm. Origin: centre of the hem edge, y up."""
    c = row["cm"]
    g = {"BW": c["back_width"], "FW": c["front_width"], "HEM": c["hem_band"], "BACK_BODY": c["underarm_to_hem"], "FRONT_BODY": row["front_panel_rows"] * ROW_CM,
         "YOKE_HALF": c["sleeve_width"] / 2, "SL": c["sleeve_length"], "CUFF": c["cuff"], "NECK": c["neck_opening"], "HOODW": c["hood_width"], "HOODH": c["hood_height"],
         "STAR": c["star_pitch"], "PAIR": c["row_pair_pitch"], "BAND": row["collar_sts"] * RIB_ST_CM, "SLEEVE_FACE": c["sleeve_width"] / 2}
    g["GAP"] = g["BW"] - 2 * g["FW"]                      # the closed fronts' centre strip (overlapped bands)
    g["UNDERARM_Y"] = g["HEM"] + g["FRONT_BODY"]           # front face: hem band + front panel rows
    g["SHOULDER_Y"] = g["UNDERARM_Y"] + g["YOKE_HALF"]     # + the front half of the yoke
    g["WINGSPAN"] = c["wingspan"]
    return g


def star_tile(w, h, ppc, g, yarn=YARN, shade=SHADE, dark=DARK):
    return SI.draw_star_fabric(int(w) + 4, int(h) + 4, g["STAR"] * ppc, g["PAIR"] * ppc, yarn=yarn, shade=shade, dark=dark)


def rib_tile(w, h, ppc, ridge_axis="x"):
    """sc-blo ribbing: a ridge every rib row (0.508 cm), running along `ridge_axis`."""
    img = Image.new("RGB", (int(w) + 4, int(h) + 4), YARN); d = ImageDraw.Draw(img); pitch = RIB_ROW_CM * ppc; lw = max(1, int(pitch * 0.35))
    n = int((h if ridge_axis == "x" else w) / pitch) + 2
    for k in range(n):
        p = k * pitch + pitch * 0.5
        if ridge_axis == "x": d.line([(0, p), (img.width, p)], fill=SHADE, width=lw)
        else: d.line([(p, 0), (p, img.height)], fill=SHADE, width=lw)
    return img


def paste_polygon(img, region, tile, poly, region_id, angle_deg=0.0, anchor=None):
    """Paint `tile` (rotated by angle about `anchor`) into the polygon; set the region id."""
    W, H = img.size
    m = Image.new("L", (W, H), 0); ImageDraw.Draw(m).polygon(poly, fill=255); mk = np.array(m) > 0
    if angle_deg:
        t = tile.rotate(-angle_deg, resample=Image.BILINEAR, expand=True)
    else: t = tile
    xs, ys = zip(*poly); x0, y0 = int(min(xs)), int(min(ys))
    ax, ay = (anchor if anchor else (x0, y0))
    canvas = Image.new("RGB", (W, H), BG); canvas.paste(t, (int(ax - t.width / 2), int(ay - t.height / 2)) if angle_deg else (x0 - 2, y0 - 2))
    arr = np.array(img); arr[mk] = np.array(canvas)[mk]; img.paste(Image.fromarray(arr)); region[mk] = region_id
    return mk


def build(out_dir: Path = OUT, prefix: str = "ref", size=FRAME, angle_deg: float = SLEEVE_ANGLE_DEG, fill: float = 0.90):
    WPX, HPX = size; pt, row = truth(); g = geometry(row); ang = math.radians(angle_deg)
    # frame: wingspan with the sleeves angled down, plus the hood above the shoulders
    sleeve_total = g["SL"] + g["CUFF"]
    extent_w = g["BW"] + 2 * (sleeve_total * math.cos(ang) + g["SLEEVE_FACE"] * math.sin(ang))
    extent_h = g["SHOULDER_Y"] + g["HOODH"]
    ppc = min(WPX * fill / extent_w, HPX * fill / extent_h)
    img = Image.new("RGB", (WPX, HPX), BG); region = np.zeros((HPX, WPX), np.uint8); d = ImageDraw.Draw(img)
    cx = WPX / 2; base_y = HPX / 2 + extent_h * ppc / 2
    X = lambda cm: cx + cm * ppc; Y = lambda cm: base_y - cm * ppc
    half = g["BW"] / 2; gap = g["GAP"] / 2; neck = g["NECK"] / 2
    tile_body = star_tile(g["BW"] * ppc + 10, (g["SHOULDER_Y"] + g["HOODH"]) * ppc + 10, ppc, g)
    tile_inside = star_tile(g["BW"] * ppc + 10, g["SHOULDER_Y"] * ppc + 10, ppc, g, yarn=INSIDE, shade=(190, 178, 166), dark=(160, 148, 136))
    # --- the back's inside shows through the V of the front neck ---
    v_poly = [(X(-neck), Y(g["SHOULDER_Y"])), (X(neck), Y(g["SHOULDER_Y"])), (X(gap), Y(g["UNDERARM_Y"])), (X(-gap), Y(g["UNDERARM_Y"]))]
    paste_polygon(img, region, tile_inside, v_poly, REGIONS["back_inside"])
    # --- fronts: hem to shoulder, inner edge straight to the underarm then sloping out to the neck opening ---
    fl = [(X(-half), Y(0)), (X(-half), Y(g["SHOULDER_Y"])), (X(-neck), Y(g["SHOULDER_Y"])), (X(-gap), Y(g["UNDERARM_Y"])), (X(-gap), Y(0))]
    fr = [(X(half), Y(0)), (X(half), Y(g["SHOULDER_Y"])), (X(neck), Y(g["SHOULDER_Y"])), (X(gap), Y(g["UNDERARM_Y"])), (X(gap), Y(0))]
    paste_polygon(img, region, tile_body, fl, REGIONS["front_left"]); paste_polygon(img, region, tile_body, fr, REGIONS["front_right"])
    boxes = {"front_left": fl, "front_right": fr, "neck_v": v_poly}
    # --- sleeves: built in, from the underarm to the shoulder at the body's sides, angled down; rows along the sleeve ---
    tile_sleeve = star_tile(sleeve_total * ppc * 1.6, g["SLEEVE_FACE"] * ppc * 1.6, ppc, g)
    for side, sgn in (("left", -1), ("right", 1)):
        top = np.array([X(sgn * half), Y(g["SHOULDER_Y"])]); u = np.array([sgn * math.cos(ang), math.sin(ang)]) * ppc; v = np.array([-sgn * math.sin(ang), math.cos(ang)]) * ppc
        p0 = top; p1 = top + u * g["SL"]; p2 = p1 + v * g["SLEEVE_FACE"]; p3 = top + v * g["SLEEVE_FACE"]
        poly = [tuple(p0), tuple(p1), tuple(p2), tuple(p3)]; centre = tuple((p0 + p2) / 2)
        paste_polygon(img, region, tile_sleeve, poly, REGIONS[f"sleeve_{side}"], angle_deg=sgn * angle_deg, anchor=centre)
        # cuff: gathered, ribbed across the sleeve end
        c0 = p1 + v * (g["SLEEVE_FACE"] * (1 - CUFF_FACE_FRACTION) / 2); c1 = c0 + u * g["CUFF"]; c2 = c1 + v * (g["SLEEVE_FACE"] * CUFF_FACE_FRACTION); c3 = c0 + v * (g["SLEEVE_FACE"] * CUFF_FACE_FRACTION)
        cuff = [tuple(c0), tuple(c1), tuple(c2), tuple(c3)]
        tile_cuff = rib_tile(g["CUFF"] * ppc * 2.5, g["SLEEVE_FACE"] * ppc * 2.5, ppc, ridge_axis="x")   # ridges along the sleeve (rib rows run round the wrist)
        paste_polygon(img, region, tile_cuff, cuff, REGIONS[f"cuff_{side}"], angle_deg=sgn * angle_deg, anchor=tuple((c0 + c2) / 2))
        boxes[f"sleeve_{side}"] = poly; boxes[f"cuff_{side}"] = cuff
    # --- hem band: sc-blo ribbing across the whole width, ridges vertical (rib rows run perpendicular to the hem) ---
    hem = [(X(-half), Y(0)), (X(half), Y(0)), (X(half), Y(g["HEM"])), (X(-half), Y(g["HEM"]))]
    paste_polygon(img, region, rib_tile(g["BW"] * ppc, g["HEM"] * ppc, ppc, ridge_axis="y"), hem, REGIONS["hem_band"]); boxes["hem_band"] = hem
    # --- button band: the centre strip from the hem to the neck point, ridges horizontal (rib rows run across the band) ---
    bb = [(X(-gap), Y(0)), (X(gap), Y(0)), (X(gap), Y(g["UNDERARM_Y"])), (X(-gap), Y(g["UNDERARM_Y"]))]
    paste_polygon(img, region, rib_tile(g["GAP"] * ppc, g["UNDERARM_Y"] * ppc, ppc, ridge_axis="x"), bb, REGIONS["button_band"]); boxes["button_band"] = bb
    # --- neck band: along each sloping front neck edge, the band's width inside the front ---
    bw = g["BAND"]
    for sgn in (-1, 1):
        a = np.array([X(sgn * gap), Y(g["UNDERARM_Y"])]); b = np.array([X(sgn * neck), Y(g["SHOULDER_Y"])]); e = (b - a) / np.linalg.norm(b - a); nrm = np.array([e[1], -e[0]]) * (sgn) * bw * ppc
        if (nrm[0] * sgn) < 0: nrm = -nrm   # the band lies inside the front (outward from the opening)
        poly = [tuple(a), tuple(b), tuple(b + nrm), tuple(a + nrm)]
        angle = math.degrees(math.atan2(e[1], e[0]))
        paste_polygon(img, region, rib_tile(np.linalg.norm(b - a) * 1.5, bw * ppc * 3, ppc, ridge_axis="y"), poly, REGIONS["neck_band"], angle_deg=angle, anchor=tuple((a + b + nrm) / 2))
        boxes.setdefault("neck_band", []).append(poly)
    # --- hood: spread open above the shoulders; from the neck opening out to the hood width, rounded top, centre seam line; face-edge band round the outside ---
    hw = g["HOODW"] / 2; hh = g["HOODH"]; ys = g["SHOULDER_Y"]
    hood = [(X(-neck - bw), Y(ys)), (X(neck + bw), Y(ys)), (X(hw), Y(ys + hh * 0.30)), (X(hw), Y(ys + hh * 0.70))]
    n_arc = 24
    for k in range(n_arc + 1):
        t = k / n_arc; xx = hw * math.cos(t * math.pi); yy = ys + hh * 0.70 + hh * 0.30 * math.sin(t * math.pi)
        hood.append((X(xx), Y(yy)))
    hood += [(X(-hw), Y(ys + hh * 0.30))]
    paste_polygon(img, region, tile_body, hood, REGIONS["hood"]); boxes["hood"] = hood
    # face-edge band: the hood's outline inset by the band width, a ribbed ring whose rib rows run
    # perpendicular to the face edge (ridges along the local edge normal); none along the neckline join
    from scipy.ndimage import binary_erosion, distance_transform_edt
    m_out = Image.new("L", (WPX, HPX), 0); ImageDraw.Draw(m_out).polygon(hood, fill=255); hood_mask = np.array(m_out) > 0
    padded = hood_mask.copy(); padded[int(Y(ys)):int(Y(ys)) + int(bw * ppc) + 4, int(X(-neck - bw)):int(X(neck + bw))] = True   # no edge at the join
    ring = hood_mask & ~binary_erosion(padded, iterations=int(bw * ppc))
    gy_, gx_ = np.gradient(distance_transform_edt(padded)); edge_vertical = np.abs(gx_) > np.abs(gy_)
    rib_v = np.array(rib_tile(WPX, HPX, ppc, ridge_axis="y").resize((WPX, HPX))); rib_h = np.array(rib_tile(WPX, HPX, ppc, ridge_axis="x").resize((WPX, HPX)))
    arr = np.array(img); sel_h = ring & edge_vertical; sel_v = ring & ~edge_vertical; arr[sel_h] = rib_h[sel_h]; arr[sel_v] = rib_v[sel_v]
    img.paste(Image.fromarray(arr)); region[ring] = REGIONS["hood_band"]
    d = ImageDraw.Draw(img); d.line([(X(0), Y(ys + hh)), (X(0), Y(ys + hh - hw))], fill=SHADE, width=max(2, int(0.25 * ppc)))   # the top seam (whip stitched)
    # --- buttons: on the centre band, evenly spaced from above the hem band to the neck point ---
    r = BUTTON_MM / 20.0 * ppc; y_lo, y_hi = g["HEM"] + 1.5, g["UNDERARM_Y"] - 1.0; buttons = []
    for k in range(BUTTONS):
        yc = y_lo + (y_hi - y_lo) * k / (BUTTONS - 1); bx = (X(0) - r, Y(yc) - r, X(0) + r, Y(yc) + r)
        d.ellipse(bx, fill=BUTTON, outline=BUTTON_RIM, width=2)
        for hx, hy in ((-0.3, -0.3), (0.3, -0.3), (-0.3, 0.3), (0.3, 0.3)): d.ellipse([X(0) + hx * r - r * 0.12, Y(yc) + hy * r - r * 0.12, X(0) + hx * r + r * 0.12, Y(yc) + hy * r + r * 0.12], fill=BUTTON_RIM)
        m = Image.new("L", (WPX, HPX), 0); ImageDraw.Draw(m).ellipse(bx, fill=255); region[np.array(m) > 0] = REGIONS["button"]; buttons.append([round(float(X(0)), 1), round(float(Y(yc)), 1), round(float(r), 1)])
    # --- mask, height, normal ---
    mask = region > 0
    from scipy.ndimage import gaussian_filter
    lum = np.array(img.convert("L")).astype(float) / 255.0; h = gaussian_filter(lum, 0.8); gy, gx = np.gradient(h * 6.0)
    n = np.stack([-gx, -gy, np.ones_like(h)], axis=-1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = ((n * 0.5 + 0.5) * 255).astype(np.uint8); normal[~mask] = (128, 128, 255)
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(out_dir / f"{prefix}_flatlay.png"); Image.fromarray((mask * 255).astype(np.uint8)).save(out_dir / f"{prefix}_mask.png")
    Image.fromarray(normal).save(out_dir / f"{prefix}_normal.png"); Image.fromarray(region).save(out_dir / f"{prefix}_regions.png")
    # --- validation against Product Truth: dimensions are the derived ones; the star instrument reads the reference's own fabric at the expected pitches ---
    star_px, pair_px = g["STAR"] * ppc, g["PAIR"] * ppc
    gray = np.array(img.convert("L")).astype(float); ys_, xs_ = np.nonzero(region == REGIONS["front_left"])
    box = (xs_.min(), ys_.min(), xs_.max(), int(Y(g["HEM"])))   # the front's fabric above the hem band
    sub = gray[box[1]:box[3], box[0]:box[2]]; submask = (region[box[1]:box[3], box[0]:box[2]] == REGIONS["front_left"])
    instr = SI.measure(sub, star_px, pair_px, mask=submask)
    validation = {"dimensions_are_product_truth": True,
                  "silhouette_cm": {"wingspan_incl_cuffs": round(g["WINGSPAN"] + 2 * g["CUFF"], 1), "front_height_hem_to_shoulder": round(g["SHOULDER_Y"], 1), "hood_above_shoulder": g["HOODH"], "back_width": g["BW"]},
                  "star_instrument_on_reference_front": {k: instr.get(k) for k in ("status", "identity", "gauge", "star_pitch_px", "row_pair_px", "pitch_over_pair", "column_offset_star", "failed")},
                  "region_pixels": {k: int((region == v).sum()) for k, v in REGIONS.items()}, "buttons_drawn": BUTTONS}
    meta = {"size": SIZE_NAME, "size_px": [WPX, HPX], "px_per_cm": round(ppc, 4), "star_px": round(star_px, 2), "row_pair_px": round(pair_px, 2), "regions": REGIONS,
            "boxes_px": {k: (v if isinstance(v, list) and v and isinstance(v[0], list) else [[round(float(x), 1), round(float(y), 1)] for x, y in v]) for k, v in boxes.items()},
            "buttons_px": buttons, "geometry_cm": {k: round(float(v), 2) for k, v in g.items()},
            "layout": {"view": "flat lay, top-down, front up, buttoned, hood spread flat above the shoulders, sleeves angled down", "sleeve_angle_deg": angle_deg, "fill": fill,
                       "cuff_face_fraction": CUFF_FACE_FRACTION, "centre_gap_cm_DECLARED": round(g["GAP"], 2), "band_cm_from_pattern": round(g["BAND"], 2),
                       "buttons_DECLARED": f"{BUTTONS} buttons {BUTTON_MM} mm, evenly spaced on the centre band from above the hem band to the neck point (pattern: 4-6 by preference)",
                       "hood_DECLARED": "spread open behind the neck, top seam drawn as a centre line, face-edge band round the outside"},
            "colour": {"yarn_rgb": YARN, "surface_rgb": BG, "basis": "Oat Milk; RGB is the lit median of the designer's flat-lay photograph of that colourway (evidence about the colourway, not pattern text); dark surface chosen so the cream garment segments by lightness"},
            "validation": validation, "cir_fingerprint": pt["cir_for_size"]["fingerprint"]}
    json.dump(meta, open(out_dir / f"{prefix}_meta.json", "w"), indent=1)
    return meta


if __name__ == "__main__":
    m = build(prefix=sys.argv[1] if len(sys.argv) > 1 else "ref")
    print(json.dumps(m["validation"], indent=1)); print("px/cm", m["px_per_cm"], "star px", m["star_px"], "pair px", m["row_pair_px"])
