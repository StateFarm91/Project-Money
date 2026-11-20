"""Wave-4 lane SPEND, K5a: spend attribution and finance reporting.

F-319 spend-to-progress (cost per milestone / listing advanced), F-322 cost per usable gallery
includes judging (UNKNOWN never 0), F-325 observation cadence is its own forecast term.
No network; every figure is written to a temporary ledger.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_spend_attribution.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
from datetime import datetime, timedelta, timezone

from r2_autonomy_harness import boot, run_tests

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _cost(db, *, cad, slug="", purpose="gallery_observation", at=NOW, kind="llm"):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        s.add(CostEntry(at=at, agent="orchestrator", kind=kind, amount_cad=cad,
                        product_slug=slug, purpose=purpose, provider="anthropic"))


def _audit(db, action, artifact, at=NOW, detail=None):
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(at=at, actor="orchestrator", action=action, artifact=artifact,
                       detail=detail or {}))


# -- F-319 ------------------------------------------------------------------------------------

def test_spend_to_progress_divides_product_spend_by_new_milestones_and_names_waste():
    from brambleloop.finance import governor

    db = boot()
    # fern advanced twice in-window (one of them the listing); its old gate was reached earlier.
    _audit(db, "gate.certified", "fern", at=NOW - timedelta(days=60))
    _audit(db, "gate.certified", "fern", at=NOW - timedelta(days=2))   # repeat: not progress
    _audit(db, "listing.seo_drafted", "fern", at=NOW - timedelta(days=2))
    _audit(db, "listing.drafted", "fern", at=NOW - timedelta(days=1))
    _cost(db, cad=3.0, slug="fern", purpose="asset_inspection", at=NOW - timedelta(days=1))
    # moss spent and advanced nothing.
    _cost(db, cad=1.5, slug="moss", purpose="asset_inspection", at=NOW - timedelta(days=1))
    # shared spend is kept apart, never spread.
    _cost(db, cad=10.0, slug="", at=NOW - timedelta(days=1))
    out = governor.spend_to_progress(db, now=NOW)
    fern = out["products"]["fern"]
    assert fern["milestones_advanced"] == ["listing.drafted", "listing.seo_drafted"], fern
    assert fern["cad_per_milestone"] == 1.5 and fern["listing_advanced"] is True
    moss = out["products"]["moss"]
    assert moss["cad_per_milestone"] is None and moss["spent_without_progress"] is True
    assert out["spent_without_progress"] == ["moss"]
    assert out["shared_cad"] == 10.0 and out["attributed_cad"] == 4.5
    assert out["milestones_advanced"] == 2 and out["listings_advanced"] == 1
    assert out["cad_per_listing_advanced"] == 4.5 and out["cad_per_milestone_advanced"] == 2.25
    # consumer: the governor report (served by /api/governor) carries it.
    with db.session() as s:
        served = governor.report(s, now=NOW)["spend_to_progress"]
    assert served["cad_per_listing_advanced"] == 4.5, served
    print("   cad/listing", out["cad_per_listing_advanced"], "shared", out["shared_cad"])


def test_no_progress_is_no_ratio_rather_than_zero():
    from brambleloop.finance import governor

    db = boot()
    out = governor.spend_to_progress(db, now=NOW)
    assert out["cad_per_listing_advanced"] is None and out["cad_per_milestone_advanced"] is None
    assert out["products"] == {}


# -- F-322 ------------------------------------------------------------------------------------

def _attempt(spent, usable):
    return {"spent_cad": spent, "usable_as_listing_asset": usable, "floors": {"photoreal": (
        "pass" if usable else "fail")}}


def test_cost_per_usable_gallery_includes_judging_and_unknown_judging_is_a_floor():
    from brambleloop.visual import reliability

    known = reliability.assess([
        {"slug": "a", "attempts": [_attempt(1.0, True)], "judging_cad": 0.5},
        {"slug": "b", "attempts": [_attempt(1.0, True)], "judging_cad": 0.25}])
    assert known["render_spend_cad"] == 2.0 and known["judging_spend_cad"] == 0.75
    assert known["total_spend_cad"] == 2.75 and known["cad_per_usable_gallery"] == 1.375
    assert known["cad_per_usable_basis"] == "render + judging"
    assert known["judging_unknown_for"] == []

    partial = reliability.assess([
        {"slug": "a", "attempts": [_attempt(1.0, True)], "judging_cad": 0.5},
        {"slug": "b", "attempts": [_attempt(1.0, True)]}])          # judging not supplied
    assert partial["judging_unknown_for"] == ["b"], partial
    assert partial["cad_per_usable_basis"].startswith("FLOOR"), partial["cad_per_usable_basis"]


def test_judging_cost_is_read_from_the_ledger_and_unknown_without_a_sequence():
    from brambleloop.publish import model_photography
    from brambleloop.visual import reliability

    db = boot()
    assert reliability._judging_cad(db, "fern") is None, "no filed sequence is UNKNOWN, not 0"
    assert reliability._judging_cad(db, None) is None
    first = datetime.now(timezone.utc) - timedelta(hours=1)
    _audit(db, model_photography.ACTION, "fern", at=first,
           detail={"slug": "fern", "method_version": model_photography.METHOD_VERSION})
    assert reliability._judging_cad(db, "fern") == 0.0, "read and empty is a measured zero"
    _cost(db, cad=0.3, slug="fern", purpose="asset_inspection", at=first - timedelta(hours=1))
    _cost(db, cad=0.2, slug="fern", purpose="asset_inspection", at=first)
    _cost(db, cad=9.0, slug="fern", purpose="gallery_observation", at=first)  # not judging
    _cost(db, cad=7.0, slug="fern", purpose="asset_inspection", at=first - timedelta(days=2))
    assert reliability._judging_cad(db, "fern") == 0.5


# -- F-325 ------------------------------------------------------------------------------------

def test_observation_cadence_is_its_own_forecast_term_and_not_counted_twice():
    from brambleloop.finance import sustainability

    db = boot()
    for d in range(10):
        _cost(db, cad=0.2, purpose="gallery_observation", at=NOW - timedelta(days=d, hours=1))
        _cost(db, cad=1.0, purpose="platform_misc", at=NOW - timedelta(days=d, hours=2))
    out = sustainability.forecast(db, now=NOW)
    m = out["measured"]
    assert m["observation_monthly_cad"] > 0 and m["cost_per_observation_run_cad"] == 0.2, m
    assert m["observation_runs_per_day"] > 0
    # platform excludes observation rows: 10 x 1.0 over the window, nothing of the 0.2s.
    window = min(sustainability.WINDOW_DAYS, max(m["history_days"], 1))
    assert m["platform_monthly_cad"] == round(10.0 * 30.0 / window, 2), m
    assert m["observation_monthly_cad"] == round(2.0 * 30.0 / window, 2), m
    if out["status"] != "computed":
        floor = out["known_floor_monthly_cad"]
        assert floor == round(m["platform_monthly_cad"] + m["observation_monthly_cad"], 2)
    for name, sc in sustainability.SCENARIOS.items():
        assert "observation_factor" in sc, name


if __name__ == "__main__":
    run_tests(globals())
