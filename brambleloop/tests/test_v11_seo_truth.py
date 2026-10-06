"""Lane G: the truthful-tag validator (F-918 anti-gaming, F-008, F-021, PT-01, F-929).

A tag must be traceable to a verified fact of the product; stuffed, competitor-branded,
protected-IP, misleading or untraceable terms are rejected, and the rejection names why.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, launch0_facts, run  # noqa: E402

from brambleloop.seo import truth


def _basket():
    f = [x for x in launch0_facts() if x.slug == "market-basket-small"]
    assert f, "Launch-0 must still contain market-basket-small"
    return f[0]


def _codes(verdict):
    return {f.split(":")[0] for f in verdict.findings}


def test_truthful_terms_pass_with_a_trace_to_their_facts():
    f = _basket()
    v = truth.check_term("crochet basket", f)
    assert v.ok, v.findings
    sources = {t["word"]: t["source"] for t in v.trace}
    assert sources["basket"] and sources["basket"].startswith("identity:"), sources
    assert truth.check_term("cotton basket", f).ok          # cir.materials
    assert truth.check_term("cream basket", f).ok           # cir.colors


def test_untraceable_terms_are_rejected():
    f = _basket()
    for term in ("blanket pattern", "knitting pattern", "mosaic basket"):
        v = truth.check_term(term, f)
        assert not v.ok and "TERM_UNTRACEABLE" in _codes(v), (term, v.findings)


def test_untrue_difficulty_and_finished_item_claims_are_misleading():
    f = _basket()
    assert f.difficulty != "beginner", f.difficulty   # premise: 'easy' is untrue here
    for term in ("easy basket pattern", "gift for her", "ready to ship basket"):
        v = truth.check_term(term, f)
        assert not v.ok and "TERM_MISLEADING" in _codes(v), (term, v.findings)
    v = truth.check_term("best basket pattern", f)
    assert "TERM_MISLEADING" in _codes(v), v.findings


def test_competitor_shop_names_are_rejected_in_any_spelling():
    f = _basket()
    for term in ("hanjan crochet", "HanJanCrochet basket", "ivy loop basket"):
        v = truth.check_term(term, f)
        assert "TERM_COMPETITOR_BRAND" in _codes(v), (term, v.findings)
    v = truth.check_term("red heart basket", f)
    assert "TERM_COMPETITOR_BRAND" in _codes(v), v.findings


def test_competitor_names_from_the_database_are_rejected():
    from brambleloop.core.models import CompetitorSnapshot

    db = fresh_db()
    with db.session() as s:
        s.add(CompetitorSnapshot(shop="WillowHookStudio", observed_on="2026-10-01"))
    names = truth.competitor_names(db)
    assert "WillowHookStudio" in names, names
    v = truth.check_term("willow hook studio", _basket(), competitors=names)
    assert "TERM_COMPETITOR_BRAND" in _codes(v), v.findings


def test_protected_ip_is_rejected():
    v = truth.check_term("disney basket", _basket())
    assert "TERM_PROTECTED_IP" in _codes(v), v.findings


def test_stuffed_listing_is_rejected():
    f = _basket()
    tags = ["basket crochet", "basket pattern", "crochet basket", "nursery basket",
            "basket diy"]
    out = truth.validate_listing("Basket Basket Basket | Crochet Pattern", tags, f)
    assert not out["ok"]
    assert any(b.startswith("LISTING_STUFFED") for b in out["blocking"]), out["blocking"]
    dup = truth.validate_listing("Hexagonal Basket | Crochet Pattern PDF",
                                 ["crochet basket", "crochet basket"], f)
    assert any(b.startswith("TAG_DUPLICATE") for b in dup["blocking"]), dup["blocking"]


def test_etsy_limits_are_enforced_by_the_validator():
    from brambleloop.commerce import seo as seo_mod

    f = _basket()
    long_tag = "nursery cotton crochet basket"            # 29 characters
    assert len(long_tag) > seo_mod.TAG_MAX_CHARS
    out = truth.validate_listing("Hexagonal Basket | Crochet Pattern PDF", [long_tag], f)
    assert any(b.startswith("LIMIT_TAG_CHARS") for b in out["blocking"]), out["blocking"]
    too_many = [f"crochet basket {i}" for i in range(14)]
    out = truth.validate_listing("Hexagonal Basket | Crochet Pattern PDF", too_many, f)
    assert any(b.startswith("LIMIT_TAG_COUNT") for b in out["blocking"]), out["blocking"]
    out = truth.validate_listing("Crochet Basket Pattern " * 8, ["crochet basket"], f)
    assert any(b.startswith("LIMIT_TITLE_CHARS") for b in out["blocking"]), out["blocking"]


def test_a_product_type_the_cir_does_not_make_is_rejected_at_listing_level():
    f = _basket()
    out = truth.validate_listing("Hexagonal Basket | Crochet Pattern PDF",
                                 ["crochet blanket"], f)
    assert not out["ok"]
    assert any("blanket" in b for b in out["blocking"]), out["blocking"]


if __name__ == "__main__":
    run(globals())
