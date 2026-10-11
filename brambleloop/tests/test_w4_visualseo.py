"""W4-VISUALSEO: certified gallery supplements are measured where a shopper sees them.

The listing-set certificate exports the disclosed set (hero/scale/detail) followed by verified
supplement frames (ANGLE, CONSTRUCTION, COLOUR_CONTEXT, SIZING, MATERIALS, CONTENTS). Before this
change the phone/full-gallery mobile contexts and the label-in-pixels check covered only the
disclosed set; a supplement reached the certificate on its producer's word for both. Now each
supplement is measured (`release_gates.supplement_presentation`) and a failing one is left out
with the reason (fail closed); the readings are ANDed into COMMERCIAL_QA / POLICY_PROVENANCE.
No threshold changed. Local, deterministic, no network, no spend.
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
_TMP = tempfile.mkdtemp(prefix="w4_visualseo_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from PIL import Image, ImageDraw  # noqa: E402

from brambleloop.publish import disclosed_listing as DL  # noqa: E402
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.publish import listing_set as ls  # noqa: E402
from brambleloop.publish import release_gates as RG  # noqa: E402
from brambleloop.visual import disclosed_render as DR  # noqa: E402
from brambleloop.visual import gallery_frames as G  # noqa: E402
from brambleloop.visual import launch_imagery as LI  # noqa: E402
from brambleloop.visual import render_contract as K  # noqa: E402

SLUG = "hexagon-coaster-set"
_C: dict = {}


def primary():
    if "p" not in _C:
        _listing, title, prim, siblings, _cat = LI._primary_for(SLUG)
        _C["p"], _C["title"], _C["siblings"] = prim, title, siblings
    return _C["p"]


def supplement(job: str = "COLOUR_CONTEXT") -> dict:
    key = f"f:{job}"
    if key not in _C:
        prim = primary()
        png = G.render(prim, job, siblings=_C["siblings"]).png
        _C[key] = {"job": job, "png": png, "position": 4,
                   "alt_text": LI.supplement_alt_text(job, _C["title"]),
                   "honesty_label": LI.supplement_label(job),
                   "purpose": LI.supplement_purpose(job), "medium": LI.supplement_medium(job),
                   "sha256": "0" * 64, "represented_variant": None}
    return dict(_C[key])


def _img(png: bytes):
    return Image.open(io.BytesIO(png)).convert("RGB")


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_a_real_supplement_is_measured_and_passes():
    f = supplement()
    got = RG.supplement_presentation(f, _img(f["png"]), cir=primary())
    assert got["ok"] is True, got
    r = got["readings"]
    assert r["label_in_image"] is True and r["label_in_alt_text"] is True
    assert set(r["title_safe_ink"]) == set(RG.SUPPLEMENT_CONTEXT_PX)
    assert all(v == 0 for v in r["title_safe_ink"].values())


def test_ink_in_the_title_safe_band_is_refused():
    f = supplement()
    img = _img(f["png"])
    d = ImageDraw.Draw(img)
    w, h = img.size
    d.rectangle([0, h // 2 - 120, max(8, round(w * 0.02)), h // 2 + 120], fill=(20, 20, 20))
    f["png"] = _png(img)
    got = RG.supplement_presentation(f, img, cir=primary())
    assert got["ok"] is False
    assert any("title-safe band" in p for p in got["problems"]), got["problems"]


def test_a_supplement_without_its_label_in_the_pixels_is_refused():
    f = supplement()
    blank = Image.new("RGB", _img(f["png"]).size, K.BACKGROUND)
    f["png"] = _png(blank)
    got = RG.supplement_presentation(f, blank, cir=primary())
    assert got["ok"] is False and got["readings"]["label_in_image"] is False
    # the label field alone never stands in for the pixels
    assert f["honesty_label"] == DL.DISCLOSURE


def test_alt_text_must_open_with_the_label():
    f = supplement()
    f["alt_text"] = f"{_C['title']}: colours. {DL.DISCLOSURE}"
    got = RG.supplement_presentation(f, _img(f["png"]), cir=primary())
    assert got["ok"] is False and got["readings"]["label_in_alt_text"] is False
    f = supplement()
    f["alt_text"] = DL.DISCLOSURE + "." + " x" * DL.ALT_TEXT_MAX
    assert RG.supplement_presentation(f, _img(f["png"]), cir=primary())["ok"] is False


def test_contents_must_carry_the_preview_label_not_a_render_label():
    f = supplement()
    f.update(job=el.CONTENTS, honesty_label=DL.DISCLOSURE,
             alt_text=f"{DL.DISCLOSURE}. pages")
    got = RG.supplement_presentation(f, _img(f["png"]), cir=primary())
    assert got["readings"]["label_in_image"] is False and got["ok"] is False
    f.update(honesty_label=el.PREVIEW_LABEL, alt_text=f"{el.PREVIEW_LABEL}. pages")
    got = RG.supplement_presentation(f, _img(f["png"]), cir=primary())
    assert got["readings"]["label_in_image"] is True and got["ok"] is True


def test_disclosed_supplements_leaves_out_a_failing_frame_with_the_reason():
    good = supplement("COLOUR_CONTEXT")
    bad = supplement("MATERIALS")
    img = _img(bad["png"])
    w, h = img.size
    ImageDraw.Draw(img).rectangle([0, h // 2 - 120, max(8, round(w * 0.02)), h // 2 + 120],
                                  fill=(20, 20, 20))
    bad["png"] = _png(img)
    good["position"], bad["position"] = 4, 5
    hero = DR.render(primary(), "hero").png
    rec = {"frames": [{"position": 1, "view": "hero",
                       "disclosed_render": {"job": el.DESIRE}}]}
    original = LI.supplements_for_certificate
    LI.supplements_for_certificate = lambda *a, **k: {"frames": [good, bad], "refused": {},
                                                      "listing": SLUG}
    try:
        sups, qa, notes = RG.disclosed_supplements(rec, [("hero", hero, "alt")], slug=SLUG,
                                                   version=primary().version)
    finally:
        LI.supplements_for_certificate = original
    jobs = [s.job for s in sups]
    assert jobs == ["COLOUR_CONTEXT"], jobs
    assert "MATERIALS" in notes and notes["MATERIALS"].startswith("presentation:"), notes
    assert qa["mobile"]["ok"] is True and qa["mobile"]["full_gallery_frames"] == 2
    assert qa["disclosure"]["ok"] is True
    assert list(qa["mobile"]["frames"]) == ["COLOUR_CONTEXT"]


def _rec_ok():
    return {"qa": {"layout_qa": {"ok": True}, "frame_set": {"ok": True},
                   "mobile": {"ok": True}, "hero_thumbnail": {"ok": True},
                   "asset_truth": {"ok": True},
                   "frames": {"hero": {"legibility_340": {"ok": True}}}},
            "frames": [{"view": "hero", "structural_truth": {"status": "PASS"}}]}


def test_gate_results_read_the_supplement_readings_additively():
    base = {"verified": [True], "layout_qa": {"ok": True}, "frame_set": {"ok": True}}
    before = ls.disclosed_gate_results(_rec_ok(), exported=True, dimensions_ok=True,
                                       supplement_qa=base)
    assert before and all(v == el.PASSED for v in before.values()), before
    measured = dict(base, mobile={"ok": True}, disclosure={"ok": True})
    assert ls.disclosed_gate_results(_rec_ok(), exported=True, dimensions_ok=True,
                                     supplement_qa=measured) == before
    bad_mobile = dict(measured, mobile={"ok": False})
    got = ls.disclosed_gate_results(_rec_ok(), exported=True, dimensions_ok=True,
                                    supplement_qa=bad_mobile)
    assert got[el.COMMERCIAL_QA] == el.FAILED
    bad_label = dict(measured, disclosure={"ok": False})
    got = ls.disclosed_gate_results(_rec_ok(), exported=True, dimensions_ok=True,
                                    supplement_qa=bad_label)
    assert got[el.POLICY_PROVENANCE] == el.FAILED


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
