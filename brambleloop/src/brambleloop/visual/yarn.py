"""Continuous yarn geometry for certified crochet fabric.

The glyph renderer failed because it drew stitches as independent symbols on a lattice
(B-704). This builds the thing that failure pointed at: one continuous strand of yarn whose
path through space is determined by the CIR, where a stitch is a *linkage* to the stitch
below rather than a picture placed above it.

**Crochet, not knitting, and the difference is load-bearing.** In knitting a row of live
loops is held on a needle and each new loop is drawn through the loop directly below it, so
the fabric is a lattice of interlocking Vs. In crochet exactly one loop is live -- the one on
the hook -- and each stitch is *completed* before the next begins: the hook is inserted into
finished fabric, yarn is drawn up, and the loops on the hook are closed off. That is why a
crochet stitch has a post standing proud of the fabric and a pair of top loops lying across
it, and why those top loops are what the next row works into. Borrowing knitting's loop
topology would produce fabric that renders beautifully and is the wrong textile, which the
owner named as a failure condition rather than a nuance.

**Loop targeting becomes physical here, which is the point.** A half double worked through
the back loop puts its post around the anchor's back loop only, and the anchor's front loop
is then left *unattached* -- a free strand lying on the surface with nothing drawn through it.
That free strand is the ridge you see and feel in textured crochet. A glyph renderer can only
colour it differently; yarn geometry leaves it genuinely loose, so it catches light, casts a
shadow onto the fabric beneath and lifts where the fabric is compressed. The texture stops
being a drawing convention and becomes a consequence of construction.

Every point produced here is traceable to a cell the compiler counted. Nothing is sculpted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class YarnPath:
    """One continuous strand: a polyline in millimetres, plus where it came from."""

    points: np.ndarray                      # (n, 3)
    radius_mm: float
    # Which cell each vertex belongs to, so any point in the geometry can be traced back to
    # the stitch the compiler counted. This is what makes the render auditable rather than
    # merely deterministic.
    provenance: list[tuple[int, int]] = field(default_factory=list)
    # Segments that are free loops -- unattached strands lying on the surface. Kept separate
    # because they are the visible texture and because they relax differently: nothing is
    # drawn through them, so they are the first thing to lift and shift.
    free_spans: list[tuple[int, int]] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.points)


# Yarn diameter as a fraction of stitch width. A worsted yarn worked at its recommended hook
# fills most of the stitch: the gaps in crochet are small, and fabric that shows daylight
# between every strand is fabric worked far too loosely -- the first thing wrong with the
# glyph renders.
YARN_FILL = 0.30

# How far a post stands proud of the fabric plane, as a fraction of stitch width. Crochet is
# a thick fabric; this is what separates it from a flat weave.
POST_DEPTH = 0.42


def _hdc_stitch(x0: float, x1: float, y_top: float, y_bot: float, depth: float,
                loop: str, direction: int, anchor_z: float) -> tuple[list, list]:
    """One half double crochet, as the yarn actually runs.

    The first version of this routed the yarn down near the anchor and back up, which
    produced a net of struts and bars: strands that pass close to one another are not
    interlocked, and fabric whose loops are not interlocked is not fabric. Two things were
    missing and they share a cause -- the path was a schematic of a stitch rather than the
    route the yarn takes.

      * **The pull-up must encircle the anchor.** A half double is made by drawing a loop
        *through* the top of the stitch below, so the new strand passes around the anchor's
        loop and cannot be separated from it without cutting. Proximity is not linkage.
      * **A half double has three strands in its post, not one.** Yarn over, pull up a loop,
        then close all three loops off together -- the wrap, the pull-up and the closing all
        leave yarn standing in the same place. That is why crochet is a thick, dense fabric
        and why the first render showed daylight through it: one strut where there should be
        three leaves two thirds of the yarn missing.

    Loop targeting decides which of the anchor's two top loops the post encircles, and the
    other is left genuinely unattached -- a free strand lying across the face with nothing
    drawn through it. That is the ridge, and it exists here as geometry rather than shading.
    """
    pts: list[tuple[float, float, float]] = []
    mid = (x0 + x1) / 2.0
    w = abs(x1 - x0)
    d = direction
    h = y_top - y_bot

    # Which of the anchor's loops this stitch is drawn through, and where that sits in depth.
    if loop == "back":
        thru_z = -depth * 0.40          # around the back loop; front loop left free above
    elif loop == "front":
        thru_z = depth * 0.40
    else:
        thru_z = 0.0                    # through both together: nothing left loose

    # 1. Yarn over -- the wrap that makes this a half double. It crosses the front of the
    #    post and ends up as one of the three strands standing in it.
    pts.append((x0, y_top - h * 0.08, depth * 0.62))
    pts.append((mid - d * w * 0.30, y_top - h * 0.22, depth * 0.78))
    pts.append((mid - d * w * 0.24, y_bot + h * 0.34, depth * 0.52))

    # 2. Insert and pull up: the strand goes BEHIND the anchor loop, under it, and back out
    #    in front -- an encirclement, so the two are genuinely linked.
    pts.append((mid - d * w * 0.12, y_bot + h * 0.16, thru_z - depth * 0.55))
    pts.append((mid, y_bot + h * 0.03, thru_z - depth * 0.15))     # under the anchor
    pts.append((mid + d * w * 0.10, y_bot + h * 0.06, thru_z + depth * 0.62))
    pts.append((mid + d * w * 0.16, y_bot + h * 0.30, thru_z + depth * 0.40))

    # 3. The pull-up strand rises -- the second of the three in the post.
    pts.append((mid + d * w * 0.06, y_bot + h * 0.58, depth * 0.10))
    pts.append((mid - d * w * 0.04, y_top - h * 0.30, -depth * 0.22))

    # 4. Closing all three loops off: a wrap around the top of the post, which leaves the
    #    third strand and forms the neck of the stitch.
    pts.append((mid - d * w * 0.20, y_top - h * 0.16, -depth * 0.50))
    pts.append((mid + d * w * 0.02, y_top - h * 0.10, -depth * 0.30))
    pts.append((mid + d * w * 0.22, y_top - h * 0.18, depth * 0.05))
    pts.append((mid + d * w * 0.10, y_top - h * 0.30, depth * 0.44))

    # 5. The two top loops, which the next row will work into. Back loop first, then front.
    back_z, front_z = -depth * 0.52, depth * 0.52
    pts.append((mid - d * w * 0.10, y_top - h * 0.06, back_z))
    pts.append((x1 - d * w * 0.10, y_top - h * 0.02, back_z))
    pts.append((x1, y_top + h * 0.02, back_z * 0.4))
    free_start = len(pts)
    pts.append((x1 - d * w * 0.06, y_top + h * 0.05, front_z))
    pts.append((mid, y_top + h * 0.07, front_z))
    pts.append((x0 + d * w * 0.10, y_top + h * 0.04, front_z))
    free_end = len(pts)
    pts.append((x1, y_top - h * 0.01, depth * 0.20))               # away to the next stitch

    return pts, [free_start, free_end]


def yarn_path(twin, gauge, *, max_rows: int | None = None, max_cols: int | None = None,
              seed: int = 0) -> YarnPath:
    """Build the continuous yarn for a compiled fabric, stitch by stitch, in working order.

    Working order matters: the strand is continuous because it is made continuously, and the
    turn at the end of a flat row is why alternate rows run the other way. Reversing the
    geometry to match a chart would break the one property this representation exists to
    have.
    """
    sw = 10.0 / gauge.stitches_per_10cm * 10.0          # stitch width in mm
    sh = 10.0 / gauge.rows_per_10cm * 10.0              # row height in mm
    radius = sw * YARN_FILL * 0.5
    depth = sw * POST_DEPTH

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r),
                        key=lambda c: c.position)                      # working order
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    rng = np.random.default_rng(seed)
    pts: list[tuple[float, float, float]] = []
    prov: list[tuple[int, int]] = []
    free: list[tuple[int, int]] = []

    for ri, r in enumerate(rows):
        cells = [c for c in by_row[r] if getattr(c, "fabric_position", c.position) < ncols]
        if max_cols:
            cells = cells[:ncols]
        # Flat rows turn, so every other row is laid down in the opposite direction. The
        # fabric position is where the stitch ENDS UP; the order is how it was made.
        direction = 1 if ri % 2 == 0 else -1
        y_top = (ri + 1) * sh
        y_bot = ri * sh
        for c in cells:
            fp = getattr(c, "fabric_position", c.position)
            x0 = fp * sw if direction > 0 else (fp + 1) * sw
            x1 = (fp + 1) * sw if direction > 0 else fp * sw
            anchor_z = 0.0
            seg, span = _hdc_stitch(x0, x1, y_top, y_bot, depth,
                                    getattr(c, "loop", "both"), direction, anchor_z)
            base = len(pts)
            pts.extend(seg)
            prov.extend([(c.row, fp)] * len(seg))
            free.append((base + span[0], base + span[1]))

    arr = np.asarray(pts, dtype=np.float64)
    if len(arr):
        # Hand tension is not uniform and not random either: it drifts. A smooth
        # low-frequency field across the whole panel, not per-stitch noise -- that distinction
        # is the diagnosis B-704 left behind, since local jitter on a regular grid still reads
        # as a regular grid.
        arr = _tension_drift(arr, rng, sw)
    return YarnPath(points=arr, radius_mm=radius, provenance=prov, free_spans=free)


def _tension_drift(arr: np.ndarray, rng, sw: float) -> np.ndarray:
    """Low-frequency wander across the whole piece, the way hand fabric actually varies.

    Three smooth sinusoids at incommensurate wavelengths, phased randomly. The point is that
    the variation is correlated over dozens of stitches: edges bow, rows are not quite
    parallel, one region is worked a little tighter than another. Per-stitch jitter cannot
    produce that and a lattice with noise on it is still a lattice.
    """
    x, y = arr[:, 0], arr[:, 1]
    span = max(float(np.ptp(arr[:, 0])), float(np.ptp(arr[:, 1])), 1.0)
    out = arr.copy()
    for axis, amp in ((0, 0.13), (1, 0.09), (2, 0.22)):
        d = np.zeros_like(x)
        for k, wl in enumerate((0.9, 0.43, 0.21)):
            ph = rng.uniform(0, 2 * np.pi, size=2)
            d += (amp / (k + 1)) * np.sin(2 * np.pi * x / (span * wl) + ph[0]) \
                                 * np.cos(2 * np.pi * y / (span * wl * 1.31) + ph[1])
        out[:, axis] += d * sw
    return out


def resample(path: YarnPath, *, per_segment: int = 5) -> YarnPath:
    """Smooth the polyline into something yarn-shaped.

    A Catmull-Rom pass through the control points. Yarn does not turn corners: every bend in
    a real strand has the radius the fibre's own stiffness gives it, and a polyline with hard
    corners renders as bent wire.
    """
    p = path.points
    if len(p) < 4:
        return path
    out, prov = [], []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for j in range(per_segment):
            t = j / per_segment
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t +
                              (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
            prov.append(path.provenance[i] if i < len(path.provenance) else (0, 0))
    scale = len(out) / max(1, len(p))
    return YarnPath(points=np.asarray(out), radius_mm=path.radius_mm, provenance=prov,
                    free_spans=[(int(a * scale), int(b * scale))
                                for a, b in path.free_spans])


def relax(path: YarnPath, *, iterations: int = 40, stiffness: float = 0.22,
          repulsion: float = 0.55, free_lift: float = 0.35) -> YarnPath:
    """Let neighbouring strands push each other apart, the way real fabric settles.

    Two forces, and both are what makes this a fabric rather than a set of curves that happen
    to be near one another:

      * **structural** -- the yarn resists stretching, so vertices are pulled back towards an
        even spacing along the strand;
      * **contact** -- yarn cannot pass through yarn, so nearby vertices from different parts
        of the path push apart. This is what closes the gaps up, thickens the fabric, and
        makes a stitch's neighbours visibly affect it.

    Free loops additionally lift, because nothing is drawn through them to hold them down --
    which is precisely why a textured pattern has relief at all.
    """
    if len(path) < 3:
        return path
    p = path.points.copy()
    rest = float(np.mean(np.linalg.norm(np.diff(p, axis=0), axis=1)))
    contact = path.radius_mm * 2.0

    free_mask = np.zeros(len(p), dtype=bool)
    for a, b in path.free_spans:
        free_mask[max(0, a):min(len(p), b)] = True
    p[free_mask, 2] += path.radius_mm * free_lift

    # Bucket by cell so contact is O(n) rather than O(n^2): a strand can only touch strands
    # that are already close, so only near neighbours need consulting.
    for _ in range(iterations):
        d = np.diff(p, axis=0)
        length = np.linalg.norm(d, axis=1, keepdims=True)
        length[length == 0] = 1e-9
        pull = (length - rest) / length * d * stiffness
        p[:-1] += pull * 0.5
        p[1:] -= pull * 0.5

        cell = np.floor(p / max(contact, 1e-6)).astype(np.int64)
        buckets: dict[tuple[int, int, int], list[int]] = {}
        for i, key in enumerate(map(tuple, cell)):
            buckets.setdefault(key, []).append(i)
        for key, members in buckets.items():
            if len(members) < 2:
                continue
            idx = np.asarray(members)
            sub = p[idx]
            diff = sub[:, None, :] - sub[None, :, :]
            dist = np.linalg.norm(diff, axis=2)
            np.fill_diagonal(dist, np.inf)
            # Neighbours along the strand are supposed to be close; only non-adjacent
            # vertices are in contact.
            adjacent = np.abs(idx[:, None] - idx[None, :]) <= 2
            dist[adjacent] = np.inf
            close = dist < contact
            if not close.any():
                continue
            push = np.where(close[..., None], diff / np.maximum(dist, 1e-9)[..., None] *
                            ((contact - np.minimum(dist, contact)) / contact)[..., None], 0.0)
            p[idx] += push.sum(axis=1) * repulsion * contact * 0.25
    return YarnPath(points=p, radius_mm=path.radius_mm, provenance=path.provenance,
                    free_spans=path.free_spans)


def write_curve_file(path: YarnPath, filename: str, *, ply_wobble: float = 0.0) -> int:
    """Mitsuba's linear-curve format: one `x y z radius` per vertex, blank line per strand."""
    n = 0
    with open(filename, "w") as f:
        for i, (x, y, z) in enumerate(path.points):
            r = path.radius_mm
            if ply_wobble:
                # Plied yarn is not a smooth cylinder; its diameter pulses along its length.
                r *= 1.0 + ply_wobble * float(np.sin(i * 0.9))
            f.write(f"{x:.5f} {y:.5f} {z:.5f} {r:.5f}\n")
            n += 1
        f.write("\n")
    return n
