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

CHECKER = "visual.vessel 1.0.0"
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
        bands, sizes = [], []
        for c in colours:
            if bands and bands[-1] == c:
                sizes[-1] += 1
            else:
                bands.append(c)
                sizes.append(1)
        out.append(VesselModel(comp.name, twin.sides, bands, sizes, colours[-1],
                               len(counts) - wall_n, wall_n, dict(cir.colors)))
    return out


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


def _bands(mask: np.ndarray, lab: np.ndarray, palette: dict[str, str], rows_total: int = 1):
    ys, xs = np.nonzero(mask)
    top, bottom = ys.min(), ys.max()
    # An "off" run thinner than half a wall row is the edge blending into the surface
    # (blur, rotation, JPEG), not a band: it is merged like any too-short run.
    min_off = OFF_MIN_ROWS * (bottom - top + 1) / max(rows_total, 1)
    ids = list(palette)
    pal = np.array([F._lab(np.array([[F._hex_rgb(palette[i])]], dtype=np.float64))[0, 0]
                    for i in ids])
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
        cls, near = dist.argmin(axis=1), dist.min(axis=1)
        ok = near <= F.OFF_PALETTE_DE
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
    runs, widths, height, coverage = _bands(mask, lab, model.palette, model.wall_total_rows)
    if height / max(model.wall_total_rows, 1) < MIN_PX_PER_ROW:
        return [F._check(f"{name}:wall_bands", F.UNKNOWN,
                         f"{height} px for {model.wall_total_rows} wall rows",
                         code="UNVERIFIABLE_COUNT")]
    seen = [r[0] for r in runs]
    out = [F._check(f"{name}:palette", F.PASS if coverage >= PALETTE_COVERAGE_MIN else F.FAIL,
                    f"{coverage:.0%} of the wall is within {F.OFF_PALETTE_DE:g} dE of the "
                    f"CIR's colours (needs {PALETTE_COVERAGE_MIN:.0%})",
                    code="OFF_PALETTE_COLOUR", coverage=round(coverage, 3))]
    expected = list(model.wall_bands)
    extra_top = len(seen) == len(expected) + 1 and seen[:-1] == expected
    rim_w = np.median(widths[-max(1, int(RIM_STRIP * len(widths))):])
    wall_w = np.median(widths[: max(1, int(0.8 * len(widths)))])
    bulge = float(rim_w / max(wall_w, 1e-9))
    if seen == expected:
        shares = [r[1] / height for r in runs]
        want = [n / model.wall_total_rows for n in model.wall_rows]
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
