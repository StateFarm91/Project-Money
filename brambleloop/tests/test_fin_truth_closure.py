"""Final Build closure, FIN worker: F-321/F-324/F-325/F-329, F-186, F-188, F-189.

* F-321/F-324/F-325/F-329 -- a *runtime* spend path (a queued job run by the real `Worker`,
  calling the real `ModelGateway` and a real vision judge with fake providers) writes cost rows
  and a reservation tagged with the job's product; shared spend stays untagged and labelled
  `shared`; with that attribution the sustainability forecast becomes computable.
* F-324 -- a product with no tagged creation cost has break-even UNKNOWN, never 0 sales.
* F-186 -- the dashboard's gauge-standard criterion is read from the stored certificate.
* F-188 -- the creative audit names its cohort and the tournament cohort is a separate row.
* F-189 -- weekly growth, the capacity reading and reinvestment consume MEASURED/UNMEASURED,
  never the modelled bound.

No network, no model calls, no secrets: every provider here is a local fake.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_fin_truth_closure.py
"""
from __future__ import annotations

import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="fin_truth_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the FIN closure harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Listing, ListingAsset,  # noqa: E402
                                     PatternVersion, Product, SpendReservation)
from brambleloop.finance import spend_report, sustainability  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402

NOW = datetime.now(timezone.utc)
SLUG = "fin-test-blanket"
_n = [0]


def _db():
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/fin{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _product(db, slug=SLUG):
    with db.session() as s:
        s.add(Product(slug=slug, title="Fin test blanket"))


class _TextProvider:
    """A fake priced model: the transport is local, the tokens and the price are real rows."""
    name = "fake-text"
    model = "claude-opus-5"
    cost_per_1k_input_cad = 0.01
    cost_per_1k_output_cad = 0.02

    def complete(self, system, user, *, max_tokens):
        from brambleloop.gateway.model_gateway import ModelResponse
        return ModelResponse(text='{"pick": "A", "reason": "warmer"}', provider=self.name,
                             model=self.model, input_tokens=1000, output_tokens=100,
                             latency_ms=1.0)


class _VisionProvider(_TextProvider):
    name = "fake-vision"

    def see(self, system, prompt, image_urls, *, max_tokens):
        from brambleloop.gateway.model_gateway import ModelResponse
        return ModelResponse(text='{"notes": ""}', provider=self.name, model=self.model,
                             input_tokens=1500, output_tokens=50, latency_ms=1.0)


def _run_job(db, inputs: dict) -> int:
    """Queue a job and run it through the real Worker with a handler that spends."""
    from brambleloop.gateway.model_gateway import ModelGateway
    from brambleloop.runtime.worker import HandlerRegistry, Worker
    from brambleloop.visual import photoreal

    registry = HandlerRegistry()

    @registry.register("cir.twin")
    def _spends(ctx):
        gateway = ModelGateway([_TextProvider()], registry=ctx.registry, job_id=ctx.job.id)
        gateway.complete_json("creative.blinded_appeal@1", agent="validator",
                              values={"option_a": {}, "option_b": {}},
                              required=("pick", "reason"))
        photoreal.judge("https://example.invalid/frame.png", db=ctx.db,
                        provider=_VisionProvider())
        return {"spent": gateway.spend_cad()}

    job = JobQueue(db).enqueue("validator", "cir.twin", inputs)
    worker = Worker(db, "fin-worker", registry=registry)
    assert worker.run_once() is True
    return job.id


def _cost_rows(db):
    with db.session() as s:
        return [(c.product_slug, c.purpose, dict(c.detail or {}))
                for c in s.scalars(select(CostEntry).order_by(CostEntry.id))]


def _reservations(db):
    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(select(SpendReservation))]


# ---------------------------------------------------------------------------
# F-321 / F-324 / F-325 / F-329: runtime attribution


def test_a_product_job_writes_cost_rows_and_reservations_tagged_with_its_product():
    db = _db()
    _product(db)
    _run_job(db, {"slug": SLUG})
    rows = _cost_rows(db)
    assert len(rows) >= 2, rows                      # gateway row + vision judge row
    purposes = {p for _s, p, _d in rows}
    assert "creative.blinded_appeal@1" in purposes and "asset_inspection" in purposes
    for slug, purpose, detail in rows:
        assert slug == SLUG, (purpose, slug)
        assert detail["attribution"] == "product", (purpose, detail)
    held = _reservations(db)
    assert held and all(d.get("product_slug") == SLUG for d in held), held
    # The tagged rows are this product's creation cost now, not platform spend.
    split = sustainability.split_costs(db)
    assert split["creation"].get(SLUG, 0.0) > 0 and split["platform"] == 0.0


def test_spend_outside_a_product_job_stays_untagged_and_labelled_shared():
    db = _db()
    _run_job(db, {})                                  # no slug: shared work
    _run_job(db, {"slug": "not-a-product"})           # a slug the catalogue does not know
    rows = _cost_rows(db)
    assert rows
    for slug, purpose, detail in rows:
        assert slug == "" and detail["attribution"] == "shared", (purpose, slug, detail)


def test_explicitly_shared_spend_is_not_charged_to_the_running_product():
    db = _db()
    with spend_report.attributed_to(SLUG):
        spend_report.record(db, agent="gateway", amount_cad=0.01, purpose="model.probe",
                            detail={"attribution": "shared"})
        spend_report.record(db, agent="gateway", amount_cad=0.02, purpose="x.render")
    spend_report.record(db, agent="gateway", amount_cad=0.03, purpose="radar")
    got = {p: (s, d["attribution"]) for s, p, d in _cost_rows(db)}
    assert got == {"model.probe": ("", "shared"), "x.render": (SLUG, "product"),
                   "radar": ("", "shared")}


def test_with_runtime_attribution_the_forecast_becomes_computable():
    db = _db()
    _product(db)
    # The product's creation spend, written by the runtime path, not by a fixture.
    _run_job(db, {"slug": SLUG})
    assert sustainability.forecast(db, now=NOW)["status"] == "INSUFFICIENT_DATA"
    # Platform history: shared cadence spend over thirty days.
    for d in range(1, 31):
        spend_report.record(db, agent="market_radar", amount_cad=0.01, purpose="radar")
    with db.session() as s:
        rows = list(s.scalars(select(CostEntry).where(CostEntry.purpose == "radar")
                              .order_by(CostEntry.id)))
        for i, c in enumerate(rows):
            c.at = NOW - timedelta(days=i + 1)
        s.add(Listing(product_slug=SLUG, version="1.0.0", title="B", description="",
                      price_cad=12.0, state="draft", etsy_listing_id=None,
                      created_at=NOW))
    f = sustainability.forecast(db, now=NOW)
    assert f["status"] == "computed", f.get("missing")
    assert f["measured"]["creation_cost_per_product_cad"] > 0
    assert f["scenarios"]["base"]["components_cad"]["creation"] > 0
    v = sustainability.verdict(db, now=NOW)
    assert v["status"] == "computed" and isinstance(v["sustainable"], bool)


# ---------------------------------------------------------------------------
# F-324: no tagged creation cost is UNKNOWN, not zero


def test_break_even_with_no_tagged_creation_cost_is_unknown_not_zero():
    db = _db()
    with db.session() as s:
        s.add(Listing(product_slug="priced-only", version="1.0.0", title="B",
                      description="", price_cad=12.0, state="draft", created_at=NOW))
    row = sustainability.break_even(db)["products"]["priced-only"]
    assert row["break_even_sales"] is None, row
    assert row["recovered"] is None and row["reading"] == "UNKNOWN"
    assert row["creation_cost_cad"] is None and row["creation_cost_reading"] == "UNKNOWN"
    assert "unknown (not zero)" in row["why"]


def test_break_even_with_tagged_creation_cost_is_still_computed():
    db = _db()
    with db.session() as s:
        s.add(CostEntry(agent="gateway", kind="llm", amount_cad=3.0, product_slug="p",
                        at=NOW - timedelta(days=3), purpose="creation"))
        s.add(Listing(product_slug="p", version="1.0.0", title="B", description="",
                      price_cad=12.0, state="draft", created_at=NOW))
    row = sustainability.break_even(db)["products"]["p"]
    assert row["reading"] == "computed" and row["break_even_sales"] >= 1
    assert row["recovered"] is False


# ---------------------------------------------------------------------------
# F-186: the gauge standard is read from the certificate


def _certified(db, slug, certificate, *, version="1.0.0"):
    with db.session() as s:
        p = Product(slug=slug, title=slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json={},
                             certified=True, certificate=certificate))
        s.add(ListingAsset(product_slug=slug, version=version, position=0,
                           asset_class="hero", role="hero", sha256="a" * 64,
                           approved=True, blocked_reasons=[]))


def test_a_certified_launch0_product_with_the_current_gauge_standard_is_launch_cleared():
    from brambleloop.app import dashboard_truth
    from brambleloop.gates.certificate import GAUGE_STANDARD, certify
    from brambleloop.products import launch0

    cand = launch0.candidate("hexagon-coaster-set")
    cir = launch0.cir_for(cand.variants[0].build)
    cert = certify(cir).to_dict()
    assert cert["granted"] and cert["gauge_standard"] == GAUGE_STANDARD
    db = _db()
    _certified(db, cir.slug, cert)
    _certified(db, "legacy-throw", {"granted": True})       # predates the gauge check
    inv = dashboard_truth.launch_inventory(db, survivors=[cir.slug, "legacy-throw"])
    rows = {r["slug"]: r for r in inv["products"]}
    assert rows[cir.slug]["criteria"]["gauge_standard"] is True
    assert rows[cir.slug]["launch_cleared"] is True, rows[cir.slug]
    assert rows["legacy-throw"]["criteria"]["gauge_standard"] is False
    assert "gauge_standard" in rows["legacy-throw"]["failing"]
    assert "predates the check" in rows["legacy-throw"]["gauge_standard_why"]
    assert inv["launch_cleared"] == 1 and inv["cleared_slugs"] == [cir.slug]
    assert inv["unassessed_criteria"] == []


# ---------------------------------------------------------------------------
# F-188: cohorts


def test_the_creative_audit_names_its_cohort_and_the_tournament_is_separate():
    from brambleloop.app import dashboard_truth
    from brambleloop.creative import audit

    report = audit.audit_catalogue()
    cohort = report["cohort"]
    assert cohort["name"] == audit.LEGACY_COHORT
    assert cohort["generator_version"].startswith("builder@")
    assert cohort["n"] == report["products_audited"]

    db = _db()
    none = audit.tournament_cohort(db)
    assert none["state"] == "NO_RUNS" and none["survivors"] is None
    with db.session() as s:
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       artifact="christmas/home",
                       detail={"field": {"generated": 40},
                               "survivors": [{"key": "a"}, {"key": "b"}]}))
    t = audit.tournament_cohort(db)
    assert t["state"] == "MEASURED" and t["candidates"] == 40 and t["survivors"] == 2
    # Legacy failures are not the tournament's: the two readings never share a number.
    survivors = dashboard_truth.creative_survivors(db)
    assert survivors["cohort"]["name"] == audit.LEGACY_COHORT
    assert survivors["tournament_cohort"]["survivors"] == 2
    assert survivors["count"] == len(report["survivors"])
    kpi = dashboard_truth._tournament_kpi(survivors["tournament_cohort"])
    assert kpi["key"] == "tournament_cohort" and kpi["value"] == "2 / 40"
    assert kpi["evidence"]["source"] and kpi["why"]


# ---------------------------------------------------------------------------
# F-189: runtime consumers read MEASURED/UNMEASURED


def test_reinvestment_makes_no_recommendation_from_an_unmeasured_confidence():
    from brambleloop.finance import reinvestment

    db = _db()
    e = reinvestment.envelope(db, gross_cad=20_000.0)
    d = e.to_dict()
    assert d["confidence"] is None and d["confidence_state"] == "UNMEASURED"
    assert d["envelope_cad"] > 0 and d["recommended_cad"] == 0
    assert "UNMEASURED" in d["note"]


def test_the_weekly_growth_reading_carries_unmeasured_not_the_modelled_bound():
    from brambleloop.growth import weekly

    db = _db()
    reading = weekly.solve(db)
    c = reading["confidence"]
    assert c["state"] == "UNMEASURED" and c["probability"] is None, c
    assert c["display"].startswith("UNMEASURED")
    assert isinstance(c["modelled_bound"], float)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
