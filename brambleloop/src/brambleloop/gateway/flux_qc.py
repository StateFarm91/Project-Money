"""ENG-VIS-FLUX: the generation-time check, before any QA judge sees a render.

A render that is the wrong size, the wrong shape for its frame, or not a decodable PNG/JPEG is
rejected here, with a named reason, the moment its bytes are on disk. It is never handed to an
identity, product or vision judge (each of which costs money and none of which is the right
instrument for "is this a 2048 px square JPEG"), and nothing is ever upscaled or re-encoded to
pass: a defect is a rejection, not a repair.

Deterministic and offline: Pillow reads the bytes; no model is asked.

Frame roles (`FRAME_ROLES`):

* `listing` -- every listing-gallery frame. PNG or JPEG, opaque, at least 2000 px on the
  shortest side (the W-OWNERIMG listing floor, `image_stages.LISTING_MIN_PX`), and the aspect
  ratio the frame asked for, within 1 %.
* `intermediate` -- a working reference that never ships (the stage-A identity anchor at the
  1k tier). Same format and aspect rules; at least 900 px on the shortest side.

A render with no role (a benchmark trial, a probe) is not checked here: those are not frames.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

LISTING, INTERMEDIATE = "listing", "intermediate"
ACCEPTED_FORMATS = ("PNG", "JPEG")
ASPECT_TOLERANCE = 0.01

# Reason codes. Each is a fact about the bytes, never a judgement about the picture.
CORRUPT_BYTES = "corrupt_bytes"
WRONG_FORMAT = "wrong_format"
BELOW_RESOLUTION = "below_resolution"
WRONG_ASPECT = "wrong_aspect_for_frame_role"
NOT_OPAQUE = "not_opaque"
UNKNOWN_ROLE = "unknown_frame_role"
REASONS = (CORRUPT_BYTES, WRONG_FORMAT, BELOW_RESOLUTION, WRONG_ASPECT, NOT_OPAQUE,
           UNKNOWN_ROLE)


@dataclass(frozen=True)
class FrameRole:
    name: str
    min_short_side_px: int
    require_opaque: bool = True


FRAME_ROLES: dict[str, FrameRole] = {
    LISTING: FrameRole(LISTING, 2000),
    INTERMEDIATE: FrameRole(INTERMEDIATE, 900),
}


def _ratio(size: str) -> tuple[int, int]:
    w, h = (int(x) for x in str(size).lower().split("x"))
    if w <= 0 or h <= 0:
        raise ValueError(size)
    return w, h


def inspect(raw: bytes, *, requested_size: str, frame_role: str) -> dict:
    """{ok, reasons, px, format, opaque, role, requested_size}. Never raises on bad bytes."""
    role = FRAME_ROLES.get(str(frame_role or ""))
    out = {"ok": False, "reasons": [], "px": None, "format": None, "opaque": None,
           "role": frame_role, "requested_size": requested_size,
           "min_short_side_px": role.min_short_side_px if role else None}
    if role is None:
        out["reasons"] = [UNKNOWN_ROLE]
        return out
    try:
        from PIL import Image

        with Image.open(io.BytesIO(bytes(raw or b""))) as im:
            im.verify()                         # structural check of the whole stream
        with Image.open(io.BytesIO(bytes(raw))) as im:
            im.load()                           # every pixel decodes (truncation is caught)
            w, h = im.size
            fmt = str(im.format or "")
            opaque = True
            if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P"
                                                  and "transparency" in im.info):
                opaque = im.convert("RGBA").getchannel("A").getextrema()[0] == 255
    except Exception as exc:  # noqa: BLE001 - undecodable is the finding
        out["reasons"] = [CORRUPT_BYTES]
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return out
    out.update(px=[w, h], format=fmt, opaque=opaque)
    reasons = []
    if fmt not in ACCEPTED_FORMATS:
        reasons.append(WRONG_FORMAT)
    if min(w, h) < role.min_short_side_px:
        reasons.append(BELOW_RESOLUTION)
    try:
        rw, rh = _ratio(requested_size)
        if abs((w / h) / (rw / rh) - 1.0) > ASPECT_TOLERANCE:
            reasons.append(WRONG_ASPECT)
    except (ValueError, ZeroDivisionError):
        reasons.append(WRONG_ASPECT)
    if role.require_opaque and not opaque:
        reasons.append(NOT_OPAQUE)
    out["reasons"] = reasons
    out["ok"] = not reasons
    return out


def explain(verdict: dict) -> str:
    """One line for the receipt and the exception text."""
    if verdict.get("ok"):
        return "passed the generation-time check"
    bits = []
    for r in verdict.get("reasons") or []:
        if r == BELOW_RESOLUTION:
            bits.append(f"{r} ({verdict.get('px')} < {verdict.get('min_short_side_px')} px "
                        f"shortest side)")
        elif r == WRONG_ASPECT:
            bits.append(f"{r} ({verdict.get('px')} for a {verdict.get('requested_size')} "
                        f"{verdict.get('role')} frame)")
        elif r == WRONG_FORMAT:
            bits.append(f"{r} ({verdict.get('format')}; PNG or JPEG only)")
        else:
            bits.append(r)
    return "; ".join(bits)
