"""Apparent stitch scale in imagery is Product Truth (F-753).

A photoreal image whose stitches are materially bigger or smaller than the gauge makes them is
a picture of a different fabric -- a chunky-yarn look sold as a DK pattern, a fine-gauge
texture on a bulky blanket -- however good it looks. This module measures the stitch pitch an
image actually shows and holds it to the pitch the gauge implies at the image's stated scale.

* `read(image_bytes, px_per_cm=...)` measures the dominant along-row period of a fabric
  region (luminance column profile, FFT power, fundamental preferred over a harmonic),
  searched within a window around the expected pitch so a harmonic far away is not picked.
* `expected_pitch_px(cir, px_per_cm, component=)` is the gauge's stitch width at that scale,
  from the component's own gauge when it declares one (F-754) and the main gauge otherwise.
  A star-stitch fabric repeats every star, two stitches of the row below
  (`cir.stitches.ANATOMY`), so its visible pitch is two stitch widths.
* `verdict(...)` -> PASS within `TOLERANCE`, FAIL outside it, UNKNOWN when either side is
  missing. `gates.asset_truth.check_asset` refuses a generated image that depicts stitches
  with no reading (UNKNOWN is never a pass) or with a FAIL.
"""
from __future__ import annotations

import io

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
TOLERANCE = 0.20          # +-20 % of the gauge's pitch: a whole yarn weight is ~25-40 %
SEARCH = 2.5              # the period is searched in [expected / 2.5, expected * 2.5]


def _gauge_for(cir, component: str | None):
    if component:
        comp = next((c for c in cir.components if c.name == component), None)
        if comp is not None and comp.gauge is not None:
            return comp.gauge
    return cir.gauge


def _repeat_stitches(cir, component: str | None) -> int:
    from ..cir import stitches as S

    comps = [c for c in cir.components if component in (None, c.name)]
    used: set[str] = set()

    def walk(nodes):
        for n in nodes or ():
            inner = getattr(n, "ops", None)
            if inner is not None:
                walk(inner)
            elif getattr(n, "stitch", None):
                used.add(n.stitch)

    for c in comps:
        for r in c.rows:
            walk(r.ops)
    # The repeating star (worked into the previous eye, closing into one eye) sets the pitch;
    # the beginning and end stars are edge stitches.
    stars = [S.anatomy(code) for code in used if S.anatomy(code) is not None
             and S.anatomy(code).placement == "star" and "prev_eye" in S.anatomy(code).anchors
             and S.anatomy(code).makes == ("eye",)]
    return stars[0].new_stitches if stars else 1


def expected_pitch_px(cir, px_per_cm: float, *, component: str | None = None) -> float | None:
    g = _gauge_for(cir, component)
    if g is None or not px_per_cm or px_per_cm <= 0:
        return None
    return px_per_cm * (10.0 / g.stitches_per_10cm) * _repeat_stitches(cir, component)


HARMONIC_SHARE = 0.25     # a period twice as long with this share of the power is the fundamental


def _fundamental_period(signal, lo: float, hi: float) -> float | None:
    """Dominant period in [lo, hi] px by FFT power, preferring the fundamental to a harmonic.

    A drawn or photographed stitch row is not a sine: its spectrum has power at the stitch
    pitch and at half of it. The strongest bin can be the harmonic, so a period whose double
    also carries real power within the window is promoted to that double.
    """
    import numpy as np

    s = np.asarray(signal, dtype=float)
    s = s - s.mean()
    n = len(s)
    if n < 8:
        return None
    power = np.abs(np.fft.rfft(s * np.hanning(n))) ** 2
    freqs = np.fft.rfftfreq(n)
    periods = np.where(freqs > 0, 1.0 / np.maximum(freqs, 1e-12), np.inf)
    sel = (periods >= lo) & (periods <= hi)
    if not sel.any():
        return None
    k = int(np.argmax(np.where(sel, power, -1.0)))
    best = float(periods[k])
    while best * 2 <= hi:
        near = sel & (np.abs(periods - best * 2) <= best * 2 * 0.08)
        if not near.any():
            break
        j = int(np.argmax(np.where(near, power, -1.0)))
        if power[j] < HARMONIC_SHARE * power[k]:
            break
        best, k = float(periods[j]), j
    return best


def read(image_bytes: bytes, *, px_per_cm: float, expected_px: float | None = None,
         box: tuple[int, int, int, int] | None = None, component: str | None = None) -> dict:
    """The along-row stitch pitch an image shows, in px. None when no period is found."""
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("L")
    if box:
        img = img.crop(box)
    gray = np.asarray(img, dtype=float)
    profile = gray.mean(axis=0)
    w = len(profile)
    lo, hi = 3.0, w / 3.0
    if expected_px:
        lo, hi = max(lo, expected_px / SEARCH), min(hi, expected_px * SEARCH)
    period = _fundamental_period(profile, lo, hi) if hi > lo else None
    return {"measured_pitch_px": None if period is None else round(period, 2),
            "px_per_cm": px_per_cm, "component": component, "box": list(box) if box else None,
            "method": "luminance column profile, FFT fundamental period"}


def verdict(cir, reading: dict | None) -> dict:
    """PASS / FAIL / UNKNOWN for one reading against the gauge (F-753)."""
    if not reading or not reading.get("px_per_cm"):
        return {"verdict": UNKNOWN, "why": "no stitch-scale reading with a stated image scale"}
    expected = expected_pitch_px(cir, float(reading["px_per_cm"]),
                                 component=reading.get("component"))
    measured = reading.get("measured_pitch_px")
    if expected is None or measured is None:
        return {"verdict": UNKNOWN, "expected_px": expected, "measured_px": measured,
                "why": "no gauge" if expected is None else "no stitch period found"}
    ratio = float(measured) / expected
    return {"verdict": PASS if abs(ratio - 1.0) <= TOLERANCE else FAIL,
            "expected_px": round(expected, 2), "measured_px": measured,
            "ratio": round(ratio, 3), "tolerance": TOLERANCE}
