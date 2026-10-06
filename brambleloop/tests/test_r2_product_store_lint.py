"""R2 / J-product P-3 + P-4: the store truthfulness lint is robust, and every customer-facing
string a surface holds reaches it.

P-3: every phrase the audit executed as MISSED (j_product_lint.py) is now a regression case:
ratings/stars, sales counts in digits and words, years/decades in words, "handmade" (the shop
sells digital designs), scarcity, safety claims needing evidence, and Unicode disguises
(fullwidth, zero-width, homoglyph, letter-spaced). The negation window no longer crosses a
clause, so "Not a toy, we crocheted this" is the claim it makes.
P-4: Surface.text() recurses and includes `title`, so opening_grid tile titles, nested lists
and unknown keys (`body`) are linted (j_product_surface_text.py).

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_store_lint.py
"""
from __future__ import annotations

from _r2_harness import run

from brambleloop.store_foundation import content as C, lint, readiness as R

# Every MISSED phrase from the audit, with the rule that must now catch it.
MISSED_ON_DDF9C6E = {
    "Rated 4.9 stars": "TRUTH_SOCIAL_PROOF",
    "Over 500 patterns sold": "TRUTH_SOCIAL_PROOF",
    "Customers love it": "TRUTH_SOCIAL_PROOF",
    "A trusted name in crochet": "TRUTH_SOCIAL_PROOF",
    "Established in the 2010s": "TRUTH_YEARS_IN_BUSINESS",
    "Fifteen years in business": "TRUTH_YEARS_IN_BUSINESS",
    "Over twenty years of crochet": "TRUTH_YEARS_IN_BUSINESS",
    "Handmade with love": "TRUTH_PHYSICAL_MAKING",
    "Hand-crocheted sample shown": "TRUTH_PHYSICAL_MAKING",
    "We have tested every row": "TRUTH_PHYSICAL_MAKING",
    "Only a few left": "TRUTH_SCARCITY",
    "Last chance": "TRUTH_SCARCITY",
    "Save 20 percent": "TRUTH_SCARCITY",
    "Half price this week": "TRUTH_SCARCITY",
    "Top quality": "TRUTH_SUPERLATIVE",
    "Most-loved pattern": "TRUTH_SUPERLATIVE",
    "Etsy's choice": "TRUTH_SUPERLATIVE",
    "Safe for babies": "TRUTH_SAFETY_CERT",
    "Oeko-Tex certified": "TRUTH_SAFETY_CERT",
    "The b e s t pattern": "TRUTH_SUPERLATIVE",
    "b​est pattern": "TRUTH_SUPERLATIVE",
    "Ƅest crochet patterns": "TRUTH_SUPERLATIVE",
    # the rest of the probe list, also caught now
    "Since 2014 we have made patterns": "TRUTH_YEARS_IN_BUSINESS",
    "Serving makers since the early days": "TRUTH_YEARS_IN_BUSINESS",
    "Est. two thousand fifteen": "TRUTH_YEARS_IN_BUSINESS",
    "Two decades": "TRUTH_YEARS_IN_BUSINESS",
    "Over five hundred sold": "TRUTH_SOCIAL_PROOF",
    "Shop reviews are glowing": "TRUTH_SOCIAL_PROOF",
    "Five stars from buyers": "TRUTH_SOCIAL_PROOF",
    "★★★★★": "TRUTH_SOCIAL_PROOF",
    "hand made in Canada": "TRUTH_PHYSICAL_MAKING",
    "Pattern tested by crocheters": "TRUTH_PHYSICAL_MAKING",
    "Limited edition colourway": "TRUTH_SCARCITY",
    "Non-toxic and lab-tested": "TRUTH_SAFETY_CERT",
    "Hypoallergenic": "TRUTH_SAFETY_CERT",
    "Everyone's favourite": "TRUTH_SUPERLATIVE",
    "A beloved pattern": "TRUTH_SUPERLATIVE",
    "ＢＥＳＴ pattern": "TRUTH_SUPERLATIVE",          # fullwidth BEST
    "Тhe best": "TRUTH_SUPERLATIVE",                            # Cyrillic T
}

NEGATION_EVASIONS = {
    "Not a toy, we crocheted this basket ourselves": "TRUTH_PHYSICAL_MAKING",
    "No fuss, no waiting: we crocheted and photographed every sample":
        "TRUTH_PHYSICAL_MAKING",
    "Never boring, always lab-tested": "TRUTH_SAFETY_CERT",
    "We never skip it and these are baby safe": "TRUTH_SAFETY_CERT",
}

TRUE_NEGATIVES = (
    "No sample has been photographed.",
    "No sample was ever photographed",
    "each listing image is a digital rendering, not a photograph",
    "We have not yet worked a physical sample of these designs.",
    "A premium crochet pattern, checked row by row.",
    "Not intended for children under 3 years.",
    "Suitable from 3 years and up.",
    "This pattern is not safety-certified, and the finished item is not lab-tested.",
    "A limited personal licence: you may sell what you make.",
)


def _codes(text):
    return {f["code"] for f in lint.lint(text, voice=False) if f["kind"] == lint.TRUTH}


def test_every_phrase_the_audit_missed_is_caught_by_its_rule():
    assert MISSED_ON_DDF9C6E
    for text, code in MISSED_ON_DDF9C6E.items():
        codes = _codes(text)
        assert code in codes, (text, codes)
        assert not lint.is_truthful(text), text


def test_a_negator_in_another_clause_does_not_excuse_the_claim():
    assert NEGATION_EVASIONS
    for text, code in NEGATION_EVASIONS.items():
        assert code in _codes(text), (text, _codes(text))


def test_true_negative_disclosures_still_pass():
    assert TRUE_NEGATIVES
    for text in TRUE_NEGATIVES:
        assert lint.is_truthful(text), (text, lint.lint(text, voice=False))


def test_disguised_text_is_flagged_as_obfuscated():
    for text in ("b​est pattern", "Тhe best", "ＢＥＳＴ"):
        assert "TRUTH_OBFUSCATED_TEXT" in _codes(text), text


def test_current_shop_copy_is_still_truthful():
    s = C.build(None)
    facing = [x for x in s.values() if x.customer_facing]
    assert facing
    for surface in facing:
        found = [f for f in lint.lint(surface.text(), surface=surface.key)
                 if f["kind"] == lint.TRUTH]
        assert not found, (surface.key, found)


def _surface(key, value):
    return C.Surface(key=key, label=key, group="shop", value=value, source="probe",
                     etsy_location="x", entry="x")


def test_surface_text_reaches_titles_nested_values_and_unknown_keys():
    grid = _surface("opening_grid", [{
        "title": "Best-selling Crochet Basket, Trusted by 5,000 Makers, Since 2014",
        "plan_title": "x", "candidate": "c", "qualifiers": [], "price_cad": 6.5,
        "variant_count": 1, "representative": {"build": "b"}}])
    assert "Best-selling" in grid.text()
    assert _codes(grid.text()), grid.text()
    nested = _surface("about", {"story": ["Since 2014, thousands of makers trust us"]})
    assert "Since 2014" in nested.text() and _codes(nested.text())
    body = _surface("faq", [{"question": "q", "body": "Trusted by thousands of makers"}])
    assert "Trusted" in body.text() and _codes(body.text())
    deep = _surface("about", {"a": {"b": [{"c": "Rated 4.9 stars"}]}})
    assert "Rated" in deep.text()


def test_readiness_fails_a_grid_tile_title_that_lies():
    s = C.build(None)
    grid = s["opening_grid"]
    rows = [dict(r) for r in grid.value]
    assert rows
    rows[0]["title"] = "Best-selling Basket | Since 2014"
    s["opening_grid"] = _surface("opening_grid", rows)
    found = [f for r in R.evaluate(s) for f in r["findings"]
             if str(f.get("code", "")).startswith("TRUTH_")]
    assert found, "a lying tile title passed store readiness"


run(globals())
