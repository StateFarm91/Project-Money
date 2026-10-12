"""Brand Asset Health (Final Master F-527): is the shop Etsy shows wearing the brand?

The criterion: "Maintain logo/icon, banner, color, typography and listing-image consistency
across Etsy. Detect stale, missing, low-resolution or off-brand assets and route fixes to
Brand/Visual."

This module compares the live shop's icon and banner, as read through Etsy's API, with the
owner's canonical brand files (`brand.canonical_assets`, D-FB-17). Every reading is
deterministic:

- **missing**: getShop returns no `icon_url_fullxfull` or `image_url_760x100`.
- **low_resolution**: the live icon is smaller than Etsy's recommended 500 x 500 px for a
  logo (Etsy help 115015663347, "The recommended size for logos is 500 x 500px", read through
  the Help Center API). The API returns the banner only as a 760 x 100 rendition, so the
  banner's upload resolution against Etsy's 1200 x 160 minimum is UNKNOWN and is reported as
  unknown, never as a pass.
- **on-brand / stale / off-brand**: a 64-bit difference hash is compared against the
  canonical renditions (icon: the owner monogram crop and the padded full lockup; banner: the
  canonical banner).
  - Within MATCH_BITS of a canonical rendition is on-brand.
  - Otherwise, a live image whose mean colour sits within PALETTE_DISTANCE of a brand palette
    colour is **stale**: the brand's colours, but not the current artwork.
  - Anything else is **off-brand**.
- **Typography / colour of listing images**: deferred to `brand.bible` (BRAND_PALETTE_DRIFT
  over listings), which is already checked. This module reads only the shop-level assets.

Fixes are routed, not performed. Etsy has no shop-image upload endpoint, so a person uploads
the canonical file. Each problem opens one incident naming the canonical file to upload, and
the incident closes when a fresh reading is on-brand.

Network: the only fetch is the public image at the URL getShop returned, on Etsy's own CDN.
"""
from __future__ import annotations

import io
import urllib.request

ACTION = "brand.asset_health"
INCIDENT_PREFIX = "brand.asset_health:"
ICON_MIN_PX = 500            # Etsy help 115015663347: recommended logo size 500 x 500 px
BANNER_MIN = (1200, 160)     # same article: mini shop banner minimum 1200 x 160 px
MATCH_BITS = 12              # of 64: within this Hamming distance is the same artwork
PALETTE_DISTANCE = 60.0      # RGB distance of the mean colour to the nearest brand colour
USER_AGENT = "BrambleloopStudioResearch/1.0 (+contact via Etsy shop BrambleloopStudio)"

ON_BRAND, STALE, OFF_BRAND, UNKNOWN = "on_brand", "stale", "off_brand", "unknown"


def _fetch(url: str, *, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def dhash(im) -> int:
    """64-bit difference hash of a PIL image (9x8 grey, adjacent-pixel comparisons)."""
    from PIL import Image

    small = im.convert("L").resize((9, 8), Image.LANCZOS)
    px = list(small.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (px[row * 9 + col] > px[row * 9 + col + 1])
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _mean_rgb(im) -> tuple[float, float, float]:
    small = im.convert("RGB").resize((32, 32))
    px = list(small.getdata())
    return tuple(sum(p[i] for p in px) / len(px) for i in range(3))


def _palette_distance(rgb) -> float:
    from .bible import PALETTE

    best = None
    for hexv in PALETTE.values():
        h = hexv.lstrip("#")
        c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        d = sum((a - b) ** 2 for a, b in zip(rgb, c)) ** 0.5
        best = d if best is None else min(best, d)
    return float(best)


def canonical_hashes() -> dict[str, list[int]]:
    """dHashes of the owner's canonical renditions, per surface."""
    from . import canonical_assets as ca

    logo = ca.image(ca.HERO_LOGO)
    fill = ca.paper_colour()
    return {
        "icon": [dhash(ca._pad_square(logo.crop(ca.LOGO_CROP_MONOGRAM), fill)),
                 dhash(ca._pad_square(logo, fill))],
        "banner": [dhash(ca.image(ca.STOREFRONT_BANNER))],
    }


def judge_image(data: bytes, surface: str, canon: list[int]) -> dict:
    """Size, artwork match and colour reading for one live image's bytes."""
    from PIL import Image

    im = Image.open(io.BytesIO(data))
    w, h = im.size
    h_live = dhash(im)
    distance = min(_hamming(h_live, c) for c in canon) if canon else None
    colour_gap = round(_palette_distance(_mean_rgb(im)), 1)
    if distance is not None and distance <= MATCH_BITS:
        brand = ON_BRAND
    elif colour_gap <= PALETTE_DISTANCE:
        brand = STALE
    else:
        brand = OFF_BRAND
    out = {"size": [w, h], "artwork_distance_bits": distance, "colour_gap": colour_gap,
           "brand": brand}
    if surface == "icon":
        out["low_resolution"] = w < ICON_MIN_PX or h < ICON_MIN_PX
        out["resolution_basis"] = f"Etsy recommends {ICON_MIN_PX} x {ICON_MIN_PX} px for a logo"
    else:
        out["low_resolution"] = None
        out["resolution_basis"] = ("UNKNOWN: the API returns a 760 x 100 rendition, so the "
                                   f"upload's size against Etsy's {BANNER_MIN[0]} x "
                                   f"{BANNER_MIN[1]} minimum cannot be read")
    return out


SURFACES = (("icon", "icon_url_fullxfull"), ("banner", "image_url_760x100"))


def assess(shop: dict, *, fetch=None, canon: dict | None = None) -> dict:
    """One reading of the live shop's icon and banner. `shop` is getShop's body."""
    fetch = fetch or _fetch
    canon = canon if canon is not None else canonical_hashes()
    surfaces, problems = {}, []
    for surface, field in SURFACES:
        url = str((shop or {}).get(field) or "").strip()
        if not url:
            surfaces[surface] = {"state": "missing", "field": field}
            problems.append({"surface": surface, "problem": "missing",
                             "why": f"getShop returned no {field}"})
            continue
        try:
            got = judge_image(fetch(url), surface, canon.get(surface) or [])
        except Exception as exc:  # noqa: BLE001 - an unread image is unknown, not healthy
            surfaces[surface] = {"state": UNKNOWN, "url": url,
                                 "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
            continue
        surfaces[surface] = {"state": got["brand"], "url": url, **got}
        if got["brand"] != ON_BRAND:
            problems.append({"surface": surface, "problem": got["brand"],
                             "why": (f"{got['artwork_distance_bits']} of 64 bits from the "
                                     f"canonical artwork; mean colour {got['colour_gap']} from "
                                     f"the nearest brand colour")})
        if got["low_resolution"]:
            problems.append({"surface": surface, "problem": "low_resolution",
                             "why": f"{got['size'][0]} x {got['size'][1]} px, under "
                                    f"{ICON_MIN_PX} x {ICON_MIN_PX}"})
    return {"surfaces": surfaces, "problems": problems,
            "healthy": not problems and all(v["state"] == ON_BRAND
                                            for v in surfaces.values()),
            "route": ("Brand/Visual: upload the canonical file "
                      "(brand/owner_source, D-FB-17) in Shop Manager > Settings > Info & "
                      "appearance; Etsy has no shop-image upload endpoint")}


def record(db, reading: dict) -> dict:
    """Store the reading and open/close one incident per surface problem."""
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident, utcnow

    want = {f"{INCIDENT_PREFIX}{p['surface']}:{p['problem']}": p for p in reading["problems"]}
    opened, resolved = [], []
    with db.session() as s:
        s.add(AuditLog(actor="orchestrator", action=ACTION, detail=reading))
        open_rows = {i.signature: i for i in s.scalars(select(Incident).where(
            Incident.resolved == False,  # noqa: E712
            Incident.signature.like(f"{INCIDENT_PREFIX}%")))}
        for sig, inc in open_rows.items():
            surface = sig[len(INCIDENT_PREFIX):].split(":")[0]
            state = (reading["surfaces"].get(surface) or {}).get("state")
            if sig not in want and state not in (UNKNOWN, None):
                detail = dict(inc.detail or {})
                detail.update(resolution="a fresh reading no longer shows this problem",
                              resolved_at=utcnow().isoformat())
                inc.detail, inc.resolved = detail, True
                resolved.append(sig)
        for sig, p in want.items():
            if sig in open_rows:
                continue
            s.add(Incident(severity="P2", signature=sig, halts_publication=False,
                           summary=(f"Shop {p['surface']} is {p['problem'].replace('_', ' ')}: "
                                    f"{p['why']}. {reading['route']}"),
                           detail={**p, "route": reading["route"], "department": "brand"}))
            opened.append(sig)
    return {"opened": opened, "resolved": resolved}
