"""K9 (wave 4): Product Truth for graded garments -- size matrix, recomputation at certify, fit
and ease, package completeness, children's sizing, claim evidence and graded provenance.

Rows: F-762 size architecture, F-768 QA recomputes grading, F-763 ease and fit explicit,
F-761 package completeness, F-362 age-range clarity, F-777 evidence-backed claims, F-794
design-difference ledger for graded designs, F-750 work direction and construction order.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.cir import graded as GR  # noqa: E402
from brambleloop.cir.grading import GradingRefused  # noqa: E402
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.gates import originality as O  # noqa: E402
from brambleloop.gates.certificate import certify, grading_findings  # noqa: E402
from brambleloop.gates.policy import ListingDraft, check_listing, claim_findings  # noqa: E402
from brambleloop.intel import childrens as ch  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402
from brambleloop.publish import pdf as P  # noqa: E402

_CACHE: dict = {}


def _family(key: str) -> dict[str, CIR]:
    if key not in _CACHE:
        _CACHE[key] = G.DESIGNS[key]().build_all()
    return _CACHE[key]


def _one(key: str, size: str) -> CIR:
    """A size, through one serialisation hop (every pipeline hop serialises)."""
    return CIR.from_dict(copy.deepcopy(_family(key)[size].to_dict()))


# ---- F-762 -------------------------------------------------------------------------------

def test_every_graded_size_carries_the_whole_size_matrix():
    for key, design in G.DESIGNS.items():
        fam = _family(key)
        assert fam, key
        names = design().sourced_sizes()
        for size, cir in fam.items():
            g = CIR.from_dict(cir.to_dict()).grading
            assert g is not None and g.size == size, (key, size)
            assert g.size_names == names, (key, g.size_names)
            assert g.fit == "relaxed" and g.ease_cm["bust"] > 0
            for e in g.sizes:
                assert set(e) == {"size", "body_cm", "intended_cm", "built_cm", "stitches",
                                  "rows", "yarn_m"}, e.keys()
                assert e["built_cm"]["chest"] > 0 and e["yarn_m"] > 0
                assert set(e["stitches"]) == {c.name for c in cir.components}
        yarn = [e["yarn_m"] for e in fam[names[0]].grading.sizes]
        assert all(b > a for a, b in zip(yarn, yarn[1:])), (key, yarn)


# ---- F-768 -------------------------------------------------------------------------------

def test_certify_recomputes_the_size_and_rechecks_the_family():
    cir = _one("harbour-drop-shoulder-pullover", "M")
    assert grading_findings(cir) == [], [f.message for f in grading_findings(cir)]
    # This size's stored yardage no longer matches its rows.
    stale = _one("harbour-drop-shoulder-pullover", "M")
    stale.grading.entry()["yarn_m"] += 40
    assert any("recomputed yardage" in f.message for f in grading_findings(stale))
    # A neighbour built smaller than the size below it: the family no longer grades.
    shrunk = _one("harbour-drop-shoulder-pullover", "M")
    shrunk.grading.entry("L")["built_cm"]["chest"] = 100.0
    msgs = [f.message for f in grading_findings(shrunk)]
    assert any("built chest" in m and "does not grow" in m for m in msgs), msgs
    # A body figure that is not the sourced standard's.
    forged = _one("pebble-raglan-cardigan", "6")
    forged.grading.entry("8")["body_cm"]["bust"] = 70.0
    assert any("not the sourced" in f.message for f in grading_findings(forged))
    # A graded build that lost its matrix cannot be re-checked, and says so.
    bare = _one("pebble-raglan-cardigan", "6")
    bare.grading = None
    assert [f.code for f in grading_findings(bare)] == ["GRADING_INCONSISTENT"]
    # Wired into the release chain: the tampered size is refused by certify itself.
    codes = [f.code for f in certify(shrunk).errors]
    assert "GRADING_INCONSISTENT" in codes, codes


# ---- F-763 / F-777 -----------------------------------------------------------------------

def test_a_fit_word_must_match_the_stated_ease():
    try:
        GR.FitIntent({"bust": 30}, character="relaxed")
    except GradingRefused as exc:
        assert "relaxed" in str(exc)
    else:
        raise AssertionError("a relaxed fit with 30 cm of ease was accepted")
    GR.FitIntent({"bust": 30}, character="oversized")
    cir = _one("harbour-drop-shoulder-pullover", "S")
    ok = claim_findings("Relaxed fit drop-shoulder pullover", "listing.title", cir)
    assert ok == [], [f.message for f in ok]
    bad = claim_findings("Oversized boxy pullover", "listing.title", cir)
    assert {f.code for f in bad} == {"POLICY_FIT_CLAIM_MISMATCH"}, [f.message for f in bad]
    plain = CIR.from_dict({**cir.to_dict(), "grading": None})
    assert [f.code for f in claim_findings("an oversized throw", "t", plain)] == \
        ["POLICY_FIT_CLAIM_UNSUPPORTED"]


def test_each_untraceable_claim_word_is_refused():
    cir = _one("harbour-drop-shoulder-pullover", "S")
    words = ["machine washable", "anti-pilling", "hypoallergenic", "quick to make",
             "a weekend project", "reversible", "9 sizes"]
    for phrase in words:
        codes = {f.code for f in claim_findings(f"Pullover pattern, {phrase}", "d", cir)}
        assert codes and codes <= {"POLICY_CLAIM_UNTRACEABLE",
                                   "POLICY_SIZE_COVERAGE_UNSUPPORTED"}, (phrase, codes)
    for phrase in ["quick reference stitch key", "a relaxed afternoon of colour", "1 size"]:
        assert claim_findings(phrase, "d", cir) == [], phrase
    draft = ListingDraft(title="Harbour Pullover Crochet Pattern",
                         description="Machine washable, written with AI assistance.",
                         tags=["oversized sweater"], price_cad=9.0)
    codes = [f.code for f in check_listing(draft, cir)]
    assert "POLICY_CLAIM_UNTRACEABLE" in codes and "POLICY_FIT_CLAIM_MISMATCH" in codes, codes


# ---- F-761 / F-762 / F-763 / F-362 in the customer's document -----------------------------

def test_a_graded_pdf_prints_its_size_chart_fit_care_and_is_complete():
    cir = _one("harbour-drop-shoulder-pullover", "M")
    doc = P.build_pattern_pdf(cir)
    text = P.extracted_text(doc.pdf_bytes)
    assert P.SIZES_HEADING in text and P.CARE_HEADING in text
    assert "Intended fit: relaxed" in text
    assert "This document is size M of 9" in text and "this document; to fit chest" in text
    for e in cir.grading.sizes:
        assert f"finished chest {e['built_cm']['chest']:g} cm" in text, e["size"]
    assert P.package_missing(cir, doc.prose) == ()
    # Without the size section the same release is an incomplete package.
    lines = [x for x in doc.prose.split("\n") if x not in (P.SIZES_HEADING, P.CARE_HEADING)]
    assert set(P.package_missing(cir, lines)) == {P.SIZES_HEADING, P.CARE_HEADING}
    # A one-size product's package does not demand a size chart.
    assert P.SIZES_HEADING not in P.package_requirements(
        CIR.from_dict({**cir.to_dict(), "grading": None}))


def test_a_childs_graded_garment_says_measurements_not_age_govern_fit():
    assert P.graded_childrens_assignment(_one("pebble-raglan-cardigan", "2")) == \
        ("childrens_garment", ch.UNDER_3)
    assert P.graded_childrens_assignment(_one("pebble-raglan-cardigan", "12")) == \
        ("childrens_garment", ch.SIX_TO_TWELVE)
    assert P.graded_childrens_assignment(_one("pebble-raglan-cardigan", "14")) is None
    assert P.graded_childrens_assignment(_one("harbour-drop-shoulder-pullover", "M")) is None
    assert "measurements_govern_fit" in ch.required_statements("childrens_garment",
                                                               ch.THREE_TO_SIX)
    cir = _one("pebble-raglan-cardigan", "4")
    doc = P.build_pattern_pdf(cir)
    text = P.extracted_text(doc.pdf_bytes)
    audit = P.childrens_statements_in(doc.pdf_bytes, P.childrens_assignment(cir))
    assert audit["complete"] and "measurements_govern_fit" in audit["present"], audit
    assert "Age does not decide fit" in text and "to fit chest" in text


# ---- F-794 -------------------------------------------------------------------------------

def test_a_benchmark_informed_graded_garment_needs_its_ledger():
    import dataclasses
    design = dataclasses.replace(G.pebble_cardigan(), benchmarks_consulted=("synthetic-b",))
    cir = design.build("4")
    assert cir.provenance.benchmarks_consulted == ("synthetic-b",)
    codes = [f.code for f in O.provenance_findings(cir)]
    assert "DESIGN_LEDGER_MISSING" in codes, codes
    plain = _one("pebble-raglan-cardigan", "4")
    assert "DESIGN_LEDGER_MISSING" not in [f.code for f in O.provenance_findings(plain)]


# ---- F-750 -------------------------------------------------------------------------------

def test_work_direction_is_written_read_back_and_held_to_the_rows():
    from brambleloop.cir import topology as TP
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.reverse import compare
    from brambleloop.cir.writer import write_pattern

    base = _one("pebble-raglan-cardigan", "4")
    assert TP.topology_problems(base) == []
    steps = TP.construction_steps(base)
    assert steps and [s["sleeve"] for s in steps if s["step"] == "work"] == \
        [None, "built_in", "built_in"], steps
    d = base.to_dict()
    for c in d["components"]:
        c["work_direction"] = "top_down"
    top = CIR.from_dict(d)
    assert TP.construction_fingerprint(top) != TP.construction_fingerprint(base)
    text = write_pattern(top, compile_cir(top))
    assert "Worked from the top down." in text
    assert [f for f in compare(top, text) if f.code == "REVERSE_DIRECTION"] == []
    # The document says one direction, the validated design another: refused.
    lied = text.replace("Worked from the top down.", "Worked from the bottom up.", 1)
    assert any(f.code == "REVERSE_DIRECTION" for f in compare(top, lied))
    # A sleeve continuing from held stitches cannot run the other way.
    d2 = top.to_dict()
    d2["components"][1]["work_direction"] = "bottom_up"
    msgs = TP.topology_problems(CIR.from_dict(d2))
    assert any("same direction" in m for m in msgs), msgs
    codes = [f.code for f in certify(CIR.from_dict(d2)).errors]
    assert "TOPOLOGY_INCONSISTENT" in codes, codes
    # Side to side contradicts an 'up' grain; an unknown direction or feature is refused.
    d3 = base.to_dict()
    d3["components"][0]["work_direction"] = "side_to_side"
    assert any("side to side" in m for m in TP.topology_problems(CIR.from_dict(d3)))
    for bad in ({"work_direction": "inside_out"}, {"feature": "tail"}):
        d4 = base.to_dict()
        d4["components"][0].update(bad)
        try:
            CIR.from_dict(d4)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted {bad}")
    # The certified digests of designs that declare nothing do not move.
    assert "work_direction" not in base.to_dict()["components"][0]


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print("FAIL", name, repr(exc)[:600])
    print(f"\n{len(tests) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
