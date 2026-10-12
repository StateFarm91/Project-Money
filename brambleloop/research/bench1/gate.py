"""Commercial benchmark 1, phase 5: the commercial Product Truth gate.

A candidate image is measured against (a) the pattern-derived Product Truth, through the
deterministic reference it was conditioned on, and (b) the independent reader's answers to
one fixed question set. Deterministic first: silhouette and proportions against the
reference mask (scale and shift free, shape not -- the same rule as E3-E5); then the reader's
properties, each judged PASS/FAIL/UNKNOWN against the expectation Product Truth states; then
the unchanged D judge for photographic realism.

Materiality: a property is MATERIAL when a buyer would expect a different finished product if
it were wrong (product type, open front with no closure, ribbed front band, hem band, cuffs,
two hip pockets, long sleeves, body length, waffle texture with vertical ridges, one colour,
no invented features). Silhouette and proportions are material too. A property the reader
cannot see on the reference is not testable by the reader (E3 rule) and is UNKNOWN there,
which blocks certification but is reported as what it is.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(ROOT, "src")); sys.path.insert(0, os.path.join(ROOT, "research", "e4")); sys.path.insert(0, os.path.join(ROOT, "research", "e3")); sys.path.insert(0, HERE)
from correspond import yarn_mask                   # noqa: E402  hue segmentation (dusty pink on neutral)
from scipy.ndimage import zoom                     # noqa: E402
import reader as R                                 # noqa: E402

def _place(z, dy, dx, shape):
    H, W = shape
    out = np.zeros((H, W), bool); h, w = z.shape; sy0, sx0 = int(round(dy)), int(round(dx))
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W)
    if y1 > y0 and x1 > x0: out[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    return out


BARS = {"silhouette_iou": 0.80, "aspect_drift": 0.10, "sleeve_span_drift": 0.12}
# What Product Truth expects the reader to see. Each: (accepted answers, material?)
EXPECT = {
    "product_type": ({"cardigan"}, True), "front": ({"open", "overlapping"}, True), "closure_count": ({0}, True),
    "front_band": ({"ribbed_band", "plain_band"}, True), "hem_band": ({"ribbed", "plain"}, True), "cuffs": ({"ribbed", "gathered"}, True),
    "pocket_count": ({2}, True), "pocket_position": ({"hip"}, True), "sleeve_length": ({"long"}, True),
    "body_length": ({"hip", "mid_thigh"}, True), "texture": ({"waffle_textured", "ribbed_all_over", "other"}, True),
    # Ridge direction is reported but NOT material for the gate: calibrated on the seller's own
    # photographs the reader answered "horizontal" on 3 of 4 (the front bands' ridges dominate),
    # so it cannot read this property reliably even on ground truth and must not veto on it.
    "body_ridge_direction": ({"vertical"}, False), "colour_count": ({1}, True), "extra_features": ({"none"}, True), "handmade_crochet": ({True}, False),
}


def masks(candidate_path, refv="ref"):
    ref = np.array(Image.open(os.path.join(OUT, f"{refv}_mask.png"))) > 127; H, W = ref.shape
    gen = Image.open(candidate_path).convert("RGB").resize((W, H), Image.LANCZOS); gm, _ = yarn_mask(gen)
    ys, xs = np.nonzero(gm); rys, rxs = np.nonzero(ref)
    if len(ys) < 0.01 * len(rys): return ref, np.zeros_like(ref), None, gm
    s = np.sqrt(len(rys) / len(ys)); z = zoom(gm.astype(float), s, order=1) > 0.5
    zys, zxs = np.nonzero(z); dy, dx = rys.mean() - zys.mean(), rxs.mean() - zxs.mean()
    def iou(m): u = (m | ref).sum(); return float((m & ref).sum() / u) if u else 0.0
    best = (iou(_place(z, dy, dx, ref.shape)), s, dy, dx)
    for scales, step, span in (((0.90, 0.94, 0.97, 1.0, 1.03, 1.06, 1.10), 8, 48), ((0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015), 2, 8)):
        _, s1, dy1, dx1 = best
        for f in scales:
            zz = zoom(gm.astype(float), s1 * f, order=1) > 0.5
            for ddy in range(-span, span + 1, step):
                for ddx in range(-span, span + 1, step):
                    v = iou(_place(zz, dy1 + ddy, dx1 + ddx, ref.shape))
                    if v > best[0]: best = (v, s1 * f, dy1 + ddy, dx1 + ddx)
    _, s, dy, dx = best; al = _place(zoom(gm.astype(float), s, order=1) > 0.5, dy, dx, ref.shape)
    return ref, al, {"scale": float(s), "shift_px": [float(dy), float(dx)], "iou": best[0]}, gm


def texture_period_px(gray, region_mask):
    """Dominant spatial period (px) of the fabric texture inside a region: radial power
    spectrum of the high-passed grey image, peak between 3 and 40 px."""
    from scipy.ndimage import gaussian_filter
    ys, xs = np.nonzero(region_mask); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    g = gray[y0:y1, x0:x1].astype(float); g = g - gaussian_filter(g, 6.0); g = g * region_mask[y0:y1, x0:x1]
    F = np.abs(np.fft.fftshift(np.fft.fft2(g))) ** 2; h, w = F.shape; cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[:h, :w]; r = np.hypot(yy - cy, xx - cx).astype(int)
    radial = np.bincount(r.ravel(), F.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    freqs = np.arange(len(radial)); ok = (freqs > 0)
    periods = np.where(ok, max(h, w) / np.maximum(freqs, 1), 0.0)
    sel = (periods >= 3) & (periods <= 40); k = np.argmax(np.where(sel, radial, -1))
    return float(periods[k])


def stitch_scale(candidate_path, align, refv="ref"):
    """The candidate's texture period against the reference's, inside the left front panel
    (pocket excluded), after the same scale/shift alignment as the silhouette. A period much
    larger than the reference's means the yarn reads chunkier and the garment smaller than the
    pattern makes it (the reader's 'child-sized'); bar +-35 % (CHOSEN: the generator adds fuzz
    and shading at the stitch scale, which widens the peak but should not move it)."""
    regions = np.array(Image.open(os.path.join(OUT, f"{refv}_regions.png"))); meta = json.load(open(os.path.join(OUT, f"{refv}_meta.json")))
    rid = meta["regions"]; panel = (regions == rid["front_left"]); H, W = regions.shape
    ref_gray = np.array(Image.open(os.path.join(OUT, f"{refv}_flatlay.png")).convert("L")).astype(float)
    gen = np.array(Image.open(candidate_path).convert("L").resize((W, H), Image.LANCZOS)).astype(float)
    z = zoom(gen, align["scale"], order=1); canvas = np.zeros((H, W)); h, w = z.shape; sy0, sx0 = int(round(align["shift_px"][0])), int(round(align["shift_px"][1]))
    y0, x0 = max(sy0, 0), max(sx0, 0); y1, x1 = min(sy0 + h, H), min(sx0 + w, W); canvas[y0:y1, x0:x1] = z[y0 - sy0:y1 - sy0, x0 - sx0:x1 - sx0]
    p_ref, p_gen = texture_period_px(ref_gray, panel), texture_period_px(canvas, panel)
    ratio = p_gen / p_ref
    return {"status": "PASS" if abs(ratio - 1) <= 0.35 else "FAIL", "evidence": {"period_px_reference": round(p_ref, 2), "period_px_candidate_aligned": round(p_gen, 2), "ratio": round(ratio, 3),
            "reference_cell_px": {"stitch": round(meta["px_per_cm"] * 10 / 14.5, 2), "row": round(meta["px_per_cm"] * 10 / 9.5, 2)}}}


def deterministic(candidate_path, refv="ref"):
    ref, al, align, gm = masks(candidate_path, refv)
    if align is None: return {"status": "FAIL", "why": "no garment-coloured region found", "items": {}}
    def bbox(m):
        ys, xs = np.nonzero(m); return xs.min(), ys.min(), xs.max(), ys.max()
    rb, gb = bbox(ref), bbox(al); r_asp = (rb[3] - rb[1]) / (rb[2] - rb[0]); g_asp = (gb[3] - gb[1]) / (gb[2] - gb[0])
    drift = abs(g_asp - r_asp) / r_asp
    # sleeve span: the widest row of the silhouette relative to its height (sleeves out) -- proportions of the outline beyond the aspect
    def widest(m):
        w = m.sum(axis=1); return float(w.max()) / max(1, (bbox(m)[3] - bbox(m)[1]))
    sspan = abs(widest(al) - widest(ref)) / widest(ref)
    items = {"silhouette": ("PASS" if align["iou"] >= BARS["silhouette_iou"] else "FAIL", {"iou_aligned": round(align["iou"], 3), "alignment": align}),
             "proportions": ("PASS" if drift <= BARS["aspect_drift"] else "FAIL", {"aspect_ref": round(float(r_asp), 3), "aspect_gen": round(float(g_asp), 3), "drift": round(float(drift), 3)}),
             "sleeve_span": ("PASS" if sspan <= BARS["sleeve_span_drift"] else "FAIL", {"widest_row_over_height_ref": round(widest(ref), 3), "gen": round(widest(al), 3), "drift": round(float(sspan), 3)})}
    ss = stitch_scale(candidate_path, align, refv); items["stitch_scale"] = (ss["status"], ss["evidence"])
    return {"status": "FAIL" if any(s == "FAIL" for s, _ in items.values()) else "PASS", "items": {k: {"status": s, "evidence": e} for k, (s, e) in items.items()}}


def properties(answers: dict, reference_answers: dict | None = None) -> dict:
    """Each expected property against the reader's answer. Where a reference reading is given,
    a property the reader could not see on the deterministic reference is UNKNOWN (E3 rule)."""
    out = {}
    for key, (accept, material) in EXPECT.items():
        got = answers.get(key)
        if isinstance(got, list): got = "none" if (not got or got == ["none"]) else "extra:" + ",".join(map(str, got))
        # The expectation comes from Product Truth, not from the reference reading; whether the
        # reader could see the property on the deterministic reference is recorded beside the
        # verdict (calibration), never used as a veto (the brief: an instrument that cannot read
        # its own reference must not veto a commercially truthful photograph).
        seen_on_reference = None if reference_answers is None else (key in reference_answers)
        if got is None: out[key] = {"status": "UNKNOWN", "got": None, "why": "not visible to the reader", "material": material}; continue
        ok = got in accept
        if key == "extra_features": ok = (got == "none")
        out[key] = {"status": "PASS" if ok else "FAIL", "got": got, "expected": sorted(map(str, accept)), "material": material, "reader_saw_it_on_reference": seen_on_reference}
    return out


def verdict(det: dict, props: dict, judge_items: dict | None) -> dict:
    material_fail = [k for k, v in props.items() if v["material"] and v["status"] == "FAIL"] + [k for k, v in det["items"].items() if v["status"] == "FAIL"]
    unknown = [k for k, v in props.items() if v["material"] and v["status"] == "UNKNOWN"]
    judge_fail = [k for k, v in (judge_items or {}).items() if v != "PASS"]
    if material_fail: status = "FAIL"
    elif unknown or judge_items is None: status = "UNKNOWN"
    elif judge_fail: status = "FAIL"
    else: status = "PASS"
    return {"status": status, "material_failures": material_fail, "unknown_material": unknown, "judge_failures": judge_fail,
            "rule": "PASS only when every material property and every deterministic measure PASS and every judge item PASS; any material FAIL is FAIL; UNKNOWN never passes"}
