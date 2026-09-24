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

from dataclasses import dataclass, field, replace

import numpy as np

from . import linkage, stitch_shape

# Published proportions (Storck et al. 2022), used as stated.
LOOP_REACH = 1.85          # a loop spans this many stitch pitches in x
CROWN_RISE = 1.23          # a key point rises this fraction of H above the base
# Yarn diameter as a fraction of stitch pitch. Their sample is 0.1 (fine cotton at L=5mm);
# the benchmark garment is worsted at L=6.9mm with roughly 2mm yarn, so ~0.29. Carried as a
# parameter rather than a constant because it is a property of the yarn, not of crochet.
DEFAULT_D_OVER_L = 0.29

# How close two strands may come, as a fraction of yarn diameter. Yarn compresses where it
# crosses, so centres closer than a full diameter are physical; closer than this is not.
#
# ONE constant, used by both the check and the relaxation. They used to disagree: the check
# accepted 0.45 and the relaxation pushed everything to 1.0, so relaxation inflated the
# fabric to a separation neither the check nor real crochet asks for. With thin yarn that was
# invisible. With the correct yarn it tore the fabric apart -- linkage 208 -> 189, and only
# 15 of 224 stitches still shaped like half double crochet.
COMPRESSED_CONTACT = 0.45

# What relaxation AIMS for, which is not the same quantity as the floor above. The floor is
# the point past which yarn cannot be squeezed; this is where two touching strands actually
# rest. Using one number for both made relaxation settle exactly on the limit, so the verdict
# came down to floating point and a fabric could be rejected for being 0.0000001mm inside a
# bound it had been pushed precisely onto.
RESTING_CONTACT = 0.62

# Closing a single loop strand needs a third point off its own line, or the
# 'loop' is a degenerate sliver bounding no area and nothing can pass through it.
# The offset is behind the fabric, where the strand's own stitch body is.
# How far the fictitious closure reaches. A single top loop is a degenerate sliver bounding
# no area, so to ask whether a stitch ENCIRCLES that strand the loop is closed through a
# point off to one side, and the stitch must cross the triangle this spans.
#
# The triangle is fictitious, so its only requirement is that real yarn cannot leave through
# its EDGE -- if it can, a stitch that genuinely wraps the strand scores zero because it
# went around the surface rather than through it. That is a check failing to see what it
# exists to measure, and it happened: at a fixed 6mm the identical-stitch control was fine,
# but once stitches leaned the yarn began escaping past the edge and eleven of forty-two
# certified stitches read as unlinked. The same fabric scored 42/42 at every tail from 12mm
# to 60mm, so the verdict was a property of the tail length, not of the crochet.
#
# So it is derived rather than chosen: no path can get further from its anchor loop than the
# cell's diagonal plus the fabric depth, and twice that cannot be rounded. `_AWAY` remains
# as the fallback for callers without a fabric to measure.
_AWAY = np.array([0.0, -6.0, 0.0])


def _away_reach(fab) -> float:
    """How far the fictitious closure must extend to be a wall rather than a flap."""
    return 2.0 * float(np.hypot(fab.L, fab.H) + fab.D)


def _away_vector(fab, down=None) -> np.ndarray:
    """The fictitious closure offset, sized AND AIMED so real yarn cannot get round it.

    The length was derived earlier, after a fixed 6mm tail let leaning stitches escape past
    the triangle's edge. The DIRECTION had the same defect and kept it longer, because it is
    invisible while the fabric lies in the plane it was built in: a tail fixed along global
    -y stops pointing away from the fabric as soon as the fabric turns. Rigidly rotating the
    certified swatch about z -- which changes nothing physical -- dropped linkage from 42 of
    42 to 3 of 42 at thirty degrees, while rotations about x and y, which leave -y pointing
    along the same part of the cloth, were unaffected. That asymmetry is the signature of a
    global direction being used for a local property.

    It matters for drape rather than for rotation: a curled row has stitches whose "below"
    points in a different direction from their neighbours', so no single global vector can
    serve them all. `down` is the stitch's own -UP from its local frame; the global fallback
    remains only for callers with no frame to offer.
    """
    reach = _away_reach(fab)
    if down is None:
        return np.array([0.0, -reach, 0.0])
    d = np.asarray(down, dtype=float)
    n = float(np.linalg.norm(d))
    if n < 1e-9:
        return np.array([0.0, -reach, 0.0])
    return (d / n) * reach

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
    # The strand the opening yarn-over leaves lying across the back of the stitch, below the
    # V. A half double has one; a single crochet does not, and a double crochet's is consumed
    # by the second pull-through. It is the stitch's signature, so the shape check names it.
    third_loop: tuple[int, int] = (0, 0)


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
    # Where through the fabric's depth this stitch's hook goes down, keyed to which strand
    # it is being worked around. This used to be +/-0.45D, which put the descent level with
    # the very leg it was supposed to pass around: measured segment to segment, the stem
    # came within 0.05mm of the front loop it was threading, against a floor of 1.50mm. The
    # vertex-sampled check reported 2.06mm of clearance for that.
    #
    # The legs of a V sit at about +/-0.43D. A strand passing BETWEEN them (both loops) has
    # to run up the middle; one passing AROUND a single leg (back or front) has to clear it
    # by a yarn's width, not brush along it.
    # The hook always goes DOWN through the mouth of the V -- that is the only way into the
    # fabric -- and what distinguishes the three loop targets is which side it comes back UP.
    # Encircling the back leg means descending in front of it and rising behind it; the
    # front leg is the mirror; both loops together means rising clear behind the whole V.
    #
    # An earlier attempt keyed the DESCENT to the target instead and pushed it outside the
    # leg it was meant to go around, so the stem threaded nothing at all: 3 of 42 linked. An
    # earlier one still put the descent level with the leg, so the stem grazed the very loop
    # it was threading at 0.05mm.
    leg = D * 0.43
    clear = yarn * 0.95
    enter_z = 0.0
    exit_z = +(leg + clear) if loop_target == "front" else -(leg + clear)

    y0 = anchor_top_y                      # the top of the stitch below: where we enter
    yt = y0 + H                            # the top of this stitch
    crown = y0 + CROWN_RISE * H            # published: a key point rises above the top
    c = 0.5 * L                            # the cell's centre: mirror-invariant

    # Named, not numbered. The spans below are derived from these names, because when they
    # were hand-counted indices both of them ran one point long and the error was invisible
    # until a swatch large enough to contain a front-loop stitch was tested. A name cannot
    # drift out of step with the point it names.
    #
    # PROPORTIONS. The published ratios this module started from -- a loop reaching 1.85L
    # along the row, a crown rising 1.23H -- describe a SLIP STITCH. That paper models
    # chains, slip stitches and single crochets, and no half double at all. A slip stitch is
    # a flat stitch whose loops lie over their neighbours; a half double stands upright on a
    # post. Borrowing the slip stitch's sideways reach gave every stitch a pronounced lean
    # and merged the row tops into a continuous bar, because the reach was carrying each
    # stitch most of a pitch sideways for a reason that does not apply to it.
    #
    # So the shape comes from the certified gauge and from documented half double anatomy
    # instead: pitch and height are the gauge's own (here H/L is about 1.5, a stitch taller
    # than it is wide), the post is upright, the top V spans most of a pitch so the next row
    # can work into it while staying distinct from its neighbours, and the opening yarn over
    # leaves its third loop across the back below the V.
    p = [
        # --- yarn over: the wrap, before the hook enters anything ---------------
        # This is the strand that makes a half double a HALF double, and it is why the stitch
        # has a third loop lying across its back below the V. Its y and z match "away" below
        # exactly, so one stitch's exit IS the next stitch's entry and the join is seamless.
        ("yo_wrap",      (0.00 * L, yt - 0.30 * H, +D * 0.46)),
        ("yo_settle",    (0.20 * L, yt - 0.46 * H, +D * 0.26)),

        # --- insert, and pull a loop THROUGH the anchor -------------------------
        # The hook enters in front of the anchor's V, passes THROUGH the opening it bounds,
        # and comes out behind. It does not dive under and return: that routing crossed the
        # opening twice in opposite directions, which is a linking number of zero -- yarn
        # that went in and came back out the way it came, holding on to nothing.
        #
        # The dive clears the anchor strand by a yarn diameter. That clearance is in
        # millimetres of yarn, not a fraction of H: ratios describe centre paths and are
        # silent about thickness, so a dive sized purely from H passed within 0.53mm of a
        # 2mm strand -- through it, not around it.
        ("insert",       (c - 0.11 * L, y0 + 0.16 * H, enter_z + D * 0.16)),
        ("through",      (c - 0.02 * L, y0 + 0.03 * H - yarn, enter_z)),
        ("behind",       (c + 0.10 * L, y0 - 0.04 * H - yarn, exit_z)),
        ("emerge",       (c + 0.11 * L, y0 + 0.16 * H, exit_z * 0.85)),

        # --- the post: upright, not leaning ------------------------------------
        # The two strands of the post are held close in x so they read as one column. Splayed
        # apart they rendered as a thin J-hook hanging off a rail rather than the upright
        # post that gives a half double its height. The post also starts low, just above the
        # V it was worked into, because starting it partway up the row left an empty band
        # between every pair of rows in a fabric that should be dense.
        # Held to the side of the cell centre. Dead centre is where the NEXT row's hook
        # comes down, and the post's crown sat 0.3mm from it -- the two stitches occupied
        # the same millimetre of space and only relaxation pulled them apart afterwards.
        # Clearance belongs in the construction; relaxation is for contact, not for repair.
        ("rise",         (c + 0.15 * L, y0 + 0.62 * H, -D * 0.30)),
        ("crown",        (c + 0.16 * L, yt - 0.16 * H, +D * 0.14)),

        # --- yarn over and pull through all three loops -------------------------
        ("close_near",   (c + 0.16 * L, yt - 0.14 * H, -D * 0.48)),
        ("third_loop",   (c - 0.12 * L, yt - 0.07 * H, -D * 0.40)),

        # --- the two top loops: the two legs of one chain loop ------------------
        # Spans 0.73 of a pitch, not 0.80. At 0.80 the V of one stitch came within 1.489mm
        # of its neighbour's, against a compressed-contact floor of 1.50mm -- adjacent tops
        # pressed very slightly harder together than yarn can be squeezed. A construction
        # fix, not a threshold one.
        # Symmetric about the centre, so they sit at the same fabric x either way. They run
        # in opposite directions -- out along the back, home along the front -- which is why
        # closing the V into a ring must not reverse one of them.
        # A flattened loop lying horizontally, not a wedge. The legs run level and
        # parallel, separated through the fabric rather than in height, joined by a rounded
        # turn. Sloped legs meeting at a point rendered as a row of arrowheads.
        #
        # The loop is traversed OUT to the left and HOME to the right, so it finishes at the
        # right-hand end -- next to where the following stitch begins. Traversed the other
        # way it finished at the left and the yarn then had to sweep the full width of the
        # cell to reach the next stitch. That sweep, paired with the back leg, is what drew
        # the arrowheads: they were never the V, they were the yarn travelling back across a
        # stitch it had already finished.
        #
        # The point set stays symmetric about the cell centre, so the row above still finds
        # the loops in the same place whichever way this row was worked. Only the order of
        # travel mirrors.
        ("back_loop",    (c + 0.300 * L, yt + 0.045 * H, -D * 0.42)),
        ("back_loop_e",  (c - 0.300 * L, yt + 0.055 * H, -D * 0.40)),
        ("v_turn_a",     (c - 0.400 * L, yt + 0.060 * H, -D * 0.22)),
        ("v_turn",       (c - 0.435 * L, yt + 0.065 * H, +D * 0.02)),
        ("v_turn_b",     (c - 0.400 * L, yt + 0.070 * H, +D * 0.26)),
        ("front_loop",   (c - 0.300 * L, yt + 0.075 * H, +D * 0.42)),
        ("front_loop_e", (c + 0.300 * L, yt + 0.065 * H, +D * 0.44)),
        ("away",         (1.00 * L, yt - 0.30 * H, +D * 0.46)),
    ]
    names = [n for n, _ in p]
    p = [xyz for _, xyz in p]
    pts = np.asarray(p, dtype=np.float64)
    if direction < 0:
        # Mirror end for end about the cell centre, and lay the points down in the reverse
        # order, because the yarn travels the other way. Everything another row must find is
        # symmetric about that centre, so it does not move.
        # Mirror the cell about its own centre. Do NOT also reverse the order of the
        # points: the yarn runs through a stitch in the order the stitch is made -- yarn
        # over, insert, pull up, close -- and that sequence does not reverse when the row
        # does. Mirroring alone already puts the entry on the right and the exit on the
        # left, which is what working right to left means. Reversing as well made every
        # cell run backwards, so consecutive stitches met end to end instead of end to
        # start and the yarn jumped two stitch pitches between each pair. That 13.9mm jump
        # sat under a continuity threshold of 2.6 pitches and was reported as continuous
        # for as long as the threshold, rather than the joins, was what got checked.
        pts[:, 0] = L - pts[:, 0]

    def span(first: str, last: str) -> tuple[int, int]:
        a, b = names.index(first), names.index(last)
        return (a, b) if a <= b else (b, a)

    spans = {
        "pull_through": span("insert", "emerge"),
        "back_loop": span("back_loop", "back_loop_e"),
        "front_loop": span("front_loop", "front_loop_e"),
        "third_loop": span("third_loop", "third_loop"),
    }
    return pts, spans


def _turning_chain(L: float, H: float, D: float, direction: int,
                   y_top: float) -> np.ndarray:
    """The transition between rows: a chain stitch that lifts the yarn to the next row.

    The paper is explicit that rows are joined by transition unit cells "partially consisting
    of a chain stitch". My earlier model had none at all, which left each row a separate
    object that happened to sit above the last -- another way the fabric was not one thing.
    """
    # Held clear of the last stitch's top V, which it grazed at exactly the compressed
    # contact distance. A turning chain stands at the edge of the fabric, outside the
    # stitches, so it has the room -- it was only sitting there because nothing had made it
    # move.
    d = direction
    return np.asarray([
        (0.24 * L * d, y_top + 0.08 * H, +D * 0.34),
        (0.52 * L * d, y_top + 0.44 * H, +D * 0.60),
        (0.38 * L * d, y_top + 0.86 * H, -D * 0.08),
        (0.02 * L * d, y_top + 0.94 * H, -D * 0.48),
        (-0.18 * L * d, y_top + 0.60 * H, -D * 0.24),
        (-0.06 * L * d, y_top + 0.18 * H, +D * 0.28),
    ], dtype=np.float64)


def build(twin, gauge, *, max_rows: int | None = None, max_cols: int | None = None,
          d_over_l: float = DEFAULT_D_OVER_L, hand=None) -> Fabric:
    """Translate certified cells into one continuous crochet yarn path.

    `hand` optionally supplies a HandTension, which gives each stitch its own loop length.
    Per Munden that scales the stitch ENVELOPE -- width and height -- and nothing else: the
    yarn diameter comes from the hook and does not change because a stitch was worked
    tighter, so `yarn_d` and `D` stay outside the perturbation. Stitch count, stitch type,
    loop target, working direction and the order the hook makes them in are untouched.
    """
    L = 10.0 / gauge.stitches_per_10cm * 10.0
    H = 10.0 / gauge.rows_per_10cm * 10.0
    # Yarn diameter comes from the hook the pattern specifies, not from a ratio chosen
    # here. It had been L * 0.29 = 2.0mm, a number with no source, and the fabric rendered
    # as open lacework because the strands were about forty per cent too thin to touch.
    #
    # The pattern states a 6mm hook, which is a chunky yarn. Two independent routes agree on
    # what that means: a 6mm hook takes yarn of roughly hook/1.8, and the certified gauge of
    # 14.5 stitches per 10cm gives a 6.9mm stitch whose post is about two strands wide, so
    # roughly 3.45mm. They land within three per cent of each other, which is why this is
    # derived rather than picked.
    hook = getattr(gauge, "hook_mm", None)
    yarn_d = hook / 1.8 if hook else L * d_over_l

    # Fabric depth, derived FROM the yarn rather than from the stitch pitch. It was L * 0.55
    # = 3.79mm, a ratio invented before the yarn diameter was derived and never revisited
    # afterwards, which left a fabric 1.14 yarn diameters deep. Three strands have to fit
    # through that depth -- a back leg, a front leg, and the stem of the next row passing
    # between them -- so a depth of barely one strand makes the V's opening too narrow for
    # the yarn that has to thread it. That is what pinned the geometry between two failures
    # it could not satisfy at once: threading the loop meant grazing its legs at 0.05mm, and
    # clearing the legs meant not threading the loop at all.
    #
    # Two diameters is the floor for a fabric that must hold two strands through its depth;
    # 2.2 leaves the stem room to pass between them. The multiplier is ESTIMATED -- it is
    # not in the pattern -- but it is bounded below by what has to physically fit.
    D = yarn_d * 2.2
    fab = Fabric(L=L, H=H, D=D, yarn_diameter=yarn_d)

    rows = sorted({c.row for c in twin.cells})
    if max_rows:
        rows = rows[:max_rows]
    by_row = {r: sorted((c for c in twin.cells if c.row == r), key=lambda c: c.position)
              for r in rows}
    ncols = max((len(v) for v in by_row.values()), default=0)
    if max_cols:
        ncols = min(ncols, max_cols)

    # Hand tension, if a hand is making this rather than a machine. The field is anchored so
    # every row still spans exactly ncols * L and the rows still total len(rows) * H; what
    # varies is how that fixed span is divided between the stitches.
    if hand is not None:
        from .hand_tension import tension_field
        cell_w, row_h, _ = tension_field(len(rows), ncols, L, H, hand)
    else:
        cell_w = np.full((len(rows), ncols), L)
        row_h = np.full(len(rows), H)
    # Left edge of each stitch, accumulated along the row. A loose stitch pushes the ones
    # after it along, exactly as it does in the hand; the anchor guarantees the row still
    # ends where the certified fabric ends.
    left = np.concatenate([np.zeros((len(rows), 1)), np.cumsum(cell_w, axis=1)], axis=1)
    top = np.concatenate([[0.0], np.cumsum(row_h)])

    for ri, r in enumerate(rows):
        direction = 1 if ri % 2 == 0 else -1
        cells = [c for c in by_row[r]
                 if getattr(c, "fabric_position", c.position) < ncols][:ncols]
        # Laid down in the order the hook makes them. Emitting in position order on a
        # right-to-left row left the yarn jumping the width of the panel at every reversal,
        # which the continuity check caught as a 35mm break.
        cells.sort(key=lambda x: getattr(x, "fabric_position", x.position),
                   reverse=direction < 0)
        anchor_top_y = top[ri]
        if ri and fab.ops:
            # At the end of the row just worked, not at x=0. Emitting it at the origin left
            # the yarn jumping the full width of the panel at every reversal -- 35mm, which
            # the continuity check reported as a break rather than a path.
            tail = fab.ops[-1].points[-1]
            turn = _turning_chain(L, row_h[ri], D, direction, anchor_top_y)
            turn = turn + np.array([tail[0] - turn[0, 0], 0.0, 0.0])
            fab.ops.append(Op("turn", r, -1, "both", direction, turn))
        for c in cells:
            fp = getattr(c, "fabric_position", c.position)
            pts, spans = _hdc_cell(cell_w[ri, fp], row_h[ri], D, direction,
                                   getattr(c, "loop", "both"),
                                   anchor_top_y, fab.yarn_diameter)
            pts = pts + np.array([left[ri, fp], 0.0, 0.0])
            if ri:
                # THE STITCH LEANS. With varying widths, row ri's stitch centres no longer
                # sit above row ri-1's, so a cell placed squarely on its own centre reaches
                # down for an anchor that has moved -- which is exactly what the validator
                # caught: linkage fell to 38 of 42. The hook does not have this problem,
                # because it goes into the stitch that is actually there, wherever the
                # previous row left it. So the cell's foot is placed on the anchor's centre
                # and its top on its own, and the stitch leans between them. Leaning is what
                # real crochet does when tension varies; it is not a correction applied to
                # make a check pass, and the check is what proved it was needed.
                own_c = left[ri, fp] + 0.5 * cell_w[ri, fp]
                anchor_c = left[ri - 1, fp] + 0.5 * cell_w[ri - 1, fp]
                lean = np.clip(1.0 - (pts[:, 1] - anchor_top_y) / row_h[ri], 0.0, 1.0)
                pts[:, 0] += (anchor_c - own_c) * lean
            fab.ops.append(Op("hdc", r, fp, getattr(c, "loop", "both"), direction, pts,
                              front_loop=spans["front_loop"], back_loop=spans["back_loop"],
                              pull_through=spans["pull_through"],
                              third_loop=spans["third_loop"]))
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
        checks["largest_gap_mm"] = round(float(steps.max()), 3)
        checks["median_step_mm"] = round(float(np.median(steps)), 3)

    # Continuity is checked at the JOINS between operations, not by thresholding the largest
    # step anywhere in the path. The threshold version asked whether any step exceeded 2.6
    # stitch pitches, and a real 13.9mm discontinuity -- every pair of adjacent stitches in
    # every right-to-left row failed to meet -- sat quietly underneath it and was reported as
    # continuous. What makes yarn continuous is that each operation begins where the last one
    # ended, so that is what is measured, and the two kinds of join are judged by what the
    # construction actually requires of them rather than by one shared number.
    same_row, at_turn = [], []
    for a, b in zip(fab.ops[:-1], fab.ops[1:]):
        gap = float(np.linalg.norm(b.points[0] - a.points[-1]))
        if a.kind == "hdc" and b.kind == "hdc" and a.row == b.row:
            same_row.append(gap)
        else:
            at_turn.append(gap)
    if same_row:
        checks["largest_join_within_a_row_mm"] = round(max(same_row), 3)
        # Consecutive stitches in a row stand one pitch apart, so the yarn between them
        # cannot need more than that.
        if max(same_row) > fab.L:
            findings.append(
                f"the yarn jumps {max(same_row):.1f}mm between neighbouring stitches in a "
                f"row, further than the {fab.L:.1f}mm that separates them: the path is in "
                f"pieces rather than continuous")
    if at_turn:
        checks["largest_join_at_a_turn_mm"] = round(max(at_turn), 3)
        # A turn climbs a row and steps sideways; it cannot legitimately need more.
        if max(at_turn) > fab.H + fab.L:
            findings.append(
                f"the yarn jumps {max(at_turn):.1f}mm at a row transition, further than "
                f"climbing one row and stepping one stitch would need")

    # --- row-to-row connectivity -------------------------------------------
    checks["turning_chains"] = len(turns)
    if rows and len(turns) != len(rows) - 1:
        findings.append(f"{len(turns)} turning chains for {len(rows)} rows: the rows are not "
                        f"joined into one piece")

    # --- THE LINKAGE CHECK --------------------------------------------------
    # Every stitch above the first row must be drawn through the loop of the stitch below.
    #
    # This is measured as a LINKING NUMBER between two closed curves, which is an integer
    # topological invariant. It replaced three separate hand-rolled tests -- a crossing
    # parity, a ribbon-encirclement count and a ring-threading test -- and the reason is not
    # that they failed but that they measured the wrong kind of property: each counted
    # crossings on a sub-path cut at an arbitrary index, so the parity moved with the cut
    # rather than with the yarn. Cut the same correct stitch two points earlier and the
    # verdict flipped. A linking number cannot do that.
    #
    # Which curve depends on the loop target, and the three cases are genuinely different
    # geometry, not three settings of one knob:
    #
    #   both  -- the two "loops" at a stitch top are the two legs of ONE chain loop. Working
    #            under both means the hook goes through the opening that loop bounds, so the
    #            curve is that whole loop, closed.
    #   back  -- only the back leg is picked up, so the new yarn encircles that single strand
    #   front -- likewise the front leg.
    linked, unlinked = 0, []
    unmeasurable: list[tuple[int, int]] = []
    numbers: list[int] = []
    by_key = {(o.row, o.position): o for o in hdc}

    # The fabric's own three directions at every stitch, computed once and used by BOTH the
    # linkage check (to aim the fictitious closure along the cloth's local down) and the
    # morphology check (to measure the stitch's features against the cloth rather than
    # against the world). Sharing one frame is deliberate: these two checks disagreeing about
    # which way is "down" at the same stitch is a defect waiting to happen.
    def _frame_for(o):
        ahead = by_key.get((o.row, o.position + 1))
        behind_n = by_key.get((o.row, o.position - 1))
        ri = rows.index(o.row)
        anchor_op = by_key.get((rows[ri - 1], o.position)) if ri > 0 else None
        flip_up = False
        if anchor_op is None and ri + 1 < len(rows):
            # The foundation row has nothing below it, but the stitch ABOVE defines the same
            # wale line, so the frame is recoverable rather than absent. Using it is not a
            # concession: the wale direction is a property of the column of stitches, and
            # either neighbour in that column determines it. Declaring the whole foundation
            # row unmeasurable would have been the instrument giving up where the fabric is
            # perfectly well defined.
            anchor_op = by_key.get((rows[ri + 1], o.position))
            flip_up = True
        if anchor_op is None:
            raise stitch_shape.Unframeable("no neighbour in this stitch's column")
        across, up, through = stitch_shape.local_frame(
            o, ahead if ahead is not None else behind_n, anchor_op,
            neighbour_is_ahead=ahead is not None)
        if flip_up:
            up = -up
            through = -through
        return across, up, through

    frames: dict = {}
    for o in hdc:
        try:
            frames[(o.row, o.position)] = _frame_for(o)
        except stitch_shape.Unframeable:
            frames[(o.row, o.position)] = None

    for o in hdc:
        anchor = by_key.get((rows[rows.index(o.row) - 1], o.position)) \
            if rows.index(o.row) > 0 else None
        if anchor is None:
            continue
        a_frame = frames.get((anchor.row, anchor.position))
        away = _away_vector(fab, None if a_frame is None else -a_frame[1])
        back = anchor.points[anchor.back_loop[0]:anchor.back_loop[1] + 1]
        front = anchor.points[anchor.front_loop[0]:anchor.front_loop[1] + 1]
        if o.loop_target == "front":
            target = linkage.close_arc(np.vstack([front, front.mean(axis=0) + away]))
        elif o.loop_target == "back":
            target = linkage.close_arc(np.vstack([back, back.mean(axis=0) + away]))
        else:
            # NOT front[::-1]. The two legs of a V already run in opposite directions --
            # the yarn travels out along the back leg and returns along the front -- so
            # reversing one folds the quadrilateral into a bowtie. A self-intersecting ring
            # has a folded spanning surface, and every one of these stitches scored a
            # linking number of 2: one crossing counted twice by the fold.
            target = linkage.close_arc(np.vstack([back, front]))
        try:
            lk = linkage.link_with_open_path(target, o.points)
        except (linkage.CurvesIntersect, ValueError):
            unmeasurable.append((o.row, o.position))
            continue
        numbers.append(lk)
        if lk != 0:
            linked += 1
        else:
            unlinked.append((o.row, o.position))

    checks["stitches_needing_linkage"] = linked + len(unlinked) + len(unmeasurable)
    checks["stitches_linked"] = linked
    checks["stitches_unmeasurable"] = len(unmeasurable)
    checks["unlinked"] = unlinked[:8]
    if numbers:
        checks["linking_numbers"] = sorted(set(numbers))
    if unlinked:
        findings.append(
            f"{len(unlinked)} of {linked + len(unlinked)} stitches have linking number zero "
            f"with the loop below: they pass beside it, or dip under and come back the way "
            f"they went. Strands that meet without passing through one another are netting")
    if unmeasurable:
        findings.append(
            f"{len(unmeasurable)} stitches touch the loop they are worked into, so their "
            f"linking number is undefined rather than zero")

    # --- IS IT ACTUALLY A HALF DOUBLE CROCHET -------------------------------
    # Linkage says a strand passes through the loop below. A straight rod dropped through a
    # hole satisfies that, and so does a knitted loop. This asks the separate question of
    # whether the thing doing the passing has the structure of the stitch the CIR ordered.
    misshapen: list[tuple[int, int, str]] = []
    # The LAST stitch worked is the free end of the yarn. Its loop is still live -- in real
    # crochet you fasten off, and nothing here does -- so it has no completed top to be
    # shaped like, and relaxation pulls it about because nothing holds it. That is a boundary
    # condition with a physical reason, not a malformed stitch, and the two are different
    # facts: counting the yarn end as a shape failure would report a defect that is not
    # there, and silently exempting it would hide one that might be. It is reported on its
    # own line.
    terminal = None
    for o in fab.ops:
        if o.kind == "hdc":
            terminal = (o.row, o.position)
    loose_end: list[str] = []
    unframeable: list[tuple[int, int]] = []
    for o in hdc:
        # The frame this stitch's shape is measured in, built from its own neighbours so it
        # travels with the cloth. Global axes were used here until a rigid rotation -- which
        # changes nothing physical -- dropped the verdict from 49 of 49 correctly shaped to
        # 0 of 49 at thirty degrees. See stitch_shape for why that had to go before the
        # fabric was allowed out of its plane.
        frame = frames.get((o.row, o.position))
        if frame is None:
            unframeable.append((o.row, o.position))
            continue
        complaints = stitch_shape.shape_report(o, fab.L, fab.H, fab.D, frame)
        if not complaints:
            continue
        if (o.row, o.position) == terminal:
            loose_end.append(complaints[0])
        else:
            misshapen.append((o.row, o.position, complaints[0]))
    checks["stitches_shaped_like_hdc"] = (len(hdc) - len(misshapen) - len(loose_end)
                                         - len(unframeable))
    # A stitch with no neighbour to orient it is not a passing stitch. The foundation row has
    # no anchor below it and so cannot be framed; that is a real limit of the measurement and
    # is reported as one rather than absorbed into the pass count.
    checks["stitches_unframeable"] = len(unframeable)
    checks["terminal_stitch_unfastened"] = bool(loose_end)
    checks["misshapen"] = [f"r{r} p{p}: {m}" for r, p, m in misshapen[:4]]
    if misshapen:
        seen = sorted({m for _, _, m in misshapen})
        findings.append(
            f"{len(misshapen)} of {len(hdc)} stitches are not shaped like a half double "
            f"crochet: {seen[0]}")

    # --- no impossible intersections ---------------------------------------
    # Yarn cannot occupy the same space as yarn. Measured between SEGMENTS: the version this
    # replaces sampled vertices, and reported 2.06mm of clearance for a fabric whose strands
    # were 0.05mm apart. That is not a tighter tolerance on the same quantity, it is a
    # different quantity -- two 3mm segments cross through each other while their four
    # endpoints stay far apart, and it is the segment that cannot pass through anything.
    gap, offenders = min_segment_separation(pts, fab.yarn_diameter)
    checks["closest_non_adjacent_mm"] = round(gap, 4)
    checks["closest_pair_segments"] = list(offenders)
    floor = fab.yarn_diameter * COMPRESSED_CONTACT
    checks["contact_floor_mm"] = round(floor, 3)
    if gap < floor:
        findings.append(f"two strands come within {gap:.3f}mm, closer than yarn can compress "
                        f"at {fab.yarn_diameter:.2f}mm diameter (floor {floor:.2f}mm)")

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
    contact = fab.yarn_diameter * RESTING_CONTACT
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
        # replace(), not a hand-listed constructor call. The hand-listed version silently
        # dropped third_loop the moment that field was added -- every settled stitch claimed
        # its third loop was at index zero, and half of them then failed the shape check for
        # a reason that had nothing to do with their shape. Copying by field name means a
        # field added later cannot be forgotten here.
        out.ops.append(replace(o, points=pts[at:at + n]))
        at += n
    return out



def closest_between_segments(p, u, q, v):
    """Closest points between two batches of segments p+s*u and q+t*v, s,t in [0,1]."""
    w = p - q
    a = np.einsum("ij,ij->i", u, u)
    b = np.einsum("ij,ij->i", u, v)
    c = np.einsum("ij,ij->i", v, v)
    dd = np.einsum("ij,ij->i", u, w)
    e = np.einsum("ij,ij->i", v, w)
    denom = a * c - b * b
    parallel = denom < 1e-12
    safe = np.where(parallel, 1.0, denom)
    s_par = np.clip(np.where(parallel, 0.0, (b * e - c * dd) / safe), 0.0, 1.0)
    t_par = np.clip((b * s_par + e) / np.where(c < 1e-12, 1.0, c), 0.0, 1.0)
    s_par = np.clip((b * t_par - dd) / np.where(a < 1e-12, 1.0, a), 0.0, 1.0)
    diff = (p + s_par[:, None] * u) - (q + t_par[:, None] * v)
    return s_par, t_par, np.linalg.norm(diff, axis=1)


def min_segment_separation(pts: np.ndarray, yarn_diameter: float) -> tuple[float, tuple]:
    """Closest approach between two parts of the yarn that are not the same bend.

    SEGMENT to segment, not vertex to vertex. The vertex-sampled version this replaces
    reported 2.06mm for a path whose strands were really 0.05mm apart, because yarn segments
    here are about 3mm long and two of them can cross clean through each other while all four
    endpoints stay far apart. Vertex proximity is not strand proximity, and the strand is the
    thing that cannot pass through itself.

    Two exclusions, and both are needed:

      * segments sharing a vertex, which touch by definition;
      * segments closer together ALONG THE YARN than half the tightest bend it can make,
        pi * radius. A strand doubling back on itself really is in contact with itself there,
        and that is a bend, not an interpenetration.

    The second is measured in arc length rather than in index. Index distance was the first
    attempt and is not a physical quantity: these segments run from microns to millimetres,
    so a fixed index gap means different things in different places.
    """
    a0 = pts[:-1]
    d = np.diff(pts, axis=0)
    seg = np.linalg.norm(d, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    mid = 0.5 * (arc[:-1] + arc[1:])
    live = np.nonzero(seg > 1e-6)[0]
    apart = np.pi * (yarn_diameter / 2.0)

    best = float("inf")
    where: tuple = ()
    for k, i in enumerate(live):
        j = live[k + 1:]
        j = j[(j - i > 1) & (np.abs(mid[j] - mid[i]) > apart)]
        if not len(j):
            continue
        _, _, dist = closest_between_segments(
            np.repeat(a0[i][None], len(j), 0), np.repeat(d[i][None], len(j), 0), a0[j], d[j])
        m = int(dist.argmin())
        if dist[m] < best:
            best = float(dist[m])
            where = (int(i), int(j[m]))
    return best, where


def coverage(fab: Fabric) -> dict:
    """Which semantic states this fabric actually contains.

    Written because a 4x5 swatch was used to prove the topology and it turned out to contain
    no front-loop stitch at all -- the one class that was broken. "Fifteen of fifteen linked"
    was true and meant nothing. A fixture that does not contain a case cannot have tested it,
    so the cases are enumerated and counted rather than assumed.
    """
    hdc = [o for o in fab.ops if o.kind == "hdc"]
    rows = sorted({o.row for o in hdc})
    anchored = {(o.row, o.position) for o in hdc if o.row != (rows[0] if rows else None)}
    states = {
        "loop_target_both": sum(1 for o in hdc if o.loop_target == "both"),
        "loop_target_back": sum(1 for o in hdc if o.loop_target == "back"),
        "loop_target_front": sum(1 for o in hdc if o.loop_target == "front"),
        "worked_left_to_right": sum(1 for o in hdc if o.direction > 0),
        "worked_right_to_left": sum(1 for o in hdc if o.direction < 0),
        "row_start_or_end": sum(1 for o in hdc
                                if o.position in (min(x.position for x in hdc),
                                                  max(x.position for x in hdc))),
        "anchored_in_a_row_below": len(anchored),
        "turning_chains": sum(1 for o in fab.ops if o.kind == "turn"),
    }
    # Each loop target must appear in BOTH working directions, because the cell is mirrored
    # for right-to-left rows and a defect can live in one mirror only. Defect 4 did.
    pairs = {(o.loop_target, o.direction) for o in hdc}
    states["loop_target_x_direction"] = len(pairs)
    missing = [k for k, v in states.items() if v == 0]
    if len(pairs) < 6:
        missing.append(f"only {len(pairs)} of 6 loop-target/direction combinations")
    states["missing"] = missing
    states["complete"] = not missing
    return states


def reconciles_with_gauge(fab: Fabric, twin, gauge, *,
                          expected_mm_per_stitch: float | None = None) -> dict:
    """Does the built geometry agree with the certified pattern's own numbers?

    Two comparisons, and they are not equally strong.

    The stitch pitch and row height are taken FROM the gauge, so agreement there confirms
    the geometry was built to spec and nothing drifted -- it is not independent evidence
    that the spec is right.

    Yarn consumed per stitch is closer to independent: it comes from the grams the pattern
    states, and nothing in this module knows that number. But converting grams to metres
    needs a linear density that is assumed rather than stated, and the key-point path is a
    polyline rather than the smooth curve real yarn follows, so it can catch a stitch that
    eats twice the yarn it should and cannot adjudicate ten per cent. It is reported with
    that limit attached rather than dressed up as a tight tolerance.
    """
    hdc = [o for o in fab.ops if o.kind == "hdc"]
    out: dict = {}
    if not hdc:
        return out
    expected_pitch = 100.0 / gauge.stitches_per_10cm
    expected_row = 100.0 / gauge.rows_per_10cm
    out["stitch_pitch_mm"] = round(fab.L, 3)
    out["expected_pitch_mm"] = round(expected_pitch, 3)
    out["row_height_mm"] = round(fab.H, 3)
    out["expected_row_height_mm"] = round(expected_row, 3)
    out["pitch_matches_gauge"] = abs(fab.L - expected_pitch) < 0.05 * expected_pitch
    out["row_height_matches_gauge"] = abs(fab.H - expected_row) < 0.05 * expected_row
    out["yarn_mm_per_stitch"] = round(float(np.mean(
        [np.linalg.norm(np.diff(o.points, axis=0), axis=1).sum() for o in hdc])), 2)
    if expected_mm_per_stitch:
        ratio = out["yarn_mm_per_stitch"] / expected_mm_per_stitch
        out["yarn_vs_pattern_ratio"] = round(ratio, 3)
        # A factor of two either way is a different stitch. Anything inside that is within
        # what the assumed linear density and the polyline path can account for, and this
        # check is not entitled to a stronger opinion than that.
        out["yarn_per_stitch_is_the_right_order"] = 0.5 <= ratio <= 2.0
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
