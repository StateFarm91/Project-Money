"""Sweep the sc post offset against the contact floor, two regimes, before and after settle."""
import sys, itertools
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from sc_swatch import sc_twin
from brambleloop.visual import crochet_topology as CT

REGIMES = {"basket 18x20 @4.0mm": dict(st_per_10=18, rows_per_10=20, hook=4.0),
           "loose sc 12x13 @6.0mm": dict(st_per_10=12, rows_per_10=13, hook=6.0)}
rows = []
for px, cz in itertools.product((0.22, 0.28), (0.10, 0.02)):
    CT.SC_POST_X, CT.SC_CROWN_Z = px, cz
    out = [f"post_x={px:.2f} crown_z={cz:+.2f}"]
    ok_all = True
    for name, kw in REGIMES.items():
        cir, tw = sc_twin(**kw)
        fab = CT.build(tw, cir.gauge, max_rows=5, max_cols=5)
        g0, _ = CT.min_segment_separation(fab.points, fab.yarn_diameter)
        fab = CT.settle(fab)
        v = CT.validate(fab, tw, max_rows=5, max_cols=5)
        floor = fab.yarn_diameter * CT.COMPRESSED_CONTACT
        out.append(f"{name}: gap {g0:.2f}->{v['closest_non_adjacent_mm']:.2f} (floor {floor:.2f}) "
                   f"link {v['stitches_linked']}/{v['stitches_needing_linkage']} shaped {v['stitches_shaped_as_ordered']}/{v['stitches_built']} "
                   f"{'PASS' if v['passes'] else 'FAIL'}")
        ok_all &= v["passes"]
    rows.append((ok_all, " | ".join(out)))
for ok, line in rows:
    print(("**" if ok else "  ") + line)
