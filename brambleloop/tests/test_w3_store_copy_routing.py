"""Wave 3 lane C: every existing store surface reads its words from store copy v2.

`store_foundation.content.build`, `commerce.shop_package` and `brand.storefront`'s tagline all
render from `store_foundation.copy_v2`, so the Owner Store Preview, the readiness roll-up and
the paste-ready package cannot drift from the copy lane B renders. No network, no model.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_store_copy_routing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import content, copy_v2 as V, lint, readiness  # noqa: E402

FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


COPY_SURFACES = ("shop_title", "announcement", "about", "policy_delivery", "policy_returns",
                 "policy_privacy", "disclosures", "faq", "support_contact",
                 "digital_sale_message", "sections", "trust_signals")


def test_content_surfaces_render_from_copy_v2():
    s = content.build()
    assert s["shop_title"].value == V.TAGLINE
    assert s["announcement"].value == V.ANNOUNCEMENT
    assert s["about"].value == V.ABOUT
    assert s["policy_delivery"].value == V.DELIVERY
    assert s["policy_returns"].value == V.RETURNS
    assert s["policy_privacy"].value.startswith(V.PRIVACY)
    assert s["policy_privacy"].value.endswith(V.PRIVACY_ADDENDUM)
    assert s["disclosures"].value == V.store_disclosure()
    assert s["support_contact"].value == V.SUPPORT_CONTACT
    assert s["digital_sale_message"].value == V.DIGITAL_SALE_MESSAGE
    trust = [t["text"] for t in s["trust_signals"].value]
    assert trust == [t.text for t in V.TRUST_SIGNALS]
    keys = [f["key"] for f in s["faq"].value]
    assert keys[0] == "sell_what_i_make" and "who_is_laura" in keys
    for surface in COPY_SURFACES:
        assert "copy_v2" in s[surface].source, (surface, s[surface].source)


def test_sections_follow_owner_nav_and_never_show_empty_shelves():
    s = content.build()
    rows = s["sections"].value
    assert rows
    names = [r["name"] for r in rows]
    assert names[:5] == ["Home", "Baby", "Wearables", "Gifts", "Seasonal"], names
    shown = [r for r in rows if r["shown"]]
    # W4-PIPE 18baa94: the snowflake ornaments (Seasonal) and the snowfall throw (Blankets)
    # joined Launch-0; Wearables and Gifts stay empty and hidden.
    assert {r["slug"] for r in shown} == {"home", "baby", "seasonal", "blankets"}, shown
    for r in rows:
        assert r["shown"] == (r["listings"] > 0)
        assert r["status"] == ("live" if r["listings"] else "planned")
    live = {r["slug"] for r in shown}
    planned = [x for x in V.SECTIONS if x.slug not in live]
    assert {x.slug for x in planned} == {"wear", "collections"}
    for x in planned:
        assert x.planned_note.startswith("planned"), x.slug
    # a live section never claims to be planned (the copy cannot outlive the catalogue)
    for x in V.SECTIONS:
        if x.slug in live:
            assert "planned" not in x.planned_note, x.slug


def test_shop_package_renders_from_copy_v2_and_keeps_its_checks():
    from brambleloop.commerce import shop_package as P
    from brambleloop.commerce import terms as T

    text = P.shop_text()
    assert text["title"] == V.TAGLINE
    assert text["digital_sale_message"] == V.DIGITAL_SALE_MESSAGE
    assert P.DELIVERY == V.DELIVERY and P.RETURNS == V.RETURNS and P.PRIVACY == V.PRIVACY
    assert P.check_package() == []
    faq = P.faq()
    assert [f["key"] for f in faq] == list(V.FAQ_ORDER)
    assert {f["key"]: f["answer"] for f in faq}["was_ai_used"] == P.ai_disclosure()
    verdict = P.surface_consistency(pdf_text=T.render(T.BRAMBLELOOP_TERMS, "pdf"),
                                    listing_text=P.policies()["licence"],
                                    faq_text=P.faq_text())
    assert verdict["consistent"], verdict["divergences"]


def test_licence_lives_in_faq_not_the_eu_only_field():
    from brambleloop.commerce import shop_package as P
    from brambleloop.commerce import terms as T

    assert P.shop_text()["policy_additional"] == ""
    assert "policy_additional" not in P.api_shop_fields()
    assert T.AXES
    faq_doc = P.faq_text()
    for axis in T.AXES:
        assert T.BRAMBLELOOP_TERMS.sentence(axis) in faq_doc, axis
    s = content.build()
    assert "policy_additional" not in {r["key"] for r in s["settings_checklist"].value}
    assert "licence_in_faq" in {r["key"] for r in s["settings_checklist"].value}
    assert "EU-only" in s["policy_licence"].etsy_location
    assert "FAQ" in V.ABOUT_PARAGRAPHS[-1]


def test_storefront_tagline_and_seo_check_pass():
    from brambleloop.brand import storefront

    store = storefront.build_storefront()
    assert store.tagline == V.TAGLINE
    store.about = V.ABOUT
    store.announcement = V.ANNOUNCEMENT
    problems = storefront.check_shop_seo(store)
    assert not problems, problems


def test_readiness_never_fails_a_copy_surface():
    rows = {r["key"]: r for r in readiness.evaluate(content.build())}
    assert rows
    for key in COPY_SURFACES:
        assert rows[key]["status"] != readiness.FAIL, (key, rows[key]["findings"])
    for key in COPY_SURFACES:
        truth = [f for f in rows[key]["findings"] if f.get("kind") == lint.TRUTH]
        assert not truth, (key, truth)


def test_settings_checklist_carries_creativity_classification():
    rows = {r["key"]: r for r in content.settings_checklist()}
    assert "creativity_classification" in rows
    r = rows["creativity_classification"]
    assert r["status"] == "OWNER_LOGIN_REQUIRED" and r["entered_on_etsy"] == "UNKNOWN"
    assert "Designed by" in r["what"] and "secondary" in r["what"]


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
