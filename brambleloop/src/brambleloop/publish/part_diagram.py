"""ENG-PLUSH: the part diagram -- every piece of a multi-piece pattern and where it joins.

A stuffed toy, a lovey or a cushion cover is several correct pieces plus the joins that make
them one object. The written assembly steps state each join; this draws them, from the same
numbers: each piece in rounds as a circle whose diameter is the twin's widest round, each
piece in rows as a rectangle of its computed width and height, all at ONE scale, with every
join drawn from the joined piece to the band of the round (or the edge) it is sewn to and
labelled with the round and stitch span the CIR states. Nothing is invented: a piece the
geometry cannot measure is drawn as a labelled box with no size, and the caption says it is
a diagram drawn from the pattern's stitch data, not a photograph.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

PAPER = (243, 238, 231)
INK = (52, 46, 42)
ROSE = (142, 90, 89)
FILL = (222, 210, 196)
W, H = 1400, 760
CAPTION = ("Parts and joins: a diagram drawn from this pattern's stitch counts and computed "
           "sizes, all pieces at one scale, not a photograph.")


def _font(size: int):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def pieces(cir, result) -> list[dict]:
    """What the diagram draws, as data (tested on its own): one entry per piece."""
    from ..cir import closed_forms
    from ..cir.twin import build_twin

    geo = {g["piece"]: g for g in closed_forms.part_geometry(cir, result)}
    out = []
    for comp in cir.components:
        g = geo.get(comp.name, {})
        entry = {"piece": comp.name, "make": comp.make, "construction": comp.construction,
                 "rounds": g.get("rounds"), "widest_sts": g.get("widest_sts"),
                 "stuff_at_round": comp.stuff_at_round, "closes": comp.closes}
        if comp.construction == "flat_rows":
            twin = build_twin(cir, result, component=comp.name)
            entry.update(width_cm=twin.width_cm, height_cm=twin.height_cm)
        else:
            entry.update(diameter_cm=g.get("diameter_cm"))
        out.append(entry)
    return out


def joins(cir) -> list[dict]:
    out = []
    for s in cir.assembly:
        if s.piece_a == s.piece_b:
            where = "its own edges"
        elif s.is_placed:
            last = s.at_round + s.spans_rounds - 1
            where = (f"Rnd {s.at_round}" if s.spans_rounds == 1 else f"Rnds {s.at_round}-{last}")
            if s.stitches_from_centre is not None:
                where += f", {2 * s.stitches_from_centre} sts"
            if s.mirrored:
                where += ", mirrored"
        else:
            where = f"{s.edge_a or '?'} to {s.edge_b or '?'} edge"
        out.append({"from": s.piece_a, "to": s.piece_b, "method": s.method, "where": where,
                    "stuffed_before_closing": bool(s.stuff_before_closing)})
    return out


def render(cir, result) -> bytes | None:
    """The diagram as PNG bytes, or None for a one-piece pattern with no join to draw."""
    ps = pieces(cir, result)
    if len(ps) < 2 and not cir.assembly:
        return None
    js = joins(cir)
    sizes = [max(p.get("diameter_cm") or 0, p.get("width_cm") or 0, p.get("height_cm") or 0)
             for p in ps]
    biggest = max(sizes) or 1.0
    slot = (W - 80) / len(ps)
    scale = min((slot - 40) / biggest, (H - 380) / biggest)
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    f_big, f_small = _font(30), _font(22)
    centres = {}
    for i, p in enumerate(ps):
        cx = 40 + slot * (i + 0.5)
        cy = 330
        if p.get("diameter_cm"):
            r = p["diameter_cm"] * scale / 2
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FILL, outline=INK, width=4)
            size = f"{p['diameter_cm']:.1f} cm across"
        elif p.get("width_cm") and p.get("height_cm"):
            w, h = p["width_cm"] * scale / 2, p["height_cm"] * scale / 2
            d.rectangle((cx - w, cy - h, cx + w, cy + h), fill=FILL, outline=INK, width=4)
            size = f"{p['width_cm']:.1f} x {p['height_cm']:.1f} cm"
        else:
            d.rectangle((cx - 60, cy - 40, cx + 60, cy + 40), outline=INK, width=3)
            size = "size from a sample"
        centres[p["piece"]] = (cx, cy)
        label = p["piece"] + (f" x{p['make']}" if p["make"] > 1 else "")
        d.text((cx, 545), label, fill=INK, font=f_big, anchor="mm")
        rows = f"{p['rounds']} {'rows' if p['construction'] == 'flat_rows' else 'rnds'}"
        d.text((cx, 585), f"{rows}, widest {p['widest_sts']} sts", fill=INK, font=f_small,
               anchor="mm")
        d.text((cx, 617), size, fill=INK, font=f_small, anchor="mm")
        extra = []
        if p.get("stuff_at_round") is not None:
            extra.append(f"stuff after Rnd {p['stuff_at_round']}")
        if p.get("closes"):
            extra.append("closes")
        if extra:
            d.text((cx, 649), ", ".join(extra), fill=ROSE, font=f_small, anchor="mm")
    for k, j in enumerate(js):
        if j["from"] not in centres or j["to"] not in centres or j["from"] == j["to"]:
            continue
        (x1, y1), (x2, y2) = centres[j["from"]], centres[j["to"]]
        lift = biggest * scale / 2 + 30 + 40 * k
        d.line((x1, y1 - 10, x1, y1 - lift, x2, y1 - lift, x2, y2 - 10), fill=ROSE, width=4)
        d.ellipse((x2 - 8, y2 - 18, x2 + 8, y2 - 2), fill=ROSE)
        d.text(((x1 + x2) / 2, y1 - lift - 22), f"{j['method']}: {j['where']}", fill=ROSE,
               font=f_small, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
