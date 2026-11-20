"""W4-VERIFY-POCKETS: the pixel verifier learns the "pockets" assembled form and closed bands.

* pockets (W4-CAND garlands): hero = every pocket the pattern makes, scale = one pocket with
  its own size line, detail = the body's relief rounds laid flat. Each is measured against a
  pocket model recomputed from the CIR's rows (`render_verification._pockets_expectation`),
  not against the frame's manifest.
* closed bands (`cir.assembly.band_axis`): an assembled planar frame proves every closed band
  is drawn as its front half, at half its length around, recomputed from the band's rows.

Every new rule has a known-good PASS and a known-bad FAIL. The bad cases that matter most
corrupt the *renderer itself* for the whole run (render and verify), so the frame still
equals a fresh drawing byte for byte: only the CIR-derived model can catch them.
Local, deterministic, no network, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.products import moment_candidates as mc  # noqa: E402
from brambleloop.products import pipeline_board as pb  # noqa: E402
from brambleloop.visual import assembled_render as A  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import render_verification as V  # noqa: E402

VIEWS = ("hero", "scale", "detail")


@contextmanager
def _patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def _verify(cir, view):
    return V.verify(D.render(cir, view).png, cir=cir, view=view)


def _status(v, check):
    return next((c["status"] for c in v["checks"] if c["check"] == check), None)


def test_garland_frames_pass_on_the_pocket_model():
    cir = mc.snowfall_advent_garland()
    body = next(c for c in cir.components if c.name == A.plan(cir).body)
    assert body.make > 1
    for view in VIEWS:
        v = _verify(cir, view)
        assert v["status"] == "PASS", (view, v["failed"], v["unknown"])
        got = {c["check"] for c in v["checks"]}
        assert {"object_count", "extent_cm", "colour_set", "legibility_340", "annotation_text",
                "marks_in_product_zone", "placement_redraw"} <= got, (view, got)
        assert v["measured"]["assembly"] == "pockets"
        want = body.make if view == "hero" else 1
        oc = next(c for c in v["checks"] if c["check"] == "object_count")
        assert oc["found"] == oc["expected"] == want, oc
        assert v["reads_manifest"] is False


def test_a_missing_pocket_fails_the_hero():
    cir = mc.snowfall_advent_garland()
    real = A._pockets

    def one_short(*a, **k):
        pl = real(*a, **k)
        pl.extra["copies"] -= 1
        return pl

    # The renderer itself drops a pocket for the whole run, so the frame still equals a fresh
    # drawing: the count comes from the CIR's `make`, and that is what has to catch it.
    with _patched(A, "_pockets", one_short):
        v = _verify(cir, "hero")
    assert v["status"] == "FAIL" and "object_count" in v["failed"], v["failed"]
    assert _status(v, "placement_redraw") == "PASS"


def test_a_loop_drawn_at_full_length_fails_the_scale():
    """The loop is a closed band: laid flat it shows half its rows. A renderer that draws
    every row makes a pocket too tall, and only the CIR's arithmetic says so."""
    cir = mc.snowfall_advent_garland()
    real = A._pockets

    def full_loop(*a, **k):
        pl = real(*a, **k)
        tab = pl.placed[2]
        assert tab.name == pl.extra["tab"]
        tab.comp = replace(tab.comp, rows=list(tab.comp.rows) * 2)
        return pl

    with _patched(A, "_pockets", full_loop):
        v = _verify(cir, "scale")
    assert v["status"] == "FAIL" and "extent_cm" in v["failed"], v["failed"]
    assert _status(v, "placement_redraw") == "PASS"


def test_a_detail_with_extra_rounds_fails():
    cir = mc.snowfall_advent_garland()
    real = A._relief_window

    def wider(c, rows):
        lo, hi = real(c, rows)
        return lo, min(max(rows), hi + 3)

    with _patched(A, "_relief_window", wider):
        v = _verify(cir, "detail")
    assert v["status"] == "FAIL" and "extent_cm" in v["failed"], v["failed"]


def test_a_recoloured_stitch_fails_the_pocket_frame():
    import io

    from PIL import Image

    cir = mc.snowfall_advent_garland()
    png = D.render(cir, "scale").png
    img = Image.open(io.BytesIO(png)).convert("RGB")
    rgb = {k: V.K.hex_rgb(x) for k, x in cir.colors.items()}
    a, b = sorted(set(r.color for c in cir.components for r in c.rows))[:2]
    w, h = img.size
    hit = next((x, y) for y in range(h // 3, h) for x in range(w) if img.getpixel((x, y)) == rgb[a])
    from PIL import ImageDraw

    ImageDraw.floodfill(img, hit, rgb[b], thresh=0)
    out = io.BytesIO()
    img.save(out, format="PNG")
    v = V.verify(out.getvalue(), cir=cir, view="scale")
    assert v["status"] == "FAIL" and "placement_redraw" in v["failed"], v["failed"]


def test_closed_bands_pass_flat_on_planar_frames():
    for cir in (pb.pencil_roll_cir(), pb.stocking_cir()):
        for view in ("hero", "scale"):
            v = _verify(cir, view)
            bands = [c for c in v["checks"] if c["check"].startswith("closed_band_flat:")]
            assert bands, (cir.slug, view)
            assert v["status"] == "PASS", (cir.slug, view, v["failed"], v["unknown"])


def test_a_closed_band_drawn_unfolded_fails():
    """The renderer lays the band at full length for the whole run: the frame matches a
    fresh drawing and its extent matches the (equally wrong) layout, so only the band rule,
    recomputed from the band's rows, can fail it."""
    cir = pb.pencil_roll_cir()
    real = A._lay_band_flat

    def unfolded(p, axis, c):
        why = real(p, axis, c)
        if why is None and axis == "rows":
            m = len(p.comp.rows)
            p.rows = (1, m)
            length = p.twin.row_top_cm[m]
            if (p.grain == "up") == (axis == "rows"):
                p.up = length
            else:
                p.across = length
        return why

    with _patched(A, "_lay_band_flat", unfolded):
        v = _verify(cir, "hero")
    assert v["status"] == "FAIL" and "closed_band_flat:band" in v["failed"], v["failed"]
    assert _status(v, "placement_redraw") == "PASS"


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert tests
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
