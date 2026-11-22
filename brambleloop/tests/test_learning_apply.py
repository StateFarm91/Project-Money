"""LEARNING-APPLY: benchmark lessons apply where they are relevant, and only there.

Production 2026-11-22 showed seo_search, pattern_engineering and creative_assets running their
hooks thousands of times with zero applications, and pricing never running at all. Each test
here pairs a relevant subject (the lesson must change the output and record an application)
with an irrelevant one (no application, never a run counted as one). Fixtures only: the
amigurumi CIR is the template test double, the catalogue CIRs are our own Launch-0 builders.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702  per-process temp sandbox
import dataclasses
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.learning import benchmark_lessons as B  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/apply.sqlite")
    db.create_all()
    B.reset_snapshot()
    return db


def _row(price, on_sale=False, effective=None):
    detail = {} if effective is None else {"effective_price_cad": effective}
    return SimpleNamespace(price_cad=price, on_sale=on_sale, detail=detail)


# ---- pricing (HC-L1) on the pricing department's own cadence --------------------------------

def test_pricing_anchor_reads_the_effective_price_of_an_on_sale_listing():
    db = _db()
    B.ingest(db)
    rows = [_row(10.0), _row(12.0, on_sale=True, effective=6.0), _row(9.0, on_sale=True)]
    prices = B.anchor_prices(db, rows, subject="price:x:pod")
    # The strike price 12.0 is replaced by 6.0; the on-sale row with no effective price is
    # left out (its listed price is a strike price, which research never reads).
    assert sorted(prices) == [6.0, 10.0], prices
    rb = B.readback(db)["departments"]["pricing"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["HC-L1"], rb
    assert rb["hook_runs"] == 1 and rb["relevant_runs"] == 1, rb
    B.reset_snapshot()


def test_pricing_anchor_with_no_sale_listing_runs_but_does_not_apply():
    db = _db()
    B.ingest(db)
    rows = [_row(10.0), _row(12.0)]
    assert B.anchor_prices(db, rows, subject="price:y:pod") == [10.0, 12.0]
    rb = B.readback(db)["departments"]["pricing"]
    assert rb["applied"] == 0 and rb["applications"] == 0 and rb["hook_runs"] == 1, rb
    assert rb["relevant_runs"] == 0 and "no relevant product" in rb["why_zero"], rb
    B.reset_snapshot()


def test_pricing_anchor_without_the_lesson_is_the_old_read():
    db = _db()                      # nothing ingested
    rows = [_row(10.0), _row(12.0, on_sale=True, effective=6.0)]
    assert B.anchor_prices(db, rows, subject="price:z:pod") == [10.0, 12.0]
    assert B.readback(db)["departments"]["pricing"]["applied"] == B.UNKNOWN


def test_the_pricing_job_runs_the_hook_on_its_own_cadence():
    """`release._outcome_price` (every pricing.decide job) runs HC-L1 over the benchmark
    catalogue it anchors on: no live SERP capture needed."""
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.runtime import release
    from brambleloop.seasonal.daily import DEPARTMENT_OF

    db = _db()
    B.ingest(db)
    category = next(c for c in DEPARTMENT_OF if DEPARTMENT_OF[c])
    pod = DEPARTMENT_OF[category]
    with db.session() as s:
        for i, (price, sale, eff) in enumerate([(8.0, False, None), (9.0, False, None),
                                                (10.0, False, None), (11.0, False, None),
                                                (30.0, True, 7.5), (40.0, True, None)]):
            s.add(BenchmarkListing(benchmark_key="t", listing_ref=f"r{i}", pod=pod,
                                   price_cad=price, on_sale=sale,
                                   detail={} if eff is None else {"effective_price_cad": eff}))
    seed = SimpleNamespace(slug="fixture-seed", maker_hours=(4.0, 6.0))
    ctx = SimpleNamespace(db=db)
    out = release._outcome_price(ctx, {"finished_size_cm": [30.0, 30.0]}, seed, category,
                                 (5.0, 15.0))
    rb = B.readback(db)["departments"]["pricing"]
    assert rb["hook_runs"] == 1 and rb["applied"] == 1, rb
    if out is not None:
        # five prices read (the 40.0 strike dropped, the 30.0 read at 7.5): a median of 9.0
        assert "observed median of 5" in out["anchor_basis"], out
    B.reset_snapshot()


def test_observation_keeps_the_effective_price_beside_the_listed_one():
    assert B.observed_effective_price({"sale_price": 6.0}, 10.0) == 6.0
    assert B.observed_effective_price({"sale_price": {"amount": 600, "divisor": 100}},
                                      10.0) == 6.0
    assert B.observed_effective_price({"sale_price": 12.0}, 10.0) is None   # not a discount
    assert B.observed_effective_price({}, 10.0) is None                      # absent: unknown


# ---- SEO (MM-L6) on the generator side ------------------------------------------------------

def _joined_amigurumi():
    import fixture_amigurumi as F

    sewn = F.pebble_friend()
    return dataclasses.replace(sewn, assembly=[dataclasses.replace(s, method="slst")
                                               for s in sewn.assembly])


def test_a_no_sew_amigurumi_earns_the_sew_modifier_tag_and_records_it():
    db = _db()
    B.ingest(db)
    cir = _joined_amigurumi()
    assert len(cir.components) > 1 and B.construction_sewing(cir)["no_sew"]
    earned = B.earned_sew_tags(cir)
    assert earned == ["no sew amigurumi", "low sew amigurumi"], earned
    assert B.note_sew_tags(cir, cir.slug, earned, ["amigurumi pattern", earned[0]])
    B.flush(db)
    rb = B.readback(db)["departments"]["seo_search"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["MM-L6"], rb
    B.reset_snapshot()


def test_a_sewn_amigurumi_and_a_catalogue_basket_earn_nothing():
    import fixture_amigurumi as F

    from brambleloop.products import launch0

    db = _db()
    B.ingest(db)
    sewn = F.pebble_friend()
    assert B.construction_sewing(sewn)["sewn"] >= 2
    assert B.earned_sew_tags(sewn) == []          # relevant (multi-piece toy), not earned
    basket = launch0.BUILDERS["basket_medium"]()
    assert B.earned_sew_tags(basket) == []        # a one-piece basket: irrelevant
    assert not B.note_sew_tags(sewn, sewn.slug, [], ["amigurumi pattern"])
    assert not B.note_sew_tags(basket, basket.slug, [], ["crochet basket"])
    B.flush(db)
    rb = B.readback(db)["departments"]["seo_search"]
    assert rb["applied"] == 0 and rb["hook_runs"] == 2 and rb["relevant_runs"] == 1, rb
    B.reset_snapshot()


def test_a_true_sew_claim_is_relevant_but_not_an_application():
    """The validator changes the listing only when it refuses a claim."""
    db = _db()
    B.ingest(db)
    cir = _joined_amigurumi()
    assert B.seo_check(cir, cir.slug, ["no sew amigurumi"]) == []
    B.flush(db)
    rb = B.readback(db)["departments"]["seo_search"]
    assert rb["applied"] == 0 and rb["relevant_runs"] == 1, rb
    assert "already satisfied" in rb["why_zero"], rb
    B.reset_snapshot()


# ---- pattern engineering: the real catalogue is not relevant, the amigurumi is ---------------

def _audit_lessons(cir):
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.twin import build_twin
    from brambleloop.publish import premium_standard as S

    result = compile_cir(cir)
    ctx = S.Context(cir=cir, twin=build_twin(cir, result), result=result, terminology="US", family=S.family_of(cir),
                    childrens=False, colourwork=False, multi_size=False,
                    lessons=frozenset(B.PDF_EFFECTS))
    S.audit_text("", ctx)


def test_pdf_lessons_apply_to_an_amigurumi_and_not_to_a_catalogue_blanket():
    import fixture_amigurumi as F

    from brambleloop.products import launch0

    db = _db()
    B.ingest(db)
    _audit_lessons(launch0.BUILDERS["cloudline_blanket"]())
    B.flush(db)
    rb = B.readback(db)["departments"]["pattern_engineering"]
    assert rb["applied"] == 0 and rb["hook_runs"] > 0, rb
    assert "no relevant product" in rb["why_zero"], rb
    _audit_lessons(F.pebble_friend())
    B.flush(db)
    rb = B.readback(db)["departments"]["pattern_engineering"]
    assert rb["applied"] >= 1 and "MM-L4" in rb["lessons_applied"], rb
    B.reset_snapshot()


def test_no_launch0_product_is_relevant_to_the_pattern_engineering_lessons():
    """The production zero is a true zero: record why, so a later amigurumi or chunky
    release is the thing that changes it."""
    from brambleloop.products import launch0
    from brambleloop.publish import premium_standard as S

    pe = {"eye_options_age", "hook_range_chunky", "chenille_care", "component_grouped",
          "join_as_you_go"}
    for key, build in launch0.BUILDERS.items():
        cir = build()
        ctx = S.Context(cir=cir, twin=None, result=None, terminology="US",
                        family=S.family_of(cir), childrens=False, colourwork=False,
                        multi_size=False, lessons=frozenset(B.PDF_EFFECTS))
        hit = {r.id for r in S.LESSON_RULES if r.required_for(ctx)} & pe
        assert not hit, (key, hit)


# ---- creative assets ------------------------------------------------------------------------

def test_hand_scale_applies_to_a_toy_campaign_and_not_to_a_blanket():
    db = _db()
    B.ingest(db)
    assert B.scale_brief("amigurumi", "base", subject="toy") == B.HAND_SCALE_BRIEF
    assert B.scale_brief("blanket", "base", subject="blanket") == "base"
    B.flush(db)
    rb = B.readback(db)["departments"]["creative_assets"]
    assert rb["applied"] == 1 and rb["lessons_applied"] == ["MM-L5"], rb
    assert rb["hook_runs"] == 2 and rb["relevant_runs"] == 1, rb
    B.reset_snapshot()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{'FAILED' if fails else 'PASSED'}: {fails} failing")
    sys.exit(1 if fails else 0)
