"""Independent product-fidelity verifier for GENERATED images (W-FIDELITY; OWNERIMG E3).

A generated product image is a claim that the pixels show what the certified pattern makes.
This module checks that claim against the certified CIR and nothing else. It never reads the
prompt, the generator's receipt, the references or the generator's own verdict.

**Deterministic first.** The product-only anchor is the unfolded flat lay of
`image_stages.product_only` (stage 3), and it is measured here:

  isolation      the product is separated from a plain background (a plane fitted to the
                 border ring); a cluttered, cropped or low-contrast background is UNKNOWN.
  piece_count    connected pieces against the CIR's `make` total (WRONG_PIECE_COUNT).
  flat/unfolded  each flat piece fills its minimum-area rectangle; a fold, a turned corner
                 or a cut-out occlusion leaves it short (UNKNOWN; never measured through).
  aspect         rectified long/short against the digital twin's centimetres
                 (WRONG_ASPECT_RATIO).
  palette        cluster colours against the CIR's declared hexes after a bounded
                 illumination correction; a structured extra colour is OFF_PALETTE_COLOUR,
                 an unexplained colour region is UNKNOWN.
  colour_layout  per-row colour profile against the CIR's own fabric render, which places
                 every band, stripe and colour change (WRONG_COLOUR_LAYOUT).
  end_bands      every plain end band the CIR declares (rows, colour) must be solid and the
                 right width (INVENTED_END_BAND_TREATMENT).
  edges          the row-end strips the CIR declares plain must look like the CIR's own
                 row ends, not like a border (INVENTED_EDGING).
  repeat_count   the period along the axis the CIR declares repeats on (motif repeats, cable
                 columns) by autocorrelation; low confidence is UNVERIFIABLE_COUNT (UNKNOWN).
                 The estimator is first run on the CIR's own render: if it cannot recover the
                 declared count there, it is not qualified for this product and reads UNKNOWN.

**Vision second.** Craft texture (crochet vs knitting, ribbing) is not reliably measurable
from pixels, so it is a question for the vision judge (`image_vision`). The judge is asked
what it sees, never shown the claim, and this module compares (the `visual.inspect` rule).
Unfunded or unread is UNKNOWN, and UNKNOWN blocks. A FAIL reading is WRONG_CRAFT_TEXTURE.

**Lifestyle images** cannot be rectified. They need (i) a PASS anchor for the same release,
(ii) a palette check inside a declared product region, and (iii) a vision consistency
reading against the anchor. Anything missing is UNKNOWN.

Every check returns PASS / FAIL / UNKNOWN with the values it measured. The verdict is the
worst check. UNKNOWN is never PASS, and a PASS never carries a failure code.

What this verifier cannot see is written down in `research/final_build/w4/FIDELITY.md`
("false-pass risk"); the short version is in `BLIND_SPOTS`.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from dataclasses import dataclass, field

import numpy as np

from ..creative import failure_codes as FC

VERIFIER_VERSION = "product-fidelity/1.0.0"
CHECKER = f"visual.fidelity {VERIFIER_VERSION}"
PASS, FAIL, UNKNOWN, NA = "PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"

# ---- failure codes ------------------------------------------------------------------------
# The four shared codes come from the one constant (creative.failure_codes). The five below
# are new. W-VISAUTO owns failure_codes.py right now, so they live here until it folds them
# in; `ALL_CODES` is the union and nothing here redefines a shared code.
WRONG_ASPECT_RATIO = "WRONG_ASPECT_RATIO"
OFF_PALETTE_COLOUR = "OFF_PALETTE_COLOUR"
WRONG_COLOUR_LAYOUT = "WRONG_COLOUR_LAYOUT"
WRONG_REPEAT_COUNT = "WRONG_REPEAT_COUNT"
WRONG_PIECE_COUNT = "WRONG_PIECE_COUNT"
LOCAL_CODES: dict[str, dict] = {
    WRONG_ASPECT_RATIO: {
        "category": FC.PRODUCT_FIDELITY,
        "meaning": "the unfolded piece's long/short ratio differs from the digital twin's "
                   "finished centimetres beyond tolerance",
        "countered_by": "the layout reference at true proportion (pattern_refs 'layout')"},
    OFF_PALETTE_COLOUR: {
        "category": FC.PRODUCT_FIDELITY,
        "meaning": "a colour the certified palette does not declare (added or substituted)",
        "countered_by": "prompt negative 'colours not in the certified palette' "
                        "(pattern_refs.PROHIBITED_ADDITIONS)"},
    WRONG_COLOUR_LAYOUT: {
        "category": FC.PRODUCT_FIDELITY,
        "meaning": "colour bands, stripes or colour changes are not where the pattern puts "
                   "them, or a declared colour is missing",
        "countered_by": "prompt negative 'colour changes anywhere except ...' "
                        "(pattern_refs.negatives)"},
    WRONG_REPEAT_COUNT: {
        "category": FC.PRODUCT_FIDELITY,
        "meaning": "a measurable count of motif repeats or cable columns differs from the CIR",
        "countered_by": "prompt negative on cable/motif count (pattern_refs.negatives)"},
    WRONG_PIECE_COUNT: {
        "category": FC.PRODUCT_FIDELITY,
        "meaning": "more or fewer pieces than the CIR makes",
        "countered_by": "prohibited addition 'extra or missing pieces'"},
}
ALL_CODES: frozenset[str] = frozenset(FC.ALL_CODES) | frozenset(LOCAL_CODES)

# ---- tolerances (each stated with its reason; none tuned to pass a frame) -----------------
MAX_SIDE_PX = 1024          # analysis resolution; a 2k flat lay keeps >= 4 px per stitch
BORDER_RING = 0.02          # outer 2 % of the short side models the background
BG_SPREAD_MAX = 10.0        # dE76 p90 of the border ring around its fitted plane
MIN_SEPARATION = 12.0       # dE76 between the background and every declared yarn colour
FG_FRACTION = 0.45          # foreground threshold = 0.45 x that separation (6..20 dE)
MIN_PIECE_AREA = 0.002      # of the image; smaller blobs are noise
MIN_FILL = 0.93             # flat piece area / its minimum-area rectangle
MIN_SOLIDITY = 0.93         # round piece area / its convex hull
ASPECT_REL = 0.10           # flat pieces; round pieces ROUND_ASPECT_REL
ROUND_ASPECT_REL = 0.15
GAIN_RANGE = (0.6, 1.6)     # per-channel illumination correction, linear RGB
CENTRE_DE_MAX = 15.0        # a yarn cluster's centre vs its declared hex, after correction
OFF_PALETTE_DE = 22.0       # a pixel this far from every palette colour (and every mix) is off
OFF_STRIPE_FRAC = 0.5       # a row/column with >= 50 % off-palette pixels is a stripe
OFF_GLOBAL_MAX = 0.03       # unstructured off-palette share above this is UNKNOWN
MISSING_SHARE = 0.25        # a declared colour at < 25 % of its expected share is missing
LAYOUT_TV_MEAN = 0.20       # mean total-variation distance of row colour profiles
LAYOUT_TV_ROW = 0.50        # a row this different is a bad row ...
LAYOUT_BAD_ROWS = 0.08      # ... and at most 8 % of rows may be bad
SHIFT_MAX = 0.02            # row-profile alignment search, of the height
BAND_SOLID = 0.75           # a band row must be >= 75 % band colour
BAND_EXTENT = (0.6, 1.5)    # measured / declared band width
INSET = 0.015               # analysis ignores this much of each rectified edge
EDGE_STRIP = 0.04           # outer row-end strip examined for an edging
EDGE_REF = (0.12, 0.22)     # interior reference strip
EDGE_SCORE = 0.30           # edge strip mismatch above this ...
EDGE_RATIO = 2.0            # ... and above 2x the interior's mismatch + 0.1 is an edging
COUNT_CONF = 0.40           # autocorrelation at the found period
COUNT_FRAC = 0.30           # |count - round(count)|
COUNT_MIN_PX_PER_STITCH = 1.5
LIFESTYLE_ON_PALETTE = 0.60  # share of a declared product region on the palette
LIFESTYLE_EXTRA_CLUSTER = 0.15

TOLERANCES = {
    "background": f"border-ring plane fit, p90 dE76 <= {BG_SPREAD_MAX}; every yarn colour "
                  f">= {MIN_SEPARATION} dE76 from it",
    "flat": f"area >= {MIN_FILL:.0%} of the minimum-area rectangle (round: solidity >= "
            f"{MIN_SOLIDITY:.0%})",
    "aspect": f"+-{ASPECT_REL:.0%} (round pieces +-{ROUND_ASPECT_REL:.0%})",
    "illumination": f"per-channel gain in {GAIN_RANGE} (linear RGB)",
    "palette": f"cluster centre <= {CENTRE_DE_MAX} dE76 after correction; pixel off-palette "
               f"> {OFF_PALETTE_DE} dE76 from every colour and every two-colour mix; a "
               f"row/column >= {OFF_STRIPE_FRAC:.0%} off is a stripe",
    "colour_layout": f"mean row TV <= {LAYOUT_TV_MEAN}, rows with TV > {LAYOUT_TV_ROW} <= "
                     f"{LAYOUT_BAD_ROWS:.0%}, alignment +-{SHIFT_MAX:.0%}",
    "end_bands": f"each band row >= {BAND_SOLID:.0%} band colour; width {BAND_EXTENT} of "
                 f"declared",
    "edges": f"outer {EDGE_STRIP:.0%} mismatch > {EDGE_SCORE} and > {EDGE_RATIO}x interior + 0.1",
    "repeat_count": f"autocorrelation >= {COUNT_CONF}, |count - round| <= {COUNT_FRAC}, "
                    f">= {COUNT_MIN_PX_PER_STITCH} px per stitch; exact count",
}

BLIND_SPOTS = (
    "stitch identity: a knitted, woven or printed fabric in the right colours and layout "
    "passes every deterministic check (that is the vision judge's question)",
    "texture-only features: ribbing, bobbles or an edging worked in the SAME colour with a "
    "texture the row-end luminance profile does not separate",
    "edgings narrower than the 1.5 % inset",
    "row counts: rows are not counted, only the colour profile along the rows",
    "counts along an axis the CIR declares no repeat on, and every count on round pieces "
    "other than the number of pieces",
    "a colour that lies on the line between two palette colours (a mix of them)",
    "anything on the back of the piece",
    "lifestyle images: only palette and consistency, never geometry",
)


def _check(name: str, status: str, why: str, *, code: str | None = None, **measured) -> dict:
    out = {"check": name, "status": status, "why": why, **measured}
    if code and status != PASS:
        out["code"] = code
    return out


def worst(statuses) -> str:
    s = [x for x in statuses if x != NA]
    return FAIL if FAIL in s else UNKNOWN if (UNKNOWN in s or not s) else PASS


# ---- colour ---------------------------------------------------------------------------------

def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = str(h).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lin(rgb: np.ndarray) -> np.ndarray:
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_WHITE = np.array([0.95047, 1.0, 1.08883])


def _lab_from_lin(lin: np.ndarray) -> np.ndarray:
    xyz = lin @ _M.T / _WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def _lab(rgb: np.ndarray) -> np.ndarray:
    return _lab_from_lin(_lin(rgb))


def _de(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((np.asarray(a) - np.asarray(b)) ** 2).sum(axis=-1))


def _hex_of_lin(lin) -> str:
    c = np.clip(np.asarray(lin, dtype=np.float64), 0, 1)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
    r, g, b = (int(round(float(v) * 255)) for v in s)
    return f"#{r:02X}{g:02X}{b:02X}"


def _seg_distance(lab: np.ndarray, pal: np.ndarray) -> np.ndarray:
    """Distance from each colour to the nearest palette colour or two-colour mix."""
    d = _de(lab[..., None, :], pal).min(axis=-1)
    for i in range(len(pal)):
        for j in range(i + 1, len(pal)):
            a, b = pal[i], pal[j]
            ab = b - a
            t = np.clip(((lab - a) * ab).sum(-1) / max(float((ab * ab).sum()), 1e-9), 0, 1)
            d = np.minimum(d, _de(lab, a + t[..., None] * ab))
    return d


# ---- expectation, from the certified CIR ----------------------------------------------------

@dataclass
class PieceModel:
    name: str
    make: int
    round_: bool
    width_cm: float
    height_cm: float
    cols: int
    rows: int
    work: tuple[int, int] = (0, 0)              # (Ww, Hw), flat only
    classes: np.ndarray | None = None           # flat: (Hw, Ww) palette index
    lum: np.ndarray | None = None               # flat: (Hw, Ww) L*
    row_y: list[float] = field(default_factory=list)   # flat: top-down cumulative fractions
    radial: np.ndarray | None = None            # round: (bins, n_palette) shares
    bands: list[dict] = field(default_factory=list)
    repeat: dict | None = None

    @property
    def ratio(self) -> float:
        a, b = float(self.width_cm or 1), float(self.height_cm or 1)
        return max(a, b) / max(min(a, b), 1e-9)


@dataclass
class Expectation:
    slug: str
    version: str
    cir_fingerprint: str
    palette_ids: list[str]
    palette_hex: list[str]
    palette_lab: np.ndarray
    palette_lin: np.ndarray
    pieces: list[PieceModel]
    edging_declared: bool
    ribbing_declared: bool
    craft: str
    expected_share: np.ndarray

    @property
    def piece_count(self) -> int:
        return sum(p.make for p in self.pieces)


_CACHE: dict[str, Expectation] = {}
RADIAL_BINS = 20


def _classify(rgb: np.ndarray, pal_lab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lab = _lab(rgb)
    return _de(lab[..., None, :], pal_lab).argmin(axis=-1), lab[..., 0]


def _flat_model(cir, comp, twin, pal_lab, facts: dict | None, rules: dict) -> PieceModel:
    from PIL import Image

    from ..publish import charts

    cols = max(len(r) for r in twin.chart_grid())
    rows = len(twin.chart_grid())
    w_cm, h_cm = float(twin.width_cm or cols), float(twin.height_cm or rows)
    ppc = max(480.0 / max(w_cm, h_cm), 3.0 * cols / w_cm, 3.0 * rows / h_cm)
    ppc = min(ppc, 900.0 / max(w_cm, h_cm))
    ww, hw = max(16, int(round(w_cm * ppc))), max(16, int(round(h_cm * ppc)))
    cell = 8
    src = np.asarray(charts.render_fabric(cir, twin, cell_px=cell).convert("RGB"),
                     dtype=np.float64)
    hs, ws = src.shape[:2]
    band = hs / rows
    try:  # stitch-weighted row heights, recomputed from the compiler (render_verification)
        from .render_verification import expected_model

        heights = [r["height_cm"] for r in expected_model(cir, comp.name, shape=False)["rows"]]
        if len(heights) != rows:
            raise ValueError("row count differs")
    except Exception:  # noqa: BLE001 - uniform rows when the model cannot say
        heights = [1.0] * rows
    cum = np.concatenate([[0.0], np.cumsum(heights)])
    cum /= cum[-1]
    # target row y (top-down) -> fabric height from the bottom -> source row and position
    yt = (np.arange(hw) + 0.5) / hw
    h_from_bottom = 1.0 - yt
    r = np.clip(np.searchsorted(cum, h_from_bottom, side="right") - 1, 0, rows - 1)
    frac = (h_from_bottom - cum[r]) / np.maximum(cum[r + 1] - cum[r], 1e-12)
    ys = np.clip((hs - (r + frac) * band).astype(int), 0, hs - 1)
    xs = np.clip(((np.arange(ww) + 0.5) / ww * ws).astype(int), 0, ws - 1)
    img = src[ys][:, xs]
    classes, lum = _classify(img, pal_lab)
    model = PieceModel(comp.name, int(getattr(comp, "make", 1) or 1), False, w_cm, h_cm,
                       cols, rows, (ww, hw), classes, lum,
                       row_y=[float(1.0 - c) for c in cum[::-1]])
    if facts is not None:
        for b in facts.get("end_bands") or []:
            lo, hi = b["rows"]
            if hi - lo + 1 < 3 or b["colour"] not in (cir.colors or {}):
                continue  # a 1-2 row band is inside the layout tolerance; checked there
            y_top, y_bot = 1.0 - cum[hi], 1.0 - cum[lo - 1]
            model.bands.append({"rows": [lo, hi], "colour": b["colour"],
                                "colour_index": list(cir.colors).index(b["colour"]),
                                "y": [float(y_top), float(y_bot)],
                                "row_px": float((y_bot - y_top) * hw / (hi - lo + 1)),
                                "outer": "top" if hi == rows else "bottom"})
        cab = facts.get("cables")
        if cab and cab.get("columns", 0) >= 2:
            from ..cir import stitches as taxonomy

            st = taxonomy.get(cab["stitch"])
            period = st.consumes + (cab["separated_by"][0] if cab["separated_by"] else 0)
            x0 = cab["edge_stitches"][0] / cols
            model.repeat = {"what": "cable columns", "n": int(cab["columns"]),
                            "x": [x0, min(1.0, x0 + cab["columns"] * period / cols)]}
    rep = rules.get("repeat") or {}
    if model.repeat is None and rep.get("component") == comp.name and \
            0 < rep.get("stitches", 0) < cols and cols % rep["stitches"] == 0 and \
            cols // rep["stitches"] >= 2:
        model.repeat = {"what": "motif repeats", "n": cols // rep["stitches"], "x": [0.0, 1.0]}
    return model


def _round_model(cir, comp, twin, pal_lab) -> PieceModel:
    from ..publish import charts

    src = np.asarray(charts.render_round_fabric(cir, twin).convert("RGB"), dtype=np.float64)
    h, w = src.shape[:2]
    cls, _ = _classify(src, pal_lab)
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - (w - 1) / 2, yy - (h - 1) / 2) / (min(w, h) / 2)
    radial = _radial(cls, rr, len(pal_lab))
    cols = max(len(r) for r in twin.chart_grid())
    return PieceModel(comp.name, int(getattr(comp, "make", 1) or 1), True,
                      float(twin.width_cm or 1), float(twin.height_cm or 1), cols,
                      len(twin.chart_grid()), radial=radial)


def _radial(cls: np.ndarray, rr: np.ndarray, n: int, valid=None) -> np.ndarray:
    out = np.zeros((RADIAL_BINS, n))
    b = np.floor(rr * RADIAL_BINS).astype(int)
    ok = (b >= 0) & (b < RADIAL_BINS)
    if valid is not None:
        ok &= valid
    for k in range(RADIAL_BINS):
        sel = ok & (b == k)
        if sel.any():
            out[k] = np.bincount(cls[sel], minlength=n)[:n] / sel.sum()
    return out


def expectation(cir) -> Expectation:
    """What the certified CIR makes, as the verifier measures it. Deterministic, cached."""
    key = hashlib.sha256(json.dumps(cir.to_dict(), sort_keys=True, default=str)
                         .encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    from ..creative import pattern_refs as PR

    if not cir.colors:
        raise ValueError("the CIR declares no colours; the palette cannot be checked")
    parts = PR._components(cir)
    rules = PR.technical_rules(cir, parts, release_hash=key)
    facts = rules["fabric"]
    ids = list(cir.colors)
    hexes = [cir.colors[i] for i in ids]
    rgb = np.array([_hex_rgb(h) for h in hexes], dtype=np.float64)
    pal_lin, pal_lab = _lin(rgb), _lab(rgb)
    pieces = []
    for comp, twin, is_round in parts:
        main = comp.name == facts["component"]
        pieces.append(_round_model(cir, comp, twin, pal_lab) if is_round else
                      _flat_model(cir, comp, twin, pal_lab, facts if main else None, rules))
    shares = np.zeros(len(ids))
    for p in pieces:
        if p.classes is not None:
            shares += np.bincount(p.classes.ravel(), minlength=len(ids)) / p.classes.size * \
                p.make * p.width_cm * p.height_cm
        elif p.radial is not None:
            shares += p.radial.mean(axis=0) * p.make * p.width_cm * p.height_cm
    shares /= max(shares.sum(), 1e-9)
    try:
        fp = cir.fingerprint
    except Exception:  # noqa: BLE001
        fp = key[:16]
    exp = Expectation(cir.slug, cir.version, str(fp), ids, hexes, pal_lab, pal_lin, pieces,
                      bool(facts["edging_declared"]), bool(facts["ribbing_declared"]),
                      facts.get("craft") or "crochet", shares)
    _CACHE[key] = exp
    return exp


# ---- isolation ------------------------------------------------------------------------------

def _load(data: bytes) -> np.ndarray:
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGB")
    w, h = img.size
    f = MAX_SIDE_PX / float(max(w, h))
    if f < 1.0:
        img = img.resize((max(1, int(round(w * f))), max(1, int(round(h * f)))), Image.BOX)
    return np.asarray(img, dtype=np.float64)


def _background(lab: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = lab.shape[:2]
    b = max(4, int(BORDER_RING * min(h, w)))
    ring = np.zeros((h, w), bool)
    ring[:b], ring[-b:], ring[:, :b], ring[:, -b:] = True, True, True, True
    yy, xx = np.mgrid[0:h, 0:w]
    a = np.stack([xx / w, yy / h, np.ones_like(xx, dtype=float)], axis=-1)
    pts, vals = a[ring], lab[ring]
    keep = np.ones(len(vals), bool)
    for _ in range(3):   # robust: something lying across the ring is not background
        coef, *_ = np.linalg.lstsq(pts[keep], vals[keep], rcond=None)
        resid = _de(vals, pts @ coef)
        keep = resid < max(6.0, 2.5 * float(np.median(resid[keep])))
    bg = a @ coef
    spread = float(np.percentile(resid[keep], 90)) if keep.any() else float("inf")
    if keep.mean() < 0.7:
        spread = float("inf")    # most of the border is not one plain surface
    return bg, spread


def _isolate(rgb: np.ndarray, exp: Expectation) -> dict:
    from scipy import ndimage

    lab = _lab(rgb)
    bg, spread = _background(lab)
    bg_mean = bg.reshape(-1, 3).mean(axis=0)
    sep = float(_de(exp.palette_lab, bg_mean).min())
    measured = {"background_spread_de": round(spread, 2) if math.isfinite(spread) else None,
                "separation_de": round(sep, 2),
                "background_lab": [round(float(v), 1) for v in bg_mean]}
    if spread > BG_SPREAD_MAX:
        return {"check": _check("isolation", UNKNOWN,
                                "the background is not plain: not a product-only flat lay, "
                                "so nothing can be rectified or counted", **measured)}
    if sep < MIN_SEPARATION:
        return {"check": _check("isolation", UNKNOWN,
                                f"the background is within {sep:.1f} dE76 of a yarn colour; "
                                "the product's outline cannot be told from it", **measured)}
    t = float(np.clip(FG_FRACTION * sep, 6.0, 20.0))
    de = _de(lab, bg)
    fg = de > t
    # A contact shadow is the background darkened: same chroma, lower L, off every yarn.
    dl = lab[..., 0] - bg[..., 0]
    dab = np.hypot(lab[..., 1] - bg[..., 1], lab[..., 2] - bg[..., 2])
    off_yarn = _de(lab[..., None, :], exp.palette_lab).min(axis=-1) > OFF_PALETTE_DE
    shadow = fg & (dl < 0) & (dab < 6.0) & off_yarn
    fg &= ~shadow
    fg = ndimage.binary_opening(fg, iterations=1)
    fg = ndimage.binary_closing(fg, iterations=2)
    fg = ndimage.binary_fill_holes(fg)
    lab_img, n = ndimage.label(fg)
    if n == 0:
        return {"check": _check("isolation", UNKNOWN, "no product could be isolated from the "
                                                      "background", threshold_de=t, **measured)}
    areas = ndimage.sum(fg, lab_img, index=range(1, n + 1))
    h, w = fg.shape
    keep = [i + 1 for i, a in enumerate(areas) if a >= MIN_PIECE_AREA * h * w]
    if not keep:
        return {"check": _check("isolation", UNKNOWN, "no object large enough to be the product",
                                threshold_de=t, **measured)}
    pieces = []
    for k in keep:
        m = lab_img == k
        ys, xs = np.nonzero(m)
        if ys.min() <= 4 or xs.min() <= 4 or ys.max() >= h - 5 or xs.max() >= w - 5:
            return {"check": _check("isolation", UNKNOWN,
                                    "a piece touches the image edge: cropped, so its shape "
                                    "and counts cannot be verified", threshold_de=t,
                                    **measured)}
        pieces.append({"mask": m, "area": int(m.sum())})
    pieces.sort(key=lambda p: -p["area"])
    return {"check": _check("isolation", PASS, f"{len(pieces)} object(s) isolated on a plain "
                                               f"background", threshold_de=round(t, 2),
                            objects=len(pieces), **measured),
            "pieces": pieces, "lab": lab}


def _min_area_rect(mask: np.ndarray) -> dict:
    from scipy import ndimage
    from scipy.spatial import ConvexHull

    edge = mask & ~ndimage.binary_erosion(mask)
    ys, xs = np.nonzero(edge)
    pts = np.stack([xs + 0.5, ys + 0.5], axis=1).astype(float)
    hull = pts[ConvexHull(pts).vertices]
    best = None
    for i in range(len(hull)):
        e = hull[(i + 1) % len(hull)] - hull[i]
        th = math.atan2(e[1], e[0])
        c, s = math.cos(th), math.sin(th)
        u = hull @ np.array([c, s])
        v = hull @ np.array([-s, c])
        area = (u.max() - u.min()) * (v.max() - v.min())
        if best is None or area < best[0]:
            cu, cv = (u.max() + u.min()) / 2, (v.max() + v.min()) / 2
            best = (area, th, u.max() - u.min() + 1, v.max() - v.min() + 1,
                    (cu * c - cv * s, cu * s + cv * c))
    _, th, w, h, (cx, cy) = best
    hull_area = float(ConvexHull(pts).volume)
    return {"angle": th, "w": float(w), "h": float(h), "cx": float(cx), "cy": float(cy),
            "solidity": float(mask.sum()) / max(hull_area, 1.0)}


def _rectify(rgb: np.ndarray, mask: np.ndarray, rect: dict, size: tuple[int, int],
             rows_vertical_long: bool | None):
    """The piece cut out along its minimum-area rectangle and resampled to `size`."""
    from PIL import Image

    w, h, th = rect["w"], rect["h"], rect["angle"]
    if rows_vertical_long is not None and ((h >= w) != rows_vertical_long):
        w, h, th = h, w, th + math.pi / 2
    c, s = math.cos(th), math.sin(th)
    ow, oh = max(2, int(round(w))), max(2, int(round(h)))
    # output (u, v) -> input centre + u' e1 + v' e2
    a, b = c * w / ow, -s * h / oh
    d, e = s * w / ow, c * h / oh
    cx0 = rect["cx"] - (a * ow + b * oh) / 2
    cy0 = rect["cy"] - (d * ow + e * oh) / 2
    data = (a, b, cx0, d, e, cy0)
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    mk = Image.fromarray((mask * 255).astype(np.uint8))
    rim = im.transform((ow, oh), Image.AFFINE, data, resample=Image.BILINEAR)
    rmk = mk.transform((ow, oh), Image.AFFINE, data, resample=Image.BILINEAR)
    fill = float((np.asarray(rmk) > 127).mean())
    ww, hw = size
    down = ow >= ww and oh >= hw
    rim = rim.resize((ww, hw), Image.BOX if down else Image.BILINEAR)
    return np.asarray(rim, dtype=np.float64), fill, (ow, oh)


# ---- palette ------------------------------------------------------------------------------

def _illumination(lin: np.ndarray, exp: Expectation) -> dict:
    """Cluster in Lab from the declared colours, then a bounded per-channel gain."""
    pal_lab, pal_lin = exp.palette_lab, exp.palette_lin
    lab = _lab_from_lin(lin)
    centres = pal_lab.copy()
    for _ in range(8):
        lbl = _de(lab[:, None, :], centres).argmin(axis=1)
        for j in range(len(centres)):
            if (lbl == j).any():
                centres[j] = lab[lbl == j].mean(axis=0)
    counts = np.bincount(lbl, minlength=len(pal_lab)).astype(float)
    c_lin = np.array([lin[lbl == j].mean(axis=0) if counts[j] else pal_lin[j]
                      for j in range(len(pal_lab))])
    wts = counts[:, None]
    gain = (wts * c_lin * pal_lin).sum(0) / np.maximum((wts * c_lin ** 2).sum(0), 1e-12)
    clamped = bool(((gain < GAIN_RANGE[0]) | (gain > GAIN_RANGE[1])).any())
    gain = np.clip(gain, *GAIN_RANGE)
    return {"gain": gain, "clamped": clamped, "counts": counts}


def _palette_check(lab_c: np.ndarray, lin_c: np.ndarray, valid: np.ndarray,
                   exp: Expectation, *, structured: bool = True, name: str = "palette"):
    pal = exp.palette_lab
    px = lab_c[valid]
    near = _de(px[:, None, :], pal)
    lbl = near.argmin(axis=1)
    centres = {}
    worst_de = 0.0
    shares = np.bincount(lbl, minlength=len(pal)) / max(len(lbl), 1)
    for j, cid in enumerate(exp.palette_ids):
        sel = lbl == j
        if sel.sum() < 0.005 * len(lbl):
            continue
        cen = px[sel].mean(axis=0)
        d = float(_de(cen, pal[j]))
        worst_de = max(worst_de, d)
        centres[cid] = {"measured": _hex_of_lin(lin_c[valid][sel].mean(axis=0)),
                        "declared": exp.palette_hex[j], "de76": round(d, 1),
                        "share": round(float(shares[j]), 3)}
    seg = np.full(valid.shape, 0.0)
    seg[valid] = _seg_distance(px, pal)
    off = valid & (seg > OFF_PALETTE_DE)
    off_share = float(off.sum()) / max(int(valid.sum()), 1)
    measured = {"clusters": centres, "off_palette_share": round(off_share, 4)}
    if off.any():
        measured["off_palette_colour"] = _hex_of_lin(lin_c[off].mean(axis=0))
    if worst_de > CENTRE_DE_MAX:
        return _check(name, FAIL, f"a yarn colour is {worst_de:.1f} dE76 from its declared "
                                  f"hex after illumination correction: a substituted colour",
                      code=OFF_PALETTE_COLOUR, **measured), shares
    if structured and off.any():
        rows = off.sum(axis=1) / np.maximum(valid.sum(axis=1), 1)
        cols = off.sum(axis=0) / np.maximum(valid.sum(axis=0), 1)
        r_runs, c_runs = _runs(rows >= OFF_STRIPE_FRAC), _runs(cols >= OFF_STRIPE_FRAC)
        if max(r_runs + c_runs, default=0) >= 2:
            return _check(name, FAIL, f"a stripe of a colour the palette does not declare "
                                      f"({measured.get('off_palette_colour')})",
                          code=OFF_PALETTE_COLOUR, stripe_rows=int(sum(r_runs)),
                          stripe_cols=int(sum(c_runs)), **measured), shares
    if off_share > OFF_GLOBAL_MAX:
        return _check(name, UNKNOWN, f"{off_share:.1%} of the product region is off the "
                                     f"palette with no stripe structure: an occlusion, a prop "
                                     f"or an invented motif; cannot tell which", **measured), \
            shares
    return _check(name, PASS, "every yarn colour matches the declared palette", **measured), \
        shares


def _runs(flags) -> list[int]:
    out, n = [], 0
    for f in list(flags) + [False]:
        if f:
            n += 1
        elif n:
            out.append(n)
            n = 0
    return out


# ---- flat-piece checks --------------------------------------------------------------------

def _profiles(cls: np.ndarray, valid: np.ndarray, n: int, axis: int) -> np.ndarray:
    """Per-row (axis=1) or per-column (axis=0) palette shares over valid pixels."""
    onehot = (cls[..., None] == np.arange(n)) & valid[..., None]
    tot = np.maximum(valid.sum(axis=axis), 1)[..., None]
    return onehot.sum(axis=axis) / tot


def _tv(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 0.5 * np.abs(a - b).sum(axis=-1)


def _layout_score(cand_rows, exp_rows, m: int, shift_max: int):
    hw = len(exp_rows)
    best = None
    for s in range(-shift_max, shift_max + 1):
        lo, hi = max(m, m + s), min(hw - m, hw - m + s)
        if hi - lo < 4:
            continue
        tv = _tv(cand_rows[lo:hi], exp_rows[lo - s:hi - s])
        sc = float(tv.mean())
        if best is None or sc < best[0]:
            best = (sc, s, tv)
    return best


def _period(sig: np.ndarray, p_exp: float) -> tuple[float, float]:
    s = sig - np.polyval(np.polyfit(np.arange(len(sig)), sig, 1), np.arange(len(sig)))
    if float(np.abs(s).max(initial=0.0)) < 1e-9:
        return 0.0, 0.0
    lo, hi = max(2, int(math.floor(p_exp / 1.6))), int(math.ceil(p_exp * 1.6))
    hi = min(hi, len(s) // 2)
    r = []
    for lag in range(lo, hi + 1):
        a, b = s[:-lag], s[lag:]
        den = math.sqrt(float((a * a).sum() * (b * b).sum())) or 1e-12
        r.append(float((a * b).sum()) / den)
    if not r:
        return 0.0, 0.0
    i = int(np.argmax(r))
    p = float(lo + i)
    if 0 < i < len(r) - 1:
        y0, y1, y2 = r[i - 1], r[i], r[i + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            p += 0.5 * (y0 - y2) / den
    return p, r[i]


def _count(cls, lum, valid, rows_sel, model: PieceModel, n_pal: int, which: str | None):
    """(count, confidence, signal) for the model's declared repeat, on these arrays."""
    ww = cls.shape[1]
    x0, x1 = model.repeat["x"]
    a, b = int(round(x0 * ww)), int(round(x1 * ww))
    v = valid[rows_sel][:, a:b]
    if which is None:
        prof = _profiles(model.classes[rows_sel][:, a:b], np.ones_like(v), n_pal, 0)
        var = prof.var(axis=0)
        which = f"class:{int(var.argmax())}" if var.max() > 0.0025 else "lum"
    if which == "lum":
        num = np.where(v, lum[rows_sel][:, a:b], 0).sum(0)
    else:
        num = ((cls[rows_sel][:, a:b] == int(which.split(":")[1])) & v).sum(0)
    den = v.sum(0)
    sig = np.where(den > 0, num / np.maximum(den, 1), np.nan)
    if np.isnan(sig).all():
        return 0.0, 0.0, which
    sig = np.where(np.isnan(sig), np.nanmean(sig), sig)   # an unmeasured column says nothing
    p_exp = (b - a) / model.repeat["n"]
    p, conf = _period(sig.astype(float), p_exp)
    return ((b - a) / p if p else 0.0), conf, which


def _band_extent(share: np.ndarray, outer: str, m: int) -> int:
    seq = share[m:] if outer == "top" else share[:len(share) - m][::-1]
    return next((i for i, x in enumerate(seq) if x < 0.5), len(seq)) + m


def _verify_flat(rgb, piece: dict, model: PieceModel, exp: Expectation) -> list[dict]:
    checks = []
    rect = _min_area_rect(piece["mask"])
    name = model.name
    expected_vertical = (model.height_cm >= model.width_cm) if model.ratio >= 1.1 else None
    ww, hw = model.work
    measured_ratio = max(rect["w"], rect["h"]) / max(min(rect["w"], rect["h"]), 1e-9)
    work_rgb, fill, native = _rectify(rgb, piece["mask"], rect, (ww, hw), expected_vertical)
    if fill < MIN_FILL:
        return [_check(f"{name}:flat", UNKNOWN,
                       f"the piece fills {fill:.0%} of its rectangle: folded, turned over, "
                       f"curved or occluded; it is not measured through",
                       code=FC.UNVERIFIABLE_COUNT, fill=round(fill, 3))]
    checks.append(_check(f"{name}:flat", PASS, f"fills {fill:.0%} of its rectangle",
                         fill=round(fill, 3)))
    rel = measured_ratio / model.ratio - 1.0
    checks.append(_check(
        f"{name}:aspect", PASS if abs(rel) <= ASPECT_REL else FAIL,
        f"long/short {measured_ratio:.3f} vs {model.ratio:.3f} from the twin ({rel:+.1%})",
        code=WRONG_ASPECT_RATIO, measured=round(measured_ratio, 4),
        expected=round(model.ratio, 4), tolerance=ASPECT_REL))

    n = len(exp.palette_ids)
    m = max(1, int(round(INSET * min(ww, hw))))
    lin = _lin(work_rgb)
    ill = _illumination(lin[m:hw - m, m:ww - m].reshape(-1, 3), exp)
    lin_c = lin * ill["gain"]
    lab_c = _lab_from_lin(lin_c)
    valid = np.zeros((hw, ww), bool)
    valid[m:hw - m, m:ww - m] = True
    pal_chk, _ = _palette_check(lab_c, lin_c, valid, exp, name=f"{name}:palette")
    pal_chk["illumination_gain"] = [round(float(g), 3) for g in ill["gain"]]
    pal_chk["gain_clamped"] = ill["clamped"]
    checks.append(pal_chk)

    cls = _de(lab_c[..., None, :], exp.palette_lab).argmin(axis=-1)
    seg = _seg_distance(lab_c, exp.palette_lab)
    ok = valid & (seg <= OFF_PALETTE_DE)
    lum = lab_c[..., 0]
    # Orientation: the dihedral transforms that keep the declared rows axis.
    cands = [lambda a: a, lambda a: a[::-1, ::-1], lambda a: a[:, ::-1], lambda a: a[::-1, :]]
    if expected_vertical is None and ww == hw:
        cands += [lambda a: np.rot90(a, 1), lambda a: np.rot90(a, 3),
                  lambda a: np.rot90(a, 1)[::-1], lambda a: np.rot90(a, 3)[::-1]]
    exp_rows = _profiles(model.classes, np.ones_like(valid), n, 1)
    exp_cols = _profiles(model.classes, np.ones_like(valid), n, 0)
    shift_max = max(1, int(round(SHIFT_MAX * hw)))
    best = None
    for t in cands:
        c, v = t(cls), t(ok)
        if c.shape != model.classes.shape:
            continue
        rs = _layout_score(_profiles(c, v, n, 1), exp_rows, m, shift_max)
        cs = float(_tv(_profiles(c, v, n, 0)[m:ww - m], exp_cols[m:ww - m]).mean())
        if rs and (best is None or rs[0] + cs < best[0]):
            best = (rs[0] + cs, t, rs, cs)
    _, t, (row_tv, shift, tv_rows), col_tv = best
    cls, ok, lum = t(cls), t(ok), t(lum)
    bad = float((tv_rows > LAYOUT_TV_ROW).mean())
    shares = _profiles(cls, ok, n, 1).mean(axis=0) if ok.any() else np.zeros(n)
    missing = [exp.palette_ids[j] for j in range(n)
               if exp.expected_share[j] >= 0.03 and float(
                   (cls[ok] == j).mean() if ok.any() else 0) < MISSING_SHARE *
               exp.expected_share[j]]
    lay_ok = row_tv <= LAYOUT_TV_MEAN and bad <= LAYOUT_BAD_ROWS and not missing
    checks.append(_check(
        f"{name}:colour_layout", PASS if lay_ok else FAIL,
        (f"row colour profile within tolerance of the CIR's (mean TV {row_tv:.3f})" if lay_ok
         else f"row colour profile differs from the CIR's: mean TV {row_tv:.3f}, "
              f"{bad:.0%} of rows over {LAYOUT_TV_ROW}" + (f"; missing {missing}" if missing
                                                          else "")),
        code=WRONG_COLOUR_LAYOUT, mean_row_tv=round(row_tv, 4), bad_rows=round(bad, 4),
        column_tv=round(col_tv, 4), shift_px=shift, missing_colours=missing))
    del shares

    # End bands: solid, the declared colour, the declared width.
    rows_prof = _profiles(cls, ok, n, 1)
    body = np.ones(hw, bool)
    for b in model.bands:
        y0, y1 = int(round(b["y"][0] * hw)), int(round(b["y"][1] * hw))
        body[max(0, y0 - int(b["row_px"])):min(hw, y1 + int(b["row_px"]))] = False
        k = b["colour_index"]
        rp = max(1, int(math.ceil(b["row_px"])))
        lo, hi = (max(y0, m), y1 - rp) if b["outer"] == "top" else (y0 + rp, min(y1, hw - m))
        solid = rows_prof[lo:hi, k] if hi > lo else np.array([1.0])
        # Width as measured the same way on the CIR's own render: from the outer edge to the
        # first row that is less than half band colour.
        ext, expected_w = _band_extent(rows_prof[:, k], b["outer"], m), _band_extent(
            exp_rows[:, k], b["outer"], m)
        ratio = ext / max(expected_w, 1)
        problems = []
        if float(solid.min(initial=1.0)) < BAND_SOLID:
            problems.append(f"a row inside the band is only {float(solid.min()):.0%} "
                            f"{b['colour']} (stripe or contrast row)")
        if not BAND_EXTENT[0] <= ratio <= BAND_EXTENT[1]:
            problems.append(f"band width {ratio:.2f}x the declared {b['rows'][1] - b['rows'][0] + 1} "
                            f"rows")
        checks.append(_check(
            f"{name}:end_band_{b['outer']}", FAIL if problems else PASS,
            "; ".join(problems) or f"plain {b['colour']} rows {b['rows'][0]}-{b['rows'][1]} "
                                   f"as declared",
            code=FC.INVENTED_END_BAND_TREATMENT, min_band_share=round(float(
                solid.min(initial=1.0)), 3), width_ratio=round(ratio, 3)))

    # Row-end edges (the CIR's plain ends of rows): compare with the CIR's own row ends.
    if not exp.edging_declared:
        body &= np.arange(hw) >= m
        body &= np.arange(hw) < hw - m
        cp = _profiles(cls[body], ok[body], n, 0)
        ep = _profiles(model.classes[body], np.ones_like(ok[body]), n, 0)
        lc = np.where(ok[body], lum[body], np.nan)
        lc = np.nanmean(np.where(np.isnan(lc), np.nanmean(lc), lc), axis=0)
        le = model.lum[body].mean(axis=0)
        r0, r1 = int(EDGE_REF[0] * ww), max(int(EDGE_REF[1] * ww), int(EDGE_REF[0] * ww) + 2)
        es = max(2, int(round(EDGE_STRIP * ww)))
        sides = {}
        for side, idx in (("left", np.arange(ww)), ("right", np.arange(ww)[::-1])):
            ci, ei = cp[idx], ep[idx]
            lci = lc[idx] - np.median(lc[idx][r0:r1])
            lei = le[idx] - np.median(le[idx][r0:r1])
            delta = np.maximum(_tv(ci, ei), np.minimum(1.0, np.abs(lci - lei) / 20.0))
            score = float(delta[m:m + es].mean())
            ref = float(delta[r0:r1].mean())
            sides[side] = {"edge": round(score, 3), "interior": round(ref, 3),
                           "edging": score > EDGE_SCORE and score > EDGE_RATIO * ref + 0.1}
        bad_sides = [s for s, v in sides.items() if v["edging"]]
        checks.append(_check(
            f"{name}:edges", FAIL if bad_sides else PASS,
            (f"a border strip along the {', '.join(bad_sides)} row ends that the pattern does "
             f"not have" if bad_sides else "row ends look like the CIR's plain row ends"),
            code=FC.INVENTED_EDGING, sides=sides))

    if model.repeat:
        rows_sel = body if body.any() else np.ones(hw, bool)
        stitch_px = native[0] / max(model.cols, 1)
        exp_count, exp_conf, which = _count(model.classes, model.lum, np.ones_like(ok),
                                            rows_sel, model, n, None)
        cnt, conf, _ = _count(cls, lum, ok, rows_sel, model, n, which)
        measured = {"what": model.repeat["what"], "expected": model.repeat["n"],
                    "measured": round(cnt, 2), "confidence": round(conf, 3),
                    "signal": which, "px_per_stitch": round(stitch_px, 2),
                    "estimator_on_cir_render": {"count": round(exp_count, 2),
                                                "confidence": round(exp_conf, 3)}}
        qualified = exp_conf >= COUNT_CONF and round(exp_count) == model.repeat["n"] and \
            abs(exp_count - round(exp_count)) <= COUNT_FRAC
        if not qualified:
            checks.append(_check(f"{name}:repeat_count", UNKNOWN,
                                 "the count estimator does not recover the declared count "
                                 "from the CIR's own render; not qualified for this product",
                                 code=FC.UNVERIFIABLE_COUNT, **measured))
        elif stitch_px < COUNT_MIN_PX_PER_STITCH or conf < COUNT_CONF or \
                abs(cnt - round(cnt)) > COUNT_FRAC:
            checks.append(_check(f"{name}:repeat_count", UNKNOWN,
                                 f"{model.repeat['what']} cannot be counted with confidence",
                                 code=FC.UNVERIFIABLE_COUNT, **measured))
        else:
            got = int(round(cnt))
            checks.append(_check(
                f"{name}:repeat_count", PASS if got == model.repeat["n"] else FAIL,
                f"{got} {model.repeat['what']} (declared {model.repeat['n']})",
                code=WRONG_REPEAT_COUNT, **measured))
    else:
        checks.append(_check(f"{name}:repeat_count", NA, "the CIR declares no horizontal "
                                                         "repeat on this piece"))
    return checks


def _verify_round(rgb, piece: dict, model: PieceModel, exp: Expectation, lab_full) -> list[dict]:
    name = model.name
    rect = _min_area_rect(piece["mask"])
    if rect["solidity"] < MIN_SOLIDITY:
        return [_check(f"{name}:flat", UNKNOWN, f"solidity {rect['solidity']:.2f}: folded, "
                                                f"curled or occluded",
                       code=FC.UNVERIFIABLE_COUNT, solidity=round(rect["solidity"], 3))]
    ratio = max(rect["w"], rect["h"]) / max(min(rect["w"], rect["h"]), 1e-9)
    rel = ratio / model.ratio - 1.0
    out = [_check(f"{name}:aspect", PASS if abs(rel) <= ROUND_ASPECT_REL else FAIL,
                  f"long/short {ratio:.3f} vs {model.ratio:.3f} ({rel:+.1%})",
                  code=WRONG_ASPECT_RATIO, measured=round(ratio, 4),
                  expected=round(model.ratio, 4))]
    mask = piece["mask"]
    ys, xs = np.nonzero(mask)
    cy, cx = ys.mean(), xs.mean()
    r_eq = math.sqrt(mask.sum() / math.pi)
    yy, xx = np.mgrid[0:mask.shape[0], 0:mask.shape[1]]
    rr = np.hypot(xx - cx, yy - cy) / r_eq
    inner = mask & (rr < 1.0 - INSET * 2)
    lin = _lin(rgb)
    ill = _illumination(lin[inner], exp)
    lin_c = lin * ill["gain"]
    lab_c = _lab_from_lin(lin_c)
    pal, _ = _palette_check(lab_c, lin_c, inner, exp, structured=False, name=f"{name}:palette")
    out.append(pal)
    cls = _de(lab_c[..., None, :], exp.palette_lab).argmin(axis=-1)
    ok = inner & (_seg_distance(lab_c, exp.palette_lab) <= OFF_PALETTE_DE)
    radial = _radial(cls, rr, len(exp.palette_ids), ok)
    tv = _tv(radial, model.radial)
    used = int(RADIAL_BINS * (1.0 - INSET * 2))
    tv = tv[:used]
    outer = float(tv[-2:].mean())
    mean = float(tv.mean())
    if mean <= LAYOUT_TV_MEAN and outer <= LAYOUT_TV_ROW:
        out.append(_check(f"{name}:colour_layout", PASS, f"round colour profile matches "
                                                         f"(mean TV {mean:.3f})",
                          mean_tv=round(mean, 4), outer_tv=round(outer, 4)))
    else:
        code = FC.INVENTED_EDGING if outer > LAYOUT_TV_ROW and float(
            tv[:-2].mean()) <= LAYOUT_TV_MEAN else WRONG_COLOUR_LAYOUT
        out.append(_check(f"{name}:colour_layout", FAIL,
                          f"round colour profile differs (mean TV {mean:.3f}, outer "
                          f"{outer:.3f})", code=code, mean_tv=round(mean, 4),
                          outer_tv=round(outer, 4)))
    return out


# ---- craft texture (vision) ---------------------------------------------------------------

CRAFT_FIELDS = ("craft", "ribbing_visible", "border_or_edging_visible", "cable_style",
                "fabric_visible_clearly")
CRAFT_SYSTEM = ("You are a textile expert looking at a photograph of a handmade item. Say "
                "only what the picture shows. Say 'unclear' whenever you cannot tell.")


def craft_prompt() -> str:
    return ("Reply with a single JSON object and nothing else. Keys:\n"
            "- craft: one of crochet, knitting, woven, printed, unclear\n"
            "- ribbing_visible: true, false or unclear\n"
            "- border_or_edging_visible: true, false or unclear (a band of different "
            "stitches or colour worked around or along the edges)\n"
            "- cable_style: one of none, crochet_post_stitch_crossings, knitted_rope, "
            "unclear\n"
            "- fabric_visible_clearly: true or false")


def compare_craft(reading: dict, exp: Expectation) -> dict:
    """Deterministic comparison of a blind craft reading with the CIR's facts."""
    if not isinstance(reading, dict):
        return _check("craft_texture", UNKNOWN, "no reading")
    v = {k: str(reading.get(k, "unclear")).strip().lower() for k in CRAFT_FIELDS}
    problems, unclear = [], []
    if v["fabric_visible_clearly"] not in ("true", "yes"):
        unclear.append("fabric not clearly visible")
    if v["craft"] == "unclear":
        unclear.append("craft unclear")
    elif v["craft"] != exp.craft:
        problems.append(f"reads as {v['craft']}, the pattern is {exp.craft}")
    if v["cable_style"] == "knitted_rope":
        problems.append("knitted rope cables")
    if not exp.ribbing_declared:
        if v["ribbing_visible"] in ("true", "yes"):
            problems.append("ribbing the pattern does not have")
        elif v["ribbing_visible"] not in ("false", "no"):
            unclear.append("ribbing unclear")
    edging = (not exp.edging_declared and v["border_or_edging_visible"] in ("true", "yes"))
    if problems:
        return _check("craft_texture", FAIL, "; ".join(problems),
                      code=FC.WRONG_CRAFT_TEXTURE, reading=v, invented_edging_seen=edging)
    if edging:
        return _check("craft_texture", FAIL, "an edging the pattern does not have",
                      code=FC.INVENTED_EDGING, reading=v)
    if unclear:
        return _check("craft_texture", UNKNOWN, "; ".join(unclear), reading=v)
    return _check("craft_texture", PASS, f"reads as {exp.craft}, no ribbing or edging",
                  reading=v)


class GatewayVisionJudge:
    """The production vision judge: `image_vision` gated, budgeted like `visual.inspect`.

    `read(question, images)` returns {"answered": bool, "reading": dict, "why": str}. While
    the gate is closed nothing is called and every answer is unanswered (UNKNOWN)."""

    name = "image_vision"

    def __init__(self, db, provider=None):
        self.db, self.provider = db, provider

    def gate_open(self) -> bool:
        if self.db is None:
            return False
        try:
            from .gallery import gates_now

            return bool(gates_now(self.db, keys=("image_vision",)).get("image_vision"))
        except Exception:  # noqa: BLE001 - an unreadable gate is closed
            return False

    def read(self, prompt: str, images: list[bytes], *, system: str = CRAFT_SYSTEM,
             max_tokens: int = 300) -> dict:
        if not self.gate_open():
            return {"answered": False, "why": "the vision judge (image_vision) is unfunded; "
                                              "nothing was called"}
        import os

        from ..core import workspace
        from ..gateway import anthropic as gw
        from . import inspect as I

        provider = self.provider or gw.provider_for(I.TASK)
        billed = {"reserved": 0.0, "actual": 0.0, "tokens_in": 0, "tokens_out": 0}
        try:
            with workspace.work_dir(None, prefix="fidelity-judge-") as tmp:
                paths = []
                for i, data in enumerate(images):
                    p = os.path.join(tmp, f"image-{i}.png")
                    with open(p, "wb") as fh:
                        fh.write(data)
                    paths.append(p)
                budget = gw.check_budget(
                    self.db, model=provider.model,
                    input_tokens=len(prompt) // 4 + gw.IMAGE_TOKENS_ESTIMATE * len(paths),
                    max_tokens=max_tokens, uncommitted_cad=0.0, agent=I.AGENT,
                    purpose=I.TASK)
                billed["reserved"] = budget["estimate_cad"]
                held = budget["reservation_id"]
                try:
                    resp = provider.see(system, prompt, paths, max_tokens=max_tokens)
                except BaseException:
                    gw.release_reservation(self.db, held)
                    raise
                cost = round(resp.input_tokens * provider.cost_per_1k_input_cad / 1000
                             + resp.output_tokens * provider.cost_per_1k_output_cad / 1000, 8)
                billed.update(actual=cost, tokens_in=resp.input_tokens,
                              tokens_out=resp.output_tokens)
                gw.release_reservation(self.db, held, actual_cad=cost)
                I._bill(self.db, provider, billed, "fidelity:" + hashlib.sha256(
                    images[0]).hexdigest()[:16])
                return {"answered": True, "reading": I._json(resp.text),
                        "model": provider.model}
        except Exception as exc:  # noqa: BLE001 - an unmade reading is UNKNOWN, never PASS
            return {"answered": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}"}


def craft_texture(data: bytes, exp: Expectation, judge) -> dict:
    if judge is None:
        return _check("craft_texture", UNKNOWN, "no vision judge is configured",
                      code=None, needs="vision judge")
    got = judge.read(craft_prompt(), [data])
    if not got.get("answered"):
        return _check("craft_texture", UNKNOWN, f"craft texture not judged: {got.get('why')}",
                      needs="vision judge")
    out = compare_craft(got.get("reading") or {}, exp)
    out["judge"] = getattr(judge, "name", "?")
    return out


# ---- the verdicts -------------------------------------------------------------------------

def _verdict(checks: list[dict], *, data: bytes, exp: Expectation | None, kind: str) -> dict:
    status = worst(c["status"] for c in checks)
    codes = sorted({c["code"] for c in checks if c.get("code") and c["status"] != PASS
                    and c["status"] != NA})
    if status == PASS:
        codes = []
    return {"status": status, "checker": CHECKER, "verifier_version": VERIFIER_VERSION,
            "kind": kind, "checks": checks,
            "failed": [c["check"] for c in checks if c["status"] == FAIL],
            "unknown": [c["check"] for c in checks if c["status"] == UNKNOWN],
            "codes": codes, "tolerances": TOLERANCES,
            "image_sha256": hashlib.sha256(data).hexdigest() if data else "",
            "cir_fingerprint": exp.cir_fingerprint if exp else None,
            "slug": exp.slug if exp else None, "version": exp.version if exp else None,
            "reads_generator_claims": False}


def verify_anchor(data: bytes, cir, *, judge=None) -> dict:
    """The product-only, unfolded flat lay against the certified CIR."""
    try:
        exp = expectation(cir)
    except Exception as exc:  # noqa: BLE001 - no expectation, nothing can pass
        return _verdict([_check("expectation", UNKNOWN, f"the CIR cannot be modelled: "
                                                        f"{type(exc).__name__}: {exc}"[:300])],
                        data=data, exp=None, kind="anchor")
    try:
        rgb = _load(data)
    except Exception as exc:  # noqa: BLE001
        return _verdict([_check("decode", FAIL, f"not a decodable image ({type(exc).__name__})")],
                        data=data, exp=exp, kind="anchor")
    iso = _isolate(rgb, exp)
    checks = [iso["check"]]
    if iso["check"]["status"] != PASS:
        checks.append(_check("counts", UNKNOWN, "nothing could be measured on this image",
                             code=FC.UNVERIFIABLE_COUNT))
        checks.append(craft_texture(data, exp, judge))
        return _verdict(checks, data=data, exp=exp, kind="anchor")
    pieces = iso["pieces"]
    want = exp.piece_count
    areas = [p["area"] for p in pieces]
    med = float(np.median(areas))
    measured = {"expected": want, "measured": len(pieces), "areas_px": areas}
    if len(pieces) == want:
        checks.append(_check("piece_count", PASS, f"{want} piece(s) as the CIR makes",
                             **measured))
    elif len(pieces) < want and max(areas) > 1.6 * med and len(pieces) > 1:
        checks.append(_check("piece_count", UNKNOWN, "pieces touch or overlap; they cannot be "
                                                     "counted apart",
                             code=FC.UNVERIFIABLE_COUNT, **measured))
    elif len(pieces) > want and min(areas) < 0.25 * med:
        checks.append(_check("piece_count", UNKNOWN, "an object that is not a piece is in the "
                                                     "frame (prop or debris)",
                             code=FC.UNVERIFIABLE_COUNT, **measured))
    else:
        checks.append(_check("piece_count", FAIL, f"{len(pieces)} piece(s); the CIR makes "
                                                  f"{want}", code=WRONG_PIECE_COUNT,
                             **measured))
    # Match pieces to components by area rank (one shared scale in a flat lay).
    slots = sorted([pm for pm in exp.pieces for _ in range(pm.make)],
                   key=lambda pm: -(pm.width_cm * pm.height_cm))
    for piece, model in zip(pieces, slots):
        try:
            if model.round_:
                checks += _verify_round(rgb, piece, model, exp, iso["lab"])
            else:
                checks += _verify_flat(rgb, piece, model, exp)
        except Exception as exc:  # noqa: BLE001 - a measurement that broke is UNKNOWN
            checks.append(_check(f"{model.name}:measure", UNKNOWN,
                                 f"{type(exc).__name__}: {str(exc)[:200]}"))
    checks.append(craft_texture(data, exp, judge))
    return _verdict(checks, data=data, exp=exp, kind="anchor")


def verify_lifestyle(data: bytes, cir, *, release_hash: str, anchor: dict | None,
                     anchor_data: bytes | None = None, product_region=None,
                     judge=None) -> dict:
    """A lifestyle image: anchor PASS for this release, region palette, vision consistency.

    `anchor`: {"status", "release_hash"} of the release's product-only anchor (its stored
    technical verdict). `product_region`: (x0, y0, x1, y1) in pixels of these bytes, from a
    detector or a judge; without one the palette is not checked (UNKNOWN)."""
    try:
        exp = expectation(cir)
    except Exception as exc:  # noqa: BLE001
        return _verdict([_check("expectation", UNKNOWN, f"{type(exc).__name__}")],
                        data=data, exp=None, kind="lifestyle")
    checks = []
    a = anchor or {}
    rel = str(a.get("release_hash") or a.get("release") or "")
    if not a:
        checks.append(_check("anchor", UNKNOWN, "no product-only anchor for this release",
                             code=FC.UNVERIFIABLE_COUNT))
    elif not (rel and release_hash and (rel.startswith(release_hash[:12]) or
                                        release_hash.startswith(rel[:12]))):
        checks.append(_check("anchor", UNKNOWN, "the anchor is for another release",
                             code=FC.UNVERIFIABLE_COUNT))
    elif a.get("status") != PASS:
        checks.append(_check("anchor", UNKNOWN, f"the anchor is {a.get('status') or 'UNKNOWN'}, "
                                                f"not PASS; counts and layout are unverified",
                             code=FC.UNVERIFIABLE_COUNT))
    else:
        checks.append(_check("anchor", PASS, "the release's unfolded anchor passed fidelity",
                             anchor_sha256=a.get("sha256")))
    try:
        rgb = _load(data)
    except Exception as exc:  # noqa: BLE001
        return _verdict(checks + [_check("decode", FAIL, f"undecodable ({type(exc).__name__})")],
                        data=data, exp=exp, kind="lifestyle")
    if not product_region:
        checks.append(_check("region_palette", UNKNOWN, "no product region is declared for "
                                                        "this image; its colours are unread"))
    else:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        sx, sy = rgb.shape[1] / im.size[0], rgb.shape[0] / im.size[1]
        x0, y0, x1, y1 = (int(product_region[0] * sx), int(product_region[1] * sy),
                          int(product_region[2] * sx), int(product_region[3] * sy))
        region = rgb[max(0, y0):y1, max(0, x0):x1].reshape(-1, 3)
        if len(region) < 100:
            checks.append(_check("region_palette", UNKNOWN, "the product region is too small"))
        else:
            lin = _lin(region)
            ill = _illumination(lin, exp)
            lab_c = _lab_from_lin(lin * ill["gain"])
            seg = _seg_distance(lab_c, exp.palette_lab)
            on = float((seg <= OFF_PALETTE_DE).mean())
            off = lab_c[seg > OFF_PALETTE_DE]
            extra = 0.0
            if len(off):
                # the largest single off-palette colour group (8 dE76 bins)
                q = np.round(off / 8.0).astype(int)
                _, cnt = np.unique(q, axis=0, return_counts=True)
                extra = float(cnt.max()) / len(region)
            m = {"on_palette_share": round(on, 3), "largest_off_cluster": round(extra, 3),
                 "illumination_gain": [round(float(g), 3) for g in ill["gain"]]}
            if extra >= LIFESTYLE_EXTRA_CLUSTER:
                checks.append(_check("region_palette", FAIL, "a large colour group in the "
                                                             "product region is off the palette",
                                     code=OFF_PALETTE_COLOUR, **m))
            elif on < LIFESTYLE_ON_PALETTE:
                checks.append(_check("region_palette", UNKNOWN, "the region is mostly not the "
                                                                "product's colours", **m))
            else:
                checks.append(_check("region_palette", PASS, "region colours on the palette",
                                     **m))
    if judge is None or not anchor_data:
        checks.append(_check("anchor_consistency", UNKNOWN,
                             "no vision reading compares this image with the anchor",
                             needs="vision judge"))
    else:
        got = judge.read(consistency_prompt(), [anchor_data, data],
                         system=CRAFT_SYSTEM, max_tokens=300)
        checks.append(compare_consistency(got))
    checks.append(craft_texture(data, exp, judge))
    return _verdict(checks, data=data, exp=exp, kind="lifestyle")


def consistency_prompt() -> str:
    return ("Image 1 is a handmade item laid flat. Image 2 is a photograph that includes a "
            "handmade item. Reply with one JSON object and nothing else. Keys:\n"
            "- same_item: true, false or unclear\n"
            "- differences: a list of short phrases naming visible differences in colours, "
            "colour order, bands, borders or edging, stitch texture, motif or cable count "
            "(empty list if none)")


def compare_consistency(got: dict) -> dict:
    if not got.get("answered"):
        return _check("anchor_consistency", UNKNOWN, f"not judged: {got.get('why')}",
                      needs="vision judge")
    r = got.get("reading") or {}
    same = str(r.get("same_item", "unclear")).lower()
    diffs = [str(d) for d in (r.get("differences") or [])]
    if same in ("false", "no") or diffs:
        text = " ".join(diffs).lower()
        code = (FC.INVENTED_EDGING if ("border" in text or "edging" in text) else
                FC.INVENTED_END_BAND_TREATMENT if "band" in text else
                FC.WRONG_CRAFT_TEXTURE if ("texture" in text or "knit" in text) else
                WRONG_COLOUR_LAYOUT)
        return _check("anchor_consistency", FAIL, "; ".join(diffs)[:300] or "not the same item",
                      code=code, reading=r)
    if same in ("true", "yes"):
        return _check("anchor_consistency", PASS, "the same item as the anchor", reading=r)
    return _check("anchor_consistency", UNKNOWN, "consistency unclear", reading=r)
