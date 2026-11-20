"""The schematic: every piece's outline with its measurements, and where the pieces join.

Drawn from `cir.assembly.assemble` and nothing else -- the same footprints and joins the
release chain has already checked -- so a number on this page is a number the certificate
covers. A schematic drawn by hand, or by a model asked to draw a sweater, is a second source
of truth about the garment's size, and a second source is how a pattern ends up telling the
maker one chest measurement in the table and another in the picture.

Every dimension printed is `Footprint.across_cm` / `Footprint.up_cm` formatted to one
decimal place, and `Schematic.labels` holds exactly the strings drawn, so a test can hold the
picture to the model rather than trusting it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from ..cir import assembly as _assembly
from .charts import _font

WIDTH_PX = 1600
MARGIN_PX = 60
GAP_PX = 70
INK = (26, 43, 60)
MUTED = (110, 110, 110)
FILL = (244, 238, 224)
JOIN = (164, 60, 40)


def cm_label(value: float) -> str:
    return f"{value:.1f} cm"


@dataclass
class Schematic:
    image: Image.Image
    # piece -> (across label, up label), exactly as drawn
    labels: dict[str, tuple[str, str]] = field(default_factory=dict)
    # (piece_a.edge_a, piece_b.edge_b, length label) for every join between two pieces
    arrows: list[tuple[str, str, str]] = field(default_factory=list)
    # self-seams, listed under the drawing rather than drawn as an arrow to nowhere
    closures: list[str] = field(default_factory=list)


def render_schematic(cir, geo) -> Schematic:
    """Outline every footprint to scale, label it in cm, and draw every join as an arrow."""
    pieces = [geo.footprints[c.name] for c in cir.components if c.name in geo.footprints]
    if not pieces:
        raise ValueError(f"{cir.slug}: no measured pieces to draw")
    usable = WIDTH_PX - 2 * MARGIN_PX - GAP_PX * (len(pieces) - 1)
    scale = usable / sum(max(p.across_cm, 1.0) for p in pieces)
    tallest = max(p.up_cm for p in pieces) * scale
    # Keep very tall pieces on the page: scale down uniformly, never per piece.
    if tallest > 900:
        scale *= 900 / tallest
        tallest = 900
    join_rows = sum(1 for j in geo.joins if j.piece_a != j.piece_b)
    closures = [j for j in geo.joins if j.piece_a == j.piece_b]
    height = int(MARGIN_PX * 2 + 60 + tallest + 80 + 34 * (join_rows + len(closures)) + 40)
    img = Image.new("RGB", (WIDTH_PX, height), "white")
    draw = ImageDraw.Draw(img)
    title_font, font, small = _font(30), _font(22), _font(18)
    draw.text((MARGIN_PX, MARGIN_PX - 40), f"Schematic: {cir.title}", fill=INK, font=title_font)

    out = Schematic(image=img)
    boxes: dict[str, tuple[float, float, float, float]] = {}
    x = MARGIN_PX
    top = MARGIN_PX + 60
    for p in pieces:
        w, h = max(p.across_cm, 1.0) * scale, p.up_cm * scale
        y0 = top + (tallest - h)
        draw.rectangle([x, y0, x + w, y0 + h], outline=INK, fill=FILL, width=3)
        name = p.piece.replace("_", " ") + (f" (make {p.copies})" if p.copies > 1 else "")
        draw.text((x, y0 - 30), name, fill=INK, font=font)
        across, up = cm_label(p.across_cm), cm_label(p.up_cm)
        draw.text((x + 4, y0 + h + 8), across, fill=INK, font=small)
        draw.text((x + w - 4 - draw.textlength(up, font=small), y0 + h / 2 - 9), up,
                  fill=INK, font=small)
        for span in p.openings:
            draw.text((x + 4, y0 + h / 2 + 14), f"opening {cm_label(span)}", fill=MUTED,
                      font=small)
        out.labels[p.piece] = (across, up)
        boxes[p.piece] = (x, y0, w, h)
        x += w + GAP_PX

    y = top + tallest + 70
    for j in geo.joins:
        a = f"{j.piece_a}.{j.edge_a or '?'}"
        b = f"{j.piece_b}.{j.edge_b or '?'}"
        if j.piece_a == j.piece_b:
            continue
        length = cm_label(j.length_b_cm) if j.length_b_cm is not None else "length not stated"
        out.arrows.append((a, b, length))
        if j.piece_a in boxes and j.piece_b in boxes:
            ax, ay, aw, ah = boxes[j.piece_a]
            bx, by, bw, bh = boxes[j.piece_b]
            start = _edge_point((ax, ay, aw, ah), j.edge_a)
            end = _edge_point((bx, by, bw, bh), j.edge_b)
            draw.line([start, end], fill=JOIN, width=3)
            _arrowhead(draw, start, end)
        draw.text((MARGIN_PX, y), f"join {a} to {b}: {length} ({j.verdict})", fill=JOIN,
                  font=small)
        y += 34
    for j in closures:
        text = f"close {j.piece_a}: {j.edge_a or '?'} edge to {j.edge_b or '?'} edge"
        out.closures.append(text)
        draw.text((MARGIN_PX, y), text, fill=MUTED, font=small)
        y += 34
    return out


def _edge_point(box, edge):
    """The midpoint of the named edge of a drawn piece; its centre for an opening."""
    x, y, w, h = box
    return {"left": (x, y + h / 2), "right": (x + w, y + h / 2), "top": (x + w / 2, y),
            "bottom": (x + w / 2, y + h), "fold": (x + w / 2, y)}.get(
                edge, (x + w / 2, y + h / 2))


def _arrowhead(draw, start, end, size: float = 14.0) -> None:
    import math

    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left = (end[0] - size * math.cos(angle - 0.4), end[1] - size * math.sin(angle - 0.4))
    right = (end[0] - size * math.cos(angle + 0.4), end[1] - size * math.sin(angle + 0.4))
    draw.polygon([end, left, right], fill=JOIN)


def schematic_for(cir, result) -> Schematic | None:
    """The schematic for a compiled multi-piece design, or None where there is nothing to join.

    A one-piece product's outline is already its finished size on the cover; a schematic is
    for designs whose pieces have to meet.
    """
    if not result.ok or len(cir.components) < 2 or not cir.assembly:
        return None
    from ..cir.twin import build_twin

    twins = {c.name: build_twin(cir, result, component=c.name) for c in cir.components}
    geo = _assembly.assemble(cir, twins)
    if not geo.footprints:
        return None
    return render_schematic(cir, geo)
