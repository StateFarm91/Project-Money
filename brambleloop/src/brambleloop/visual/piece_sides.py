"""Flat-piece polygon side count (ENG-COASTER-SIDES): `<component>:sides`, WRONG_SIDE_COUNT.

Production 2026-11-26: hexagon-coaster-set@1.2.1's accepted product anchor (candidate 40)
shows four six-sided coasters, but every derivative gallery frame (62 hero, 63 colour_context,
64 angle, 65 detail, 66 size) shows OCTAGONS. Those frames were recorded "unverified"
(product_truth UNKNOWN, because region_palette was unknown). No check ever counted a flat
piece's sides; only vessels had one (`basket:sides`, `visual.vessel.verify_top`). An
eight-sided coaster is the wrong product. It is now REJECTED deterministically by name, so the
repair loop can target it ("coaster has 8 sides; must be 6").

**What is expected comes from the release's own CIR.** It is the digital twin's `sides` for
a flat piece worked in rounds (`cir.geometry.corners`: stacked increases at n corner columns).
A hexagon gives 6, a square 4 and an octagon 8. A round piece (0) and a piece the twin
cannot name (None) have no side count, and the check is not applied. Nothing here names a
product.

**How a piece is measured.** Each segmented piece's outline is measured by contour and
polygon approximation:
  1. affine-normalise: the piece's pixel covariance is whitened (a regular polygon and a
     circle have isotropic second moments, so this undoes the foreshortening of an oblique
     camera to first order); foreshortening beyond FORESHORTEN_MAX is unreadable;
  2. the outline as a closed contour by angle: the radius of its convex hull along each
     degree's ray (the hull spans the stitch scallops, which a per-degree pixel maximum
     aliases into false corners), smoothed over SMOOTH_DEG;
  3. corners are radius maxima over +-PEAK_WINDOW_DEG standing PEAK_PROMINENCE (of the mean
     radius) above the lowest radius within +-30 degrees (the `visual.vessel` corner rule,
     same values; a regular hexagon stands 0.14, an octagon 0.077, a circle 0);
  4. the polygon approximation must hold: each side, a straight line fitted to the middle
     EDGE_SPAN of the contour between two corners (so a rounded corner is allowed), or with
     no corners the circle of the mean radius, within median FIT_MAX of the mean radius.
     Otherwise the outline is not a clean polygon (folded, occluded, merged with another
     piece), and the piece is unreadable.
  A piece is also unreadable when its solidity is below MIN_SOLIDITY, its mean radius is
  below MIN_RADIUS_PX, or the twin's side count is above MAX_SIDES (corners closer than
  2 x PEAK_WINDOW_DEG cannot be resolved).

**Verdict.** FAIL when any readable piece's count differs from the CIR's. PASS only when at
least one piece was read and every readable piece matches. Otherwise UNKNOWN. A frame whose
pieces cannot be segmented is UNKNOWN, never PASS. The one exception is a close-up role
(CLOSE_UP_ROLES, whose brief is a crop of the fabric): with no whole piece in it, the check
is not applicable (NA, which is not PASS) and that frame is judged by its other checks.

**Segmentation on generated frames that are not anchors** (hero, colour_context, angle,
size, ...). First the anchor's plain-background isolation (`fidelity._isolate`). Failing that,
the yarn itself: pixels within OFF_PALETTE_DE of the palette or a two-colour mix. A connected
component counts as a piece only when it is whole (it does not touch the frame edge), convex
(solidity), large enough, and made of the piece's colours: every declared colour that is at
least 5 % of the piece is present at >= MISSING_SHARE of its expected share. So a cream mug
or a plate is not a coaster, and an octagon in the coaster's colours is one.

A vision judge, where one is wired, may corroborate (`corroborate`). It never overrides a
deterministic reading: a deterministic FAIL stays FAIL, and a vision reading alone never PASSes.
"""
from __future__ import annotations

import math

import numpy as np

VERSION = "piece-sides/1"
PEAK_WINDOW_DEG = 18        # a corner is a radius maximum over +- this many degrees
PEAK_PROMINENCE = 0.035     # ... standing this far (fraction of the mean radius) above the
                            # lowest radius within +- 30 degrees (= visual.vessel)
SMOOTH_DEG = 7              # contour smoothing; the stitch scallops are ~4 degrees apart
FIT_MAX = 0.02              # median |contour - approximating polygon| / mean radius
EDGE_SPAN = 0.6             # each side's line is fitted over the middle 60 % between corners
MIN_SOLIDITY = 0.90         # piece area / convex hull area
MIN_RADIUS_PX = 40          # below this mean radius (analysis pixels) corners are unreadable
FORESHORTEN_MAX = 2.5       # whitening stretch beyond this: too oblique to read
MAX_SIDES = 9               # 360 / 9 = 40 deg > 2 x PEAK_WINDOW_DEG
MIN_AREA = 0.002            # of the frame (= fidelity.MIN_PIECE_AREA)
MISSING_SHARE = 0.25        # a declared colour at < 25 % of its expected share is absent
SIGNIFICANT_SHARE = 0.05    # ... checked for colours at least this share of the piece
CLOSE_UP_ROLES = frozenset({"detail"})

TOLERANCE = (f"{VERSION}: affine-normalised outline (stretch <= {FORESHORTEN_MAX}), smoothed "
             f"{SMOOTH_DEG} deg; corner = radius maximum over +-{PEAK_WINDOW_DEG} deg with "
             f"prominence >= {PEAK_PROMINENCE} of the mean radius; each side a straight line over "
             f"the middle {EDGE_SPAN:.0%} between corners (or the mean circle) within median "
             f"{FIT_MAX:.0%} of the mean radius; "
             f"solidity >= {MIN_SOLIDITY}; mean radius >= {MIN_RADIUS_PX} px; sides <= "
             f"{MAX_SIDES}; exact count")


def expected_sides(model) -> int | None:
    """The CIR's side count for a flat piece model, or None when no side count applies."""
    n = getattr(model, "sides", None)
    return int(n) if isinstance(n, int) and n >= 3 else None


def _solidity(mask: np.ndarray) -> float:
    from scipy.spatial import ConvexHull

    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], axis=1).astype(float)
    if len(pts) < 10:
        return 0.0
    try:
        hull = ConvexHull(pts).volume
    except Exception:  # noqa: BLE001 - degenerate (a line) is not a piece
        return 0.0
    return float(mask.sum()) / max(hull, 1.0)


def count_sides(mask: np.ndarray) -> dict:
    """The side count of one piece's mask: {"sides": n | None, "readable": bool, ...}.

    `sides` 0 is a round outline. `readable` False carries `why`."""
    from scipy import ndimage

    ys, xs = np.nonzero(mask)
    out: dict = {"area_px": int(len(ys))}
    if len(ys) < 50:
        return {**out, "sides": None, "readable": False, "why": "piece too small"}
    solidity = _solidity(mask)
    out["solidity"] = round(solidity, 3)
    if solidity < MIN_SOLIDITY:
        return {**out, "sides": None, "readable": False,
                "why": f"solidity {solidity:.2f}: folded, occluded or touching another piece"}
    cy, cx = ys.mean(), xs.mean()
    cov = np.cov(np.stack([xs - cx, ys - cy]))
    w, v = np.linalg.eigh(cov)
    w = np.maximum(w, 1e-9)
    stretch = float(math.sqrt(w.max() / w.min()))
    out["foreshortening"] = round(stretch, 3)
    if stretch > FORESHORTEN_MAX:
        return {**out, "sides": None, "readable": False,
                "why": f"seen too obliquely (stretch {stretch:.2f} > {FORESHORTEN_MAX})"}
    # whiten to the major axis' scale: u = V diag(sqrt(wmax / w)) V^T (p - c)
    m = v @ np.diag(np.sqrt(w.max() / w)) @ v.T
    edge = mask & ~ndimage.binary_erosion(mask)
    ey, ex = np.nonzero(edge)
    p = m @ np.stack([ex + 0.5 - cx, ey + 0.5 - cy])
    # the contour: the radius of the outline's convex hull along each degree's ray. A crochet
    # outline is scalloped (one bump per edge stitch); the furthest pixel per degree samples
    # tips in some bins and valleys in others, a low-frequency beat that reads as corners on
    # a circle. The hull spans the tips; concave defects are the solidity limit's to catch.
    from scipy.spatial import ConvexHull

    pts = p.T
    hull = pts[ConvexHull(pts).vertices]
    a, b = hull, np.roll(hull, -1, axis=0)
    e = b - a
    idx = np.arange(360)
    th = np.radians(idx + 0.5)
    d = np.stack([np.cos(th), np.sin(th)], axis=1)                     # (360, 2)
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]  # (360, H)
    t_ray = (a[None, :, 0] * e[None, :, 1] - a[None, :, 1] * e[None, :, 0]) / np.where(
        np.abs(den) > 1e-12, den, np.nan)
    u = (a[None, :, 0] * d[:, None, 1] - a[None, :, 1] * d[:, None, 0]) / np.where(
        np.abs(den) > 1e-12, den, np.nan)
    hit = (t_ray > 0) & (u >= -1e-9) & (u <= 1 + 1e-9)
    prof = np.where(hit, t_ray, np.nan)
    if np.isnan(prof).all(axis=1).any():
        return {**out, "sides": None, "readable": False, "why": "outline not star-shaped"}
    prof = np.nanmax(prof, axis=1)
    k = np.ones(SMOOTH_DEG) / SMOOTH_DEG
    prof = np.convolve(np.concatenate([prof[-SMOOTH_DEG:], prof, prof[:SMOOTH_DEG]]), k,
                       mode="same")[SMOOTH_DEG:-SMOOTH_DEG]
    mean = float(prof.mean())
    out["mean_radius_px"] = round(mean, 1)
    if mean < MIN_RADIUS_PX:
        return {**out, "sides": None, "readable": False,
                "why": f"mean radius {mean:.0f} px < {MIN_RADIUS_PX} px; corners not countable"}
    peaks: list[int] = []
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
    n = len(peaks)
    out["corners_deg"] = peaks
    out["points_to_flats"] = round(float(prof.max() / max(prof.min(), 1e-9)), 3)
    # polygon approximation: each side is a straight line fitted (total least squares) to
    # the contour over the middle EDGE_SPAN of its angular span between two corners, so a
    # rounded corner (as every crochet corner is) does not count against the fit; with no
    # corners, the circle of the mean radius
    xy = np.stack([prof * np.cos(np.radians(idx + 0.5)), prof * np.sin(np.radians(idx + 0.5))],
                  axis=1)
    if n == 0:
        dev = np.abs(prof - mean)
    elif n < 3:
        return {**out, "sides": None, "readable": False,
                "why": f"{n} corner(s): neither a polygon nor a round outline"}
    else:
        devs = []
        for j in range(n):
            a0, a1 = peaks[j], peaks[(j + 1) % n] + (360 if j == n - 1 else 0)
            span = a1 - a0
            lo, hi = a0 + (1 - EDGE_SPAN) / 2 * span, a1 - (1 - EDGE_SPAN) / 2 * span
            sel = xy[[int(round(a)) % 360 for a in np.arange(lo, hi + 1e-9)]]
            if len(sel) < 3:
                continue
            c0 = sel.mean(axis=0)
            _, _, vt = np.linalg.svd(sel - c0)
            devs.append(np.abs((sel - c0) @ vt[1]))
        dev = np.concatenate(devs) if devs else np.array([np.inf])
    fit = float(np.median(dev) / mean)
    out["fit"] = round(fit, 4)
    if fit > FIT_MAX:
        return {**out, "sides": None, "readable": False,
                "why": f"the outline is not a clean polygon (fit {fit:.3f} > {FIT_MAX})"}
    return {**out, "sides": n, "readable": True}


def _shape_word(n: int | None) -> str:
    return {0: "round", 3: "a triangle", 4: "a square", 5: "a pentagon", 6: "a hexagon",
            7: "a heptagon", 8: "an octagon"}.get(n, f"{n}-sided") if n is not None else "?"


def judge(name: str, readings: list[dict], expected: int, *, close_up: bool = False,
          segmented_why: str = "") -> dict:
    """The `<name>:sides` check from per-piece readings (see the module docstring)."""
    from . import fidelity as F

    check = f"{name}:sides"
    measured = {"expected": expected, "tolerance": TOLERANCE,
                "pieces": [{k: v for k, v in r.items() if k != "mask"} for r in readings]}
    if expected > MAX_SIDES:
        return F._check(check, F.UNKNOWN, f"{expected} sides cannot be resolved at "
                                          f"+-{PEAK_WINDOW_DEG} deg", code=F.FC.UNVERIFIABLE_COUNT,
                        **measured)
    read = [r for r in readings if r.get("readable")]
    wrong = [r for r in read if r["sides"] != expected]
    if wrong:
        seen = sorted({r["sides"] for r in wrong})

        def words(k):
            return "round (no corners)" if k == 0 else f"{k} sides"

        counted = ", ".join(words(k) for k in seen)
        # the repair names the count most pieces show (one noisy outline must not muddle it)
        tally = [r["sides"] for r in wrong]
        mode = max(seen, key=lambda k: (tally.count(k), -k))
        fix = f"{name} has {words(mode)}; must be {expected} ({_shape_word(expected)})"
        return F._check(check, F.FAIL, f"{len(wrong)} of {len(read)} readable piece(s): "
                                       f"{counted}; the CIR makes {_shape_word(expected)} "
                                       f"({expected} sides)",
                        code=F.FC.WRONG_SIDE_COUNT, counted=seen, fix=fix, **measured)
    if read:
        return F._check(check, F.PASS, f"{len(read)} piece(s) read with {expected} sides, as "
                                       f"the CIR makes", counted=[expected], **measured)
    if close_up and not readings:
        return F._check(check, F.NA, "a close-up: no whole piece is in view, so no side count "
                                     "applies to this frame", **measured)
    why = segmented_why or ("; ".join(sorted({r.get("why", "") for r in readings}))[:200]
                            or "no whole piece could be segmented")
    return F._check(check, F.UNKNOWN, f"sides not countable: {why}",
                    code=F.FC.UNVERIFIABLE_COUNT, **measured)


def _composition_ok(lab: np.ndarray, mask: np.ndarray, model, exp) -> bool:
    """The component is made of the piece's colours (each significant one present)."""
    from . import fidelity as F

    expected = None
    if getattr(model, "radial", None) is not None:
        expected = model.radial.mean(axis=0)
    elif getattr(model, "classes", None) is not None:
        expected = np.bincount(model.classes.ravel(), minlength=len(exp.palette_ids))
        expected = expected / max(expected.sum(), 1)
    if expected is None:
        return True
    px = lab[mask]
    cls = F._de(px[:, None, :], exp.palette_lab).argmin(axis=-1)
    got = np.bincount(cls, minlength=len(exp.palette_ids)) / max(len(cls), 1)
    return all(got[i] >= MISSING_SHARE * expected[i]
               for i in range(len(expected)) if expected[i] >= SIGNIFICANT_SHARE)


def segment_whole_pieces(rgb: np.ndarray, exp, model) -> tuple[list[np.ndarray], str]:
    """Masks of whole pieces in a frame that is not an anchor ([] and why when none)."""
    from scipy import ndimage

    from . import fidelity as F

    lab = F._lab(rgb)
    h, w = lab.shape[:2]
    iso = F._isolate(rgb, exp)
    cands: list[np.ndarray] = []
    if iso["check"]["status"] == F.PASS:
        cands = [p["mask"] for p in iso["pieces"]]
        why = ""
    else:
        why = iso["check"]["why"]
    if not cands:
        yarn = F._seg_distance(lab, exp.palette_lab) <= F.OFF_PALETTE_DE
        yarn = ndimage.binary_opening(yarn, iterations=1)
        yarn = ndimage.binary_closing(yarn, iterations=2)
        yarn = ndimage.binary_fill_holes(yarn)
        lbl, n = ndimage.label(yarn)
        for k in range(1, n + 1):
            m = lbl == k
            if m.sum() < MIN_AREA * h * w:
                continue
            ys, xs = np.nonzero(m)
            if ys.min() <= 4 or xs.min() <= 4 or ys.max() >= h - 5 or xs.max() >= w - 5:
                continue        # cropped by the frame: not whole
            cands.append(m)
    pieces = [m for m in cands if _composition_ok(lab, m, model, exp)]
    if not pieces:
        why = why or "no whole piece in the piece's colours is in the frame"
    return pieces, why


def frame_check(rgb: np.ndarray, exp, *, role: str = "") -> list[dict]:
    """`<component>:sides` for a frame that is not an anchor; [] when no piece has a count."""
    out = []
    for model in exp.pieces:
        n = expected_sides(model)
        if n is None:
            continue
        try:
            masks, why = segment_whole_pieces(rgb, exp, model)
            readings = [count_sides(m) for m in masks]
            out.append(judge(model.name, readings, n, close_up=role in CLOSE_UP_ROLES,
                             segmented_why=why))
        except Exception as exc:  # noqa: BLE001 - a measurement that broke is UNKNOWN
            from . import fidelity as F

            out.append(F._check(f"{model.name}:sides", F.UNKNOWN,
                                f"{type(exc).__name__}: {str(exc)[:200]}",
                                code=F.FC.UNVERIFIABLE_COUNT))
    return out


def corroborate(check: dict, reading: dict | None) -> dict:
    """Attach a vision judge's side count to a deterministic check, never overriding it.

    `reading` {"answered": bool, "reading": {"sides": n}}. A disagreement with a PASS makes
    it UNKNOWN (a second opinion that disagrees is not a pass); a FAIL stays FAIL."""
    from . import fidelity as F

    if not reading or not reading.get("answered"):
        return check
    seen = (reading.get("reading") or {}).get("sides")
    out = {**check, "vision_sides": seen}
    expected = check.get("expected")
    if check["status"] == F.PASS and isinstance(seen, int) and seen != expected:
        out.update(status=F.UNKNOWN, code=F.FC.UNVERIFIABLE_COUNT,
                   why=check["why"] + f"; the vision judge read {seen} sides")
    return out
