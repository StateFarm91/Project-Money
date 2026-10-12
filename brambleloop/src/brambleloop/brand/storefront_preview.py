"""The storefront as a buyer would first see it, rendered before there is a storefront.

F-239 (mobile storefront QA) and F-293 (storefront visual inspection). The listing set already
has its shopper contexts (`publish.mobile`, requirement 66); the shop itself had text checks
only. This renders the shop's own surfaces deterministically, at phone and desktop widths,
and measures them:

- **the icon** at 40 px and 70 px -- the sizes it is actually shown at -- for contrast against
  its own ground, for the share of the frame the mark occupies, and for a stroke that still
  exists at 40 px;
- **the banner** at the desktop width and centre-cropped for a phone, checking the wordmark
  survives the crop inside the safe margin and stays a readable height;
- **the announcement** as far as a phone shows it before "read more": the opening sentence
  must fit and the cut must fall between words;
- **the section list** -- only sections the opening grid populates are shown, as on Etsy;
- **the first tiles** of the opening grid (`storefront.opening_grid`, F-238): four on a phone,
  six on desktop, each from the frame-1 bytes of a *valid listing-set certificate* -- an
  uncertified listing has no tile, it does not get a placeholder.

**What this is not.** The approved banner and icon do not exist yet; the shop has briefs. So
by default both are rendered from the brief's layout (`storefront.BANNER_WORDMARK_BOX`, the
palette), labelled `simulated_from_brief`, and `preview(icon=..., banner=...)` measures real
artwork the moment there is some. And none of this is the live storefront: inspecting the
shop as Etsy actually serves it needs a browser worker (gate `rendered_pages`) and a live
shop. That inspection is recorded as `EXTERNAL_GATED`, never as passed.

The viewport figures below are this company's assumptions about Etsy's layout, stated as
assumptions -- the conservative reading is used where Etsy's own number is unknown.
"""
from __future__ import annotations

import hashlib
import io

from . import bible, storefront

ICON_SIZES = (40, 70)
# WCAG 2.1 1.4.11: graphical objects need 3:1 against adjacent colour.
ICON_MIN_CONTRAST = 3.0
ICON_COVERAGE = (0.08, 0.60)     # a mark too thin vanishes; one filling the frame is a blob
ICON_MIN_STROKE_PX = 2           # at 40 px, a stroke under two pixels is anti-aliasing noise

ASSUMED = "ASSUMED"
# ASSUMED: the narrowest crop a phone applies to a 4:1 banner is a centred 2:1 window,
# shown 360 px wide. The real figure is Etsy's and unread; 2:1 is the conservative reading.
PHONE_WIDTH = 360
PHONE_BANNER_ASPECT = 2.0
DESKTOP_WIDTH = 1280
WORDMARK_MIN_PX = 16             # the wordmark's rendered height on a phone
# ASSUMED: a phone shows two lines of the announcement at about 43 characters each.
PHONE_ANNOUNCEMENT_CHARS = 86
SECTION_LABEL_MAX = 30           # ASSUMED: one line of a 360 px section menu
PHONE_TILES = 4
DESKTOP_TILES = 6
PHONE_TILE_PX = 164
DESKTOP_TILE_PX = 300

SIMULATED = "simulated_from_brief"
SUPPLIED = "supplied_artwork"


def _rgb(name: str) -> tuple[int, int, int]:
    return bible.rgb255(name)


def _unit(rgb) -> tuple[float, float, float]:
    return tuple(c / 255.0 for c in rgb)  # type: ignore[return-value]


def _png(image) -> tuple[bytes, str]:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=False)
    data = buf.getvalue()
    return data, hashlib.sha256(data).hexdigest()


# ---- the icon ---------------------------------------------------------------------------

def render_icon():
    """The icon brief as pixels: one loop-and-bramble mark in pine on cream, no text."""
    from PIL import Image, ImageDraw

    w, h = storefront.ICON_SIZE
    im = Image.new("RGB", (w, h), _rgb("cream"))
    d = ImageDraw.Draw(im)
    pad = int(w * 0.18)
    d.ellipse((pad, pad, w - pad, h - pad), outline=_rgb("pine"), width=int(w * 0.12))
    # the bramble: a leaf crossing the loop's lower right
    d.ellipse((int(w * 0.55), int(h * 0.55), int(w * 0.82), int(h * 0.74)), fill=_rgb("pine"))
    return im


def _classify(im, ink, ground):
    """Each pixel assigned to whichever of the two colours it is nearer."""
    px = list(im.getdata())

    def dist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    mark = [p for p in px if dist(p, ink) < dist(p, ground)]
    rest = [p for p in px if dist(p, ink) >= dist(p, ground)]
    return mark, rest, px


def _mean(pixels):
    n = len(pixels)
    return tuple(sum(p[i] for p in pixels) / n for i in range(3)) if n else (0.0, 0.0, 0.0)


def icon_legibility(icon, size: int) -> dict:
    """The icon at `size` px: contrast of mark vs ground, coverage, and surviving stroke."""
    from PIL import Image

    small = icon.convert("RGB").resize((size, size), Image.LANCZOS)
    ink, ground = _rgb("pine"), _rgb("cream")
    mark, rest, px = _classify(small, ink, ground)
    coverage = len(mark) / len(px)
    contrast = (bible.contrast_ratio(_unit(_mean(mark)), _unit(_mean(rest)))
                if mark and rest else 1.0)
    # The ring's stroke where the centre row crosses it: the first run of mark pixels from
    # the left edge. That is the line a shopper has to resolve at this size.
    mark_set = set(mark)
    row = [px[(size // 2) * size + x] in mark_set for x in range(size)]
    longest, x = 0, 0
    while x < size and not row[x]:
        x += 1
    while x < size and row[x]:
        longest, x = longest + 1, x + 1
    problems = []
    if contrast < ICON_MIN_CONTRAST:
        problems.append(f"icon at {size}px: contrast {contrast:.2f}:1 under "
                        f"{ICON_MIN_CONTRAST}:1")
    if not ICON_COVERAGE[0] <= coverage <= ICON_COVERAGE[1]:
        problems.append(f"icon at {size}px: the mark covers {coverage:.0%} of the frame, "
                        f"outside {ICON_COVERAGE[0]:.0%}-{ICON_COVERAGE[1]:.0%}")
    if longest < ICON_MIN_STROKE_PX:
        problems.append(f"icon at {size}px: no stroke survives ({longest}px)")
    _, digest = _png(small)
    return {"size": size, "contrast": round(contrast, 2), "coverage": round(coverage, 3),
            "max_stroke_px": longest, "ok": not problems, "problems": problems,
            "render_sha256": digest}


# ---- the banner -------------------------------------------------------------------------

def render_banner():
    """The banner brief as pixels: cream ground, fabric band, wordmark block in its box."""
    from PIL import Image, ImageDraw

    w, h = storefront.BANNER_SIZE
    im = Image.new("RGB", (w, h), _rgb("cream"))
    d = ImageDraw.Draw(im)
    d.rectangle((0, int(h * 0.72), w, h), fill=_rgb("line"))       # the fabric flat-lay
    d.rectangle(storefront.BANNER_WORDMARK_BOX, fill=_rgb("pine"))  # the wordmark's block
    return im


def banner_crops(box=None, size=None) -> dict:
    """Where the wordmark lands at desktop width and in a phone's centre crop."""
    w, h = size or storefront.BANNER_SIZE
    x0, y0, x1, y1 = box or storefront.BANNER_WORDMARK_BOX
    margin = bible.CROP_RULES["safe_margin_pct"]
    out = {}
    crop_w = min(w, int(round(h * PHONE_BANNER_ASPECT)))
    left = (w - crop_w) // 2
    for name, (cx0, cw, shown_w) in {
            "desktop": (0, w, DESKTOP_WIDTH),
            "phone": (left, crop_w, PHONE_WIDTH)}.items():
        scale = shown_w / cw
        mx, my = cw * margin, h * margin
        inside = (x0 >= cx0 + mx and x1 <= cx0 + cw - mx and y0 >= my and y1 <= h - my)
        height_px = (y1 - y0) * scale
        problems = []
        if not inside:
            problems.append(f"banner ({name}): the wordmark leaves the "
                            f"{int(margin * 100)}% safe area of the {cw}x{h} crop")
        if height_px < WORDMARK_MIN_PX:
            problems.append(f"banner ({name}): the wordmark is {height_px:.0f}px tall, under "
                            f"{WORDMARK_MIN_PX}px")
        out[name] = {"crop": [cx0, 0, cx0 + cw, h], "shown_width": shown_w,
                     "wordmark_height_px": round(height_px, 1), "inside_safe_area": inside,
                     "ok": not problems, "problems": problems}
    return out


def banner_legibility(banner=None) -> dict:
    """Crop geometry plus the measured wordmark contrast on the rendered banner."""
    from PIL import Image

    im = (banner or render_banner()).convert("RGB")
    crops = banner_crops(size=im.size)
    x0, y0, x1, y1 = storefront.BANNER_WORDMARK_BOX
    word = im.crop((x0, y0, x1, y1))
    ground = im.crop((x0, max(0, y0 - 40), x1, y0))
    contrast = bible.contrast_ratio(_unit(_mean(list(word.getdata()))),
                                    _unit(_mean(list(ground.getdata()))))
    problems = [p for c in crops.values() for p in c["problems"]]
    if contrast < bible.MIN_TEXT_CONTRAST:
        problems.append(f"banner: wordmark contrast {contrast:.2f}:1 under "
                        f"{bible.MIN_TEXT_CONTRAST}:1")
    renders = {}
    for name, c in crops.items():
        cx0, _, cx1, h = c["crop"]
        shown = im.crop((cx0, 0, cx1, h)).resize(
            (c["shown_width"], max(1, int(h * c["shown_width"] / (cx1 - cx0)))), Image.LANCZOS)
        renders[name] = _png(shown)[1]
    return {"crops": crops, "wordmark_contrast": round(contrast, 2), "ok": not problems,
            "problems": problems, "render_sha256": renders}


# ---- text surfaces ----------------------------------------------------------------------

def announcement_opening(text: str, limit: int = PHONE_ANNOUNCEMENT_CHARS) -> dict:
    """What a phone shows of the announcement before "read more", cut between words."""
    text = (text or "").strip()
    if len(text) <= limit:
        shown, truncated = text, False
    else:
        cut = text[:limit]
        shown, truncated = (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(), True
    first = text.split(". ")[0].rstrip(".") + "." if text else ""
    problems = []
    if not shown:
        problems.append("announcement: nothing is shown on a phone")
    elif truncated and len(first) > limit:
        problems.append(f"announcement: the opening sentence ({len(first)} chars) does not fit "
                        f"the {limit} a phone shows, so the shop's first words are cut")
    return {"shown": shown, "truncated": truncated, "limit": limit, "limit_basis": ASSUMED,
            "ok": not problems, "problems": problems}


def section_list(grid: dict) -> dict:
    populated: dict[str, int] = {}
    for t in grid.get("tiles") or []:
        populated[t["section"]] = populated.get(t["section"], 0) + 1
    shown = [{"slug": s.slug, "name": s.name, "listings": populated[s.slug]}
             for s in storefront.SECTIONS if populated.get(s.slug)]
    problems = []
    if not shown:
        problems.append("sections: no section has a launch-cleared listing in it")
    for s in shown:
        if len(s["name"]) > SECTION_LABEL_MAX:
            problems.append(f"sections: {s['name']!r} is longer than one phone-menu line")
    return {"shown": shown, "hidden_empty": [s.slug for s in storefront.SECTIONS
                                             if not populated.get(s.slug)],
            "ok": not problems, "problems": problems}


# ---- the first tiles --------------------------------------------------------------------

def _certified_hero(db, slug: str, version: str):
    """Frame 1's sha256 from the valid listing-set certificate, or None."""
    from sqlalchemy import desc, select

    from ..core.models import ListingSetCertificateRecord

    with db.session() as s:
        rec = s.scalar(select(ListingSetCertificateRecord).where(
            ListingSetCertificateRecord.product_slug == slug,
            ListingSetCertificateRecord.version == version,
            ListingSetCertificateRecord.state == "valid")
            .order_by(desc(ListingSetCertificateRecord.id)).limit(1))
        frames = list((rec.certificate or {}).get("frames") or []) if rec else []
    hero = next((f for f in frames if f.get("position") == 1), None)
    return (hero or {}).get("sha256") or None


def tiles(db, grid: dict, *, store_root=None) -> dict:
    from PIL import Image

    from ..core.artifacts import ArtifactMissing, ArtifactStore

    store = ArtifactStore(store_root)
    out, images = [], {}
    for t in (grid.get("visible") or [])[:DESKTOP_TILES]:
        sha = _certified_hero(db, t["slug"], t["version"])
        row = {"slug": t["slug"], "version": t["version"], "frame_sha256": sha}
        if not sha:
            row.update(status="not_certified",
                       why="no valid listing-set certificate names a frame 1")
        else:
            try:
                images[t["slug"]] = Image.open(io.BytesIO(store.get(sha, db=db))).convert("RGB")
                row.update(status="rendered")
            except (ArtifactMissing, OSError) as e:
                row.update(status="bytes_missing", why=str(e)[:160])
        out.append(row)
    problems = []
    rendered = [r for r in out if r["status"] == "rendered"]
    if len(rendered) < PHONE_TILES:
        problems.append(f"grid: {len(rendered)} certified tile(s) render, a phone's first "
                        f"screen needs {PHONE_TILES}")
    for r in out:
        if r["status"] != "rendered":
            problems.append(f"grid: {r['slug']} {r['status']}")
    return {"tiles": out, "images": images, "ok": not problems, "problems": problems}


def _sheet(images: list, px: int, columns: int):
    from PIL import Image

    rows = max(1, -(-len(images) // columns))
    sheet = Image.new("RGB", (px * columns, px * rows), _rgb("cream"))
    for i, im in enumerate(images):
        sheet.paste(im.resize((px, px)), ((i % columns) * px, (i // columns) * px))
    return sheet


# ---- the preview ------------------------------------------------------------------------

def live_inspection(db) -> dict:
    """The live storefront as Etsy serves it: external, gated, and never claimed here."""
    # The browser half of `rendered_pages` only (W4-B2CLOSE): that gate also opens on a
    # person's policy-page readings (#35/#39), which inspect no storefront.
    try:
        from ..intel.browser import usable

        gate_open = bool(usable(db))
    except Exception:  # noqa: BLE001 - an unreadable gate is not an open one
        gate_open = False
    return {"status": "EXTERNAL_GATED", "gate": "rendered_pages", "gate_open": gate_open,
            "passed": False,
            "why": ("inspecting the live storefront as a buyer sees it needs a browser worker "
                    "and a live shop; this preview is a pre-launch simulation and is not that "
                    "inspection")}


def preview(db, *, today=None, icon=None, banner=None, grid: dict | None = None,
            store_root=None) -> dict:
    """The whole pre-launch storefront preview, measured, at phone and desktop widths."""
    store = storefront.build_storefront(db=db, today=today)
    grid = grid if grid is not None else storefront.opening_grid(db, today=today)
    icon_basis = SUPPLIED if icon is not None else SIMULATED
    banner_basis = SUPPLIED if banner is not None else SIMULATED
    icon_img = icon if icon is not None else render_icon()
    banner_img = banner if banner is not None else render_banner()

    icon_checks = [icon_legibility(icon_img, s) for s in ICON_SIZES]
    banner_checks = banner_legibility(banner_img)
    announcement = announcement_opening(store.announcement)
    sections = section_list(grid)
    tile_checks = tiles(db, grid, store_root=store_root)

    renders = {}
    images = [tile_checks["images"][r["slug"]] for r in tile_checks["tiles"]
              if r["status"] == "rendered"]
    for name, n, px, cols in (("phone_grid", PHONE_TILES, PHONE_TILE_PX, 2),
                              ("desktop_grid", DESKTOP_TILES, DESKTOP_TILE_PX, 3)):
        renders[name] = _png(_sheet(images[:n], px, cols))[1] if images else None

    problems: list[str] = []
    for c in icon_checks:
        problems.extend(c["problems"])
    problems.extend(banner_checks["problems"])
    problems.extend(announcement["problems"])
    problems.extend(sections["problems"])
    problems.extend(tile_checks["problems"])
    # F-293: no blank or default surface, no stale identity, no weak grid, no season mismatch.
    problems.extend(f"storefront: {p}" for p in storefront.check_storefront(store))
    problems.extend(f"opening grid: {p}" for p in grid.get("problems") or [])
    return {
        "rendered": True,
        "ok": not problems,
        "problems": problems,
        "icon": {"basis": icon_basis, "sizes": icon_checks},
        "banner": {"basis": banner_basis, **banner_checks},
        "announcement": announcement,
        "sections": sections,
        "tiles": tile_checks["tiles"],
        "grid_render_sha256": renders,
        "seasonal": {"active_events": grid.get("active_events") or [],
                     "announcement": store.announcement},
        "assumptions": {"phone_width": PHONE_WIDTH, "phone_banner_aspect": PHONE_BANNER_ASPECT,
                        "desktop_width": DESKTOP_WIDTH,
                        "phone_announcement_chars": PHONE_ANNOUNCEMENT_CHARS,
                        "basis": ASSUMED},
        "live_inspection": live_inspection(db),
    }
