"""Which stitches lose their morphology when the fabric actually drapes, and where they are."""
import sys, json
import numpy as np
sys.path.insert(0, "research/d")
import sphere_form as SF
from brambleloop.visual import crochet_topology as CT, stitch_shape as SS, drape as DR

kind = sys.argv[1] if len(sys.argv) > 1 else "hdc"
mom = float(sys.argv[2]) if len(sys.argv) > 2 else 0.98
its = int(sys.argv[3]) if len(sys.argv) > 3 else 800
draped, out = SF.main(kind, 5, 5, None, its, mom, 4)
flat = SF.certified(kind, 5, 5)[2]
cx, cy = np.array(out["extent_mm"][:2]) / 2 + flat.points.min(axis=0)[:2]
R = out["radius_mm"]
for label, fab in (("flat", flat), ("draped", draped)):
    frames = CT.stitch_frames(fab)
    print("==", label)
    for o in fab.ops:
        if not CT.is_stitch(o):
            continue
        fr = frames.get((o.row, o.position))
        if fr is None:
            print(o.row, o.position, "unframeable"); continue
        m = SS.shape_margins(o, fab.L, fab.H, fab.D, fr)
        c = o.points.mean(axis=0)
        rr = np.hypot(c[0] - cx, c[1] - cy)
        rep = SS.shape_report(o, fab.L, fab.H, fab.D, fr)
        print("row %d pos %d  r/R %.2f  z %.1f  third_below_v %+.3f  %s" % (
            o.row, o.position, rr / R, c[2], m.get("third_loop_below_v_mm", float("nan")),
            ("BROKEN: " + rep[0]) if rep else ""))
