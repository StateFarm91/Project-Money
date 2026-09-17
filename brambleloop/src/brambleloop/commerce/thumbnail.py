"""Thumbnail Warfare (Master Plan section 7).

Section 7 asks for an agent that evaluates hero variants "at mobile/search-grid scale using
real CTR, favorites and conversion". Two halves, and only one of them is available today.

The half that needs real data does not exist yet and is not faked here. `rank_by_evidence`
requires observations and refuses to name a winner without enough of them; there are no
observations, so it currently refuses. Section 8's hard rule -- no fabricated engagement --
applies to our own metrics as much as to a marketplace's.

The half that works now is the part everyone skips: a hero is judged at the size it is
actually seen. Etsy's search grid shows a listing image at roughly 230px on a phone, and an
image composed at 2000px can be unreadable there while looking excellent in the editor. So
the checks below downscale the real image and measure what survives -- contrast, how much of
the frame the subject occupies, whether text is still legible, and whether the thing reads as
distinct from its neighbours in a grid.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

# Etsy's search grid on a phone. Not a round number because the point is to test the real one.
GRID_PX = 230
MIN_CONTRAST_RATIO = 3.0        # WCAG's large-text floor; a thumbnail is large text
MIN_SUBJECT_COVERAGE = 0.35     # below this the hero is mostly background
MAX_SUBJECT_COVERAGE = 0.92     # above this it is a texture swatch with no shape
MIN_LEGIBLE_TEXT_PX = 11        # rendered height at grid scale


@dataclass
class ThumbnailVerdict:
    ok: bool
    score: float
    measurements: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "score": round(self.score, 3),
                "measurements": {k: (round(v, 4) if isinstance(v, float) else v)
                                 for k, v in self.measurements.items()},
                "problems": list(self.problems)}


def _relative_luminance(rgb) -> float:
    def channel(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def achievable_coverage(subject_aspect: float | None) -> float:
    """The most of a square frame an object of this shape can occupy.

    A table runner is long and thin. Fitted into Etsy's square crop it cannot fill much of the
    frame however well it is composed, and holding it to a blanket's standard would be asking
    the renderer to lie about the product's proportions.
    """
    if not subject_aspect or subject_aspect <= 0:
        return 1.0
    return min(subject_aspect, 1.0 / subject_aspect)


def evaluate_thumbnail(image: Image.Image, *, text_pt_on_canvas: float = 0.0,
                       canvas_px: int | None = None,
                       subject_aspect: float | None = None) -> ThumbnailVerdict:
    """Judge a hero at the size a shopper actually sees it.

    Downscales to the real grid size first. Every measurement below is taken on the small
    image, because an image evaluated at full resolution is being evaluated in a context that
    no customer will ever be in.
    """
    problems: list[str] = []
    canvas_px = canvas_px or image.width
    small = image.convert("RGB").resize((GRID_PX, GRID_PX), Image.LANCZOS)
    px = small.load()

    # Background is whatever occupies the corners; subject is everything unlike it.
    corners = [px[2, 2], px[GRID_PX - 3, 2], px[2, GRID_PX - 3], px[GRID_PX - 3, GRID_PX - 3]]
    bg = tuple(sum(c[i] for c in corners) // len(corners) for i in range(3))

    # Coverage is the subject's *footprint*, taken as the bounding box of everything unlike
    # the background -- not the count of non-background pixels.
    #
    # This distinction is the whole measurement. A two-colour crochet fabric is about half
    # cream, and cream is also the brand background, so counting pixels scored a perfectly
    # composed hero at 9% and blocked six products for a problem none of them had. The
    # question a thumbnail check is asking is "how much of the frame does the object occupy",
    # and an object with light parts in it still occupies its own area.
    min_x, min_y, max_x, max_y = GRID_PX, GRID_PX, -1, -1
    darkest = bg
    for y in range(0, GRID_PX, 2):
        for x in range(0, GRID_PX, 2):
            p = px[x, y]
            if sum(abs(p[i] - bg[i]) for i in range(3)) > 60:
                min_x, max_x = min(min_x, x), max(max_x, x)
                min_y, max_y = min(min_y, y), max(max_y, y)
                if _relative_luminance(p) < _relative_luminance(darkest):
                    darkest = p
    if max_x < 0:
        coverage = 0.0
    else:
        coverage = ((max_x - min_x + 1) * (max_y - min_y + 1)) / (GRID_PX * GRID_PX)
    ratio = contrast_ratio(darkest, bg)

    if ratio < MIN_CONTRAST_RATIO:
        problems.append(
            f"THUMB_LOW_CONTRAST: {ratio:.1f}:1 at grid scale; below {MIN_CONTRAST_RATIO}:1 "
            f"the image is a smudge in a search grid")
    # Scaled by what the subject's proportions allow rather than a flat number. A flat floor
    # asks a table runner to be as square as a blanket, which the renderer can only satisfy
    # by misrepresenting the product's shape.
    ceiling = achievable_coverage(subject_aspect)
    floor = MIN_SUBJECT_COVERAGE * ceiling
    if coverage < floor:
        problems.append(
            f"THUMB_SUBJECT_TOO_SMALL: the subject fills {coverage:.0%} of the frame against "
            f"a {ceiling:.0%} ceiling for its proportions; a hero that is mostly background "
            f"loses the click to one that is not")
    if coverage > MAX_SUBJECT_COVERAGE:
        problems.append(
            f"THUMB_NO_BREATHING_ROOM: {coverage:.0%} coverage reads as a texture swatch "
            f"rather than an object")
    if text_pt_on_canvas:
        rendered = text_pt_on_canvas * GRID_PX / canvas_px
        if rendered < MIN_LEGIBLE_TEXT_PX:
            problems.append(
                f"THUMB_TEXT_ILLEGIBLE: text renders at {rendered:.1f}px in the grid; "
                f"anything under {MIN_LEGIBLE_TEXT_PX}px is decoration, not information")

    score = 0.0
    score += min(1.0, ratio / 6.0) * 0.45
    target = max(0.45, ceiling * 0.8)
    band = 1.0 - abs(coverage - target) / max(target, 1e-6)
    score += max(0.0, band) * 0.40
    score += 0.15 if not problems else 0.0
    return ThumbnailVerdict(ok=not problems, score=score,
                            measurements={"contrast_ratio": ratio,
                                          "subject_coverage": coverage,
                                          "coverage_ceiling": ceiling,
                                          "grid_px": GRID_PX,
                                          "background_rgb": list(bg)},
                            problems=problems)


def distinctiveness(images: list[Image.Image]) -> float:
    """How different these heroes look from each other in one grid.

    A shop whose listings are indistinguishable at thumbnail size has one listing repeated,
    from the shopper's point of view. Measured as the average pairwise difference of heavily
    downscaled images -- crude on purpose, because the shopper's glance is crude.
    """
    if len(images) < 2:
        return 1.0
    thumbs = [img.convert("RGB").resize((16, 16), Image.LANCZOS) for img in images]
    diffs = []
    for i in range(len(thumbs)):
        for j in range(i + 1, len(thumbs)):
            a, b = thumbs[i].load(), thumbs[j].load()
            d = sum(abs(a[x, y][c] - b[x, y][c])
                    for x in range(16) for y in range(16) for c in range(3))
            diffs.append(d / (16 * 16 * 3 * 255))
    return round(sum(diffs) / len(diffs), 4)


# ---- the half that needs real data ----------------------------------------


class NotEnoughEvidence(RuntimeError):
    """A variant was declared a winner before the data could support it."""


MIN_IMPRESSIONS_PER_VARIANT = 500


@dataclass
class VariantObservation:
    variant: str
    impressions: int
    clicks: int
    favourites: int
    orders: int

    @property
    def ctr(self) -> float:
        return self.clicks / self.impressions if self.impressions else 0.0

    @property
    def conversion(self) -> float:
        return self.orders / self.clicks if self.clicks else 0.0


def rank_by_evidence(observations: list[VariantObservation],
                     min_impressions: int = MIN_IMPRESSIONS_PER_VARIANT) -> dict:
    """Rank hero variants on observed behaviour, or refuse.

    There are no observations yet, so in practice this refuses, and that is the correct
    output. Section 8 forbids fabricated engagement; inventing plausible CTRs to make a
    ranking function return something would be exactly that, applied to ourselves.
    """
    if not observations:
        raise NotEnoughEvidence(
            "no impressions have been observed. Nothing is published, so there is no CTR, no "
            "favourites and no conversion data, and a ranking produced without them would be "
            "invented. Compositional checks can run now; this one cannot.")
    thin = [o.variant for o in observations if o.impressions < min_impressions]
    if thin:
        raise NotEnoughEvidence(
            f"{thin} have fewer than {min_impressions} impressions. A CTR difference at that "
            f"volume is noise, and acting on it teaches the system something untrue.")
    ranked = sorted(observations,
                    key=lambda o: (o.ctr * max(o.conversion, 1e-6)), reverse=True)
    return {
        "winner": ranked[0].variant,
        "basis": "click-through multiplied by conversion, not click-through alone",
        "note": ("a variant that wins clicks and loses conversions is a promise the product "
                 "does not keep, which costs more than the clicks are worth"),
        "ranking": [{"variant": o.variant, "impressions": o.impressions,
                     "ctr": round(o.ctr, 5), "conversion": round(o.conversion, 5),
                     "favourites": o.favourites} for o in ranked],
    }
