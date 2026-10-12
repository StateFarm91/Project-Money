"""GENERATE -> PRODUCT TRUTH -> STRUCTURE/IDENTITY -> PHOTOREALISM -> COMMERCIAL, per image.

The fast loop's judges. Each is an existing, independent gate of the repository, called on the
exact bytes a pipeline version produced -- this module adds no new standard and lowers none:

* **product_truth** -- the frame is bound to the certified CIR (`render_verification.
  authoritative_cir`), by fingerprint; a frame of some other design is FAIL, an unknown design
  is UNKNOWN.
* **structure** -- `render_verification.verify` on the bytes (stitch counts, rings, piece
  count, scale bar, caption, off-palette pixels). The producer's manifest is never evidence.
* **laura_identity** -- `canonical.laura_verdict` on per-dimension identity readings. Applies to
  model-bearing imagery only; "a similar woman" is `not_laura` and blocks.
* **anatomy / photorealism** -- apply to generated/photographic frames; their readings come from
  the vision judges (`visual.photoreal`, gated `image_vision`). For disclosed deterministic
  renders photorealism is not applicable (D-FB-9): the frame says it is not a photograph.
* **composition / mobile_thumbnail** -- `publish.layout_qa.inspect` at listing scale and at the
  170 px grid size.
* **disclosure** -- the manifest carries the contract disclosure (its pixels are checked by the
  verifier's caption check).
* **gallery_contract** -- frame one is the hero (job DESIRE; `publish.eligibility` rule), one job
  per frame, one aspect ratio.
* **blind_benchmark** -- advisory and UNKNOWN until observed benchmark galleries and a blind
  vision review exist (D-FB-9 COMPETITIVE gate); recorded so the gap is visible, never invented.

An image is **accepted** only when every applicable non-advisory gate is PASS. UNKNOWN blocks
exactly like FAIL: unjudged is never passed.

Deterministic bytes make three caches honest: a render is a function of (CIR, view, layout); a
verification and an inspection are functions of (bytes, CIR, view). Latency recorded for a
cached frame is the latency measured when those bytes were first produced.
"""
from __future__ import annotations

import hashlib
import io
import time

from . import pipeline as P

PASS, FAIL, UNKNOWN, NA = "PASS", "FAIL", "UNKNOWN", "N/A"
JUDGE_VERSION = "visual-rnd-fast-judge/1"
# The hero's product-pixel share in the 170 px grid at which the thumbnail-prominence score
# saturates. A presentation preference of the internal judge, overturnable by marketplace CTR.
PROMINENCE_SATURATION = 0.5

_RENDERS: dict = {}
_VERIFIED: dict = {}
_INSPECTED: dict = {}
_AUTH: dict = {}


def _authoritative(cir):
    key = (cir.slug, cir.version)
    if key not in _AUTH:
        from ..render_verification import authoritative_cir
        try:
            _AUTH[key] = authoritative_cir(cir.slug, cir.version)
        except Exception:  # noqa: BLE001 - an unreadable registry is UNKNOWN, not PASS
            _AUTH[key] = None
    return _AUTH[key]


def _grain(png: bytes, sigma: float, seed: str) -> bytes:
    import numpy as np
    from PIL import Image

    arr = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.float32)
    rng = np.random.default_rng(int(seed[:16], 16))
    arr = np.clip(arr + rng.normal(0.0, sigma, arr.shape), 0, 255).astype("uint8")
    return _encode(Image.fromarray(arr), 9)


def _encode(img, level: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=int(level))
    return buf.getvalue()


def produce(cir, params: dict) -> list[dict]:
    """GENERATE: the gallery a pipeline version makes for one product, deterministically.

    Only the deterministic disclosed renderer is executed here. Paid stages (provider, model,
    lighting, camera...) are planned by the loop and never executed in this module.
    """
    from PIL import Image

    from .. import disclosed_render as D

    layout = {}
    if "hero_gap_ratio" in params:
        layout["hero_gap_ratio"] = float(params["hero_gap_ratio"])
    frames = []
    for view in ("hero", "scale", "detail"):
        key = (cir.slug, cir.version, cir.fingerprint, view, tuple(sorted(layout.items())))
        if key not in _RENDERS:
            t0 = time.perf_counter()
            fr = D.render(cir, view, layout=layout or None)
            _RENDERS[key] = (fr, time.perf_counter() - t0)
        fr, render_s = _RENDERS[key]
        png, post_s = fr.png, 0.0
        sigma = float(params.get("post_grain_sigma") or 0.0)
        level = int(params.get("encode_png_level", 9))
        if sigma > 0 or level != 9:
            t0 = time.perf_counter()
            if sigma > 0:
                png = _grain(png, sigma, fr.sha256)
            if level != 9:
                png = _encode(Image.open(io.BytesIO(png)), level)
            post_s = time.perf_counter() - t0
        manifest = dict(fr.manifest)
        manifest["image_sha256"] = hashlib.sha256(png).hexdigest()
        manifest["post_processing"] = {"post_grain_sigma": sigma, "encode_png_level": level}
        frames.append({"view": view, "png": png, "manifest": manifest,
                       "sha256": manifest["image_sha256"], "bytes": len(png),
                       "latency_s": round(render_s + post_s, 4)})
    return frames


def _verify(png: bytes, sha: str, cir, view: str) -> dict:
    key = (sha, cir.fingerprint, view)
    if key not in _VERIFIED:
        from ..render_verification import verify
        try:
            _VERIFIED[key] = verify(png, cir=cir, view=view)
        except Exception as exc:  # noqa: BLE001 - a verifier crash is UNKNOWN, never PASS
            _VERIFIED[key] = {"status": UNKNOWN, "failed": [], "unknown": [str(exc)[:120]]}
    return _VERIFIED[key]


def _inspect(png: bytes, sha: str, position: int) -> dict:
    key = (sha, position)
    if key not in _INSPECTED:
        from PIL import Image

        from ...publish import layout_qa
        _INSPECTED[key] = layout_qa.inspect(Image.open(io.BytesIO(png)),
                                            position=position).to_dict()
    return _INSPECTED[key]


def _gate(status: str, why: str = "", **numbers) -> dict:
    return {"status": status, "why": why, **numbers}


def judge_frame(cir, frame: dict, position: int, product_class: str) -> dict:
    """Every gate on one deterministic frame. Returns gates, accepted, failures, metrics."""
    from .. import render_contract as K

    gates: dict[str, dict] = {}
    auth = _authoritative(cir)
    fp = frame["manifest"].get("cir_fingerprint")
    if auth is None:
        gates["product_truth"] = _gate(UNKNOWN, f"no authoritative CIR for {cir.slug}@"
                                                f"{cir.version}")
    elif auth.fingerprint != fp or cir.fingerprint != fp:
        gates["product_truth"] = _gate(FAIL, "frame is bound to a different design than the "
                                             "certified CIR")
    else:
        gates["product_truth"] = _gate(PASS, "bound to the certified CIR by fingerprint")
    v = _verify(frame["png"], frame["sha256"], auth or cir, frame["view"])
    gates["structure"] = _gate(v.get("status", UNKNOWN),
                               ", ".join(list(v.get("failed") or []) +
                                         list(v.get("unknown") or [])) or "every check passed",
                               failed=list(v.get("failed") or []))
    gates["laura_identity"] = _gate(NA, "product-only frame; no person depicted")
    gates["anatomy"] = _gate(NA, "product-only frame; no person depicted")
    gates["photorealism"] = _gate(NA, "disclosed deterministic render: states it is not a "
                                      "photograph; realism judged only for photo/generated "
                                      "frames (D-FB-9)")
    rep = _inspect(frame["png"], frame["sha256"], position)
    thumb_codes = [p.split(":")[0] for p in rep["problems"]
                   if p.startswith("FRAME_DIES_AT_THUMBNAIL")]
    comp_codes = [p.split(":")[0] for p in rep["problems"] if p.split(":")[0] not in thumb_codes]
    gates["composition"] = _gate(FAIL if comp_codes else PASS, ", ".join(comp_codes),
                                 codes=comp_codes)
    gates["mobile_thumbnail"] = _gate(FAIL if thumb_codes else PASS, ", ".join(thumb_codes),
                                      mobile_ink_share=rep["mobile_ink_share"])
    gates["disclosure"] = _gate(PASS if frame["manifest"].get("disclosure") == K.DISCLOSURE
                                else FAIL, "contract disclosure in manifest; pixels checked by "
                                           "the verifier's caption check")
    gates["gallery_contract"] = _gate(NA, "judged once per gallery (frame order and jobs)")
    gates["blind_benchmark"] = _gate(UNKNOWN, "needs observed benchmark galleries and a blind "
                                              "vision review (data + image_vision gated)")
    return finish(gates, metrics={"mobile_ink_share": rep["mobile_ink_share"],
                                  "ink_share": rep["ink_share"],
                                  "crop_survival": rep["crop_survival"],
                                  "bytes": frame["bytes"]})


def finish(gates: dict, *, metrics: dict | None = None) -> dict:
    """Accepted only when every applicable, non-advisory gate passed; failures named."""
    failures = []
    for name in P.GATES:
        g = gates.get(name) or {"status": UNKNOWN, "why": "gate not run"}
        gates[name] = g
        if name in P.ADVISORY_GATES or g["status"] in (PASS, NA):
            continue
        detail = g.get("failed") or g.get("codes") or []
        failures.append(f"{name.upper()}:{g['status']}"
                        + (f":{','.join(map(str, detail[:3]))}" if detail else ""))
    return {"gates": gates, "accepted": not failures, "failures": failures,
            "metrics": dict(metrics or {}), "judge_version": JUDGE_VERSION}


def gallery_contract(frames: list[dict]) -> dict:
    from .. import disclosed_render as D

    jobs = [D.VIEWS[f["view"]]["job"] for f in frames]
    if not frames or frames[0]["view"] != "hero":
        return _gate(FAIL, "frame one is not the DESIRE hero (publish.eligibility)")
    if len(set(jobs)) != len(jobs):
        return _gate(FAIL, "two frames do the same job")
    return _gate(PASS, "hero first, one job per frame, one aspect")


def score(gallery_accepted: bool, hero_mobile_ink: float | None) -> float:
    """The task score of one gallery: zero unless every gate passed, else hero prominence."""
    if not gallery_accepted or hero_mobile_ink is None:
        return 0.0
    return round(min(1.0, float(hero_mobile_ink) / PROMINENCE_SATURATION), 4)


def judge_identity(scored: dict | None) -> dict:
    """The Laura gate on per-dimension readings (match/drift/unmeasurable)."""
    from .. import canonical

    if not scored:
        return _gate(UNKNOWN, "no identity reading: an unconfirmed likeness is not Laura")
    v = canonical.laura_verdict(scored)
    return _gate(PASS if v["verdict"] == "laura" else
                 (FAIL if v["verdict"] == "not_laura" else UNKNOWN),
                 v["why"] or f"Laura ({canonical.IDENTITY_ID})", verdict=v["verdict"],
                 failed=v["drifted"] or v["unread_locked"])
