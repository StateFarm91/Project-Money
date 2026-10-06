"""brambleloop.brand.canonical_assets -- the owner's two canonical brand files, and their guard.

Owner decision D-FB-17 (2026-10-06, supersedes D-FB-16 items 1-2): "Stop redesigning or
recreating these two owner-supplied assets."

* ``hero_logo``         -- brambleloop_owner_logo_canonical.png, the canonical hero brand
                           artwork, used EXACTLY as supplied (never redrawn, recoloured,
                           simplified on large-format uses or recomposed);
* ``storefront_banner`` -- brambleloop_owner_banner_canonical.png, the canonical storefront
                           banner / art target. Used as the exact file only if it passes every
                           applicable publication gate (`store_foundation.owner_banner`); when
                           a gate stops it, it stays the target and any correction goes back
                           to the owner.

Both live byte-for-byte in ``owner_source/`` next to this module (SHA256SUMS there). Nothing
here writes to that directory.

Hierarchy (D-FB-17 item 3): the owner rasters are the identity. Lane A3's vector system
(`owner_identity`, `identity_system`, `masters/`) is a SUPPORTING production system --
palette, type guidance, clear space, mono/reversed, small-size engineering, SVG where a
vector is genuinely needed. The A3 micro-mark is a small-size utility derivative, permitted
only where the exact artwork is *measured* illegible (`icon_report`), and never supersedes it.

Protection (D-FB-17 item 4): autonomous Brand / Learn / Visual improvement may not replace
either canonical asset because an internal score prefers another design. Replacing one needs
a new owner decision id recorded in DECISION_LOG, listed in `AUTHORISED_BRAND_CHANGES`, and
naming the exact replacement bytes in `DECISIONS` -- the same pattern as Laura's
`visual.canonical.AUTHORISED_IDENTITY_CHANGES`. A score, a judge reading, a proxy or a
marketplace number is not a decision and is never read by the guard.
"""
from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, dataclass
from pathlib import Path

DECISION_ID = "D-FB-17"

# Owner decision ids that each authorise exactly the brand assets they name (role -> sha256).
# D-FB-17 adopted the two files below; it authorises nothing else. A future replacement needs
# a NEW id here AND in DECISIONS, naming the replacement's bytes.
AUTHORISED_BRAND_CHANGES: tuple[str, ...] = (DECISION_ID,)

OWNER_SOURCE_DIR = Path(__file__).resolve().parent / "owner_source"
SUMS_FILE = "SHA256SUMS"

HERO_LOGO = "hero_logo"
STOREFRONT_BANNER = "storefront_banner"
ROLES = (HERO_LOGO, STOREFRONT_BANNER)


@dataclass(frozen=True)
class CanonicalAsset:
    role: str
    file: str
    sha256: str
    size: tuple[int, int]
    decision: str
    what: str
    use: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["size"] = list(self.size)
        d["path"] = str(OWNER_SOURCE_DIR / self.file)
        return d


ASSETS: dict[str, CanonicalAsset] = {
    HERO_LOGO: CanonicalAsset(
        HERO_LOGO, "brambleloop_owner_logo_canonical.png",
        "28f301b28766acea7b0f632ceefcb1c66e271a6fba8da0c84a65c94647d35998", (1536, 1024),
        DECISION_ID, "canonical hero brand artwork (logo)",
        "exactly as supplied: hero lockup, large-format uses, About header, PDF covers"),
    STOREFRONT_BANNER: CanonicalAsset(
        STOREFRONT_BANNER, "brambleloop_owner_banner_canonical.png",
        "048a199133f7589cc243cb876a7ee5b0f68b5d6530929a922c79de9eda64eb98", (1983, 793),
        DECISION_ID, "canonical storefront banner / art target",
        "the exact file where every applicable publication gate passes; otherwise the target "
        "that any owner-reviewed correction must keep"),
}

# What each authorising decision adopted, by role and bytes.
DECISIONS: dict[str, dict[str, str]] = {
    DECISION_ID: {r: a.sha256 for r, a in ASSETS.items()},
}

# Crop boxes inside the canonical logo (x0, y0, x1, y1), found by lane A2 from the raster's
# ink bands (`brand.comparison`): the monogram (B + sprig + yarn + ball) and the whole lockup.
# A crop changes no pixel; it selects part of the supplied artwork.
LOGO_CROP_MONOGRAM = (470, 45, 1060, 574)
LOGO_CROP_LOCKUP = (190, 45, 1346, 960)

# The display sizes the repo models for the Etsy shop icon (storefront_gate.ICON_SIZES) plus
# the intermediate sizes reported to the owner. Etsy publishes the upload size (500 x 500,
# integrations.etsy_constraints) but not the display sizes: 40/70 are repo-modelled.
ICON_REPORT_SIZES = (40, 48, 70, 96, 160, 500)


class CanonicalAssetError(RuntimeError):
    """A canonical owner file is missing or its bytes are not what the owner supplied."""


class BrandChangeRefused(ValueError):
    """An attempt to make another asset the hero logo or storefront banner without an owner
    decision that names it."""


# ---- integrity --------------------------------------------------------------------------------

def path(role: str, base: Path | None = None) -> Path:
    return Path(base or OWNER_SOURCE_DIR) / ASSETS[role].file


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _sums(base: Path) -> dict[str, str]:
    f = base / SUMS_FILE
    out: dict[str, str] = {}
    if f.is_file():
        for line in f.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                out[parts[1].lstrip("*")] = parts[0].lower()
    return out


def verify(base: Path | None = None) -> dict:
    """Re-hash both owner files. Fail closed: missing, altered, resized or unlisted -> not ok."""
    base = Path(base or OWNER_SOURCE_DIR)
    problems: list[str] = []
    rows = []
    sums = _sums(base)
    if not sums:
        problems.append(f"{SUMS_FILE} missing or empty in {base}")
    for role, a in ASSETS.items():
        p = base / a.file
        row = {"role": role, "file": a.file, "expected_sha256": a.sha256, "sha256": None,
               "size": None, "ok": False}
        if not p.is_file():
            problems.append(f"{role}: {a.file} is missing")
            rows.append(row)
            continue
        got = _sha(p)
        row["sha256"] = got
        if got != a.sha256:
            problems.append(f"{role}: {a.file} sha256 {got[:12]} is not the owner's "
                            f"{a.sha256[:12]} (D-FB-17: the files are immutable)")
        try:
            from PIL import Image

            with Image.open(p) as im:
                row["size"] = list(im.size)
                if tuple(im.size) != a.size:
                    problems.append(f"{role}: {im.size} px, expected {a.size}")
        except Exception as exc:  # noqa: BLE001 - an unreadable file is not the owner's file
            problems.append(f"{role}: unreadable ({type(exc).__name__})")
        if sums and sums.get(a.file) != a.sha256:
            problems.append(f"{role}: {SUMS_FILE} does not list {a.file} at {a.sha256[:12]}")
        row["ok"] = not [x for x in problems if x.startswith(role + ":")]
        rows.append(row)
    return {"ok": not problems, "problems": problems, "assets": rows, "decision": DECISION_ID,
            "dir": str(base)}


def require_verified(base: Path | None = None) -> dict:
    v = verify(base)
    if not v["ok"]:
        raise CanonicalAssetError("; ".join(v["problems"]))
    return v


def verified_path(role: str, base: Path | None = None) -> Path:
    """The owner file for `role`, after re-hashing it (raises CanonicalAssetError otherwise)."""
    p = path(role, base)
    if not p.is_file() or _sha(p) != ASSETS[role].sha256:
        raise CanonicalAssetError(f"{role}: {p} is missing or not the owner's bytes")
    return p


def verified_bytes(role: str, base: Path | None = None) -> bytes:
    data = path(role, base).read_bytes() if path(role, base).is_file() else b""
    if hashlib.sha256(data).hexdigest() != ASSETS[role].sha256:
        raise CanonicalAssetError(f"{role}: bytes are missing or not the owner's")
    return data


def image(role: str, base: Path | None = None):
    """The verified owner raster as a PIL RGB image (read-only use)."""
    from PIL import Image

    return Image.open(io.BytesIO(verified_bytes(role, base))).convert("RGB")


def display_bytes(role: str, max_w: int, fmt: str = "JPEG", quality: int = 86,
                  crop: tuple[int, int, int, int] | None = None) -> bytes:
    """A smaller copy of the exact artwork for on-screen previews: optional crop (selects
    pixels, changes none) then a LANCZOS resample to `max_w`. Never redraws or recolours."""
    from PIL import Image

    im = image(role)
    if crop:
        im = im.crop(crop)
    w, h = im.size
    if w > max_w:
        im = im.resize((max_w, max(1, round(h * max_w / w))), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt.upper() == "PNG":
        im.save(buf, "PNG", optimize=True)
    else:
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


# ---- protection -------------------------------------------------------------------------------

def current(role: str) -> dict:
    if role not in ASSETS:
        raise BrandChangeRefused(f"unknown brand role {role!r}: {list(ROLES)}")
    return ASSETS[role].to_dict()


def require_brand_change_authorised(role: str, candidate_sha256: str,
                                    approval: dict | None = None, *,
                                    action: str = "replace") -> dict:
    """Refuse to make `candidate_sha256` the canonical `role` without an owner decision.

    The candidate being the canonical bytes is not a change (returns change=False). Anything
    else needs ``approval['owner_decision_id']`` listed in `AUTHORISED_BRAND_CHANGES` AND
    naming exactly these bytes for this role in `DECISIONS`. Every other key of `approval`
    (scores, judges, proxies, marketplace numbers, who asked) is ignored: preference is not
    authority.
    """
    if role not in ASSETS:
        raise BrandChangeRefused(f"unknown brand role {role!r}: {list(ROLES)}")
    sha = str(candidate_sha256 or "").strip().lower()
    canon = ASSETS[role]
    if sha == canon.sha256:
        return {"role": role, "change": False, "sha256": sha, "decision": canon.decision}
    decision = str((approval or {}).get("owner_decision_id") or "").strip()
    named = DECISIONS.get(decision, {}).get(role)
    if decision and decision in AUTHORISED_BRAND_CHANGES and named and named == sha:
        return {"role": role, "change": True, "sha256": sha, "decision": decision}
    why = (f"{decision} names {named[:12] if named else 'nothing'} for {role}, not "
           f"{sha[:12] or 'these bytes'}" if decision in DECISIONS else
           f"got {decision or 'no owner decision'}")
    raise BrandChangeRefused(
        f"{action} refused: the {canon.what} is the owner's {canon.file} "
        f"({canon.sha256[:12]}, {canon.decision}). An internal score, judge or proxy "
        f"preferring another design does not authorise replacing it; that needs a new owner "
        f"decision recorded in DECISION_LOG, listed in canonical_assets.AUTHORISED_BRAND_"
        f"CHANGES and naming the replacement bytes in DECISIONS ({why}). A correction "
        f"candidate goes to the owner as OWNER_REVIEW_REQUIRED")


def is_authorised(role: str, candidate_sha256: str, approval: dict | None = None) -> bool:
    try:
        require_brand_change_authorised(role, candidate_sha256, approval)
        return True
    except BrandChangeRefused:
        return False


def select(role: str, challengers: list[dict] | None = None) -> dict:
    """The asset that holds `role` after a challenger round: always the canonical file unless
    a challenger carries an owner decision that names its exact bytes.

    Each challenger: {"id", "sha256", optional "score"/"value", optional "approval"}.
    Higher scores change nothing; refused challengers are returned as proposals the owner may
    review (status OWNER_REVIEW_REQUIRED), never adopted."""
    canon = current(role)
    held, refused, authorised = canon, [], None
    for c in challengers or []:
        sha = str(c.get("sha256") or "").lower()
        if sha == canon["sha256"]:
            continue
        try:
            r = require_brand_change_authorised(role, sha, c.get("approval"),
                                                action=f"challenger {c.get('id')!r}")
        except BrandChangeRefused as exc:
            refused.append({"id": c.get("id"), "sha256": sha,
                            "score": c.get("score", c.get("value")),
                            "status": "OWNER_REVIEW_REQUIRED", "why": str(exc)})
            continue
        if r["change"] and authorised is None:
            authorised = {**c, "decision": r["decision"]}
    if authorised is not None:
        held = {"role": role, "sha256": authorised["sha256"], "id": authorised.get("id"),
                "decision": authorised["decision"]}
    return {"role": role, "held": held, "replaced": authorised is not None,
            "refused": refused,
            "rule": f"{DECISION_ID}: only an owner decision naming the bytes changes {role}"}


# ---- hierarchy --------------------------------------------------------------------------------

HIERARCHY: tuple[dict, ...] = (
    {"use": "hero_lockup", "asset": HERO_LOGO, "kind": "owner raster, exact",
     "where": "banner centre, About header, pattern PDF cover, any large-format use",
     "label": "Canonical owner artwork (D-FB-17)"},
    {"use": "storefront_banner", "asset": STOREFRONT_BANNER, "kind": "owner raster, exact",
     "where": "Etsy big banner, if every applicable publication gate passes "
              "(store_foundation.owner_banner)",
     "label": "Canonical owner banner (D-FB-17)"},
    {"use": "shop_icon", "asset": "measured", "kind": "owner monogram crop where measured "
     "legible at every display size; otherwise the A3 micro-mark (small-size utility "
     "derivative)", "where": "Etsy shop icon (one 500 px upload, shown small)",
     "label": "see icon_report()"},
    {"use": "mono_reversed", "asset": "a3_vector", "kind": "A3 vector, supporting production "
     "system", "where": "one-ink print, stamps, embossing, cream-on-forest reversals",
     "label": "Supporting vector (A3), not the hero"},
    {"use": "small_or_svg", "asset": "a3_vector", "kind": "A3 vector, supporting production "
     "system", "where": "favicon, avatar, email footer, phone header 28-40 px, any place that "
     "needs SVG", "label": "Supporting vector (A3), not the hero"},
)
HIERARCHY_BY_USE = {h["use"]: h for h in HIERARCHY}


def _pad_square(im, fill):
    from PIL import Image

    w, h = im.size
    s = max(w, h)
    out = Image.new("RGB", (s, s), fill)
    out.paste(im, ((s - w) // 2, (s - h) // 2))
    return out


def paper_colour() -> tuple[int, int, int]:
    """The logo's paper colour: per-channel median of its top and bottom 20 rows."""
    import numpy as np

    a = np.asarray(image(HERO_LOGO))
    px = np.concatenate([a[:20].reshape(-1, 3), a[-20:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(px, axis=0))


def icon_report(sizes: tuple[int, ...] = ICON_REPORT_SIZES) -> dict:
    """Measure the exact owner artwork as a square shop icon at each size, with the same
    procedure the storefront gate uses (`storefront_gate.icon_legibility`).

    Two exact-artwork candidates (no pixel redrawn): the monogram crop, and the whole lockup
    centred on its own paper colour (padding adds ground, changes no artwork pixel)."""
    from PIL import Image

    from ..store_foundation.storefront_gate import icon_legibility
    import numpy as np

    logo = image(HERO_LOGO)
    fill = paper_colour()
    views = {"owner_monogram_crop": _pad_square(logo.crop(LOGO_CROP_MONOGRAM), fill),
             "owner_full_lockup_padded": _pad_square(logo, fill)}
    out = {}
    for name, im in views.items():
        out[name] = {}
        for px in sizes:
            small = np.asarray(im.resize((px, px), Image.LANCZOS))
            out[name][px] = icon_legibility(small, px)
    return {"measurements": out, "procedure": "storefront_gate.icon_legibility (contrast >= "
            "3:1, coverage 8-70%, a surviving stroke >= 2 px)", "paper": list(fill),
            "crop_monogram": list(LOGO_CROP_MONOGRAM)}


def shop_icon_choice(display_sizes: tuple[int, ...] = (40, 70)) -> dict:
    """Which artwork the Etsy shop icon uses, by measurement. Etsy takes one upload and shows
    it at every display size, so the exact artwork is used only if it is legible at all of
    them; otherwise the A3 micro-mark is used and labelled a derivative, with the failing
    measurement as the reason."""
    rep = icon_report(tuple(sorted(set(display_sizes) | set(ICON_REPORT_SIZES))))
    mono = rep["measurements"]["owner_monogram_crop"]
    failing = {px: mono[px]["problems"] for px in display_sizes if not mono[px]["ok"]}
    legible_from = next((px for px in sorted(mono) if all(mono[q]["ok"] for q in mono
                                                          if q >= px)), None)
    if not failing:
        return {"asset": "owner_monogram_crop", "derivative": False,
                "label": "Owner artwork (monogram crop, exact pixels)",
                "why": f"exact owner monogram measured legible at {list(display_sizes)} px",
                "legible_from_px": legible_from, "report": rep}
    return {"asset": "a3_micro_mark", "derivative": True,
            "label": "Small-size derivative of the owner artwork (A3 micro-mark)",
            "why": ("exact owner artwork measured illegible at " + "; ".join(
                f"{px} px: {', '.join(p)}" for px, p in failing.items())
                    + f". It is legible from {legible_from} px up, where it is used"),
            "legible_from_px": legible_from, "report": rep}


def summary() -> dict:
    v = verify()
    return {"decision": DECISION_ID, "ok": v["ok"], "problems": v["problems"],
            "assets": {r: a.to_dict() for r, a in ASSETS.items()},
            "authorised_brand_changes": list(AUTHORISED_BRAND_CHANGES),
            "hierarchy": [dict(h) for h in HIERARCHY],
            "rule": ("the owner rasters are the identity; A3 vectors support them; the "
                     "micro-mark only where the exact artwork is measured illegible; no "
                     "internal score replaces either file")}
