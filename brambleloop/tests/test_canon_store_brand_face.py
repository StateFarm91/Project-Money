"""Laura in the Store Foundation (D-FB-11, D-FB-12): a gated brand-face surface and an owner
preview variant that uses only her approved canonical portrait and can never be published.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_canon_store_brand_face.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import brand_face, content, lint, preview, readiness  # noqa: E402
from brambleloop.visual import canonical  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
FAILS = 0
_PAGES: dict = {}


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _page(vp: str, variant: str) -> str:
    key = (vp, variant)
    if key not in _PAGES:
        _PAGES[key] = preview.render_preview(None, vp, now=NOW, variant=variant)
    return _PAGES[key]


def test_brand_face_surface_references_the_canonical_identity():
    s = content.build()["brand_face"]
    v = s.value
    assert v["identity_id"] == canonical.IDENTITY_ID and v["name"] == "Laura"
    assert v["portrait_sha256"] == canonical.FACE_SHA256
    assert v["portrait_status"] == canonical.CANONICAL_REFERENCE
    assert v["integrity_ok"], v["integrity_problems"]
    assert v["customer_ready"] is False and v["publishable"] is False
    assert s.customer_facing is False
    assert v["role"] == "Founder/CEO (AI person)"
    assert v["public_identity"] == "Brambleloop's AI founder"


def test_brand_face_is_never_ready():
    rows = {r["key"]: r for r in readiness.evaluate(content.build())}
    row = rows["brand_face"]
    assert row["status"] != readiness.READY and row["status"] != readiness.FAIL, row
    codes = {f["code"] for f in row["findings"]}
    assert "BRAND_FACE_NOT_CUSTOMER_READY" in codes
    assert "BRAND_FACE_PHOTOREALISM" in codes
    assert "BRAND_FACE_MISSING_CANONICAL" in codes


def test_usage_plan_is_judged_not_everywhere():
    plan = {p["surface"]: p["laura"] for p in brand_face.PLACEMENTS}
    assert plan
    assert plan["shop_icon"] == "no"           # decided: logo mark is the icon
    assert plan["seller_portrait"] == "anchor"
    assert plan["banner"] == "anchor" and plan["about"] == "anchor"
    assert plan["non_wearable_listing"] == "product_first"
    assert plan["wearable_listing"] == "preferred"
    for p in brand_face.PLACEMENTS:
        assert p["why"], p


def test_customer_use_of_her_canonical_portrait_is_refused():
    for surface in ("seller_portrait", "banner", "about"):
        try:
            brand_face.image_for(surface, for_customers=True)
        except brand_face.BrandFaceRefused as exc:
            assert "not publication-approved" in str(exc)
            continue
        raise AssertionError(f"{surface}: a canonical reference was released to customers")
    ok = brand_face.image_for("owner_store_preview", for_customers=False)
    assert ok["label"] == brand_face.PREVIEW_IMAGE_LABEL and ok["customer_ready"] is False


def test_a_replaced_portrait_never_reaches_the_preview():
    import shutil
    import tempfile

    from brambleloop.visual import brief, identity

    tmp = Path(tempfile.mkdtemp())
    real = brief.ASSETS_DIR
    try:
        for p in Path(real).iterdir():
            if p.is_file():
                shutil.copy(p, tmp / p.name)
        (tmp / "identity_portrait.jpg").write_bytes(b"\xff\xd8a similar woman")
        brief.ASSETS_DIR = str(tmp)
        try:
            brand_face.image_for("owner_store_preview", for_customers=False)
        except identity.IdentityRefused:
            pass
        else:
            raise AssertionError("a replaced portrait was shown as Laura")
        assert brand_face.brand_face()["ok"] is False
    finally:
        brief.ASSETS_DIR = real
        shutil.rmtree(tmp, ignore_errors=True)


def test_brand_face_variant_is_labelled_safe_and_self_contained():
    pages = {vp: _page(vp, "brand_face") for vp in ("mobile", "desktop")}
    assert pages
    label = brand_face.PREVIEW_IMAGE_LABEL
    for vp, html in pages.items():
        assert html.startswith("<!doctype html>") and "Preview — not live" in html
        assert "<script" not in html.lower() and "javascript:" not in html.lower()
        assert not re.search(r"https?://", html), "external URL in the preview"
        assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"
        srcs = re.findall(r'src="([^"]*)"', html)
        assert srcs and all(s.startswith("data:image/") for s in srcs)
        assert "<form" not in html.lower() and "etsy.com" not in html.lower()
        # Every Laura element carries the label, visibly or in its accessible name.
        lauras = re.findall(r'<div class="[^"]*\blaura\b[^"]*"[^>]*>', html)
        assert lauras
        for el in lauras:
            assert 'role="img"' in el or 'class="lp laura"' in el, el
            if 'role="img"' in el:
                assert label in el.replace("&quot;", '"'), el
        assert html.count(label) >= len(lauras) // 2
        # Exactly the approved portrait's bytes, once, as the CSS source.
        uri = brand_face.image_for("x", for_customers=False)["data_uri"]
        assert html.count(uri) == 1


def test_standard_variant_is_unchanged_and_has_no_laura():
    html = _page("mobile", "standard")
    assert "--laura" not in html and brand_face.PREVIEW_IMAGE_LABEL not in html
    assert preview.render_preview(None, "mobile", now=NOW) == html


def test_brand_face_board_shows_etsy_crops_with_bases():
    html = _page("desktop", "brand_face")
    owner = html.split('<section class="owner"', 1)[1]
    for phrase in ("40 px (logo mark)", "70 px (logo mark)", "Phone centre crop 2:1 (ASSUMED)",
                   "Desktop banner 4:1", "Seasonal extension: winter",
                   "Etsy size UNVERIFIED", "Customer-facing gates for Laura imagery",
                   "Where Laura appears"):
        assert phrase in owner, phrase
    crops = brand_face.banner_crops()
    assert crops["phone"]["ok"] and crops["desktop"]["ok"], crops
    assert crops["phone"]["laura_inside_safe_area"]


def test_preview_copy_about_laura_is_truthful():
    shop = _page("desktop", "brand_face").split('<section class="owner"', 1)[0]
    text = re.sub(r"<[^>]+>", " ", shop)
    assert "Brambleloop's AI founder" in text.replace("&#x27;", "'")
    assert "She is an AI" in text
    assert lint.is_truthful(preview.ABOUT_LAURA_INTRO)
    assert lint.is_truthful("Laura · Brambleloop's AI founder")


def test_lint_allows_her_true_identity_and_fails_human_claims():
    ok = ["Hi, I'm Laura, Brambleloop's AI brand representative.",
          "Laura is Brambleloop's AI Brand & Customer Experience Director.",
          "Laura introduces our designs each season.",
          "Laura is not a real person; she is our AI brand representative.",
          "Laura, Brambleloop's AI founder", "Hi, I'm Laura, Brambleloop's AI founder and CEO.",
          "AI founder Laura reviewed the new collection."]
    bad = ["I learned to crochet from my grandmother.", "Laura hand-crochets every sample.",
           "Laura designed this cardigan.", "Designed by Laura.", "Our founder Laura",
           "Laura is a real woman who loves yarn.", "Hi, I'm Laura and I crochet every evening.",
           "When I was a little girl I loved wool.", "Laura tested every pattern.",
           "Laura grew up in Nova Scotia.", "Laura founded Brambleloop.",
           # Founder/CEO wording without AI disclosure, and legal-ownership/seller claims
           "Laura is the founder of Brambleloop.", "CEO Laura says hello", "Owned by Laura.",
           "Laura is the legal owner.", "Laura, our founder"]
    assert ok and bad
    for t in ok:
        assert lint.is_truthful(t), t
    for t in bad:
        codes = {f["code"] for f in lint.lint(t, voice=False)}
        assert codes & {"TRUTH_LAURA_HUMAN_CLAIM", "TRUTH_FOUNDER_STORY"}, t
    assert "TRUTH_LAURA_HUMAN_CLAIM" in {f["code"] for f in
                                        lint.lint("Laura hand-crochets every sample.")}


def test_summary_lists_the_variant_and_stays_not_live():
    out = preview.summary(None, now=NOW)
    assert "brand_face" in out["preview_variants"]
    assert out["live"] is False and out["published"] is False
    bf = [i for i in out["items"] if i["key"] == "brand_face"]
    assert bf and bf[0]["status"] not in ("READY",)


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
