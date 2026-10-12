"""E1 structural reference: the basket from Product Truth alone, with no mechanics.

What this IS: a deterministic picture of the certified product built only from the twin's
Revolution profile (per-round radius and axial height), the CIR's colour placement by round,
the gauge (stitch pitch and row pitch in millimetres) and the stitch family. Every dimension
in it is a computation over certified counts and gauge.

What this IS NOT: a physical simulation, a yarn path, or a photograph. The stitch cue is a
PROCEDURAL mark at the correct pitch, not a mechanics-derived cell -- it says "single crochet,
this dense, in these rows" and nothing about how the yarn actually travels. That is the
hypothesis under test: that this much structure is what a reference-conditioned image model
needs, and that yarn-level geometry is not.

Labels: dimensions MEASURED from the twin (which is itself UNCALIBRATED -- twin.calibrated is
False, so every centimetre is a gauge prediction); colour bands MEASURED from the CIR; stitch
cue PROCEDURAL.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from brambleloop.cir import compiler, twin as T          # noqa: E402
from brambleloop.products import launch0 as l0           # noqa: E402

COLOURS = {"cream": (238, 228, 208), "wine": (112, 30, 42)}


def product_truth(key: str) -> dict:
    cir = l0.BUILDERS[key]()
    res = compiler.compile_cir(cir)
    comp = cir.components[0]
    tw = T.build_twin(cir, res, component=comp.name)
    g = cir.gauge
    rings = [(r.radius_cm, r.axial_cm) for r in tw.geometry.rings]
    # Colour by round. The CIR row carries the yarn letter on its cells; the chart renderer
    # already reads it, so read the same source rather than guessing from op attributes.
    colour_of_round: dict[int, str] = {}
    for row in comp.rows:
        names = set()
        for op in row.ops:
            for attr in ("color", "colour", "yarn"):
                v = getattr(op, attr, None)
                if v:
                    names.add(str(v))
        if not names:
            names = {getattr(row, "color", None) or getattr(row, "colour", None) or ""}
        colour_of_round[row.index] = sorted(n for n in names if n)[0] if any(names) else ""
    return {
        "slug": cir.slug, "title": cir.title, "stitch_family": g.stitch_type,
        "gauge_st_per_10cm": g.stitches_per_10cm, "gauge_rows_per_10cm": g.rows_per_10cm,
        "hook_mm": g.hook_mm, "rings": rings, "colour_of_round": colour_of_round,
        "row_widths": dict(tw.row_widths),
        "max_diameter_cm": tw.geometry.max_diameter_cm,
        "height_cm": tw.geometry.axial_height_cm, "shape": tw.geometry.shape,
        "twin_calibrated": tw.calibrated,
        "yarn_metres_by_color": tw.yarn_metres_by_color,
    }


def _fallback_colours(truth: dict) -> dict[int, str]:
    """If the op attributes carried nothing, use the CIR's own colour changes as the chart
    renderer prints them. For basket_large that is wine at rounds 44-45 and 56-57. This
    fallback is DECLARED in structure.json so nobody mistakes it for a measurement."""
    if any(truth["colour_of_round"].values()):
        return truth["colour_of_round"]
    out = {}
    for r in range(1, len(truth["rings"]) + 1):
        out[r] = "wine" if r in (44, 45, 56, 57) else "cream"
    truth["colour_source"] = "FALLBACK: chart-observed bands, not read from op attributes"
    return out


def render(truth: dict, out_png: Path, *, size: int = 1024, elev_deg: float = 28.0,
           azim_deg: float = 30.0) -> dict:
    """Lathe the profile, flat-shade it, paint rounds by colour, mark sc rows at gauge pitch.

    A right-handed camera at `elev_deg` above the table and `azim_deg` round from the front.
    Orthographic projection: the point is proportion, and perspective would put a foreshortening
    into the silhouette ratio that the twin does not predict.
    """
    rings = truth["rings"]
    colours = _fallback_colours(truth)
    st_pitch_cm = 10.0 / truth["gauge_st_per_10cm"]
    n_theta = 256
    theta = np.linspace(0, 2 * math.pi, n_theta, endpoint=False)
    el, az = math.radians(elev_deg), math.radians(azim_deg)
    # View direction (from object to camera) and screen basis.
    view = np.array([math.cos(el) * math.sin(az), -math.cos(el) * math.cos(az), math.sin(el)])
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(up, view); right /= np.linalg.norm(right)
    sup = np.cross(view, right)
    light = np.array([-0.4, -0.6, 0.7]); light /= np.linalg.norm(light)

    faces = []  # (depth, poly2d, shade, colour)
    def surf(r, z):
        return np.stack([r * np.cos(theta), r * np.sin(theta), np.full(n_theta, z)], 1)
    prev = None
    for i, (r, z) in enumerate(rings):
        cur = surf(max(r, 0.05), z)
        if prev is not None:
            col = COLOURS[colours.get(i + 1, "cream")]
            for k in range(n_theta):
                k2 = (k + 1) % n_theta
                quad = np.array([prev[k], prev[k2], cur[k2], cur[k]])
                n = np.cross(quad[1] - quad[0], quad[3] - quad[0])
                nn = np.linalg.norm(n)
                if nn < 1e-9:
                    continue
                n /= nn
                if n @ view < 0:
                    n = -n
                shade = 0.35 + 0.65 * max(0.0, float(n @ light))
                depth = float(quad.mean(0) @ view)
                faces.append((depth, quad, shade, col, i + 1))
        prev = cur
    # Base disc fill (round 1 centre)
    faces.sort(key=lambda f: f[0])

    # Project to screen.
    allpts = np.concatenate([f[1] for f in faces])
    sx = allpts @ right; sy = allpts @ sup
    pad = 0.08
    span = max(sx.max() - sx.min(), sy.max() - sy.min()) * (1 + 2 * pad)
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2
    scale = size / span
    def P(p):
        return ((p @ right - cx) * scale + size / 2, size / 2 - (p @ sup - cy) * scale)

    img = Image.new("RGB", (size, size), (236, 236, 232))
    d = ImageDraw.Draw(img)
    for depth, quad, shade, col, rnd in faces:
        c = tuple(int(v * shade) for v in col)
        d.polygon([P(p) for p in quad], fill=c)

    # Procedural sc cue: one short dark tick per stitch along each visible round, at the
    # gauge's stitch pitch, plus a faint line between rounds at the row pitch. This is a
    # density/family cue, not yarn.
    tick = tuple(int(v * 0.55) for v in COLOURS["cream"])
    for i, (r, z) in enumerate(rings):
        if i == 0:
            continue
        n_st = truth["row_widths"].get(i + 1, int(2 * math.pi * r / st_pitch_cm))
        n_st = max(6, int(n_st))
        for s in range(n_st):
            t = 2 * math.pi * s / n_st
            p = np.array([r * math.cos(t), r * math.sin(t), z])
            nrm = np.array([math.cos(t), math.sin(t), 0.0]) if z > 0 else np.array([0, 0, 1.0])
            if nrm @ view <= 0.05:
                continue
            x, y = P(p)
            zprev = rings[i - 1][1]
            h = max(1.5, (z - zprev) * scale * 0.45) if z > zprev else max(1.5, st_pitch_cm * scale * 0.25)
            d.line([(x, y - h), (x, y + h)], fill=tick, width=1)

    img.save(out_png)
    meta = {
        "reference_png": str(out_png), "camera": {"elev_deg": elev_deg, "azim_deg": azim_deg,
                                                   "projection": "orthographic"},
        "silhouette_ratio_diameter_over_height": truth["max_diameter_cm"] / truth["height_cm"],
        "colour_bands_by_round": sorted({v: [k for k, c in colours.items() if c == v]
                                         for v in set(colours.values())}.items()),
        "stitch_cue": "PROCEDURAL tick per stitch at gauge pitch; not mechanics-derived",
    }
    return meta


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "basket_large"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "out"
    out.mkdir(parents=True, exist_ok=True)
    truth = product_truth(key)
    meta = render(truth, out / f"{key}_structural.png")
    truth.pop("row_widths")
    (out / f"{key}_structure.json").write_text(json.dumps({**truth, **meta}, indent=1, default=str))
    print(json.dumps({k: truth[k] for k in ("slug", "stitch_family", "max_diameter_cm", "height_cm",
                                            "twin_calibrated")} | {"ratio": meta["silhouette_ratio_diameter_over_height"],
                                            "colour_source": truth.get("colour_source", "op attributes")}))
