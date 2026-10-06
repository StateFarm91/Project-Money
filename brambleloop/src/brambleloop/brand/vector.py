"""A tiny deterministic vector engine for the identity system.

Why not hand-written SVG strings: a mark has to be *measured*, not only drawn. The owner's
directive asks whether the icon survives at 40 px, whether it stays distinct, whether it holds
in monochrome. Those are raster questions, and the repository has no SVG rasteriser (no
cairosvg, and a browser is too heavy for a unit test). So every mark is built from a short list
of primitives that this module can both *emit as SVG* and *rasterise with Pillow* from the same
geometry. The SVG is what ships; the raster is what the tests and the judge read. Both come
from one description, so the measurement is of the thing that ships.

Primitives
  Fill      closed path(s), even-odd rule (letterforms, leaves, petals)
  Stroke    open or closed path with round caps and joins (yarn, stems)
  Circle    filled disc (berries, yarn ball, drupelets)
  Knockout  removes coverage from everything drawn before it (the gap that makes a strand
            read as passing *over* something). Emitted as an SVG <mask>, so the mark stays
            transparent-ready -- never a fake gap painted in the background colour.

Colour is by *role* ("ink", "accent", "leaf"...), resolved against a palette at render time, so
the monochrome and reversed variants are the same geometry with a different role map.

Curves are flattened with a fixed number of segments, so the same mark gives the same bytes and
the same raster on every machine.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

Pt = tuple[float, float]

Q_STEPS = 10
C_STEPS = 16


def f(x: float) -> str:
    """Compact deterministic number formatting for SVG."""
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# ---- paths -----------------------------------------------------------------------------------


class Path:
    """Records M/L/Q/C/Z ops; yields an SVG `d` (curves kept) and flattened polygons (raster)."""

    def __init__(self) -> None:
        self.ops: list[tuple] = []

    # building
    def M(self, x: float, y: float) -> "Path":
        self.ops.append(("M", (x, y)))
        return self

    def L(self, x: float, y: float) -> "Path":
        self.ops.append(("L", (x, y)))
        return self

    def Q(self, x1: float, y1: float, x: float, y: float) -> "Path":
        self.ops.append(("Q", (x1, y1), (x, y)))
        return self

    def C(self, x1: float, y1: float, x2: float, y2: float, x: float, y: float) -> "Path":
        self.ops.append(("C", (x1, y1), (x2, y2), (x, y)))
        return self

    def Z(self) -> "Path":
        self.ops.append(("Z",))
        return self

    def extend(self, other: "Path") -> "Path":
        self.ops.extend(other.ops)
        return self

    # transforms
    def mapped(self, fn) -> "Path":
        out = Path()
        for op in self.ops:
            out.ops.append((op[0],) + tuple(fn(p) for p in op[1:]))
        return out

    def transformed(self, sx: float = 1.0, sy: float | None = None, tx: float = 0.0,
                    ty: float = 0.0, rot_deg: float = 0.0, origin: Pt = (0.0, 0.0)) -> "Path":
        sy = sx if sy is None else sy
        a = math.radians(rot_deg)
        ca, sa = math.cos(a), math.sin(a)
        ox, oy = origin

        def fn(p: Pt) -> Pt:
            x, y = (p[0] - ox) * sx, (p[1] - oy) * sy
            return (ox + x * ca - y * sa + tx, oy + x * sa + y * ca + ty)

        return self.mapped(fn)

    # output
    def d(self) -> str:
        parts: list[str] = []
        for op in self.ops:
            k = op[0]
            if k == "Z":
                parts.append("Z")
            else:
                parts.append(k + " ".join(f"{f(p[0])} {f(p[1])}" for p in op[1:]))
        return "".join(parts)

    def polylines(self) -> list[tuple[list[Pt], bool]]:
        """Flattened subpaths as (points, closed)."""
        out: list[tuple[list[Pt], bool]] = []
        cur: list[Pt] = []
        start: Pt | None = None
        for op in self.ops:
            k = op[0]
            if k == "M":
                if len(cur) > 1:
                    out.append((cur, False))
                cur = [op[1]]
                start = op[1]
            elif k == "L":
                cur.append(op[1])
            elif k == "Q":
                p0 = cur[-1]
                (x1, y1), (x, y) = op[1], op[2]
                for i in range(1, Q_STEPS + 1):
                    t = i / Q_STEPS
                    mt = 1 - t
                    cur.append((mt * mt * p0[0] + 2 * mt * t * x1 + t * t * x,
                                mt * mt * p0[1] + 2 * mt * t * y1 + t * t * y))
            elif k == "C":
                p0 = cur[-1]
                (x1, y1), (x2, y2), (x, y) = op[1], op[2], op[3]
                for i in range(1, C_STEPS + 1):
                    t = i / C_STEPS
                    mt = 1 - t
                    cur.append((mt ** 3 * p0[0] + 3 * mt * mt * t * x1 + 3 * mt * t * t * x2
                                + t ** 3 * x,
                                mt ** 3 * p0[1] + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2
                                + t ** 3 * y))
            elif k == "Z":
                if cur:
                    out.append((cur, True))
                cur = []
        if len(cur) > 1:
            out.append((cur, False))
        return out

    def bbox(self) -> tuple[float, float, float, float]:
        pts = [p for pl, _ in self.polylines() for p in pl]
        if not pts:
            return (0.0, 0.0, 0.0, 0.0)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


def cubic_through(points: Sequence[Pt], tension: float = 1.0) -> Path:
    """A smooth open curve through the given points (Catmull-Rom converted to cubics)."""
    p = Path().M(*points[0])
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        p.C(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    return p


def closed_through(points: Sequence[Pt], tension: float = 1.0) -> Path:
    """A smooth closed curve through the points."""
    n = len(points)
    p = Path().M(*points[0])
    for i in range(n):
        p0, p1 = points[(i - 1) % n], points[i]
        p2, p3 = points[(i + 1) % n], points[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        p.C(c1[0], c1[1], c2[0], c2[1], p2[0], p2[1])
    return p.Z()


def leaf_path(base: Pt, angle_deg: float, length: float, width: float,
              bend: float = 0.0) -> Path:
    """A pointed leaf from `base` along `angle_deg`: two cubic edges meeting at the tip."""
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    bx, by = base

    def at(t: float, o: float) -> Pt:
        o2 = o + bend * math.sin(math.pi * t) * length
        return (bx + ux * t * length + nx * o2, by + uy * t * length + ny * o2)

    tip = at(1.0, 0.0)
    p = Path().M(bx, by)
    c1, c2 = at(0.18, width * 1.05), at(0.62, width * 0.95)
    p.C(c1[0], c1[1], c2[0], c2[1], tip[0], tip[1])
    c3, c4 = at(0.62, -width * 0.95), at(0.18, -width * 1.05)
    p.C(c3[0], c3[1], c4[0], c4[1], bx, by)
    return p.Z()


def leaf_midrib(base: Pt, angle_deg: float, length: float, bend: float = 0.0,
                start: float = 0.12, end: float = 0.8) -> Path:
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    pts = []
    for i in range(6):
        t = start + (end - start) * i / 5
        o = bend * math.sin(math.pi * t) * length
        pts.append((base[0] + ux * t * length + nx * o, base[1] + uy * t * length + ny * o))
    return cubic_through(pts)


def circle_path(cx: float, cy: float, r: float) -> Path:
    k = 0.5522847498 * r
    return (Path().M(cx + r, cy)
            .C(cx + r, cy + k, cx + k, cy + r, cx, cy + r)
            .C(cx - k, cy + r, cx - r, cy + k, cx - r, cy)
            .C(cx - r, cy - k, cx - k, cy - r, cx, cy - r)
            .C(cx + k, cy - r, cx + r, cy - k, cx + r, cy).Z())


def ellipse_path(cx: float, cy: float, rx: float, ry: float, rot_deg: float = 0.0) -> Path:
    return circle_path(0, 0, 1).transformed(sx=rx, sy=ry).transformed(rot_deg=rot_deg).transformed(
        tx=cx, ty=cy)


# ---- elements --------------------------------------------------------------------------------


@dataclass
class Fill:
    path: Path
    role: str


@dataclass
class Stroke:
    path: Path
    width: float
    role: str


@dataclass
class Circle:
    cx: float
    cy: float
    r: float
    role: str


@dataclass
class Knockout:
    """Removes coverage, beneath it, of every element drawn so far."""
    shapes: list  # Fill | Stroke | Circle (their role is ignored)


@dataclass
class Mark:
    name: str
    width: float
    height: float
    elements: list = field(default_factory=list)
    title: str = ""

    def add(self, *els) -> "Mark":
        self.elements.extend(els)
        return self

    def roles(self) -> set[str]:
        out: set[str] = set()
        for e in self.elements:
            if not isinstance(e, Knockout):
                out.add(e.role)
        return out


# ---- SVG -------------------------------------------------------------------------------------


def _el_svg(e, colour: str) -> str:
    if isinstance(e, Fill):
        return f'<path d="{e.path.d()}" fill="{colour}" fill-rule="evenodd"/>'
    if isinstance(e, Stroke):
        return (f'<path d="{e.path.d()}" fill="none" stroke="{colour}" '
                f'stroke-width="{f(e.width)}" stroke-linecap="round" stroke-linejoin="round"/>')
    if isinstance(e, Circle):
        return f'<circle cx="{f(e.cx)}" cy="{f(e.cy)}" r="{f(e.r)}" fill="{colour}"/>'
    raise TypeError(type(e))


def to_svg(mark: Mark, colours: dict[str, str], ground: str | None = None, *,
           width: float | None = None, height: float | None = None,
           id_prefix: str | None = None, title: str | None = None) -> str:
    """Self-contained SVG: no external references, no <text>, no scripts, no fonts."""
    pid = id_prefix or ("m" + hashlib.sha1(mark.name.encode()).hexdigest()[:6])
    w, h = mark.width, mark.height
    defs: list[str] = []
    body = ""
    k = 0
    for e in mark.elements:
        if isinstance(e, Knockout):
            k += 1
            mid = f"{pid}-k{k}"
            black = "".join(_el_svg(s, "#000") for s in e.shapes)
            defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" '
                        f'width="{f(w)}" height="{f(h)}"><rect width="{f(w)}" height="{f(h)}" '
                        f'fill="#fff"/>{black}</mask>')
            body = f'<g mask="url(#{mid})">{body}</g>'
        else:
            body += _el_svg(e, colours[e.role])
    bg = f'<rect width="{f(w)}" height="{f(h)}" fill="{ground}"/>' if ground else ""
    t = title if title is not None else (mark.title or mark.name)
    size = ""
    if width is not None:
        size = f' width="{f(width)}" height="{f(height if height is not None else width * h / w)}"'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}"{size} '
            f'role="img" aria-label="{_esc(t)}"><title>{_esc(t)}</title>'
            + (f"<defs>{''.join(defs)}</defs>" if defs else "") + bg + body + "</svg>")


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---- raster ----------------------------------------------------------------------------------


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _coverage(e, scale: float, W: int, H: int, ss: int):
    import numpy as np
    from PIL import Image, ImageDraw

    S = scale * ss
    if isinstance(e, Fill):
        acc = np.zeros((H * ss, W * ss), dtype=bool)
        for pts, _closed in e.path.polylines():
            if len(pts) < 3:
                continue
            im = Image.new("1", (W * ss, H * ss), 0)
            ImageDraw.Draw(im).polygon([(x * S, y * S) for x, y in pts], fill=1)
            acc ^= np.asarray(im, dtype=bool)
        cov = acc.astype(np.float32)
    else:
        im = Image.new("L", (W * ss, H * ss), 0)
        dr = ImageDraw.Draw(im)
        if isinstance(e, Circle):
            r = e.r * S
            dr.ellipse([e.cx * S - r, e.cy * S - r, e.cx * S + r, e.cy * S + r], fill=255)
        else:
            # Exact round-cap, round-join stroke: a quad per segment plus a disc per vertex.
            # (Pillow's wide `line` leaves seams on densely flattened curves.)
            rr = max(0.5, e.width * S / 2)
            for pts, closed in e.path.polylines():
                q = [(x * S, y * S) for x, y in pts]
                if closed:
                    q = q + [q[0]]
                for (x0, y0), (x1, y1) in zip(q, q[1:]):
                    dx, dy = x1 - x0, y1 - y0
                    ln = math.hypot(dx, dy)
                    if ln < 1e-9:
                        continue
                    nx, ny = -dy / ln * rr, dx / ln * rr
                    dr.polygon([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny),
                                (x0 - nx, y0 - ny)], fill=255)
                for x, y in q:
                    dr.ellipse([x - rr, y - rr, x + rr, y + rr], fill=255)
        cov = np.asarray(im, dtype=np.float32) / 255.0
    return cov.reshape(H, ss, W, ss).mean(axis=(1, 3))


def rasterize(mark: Mark, colours: dict[str, str], px_w: int, px_h: int | None = None,
              ground: str | None = None, ss: int = 4):
    """Render to an (H, W, 4) float RGBA array, straight alpha, values 0..1.

    `ss` is the supersampling factor per axis (anti-aliasing). Deterministic.
    """
    import numpy as np

    px_h = px_h if px_h is not None else int(round(px_w * mark.height / mark.width))
    scale = px_w / mark.width
    rgb = np.zeros((px_h, px_w, 3), dtype=np.float32)   # premultiplied
    a = np.zeros((px_h, px_w), dtype=np.float32)
    for e in mark.elements:
        if isinstance(e, Knockout):
            cov = np.zeros((px_h, px_w), dtype=np.float32)
            for s in e.shapes:
                cov = np.maximum(cov, _coverage(s, scale, px_w, px_h, ss))
            rgb *= (1 - cov)[..., None]
            a *= (1 - cov)
            continue
        cov = _coverage(e, scale, px_w, px_h, ss)
        col = np.array(_hex(colours[e.role]), dtype=np.float32)
        rgb = rgb * (1 - cov)[..., None] + col[None, None, :] * cov[..., None]
        a = a * (1 - cov) + cov
    if ground:
        g = np.array(_hex(ground), dtype=np.float32)
        rgb = rgb + g[None, None, :] * (1 - a)[..., None]
        a = np.ones_like(a)
    out = np.zeros((px_h, px_w, 4), dtype=np.float32)
    safe = np.where(a > 1e-6, a, 1.0)
    out[..., :3] = np.where(a[..., None] > 1e-6, rgb / safe[..., None], 0)
    out[..., 3] = a
    return out


def to_png_bytes(arr) -> bytes:
    import io

    import numpy as np
    from PIL import Image

    im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype("uint8"), "RGBA")
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def all_points(mark: Mark) -> Iterable[Pt]:
    for e in mark.elements:
        shapes = e.shapes if isinstance(e, Knockout) else [e]
        for s in shapes:
            if isinstance(s, Circle):
                yield (s.cx - s.r, s.cy - s.r)
                yield (s.cx + s.r, s.cy + s.r)
            else:
                pad = s.width / 2 if isinstance(s, Stroke) else 0.0
                for pts, _ in s.path.polylines():
                    for x, y in pts:
                        yield (x - pad, y - pad)
                        yield (x + pad, y + pad)
