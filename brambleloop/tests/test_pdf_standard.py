"""ENG-SALE-PIPELINE: the premium PDF standard, checked from the BUILT bytes
(`publish.pdf_standard`, D-OWNER-PDF-STANDARD).

Real documents: the certified hexagon coaster set rendered by `publish.pdf` in both editions,
with a synthetic seven-frame certified gallery (test_double images: flat colour PNGs standing
in for the certified campaign frames) placed through the `campaign_photos` hook. Each check
is then broken one at a time and must FAIL; UNKNOWN is never PASS.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_pdf_standard.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import hashlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from brambleloop.products import launch0 as L  # noqa: E402
from brambleloop.publish import pdf_photos as PP  # noqa: E402
from brambleloop.publish import pdf_standard as PS  # noqa: E402
from brambleloop.publish.pdf import build_pattern_pdf  # noqa: E402

ROLES = ["hero", "lifestyle", "detail", "size", "colour_context", "materials", "whats_included"]
_C: dict = {}


def frames(seed=0, n=7):
    """test_double: the certified campaign frames' bytes."""
    out = []
    for i, r in enumerate(ROLES[:n]):
        im = Image.new("RGB", (1800, 1800), ((40 + i * 25 + seed) % 256, 90, 120))
        b = io.BytesIO()
        im.save(b, "PNG")
        d = b.getvalue()
        out.append({"sha256": hashlib.sha256(d).hexdigest(), "role": r, "position": i + 1,
                    "data": d})
    return out


def _fixture():
    if not _C:
        cir = L.cir_for("hexagon_coasters")
        plan = PP.plan(frames())
        _C.update(cir=cir, plan=plan, expected=PP.expected(plan["slots"]))
        for t in PS.TERMINOLOGIES:
            _C[t] = build_pattern_pdf(cir, terminology=t, campaign_photos=plan["slots"]).pdf_bytes
        _C["base_US"] = build_pattern_pdf(cir, terminology="US").pdf_bytes
    return _C


def _status(r, name):
    return next(c["status"] for c in r["checks"] if c["check"] == name)


def test_both_engine_editions_pass_every_structural_check_from_their_bytes():
    """The engine layout's premium editions meet every structural and photo-slot rule. They
    still FAIL as a whole: the engine cover carries no owner logo (D-OWNER-PDF-LOGO), which
    is why the sale pipeline certifies only the owner template (test_sale_pipeline_e2e)."""
    C = _fixture()
    assert C["plan"]["problems"] == []
    for t in PS.TERMINOLOGIES:
        r = PS.check(C[t], cir=C["cir"], terminology=t, expected=C["expected"])
        assert r["layout"] == "engine"
        assert r["verdict"] == PS.FAIL and r["failed"] == ["logo:cover"], (t, r["failed"])
        r2 = PS.check(C[t], cir=C["cir"], terminology=t, expected=C["expected"],
                      require_template=True)
        assert set(r2["failed"]) == {"logo:cover", "layout"}, r2["failed"]
        for slot in PP.SLOTS:
            assert _status(r, f"slot:{slot}") == PS.PASS
        for name in ("sections", "licence_page", "stitch_counts", "schematic", "diagrams",
                     "page_range", "cover", "terminology", "no_uncertified_photos"):
            assert _status(r, name) == PS.PASS, name


def test_the_edition_must_be_the_one_checked():
    C = _fixture()
    r = PS.check(C["US"], cir=C["cir"], terminology="UK", expected=C["expected"])
    assert r["verdict"] == PS.FAIL and "terminology" in r["failed"]


def test_a_document_without_the_gallery_fails_every_photo_slot():
    C = _fixture()
    r = PS.check(C["base_US"], cir=C["cir"], terminology="US", expected=C["expected"])
    assert r["verdict"] == PS.FAIL
    assert {"slot:cover_hero", "slot:overview_lifestyle", "slot:progress",
            "slot:gallery"} <= set(r["failed"])


def test_pending_images_is_the_pre_image_reading_and_never_a_pass():
    C = _fixture()
    r = PS.check(C["base_US"], cir=C["cir"], terminology="US", expected=None, images="pending")
    assert r["verdict"] == "PASS_PENDING_IMAGES" and r["verdict"] != PS.PASS
    assert _status(r, "slot:gallery") == PS.PENDING


def test_images_that_are_not_the_certified_frames_never_count():
    C = _fixture()
    other = PP.expected(PP.plan(frames(seed=101))["slots"])
    r = PS.check(C["US"], cir=C["cir"], terminology="US", expected=other)
    assert r["verdict"] == PS.FAIL
    assert "slot:gallery" in r["failed"] and "no_uncertified_photos" in r["failed"]


def test_no_expectation_is_unknown_never_pass():
    C = _fixture()
    r = PS.check(C["US"], cir=C["cir"], terminology="US", expected=None)
    # Without an expectation every photo slot is UNKNOWN, never PASS (the engine cover's
    # missing logo FAILs on its own, so the verdict is FAIL here, still never PASS).
    assert r["verdict"] != PS.PASS and all(
        _status(r, f"slot:{s}") == PS.UNKNOWN for s in PP.SLOTS), r["checks"]
    assert PS.check(b"not a pdf", cir=C["cir"], terminology="US",
                    expected=C["expected"])["verdict"] == PS.UNKNOWN


def test_a_short_gallery_fails_the_gallery_slot():
    C = _fixture()
    plan = PP.plan(frames(n=5))         # hero..colour_context: 5 frames, 5 in the gallery
    assert plan["slots"]["gallery"] and len(plan["slots"]["gallery"]) == 5
    short = {k: list(v) for k, v in plan["slots"].items()}
    short["gallery"] = short["gallery"][:4]
    data = build_pattern_pdf(C["cir"], terminology="US", campaign_photos=short).pdf_bytes
    r = PS.check(data, cir=C["cir"], terminology="US", expected=PP.expected(short))
    assert "slot:gallery" in r["failed"], r["failed"]
    assert any("gallery page needs" in p for p in PP.plan(frames(n=4))["problems"])


def test_the_cover_hero_must_be_full_bleed():
    doc = {"pages": [{"index": 1, "width": 612.0, "lines": [], "text": "", "section": "Cover",
                      "images": [{"sha256": "h", "dct": True, "drawn": (500.0, 300.0)}]}],
           "page_count": 1}
    exp = {"slots": {"cover_hero": ["h"]}, "renditions": {"h": {}}}
    got = {c["check"]: c for c in PS._slots(doc, exp)}
    assert got["slot:cover_hero"]["status"] == PS.FAIL
    assert "full bleed" in got["slot:cover_hero"]["why"]


def test_a_row_without_its_stitch_count_fails():
    doc = {"pages": [{"index": 7, "section": "Instructions", "text": "", "images": [],
                      "lines": ["Rnd 1 (cream):", "6 sc in ring.", "(6 sts)",
                                "Rnd 2 (cream):", "[inc] x 6.", "after Rnd 2",
                                "Rnd 3 (cream):", "[sc, inc] x 6.", "(18 sts)"]}]}
    r = PS._stitch_counts(doc)
    assert r["status"] == PS.FAIL and "1 of 3" in r["why"], r
    doc["pages"][0]["lines"].insert(5, "(12 sts)")
    assert PS._stitch_counts(doc)["status"] == PS.PASS


def test_the_licence_page_must_carry_every_decided_paragraph():
    C = _fixture()
    doc = PS.read(C["US"])
    assert PS._licence(doc)["status"] == PS.PASS
    for p in doc["pages"]:
        if p["section"] == "Terms and support":
            p["text"] = "Terms and support\nSupport and credits"
    assert PS._licence(doc)["status"] == PS.FAIL


def test_family_aware_sections_and_page_range():
    C = _fixture()
    assert PS.family(C["cir"]) == "home"
    doc = PS.read(C["US"])
    assert PS._page_range(doc, "home")["status"] == PS.PASS
    assert PS._page_range({"page_count": 3}, "home")["status"] == PS.FAIL

    class Graded:                       # a graded garment needs its size chart and care
        grading = object()
        title = C["cir"].title
    got = {c["check"]: c for c in PS._sections(doc, Graded(), "US")}
    assert got["sections"]["status"] == PS.FAIL and "Sizes and fit" in got["sections"]["why"]


def test_schematic_and_diagrams_are_required():
    C = _fixture()
    doc = PS.read(C["US"])
    for p in doc["pages"]:
        if p["section"] == "Instructions":
            p["images"] = []
    got = {c["check"]: c for c in PS._schematic_and_diagrams(doc, set())}
    assert got["diagrams"]["status"] == PS.FAIL
    for p in doc["pages"]:
        p["images"] = []
    got = {c["check"]: c for c in PS._schematic_and_diagrams(doc, set())}
    assert got["schematic"]["status"] == PS.FAIL


def test_renditions_are_deterministic_and_refuse_wrong_bytes():
    f = frames()[0]
    assert PP.rendition(f["data"]) == PP.rendition(f["data"])
    bad = dict(f, sha256="0" * 64)
    assert PP.plan([bad])["problems"] and not PP.plan([bad])["slots"]["cover_hero"]


def test_omitting_the_hook_leaves_the_document_unchanged():
    from datetime import date

    cir = L.cir_for("hexagon_coasters")
    a = build_pattern_pdf(cir, terminology="US", released_on=date(2026, 11, 1)).pdf_bytes
    b = build_pattern_pdf(cir, terminology="US", released_on=date(2026, 11, 1),
                          campaign_photos=None).pdf_bytes
    assert a == b


if __name__ == "__main__":
    import traceback

    failed = 0
    for name, fn in sorted((n, f) for n, f in dict(globals()).items() if n.startswith("test_")):
        try:
            fn()
            print("OK  ", name)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", name)
            traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
