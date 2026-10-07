"""Disclosed renders of a multi-piece product, assembled only as its CIR says (W4-RENDER).

`visual.disclosed_render` draws one compiled piece. A stocking, a pencil roll or a tea cosy is
several pieces, and drawing them as one object is a claim about how they go together. This
module makes that claim only from structure the certified CIR states -- never from a note's
prose, a product photograph or a model's idea of what such things look like:

  * **planar joins** -- a `Seam` between two flat pieces that names opposite edges (one's
    bottom to the other's top, one's right to the other's left) puts the second piece beside
    the first, in the plane, at the rows the seam is placed across (`at_round`/`spans_rounds`
    on piece_b). `cir.assembly.assemble` has already checked both edge lengths agree;
    a CIR that does not assemble is refused, not drawn.
  * **layers** -- a join of two pieces' *same* edges (left to left) stacks them wrong sides
    together. The front view shows the front layer; the back layer is drawn only by proving
    it hides: every back piece must pair with a front piece of the same footprint through a
    mirrored copy of the same joins. A back layer that would show is refused.
  * **rings** -- a piece placed on both layers (a cuff sewn half to the front leg and half to
    the back) shows only the rows the front-layer joins place.
  * **folds** -- a flat piece whose two side edges are each self-seamed across rows 1..k is
    folded there: those rows lie over rows k+1..2k, upside down. Nothing else is a fold.
  * **resumed panels** -- a flat piece that `resumes` a `Hold` of a round piece continues
    that round's held stitches, so it hangs from them as part of the same wall.

A piece the structure cannot place is *not drawn*, and the manifest says which and why (a
loop whose only fold is in its note, a cord threaded through tabs). A product whose main
pieces cannot be placed is refused with the reason, so the pipeline names the CIR work that
would make it drawable. Every stitch drawn is a cell of that piece's twin, in its row colour,
at the gauge; the disclosure and the scale bar are the single-piece renderer's own.

Verification: assembled hero/scale frames carry `ASSEMBLED_RENDERER_VERSION`, which the
product-authority policy does not list as qualified, so their structural truth is UNKNOWN
(fail-closed) until the independent verifier measures assembled frames. The detail view is
the body piece through the single-piece renderer, and the verifier measures it against that
piece of the certified CIR.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from . import disclosed_render as D
from . import render_contract as K

ASSEMBLED_RENDERER_VERSION = "disclosed-render-assembled/1.0.0"

OPPOSITE = {("bottom", "top"), ("top", "bottom"), ("left", "right"), ("right", "left")}
SIDES = ("left", "right", "top", "bottom")

# Assembled forms that are worn over something with their opening down. The certified title
# (name truth is a release gate) is what says the object is one; the stitches cannot.
OPENING_DOWN_FORMS = ("cosy", "cozy")


@dataclass
class Placed:
    name: str
    comp: object
    twin: object
    x0: float                      # object cm, bottom-left of the piece's rectangle
    y0: float
    across: float
    up: float
    grain: str
    rows: tuple[int, int] | None = None      # rows shown (a ring shows its front rows)
    fold: int = 0                            # rows 1..fold folded up over the piece


@dataclass
class Plan:
    form: str                                # "planar" | "vessel_skirts"
    body: str
    placed: list[Placed] = field(default_factory=list)
    hidden: dict[str, str] = field(default_factory=dict)
    not_drawn: dict[str, str] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- planning

def _twins(cir, result) -> dict:
    from ..cir.twin import build_twin

    return {c.name: build_twin(cir, result, component=c.name) for c in cir.components}


def body_piece(cir, twins) -> str:
    """The piece that carries the object's body: the largest finished area (the convention
    `cir.assembly` uses for the silhouette), ties broken by CIR order."""
    best, area = cir.components[0].name, -1.0
    for c in cir.components:
        t = twins[c.name]
        a = (t.width_cm or 0.0) * (t.height_cm or 0.0)
        if a > area + 1e-9:
            best, area = c.name, a
    return best


def _row_start(placed: Placed, row: int) -> float:
    """Where row `row` begins along the edge its rows stack on, in the piece's own cm."""
    tops = placed.twin.row_top_cm
    start = tops.get(row - 1, 0.0)
    if placed.fold and row > placed.fold:
        start -= tops[placed.fold]
    return start


def _fold_of(cir, comp) -> int:
    """k when both side edges of this flat piece are self-seamed across rows 1..k and a seam
    says it is folded; else 0."""
    spans = {}
    folded = False
    for s in cir.assembly:
        if s.piece_a == s.piece_b == comp.name and s.edge_a == s.edge_b and \
                s.edge_a in ("left", "right") and s.at_round == 1:
            spans[s.edge_a] = s.spans_rounds
            folded |= "fold" in (s.note or "").lower()
    if comp.grain == "up" and folded and set(spans) == {"left", "right"} and \
            spans["left"] == spans["right"] and 2 * spans["left"] <= len(comp.rows):
        return spans["left"]
    return 0


def _place(p: Placed, edge_p: str, n: Placed, edge_n: str, *, n_is_b: bool, seam) -> None:
    """Put piece n against piece p's edge (opposite edges), aligned where the seam says."""
    # Offset along the shared edge: a placed seam runs across rows at_round.. of piece_b.
    along_p = along_n = 0.0
    if seam.at_round is not None:
        b = n if n_is_b else p
        rows_along = ("left", "right") if b.grain == "up" else ("top", "bottom")
        edge_b = edge_n if n_is_b else edge_p
        if edge_b in rows_along:
            off = _row_start(b, seam.at_round)
            if n_is_b:
                along_n = off
            else:
                along_p = off
    if edge_p in ("top", "bottom"):
        n.x0 = p.x0 + along_p - along_n
        n.y0 = p.y0 + p.up if edge_p == "top" else p.y0 - n.up
    else:
        n.y0 = p.y0 + along_p - along_n
        n.x0 = p.x0 + p.across if edge_p == "right" else p.x0 - n.across


def _folds_in_notes(cir, name: str) -> bool:
    """A join whose note folds the piece being sewn on (piece_a) with no structured fold."""
    return any(s.piece_a == name and "fold" in (s.note or "").lower()
               and not (s.piece_a == s.piece_b and s.edge_a == s.edge_b
                        and s.edge_a in ("left", "right"))
               for s in cir.assembly)


def _planar(cir, result, twins) -> Plan:
    from ..cir.assembly import assemble, footprint

    geo = assemble(cir, twins)
    if geo.verdict != "assembles":
        raise D.RenderRefused(f"{cir.slug}: the pieces do not assemble ({geo.verdict}: "
                              f"{geo.why}); an assembled drawing would be a guess")
    comps = {c.name: c for c in cir.components}
    for c in cir.components:
        if c.make != 1:
            raise D.RenderRefused(f"{cir.slug}: {c.name} is made {c.make} times; an assembled "
                                  f"front view of repeated loose pieces is not drawable here")
    feet = {n: footprint(c, twins[n], cir.gauge) for n, c in comps.items()}
    body = body_piece(cir, twins)
    cross = [s for s in cir.assembly if s.piece_a != s.piece_b]
    for s in cross:
        if not s.names_its_edges or s.edge_a not in SIDES or s.edge_b not in SIDES:
            raise D.RenderRefused(f"{cir.slug}: the join {s.piece_a}.{s.edge_a} to "
                                  f"{s.piece_b}.{s.edge_b} is not between two outer edges, "
                                  f"so it does not lie in the plane")
    stacks = [s for s in cross if s.edge_a == s.edge_b]
    mirrored = [s for s in cross if s.mirrored and (s.edge_a, s.edge_b) in OPPOSITE]
    planar = [s for s in cross if not s.mirrored and (s.edge_a, s.edge_b) in OPPOSITE]
    odd = [s for s in cross if s not in stacks and s not in mirrored and s not in planar]
    if odd:
        raise D.RenderRefused(f"{cir.slug}: join {odd[0].piece_a}.{odd[0].edge_a} to "
                              f"{odd[0].piece_b}.{odd[0].edge_b} is neither in the plane nor "
                              f"a wrong-sides-together stack")

    # The back layer: what the body is stacked against, and what mirrored joins hang off it.
    back: set[str] = set()
    for s in stacks:
        if body in (s.piece_a, s.piece_b):
            back.add(s.piece_b if s.piece_a == body else s.piece_a)
    grew = True
    while grew:
        grew = False
        for s in mirrored:
            for a, b in ((s.piece_a, s.piece_b), (s.piece_b, s.piece_a)):
                if a in back and b not in back:
                    back.add(b)
                    grew = True
    if body in back:
        raise D.RenderRefused(f"{cir.slug}: the body piece is stacked against itself")

    def new_placed(name: str) -> Placed:
        c = comps[name]
        p = Placed(name, c, twins[name], 0.0, 0.0, feet[name].across_cm, feet[name].up_cm,
                   c.grain, fold=_fold_of(cir, c))
        if p.fold:
            # Folded rows lie over the piece, so its height is the rows above the fold.
            tops = p.twin.row_top_cm
            p.up = tops[max(tops)] - tops[p.fold]
        return p

    plan = Plan(form="planar", body=body)
    order = [body]
    placed = {body: new_placed(body)}
    front_rows: dict[str, list[tuple[int, int]]] = {}
    back_rows: dict[str, list[tuple[int, int]]] = {}
    queue = [body]
    while queue:
        cur = queue.pop(0)
        for s in planar:
            if cur not in (s.piece_a, s.piece_b):
                continue
            other = s.piece_b if s.piece_a == cur else s.piece_a
            if other in back:
                continue
            if s.at_round is not None:
                front_rows.setdefault(s.piece_b, []).append(
                    (s.at_round, s.at_round + s.spans_rounds - 1))
            if other in placed:
                continue
            p_new = new_placed(other)
            cur_edge = s.edge_a if s.piece_a == cur else s.edge_b
            new_edge = s.edge_b if s.piece_a == cur else s.edge_a
            _place(placed[cur], cur_edge, p_new, new_edge, n_is_b=(other == s.piece_b), seam=s)
            placed[other] = p_new
            order.append(other)
            queue.append(other)
    for s in planar:
        if s.at_round is not None and (s.piece_a in back) and s.piece_b in placed:
            back_rows.setdefault(s.piece_b, []).append(
                (s.at_round, s.at_round + s.spans_rounds - 1))

    # A ring (placed on both layers) shows only the rows the front joins place.
    for name, spans in back_rows.items():
        if name not in front_rows:
            continue
        lo = min(a for a, _ in front_rows[name])
        hi = max(b for _, b in front_rows[name])
        if any(not (b < lo or a > hi) for a, b in spans):
            raise D.RenderRefused(f"{cir.slug}: {name}'s front and back rows overlap")
        p = placed[name]
        p.rows = (lo, hi)
        start, end = _row_start(p, lo), _row_start(p, hi + 1)
        if p.grain == "up":
            p.y0, p.up = p.y0 + start, end - start
        else:
            p.x0, p.across = p.x0 + start, end - start

    # Back layer: hidden only if it is the front's mirror image, piece for piece.
    def key(n):
        f = feet[n]
        return (round(f.across_cm, 2), round(f.up_cm, 2))

    pairs: dict[str, str] = {}
    for s in stacks:
        f, b = (s.piece_a, s.piece_b) if s.piece_b in back else (s.piece_b, s.piece_a)
        if f in placed and b in back:
            pairs[b] = f
    for s in mirrored:
        twin_seams = [t for t in planar if (t.edge_a, t.edge_b, t.at_round, t.spans_rounds)
                      == (s.edge_a, s.edge_b, s.at_round, s.spans_rounds)
                      and key(t.piece_a) == key(s.piece_a) and key(t.piece_b) == key(s.piece_b)
                      and t.piece_a in placed and t.piece_b in placed]
        if not twin_seams:
            raise D.RenderRefused(f"{cir.slug}: back-layer join {s.piece_a}-{s.piece_b} has no "
                                  f"front twin, so the back would show past the front")
        pairs.setdefault(s.piece_a, twin_seams[0].piece_a)
        pairs.setdefault(s.piece_b, twin_seams[0].piece_b)
    for b in sorted(back):
        f = pairs.get(b)
        if f is None or key(f) != key(b):
            raise D.RenderRefused(f"{cir.slug}: {b} is on the back layer and does not match a "
                                  f"front piece, so a front view would hide part of the object")
        plan.hidden[b] = f"behind {f}: the back layer mirrors the front"

    for name in order:
        if name != body and _folds_in_notes(cir, name):
            plan.not_drawn[name] = ("its seam note folds it, and the fold is not a structured "
                                    "join, so its finished shape is not derivable")
            continue
        plan.placed.append(placed[name])
    for name in comps:
        if name not in placed and name not in back:
            plan.not_drawn[name] = "no join places it against the drawn pieces"
    if len(plan.placed) < 2:
        raise D.RenderRefused(f"{cir.slug}: only {len(plan.placed)} piece can be placed from "
                              f"the CIR's joins; {plan.not_drawn}")
    return plan


def _vessel_skirts(cir, result, twins) -> Plan:
    rounds = [c for c in cir.components if c.construction != "flat_rows"]
    if len(rounds) != 1:
        raise D.RenderRefused(f"{cir.slug}: {len(rounds)} round pieces; only one round body "
                              f"with resumed panels is drawable assembled")
    bodyc = rounds[0]
    if bodyc.make != 1:
        raise D.RenderRefused(f"{cir.slug}: {bodyc.name} is made {bodyc.make} times")
    title = (cir.title or "").lower()
    if not any(w in title for w in OPENING_DOWN_FORMS):
        raise D.RenderRefused(f"{cir.slug}: a round body with resumed panels is drawn only where "
                              f"the certified title says which way its opening faces")
    plan = Plan(form="vessel_skirts", body=bodyc.name, extra={"opening": "down"})
    holds = {h.name: h for h in bodyc.holds}
    last = max(r.index for r in bodyc.rows)
    skirts = []
    for c in cir.components:
        if c is bodyc:
            continue
        h = holds.get(c.resumes or "")
        if h is None or c.construction != "flat_rows" or c.make != 1:
            plan.not_drawn[c.name] = "it resumes no held stitches of the body"
            continue
        if h.at_row != last:
            raise D.RenderRefused(f"{cir.slug}: {c.name} resumes stitches held at round "
                                  f"{h.at_row}, not the last round; not drawable here")
        skirts.append((c, h))
    if not skirts:
        raise D.RenderRefused(f"{cir.slug}: nothing hangs from the body's held stitches")
    plan.extra["skirts"] = [(c.name, h.from_stitch, h.count) for c, h in skirts]
    plan.placed = [Placed(bodyc.name, bodyc, twins[bodyc.name], 0, 0, 0, 0, "round")] + [
        Placed(c.name, c, twins[c.name], 0, 0, 0, 0, c.grain) for c, _ in skirts]
    return plan


def plan(cir, result=None) -> Plan:
    from ..cir.compiler import compile_cir

    result = result or compile_cir(cir)
    if not result.ok:
        raise D.RenderRefused(f"{cir.slug} does not compile; nothing true to render")
    twins = _twins(cir, result)
    if all(c.construction == "flat_rows" for c in cir.components):
        return _planar(cir, result, twins)
    if any(c.resumes for c in cir.components):
        return _vessel_skirts(cir, result, twins)
    raise D.RenderRefused(f"{cir.slug}: round pieces with no structural placement (no seam "
                          f"names their edges and no panel resumes their stitches)")


# --------------------------------------------------------------------------- drawing

def _cells_by_row(twin) -> dict[int, list]:
    return D._by_row(twin)


def _draw_up(d, cir, p: Placed, palette, *, px, ox, oy) -> dict:
    """A grain-up piece: rows bottom to top, stitches left to right (the flat renderer's
    `_draw_flat`), with a fold drawn over it when the CIR folds it."""
    rows = _cells_by_row(p.twin)
    tops = p.twin.row_top_cm
    lo, hi = p.rows or (min(rows), max(rows))
    if p.fold:
        lo = max(lo, p.fold + 1)
    left = ox + p.x0 * px
    bottom = oy - p.y0 * px
    out = D._draw_flat(d, cir, p.twin, palette, px=px, left=left, bottom=bottom,
                       rows_window=(lo, hi))
    if p.fold:
        out["fold"] = _draw_flap(d, cir, p, palette, rows, tops, px=px, left=left, bottom=bottom)
    return out


def _draw_flap(d, cir, p: Placed, palette, rows, tops, *, px, left, bottom) -> dict:
    """Rows 1..k folded up over rows k+1..2k: row j lies tops[k]-tops[j] .. tops[k]-tops[j-1]
    above the fold, upside down (its top towards the fold), seen from its wrong side."""
    w_cm = 10.0 / cir.gauge.stitches_per_10cm
    k = p.fold
    fold_h = tops[k]
    d.rectangle([left, bottom - fold_h * px, left + p.across * px - 1, bottom - 1], fill=K.GAP)
    base = cir.gauge.stitch_type
    drawn = []
    for j in range(1, k + 1):
        y_lo = bottom - (fold_h - tops[j]) * px          # nearer the fold: the stitch top
        y_hi = bottom - (fold_h - tops.get(j - 1, 0.0)) * px
        for c in rows[j]:
            x0 = left + c.fabric_position * w_cm * px
            x1 = x0 + w_cm * px
            rgb = palette[c.color]
            # Top corners first (`_tile`'s convention): the stitch top faces the fold.
            D._tile(d, [(x1, y_lo), (x0, y_lo), (x0, y_hi), (x1, y_hi)], rgb)
            if D._stitch_height_units(c.stitch, base) > 1.0 + 1e-9:
                post_w = max(2.0, (x1 - x0) * 0.36)
                mid = (x0 + x1) / 2
                inset = K.GAP_PX + max(1.0, (y_lo - y_hi) * 0.10)
                d.rectangle([round(mid - post_w / 2), round(y_hi + inset),
                             round(mid + post_w / 2) - 1, round(y_lo - inset) - 1],
                            fill=K.relief(rgb))
        drawn.append({"row": j, "count": len(rows[j]), "colour": rows[j][0].color})
    return {"rows": drawn, "fold_rows": k, "height_cm": round(fold_h, 3)}


def _draw_across(d, cir, p: Placed, palette, *, px, ox, oy) -> dict:
    """A side-to-side piece: row 1 (the foundation) at its left edge, rows running right,
    stitches stacked from the bottom edge up -- each stitch the gauge width tall."""
    w_cm = 10.0 / cir.gauge.stitches_per_10cm
    rows = _cells_by_row(p.twin)
    tops = p.twin.row_top_cm
    lo, hi = p.rows or (min(rows), max(rows))
    x_origin = ox + (p.x0 - _row_start(p, lo)) * px
    bottom = oy - p.y0 * px
    d.rectangle([ox + p.x0 * px, bottom - p.up * px, ox + (p.x0 + p.across) * px - 1,
                 bottom - 1], fill=K.GAP)
    drawn = []
    for r in range(lo, hi + 1):
        xa = x_origin + tops.get(r - 1, 0.0) * px
        xb = x_origin + tops[r] * px
        for c in rows[r]:
            y_lo = bottom - c.fabric_position * w_cm * px
            y_hi = y_lo - w_cm * px
            # The stitch top faces the next row (to the right).
            D._tile(d, [(xb, y_hi), (xb, y_lo), (xa, y_lo), (xa, y_hi)], palette[c.color])
        drawn.append({"row": r, "count": len(rows[r]), "colour": rows[r][0].color})
    return {"rows": drawn, "width_cm": round(p.across, 3), "height_cm": round(p.up, 3)}


def _extent(pl: Plan) -> tuple[float, float, float, float]:
    xs0 = min(p.x0 for p in pl.placed)
    ys0 = min(p.y0 for p in pl.placed)
    xs1 = max(p.x0 + p.across for p in pl.placed)
    ys1 = max(p.y0 + p.up for p in pl.placed)
    return xs0, ys0, xs1, ys1


def _planar_view(cir, pl: Plan, palette, view: str):
    img, d = D._canvas()
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    x0, y0, x1, y1 = _extent(pl)
    W, H = x1 - x0, y1 - y0
    margin = 70 if view == "scale" else 0
    px = min((zx1 - zx0 - margin) / W, (zy1 - zy0 - margin) / H)
    left = zx0 + margin + ((zx1 - zx0 - margin) - W * px) / 2
    bottom = zy1 - ((zy1 - zy0 - margin) - H * px) / 2 - margin
    if view == "hero":
        left = zx0 + ((zx1 - zx0) - W * px) / 2
        bottom = zy1 - ((zy1 - zy0) - H * px) / 2
    ox, oy = left - x0 * px, bottom + y0 * px
    pieces = []
    for p in pl.placed:
        if p.grain == "up":
            drawn = _draw_up(d, cir, p, palette, px=px, ox=ox, oy=oy)
        else:
            drawn = _draw_across(d, cir, p, palette, px=px, ox=ox, oy=oy)
        pieces.append({"piece": p.name, "grain": p.grain, "x0_cm": round(p.x0 - x0, 3),
                       "y0_cm": round(p.y0 - y0, 3), "across_cm": round(p.across, 3),
                       "up_cm": round(p.up, 3), "rows_shown": list(p.rows) if p.rows else None,
                       "fold_rows": p.fold, "drawn": drawn})
    extra = []
    if view == "scale":
        top = bottom - H * px
        D._dimension_line(d, (left, bottom + 40), (left + W * px, bottom + 40), ticks="v")
        D._dimension_line(d, (left - 40, top), (left - 40, bottom), ticks="h")
        extra = K.annotation_lines("scale", "assembled", {"width": W, "height": H})
    layout = {"pieces": pieces, "width_cm": round(W, 3), "height_cm": round(H, 3),
              "objects": 1, "projection": "front"}
    return img, d, px, layout, extra


def _vessel_view(cir, result, pl: Plan, palette, view: str):
    from ..cir.geometry import corners

    body = pl.placed[0]
    rows_all = [r for r in result.rows if r.component == body.name]
    sides = corners(rows_all)
    if sides is None:
        raise D.RenderRefused(f"{cir.slug}: {body.name}'s increases neither all stack nor all "
                              f"stagger, so its outline is not a named shape")
    shim = replace(cir, components=[body.comp] + [c for c in cir.components
                                                  if c is not body.comp])
    rings, rows, base, wall = D._rounds(shim, body.twin, sides)
    if not wall:
        raise D.RenderRefused(f"{cir.slug}: {body.name} has no wall to hang panels from")
    levels = D._wall_levels(shim, result, wall)
    Hb = levels[-1]
    R = (base or rings)[-1].radius_cm
    n = len(rows[wall[-1].index])
    skirts = []
    for (name, start, count), p in zip(pl.extra["skirts"], pl.placed[1:]):
        srows = _cells_by_row(p.twin)
        skirts.append((p, start, count, srows, p.twin.row_top_cm))
    Hs = max(max(t.values()) for _p, _s, _c, _r, t in skirts)
    # Face the first hold towards the viewer (a rotation of the whole object, not a claim).
    _p0, s0, c0, _r0, _t0 = skirts[0]
    t_mid = (s0 + c0 / 2) / n

    def angle(t):
        return 2 * math.pi * (t - t_mid) + 1.5 * math.pi

    alpha = math.radians(K.camera_deg(view) if view == "hero" else 0.0)
    ca, sa = math.cos(alpha), math.sin(alpha)
    img, d = D._canvas()
    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    zw, zh = zx1 - zx0, zy1 - zy0
    margin = 80 if view == "scale" else 0
    total = Hb + Hs
    height_cm = total * ca + 2 * R * sa
    px = min((zw - margin) / (2 * R), (zh - margin) / height_cm)
    cx = zx0 + margin / 2 + (zw - margin) / 2
    low = (zy0 + (zh - margin) / 2) + height_cm * px / 2      # front of the bottom edge
    ground = low - R * sa * px                                # screen y of Z=0, Y=0

    def proj(X, Y, Z):
        return cx + X * px, ground - (Z * ca + Y * sa) * px

    def arc(t0, t1, rho):
        steps = max(2, int(math.ceil((t1 - t0) * 96)))
        return [(rho * math.cos(angle(t0 + (t1 - t0) * k / steps)),
                 rho * math.sin(angle(t0 + (t1 - t0) * k / steps))) for k in range(steps + 1)]

    base_st = cir.gauge.stitch_type

    def quad(t0, t1, z0, z1, stitch):
        path = arc(t0, t1, R)
        bottom = [proj(x, y, z0) for x, y in path]
        top = [proj(x, y, z1) for x, y in path]
        if top[0][0] > top[-1][0]:
            top, bottom = list(reversed(top)), list(reversed(bottom))
        raised = D._stitch_height_units(stitch, base_st) > 1.0 + 1e-9
        return top + list(reversed(bottom)), ((top, bottom) if raised else None)

    def front(tm):
        return math.sin(angle(tm)) < -1e-9

    tiles = []
    # The body's wall rounds hang down from the crown at the top: round j's top edge is
    # Hs + Hb - levels[j-1], its bottom Hs + Hb - levels[j].
    for j, ring in enumerate(wall):
        cells = rows[ring.index]
        m = len(cells)
        z_hi = Hs + Hb - (levels[j - 1] if j else 0.0)
        z_lo = Hs + Hb - levels[j]
        for i, c in enumerate(cells):
            t0, t1 = i / m, (i + 1) / m
            if front((t0 + t1) / 2):
                tiles.append((*quad(t0, t1, z_lo, z_hi, c.stitch), palette[c.color]))
    drawn_skirts = []
    for p, start, count, srows, tops in skirts:
        k = 0
        for r in sorted(srows):
            cells = sorted(srows[r], key=lambda c: c.fabric_position)
            z_hi = Hs - tops.get(r - 1, 0.0)
            z_lo = Hs - tops[r]
            for c in cells:
                t0 = (start + c.fabric_position) / n
                t1 = (start + c.fabric_position + 1) / n
                if front((t0 + t1) / 2):
                    tiles.append((*quad(t0, t1, z_lo, z_hi, c.stitch), palette[c.color]))
                    k += 1
        drawn_skirts.append({"piece": p.name, "held_from": start, "held_count": count,
                             "rows": len(srows), "front_tiles": k})
    for pts, post, rgb in tiles:
        D._tile(d, pts, rgb)
        if post:
            D._post(d, *post, rgb)
    crown = []
    if sa > 1e-9:
        # The crown's outer face, seen from above, on top of the walls.
        previous = 0.0
        for ring in base:
            cells = rows[ring.index]
            m = len(cells)
            for i, c in enumerate(cells):
                t0, t1 = i / m, (i + 1) / m
                out = [proj(x, y, total) for x, y in arc(t0, t1, ring.radius_cm)]
                inn = [proj(x, y, total) for x, y in reversed(arc(t0, t1, previous))]
                D._tile(d, out + inn, palette[c.color], notch=False)
            crown.append({"round": ring.index, "count": m})
            previous = ring.radius_cm
    extra = []
    if view == "scale":
        top = low - total * px
        D._dimension_line(d, (cx - R * px, low + 40), (cx + R * px, low + 40), ticks="v")
        D._dimension_line(d, (cx - R * px - 40, top), (cx - R * px - 40, low), ticks="h")
        extra = K.annotation_lines("scale", "assembled", {"width": 2 * R, "height": total})
    layout = {"sides": sides, "objects": 1, "opening": "down", "alpha_deg": round(
        math.degrees(alpha), 3), "projection": "oblique" if sa else "elevation",
        "body_wall_rounds": len(wall), "crown_rounds": crown, "skirts": drawn_skirts,
        "width_cm": round(2 * R, 3), "height_cm": round(total, 3)}
    return img, d, px, layout, extra


# --------------------------------------------------------------------------- public API

def render(cir, view: str) -> D.RenderedFrame:
    """One disclosed frame of a multi-piece product (hero, scale or detail)."""
    import hashlib

    from ..cir.compiler import compile_cir

    if view not in ("hero", "scale", "detail"):
        raise D.RenderRefused(f"{cir.slug}: {view!r} is not drawn for an assembled product")
    if cir.gauge is None:
        raise D.RenderRefused(f"{cir.slug}: no gauge, so no physical size to draw at")
    result = compile_cir(cir)
    pl = plan(cir, result)
    palette = D._palette(cir)
    used = {c.color for p in pl.placed for c in p.twin.cells}
    missing = sorted(str(c) for c in used if c not in palette)
    if missing:
        raise D.RenderRefused(f"{cir.slug}: colours {missing} have no RGB value in cir.colors")
    if K.separation({k: v for k, v in palette.items() if k in used}) < K.MIN_SEPARATION:
        raise D.RenderRefused(f"{cir.slug}: palette too close to a contract colour to measure")
    body = next(p for p in pl.placed if p.name == pl.body)
    if view == "detail":
        # The body piece, stitch for stitch, through the single-piece renderer: the frame
        # the verifier measures against that piece of the certified CIR.
        shim = replace(cir, components=[body.comp] + [c for c in cir.components
                                                      if c is not body.comp])
        if body.comp.construction == "flat_rows":
            img, drawn = D._flat_view(shim, body.twin, palette, "detail")
            form = "flat"
        else:
            img, drawn = D._round_view(shim, result, body.twin, palette, "detail")
            form = "rounds"
        version = D.RENDERER_VERSION
        construction = body.comp.construction
    else:
        if pl.form == "planar":
            img, d, px, drawn, extra = _planar_view(cir, pl, palette, view)
        else:
            img, d, px, drawn, extra = _vessel_view(cir, result, pl, palette, view)
        drawn["px_per_cm"] = px
        drawn["scale_bar"] = D._scale_bar(d, px)
        drawn["caption"] = D._caption(d, extra)
        form = "assembled"
        version = ASSEMBLED_RENDERER_VERSION
        construction = cir.construction
    png = D._png(img)
    twin = body.twin
    manifest = {
        "kind": D.KIND, "renderer_version": version, "contract_version": K.CONTRACT_VERSION,
        "slug": cir.slug, "version": cir.version, "title": cir.title,
        "cir_fingerprint": cir.fingerprint,
        "represented_variant": {"key": cir.variant_key, "features": dict(cir.represented_variant)},
        "twin_digest": D.twin_digest(twin), "colour_map_digest": D.colour_map_digest(cir, twin),
        "view": view, "role": D.VIEWS[view]["role"], "job": D.VIEWS[view]["job"],
        "form": form, "construction": construction,
        "piece": pl.body if view == "detail" else None,
        "assembly": {"form": pl.form, "body": pl.body,
                     "drawn": [p.name for p in pl.placed],
                     "hidden": dict(pl.hidden), "not_drawn": dict(pl.not_drawn)},
        "stitch_counts": {p.name: sum(1 for _ in p.twin.cells) for p in pl.placed},
        "finished_dimensions_cm": (
            {"width": twin.width_cm, "height": twin.height_cm} if view == "detail" else
            {"width": drawn["width_cm"], "height": drawn["height_cm"]}),
        "pieces": sum(c.make for c in cir.components),
        "layout": drawn, "disclosure": K.DISCLOSURE,
        "image_sha256": hashlib.sha256(png).hexdigest(), "image_px": [K.CANVAS_PX, K.CANVAS_PX],
        "generated": False, "photograph": False, "model_in_path": False,
        "calibrated": all(p.twin.calibrated for p in pl.placed),
        "modelling_notes": _notes(pl, view),
    }
    return D.RenderedFrame(view=view, png=png, manifest=manifest)


def _notes(pl: Plan, view: str) -> list[str]:
    if view == "detail":
        return [f"the {pl.body} piece alone, stitch for stitch"]
    out = ["pieces placed only by the CIR's named-edge joins, folds and resumed holds"]
    if pl.hidden:
        out.append("the back layer mirrors the front and is hidden behind it")
    if pl.not_drawn:
        out.append("not drawn (placement not derivable from structure): "
                   + ", ".join(sorted(pl.not_drawn)))
    if pl.form == "vessel_skirts":
        out.append("panels resumed from held stitches continue the body's wall")
    if any(p.fold for p in pl.placed):
        out.append("folded rows are drawn over the rows they lie on, upside down")
    return out
