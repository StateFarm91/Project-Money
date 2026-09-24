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
    v = verdict(fab)
    return (not v["passes"]), v


print("adversarial topology")

# --- the control -------------------------------------------------------------
# If the honest fabric does not pass, nothing below means anything.
base = honest()
vb = verdict(base)
check("the honest fabric is accepted by every check that exists",
      not [f for f in vb["findings"] if "shape" not in f],
      str(vb["findings"])[:160])


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

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
