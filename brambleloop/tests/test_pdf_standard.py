"""ENG-PDF-PREMIUM: the family-aware premium PDF standard, held to the rendered bytes.

- Golden structure per family: the rules each family requires, and a real document of that
  family that passes all of them in both editions.
- US/UK term correctness, a certified count after every row, reproducible bytes.
- A mutation for every rule: delete the rule's evidence from a real document's extracted
  text, and that rule, by id, must fail. And one end-to-end mutation: a renderer that drops
  the licence is refused by `build_pattern_pdf` itself.
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.commerce import terms as T  # noqa: E402
from brambleloop.publish import abbreviations, pdf  # noqa: E402
from brambleloop.publish import pdf_standard as S  # noqa: E402

RELEASED = date(2026, 10, 27)


def _cir(key: str):
    if key == "garment":
        from brambleloop.products import garments
        return garments.every_graded_cir()["harbour-drop-shoulder-pullover-xs"]
    if key == "pillow":
        from brambleloop.products import moment_candidates
        return moment_candidates.heart_row_ring_pillow()
    from brambleloop.products import launch0
    return launch0.cir_for(key)


# One representative per family, chosen for render time.
FAMILY_DOCS = {
    S.SMALL_HOME: "hexagon_coasters",
    S.BLANKET: "nordic_forest_baby",
    S.BASKET: "basket_small",
    S.GARMENT: "garment",
    S.PILLOW: "pillow",
}


@lru_cache(maxsize=None)
def _doc(key: str, term: str = "US"):
    cir = _cir(key)
    result = compile_cir(cir)
    twin = build_twin(cir, result)
    doc = pdf.build_pattern_pdf(cir, terminology=term, released_on=RELEASED, twin=twin)
    return cir, result, twin, doc


@lru_cache(maxsize=None)
def _text(key: str, term: str = "US") -> str:
    return pdf.extracted_text(_doc(key, term)[3].pdf_bytes)


def _ctx(key: str, term: str = "US") -> S.Context:
    cir, result, twin, _ = _doc(key, term)
    return S.context(cir, twin, result, term)


# ---- families -------------------------------------------------------------------------------

def test_each_representative_is_classified_into_its_family():
    for fam, key in FAMILY_DOCS.items():
        assert S.family_of(_cir(key)) == fam, (key, S.family_of(_cir(key)))
    assert S.family_of(_cir("placemat_pair")) == S.SMALL_HOME
    assert S.family_of(_cir("snowflake_ornaments")) == S.SMALL_HOME
    assert S.family_of(_cir("cloudline_blanket")) == S.BLANKET


def test_an_amigurumi_cir_gets_the_toy_rules_when_one_exists():
    """No amigurumi engine exists yet (ENG-FAMILIES: none). Its rule set is fixed now."""
    import dataclasses
    cir = dataclasses.replace(_cir("hexagon_coasters"), title="Little Fox Amigurumi Toy")
    assert S.family_of(cir) == S.AMIGURUMI
    _c, result, twin, _d = _doc("hexagon_coasters")
    ctx = S.context(cir, twin, result, "US", childrens=False)
    need = {r.id for r in S.RULES if r.required_for(ctx)}
    assert {"safety", "inline_diagrams"} <= need


GOLDEN = {
    # The concise-but-complete standard every family starts from.
    "core": {"cover", "overview_table", "supply_yarn", "supply_hook_notions",
             "gauge_every_fabric", "construction_narrative", "abbreviations",
             "row_counts", "rs_ws", "finishing", "tips", "licence",
             "about_brand", "rendering_disclosure", "substitution", "schematic",
             "techniques_appendix"},
    S.SMALL_HOME: {"colourwork_chart"},
    S.BLANKET: {"colourwork_chart", "safety"},
    S.BASKET: {"inline_diagrams", "colourwork_chart"},
    S.GARMENT: {"size_chart", "assembly"},
    S.PILLOW: {"inline_diagrams", "assembly", "colourwork_chart"},
}


def _golden(fam: str, term: str):
    key = FAMILY_DOCS[fam]
    _cir_, _r, _t, doc = _doc(key, term)
    audit = doc.standard
    assert audit["family"] == fam
    assert audit["ok"], (key, term, audit["failures"])
    expected = GOLDEN["core"] | GOLDEN[fam] | {"running_header_footer"}
    assert set(audit["required"]) == expected, (
        key, sorted(set(audit["required"]) ^ expected))


def test_golden_structure_small_home_goods():
    for term in ("US", "UK"):
        _golden(S.SMALL_HOME, term)


def test_golden_structure_blanket():
    for term in ("US", "UK"):
        _golden(S.BLANKET, term)


def test_golden_structure_basket():
    for term in ("US", "UK"):
        _golden(S.BASKET, term)


def test_golden_structure_garment():
    for term in ("US", "UK"):
        _golden(S.GARMENT, term)


def test_golden_structure_pillow():
    for term in ("US", "UK"):
        _golden(S.PILLOW, term)


def test_a_coaster_is_not_held_to_the_garment_manual():
    need = set(_doc("hexagon_coasters")[3].standard["required"])
    assert "size_chart" not in need and "assembly" not in need and "safety" not in need


# ---- terms, counts, bytes --------------------------------------------------------------------

def test_each_edition_uses_its_own_terms():
    for key in ("hexagon_coasters", "placemat_pair"):
        uk = S._instructions(_text(key, "UK"), _ctx(key, "UK"))
        us = S._instructions(_text(key, "US"), _ctx(key, "US"))
        assert uk and us
        assert not re.search(r"(?<![\w-])sc(?![\w-])", uk), key
        assert re.search(r"(?<![\w-])sc(?![\w-])", us), key
        # The UK edition's double crochet is the US single crochet.
        assert re.search(r"(?<![\w-])dc(?![\w-])", uk), key
        used = _doc(key)[2].stitch_types_used
        assert used, key
        for code in used:
            for term, body in (("US", us), ("UK", uk)):
                key_text = _text(key, term)
                assert any(w in key_text for w in abbreviations.spellings(code, term)), (
                    key, term, code)


def test_yarn_is_in_yards_in_the_us_edition_and_metres_in_the_uk_edition():
    for key in ("hexagon_coasters", "nordic_forest_baby"):
        us = S._section(_text(key, "US"), "How much yarn", ("Substituting",))
        uk = S._section(_text(key, "UK"), "How much yarn", ("Substituting",))
        assert " yd" in us and "100 g ball" in us
        assert " yd" not in uk and " m" in uk and "100 g ball" in uk


def test_the_hook_is_given_in_us_and_mm_with_the_gauge_phrase():
    t = _text("hexagon_coasters")
    assert "5 mm (US H-8)" in t and S.HOOK_GAUGE_PHRASE in t
    assert S.hook_words(5.25) == "5.25 mm"          # no guessed US name off the table


def test_every_row_and_round_has_its_certified_count():
    for key in ("hexagon_coasters", "placemat_pair", "garment", "pillow"):
        for term in ("US", "UK"):
            rows = S.row_counts(_text(key, term), term)
            assert len(rows) >= 7, (key, term)
            assert all(c is not None for _k, _i, c in rows), (key, term)
            assert not S._counts(_text(key, term), _ctx(key, term)), (key, term)


def test_flat_rows_alternate_rs_and_ws_from_the_cirs_turns():
    body = S._instructions(_text("placemat_pair"), _ctx("placemat_pair"))
    assert "Row 1 (RS) (cream):" in body and "Row 2 (WS) (wine):" in body
    assert "Row 3 (RS)" in body
    assert pdf.RS_NOTE[:40] in _text("placemat_pair")


def test_same_release_same_bytes_in_both_editions():
    for key in ("hexagon_coasters", "placemat_pair"):
        cir = _cir(key)
        for term in ("US", "UK"):
            a = pdf.build_pattern_pdf(cir, terminology=term, released_on=RELEASED)
            b = pdf.build_pattern_pdf(_cir(key), terminology=term, released_on=RELEASED)
            assert hashlib.sha256(a.pdf_bytes).digest() == hashlib.sha256(b.pdf_bytes).digest()


def test_multi_piece_covers_do_not_count_the_object_by_its_first_piece():
    assert pdf.makes_words(_cir("hexagon_coasters")) == "Makes 4 coasters"
    assert pdf.makes_words(_cir("garment")) == "Made from 4 pieces"
    assert pdf.makes_words(_cir("pillow")) == "Made from 3 pieces"
    for key in ("garment", "pillow"):
        t = _text(key)
        assert "bodys" not in t and "Makes 3 pillows" not in t


def test_the_licence_is_ours_and_carries_credit_and_a_disclaimer():
    sale = T.BRAMBLELOOP_TERMS.sentence(T.FINISHED_ITEM_SALE)
    assert "not manufactured at scale" in sale and "credit to Brambleloop Studio" in sale
    for key in FAMILY_DOCS.values():
        t = _text(key)
        assert sale in t and S.DISCLAIMER in t, key


def test_the_brand_page_is_about_the_studio_and_never_laura():
    for key in FAMILY_DOCS.values():
        for term in ("US", "UK"):
            t = _text(key, term)
            assert S.ABOUT_HEADING in t and not re.search(r"\bLaura\b", t), (key, term)
    assert not any("Laura" in p for p in S.ABOUT_PARAGRAPHS)


# ---- mutations: one per rule ----------------------------------------------------------------

def _drop(*needles):
    def m(text):
        for n in needles:
            text = text.replace(n, "")
        return text
    return m


def _sub(pattern, repl):
    return lambda text: re.sub(pattern, repl, text)


# rule id -> (document key that requires the rule, mutation of its extracted text)
MUTATIONS = {
    "cover": ("hexagon_coasters", _drop("SKILL")),
    "overview_table": ("hexagon_coasters", _drop("CYC 3")),
    "supply_yarn": ("hexagon_coasters", _drop("100 g ball")),
    "supply_hook_notions": ("hexagon_coasters", _drop(S.HOOK_GAUGE_PHRASE)),
    "gauge_every_fabric": ("hexagon_coasters", _sub(r"14\.5 sts x 16(\.0)? rows", "x")),
    "construction_narrative": ("hexagon_coasters", _drop("How it is made")),
    "schematic": ("hexagon_coasters", _drop("FINISHED MEASUREMENTS")),
    "size_chart": ("garment", _drop("finished chest")),
    "abbreviations": ("hexagon_coasters", _drop("US CROCHET TERMS")),
    "row_counts": ("hexagon_coasters", _sub(r"\(42 sts\)", "")),
    "rs_ws": ("placemat_pair", _sub(r"Row 2 \(WS\)", "Row 2")),
    "inline_diagrams": ("basket_small", _drop("construction diagram")),
    "colourwork_chart": ("hexagon_coasters", _drop("CHART AND KEYS")),
    "finishing": ("hexagon_coasters", _drop("weave in")),
    "assembly": ("pillow", _drop("ASSEMBLY AND FINISHING")),
    "substitution": ("hexagon_coasters", _drop("yd per gram")),
    "tips": ("hexagon_coasters", _drop("Tips and troubleshooting")),
    "licence": ("hexagon_coasters", _drop("credit to Brambleloop Studio")),
    "about_brand": ("hexagon_coasters", lambda t: t + " Designed by Laura."),
    "rendering_disclosure": ("hexagon_coasters",
                             _drop("not a photograph", "digital rendering", "Photograph")),
    "safety": ("nordic_forest_baby", _drop(pdf.CHILDRENS_HEADING)),
    "techniques_appendix": ("hexagon_coasters", _drop("Starting in a magic ring")),
}


def test_every_rule_has_a_mutation():
    # The amigurumi-only rules (no engine document is amigurumi) are mutated on the template's
    # amigurumi document in tests/test_pdf_diagrams.py (AMI_MUTATIONS), each by id.
    from tests.test_pdf_diagrams import AMI_MUTATIONS

    assert set(MUTATIONS) | set(AMI_MUTATIONS) | {"running_header_footer",
                                                  "special_stitches"} == set(S.RULE_IDS)



def test_a_special_stitch_without_its_definition_fails():
    """No catalogue product uses a special stitch yet, so the rule is held on a context whose
    twin uses the bobble: required, failing without the section, passing with it."""
    import types
    from brambleloop.publish import abbreviations as A

    ctx = _ctx("hexagon_coasters")
    twin = types.SimpleNamespace(**{k: getattr(ctx.twin, k) for k in
                                    ("stitch_types_used", "yarn_metres_by_color", "width_cm")})
    twin.stitch_types_used = set(twin.stitch_types_used) | {"bob"}
    import dataclasses
    ctx = dataclasses.replace(ctx, twin=twin)
    rule = next(r for r in S.RULES if r.id == "special_stitches")
    assert rule.required_for(ctx)
    assert rule.check(_text("hexagon_coasters"), ctx)
    ok = _text("hexagon_coasters") + " Special stitches bob " + A.method("bob", "US")
    assert not rule.check(ok, ctx)


def test_each_rule_fails_when_its_evidence_is_removed():
    for rule_id, (key, mutate) in sorted(MUTATIONS.items()):
        ctx = _ctx(key)
        text = _text(key)
        assert rule_id in {r.id for r in S.RULES if r.required_for(ctx)}, (rule_id, key)
        before = S.audit_text(text, ctx)
        assert rule_id not in before.failures, (rule_id, before.failures.get(rule_id))
        mutated = mutate(text)
        assert mutated != text, f"{rule_id}: the mutation changed nothing in {key}"
        after = S.audit_text(mutated, ctx)
        assert rule_id in after.failures, f"{rule_id}: removing its evidence did not fail it"


def test_a_page_without_its_folio_or_running_head_fails():
    cir, _r, _t, doc = _doc("hexagon_coasters")
    pages = S.pages_text(doc.pdf_bytes)
    assert not S.header_footer_failures(pages, cir)
    broken = list(pages)
    broken[2] = broken[2].replace(f"page 3 of {len(pages)}", "")
    assert S.header_footer_failures(broken, cir)
    broken = list(pages)
    broken[4] = broken[4].replace("BRAMBLELOOP ·", "")
    assert S.header_footer_failures(broken, cir)


def test_no_production_code_turns_the_standard_off():
    src = ROOT / "src" / "brambleloop"
    hits = [str(p.relative_to(src)) for p in src.rglob("*.py")
            if "enforce_standard=False" in p.read_text(encoding="utf-8")]
    assert hits == [], hits


def test_the_build_refuses_a_pdf_that_drops_a_required_section():
    original = pdf.licence_paragraphs
    try:
        pdf.licence_paragraphs = lambda: ["Terms"]
        try:
            pdf.build_pattern_pdf(_cir("hexagon_coasters"), released_on=RELEASED)
        except S.PremiumStandardRefused as e:
            assert "licence" in str(e)
        else:
            raise AssertionError("a PDF without its licence was built")
    finally:
        pdf.licence_paragraphs = original


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
