"""ENG-GARMENT: the garment schematic, drawn from each size's compiled rows and twin.

Never image-model art. `measures(cir)` reads every key measurement of one built size from its
compiler result and twin (half chest, length, armhole depth, neck width, sleeve length, upper
arm, cuff, band depth). `primitives(release)` lays the pieces out to scale at the middle size
and labels every dimension with every size, smallest first, the others in parentheses. The one
primitive list is rendered twice -- `to_svg` (the schematic as SVG, stored with the document)
and `draw` (the same lines on the PDF page) -- so the picture and the SVG cannot disagree.
"""
from __future__ import annotations

from ..products import garment_families as GF

NAMES = {"half_chest": "Half chest, finished",
         "length": "Length, finished", "armhole": "Armhole depth", "neck": "Neck opening",
         "sleeve": "Sleeve length", "upper_arm": "Upper arm, finished", "cuff": "Cuff width",
         "band": "Band depth (included in the measurements above)"}
STROKE = "#2F3B2F"
FILL = "#F4EFE4"
DIM = "#8A6F5A"


def measures(cir) -> dict[str, float]:
    """Every dimension the schematic labels, for one built size, in cm."""
    from ..cir.compiler import compile_cir
    from ..cir.twin import build_twin, row_width_cm

    r = compile_cir(cir)
    if not r.ok:
        raise ValueError(f"{cir.slug} does not compile")
    built = GF.built_measures(cir)
    facts = GF.facts_of(cir)
    kind = GF.construction_of(cir)
    gauge = cir.gauge
    out = {"half_chest": round(built["chest"] / 2.0, 1), "length": round(built["length"], 1),
           "armhole": round(facts.armhole_cm, 1), "neck": round(facts.neck_cm, 1)}
    if facts.band_cm:
        out["band"] = round(facts.band_cm, 1)
    if kind in ("raglan", "drop_shoulder"):
        name = "sleeve_left" if kind == "raglan" else "sleeve"
        rows = [x for x in r.rows if x.component == name]
        widths = [row_width_cm(x, gauge)[0] for x in rows]
        t = build_twin(cir, r, component=name)
        out.update(upper_arm=round(max(widths), 1), cuff=round(widths[-1] if kind == "raglan"
                                                              else widths[0], 1),
                   sleeve=round(t.height_cm, 1))
    elif kind == "one_piece":
        body = next(c for c in cir.components if c.name == "body")
        ext = next(s for s in facts.pieces["body"] if s.kind == "chain_on").get("extra")
        out.update(upper_arm=round(built["upper_arm"], 1),
                   sleeve=round(ext * 10.0 / gauge.stitches_per_10cm, 1))
        del body
    return out


def _fmt(values: list[float]) -> str:
    xs = [f"{v:g}" for v in values]
    return xs[0] if len(set(xs)) == 1 else f"{xs[0]} ({', '.join(xs[1:])})"


def primitives(design, cirs: dict) -> dict:
    """{"width", "height", "items": [...]} in schematic units (cm at the middle size)."""
    sizes = list(cirs)
    ms = [measures(cirs[s]) for s in sizes]
    mid = ms[len(ms) // 2]
    kind = GF.construction_of(cirs[sizes[0]])

    def lab(key):
        return f"{_fmt([m[key] for m in ms])} cm"

    items: list[dict] = []
    W, L = mid["half_chest"], mid["length"]
    gap = 8.0
    x0, y0 = 4.0, 6.0

    def rect(x, y, w, h, name):
        items.append({"kind": "poly", "name": name,
                      "points": [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]})

    legend: list[tuple[str, str, str]] = []

    def dim(a, b, key, side):
        letter = "ABCDEFGH"[len(legend)]
        name = NAMES[key]
        if key == "half_chest" and kind == "raglan":
            name += " (the back; the two fronts and one band together are the same)"
        legend.append((letter, name, lab(key)))
        items.append({"kind": "dim", "from": a, "to": b, "label": letter, "side": side,
                      "key": key})

    def text(at, s):
        items.append({"kind": "text", "at": at, "label": s})

    if kind == "one_piece":
        S = mid["sleeve"]
        A = mid["upper_arm"] / 2.0
        top = y0
        pts = [(x0, top), (x0 + S, top), (x0 + S + W, top), (x0 + 2 * S + W, top),
               (x0 + 2 * S + W, top + A), (x0 + S + W, top + A), (x0 + S + W, top + L),
               (x0 + S, top + L), (x0 + S, top + A), (x0, top + A)]
        items.append({"kind": "poly", "name": "body (front shown; the back is the same)",
                      "points": pts})
        N = mid["neck"]
        nx = x0 + S + (W - N) / 2.0
        items.append({"kind": "line", "from": (nx, top), "to": (nx + N, top), "heavy": True})
        dim((x0 + S, top + L), (x0 + S + W, top + L), "half_chest", "below")
        dim((x0 + S + W, top + A), (x0 + S + W, top + L), "length", "right")
        dim((x0, top), (x0 + S, top), "sleeve", "above")
        dim((x0, top), (x0, top + A), "armhole", "left")
        dim((nx, top), (nx + N, top), "neck", "above")
        width, height = 2 * S + W + 2 * x0, L + 2 * y0 + 4
    elif kind == "side_to_side":
        rect(x0, y0, W, L, "back")
        rect(x0 + W + gap, y0, W, L, "front")
        N = mid["neck"]
        A = mid["armhole"]
        for bx in (x0, x0 + W + gap):
            nx = bx + (W - N) / 2.0
            items.append({"kind": "line", "from": (nx, y0), "to": (nx + N, y0), "heavy": True})
            items.append({"kind": "line", "from": (bx, y0 + A), "to": (bx + 1.2, y0 + A)})
            items.append({"kind": "line", "from": (bx + W - 1.2, y0 + A), "to": (bx + W, y0 + A)})
        dim((x0, y0 + L), (x0 + W, y0 + L), "half_chest", "below")
        dim((x0 + 2 * W + gap, y0), (x0 + 2 * W + gap, y0 + L), "length", "right")
        dim((x0, y0), (x0, y0 + A), "armhole", "left")
        nx = x0 + (W - N) / 2.0
        dim((nx, y0), (nx + N, y0), "neck", "above")
        text((x0 + W / 2.0, y0 + L / 2.0), "back")
        text((x0 + W + gap + W / 2.0, y0 + L / 2.0), "front")
        text((x0 + W + gap + W / 2.0, y0 + L / 2.0 + 3), "rows run up and down")
        width, height = 2 * W + gap + 2 * x0 + 6, L + 2 * y0 + 4
    else:
        rect(x0, y0, W, L, "body")
        A = mid["armhole"]
        items.append({"kind": "line", "from": (x0 + W - 1.2, y0 + A), "to": (x0 + W, y0 + A)})
        if kind == "drop_shoulder":
            N = mid["neck"]
            nx = x0 + (W - N) / 2.0
            items.append({"kind": "line", "from": (nx, y0), "to": (nx + N, y0), "heavy": True})
            dim((nx, y0), (nx + N, y0), "neck", "above")
        dim((x0, y0 + L), (x0 + W, y0 + L), "half_chest", "below")
        dim((x0, y0), (x0, y0 + L), "length", "left")
        dim((x0 + W, y0), (x0 + W, y0 + A), "armhole", "right")
        text((x0 + W / 2.0, y0 + L / 2.0), "back" if kind == "raglan" else "body")
        U, C, Ls = mid["upper_arm"], mid["cuff"], mid["sleeve"]
        sx = x0 + W + gap + 4
        top_w, bot_w = U, C
        pts = [(sx, y0), (sx + top_w, y0), (sx + (top_w + bot_w) / 2.0, y0 + Ls),
               (sx + (top_w - bot_w) / 2.0, y0 + Ls)]
        items.append({"kind": "poly", "name": "sleeve", "points": pts})
        dim((sx, y0), (sx + top_w, y0), "upper_arm", "above")
        dim((sx + (top_w - bot_w) / 2.0, y0 + Ls), (sx + (top_w + bot_w) / 2.0, y0 + Ls),
            "cuff", "below")
        dim((sx + top_w, y0), (sx + top_w, y0 + Ls), "sleeve", "right")
        text((sx + top_w / 2.0, y0 + Ls / 2.0), "sleeve")
        width, height = sx + top_w + 14, max(L, Ls) + 2 * y0 + 4
    if "band" in mid:
        legend.append(("", NAMES["band"], lab("band")))
    return {"width": width, "height": height, "items": items, "sizes": sizes,
            "legend": legend,
            "measures": {s: m for s, m in zip(sizes, ms)}, "kind": kind}


def _dim_label_pos(it):
    (ax, ay), (bx, by) = it["from"], it["to"]
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    off = {"above": (0, -1.6), "below": (0, 2.6), "left": (-1.2, 0), "right": (1.2, 0)}[
        it["side"]]
    return mx + off[0], my + off[1]


def to_svg(p: dict, *, px_per_cm: float = 6.0) -> str:
    s = px_per_cm
    W, H = p["width"] * s, p["height"] * s
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.1f} {H:.1f}" font-family="Work Sans, sans-serif" '
           f'font-size="11">',
           f'<title>Schematic: every measurement for every size, from the pattern</title>']
    for it in p["items"]:
        if it["kind"] == "poly":
            pts = " ".join(f"{x * s:.1f},{y * s:.1f}" for x, y in it["points"])
            out.append(f'<polygon points="{pts}" fill="{FILL}" stroke="{STROKE}" '
                       f'stroke-width="1.5"><title>{it["name"]}</title></polygon>')
        elif it["kind"] == "line":
            (ax, ay), (bx, by) = it["from"], it["to"]
            out.append(f'<line x1="{ax * s:.1f}" y1="{ay * s:.1f}" x2="{bx * s:.1f}" '
                       f'y2="{by * s:.1f}" stroke="{STROKE}" stroke-width='
                       f'"{3 if it.get("heavy") else 1.2}"/>')
        elif it["kind"] == "dim":
            (ax, ay), (bx, by) = it["from"], it["to"]
            lx, ly = _dim_label_pos(it)
            anchor = {"left": "end", "right": "start"}.get(it["side"], "middle")
            out.append(f'<line x1="{ax * s:.1f}" y1="{ay * s:.1f}" x2="{bx * s:.1f}" '
                       f'y2="{by * s:.1f}" stroke="{DIM}" stroke-width="0.8" '
                       f'stroke-dasharray="3 2"/>')
            out.append(f'<text x="{lx * s:.1f}" y="{ly * s:.1f}" fill="{DIM}" '
                       f'text-anchor="{anchor}" data-key="{it["key"]}">{it["label"]}</text>')
        elif it["kind"] == "text":
            x, y = it["at"]
            out.append(f'<text x="{x * s:.1f}" y="{y * s:.1f}" fill="{STROKE}" '
                       f'text-anchor="middle">{it["label"]}</text>')
    y = H + 16
    for letter, name, label in p.get("legend", []):
        out.append(f'<text x="8" y="{y:.0f}" fill="{STROKE}">{letter + "  " if letter else ""}'
                   f'{name}: {label}</text>')
        y += 15
    out[0] = out[0].replace(f'height="{H:.0f}"', f'height="{y:.0f}"').replace(
        f'viewBox="0 0 {W:.1f} {H:.1f}"', f'viewBox="0 0 {W:.1f} {y:.1f}"')
    out.append("</svg>")
    return "\n".join(out)


def draw(doc, p: dict, *, x: float, top: float, width: float, height: float,
         font: str, size: float) -> list[str]:
    """Draw the same primitives on a reportlab canvas; returns every label drawn."""
    from reportlab.lib import colors

    c = doc.c
    s = min(width / p["width"], height / p["height"])

    def X(v):
        return x + v * s

    def Y(v):
        return top - v * s

    labels = []
    for it in p["items"]:
        if it["kind"] == "poly":
            c.setStrokeColor(colors.HexColor(STROKE))
            c.setFillColor(colors.HexColor(FILL))
            c.setLineWidth(1.2)
            path = c.beginPath()
            (px, py), *rest = it["points"]
            path.moveTo(X(px), Y(py))
            for qx, qy in rest:
                path.lineTo(X(qx), Y(qy))
            path.close()
            c.drawPath(path, fill=1, stroke=1)
        elif it["kind"] == "line":
            (ax, ay), (bx, by) = it["from"], it["to"]
            c.setStrokeColor(colors.HexColor(STROKE))
            c.setLineWidth(2.4 if it.get("heavy") else 1.0)
            c.line(X(ax), Y(ay), X(bx), Y(by))
        elif it["kind"] == "dim":
            (ax, ay), (bx, by) = it["from"], it["to"]
            c.setStrokeColor(colors.HexColor(DIM))
            c.setLineWidth(0.6)
            c.setDash(3, 2)
            c.line(X(ax), Y(ay), X(bx), Y(by))
            c.setDash()
            lx, ly = _dim_label_pos(it)
            align = {"left": "right", "right": "left"}.get(it["side"], "centre")
            doc.text(X(lx), Y(ly), it["label"], font, size, colors.HexColor(DIM), align=align)
            labels.append(it["label"])
        elif it["kind"] == "text":
            ax, ay = it["at"]
            doc.text(X(ax), Y(ay), it["label"], font, size, colors.HexColor(STROKE),
                     align="centre")
            labels.append(it["label"])
    return labels
