"""CIR -> full-size, addressable surface routing probe (NOT certified crochet).

All 17,424 cells and all 540 crossings are represented. This tests a renderer
contract, not the as-yet-unimplemented fpdc/bpdc/cable loop topology. The short
curves are schematic post/crown carriers; their ends are not joined into the
maker's yarn path. No geometry, reference or photo from another product is used.
"""
import collections
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out"
sys.path.insert(0, str(ROOT / "src"))
from brambleloop.products.texture import build_cable_throw
from brambleloop.cir import compiler, twin, stitches

FAMILY = {"sc": 1, "bpdc": 2, "fpdc": 3, "cable2x2": 4}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_cells():
    cir = build_cable_throw()
    compiled = compiler.compile_cir(cir)
    if not compiled.ok:
        raise ValueError(compiled.errors)
    tw = twin.build_twin(cir, compiled, cir.components[0].name)
    pt_path = HERE.parent / "v1grad/out/product_truth.json"
    pt = json.loads(pt_path.read_text())
    frozen = json.loads((HERE.parent / "v1grad/out/v1grad_manifest.json").read_text())
    if sha(pt_path) != frozen["frozen_digests"]["product_truth.json"]:
        raise ValueError("Frozen Product Truth digest differs")
    if cir.fingerprint != pt["cir"]["fingerprint"]:
        raise ValueError("CIR differs from frozen Product Truth")
    ordered = sorted(tw.cells, key=lambda c: (c.row, c.fabric_position))
    heights = []
    for row in range(1, 122):
        heights.append(max(stitches.get(c.stitch).row_height for c in ordered if c.row == row) * 100 / cir.gauge.rows_per_10cm)
    y = np.r_[0., np.cumsum(heights)]
    w = 100 / cir.gauge.stitches_per_10cm
    return cir, tw, pt_path, ordered, y, w


def main():
    start = time.perf_counter()
    cir, tw, pt_path, cells, edges_y, width = compile_cells()
    OUT.mkdir(exist_ok=True)
    routes, table = [], []
    # Coordinates in mm. These motifs are deliberately labelled carriers, not
    # implementations of the yarn's loop-entry/post-wrap semantics.
    t = np.linspace(0, 1, 18)
    for cell in cells:
        row, p = cell.row, cell.fabric_position
        y0, y1 = edges_y[row - 1:row + 1]
        x = (p + .5) * width
        yy = y0 + (y1 - y0) * (.12 + .76 * t)
        xx = x + .19 * width * np.sin(2 * np.pi * t)
        zz = np.full_like(t, 1.8 if cell.stitch == "bpdc" else 3.8)
        if cell.stitch == "sc":
            xx = x + .28 * width * np.sin(2 * np.pi * t)
            yy = y0 + (y1 - y0) * (.5 + .28 * np.cos(2 * np.pi * t))
            zz[:] = 1.8
        if cell.stitch == "cable2x2":
            in_cable = p % 8 - 2
            shift = 2 if in_cable < 2 else -2
            xx = x + shift * width * (.5 - .5 * np.cos(np.pi * t))
            zz += (2.6 if shift > 0 else -1.3) * np.sin(np.pi * t)
        # Small head/crown hook, within the allocated cell. Not a loop topology claim.
        pts = np.column_stack([xx, yy, zz])
        routes.append(pts)
        table.append((row, p, FAMILY[cell.stitch], (p // 8 + 1) if 2 <= p % 8 <= 5 and row > 1 else 0))
    routes = np.asarray(routes, dtype=np.float32)
    table = np.asarray(table, dtype=np.int32)
    np.savez_compressed(OUT / "routing_probe.npz", points_mm=routes, cells=table, row_edges_mm=edges_y)
    # Human-reviewable source schedule is independent of any photographic judgement.
    crossing_rows = sorted({c.row for c in cells if c.stitch == "cable2x2"})
    crossing_y = [(edges_y[r-1] + edges_y[r]) / 2 for r in crossing_rows]
    data = {
        "scope": "Complete semantic grid and schematic surface routing; NOT certified crochet geometry",
        "product_truth_sha256": sha(pt_path), "cir_fingerprint": cir.fingerprint,
        "source_code_sha256": sha(ROOT / "src/brambleloop/products/texture.py"),
        "generator_sha256": sha(Path(__file__)), "geometry_file_sha256": sha(OUT / "routing_probe.npz"),
        "points_array_sha256": hashlib.sha256(routes.tobytes()).hexdigest(),
        "cell_columns": ["row", "fabric_position", "family_code", "cable_column_or_zero"], "family_codes": FAMILY,
        "counts": dict(collections.Counter(c.stitch for c in cells)),
        "rows": len(edges_y)-1, "stitches_per_row": 144, "cell_count": len(cells),
        "cable_columns": 18, "cable_crossings": len(crossing_rows)*18,
        "dimensions_mm": [tw.width_cm*10, float(edges_y[-1])], "frozen_dimensions_cm": [tw.width_cm, tw.height_cm],
        "cable_centres_x_mm": [(i*8+4)*width for i in range(18)],
        "crossing_rows": crossing_rows, "crossing_centres_y_mm": crossing_y,
        "cable_pitch_mm": width*8, "crossing_pitch_mm_from_rows": float(np.mean(np.diff(crossing_y))),
        "frozen_crossing_pitch_mm": json.loads(pt_path.read_text())["derived"]["crossing_period_cm"]*10,
        "colour_srgb": list(cir.colors.values())[0], "calibrated": False,
        "no_external_finished_product_images": True,
        "construction_convention": "Left incoming pair above right; inherited declared V1 convention, unspecified in CIR",
        "not_certified": ["fpdc/bpdc loop-entry and wrap topology", "one continuous maker yarn path", "edge turning chains", "mechanical drape", "material/fibre calibration", "photographic realism"],
        "seconds": round(time.perf_counter()-start, 3),
    }
    (OUT / "geometry_manifest.json").write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
