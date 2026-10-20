"""W4-PRODREADY (owner ruling 2026-10-19, D-W4-VISROLE-LEGIBILITY): essential customer-facing
text is readable at the size it is ACTUALLY displayed. There is no blanket pixel floor.

* Each line a listing frame draws carries a `slot`. `frame_role.text_tier` classifies it from
  the frame plan, never from a model: essential at the 340 px grid (title, headline), essential
  at the 390 px phone gallery (product type, disclosure, rows, size and scale labels, colour
  names, preview caption), or secondary (brand line, pattern excerpt). An unnamed slot is
  essential at 340 px, the strict rule.
* Essential lines clear `thumbnail.MIN_LEGIBLE_TEXT_PX` there. The measured failures were the
  hero disclosure (8.0 px), "CROCHET PATTERN · PDF" (9.75 px), "180 cm adult" (10.1 px) and the
  colour names (9.4 px).
* A failure blocks deterministically (`check_frame_plan`) and in the role check. Secondary
  lines are reported, not blocked.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_prodready_legibility.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_prodready_leg_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-PRODREADY harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.commerce.thumbnail import MIN_LEGIBLE_TEXT_PX  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from brambleloop.publish import listing_assets as LA  # noqa: E402
from brambleloop.publish import mobile  # noqa: E402
from brambleloop.visual import frame_role as FR  # noqa: E402

# A round piece with a label wider than the piece (coasters), a flat blanket, and a long thin
# runner: the three layouts the size card and the hero draw differently.
BUILDS = ("hexagon_coasters", "cloudline_blanket", "harvest_runner")
_C: dict = {}


def _frames(key):
    if key not in _C:
        cir = launch0.cir_for(key)
        res = compile_cir(cir)
        twin = build_twin(cir, res)
        _C[key] = LA.build_frames(cir, twin, pattern_text=write_pattern(cir, res),
                                  difficulty="easy", pages=6, siblings=["another pattern"])
    return _C[key]


def _copy(frame):
    f = copy.copy(frame)
    f.image = frame.image.copy()
    f.image.info["layout"] = [dict(e) for e in frame.image.info.get("layout") or []]
    return f


def test_the_tier_table_reads_the_plan_and_the_display_sizes_are_the_real_ones():
    assert FR.LISTING_VIEW_PX == mobile.CONTEXT_MEANS[mobile.PHONE_GALLERY]["px"] == 390
    assert FR.GRID_PX == FR.LEGIBILITY_PX == 340
    for slot in ("title", "headline"):
        t = FR.text_tier("hero", slot)
        assert t["essential"] and t["display_px"] == 340, t
    for slot in ("product_type", "disclosure", "row_label", "row_value", "size_label",
                 "scale_reference", "colour_name", "caption"):
        t = FR.text_tier("size", slot)
        assert t["essential"] and t["display_px"] == 390, (slot, t)
    for slot in ("brand", "excerpt"):
        assert not FR.text_tier("hero", slot)["essential"], slot
    # anything the table does not name is essential at the smaller (stricter) size
    for slot in (None, "", "something_new"):
        t = FR.text_tier("collection", slot)
        assert t["essential"] and t["display_px"] == 340, (slot, t)
    # the floors the renderer sets are the ones the checker reads
    assert LA.min_pt_for("disclosure") * 390 / 2000 >= MIN_LEGIBLE_TEXT_PX
    assert LA.min_pt_for("title", role="hero") * 340 / 2000 >= MIN_LEGIBLE_TEXT_PX
    assert LA.min_pt_for("excerpt") == 14


def test_every_line_the_renderer_draws_names_its_slot():
    n = 0
    for key in BUILDS:
        for f in _frames(key):
            for e in f.image.info["layout"]:
                if e.get("kind") == "text" and str(e.get("text") or "").strip():
                    n += 1
                    assert e.get("slot"), (key, f.role, e)
    assert n > 60, n


def test_every_essential_line_clears_the_floor_at_its_display_size():
    seen = 0
    for key in BUILDS:
        frames = _frames(key)
        problems = LA.check_frame_plan(frames)
        assert not [p for p in problems if "ESSENTIAL_TEXT" in p], (key, problems)
        assert not problems, (key, problems)
        for f in frames:
            leg = FR.legibility(f)
            assert leg is not None and leg["ok"] is True, (key, f.role, leg)
            for ln in leg["lines"]:
                if ln["tier"] == FR.ESSENTIAL:
                    seen += 1
                    assert ln["px"] >= MIN_LEGIBLE_TEXT_PX, (key, f.role, ln)
    assert seen > 50, seen


def test_the_four_measured_failures_are_fixed_at_390_px():
    def px(frames, role, needle):
        for f in frames:
            if f.role != role:
                continue
            for e in f.image.info["layout"]:
                if e.get("kind") == "text" and needle in str(e.get("text")):
                    return e["pt"] * 390 / f.image.size[0]
        raise AssertionError(f"{needle!r} not drawn on {role}")

    for key in BUILDS:
        fr = _frames(key)
        assert px(fr, "hero", "not a photograph") >= MIN_LEGIBLE_TEXT_PX       # was 8.0
        assert px(fr, "hero", "CROCHET PATTERN") >= MIN_LEGIBLE_TEXT_PX        # was 9.75
        assert px(fr, "size", "180 cm adult") >= MIN_LEGIBLE_TEXT_PX           # was 10.1
        cir = launch0.cir_for(key)
        assert cir.colors, key
        for colour in cir.colors:
            assert px(fr, "materials", colour) >= MIN_LEGIBLE_TEXT_PX, colour  # was 9.4


def test_the_disclosure_keeps_not_a_photograph_whole_and_inside_the_title_safe_band():
    for key in BUILDS:
        hero = _frames(key)[0]
        lines = [e for e in hero.image.info["layout"] if e.get("slot") == "disclosure"]
        assert lines, key
        assert any(FR.DRAWN_DISCLOSURE in e["text"].lower() for e in lines), lines
        band = int(hero.image.size[1] * (1 - mobile.TITLE_SAFE_MARGIN))
        assert hero.image.info["layout"], key
        for e in hero.image.info["layout"]:
            if e.get("kind") == "text":
                assert e["box"][3] <= band, (key, e)


def test_the_size_label_is_on_the_image_and_clear_of_the_scale_bar():
    for key in BUILDS:
        size = next(f for f in _frames(key) if f.role == "size")
        w = size.image.size[0]
        m = int(w * 0.04)
        layout = size.image.info["layout"]
        label = next(e for e in layout if e.get("slot") == "size_label")
        bar = next(e for e in layout if e.get("kind") == "scale_bar")
        assert m <= label["box"][0] and label["box"][2] <= w - m, (key, label)
        overlap_w = min(label["box"][2], bar["box"][2]) - max(label["box"][0], bar["box"][0])
        overlap_h = min(label["box"][3], bar["box"][3]) - max(label["box"][1], bar["box"][1])
        assert overlap_w <= 0 or overlap_h <= 0, (key, label, bar)


def test_an_essential_line_below_the_floor_blocks_and_a_secondary_one_is_reported():
    frames = [_copy(f) for f in _frames("hexagon_coasters")]
    hero = frames[0]
    for e in hero.image.info["layout"]:
        if e.get("slot") == "disclosure":
            e["pt"] = 41            # the old fitted size: 8.0 px at 390 px
    problems = LA.check_frame_plan(frames)
    bad = [p for p in problems if p.startswith("LISTING_FRAME_1_ESSENTIAL_TEXT_ILLEGIBLE")]
    assert len(bad) == 2 and "8.0px at its 390px" in bad[0], problems
    checks = FR.role_checks(hero, slug="x", visual_role=FR.DISCLOSED_RENDER,
                            description=None)
    t = checks["text_legible_340"]
    assert t["passed"] is False and len(t["essential_failing"]) == 2, t
    # the brand line is secondary: at 9.4 px it is reported, never a failure
    clean = [_copy(f) for f in _frames("hexagon_coasters")]
    leg = FR.legibility(clean[0])
    assert [ln["slot"] for ln in leg["secondary_below_floor"]] == ["brand"], leg
    assert leg["ok"] is True
    checks = FR.role_checks(clean[0], slug="x", visual_role=FR.DISCLOSED_RENDER,
                            description=None)
    assert checks["text_legible_340"]["passed"] is True, checks["text_legible_340"]
    assert checks["text_legible_340"]["secondary_below_floor"], checks["text_legible_340"]
    # an unnamed line is held to the strict grid size: 58 pt clears 390 px, not 340 px
    odd = _copy(_frames("hexagon_coasters")[1])
    odd.image.info["layout"].append({"kind": "text", "box": [200, 1700, 600, 1760],
                                     "text": "unclassified", "pt": 58})
    assert not FR.legibility(odd)["ok"]
    # a line with no recorded size is unmeasured, never legible
    odd.image.info["layout"].append({"kind": "text", "box": [200, 1780, 600, 1800],
                                     "text": "no size", "pt": None, "slot": "row_value"})
    assert FR.legibility(odd)["ok"] is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback

            traceback.print_exc()
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:600])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
