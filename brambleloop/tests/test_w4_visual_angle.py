"""W4-VISUAL: the disclosed vessel ANGLE view (F-254 "the side, back or inside").

The renderer draws a vessel from a raised camera (render_contract.ANGLE_DEG) and the
independent pixel verifier measures it with the same un-projection it uses for the hero.
A flat or plan-form product refuses the view; a frame verified at the wrong camera angle or
with a recoloured round does not pass. Local, deterministic, no network, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual_angle_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from PIL import Image  # noqa: E402

from brambleloop.core.artifacts import ArtifactStore  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import disclosed_render as DR  # noqa: E402
from brambleloop.visual import launch_imagery as LI  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402
from brambleloop.visual import render_verification as RV  # noqa: E402

_C: dict = {}


def cir(key):
    if key not in _C:
        _C[key] = launch0.cir_for(key)
    return _C[key]


BASKETS = ("basket_small", "basket_medium", "basket_large")


def test_angle_view_verifies_for_every_basket_size():
    assert BASKETS
    for key in BASKETS:
        c = cir(key)
        fr = DR.render(c, "angle")
        assert fr.manifest["job"] == "ANGLE" and fr.manifest["role"] == "angle"
        assert fr.manifest["layout"]["alpha_deg"] == K.ANGLE_DEG
        assert fr.manifest["disclosure"] == K.DISCLOSURE
        assert fr.manifest["generated"] is False and fr.manifest["photograph"] is False
        v = RV.verify(fr.png, cir=c, view="angle")
        assert v["status"] == "PASS", (key, v["failed"], v["unknown"])
        names = {ch["check"] for ch in v["checks"]}
        assert {"stitch_counts", "colour_placement", "wall_height_cm", "extent_cm"} <= names


def test_angle_is_refused_for_flat_and_plan_products():
    for key in ("hexagon_coasters", "cloudline_blanket"):
        try:
            DR.render(cir(key), "angle")
        except DR.RenderRefused:
            continue
        raise AssertionError(f"{key}: an angle view was drawn for a non-vessel")
    hero = DR.render(cir("hexagon_coasters"), "hero")
    v = RV.verify(hero.png, cir=cir("hexagon_coasters"), view="angle")
    assert v["status"] == "FAIL" and "view" in v["failed"], v


def test_camera_angle_is_measured_not_trusted():
    c = cir("basket_medium")
    angle = DR.render(c, "angle").png
    hero = DR.render(c, "hero").png
    assert RV.verify(angle, cir=c, view="hero")["status"] != "PASS"
    assert RV.verify(hero, cir=c, view="angle")["status"] != "PASS"


def test_recoloured_round_fails_the_angle_view():
    c = cir("basket_large")
    fr = DR.render(c, "angle")
    img = Image.open(io.BytesIO(fr.png)).convert("RGB")
    pal = {tuple(v) for v in DR._palette(c).values()}
    colours = sorted({img.getpixel((x, y)) for x in range(0, img.width, 7)
                      for y in range(0, img.height, 7)} & pal)
    assert len(colours) >= 2, colours
    a, b = colours[0], colours[1]
    px = img.load()
    swapped = 0
    for x in range(img.width):
        for y in range(img.height // 2, img.height * 3 // 4):
            if px[x, y] == a:
                px[x, y] = b
                swapped += 1
    assert swapped
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert RV.verify(buf.getvalue(), cir=c, view="angle")["status"] != "PASS"


def test_basket_listing_covers_angle_and_others_do_not_claim_it():
    store = ArtifactStore(os.path.join(_TMP, "store"))
    rec = LI.assemble("nursery-nesting-baskets", store=store)
    assert "ANGLE" in rec["covered"], rec["missing"]
    assert rec["angle_frames"] and rec["angle_frames"][0]["verification"] == "PASS"
    assert rec["method"]["angle_view"] == LI.ANGLE_METHOD
    coasters = LI.assemble("hexagon-coaster-set", store=store)
    assert "ANGLE" not in coasters["covered"] and not coasters["angle_frames"]


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
