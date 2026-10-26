"""W4-AGENTS W7 (F-224): photographic principles from the judged benchmark galleries.

Only the closed shot vocabulary and gallery rank are read; a pod below the listing floor has no
principles; each Launch-0 shot plan is compared with its pod's principles as an advisory gap
list; no plan is changed and no competitor wording is carried.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_photo_principles.py
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
from brambleloop.core.models import (BenchmarkListing, BenchmarkObservation,  # noqa: E402
                                     OperatingReading, Phase)
from brambleloop.publish import eligibility as el  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402
from brambleloop.visual import photo_principles as PP  # noqa: E402
from brambleloop.visual import shot_plans  # noqa: E402

_N = [0]
_TMP = tempfile.mkdtemp(prefix="w4pp_")
SECRET = "Rival's lovely sunlit oak table with their exact wording"


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/p{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _gallery(db, ref, pod, shots):
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key="mjs", listing_ref=ref, pod=pod, title="t"))
        for rank, shot in enumerate(shots):
            s.add(BenchmarkObservation(
                benchmark_key="mjs", listing_ref=ref, kind="gallery_image_observation",
                detail={"image": {"rank": rank, "listing_ref": ref},
                        "observation": {"shot_type": shot, "setting": SECRET,
                                        "composition": SECRET}}))


def test_no_judged_gallery_means_no_principle():
    db = _db()
    out = PP.run(db)
    assert out["profile"]["judged_listings"] == 0 and out["profile"]["pods"] == {}
    assert out["gaps"] == 0
    assert out["plans"] and all(c["state"] == "UNKNOWN" for c in out["plans"].values())


def test_a_pod_below_the_floor_is_insufficient_not_a_principle():
    db = _db()
    for i in range(PP.MIN_LISTINGS - 1):
        _gallery(db, f"r{i}", "home_decor", ["hero_product_only", "detail_macro"])
    pod = PP.profile(db)["pods"]["home_decor"]
    assert pod["state"] == PP.INSUFFICIENT and pod["principles"] == []


def test_wide_shot_types_become_principles_and_missing_jobs_are_advisory_gaps():
    db = _db()
    for i in range(6):
        shots = ["hero_styled", "detail_macro", "in_use"] + (["packaging"] if i < 4 else [])
        _gallery(db, f"h{i}", "home_decor", shots)
    prof = PP.profile(db)
    pod = prof["pods"]["home_decor"]
    assert pod["state"] == "MEASURED" and pod["judged_listings"] == 6
    assert pod["first_image"] == {"hero_styled": 1.0}
    shots = {p["shot_type"]: p for p in pod["principles"]}
    assert set(shots) == {"hero_styled", "detail_macro", "in_use", "packaging"}
    assert shots["packaging"]["share"] == round(4 / 6, 3)
    # a home-decor Launch-0 plan compared against it
    plan = {"roles": [{"job": el.DESIRE}, {"job": el.DETAIL}, {"job": el.LIFESTYLE}]}
    cmp_ = PP.compare(plan, pod)
    assert cmp_["state"] == "COMPARED" and cmp_["advisory"] is True
    assert [g["shot_type"] for g in cmp_["gaps"]] == ["packaging"]
    assert {c["shot_type"] for c in cmp_["covered"]} == {"hero_styled", "detail_macro",
                                                         "in_use"}
    # nothing but the closed vocabulary and counts is carried
    assert SECRET not in repr(prof) and SECRET not in repr(PP.run(db))


def test_the_handler_stores_a_reading_and_changes_no_plan():
    db = _db()
    for i in range(5):
        _gallery(db, f"b{i}", "home_decor", ["hero_product_only", "scale_reference"])
    before = shot_plans.all_plans()["plans"]
    job = JobQueue(db).enqueue("creative_director", "creative.photo_principles", {})
    out = handlers.get("creative.photo_principles")(JobContext(
        job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    assert out["pods_measured"] == 1 and out["plans_changed"] == 0 and out["work_done"] == 1
    with db.session() as s:
        r = s.scalar(select(OperatingReading).where(OperatingReading.kind == PP.READING))
        assert r is not None and r.payload["profile"]["judged_listings"] == 5
        home = [c for c in r.payload["plans"].values() if c["pod"] == "home_decor"]
        assert home and all(c["state"] == "COMPARED" for c in home)
    assert shot_plans.all_plans()["plans"] == before
    assert ("photo_principles", "creative_director", "creative.photo_principles",
            86400) in CADENCES
    Registry(db).authorize("creative_director", "creative.photo_principles")


def test_every_judged_shot_type_maps_to_a_gallery_job():
    from brambleloop.intel.vision import SHOT_TYPES

    assert set(PP.JOB_OF_SHOT) == set(SHOT_TYPES)
    assert set(PP.JOB_OF_SHOT.values()) <= set(shot_plans.ORDER)


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
