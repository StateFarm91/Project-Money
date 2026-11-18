"""S1 Product Truth, third review of a570aab7: the size parser fails closed (D-S1-FAIL-CLOSED).

Each review round found more title phrasings the parser silently dropped, and the product
certified at its template size. The design is now fail-closed: every title is tokenised, and
after the bound claims (named classes, stated dimensions with a unit, relative words a family
defines) are taken out, any figure, fraction, decimal, number word, size-class word the family
does not define, size letter, leftover "size" or unit with no figure is refused with
"unbound size token: <token>" -- at plan and at certification. Only the cited entries of
`size_truth.ALLOWED_NON_SIZE` pass, and the count / colour / grade entries are bound to what the
CIR states.

* S1F2-H1: "3 yards", "2 yards", "108", "72", "20", "60 yd", "forty by fifty inches" were
  dropped and certified at the default size. Yards are a unit now; every other figure is bound
  or refused.
* S1F2-M1: body / euro / floor pillows, double / toddler blankets, medium, half size, size S /
  size L passed at the default size while small / petite were refused.
* LOWs: plan and certify disagreed (the plan now measures the size it would draft and runs the
  certificate's own size check on it); curly quotes were refused; "XL Dog Blanket" was drafted
  from the human large-blanket family.
* Rebase: w6-INTEG1's A4a object-size check and this branch's are one check.

Every case runs the real path: plan -> geometry -> builder -> compile -> twin -> certify.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s1_product_truth_3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.creative import fallback_constructions as FC  # noqa: E402
from brambleloop.creative import size_truth as ST  # noqa: E402
from brambleloop.gates import certificate as C  # noqa: E402

import test_s1_fix_size_families as F  # noqa: E402

SIZE_CODES = {"OBJECT_SIZE_NOT_AS_TITLED", "OBJECT_SIZE_OUT_OF_BAND", "OBJECT_SIZE_UNBOUND",
              "LISTING_SIZE_NOT_AS_TITLED"}


def _size_errors(cir):
    cert = C.certify(cir)
    return sorted({f.code for f in cert.findings
                   if str(f.severity) == C.ERROR and f.code in SIZE_CODES})


def _drafted_at(category, title, short, long_):
    route, cir, twin = F._drafted(category, title)
    assert twin is not None, (title, route)
    got = sorted((twin.width_cm, twin.height_cm))
    assert ST._met(short, got[0]) and ST._met(long_, got[1]), (title, got, (short, long_))
    assert _size_errors(cir) == [], (title, got, C.object_size_findings(cir, twin))
    return got


def _refused_at_draft(category, title, *words):
    route = FC.plan(category=category, title=title)
    assert route["family"] == FC.REFUSED, (title, route)
    for w in words:
        assert w in route["why"], (title, w, route["why"])
    return route["why"]


def _unbound_at_certify(title, size, token=None):
    codes = F._size_codes(F._Cir(title), F._Twin(*size))
    assert "OBJECT_SIZE_UNBOUND" in codes, (title, codes)
    if token:
        msgs = [f.message for f in C.object_size_findings(F._Cir(title), F._Twin(*size))]
        assert any(f"unbound size token: {token}" in m for m in msgs), (title, msgs)


class _Comp:
    def __init__(self, make):
        self.make = make


class _Grading:
    def __init__(self, size):
        self.size = size


class _FactCir:
    """A CIR stand-in carrying the facts a title's counts bind to."""

    def __init__(self, title, *, makes=(1,), colours=2, grade=None):
        self.title = title
        self.components = [_Comp(m) for m in makes]
        self.colors = {f"c{i}": "#000000" for i in range(colours)}
        self.grading = _Grading(grade) if grade else None


def _cert_unbound(cir, size=(40.0, 40.0)):
    return [f.message for f in C.object_size_findings(cir, F._Twin(*size))
            if f.code == "OBJECT_SIZE_UNBOUND"]


# ---- S1F2-H1: no figure is dropped -----------------------------------------------------------


def test_h1_every_unbound_figure_is_refused_at_plan_and_at_certify():
    for category, title, token, template in (
            ("runner", "Linen Table Runner 108", "108", (32.0, 120.7)),
            ("scarf", "Linen Scarf 72", "72", (19.2, 152.2)),
            ("pillow", "Linen Pillow Cover 20", "20", (41.6, 41.7)),
            ("blanket", "Linen Throw forty by fifty inches", "forty", (128.0, 152.2)),
            ("blanket", "Linen Throw 1/2", "1/2", (128.0, 152.2)),
            ("blanket", "Linen Throw ½", "1⁄2", (128.0, 152.2)),
            ("blanket", "Linen Throw 2026", "2026", (128.0, 152.2)),
            ("blanket", "Linen Throw 1,5 m", "1,5", (128.0, 152.2))):
        _refused_at_draft(category, title, f"unbound size token: {token}")
        # The certificate refuses the template-size twin the old code certified.
        _unbound_at_certify(title, template, token)


def test_h1_yards_are_a_unit():
    assert ST.stated_dimensions("Linen Table Runner 2 yards") == (182.9,)
    assert ST.stated_dimensions("Linen Throw 60 yd") == (5486.4,)
    # 2 yards is a runner's length: drafted at it, and it certifies.
    _drafted_at("runner", "Linen Table Runner 2 yards", 35.0, 182.9)
    # 3 yards (274 cm) is longer than any scarf, 60 yards is no throw: refused, by size.
    _refused_at_draft("scarf", "Linen Scarf 3 yards", "274.3")
    _refused_at_draft("blanket", "Linen Throw 60 yd", "5486.4")
    # And the template-size twins the old code certified are refused at certify.
    assert "OBJECT_SIZE_NOT_AS_TITLED" in F._size_codes(F._Cir("Linen Scarf 3 yards"),
                                                        F._Twin(19.2, 152.2))
    assert "OBJECT_SIZE_NOT_AS_TITLED" in F._size_codes(F._Cir("Linen Table Runner 2 yards"),
                                                        F._Twin(32.0, 120.7))


# ---- S1F2-M1: size-class words without a cited family ----------------------------------------


def test_m1_size_class_words_without_a_cited_family_are_refused():
    for category, title, token, template in (
            ("pillow", "Body Pillow Cover", "body", (41.6, 41.7)),
            ("pillow", "Euro Pillow Sham", "euro", (41.6, 41.7)),
            ("pillow", "Floor Pillow Cover", "floor", (41.6, 41.7)),
            ("pillow", "King Pillow Cover", "king", (41.6, 41.7)),
            ("blanket", "Double Linen Blanket", "double", (128.0, 152.2)),
            ("blanket", "Toddler Linen Blanket", "toddler", (128.0, 152.2)),
            ("blanket", "Half Size Linen Blanket", "half", (128.0, 152.2)),
            ("blanket", "Linen Throw Size S", "size s", (128.0, 152.2)),
            ("blanket", "Linen Throw Size L", "size l", (128.0, 152.2))):
        _refused_at_draft(category, title, f"unbound size token: {token}")
        _unbound_at_certify(title, template, token)


def test_m1_medium_follows_the_relative_size_rule_like_small_and_petite():
    for word in ("Small", "Petite", "Medium"):
        title = f"{word} Linen Throw"
        _refused_at_draft("blanket", title, "relative size", word.lower())
        _unbound_at_certify(title, (128.0, 152.2))


def test_m1_construction_phrases_with_bed_words_are_not_sizes():
    for title in ("Double-Sided Linen Throw", "Double Layer Linen Throw",
                  "Double Crochet Linen Throw"):
        assert ST.plan_refusal("blanket", title) is None, (title, ST.plan_refusal("blanket",
                                                                                 title))
        _drafted_at("blanket", title, 128.0, 152.2)


# ---- LOWs ------------------------------------------------------------------------------------


def test_low_plan_refuses_exactly_what_certify_refuses():
    # Each was drafted by the plan and then refused at certify (OBJECT_SIZE_NOT_AS_TITLED).
    for category, title in (("blanket", "Linen Throw 1.5 m"),
                            ("blanket", 'Linen Throw Blanket 60"'),
                            ("blanket", "Large Baby Blanket")):
        _refused_at_draft(category, title)
    # Whatever the plan drafts, the certificate finds no size error in: the property, over
    # every case of this review and the earlier ones.
    titles = (("blanket", "Linen Blanket 150cm square"), ("blanket", "Linen Blanket 2 metres"),
              ("runner", "Linen Table Runner 2 yards"), ("runner", "Linen Table Runner 72 in"),
              ("blanket", "Linen Throw 50”x60”"), ("blanket", "Large Linen Throw"),
              ("blanket", "Queen Linen Blanket"), ("pillow", "Linen Pillow Cover 26x26"),
              ("pillow", "Linen Lumbar Pillow 12 x 24"), ("blanket", "Linen Throw 2 in 1"),
              ("blanket", "Linen Throw 1.5 m"), ("blanket", 'Linen Throw Blanket 60"'),
              ("blanket", "Large Baby Blanket"), ("blanket", "XL Dog Blanket"),
              ("scarf", "Linen Scarf 72"), ("blanket", "Medium Linen Throw"),
              ("wall_decor", "Large Tapestry 100 x 150 cm"), ("baby", "Baby Burp Cloth"))
    drafted = 0
    for category, title in titles:
        route, cir, twin = F._drafted(category, title)
        if twin is None:
            continue
        drafted += 1
        assert _size_errors(cir) == [], (title, twin.width_cm, twin.height_cm,
                                         C.object_size_findings(cir, twin))
    assert drafted >= 10, drafted


def test_low_curly_quotes_are_inch_marks():
    straight = ST.stated_dimensions('Linen Throw 50"x60"')
    assert straight == (127.0, 152.4), straight
    for curly in ("Linen Throw 50”x60”", "Linen Throw 50″x60″",
                  "Linen Throw 50“x60”"):
        assert ST.stated_dimensions(curly) == straight, curly
        assert ST.plan_refusal("blanket", curly) is None, curly
    _drafted_at("blanket", "Linen Throw 50”x60”", 127.0, 152.4)


def test_low_a_pet_blanket_has_no_human_size_family():
    _refused_at_draft("blanket", "XL Dog Blanket", "pet blanket", "'xl'")
    _refused_at_draft("blanket", "Large Cat Blanket", "pet blanket")
    _refused_at_draft("blanket", "Queen Dog Blanket", "unbound size token: queen")
    # The 153.6 x 202.9 cm "XL Dog Blanket" the old code drafted is refused at certify.
    _unbound_at_certify("XL Dog Blanket", (153.6, 202.9))
    # A person's large blanket keeps its recorded family (D-S1-RELATIVE-SIZE).
    assert ST.plan_refusal("blanket", "Large Linen Throw") is None


# ---- the allow-list: each entry bound or shown not to be a size ------------------------------


def test_allow_list_n_in_1_is_not_a_size():
    for title in ("Linen Throw 2 in 1", "Linen Throw 2-in-1", "Linen Throw 3 in 1"):
        assert ST.plan_refusal("blanket", title) is None, title
        assert _cert_unbound(_FactCir(title), (128.0, 152.2)) == [], title
    _drafted_at("blanket", "Linen Throw 2-in-1", 128.0, 152.2)
    # Only the idiom: "5 in 1" is not in it, and "2 in" before a non-1 figure is not inches.
    assert ST.plan_refusal("blanket", "Linen Throw 5 in 1")


def test_allow_list_counts_are_bound_to_the_piece_count():
    for title, make in (("Textured Stripe Ornament Set (6)", 6), ("Ornament Set of 6", 6),
                        ("Ornament Set of Six", 6), ("Motif Library (12)", 12),
                        ("Ornament 6-Piece Set", 6), ("Ornament 6 Pack", 6)):
        assert _cert_unbound(_FactCir(title, makes=(make,))) == [], title
        assert _cert_unbound(_FactCir(title, makes=(make - 1,))), title
    # A count with no single component to bind to is unbound.
    assert _cert_unbound(_FactCir("Ornament Set (2)", makes=(1, 1)))
    # The fallback drafts one piece: a set of four is refused before drafting.
    _refused_at_draft("placemat", "Linen Placemat Set of 4", "unbound size token: set of 4")


def test_allow_list_colour_counts_are_bound_to_the_colour_table():
    assert _cert_unbound(_FactCir("Two-Colour Ornament", colours=2)) == []
    assert _cert_unbound(_FactCir("3 Colour Ornament", colours=3)) == []
    assert _cert_unbound(_FactCir("Two-Colour Ornament", colours=3))
    # At plan the palette is not chosen yet: the count is checked at certification.
    assert ST.plan_refusal("blanket", "Two-Colour Linen Throw") is None


def test_allow_list_garment_grades_are_bound_to_the_grading():
    for grade in ("2X", "XL", "XS", "10", "M"):
        title = f"Harbour Pullover (size {grade})"
        assert _cert_unbound(_FactCir(title, makes=(1, 2, 1), grade=grade)) == [], title
        assert _cert_unbound(_FactCir(title, makes=(1, 2, 1), grade="L")), title
    # Every graded garment in the catalogue binds its own title.
    from brambleloop.products import garments as G

    cirs = G.every_graded_cir()
    assert len(cirs) >= 17, len(cirs)
    for slug, cir in cirs.items():
        assert ST.claims(None, cir.title, ST.facts_of(cir))["unbound"] == [], (slug, cir.title)


def test_allow_list_letter_led_codes_are_not_figures():
    # S1F3-H1 (round 5): the code entry is an exact, cited list -- C2C and the Craft Yarn
    # Council US hook sizes. "C5" and "J7" were accepted by the old letter-led shape; neither
    # is a hook size, so they are unbound now (tests/test_s1_product_truth_4.py has the rest).
    for title in ("H-8 Hook Linen Throw", "Linen Throw J-10", "Tapestry C2C Linen Throw"):
        assert ST.claims("blanket", title)["unbound"] == [], title
        assert _cert_unbound(_FactCir(title), (128.0, 152.2)) == [], title
    for title in ("C5 Linen Throw", "Linen Throw J7"):
        assert _cert_unbound(_FactCir(title), (128.0, 152.2)), title
    # An x-led figure is a count, not a code.
    assert _cert_unbound(_FactCir("Ornament x2", makes=(1,)))


def test_every_allow_list_entry_is_tested():
    # S1F3-LOW (round 5) added percent, ply and number; each is tested in
    # tests/test_s1_product_truth_4.py (test_low_*_is_not_a_size).
    assert set(ST.ALLOWED_NON_SIZE) == {"n_in_1", "count", "colours", "grade", "code",
                                        "percent", "ply", "number"}, (
        "a new ALLOWED_NON_SIZE entry needs its own test here")
    for key, entry in ST.ALLOWED_NON_SIZE.items():
        assert entry.get("basis"), key


# ---- rebase onto w6-INTEG1: one size check ---------------------------------------------------


def test_one_object_size_check_after_the_integ1_rebase():
    import inspect

    src = inspect.getsource(C.certify)
    assert src.count("object_size_findings(cir, twin)") == 1, "two object-size gates"
    # A4a's dishcloth band is the table's own entry, unchanged.
    assert C.OBJECT_SIZE_BANDS["dishcloth"]["side_cm"] == (18.0, 28.0)
    # The plan runs the certificate's own size function on the size it would draft.
    assert "size_findings_for" in inspect.getsource(ST.drafted_refusal)
    assert "size_findings_for" in inspect.getsource(C.object_size_findings)
    # A4A-1 still holds through the one check.
    bad = C.object_size_findings(F._Cir("Linen Ridge Dishcloth"), F._Twin(38.4, 11.4))
    assert [f.code for f in bad] == ["OBJECT_SIZE_OUT_OF_BAND"], bad


def test_prior_fixed_cases_hold():
    for category, title, size in (("pillow", "Linen Lumbar Pillow 12 x 24", (30.5, 61.0)),
                                  ("blanket", "Linen Blanket 200 x 220", (200.0, 220.0)),
                                  ("pillow", "Linen Pillow Cover 26x26", (66.0, 66.0)),
                                  ("blanket", "Queen Linen Blanket", (229.0, 254.0))):
        _drafted_at(category, title, *size)
    _refused_at_draft("blanket", "King Size Ridge Throw", "king", "throw")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
