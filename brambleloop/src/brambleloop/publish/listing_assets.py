"""The listing image system (Master Plan section 7).

Section 7 is specific about what listing imagery is for: the first image exists to win the
click, and every frame after it answers a question that would otherwise stop a purchase. So
the frame plan here is not decoration, it is an ordered argument -- what it looks like, what
you get, how big it is, what it takes, what the pattern actually reads like, what else is in
the collection.

Two rules make this system different from writing the same thing by hand.

Every frame is rendered from the digital twin, so the sizes, colours, stitches, yardage and
row counts on an infographic are the compiled pattern's own numbers. There is no path by
which a listing image and the pattern disagree, because there is no second source.

And every frame declares its asset class and its claims, so Asset Truth checks the images the
way it checks anything else. A render may never present itself as a photograph of a finished
object, and an AI lifestyle concept may never be the hero -- a picture of a thing nobody has
made is not evidence the thing exists.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from ..brand import bible
from ..cir.model import CIR
from ..cir.twin import TwinModel
from ..cir.writer import collapses_rows
from ..gates.asset_truth import Asset, AssetClass, Claims, Provenance
from .charts import (
    ChartSpec, _font, _hex_to_rgb, crop_grids, detect_repeat, is_round, render_chart,
    render_fabric, render_round_chart, render_round_fabric,
)

CANVAS = 2000            # Etsy recommends 2000px on the short edge for listing images
INK = _hex_to_rgb(bible.PALETTE["ink"])
PINE = _hex_to_rgb(bible.PALETTE["pine"])
CREAM = _hex_to_rgb(bible.PALETTE["cream"])
GOLD = _hex_to_rgb(bible.PALETTE["gold"])
LINE = _hex_to_rgb(bible.PALETTE["line"])
MUTED = _hex_to_rgb(bible.PALETTE["muted"])


@dataclass
class Frame:
    """One listing image: its job, its class, and what it is allowed to claim."""

    position: int
    role: str
    asset_class: AssetClass
    caption: str
    image: Image.Image | None = None
    claims: Claims = field(default_factory=Claims)
    depicts_stitches: list[str] = field(default_factory=list)
    depicts_colors: list[str] = field(default_factory=list)

    @property
    def is_hero(self) -> bool:
        return self.position == 1

    def to_asset(self, slug: str) -> Asset:
        return Asset(
            asset_id=f"{slug}-frame-{self.position}",
            asset_class=self.asset_class,
            provenance=Provenance(source="twin", created_by="publishing",
                                  tool="listing_assets@1"),
            depicts_stitches=sorted(self.depicts_stitches),
            depicts_colors=sorted(self.depicts_colors),
            is_hero=self.is_hero,
            claims=self.claims,
        )

    def png(self) -> bytes:
        if self.image is None:
            raise ValueError(f"frame {self.position} ({self.role}) has no image")
        buf = io.BytesIO()
        self.image.save(buf, format="PNG")
        return buf.getvalue()


# ---- drawing helpers -------------------------------------------------------


def _canvas(size: int = CANVAS) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (size, size), CREAM)
    return img, ImageDraw.Draw(img)


def _safe(size: int = CANVAS) -> int:
    """Nothing meaningful inside the outer margin -- Etsy's grid crops without asking."""
    return int(size * bible.CROP_RULES["safe_margin_pct"])


def _wrap(d: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out


def _fit_text(d: ImageDraw.ImageDraw, text: str, x: int, y: int, max_w: int,
              start_pt: int, color) -> None:
    """Shrink until it fits rather than letting a long title run off the canvas.

    A title clipped mid-word is the single clearest signal that a listing was machine-made
    without anyone looking at it, which is the opposite of what this brand is selling.
    """
    pt = start_pt
    while pt > 14:
        font = _font(pt)
        if d.textlength(text, font=font) <= max_w:
            break
        pt = int(pt * 0.94)
    d.text((x, y), text, font=_font(pt), fill=color)


def _title_block(d: ImageDraw.ImageDraw, text: str, y: int, size: int = CANVAS,
                 color=PINE) -> int:
    font = _font(int(size * 0.052))
    m = _safe(size)
    for line in _wrap(d, text, font, size - 2 * m):
        d.text((m, y), line, font=font, fill=color)
        y += int(size * 0.062)
    d.line([(m, y + 10), (m + int(size * 0.09), y + 10)], fill=GOLD, width=4)
    return y + int(size * 0.05)


def _rows(d: ImageDraw.ImageDraw, pairs: list[tuple[str, str]], y: int,
          size: int = CANVAS) -> int:
    """Label/value rows. The whole point of these frames is legibility at thumbnail size."""
    label_font = _font(int(size * 0.026))
    value_font = _font(int(size * 0.034))
    m = _safe(size)
    for label, value in pairs:
        d.text((m, y), label.upper(), font=label_font, fill=MUTED)
        y += int(size * 0.034)
        for line in _wrap(d, value, value_font, size - 2 * m):
            d.text((m, y), line, font=value_font, fill=INK)
            y += int(size * 0.045)
        y += int(size * 0.022)
    return y


# ---- the frames ------------------------------------------------------------


def _hero(cir: CIR, twin: TwinModel) -> Frame:
    """A clean finished-result hero, not a cluttered collage (section 7).

    Until a physical sample exists this is a digital twin render, and it says so on the
    image. Section 7's asset classes exist precisely so a render cannot quietly do a
    photograph's job.
    """
    size = CANVAS
    img, d = _canvas(size)
    m = _safe(size)

    # The fabric gets most of the frame. Thumbnail Warfare measures subject coverage at
    # search-grid size, and a hero that is mostly cream background loses the click to one
    # that is not -- an earlier layout sat barely above the floor at 36%.
    top = int(size * 0.175)
    bottom = int(size * 0.885)
    box_w, box_h = int(size * 0.96), bottom - top
    round_worked = is_round(cir, twin)
    if round_worked:
        # A round piece has no rectangle of fabric to show. The twin knows it as rounds, so
        # the hero is the object from above -- which is honest, and says so on the image.
        fabric = render_round_fabric(cir, twin, ChartSpec(cell_px=26))
    else:
        grid, colour_grid = twin.chart_grid(), twin.color_grid()
        cols, rows = detect_repeat(grid, colour_grid)
        grids = crop_grids(grid, colour_grid,
                           min(cols * 4, max(len(r) for r in grid)),
                           min(rows * 3, len(grid)))
        fabric = render_fabric(cir, twin, cell_px=24, grids=grids)
    scale = min(box_w / fabric.width, box_h / fabric.height)
    fabric = fabric.resize((max(1, int(fabric.width * scale)),
                            max(1, int(fabric.height * scale))), Image.LANCZOS)
    img.paste(fabric, ((size - fabric.width) // 2, top + (box_h - fabric.height) // 2))

    d.text((m, int(size * 0.072)), "BRAMBLELOOP STUDIO", font=_font(int(size * 0.024)),
           fill=MUTED)
    _fit_text(d, cir.title, m, int(size * 0.105), size - 2 * m, int(size * 0.056), PINE)

    foot = _font(int(size * 0.025))
    d.text((m, int(size * 0.900)), "CROCHET PATTERN · PDF · CHART + WRITTEN", font=foot,
           fill=GOLD)
    d.text((m, int(size * 0.936)),
           ("Digital render from above, not a photograph of a finished item"
            if round_worked else
            "Digital pattern render, not a photograph of a finished item"), font=foot,
           fill=MUTED)
    return Frame(position=1, role="hero", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                 caption="clean finished-result hero", image=img,
                 depicts_stitches=sorted(twin.stitch_types_used),
                 depicts_colors=sorted(c for c in twin.colors_used if c),
                 claims=Claims(colors=sorted(c for c in twin.colors_used if c)))


def _whats_included(cir: CIR, twin: TwinModel, pages: int | None,
                    collapsed_repeats: bool = False) -> Frame:
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "What you get", int(size * 0.10), size)
    items = [
        ("Written pattern",
         "Row by row with a stitch count on each; the repeat written once"
         if collapsed_repeats else "Every row, with a stitch count on each"),
        ("Colour chart", "Generated from the same data as the words, so they cannot disagree"),
        ("Terminology", "US terms, with the UK equivalent in the stitch key"),
    ]
    if pages:
        items.append(("Format", f"{pages}-page PDF, instant download, readable on a phone"))
    _rows(d, items, y, size)
    return Frame(position=2, role="whats_included", asset_class=AssetClass.INFOGRAPHIC,
                 caption="what is included", image=img)


def _size_frame(cir: CIR, twin: TwinModel) -> Frame:
    """Finished size, drawn to scale against a known reference object."""
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "Finished size", int(size * 0.10), size)

    if twin.width_cm and twin.height_cm:
        # Draw the piece against a 180cm human silhouette bar, so scale is felt not read.
        ref_cm = 180.0
        area_h = int(size * 0.46)
        px_per_cm = area_h / ref_cm
        top = y + int(size * 0.04)
        left = _safe(size)
        w_px = int(twin.width_cm * px_per_cm)
        h_px = int(twin.height_cm * px_per_cm)
        d.rectangle([left, top, left + w_px, top + h_px], fill=PINE, outline=PINE)
        d.text((left + w_px // 2, top + h_px + 18),
               f"{twin.width_cm:.0f} × {twin.height_cm:.0f} cm",
               font=_font(int(size * 0.030)), fill=INK, anchor="ma")
        ref_x = left + w_px + int(size * 0.10)
        d.rectangle([ref_x, top, ref_x + int(size * 0.035), top + area_h], outline=LINE,
                    width=4)
        d.text((ref_x + int(size * 0.018), top + area_h + 18), "180 cm",
               font=_font(int(size * 0.026)), fill=MUTED, anchor="ma")
        _rows(d, [("Worked at", "the gauge in the pattern — your gauge changes the size "
                                "in the same proportion")],
              top + area_h + int(size * 0.09), size)
    elif twin.circumference_cm:
        # A closed shaped piece has a circumference that is arithmetic and a height that is
        # not. Saying so is better than drawing a rectangle nobody measured.
        _rows(d, [("Around at the widest round", f"{twin.circumference_cm:.0f} cm"),
                  ("Finished height", "measured from a physical sample, not computed: "
                                     "stuffing and tension set the final shape")],
              y + int(size * 0.06), size)
    claims = Claims(finished_width_cm=twin.width_cm, finished_height_cm=twin.height_cm)
    return Frame(position=3, role="size", asset_class=AssetClass.INFOGRAPHIC,
                 caption="finished size to scale", image=img, claims=claims)


def _materials_frame(cir: CIR, twin: TwinModel, difficulty: str) -> Frame:
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "What it takes", int(size * 0.10), size)
    tol = int(twin.yardage_tolerance * 100)
    yarn = "; ".join(
        f"{name} about {m * (1 - twin.yardage_tolerance):.0f}–"
        f"{m * (1 + twin.yardage_tolerance):.0f} m"
        for name, m in sorted(twin.yarn_metres_by_color.items())) or "see the pattern"
    pairs = [
        ("Difficulty", difficulty),
        ("Stitches used", ", ".join(sorted(twin.stitch_types_used))),
        ("Yarn", f"{yarn} (estimate, ±{tol}%, not a measurement)"),
    ]
    if cir.gauge:
        pairs.insert(1, ("Hook", f"{cir.gauge.hook_mm:g} mm"))
        pairs.append(("Gauge", f"{cir.gauge.stitches_per_10cm} sts × "
                               f"{cir.gauge.rows_per_10cm} rows = 10 cm"))
    y = _rows(d, pairs, y, size)

    m = _safe(size)
    for i, (name, hexv) in enumerate(sorted(cir.colors.items())):
        x = m + i * int(size * 0.13)
        d.rectangle([x, y, x + int(size * 0.10), y + int(size * 0.10)],
                    fill=_hex_to_rgb(hexv), outline=LINE, width=3)
        d.text((x, y + int(size * 0.11)), name, font=_font(int(size * 0.024)), fill=MUTED)
    return Frame(position=4, role="materials", asset_class=AssetClass.INFOGRAPHIC,
                 caption="materials and difficulty", image=img,
                 depicts_colors=sorted(c for c in twin.colors_used if c),
                 claims=Claims(difficulty=difficulty,
                               materials=[mat.name for mat in cir.materials],
                               colors=sorted(cir.colors)))


def _pattern_preview(cir: CIR, twin: TwinModel, pattern_text: str) -> Frame:
    """A genuine excerpt. A preview that shows nothing real is a preview of nothing."""
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "A look inside", int(size * 0.10), size)
    body = _font(int(size * 0.024))
    m = _safe(size)
    lines = [ln for ln in pattern_text.split("\n") if ln.strip()][:14]
    for line in lines:
        for wrapped in _wrap(d, line, body, size - 2 * m):
            d.text((m, y), wrapped, font=body, fill=INK)
            y += int(size * 0.031)
            if y > size * 0.86:
                break
        if y > size * 0.86:
            break
    d.text((m, int(size * 0.92)), "Actual pattern text from this release",
           font=_font(int(size * 0.024)), fill=MUTED)
    return Frame(position=5, role="pattern_preview", asset_class=AssetClass.PATTERN_PREVIEW,
                 caption="real excerpt from the released pattern", image=img,
                 depicts_stitches=sorted(twin.stitch_types_used))


def _chart_frame(cir: CIR, twin: TwinModel) -> Frame:
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "The chart", int(size * 0.10), size)
    if is_round(cir, twin):
        chart = render_round_chart(
            cir, twin, ChartSpec(cell_px=30, margin_px=40, max_width_px=size),
            caption="every round, from the centre out")
        caption = "the round chart"
    else:
        grid, colour_grid = twin.chart_grid(), twin.color_grid()
        cols, rows = detect_repeat(grid, colour_grid)
        grids = crop_grids(grid, colour_grid, cols, rows)
        chart = render_chart(cir, twin,
                             ChartSpec(cell_px=48, margin_px=40, max_width_px=size),
                             grids=grids,
                             caption=f"one repeat · {cols} sts × {rows} rows")
        caption = "one chart repeat"
    box = int(size * 0.74)
    scale = min(box / chart.width, (size * 0.62) / chart.height)
    chart = chart.resize((int(chart.width * scale), int(chart.height * scale)),
                         Image.LANCZOS)
    img.paste(chart, ((size - chart.width) // 2, y))
    return Frame(position=6, role="chart", asset_class=AssetClass.DIGITAL_TWIN_RENDER,
                 caption=caption, image=img,
                 depicts_stitches=sorted(twin.stitch_types_used),
                 depicts_colors=sorted(c for c in twin.colors_used if c))


def _collection_frame(cir: CIR, siblings: list[str]) -> Frame | None:
    if not siblings:
        return None
    size = CANVAS
    img, d = _canvas(size)
    y = _title_block(d, "Part of a collection", int(size * 0.10), size)
    _rows(d, [("Also in this collection", ", ".join(siblings)),
              ("Bundle", "The collection is also sold together, at a real saving against "
                         "buying each pattern separately")], y, size)
    return Frame(position=7, role="collection", asset_class=AssetClass.INFOGRAPHIC,
                 caption="collection cross-sell", image=img)


# ---- the plan --------------------------------------------------------------


def build_frames(cir: CIR, twin: TwinModel, *, pattern_text: str,
                 difficulty: str, pages: int | None = None,
                 siblings: list[str] | None = None) -> list[Frame]:
    """The ordered argument a listing makes, rendered.

    Order is the decision. The hero wins the click; frames two to four remove the reasons a
    buyer hesitates -- what am I getting, how big is it, what will it cost me in yarn and
    hours; frames five and six prove the thing is real; frame seven sells the next one.
    """
    frames = [
        _hero(cir, twin),
        _whats_included(cir, twin, pages, collapses_rows(cir)),
        _size_frame(cir, twin),
        _materials_frame(cir, twin, difficulty),
        _pattern_preview(cir, twin, pattern_text),
        _chart_frame(cir, twin),
    ]
    extra = _collection_frame(cir, siblings or [])
    if extra:
        frames.append(extra)
    return frames


def check_frame_plan(frames: list[Frame]) -> list[str]:
    """Structural rules a listing's imagery must satisfy before Asset Truth even runs."""
    problems: list[str] = []
    if not frames:
        return ["LISTING_NO_IMAGES: a listing with no imagery cannot be published"]
    heroes = [f for f in frames if f.is_hero]
    if len(heroes) != 1:
        problems.append(f"LISTING_HERO_COUNT: expected exactly one hero, got {len(heroes)}")
    elif heroes[0].asset_class is AssetClass.AI_LIFESTYLE_CONCEPT:
        problems.append(
            "LISTING_HERO_IS_A_CONCEPT: an AI lifestyle concept may not be the hero. A "
            "picture of a thing nobody has made is not evidence the thing exists.")
    positions = [f.position for f in frames]
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        problems.append(f"LISTING_FRAME_ORDER: positions are not a clean sequence: {positions}")
    if len(frames) > 10:
        problems.append(f"LISTING_TOO_MANY_IMAGES: {len(frames)} exceeds Etsy's 10 slots")
    roles = {f.role for f in frames}
    for required in ("hero", "whats_included", "size", "materials"):
        if required not in roles:
            problems.append(f"LISTING_MISSING_FRAME: no {required!r} frame; section 7 "
                            f"requires the listing to answer this before a buyer asks")
    for f in frames:
        if f.image is None:
            problems.append(f"LISTING_FRAME_EMPTY: frame {f.position} ({f.role}) has no image")
            continue
        if f.image.width != f.image.height:
            problems.append(
                f"LISTING_FRAME_NOT_SQUARE: frame {f.position} is "
                f"{f.image.width}x{f.image.height}; Etsy's grid crops to square")
        if f.image.width < 1000:
            problems.append(f"LISTING_FRAME_LOW_RES: frame {f.position} is "
                            f"{f.image.width}px on the short edge")
    return problems
