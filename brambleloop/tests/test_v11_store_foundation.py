"""v1.1 lane F: the store foundation content model, readiness checks and truthfulness lint.

Directive v1.1 section 10 and F-233..F-241 / F-515: every store-level surface exists, each has
a deterministic readiness verdict, fabricated history / social proof / superlatives are caught,
limits are labelled by how well they are known, and nothing is claimed READY that was not
checked. No network, no model.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_store_foundation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import assets, content, limits, lint, readiness  # noqa: E402

EXPECTED_SURFACES = {
    "shop_name", "icon", "banner", "shop_title", "announcement", "about", "policy_delivery",
    "policy_returns", "policy_licence", "policy_privacy", "disclosures", "faq",
    "support_contact", "digital_sale_message", "sections", "opening_grid", "trust_signals",
    "voice", "settings_checklist", "search_readiness", "support_readiness",
    # D-FB-11: Laura, the brand face, is a Store Foundation surface (GATED, never READY).
    "brand_face",
}

FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def _rows(surfaces=None):
    surfaces = surfaces or content.build()
    return {r["key"]: r for r in readiness.evaluate(surfaces)}, surfaces


def test_every_surface_present():
    s = content.build()
    assert set(s) == EXPECTED_SURFACES, set(s) ^ EXPECTED_SURFACES
    for surface in s.values():
        assert surface.source and surface.etsy_location and surface.entry, surface.key
        d = surface.to_dict()
        assert d["entered_on_etsy"] == "UNKNOWN"   # never claimed entered


def test_every_surface_has_a_verdict():
    rows, _ = _rows()
    assert rows
    for r in rows.values():
        assert r["status"] in readiness.ORDER, r
    assert set(rows) == EXPECTED_SURFACES


def test_current_content_has_no_failures_and_is_not_claimed_ok():
    rows, _ = _rows()
    fails = {k: [f["code"] for f in r["findings"] if f["severity"] == "fail"]
             for k, r in rows.items() if r["status"] == readiness.FAIL}
    assert not fails, fails
    roll = readiness.rollup(list(rows.values()))
    # Owner decisions and unverified Etsy limits remain, so the honest roll-up is DEGRADED.
    assert roll["status"] == "DEGRADED", roll["status"]
    assert roll["owner_actions"]


def test_truth_lint_catches_fabrication():
    cases = {
        "Since 2014 we have designed patterns": "TRUTH_YEARS_IN_BUSINESS",
        "Over 10 years of experience": "TRUTH_YEARS_IN_BUSINESS",
        "The best crochet patterns on Etsy": "TRUTH_SUPERLATIVE",
        "Our bestselling blanket": "TRUTH_SUPERLATIVE",
        "Loved by thousands of makers": "TRUTH_SOCIAL_PROOF",
        "Join 5,000+ happy customers": "TRUTH_SOCIAL_PROOF",
        "Rated 5 stars by our buyers": "TRUTH_SOCIAL_PROOF",
        "As seen in Crochet Monthly": "TRUTH_SOCIAL_PROOF",
        "My grandmother taught me to crochet": "TRUTH_FOUNDER_STORY",
        "Every pattern is tested by our testers": "TRUTH_PHYSICAL_MAKING",
        "Photographed in our studio": "TRUTH_PHYSICAL_MAKING",
        "Only 2 left - sale ends tonight": "TRUTH_SCARCITY",
        "A child-safe toy": "TRUTH_SAFETY_CERT",
    }
    assert cases
    for text, code in cases.items():
        codes = {f["code"] for f in lint.lint(text)}
        assert code in codes, (text, codes)
        assert not lint.is_truthful(text), text


def test_truth_lint_respects_true_negatives():
    for text in ("No sample has been photographed.",
                 "each listing image is a digital rendering, not a photograph",
                 "We have not yet worked a physical sample of these designs.",
                 "A premium crochet pattern, checked row by row."):
        assert lint.is_truthful(text), (text, lint.lint(text))


def test_all_customer_copy_is_truthful():
    s = content.build()
    facing = [x for x in s.values() if x.customer_facing]
    assert facing
    for surface in facing:
        found = [f for f in lint.lint(surface.text(), surface=surface.key)
                 if f["kind"] == lint.TRUTH]
        assert not found, found


def test_fabricated_about_fails_and_blocks():
    s = content.build()
    s["about"].value += "\n\nFounded in 2012, we are the best pattern shop, loved by 10,000 makers."
    rows, _ = _rows(s)
    assert rows["about"]["status"] == readiness.FAIL
    codes = {f["code"] for f in rows["about"]["findings"]}
    assert {"TRUTH_YEARS_IN_BUSINESS", "TRUTH_SUPERLATIVE", "TRUTH_SOCIAL_PROOF"} <= codes
    assert readiness.rollup(list(rows.values()))["status"] == "BLOCKED"


def test_limits_are_labelled_never_invented():
    assert limits.LIMITS
    for lim in limits.LIMITS.values():
        assert lim.basis in limits.BASES
        assert (lim.max_chars is None) == (lim.basis == limits.UNKNOWN), lim
    assert limits.LIMITS["shop_title"].basis == limits.UNKNOWN
    assert limits.LIMITS["listing_title"].max_chars == 140
    try:
        limits.FieldLimit("x", "x", 55, limits.UNKNOWN, "guess")
        raise AssertionError("an UNKNOWN limit accepted a number")
    except ValueError:
        pass
    assert limits.check_length("listing_title", "x" * 141)[0]["severity"] == "fail"
    assert limits.check_length("announcement", "x" * 500)[0]["severity"] == "unverified"
    unknown = limits.check_length("shop_title", "x")
    assert unknown and unknown[0]["code"] == "LIMIT_UNVERIFIED"


def test_opening_grid_counts_products_not_sizes():
    from brambleloop.launch import readiness as lr

    rows, s = _rows()
    products = s["opening_grid"].value
    # W4-PIPE 2026-10-07: the snowflake ornaments and the snowfall throw joined Launch-0.
    assert [p["candidate"] for p in products] == [
        "nursery-nesting-baskets", "cloudline-baby-blanket", "hexagon-coaster-set",
        "nordic-star-ornaments", "winter-village-graphghan"]
    assert [p["price_cad"] for p in products] == [6.50, 7.50, 4.00, 4.50, 7.50]
    assert products[0]["variant_count"] == 3
    assert lr.MIN_LISTINGS_TO_OPEN == 8           # not lowered by this lane
    depth = [f for f in rows["opening_grid"]["findings"] if f["code"] == "CATALOGUE_DEPTH"]
    assert depth and "5 Launch-0 products" in depth[0]["detail"]
    assert depth[0]["severity"] == "owner"


def test_basket_naming_is_an_owner_decision():
    rows, _ = _rows()
    codes = [(f["code"], f["severity"]) for f in rows["opening_grid"]["findings"]]
    assert ("TITLE_PLAN_MISMATCH", "owner") in codes, codes


def test_long_listing_title_fails():
    s = content.build()
    s["opening_grid"].value[0]["title"] = "Basket " * 30
    rows, _ = _rows(s)
    assert rows["opening_grid"]["status"] == readiness.FAIL


def test_assets_deterministic_on_palette():
    assert assets.icon_svg() == assets.icon_svg()
    assert assets.banner_svg() == assets.banner_svg()
    from brambleloop.brand import bible

    # brand palette = the bible plus lane A's identity_system.PALETTE (wave 3)
    palette = {v.upper() for v in bible.PALETTE.values()} | assets.palette_hexes()
    assert assets.colours_used(assets.icon_svg()) <= palette
    assert assets.colours_used(assets.banner_svg()) <= palette
    assert "<text" not in assets.icon_svg()
    assert "BRAMBLELOOP" in assets.banner_svg()
    for svg_check in (assets.check_icon(), assets.check_banner()):
        assert not [f for f in svg_check if f["severity"] == "fail"], svg_check
    bad = assets.check_icon(assets.icon_svg().replace("#2F3E33", "#FF00FF"))
    assert any(f["code"] == "ASSET_OFF_PALETTE" for f in bad)
    assert any(f["code"] == "ICON_HAS_TEXT" for f in assets.check_icon(
        assets.icon_svg().replace("</svg>", "<text>B</text></svg>")))
    crops = assets.describe()["banner"]["crops"]
    assert crops["phone"]["inside_safe_area"] and crops["desktop"]["inside_safe_area"]


def test_trust_signals_need_evidence():
    s = content.build()
    assert s["trust_signals"].value
    for t in s["trust_signals"].value:
        assert t["kind"] in content.TRUST_KINDS
    s["trust_signals"].value.append({"key": "fake", "text": "Trusted quality",
                                     "kind": "verified_process",
                                     "evidence": ["src/brambleloop/nope.py"]})
    rows, _ = _rows(s)
    assert rows["trust_signals"]["status"] == readiness.FAIL


def test_disclosures_carry_render_phrase_and_ai():
    rows, s = _rows()
    assert rows["disclosures"]["status"] != readiness.FAIL
    s["disclosures"].value = "This is a digital pattern. AI was used."
    rows, _ = _rows(s)
    assert any(f["code"] == "DISCLOSURE_NO_RENDER_PHRASE" for f in
               rows["disclosures"]["findings"])


def test_privacy_casl_pipeda_and_legal_review():
    rows, s = _rows()
    text = s["policy_privacy"].value
    assert "CASL" in text and "PIPEDA" in text and "unsubscribe" in text
    assert any(f["code"] == "LEGAL_REVIEW_PENDING" for f in rows["policy_privacy"]["findings"])


def test_returns_must_say_non_returnable():
    s = content.build()
    s["policy_returns"].value = "Contact us for a refund."
    rows, _ = _rows(s)
    assert rows["policy_returns"]["status"] == readiness.FAIL


def test_about_is_paste_ready():
    from brambleloop.brand import storefront
    from brambleloop.commerce import shop_package

    paras = storefront.ABOUT.split("\n\n")
    assert len(paras) >= 4
    for p in paras:
        assert "\n" not in p, p[:60]
    assert not shop_package.check_about(storefront.ABOUT)


def test_faq_covers_first_purchase_questions():
    rows, s = _rows()
    keys = [f["key"] for f in s["faq"].value]
    assert keys[0] == "sell_what_i_make"
    for k in ("skill_level", "are_images_photos", "sample_made", "contact"):
        assert k in keys
    assert rows["faq"]["status"] != readiness.FAIL


def test_drafted_listing_row_is_preferred():
    from brambleloop.core.db import Database
    from brambleloop.core.models import Listing

    db = Database("sqlite://", scratch=True)
    db.create_all()
    with db.session() as sess:
        sess.add(Listing(product_slug="hexagon-coaster-set", version="1.0.0",
                         title="Hexagon Coaster Set | Crochet Pattern PDF", description="d",
                         tags=[], price_cad=4.0))
    products = content.launch0_products(db)
    coaster = [p for p in products if p["candidate"] == "hexagon-coaster-set"]
    assert coaster and coaster[0]["title_basis"].startswith("drafted_listing")
    assert coaster[0]["title"] == "Hexagon Coaster Set | Crochet Pattern PDF"


def test_settings_checklist_is_owner_login_and_unknown():
    s = content.build()
    rows = s["settings_checklist"].value
    assert rows
    for r in rows:
        assert r["status"] == "OWNER_LOGIN_REQUIRED" and r["entered_on_etsy"] == "UNKNOWN"
        assert r["max_cost_cad"] == 0.0 and r["minutes_basis"] == "ESTIMATED"


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
