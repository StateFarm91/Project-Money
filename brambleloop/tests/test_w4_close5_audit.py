"""W4-CLOSE5 spot audit: tests for the clause each downgraded row's evidence left unasserted.

The behaviour is in the deployed tree (b931d17); only the assertion was missing. Each test
quotes the clause it adds. See research/final_build/w4/CLOSE5.md (spot audit) and
BOARD_AUDIT.json (`reclosed`).

  F-251  "Titles/tags follow shop-language rules; translations are deliberate and not used as
          impression bait."  -- the TITLE half (only tags were asserted)
  F-073  "...novel assemblies ... and new construction primitives require stronger
          independent/physical evidence."  -- the two matrix features never asserted
  F-057  "Capture buyer-relevant crochet technique/material differentiators truthfully."
          -- the MATERIAL half (only technique was asserted)
  B2#219 "Maintain a changing elite panel including other category leaders and purchased
          Benchmark Library products."  -- the purchased-products half

Local, deterministic; no network, no provider, no spend.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close5_audit.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))


# ---- F-251: the title is held to the shop language too --------------------------------------

def _copy(**kw):
    from brambleloop.commerce import seo

    base = dict(title="Market Basket Trio | Crochet Pattern PDF | 3 Sizes",
                tags=[f"tag{i} word{i}" for i in range(13)], description="d" * 400,
                materials=[], price_cad=9.0, supported_claims=[])
    base.update(kw)
    return seo.ListingCopy(**base)


def test_f251_a_foreign_language_title_is_refused_unless_a_deliberate_translation():
    from brambleloop.commerce import seo

    english_tags = [f"tag{i} word{i}" for i in range(13)]
    for title in ("Häkelanleitung Korb Trio | Crochet Pattern PDF",     # by alphabet
                  "Patron Ganchillo Cesta | Crochet Pattern PDF"):      # ASCII foreign words
        gate = seo.check_search_copy(_copy(title=title, tags=english_tags))
        assert any(p.startswith("LISTING_LANGUAGE") for p in gate["blocking"]), (title, gate)
        bait = seo.check_search_copy(_copy(title=title, tags=english_tags),
                                     translation_record="translated for more impressions")
        assert any("impression bait" in p for p in bait["blocking"]), (title, bait["blocking"])
        ok = seo.check_search_copy(_copy(title=title, tags=english_tags), translation_record={
            "language": "de" if "Häkel" in title else "es",
            "reason": "a translated edition of the PDF ships with this listing"})
        assert not any(p.startswith("LISTING_LANGUAGE") for p in ok["blocking"]), ok
    # the English title with English tags is not asked for anything
    plain = seo.check_search_copy(_copy(tags=english_tags))
    assert not any(p.startswith("LISTING_LANGUAGE") for p in plain["blocking"]), plain


# ---- F-073: novel assemblies and new primitives raise the class ----------------------------

def test_f073_a_novel_assembly_raises_the_class_and_a_short_one_does_not():
    from brambleloop.cir.model import Seam
    from brambleloop.gates import risk_matrix as rm

    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    cir.risk_class = "A"
    name = cir.components[0].name
    keys = lambda c: [f.key for f in rm.features(c, {}, None)]  # noqa: E731
    short = copy.deepcopy(cir)
    short.assembly = [Seam("whipstitch", name, name) for _ in range(rm.NOVEL_ASSEMBLY_SEAMS)]
    assert "multi_seam_assembly" not in keys(short)
    novel = copy.deepcopy(cir)
    novel.assembly = [Seam("whipstitch", name, name)
                      for _ in range(rm.NOVEL_ASSEMBLY_SEAMS + 1)]
    assert "multi_seam_assembly" in keys(novel)
    m = rm.assess(novel, twin_summary={}, primitive_status=None)
    assert m["declared"] == "A" and m["derived"] == "B" and m["effective"] == "B", m
    assert m["raised_by_matrix"] is True and m["required_physical"] == rm.PARTIAL_PHYSICAL


def test_f073_a_new_construction_primitive_raises_the_class_until_calibrated():
    from brambleloop.cir.model import Op, Row
    from brambleloop.gates import risk_matrix as rm

    from tests import fixtures

    cir = fixtures.good_mosaic_panel()
    cir.risk_class = "A"
    base = rm.matrix_for(cir)
    assert "uncalibrated_primitive" not in [f["key"] for f in base["features"]], base
    cir.components[0].rows.append(Row(index=5, ops=[Op("sc", 19), Op("bob"), Op("sc", 20)],
                                      declared_count=40, color="forest", turning_chain=1))
    m = rm.matrix_for(cir)
    feats = {f["key"]: f for f in m["features"]}
    assert "uncalibrated_primitive" in feats and "bob" in feats["uncalibrated_primitive"]["detail"]
    assert rm.RANK[m["effective"]] >= rm.RANK["B"] and m["required_physical"], m
    calibrated = rm.matrix_for(cir, calibrated_primitives={"bob"})
    assert "uncalibrated_primitive" not in [f["key"] for f in calibrated["features"]], calibrated


# ---- F-057: a material the pattern does not use is never claimed ---------------------------

def test_f057_a_material_the_pattern_does_not_use_is_refused_and_the_strategy_blocks_it():
    from brambleloop.products import launch0 as L
    from brambleloop.seo import facts as facts_mod
    from brambleloop.seo import strategy, truth

    slug = next(s for s in L.LAUNCH0_SLUGS
                if any(f["family"] == "material" for f in strategy.FAMILIES.get(s, [])))
    cand = L.candidate(slug)
    f = facts_mod.for_product(cand)
    fibres = " ".join(f.materials).lower()
    assert fibres, "the product's materials are its facts"
    used = next(w for w in ("cotton", "acrylic", "wool", "linen", "merino") if w in fibres)
    unused = [w for w in ("wool", "merino", "acrylic", "linen", "alpaca", "bamboo")
              if w not in fibres]
    assert truth.check_term(f"{used} crochet", f).ok
    for w in unused:
        v = truth.check_term(f"{w} crochet", f)
        assert not v.ok and any(x.startswith("TERM_UNTRACEABLE") for x in v.findings), (w, v)
    # the shipped material family is true...
    clean = strategy.build(cand, f)
    mat = [r for fam in clean["families"] if fam["family"] == "material" for r in fam["phrases"]]
    assert mat and all(r["true"] for r in mat), mat
    assert not any(b.startswith("FAMILY_PHRASE_UNTRUE: material") for b in clean["blocking"])
    # ...and a material phrase the product does not use blocks the strategy
    saved = strategy.FAMILIES[slug]
    strategy.FAMILIES[slug] = [dict(fam, phrases=list(fam["phrases"]) + [f"{unused[0]} crochet"])
                               if fam["family"] == "material" else fam for fam in saved]
    try:
        bad = strategy.build(cand, f)
    finally:
        strategy.FAMILIES[slug] = saved
    assert bad["ok"] is False
    assert any(b.startswith("FAMILY_PHRASE_UNTRUE: material") and unused[0] in b
               for b in bad["blocking"]), bad["blocking"]


# ---- B2#219: purchased Benchmark Library products put their seller on the panel ------------

def test_b2_219_a_purchased_library_product_puts_its_seller_on_the_panel():
    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing, BenchmarkProduct
    from brambleloop.intel import benchmarks, mission_runtime, panel

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/panel.sqlite")
    db.create_all()
    today = date(2026, 10, 20)
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="mjs-1",
                               title="Cardigan", pod="garments", audit_state="audited",
                               price_cad=9.0, media_count=6, detail={}))
    before = {m.seller_ref for m in mission_runtime.panel_members(db, today)}
    assert before == {benchmarks.MJS_KEY}
    with db.session() as s:
        s.add(BenchmarkProduct(ref="lib-1", seller="library_seller_x", title="Purchased hat",
                               pod="accessories", purchased_on="2026-10-01", paid_cad=6.5))
    members = {m.seller_ref: m for m in mission_runtime.panel_members(db, today)}
    assert set(members) == {benchmarks.MJS_KEY, "library_seller_x"}, members
    bought = members["library_seller_x"]
    assert bought.categories == ("accessories",) and bought.added_on == date(2026, 10, 1)
    assert bought.is_anchor is False and members[benchmarks.MJS_KEY].is_anchor is True
    # the panel is a changing set, and one seller is not a mechanism worth learning
    st = panel.panel_state(list(members.values()), on=today)
    assert st, st
    one = panel.mechanism_is_learnable(mechanism="gallery_depth",
                                       seen_in=(benchmarks.MJS_KEY,))
    two = panel.mechanism_is_learnable(mechanism="gallery_depth",
                                       seen_in=(benchmarks.MJS_KEY, "library_seller_x"))
    assert not one.get("learnable") and two.get("learnable"), (one, two)


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 5, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
