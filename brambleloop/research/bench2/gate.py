"""Commercial benchmark 2, phase 6: the certification gate.

A candidate passes only when BOTH hold: (a) Product Truth -- Bench1's deterministic checks
(silhouette, proportions, sleeve span against the reference mask, scale and shift free), plus
the star-stitch identity instrument and its gauge reading on the candidate's front panels at
the pitches Product Truth prescribes, plus the reader's material properties against what
Product Truth expects -- and (b) the unchanged D realism judge. Any material FAIL is FAIL;
UNKNOWN never passes; nothing is cherry-picked.

The garment mask is by lightness: the reference lays the cream garment on a dark slate
surface and the prompt keeps that surface, so the candidate segments without a hue rule.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import zoom, binary_fill_holes, binary_opening
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "research", "bench1"))
import star_identity as SI   # noqa: E402
import importlib.util as _ilu   # Bench1's gate under its own name (both files are called gate.py): _place, verdict (unchanged rule)
_spec = _ilu.spec_from_file_location("bench1_gate", os.path.join(ROOT, "research", "bench1", "gate.py")); G1 = _ilu.module_from_spec(_spec); _spec.loader.exec_module(G1)

BARS = {"silhouette_iou": 0.80, "aspect_drift": 0.10, "sleeve_span_drift": 0.12}
# What Product Truth expects the reader to see: (accepted answers, material?)
EXPECT = {
    "product_type": ({"cardigan"}, True), "front": ({"buttoned", "overlapping", "closed_other"}, True), "closure_count": ({5}, True),
    "front_band": ({"ribbed_band", "plain_band"}, True), "hem_band": ({"ribbed"}, True), "cuffs": ({"ribbed", "gathered"}, True),
    "pocket_count": ({0}, True), "pocket_position": ({"none"}, True), "sleeve_length": ({"long"}, True), "body_length": ({"hip"}, True),
    "texture": ({"star_stitch"}, True), "hood": ({"attached_hood"}, True), "hood_edge": ({"ribbed_band", "plain"}, False),
    "cluster_rows_direction": ({"horizontal"}, False), "body_ridge_direction": ({"horizontal", "none"}, False),
    "colour_count": ({1}, True), "extra_features": ({"hood", "buttons"}, True), "handmade_crochet": ({True}, False),
}
# Materiality can be withdrawn only by calibration on the designer's own photographs (E3 rule:
# a reader that cannot read a property on ground truth must not veto on it). Recorded here
# when it happens, with the evidence, by `calibrate()`; never by hand to pass a candidate.
CALIBRATION_FILE = os.path.join(OUT, "reader_calibration.json")


def expectations():
    ex = {k: (a, m) for k, (a, m) in EXPECT.items()}
    if os.path.exists(CALIBRATION_FILE):
        cal = json.load(open(CALIBRATION_FILE))
        for k in cal.get("withdrawn_material", []): ex[k] = (ex[k][0], False)
    return ex


def garment_mask(img):
    """The cream garment on the dark surface: light, low-saturation pixels; buttons and
    shadows inside the outline are filled."""
    hsv = np.array(img.convert("HSV")).astype(float); s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    m = (v > 0.50) & (s < 0.45)
    m = binary_opening(m, iterations=2); m = binary_fill_holes(m)
    return m


def masks(candidate_path, refv="ref"):
    ref = np.array(Image.open(os.path.join(OUT, f"{refv}_mask.png"))) > 127; H, W = ref.shape
    gen = Image.open(candidate_path).convert("RGB").resize((W, H), Image.LANCZOS); gm = garment_mask(gen)
    ys, xs = np.nonzero(gm); rys, rxs = np.nonzero(ref)
    if len(ys) < 0.01 * len(rys): return ref, np.zeros_like(ref), None, gm
    s = np.sqrt(len(rys) / len(ys)); z = zoom(gm.astype(float), s, order=1) > 0.5
    zys, zxs = np.nonzero(z); dy, dx = rys.mean() - zys.mean(), rxs.mean() - zxs.mean()
    def iou(m): u = (m | ref).sum(); return float((m & ref).sum() / u) if u else 0.0
    best = (iou(G1._place(z, dy, dx, ref.shape)), s, dy, dx)
    for scales, step, span in (((0.90, 0.94, 0.97, 1.0, 1.03, 1.06, 1.10), 8, 48), ((0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015), 2, 8)):
        _, s1, dy1, dx1 = best
        for f in scales:
            zz = zoom(gm.astype(float), s1 * f, order=1) > 0.5
            for ddy in range(-span, span + 1, step):
                for ddx in range(-span, span + 1, step):
                    v = iou(G1._place(zz, dy1 + ddy, dx1 + ddx, ref.shape))
                    if v > best[0]: best = (v, s1 * f, dy1 + ddy, dx1 + ddx)
    _, s, dy, dx = best; al = G1._place(zoom(gm.astype(float), s, order=1) > 0.5, dy, dx, ref.shape)
    return ref, al, {"scale": float(s), "shift_px": [float(dy), float(dx)], "iou": best[0]}, gm


def aligned_gray(candidate_path, align, shape):
    H, W = shape
    gen = np.array(Image.open(candidate_path).convert("L").resize((W, H), Image.LANCZOS)).astype(float)
    z = zoom(gen, align["scale"], order=1); canvas = np.zeros((H, W)); h, w = z.shape; sy0, sx0 = int(round(align["shift_px"][0])), int(round(align["shift_px"][1]))
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W); canvas[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    return canvas


def aligned_array(arr, align, shape):
    H, W = shape
    z = zoom(arr, align["scale"], order=1); canvas = np.zeros((H, W)); h, w = z.shape; sy0, sx0 = int(round(align["shift_px"][0])), int(round(align["shift_px"][1]))
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W); canvas[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    return canvas


def button_count(candidate_path, align, refv="ref", expected=5):
    """Deterministic button count: dark, roughly round blobs of about the reference button's
    area on (or just beside) the reference's centre band, in the aligned candidate. The reader's
    closure count was withdrawn from materiality by calibration; this check is code."""
    from scipy.ndimage import binary_dilation, label
    regions = np.array(Image.open(os.path.join(OUT, f"{refv}_regions.png"))); meta = json.load(open(os.path.join(OUT, f"{refv}_meta.png".replace(".png", ".json")))); rid = meta["regions"]
    r = meta["buttons_px"][0][2]; area = np.pi * r * r
    band = (regions == rid["button_band"]) | (regions == rid["button"]); band = binary_dilation(band, iterations=int(1.5 * r))
    rgb = np.array(Image.open(candidate_path).convert("RGB").resize((regions.shape[1], regions.shape[0]), Image.LANCZOS)).astype(float)
    v = aligned_array(rgb.max(axis=2) / 255.0, align, regions.shape)
    garment_v = np.median(v[(regions == rid["front_left"]) & (v > 0)]) if ((regions == rid["front_left"]) & (v > 0)).any() else 0.8
    dark = (v < 0.62 * garment_v) & band & (v > 0)
    lab, n = label(dark); found = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i); a = len(ys)
        if not (0.25 * area <= a <= 3.0 * area): continue
        h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if max(h, w) / max(1, min(h, w)) > 2.0: continue   # not round
        found.append([int(xs.mean()), int(ys.mean()), int(a)])
    return {"status": "PASS" if len(found) == expected else "FAIL", "evidence": {"count": len(found), "expected": expected, "blobs_px": found, "reference_button_area_px": round(float(area), 1), "garment_value": round(float(garment_v), 3)}}


def star_on_candidate(candidate_path, align, refv="ref"):
    """The identity instrument on the candidate's front panels (above the hem band, the neck
    bands excluded), aligned to the reference, at the pitches Product Truth prescribes for
    this pixel scale. The scale of the candidate's fabric is corrected by the alignment scale,
    so the gauge reading is in garment terms."""
    regions = np.array(Image.open(os.path.join(OUT, f"{refv}_regions.png"))); meta = json.load(open(os.path.join(OUT, f"{refv}_meta.json"))); rid = meta["regions"]
    canvas = aligned_gray(candidate_path, align, regions.shape)
    out = {}
    for side in ("front_left", "front_right"):
        m = regions == rid[side]; ys, xs = np.nonzero(m); box = (xs.min(), ys.min(), xs.max(), ys.max())
        sub = canvas[box[1]:box[3], box[0]:box[2]]; submask = m[box[1]:box[3], box[0]:box[2]]
        out[side] = SI.measure(sub, meta["star_px"], meta["row_pair_px"], mask=submask)
    ids = [o.get("identity") for o in out.values()]; gs = [o.get("gauge", {}).get("status") if isinstance(o.get("gauge"), dict) else "UNKNOWN" for o in out.values()]
    identity = "PASS" if all(i == "PASS" for i in ids) else ("UNKNOWN" if any(i == "UNKNOWN" for i in ids) and not any(i == "FAIL" for i in ids) else "FAIL")
    gauge = "PASS" if all(g == "PASS" for g in gs) else ("UNKNOWN" if any(g == "UNKNOWN" for g in gs) and not any(g == "FAIL" for g in gs) else "FAIL")
    return {"identity": identity, "gauge": gauge, "panels": {k: {kk: v.get(kk) for kk in ("status", "identity", "gauge", "star_pitch_px", "row_pair_px", "pitch_over_pair", "column_offset_star", "row_peak", "next_row_peak",
                                                                                 "blob_isotropy", "diagonal_fraction", "return_row_contrast", "failed", "why")} for k, v in out.items()},
            "expected_px": {"star": meta["star_px"], "row_pair": meta["row_pair_px"]}, "rule": "both front panels must PASS identity and gauge; UNKNOWN blocks"}


def deterministic(candidate_path, refv="ref"):
    ref, al, align, gm = masks(candidate_path, refv)
    if align is None: return {"status": "FAIL", "why": "no garment-coloured region found", "items": {}}
    def bbox(m):
        ys, xs = np.nonzero(m); return xs.min(), ys.min(), xs.max(), ys.max()
    rb, gb = bbox(ref), bbox(al); r_asp = (rb[3] - rb[1]) / (rb[2] - rb[0]); g_asp = (gb[3] - gb[1]) / (gb[2] - gb[0]); drift = abs(g_asp - r_asp) / r_asp
    def widest(m):
        w = m.sum(axis=1); return float(w.max()) / max(1, (bbox(m)[3] - bbox(m)[1]))
    sspan = abs(widest(al) - widest(ref)) / widest(ref)
    items = {"silhouette": ("PASS" if align["iou"] >= BARS["silhouette_iou"] else "FAIL", {"iou_aligned": round(align["iou"], 3), "alignment": align}),
             "proportions": ("PASS" if drift <= BARS["aspect_drift"] else "FAIL", {"aspect_ref": round(float(r_asp), 3), "aspect_gen": round(float(g_asp), 3), "drift": round(float(drift), 3)}),
             "sleeve_span": ("PASS" if sspan <= BARS["sleeve_span_drift"] else "FAIL", {"widest_row_over_height_ref": round(widest(ref), 3), "gen": round(widest(al), 3), "drift": round(float(sspan), 3)})}
    bc = button_count(candidate_path, align, refv); items["buttons"] = (bc["status"], bc["evidence"])
    st = star_on_candidate(candidate_path, align, refv)
    items["star_identity"] = (st["identity"], st); items["star_gauge"] = (st["gauge"], {"panels": {k: v.get("gauge") for k, v in st["panels"].items()}, "expected_px": st["expected_px"]})
    status = "FAIL" if any(s == "FAIL" for s, _ in items.values()) else ("UNKNOWN" if any(s == "UNKNOWN" for s, _ in items.values()) else "PASS")
    return {"status": status, "items": {k: {"status": s, "evidence": e} for k, (s, e) in items.items()}}


def properties(answers: dict, reference_answers: dict | None = None) -> dict:
    out = {}
    for key, (accept, material) in expectations().items():
        got = answers.get(key)
        seen_on_reference = None if reference_answers is None else (key in reference_answers)
        if got is None: out[key] = {"status": "UNKNOWN", "got": None, "why": "not visible to the reader", "material": material}; continue
        if key == "extra_features":
            feats = set() if (not got or got == ["none"] or got == "none") else set(map(str, got if isinstance(got, list) else [got]))
            ok = feats <= accept; got = sorted(feats) or "none"
        else: ok = got in accept
        out[key] = {"status": "PASS" if ok else "FAIL", "got": got, "expected": sorted(map(str, accept)), "material": material, "reader_saw_it_on_reference": seen_on_reference}
    return out


def verdict(det: dict, props: dict, judge_items: dict | None) -> dict:
    v = G1.verdict(det, props, judge_items)
    det_unknown = [k for k, x in det.get("items", {}).items() if x["status"] == "UNKNOWN"]
    if v["status"] == "PASS" and det_unknown: v["status"] = "UNKNOWN"
    v["unknown_deterministic"] = det_unknown
    v["rule"] = "PASS only when every material property, every deterministic measure (silhouette, proportions, sleeve span, button count, star identity, star gauge) and every judge item PASS; any material FAIL is FAIL; UNKNOWN never passes"
    return v


def calibrate(designer_readings: dict) -> dict:
    """The reader on the designer's photographs of the real product (private evidence). A
    material property the reader gets wrong on a majority of the photographs that show it is
    withdrawn from materiality (kept, reported), as Bench1 did for ridge direction."""
    tally = {}
    for name, ans in designer_readings.items():
        for key, res in properties(ans).items():
            if res["status"] == "UNKNOWN": continue
            tally.setdefault(key, []).append(res["status"] == "PASS")
    withdrawn = [k for k, oks in tally.items() if EXPECT[k][1] and sum(oks) * 2 < len(oks)]
    cal = {"tally": {k: {"agree": int(sum(v)), "of": len(v)} for k, v in tally.items()}, "withdrawn_material": withdrawn,
           "rule": "a material property the reader reads wrong on more than half of the designer's photographs that show it cannot veto a candidate (E3 rule); it is still reported"}
    json.dump(cal, open(CALIBRATION_FILE, "w"), indent=1); return cal
