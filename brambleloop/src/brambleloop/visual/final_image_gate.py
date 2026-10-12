"""Final Image Gate (F-677): a beautiful image that changes the certified product is rejected.

Wave-3 lane K12. The audit's finding was that Product Truth on generated and model-bearing
images was a vision-model judgement -- a proxy. This gate makes the PASS side deterministic
and leaves the proxy only one power: to fail an image.

**How an image can PASS.** Only by deterministic proof that its product region is the
certified product, pixel for pixel:

1. a *source* frame from the qualified disclosed renderer whose bytes pass the independent
   pixel verifier against the certified CIR (`product_authority.structural_floor` --
   stitch counts, piece count, dimensions, palette/colour placement, caption, scale), and
2. the judged image (bound by sha256) keeps every product pixel of that verified render
   unchanged -- the product region is every non-background pixel of the render
   (`render_contract.BACKGROUND`), checked by `compose.verify`.

Then neckline, sleeves, silhouette, stitch family, colour placement, dimensions and
construction are all *held*, because the pixels that carry each of them are identical to
pixels the verifier passed. A presentation stage may change the room, the light outside the
product and everything around it; it may not touch the product.

**How an image FAILs.** A verified source that fails, a product pixel that changed, bytes not
bound to the judged image, or any vision reading that says an attribute changed (a proxy may
reject, never approve).

**Everything else is UNKNOWN**, which blocks: a pure generation with no verified source has
no deterministic Product Truth evidence, however good it looks. That is the current honest
state of model photography (F-852: generative product redraw is prohibited).
"""
from __future__ import annotations

import hashlib
from io import BytesIO

GATE_VERSION = "final-image-gate/1"
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# F-677's list, verbatim, plus "other Product Truth" carried by the verifier's checks.
ATTRIBUTES: tuple[str, ...] = ("neckline", "sleeves", "silhouette", "stitch_family",
                               "colour_placement", "dimensions", "construction")

# What a vision reading may say about an attribute that counts as "it changed".
_CHANGED = frozenset({"changed", "mismatch", "drift", "fail", "different"})


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gate(status: str, why: str, attributes: dict | None = None, **extra) -> dict:
    return {"status": status, "why": why, "gate_version": GATE_VERSION,
            "attributes": attributes or {a: status if status == FAIL else UNKNOWN
                                         for a in ATTRIBUTES},
            "proxy_can_only_fail": True, **extra}


def product_cutout(render_png: bytes) -> bytes:
    """The verified render's product region as RGBA: alpha 255 on every non-background pixel."""
    from PIL import Image

    from . import render_contract as K

    img = Image.open(BytesIO(render_png)).convert("RGB")
    bg = tuple(K.BACKGROUND)
    out = Image.new("RGBA", img.size)
    out.putdata([(r, g, b, 0 if (r, g, b) == bg else 255) for r, g, b in img.getdata()])
    buf = BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _source_bytes(frame: dict) -> bytes | None:
    from ..core.artifacts import ArtifactStore

    sha = ((frame.get("image") or {}).get("sha256") if isinstance(frame.get("image"), dict)
           else None)
    if not sha:
        return None
    try:
        data = ArtifactStore(frame.get("artifact_dir") or None).get(sha)
    except (OSError, ValueError, RuntimeError):
        return None
    return data if _sha(data) == sha else None


def evaluate(evidence: dict | None) -> dict:
    """PASS only on deterministic evidence; a vision reading can only FAIL the image."""
    ev = dict(evidence or {})
    vision = ev.get("vision") or {}
    changed = sorted(a for a, v in (vision.items() if isinstance(vision, dict) else ())
                     if str(v).strip().lower() in _CHANGED)
    if changed:
        return _gate(FAIL, f"a reading says the image changed {changed}; a beautiful image "
                           f"of a different product is rejected",
                     {a: (FAIL if a in changed else UNKNOWN) for a in ATTRIBUTES},
                     failed=changed)

    image = ev.get("image_png")
    want = str(ev.get("image_sha256") or "").lower()
    source_frame = ev.get("source_frame")
    if not isinstance(source_frame, dict):
        return _gate(UNKNOWN, "no verified source render: a generated or photographed image "
                              "has no deterministic Product Truth evidence, and a vision "
                              "reading cannot pass it")
    if not isinstance(image, (bytes, bytearray)) or not want or _sha(bytes(image)) != want:
        return _gate(FAIL if image and want else UNKNOWN,
                     "the image bytes are missing or not bound to the judged image's sha256")

    from .product_authority import structural_floor

    floor = structural_floor(source_frame)
    if floor.get("status") != PASS:
        return _gate(FAIL if floor.get("status") == FAIL else UNKNOWN,
                     f"source render is not verified: {floor.get('why', '')}",
                     source_structure=floor.get("status"))
    source = _source_bytes(source_frame)
    if source is None:
        return _gate(UNKNOWN, "verified source bytes unavailable",
                     source_structure=floor.get("status"))

    from .compose import verify

    try:
        pres = verify(product_cutout(source), bytes(image))
    except Exception as exc:  # noqa: BLE001 - an unreadable image is not a preserved one
        return _gate(UNKNOWN, f"preservation unreadable ({type(exc).__name__})")
    if pres.get("status") == FAIL:
        return _gate(FAIL, f"the presentation changed the certified product: "
                           f"{pres.get('changed_pixels', 'canvas')} product pixel(s) differ "
                           f"from the verified render ({pres.get('why', '')})".strip(),
                     {a: FAIL for a in ATTRIBUTES}, preservation=pres,
                     source_structure=PASS)
    if pres.get("status") != PASS:
        return _gate(UNKNOWN, f"preservation {pres.get('status')}: {pres.get('why', '')}",
                     preservation=pres, source_structure=PASS)
    return _gate(PASS, (f"every one of {pres['protected_pixels']} product pixels is identical "
                        f"to a render the independent verifier passed against the certified "
                        f"CIR; {', '.join(ATTRIBUTES)} are held"),
                 {a: PASS for a in ATTRIBUTES}, preservation=pres, source_structure=PASS,
                 verification=floor.get("verification"))
