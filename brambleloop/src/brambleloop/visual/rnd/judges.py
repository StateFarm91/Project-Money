"""Desirability and brand-consistency judges for the internal FAST loop -- all PROXY.

Every judge here is a *proxy*: a deterministic pixel measurement standing in for what buyers
will do. They exist so the R&D loop can rank gate-passing candidates in seconds instead of
waiting weeks for marketplace data. They are labelled PROXY on every reading, carry a trust
factor that the slow loop (`visual.rnd.commercial`) lowers whenever marketplace evidence
overturns a decision they made, and they never touch a hard gate: a judge reading is an
input to `objective.evaluate`, which only ranks candidates that already passed every gate.

* `thumbnail_desirability` -- at the 170 px search-grid size: subject prominence, local
  contrast, colourfulness, warmth and centring. A thumbnail that reads as a warm, vivid,
  prominent object is a better *bet*; whether it sells is the slow loop's question.
* `brand_consistency` -- share of the frame's pixels near the brand palette plus warmth. The
  brand TARGET is the owner's canonical files (D-FB-17, `brand.canonical_assets`: the hero
  logo and the storefront banner, verified by sha256 on every read); the palette is the one
  sampled from them (`brand.identity_system` / `owner_identity.CONCEPT_SAMPLES`, re-sampled
  from the files by its tests), or the provisional palette sampled from the same files when
  that interface is absent. If the canonical files fail verification the reading is UNKNOWN:
  a brand score with no verified target is not a brand score.
* `blind_benchmark` -- a slot, UNKNOWN until observed benchmark galleries and a blind vision
  review exist. Never invented.
* `photographic_quality` -- N/A for disclosed renders (they say they are not photographs);
  for photographic/generated frames it is the vision judge's reading when supplied, else
  UNKNOWN.

UNKNOWN is `None` with a reason, never 0.
"""
from __future__ import annotations

import io

PROXY = "PROXY"
PROXY_LABEL = "PROXY -- internal estimate, not marketplace evidence"
THUMB_PX = 170

# Provisional owner-concept palette: dominant colours sampled (median-cut) from the owner's
# concept images (owner_logo_concept.png sha256 28f301b2..., owner_banner_concept.png sha256
# 048a1991...). Replaced by lane A's production palette when `brand.identity_system` exports
# `OWNER_CONCEPT_PALETTE` (or its DIRECTION_ID names the owner concept).
PROVISIONAL_OWNER_PALETTE: dict[str, str] = {
    "cream": "#F4EFE8", "linen": "#E5DBD3", "stone": "#C7BFB4", "taupe": "#A59C8F",
    "warm_taupe": "#827869", "moss": "#656556", "forest": "#494A3C",
    "warm_natural": "#BA9781", "walnut": "#7E5F47", "umber": "#4B3423",
}
PALETTE_RADIUS = 52.0   # RGB euclidean distance counted as "on palette"


def brand_target() -> dict:
    """The canonical brand target (D-FB-17): the owner's two files, re-hashed. The banner is
    also the registered art target for any banner reproduction work."""
    try:
        from ...brand import canonical_assets as CA

        v = CA.verify()
        return {"decision": CA.DECISION_ID, "verified": v["ok"], "problems": v["problems"],
                "assets": {r: {"file": a.file, "sha256": a.sha256, "size": list(a.size)}
                           for r, a in CA.ASSETS.items()},
                "banner_art_target": CA.ASSETS[CA.STOREFRONT_BANNER].sha256}
    except Exception as exc:  # noqa: BLE001 - no target -> UNKNOWN brand readings
        return {"verified": False, "problems": [f"{type(exc).__name__}: {str(exc)[:120]}"],
                "assets": {}}


def brand_palette() -> tuple[dict[str, str], str]:
    """(palette, provenance). The palette sampled from the canonical owner files (lane A's
    export of it when present, else the provisional samples of the same files)."""
    try:
        from ...brand import identity_system as I
        pal = getattr(I, "OWNER_CONCEPT_PALETTE", None)
        if not pal and "owner" in str(getattr(I, "DIRECTION_ID", "")).lower():
            pal = getattr(I, "PALETTE", None)
        if pal:
            return dict(pal), ("brand.identity_system palette sampled from the canonical owner "
                               "files (D-FB-17)")
    except Exception:  # noqa: BLE001 - absent interface -> provisional palette
        pass
    return dict(PROVISIONAL_OWNER_PALETTE), ("provisional: sampled from the owner concept "
                                             "images; pending lane A's production palette")


def _rgb(png: bytes, px: int):
    import numpy as np
    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    im = im.resize((px, max(1, round(px * h / w))))
    return np.asarray(im, dtype=np.float32)


def _reading(name: str, version: str, value, why: str = "", **metrics) -> dict:
    return {"judge": name, "judge_version": version, "basis": PROXY if value is not None
            else "unknown", "label": PROXY_LABEL,
            "value": None if value is None else round(float(value), 4),
            "reading": "PROXY" if value is not None else "UNKNOWN", "why": why,
            "metrics": metrics}


def thumbnail_desirability(png: bytes) -> dict:
    import numpy as np

    name, ver = "thumbnail_desirability", "thumb-desirability-proxy/1"
    try:
        a = _rgb(png, THUMB_PX)
    except Exception as exc:  # noqa: BLE001
        return _reading(name, ver, None, f"unreadable image: {type(exc).__name__}")
    flat = a.reshape(-1, 3)
    q = (flat // 16).astype(int)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    bg_key = keys[counts.argmax()]
    bg = flat[(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]) == bg_key].mean(axis=0)
    mask = np.linalg.norm(a - bg, axis=2) > 40.0
    prominence = float(mask.mean())
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    subj = a[mask] if mask.any() else flat
    contrast = float(np.std(lum[mask]) / 64.0) if mask.sum() > 10 else 0.0
    rg = subj[:, 0] - subj[:, 1]
    yb = 0.5 * (subj[:, 0] + subj[:, 1]) - subj[:, 2]
    colourful = float((np.sqrt(rg.std() ** 2 + yb.std() ** 2)
                       + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)) / 80.0)
    warmth = float(np.clip((subj[:, 0].mean() - subj[:, 2].mean()) / 60.0 + 0.5, 0, 1))
    if mask.any():
        ys, xs = np.nonzero(mask)
        h, w = mask.shape
        off = np.hypot(ys.mean() / h - 0.5, xs.mean() / w - 0.5) / 0.5
        centred = float(np.clip(1 - off, 0, 1))
    else:
        centred = 0.0
    prom_s = min(1.0, prominence / 0.5)
    value = (0.35 * prom_s + 0.2 * min(1.0, contrast) + 0.2 * min(1.0, colourful)
             + 0.15 * warmth + 0.1 * centred)
    return _reading(name, ver, value, "thumbnail proxy at the 170 px grid size",
                    prominence=round(prominence, 4), contrast=round(contrast, 4),
                    colourfulness=round(colourful, 4), warmth=round(warmth, 4),
                    centred=round(centred, 4))


def brand_consistency(png: bytes) -> dict:
    import numpy as np

    name, ver = "brand_consistency", "brand-palette-proxy/2"
    target = brand_target()
    if not target["verified"]:
        return _reading(name, ver, None, "canonical brand target unverified (D-FB-17): "
                        + "; ".join(target["problems"])[:200])
    pal, prov = brand_palette()
    try:
        a = _rgb(png, 128).reshape(-1, 3)
    except Exception as exc:  # noqa: BLE001
        return _reading(name, ver, None, f"unreadable image: {type(exc).__name__}")
    cols = np.array([[int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
                     for h in pal.values()], dtype=np.float32)
    d = np.linalg.norm(a[:, None, :] - cols[None, :, :], axis=2).min(axis=1)
    on = float((d <= PALETTE_RADIUS).mean())
    warmth = float(np.clip((a[:, 0].mean() - a[:, 2].mean()) / 40.0 + 0.5, 0, 1))
    value = 0.8 * on + 0.2 * warmth
    return _reading(name, ver, value, f"palette share vs the canonical owner assets' palette "
                    f"({prov})", on_palette_share=round(on, 4), warmth=round(warmth, 4),
                    palette_provenance=prov, brand_target=target["assets"],
                    brand_target_decision=target.get("decision"))


def blind_benchmark(png: bytes | None = None) -> dict:
    return _reading("blind_benchmark", "blind-benchmark-slot/1", None,
                    "slot: needs observed benchmark galleries and a blind vision review "
                    "(data + image_vision gated); never invented")


def photographic_quality(*, medium: str, vision_reading: float | None = None) -> dict:
    name, ver = "photographic_quality", "photo-quality/1"
    if str(medium).upper() == "DIGITAL_TWIN_RENDER":
        r = _reading(name, ver, None, "N/A: disclosed render, states it is not a photograph "
                                      "(D-FB-9)")
        r["reading"] = "N/A"
        return r
    if vision_reading is None:
        return _reading(name, ver, None, "no vision-judge reading for this frame")
    r = _reading(name, ver, vision_reading, "vision judge reading (visual.photoreal)")
    r["basis"] = "measured (vision judge)"
    return r


JUDGES = ("thumbnail_desirability", "brand_consistency", "blind_benchmark",
          "photographic_quality")


def judge_all(png: bytes, *, medium: str = "DIGITAL_TWIN_RENDER",
              vision_reading: float | None = None) -> dict:
    """Component readings for `objective.evaluate` (desirability, brand, photo, benchmark)."""
    return {"desirability": thumbnail_desirability(png),
            "brand_consistency": brand_consistency(png),
            "photographic_quality": photographic_quality(medium=medium,
                                                         vision_reading=vision_reading),
            "blind_benchmark": blind_benchmark(png)}


def describe() -> dict:
    pal, prov = brand_palette()
    return {"judges": list(JUDGES), "basis": PROXY, "label": PROXY_LABEL,
            "thumb_px": THUMB_PX, "palette": pal, "palette_provenance": prov,
            "brand_target": brand_target(),
            "note": "internal fast-loop proxies; marketplace evidence (slow loop) overrides "
                    "them and lowers their trust when it disagrees"}
