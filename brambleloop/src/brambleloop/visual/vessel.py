"""V2 / P0-c: deterministic fidelity for vessels (baskets) — side count, wall stripes, rim.

`fidelity._verify_round` judged a vessel as a round piece: solidity, aspect within +-15 %,
palette and a radial colour profile. A hexagon's points-to-flats ratio (1.155) sits inside
that aspect tolerance, so a round, a pentagon or an octagon basket passed as a hexagon.
Nothing counted the wall stripes, and nothing read the rim. And the flat-lay brief asked for
a basket "laid completely flat and unfolded", which a basket cannot be.

A vessel is checked from two product-only views instead of one flat lay:

* **top** (standing on its base, seen from directly above). The outline's corners are counted
  from the boundary radius around the centroid: one prominent radius peak per corner. The
  count must equal the twin's `sides`. A wrong count is `WRONG_REPEAT_COUNT` ("a measurable
  count ... differs from the CIR"); a round outline has no peaks and fails the same way.
* **side** (standing, camera level with the middle of the wall). Each image row inside the
  product is labelled with its majority palette colour, runs are merged, and the bottom-to-top
  band sequence must equal the CIR's wall rows collapsed into colour runs. Different bands
  are `WRONG_COLOUR_LAYOUT`. An extra band on top only, or a top silhouette wider than the
  wall, is a rim nobody wrote: `INVENTED_EDGING`.

Expected values come only from the certified CIR and its digital twin. The base is the
rounds that increase; the wall is the trailing rounds that repeat the round before them.
Deterministic, CA$0, no model call. Fail-closed: an unreadable background, no product, or too few pixels per band is
UNKNOWN, never PASS.

**Blind spots** (stated, not hidden): a rim worked in the wall's own colour with the same
silhouette (braid texture only); stitch identity; the inside and the base underside.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from . import fidelity as F

CHECKER = "visual.vessel 1.2.0"   # 1.1: illumination-corrected palette and bands (IMAGES-DIALIN)
                                  # 1.2: near wall only; band shares by height (IMAGE-FIDELITY-2)
SEP_DE = 12.0               # product pixel: at least this far (dE76) from the fitted surface
PEAK_WINDOW_DEG = 18        # a corner is a radius maximum over +- this many degrees
PEAK_PROMINENCE = 0.035     # ... standing this far (fraction of the mean radius) above the
                            # lowest radius within +- 30 degrees
# The prominence floor is load-bearing (review V2 F5): it is what keeps a nearly round
# outline (a circle with a slight 6-lobed ripple) from being counted as a hexagon.
# test_a_lobed_circle_is_round_not_a_hexagon pins it. (For a bump on a polygon's flat the
# +-18 deg window already decides; test_a_jagged_flat_is_not_a_corner pins that.)
SMOOTH_DEG = 7
MIN_PRODUCT_FRAC = 0.03     # of the image area
MIN_BAND_PX = 3             # a colour run shorter than this is merged into its neighbour
MIN_PX_PER_ROW = 1.5        # the side view needs this many pixels per wall row
RIM_WIDTH_RATIO = 1.06      # top-strip width over the wall's median width
RIM_STRIP = 0.06            # the top 6 % of the wall's height is the rim strip
SHARE_REL_MAX = 0.35        # each wall band's share of the wall may be off by this much
MIN_TOP_RADIUS_PX = 60      # below this mean outline radius a corner count is not readable
PALETTE_COVERAGE_MIN = 0.85  # share of wall pixels within OFF_PALETTE_DE of the palette
OFF_ROW_FRAC = 0.5          # a row with more off-palette pixels than this is labelled "off"
OFF_MIN_ROWS = 0.5          # an "off" run under this many wall rows tall is edge blending
CENTRE_COLUMN = (0.30, 0.70)  # band labels read from the middle of the wall only
# IMAGE-FIDELITY-2: a side view taken from above the rim shows the opening, and through it
# the INSIDE of the far wall, whose bands are the same wall's bands again. Read as wall, a
# correct two-stripe basket counted four stripes (production 19i25: basket:wall_bands FAIL on
# market-basket-small, and the certified PDF's own renderings FAIL the same way). The near
# wall's projected height is read from the steep part of the side outlines (`near_wall`);
# the centre column is taller than that by the opening, and only the near wall is read.
STEEP_SLOPE = 0.36          # |dx/dy| of a side outline that is the wall (within ~20 deg)
SLOPE_WINDOW = 0.02         # the slope is read over +- 2 % of the silhouette's height
WALL_SLOPE_TOL = 0.12       # ... and the wall is the rows within this of its own median slope
OPENING_MIN = 0.15          # centre taller than the sides by more than this: an opening shows
                            # (eye-level perspective makes the near face up to ~10 % taller)

BLIND_SPOTS = (
    "a rim worked in the wall's own colour whose silhouette is the wall's (texture only)",
    "stitch identity (a printed or woven vessel in the right colours and shape passes)",
    "the inside of the vessel and the underside of its base",
    "row counts: bands are compared by order and share, not by counting rows",
)


@dataclass
class VesselModel:
    component: str
    sides: int | None
    wall_bands: list[str]                 # colour ids, bottom to top
    wall_rows: list[int]                  # rows per band
    rim_colour: str
    base_rows: int
    wall_total_rows: int
    palette: dict[str, str] = field(default_factory=dict)
    # False when the twin says "vessel" but no wall can be modelled (review V2 F4): the
    # verdict is then UNKNOWN by name, never the round-piece check.
    modelled: bool = True
    # IMAGE-FIDELITY-2: each band's height in cm (`cir.geometry.row_height_cm`, the twin's
    # rule). A double-crochet round stands taller than a single-crochet one and a slip-stitch
    # rim is a fraction of either, so a band's share of the wall is its height, not its round
    # count. Empty when the rounds could not be resolved (shares then fall back to counts).
    wall_heights_cm: list[float] = field(default_factory=list)

    @property
    def wall_shares(self) -> list[float]:
        """Each wall band's share of the wall's HEIGHT, bottom to top (what a picture shows)."""
        if self.wall_heights_cm and len(self.wall_heights_cm) == len(self.wall_rows):
            total = sum(self.wall_heights_cm)
            if total > 0:
                return [h / total for h in self.wall_heights_cm]
        return [n / max(self.wall_total_rows, 1) for n in self.wall_rows]


def vessel_models(cir) -> list[VesselModel]:
    """One model per vessel component of the CIR (empty when the design has none)."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    result = compile_cir(cir)
    out = []
    for comp in cir.components:
        twin = build_twin(cir, result, component=comp.name) if _takes_component() else \
            build_twin(cir, result)
        if (twin.shape or "") != "vessel":
            continue
        counts = [r.count for r in (getattr(twin.geometry, "rings", None) or [])]
        if not counts:
            out.append(VesselModel(comp.name, twin.sides, [], [], "", 0, 0,
                                   dict(cir.colors), modelled=False))
            continue
        # The wall is the trailing rounds that repeat the round before them; the round that
        # first reaches the final count is the last increase round, the base's outer edge.
        wall_n = 0
        for i in range(len(counts) - 1, 0, -1):
            if counts[i] != counts[i - 1]:
                break
            wall_n += 1
        if wall_n == 0:
            out.append(VesselModel(comp.name, twin.sides, [], [], "", len(counts), 0,
                                   dict(cir.colors), modelled=False))
            continue
        rows = comp.rows[-wall_n:]
        colours = [getattr(r, "color", None) or "" for r in rows]
        heights = _row_heights(cir, result, comp.name, rows)
        bands, sizes, band_h = [], [], []
        for i, c in enumerate(colours):
            if bands and bands[-1] == c:
                sizes[-1] += 1
                band_h[-1] += heights[i] if heights else 0.0
            else:
                bands.append(c)
                sizes.append(1)
                band_h.append(heights[i] if heights else 0.0)
        out.append(VesselModel(comp.name, twin.sides, bands, sizes, colours[-1],
                               len(counts) - wall_n, wall_n, dict(cir.colors),
                               wall_heights_cm=[round(h, 4) for h in band_h] if heights
                               else []))
    return out


def _row_heights(cir, result, component: str, rows) -> list[float]:
    """Each row's height in cm by the twin's rule, or [] when a row cannot be resolved."""
    try:
        from ..cir.geometry import row_height_cm

        by_index = {r.index: r for r in result.rows if r.component == component}
        return [float(row_height_cm(by_index[r.index], cir)) for r in rows]
    except Exception:  # noqa: BLE001 - unresolvable heights: shares fall back to counts
        return []


def _takes_component() -> bool:
    import inspect

    from ..cir.twin import build_twin

    return "component" in inspect.signature(build_twin).parameters


def is_vessel(cir) -> bool:
    return bool(vessel_models(cir))


# ---- image helpers --------------------------------------------------------------------------

class _Undecodable(Exception):
    pass


def _product_mask(data: bytes):
    from scipy import ndimage

    try:
        rgb = F._load(data)
    except Exception as exc:  # noqa: BLE001 - review VISUAL_STACK N2: a verdict, not a raise
        raise _Undecodable(type(exc).__name__) from None
    lab = F._lab(rgb)
    bg, spread = F._background(lab)
    if not math.isfinite(spread) or spread > F.BG_SPREAD_MAX:
        return None, lab, f"background is not one plain surface (p90 spread {spread:.1f})"
    fg = F._de(lab, bg) > SEP_DE
    fg = ndimage.binary_opening(fg, iterations=1)
    fg = ndimage.binary_closing(fg, iterations=2)
    labels, n = ndimage.label(fg)
    if n == 0:
        return None, lab, "no product separated from the surface"
    sizes = ndimage.sum(fg, labels, range(1, n + 1))
    biggest = int(np.argmax(sizes)) + 1
    mask = ndimage.binary_fill_holes(labels == biggest)
    if mask.mean() < MIN_PRODUCT_FRAC:
        return None, lab, f"product is {mask.mean():.1%} of the frame"
    return mask, lab, ""


def corner_count(mask: np.ndarray) -> tuple[int, dict]:
    """Corners of a top-down outline: prominent maxima of the boundary radius by angle."""
    from scipy import ndimage

    edge = mask & ~ndimage.binary_erosion(mask)
    ys, xs = np.nonzero(edge)
    cy, cx = np.nonzero(mask)[0].mean(), np.nonzero(mask)[1].mean()
    ang = (np.degrees(np.arctan2(ys - cy, xs - cx)) + 360.0) % 360.0
    rad = np.hypot(ys - cy, xs - cx)
    prof = np.full(360, np.nan)
    for b, r in zip(ang.astype(int) % 360, rad):
        if not prof[b] >= r:
            prof[b] = r
    idx = np.arange(360)
    ok = ~np.isnan(prof)
    prof = np.interp(idx, idx[ok], prof[ok], period=360)
    k = np.ones(SMOOTH_DEG) / SMOOTH_DEG
    prof = np.convolve(np.concatenate([prof[-SMOOTH_DEG:], prof, prof[:SMOOTH_DEG]]), k,
                       mode="same")[SMOOTH_DEG:-SMOOTH_DEG]
    mean = float(prof.mean())
    peaks = []
    for i in range(360):
        win = prof[[(i + d) % 360 for d in range(-PEAK_WINDOW_DEG, PEAK_WINDOW_DEG + 1)]]
        if prof[i] < win.max():
            continue
        low = prof[[(i + d) % 360 for d in range(-30, 31)]].min()
        if (prof[i] - low) / mean >= PEAK_PROMINENCE:
            if not peaks or i - peaks[-1] > PEAK_WINDOW_DEG:
                peaks.append(i)
    if len(peaks) > 1 and (peaks[0] + 360 - peaks[-1]) <= PEAK_WINDOW_DEG:
        peaks.pop()
    return len(peaks), {"peaks_deg": peaks, "mean_radius_px": round(mean, 1),
                        "points_to_flats": round(float(prof.max() / max(prof.min(), 1e-9)), 3)}


def _palette_arrays(palette: dict[str, str]):
    ids = list(palette)
    rgb = np.array([[F._hex_rgb(palette[i]) for i in ids]], dtype=np.float64)
    return ids, F._lab(rgb)[0], F._lin(rgb)[0]


def _wall_pixels(mask: np.ndarray) -> np.ndarray:
    """The wall's centre column (CENTRE_COLUMN of each row's span) inside the product mask."""
    sel = np.zeros_like(mask, dtype=bool)
    for y in np.nonzero(mask.any(axis=1))[0]:
        row = np.nonzero(mask[y])[0]
        x0, x1 = row.min(), row.max()
        a, b = int(x0 + CENTRE_COLUMN[0] * (x1 - x0)), int(x0 + CENTRE_COLUMN[1] * (x1 - x0))
        sel[y, a:b + 1] = mask[y, a:b + 1]
    return sel


def illumination_corrected(rgb: np.ndarray, mask: np.ndarray, palette: dict[str, str]):
    """IMAGES-DIALIN: the side view in Lab after the gate's own bounded illumination correction.

    Every other colour check in the stack corrects for the light before it compares a pixel
    with a declared hex: the flat and round anchor paths and the lifestyle region
    (`fidelity._illumination`, per-channel gain clamped to `fidelity.GAIN_RANGE`), and the
    owner-frame stripe check (`owner_frames.bands_in_column`). This check compared raw pixels
    with the hex, so the shaded side of a correctly coloured cream wall read off-palette. The
    same bounded gain is fitted here on the wall's centre column; a substituted colour needs
    more than the clamp allows and still reads off the palette."""
    from types import SimpleNamespace

    ids, pal_lab, pal_lin = _palette_arrays(palette)
    lin = F._lin(rgb)
    wall = _wall_pixels(mask)
    exp = SimpleNamespace(palette_lab=pal_lab, palette_lin=pal_lin)
    ill = F._illumination(lin[wall], exp)
    lin_c = lin * ill["gain"]
    return F._lab_from_lin(lin_c), {"gain": [round(float(g), 3) for g in ill["gain"]],
                                    "gain_clamped": bool(ill["clamped"])}


def colour_centres(lab_c: np.ndarray, mask: np.ndarray, palette: dict[str, str]) -> dict:
    """Each declared colour's measured cluster centre on the wall (after correction), as
    `fidelity._palette_check` measures it. Evidence only (see `verify_side`)."""
    ids, pal_lab, _ = _palette_arrays(palette)
    px = lab_c[_wall_pixels(mask)]
    if px.size == 0:
        return {}
    lbl = F._de(px[:, None, :], pal_lab[None, :, :]).argmin(axis=1)
    out = {}
    for j, cid in enumerate(ids):
        sel = lbl == j
        if sel.sum() < 0.005 * len(lbl):
            continue
        out[cid] = round(float(F._de(px[sel].mean(axis=0), pal_lab[j])), 1)
    return out


def _steep_run(xs: np.ndarray, win: int) -> tuple[int, int]:
    """The longest run of rows over which an outline x(y) is the wall's own side line.

    Two passes: the rows within STEEP_SLOPE of vertical, then, around that run's own median
    slope (a flared or tapered wall is straight, not vertical), only the rows within
    WALL_SLOPE_TOL of it at either end, so the curve of a rounded rim or base is not counted
    as wall."""
    n = len(xs)
    if n < 3:
        return 0, n
    from scipy import ndimage

    k = max(1, win)
    xs = ndimage.median_filter(np.asarray(xs, dtype=float), size=2 * k + 1, mode="nearest")
    slopes = np.array([(float(xs[min(n - 1, y + k)]) - float(xs[max(0, y - k)]))
                       / max(min(n - 1, y + k) - max(0, y - k), 1) for y in range(n)])

    def longest(ok):
        best_len = cur = 0
        best = (0, 0)
        for y in range(n):
            cur = cur + 1 if ok[y] else 0
            if cur > best_len:
                best_len, best = cur, (y - cur + 1, y + 1)
        return best

    a, b = longest(np.abs(slopes) <= STEEP_SLOPE)
    if b <= a:
        return 0, 0
    own = float(np.median(slopes[a:b]))
    on = np.nonzero(np.abs(slopes[a:b] - own) <= WALL_SLOPE_TOL)[0]
    # Only the ends are trimmed (the rim's and the base's curves); a bump in the middle of
    # the wall (a raised round, a stitch) never splits it.
    return (int(a + on[0]), int(a + on[-1] + 1)) if on.size else (0, 0)


def near_wall(mask: np.ndarray) -> dict:
    """Where the near wall ends in a side view: rows above it are the opening (IMAGE-FIDELITY-2).

    The wall's projected height is read where the outline IS the wall: the left and right
    outlines run steeply (within STEEP_SLOPE of vertical) from the base corner to the rim
    corner, or along the tangent line of a round wall; above and below they turn inward
    along the rim and the base. The centre column runs from the near base up to the FAR rim;
    when it is taller than the wall by more than OPENING_MIN, the rows above
    `cut_from_bottom_px` show the inside of the far wall and are not wall bands. At eye level
    the outline is steep from base to rim, the centre is no taller and nothing is cut."""
    rows = np.nonzero(mask.any(axis=1))[0]
    top, bottom = int(rows.min()), int(rows.max())
    height = bottom - top + 1
    left = np.array([np.nonzero(mask[y])[0].min() if mask[y].any() else -1
                     for y in range(top, bottom + 1)], dtype=float)
    right = np.array([np.nonzero(mask[y])[0].max() if mask[y].any() else -1
                      for y in range(top, bottom + 1)], dtype=float)
    win = max(2, int(round(SLOPE_WINDOW * height)))
    (la, lb), (ra, rb) = _steep_run(left, win), _steep_run(right, win)
    side_l, side_r = lb - la, rb - ra
    side = (side_l + side_r) / 2.0
    cols = np.nonzero(mask.any(axis=0))[0]
    x0, x1 = int(cols.min()), int(cols.max())
    width = x1 - x0 + 1
    a, b = int(x0 + CENTRE_COLUMN[0] * width), int(x0 + CENTRE_COLUMN[1] * width)
    centre = []
    for x in range(a, b + 1):
        ys = np.nonzero(mask[:, x])[0]
        if ys.size:
            centre.append(int(ys.max() - ys.min() + 1))
    centre_px = float(np.median(centre)) if centre else 0.0
    ratio = centre_px / side if side else 1.0
    opening = bool(side > 0 and ratio > 1.0 + OPENING_MIN)
    return {"side_px": round(side, 1), "left_px": int(side_l), "right_px": int(side_r),
            "centre_px": round(centre_px, 1), "ratio": round(ratio, 3), "opening": opening,
            "bottom": bottom, "cut_from_bottom_px": round(side, 1) if opening else None,
            "wall_rows": [top + max(la, ra), top + min(lb, rb)]}


def _rim_bulge_through_opening(mask: np.ndarray, view: dict) -> float:
    """The rim check for a view that shows the opening: the silhouette's width just above
    and at the top of the rows where both side outlines are the wall, over its width there.
    A rim that juts out (rolled, braided) widens the outline where the wall line ends."""
    ya, yb = view["wall_rows"]
    if yb - ya < 4:
        return 1.0
    widths = {}
    for y in range(max(0, ya - int(0.1 * (yb - ya))), yb):
        xs = np.nonzero(mask[y])[0]
        if xs.size:
            widths[y] = int(xs.max() - xs.min() + 1)
    wall = [w for y, w in widths.items() if ya <= y < yb]
    rim = [w for y, w in widths.items() if y < ya + max(1, int(RIM_STRIP * (yb - ya)))]
    if not wall or not rim:
        return 1.0
    return float(np.percentile(rim, 90) / max(np.median(wall), 1e-9))


def _bands(mask: np.ndarray, lab: np.ndarray, palette: dict[str, str], rows_total: int = 1):
    ys, xs = np.nonzero(mask)
    top, bottom = ys.min(), ys.max()
    # An "off" run thinner than half a wall row is the edge blending into the surface
    # (blur, rotation, JPEG), not a band: it is merged like any too-short run.
    min_off = OFF_MIN_ROWS * (bottom - top + 1) / max(rows_total, 1)
    ids, pal, _ = _palette_arrays(palette)
    labels, widths = [], []
    on_px = total_px = 0
    for y in range(bottom, top - 1, -1):                  # bottom to top
        row = np.nonzero(mask[y])[0]
        if row.size == 0:
            continue
        x0, x1 = row.min(), row.max()
        widths.append(x1 - x0 + 1)
        a, b = int(x0 + CENTRE_COLUMN[0] * (x1 - x0)), int(x0 + CENTRE_COLUMN[1] * (x1 - x0))
        px = lab[y, a:b + 1][mask[y, a:b + 1]]
        if px.size == 0:
            labels.append(None)
            continue
        dist = F._de(px[:, None, :], pal[None, :, :])
        cls = dist.argmin(axis=1)
        # IMAGES-DIALIN: on the palette means what it means everywhere else in the gate --
        # within OFF_PALETTE_DE of a declared colour or of a two-colour mix
        # (`fidelity._seg_distance`), the blend where a stitch of one colour shadows or
        # meets the next. The row's label is still the nearest declared colour.
        ok = F._seg_distance(px, pal) <= F.OFF_PALETTE_DE
        on_px += int(ok.sum())
        total_px += int(ok.size)
        # Review V2 F1: a pixel is only a palette colour if it is near one. A row mostly
        # off the palette is "off", so a wrong colourway cannot pass as the right bands.
        if ok.mean() < 1.0 - OFF_ROW_FRAC:
            labels.append("off")
            continue
        labels.append(ids[int(np.bincount(cls[ok], minlength=len(ids)).argmax())])
    runs: list[list] = []
    for lab_id in labels:
        if runs and runs[-1][0] == lab_id:
            runs[-1][1] += 1
        else:
            runs.append([lab_id, 1])
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for i, (cid, n) in enumerate(runs):
            if n < MIN_BAND_PX or cid is None or (cid == "off" and n < min_off):
                j = i - 1 if i > 0 else i + 1
                runs[j][1] += n
                del runs[i]
                k = 0
                while k < len(runs) - 1:               # re-merge equal neighbours
                    if runs[k][0] == runs[k + 1][0]:
                        runs[k][1] += runs.pop(k + 1)[1]
                    else:
                        k += 1
                changed = True
                break
    coverage = on_px / total_px if total_px else 0.0
    return runs, widths, bottom - top + 1, coverage


# ---- the verifier ---------------------------------------------------------------------------

def verify_top(data: bytes, model: VesselModel) -> dict:
    name = f"{model.component}:sides"
    try:
        mask, _lab, why = _product_mask(data)
    except _Undecodable as exc:
        # Same shape as fidelity's round-path decode FAIL (no repair code: regenerate).
        return F._check(name, F.FAIL, f"the top view is not a decodable image ({exc})")
    if mask is None:
        return F._check(name, F.UNKNOWN, why, code="UNVERIFIABLE_COUNT")
    if model.sides is None:
        # Review V2 F2: a side count the twin cannot state is a verification gap.
        return F._check(name, F.UNKNOWN, "the twin states no side count for this vessel",
                        code="UNVERIFIABLE_COUNT")
    n, measured = corner_count(mask)
    if measured["mean_radius_px"] < MIN_TOP_RADIUS_PX:
        # Review V2 F3: a tiny outline's corners are not countable.
        return F._check(name, F.UNKNOWN, f"outline radius {measured['mean_radius_px']} px is "
                                         f"under {MIN_TOP_RADIUS_PX} px; corners not countable",
                        code="UNVERIFIABLE_COUNT", **measured)
    ok = n == model.sides          # 0 for a round vessel: a round outline has no corners
    shape = "round" if model.sides == 0 else f"{model.sides}-sided"
    return F._check(name, F.PASS if ok else F.FAIL,
                    f"{n} corners counted from above, the CIR makes a {shape} vessel",
                    code="WRONG_REPEAT_COUNT", counted=n, expected=model.sides, **measured)


def verify_side(data: bytes, model: VesselModel) -> list[dict]:
    name = model.component
    try:
        mask, lab, why = _product_mask(data)
    except _Undecodable as exc:
        return [F._check(f"{name}:wall_bands", F.FAIL,
                         f"the side view is not a decodable image ({exc})")]
    if mask is None:
        return [F._check(f"{name}:wall_bands", F.UNKNOWN, why, code="UNVERIFIABLE_COUNT")]
    full_mask, rgb = mask, F._load(data)
    view = near_wall(mask)
    interior = None
    if view["opening"]:
        lab_full, _light = illumination_corrected(rgb, full_mask, model.palette)
        mask, view = _near_mask(full_mask, lab_full, view, model)
    lab, light = illumination_corrected(rgb, mask, model.palette)
    runs, widths, height, coverage = _bands(mask, lab, model.palette, model.wall_total_rows)
    if view["opening"]:
        # Recorded, not judged: the inside of the far wall seen through the opening.
        above = full_mask & ~mask
        above[view["bottom"] - int(round(view["cut_from_bottom_px"])) + 1:, :] = False
        if above.any():
            interior = [r[0] for r in _bands(above, lab, model.palette,
                                             model.wall_total_rows)[0]]
    light = {**light, "view": {**view, "interior_bands": interior}}
    if height / max(model.wall_total_rows, 1) < MIN_PX_PER_ROW:
        return [F._check(f"{name}:wall_bands", F.UNKNOWN,
                         f"{height} px for {model.wall_total_rows} wall rows",
                         code="UNVERIFIABLE_COUNT")]
    seen = [r[0] for r in runs]
    # Recorded, not judged: on a textured photograph the nearest-colour cluster of a dark
    # yarn also collects the shadow between pale stitches, so a centre test there reads the
    # stitch gaps rather than the yarn (measured on the owner's hero frame: "wine" raw centre
    # #5F3F3A). The coverage rule below is the check; a substituted colourway reads ~0 %.
    centres = colour_centres(lab, mask, model.palette)
    pal_check = F._check(f"{name}:palette",
                         F.PASS if coverage >= PALETTE_COVERAGE_MIN else F.FAIL,
                         f"{coverage:.0%} of the wall is within {F.OFF_PALETTE_DE:g} dE of "
                         f"the CIR's colours or their mixes after illumination correction "
                         f"(needs {PALETTE_COVERAGE_MIN:.0%})",
                         code="OFF_PALETTE_COLOUR", coverage=round(coverage, 3),
                         centre_de=centres, **light)
    out = [pal_check]
    expected = list(model.wall_bands)
    extra_top = len(seen) == len(expected) + 1 and seen[:-1] == expected
    if view["opening"]:
        bulge = _rim_bulge_through_opening(full_mask, view)
    else:
        rim_w = np.median(widths[-max(1, int(RIM_STRIP * len(widths))):])
        wall_w = np.median(widths[: max(1, int(0.8 * len(widths)))])
        bulge = float(rim_w / max(wall_w, 1e-9))
    if seen == expected:
        shares = [r[1] / height for r in runs]
        want = list(model.wall_shares)
        worst_rel = max(abs(s - w) / w for s, w in zip(shares, want))
        out.append(F._check(f"{name}:wall_bands",
                            F.PASS if worst_rel <= SHARE_REL_MAX else F.FAIL,
                            f"bands {seen} bottom to top; worst share off by "
                            f"{worst_rel:.0%}", code="WRONG_COLOUR_LAYOUT",
                            bands=seen, shares=[round(s, 3) for s in shares],
                            expected_shares=[round(w, 3) for w in want]))
    elif extra_top:
        out.append(F._check(f"{name}:wall_bands", F.PASS,
                            f"wall bands {expected} match below an extra top band",
                            bands=seen))
    else:
        out.append(F._check(f"{name}:wall_bands", F.FAIL,
                            f"bands {seen} bottom to top; the CIR's wall is {expected}",
                            code="WRONG_COLOUR_LAYOUT", bands=seen, expected=expected))
    rim_bad = extra_top or bulge > RIM_WIDTH_RATIO
    out.append(F._check(f"{name}:rim", F.FAIL if rim_bad else F.PASS,
                        (f"a top band {seen[-1]!r} the CIR does not work" if extra_top else
                         f"top-strip width {bulge:.3f}x the wall's" if rim_bad else
                         f"plain {model.rim_colour} rim; top-strip width {bulge:.3f}x the wall's"),
                        code="INVENTED_EDGING", rim_width_ratio=round(bulge, 3)))
    return out


def _near_mask(mask: np.ndarray, lab: np.ndarray, view: dict, model: VesselModel):
    """The side view's mask cut to the near wall (rows above it are the opening).

    The cut is the measured wall height above the bottom, moved to the nearest colour
    boundary of the centre column only when one lies within half the thinnest declared band
    (so a band edge is not split by a few pixels of perspective); never further, so no
    declared band can be cut away by the snap."""
    cut = float(view["cut_from_bottom_px"])
    bottom = view["bottom"]
    snap = 0.5 * min(model.wall_shares or [1.0]) * cut
    runs = _bands(mask, lab, model.palette, model.wall_total_rows)[0]
    boundaries, h = [], 0
    for _cid, n in runs[:-1]:
        h += n
        boundaries.append(h)
    near = [b for b in boundaries if abs(b - cut) <= snap]
    if near:
        cut = float(min(near, key=lambda b: abs(b - cut)))
    out = mask.copy()
    out[: bottom - int(round(cut)) + 1, :] = False
    return out, {**view, "cut_from_bottom_px": round(cut, 1), "snap_px": round(snap, 1)}


def verify(top: bytes, side: bytes, cir) -> dict:
    """The vessel anchor verdict from a top-down and a side view of the product alone."""
    models = vessel_models(cir)
    if not models:
        checks = [F._check("vessel", F.NA, "the design has no vessel component")]
    else:
        checks = []
        for m in models:
            if not m.modelled:
                checks.append(F._check(f"{m.component}:vessel_model", F.UNKNOWN,
                                       "the twin is a vessel but its wall cannot be modelled "
                                       "(no constant trailing rounds)",
                                       code="UNVERIFIABLE_COUNT"))
                continue
            checks.append(verify_top(top, m))
            checks.extend(verify_side(side, m))
    status = F.worst(c["status"] for c in checks)
    codes = [] if status == F.PASS else sorted(
        {c["code"] for c in checks if c.get("code") and c["status"] in (F.FAIL, F.UNKNOWN)})
    return {"status": status, "checker": CHECKER, "kind": "vessel_anchor", "checks": checks,
            "codes": codes, "failed": [c["check"] for c in checks if c["status"] == F.FAIL],
            "unknown": [c["check"] for c in checks if c["status"] == F.UNKNOWN],
            "image_sha256": {"top": hashlib.sha256(top).hexdigest(),
                             "side": hashlib.sha256(side).hexdigest()},
            "slug": cir.slug, "version": cir.version, "blind_spots": list(BLIND_SPOTS),
            "reads_generator_claims": False}
