"""W4-VISUAL2: the remaining gallery work after W4-VISUAL.

* wiring #7 -- `commerce.search_evidence` counts the sizes and colours a listing sells from
  its certified CIR (and Launch-0 sibling variants), never a hard-coded 1, so SIZING and
  COLOUR_CONTEXT applicability is measured rather than assumed; no CIR is UNMEASURED.
* CONTENTS -- `visual.contents_frame` previews the release's certified PDF (real pages), is
  verified on its exact bytes against that PDF and the certified CIR, carries the preview
  label (never the render disclosure), and enters the listing-set certificate through the
  same supplement path as every other gallery frame.
* harvest-table-runner (3.8:1) -- elongated flat pieces draw hero/scale on the contract
  diagonal (`render_contract.diagonal_deg`); `render_verification` recomputes the rotation
  from the CIR and un-rotates every glyph. The 25 % fill gate is unchanged and now passes.
Local, deterministic, no network, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual2_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.commerce import search_evidence as SE  # noqa: E402
from brambleloop.products import launch0  # noqa: E402


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/se.sqlite")
    db.create_all()
    return db


def _certify(db, slug, version, jobs):
    from brambleloop.core.models import ListingSetCertificateRecord

    with db.session() as s:
        s.add(ListingSetCertificateRecord(product_slug=slug, version=version, state="valid",
                                          certificate={"frames": [{"job": j} for j in jobs]}))


def test_sizes_and_colours_come_from_the_certified_cir():
    basket = launch0.candidate("nursery-nesting-baskets")
    small = launch0.cir_for(basket.variants[0].build)
    assert len(basket.variants) == 3
    cat, sizes, colours = SE._category_for(small.slug)
    assert sizes == 3, sizes                       # S/M/L sold on the primary's listing
    assert colours == len(small.colors) and colours > 1, colours
    med = launch0.cir_for("basket_medium")
    _cat, msizes, mcolours = SE._category_for(med.slug)
    assert msizes == 1 and mcolours == len(med.colors)     # a sibling sells its one size
    assert SE._category_for("no-such-product-anywhere")[1:] == (None, None)


def test_gallery_applicability_is_measured_not_assumed():
    db = _db()
    basket = launch0.candidate("nursery-nesting-baskets")
    small = launch0.cir_for(basket.variants[0].build)
    base = ["DESIRE", "SCALE", "DETAIL", "ANGLE", "CONSTRUCTION", "MATERIALS"]
    _certify(db, small.slug, small.version, base)
    g = SE.gallery(db, small.slug, small.version)
    assert g["sizes"] == 3 and g["colours"] == len(small.colors)
    # with sizes/colours hard-coded to 1 these two jobs were silently not applicable
    assert "SIZING" in g["applicable"] and "COLOUR_CONTEXT" in g["applicable"], g
    assert {"SIZING", "COLOUR_CONTEXT"} <= set(g["missing"]) and g["status"] == SE.FAIL
    _certify(db, "no-such-product-anywhere", "1.0.0", base)
    u = SE.gallery(db, "no-such-product-anywhere", "1.0.0")
    assert u["status"] == SE.UNMEASURED, u


# ---- CONTENTS ----------------------------------------------------------------------------

_PDF: dict = {}


def _pdf(slug):
    if slug not in _PDF:
        from datetime import date

        from brambleloop.publish.pdf import build_pattern_pdf
        from brambleloop.runtime import pipeline

        cir = pipeline._engineered_cir(slug)
        _PDF[slug] = (cir, build_pattern_pdf(cir, terminology="US",
                                             released_on=date(2026, 10, 7)).pdf_bytes)
    return _PDF[slug]


def test_contents_frame_is_the_certified_pdf_and_verifies_only_on_it():
    import hashlib
    import io

    from PIL import Image

    from brambleloop.publish import layout_qa
    from brambleloop.visual import contents_frame as CF

    cir, pdf = _pdf("hexagon-coaster-set")
    other_cir, other_pdf = _pdf("cloudline-baby-blanket")
    sha = hashlib.sha256(pdf).hexdigest()
    fr = CF.render(pdf, slug=cir.slug, version=cir.version, title=cir.title,
                   editions=["UK", "US"])
    assert fr.manifest["facts"]["pages"] >= 1 and fr.manifest["label"] == "Preview of the pattern document"
    ok = CF.verify(fr.png, pdf, cir, fr.manifest, certified_sha256=sha, editions=["UK", "US"])
    assert ok["status"] == "PASS", ok
    assert not layout_qa.inspect(Image.open(io.BytesIO(fr.png)).convert("RGB"), position=6,
                                 expect_text=True).problems
    # another product's PDF is not this release's document
    wrong = CF.render(other_pdf, slug=cir.slug, version=cir.version, title=cir.title,
                      editions=["UK", "US"])
    v = CF.verify(wrong.png, other_pdf, cir, wrong.manifest,
                  certified_sha256=hashlib.sha256(other_pdf).hexdigest(), editions=["UK", "US"])
    assert v["status"] == "FAIL" and "pdf_names_release" in v["failed"], v
    # a PDF that is not the file on record
    v = CF.verify(fr.png, pdf, cir, fr.manifest, certified_sha256="0" * 64, editions=["UK", "US"])
    assert v["status"] == "FAIL" and "pdf_is_certified_file" in v["failed"], v
    # one changed pixel
    img = Image.open(io.BytesIO(fr.png)).convert("RGB")
    img.putpixel((1000, 900), (255, 0, 0))
    buf = io.BytesIO(); img.save(buf, format="PNG")
    v = CF.verify(buf.getvalue(), pdf, cir, dict(fr.manifest,
                  image_sha256=hashlib.sha256(buf.getvalue()).hexdigest()),
                  certified_sha256=sha, editions=["UK", "US"])
    assert v["status"] == "FAIL" and "pixels_are_the_pages" in v["failed"], v
    # an edition claim the record does not make
    v = CF.verify(fr.png, pdf, cir, fr.manifest, certified_sha256=sha, editions=["US"])
    assert v["status"] == "FAIL" and "facts_agree" in v["failed"], v


def test_contents_is_certified_through_the_supplement_path_with_the_preview_label():
    import hashlib

    from brambleloop.core.artifacts import ArtifactStore
    from brambleloop.publish import listing_set as ls
    from brambleloop.runtime import pipeline
    from brambleloop.visual import launch_imagery as LI

    cir, pdf = _pdf("hexagon-coaster-set")
    store = ArtifactStore(os.path.join(_TMP, "contents"))
    sha = store.put(f"{cir.slug}/{cir.version}/pattern-US.pdf", pdf, "application/pdf").sha256
    real = pipeline._certified_pdf_hashes
    try:
        pipeline._certified_pdf_hashes = lambda db, s, v, r: {"US": sha} if s == cir.slug else None
        # no database: the certified PDF cannot be read, so CONTENTS is refused, never padded
        none = LI.supplements_for_certificate(cir.slug, cir.version, start=4, store=store,
                                              release_fingerprint=cir.fingerprint)
        assert "CONTENTS" in none["refused"] and "CONTENTS" not in [f["job"] for f in none["frames"]]
        offer = LI.supplements_for_certificate(cir.slug, cir.version, start=4, store=store,
                                               release_fingerprint=cir.fingerprint, db=object())
        jobs = [f["job"] for f in offer["frames"]]
        assert jobs == ["COLOUR_CONTEXT", "MATERIALS", "CONTENTS"], (jobs, offer["refused"])
        c = offer["frames"][-1]
        assert c["medium"] == "PATTERN_PREVIEW" and c["honesty_label"] == "Preview of the pattern document"
        assert c["alt_text"].startswith("Preview of the pattern document") \
            and c["alt_text"] == LI.expected_alt_text(cir.slug, "CONTENTS")
        assert LI.check_supplement(cir.slug, cir.version, "CONTENTS", c["png"], db=object(),
                                   store=store)["status"] == "PASS"
        # the upload-time check against a different certified PDF refuses the same bytes
        _oc, other = _pdf("cloudline-baby-blanket")
        osha = store.put("x/other.pdf", other, "application/pdf").sha256
        pipeline._certified_pdf_hashes = lambda db, s, v, r: {"US": osha}
        assert LI.check_supplement(cir.slug, cir.version, "CONTENTS", c["png"], db=object(),
                                   store=store)["status"] == "FAIL"
    finally:
        pipeline._certified_pdf_hashes = real
    frame = dict(position=6, asset_id="x-contents", sha256=c["sha256"], job="CONTENTS",
                 purpose="CUSTOMER_INFORMATION", medium="PATTERN_PREVIEW",
                 kind=ls.DISCLOSED_SUPPLEMENT, represented_variant="single")
    ls.CertifiedFrame(**frame, honesty_label=c["honesty_label"], alt_text=c["alt_text"])
    for bad in ({"honesty_label": ls_disclosure(), "alt_text": ls_disclosure() + ". x"},
                {"honesty_label": c["honesty_label"], "alt_text": "a pattern"}):
        try:
            ls.CertifiedFrame(**frame, **bad)
            raise AssertionError(f"accepted {bad}")
        except ls.ListingSetRefused:
            pass
    try:   # a preview cannot do any job but CONTENTS (never the hero)
        ls.CertifiedFrame(**dict(frame, job="DESIRE", position=1),
                          honesty_label=c["honesty_label"], alt_text=c["alt_text"])
        raise AssertionError("a pattern preview was certified as DESIRE")
    except ls.ListingSetRefused:
        pass
    assert hashlib.sha256(c["png"]).hexdigest() == c["sha256"]


def ls_disclosure():
    from brambleloop.publish.disclosed_listing import DISCLOSURE

    return DISCLOSURE


# ---- elongated flat pieces: the diagonal hero/scale ------------------------------------------

def test_the_runner_is_drawn_on_the_diagonal_verified_and_legible_without_moving_the_gate():
    from brambleloop.publish import disclosed_listing as DL
    from brambleloop.runtime import pipeline
    from brambleloop.visual import disclosed_render as DR
    from brambleloop.visual import render_contract as K
    from brambleloop.visual import render_verification as RV

    cir = pipeline._engineered_cir("harvest-table-runner")
    model = RV.expected_model(cir)
    deg = RV.flat_rotation(model, "hero")
    assert deg is not None and -80 <= deg <= -10, deg
    assert RV.flat_rotation(model, "detail") is None
    for view in ("hero", "scale"):
        fr = DR.render(cir, view)
        assert fr.manifest["layout"]["rotation_deg"] == RV.flat_rotation(model, view)
        v = RV.verify(fr.png, cir=cir, view=view)
        assert v["status"] == "PASS", (view, v["failed"], v["unknown"])
        assert v["measured"]["rows"] == len(model["rows"])
        leg = DL._thumb_legibility(fr.png, model, 1)
        assert leg["ok"], (view, leg["problems"])
    # the gate itself is untouched
    import inspect
    assert "coverage < 0.25" in inspect.getsource(DL._thumb_legibility)
    # the upright drawing of the same runner still fails that unchanged gate
    real = K.diagonal_deg
    try:
        K.diagonal_deg = lambda *a, **k: None
        upright = DR.render(cir, "hero")
    finally:
        K.diagonal_deg = real
    leg = DL._thumb_legibility(upright.png, model, 1)
    assert not leg["ok"] and any("fills" in p for p in leg["problems"]), leg
    # ... and is not what the contract says this piece's hero is
    assert RV.verify(upright.png, cir=cir, view="hero")["status"] != "PASS"


def test_a_recoloured_stitch_on_the_diagonal_fails_and_square_pieces_stay_upright():
    import io

    from PIL import Image, ImageDraw

    from brambleloop.runtime import pipeline
    from brambleloop.visual import disclosed_render as DR
    from brambleloop.visual import render_contract as K
    from brambleloop.visual import render_verification as RV

    cir = pipeline._engineered_cir("harvest-table-runner")
    fr = DR.render(cir, "hero")
    img = Image.open(io.BytesIO(fr.png)).convert("RGB")
    pal = [K.hex_rgb(v) for v in cir.colors.values()]
    assert len(pal) >= 2
    cx, cy = K.CANVAS_PX // 2, int(K.zone_px(K.PRODUCT_ZONE)[1] + K.zone_px(K.PRODUCT_ZONE)[3]) // 2
    seed = next((x, y) for y in range(cy - 40, cy + 40) for x in range(cx - 40, cx + 40)
                if img.getpixel((x, y)) == pal[0])
    ImageDraw.floodfill(img, seed, pal[1], thresh=0)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    v = RV.verify(buf.getvalue(), cir=cir, view="hero")
    assert v["status"] == "FAIL" and "colour_placement" in v["failed"], v["failed"]
    # every product below the elongation threshold keeps its upright, byte-identical frames
    assert K.diagonal_deg(79.2, 96.4, "hero") is None and K.diagonal_deg(32, 122, "detail") is None
    blanket = launch0.cir_for(launch0.candidate("cloudline-baby-blanket").variants[0].build)
    assert "rotation_deg" not in DR.render(blanket, "hero").manifest["layout"]


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
