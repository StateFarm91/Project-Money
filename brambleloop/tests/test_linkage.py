"""The linking number, checked against values that were not decided here.

Everything else in this repository validates crochet geometry against crochet reasoning I
wrote. This file does not: the linking numbers below are textbook properties of named links,
fixed long before any of this existed. If the implementation disagrees with them it is
wrong, whatever it says about a stitch.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from brambleloop.visual.linkage import (close_arc, link_with_open_path, linking_number,
                                        CurvesIntersect)

PASSED = FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    # "OK  " at the start of the line, not "PASS". run_tests.sh counts a suite's passes
    # with grep -c '^OK', and counts a suite that exits clean while reporting none as a
    # failure -- deliberately, because nine files once printed a different marker and their
    # results silently stopped reaching the headline total for a whole session. These three
    # files did exactly that again: 44 passes absent from a total of 3213, and two suites
    # reported failing that were green.
    if cond:
        PASSED += 1
        print("OK  ", name)
    else:
        FAILED += 1
        print("FAIL", name, detail)


def circle(centre, radius, normal="z", n=97):
    t = np.linspace(0, 2 * np.pi, n)
    a, b = radius * np.cos(t), radius * np.sin(t)
    z = np.zeros_like(t)
    if normal == "z":
        pts = np.stack([a, b, z], 1)
    elif normal == "y":
        pts = np.stack([a, z, b], 1)
    else:
        pts = np.stack([z, a, b], 1)
    return pts + np.asarray(centre, float)


print("linking number against known links")

# --- the unlink: two circles side by side, Lk = 0 ----------------------------
u1 = circle([0, 0, 0], 1.0, "z")
u2 = circle([4, 0, 0], 1.0, "z")
check("unlink is 0", linking_number(u1, u2) == 0, str(linking_number(u1, u2)))

# --- the Hopf link: two circles through one another, Lk = +/-1 ---------------
h1 = circle([0, 0, 0], 1.0, "z")
h2 = circle([0.75, 0, 0], 1.0, "y")
hopf = linking_number(h1, h2)
check("Hopf link is +/-1", abs(hopf) == 1, str(hopf))

# The sign is a property of orientation, so reversing one component flips it and
# reversing both leaves it alone.
check("reversing one component flips the sign",
      linking_number(h1, h2[::-1].copy()) == -hopf)
check("reversing both components leaves it unchanged",
      linking_number(h1[::-1].copy(), h2[::-1].copy()) == hopf)

# Linking number is symmetric in its arguments.
check("Lk(a,b) == Lk(b,a)", linking_number(h2, h1) == hopf)

# --- a curve threading the ring twice in the same direction, Lk = +/-2 ------
# An earlier version of this test claimed to build a Solomon link and actually built two
# nested circles that do not link at all, so it asserted 2 and the correct answer was 0.
# This one is checkable by hand instead of by name.
#
# The ring is the unit circle in z=0, spanned by the flat unit disk. The second curve runs
# on a torus about it: radius (1 + r cos s) at angle s/2, height r sin s, for s in [0, 4pi].
# It closes, and it meets z=0 where sin s = 0, at s = 0, pi, 2pi, 3pi, 4pi. Its distance
# from the origin there is 1 + r cos s, which is inside the disk only where cos s = -1,
# that is at s = pi and s = 3pi. At both, dz/ds = r cos s < 0. Two crossings of the disk,
# both downward, so the linking number is 2 and not 0.
r = 0.35
s = np.linspace(0, 4 * np.pi, 801)
ring2 = circle([0, 0, 0], 1.0, "z", 401)
twice = np.stack([(1 + r * np.cos(s)) * np.cos(s / 2),
                  (1 + r * np.cos(s)) * np.sin(s / 2),
                  r * np.sin(s)], 1)
twice[-1] = twice[0]
sol = linking_number(ring2, twice)
check("a curve threading the ring twice is +/-2", abs(sol) == 2, str(sol))

# --- invariance: deformation must not change it ------------------------------
# The whole reason for using this measure. Jiggle every vertex by an amount far larger
# than the tolerances used elsewhere, and the answer must not move.
rng = np.random.default_rng(20260924)
for scale in (0.01, 0.05, 0.12):
    j1 = h1 + rng.normal(0, scale, h1.shape)
    j1[-1] = j1[0]
    j2 = h2 + rng.normal(0, scale, h2.shape)
    j2[-1] = j2[0]
    check(f"Hopf survives a {scale:.2f} jiggle", linking_number(j1, j2) == hopf)

# --- resolution invariance ---------------------------------------------------
vals = {linking_number(circle([0, 0, 0], 1.0, "z", n), circle([0.75, 0, 0], 1.0, "y", m))
        for n in (33, 97, 201) for m in (33, 97, 201)}
check("independent of how finely either curve is sampled", len(vals) == 1, str(vals))

# --- scale invariance --------------------------------------------------------
check("independent of overall scale",
      linking_number(h1 * 1000.0, h2 * 1000.0) == hopf)
check("independent of translation",
      linking_number(h1 + 500.0, h2 + 500.0) == hopf)

# --- open paths --------------------------------------------------------------
# An open strand has no linking number of its own. The closure is accepted only once it has
# been shown to contribute nothing, so the answer belongs to the strand and the loop.
ring = circle([0, 0, 0], 1.0, "z")
through = np.array([[0.2, 0.1, -6.0], [0.2, 0.1, 6.0]])
beside = np.array([[3.0, 0.0, -6.0], [3.0, 0.0, 6.0]])
check("an open strand through a loop is 1", abs(link_with_open_path(ring, through)) == 1)
check("an open strand beside a loop is 0", link_with_open_path(ring, beside) == 0)

# Yarn that goes in and comes back out the way it came holds on to nothing. This is the
# case that the old crossing-parity test called linked.
dip = np.array([[0.2, 0.1, 4.0], [0.2, 0.1, -0.4], [0.25, 0.1, 4.0]])
check("a strand that dips through and returns is 0", link_with_open_path(ring, dip) == 0)

# --- the property the old test did not have ----------------------------------
# Truncating the strand must not change the verdict. Parity on a sub-path did change, which
# is why it was replaced.
cuts = {link_with_open_path(ring, np.array([[0.2, 0.1, -L], [0.2, 0.1, L]]))
        for L in (1.1, 1.5, 2.0, 3.0, 5.0, 12.0, 60.0)}
check("truncating the strand does not change the answer", len(cuts) == 1, str(cuts))

# --- an arc closed into a loop ------------------------------------------------
arc = circle([0, 0, 0], 1.0, "z", 40)[:28]
closed = close_arc(arc)
check("close_arc returns a closed curve", np.allclose(closed[0], closed[-1]))
check("a closed arc still links a strand through it",
      abs(link_with_open_path(closed, np.array([[0.0, 0.0, -6.0], [0.0, 0.0, 6.0]]))) == 1)

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
