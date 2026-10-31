"""W4-MULTIPIECE: a flat piece the pattern makes N times is shown as the set of N.

Root cause (found W4-IMAGES): the rounds form drew `make` copies on the hero (coasters), the
flat form drew one, and the verifier measured only the one piece it was given, so "Nordic
Snowflake Ornament Set (6)" verified with a one-piece hero whose alt text said "the whole
piece". Now the flat hero draws every copy, the verifier counts them (`object_count`) and
checks each, and the alt text states the count. Single-piece heroes are byte-identical.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_multipiece.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import dataclasses
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_multipiece_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import disclosed_listing as DL  # noqa: E402
from brambleloop.visual import disclosed_render as DR  # noqa: E402
from brambleloop.visual import render_verification as RV  # noqa: E402

_C: dict = {}


def cir(build):
    if build not in _C:
        b = L.BUILDERS.get(build) or L.PROPOSED_BUILDERS[build]
        _C[build] = b()
    return _C[build]


def hero(build):
    key = ("hero", build)
    if key not in _C:
        _C[key] = DR.render(cir(build), "hero")
    return _C[key]


def _one_piece(c):
    """The same CIR with make=1: what the old renderer drew for a set."""
    comps = [dataclasses.replace(c.components[0], make=1)] + list(c.components[1:])
    return dataclasses.replace(c, components=comps)


def test_a_one_piece_render_of_a_make_6_product_fails_truth():
    c = cir("snowflake_ornaments")
    assert c.components[0].make == 6
    partial = DR.render(_one_piece(c), "hero")
    v = RV.verify(partial.png, cir=c, view="hero")
    assert v["status"] == "FAIL", v["status"]
    oc = next(x for x in v["checks"] if x["check"] == "object_count")
    assert oc["status"] == "FAIL" and oc["found"] == 1 and oc["expected"] == 6


def test_the_set_hero_draws_and_verifies_every_copy():
    for build, n in (("snowflake_ornaments", 6), ("placemat_pair", 2)):
        fr = hero(build)
        assert fr.manifest["layout"]["objects"] == n
        v = RV.verify(fr.png, cir=cir(build), view="hero")
        assert v["status"] == "PASS", (build, v["failed"], v["unknown"])
        names = [x["check"] for x in v["checks"]]
        assert "object_count" in names and "stitch_counts" in names
        sc = next(x for x in v["checks"] if x["check"] == "stitch_counts")
        assert sc["per_copy"] == ["PASS"] * n


def test_a_recoloured_copy_fails_the_whole_set():
    import io

    from PIL import Image, ImageDraw

    fr = hero("snowflake_ornaments")
    im = Image.open(io.BytesIO(fr.png)).convert("RGB")
    # Paint over part of one copy (the last) with another contract yarn colour.
    c = cir("snowflake_ornaments")
    other = next(v for k, v in c.colors.items() if k == "cream")
    from brambleloop.visual import render_contract as K

    zx0, zy0, zx1, zy1 = K.zone_px(K.PRODUCT_ZONE)
    rgb = K.hex_rgb(other)
    d = ImageDraw.Draw(im)
    d.rectangle([zx1 - 260, zy1 - 520, zx1 - 120, zy1 - 300], fill=rgb)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    v = RV.verify(buf.getvalue(), cir=c, view="hero")
    assert v["status"] != "PASS", v["checks"]


def test_alt_text_states_the_true_count_and_per_piece_size():
    alt = DL.alt_text(hero("snowflake_ornaments").manifest, cir("snowflake_ornaments"))
    assert "all 6 pieces laid flat" in alt and "cm each" in alt and "whole piece" not in alt
    alt2 = DL.alt_text(hero("placemat_pair").manifest, cir("placemat_pair"))
    assert "both pieces laid flat" in alt2 and "cm each" in alt2


def test_single_piece_heroes_are_byte_identical_to_before():
    # sha256 of the single-piece hero frames, pinned so a multi-piece change cannot move
    # them. Re-pinned once, deliberately, for disclosed-render contract 3 (W4-PRODREADY,
    # 2026-10-19: legible lettering and the zone that gives it rows); the contract-2 pins
    # were basket_medium 2853edb459191a8d, cloudline_blanket bf30686b90bff8e0,
    # hexagon_coasters dde60f6bbe780d18, snowfall_throw c7c15427340597e4.
    from brambleloop.visual import render_contract as K

    assert K.CONTRACT_VERSION == "disclosed-render-contract/3.1"   # 3.1: basket-small corners only
    before = {"basket_medium": "a0011d65108949e3", "cloudline_blanket": "95f59af9b7e0bdee",
              "hexagon_coasters": "fd296d0e413c4bd8", "snowfall_throw": "0d76c06c3339e5a9"}
    assert before
    for build, prefix in before.items():
        assert hashlib.sha256(hero(build).png).hexdigest().startswith(prefix), build


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
