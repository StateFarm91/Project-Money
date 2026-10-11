"""W4-STOREFRONT: customer storefront preview + owner Store area.

* The customer view (`preview.render_preview(..., variant="storefront")`, the Command Center's
  default) shows only customer material: verified images or a neutral placeholder (never an
  unverified asset), titles, prices, "Digital download (PDF pattern)", populated categories,
  concise descriptions and the material disclosures. Every internal item lives in one folded
  owner evidence panel; nothing is deleted (the earlier variants still render).
* `etsy_controls()` comes from the quoted constraints on file; UNKNOWN carries no number.
* The owner catalogue is the 8-product launch collection: Launch-0 + the D-FB-9 proposal.
* `/api/cc/store/catalogue|image|pdf` need an owner session; an unverified image is never served.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_w4_storefront.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import re
import socket
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_storefront_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'sf.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*_a, **_k):
    raise OSError("network refused by the storefront harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.store_foundation import copy_v2, owner_store, preview  # noqa: E402
from brambleloop.store_foundation import preview_v2 as V2  # noqa: E402
from brambleloop.store_foundation import storefront as SF  # noqa: E402

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
_PAGES: dict = {}


def page(vp: str = "mobile") -> str:
    if vp not in _PAGES:
        _PAGES[vp] = preview.render_preview(None, vp, now=NOW, variant="storefront")
    return _PAGES[vp]


def test_variant_registered_module_default_unchanged_owner_default_is_storefront():
    assert "storefront" in preview.VARIANTS
    assert preview.DEFAULT_OWNER_VARIANT == "storefront"
    std = preview.render_preview(None, "mobile", now=NOW)
    assert 'data-variant="storefront"' not in std            # module default is still v1
    for v in ("standard", "brand_face", "v2", "compare"):  # nothing deleted
        assert preview.render_preview(None, "mobile", now=NOW, variant=v).startswith("<!doctype html>")


def test_page_is_a_labelled_self_contained_preview():
    for vp in ("mobile", "desktop"):
        html = page(vp)
        assert html.startswith("<!doctype html>") and SF.PREVIEW_LABEL in html
        assert "not the real Etsy storefront" in html and "not the Etsy storefront" in html
        assert 'name="robots" content="noindex,nofollow"' in html
        assert "<script" not in html.lower() and "javascript:" not in html.lower()
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", html), "external URL"
        assert not re.search(r"\son[a-z]+\s*=", html), "inline event handler"
        assert "<form" not in html.lower() and "<iframe" not in html.lower()
        urls = re.findall(r'url\("([^"]*)"\)', html)
        assert urls and all(u.startswith("data:image/") for u in urls), urls[:2]
        srcs = re.findall(r'\ssrc="([^"]*)"', html)
        assert all(s.startswith("data:image/") for s in srcs), srcs[:2]


def test_customer_view_has_no_internal_material():
    cust = SF.customer_html(page())
    assert cust, "customer section not found"
    text = V2.visible_text(cust).lower()
    # The one allowance: Etsy's required AI disclosure, verbatim from its owner
    # (gates.platform_policy.DISCLOSURES["ai_assisted_design"], COPY v3). "Checked before
    # release" there is plain English for "before it is published" and the sentence must not be
    # reworded on the shop page, so exactly that sentence -- and nothing else -- is excused from
    # the jargon guard. It must actually be present (an allowance for an absent sentence is a
    # silent hole), and any other "release" still fails.
    from brambleloop.gates.platform_policy import DISCLOSURES

    allowed = re.sub(r"\s+", " ", DISCLOSURES["ai_assisted_design"]).lower()
    flat = re.sub(r"\s+", " ", text)
    assert allowed in flat, "the Etsy AI disclosure is missing from the customer view"
    text = flat.replace(allowed, " ")
    assert V2.jargon_hits(text) == [], V2.jargon_hits(text)
    banned = [t for t in copy_v2.BANNED_TECHNICAL_TERMS
              if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", text)]
    assert banned == [], banned
    for internal in ("sha256", "readiness", "verifier", "gate", "fingerprint", "d-fb-",
                     "owner_login", "unverified", "repo_asserted", "basis"):
        assert internal not in text, internal
    assert "[copy:" not in cust, "unfilled copy placeholder in the customer view"


def test_owner_evidence_panel_keeps_everything_folded_and_separate():
    html = page()
    i = html.index('<details class="owner" data-owner-evidence="1">')
    assert html.index('data-customer-view="1"') < i
    owner = html[i:]
    assert "<details class=\"owner\" data-owner-evidence=\"1\" open" not in html   # folded
    for item in ("Owner readiness", "Listing images (rendered and verified at load)", "sha256",
                 "Where titles and prices come from", "Settings that need the owner signed in",
                 "How the trust lines are backed", "What Etsy lets the shop control",
                 "Categories hidden until populated", "Customer copy source"):
        assert item in owner, item


def test_cards_titles_prices_digital_label_and_verified_images_only():
    html = page()
    cust = SF.customer_html(html)
    cards = re.findall(r'<a class="card"[^>]*data-product="([^"]+)"', cust)
    coll = SF.collection(None)
    launch = [p for p in coll if p["launch_status"] == "LAUNCH_0"
              or (p["launch_status"] == SF.CAP1_SCOPE and SF.customer_gates_pass(p)[0])]
    assert sorted(cards) == sorted(p["slug"] for p in launch) and len(cards) >= 5
    assert cust.count(SF.DIGITAL_LABEL) >= 2 * len(cards)  # card + sheet
    for p in launch:
        assert f"CA${p['price_cad']:.2f}" in cust, p["slug"]
    frames = {f["build"]: f for f in (preview.hero_frame(p["representative"]["build"]) for p in launch)}
    assert frames
    for build, f in frames.items():
        if f["status"] == "VERIFIED" and not f.get("pieces_finding"):
            assert f'im-{build}' in cust and f".im-{build}{{background-image" in html
        else:
            assert f'im-{build}' not in html
    # A withheld frame becomes the placeholder, never its asset.
    fake = {"build": "x", "status": "WITHHELD", "png": b"\x89PNG-unverified", "alt_text": "a"}
    markup, real = SF._img(fake, "Name")
    assert not real and "im-placeholder" in markup and 'data-image="placeholder"' in markup
    assert "im-x" not in SF._image_css([fake])
    # CAP-1 products (cap 5 -> 8 is configuration only) and any proposal stay off the
    # customer page unless every gate passes; none passes today (no owner grant, no
    # listing-set certificate in this harness).
    assert coll
    for p in coll:
        if p["launch_status"] == SF.CAP1_SCOPE:
            ok, why = SF.customer_gates_pass(p)
            assert not ok and why, (p["slug"], why)
            assert p["launch_status_note"] == SF.CAP1_NOTE
        if p["launch_status"] in (SF.CAP1_SCOPE, "PROPOSED"):
            assert f'data-product="{p["slug"]}"' not in cust
    # an incomplete hero (W4-IMAGES pieces finding) is never shown to customers
    inc = {"build": "y", "status": "VERIFIED", "png": b"x", "pieces_finding": "shows 1 of 6"}
    assert not SF._img(inc, "N")[1] and "im-y" not in SF._image_css([inc])


def test_categories_are_populated_only_and_disclosures_stay_customer_facing():
    from brambleloop.store_foundation import navigation

    cust = SF.customer_html(page())
    public, hidden = navigation.public_nav(None), navigation.hidden(None)
    assert public and hidden    # both exist today (e.g. Wearables / Gifts are hidden)
    for s in public:
        assert f'href="#c-{s["slug"]}"' in cust and f'id="c-{s["slug"]}"' in cust
    for s in hidden:
        assert f'#c-{s["slug"]}"' not in cust
    assert 'data-disclosure="shop"' in cust and cust.count('data-disclosure="listing"') == len(re.findall(r'<a class="card"', cust))
    assert "not a photograph" in cust and "AI" in V2.visible_text(cust)


def test_customer_page_rule_matches_image_review():
    """One rule for "may reach the customer page": the storefront's product set equals the
    image review's `customer_page_eligible` set (core Launch-0; CAP-1 only once every gate
    passes). `in_owner_store_preview` is a different fact (the owner preview grid, 8)."""
    from brambleloop.store_foundation import image_review as IR

    cands = IR.candidates()
    assert cands
    eligible = {c["slug"] for c in cands if c["customer_page_eligible"]}
    cards = set(re.findall(r'<a class="card"[^>]*data-product="([^"]+)"', SF.customer_html(page())))
    assert eligible and cards == eligible, (sorted(cards), sorted(eligible))


def test_copy_keys_and_placeholder_fallback():
    text, origin = SF.copy_text("tagline")
    assert origin in ("copy_lane", "copy_v2") and text
    assert SF.copy_text("no_such_key_xyz") == ("[copy: no_such_key_xyz]", "placeholder")
    assert SF.copy_text("no_such_key_xyz", "Fallback") == ("Fallback", "fallback")
    assert 'data-copy="tagline"' in page() and 'data-copy="announcement"' in page()


def test_etsy_controls_are_quoted_or_unknown():
    ctl = SF.etsy_controls()
    rows = [r for items in ctl["surfaces"].values() for r in items]
    assert len(rows) > 20
    keys = {r["key"]: r for r in rows}
    assert keys["shop_title_max_chars"]["value"] == 55
    assert keys["sections_max"]["value"] == 20 and keys["featured_listings"]["value"] == 4
    for r in rows:
        if r["basis"] == "UNKNOWN":
            assert r["value"] is None, r
    assert ctl["not_controlled"] and all(x["why"] for x in ctl["not_controlled"])


def test_owner_catalogue_is_the_8_product_collection():
    cat = owner_store.catalogue(None, wait=900)   # the full (pictures + quality) catalogue
    assert not cat.get("preparing")
    ps = cat["products"]
    from brambleloop.products import launch0 as l0

    assert len(ps) == 8 and cat["counts"]["collection"] == 8
    assert cat["counts"]["launch0"] == 5
    if l0.CATALOGUE_FLOOR_APPROVED:   # CAP-1: cap approved as configuration only
        assert cat["counts"]["proposed"] == 0 and cat["counts"]["cap1"] == 3
        assert cat["decision"]["key"] == "CAP-1" and cat["decision"]["cap_approved"] is True
        assert cat["decision"]["approved"] is False      # the products are not approved
        for p in ps:
            if p["launch_status"] == SF.CAP1_SCOPE:
                assert p["on_customer_page"] is False
                assert any("not approved" in b["what"] for b in p["readiness"]["blockers"])
    else:
        assert cat["counts"]["proposed"] == 3
    for p in ps:
        assert p["digital_label"] == SF.DIGITAL_LABEL
        assert p["listing"]["on_etsy"] == "UNKNOWN"
        img = p["image"]
        assert (img["path"] is not None) == (img["status"] == "VERIFIED"), (p["slug"], img)
        assert "png" not in img
        assert p["quality"]["status"] in ("OK", "BLOCKED", "UNKNOWN")
        assert set(p["pdf"]["paths"]) == {"US", "UK"}
    assert cat["etsy"]["status"] == "UNKNOWN"   # no database in this call: never "connected"


def test_a_cold_catalogue_never_blocks_and_never_claims_a_pass():
    class Fresh:   # a db stand-in nobody has warmed: forces the quick path
        def session(self):
            raise RuntimeError("no database")
    quick = owner_store.catalogue(Fresh(), wait=0)
    assert quick.get("preparing") is True and quick["etsy"]["status"] == "UNKNOWN"
    assert quick["products"] and len(quick["products"]) == 8
    for p in quick["products"]:
        assert p["image"]["status"] == "NOT_CHECKED" and p["image"]["path"] is None
        assert p["quality"]["status"] == "UNKNOWN"
    assert quick["counts"]["images_verified"] is None and quick["counts"]["quality_ok"] is None


def test_image_and_pdf_helpers_refuse_anything_outside_the_collection():
    assert owner_store.image_png("../../etc/passwd") is None
    assert owner_store.image_png("not_a_build") is None
    assert owner_store.pattern_pdf("not-a-product") is None
    assert owner_store.pattern_pdf("hexagon-coaster-set", "FR") is None
    data, name = owner_store.pattern_pdf("hexagon-coaster-set", "UK")
    assert data.startswith(b"%PDF") and name.endswith(".pdf")


def test_api_routes_need_an_owner_session_and_never_serve_unverified():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.app.command_center import auth
    from brambleloop.core import opsauth

    os.environ[opsauth.TOKEN_VAR] = "s" * 40
    pw = "owner passphrase for the storefront harness"
    os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(pw, iterations=100_000)
    os.environ.pop(auth.TOTP_VAR, None)
    main.db.create_all()
    owner_store.catalogue(main.db, wait=900)      # warm: the route then answers in full
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    for path in ("/api/cc/store/catalogue", "/api/cc/store/image/basket_medium",
                 "/api/cc/store/pdf/hexagon-coaster-set?terms=US"):
        r = anon.get(path)
        assert r.status_code == 401, (path, r.status_code)
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": pw})
    assert r.status_code == 200, r.text[:200]
    r = c.get("/api/cc/store/catalogue")
    assert r.status_code == 200 and len(r.json()["products"]) == 8
    assert r.json()["etsy"]["status"] in ("NOT_CONNECTED", "CONNECTED", "UNKNOWN")
    verified = [p for p in r.json()["products"] if p["image"]["status"] == "VERIFIED"]
    assert verified
    img = c.get(verified[0]["image"]["path"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content.startswith(b"\x89PNG") and img.headers["cache-control"] == "no-store"
    assert c.get("/api/cc/store/image/not_a_build").status_code == 404
    pdf = c.get("/api/cc/store/pdf/hexagon-coaster-set?terms=US")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and "inline" in pdf.headers["content-disposition"]
    assert c.get("/api/cc/store/pdf/hexagon-coaster-set?terms=XX").status_code == 404
    # The owner preview page opens on the customer storefront view by default.
    pv = c.get("/cc/store-preview?viewport=mobile")
    assert pv.status_code == 200 and 'data-variant="storefront"' in pv.text
    std = c.get("/cc/store-preview?viewport=mobile&variant=standard")
    assert std.status_code == 200 and 'data-variant="storefront"' not in std.text


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
