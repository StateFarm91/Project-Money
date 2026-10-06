"""Measuring the rendered frame rather than the plan that produced it.

Requirement 59. Deterministic bounding-box and safe-area tests: title truncation, collision,
footer overlap, edge clipping, minimum font size, mobile crop, aspect ratio, whitespace --
every frame rendered at listing scale and again at the size a shopper actually sees first.

This module exists because of a specific failure. Build 1 shipped listing images whose text
was a few pixels tall, on a hero whose fabric render had no internal contrast, and everything
upstream reported success: the plan was correct, the renderer ran, the file was written. The
defect was only ever visible in the pixels, and nothing was looking at the pixels.

So these checks measure the image. They do it without knowing the palette, because a check
that hardcodes cream is a check that passes a blank frame the day the brand changes: the
background is the colour that fills most of the frame, and *ink* is whatever differs from it.
That makes every rule below a statement about the picture rather than about the code that
drew it.

(It was inferred from the corners once, and this paragraph still said so after `_dominant`
stopped doing it. A full-bleed subject reached the corners, became the background by
definition, and a frame that was 97% one block of colour was reported as 96% empty --
`_dominant`'s own note records the fix. A docstring describing a method the function no
longer uses is the next reader's false map.)

The mobile scale is not a smaller version of the same check. An image is judged in a search
grid at a couple of hundred pixels, and detail that survives at two thousand can vanish
entirely -- which is the failure mode this catalogue has already had once. An image that is
legible at listing size and uniform at thumbnail size is an image nobody will ever click.
"""
from __future__ import annotations

from dataclasses import dataclass

# What a shopper sees first. Etsy's search grid serves a thumbnail in this region, and an
# image that dies here never gets the chance to be good at full size.
MOBILE_THUMB_PX = 170

# A pixel this far from the inferred background, on any channel, is ink.
INK_THRESHOLD = 24

# The outer band of the frame. Marketplace badges, favourite hearts and the grid's own
# rounding live here, so content inside it is content at risk.
SAFE_MARGIN = 0.04

# A frame this much one flat colour is not composed. Deliberately stated as the *dominant*
# colour rather than as the background: the first version inferred the background from the
# corners, which inverted on a full-bleed image -- the subject reached the corners, became
# the background by definition, and a frame that was 97% one block of colour was reported as
# 96% empty. Both failures are the same failure, and it is "one colour is the whole frame".
MAX_DOMINANT_SHARE = 0.94

# Ink remaining after the square centre crop a mobile grid applies. Below this, the crop has
# removed the subject.
MIN_CROP_SURVIVAL = 0.55

# The smallest run of ink rows that can be a line of type at listing scale. Below it, text is
# the few-pixel-tall smudge the font fallback produced.
MIN_TEXT_BAND_PX = 14


@dataclass(frozen=True)
class FrameReport:
    position: int
    width: int
    height: int
    aspect: float
    background_share: float
    ink_share: float
    edge_ink: float
    mobile_ink_share: float
    crop_survival: float
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_dict(self) -> dict:
        return {"position": self.position, "width": self.width, "height": self.height,
                "aspect": round(self.aspect, 4),
                "background_share": round(self.background_share, 4),
                "ink_share": round(self.ink_share, 4),
                "edge_ink": round(self.edge_ink, 4),
                "mobile_ink_share": round(self.mobile_ink_share, 4),
                "crop_survival": round(self.crop_survival, 4),
                "problems": list(self.problems), "ok": self.ok}


def _dominant(image) -> tuple[tuple[int, int, int], float]:
    """The colour that fills most of the frame, and how much of it that is.

    Inferred rather than assumed from a palette: a check that hardcodes the brand's cream
    passes a blank frame the moment the brand changes, and the blank frame is exactly what it
    was written to catch. Measured over the whole image rather than the corners, because a
    subject that bleeds to the corners would otherwise be classified as the background and
    the frame would read as empty -- which is what the first version of this did.
    """
    import numpy as np

    rgb = image.convert("RGB")
    total = rgb.size[0] * rgb.size[1]
    # Pack each pixel into one integer and count in C. The pure-Python loop this replaces
    # was correct and cost ~1 s per frame -- seconds per product on every assets.build and
    # the bulk of the acceptance gates' wall time (W3-HANG). Ties go to the colour seen first
    # in scan order, exactly as the dict-insertion-order `max` did.
    a = np.asarray(rgb, dtype=np.uint32).reshape(-1, 3)
    packed = (a[:, 0] << 16) | (a[:, 1] << 8) | a[:, 2]
    values, first, counts = np.unique(packed, return_index=True, return_counts=True)
    best = counts.max()
    winner = int(values[counts == best][np.argmin(first[counts == best])])
    colour = ((winner >> 16) & 0xFF, (winner >> 8) & 0xFF, winner & 0xFF)
    return colour, float(best) / total


def _mask_array(mask):
    import numpy as np

    return np.asarray(mask) != 0


def _ink_mask(image, background: tuple[int, int, int]):
    """A 1-bit image: white where the frame carries content, black where it is background."""
    import numpy as np
    from PIL import Image

    rgb = image.convert("RGB")
    a = np.asarray(rgb, dtype=np.int16)
    diff = np.abs(a - np.asarray(background, dtype=np.int16))
    inked = (diff > INK_THRESHOLD).any(axis=2)
    return Image.fromarray(np.where(inked, 255, 0).astype(np.uint8))


def _share(mask) -> float:
    total = mask.size[0] * mask.size[1]
    return (int(_mask_array(mask).sum()) / total) if total else 0.0


def _edge_ink(mask) -> float:
    """How much of the safe-area band carries content. Badges land here."""
    w, h = mask.size
    band_x, band_y = max(1, int(w * SAFE_MARGIN)), max(1, int(h * SAFE_MARGIN))
    m = _mask_array(mask)  # shape (h, w)
    inner = m[band_y:max(band_y, h - band_y), band_x:max(band_x, w - band_x)]
    counted = w * h - inner.size
    inked = int(m.sum()) - int(inner.sum())
    return (inked / counted) if counted else 0.0


def _tallest_text_band(mask) -> int:
    """The tallest run of consecutive rows carrying a little ink but not a lot.

    A line of type is a thin horizontal band: present, and sparse. A photograph is dense and
    a blank area is empty, so the middle is where text lives, and its height is the number
    the font-fallback defect destroyed.
    """
    w, h = mask.size
    rows = _mask_array(mask).sum(axis=1) if h else []
    best = run = 0
    for row in rows:
        density = int(row) / w if w else 0.0
        if 0.01 < density < 0.45:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _crop_survival(mask) -> float:
    """How much of the content survives the square centre crop a mobile grid applies."""
    w, h = mask.size
    m = _mask_array(mask)
    total = int(m.sum())
    if not total:
        return 0.0
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    return int(m[top:top + side, left:left + side].sum()) / total


def inspect(image, *, position: int, expect_text: bool = False) -> FrameReport:
    """Measure one rendered frame, at listing scale and at the size a shopper sees first."""
    background, dominant_share = _dominant(image)
    mask = _ink_mask(image, background)
    ink = _share(mask)
    w, h = image.size

    thumb = image.convert("RGB").resize(
        (MOBILE_THUMB_PX, max(1, round(MOBILE_THUMB_PX * h / w))))
    mobile_ink = _share(_ink_mask(thumb, _dominant(thumb)[0]))

    problems: list[str] = []
    if dominant_share > MAX_DOMINANT_SHARE:
        problems.append(
            f"FRAME_FLAT: {dominant_share:.1%} of frame {position} is one colour. Whatever "
            f"was composed on it is not visible, and every check upstream of the pixels "
            f"reported success")

    edge = _edge_ink(mask)
    if edge > 0.25:
        problems.append(
            f"FRAME_EDGE_CLIPPING: {edge:.0%} of frame {position}'s outer "
            f"{SAFE_MARGIN:.0%} band carries content. Marketplace badges and the grid's own "
            f"rounding live there, so it is content at risk rather than content")

    survival = _crop_survival(mask)
    # Only meaningful where there is a subject to lose. On a flat frame FRAME_FLAT has
    # already said the thing worth saying, and a second complaint about the crop is noise
    # that teaches a reader to skim the list.
    if ink >= 0.01 and survival < MIN_CROP_SURVIVAL:
        problems.append(
            f"FRAME_CROP_LOSS: a square centre crop keeps {survival:.0%} of frame "
            f"{position}'s content. The mobile grid applies that crop, so the shopper sees "
            f"the part that was left over")

    if mobile_ink < 0.005 <= ink:
        problems.append(
            f"FRAME_DIES_AT_THUMBNAIL: frame {position} carries content at listing scale and "
            f"almost none at {MOBILE_THUMB_PX}px. An image legible at two thousand pixels and "
            f"uniform in the search grid is an image nobody will ever click")

    if expect_text:
        band = _tallest_text_band(mask)
        if band < MIN_TEXT_BAND_PX:
            problems.append(
                f"FRAME_TEXT_TOO_SMALL: the tallest line of type on frame {position} is "
                f"{band}px. This is the few-pixel smudge a missing font produces, and it "
                f"rendered without error")

    return FrameReport(position=position, width=w, height=h, aspect=(w / h if h else 0.0),
                       background_share=1 - ink, ink_share=ink, edge_ink=edge,
                       mobile_ink_share=mobile_ink, crop_survival=survival,
                       problems=tuple(problems))


def check_frames(frames, *, text_positions: tuple[int, ...] = ()) -> list[str]:
    """Layout QA across a listing's rendered frames, in the existing problem-code style.

    A frame with no rendered image is not silently skipped: an unrendered frame is the state
    in which every pixel-level rule trivially passes.
    """
    problems: list[str] = []
    ratios: list[float] = []
    for frame in frames:
        image = getattr(frame, "image", None)
        position = getattr(frame, "position", 0)
        if image is None:
            problems.append(
                f"FRAME_NOT_RENDERED: frame {position} has no image, so the pixel rules "
                f"below it all pass by having nothing to measure")
            continue
        report = inspect(image, position=position, expect_text=position in text_positions)
        problems.extend(report.problems)
        ratios.append(report.aspect)

    if len(set(round(r, 2) for r in ratios)) > 1:
        problems.append(
            f"FRAME_RATIOS_DISAGREE: the gallery mixes aspect ratios {sorted({round(r, 2) for r in ratios})}. "
            f"A grid of frames that do not share a shape reads as a reseller's page whatever "
            f"is in them")
    return problems


def report(frames, *, text_positions: tuple[int, ...] = ()) -> dict:
    """The full measurement, for a reader who wants the numbers rather than the verdict."""
    rows = []
    for frame in frames:
        image = getattr(frame, "image", None)
        if image is None:
            rows.append({"position": getattr(frame, "position", 0), "rendered": False})
            continue
        rows.append({**inspect(image, position=frame.position,
                               expect_text=frame.position in text_positions).to_dict(),
                     "rendered": True})
    problems = check_frames(frames, text_positions=text_positions)
    return {
        "frames": rows,
        "problems": problems,
        "ok": not problems,
        "mobile_thumb_px": MOBILE_THUMB_PX,
        "note": ("Measured on the rendered pixels, with the background taken as the frame's "
                 "dominant colour rather than assumed from the palette. Every rule here is a "
                 "statement about the picture rather than about the code that drew it (#59)."),
    }


# ---------------------------------------------------------------------------
# Bounding boxes (C-69, #59): the rules only the renderer's own boxes can decide.
#
# `listing_assets` records every line of type and every pasted graphic as it draws them
# (`image.info["layout"]`). These rules read those boxes: a line of type outside the safe
# area is truncated or clipped, type that overlaps a chart or a fabric render is a collision,
# the lowest line (the footer) overlapping anything above it is a footer overlap, and a line
# set in a face smaller than the minimum is too small to read at listing scale. An image with
# no recorded layout is reported, never passed.

MIN_TEXT_PT = 16
# Overlap below this many square pixels is anti-aliasing touching, not a collision.
MIN_OVERLAP_PX = 60


def _intersection(a, b) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def check_layout(image, *, position: int, safe_margin: float = SAFE_MARGIN) -> list[str]:
    layout = list((getattr(image, "info", None) or {}).get("layout") or [])
    if not layout:
        return [f"LAYOUT_UNRECORDED: frame {position} carries no recorded layout, so title "
                f"truncation, collisions and footer overlap cannot be measured on it"]
    w, h = image.size
    m_x, m_y = int(w * safe_margin), int(h * safe_margin)
    problems: list[str] = []
    texts = [e for e in layout if e.get("kind") == "text" and str(e.get("text", "")).strip()]
    graphics = [e for e in layout if e.get("kind") != "text"]
    for e in texts:
        x0, y0, x1, y1 = e["box"]
        if x0 < m_x or y0 < m_y or x1 > w - m_x or y1 > h - m_y:
            problems.append(
                f"LAYOUT_TEXT_OUTSIDE_SAFE_AREA: frame {position}: {e['text']!r} spans "
                f"{e['box']} against a safe area of {m_x}..{w - m_x} x {m_y}..{h - m_y}; a "
                f"title past the edge is a truncated title")
        if e.get("pt") is not None and e["pt"] < MIN_TEXT_PT:
            problems.append(
                f"LAYOUT_TEXT_TOO_SMALL: frame {position}: {e['text']!r} is set at "
                f"{e['pt']}pt against a minimum of {MIN_TEXT_PT}")
        for g in graphics:
            if _intersection(e["box"], g["box"]) > MIN_OVERLAP_PX:
                problems.append(
                    f"LAYOUT_TEXT_GRAPHIC_COLLISION: frame {position}: {e['text']!r} "
                    f"overlaps the {g['kind']} at {g['box']}")
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if _intersection(a["box"], b["box"]) > MIN_OVERLAP_PX:
                footer = max((a, b), key=lambda e: e["box"][3])
                code = ("LAYOUT_FOOTER_OVERLAP" if footer is max(texts, key=lambda e: e["box"][3])
                        else "LAYOUT_TEXT_COLLISION")
                problems.append(f"{code}: frame {position}: {a['text']!r} and {b['text']!r} "
                                f"overlap")
    return problems


def check_listing_frames(frames, *, text_positions: tuple[int, ...] = ()) -> list[str]:
    """#59 on every listing frame: pixel rules plus the box rules, each frame by position."""
    problems = check_frames(frames, text_positions=text_positions)
    for frame in frames:
        image = getattr(frame, "image", None)
        if image is not None:
            problems.extend(check_layout(image, position=getattr(frame, "position", 0)))
    return problems
