"""W4-PRODREADY B1: the images Launch-0 actually uploads letter every word legibly at the size
it is shown (owner ruling 2026-10-19, D-W4-VISROLE-LEGIBILITY), under disclosed-render
contract 3, and the verifier is as strict as before.

What Launch-0 uploads is the disclosed-render set (hero, scale, detail) plus the verified
gallery supplements (materials, colour, construction, sizing) and the CONTENTS preview.
Contract 2 lettered the disclosure at 34 px and the size labels at 30 px on the 2000 px canvas,
which is 6.6 px and 5.8 px in a 390 px phone gallery. The gallery and contents frames used 64 /
50 / 40 px (10.9 px at 340, 9.8 and 7.8 px at 390).

* Every lettered line is recorded with a slot. `frame_role.text_tier` classifies it from the
  plan, and every essential line clears 11 px at its display size, on every frame of every
  release checked here.
* The verifier re-letters the contract-3 lines from its own CIR figures. A frame drawn under
  contract 2 (the old small type), a frame missing the second disclosure line, and a frame
  with an edited figure all fail. Nothing was relaxed.
* The disclosure keeps "not a photograph" whole on one line, inside the title-safe band.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_prodready_contract3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import io
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_prodready_c3_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-PRODREADY harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from PIL import Image, ImageDraw  # noqa: E402

from brambleloop.commerce.thumbnail import MIN_LEGIBLE_TEXT_PX  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish import mobile  # noqa: E402
from brambleloop.visual import disclosed_render as D  # noqa: E402
from brambleloop.visual import frame_role as FR  # noqa: E402
from brambleloop.visual import gallery_frames as GF  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402
from brambleloop.visual import render_verification as RV  # noqa: E402

# A polygon vessel (3 annotation facts), a flat blanket with a thin contrast row, a set of
# pieces: the three layouts the contract letters differently.
BUILDS = ("basket_medium", "cloudline_blanket", "hexagon_coasters")
_C: dict = {}


def _set(key):
    if key not in _C:
        _C[key] = D.listing_set(l0.cir_for(key))
    return _C[key]


def _px(entry) -> float:
    tier = FR.text_tier("", entry["slot"])
    return entry["pt"] * tier["display_px"] / K.CANVAS_PX


def _verdict(png: bytes, key: str, view: str) -> dict:
    cir = l0.cir_for(key)
    return RV.verify(png, cir=cir, view=view)


def test_contract_3_sizes_are_the_floor_at_the_real_display_size():
    # 3.1 (W4-PDF1): soft wall corners for render_contract.SOFT_CORNER_SLUGS only; the
    # contract-3 lettering this test measures is unchanged.
    assert K.CONTRACT_VERSION == "disclosed-render-contract/3.1"
    assert D.RENDERER_VERSION == "disclosed-render/3.1.0"
    assert RV.VERIFIER_VERSION.startswith("render-verification/3.")
    gallery = FR.LISTING_VIEW_PX == mobile.CONTEXT_MEANS[mobile.PHONE_GALLERY]["px"]
    assert gallery
    assert K.TEXT_PX * FR.LISTING_VIEW_PX / K.CANVAS_PX >= MIN_LEGIBLE_TEXT_PX
    assert K.CAPTION_PX == K.LABEL_PX == K.TEXT_PX
    assert GF.TITLE_PX * FR.GRID_PX / K.CANVAS_PX >= MIN_LEGIBLE_TEXT_PX
    for slot in ("disclosure", "annotation", "scale_label"):
        t = FR.text_tier("", slot)
        assert t["essential"] and t["display_px"] == 390, (slot, t)


def test_every_lettered_line_of_the_disclosed_set_is_legible_where_shown():
    seen = 0
    for key in BUILDS:
        frames = _set(key)
        assert len(frames) == 3, key
        for rf in frames:
            lay = rf.manifest["layout"]["caption"]["text_layout"]
            slots = {e["slot"] for e in lay}
            assert {"disclosure", "scale_label"} <= slots, (key, rf.view, slots)
            for e in lay:
                seen += 1
                assert _px(e) >= MIN_LEGIBLE_TEXT_PX, (key, rf.view, e)
                # inside the 8 % title-safe band on every side
                band = K.CANVAS_PX * mobile.TITLE_SAFE_MARGIN
                x0, y0, x1, y1 = e["box"]
                assert x0 >= band and y0 >= band, (key, rf.view, e)
                assert x1 <= K.CANVAS_PX - band and y1 <= K.CANVAS_PX - band, (key, rf.view, e)
            # "not a photograph" whole on one line
            assert any("not a photograph" in e["text"] for e in lay
                       if e["slot"] == "disclosure"), lay
    assert seen >= 25, seen


def test_the_honest_frames_still_verify_pass():
    assert BUILDS
    for key in BUILDS:
        frames = _set(key)
        assert frames, key  # INTEG3: non-empty before the loop (test_vacuity)
        for rf in frames:
            r = _verdict(rf.png, key, rf.view)
            assert r["status"] == "PASS", (key, rf.view, [c for c in r["checks"]
                                                          if c["status"] != "PASS"])
            assert rf.manifest["contract_version"] == K.CONTRACT_VERSION


def _old_caption(png: bytes) -> bytes:
    """The same frame with its disclosure re-lettered the contract-2 way: one line, 34 px."""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    cap = K.caption_layout()
    y0, y1 = cap[0][1][1], cap[-1][1][1] + 2 * K.CAPTION_PX
    d.rectangle([0, y0 - 6, K.CANVAS_PX - 1, y1], fill=K.BACKGROUND)
    f = K.font(34)
    w = d.textlength(K.DISCLOSURE, font=f)
    d.text((round((K.CANVAS_PX - w) / 2), y0), K.DISCLOSURE, fill=K.CAPTION, font=f)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_small_type_a_dropped_line_or_an_edited_figure_fails_verification():
    key = "cloudline_blanket"
    hero = next(rf for rf in _set(key) if rf.view == "hero")
    r = _verdict(_old_caption(hero.png), key, "hero")
    assert r["status"] != "PASS", r["status"]
    # the second disclosure line ("not a photograph") painted out
    img = Image.open(io.BytesIO(hero.png)).convert("RGB")
    d = ImageDraw.Draw(img)
    (_t, (_x, y)) = K.caption_layout()[1]
    d.rectangle([0, y - 4, K.CANVAS_PX - 1, y + K.CAPTION_PX + 14], fill=K.BACKGROUND)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = _verdict(buf.getvalue(), key, "hero")
    assert r["status"] != "PASS"
    # one figure of the finished size edited on the scale frame
    scale = next(rf for rf in _set(key) if rf.view == "scale")
    lines = scale.manifest["layout"]["caption"]["wrapped_lines"]
    target = next(t for t in lines if " cm " in t)
    placed = dict(K.annotation_layout(scale.manifest["layout"]["caption"]["lines"]))
    x, y = placed[target]
    digit = next(ch for ch in target if ch.isdigit())
    bad = target.replace(digit, "8" if digit != "8" else "3", 1)
    assert bad != target
    img = Image.open(io.BytesIO(scale.png)).convert("RGB")
    d = ImageDraw.Draw(img)
    d.fontmode = "1"
    d.rectangle([x, y, x + d.textlength(target, font=K.font(K.LABEL_PX)) + 4,
                 y + K.LABEL_PX + 12], fill=K.BACKGROUND)
    d.text((x, y), bad, fill=K.CAPTION, font=K.font(K.LABEL_PX))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = _verdict(buf.getvalue(), key, "scale")
    by = {c["check"]: c for c in r["checks"]}
    assert by["annotation_text"]["status"] == "FAIL", by["annotation_text"]


def test_lettering_that_cannot_fit_is_refused_never_shrunk():
    long = "x" * 400
    try:
        K.annotation_layout([long])
    except K.LetteringRefused:
        pass
    else:
        raise AssertionError("an unbreakable over-wide line was accepted")
    try:
        K.annotation_layout(["one two three four five six seven eight nine ten"] * 3)
    except K.LetteringRefused:
        pass
    else:
        raise AssertionError("more annotation lines than the contract rows were accepted")


def test_every_lettered_line_of_the_gallery_frames_is_legible_where_shown():
    seen = 0
    for key in BUILDS:
        cir = l0.cir_for(key)
        jobs = GF.applicable_jobs(cir)
        assert jobs, key
        for job in jobs:
            g = GF.render(cir, job)
            assert GF.verify(g.png, cir, g.manifest)["status"] == "PASS", (key, job)
            lay = g.manifest["text_layout"]
            assert any(e["slot"] == "disclosure" for e in lay), (key, job)
            for e in lay:
                seen += 1
                assert _px(e) >= MIN_LEGIBLE_TEXT_PX, (key, job, e)
                assert e["box"][2] <= K.zone_px(K.PRODUCT_ZONE)[2] + 2, (key, job, e)
    assert seen >= 20, seen


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
            print(f"FAIL {name}: {type(exc).__name__}: {exc}"[:800])
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
