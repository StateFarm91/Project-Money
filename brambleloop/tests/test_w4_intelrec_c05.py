"""W4-INTELREC C05 (Market Intelligence and the research agent): F-565 and F-231.

OFFLINE (fixtures; not production evidence).
* F-565: owner-recorded Marketplace Insights terms are scored from searches, competing
  listings, trend, Product Truth feasibility, policy eligibility, expected margin and catalogue
  fit, with the raw Etsy evidence kept apart from the derived score.
* F-231: the judged benchmark galleries are quantified into gallery grammar (image count,
  hero shot, close-up frequency, model-vs-product mix, sequence), closed vocabulary only.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_intelrec_c05.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import insights, insights_score as IS  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='c05-')}/c.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_f565_scores_keep_raw_evidence_apart_and_name_every_component():
    db = _db()
    insights.record(db, keyword="mosaic throw crochet pattern", search_count=900,
                    listing_count=300, trend_direction="up", recorded_by="owner (fixture)",
                    observed_on="2026-10-20")
    insights.record(db, keyword="storage basket crochet pattern", search_count=400,
                    listing_count=800, trend_direction="flat", recorded_by="owner (fixture)",
                    observed_on="2026-10-20")
    out = IS.scores(db)
    by = {r["keyword"]: r for r in out["keywords"]}
    throw = by["mosaic throw crochet pattern"]
    assert throw["raw"]["search_count"] == 900 and throw["raw"]["basis"] == insights.BASIS
    d = throw["derived"]
    assert d["demand_ratio"]["value"] == 3.0 and d["trend"]["value"] == 1.2
    assert d["feasibility"]["value"] is True and d["policy"]["value"] is True
    assert d["margin"]["value"] is not None and d["catalogue_fit"]["value"] is True
    assert d["score"]["value"] == 3.6 and d["score"]["status"] == "DERIVED"
    assert out["ranked"][0] == "mosaic throw crochet pattern"
    # raw is never altered by scoring
    assert set(throw["raw"]) >= {"search_count", "listing_count", "trend_direction",
                                 "recorded_by", "observed_on"}


def test_f565_ineligible_infeasible_and_unmeasured_terms_get_no_score():
    db = _db()
    insights.record(db, keyword="disney castle blanket", search_count=5000, listing_count=10,
                    trend_direction="up", recorded_by="owner (fixture)")
    insights.record(db, keyword="lattice triangle shawl", search_count=300, listing_count=100,
                    recorded_by="owner (fixture)")
    insights.record(db, keyword="harvest table runner", listing_count=40,
                    recorded_by="owner (fixture)")
    by = {r["keyword"]: r["derived"] for r in IS.scores(db)["keywords"]}
    assert by["disney castle blanket"]["score"]["status"] == "INELIGIBLE"
    assert "disney" in by["disney castle blanket"]["policy"]["protected_terms"]
    assert by["lattice triangle shawl"]["score"]["status"] == "INELIGIBLE"     # no geometry
    assert by["lattice triangle shawl"]["trend"]["value"] is None             # unknown trend
    runner = by["harvest table runner"]
    assert runner["score"]["value"] is None and runner["score"]["status"] == "UNKNOWN"
    assert runner["demand_ratio"]["value"] is None                             # never 0


def test_f565_reaches_the_market_intel_reading():
    from brambleloop.intel import market_intel

    db = _db()
    insights.record(db, keyword="mosaic throw crochet pattern", search_count=900,
                    listing_count=300, trend_direction="up", recorded_by="owner (fixture)")
    market_intel.refresh(db)
    payload = market_intel.latest(db)
    assert payload["insights_opportunities"]["ranked"] == ["mosaic throw crochet pattern"]


def _gallery(db, ref, pod, shots):
    from brambleloop.core.models import BenchmarkListing, BenchmarkObservation

    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs", listing_ref=ref, pod=pod, title="t"))
        for rank, shot in enumerate(shots):
            s.add(BenchmarkObservation(
                benchmark_key="mjs", listing_ref=ref, kind="gallery_image_observation",
                detail={"image": {"rank": rank}, "observation": {
                    "shot_type": shot, "setting": "their sunlit oak table, their words"}}))


def test_f231_gallery_grammar_is_quantified_from_the_closed_vocabulary_only():
    from brambleloop.intel import gallery_grammar as GG

    db = _db()
    for i in range(5):
        shots = ["hero_product_only", "detail_macro", "detail_macro", "scale_reference"]
        if i < 2:
            shots.append("full_fit")
        _gallery(db, f"g{i}", "garments", shots)
    for i in range(2):
        _gallery(db, f"h{i}", "hats", ["hero_styled"])
    g = GG.grammar(db)
    pod = g["pods"]["garments"]
    assert pod["state"] == "MEASURED" and pod["judged_listings"] == 5
    assert pod["image_count_median"] == 4 and pod["hero_composition"] == {"hero_product_only": 1.0}
    assert pod["product_only_hero_share"] == 1.0 and pod["model_shot_share"] == 0.4
    assert pod["first_close_up_position_median"] == 2
    assert 0 < pod["close_up_frequency"] < 0.5 and pod["within_listing_consistency"] < 1.0
    assert g["pods"]["hats"]["state"] == GG.INSUFFICIENT
    assert set(g["unmeasured"]) == {"lighting", "background_environment", "framing"}
    assert "sunlit oak" not in repr(g)


def test_f231_the_photo_principles_job_stores_the_grammar_reading():
    from sqlalchemy import select

    from brambleloop.core.models import OperatingReading, Phase
    from brambleloop.intel import gallery_grammar as GG
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.worker import JobContext, handlers

    db = _db()
    for i in range(5):
        _gallery(db, f"g{i}", "home_decor", ["hero_styled", "in_use"])
    job = JobQueue(db).enqueue("creative_director", "creative.photo_principles", {})
    handlers.get("creative.photo_principles")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    with db.session() as s:
        r = s.scalar(select(OperatingReading).where(OperatingReading.kind == GG.READING))
        assert r is not None and r.payload["pods"]["home_decor"]["state"] == "MEASURED"


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
