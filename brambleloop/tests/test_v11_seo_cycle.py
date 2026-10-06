"""Lane G: the continuous cycle (idempotent), the measurement hook and the provider contract.

`seo.jobs.run_cycle(db)` re-evaluates only when an input changes; `seo.status.summary(db)` is
UNKNOWN on an empty database and never raises; `seo.status.next_work(db)` returns the
documented item shape.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, run  # noqa: E402

from sqlalchemy import func, select

from brambleloop.seo import jobs, measure, status
from brambleloop.seo.models import SeoCycle, SeoKeywordEvidence, SeoProposal

CONTRACT = {"status", "as_of", "basis", "items", "sources"}


def _count(db, model, **where):
    with db.session() as s:
        q = select(func.count()).select_from(model)
        for k, v in where.items():
            q = q.where(getattr(model, k) == v)
        return s.scalar(q)


def test_summary_is_unknown_on_an_empty_db_and_never_raises():
    for db in (fresh_db(create=False), fresh_db()):
        out = status.summary(db)
        assert CONTRACT <= set(out), out.keys()
        assert out["status"] == "UNKNOWN" and out["basis"] == "unknown", out
        assert out["items"] == [] and out["as_of"] is None and out["reason"]
        json.dumps(out)
    assert status.summary(None)["status"] == "UNKNOWN"


def test_run_cycle_is_idempotent():
    db = fresh_db()
    first = jobs.run_cycle(db)
    assert first["changed"] and first["proposals_written"], first
    assert first["writes_to_etsy"] is False
    n_prop, n_ev, n_cyc = (_count(db, SeoProposal), _count(db, SeoKeywordEvidence),
                           _count(db, SeoCycle))
    second = jobs.run_cycle(db)
    assert second["changed"] is False, second
    assert second["proposals_written"] == [] and second["evidence_added"] == 0
    assert second["cycle_fingerprint"] == first["cycle_fingerprint"]
    assert (_count(db, SeoProposal), _count(db, SeoKeywordEvidence),
            _count(db, SeoCycle)) == (n_prop, n_ev, n_cyc)


def test_new_evidence_re_evaluates_and_supersedes():
    from brambleloop.core.models import InsightsSnapshot

    db = fresh_db()
    jobs.run_cycle(db)
    before = _count(db, SeoProposal, state="PROPOSED")
    assert before >= 3
    with db.session() as s:
        s.add(InsightsSnapshot(keyword="crochet basket", search_count=1200, listing_count=800,
                               observed_on=datetime(2026, 10, 1, tzinfo=timezone.utc),
                               recorded_by="owner"))
    again = jobs.run_cycle(db)
    assert again["changed"] and again["evidence_added"] == 2, again
    assert again["proposals_written"], again          # evidence fingerprint is an input
    assert _count(db, SeoProposal, state="PROPOSED") == before
    assert _count(db, SeoProposal, state="SUPERSEDED") == len(again["proposals_written"])
    with db.session() as s:
        ev = list(s.scalars(select(SeoKeywordEvidence).where(
            SeoKeywordEvidence.source == "marketplace_insights_owner_recorded")))
    assert ev and {e.basis for e in ev} == {"measured"}
    assert {e.use for e in ev} == {"demand", "proxy:competition"}
    assert jobs.run_cycle(db)["changed"] is False


def test_summary_after_a_cycle_is_degraded_modelled_and_honest():
    db = fresh_db()
    jobs.run_cycle(db)
    out = status.summary(db)
    json.dumps(out)
    assert CONTRACT <= set(out)
    assert out["status"] == "DEGRADED", out["reason"]       # categories are GATED(etsy_api)
    assert out["basis"] == "modelled" and out["as_of"]
    assert out["items"] and all(i["taxonomy_status"] == "GATED(etsy_api)" for i in out["items"])
    assert out["kpis"]["search_outcomes"]["value"] is None
    assert out["kpis"]["search_outcomes"]["status"] == "UNKNOWN"
    assert any("F-918" in g for g in out["guardrails"])


def test_next_work_contract():
    db = fresh_db()
    before = status.next_work(db)
    assert before and before[0]["key"] == "seo.run_cycle"
    jobs.run_cycle(db)
    after = status.next_work(db)
    assert after
    keys = {"key", "department", "title", "kind", "action", "priority", "gated_by", "why",
            "external_effect", "sources"}
    for w in after:
        assert keys <= set(w), w
        assert w["department"] == "seo" and w["external_effect"] is False
        assert w["kind"] in ("internal", "owner", "gated")
    assert "seo.run_cycle" not in {w["key"] for w in after}     # nothing new to ingest
    gated = {w["key"]: w for w in after if w["kind"] == "gated"}
    assert gated["seo.taxonomy_confirm"]["gated_by"] == "etsy_api"
    assert gated["seo.stats_export"]["gated_by"] == "live_listings"
    json.dumps(after)


def test_measurement_is_unknown_without_stats_and_honest_with_them():
    from brambleloop.core.models import Listing, ListingOutcome, OperatingReading

    db = fresh_db()
    out = measure.attribution(db, {"hexagon-coaster-set": ["hexagon coaster"]},
                              evidence_rows=[])
    assert out["status"] == "UNKNOWN"
    kw = out["per_slug"]["hexagon-coaster-set"]["keywords"]
    assert kw and kw[0]["status"] == "UNKNOWN" and "impressions" not in kw[0]
    with db.session() as s:
        s.add(Listing(product_slug="hexagon-coaster-set", version="1.0.0", title="t",
                      description="d", tags=["hexagon coaster"], etsy_listing_id="123"))
        s.add(ListingOutcome(product_slug="hexagon-coaster-set", period_start="2026-10-01",
                             period_end="2026-10-07", impressions=900, visits=45,
                             favourites=4, orders=2, source="test"))
        s.add(OperatingReading(kind="attribution.stats", period_key="2026-10-07", payload={
            "joined": {"terms": [{"term": "hexagon coaster", "impressions": 500,
                                  "visits": 40, "orders": 2, "revenue_cad": 8.0}]}}))
    jobs.run_cycle(db)
    out = measure.attribution(db, {"hexagon-coaster-set": ["hexagon coaster", "diy coaster"]})
    assert out["status"] == "MEASURED_PARTIAL"
    by = {k["term"]: k for k in out["per_slug"]["hexagon-coaster-set"]["keywords"]}
    assert by["hexagon coaster"]["status"] == "ATTRIBUTED"
    assert by["hexagon coaster"]["basis"] == "estimated"
    assert by["hexagon coaster"]["confidence"] == "low"          # 40 visits
    assert by["diy coaster"]["status"] == "UNKNOWN"
    lo = out["per_slug"]["hexagon-coaster-set"]["listing_outcome"]
    assert lo["basis"] == "measured" and lo["orders"] == 2


def test_a_bare_sqlalchemy_session_is_accepted():
    db = fresh_db()
    jobs.run_cycle(db)
    s = db.new_session()
    try:
        out = status.summary(s)
        assert out["status"] == "DEGRADED", out["reason"]
        assert status.next_work(s)
    finally:
        s.close()


def test_the_seo_cycle_handler_registers_and_runs():
    from types import SimpleNamespace

    from brambleloop.runtime.worker import handlers
    from brambleloop.seo import handler  # noqa: F401  (registers seo.cycle)

    fn = handlers.get("seo.cycle")
    assert fn is not None
    db = fresh_db()
    first = fn(SimpleNamespace(db=db))
    assert first["changed"] is True and first["writes_to_etsy"] is False
    assert fn(SimpleNamespace(db=db))["changed"] is False


if __name__ == "__main__":
    run(globals())
