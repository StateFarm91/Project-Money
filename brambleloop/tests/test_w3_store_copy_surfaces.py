"""Wave 3 lane C: store copy v2 -- every surface present, truthful, within limits, not technical.

Owner directive 2026-10-06 sections 3, 6, 7, 14, 16: the shop leads with crochet patterns people
want to make; reliability is customer value; Laura is the AI founder and the face of the shop,
never claimed human; machinery is not the shop-window message. No network, no model.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_store_copy_surfaces.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.store_foundation import copy_v2 as V, lint  # noqa: E402

FAILS = 0


def check(name: str, fn) -> None:
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as exc:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


REQUIRED_EXPORT_KEYS = {
    "tagline", "tagline_candidates", "banner", "announcement", "seasonal_announcements",
    "seller_caption", "about_laura_intro", "about", "about_paragraphs", "policies",
    "digital_sale_message", "support_contact", "faq", "store_disclosure", "sections",
    "page_headings", "trust_headline", "trust_signals", "voice", "constraints",
    "lint_misfires", "above_the_fold_keys",
}


def _has_word(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text.lower()) is not None


def test_every_surface_is_exported_and_non_empty():
    out = V.export()
    assert REQUIRED_EXPORT_KEYS <= set(out), REQUIRED_EXPORT_KEYS - set(out)
    for k in REQUIRED_EXPORT_KEYS:
        assert out[k] not in ("", None, [], {}), k
    for k in ("delivery", "returns", "privacy", "privacy_addendum"):
        assert out["policies"][k].strip(), k
    import json
    json.dumps(out)    # serialisable for lane B and the Command Center


def test_every_customer_string_is_lint_clean_truth_and_voice():
    copy = V.customer_copy()
    assert len(copy) > 40
    for key, text in copy.items():
        assert text.strip(), key
        found = lint.lint(text, surface=key)       # truth AND voice
        assert not found, (key, [(f["code"], f["match"]) for f in found])


def test_chosen_tagline_is_lint_clean_and_owner_line_is_reported_not_forced():
    rows = V.tagline_candidates()
    assert len(rows) >= 3
    chosen = [r for r in rows if r["chosen"]]
    assert len(chosen) == 1 and chosen[0]["text"] == V.TAGLINE and not chosen[0]["problems"]
    assert lint.is_truthful(V.TAGLINE)
    owner = rows[0]
    assert owner["owner_concept"] and "handmade" in owner["text"].lower()
    if owner["problems"]:
        # The lint refuses the owner's line; it is reported to the integrator, never forced
        # through and never "fixed" by weakening the rule.
        assert not owner["chosen"]
        assert any(m["rule"] == "TRUTH_PHYSICAL_MAKING" for m in V.LINT_MISFIRES)
        assert not lint.is_truthful(owner["text"])
    assert V.BANNER["descriptor"] == "Crochet Patterns"
    assert V.BANNER["owner_line"] == "Patterns for a More Handmade Life"
    assert not lint.lint(V.BANNER["line"])


def test_lengths_within_recorded_constraints():
    c = V.CONSTRAINTS
    assert c
    assert len(V.TAGLINE) <= c["shop_title"].max_chars
    for t in [V.ANNOUNCEMENT, *V.SEASONAL_ANNOUNCEMENTS.values()]:
        assert len(t) <= c["announcement"].max_chars, (len(t), t)
        first = t.split(". ")[0].rstrip(".") + "."
        assert len(first) <= c["announcement_first_sentence"].max_chars, first
    assert 400 <= len(V.ABOUT) <= c["about"].max_chars
    assert V.SECTIONS
    for s in V.SECTIONS:
        assert len(s.name) <= c["section_name"].max_chars, s.name
    faq = V.faq()
    assert faq
    for f in faq:
        assert len(f["answer"]) <= c["faq_answer"].max_chars, f["key"]
    # The repository's own recorded limits agree.
    from brambleloop.store_foundation import limits

    for key, text in (("announcement", V.ANNOUNCEMENT), ("about", V.ABOUT)):
        assert not [f for f in limits.check_length(key, text)
                    if f["code"] == "LIMIT_EXCEEDED"], key
    for c_ in c.values():
        assert c_.basis in (V.SECONDARY, V.REPO_ASSERTED, V.VERIFIED_ETSY) and c_.source
    # Lane I's verified Etsy limits are used when present (Etsy help articles, 2026-10-06).
    try:
        from brambleloop.integrations import etsy_constraints as ec
    except ImportError:
        ec = None
    if ec is not None:
        for key, ekey in (("shop_title", "shop_title_max_chars"), ("about", "about_max_chars"),
                          ("section_name", "section_name_max_chars")):
            assert c[key].basis == V.VERIFIED_ETSY, key
            assert c[key].max_chars == ec.value(ekey), key
            assert not ec.text_problems(key, {"shop_title": V.TAGLINE, "about": V.ABOUT,
                                              "section_name": V.SECTIONS[0].name}[key]), key
        for s in V.SECTIONS:
            assert not ec.text_problems("section_name", s.name), s.name
        assert len(V.SECTIONS) <= ec.value("sections_max")


def test_banned_technical_terms_absent_above_the_fold():
    atf = V.ABOVE_THE_FOLD
    assert "tagline" in atf and "announcement" in atf and "about_opening" in atf
    for key, text in atf.items():
        for term in V.BANNED_TECHNICAL_TERMS:
            assert not _has_word(text, term), (key, term)
        assert not _has_word(text, "ai"), (key, "AI is disclosed below the fold, not sold")


def test_implementation_vocabulary_absent_from_all_customer_copy():
    copy = V.customer_copy()
    assert copy
    for key, text in copy.items():
        for term in V.BANNED_EVERYWHERE:
            assert not _has_word(text, term), (key, term)
    for phrase in ("machine-readable", "machine checked", "formal description", "compiler"):
        assert phrase not in V.ABOUT.lower(), phrase


def test_about_leads_with_patterns_then_laura_then_process():
    p = V.ABOUT_PARAGRAPHS
    assert len(p) >= 5
    assert "crochet patterns" in p[0].lower() and "laura" not in p[0].lower()
    assert "Laura" in p[1] and "AI" in p[1]
    first_process = next(i for i, x in enumerate(p) if "checking" in x or "verified" in x)
    assert first_process >= 2
    from brambleloop.commerce import shop_package

    assert shop_package.check_about(V.ABOUT) == []
    assert "\n" not in "".join(p)      # paste-ready: one line per paragraph


def test_no_laura_human_claims_anywhere():
    copy = V.customer_copy()
    laura = {k: v for k, v in copy.items() if "laura" in v.lower()}
    assert len(laura) >= 4, sorted(laura)
    for key, text in laura.items():
        codes = {f["code"] for f in lint.lint(text, voice=False)}
        assert "TRUTH_LAURA_HUMAN_CLAIM" not in codes, (key, text)
        assert "TRUTH_FOUNDER_STORY" not in codes, (key, text)
    # Every Laura introduction discloses she is an AI.
    for text in (V.SELLER_CAPTION, V.ABOUT_LAURA_INTRO, V.LAURA_FAQ["answer"],
                 V.ABOUT_PARAGRAPHS[1], V.store_disclosure()):
        assert "AI" in text, text
    # Never the legal owner or seller of record; the human account holder is named as such.
    for text in laura.values():
        assert not re.search(r"laura[^.]{0,40}\b(legal owner|seller of record|owns)\b",
                             text, re.I), text
    assert "human account holder" in V.store_disclosure()
    assert "human" in V.ABOUT_PARAGRAPHS[-1]


def test_laura_is_brand_face_not_account_holder():
    p = V.LAURA_PLACEMENT
    assert p
    assert p["account_profile_photo"].startswith("no")
    assert p["shop_team_owner_role"].startswith("no")
    for k in ("banner", "about_story", "seasonal"):
        assert p[k].startswith("yes"), k


def test_the_lint_still_refuses_human_laura_copy():
    bad = ["Laura hand-crochets every sample.", "Designed by Laura.", "Laura is the founder.",
           "Laura is a real woman.", "Owned by Laura."]
    assert bad
    for t in bad:
        assert "TRUTH_LAURA_HUMAN_CLAIM" in {f["code"] for f in lint.lint(t, voice=False)}, t


def test_renders_and_no_sample_are_said_where_it_matters():
    from brambleloop.visual import render_contract

    disc = " ".join(V.store_disclosure().lower().split())
    assert render_contract.DISCLOSURE.lower() in disc
    keys = {f["key"]: f["answer"] for f in V.faq()}
    assert "not a photograph" in keys["are_images_photos"]
    assert "not yet worked a physical sample" in keys["sample_made"]
    assert "not photographs" in V.ABOUT


def test_policies_carry_the_required_customer_language():
    assert "cannot be returned" in V.RETURNS.lower() and "does not allow" in V.RETURNS
    assert "correct the pattern" in V.RETURNS
    assert "digital" in V.DELIVERY and "no processing time" in V.DELIVERY
    assert "nothing is posted" in V.DELIVERY and "will not open" in V.DELIVERY
    priv = (V.PRIVACY + V.PRIVACY_ADDENDUM).lower()
    for w in ("casl", "pipeda", "unsubscribe", "do not sell", "expressly agreed"):
        assert w in priv, w
    assert "etsy messages" in V.SUPPORT_CONTACT.lower()


def test_sale_message_quotes_the_decided_licence():
    from brambleloop.commerce import terms as T

    sell = T.BRAMBLELOOP_TERMS.sentence(T.FINISHED_ITEM_SALE)
    assert sell in V.DIGITAL_SALE_MESSAGE
    assert "you may sell the items you make from this pattern" not in V.DIGITAL_SALE_MESSAGE


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)

if FAILS:
    sys.exit(1)
