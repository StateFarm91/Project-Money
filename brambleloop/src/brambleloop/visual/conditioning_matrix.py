"""F-679 Conditioning Research: a systematic conditioning comparison matrix (W4-C08).

"compare RGB, depth, normals, edges, segmentation/material masks, multi-view and hybrids to
determine the minimum deterministic fidelity needed for faithful photoreal generation."

The earlier conditioning work was research waves (E1-E5, Bench1/2, V2 R&D) with no common
record. This module is the matrix those waves lacked:

* `ARMS` -- every single modality and the hybrids worth testing, each a frozen tuple of
  modalities, ordered by how much deterministic fidelity it carries (`fidelity_cost`).
* `derive_passes(rgb_png, yarn_colours)` -- the passes that can be derived deterministically
  from the Brambleloop 3D render's RGB bytes, locally and at CA$0: `edges` (Sobel magnitude),
  `segmentation` (piece vs background) and `material_masks` (one mask per yarn colour of the
  CIR). `multi_view` is the disclosed set's own ANGLE frame (`launch_imagery`). `depth` and
  `normals` need a geometry pass the renderer does not yet emit: they are reported
  NOT_PRODUCED, never approximated from RGB, and every arm needing them is UNAVAILABLE.
* `record_trial(db, ...)` -- one generated candidate under one arm, with its Product Truth
  fidelity verdict (the existing `visual.fidelity` verifier's PASS/FAIL), cost and output
  hash, persisted as an `operating_readings` row (kind `visual.conditioning_trial`).
* `matrix(db)` / `minimum_fidelity(db)` -- per arm: trials, pass rate, spend; the minimum is
  the arm with the FEWEST modalities (then the lowest cost) whose pass rate clears
  `FIDELITY_FLOOR` on at least `MIN_TRIALS` trials. Before that evidence exists the answer is
  UNDETERMINED, never the incumbent by default.
* `plan(db)` -- the arms still short of evidence, each a proposal for the existing paid door
  (`experiments.controlled`: frozen definition, owner authorization and step-up). Nothing
  here calls a provider or reserves spend.
"""
from __future__ import annotations

import hashlib
import io

KIND = "visual.conditioning_trial"
MODALITIES = ("rgb", "depth", "normals", "edges", "segmentation", "material_masks",
              "multi_view")
DERIVABLE = frozenset({"rgb", "edges", "segmentation", "material_masks", "multi_view"})
NOT_PRODUCED = frozenset({"depth", "normals"})
ARMS: tuple[tuple[str, ...], ...] = (
    ("rgb",), ("edges",), ("segmentation",), ("material_masks",), ("depth",), ("normals",),
    ("multi_view",),
    ("rgb", "edges"), ("rgb", "segmentation"), ("rgb", "material_masks"),
    ("rgb", "depth"), ("depth", "normals", "edges"),
    ("rgb", "material_masks", "edges"), ("rgb", "multi_view"),
    ("rgb", "depth", "normals", "material_masks", "multi_view"),
)
FIDELITY_FLOOR = 0.9
MIN_TRIALS = 6
EDGE_THRESHOLD = 48.0


def arm_id(arm) -> str:
    return "+".join(arm)


def fidelity_cost(arm) -> tuple[int, int]:
    """More modalities = more deterministic fidelity to produce; 3D passes cost more."""
    return (len(arm), sum(2 if m in NOT_PRODUCED else 1 for m in arm))


def available(arm) -> bool:
    return not (set(arm) & NOT_PRODUCED)


def _png(arr) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def derive_passes(rgb_png: bytes, yarn_colours: list[str] | None = None,
                  *, background: tuple[int, int, int] | None = None) -> dict:
    """Deterministic passes from one RGB render. Same bytes in, same bytes out."""
    import numpy as np
    from PIL import Image

    img = np.asarray(Image.open(io.BytesIO(rgb_png)).convert("RGB")).astype("float32")
    grey = img.mean(axis=2)
    gx = np.zeros_like(grey)
    gy = np.zeros_like(grey)
    gx[1:-1, 1:-1] = (grey[1:-1, 2:] - grey[1:-1, :-2]) * 2 + (grey[:-2, 2:] - grey[:-2, :-2]) \
        + (grey[2:, 2:] - grey[2:, :-2])
    gy[1:-1, 1:-1] = (grey[2:, 1:-1] - grey[:-2, 1:-1]) * 2 + (grey[2:, :-2] - grey[:-2, :-2]) \
        + (grey[2:, 2:] - grey[:-2, 2:])
    edges = ((np.hypot(gx, gy) > EDGE_THRESHOLD) * 255).astype("uint8")
    bg = np.array(background if background is not None else img[0, 0], dtype="float32")
    fg = (np.abs(img - bg).sum(axis=2) > 30)
    seg = (fg * 255).astype("uint8")
    masks = {}
    for hexc in yarn_colours or []:
        h = hexc.lstrip("#")
        c = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype="float32")
        masks[hexc.upper()] = _png(((np.abs(img - c).sum(axis=2) < 60) & fg).astype("uint8")
                                   * 255)
    out = {"rgb": rgb_png, "edges": _png(edges), "segmentation": _png(seg),
           "material_masks": masks}
    return {"passes": out,
            "sha256": {k: (hashlib.sha256(v).hexdigest() if isinstance(v, bytes) else
                           {c: hashlib.sha256(b).hexdigest() for c, b in v.items()})
                       for k, v in out.items()},
            "foreground_share": round(float(fg.mean()), 4),
            "not_produced": sorted(NOT_PRODUCED),
            "multi_view": "the disclosed set's ANGLE frame (visual.launch_imagery)"}


def record_trial(db, *, arm, product: str, fidelity: str, cost_cad: float | None,
                 output_sha256: str, provider: str = "UNKNOWN", reason: str = "") -> dict:
    from ..core.models import OperatingReading

    arm = tuple(arm)
    if arm not in ARMS:
        raise ValueError(f"{arm_id(arm)} is not an arm of the matrix")
    if not available(arm):
        raise ValueError(f"{arm_id(arm)} needs {sorted(set(arm) & NOT_PRODUCED)}, which no "
                         f"renderer produces yet; a trial under it cannot be honest")
    if fidelity not in ("PASS", "FAIL"):
        raise ValueError("a trial is recorded with the fidelity verifier's PASS or FAIL")
    payload = {"arm": arm_id(arm), "product": product, "fidelity": fidelity,
               "cost_cad": cost_cad, "output_sha256": output_sha256, "provider": provider,
               "reason": reason[:300]}
    with db.session() as s:
        s.add(OperatingReading(kind=KIND, period_key=output_sha256[:20], payload=payload))
    return payload


def matrix(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import OperatingReading

    with db.session() as s:
        trials = [dict(r.payload or {}) for r in s.scalars(
            select(OperatingReading).where(OperatingReading.kind == KIND))]
    rows = []
    for arm in ARMS:
        mine = [t for t in trials if t.get("arm") == arm_id(arm)]
        costs = [t["cost_cad"] for t in mine if isinstance(t.get("cost_cad"), (int, float))]
        rows.append({"arm": arm_id(arm), "modalities": list(arm),
                     "available": available(arm), "fidelity_cost": fidelity_cost(arm),
                     "trials": len(mine),
                     "pass_rate": (round(sum(t["fidelity"] == "PASS" for t in mine) /
                                         len(mine), 4) if mine else None),
                     "spent_cad": round(sum(costs), 4),
                     "products": sorted({t["product"] for t in mine})})
    return rows


def minimum_fidelity(db) -> dict:
    rows = matrix(db)
    good = [r for r in rows if r["available"] and r["trials"] >= MIN_TRIALS
            and r["pass_rate"] is not None and r["pass_rate"] >= FIDELITY_FLOOR]
    if not good:
        return {"state": "UNDETERMINED", "arm": None,
                "why": (f"no arm has {MIN_TRIALS}+ trials at >= {FIDELITY_FLOOR:.0%} Product "
                        f"Truth fidelity yet"), "matrix": rows}
    best = sorted(good, key=lambda r: (r["fidelity_cost"], r["spent_cad"] / r["trials"]))[0]
    return {"state": "DETERMINED", "arm": best["arm"], "modalities": best["modalities"],
            "pass_rate": best["pass_rate"], "trials": best["trials"],
            "rule": "fewest modalities, then lowest cost, clearing the floor", "matrix": rows}


def plan(db) -> list[dict]:
    """Arms still short of evidence, as proposals for the controlled-experiment door."""
    out = []
    for r in matrix(db):
        if not r["available"]:
            out.append({"arm": r["arm"], "state": "UNAVAILABLE",
                        "why": "needs a depth/normals pass the renderer does not emit"})
        elif r["trials"] < MIN_TRIALS:
            out.append({"arm": r["arm"], "state": "NEEDS_TRIALS",
                        "missing": MIN_TRIALS - r["trials"],
                        "door": "experiments.controlled (owner authorization + step-up)",
                        "spend": "never from here"})
    return out
