"""Continuous yarn geometry from certified fabric.

These test the properties the representation claims -- continuity, traceability, and that
loop targeting produces genuinely free strands. They do NOT test that the render looks like
crochet, because as of B-705 it does not; asserting otherwise would be a lie in a test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from brambleloop.cir import benchmarks as B
from brambleloop.cir.compiler import compile_cir
from brambleloop.cir.twin import build_twin
from brambleloop.visual import yarn


def _path(**kw):
    c = B.cardigan("S")
    r = compile_cir(c)
    assert r.ok
    t = build_twin(c, r, component="body")
    return c, yarn.yarn_path(t, c.gauge, max_rows=4, max_cols=5, **kw)


def test_the_yarn_is_one_continuous_strand():
    """Crochet is made from a single strand; a representation in pieces is a different thing."""
    c, p = _path()
    assert len(p) > 0
    steps = np.linalg.norm(np.diff(p.points, axis=0), axis=1)
    # No vertex is a teleport: the largest step is a small multiple of the median, so the
    # polyline never jumps somewhere unconnected.
    assert steps.max() < np.median(steps) * 12, "the strand jumps, so it is not continuous"


def test_every_vertex_traces_back_to_a_counted_stitch():
    """Auditable, not merely deterministic: any point can be attributed to a cell."""
    c, p = _path()
    assert len(p.provenance) == len(p.points)
    rows = {r for r, _ in p.provenance}
    assert rows and all(isinstance(r, int) for r in rows)


def test_loop_targeting_leaves_genuinely_free_strands():
    """The ridge is geometry here, not shading: a free loop has nothing drawn through it."""
    c, p = _path()
    assert p.free_spans, "no free loops, so the texture is not physically represented"
    assert all(b > a for a, b in p.free_spans)


def test_the_yarn_radius_comes_from_the_gauge():
    """Yarn thickness is a consequence of the fabric's own numbers, not a style choice."""
    c, p = _path()
    stitch_w = 10.0 / c.gauge.stitches_per_10cm * 10.0
    assert abs(p.radius_mm - stitch_w * yarn.YARN_FILL * 0.5) < 1e-9


def test_tension_drifts_across_the_panel_rather_than_per_stitch():
    """The diagnosis B-704 left behind: local noise on a lattice is still a lattice.

    Drift must be correlated over distance -- neighbouring stitches displaced similarly,
    distant ones differently -- which is what makes fabric look handmade rather than noisy.
    """
    c, a = _path(seed=1)
    _, b = _path(seed=2)
    assert not np.allclose(a.points, b.points), "the drift field is not seeded"
    d = a.points - b.points
    near = np.linalg.norm(d[1:40] - d[:39], axis=1).mean()
    far = np.linalg.norm(d[1:40] - d[-39:], axis=1).mean()
    assert near < far, "displacement is uncorrelated, so it is noise rather than drift"


def test_relaxation_preserves_the_strand_and_its_provenance():
    c, p = _path()
    p = yarn.resample(p, per_segment=3)
    before = len(p)
    r = yarn.relax(p, iterations=5)
    assert len(r) == before
    assert len(r.provenance) == len(r.points)
    assert r.radius_mm == p.radius_mm


def test_the_curve_file_is_written_in_the_renderers_format():
    import tempfile, os
    c, p = _path()
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "y.txt")
        n = yarn.write_curve_file(p, f)
        lines = [l for l in open(f).read().splitlines() if l.strip()]
        assert n == len(lines)
        assert all(len(l.split()) == 4 for l in lines), "expected x y z radius per vertex"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("OK  ", name)
            except Exception as e:
                fails += 1; print("FAIL", name, repr(e)); traceback.print_exc()
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
