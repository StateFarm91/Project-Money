"""Is this actually a half double crochet, or merely a curve that links the right loop?

The topology checks answer a narrow question: does this strand pass through that one. A
straight rod dropped through a hole answers it correctly, and so does a knitted loop. Neither
is crochet. Everything here is about morphology -- the structural features that make a half
double a half double and not a single, a double, or a piece of string.

The features are taken from how the stitch is made, not from how this codebase happens to
draw it:

    yarn over            <- the strand that makes it a HALF double
    insert into the anchor
    pull up a loop       <- three loops now on the hook
    yarn over, pull through all three

Two consequences of that sequence are externally documented, structural, and measurable:

  * The opening yarn over leaves a strand lying across the BACK of the finished stitch, just
    below the top V. Crocheters call it the third loop and work into it deliberately for
    texture. A single crochet has no yarn over and therefore no third loop at all; a double
    crochet's is consumed by its second pull-through. Its presence, behind the fabric and
    below the V, is the signature of this stitch specifically.

  * The stitch stands two chains tall. That is a ratio to the row gauge, which comes from the
    certified pattern rather than from any choice made here.

The top V is two legs of ONE chain loop, so they run in opposite directions -- out along the
back, home along the front. A "V" whose legs run the same way is not a loop, it is a fold,
and nothing can be worked into it.

Thresholds are deliberately loose. This check exists to reject a stitch that is the wrong
KIND of thing, not to police millimetres, and a tight threshold here would be a tuned
constant pretending to be a law.

WHY EVERY MEASUREMENT IS TAKEN IN A LOCAL FRAME. The first version of this file read the
features off the global axes: "behind" meant -z, "below" and "height" meant y, the V ran
along x. That works for exactly as long as the fabric lies flat in the plane it was built in,
and it is not a description of crochet -- it is a description of crochet lying still. Rigidly
rotating the certified fabric, which changes no physical property of it whatsoever, collapsed
the verdict from 49 of 49 stitches correctly shaped to 2 of 49 at fifteen degrees and 0 of 49
at thirty. The stitches were not deformed. The instrument was measuring orientation.

That mattered the moment the fabric was allowed out of its plane, because a draped fabric is
a rotated one everywhere at once: each stitch sits on a surface with its own normal, and a
row that curls has stitches whose "behind" points in a different direction from their
neighbours'. Grandfathering the planar version would have meant every draped stitch failing a
morphology check for a reason that has nothing to do with morphology, and the obvious
response -- flattening the fabric until the check passed again -- would have been deforming a
correct product to satisfy a broken instrument.

So each stitch is measured against a frame built from its own neighbours:

    ACROSS   the course direction, from this stitch towards the next along its row
    UP       the wale direction, from the anchor it was worked into towards this stitch
    THROUGH  across x up, which points out of the FRONT face of the fabric

These are the same three directions the planar version assumed, derived per stitch instead of
assumed globally, so on flat fabric the two agree exactly. Under rotation, drape or curl the
frame travels with the cloth and the verdicts do not move. A stitch with no neighbour to
build a frame from is reported UNMEASURABLE rather than passed, because a check that cannot
see its subject must never be the cheapest way to get a pass.
"""
from __future__ import annotations

import numpy as np

__all__ = ["shape_report", "local_frame", "shape_margins", "MORPHOLOGY", "Unframeable"]

MORPHOLOGY = (
    "a third loop behind the fabric, below the top V",
    "a top V of two legs running in opposite directions",
    "a top V wide enough for the next row to work into",
    "a post that stands about one row height tall",
    "a path that climbs from the anchor to its own top",
)


class Unframeable(Exception):
    """This stitch has no neighbours to orient it, so its shape cannot be measured."""


def _span(points, lo_hi):
    a, b = lo_hi
    return points[a:b + 1]


def _unit(v):
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        raise Unframeable("a frame direction collapsed to zero length")
    return v / n


def rigid_rotation(rest: np.ndarray, now: np.ndarray) -> np.ndarray:
    """The proper rotation that best carries `rest` onto `now` (centroids removed): the polar
    factor of the cross-covariance, by SVD with the reflection excluded. Kabsch/Umeyama."""
    q = np.asarray(rest, float); p = np.asarray(now, float)
    h = (q - q.mean(axis=0)).T @ (p - p.mean(axis=0))
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    return vt.T @ np.diag([1.0, 1.0, d]) @ u.T


def carried_frame(op, reference_op, reference_frame):
    """The reference stitch's frame, carried by THIS stitch's own rigid motion since then.

    WHY A SECOND WAY TO FRAME A STITCH. `local_frame` builds the frame from neighbours so
    that it travels with the cloth, and on a flat or gently curved fabric that is right. On
    a fabric that actually drapes it is not: measured on the 5x5 over a sphere with every
    stitch held rigid to 0.1mm, the neighbour frame's UP sat 17-19.5 degrees off the
    stitch's own, and four intact stitches -- third loop 1.6mm below the V in their own
    frame, exactly as certified -- were reported everted. A frame borrowed from a neighbour
    that has rotated 20 degrees away measures the neighbour's rotation, not this stitch's
    shape.

    So on a deformed fabric the frame is the certified stitch's own frame, rotated by the
    least-squares rigid motion of ALL this stitch's points since certification. That is not
    self-reference: the reference shape was validated in its own right, the rotation is
    fitted over every point of the stitch, and a loop that has moved 2mm out of place cannot
    rotate that fit enough to hide itself -- `test_stitch_identity` everts one to prove it.
    """
    r = rigid_rotation(reference_op.points, op.points)
    return tuple(r @ np.asarray(a, float) for a in reference_frame)


def local_frame(op, row_neighbour=None, anchor=None, neighbour_is_ahead: bool = True):
    """The fabric's own three directions at this stitch: (across, up, through).

    `row_neighbour` is an adjacent stitch in the SAME row and `anchor` the stitch in the row
    below that this one was worked into. Both are ordinary stitches of the fabric, so the
    frame bends with the cloth: this is what makes the morphology checks mean the same thing
    on a flat swatch and on a draped one.

    `neighbour_is_ahead` says whether `row_neighbour` sits at a higher fabric position, so
    that ACROSS points consistently along the row regardless of which side had a neighbour to
    offer. Getting that backwards would mirror the frame and turn every stitch's V into a
    fold, which is why it is passed explicitly rather than guessed from coordinates.
    """
    if row_neighbour is None or anchor is None:
        raise Unframeable("a stitch needs a neighbour along its row and the anchor below it")
    here = op.points.mean(axis=0)
    across = _unit((row_neighbour.points.mean(axis=0) - here)
                   * (1.0 if neighbour_is_ahead else -1.0))
    up_raw = here - anchor.points.mean(axis=0)
    # Orthogonalise UP against ACROSS. They are close to perpendicular in flat fabric and
    # drift apart as it deforms; projecting keeps the frame orthonormal without pretending
    # the fabric is undeformed.
    up = _unit(up_raw - np.dot(up_raw, across) * across)
    through = _unit(np.cross(across, up))
    return across, up, through


def shape_report(op, L: float, H: float, D: float, frame) -> list[str]:
    """Structural complaints about one stitch. Empty means it looks like an HDC.

    `frame` is the (across, up, through) triple from `local_frame`. It is required rather
    than defaulted to the global axes, because a default would silently reinstate exactly the
    planar assumption this signature exists to remove.
    """
    across, up, through = frame
    out: list[str] = []
    pts = op.points
    back = _span(pts, op.back_loop)
    front = _span(pts, op.front_loop)
    kind = getattr(op, "kind", "hdc")
    if len(back) < 2 or len(front) < 2:
        return ["the stitch does not name its own loops"]

    def along(p, axis):
        return np.asarray(p) @ axis

    v_up = float(min(along(back, up).min(), along(front, up).min()))

    # --- the third loop: the family's signature, checked in BOTH directions ------------
    # A half double's opening yarn over leaves a strand behind the fabric below the V; a
    # single crochet has no opening yarn over and so has no such strand. So an hdc without
    # one is an sc wearing the wrong label, and an sc that names one is an hdc wearing the
    # wrong label. Neither is a near miss, and neither is silently accepted.
    if kind == "sc":
        if op.third_loop is not None:
            out.append("a single crochet names a third loop: this cell carries an opening "
                       "yarn over, which makes it a half double rather than a single crochet")
    else:
        third = _span(pts, op.third_loop) if op.third_loop is not None else pts[0:0]
        if len(third) < 1:
            return ["the stitch does not name its own loops"]
        if along(third, through).mean() >= along(front, through).mean():
            out.append("no third loop behind the fabric: the opening yarn over is missing, "
                       "which makes this a single crochet rather than a half double")
        if along(third, up).mean() > v_up:
            out.append("the third loop sits above the top V instead of below it")

    # --- the top V ------------------------------------------------------------
    back_run = float(along(back[-1], across) - along(back[0], across))
    front_run = float(along(front[-1], across) - along(front[0], across))
    if back_run * front_run > 0:
        out.append("the two top loops run the same way, so they are a fold rather than a "
                   "loop and nothing can be worked into them")
    v_width = max(abs(back_run), abs(front_run))
    if v_width < 0.35 * L:
        out.append(f"the top V spans {v_width:.1f}mm of a {L:.1f}mm stitch: too narrow for "
                   f"the next row to work into")
    # The two legs must be separated through the fabric, or there is no opening between them.
    if abs(float(along(front, through).mean() - along(back, through).mean())) < 0.25 * D:
        out.append("the front and back loops lie on top of one another, leaving no opening")

    # --- the post -------------------------------------------------------------
    rise_axis = along(pts, up)
    rise = float(rise_axis.max() - rise_axis.min())
    if not 0.55 * H <= rise <= 2.6 * H:
        out.append(f"the stitch rises {rise:.1f}mm where a row is {H:.1f}mm: this is not a "
                   f"{'single' if kind == 'sc' else 'half double'} crochet's height")

    # --- it must climb --------------------------------------------------------
    # A stitch starts at the row below and finishes at its own top. One that ends lower than
    # it started is not standing up.
    if float(rise_axis[-1] - rise_axis.min()) < 0.25 * H:
        out.append("the stitch does not finish above the row it was worked into")
    return out


def shape_margins(op, L: float, H: float, D: float, frame) -> dict:
    """How far each morphology feature is from failing, in millimetres.

    The pass/fail report cannot tell a stitch that is 0.02mm the wrong side of a threshold
    from one that has been turned inside out, and those need different responses: the first
    is a threshold with no tolerance, the second is a deformed product. When out-of-plane
    freedom was first enabled, three edge stitches failed the third-loop test and this was
    what separated the cases -- flat, every stitch sat 1.5 to 1.7mm clear with none within
    0.5mm of the line, and draped, two of them had moved by +4.6mm and +7.0mm. That is not a
    threshold being grazed, and it stopped the failure being written off as strictness.

    Negative is correct in every entry, so the worst value is the maximum.
    """
    across, up, through = frame
    pts = op.points
    back = _span(pts, op.back_loop)
    front = _span(pts, op.front_loop)
    has_third = op.third_loop is not None
    third = _span(pts, op.third_loop) if has_third else pts[0:0]
    if len(back) < 2 or len(front) < 2 or (has_third and len(third) < 1):
        return {}
    v_up = float(min((back @ up).min(), (front @ up).min()))
    back_run = float((back[-1] @ across) - (back[0] @ across))
    front_run = float((front[-1] @ across) - (front[0] @ across))
    return {
        # Absent for a single crochet: there is no third loop to measure, and a margin for a
        # strand that does not exist would be a number about nothing.
        **({"third_loop_below_v_mm": float((third @ up).mean() - v_up),
            "third_loop_behind_front_mm": float((third @ through).mean()
                                                - (front @ through).mean())}
           if has_third else {}),
        "v_legs_opposed": -abs(back_run * front_run) if back_run * front_run < 0
                          else abs(back_run * front_run),
        "v_width_margin_mm": float(0.35 * L - max(abs(back_run), abs(front_run))),
        "leg_separation_margin_mm": float(
            0.25 * D - abs((front @ through).mean() - (back @ through).mean())),
    }
