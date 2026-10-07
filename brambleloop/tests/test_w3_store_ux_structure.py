"""Wave 3 lane B: the v2 Owner Store Preview -- structure, escaping, labels, sources.

The v2 page is the proposed storefront that replaces the owner-rejected v1. These tests hold
it to the same safety rules as v1 (escaped, script-free, no external URL, never publishable,
"Preview -- not live") and to the wave's rules for Laura (only her verified canonical
portrait, every use labelled internal) and for products (only verified disclosed renders).

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w3_store_ux_structure.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import brand_face, lint, preview, preview_sources, preview_v2  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
LABEL = brand_face.PREVIEW_IMAGE_LABEL
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


def page(vp: str = "mobile", variant: str = "v2") -> str:
    if (vp, variant) not in _PAGES:
        _PAGES[(vp, variant)] = preview.render_preview(None, vp, now=NOW, variant=variant)
    return _PAGES[(vp, variant)]


def shop(html: str) -> str:
    return html.split('<div class="frame">', 1)[1].split('<section class="board"', 1)[0]


def test_variants_registered_and_default_unchanged():
    assert {"standard", "brand_face", "v2", "compare"} <= set(preview.VARIANTS)
    assert preview.summary(None, now=NOW)["preview_variants"] == sorted(preview.VARIANTS)
    # the default is still v1, so existing callers and tests see the baseline
    assert 'data-fold="first-screen"' not in page("mobile", "standard")


def test_v2_is_labelled_safe_and_self_contained():
    pages = [page(vp, v) for vp in ("mobile", "desktop") for v in ("v2", "compare")]
    assert pages
    for html in pages:
        assert html.startswith("<!doctype html>") and "Preview — not live" in html
        assert 'name="robots" content="noindex,nofollow"' in html
        assert "<script" not in html.lower() and "javascript:" not in html.lower()
        assert not re.search(r"https?://", html), "external URL"
        assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"
        assert "<form" not in html.lower() and "<iframe" not in html.lower()
        assert "etsy.com" not in html.lower()
        srcs = re.findall(r'\ssrc="([^"]*)"', html)
        assert srcs and all(s.startswith("data:image/") for s in srcs), srcs[:3]
        urls = re.findall(r'url\("([^"]*)"\)', html)
        assert all(u.startswith("data:image/") for u in urls), urls[:3]
        assert all('alt="' in i for i in re.findall(r"<img\b[^>]*>", html))
        assert "never publishable" in html


def test_v2_has_every_required_surface():
    m, d = page("mobile"), page("desktop")
    for html in (m, d):
        s = shop(html)
        for needle in ('data-fold="first-screen"', 'class="bn', 'class="icon"', "<h1>",
                       "Announcement", 'aria-label="Shop sections"', 'class="card"',
                       'class="about"', "About Brambleloop", "Policies",
                       "Questions", "<details", "Returns and refunds",
                       "AI-use, digital-item and image disclosures", "New shop, no reviews yet",
                       "CA$6.50", "CA$7.50", "CA$4.00"):
            assert needle in s, needle
        board = html.split('<section class="board"', 1)[1]
        for needle in ("16 px", "40 px", "70 px", "Dark surround", "Desktop: whole canvas",
                       "Phone 390 px", "Small phone 320 px", "Winter, desktop",
                       "Winter, phone crop", "Awkward crops", "Text contrast",
                       "Customer-facing gates for Laura imagery", "Where Laura appears",
                       "Owner readiness", "Sources"):
            assert needle in board, needle
    assert 'class="owner-card"' in d          # desktop header carries the brand-face card


def test_every_laura_element_is_labelled_and_uses_only_her_verified_portrait():
    uri = brand_face.image_for("x", for_customers=False)["data_uri"]
    for vp in ("mobile", "desktop"):
        html = page(vp)
        assert html.count(uri) == 1, "Laura's bytes must be embedded exactly once"
        els = re.findall(r'<div class="[^"]*\blaura\b[^"]*"[^>]*>', html)
        assert len(els) >= 4, els
        for el in els:
            assert 'role="img"' in el and LABEL in el.replace("&quot;", '"').replace(
                "&#x27;", "'"), el
        visible = shop(html)
        assert visible.count(LABEL) >= 2      # banner caption strip + About portrait tag
        assert "Brambleloop&#x27;s AI founder" in visible


def test_laura_is_never_released_for_customers():
    try:
        brand_face.image_for("banner", for_customers=True)
    except brand_face.BrandFaceRefused:
        pass
    else:
        raise AssertionError("a canonical reference was released for customers")


def test_owner_concept_image_is_not_embedded():
    # D-FB-17/18: the owner's canonical banner (not the scratchpad concept file) is shown,
    # labelled internal and not publication-approved; its Laura is owner-confirmed for that
    # banner only
    html = page("desktop")
    assert "owner_banner_concept" not in html
    assert "confirmed by the owner's review of this banner (D-FB-18)" in html
    assert "not publication-approved" in html


def test_listing_images_are_only_verified_disclosed_renders():
    html = page("mobile")
    frames = list(preview._FRAMES.values())
    assert len(frames) == 5      # W4-PIPE: one hero frame per Launch-0 product (5)
    for f in frames:
        if f["status"] == "VERIFIED":
            b64 = __import__("base64").b64encode(f["png"]).decode()[:200]
            assert html.count(b64) == 1, f["build"]
    cards = re.findall(r'<article class="card">.*?</article>', shop(html), re.S)
    assert len(cards) == 5
    for c in cards:
        assert "Digital rendering, not a photograph" in c


def test_withheld_frame_is_not_shown_in_v2():
    from brambleloop.products import launch0 as l0

    cir = l0.cir_for("hexagon_coasters")
    key = ("hexagon_coasters", cir.fingerprint)
    saved = preview._FRAMES.get(key)
    preview._FRAMES[key] = {"build": "hexagon_coasters", "cir_slug": cir.slug,
                            "cir_fingerprint": cir.fingerprint, "status": "WITHHELD",
                            "verifier_status": "FAIL", "png": b"\x89PNG-not-shown"}
    try:
        html = preview.render_preview(None, "mobile", now=NOW, variant="v2")
        assert "Image withheld" in html and "--r-hexagon_coasters" not in html
    finally:
        if saved is None:
            preview._FRAMES.pop(key, None)
        else:
            preview._FRAMES[key] = saved


def test_database_text_is_escaped():
    from brambleloop.core.db import Database
    from brambleloop.core.models import Listing

    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as s:
        s.add(Listing(product_slug="hexagon-coaster-set", version="1.0.0",
                      title='<script>alert("x")</script> Coasters & "Mats"', description="d",
                      tags=[], price_cad=4.0))
    html = preview.render_preview(db, "mobile", now=NOW, variant="v2")
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; Coasters &amp; &quot;Mats&quot;" \
        in html


def test_peer_copy_is_escaped():
    real = preview_sources.copy

    def evil():
        out = real()
        v = dict(out.value)
        v["announcement"] = '<img src=x onerror=alert(1)> "quoted" & more'
        v["tagline"] = "</style><script>x</script>"
        return preview_sources.Sourced(v, preview_sources.PEER, "test", [])

    preview_sources.copy = evil
    try:
        html = preview.render_preview(None, "mobile", now=NOW, variant="v2")
    finally:
        preview_sources.copy = real
    assert "<script" not in html.lower() and "onerror=alert" not in html.replace(
        "onerror=alert(1)&gt;", "")
    assert "&lt;img src=x onerror=alert(1)&gt; &quot;quoted&quot; &amp; more" in html


def test_sources_tolerate_absent_or_broken_peers():
    ident, cp, spec = preview_sources.identity(), preview_sources.copy(), preview_sources.banner_spec()
    assert ident.source in (preview_sources.PEER, preview_sources.FALLBACK)
    assert ident.value["mark_svg"].lstrip().startswith("<svg")
    assert set(preview_sources.FALLBACK_PALETTE) <= set(ident.value["palette"])
    assert cp.value["tagline"] and cp.value["announcement"] and cp.value["trust"]
    w, h = spec.value["canvas"]
    assert w > h > 0 and spec.value["phone_aspect"] > 0 and spec.value["basis"]
    real = preview_sources._import
    preview_sources._import = lambda path: None
    try:
        assert preview_sources.identity().source == preview_sources.FALLBACK
        assert preview_sources.copy().source == preview_sources.FALLBACK
        assert preview_sources.banner_spec().source == preview_sources.FALLBACK
        html = preview.render_preview(None, "mobile", now=NOW, variant="v2")
        assert "fallback" in html and 'data-fold="first-screen"' in html
    finally:
        preview_sources._import = real


def test_fallback_copy_passes_truth_and_voice_lint():
    texts = []

    def walk(v):
        if isinstance(v, str):
            texts.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(preview_sources.FALLBACK_COPY)
    assert len(texts) > 10
    for t in texts:
        found = lint.lint(t, voice=True)
        assert not found, (t, found)


def test_v2_shop_page_has_no_truth_findings():
    for vp in ("mobile", "desktop"):
        text = preview_v2.visible_text(shop(page(vp)))
        found = [f for f in lint.lint(text, voice=False) if f["kind"] == lint.TRUTH]
        assert not found, found[:3]
        assert not re.search(r"\b\d[\d,]*\s*(sales|reviews|favou?rites|orders)\b", text, re.I)


def test_banner_geometry_keeps_laura_and_lockup_in_the_phone_window():
    spec = preview_sources.banner_spec().value
    g = preview_v2._geometry(spec)
    lo, hi = g["win"]
    assert lo >= 0 and hi <= 1 and hi > lo
    for k in ("who", "lock"):
        a, b = g[k]
        assert lo - 1e-9 <= a < b <= hi + 1e-9, (k, g[k], g["win"])
    # the desktop-only wings lie outside the phone window
    assert g["wing_l"][1] <= lo + 1e-9 and g["wing_r"][0] >= hi - 1e-9
    # 2.5:1 (the owner's concept canvas) keeps the same guarantee
    g2 = preview_v2._geometry({"canvas": (1983, 793), "phone_aspect": 2.0})
    assert g2["win"][0] <= g2["who"][0] and g2["lock"][1] <= g2["win"][1]


def test_text_contrast_meets_wcag_aa():
    pal = preview_sources.identity().value["palette"]
    pairs = preview_v2.text_pairs(pal)
    assert pairs
    for role, fg, bg, minimum in pairs:
        assert preview_v2.contrast(fg, bg) >= minimum, (role, fg, bg)
    assert preview_v2.contrast("#000000", "#FFFFFF") == 21.0


def test_deterministic():
    a = preview.render_preview(None, "desktop", now=NOW, variant="v2")
    assert a == page("desktop")


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
