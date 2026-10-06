"""v1.1 lane F: the Owner Store Preview (F-926) and the store-readiness provider.

The provider honours the cross-lane contract and never raises; the preview is escaped,
script-free, carries no external URL, says "Preview -- not live", shows no fabricated social
proof, and shows a listing image only when the disclosed render verifies on its exact bytes
(D-FB-7). No network, no model.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_store_preview.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import lint, preview  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
STATUSES = {"OK", "DEGRADED", "BLOCKED", "UNKNOWN"}
FAILS = 0

try:
    import numpy  # noqa: F401 - the disclosed renderer's verifier needs it
    RENDERER_AVAILABLE = True
except ImportError:
    RENDERER_AVAILABLE = False


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _db():
    from brambleloop.core.db import Database

    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _contract(out: dict) -> None:
    assert out["status"] in STATUSES, out["status"]
    assert "as_of" in out and out["basis"] in ("measured", "estimated", "modelled", "unknown")
    assert isinstance(out["items"], list) and isinstance(out["sources"], list)
    json.dumps(out)


def test_summary_contract_without_db():
    out = preview.summary(None, now=NOW)
    _contract(out)
    assert out["items"]
    assert out["preview_path"] == "/cc/store-preview"
    assert out["live"] is False and out["published"] is False
    assert out["sizes_counted_as_products"] is False and out["products"] == 3
    img = [i for i in out["items"] if i["key"] == "listing_images"]
    assert img and img[0]["status"] == "UNKNOWN"     # not computed, so not reported


def test_summary_contract_with_empty_db():
    out = preview.summary(_db(), now=NOW)
    _contract(out)
    assert out["status"] in ("DEGRADED", "BLOCKED")
    assert out["as_of"].startswith("2026-10-06T12:00")


def test_summary_never_raises_on_broken_db():
    class Broken:
        def session(self):
            raise RuntimeError("database unreachable")

    out = preview.summary(Broken(), now=NOW)
    _contract(out)


def test_summary_accepts_bare_session():
    db = _db()
    with db.session() as s:
        out = preview.summary(s, now=NOW)
    _contract(out)


def _frame_part(html: str) -> str:
    return html.split('<div class="frame">', 1)[1].split('<section class="owner"', 1)[0]


def test_preview_is_labelled_safe_and_self_contained():
    pages = {vp: preview.render_preview(None, vp, now=NOW) for vp in ("mobile", "desktop")}
    assert pages
    for vp, html in pages.items():
        assert html.startswith("<!doctype html>")
        assert "Preview — not live" in html and f'class="vp-{vp}"' in html
        assert "<script" not in html.lower() and "javascript:" not in html.lower()
        assert not re.search(r"https?://", html), "external URL in the preview"
        assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"
        srcs = re.findall(r'src="([^"]*)"', html)
        assert srcs and all(s.startswith("data:image/") for s in srcs), srcs
        imgs = re.findall(r"<img\b[^>]*>", html)
        assert imgs and all('alt="' in i for i in imgs)
        assert "<form" not in html.lower()
        assert "etsy.com" not in html.lower()


def test_preview_is_deterministic():
    a = preview.render_preview(None, "desktop", now=NOW)
    b = preview.render_preview(None, "desktop", now=NOW)
    assert a == b


def test_invalid_viewport_falls_back_to_mobile():
    html = preview.render_preview(None, "<script>", now=NOW)
    assert 'class="vp-mobile"' in html and "<script" not in html


def test_preview_escapes_database_text():
    from brambleloop.core.models import Listing

    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="hexagon-coaster-set", version="1.0.0",
                      title='<script>alert("x")</script> Coasters & "Mats"', description="d",
                      tags=[], price_cad=4.0))
    html = preview.render_preview(db, "mobile", now=NOW)
    assert "<script" not in html.lower()
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt; Coasters &amp; &quot;Mats&quot;" \
        in html


def test_preview_shows_no_fabricated_social_proof():
    html = preview.render_preview(None, "desktop", now=NOW)
    shop = _frame_part(html)
    assert "no reviews" in shop.lower()
    assert not re.search(r"\b\d[\d,]*\s*(sales|reviews|favou?rites|orders)\b", shop, re.I)
    text = re.sub(r"<[^>]+>", "\n", re.sub(r'src="[^"]*"', "", shop))
    found = [f for f in lint.lint(text, voice=False) if f["kind"] == lint.TRUTH]
    assert not found, found


def test_preview_shows_every_surface():
    html = preview.render_preview(None, "mobile", now=NOW)
    for needle in ("Brambleloop Studio", "Crochet patterns checked row by row",
                   "Announcement", "About Brambleloop Studio", "Delivery (digital)",
                   "Returns and refunds", "Pattern licence and customer use", "Privacy",
                   "AI-use, digital-item and image disclosures", "Frequently asked questions",
                   "Questions and support", "Home &amp; Table", "Baby &amp; Nursery",
                   "CA$6.50", "CA$7.50", "CA$4.00", "3 sizes in one pattern",
                   "Owner readiness", "Settings that need the owner signed in"):
        assert needle in html, needle


def test_listing_images_verified_or_withheld():
    html = preview.render_preview(None, "mobile", now=NOW)
    frames = list(preview._FRAMES.values())
    assert len(frames) == 3
    if RENDERER_AVAILABLE:
        assert all(f["status"] == "VERIFIED" for f in frames), [
            (f["cir_slug"], f.get("verifier_status"), f.get("why")) for f in frames]
        assert html.count("data:image/png;base64,") == 3
        assert "Image withheld" not in _frame_part(html)
    else:   # fail closed: an image nobody verified is not shown
        assert all(f["status"] == "WITHHELD" for f in frames)
        assert "data:image/png;base64," not in html


def test_unverified_frame_is_withheld_not_shown():
    from brambleloop.products import launch0 as l0

    cir = l0.cir_for("hexagon_coasters")
    key = ("hexagon_coasters", cir.fingerprint)
    saved = preview._FRAMES.get(key)
    preview._FRAMES[key] = {"build": "hexagon_coasters", "cir_slug": cir.slug,
                            "cir_fingerprint": cir.fingerprint, "status": "WITHHELD",
                            "verifier_status": "FAIL", "png": b"\x89PNG-not-shown"}
    try:
        html = preview.render_preview(None, "mobile", now=NOW)
        assert "Image withheld" in html and "D-FB-7" in html
        out = preview.summary(None, verify_images=True, now=NOW)
        img = [i for i in out["items"] if i["key"] == "listing_images"]
        assert img and img[0]["status"] == "FAIL" and out["status"] == "BLOCKED"
    finally:
        if saved is None:
            preview._FRAMES.pop(key, None)
        else:
            preview._FRAMES[key] = saved


def test_summary_with_image_verification():
    out = preview.summary(None, verify_images=True, now=NOW)
    _contract(out)
    img = [i for i in out["items"] if i["key"] == "listing_images"]
    assert img and len(img[0]["frames"]) == 3
    assert all("png" not in f for f in img[0]["frames"])
    if RENDERER_AVAILABLE:
        assert img[0]["status"] == "READY"


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
