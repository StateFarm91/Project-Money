"""
Commercial benchmark 2, phase 2: the star-stitch identity and gauge instrument.

What star stitch IS, from the purchased pattern's own stitch definitions (p6-7): a two-row
repeat. In the star row each star closes its loops into one EYE and spans two stitches of
the row below; the return row works two hdc into every eye. The next star row's stars are
worked into the two hdc over each eye, so each new eye forms over the eye below, shifted by
about half an hdc (a quarter star) in the working direction, which alternates every row pair.
The visible signature is therefore the LATTICE OF EYES: dark round holes at the star pitch
along the row, the next star row one row pair across with the eyes stacked in near-vertical
columns (small alternating offset), a thin return row of hdc between star rows, and the five
legs of each star fanning into its eye.

The instrument measures, on a fabric region:
  1. an isotropic-dark-blob map (Hessian; lines, posts and valleys are rejected) and its
     autocorrelation: the along-row fundamental a (star pitch) and the across-row lattice
     basis (row pair); the shortest well-fitting lattice vector decides the column offset;
  2. column offset <= 0.30 star (a checker -- seed, waffle, bobble -- is half a star over);
  3. star pitch / row pair in the band derived from the gauge (0.556 +- 30 %);
  4. the blobs' isotropy (holes, not bars);
  5. the diagonal share of gradient energy (fans; plain hdc rows and grids fail);
  6. return-row contrast: across-row edge energy folded by the pair concentrates in one band;
  7. gauge: measured pitch and pair against the expected pitches, +-35 %.
Bars are fixed a priori and named in BARS/WHY; `selftest()` runs the instrument on the
deterministic truth, on deliberately wrong textures and on the designer's photographs, and
reports what it did. Thresholds were not moved to make anything pass; what changed on the
evidence of the photographs was the MODEL of the stitch (see FIRST_DESIGN_NOTE and the truth
fabric's docstring), which is recorded.

Operating envelope (stated before use): a flat fabric region, rows within about 30 degrees of
horizontal, at least six stars across and four row pairs down, eyes resolved at 1.5 px or more
(regions from small photographs are upscaled x2 first). Worn, curved or foreshortened fabric is
outside it and reads FAIL or UNKNOWN, never PASS by accident.
"""
from __future__ import annotations
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, sobel, zoom
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")

BARS = {"row_pair_scale": 0.35, "star_pitch_scale": 0.35, "pitch_over_pair": (0.39, 0.72), "lattice_peak": 0.10, "column_offset": 0.30, "blob_isotropy": 0.55, "diagonal_fraction": 0.30, "return_row_contrast": 1.25}
WHY = {"row_pair_scale": "CHOSEN: +-35 %, the same generator-fuzz tolerance Bench1 used for stitch scale",
       "star_pitch_scale": "CHOSEN: +-35 %, as above",
       "pitch_over_pair": "DERIVED: a star spans 2 sts (2 x 4/18 in) and a row pair spans 2 rows (2 x 4/10 in): 0.556, accepted +-30 %",
       "lattice_peak": "CHOSEN a priori: the eye map's normalised autocorrelation must show the along-row peak (star pitch) and the next-star-row peak at >= 0.10 of the origin",
       "column_offset": "DERIVED from the stitch: each star of the next row is worked into the two hdc that sit over one eye, so its eye forms over that eye shifted by about half an hdc (a quarter star) in the working direction, alternating each row pair; the eyes stack in near-vertical columns. Accepted |offset| <= 0.30 star. A half-star offset is a checker (seed, waffle, bobble lattices) and fails",
       "blob_isotropy": "CHOSEN a priori: the detected dark features must be round holes (curvature ratio >= 0.55 on average), not bars, posts or valleys",
       "diagonal_fraction": "CHOSEN a priori: the five legs of each star fan into the eye, so at least 0.30 of gradient energy lies 20-70 degrees off the row direction; plain hdc rows (posts and row lines) and ribbed/waffle grids sit near 0 and 90 degrees",
       "return_row_contrast": "DERIVED from the stitch: every row pair has a thin return row of hdc between the star rows, so across-row edge energy folded by the pair must concentrate in one phase band (peak bin >= 1.25 x the mean of 8 bins). Bump lattices (seed, bobble, puff) with the same eye lattice have no such row"}
FIRST_DESIGN_NOTE = ("A first design measured alternation of along-row frequency (star rows repeat per star, return rows per stitch) and then of texture "
                     "energy between half-bands. Both passed the deterministic truth and failed on every real photograph of the fabric: in a photograph the two "
                     "hdc of a return row group under their eye and repeat per star, and the thin return row has strong edges. The signature that survives "
                     "real fabric is the eye lattice. The first truth fabric also stacked the star rows half a star apart; the stitch mechanics and the "
                     "flat-lay photographs (offset 0.03-0.20 star) say the eyes stack in near-vertical columns, and the half-offset fabric is now a control. "
                     "Recorded so the next stitch instrument starts from lattice geometry and the stitch mechanics, not from row-frequency reasoning.")


# ---------------------------------------------------------------- deterministic star fabric
def draw_star_fabric(w_px, h_px, star_px, pair_px, yarn=(232, 219, 196), shade=(178, 160, 136), dark=(140, 122, 102), phase=0.0, seed=0, column_offset=0.15):
    """A star-stitch fabric at the given pitches. Each star: five thick loops rising from the
    base points to one eye (a small dark hole at the top centre), which reads as a rounded puff;
    a thin return row of half-double posts (two per star) between the star rows. Each star of
    the next row is worked into the two hdc over one eye, so the eyes stack in near-vertical
    columns with a small offset (about a quarter star) that alternates with the working
    direction. (A first version stacked them with a half-star offset; the designer's flat-lay
    photographs measure the offset at 0.07-0.22 star, and the stitch mechanics say why.)"""
    img = Image.new("RGB", (w_px, h_px), yarn); d = ImageDraw.Draw(img)
    rows = int(np.ceil(h_px / pair_px)) + 1; star_h = pair_px * 0.62; hdc_h = pair_px - star_h
    lw = max(2, int(star_px * 0.16)); light = tuple(min(255, int(c * 1.06)) for c in yarn)
    for r in range(rows):
        y_top = r * pair_px + phase * pair_px; off = (column_offset * star_px) if r % 2 else 0.0
        for c in range(int(w_px / star_px) + 2):
            cx = c * star_px + off; eye = (cx, y_top + star_h * 0.20); base_y = y_top + star_h * 0.98
            for bx in (cx - star_px * 0.50, cx - star_px * 0.25, cx, cx + star_px * 0.25, cx + star_px * 0.50):
                # a loop: a bowed stroke from the base to the eye. The outer legs meet the neighbouring
                # stars' outer legs at the shared base points (the first leg of a star is worked into the
                # previous star's eye); legs of adjacent stars never cross.
                mid = ((bx + cx) / 2 + (bx - cx) * 0.30, (base_y + eye[1]) / 2 + star_h * 0.12)
                d.line([(bx, base_y), mid, eye], fill=shade, width=lw, joint="curve")
                d.line([(bx, base_y), mid, eye], fill=light, width=max(1, lw // 3), joint="curve")
            d.ellipse([cx - star_px * 0.10, eye[1] - star_px * 0.08, cx + star_px * 0.10, eye[1] + star_px * 0.08], fill=dark)
        y0 = y_top + star_h
        d.rectangle([0, y0, w_px, y0 + hdc_h], fill=yarn)
        for c in range(int(w_px / (star_px / 2)) + 2):
            px = c * star_px / 2 + off + star_px * 0.25
            d.line([(px, y0), (px, y0 + hdc_h)], fill=shade, width=max(1, int(star_px * 0.07)))
        d.line([(0, y0), (w_px, y0)], fill=dark, width=1)
    return img


def draw_hdc_fabric(w_px, h_px, st_px, row_px, yarn=(232, 219, 196), shade=(178, 160, 136), dark=(140, 122, 102)):
    img = Image.new("RGB", (w_px, h_px), yarn); d = ImageDraw.Draw(img)
    for r in range(int(h_px / row_px) + 1):
        y0 = r * row_px
        for c in range(int(w_px / st_px) + 1):
            d.line([(c * st_px, y0), (c * st_px, y0 + row_px)], fill=shade, width=max(1, int(st_px * 0.15)))
        d.line([(0, y0), (w_px, y0)], fill=dark, width=1)
    return img


def draw_seed_fabric(w_px, h_px, st_px, row_px, yarn=(232, 219, 196), shade=(178, 160, 136)):
    img = Image.new("RGB", (w_px, h_px), yarn); d = ImageDraw.Draw(img)
    for r in range(int(h_px / row_px) + 1):
        for c in range(int(w_px / st_px) + 1):
            if (r + c) % 2: d.ellipse([c * st_px, r * row_px, (c + 1) * st_px, (r + 1) * row_px], fill=shade)
    return img


def draw_knit_fabric(w_px, h_px, st_px, row_px, yarn=(232, 219, 196), shade=(178, 160, 136)):
    img = Image.new("RGB", (w_px, h_px), yarn); d = ImageDraw.Draw(img)
    for r in range(int(h_px / row_px) + 1):
        for c in range(int(w_px / st_px) + 1):
            x, y = c * st_px, r * row_px
            d.line([(x, y), (x + st_px / 2, y + row_px)], fill=shade, width=max(1, int(st_px * 0.12)))
            d.line([(x + st_px, y), (x + st_px / 2, y + row_px)], fill=shade, width=max(1, int(st_px * 0.12)))
    return img


# ---------------------------------------------------------------- measurement
def _hp(gray, sigma):
    return gray - gaussian_filter(gray, sigma)


def dominant_period(signal, pmin, pmax):
    """Dominant period of a 1-D signal between pmin and pmax px, by FFT power."""
    s = signal - signal.mean(); n = len(s)
    if n < 8: return None
    F = np.abs(np.fft.rfft(s * np.hanning(n))) ** 2; freqs = np.fft.rfftfreq(n)
    with np.errstate(divide="ignore"):
        periods = np.where(freqs > 0, 1.0 / np.maximum(freqs, 1e-9), np.inf)
    sel = (periods >= pmin) & (periods <= pmax)
    if not sel.any(): return None
    k = np.argmax(np.where(sel, F, -1)); return float(periods[k])


def eye_map(gray, sigma):
    """Dark, isotropic blobs (the eyes of the stars) by the Hessian at scale sigma: a local
    minimum of the smoothed image whose two curvatures are both positive and similar. Lines and
    ridges (posts, bars, the valleys of a knit) have one curvature near zero and are rejected."""
    from scipy.ndimage import gaussian_filter as gf
    g = gray.astype(float); hxx = gf(g, sigma, order=(0, 2)); hyy = gf(g, sigma, order=(2, 0)); hxy = gf(g, sigma, order=(1, 1))
    det = hxx * hyy - hxy ** 2; tr = hxx + hyy
    lam1 = tr / 2 + np.sqrt(np.maximum((hxx - hyy) ** 2 / 4 + hxy ** 2, 0)); lam2 = tr / 2 - np.sqrt(np.maximum((hxx - hyy) ** 2 / 4 + hxy ** 2, 0))
    iso = np.where(lam1 > 1e-9, lam2 / lam1, 0.0)   # 1 = perfectly round hole, 0 = a line
    score = np.where((lam2 > 0) & (iso > 0.35), det, 0.0)
    return score, iso


def autocorr_peaks(m, min_lag=3, top=12):
    """Off-origin peaks of the normalised autocorrelation of a map, as (dx, dy, value)."""
    m = m - m.mean(); F = np.fft.fft2(m); A = np.real(np.fft.ifft2(np.abs(F) ** 2)); A0 = max(float(A[0, 0]), 1e-9); A = np.fft.fftshift(A) / A0
    H, W = A.shape; cy, cx = H // 2, W // 2
    from scipy.ndimage import maximum_filter
    loc = (A == maximum_filter(A, size=7)) & (A > 0.02)
    yy, xx = np.nonzero(loc); vals = A[yy, xx]; peaks = []
    for y, x, v in sorted(zip(yy, xx, vals), key=lambda t: -t[2]):
        dx, dy = x - cx, y - cy
        if abs(dx) < min_lag and abs(dy) < min_lag: continue
        if dy < 0 or (dy == 0 and dx < 0): continue   # keep one half-plane
        peaks.append((int(dx), int(dy), float(v)))
        if len(peaks) >= top: break
    return peaks


def diagonal_fraction(g, row_angle_deg, sigma=1.0):
    """Fraction of gradient energy 20-70 degrees off the row direction (either sign)."""
    from scipy.ndimage import gaussian_filter as gf
    gx = gf(g, sigma, order=(0, 1)); gy = gf(g, sigma, order=(1, 0)); E = gx ** 2 + gy ** 2
    th = (np.degrees(np.arctan2(gy, gx)) - row_angle_deg) % 180
    d = E[((th >= 20) & (th < 70)) | ((th > 110) & (th <= 160))].sum()
    return float(d / max(E.sum(), 1e-9))


def return_row_contrast(g, row_angle_deg, pair_px, sigma=1.0, bins=8):
    """The return row is a thin row of hdc between star rows: across-row edge energy, averaged
    along the rows and folded by the row pair, concentrates in one phase band. Reported as the
    peak phase bin over the mean of the bins (1.0 = no row structure)."""
    from scipy.ndimage import gaussian_filter as gf, rotate
    gr = rotate(g, row_angle_deg, reshape=False, order=1, mode="reflect")
    gy = gf(gr, sigma, order=(1, 0)); E = gy ** 2
    H, W = E.shape; m = int(0.15 * min(H, W)); E = E[m:H - m, m:W - m]   # drop the rotated border
    prof = E.mean(axis=1); ph = ((np.arange(prof.size) / pair_px) % 1.0 * bins).astype(int)
    fold = np.array([prof[ph == b_].mean() if (ph == b_).any() else 0.0 for b_ in range(bins)])
    return float(fold.max() / max(fold.mean(), 1e-9))


def lattice(peaks, min_peak):
    """From autocorrelation peaks pick the row basis a (along-row fundamental) and the
    next-star-row basis b (the fundamental across the rows: the shortest of the strong
    across-row peaks, so two row pairs are never mistaken for one). Returns None when the
    row basis is missing."""
    strong = [pk for pk in peaks if pk[2] >= min_peak]
    row = [pk for pk in strong if pk[0] != 0 and abs(pk[1]) <= 0.6 * abs(pk[0])]   # rows tilted up to ~30 degrees
    if not row: return None
    row = [((pk[0], pk[1], pk[2]) if pk[0] > 0 else (-pk[0], -pk[1], pk[2])) for pk in row]
    vmax_row = max(t[2] for t in row)
    a = min([t for t in row if t[2] >= 0.6 * vmax_row], key=lambda t: np.hypot(t[0], t[1]))   # the fundamental: shortest strong along-row peak
    la = float(np.hypot(a[0], a[1])); ah = np.array([a[0], a[1]]) / la; n = np.array([-ah[1], ah[0]])
    if n[1] < 0: n = -n
    across = []
    allpk = [(q[0], q[1], q[2]) for q in peaks]
    def peak_value(x, y, tol):
        vals = [qv for qx, qy, qv in allpk if abs(qx - x) <= tol and abs(qy - y) <= tol]
        return max(vals) if vals else 0.0
    for pk in strong:
        v = np.array([pk[0], pk[1]], float); t = float(v @ ah) / la; s_ = float(v @ n) / la
        if s_ >= 0.8:
            # Lattice fit of a candidate b: peaks at i*a + j*b, j = 1, 2. The eye rows zigzag (the
            # offset alternates with the working direction) so for j = 2 the column-aligned double
            # 2 s n counts as well. The return row's gap family (half a star over, part of a pair up)
            # has no double and scores low; a harmonic 2b scores below b because 4b is weak or absent.
            c = 2 * s_ * la * n
            fit = sum(peak_value(i * a[0] + pk[0], i * a[1] + pk[1], 0.15 * la) for i in (-1, 0, 1))
            fit += sum(max(peak_value(i * a[0] + 2 * pk[0], i * a[1] + 2 * pk[1], 0.15 * la), peak_value(i * a[0] + c[0], i * a[1] + c[1], 0.15 * la)) for i in (-1, 0, 1))
            t = ((t + 0.5) % 1.0) - 0.5
            across.append((pk, t, s_, fit))
    base = {"a": a, "a_len": la, "row_angle_deg": float(np.degrees(np.arctan2(a[1], a[0]))), "b": None}
    if not across: return base
    fmax = max(z[3] for z in across); good = sorted([z for z in across if z[3] >= 0.8 * fmax], key=lambda z: z[2])
    # The shortest well-fitting basis decides the column offset (a checker's shortest basis is half
    # a star over). In a photograph the gaps between the two hdc over each eye add a second blob
    # row directly above the eyes, so the row pair is the shortest well-fitting basis at least
    # 1 / 0.72 = 1.39 stars across the rows (the pitch-over-pair band).
    b0, t0, s0, f0 = good[0]
    pairs = [z for z in good if z[2] >= 1 / BARS["pitch_over_pair"][1]]
    if not pairs:
        base.update({"b": None, "shortest": b0, "offset_star": t0}); return base
    b, t, s_, fit = pairs[0]
    base.update({"b": b, "shortest": b0, "offset_star": (t if abs(t) >= abs(t0) else t0), "pair_len": s_ * la, "lattice_fit": fit}); return base


def measure(gray, star_px_expected=None, pair_px_expected=None, mask=None, upscale=None):
    """gray: a fabric region, rows roughly horizontal (tilt up to ~20 degrees is found). Star
    identity is the lattice of the stars' eyes: dark round holes repeating at the star pitch
    along the row, the next star row one row pair across with the eyes stacked in near-vertical
    columns; the legs of each star fan into its eye. Measured on the autocorrelation of an
    isotropic-dark-blob map plus the gradient-orientation distribution. Gauge: the measured
    star pitch and row pair against the expected pitches."""
    g = gray.astype(float)
    if upscale and upscale != 1: g = zoom(g, upscale, order=1)
    if mask is not None:
        mk = zoom(mask.astype(float), upscale, order=0) > 0.5 if upscale and upscale != 1 else mask
        g = np.where(mk, g, np.nan); g = np.where(np.isnan(g), np.nanmean(g), g)
    u = upscale or 1
    from scipy.ndimage import gaussian_filter as _gf
    def at_sigma(sg):
        score, iso = eye_map(g, sg); thr = np.quantile(score, 0.97); B = (score >= thr) & (score > 0)
        # weighted blob map: the eyes are the largest, darkest holes, so they dominate the
        # autocorrelation over the smaller gaps of the return row; smoothed so a quarter-star
        # column offset still correlates
        Wm = np.where(score >= np.quantile(score, 0.90), score, 0.0); Wm = Wm / max(Wm.max(), 1e-9)
        peaks = autocorr_peaks(_gf(Wm, sg), top=60)
        L = lattice(peaks, 0.5 * BARS["lattice_peak"])
        if L is None: return None
        return {"sigma": sg, "L": L, "blob_isotropy": float(np.mean(iso[B])) if B.any() else 0.0, "peaks": [(int(a), int(b), round(c, 3)) for a, b, c in peaks[:8]]}
    # pass 1: the row pitch, from whichever blob scale shows it most strongly
    sweep = [c for c in (at_sigma(sg) for sg in (2.5, 3.5, 5.0)) if c]
    if not sweep: return {"status": "UNKNOWN", "why": "no periodic blob lattice found", "identity": "UNKNOWN"}
    pitch = max(sweep, key=lambda c: c["L"]["a"][2])["L"]["a_len"]
    # pass 2: everything at the eye scale of that pitch (an eye is about a tenth of a star across)
    best = at_sigma(max(1.5, 0.10 * pitch))
    if best is None: return {"status": "UNKNOWN", "why": "no periodic blob lattice found", "identity": "UNKNOWN"}
    L = best["L"]; a_len = L["a_len"] / u; pair = (L["pair_len"] / u) if L["b"] else None
    ratio = (a_len / pair) if pair else None
    diag = diagonal_fraction(g, L["row_angle_deg"], sigma=1.0 * u)
    rrc = return_row_contrast(g, L["row_angle_deg"], L["pair_len"], sigma=1.0 * u) if L["b"] else None
    out = {"star_pitch_px": round(a_len, 2), "row_pair_px": round(pair, 2) if pair else None, "pitch_over_pair": round(ratio, 3) if ratio else None,
           "row_peak": round(L["a"][2], 3), "next_row_peak": round(L["b"][2], 3) if L["b"] else 0.0, "column_offset_star": round(abs(L["offset_star"]), 3) if "offset_star" in L else None,
           "row_angle_deg": round(L["row_angle_deg"], 1), "blob_isotropy": round(best["blob_isotropy"], 3), "diagonal_fraction": round(diag, 3), "return_row_contrast": round(rrc, 3) if rrc else None, "eye_sigma": best["sigma"], "peaks": best["peaks"]}
    tests = {"row_peak": out["row_peak"] >= BARS["lattice_peak"], "next_row_peak": out["next_row_peak"] >= BARS["lattice_peak"],
             "column_offset": (out["column_offset_star"] is not None and out["column_offset_star"] <= BARS["column_offset"]),
             "pitch_over_pair": (ratio is not None and BARS["pitch_over_pair"][0] <= ratio <= BARS["pitch_over_pair"][1]),
             "blob_isotropy": out["blob_isotropy"] >= BARS["blob_isotropy"], "diagonal_fraction": diag >= BARS["diagonal_fraction"], "return_row_contrast": (rrc is not None and rrc >= BARS["return_row_contrast"])}
    out["tests"] = tests; out["identity"] = "PASS" if all(tests.values()) else "FAIL"; out["failed"] = [k for k, v in tests.items() if not v]
    if star_px_expected and pair_px_expected and pair:
        rs, ss = pair / pair_px_expected, a_len / star_px_expected
        out["gauge"] = {"row_pair_ratio": round(rs, 3), "star_pitch_ratio": round(ss, 3), "status": "PASS" if abs(rs - 1) <= BARS["row_pair_scale"] and abs(ss - 1) <= BARS["star_pitch_scale"] else "FAIL"}
    elif star_px_expected:
        out["gauge"] = {"status": "UNKNOWN", "why": "no row pair measured"}
    out["status"] = out["identity"] if "gauge" not in out else ("PASS" if out["identity"] == "PASS" and out["gauge"]["status"] == "PASS" else ("UNKNOWN" if out["gauge"]["status"] == "UNKNOWN" and out["identity"] == "PASS" else "FAIL"))
    return out


def region_gray(path, box=None, resize_to=None):
    im = Image.open(path).convert("L")
    if resize_to: im = im.resize(resize_to, Image.LANCZOS)
    if box: im = im.crop(box)
    return np.array(im).astype(float)


# ---------------------------------------------------------------- self-test
def selftest(star_px=24.0, pair_px=43.0, private_photos=None):
    """Deterministic truth, wrong controls, and (privately) real photographs. Returns every
    reading; nothing here adjusts a bar."""
    W_, H_ = 480, 400; res = {}
    truth = draw_star_fabric(W_, H_, star_px, pair_px); res["truth_star"] = measure(np.array(truth.convert("L")).astype(float), star_px, pair_px)
    res["truth_star_phase"] = measure(np.array(draw_star_fabric(W_, H_, star_px, pair_px, phase=0.37).convert("L")).astype(float), star_px, pair_px)
    res["truth_star_2x_scale(gauge_must_fail)"] = measure(np.array(draw_star_fabric(W_, H_, star_px * 2, pair_px * 2).convert("L")).astype(float), star_px, pair_px)
    res["control_star_half_offset(first_model)"] = measure(np.array(draw_star_fabric(W_, H_, star_px, pair_px, column_offset=0.5).convert("L")).astype(float), star_px, pair_px)
    res["control_hdc_rows"] = measure(np.array(draw_hdc_fabric(W_, H_, star_px / 2, pair_px / 2).convert("L")).astype(float), star_px, pair_px)
    res["control_seed"] = measure(np.array(draw_seed_fabric(W_, H_, star_px / 2, pair_px / 2).convert("L")).astype(float), star_px, pair_px)
    res["control_knit"] = measure(np.array(draw_knit_fabric(W_, H_, star_px / 2, pair_px / 2).convert("L")).astype(float), star_px, pair_px)
    # waffle: Bench1's deterministic reference (front-left panel), at its own scale -> identity must fail
    b1 = os.path.join(os.path.dirname(HERE), "bench1", "out")
    if os.path.exists(os.path.join(b1, "ref3_regions.png")):
        reg = np.array(Image.open(os.path.join(b1, "ref3_regions.png"))); ys, xs = np.nonzero(reg == 2)
        g = region_gray(os.path.join(b1, "ref3_flatlay.png"), (xs.min(), ys.min(), xs.max(), ys.max()))
        res["control_bench1_waffle_reference"] = measure(g)
        hero = os.path.join(b1, "gen", "oa15_hifi_10.png")
        if os.path.exists(hero):
            res["control_bench1_hero_photo(seed-like)"] = measure(region_gray(hero, (xs.min(), ys.min(), xs.max(), ys.max()), resize_to=(1536, 1024)))
    for name, (path, box) in (private_photos or {}).items():
        if os.path.exists(path): res[f"real_photo:{name}"] = measure(region_gray(path, box), upscale=2)
    return res


if __name__ == "__main__":
    S = "/tmp/claude-0/-home-user-Project-Money/0aa334b9-5ba9-5fd2-9058-e50b4b8604ea/scratchpad/bench2/pdf_images"
    private = {"cover_flatlay_brown_right": (os.path.join(S, "p1_0_X0.jpg"), (630, 400, 740, 530)), "cover_flatlay_brown_left": (os.path.join(S, "p1_0_X0.jpg"), (410, 400, 570, 530)),
               "cover_flatlay_cream_right": (os.path.join(S, "p1_0_X0.jpg"), (560, 770, 720, 900)), "cover_flatlay_cream_left": (os.path.join(S, "p1_0_X0.jpg"), (360, 780, 470, 900)),
               "gallery_baby_worn_body": (os.path.join(S, "p13_2_X63.jpg"), (320, 360, 440, 480)), "gallery_toddler_worn_body": (os.path.join(S, "p13_0_X61.jpg"), (300, 330, 400, 470))}
    r = selftest(private_photos=private); os.makedirs(OUT, exist_ok=True)
    json.dump({"bars": BARS, "why": WHY, "results": r}, open(os.path.join(OUT, "star_identity_selftest.json"), "w"), indent=1)
    for k, v in r.items():
        print(f"{k:42s} identity {v.get('identity'):7s} gauge {v.get('gauge', {}).get('status') if isinstance(v.get('gauge'), dict) else '-':7s} | star {v.get('star_pitch_px')} pair {v.get('row_pair_px')} p/p {v.get('pitch_over_pair')} row {v.get('row_peak')} next {v.get('next_row_peak')} off {v.get('column_offset_star')} iso {v.get('blob_isotropy')} diag {v.get('diagonal_fraction')} rrc {v.get('return_row_contrast')} failed {v.get('failed')}")
