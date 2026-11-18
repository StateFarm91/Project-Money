"""S1 Product Truth, review of 2a858b59 (round 5): the code allow-list is exact, lettered
dimensions and bed-size compounds are size claims, the LOWs, and the proposals' whole-motif
counts fit their size.

* S1F3-H1: the `code` entry accepted any letter-led figure, so "Linen Scarf L300" (300 cm, out
  of the scarf band), "Runner L250 W40", "Pillow Cover W60 H60", "Throw H150 W200", "W50 L60",
  "d50" and "sz60" certified at the template size. The entry is now an exact, cited list (C2C
  and the Craft Yarn Council US hook sizes), and L / W / H / D / Sz + figure is a lettered
  dimension: bound as the stated dimensions it is, or refused.
* S1F3-M1: "Kingsize", "Queensize", "Superking", "Bedspread", "Coverlet", "Bassinet",
  "Picnic", "Travel" and "Grand" drafted at the 128 x 152 cm throw default. The compounds are
  normalised to their CYC class; the others are size claims with no cited band and are
  refused (a bed cover binds to a bed class it names: "Queen Coverlet").
* LOWs: "50 x 60 inches 2 in 1", "W130cm L170cm", '60ʺ', "100% Cotton", "4ply", "No. 5"
  were refused; a colour count was checked only at certify, so the plan drafted "3 Colour".
* Integration: the dishcloth and washcloth proposals compiled at 21.6 x 15.9 and 19.2 x 17.0
  cm, outside A4a's dishcloth band (18-28 cm a side, aspect <= 1.25). Their counts are now
  chosen to fit the proposal's size; the band is not loosened, and the check below uses the
  band's numbers literally so it holds with or without A4a's code on the tree.

Every case runs the real path: plan -> geometry -> builder -> compile -> twin -> certify.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_s1_product_truth_4.py
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
import test_s1_product_truth_3 as T  # noqa: E402

THROW = (128.0, 152.2)      # the throw template the fallback drafts


def _plan_refuses(category, title, *words):
    return T._refused_at_draft(category, title, *words)


def _certify_refuses(title, size, code="OBJECT_SIZE_UNBOUND"):
    codes = F._size_codes(F._Cir(title), F._Twin(*size))
    assert code in codes, (title, size, codes)


def _drafts_and_certifies(category, title, short, long_):
    return T._drafted_at(category, title, short, long_)


# ---- S1F3-H1: the code list is exact; lettered dimensions are size claims --------------------


def test_h1_lettered_dimensions_are_bound_or_refused():
    # Refused at plan, and at certify at the size the template would have drafted.
    for category, title, size, word in (
            ("scarf", "Linen Scarf L300", (19.2, 152.2), "l300"),
            ("scarf", "Linen Scarf L230", (19.2, 152.2), "l230"),
            ("blanket", "Throw H150 W200", THROW, "no unit"),
            ("blanket", "Linen Blanket W50 L60", THROW, "no unit"),
            ("blanket", "Linen Throw sz60", THROW, "sz60")):
        _plan_refuses(category, title, word)
        _certify_refuses(title, size)
    # A diameter is never bound: the fallback drafts no round piece.
    _certify_refuses("Linen Coaster d50", (10.0, 10.0))
    _certify_refuses("Linen Throw d50", THROW)
    # Bound when they can be: drafted at the stated size, and certified there.
    _drafts_and_certifies("runner", "Runner L250 W40", 40.0, 250.0)
    _drafts_and_certifies("pillow", "Pillow Cover W60 H60", 60.0, 60.0)
    _drafts_and_certifies("scarf", "Linen Scarf L180cm", 20.0, 180.0)
    # ... and a template that does not make the stated size is refused at certify.
    _certify_refuses("Runner L250 W40", (32.0, 120.7), "OBJECT_SIZE_NOT_AS_TITLED")
    _certify_refuses("Pillow Cover W60 H60", (41.6, 41.7), "OBJECT_SIZE_NOT_AS_TITLED")
    _certify_refuses("Linen Scarf L180cm", (19.2, 152.2), "OBJECT_SIZE_NOT_AS_TITLED")
    # Two widths, or two lengths, are not one size.
    _plan_refuses("blanket", "Linen Throw W130cm W150cm", "2 widths")


def test_h1_code_allow_list_is_exact_and_cited():
    entry = ST.ALLOWED_NON_SIZE["code"]
    assert "craftyarncouncil.com/standards/hooks" in entry["basis"], entry["basis"]
    for code in ("C2C", "B-1", "C-2", "D-3", "E-4", "F-5", "G-6", "H-8", "I-9", "J-10",
                 "K-10.5", "K-10 1/2", "L-11", "M-13", "N-13", "M/N-13", "N-15", "P-15",
                 "N/P-15", "H-8 Hook"):
        title = f"Linen Throw {code}"
        assert ST.plan_refusal("blanket", title) is None, title
        assert T._cert_unbound(T._FactCir(title), THROW) == [], title
    # The hook sizes are exact pairs: "L-11" is the 8 mm hook, "L-12" and "H-9" are not hooks,
    # and "C5", "J7", "v3" are not codes at all.
    for title in ("Linen Throw L-12", "Linen Throw H-9", "C5 Linen Throw", "Linen Throw J7",
                  "Linen Throw v3", "Linen Throw L11"):
        assert ST.plan_refusal("blanket", title), title
        assert T._cert_unbound(T._FactCir(title), THROW), title
    _drafts_and_certifies("blanket", "Linen Throw L-11", 128.0, 152.2)


# ---- S1F3-M1: bed-size compounds and bed / occasion size words -------------------------------


def test_m1_bed_size_compounds_bind_to_their_cyc_class():
    # "Kingsize" is the CYC king, "Queensize" the queen: drafted at the class default.
    _drafts_and_certifies("blanket", "Kingsize Linen Blanket", 254.0, 274.0)
    _drafts_and_certifies("blanket", "Queensize Linen Blanket", 229.0, 254.0)
    assert set(ST.claims("blanket", "Calking Linen Blanket")["classes"]) == {"king"}
    # ... and held to it at certify: the throw template is not a king blanket.
    _certify_refuses("Kingsize Linen Blanket", THROW, "OBJECT_SIZE_NOT_AS_TITLED")
    _certify_refuses("Queensize Linen Blanket", THROW, "OBJECT_SIZE_NOT_AS_TITLED")


def test_m1_bed_and_occasion_size_words_without_a_cited_band_are_refused():
    for title, word in (("Superking Linen Blanket", "superking"),
                        ("Super King Linen Blanket", "superking"),
                        ("Linen Bedspread", "bedspread"), ("Linen Coverlet", "coverlet"),
                        ("Bassinet Blanket", "bassinet"), ("Picnic Blanket", "picnic"),
                        ("Travel Blanket", "travel"), ("Grand Throw", "grand"),
                        ("Travel Pillow Cover", "travel")):
        category = "pillow" if "Pillow" in title else "blanket"
        _plan_refuses(category, title, f"unbound size token: {word}")
        _certify_refuses(title, THROW if category == "blanket" else (41.6, 41.7))
    # A bed cover that names its bed class binds to it.
    _drafts_and_certifies("blanket", "Queen Linen Coverlet", 229.0, 254.0)
    _certify_refuses("Queen Linen Coverlet", THROW, "OBJECT_SIZE_NOT_AS_TITLED")


# ---- LOWs: safe failures that cost sales -----------------------------------------------------


def test_low_inches_followed_by_a_figure_are_still_inches():
    assert ST.stated_dimensions("Linen Blanket 50 x 60 inches 2 in 1") == (127.0, 152.4)
    _drafts_and_certifies("blanket", "Linen Blanket 50 x 60 inches 2 in 1", 127.0, 152.4)
    # The bare "in" still refuses a following figure: "2 in 1" is never 2 inches.
    assert ST.stated_dimensions("Linen Throw 2 in 1") == ()


def test_low_lettered_dimensions_with_units_bind():
    _drafts_and_certifies("blanket", "Linen Blanket W130cm L170cm", 130.0, 170.0)
    _certify_refuses("Linen Blanket W130cm L170cm", THROW, "OBJECT_SIZE_NOT_AS_TITLED")


def test_low_modifier_letter_primes_are_inch_and_foot_marks():
    assert ST.stated_dimensions("Linen Table Runner 72ʺ") == (182.9,)
    assert ST.stated_dimensions("Linen Table Runner 6ʹ") == (182.9,)
    _drafts_and_certifies("runner", "Linen Table Runner 60ʺ", 35.0, 152.4)
    _drafts_and_certifies("blanket", "Linen Throw 50ʺ x 60ʺ", 127.0, 152.4)


def test_low_percent_is_not_a_size():
    for title in ("100% Cotton Linen Throw", "Linen Throw 50% Wool", "Linen Throw 100 % Cotton"):
        assert ST.plan_refusal("blanket", title) is None, title
        assert T._cert_unbound(T._FactCir(title), THROW) == [], title
    _drafts_and_certifies("blanket", "100% Cotton Linen Throw", 128.0, 152.2)
    # More than a whole is not fibre content.
    assert ST.plan_refusal("blanket", "150% Linen Throw")


def test_low_ply_is_not_a_size():
    for title in ("4ply Linen Throw", "8 ply Linen Throw", "Linen Throw 10-ply"):
        assert ST.plan_refusal("blanket", title) is None, title
        assert T._cert_unbound(T._FactCir(title), THROW) == [], title
    _drafts_and_certifies("blanket", "4ply Linen Throw", 128.0, 152.2)
    assert "yarn-weight-system" in ST.ALLOWED_NON_SIZE["ply"]["basis"]
    # Only the yarn-weight ply names: there is no 7 ply.
    assert ST.plan_refusal("blanket", "7ply Linen Throw")


def test_low_number_is_not_a_size():
    for title in ("Linen Throw No. 5", "Linen Throw No 12", "Linen Throw no.3"):
        assert ST.plan_refusal("blanket", title) is None, title
        assert T._cert_unbound(T._FactCir(title), THROW) == [], title
    _drafts_and_certifies("blanket", "Linen Throw No. 5", 128.0, 152.2)
    # A "no." followed by a unit is a dimension, not a design number: it is read (and held to
    # the size it states) before the allow-list runs.
    assert ST.stated_dimensions("Linen Table Runner No 72 in") == (182.9,)
    _drafts_and_certifies("runner", "Linen Table Runner No 72 in", 35.0, 182.9)
    _certify_refuses("Linen Table Runner No 72 in", (32.0, 120.7), "OBJECT_SIZE_NOT_AS_TITLED")


def test_low_colour_count_is_refused_at_plan_as_at_certify():
    assert ST.fallback_colour_counts() == frozenset({2})
    why = _plan_refuses("blanket", "3 Colour Linen Throw", "unbound size token: 3 colour")
    assert "2 colours" in why, why
    _plan_refuses("blanket", "Linen Throw Five Colours", "unbound size token: five colours")
    # The palette the fallback drafts has two colours: a two-colour title binds at plan.
    assert ST.plan_refusal("blanket", "Two-Colour Linen Throw") is None
    _drafts_and_certifies("blanket", "Two-Colour Linen Throw", 128.0, 152.2)
    # Plan and certify agree: the drafted throw has two colours, and certify refuses three.
    route, cir, twin = F._drafted("blanket", "Two-Colour Linen Throw")
    assert len(cir.colors) == 2, cir.colors
    assert T._cert_unbound(T._FactCir("3 Colour Linen Throw", colours=2), THROW)


# ---- Integration: the proposals' whole-motif counts fit their size --------------------------


DISHCLOTH_BAND = (18.0, 28.0)    # gates.certificate.OBJECT_SIZE_BANDS["dishcloth"], A4A-1
DISHCLOTH_MAX_ASPECT = 1.25


def test_integration_every_proposal_compiles_inside_its_size():
    from brambleloop.products import pipeline_board as pb

    made = {}
    for p in pb.PROPOSALS:
        cir = pb.proposal_cir(p)
        w, h = pb._measured(cir)
        made[p.slug] = (round(w, 1), round(h, 1))
        cert = C.certify(cir)
        size = [f.code for f in cert.findings if f.code.startswith("OBJECT_SIZE")
                or f.code.startswith("LISTING_SIZE")]
        assert size == [], (p.slug, made[p.slug], size)
        assert cert.granted, (p.slug, [str(f) for f in cert.findings][:3])
    # A dishcloth / washcloth is square-ish inside the dishcloth band, checked by its numbers
    # here so the check holds whether or not A4a's code is on the tree.
    for slug in ("diamond-lattice-dishcloth", "basketweave-textured-washcloth"):
        short, long_ = sorted(made[slug])
        lo, hi = DISHCLOTH_BAND
        assert lo <= short and long_ <= hi, (slug, made[slug])
        assert long_ / short <= DISHCLOTH_MAX_ASPECT, (slug, made[slug])
    assert made["diamond-lattice-dishcloth"] == (21.6, 23.8), made
    assert made["basketweave-textured-washcloth"] == (25.6, 25.7), made
    # The other proposals already met their size and keep their counts.
    assert made["chevron-relief-scarf"] == (19.2, 154.8), made
    assert made["heart-relief-table-runner"] == (32.0, 119.1), made
    assert made["pumpkin-relief-table-runner"] == (32.0, 116.4), made
    assert made["fir-star-relief-table-runner"] == (28.8, 112.9), made
    assert made["basketweave-textured-hand-towel"] == (32.0, 43.1), made


def test_integration_the_dishcloth_band_is_not_loosened():
    band = C.OBJECT_SIZE_BANDS.get("dishcloth")
    if band is not None:        # A4a's code (or S1's port of A4A-1) on the tree
        assert band["side_cm"] == DISHCLOTH_BAND and band["max_aspect"] == DISHCLOTH_MAX_ASPECT


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
