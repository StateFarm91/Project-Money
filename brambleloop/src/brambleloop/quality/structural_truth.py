"""3D structural truth acceptance (F-675) -- W4-C07.

"Deterministic 3D preserves silhouette, dimensions, construction, stitch structure, shaping,
colour placement and believable macro drape; it need not itself be the final photograph unless
evidence requires it."

`expected(cir)` derives, from the CIR alone (compiler and twin -- Product Truth), what any
deterministic 3D model of the product must preserve. `assess(cir, model)` compares a 3D model's
own read-back against it, property by property. The model summary is what the 3D builder
measures on its geometry:

* `components` and `construction` per component;
* `rows`: {component: [stitch count per row, in order]} -- stitch structure, and the
  row-to-row deltas are the shaping;
* `colours`: {component: [colour per row]} -- colour placement at row resolution;
* `dimensions_cm`: {component: [width, height]} -- against the twin (`DIMENSION_TOLERANCE`);
* `silhouette_iou`: the model's outline against the twin-derived outline;
* `drape`: the drape solver's own locks (equilibrium reached, energy descended, no structural
  drift -- `visual.milestone_d`). Absent locks are UNKNOWN.

STRUCTURALLY_TRUE only when every property passes. A drape that was not measured is UNKNOWN and
keeps the verdict open (never PASS by omission). The model is never the photograph: this
accepts the reference a photograph is later checked against.
"""
from __future__ import annotations

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
PROPERTIES = ("silhouette", "dimensions", "construction", "stitch_structure", "shaping",
              "colour_placement", "macro_drape")
DIMENSION_TOLERANCE = 0.02
MIN_SILHOUETTE_IOU = 0.98
DRAPE_LOCKS = ("equilibrium_fixed_point", "energy_descends", "no_structural_drift")


def expected(cir) -> dict:
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin

    res = compile_cir(cir)
    if not res.ok:
        raise ValueError("a CIR that does not compile has no structural truth to preserve")
    names = [c.name for c in cir.components]
    rows = {n: res.counts(n) for n in names}
    colours = {n: [r.color for r in res.rows if r.component == n] for n in names}
    dims = {}
    for n in names:
        try:
            t = build_twin(cir, res, component=n)
            dims[n] = [t.width_cm, t.height_cm]
        except Exception:  # noqa: BLE001 - a component the twin cannot size is UNKNOWN
            dims[n] = [None, None]
    return {"components": names,
            "construction": {c.name: str(c.construction) for c in cir.components},
            "rows": rows, "colours": colours, "dimensions_cm": dims}


def _shape(counts):
    return [b - a for a, b in zip(counts, counts[1:])]


def assess(cir, model: dict) -> dict:
    exp = expected(cir)
    out: dict[str, dict] = {}
    iou = model.get("silhouette_iou")
    out["silhouette"] = ({"status": UNKNOWN, "why": "no outline comparison"} if iou is None
                         else {"status": PASS if iou >= MIN_SILHOUETTE_IOU else FAIL,
                               "iou": iou})
    bad_dims, unk_dims = [], []
    for n, (w, h) in exp["dimensions_cm"].items():
        got = (model.get("dimensions_cm") or {}).get(n)
        if w is None or h is None or not got:
            unk_dims.append(n)
            continue
        if abs(got[0] - w) / w > DIMENSION_TOLERANCE or abs(got[1] - h) / h > DIMENSION_TOLERANCE:
            bad_dims.append({"component": n, "twin": [w, h], "model": got})
    out["dimensions"] = {"status": FAIL if bad_dims else UNKNOWN if unk_dims else PASS,
                         "off": bad_dims, "unsized": unk_dims}
    cons = model.get("construction") or {}
    wrong = sorted(n for n in exp["components"] if cons.get(n) != exp["construction"][n])
    out["construction"] = {"status": FAIL if wrong or model.get("components") !=
                           exp["components"] else PASS, "mismatched": wrong}
    rows = model.get("rows") or {}
    count_off = sorted(n for n in exp["components"] if rows.get(n) != exp["rows"][n])
    out["stitch_structure"] = {"status": FAIL if count_off else PASS, "components": count_off}
    shape_off = sorted(n for n in exp["components"]
                       if _shape(rows.get(n) or []) != _shape(exp["rows"][n]))
    out["shaping"] = {"status": FAIL if shape_off else PASS, "components": shape_off}
    cols = model.get("colours") or {}
    colour_off = sorted(n for n in exp["components"] if cols.get(n) != exp["colours"][n])
    out["colour_placement"] = {"status": FAIL if colour_off else PASS, "components": colour_off}
    locks = model.get("drape") or {}
    if not locks:
        out["macro_drape"] = {"status": UNKNOWN, "why": "the drape locks were not measured"}
    else:
        failed = [k for k in DRAPE_LOCKS if locks.get(k) != PASS]
        out["macro_drape"] = {"status": PASS if not failed else
                              FAIL if any(locks.get(k) == FAIL for k in DRAPE_LOCKS)
                              else UNKNOWN, "locks": {k: locks.get(k) for k in DRAPE_LOCKS}}
    fails = [p for p in PROPERTIES if out[p]["status"] == FAIL]
    unknown = [p for p in PROPERTIES if out[p]["status"] == UNKNOWN]
    return {"state": "NOT_TRUE" if fails else "UNKNOWN" if unknown else "STRUCTURALLY_TRUE",
            "failed": fails, "unknown": unknown, "properties": out,
            "basis": "cir.compiler + cir.twin (Product Truth); the model is the reference, not "
                     "the photograph"}
