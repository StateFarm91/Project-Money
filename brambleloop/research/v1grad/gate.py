"""Product-only Visual V1 graduation, phases 3 and 5: the cable identity + gauge instrument
and the certification gate.

Deterministic first, as every benchmark before it: silhouette, proportions and sleeve-span
style outline checks (here the outline is a rectangle whose aspect is Product Truth's), then
the CABLE instrument on the candidate aligned to the reference, then the reader's material
properties against Product Truth's expectations, then the unchanged D realism judge. Any
material FAIL is FAIL; UNKNOWN never passes; nothing is cherry-picked.

The cable instrument, from what the design IS (Product Truth): 18 raised cable columns of four
stitches separated by four recessed back-post stitches, so the fabric is periodic ACROSS the
rows at the column pitch (8 stitches = 5.0 cm); within each column the two strand pairs cross
every fourth row, so the columns are periodic UP the rows at the crossing period (4 post rows
= 4.22 cm); the ribs make the surface's gradient energy run along the rows (vertical edges).
Bars a priori, named in BARS/WHY. Self-tested on the deterministic reference, on the reference
rotated a quarter turn, on a plain fabric, on Bench2's star truth and on Bench1's waffle before
any paid image was gated; thresholds were not moved.
"""
from __future__ import annotations
import importlib.util, json, os, sys
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, zoom, binary_fill_holes, binary_opening
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
sys.path.insert(0, os.path.join(ROOT, "src"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


G1 = _load("bench1_gate", "research/bench1/gate.py")      # _place, verdict rule (unchanged)
G2 = _load("bench2_gate", "research/bench2/gate.py")      # garment_mask (lightness on dark), aligned_array

BARS = {"silhouette_iou": 0.80, "aspect_drift": 0.10, "period_scale": 0.35, "peak": 0.10, "column_dominance": 1.20, "pitch_ratio_band": (0.83, 1.65)}
WHY = {"silhouette_iou": "E3-E5 / Bench1 rule: scale- and shift-free outline agreement >= 0.80",
       "aspect_drift": "Bench1 rule: the outline's aspect within +-10 % of Product Truth's",
       "period_scale": "Bench1/2 rule: a measured period within +-35 % of the expected one (generator fuzz widens a peak, must not move it)",
       "peak": "Bench2 rule: a periodicity exists when the normalised autocorrelation peak is >= 0.10",
       "column_dominance": "DERIVED: post-stitch ribs are vertical edges, so along-row gradient energy exceeds across-row energy; accepted >= 1.2 (a plain or isotropic fabric sits near 1)",
       "pitch_ratio_band": "DERIVED: column pitch / crossing period = 8 sts x 0.625 cm over 4 rows x 1.056 cm = 1.18, accepted +-30 % (0.83-1.65)"}

# What Product Truth expects the reader to see: (accepted answers, material?)
EXPECT = {"product_type": ({"blanket_or_throw"}, True), "shape": ({"rectangle"}, True), "texture": ({"cabled"}, True), "cable_direction": ({"along_the_length"}, True),
          "colour_count": ({1}, True), "edging": ({"none"}, True), "extra_features": (set(), True), "cable_column_count": ({18}, False), "handmade_crochet": ({True}, False),
          "presentation": ({"flat", "folded", "draped"}, False)}


def dominant_period(profile, pmin, pmax):
    """The fundamental period of a 1-D profile from its normalised autocorrelation: the
    shortest lag in [pmin, pmax] whose local maximum is at least 0.6 of the strongest one (a
    harmonic at twice or five times the pitch can edge above the fundamental by a few
    hundredths; it is never the fundamental). Returns (period, peak)."""
    p = profile - profile.mean(); n = len(p)
    if n < 2 * pmin or p.std() < 1e-9: return None, 0.0
    F = np.fft.rfft(p, 2 * n); A = np.fft.irfft(np.abs(F) ** 2)[:n]; A = A / max(A[0], 1e-9)
    lo, hi = int(pmin), min(int(pmax), n - 2)
    if hi <= lo: return None, 0.0
    peaks = [(lag, float(A[lag])) for lag in range(lo, hi) if A[lag] >= A[lag - 1] and A[lag] >= A[lag + 1] and A[lag] > 0]
    if not peaks: return None, 0.0
    vmax = max(v for _, v in peaks); lag, v = min([(l, v) for l, v in peaks if v >= 0.6 * vmax], key=lambda t: t[0])
    return float(lag), v


def measure(gray, mask, col_expected=None, cross_expected=None, column_mask=None):
    """gray: the fabric, rows horizontal (columns of cables vertical). mask: the fabric region.
    column_mask (optional): where the cable columns are, from the reference; when absent the
    strips are found from the along-row profile itself."""
    g = gray.astype(float); mk = mask.astype(bool)
    if mk.sum() < 100: return {"status": "UNKNOWN", "identity": "UNKNOWN", "why": "no fabric region"}
    ys, xs = np.nonzero(mk); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    g = g[y0:y1, x0:x1]; mk = mk[y0:y1, x0:x1]
    g = np.where(mk, g, np.nan); g = np.where(np.isnan(g), np.nanmean(g), g)
    hp = g - gaussian_filter(g, 8.0)
    gx = gaussian_filter(g, 1.0, order=(0, 1)); gy = gaussian_filter(g, 1.0, order=(1, 0))
    dominance = float((gx ** 2)[mk].mean() / max((gy ** 2)[mk].mean(), 1e-9))
    # across the rows: the column pitch, from the along-x profile of the smoothed |gx| (ribs) -- the ribs' edges repeat at the pitch
    prof_x = np.where(mk, np.abs(gx), 0).sum(axis=0) / np.maximum(mk.sum(axis=0), 1)
    prof_x = gaussian_filter(prof_x, 2.5)   # the strands inside a column ripple at the stitch width; the pitch is the column's
    H, W = g.shape
    col_period, col_peak = dominant_period(prof_x, 6, min(W // 3, 400))
    # up the rows: the crossing period, from the along-y profile of diagonal gradient energy inside the cable strips
    if column_mask is not None:
        cm = column_mask[y0:y1, x0:x1].astype(bool) & mk
    elif col_period:
        # strips: the columns where |gx| smoothed at the pitch is above its median (the raised ribs)
        s = gaussian_filter(prof_x, col_period / 4); cm = np.zeros_like(mk); cm[:, s > np.median(s)] = True; cm &= mk
    else: cm = mk
    diag = np.abs(gx * gy)
    prof_y = gaussian_filter(np.where(cm, diag, 0).sum(axis=1) / np.maximum(cm.sum(axis=1), 1), 2.5)
    cross_period, cross_peak = dominant_period(prof_y, 6, min(H // 3, 400))
    out = {"column_pitch_px": round(col_period, 2) if col_period else None, "column_peak": round(col_peak, 3), "crossing_period_px": round(cross_period, 2) if cross_period else None, "crossing_peak": round(cross_peak, 3),
           "column_dominance": round(dominance, 3), "pitch_ratio": round(col_period / cross_period, 3) if (col_period and cross_period) else None}
    tests = {"column_periodicity": bool(col_period) and col_peak >= BARS["peak"], "crossing_periodicity": bool(cross_period) and cross_peak >= BARS["peak"],
             "column_dominance": dominance >= BARS["column_dominance"],
             "pitch_ratio": out["pitch_ratio"] is not None and BARS["pitch_ratio_band"][0] <= out["pitch_ratio"] <= BARS["pitch_ratio_band"][1]}
    out["tests"] = tests; out["identity"] = "PASS" if all(tests.values()) else "FAIL"; out["failed"] = [k for k, v in tests.items() if not v]
    if col_expected and cross_expected:
        if col_period and cross_period:
            rc, rx = col_period / col_expected, cross_period / cross_expected
            out["gauge"] = {"column_pitch_ratio": round(rc, 3), "crossing_period_ratio": round(rx, 3), "status": "PASS" if abs(rc - 1) <= BARS["period_scale"] and abs(rx - 1) <= BARS["period_scale"] else "FAIL"}
        else: out["gauge"] = {"status": "UNKNOWN", "why": "a period was not found"}
        out["status"] = "PASS" if out["identity"] == "PASS" and out["gauge"]["status"] == "PASS" else ("UNKNOWN" if out["gauge"]["status"] == "UNKNOWN" and out["identity"] == "PASS" else "FAIL")
    else: out["status"] = out["identity"]
    return out


# ---------------------------------------------------------------- gate on a candidate
def masks(candidate_path, refv="ref"):
    ref = np.array(Image.open(os.path.join(OUT, f"{refv}_mask.png"))) > 127; H, W = ref.shape
    gen = Image.open(candidate_path).convert("RGB").resize((W, H), Image.LANCZOS); gm = G2.garment_mask(gen)
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


def deterministic(candidate_path, refv="ref"):
    ref, al, align, gm = masks(candidate_path, refv)
    if align is None: return {"status": "FAIL", "why": "no garment-coloured region found", "items": {}}
    meta = json.load(open(os.path.join(OUT, f"{refv}_meta.json"))); regions = np.array(Image.open(os.path.join(OUT, f"{refv}_regions.png")))
    def bbox(m):
        ys, xs = np.nonzero(m); return xs.min(), ys.min(), xs.max(), ys.max()
    rb, gb = bbox(ref), bbox(al); r_asp = (rb[3] - rb[1]) / (rb[2] - rb[0]); g_asp = (gb[3] - gb[1]) / (gb[2] - gb[0]); drift = abs(g_asp - r_asp) / r_asp
    items = {"silhouette": ("PASS" if align["iou"] >= BARS["silhouette_iou"] else "FAIL", {"iou_aligned": round(align["iou"], 3), "alignment": align}),
             "proportions": ("PASS" if drift <= BARS["aspect_drift"] else "FAIL", {"aspect_ref": round(float(r_asp), 3), "aspect_gen": round(float(g_asp), 3), "drift": round(float(drift), 3)})}
    gray = G2.aligned_array(np.array(Image.open(candidate_path).convert("L").resize((ref.shape[1], ref.shape[0]), Image.LANCZOS)).astype(float), align, ref.shape)
    inner = ref & al
    from scipy.ndimage import binary_erosion
    inner = binary_erosion(inner, iterations=6)   # keep the instrument off the outline
    st = measure(gray, inner, meta["expected_px"]["cable_column_pitch"], meta["expected_px"]["crossing_period"], column_mask=(regions == meta["regions"]["cable_column"]))
    items["cable_identity"] = (st["identity"], {k: st.get(k) for k in ("column_pitch_px", "column_peak", "crossing_period_px", "crossing_peak", "column_dominance", "pitch_ratio", "tests", "failed")})
    items["cable_gauge"] = (st.get("gauge", {}).get("status", "UNKNOWN"), {**st.get("gauge", {}), "expected_px": meta["expected_px"]})
    status = "FAIL" if any(s == "FAIL" for s, _ in items.values()) else ("UNKNOWN" if any(s == "UNKNOWN" for s, _ in items.values()) else "PASS")
    return {"status": status, "items": {k: {"status": s, "evidence": e} for k, (s, e) in items.items()}}


def expectations(refv: str = "ref") -> dict:
    """Product Truth's expectations as the reader will see them in this presentation. The
    columns run up the rows (along the throw's 129 cm length) in every version; the reader
    answers the direction RELATIVE TO THE PIECE'S LONGER SIDE AS SHOWN, so in the folded view
    (the visible half is 90 wide x 64 tall) the same columns run across the longer side.
    Found by round 4 (draws 11-13), which the first expectation mis-read; the readings did
    not change, the expectation was corrected to what Product Truth says for that view."""
    ex = dict(EXPECT)
    try:
        meta = json.load(open(os.path.join(OUT, f"{refv}_meta.json")))
        if meta["conventions_DECLARED"].get("folded") and meta["dimensions_cm"]["width"] > meta["dimensions_cm"]["height"]:
            ex["cable_direction"] = ({"across_the_width"}, True)
    except FileNotFoundError: pass
    return ex


def properties(answers: dict, reference_answers: dict | None = None, refv: str = "ref") -> dict:
    out = {}
    for key, (accept, material) in expectations(refv).items():
        got = answers.get(key); seen = None if reference_answers is None else (key in reference_answers)
        if got is None: out[key] = {"status": "UNKNOWN", "got": None, "why": "not visible to the reader", "material": material}; continue
        if key == "extra_features":
            feats = set() if (not got or got == ["none"] or got == "none") else set(map(str, got if isinstance(got, list) else [got])); ok = feats <= accept; got = sorted(feats) or "none"
        else: ok = got in accept
        out[key] = {"status": "PASS" if ok else "FAIL", "got": got, "expected": sorted(map(str, accept)), "material": material, "reader_saw_it_on_reference": seen}
    return out


def verdict(det, props, judge_items):
    v = G1.verdict(det, props, judge_items)
    det_unknown = [k for k, x in det.get("items", {}).items() if x["status"] == "UNKNOWN"]
    if v["status"] == "PASS" and det_unknown: v["status"] = "UNKNOWN"
    v["unknown_deterministic"] = det_unknown
    v["rule"] = "PASS only when every material property, every deterministic measure (silhouette, proportions, cable identity, cable gauge) and every judge item PASS; any material FAIL is FAIL; UNKNOWN never passes"
    return v


# ---------------------------------------------------------------- self-test
def selftest():
    res = {}
    ref = np.array(Image.open(os.path.join(OUT, "ref_flatlay.png")).convert("L")).astype(float); mask = np.array(Image.open(os.path.join(OUT, "ref_mask.png"))) > 127
    meta = json.load(open(os.path.join(OUT, "ref_meta.json"))); regions = np.array(Image.open(os.path.join(OUT, "ref_regions.png"))); ce, xe = meta["expected_px"]["cable_column_pitch"], meta["expected_px"]["crossing_period"]
    cols = regions == meta["regions"]["cable_column"]
    res["reference"] = measure(ref, mask, ce, xe, column_mask=cols)
    res["reference_without_column_map"] = measure(ref, mask, ce, xe)
    res["reference_rotated_quarter_turn(must_fail)"] = measure(np.rot90(ref), np.rot90(mask), ce, xe)
    # 2x scale: the reference upsampled -> identity should hold, gauge must fail
    res["reference_2x_scale(gauge_must_fail)"] = measure(zoom(ref, 2, order=1), zoom(mask.astype(float), 2, order=0) > 0.5, ce, xe)
    # plain fabric control: rows of single crochet drawn with Bench2's hdc drawer at the same cell scale
    sys.path.insert(0, os.path.join(ROOT, "research", "bench2")); import star_identity as SI
    H, W = 900, 700; cell = meta["cell_px"]
    res["control_plain_rows(must_fail)"] = measure(np.array(SI.draw_hdc_fabric(W, H, cell[0], cell[1]).convert("L")).astype(float), np.ones((H, W), bool), ce, xe)
    res["control_star_truth(must_fail)"] = measure(np.array(SI.draw_star_fabric(W, H, 18.4, 33.1).convert("L")).astype(float), np.ones((H, W), bool), ce, xe)
    b1 = os.path.join(ROOT, "research", "bench1", "out")
    if os.path.exists(os.path.join(b1, "ref3_regions.png")):
        reg = np.array(Image.open(os.path.join(b1, "ref3_regions.png"))); g = np.array(Image.open(os.path.join(b1, "ref3_flatlay.png")).convert("L")).astype(float)
        res["control_bench1_waffle_reference(must_fail)"] = measure(g, reg == 2, ce, xe)
    return res


if __name__ == "__main__":
    r = selftest(); json.dump({"bars": BARS, "why": WHY, "results": r}, open(os.path.join(OUT, "cable_identity_selftest.json"), "w"), indent=1)
    for k, v in r.items():
        print(f"{k:48s} identity {v.get('identity'):7s} gauge {(v.get('gauge') or {}).get('status', '-'):7s} | col {v.get('column_pitch_px')} ({v.get('column_peak')}) cross {v.get('crossing_period_px')} ({v.get('crossing_peak')}) dom {v.get('column_dominance')} ratio {v.get('pitch_ratio')} failed {v.get('failed')}")
