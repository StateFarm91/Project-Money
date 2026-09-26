"""Worst non-adjacent segment pairs in an sc swatch, by key-point name. A diagnostic, kept."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from sc_swatch import sc_twin
from brambleloop.visual import crochet_topology as CT
SC = ["entry","approach","insert","through","behind","emerge","rise","crown","close","back_loop","back_loop_e","v_turn_a","v_turn","v_turn_b","front_loop","front_loop_e","away"]
def name(fab, seg):
    off = 0
    for o in fab.ops:
        n = len(o.points)
        if off <= seg < off + n:
            k = seg - off
            a = SC[k] if o.kind == "sc" and k < len(SC) else f"pt{k}"
            b = SC[k+1] if o.kind == "sc" and k+1 < len(SC) else f"pt{k+1}"
            return f"{o.kind} r{o.row}p{o.position} {a}->{b}"
        off += n
    return "?"
def worst_pairs(fab, k=6):
    pts = fab.points; d = np.diff(pts, axis=0); seg = np.linalg.norm(d, axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)]); mid = 0.5*(arc[:-1]+arc[1:]); live = np.nonzero(seg > 1e-6)[0]
    apart = np.pi * fab.yarn_diameter / 2; found = []
    for kk, i in enumerate(live):
        j = live[kk+1:]; j = j[(j - i > 1) & (np.abs(mid[j] - mid[i]) > apart)]
        if not len(j): continue
        _, _, dist = CT.closest_between_segments(np.repeat(pts[i][None], len(j), 0), np.repeat(d[i][None], len(j), 0), pts[j], d[j])
        for m in np.argsort(dist)[:2]:
            found.append((float(dist[m]), int(i), int(j[m])))
    found.sort(); out, seen = [], set()
    for dd, i, j in found:
        key = (" ".join(name(fab,i).split()[2:]), " ".join(name(fab,j).split()[2:]))
        if key in seen: continue
        seen.add(key); out.append((dd, i, j))
        if len(out) >= k: break
    return out
if __name__ == "__main__":
    for label, kw in (("basket 18x20@4", dict(st_per_10=18, rows_per_10=20, hook=4.0)), ("loose 12x13@6", dict(st_per_10=12, rows_per_10=13, hook=6.0))):
        cir, tw = sc_twin(**kw); fab = CT.build(tw, cir.gauge, max_rows=5, max_cols=5)
        print(f"== {label}: L={fab.L:.2f} H={fab.H:.2f} D={fab.D:.2f} yarn={fab.yarn_diameter:.2f} floor={fab.yarn_diameter*0.45:.2f}")
        for dd, i, j in worst_pairs(fab):
            print(f"   {dd:.3f} mm   {name(fab,i)}   vs   {name(fab,j)}")
