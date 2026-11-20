"""Bounded material enhancement (F-855) -- W4-C07.

"AI may enhance fibre/fuzz/micro-material only when macro geometry/stitch boundaries remain
protected and revalidated."

`check(before, after, silhouette, boundaries, revalidate=...)` decides whether an enhanced
image may replace the one Product Truth produced. Arrays are greyscale (H x W); `silhouette`
and `boundaries` are boolean masks from the deterministic reference (the object's outline and
its stitch boundaries -- edges of every stitch, eye and row).

* **Macro geometry** -- the enhanced image's silhouette (pixels darker/lighter than the
  background by the reference's own threshold) must overlap the reference silhouette with IoU of
  at least `MIN_SILHOUETTE_IOU`.
* **Protected boundaries** -- inside the stitch-boundary band (the boundaries dilated by
  `BAND_PX`), at most `MAX_CHANGED_FRACTION` of pixels may change by more than `MAX_DELTA`
  levels, and the mean change stays under `MAX_DELTA`. Fibre and fuzz live between the
  boundaries; the boundaries are the product.
* **Revalidation** -- the existing structural validator (`revalidate(after)`, e.g. the stitch
  identity instrument) must still return PASS. A missing validator is UNKNOWN, and UNKNOWN is
  refused, never allowed.

ALLOWED only when all three hold. Nothing here enhances anything; it judges a proposed result.
"""
from __future__ import annotations

import numpy as np

MIN_SILHOUETTE_IOU = 0.99
BAND_PX = 1
MAX_DELTA = 12.0
MAX_CHANGED_FRACTION = 0.02


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def _silhouette(img: np.ndarray, ref_mask: np.ndarray) -> np.ndarray:
    inside, outside = img[ref_mask], img[~ref_mask]
    thr = (float(np.median(inside)) + float(np.median(outside))) / 2.0
    return img > thr if np.median(inside) > np.median(outside) else img < thr


def check(before: np.ndarray, after: np.ndarray, silhouette: np.ndarray,
          boundaries: np.ndarray, *, revalidate=None) -> dict:
    b, a = before.astype(float), after.astype(float)
    if b.shape != a.shape or b.shape != silhouette.shape or b.shape != boundaries.shape:
        return {"state": "REFUSED", "reasons": ["the images and masks differ in shape"]}
    reasons = []
    sil = _silhouette(a, silhouette)
    inter = np.logical_and(sil, silhouette).sum()
    union = np.logical_or(sil, silhouette).sum()
    iou = float(inter / union) if union else 0.0
    if iou < MIN_SILHOUETTE_IOU:
        reasons.append(f"silhouette IoU {iou:.3f} < {MIN_SILHOUETTE_IOU}")
    band = _dilate(boundaries.astype(bool), BAND_PX)
    delta = np.abs(a - b)[band]
    changed = float((delta > MAX_DELTA).mean()) if delta.size else 0.0
    mean = float(delta.mean()) if delta.size else 0.0
    if changed > MAX_CHANGED_FRACTION or mean > MAX_DELTA:
        reasons.append(f"stitch boundaries moved: {changed:.1%} of the protected band changed "
                       f"by more than {MAX_DELTA:g} levels (mean {mean:.1f})")
    if revalidate is None:
        verdict = "UNKNOWN"
        reasons.append("no structural validator was run on the enhanced image (UNKNOWN)")
    else:
        verdict = revalidate(a)
        if verdict != "PASS":
            reasons.append(f"structural revalidation returned {verdict}")
    free = ~band & silhouette.astype(bool)
    return {"state": "REFUSED" if reasons else "ALLOWED", "reasons": reasons,
            "silhouette_iou": round(iou, 4), "band_changed_fraction": round(changed, 4),
            "band_mean_delta": round(mean, 2), "revalidation": verdict,
            "enhanced_area_mean_delta": round(float(np.abs(a - b)[free].mean()), 2)
            if free.any() else 0.0}
