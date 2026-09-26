"""Stitch identity cannot drift. A single crochet is built as a single crochet, a half double
as a half double, and a stitch this module has no cell for is refused by name rather than
drawn as its nearest relative.

The defect these pin: `crochet_topology.build` used to call the half double cell builder
unconditionally, so an sc basket twin came out as 24 half doubles and every count still
matched. Found 2026-09-26; every check here failed against that code and passes against the
fix, and the injected-defect check at the end proves the identity test can see a relabel.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "research" / "d"))

from brambleloop.cir import benchmarks as B, compiler, twin as T
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Row
from brambleloop.products import launch0 as l0
from brambleloop.visual import crochet_topology as CT, relaxation as RX
from sc_swatch import sc_twin

PASSED = FAILED = 0
def check(name, ok, detail=""):
    global PASSED, FAILED
    PASSED += ok; FAILED += (not ok)
    print(("OK   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"))

def flat_twin(stitch, rows=4, cols=5):
    g = Gauge(stitches_per_10cm=18, rows_per_10cm=20, stitch_type=stitch, hook_mm=4.0, yarn_weight="worsted")
    rr = [Row(index=1, ops=[Op(stitch, cols)], declared_count=cols, turning_chain=0, skips=1)]
    rr += [Row(index=i, ops=[Op(stitch, cols)], declared_count=cols, turning_chain=1) for i in range(2, rows + 1)]
    cir = CIR(slug=f"{stitch}-fixture", title="fixture", version="0.0.1", construction="flat_rows", gauge=g,
              materials=[Material(name="m", yarn_weight="worsted")],
              components=[Component("swatch", "flat_rows", rr, foundation=cols + 1)])
    return cir, T.build_twin(cir, compiler.compile_cir(cir), component="swatch")

# --- 1. an sc twin builds sc, never hdc ------------------------------------------------
cir, tw = sc_twin()
fab = CT.build(tw, cir.gauge, max_rows=5, max_cols=5)
kinds = {o.kind for o in fab.ops if CT.is_stitch(o)}
check("an sc twin builds single crochets", kinds == {"sc"}, str(kinds))
check("and not one of them is a half double", not any(o.kind == "hdc" for o in fab.ops))
check("a single crochet names no third loop", all(o.third_loop is None for o in fab.ops if o.kind == "sc"))

# --- 2. the identity invariant: every op's kind is the cell's stitch ---------------------
cells = {(c.row, getattr(c, "fabric_position", c.position)): c.stitch for c in tw.cells}
mismatch = [(o.row, o.position, o.kind, cells.get((o.row, o.position))) for o in fab.ops
            if CT.is_stitch(o) and cells.get((o.row, o.position)) != o.kind]
check("every built stitch carries exactly the stitch the CIR cell ordered", not mismatch, str(mismatch[:3]))

# --- 3. the hdc path is untouched ---------------------------------------------------------
c = B.cardigan("S"); tw2 = T.build_twin(c, compiler.compile_cir(c), component="body")
hfab = CT.build(tw2, c.gauge, max_rows=5, max_cols=5)
check("the hdc cardigan still builds half doubles", {o.kind for o in hfab.ops if CT.is_stitch(o)} == {"hdc"})
check("with 25 stitches and 4 turns on the 5x5, as before",
      sum(1 for o in hfab.ops if o.kind == "hdc") == 25 and sum(1 for o in hfab.ops if o.kind == "turn") == 4)
check("and every half double names its third loop", all(o.third_loop is not None for o in hfab.ops if o.kind == "hdc"))

# --- 4. refusal by name, never substitution --------------------------------------------
for stitch in ("dc", "tr"):
    try:
        dcir, dtw = flat_twin(stitch)
        CT.build(dtw, dcir.gauge, max_rows=3, max_cols=4)
        check(f"a {stitch} twin is refused", False, "build returned a fabric")
    except CT.UnmodelledStitch as e:
        check(f"a {stitch} twin is refused by name", stitch in str(e), str(e)[:80])
    except Exception as e:  # noqa: BLE001
        check(f"a {stitch} twin is refused", False, f"{type(e).__name__}: {e}")
# An increase makes two stitches, so it is declared as such (the compiler refuses a row that
# says otherwise, correctly) -- and then the topology module refuses to draw it.
g = Gauge(stitches_per_10cm=18, rows_per_10cm=20, stitch_type="sc", hook_mm=4.0, yarn_weight="worsted")
icir = CIR(slug="inc-fixture", title="fixture", version="0.0.1", construction="flat_rows", gauge=g,
           materials=[Material(name="m", yarn_weight="worsted")],
           components=[Component("swatch", "flat_rows", [
               Row(index=1, ops=[Op("sc", 5)], declared_count=5, turning_chain=0, skips=1),
               Row(index=2, ops=[Op("sc", 2), Op("inc", 1), Op("sc", 2)], declared_count=6, turning_chain=1),
               Row(index=3, ops=[Op("sc", 6)], declared_count=6, turning_chain=1)], foundation=6)])
itw = T.build_twin(icir, compiler.compile_cir(icir), component="swatch")
try:
    CT.build(itw, icir.gauge, max_rows=3, max_cols=6)
    check("an increase is refused rather than drawn as two plain stitches", False, "build returned a fabric")
except CT.UnmodelledStitch as e:
    check("an increase is refused by name rather than drawn as two plain stitches", "inc" in str(e), str(e)[:80])
bcir = l0.BUILDERS["basket_large"](); btw = T.build_twin(bcir, compiler.compile_cir(bcir), component=bcir.components[0].name)
try:
    CT.build(btw, bcir.gauge, max_rows=3, max_cols=6)
    check("a piece worked in the round is refused rather than laid as flat rows", False, "build returned a fabric")
except CT.UnmodelledConstruction as e:
    check("a piece worked in the round is refused rather than laid as flat rows", "round" in str(e))
except CT.UnmodelledStitch as e:
    # the basket carries `inc` too; either refusal is a refusal, but the construction one must come first
    check("a piece worked in the round is refused rather than laid as flat rows", False, f"stitch refusal fired before construction refusal: {e}")

# --- 5. the sc cell passes the SAME certifying chain the hdc cell passes ----------------
for label, kw in (("Launch-0 basket gauge", dict(st_per_10=18, rows_per_10=20, hook=4.0)),
                  ("a loose sc gauge", dict(st_per_10=12, rows_per_10=13, hook=6.0))):
    scir, stw = sc_twin(**kw)
    flat, rep = RX.relax(CT.settle(CT.build(stw, scir.gauge, max_rows=5, max_cols=5)))
    v = CT.validate(flat, stw, max_rows=5, max_cols=5)
    check(f"sc 5x5 at {label}: every stitch linked", v["stitches_linked"] == v["stitches_needing_linkage"] == 20, str((v["stitches_linked"], v["stitches_needing_linkage"])))
    check(f"sc 5x5 at {label}: every stitch shaped like a single crochet", v["stitches_shaped_like_hdc"] == v["stitches_built"] == 25, str(v["misshapen"][:2]))
    check(f"sc 5x5 at {label}: clear of the contact floor", v["closest_non_adjacent_mm"] >= v["contact_floor_mm"], f"{v['closest_non_adjacent_mm']} < {v['contact_floor_mm']}")
    check(f"sc 5x5 at {label}: the validator passes it", v["passes"] is True, str(v["findings"][:1]))

# --- 6. the shape check sees a relabel in BOTH directions -------------------------------
from brambleloop.visual import stitch_shape as SS
frames = CT.stitch_frames(flat)
sc_op = next(o for o in flat.ops if o.kind == "sc" and (o.row, o.position) in frames)
fr = frames[(sc_op.row, sc_op.position)]
check("a correctly built sc has no shape complaint", SS.shape_report(sc_op, flat.L, flat.H, flat.D, fr) == [])
from dataclasses import replace
fake = replace(sc_op, third_loop=(7, 7))
check("an 'sc' that names a third loop is called a half double wearing the wrong label",
      any("half double" in m for m in SS.shape_report(fake, flat.L, flat.H, flat.D, fr)))
hframes = CT.stitch_frames(hfab)
h_op = next(o for o in hfab.ops if o.kind == "hdc" and (o.row, o.position) in hframes)
fake_h = replace(h_op, kind="sc")
check("an hdc relabelled 'sc' is caught: it names a third loop a single crochet cannot have",
      any("half double" in m for m in SS.shape_report(fake_h, hfab.L, hfab.H, hfab.D, hframes[(h_op.row, h_op.position)])))

# --- 7. injected defect: the identity test can SEE the original relabel ----------------
saved = CT.CELLS["sc"]
try:
    CT.CELLS["sc"] = CT._hdc_cell                 # the old behaviour, reinstated on purpose
    fab_bad = CT.build(tw, cir.gauge, max_rows=5, max_cols=5)
    # The kind is now stamped from the cell name, so ops still say "sc"; the ANATOMY is hdc.
    # The shape check must therefore be the thing that catches it.
    bf = CT.stitch_frames(fab_bad)
    op_bad = next(o for o in fab_bad.ops if o.kind == "sc" and (o.row, o.position) in bf)
    complaints = SS.shape_report(op_bad, fab_bad.L, fab_bad.H, fab_bad.D, bf[(op_bad.row, op_bad.position)])
    check("with the hdc cell reinstated for sc, the shape check rejects every stitch as a relabel",
          any("half double" in m for m in complaints), str(complaints[:1]))
finally:
    CT.CELLS["sc"] = saved

print(f"\n  {PASSED} passing, {FAILED} failing")
sys.exit(1 if FAILED else 0)
