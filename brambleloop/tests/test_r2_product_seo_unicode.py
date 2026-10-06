"""R2 / J-product P-1: seo.truth and publish.listing_schema read the term a buyer reads.

Fullwidth (`ｄｉｓｎｅｙ`, `ＢＥＳＴ ＳＥＬＬＥＲ`), zero-width and non-Latin (`最佳`) spellings used to
pass `seo.truth.validate_listing` and `listing_schema.tag_problems/title_problems` because
every word check folded to `[a-z0-9]+` and found nothing to check. Repro:
research/final_build/audit_ddf9c6e/j_product_seotruth.py, j_product_schema.py.

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_seo_unicode.py
"""
from __future__ import annotations

from _r2_harness import run

from brambleloop.publish import listing_schema as LS
from brambleloop.seo import facts as F, truth as T

FACTS = F.launch0_facts()[0]
BASE = ["crochet basket", "storage basket", "nursery decor", "hexagon pattern", "pdf pattern",
        "crochet pdf", "beginner basket", "basket pdf", "hexagonal", "written chart",
        "us uk terms"]
TITLE = "Hexagonal Storage Basket | Crochet Pattern PDF"
EVASIVE = ["ｒａｖｅｌｒｙ", "ＢＥＳＴ ＳＥＬＬＥＲ", "ｄｉｓｎｅｙ", "最佳", "★★★★★", "b​est basket"]


def _validate(title, tags):
    return T.validate_listing(title, tags, FACTS, competitors=T.competitor_names())


def test_the_clean_baseline_still_passes():
    r = _validate(TITLE, BASE)
    assert r["ok"], r["blocking"]


def test_every_evasive_tag_is_refused_by_the_seo_validator():
    assert EVASIVE
    for tag in EVASIVE:
        r = _validate(TITLE, BASE + [tag])
        assert not r["ok"], (tag, "passed")
        v = T.check_term(tag, FACTS, competitors=T.competitor_names())
        assert not v.ok and any(f.startswith("TERM_UNTRACEABLE") for f in v.findings), \
            (tag, v.findings)


def test_fullwidth_brand_ip_and_superlative_are_named_after_normalising():
    ip = T.check_term("ｄｉｓｎｅｙ", FACTS, competitors=[])
    assert any(f.startswith("TERM_PROTECTED_IP") for f in ip.findings), ip.findings
    best = T.check_term("ＢＥＳＴ ＳＥＬＬＥＲ", FACTS, competitors=[])
    assert any(f.startswith("TERM_MISLEADING") for f in best.findings), best.findings
    brand = T.check_term("ｒａｖｅｌｒｙ", FACTS, competitors=[])
    assert any(f.startswith("TERM_COMPETITOR_BRAND") for f in brand.findings), brand.findings


def test_evasive_title_segments_are_refused():
    for title in ("ＢＥＳＴ Hexagonal Storage Basket | Crochet Pattern PDF",
                  "Hexagonal Storage Basket | ｄｉｓｎｅｙ | Crochet Pattern PDF",
                  "Hexagonal Storage Basket | 最佳 | Crochet Pattern PDF"):
        assert not _validate(title, BASE)["ok"], title


def test_production_listing_schema_refuses_them_too():
    for tags in (["ｄｉｓｎｅｙ"], ["ＢＥＳＴ ＳＥＬＬＥＲ"], ["最佳"], ["ＤＩＳＮＥＹ ｂａｓｋｅｔ"]):
        assert LS.tag_problems(tags), tags
    for title in ("ＤＩＳＮＥＹ Basket Crochet Pattern PDF", "ＢＥＳＴ ＳＥＬＬＥＲ Basket",
                  "最佳 Basket Crochet Pattern PDF"):
        assert LS.title_problems(title), title
    # and check_payload (what build_payload calls) carries them
    payload = {"title": "ＢＥＳＴ ＳＥＬＬＥＲ Basket", "tags": ["最佳"], "type": "download",
               "who_made": "i_did", "quantity": 1}
    probs = " ".join(LS.check_payload(payload))
    assert "COMPATIBILITY_FORM" in probs and "UNTRACEABLE_SCRIPT" in probs, probs


def test_plain_titles_and_allowed_marks_are_untouched():
    assert LS.title_problems("Hexagon Coaster Set | Crochet Pattern PDF") == []
    assert LS.tag_problems(["crochet basket", "us and uk terms", "nursery-basket"]) == []
    assert LS.title_problems("Café Basket™ Crochet Pattern") == []


run(globals())
