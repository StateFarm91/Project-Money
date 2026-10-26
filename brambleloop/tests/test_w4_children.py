"""W4-AGENTS cluster C1: the priority baby & children's family (F-351, F-353, F-358, F-359,
F-365, F-366). Deterministic, own rows plus observed listings as counts only.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_children.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (BenchmarkListing, OperatingReading, PatternVersion,  # noqa: E402
                                     Phase, Product)
from brambleloop.creative import children as C  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4kids_")
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/k{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _observe(db, titles):
    with db.session() as s:
        for i, t in enumerate(titles):
            s.add(BenchmarkListing(benchmark_key="obs", listing_ref=str(i), title=t,
                                   pod="garments"))


def test_f353_core_categories_are_the_rows_list_and_gaps_are_named():
    assert {"baby_cardigan", "child_cardigan", "sweater", "jacket", "dress", "top_vest",
            "hooded", "matching_set", "bonnet_hat", "collar", "blanket", "seasonal_garment",
            "unisex"} == set(C.CORE_CATEGORIES)
    db = _db()
    before = C.coverage(db)
    _observe(db, ["Baby Cardigan Crochet Pattern", "Toddler Hooded Jacket Pattern"])
    after = C.coverage(db)
    got = {r["category"]: r for r in after["categories"]}
    assert got["baby_cardigan"]["observed_listings"] == 1
    assert got["hooded"]["observed_listings"] == 1 and got["jacket"]["observed_listings"] == 1
    assert len(after["gaps"]) < len(before["gaps"])
    assert all(g["item"] == "research" for g in after["gaps"])
    assert "Toddler Hooded" not in repr(after)          # counts only, no competitor text


def test_f358_style_segments_count_without_inferring_a_palette():
    db = _db()
    assert C.style_segments(db)["status"] == "UNMEASURED"
    _observe(db, ["Unisex Baby Sweater", "Girls Dress Pattern", "Vintage Baby Bonnet",
                  "Kitchen Towel"])
    seg = C.style_segments(db)
    assert seg["children_listings"] == 3 and seg["gender_neutral"] == 1
    assert seg["gendered"] == 1 and seg["style_terms"] == {"vintage": 1}
    assert "not inferred" in seg["palette"]


def test_f366_launch_mix_considers_children_alongside_the_other_four_segments():
    mix = C.launch_mix(_db())
    assert mix["segments_considered"] == list(C.SEGMENTS) and mix["children_considered"]
    assert mix["children_in_launch"] >= 1 and mix["ok"] is True
    assert sum(mix["launch0"].values()) >= 1


def _certify(db, slug, title):
    from brambleloop.runtime.pipeline import Concept, concept_to_cir

    cir = concept_to_cir(Concept(slug=slug, title=title, category="baby",
                                 stitch_repeat=[("sc", 2), ("dc", 2)], width_stitches=40,
                                 rows=8, colors={"A": "cream", "B": "sage"}))
    with db.session() as s:
        p = Product(slug=slug, title=title, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=cir.version, cir_json=cir.to_dict(),
                             certified=True, release_hash=slug))


def test_f365_baby_and_kids_collection_only_when_depth_justifies_it():
    db = _db()
    for i in range(C.BABY_KIDS_DEPTH - 1):
        _certify(db, f"kid-{i}", f"Baby Blanket {i}")
    assert C.architecture(db)["propose_collection"] is False
    _certify(db, "kid-last", "Baby Bonnet")
    arch = C.architecture(db)
    assert arch["propose_collection"] is True and arch["section"] == "Baby & Kids"
    assert sum(len(v) for v in arch["navigation"]["by_family"].values()) == C.BABY_KIDS_DEPTH
    from brambleloop.store_foundation import director

    rev = director.review(db)
    adv = next(r for r in rev["surfaces"] if r["surface"] == "baby_kids_collection")
    assert adv["status"] == "PROPOSED" and adv["actor"] == "ADVISORY"


def test_f351_portfolio_job_runs_daily_and_records_one_reading():
    assert ("children_portfolio", "market_radar", "intel.children_portfolio",
            86400) in CADENCES
    db = _db()
    job = JobQueue(db).enqueue("market_radar", "intel.children_portfolio", {})
    Registry(db).authorize("market_radar", "intel.children_portfolio")
    out = handlers.get("intel.children_portfolio")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    assert out["network_calls"] == 0 and out["children_in_launch"] >= 1
    with db.session() as s:
        row = s.scalar(select(OperatingReading).where(
            OperatingReading.kind == "intel.children_portfolio"))
    assert row.payload["priority_family"] == C.PRIORITY_FAMILY
    assert {"coverage", "style_segments", "launch_mix", "architecture",
            "sibling_sets"} <= set(row.payload)


def test_f367_children_competitive_study_is_counts_and_prices_by_aliased_shop():
    from brambleloop.runtime.intel_ops import benchmark_alias

    db = _db()
    rows = [("mjs_off_the_hook_designs", "Baby cardigan pattern with secret wording", 8.0, True),
            ("mjs_off_the_hook_designs", "Newborn baby cardigan raglan", 10.0, False),
            ("other_shop_name", "Baby cardigan easy", 0.0, False),
            ("other_shop_name", "Adult cardigan, not for children", 12.0, False)]
    with db.session() as s:
        for i, (bk, title, price, sale) in enumerate(rows):
            s.add(BenchmarkListing(benchmark_key=bk, listing_ref=f"cs{i}", title=title,
                                   price_cad=price, on_sale=sale, media_count=4 + i))
    study = C.competitive_study(db)
    cat = next(c for c in study["categories"] if c["category"] == "baby_cardigan")
    assert cat["listings"] == 3 and cat["shops"] == 2 and cat["status"] == "MEASURED"
    assert cat["price_median_cad"] == 9.0 and cat["price_min_cad"] == 8.0   # 0.0 unobserved
    assert cat["shops_with_a_family"] == 1 and cat["on_sale_share"] == round(1 / 3, 3)
    blob = repr(study)
    assert "secret wording" not in blob and "mjs_off_the_hook" not in blob
    assert "other_shop_name" not in blob and benchmark_alias("x").startswith("bm-")
    empty = next(c for c in study["categories"] if c["category"] == "collar")
    assert empty["status"] == C.UNMEASURED and empty["listings"] == 0
    assert "competitive_study" in C.portfolio(db)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
