"""The certified campaign gallery's images, prepared for the premium pattern PDF
(D-OWNER-PDF-STANDARD, D-OWNER-SALE-PIPELINE; ENG-SALE-PIPELINE).

"The PDF's photos are the listing's certified gallery images, reused." One gallery spend
serves both the listing and both PDF editions. This module decides which certified frame
fills which slot of `research/benchmarks/PDF_STRUCTURE_STANDARD.md` and makes the bytes the
PDF embeds. It owns no layout (ENG-PDF-PREMIUM owns `publish.pdf`); it is the contract the
layout's embedding hook (`build_pattern_pdf(campaign_photos=...)`) and the deterministic
checker (`publish.pdf_standard`) both read, so they cannot disagree about which picture is
which.

**Renditions.** A frame is embedded as a deterministic JPEG rendition: RGB, the long edge
at most `MAX_PX`, quality `JPEG_QUALITY`, no metadata, no progressive or optimise passes. The
same certified bytes always give the same rendition bytes, and reportlab passes a JPEG
through unchanged (DCTDecode), so the checker proves from the BUILT PDF that an embedded
image is exactly the rendition of a certified frame: it hashes the decoded stream and
compares it with `rendition(frame_bytes)`. A picture that is not a certified frame cannot
count towards a slot.

**Slots** (the standard's photo parts):

* `cover_hero`: the full-bleed cover photo (role `hero`);
* `overview_lifestyle`: the overview page's lifestyle photo (role `lifestyle`);
* `progress`: the construction page's progress photo (role `construction`, else the close
  `detail` view of the stitches, else `materials`);
* `gallery`: the gallery page, 5 to 6 photos (every campaign frame except the deterministic
  "what's included" preview, which pictures the files, not the piece).

No model, network or spend. Pure functions.
"""
from __future__ import annotations

import hashlib
import io

SLOTS = ("cover_hero", "overview_lifestyle", "progress", "gallery")
MAX_PX = 1600
JPEG_QUALITY = 85
GALLERY_MIN, GALLERY_MAX = 5, 6
# Roles that fill each single-photo slot, in preference order.
SLOT_ROLES: dict[str, tuple[str, ...]] = {
    "cover_hero": ("hero",),
    "overview_lifestyle": ("lifestyle",),
    "progress": ("construction", "detail", "materials"),
}
# Roles never placed on the gallery page: the contents preview is a picture of the files.
NOT_GALLERY = frozenset({"whats_included"})
# The caption every campaign image carries in the PDF. Honest by construction: the
# certified frames are generated images of the finished design, never photographs.
CAPTION = ("AI-generated image of the finished design, checked against this pattern; "
           "not a photograph of a worked sample.")
DISCLOSURE = ("About the pictures: the lifestyle images in this edition are AI-generated "
              "images of the finished design, each checked against this pattern's certified "
              "data before it was used; none is a photograph of a worked sample. The "
              "schematic and the construction diagrams are drawn from the pattern's own "
              "data at the stated gauge.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rendition(data: bytes) -> bytes:
    """The deterministic JPEG the PDF embeds for one certified frame's bytes."""
    from PIL import Image

    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, MAX_PX / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                         Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=False, progressive=False,
             subsampling=2)
    return out.getvalue()


def plan(frames: list[dict]) -> dict:
    """Assign certified frames to the standard's photo slots.

    `frames`: [{"sha256", "role", "position", "data": bytes}] in certificate order (each
    frame's `data` is the certified image's bytes, whose sha256 must be `sha256`).
    Returns {"slots": {slot: [photo]}, "problems": [...]}, where a photo is
    {"frame_sha256", "rendition_sha256", "role", "position", "jpeg", "caption"}. A frame whose
    bytes do not hash to its certified sha256 is refused, never placed."""
    problems: list[str] = []
    photos = []
    for f in sorted(frames, key=lambda f: int(f.get("position") or 0)):
        data = f.get("data")
        if not isinstance(data, (bytes, bytearray)) or sha256(bytes(data)) != f.get("sha256"):
            problems.append(f"frame {f.get('position')} ({f.get('role')}): bytes do not match "
                            f"the certified sha256")
            continue
        jpeg = rendition(bytes(data))
        photos.append({"frame_sha256": f["sha256"], "rendition_sha256": sha256(jpeg),
                       "role": str(f.get("role") or ""), "position": int(f.get("position") or 0),
                       "jpeg": jpeg, "caption": CAPTION})
    by_role: dict[str, dict] = {}
    for p in photos:
        by_role.setdefault(p["role"], p)
    slots: dict[str, list[dict]] = {s: [] for s in SLOTS}
    for slot, roles in SLOT_ROLES.items():
        pick = next((by_role[r] for r in roles if r in by_role), None)
        if pick is None:
            problems.append(f"no certified frame for the {slot} slot (roles {list(roles)})")
        else:
            slots[slot] = [pick]
    gallery = [p for p in photos if p["role"] not in NOT_GALLERY][:GALLERY_MAX]
    if len(gallery) < GALLERY_MIN:
        problems.append(f"gallery page needs {GALLERY_MIN}-{GALLERY_MAX} certified images; "
                        f"{len(gallery)} available")
    slots["gallery"] = gallery
    return {"slots": slots, "problems": problems}


def expected(slots: dict) -> dict:
    """What the checker must find, without the bytes: slot -> [rendition_sha256], plus the
    rendition -> frame map. Stored on the PDF certificate."""
    return {"slots": {s: [p["rendition_sha256"] for p in slots.get(s) or []] for s in SLOTS},
            "renditions": {p["rendition_sha256"]: {"frame_sha256": p["frame_sha256"],
                                                   "role": p["role"]}
                           for s in SLOTS for p in slots.get(s) or []}}
