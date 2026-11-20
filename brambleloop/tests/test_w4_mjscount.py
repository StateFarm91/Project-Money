"""W4-MJSCOUNT: one snapshot for the MJs counters, scan-health detail, gallery cost forecast.

Rows: F-191 (MJs Scan Consistency), F-192 (Scan Health Semantics), F-193 (Gallery Cost Forecast).
Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_mjscount.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_mjscount_")

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import BenchmarkListing, CostEntry  # noqa: E402
from brambleloop.intel import benchmarks, mission, vision  # noqa: E402

KEY = benchmarks.MJS_KEY
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _listing(s, ref, *, audited=True, pod="", urls=0, judged=(), failed=None, gallery=False):
    s.add(BenchmarkListing(
        benchmark_key=KEY, listing_ref=ref, pod=pod,
        audit_state="audited" if audited else "discovered",
        detail={"image_urls": [f"https://img.example/{ref}/{i}" for i in range(urls)],
                "gallery_ranks_judged": list(judged),
                "gallery_ranks_failed": failed or {}, "gallery_audited": gallery}))


def _seed(db, n_extra_unjudged: int = 0):
    with db.session() as s:
        _listing(s, "a", pod="blankets", urls=4, judged=(1, 2), gallery=True)
        _listing(s, "b", pod="", urls=3, failed={"1": vision.FAILED_ATTEMPTS})
        _listing(s, "c", audited=False, pod="toys", urls=5)
        for i in range(n_extra_unjudged):
            _listing(s, f"x{i}", pod="blankets", urls=3)


def test_every_counter_comes_from_one_snapshot_and_reconciles():
    db = _db()
    _seed(db)
    snap = mission.snapshot(db, KEY)
    assert snap["listings_known"] == 3 and snap["listings_audited"] == 2
    assert snap["gallery_audited"] == 1 and snap["unclassified"] == 1
    assert snap["images"] == {"unjudged": 4, "judged": 2, "given_up_on": 1, "image_slots": 7}
    assert snap["reconciliation"]["ok"] is True, snap["reconciliation"]
    assert len(snap["reconciliation"]["checks"]) == 5
    report = mission.mission_report(db, benchmark_key=KEY)
    assert report["catalogue_coverage"]["listings_known"] == snap["listings_known"]
    assert report["reconciliation"]["ok"] is True
    plan = vision.plan(db, KEY)
    assert plan["pending_images"] == snap["images"]["unjudged"]
    assert vision.pending_count(db, KEY) == {k: snap["images"][k]
                                             for k in ("unjudged", "judged", "given_up_on")}


def test_the_backlog_count_no_longer_saturates_at_a_page():
    """plan() counted len(pending(limit=200)); the snapshot counts the catalogue."""
    db = _db()
    _seed(db, n_extra_unjudged=80)  # 240 more unjudged images
    plan = vision.plan(db, KEY)
    assert plan["pending_images"] == 4 + 240, plan["pending_images"]
    assert len(vision.pending(db, KEY)) == 200  # the page is still a page


def test_a_broken_identity_is_reported_not_corrected():
    db = _db()
    _seed(db)
    real = vision.image_counts

    def skewed(rows):
        c = real(rows)
        return {**c, "image_slots": c["image_slots"] + 1}

    vision.image_counts = skewed
    try:
        snap = mission.snapshot(db, KEY)
    finally:
        vision.image_counts = real
    assert snap["reconciliation"]["ok"] is False
    assert snap["reconciliation"]["failing"] == ["image slots = judged + unjudged + given up"]


def test_forecast_is_measured_or_unknown_never_zero():
    db = _db()
    _seed(db)
    fc = vision.plan(db, KEY)["forecast"]
    assert fc["measured_cad_per_image"] is None and fc["measured_basis"].startswith("UNKNOWN")
    assert fc["cost_to_drain_basis"] == "estimated"
    assert fc["allocation"]["share_of_ceiling"] == 0.40
    with db.session() as s:
        s.add(CostEntry(agent=vision.AGENT, amount_cad=0.068, kind="llm", purpose=vision.TASK,
                        detail={}))
    fc = vision.plan(db, KEY)["forecast"]
    assert fc["measured_cad_per_image"] == 0.034  # CA$0.068 over 2 judged images
    assert fc["cost_to_drain_cad"] == round(4 * 0.034, 4) and fc["cost_to_drain_basis"] == "measured"
    assert fc["runs_per_day"] == 12.0  # the two-hourly gallery cadence
    if fc["images_per_day"]:
        assert fc["eta_days"] == round(4 / fc["images_per_day"], 1)
    else:
        assert fc["eta_days"] is None and fc["eta_basis"].startswith("UNKNOWN")


def test_dashboard_mission_shows_scan_health_detail_reconciliation_and_forecast():
    src = (ROOT / "src" / "brambleloop" / "app" / "main.py").read_text(encoding="utf-8")
    body = src[src.index("    def _mission() -> str:"):src.index("    def _seasonal() -> str:")]
    for needle in ('sh.get("problem")', 'sh.get("checked_at")', '"counts reconcile"',
                   '"gallery cost forecast"', "measured_cad_per_image"):
        assert needle in body, needle


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
