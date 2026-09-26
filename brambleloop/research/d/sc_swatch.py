"""An sc-only flat swatch, through the real CIR compiler and twin, for validating the sc cell.

Not a product: a fixture. Gauge and hook are the Launch-0 basket's (18 st x 20 rows per
10 cm on a 4.0 mm hook, p3 of that pattern's own gauge), so the cell is validated in the
regime a Launch-0 product actually puts it in -- yarn 44% of row height -- rather than in the
roomier hdc cardigan regime.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from brambleloop.cir.model import CIR, Component, Gauge, Material, Op, Row      # noqa: E402
from brambleloop.cir import compiler, twin as T                                  # noqa: E402

def sc_cir(rows: int = 8, cols: int = 8, *, st_per_10=18, rows_per_10=20, hook=4.0) -> CIR:
    g = Gauge(stitches_per_10cm=st_per_10, rows_per_10cm=rows_per_10, stitch_type="sc", hook_mm=hook, yarn_weight="worsted")
    rr = [Row(index=1, ops=[Op("sc", cols)], declared_count=cols, turning_chain=0, skips=1)]
    for i in range(2, rows + 1):
        rr.append(Row(index=i, ops=[Op("sc", cols)], declared_count=cols, turning_chain=1))
    comp = Component("swatch", "flat_rows", rr, foundation=cols + 1)
    return CIR(slug="sc-swatch-fixture", title="sc swatch fixture", version="0.0.1", construction="flat_rows",
               gauge=g, materials=[Material(name="fixture worsted", yarn_weight="worsted")], components=[comp])

def sc_twin(rows=8, cols=8, **kw):
    cir = sc_cir(rows, cols, **kw); res = compiler.compile_cir(cir)
    return cir, T.build_twin(cir, res, component="swatch")

if __name__ == "__main__":
    import json
    from brambleloop.visual import crochet_topology as CT
    cir, tw = sc_twin()
    print("twin:", tw.stitch_total, "stitches", tw.width_cm, "x", tw.height_cm, "cm; cells:", sorted({c.stitch for c in tw.cells}))
    fab = CT.build(tw, cir.gauge, max_rows=5, max_cols=5)
    kinds = {}; [kinds.__setitem__(o.kind, kinds.get(o.kind, 0) + 1) for o in fab.ops]
    print("ops:", kinds, "| L,H,D,yarn:", round(fab.L,2), round(fab.H,2), round(fab.D,2), round(fab.yarn_diameter,2))
    fab = CT.settle(fab)
    v = CT.validate(fab, tw, max_rows=5, max_cols=5)
    keep = ("passes","stitches_built","linked","needing_linkage","stitches_shaped_like_hdc","stitches_unframeable","closest_non_adjacent_mm","contact_floor_mm","misshapen","findings")
    print(json.dumps({k: v.get(k) for k in keep if k in v}, default=str)[:1500])
