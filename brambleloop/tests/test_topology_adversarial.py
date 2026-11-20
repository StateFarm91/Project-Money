"""Deliberately wrong crochet, fed to the validator.

A validator is only worth its runtime if it rejects things. Each fixture here is a fabric
that is broken in one specific, nameable way; the validator must produce a finding for it.
Anything that slips through is recorded as a known gap rather than quietly passed, because a
gap you have written down is a different thing from one you have not noticed.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import copy
import numpy as np
from brambleloop.cir import benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.visual import crochet_topology as CT

PASSED = FAILED = 0
ROWS, COLS = 8, 10


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


CIR = B.cardigan("S")
TWIN = build_twin(CIR, compile_cir(CIR), component="body")


def honest():
    return CT.settle(CT.build(TWIN, CIR.gauge, max_rows=ROWS, max_cols=COLS))


def verdict(fab):
    return CT.validate(fab, TWIN, max_rows=ROWS, max_cols=COLS)


def rejects(fab, why):
    """Rejected for a NEW reason, not merely for the interpenetration the base already has."""
    v = verdict(fab)
    fresh = [f for f in v["findings"] if "closer than yarn can compress" not in f]
    return bool(fresh), v


print("adversarial topology")

# --- the control -------------------------------------------------------------
# If the honest fabric does not pass, nothing below means anything.
base = honest()
vb = verdict(base)
# The honest fabric carries exactly one finding: its strands interpenetrate, measured
# segment to segment, at about 0.61mm against a 1.50mm floor. That is real and is what
# physical relaxation exists to resolve; it is named here so it cannot drift into being
# treated as normal, and so that any OTHER finding on the honest fabric fails this test.
_known = "closer than yarn can compress"
check("the honest fabric carries no finding except the known interpenetration",
      not [f for f in vb["findings"] if _known not in f],
      str(vb["findings"])[:160])
check("and that one finding is present, not silently gone",
      any(_known in f for f in vb["findings"]), str(vb["findings"])[:120])


def mutate(fn):
    fab = copy.deepcopy(base)
    fn(fab)
    return fab


def hdcs(fab):
    return [o for o in fab.ops if o.kind == "hdc"]


# --- 1. strand intersection ---------------------------------------------------
def collide(fab):
    a, b = hdcs(fab)[20], hdcs(fab)[21]
    b.points[:] = b.points + (a.points[0] - b.points[0])


bad, v = rejects(mutate(collide), "strands occupy the same space")
check("rejects two strands in the same place", bad, str(v["findings"])[:120])

# --- 2. disconnected yarn, hidden by the projection --------------------------
# Displaced only in z, so a flat drawing of it looks perfectly continuous.
def snap_in_depth(fab):
    o = hdcs(fab)[15]
    o.points[:, 2] += 40.0


bad, v = rejects(mutate(snap_in_depth), "the yarn is in two pieces")
check("rejects a break visible only in depth", bad, str(v["findings"])[:120])

# --- 3. a stitch that links nothing ------------------------------------------
def unhook(fab):
    for o in hdcs(fab)[12:18]:
        o.points[:, 1] += 6.0          # lift clear of the loop below


bad, v = rejects(mutate(unhook), "stitches float free of the row below")
check("rejects stitches lifted out of their anchors", bad,
      f"linked {v['stitches_linked']}/{v['stitches_needing_linkage']}")

# --- 4. right shape, wrong anchor --------------------------------------------
# Each stitch is a perfectly good stitch. It is just linked to the wrong one.
def shift_anchor(fab):
    tgt = [o for o in hdcs(fab) if o.row == 4]
    for o in tgt:
        o.points[:, 0] += 2 * fab.L


bad, v = rejects(mutate(shift_anchor), "linked to the wrong stitch")
check("rejects correct stitches linked to the wrong anchor", bad,
      f"linked {v['stitches_linked']}/{v['stitches_needing_linkage']}")

# --- 5. FLO where the CIR says BLO -------------------------------------------
# The geometry is a real front-loop stitch; the CIR asked for a back-loop one.
def swap_loop_target(fab):
    for o in hdcs(fab):
        if o.loop_target == "back":
            o.loop_target = "front"


bad, v = rejects(mutate(swap_loop_target), "worked into the wrong loop")
check("rejects front-loop geometry where the CIR says back loop", bad,
      f"targets_match={v.get('loop_targets_match_cir')}")

# --- 6. rows not joined ------------------------------------------------------
def drop_turning_chains(fab):
    fab.ops[:] = [o for o in fab.ops if o.kind != "turn"]


bad, v = rejects(mutate(drop_turning_chains), "rows are separate objects")
check("rejects rows that are not joined into one piece", bad,
      f"turns={v.get('turning_chains')}")

# --- 7. a straight rod through the loop --------------------------------------
# Maximally degenerate: linked, continuous, non-intersecting -- and not a stitch.
def rods(fab):
    for o in hdcs(fab):
        if o.row < 2:
            continue
        a, b = o.points[0].copy(), o.points[-1].copy()
        mid = 0.5 * (a + b)
        mid[1] -= 3.0 * fab.H
        o.points[:] = np.array([a + (mid - a) * t for t in np.linspace(0, 1, len(o.points))])


bad, v = rejects(mutate(rods), "not a stitch, just a line through a hole")
check("rejects a straight rod substituted for a stitch", bad, str(v["findings"])[:120])

# --- 8. a knitted loop where a crochet stitch belongs -------------------------
# A knit stitch is a symmetric U hung on the row above: continuous, non-intersecting,
# interlocked. It is simply not crochet.
def knit(fab):
    for o in hdcs(fab):
        if o.row < 2:
            continue
        n = len(o.points)
        t = np.linspace(0, 1, n)
        base = o.points[0]
        width, height = 0.9 * fab.L, 1.1 * fab.H
        o.points[:] = np.stack([
            base[0] + width * np.sin(np.pi * t),
            base[1] + height * np.sin(np.pi * t) ** 2,
            base[2] + 0.4 * fab.D * np.sin(2 * np.pi * t),
        ], axis=1)


bad, v = rejects(mutate(knit), "knitting, not crochet")
check("rejects a knitted loop substituted for a crochet stitch", bad,
      str(v["findings"])[:120])


# =============================================================================
# Shape. Everything above can be defeated by a rod or a knit loop that happens to break
# linkage on its way past; these fixtures stay linked, continuous and non-intersecting and
# are still not half double crochet.
# =============================================================================
print("\nadversarial shape")


def reshape(fn):
    fab = copy.deepcopy(base)
    for o in hdcs(fab):
        fn(fab, o)
    return fab


def shape_findings(fab):
    return [f for f in verdict(fab)["findings"] if "shaped like" in f]


# --- a single crochet wearing a half double's linkage ------------------------
# No opening yarn over, so no third loop behind the fabric. Every other property survives.
def single_crochet(fab, o):
    a, b = o.third_loop
    o.points[a:b + 1, 2] = abs(o.points[a:b + 1, 2]) + 0.6 * fab.D


f = reshape(single_crochet)
check("rejects a single crochet substituted for a half double",
      shape_findings(f), str(verdict(f)["findings"])[:130])

# --- a double crochet: right structure, wrong height -------------------------
def double_crochet(fab, o):
    base_y = o.points[:, 1].min()
    o.points[:, 1] = base_y + (o.points[:, 1] - base_y) * 2.4


f = reshape(double_crochet)
check("rejects a stitch that stands at double crochet height", shape_findings(f),
      str(verdict(f)["findings"])[:130])

# --- a folded V: two legs running the same way -------------------------------
# Nothing can be worked into a fold, but it links and draws perfectly well.
def folded_v(fab, o):
    a, b = o.front_loop
    o.points[a:b + 1, 0] = o.points[a:b + 1, 0][::-1]


f = reshape(folded_v)
check("rejects a top V folded so its legs run the same way", shape_findings(f),
      str(verdict(f)["findings"])[:130])

# --- a collapsed V: both loops in the same plane -----------------------------
def collapsed_v(fab, o):
    a, b = o.front_loop
    c, d = o.back_loop
    o.points[a:b + 1, 2] = o.points[c:d + 1, 2].mean()


f = reshape(collapsed_v)
check("rejects a top V with no opening between its loops", shape_findings(f),
      str(verdict(f)["findings"])[:130])

# --- a stitch that does not stand up -----------------------------------------
def upside_down(fab, o):
    top = o.points[:, 1].max()
    o.points[:, 1] = top - (o.points[:, 1] - o.points[:, 1].min())


f = reshape(upside_down)
check("rejects a stitch that hangs instead of standing", shape_findings(f),
      str(verdict(f)["findings"])[:130])

# --- a discontinuity small enough to hide under the old threshold ------------
# This is the case that was real and was passing: neighbouring stitches in a row failing to
# meet by about two stitch pitches. The old continuity check thresholded the largest step at
# 2.6 pitches, so a 13.9mm break in a 6.9mm pitch fabric was reported as continuous. Kept as
# a fixture because a check that once missed something should be made to prove it no longer
# does.
def small_break(fab, o):
    if o.position % 2 == 0:
        o.points[:] = o.points + np.array([1.9 * fab.L, 0.0, 0.0])


f = reshape(small_break)
v = verdict(f)
check("rejects a break of two pitches between neighbouring stitches",
      not v["passes"] and any("in pieces" in x or "jumps" in x for x in v["findings"]),
      str(v["findings"])[:140])
check("the break is measured at the joins, not as a largest step",
      v["largest_join_within_a_row_mm"] > f.L,
      f"join {v.get('largest_join_within_a_row_mm')} vs L {f.L:.2f}")

# --- and the control: the honest fabric must still pass the shape check ------
check("the honest fabric is shaped like half double crochet", not shape_findings(base),
      str(verdict(base)["findings"])[:130])

# --- REGRESSION: the fictitious closure must be big enough to be a wall ------------------
# The encirclement test closes a single top loop through a point off to one side and asks
# whether the stitch crosses the triangle that spans. That triangle is not yarn, so the
# stitch must not be able to leave through its EDGE -- if it can, a stitch that genuinely
# wraps the strand scores zero for a reason that has nothing to do with crochet.
#
# At a fixed 6mm tail that is exactly what happened. The identical-stitch control was
# unaffected, so the defect stayed invisible until stitches began to lean under hand
# tension, at which point eleven of forty-two CERTIFIED stitches read as unlinked. The same
# fabric scored 42/42 at every tail from 12mm to 60mm. A verdict that depends on the size of
# an imaginary surface is measuring the surface, not the fabric, so the tail is now derived
# from the fabric and this test pins the invariance.
import brambleloop.visual.crochet_topology as _ct

_f = honest()
_orig = _ct._away_vector
try:
    verdicts = {}
    for _tail in (12.0, 20.0, 35.0, 60.0, 120.0):
        _ct._away_vector = (lambda t: (lambda fab, down=None: np.array([0.0, -t, 0.0])))(_tail)
        _v = _ct.validate(_f, TWIN, max_rows=ROWS, max_cols=COLS)
        verdicts[_tail] = (_v["stitches_linked"], _v["stitches_needing_linkage"])
    check("the linkage verdict does not depend on the size of the fictitious closure",
          len(set(verdicts.values())) == 1, str(verdicts))
    check("the derived closure is long enough that yarn cannot round its end",
          np.linalg.norm(_orig(_f)) >= 2.0 * float(np.hypot(_f.L, _f.H) + _f.D) - 1e-9,
          "%.2fmm" % np.linalg.norm(_orig(_f)))
    # The tail's DIRECTION had the same defect as its length and survived longer, because it
    # is invisible while the fabric lies flat. It is aimed along the stitch's own down now,
    # so it must follow an arbitrary direction handed to it rather than staying on -y.
    _d = np.array([0.3, -0.8, 0.5])
    _v = _orig(_f, _d)
    check("the closure follows the fabric's local down rather than a global axis",
          abs(float(np.dot(_v / np.linalg.norm(_v), _d / np.linalg.norm(_d))) - 1.0) < 1e-9,
          str(_v))
finally:
    _ct._away_vector = _orig

# --- REGRESSION: the validators must measure the cloth, not its orientation ---------------
# A rigid rotation changes no physical property of a fabric, so every verdict must be
# identical under all of them. Both checks failed this before the fabric was allowed out of
# its plane, and in different ways that are worth keeping distinct:
#
#   MORPHOLOGY read its features off the global axes -- "behind" was -z, "below" and height
#   were y, the V ran along x. 49 of 49 correctly shaped became 2 of 49 at fifteen degrees
#   and 0 of 49 at thirty. The stitches were untouched.
#
#   LINKAGE aimed its fictitious closure along a fixed global -y. Rotations about x and y
#   left that pointing along the same part of the cloth and looked fine; rotation about z
#   dropped it from 42 of 42 to 3 of 42. That asymmetry -- broken on one axis, clean on the
#   others -- is the signature of a global direction standing in for a local one.
#
# This matters for drape rather than for rotation. A draped fabric is a rotated one
# everywhere at once, each stitch on a surface with its own normal, so a validator that
# assumes one global orientation fails every curved row. Had these been grandfathered, the
# obvious response would have been to flatten correct geometry until the checks passed.
_rot_f = honest()
_base = verdict(_rot_f)


def _rotated(fab, deg, axis):
    import dataclasses
    t = np.radians(deg)
    c, sn = np.cos(t), np.sin(t)
    R = {"x": np.array([[1, 0, 0], [0, c, -sn], [0, sn, c]]),
         "y": np.array([[c, 0, sn], [0, 1, 0], [-sn, 0, c]]),
         "z": np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1]])}[axis]
    return dataclasses.replace(
        fab, ops=[dataclasses.replace(o, points=o.points @ R.T) for o in fab.ops])


for _axis in ("x", "y", "z"):
    _same = True
    _detail = ""
    for _deg in (15, 30, 45, 90, 137):
        _v = _ct.validate(_rotated(_rot_f, _deg, _axis), TWIN, max_rows=ROWS, max_cols=COLS)
        if (_v["stitches_linked"], _v["stitches_shaped_as_ordered"],
                _v.get("stitches_unframeable", 0)) != (
                _base["stitches_linked"], _base["stitches_shaped_as_ordered"],
                _base.get("stitches_unframeable", 0)):
            _same = False
            _detail = "%ddeg: linked %s shaped %s" % (
                _deg, _v["stitches_linked"], _v["stitches_shaped_as_ordered"])
            break
    check("every verdict is invariant under rigid rotation about %s" % _axis, _same, _detail)

check("no stitch is unmeasurable for want of a frame, foundation row included",
      _base.get("stitches_unframeable", 0) == 0, str(_base.get("stitches_unframeable")))

# --- REGRESSION: encirclement must not depend on which closure was picked ----------------
# Third time a verdict has turned out to rest on a property of an imaginary surface. The
# closure's LENGTH was wrong twice -- 6mm let leaning stitches escape past the triangle's
# edge, and the cell-derived length did the same once the fabric draped. Its DIRECTION was
# wrong a third time, and only on curved cloth: a stitch that is demonstrably linked scored
# -1 for three closure directions and 0 for a fourth at comparable clearance, so the fourth
# was a triangle that missed the crossing, and the validator called the stitch unlinked.
#
# The linking number of an open path with an artificially closed ring is not an invariant on
# its own. So several closures are tried and the rule follows how each error actually
# happens: a miss is easy and gives a false negative, so one clear detection establishes
# linkage; a false positive needs the tail to thread the stitch, which clearance excludes.
#
# The property that must hold, and that this pins, is that a genuinely unlinked stitch is
# caught by NO closure. If any direction could manufacture a crossing, every fixture below
# would start passing and the check would be decorative.
_enc_f = honest()
_enc_hdc = [o for o in _enc_f.ops if o.kind == "hdc"]
_enc_by = {(o.row, o.position): o for o in _enc_hdc}
_enc_rows = sorted({o.row for o in _enc_hdc})
_single = [o for o in _enc_hdc if o.loop_target in ("front", "back")
           and _enc_rows.index(o.row) > 0]
check("the benchmark fabric actually exercises single-loop encirclement",
      len(_single) > 0, str(len(_single)))

_agree = 0
for _o in _single[:12]:
    _a = _enc_by[(_enc_rows[_enc_rows.index(_o.row) - 1], _o.position)]
    _arc = (_a.points[_a.front_loop[0]:_a.front_loop[1] + 1] if _o.loop_target == "front"
            else _a.points[_a.back_loop[0]:_a.back_loop[1] + 1])
    _linked, _det, _ = _ct._encirclement(_arc, _o.points, _enc_f, None)
    if _linked and _det:
        _agree += 1
check("every single-loop stitch of an honest fabric is found linked",
      _agree == len(_single[:12]), "%d of %d" % (_agree, len(_single[:12])))

# A strand that merely lies NEAR the loop, never through it, must be caught by no closure.
_o = _single[0]
_a = _enc_by[(_enc_rows[_enc_rows.index(_o.row) - 1], _o.position)]
_arc = (_a.points[_a.front_loop[0]:_a.front_loop[1] + 1] if _o.loop_target == "front"
        else _a.points[_a.back_loop[0]:_a.back_loop[1] + 1])
_beside = _arc.mean(axis=0) + np.array([0.0, 0.0, 40.0]) + np.linspace(
    -20, 20, 24)[:, None] * np.array([1.0, 0.0, 0.0])
_lk, _det2, _ = _ct._encirclement(_arc, _beside, _enc_f, None)
check("a strand passing beside the loop is not reported as encircling it",
      (not _lk) and _det2, "linked=%s determinate=%s" % (_lk, _det2))

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
