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
"""
from __future__ import annotations

import numpy as np

__all__ = ["shape_report", "MORPHOLOGY"]

MORPHOLOGY = (
    "a third loop behind the fabric, below the top V",
    "a top V of two legs running in opposite directions",
    "a top V wide enough for the next row to work into",
    "a post that stands about one row height tall",
    "a path that climbs from the anchor to its own top",
)


def _span(points, lo_hi):
    a, b = lo_hi
    return points[a:b + 1]


def shape_report(op, L: float, H: float, D: float) -> list[str]:
    """Structural complaints about one stitch. Empty means it looks like an HDC."""
    out: list[str] = []
    pts = op.points
    back = _span(pts, op.back_loop)
    front = _span(pts, op.front_loop)
    third = _span(pts, op.third_loop)
    if len(back) < 2 or len(front) < 2 or len(third) < 1:
        return ["the stitch does not name its own loops"]

    v_y = float(min(back[:, 1].min(), front[:, 1].min()))

    # --- the third loop -------------------------------------------------------
    # Behind the front leg, and below the V. A stitch drawn without the opening yarn over
    # has nothing here, and that is exactly the difference between this and a single crochet.
    if third[:, 2].mean() >= front[:, 2].mean():
        out.append("no third loop behind the fabric: the opening yarn over is missing, "
                   "which makes this a single crochet rather than a half double")
    if third[:, 1].mean() > v_y:
        out.append("the third loop sits above the top V instead of below it")

    # --- the top V ------------------------------------------------------------
    back_run = float(back[-1, 0] - back[0, 0])
    front_run = float(front[-1, 0] - front[0, 0])
    if back_run * front_run > 0:
        out.append("the two top loops run the same way, so they are a fold rather than a "
                   "loop and nothing can be worked into them")
    v_width = max(abs(back_run), abs(front_run))
    if v_width < 0.35 * L:
        out.append(f"the top V spans {v_width:.1f}mm of a {L:.1f}mm stitch: too narrow for "
                   f"the next row to work into")
    # The two legs must be separated through the fabric, or there is no opening between them.
    if abs(float(front[:, 2].mean() - back[:, 2].mean())) < 0.25 * D:
        out.append("the front and back loops lie on top of one another, leaving no opening")

    # --- the post -------------------------------------------------------------
    rise = float(pts[:, 1].max() - pts[:, 1].min())
    if not 0.55 * H <= rise <= 2.6 * H:
        out.append(f"the stitch rises {rise:.1f}mm where a row is {H:.1f}mm: this is not a "
                   f"half double's height")

    # --- it must climb --------------------------------------------------------
    # A stitch starts at the row below and finishes at its own top. One that ends lower than
    # it started is not standing up.
    if float(pts[-1, 1] - pts[:, 1].min()) < 0.25 * H:
        out.append("the stitch does not finish above the row it was worked into")
    return out
