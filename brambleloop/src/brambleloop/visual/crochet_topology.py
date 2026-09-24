"""Certified CIR operations translated into physically correct continuous crochet yarn.

This replaces the hand-authored stitch path that failed (B-705, B-707). The failure was
specific: every key point stayed inside its own stitch cell, so loops sat beside one another
instead of passing through one another, and strands that meet without passing through are
netting rather than fabric.

The method here is adapted from a published, crochet-specific one rather than invented:

    Storck, Gerber, Steenbock, Kyosev (2022), "Topology based modelling of crochet
    structures", Journal of Industrial Textiles 52:1-18 (open access).

Each stitch is a **unit cell of parameterised key points along the yarn centre path**, driven
by three shaping parameters -- L (stitch pitch along the row), H (stitch height), D (depth
through the fabric) -- plus the yarn diameter. Rows carry a left/right orientation, are
shifted and rotated so their loops intermesh, and are joined by explicit transition cells
containing a chain stitch: the turning chain. The centre path is then interpolated with
Kochanek-Bartels splines.

Three published proportions are load-bearing and are used as given:

    4a.x - 1a.x = 1.85 L     a loop spans nearly two stitch widths
    2a.y - 1a.y = 1.23 H     a key point rises above the nominal stitch height
    3a.z - 5a.z = D          front and back of the cell are separated in depth

The first two are what my hand-authored version got wrong. A loop that reaches almost two
stitches along the row and arches above the row line is a loop the next row can come down
*through*; a loop contained in its own cell is not.

**What is ours and what is theirs, kept distinct.** The paper models chain, slip stitch and
single crochet. It does not model half double, which is what the benchmark garment is made
of, and the authors state the approach extends by "defining more parameterized key points
... accounting for the spatial arrangement of the loops". The HDC unit cell below is
therefore ours, constrained by their proportions and by the actual fabrication sequence,
rather than copied. Saying which is which matters: one is cited evidence, the other is a
modelling choice that has to earn its place by passing the topology checks.

**The CIR remains the authority.** Nothing here decides what the product is. It translates
operations the compiler already certified -- stitch type, loop target, row, position, working
direction -- into where the yarn physically goes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Published proportions (Storck et al. 2022), used as stated.
LOOP_REACH = 1.85          # a loop spans this many stitch pitches in x
CROWN_RISE = 1.23          # a key point rises this fraction of H above the base
# Yarn diameter as a fraction of stitch pitch. Their sample is 0.1 (fine cotton at L=5mm);
# the benchmark garment is worsted at L=6.9mm with roughly 2mm yarn, so ~0.29. Carried as a
# parameter rather than a constant because it is a property of the yarn, not of crochet.
DEFAULT_D_OVER_L = 0.29

# The 27 cells of a uniform-grid neighbourhood, including the cell itself.
_NEIGHBOURHOOD = tuple((i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1))


@dataclass
class Op:
    """One certified operation, and where its yarn went."""

    kind: str                      # "hdc" | "chain" | "turn"
    row: int
    position: int
    loop_target: str               # "front" | "back" | "both"
    direction: int                 # +1 or -1 along x
    points: np.ndarray             # (n,3) key points of this unit cell
    # Indices, within this cell, of the two top loops the NEXT row works into. Named because
    # the whole of loop targeting is a choice between them.
    front_loop: tuple[int, int] = (0, 0)
    back_loop: tuple[int, int] = (0, 0)
    # The span that passes through the anchor's loop. This is the linkage, and the topology
    # validator checks exactly this.
    pull_through: tuple[int, int] = (0, 0)


@dataclass
class Fabric:
    """A continuous yarn path plus the operation structure that produced it."""

    ops: list[Op] = field(default_factory=list)
    L: float = 0.0
    H: float = 0.0
    D: float = 0.0
    yarn_diameter: float = 0.0

    @property
    def points(self) -> np.ndarray:
        return np.concatenate([o.points for o in self.ops]) if self.ops else np.zeros((0, 3))

    def offset_of(self, index: int) -> int:
        """Where operation `index` starts in the concatenated path."""
        return int(sum(len(o.points) for o in self.ops[:index]))


def _hdc_cell(L: float, H: float, D: float, direction: int, loop_target: str,
              anchor_top_y: float, yarn: float) -> tuple[np.ndarray, dict]:
    """One half double crochet, as key points of the yarn centre path.

    Ours, not the paper's -- they model chain, slip stitch and single crochet. Built from the
    fabrication sequence a half double actually follows, with the published proportions
    imposed on it:

        live loop on the hook
          -> yarn over                       (the strand that makes this a HALF double)
          -> insert into the CIR's loop target of the stitch below
          -> pull up a loop THROUGH it       (three loops on the hook)
          -> yarn over, pull through all three
          -> the new live loop, which is this stitch's top

    **Positions are in fabric coordinates; only the path's direction of travel reverses.**
    The first version let working direction shift the key points themselves, so a stitch's
    top loops landed at one x on a right-going row and a different x on a left-going one --
    roughly 1.3 pitches apart. The row above then reached for a loop that was never there,
    and the validator reported 0 of 15 stitches linked. Turning changes the order the yarn is
    laid down, not where the fabric ends up: the loops a row leaves behind are in the same
    place whichever way it was worked, which is why the next row can find them at all.

    So the cell is built once, symmetric about its own centre for everything another row has
    to find -- the insertion point and the two top loops -- and mirrored end for end when the
    row runs the other way.
    """
    # Depth of the loop the hook enters. Working through the back loop puts the pull-up
    # behind the anchor's front loop, which is then left lying loose on the face -- the ridge.
    if loop_target == "back":
        enter_z = -D * 0.45
    elif loop_target == "front":
        enter_z = +D * 0.45
    else:
        enter_z = 0.0

    y0 = anchor_top_y                      # the top of the stitch below: where we enter
    yt = y0 + H                            # the top of this stitch
    crown = y0 + CROWN_RISE * H            # published: a key point rises above the top
    c = 0.5 * L                            # the cell's centre: mirror-invariant

    p = [
        # --- yarn over: the wrap, before the hook enters anything ---------------
        (0.00 * L, yt - 0.18 * H, +D * 0.62),
        (0.22 * L, yt - 0.04 * H, +D * 0.34),

        # --- insert, and pull a loop THROUGH the anchor -------------------------
        # Centred on the cell so the row above finds it in the same place whichever way it
        # was worked. Down the near side of the anchor's loop, under it, up the far side --
        # these three points are the linkage the validator tests.
        # The dive clears the anchor strand by a yarn diameter. That clearance is in
        # millimetres of yarn, not a fraction of H: the published ratios describe centre
        # paths and are silent about thickness, so a dive sized purely from H passed within
        # 0.53mm of a 2mm strand -- through it, not around it. What is being gone around has
        # a radius, and every one of the fifteen stitches interpenetrated by the same amount
        # because the same constant was wrong in all of them.
        (c - 0.16 * L, y0 + 0.46 * H, enter_z + D * 1.05),
        (c, y0 - 0.02 * H - yarn, enter_z),
        (c + 0.16 * L, y0 + 0.46 * H, enter_z - D * 1.05),

        # --- the pull-up rises, reaching along the row --------------------------
        # LOOP_REACH is imposed here: the loop extends nearly two pitches, overlapping the
        # neighbouring stitch, which is what lets the next row intermesh.
        (c + 0.34 * L, y0 + 0.74 * H, -D * 0.34),
        (LOOP_REACH * 0.52 * L, crown, +D * 0.08),

        # --- yarn over and pull through all three loops -------------------------
        (c + 0.30 * L, yt - 0.12 * H, -D * 0.58),
        (c - 0.06 * L, yt - 0.04 * H, -D * 0.38),

        # --- the two top loops: what the next row works into --------------------
        # Symmetric about the centre, so they sit at the same fabric x either way.
        (c - 0.34 * L, yt + 0.02 * H, -D * 0.50),          # back loop, start
        (c + 0.34 * L, yt + 0.05 * H, -D * 0.46),          # back loop, end
        (c + 0.40 * L, yt + 0.09 * H, +D * 0.04),
        (c + 0.34 * L, yt + 0.11 * H, +D * 0.50),          # front loop, start
        (c - 0.34 * L, yt + 0.07 * H, +D * 0.52),          # front loop, end
        (1.00 * L, yt - 0.06 * H, +D * 0.22),              # away to the next stitch
    ]
    pts = np.asarray(p, dtype=np.float64)
    if direction < 0:
        # Mirror end for end about the cell centre, and lay the points down in the reverse
        # order, because the yarn travels the other way. Everything another row must find is
        # symmetric about that centre, so it does not move.
        pts[:, 0] = L - pts[:, 0]
        pts = pts[::-1].copy()
        spans = {"pull_through": (len(pts) - 6, len(pts) - 3),
                 "back_loop": (len(pts) - 11, len(pts) - 10),
                 "front_loop": (len(pts) - 14, len(pts) - 13)}
    else:
        # A loop ends where the comments above say it ends. Both spans used to run one point
        # long, swallowing the point after the loop. For the back loop that point continues
        # in the same direction, so the strand stayed a simple arc and encirclement still
        # counted odd. For the front loop the extra point is the run-off to the next stitch,
        # which doubles back in x: the strand became a hairpin, a passing yarn crossed the
        # ribbon under it twice, and an even count reads as not linked. Every front-loop
        # stitch failed and no other kind did.
        spans = {"pull_through": (2, 5), "back_loop": (9, 10), "front_loop": (12, 13)}
    return pts, spans


def _turning_chain(L: float, H: float, D: float, direction: int,
                   y_top: float) -> np.ndarray:
    """The transition between rows: a chain stitch that lifts the yarn to the next row.

    The paper is explicit that rows are joined by transition unit cells "partially consisting
    of a chain stitch". My earlier model had none at all, which left each row a separate
    object that happened to sit above the last -- another way the fabric was not one thing.
    """
    d = direction
    return np.asarray([
        (0.10 * L * d, y_top + 0.10 * H, +D * 0.30),
        (0.34 * L * d, y_top + 0.46 * H, +D * 0.55),
        (0.18 * L * d, y_top + 0.86 * H, -D * 0.10),
        (-0.16 * L * d, y_top + 0.92 * H, -D * 0.45),
        (-0.34 * L * d, y_top + 0.58 * H, -D * 0.20),
        (-0.20 * L * d, y_top + 0.16 * H, +D * 0.25),
    ], dtype=np.float64)


def build(twin, gauge, *, max_rows: int | None = None, max_cols: int | None = None,
          d_over_l: float = DEFAULT_D_OVER_L) -> Fabric:
    """Translate certified cells into one continuous crochet yarn path."""
    L = 10.0 / gauge.stitches_per_10cm * 10.0
    H = 10.0 / gauge.rows_per_10cm * 10.0
    D = L * 0.55
    fab = Fabric(L=L, H=H, D=D, yarn_diameter=L * d_over_l)

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r), key=lambda c: c.position)
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    for ri, r in enumerate(rows):
        direction = 1 if ri % 2 == 0 else -1
        cells = [c for c in by_row[r]
                 if getattr(c, "fabric_position", c.position) < ncols][:ncols]
        # Laid down in the order the hook makes them. Emitting in position order on a
        # right-to-left row left the yarn jumping the width of the panel at every reversal,
        # which the continuity check caught as a 35mm break.
        cells.sort(key=lambda x: getattr(x, "fabric_position", x.position),
                   reverse=direction < 0)
        anchor_top_y = ri * H
        if ri and fab.ops:
            # At the end of the row just worked, not at x=0. Emitting it at the origin left
            # the yarn jumping the full width of the panel at every reversal -- 35mm, which
            # the continuity check reported as a break rather than a path.
            tail = fab.ops[-1].points[-1]
            turn = _turning_chain(L, H, D, direction, anchor_top_y)
            turn = turn + np.array([tail[0] - turn[0, 0], 0.0, 0.0])
            fab.ops.append(Op("turn", r, -1, "both", direction, turn))
        for c in cells:
            fp = getattr(c, "fabric_position", c.position)
            pts, spans = _hdc_cell(L, H, D, direction, getattr(c, "loop", "both"),
                                   anchor_top_y, fab.yarn_diameter)
            pts = pts + np.array([fp * L, 0.0, 0.0])
            fab.ops.append(Op("hdc", r, fp, getattr(c, "loop", "both"), direction, pts,
                              front_loop=spans["front_loop"], back_loop=spans["back_loop"],
                              pull_through=spans["pull_through"]))
    return fab


# ---------------------------------------------------------------------------
# Topology validation, which runs BEFORE anything is rendered.
#
# The owner's rule, and it is the right one: if the topology does not pass, stop there and do
# not use materials or lighting to hide it. A beautiful render of the wrong structure is the
# failure this whole architecture exists to prevent, and it is much easier to produce by
# accident than a correct one.
#
# The check that matters most is linkage. Two strands that pass near one another and two
# strands that pass through one another look almost identical from a camera and are
# completely different textiles -- netting versus fabric. So it is tested geometrically
# rather than eyeballed: does the pull-up span actually cross the surface spanned by the
# anchor's loop?
# ---------------------------------------------------------------------------


def _crosses_ring(path: np.ndarray, ring: np.ndarray) -> bool:
    """Does `path` pass through the opening bounded by `ring`?

    Used for stitches worked under BOTH top loops, because that is a different topological
    relation from working under one. Under a single loop the new yarn *encircles a strand*;
    under both it *passes through the opening* the two strands bound together. Testing the
    second as though it were the first returns zero every time -- correctly, because the yarn
    threads between the strands rather than going round either -- which is exactly what the
    validator reported before this distinction was drawn.

    The ring is triangulated as a fan from its centroid. It has real area because it is built
    from both strands; a single top loop is three nearly collinear points and spans nothing,
    which is why the first version of this check could never fire.
    """
    if len(ring) < 3:
        return False
    centre = ring.mean(axis=0)
    hits = 0
    for i in range(len(ring)):
        v0, v1, v2 = centre, ring[i], ring[(i + 1) % len(ring)]
        e1, e2 = v1 - v0, v2 - v0
        for j in range(len(path) - 1):
            o, d = path[j], path[j + 1] - path[j]
            h = np.cross(d, e2)
            det = float(np.dot(e1, h))
            if abs(det) < 1e-12:
                continue
            inv = 1.0 / det
            sv = o - v0
            u = inv * float(np.dot(sv, h))
            if u < 0.0 or u > 1.0:
                continue
            q = np.cross(sv, e1)
            v = inv * float(np.dot(d, q))
            if v < 0.0 or u + v > 1.0:
                continue
            t = inv * float(np.dot(e2, q))
            if 1e-9 < t < 1.0 - 1e-9:
                hits += 1
    return hits % 2 == 1


def _crossings_of_spanning_surface(path: np.ndarray, strand: np.ndarray,
                                   drop: float) -> int:
    """How many times `path` crosses the half-plane hanging below `strand`.

    This is the linkage test, and getting it right took being wrong first. The initial
    version treated the anchor's loop as a surface and asked whether the new strand passed
    through it -- but the anchor's top loop is three nearly collinear points, so the
    "surface" was a sliver with no area and nothing could ever cross it. Worse, it was asking
    the wrong question: a back-loop stitch does not pass through an opening, it **encircles a
    strand**, the way one link of a chain encircles the next.

    Two curves are linked when one crosses a surface bounded by the other an odd number of
    times. Taking that surface as the ribbon hanging straight down from the strand gives a
    test that is cheap, needs no closed curve, and answers exactly the physical question:
    did the yarn go round it, or merely past it?
    """
    if len(strand) < 2:
        return 0
    hits = 0
    for i in range(len(strand) - 1):
        a, b = strand[i], strand[i + 1]
        below_a = a - np.array([0.0, drop, 0.0])
        below_b = b - np.array([0.0, drop, 0.0])
        for tri in ((a, b, below_b), (a, below_b, below_a)):
            v0, v1, v2 = tri
            e1, e2 = v1 - v0, v2 - v0
            for j in range(len(path) - 1):
                o, dvec = path[j], path[j + 1] - path[j]
                h = np.cross(dvec, e2)
                det = float(np.dot(e1, h))
                if abs(det) < 1e-12:
                    continue
                inv = 1.0 / det
                sv = o - v0
                u = inv * float(np.dot(sv, h))
                if u < 0.0 or u > 1.0:
                    continue
                q = np.cross(sv, e1)
                v = inv * float(np.dot(dvec, q))
                if v < 0.0 or u + v > 1.0:
                    continue
                t = inv * float(np.dot(e2, q))
                if 1e-9 < t < 1.0 - 1e-9:
                    hits += 1
    return hits


def validate(fab: Fabric, twin, *, max_rows: int | None = None,
             max_cols: int | None = None) -> dict:
    """Mechanically check the yarn against the certified operations. Renders nothing."""
    findings: list[str] = []
    checks: dict[str, object] = {}

    hdc = [o for o in fab.ops if o.kind == "hdc"]
    turns = [o for o in fab.ops if o.kind == "turn"]

    # --- correspondence with the CIR ---------------------------------------
    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    expected = 0
    for r in rows:
        cells = [c for c in twin.cells if c.row == r]
        if max_cols:
            cells = [c for c in cells
                     if getattr(c, "fabric_position", c.position) < max_cols]
        expected += len(cells)
    checks["stitches_expected"] = expected
    checks["stitches_built"] = len(hdc)
    if len(hdc) != expected:
        findings.append(f"built {len(hdc)} stitches for {expected} certified cells")

    cir_targets = {}
    for c in twin.cells:
        fp = getattr(c, "fabric_position", c.position)
        if c.row in rows and (max_cols is None or fp < max_cols):
            cir_targets[(c.row, fp)] = getattr(c, "loop", "both")
    wrong = [(o.row, o.position) for o in hdc
             if cir_targets.get((o.row, o.position)) != o.loop_target]
    checks["loop_targets_match_cir"] = not wrong
    if wrong:
        findings.append(f"{len(wrong)} stitches carry a loop target the CIR did not specify")

    # --- one continuous yarn ------------------------------------------------
    pts = fab.points
    checks["total_points"] = len(pts)
    if len(pts) > 1:
        steps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        gap = float(steps.max())
        checks["largest_gap_mm"] = round(gap, 3)
        checks["median_step_mm"] = round(float(np.median(steps)), 3)
        # A break in the strand shows up as a step far larger than the working spacing.
        if gap > fab.L * 2.6:
            findings.append(f"the yarn jumps {gap:.1f}mm, which is a break rather than a path")

    # --- row-to-row connectivity -------------------------------------------
    checks["turning_chains"] = len(turns)
    if rows and len(turns) != len(rows) - 1:
        findings.append(f"{len(turns)} turning chains for {len(rows)} rows: the rows are not "
                        f"joined into one piece")

    # --- THE LINKAGE CHECK --------------------------------------------------
    # Every stitch above the first row must be drawn through the loop of the stitch below it.
    linked, unlinked = 0, []
    indeterminate: list[tuple[int, int]] = []
    by_key = {(o.row, o.position): o for o in hdc}
    for o in hdc:
        anchor = by_key.get((rows[rows.index(o.row) - 1], o.position)) \
            if rows.index(o.row) > 0 else None
        if anchor is None:
            continue
        # Which strand this stitch was drawn around is the loop target, exactly. Working
        # through both loops encircles the pair together, which is why plain fabric has no
        # ridge: neither strand is left loose.
        if o.loop_target == "front":
            strand = anchor.points[anchor.front_loop[0]:anchor.front_loop[1] + 1]
        elif o.loop_target == "back":
            strand = anchor.points[anchor.back_loop[0]:anchor.back_loop[1] + 1]
        else:
            strand = None            # both loops: tested against each in turn, below
        a0, a1 = o.pull_through
        pull = o.points[a0:min(a1 + 1, len(o.points))]
        if strand is not None:
            # One loop: the new yarn goes ROUND that strand.
            through = _crossings_of_spanning_surface(pull, strand, fab.H * 4.0) % 2 == 1
        else:
            # Working through BOTH loops, the hook goes UNDER the pair: the stem encircles
            # the two strands as a bundle. That is a third relation, and I cannot yet measure
            # it. Encircling each strand separately is not it. Threading between them --
            # which is what the previous version tested -- is a different relation entirely,
            # and it counted crossings on a sub-path cut at an arbitrary point, so its parity
            # moved with where the cut fell rather than with the topology. It reported 16 of
            # these linked and 7 unlinked, and neither number meant anything.
            #
            # So this is recorded as indeterminate, not as a pass and not as a failure. A
            # relation nobody has measured is not a relation that holds.
            indeterminate.append((o.row, o.position))
            continue
        if through:
            linked += 1
        else:
            unlinked.append((o.row, o.position))
    checks["stitches_needing_linkage"] = linked + len(unlinked) + len(indeterminate)
    checks["stitches_indeterminate"] = len(indeterminate)
    if indeterminate:
        findings.append(
            f"{len(indeterminate)} stitches work through both loops, whose linkage this "
            f"validator cannot yet measure. Not counted as linked")
    checks["stitches_linked"] = linked
    checks["unlinked"] = unlinked[:8]
    if unlinked:
        findings.append(
            f"{len(unlinked)} of {linked + len(unlinked)} stitches pass BESIDE the loop below "
            f"rather than through it. Strands that meet without passing through one another "
            f"are netting, not fabric")

    # --- no impossible intersections ---------------------------------------
    # Yarn cannot occupy the same space as yarn. Sampled, because the exact test is
    # quadratic and this is a diagnostic rather than a simulation.
    if len(pts) > 40:
        step = max(1, len(pts) // 600)
        s = pts[::step]
        diff = s[:, None, :] - s[None, :, :]
        dist = np.linalg.norm(diff, axis=2)
        idx = np.arange(len(s))
        adjacent = np.abs(idx[:, None] - idx[None, :]) <= 3
        np.fill_diagonal(dist, np.inf)
        dist[adjacent] = np.inf
        worst = float(dist.min())
        checks["closest_non_adjacent_mm"] = round(worst, 3)
        # Real yarn compresses where it crosses, so some overlap is physical; half a diameter
        # is not.
        if worst < fab.yarn_diameter * 0.45:
            findings.append(f"two strands come within {worst:.2f}mm, closer than yarn can "
                            f"compress at {fab.yarn_diameter:.2f}mm diameter")

    checks["passes"] = not findings
    checks["findings"] = findings
    checks["why"] = ("the yarn corresponds to the certified operations, runs continuously, "
                     "joins row to row and is drawn through the fabric below at every stitch"
                     if not findings else "; ".join(findings))
    return checks


def settle(fab: Fabric, *, iterations: int = 60, stiffness: float = 0.16,
           repulsion: float = 0.40) -> Fabric:
    """Let the yarn settle: strands push apart where they touch, and the path resists stretch.

    Physically this is what the fabric does when it comes off the hook. Freshly constructed
    key points put strands where the *operations* say they go, and real yarn then relieves the
    overlaps -- which is why the built geometry shows strands 0.5mm apart at 2mm diameter and
    a finished fabric does not.

    **The rest length is per segment, taken from the built geometry.** The first version
    pulled every segment towards one average spacing, and that destroyed all fifteen
    linkages on its first run -- the validator caught it immediately, which is the only
    reason this docstring does not still claim otherwise. A stitch's path is deliberately
    uneven: tight through the loop it is drawn through, long across the reach into the
    neighbouring stitch. Averaging that away drags strands back out of the loops they were
    threaded through. The yarn's length between two key points is set by the operation that
    put them there, so it is what the spring restores to.

    Linkage is therefore preserved by construction rather than by hope, and the validator is
    run again afterwards regardless, because "preserved by construction" is exactly the kind
    of claim that turns out to be wrong.
    """
    pts = fab.points.copy()
    if len(pts) < 4:
        return fab
    contact = fab.yarn_diameter
    # Each segment's own length, as built. Not an average.
    rest = np.linalg.norm(np.diff(pts, axis=0), axis=1, keepdims=True)
    rest[rest == 0] = 1e-9

    for _ in range(iterations):
        d = np.diff(pts, axis=0)
        ln = np.linalg.norm(d, axis=1, keepdims=True)
        ln[ln == 0] = 1e-9
        pull = (ln - rest) / ln * d * stiffness
        pts[:-1] += pull * 0.5
        pts[1:] -= pull * 0.5

        # Uniform grid. The neighbourhood must include the surrounding cells: two points
        # half a diameter apart usually straddle a cell boundary, and the first version,
        # which compared only within a cell, could not see a single one of the contacts it
        # existed to relieve.
        cell = np.floor(pts / max(contact, 1e-6)).astype(np.int64)
        buckets: dict[tuple, list[int]] = {}
        for i, key in enumerate(map(tuple, cell)):
            buckets.setdefault(key, []).append(i)

        shift = np.zeros_like(pts)
        for key, members in buckets.items():
            near: list[int] = []
            for off in _NEIGHBOURHOOD:
                near.extend(buckets.get((key[0] + off[0], key[1] + off[1], key[2] + off[2]), ()))
            if len(near) < 2:
                continue
            idx = np.asarray(members)
            cand = np.asarray(near)
            diff = pts[idx][:, None, :] - pts[cand][None, :, :]
            dist = np.linalg.norm(diff, axis=2)
            # A point never repels itself or its own immediate neighbours along the yarn:
            # consecutive vertices are meant to be close.
            dist[np.abs(idx[:, None] - cand[None, :]) <= 3] = np.inf
            close = dist < contact
            if not close.any():
                continue
            push = np.where(
                close[..., None],
                diff / np.maximum(dist, 1e-9)[..., None]
                * ((contact - np.minimum(dist, contact)) / contact)[..., None], 0.0)
            shift[idx] += push.sum(axis=1) * repulsion * contact * 0.22
        pts += shift

    out = Fabric(L=fab.L, H=fab.H, D=fab.D, yarn_diameter=fab.yarn_diameter)
    at = 0
    for o in fab.ops:
        n = len(o.points)
        out.ops.append(Op(o.kind, o.row, o.position, o.loop_target, o.direction,
                          pts[at:at + n], o.front_loop, o.back_loop, o.pull_through))
        at += n
    return out


def diagnostic_svg(fab: Fabric, *, width: int = 1100) -> str:
    """An inspectable picture of the yarn path, for reading rather than for looking at.

    Segments are drawn back to front by depth, so where one strand passes behind another the
    near one covers it. That is the whole point: over-and-under is the property under test,
    and a flat drawing of the same path would show two lines meeting and tell you nothing
    about which way they meet. Each stitch is tinted by the loop target the CIR gave it, so a
    row of ribbing is visible as ribbing rather than inferred from the chart.

    This is a diagnostic. It is not photography and must never be presented as a product
    image: no material, no light, no camera.
    """
    pts = fab.points
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span_x, span_y = max(hi[0] - lo[0], 1e-6), max(hi[1] - lo[1], 1e-6)
    pad = 24
    scale = (width - 2 * pad) / span_x
    height = int(span_y * scale + 2 * pad)

    def place(p):
        return (pad + (p[0] - lo[0]) * scale, height - pad - (p[1] - lo[1]) * scale)

    tint = {"back": "#b4654a", "front": "#4a7fb4", "both": "#6f6f6f"}
    segs = []
    for o in fab.ops:
        colour = tint.get(o.loop_target, "#6f6f6f") if o.kind == "hdc" else "#9a8f5c"
        for a, b in zip(o.points[:-1], o.points[1:]):
            segs.append((0.5 * (a[2] + b[2]), place(a), place(b), colour))
    segs.sort(key=lambda s: s[0])            # far first, so near strands cover them

    depth = max(hi[2] - lo[2], 1e-6)
    body = []
    for z, (x1, y1), (x2, y2), colour in segs:
        # Thicker and lighter as it comes forward: the yarn has a radius and a near strand
        # occludes a far one.
        t = (z - lo[2]) / depth
        body.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{colour}" stroke-opacity="{0.45 + 0.55 * t:.2f}" '
            f'stroke-width="{fab.yarn_diameter * scale * (0.72 + 0.34 * t):.2f}" '
            f'stroke-linecap="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="#faf7f2"/>'
            + "".join(body) + "</svg>")
