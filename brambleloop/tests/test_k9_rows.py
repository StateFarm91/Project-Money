"""K9 (wave 4) continuation: the Product Truth rows the first pass left open.

Rows: F-779 listing conversion is not product truth (variant activation), F-784/F-795
similarity review incl. presentation, F-792 spec freeze before the instruction writer,
F-756 schematic cross-check, F-755 all-size parse, F-751 stitch semantics, F-753/F-754
region gauge and apparent stitch scale, F-363 children's physical plausibility.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from brambleloop.cir.model import CIR  # noqa: E402
from brambleloop.commerce import listing_tests as T  # noqa: E402
from brambleloop.growth.experiments import HOLDOUT, Experiment  # noqa: E402
from brambleloop.products import garments as G  # noqa: E402

_CACHE: dict = {}


def _graded(key: str | None = None, size: str | None = None) -> CIR:
    key = key or sorted(G.DESIGNS)[0]
    if key not in _CACHE:
        _CACHE[key] = G.DESIGNS[key]().build_all()
    fam = _CACHE[key]
    assert fam, key
    size = size or sorted(fam)[0]
    return CIR.from_dict(copy.deepcopy(fam[size].to_dict()))


# ---- F-779 -------------------------------------------------------------------------------

def _listing_test(variables=("title",)):
    plan = Experiment("v1", "a clearer title lifts click-through on ornament listings", "ctr", HOLDOUT, 0.05, 0.02,
                      200, date(2026, 11, 1))
    return T.ListingTest(key="v1", listing_ref="L1", plan=plan, variables=variables,
                         context=T.Context("ornaments", "under_6", "Christmas", "new"))


def test_a_listing_variant_may_not_distort_product_truth():
    cir = _graded()
    control = T.ListingVariant(
        test_key="v1", title=f"{cir.title} | Crochet Garment Pattern PDF",
        description="Written instructions with stitch counts for every row, worsted weight, "
                    "with charts. Intermediate.",
        tags=("crochet pattern", "sweater"), price_cad=9.0, thumbnail="frame-1.png")
    test = _listing_test()
    ok = T.activate_variant(test, T.ListingVariant(**{**control.__dict__,
                                                      "title": "Cosy Sweater Crochet Pattern PDF"}),
                            control=control, cir=cir)
    assert ok["activated"] and ok["changed"] == ["title"], ok
    bad_titles = {
        "Easy Beginner Sweater Pattern PDF": "difficulty",
        "Seamless Top-Down Sweater Pattern": "construction",
        "Bulky Sweater Crochet Pattern PDF": "materials",
        "Cable Sweater Crochet Pattern PDF": "stitch_appearance",
        "Sweater Crochet Kit, Yarn Included": "deliverables",
        "Oversized Fit Sweater Pattern PDF": "POLICY_FIT_CLAIM",
        "Sweater Pattern in 9 Sizes PDF": "POLICY_SIZE_COVERAGE",
        "Machine Washable Sweater Pattern": "POLICY_CLAIM_UNTRACEABLE",
    }
    assert bad_titles
    for title, why in bad_titles.items():
        out = T.activate_variant(test, T.ListingVariant(**{**control.__dict__, "title": title}),
                                 control=control, cir=cir)
        assert not out["activated"] and any(why in p for p in out["problems"]), (title, out)
    # A change the test did not declare, an uncertified thumbnail and a missing CIR refuse.
    out = T.activate_variant(test, T.ListingVariant(**{**control.__dict__, "price_cad": 7.0}),
                             control=control, cir=cir)
    assert any("VARIANT_UNDECLARED_CHANGE" in p for p in out["problems"]), out
    thumb = _listing_test(("thumbnail",))
    out = T.activate_variant(thumb, T.ListingVariant(**{**control.__dict__,
                                                        "thumbnail": "seller-photo.png"}),
                             control=control, cir=cir, certified_assets={"frame-1.png",
                                                                         "frame-2.png"})
    assert any("VARIANT_IMAGE_UNCERTIFIED" in p for p in out["problems"]), out
    out = T.activate_variant(thumb, T.ListingVariant(**{**control.__dict__,
                                                        "thumbnail": "frame-2.png"}),
                             control=control, cir=cir, certified_assets={"frame-1.png",
                                                                         "frame-2.png"})
    assert out["activated"], out
    out = T.activate_variant(test, control, control=control, cir=None)
    assert any("VARIANT_NO_PRODUCT_TRUTH" in p for p in out["problems"]), out


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
