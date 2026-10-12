"""W4-SPENDA, Final Master cluster K5a: spend attribution and finance reporting.

F-304 per-operation attribution (listing, image count, observed actual, evidence), F-103/F-106
provider billing settlement (gated on an admin key; parsed and settled from fixtures here),
F-070 benchmark information value, F-319 spend-to-progress, F-322 judging inside cost per usable
gallery, F-325 observation cadence as a forecast term, F-629 credits kept apart from cash.
No network and no paid call: provider billing is read through an injected transport.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w4_spenda_k5a.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E401,E702

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from r2_autonomy_harness import boot, run_tests  # noqa: E402

NOW = datetime.now(timezone.utc)
NO_KEYS: dict = {}


def _listing(db, slug, etsy_id="", created=None):
    from brambleloop.core.models import Listing

    with db.session() as s:
        row = Listing(product_slug=slug, version="1.0.0", title="T", description="",
                      price_cad=9.0, state="draft", etsy_listing_id=etsy_id,
                      created_at=created or NOW - timedelta(days=3))
        s.add(row)
        s.flush()
        return row.id


def _attr(db, cost_id):
    from sqlalchemy import select

    from brambleloop.finance.cost_attribution import CostAttribution

    with db.session() as s:
        row = s.scalar(select(CostAttribution).where(CostAttribution.cost_entry_id == cost_id))
        s.expunge(row)
        return row


# -- F-304 ----------------------------------------------------------------------------------

def test_every_billed_row_carries_listing_images_observed_and_evidence_beside_it():
    from brambleloop.finance import cost_attribution as CA, spend_report

    db = boot()
    lid = _listing(db, "fern-throw", etsy_id="4401")
    img = spend_report.record(db, agent="gateway", amount_cad=0.0411, purpose="image.generate",
                              provider="openai_gpt_image", model="openai_gpt_image",
                              product_slug="fern-throw", kind="image",
                              detail={"reservation_id": 77})
    vis = spend_report.record(db, agent="quality", amount_cad=0.01, purpose="asset_inspection",
                              provider="anthropic", model="m", product_slug="fern-throw",
                              detail={"image": "frame-1.png"})
    txt = spend_report.record(db, agent="orchestrator", amount_cad=0.02, purpose="concept",
                              provider="anthropic", model="m", product_slug="ghost-product")
    shared = spend_report.record(db, agent="gateway", amount_cad=0.03, purpose="probe",
                                 provider="anthropic", model="m",
                                 detail={"attribution": "shared"})
    a = _attr(db, img)
    assert a.listing_id == lid and a.etsy_listing_id == "4401", a.__dict__
    assert a.listing_basis == CA.LISTING_RESOLVED
    assert a.image_count == 1 and a.unit == "image" and a.units == 1
    assert a.evidence_ref == "reservation:77"
    assert a.observed_cad is None, "a recorded estimate is never written as observed"
    v = _attr(db, vis)
    assert v.image_count == 1 and v.image_basis == CA.IMAGES_SENT and v.unit == "call"
    t = _attr(db, txt)
    assert t.listing_id is None and t.listing_basis == CA.LISTING_NONE_YET
    assert t.image_count is None and t.image_basis == CA.IMAGES_UNKNOWN, "UNKNOWN is never 0"
    assert _attr(db, shared).listing_basis == CA.LISTING_SHARED

    rep = spend_report.governance(db)["per_operation"]
    assert rep["reconciles"] is True, rep
    assert rep["by_listing"] and rep["by_listing"][0]["listing_id"] == lid
    assert rep["by_listing"][0]["images_rendered"] == 1
    assert rep["images_rendered"] == 1 and rep["cad_per_rendered_image"] == 0.0411
    assert rep["provider_observed"]["observed_cad"] is None
    assert rep["no_listing_yet_cad"] == 0.02 and rep["shared_cad"] == 0.03


def test_an_observed_cost_must_name_its_source_and_the_governor_reads_the_sidecar():
    from brambleloop.finance import governor, spend_report

    db = boot()
    try:
        spend_report.record(db, agent="a", amount_cad=0.1, purpose="p", observed_cad=0.12)
    except ValueError as exc:
        assert "source" in str(exc)
    else:
        raise AssertionError("an observed cost without a source was accepted")
    cid = spend_report.record(db, agent="a", amount_cad=0.1, purpose="p", observed_cad=0.12,
                              observed_basis="provider_invoice", evidence_ref="inv-1")
    a = _attr(db, cid)
    assert a.observed_cad == 0.12 and a.evidence_ref == "inv-1"
    with db.session() as s:          # /api/governor passes a session
        rep = governor.report(s)
    po = rep["per_operation"]
    assert po["provider_observed"]["rows"] == 1 and po["provider_observed"]["observed_cad"] == 0.12


# -- F-106 / F-103 -------------------------------------------------------------------------

ANTHROPIC_PAGE = {
    "data": [{"starting_at": (NOW - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
              "results": [{"currency": "USD", "amount": "73.00", "model": "claude-x"}]}],
    "has_more": False}


def test_provider_cost_reports_parse_in_cents_and_per_day():
    from brambleloop.ops import provider_accounts as P

    rows = P.parse_anthropic_cost_report(ANTHROPIC_PAGE)
    assert rows == [{"day": (NOW - timedelta(days=1)).date().isoformat(), "model": "claude-x",
                     "usd": 0.73}], rows
    oa = P.parse_openai_costs({"data": [{"start_time": int((NOW - timedelta(days=1)).timestamp()),
                                         "results": [{"amount": {"value": 1.5, "currency": "usd"},
                                                      "line_item": "Image models"}]}]})
    assert oa and oa[0]["model"] == "*" and oa[0]["usd"] == 1.5


def test_without_an_admin_key_billing_is_owner_gated_and_nothing_is_fetched():
    from brambleloop.ops import provider_accounts as P

    db = boot()
    called = []
    got = P.settle_all(db, env=NO_KEYS, transport=lambda *a: called.append(a) or {})
    assert set(got) == set(P.ADMIN_KEY_ENV) and not called
    for provider, v in got.items():
        assert v["state"] == "OWNER_GATED" and v["needs"] == P.ADMIN_KEY_ENV[provider]
    rec = P.reconcile(db)
    assert set(rec["provider_billing"]) == set(P.ADMIN_KEY_ENV)
    assert isinstance(rec["reported_vs_ledger"], list) and rec["reported_vs_ledger"]


def test_settlement_against_the_provider_bill_writes_observed_and_opens_an_incident():
    from sqlalchemy import select

    from brambleloop.core.models import CostEntry, Incident
    from brambleloop.finance import spend_report
    from brambleloop.gateway.routing import USD_PER_CAD
    from brambleloop.ops import provider_accounts as P

    db = boot()
    cid = spend_report.record(db, agent="a", amount_cad=0.20, purpose="p",
                              provider="anthropic", model="claude-x")
    with db.session() as s:
        s.get(CostEntry, cid).at = NOW - timedelta(days=1)
    seen = []

    def transport(url, headers):
        seen.append(url)
        assert "cost_report" in url and headers.get("x-api-key")
        return ANTHROPIC_PAGE

    got = P.settle_all(db, env={"ANTHROPIC_ADMIN_KEY": "fixture"}, transport=transport, now=NOW)
    assert seen and got["anthropic"]["state"] == "SETTLED", got
    assert got["openai"]["state"] == "OWNER_GATED"
    provider_cad = round(0.73 / USD_PER_CAD, 6)
    a = _attr(db, cid)
    assert a.observed_cad == provider_cad and a.observed_basis == P.OBSERVED_BASIS
    assert got["anthropic"]["material_gaps"] == 1 and got["anthropic"]["incident"] == "opened"
    with db.session() as s:
        inc = list(s.scalars(select(Incident).where(
            Incident.signature.like(f"{P.SETTLEMENT_SIGNATURE}%"))))
    assert inc and inc[0].severity == "P2"
    # the recorded amount is left as recorded: observed sits beside it, never over it
    with db.session() as s:
        assert s.get(CostEntry, cid).amount_cad == 0.2
        assert s.get(CostEntry, cid).observed_cad == provider_cad
    last = P.last_settlements(db)["anthropic"]
    assert last["state"] == "SETTLED" and last["material_gaps"] == 1


def test_a_bucket_of_several_calls_is_settled_without_inventing_per_call_actuals():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import spend_report
    from brambleloop.gateway.routing import USD_PER_CAD
    from brambleloop.ops import provider_accounts as P

    db = boot()
    half = round(0.73 / USD_PER_CAD / 2, 6)
    ids = [spend_report.record(db, agent="a", amount_cad=half, purpose="p",
                               provider="anthropic", model="claude-x") for _ in range(2)]
    with db.session() as s:
        for i in ids:
            s.get(CostEntry, i).at = NOW - timedelta(days=1)
    rows = P.parse_anthropic_cost_report(ANTHROPIC_PAGE)
    got = P.settle(db, "anthropic", rows, now=NOW)
    b = got["buckets"][0]
    assert b["ledger_rows"] == 2 and b["per_call_observed_written"] is False
    assert all(_attr(db, i).observed_cad is None for i in ids)
    assert b["material"] is False and abs(b["difference_cad"]) < 1e-5, b
    assert got["incident"] is None


def test_the_governor_pass_records_the_settlement_state():
    from brambleloop.finance import governor

    db = boot()
    got = governor.enforce(db, now=NOW)
    ps = got["provider_settlement"]
    assert ps and all(v["state"] in ("OWNER_GATED", "SETTLED", "UNREADABLE")
                      for v in ps.values()), ps
    assert got["ceilings_changed"] == 0


# -- F-070 ----------------------------------------------------------------------------------

def test_each_purchased_benchmark_reports_what_it_taught_and_unknown_price_is_not_zero():
    from brambleloop.core.models import BenchmarkProduct, Improvement, TeardownFinding
    from brambleloop.intel import purchase_selection as PS

    db = boot()
    empty = PS.information_value(db)
    assert empty["purchased"] == 0 and empty["why_empty"]
    with db.session() as s:
        s.add(BenchmarkProduct(ref="b1", seller="x", title="One", paid_cad=8.0,
                               purchased_on="2026-10-01", teardown_state="audited"))
        s.add(BenchmarkProduct(ref="b2", seller="x", title="Two", paid_cad=0.0,
                               teardown_state="audited"))
        f1 = TeardownFinding(benchmark_ref="b1", dimension="structure", score=4,
                             promoted=True, detail={"adopted": {"floor": 3}})
        f2 = TeardownFinding(benchmark_ref="b1", dimension="sizing", score=2)
        s.add_all([f1, f2])
        s.flush()
        s.add(Improvement(cell="c", metric="m", hypothesis="h", state="promoted",
                          rollback_ref=f"teardown-finding:{f1.id}"))
    got = PS.information_value(db)
    by = {b["ref"]: b for b in got["benchmarks"]}
    assert set(by) == {"b1", "b2"}
    b1 = by["b1"]
    assert b1["findings"] == 2 and b1["findings_promoted"] == 1 and b1["floors_adopted"] == 1
    assert b1["improvements_created"] == 1 and b1["improvements_promoted"] == 1
    assert b1["cad_per_finding"] == 4.0 and b1["cad_per_improvement_promoted"] == 8.0
    b2 = by["b2"]
    assert b2["paid_cad"] is None and b2["paid_basis"] == "UNKNOWN" and b2["cad_per_finding"] is None
    assert got["taught_nothing_yet"] == ["b2"] and got["paid_unknown_for"] == ["b2"]
    assert got["cad_per_finding"] is None, "no set ratio while a price is unknown"


def test_the_selection_the_owner_reads_carries_the_post_purchase_value():
    from brambleloop.intel import purchase_selection as PS

    db = boot()
    pool = [PS.Candidate(listing_ref=f"L{i}", title=f"t{i}", pod="p", price_cad=5.0 + i,
                         media_count=3, seasonal="", url="",
                         facets={f: f"{f}{i}" for f in PS.FACETS}) for i in range(3)]
    real = PS.candidates
    PS.candidates = lambda *a, **k: pool
    try:
        out = PS.select(db, "mjs", target=2, budget_cad=300.0)
    finally:
        PS.candidates = real
    assert out["selected_count"] == 2 and out["within_budget"]
    assert out["post_purchase_information_value"]["purchased"] == 0


# -- F-319 ----------------------------------------------------------------------------------

def test_spend_to_progress_names_cost_per_milestone_and_spend_that_advanced_nothing():
    from brambleloop.core.models import AuditLog, CostEntry
    from brambleloop.finance import governor

    db = boot()
    with db.session() as s:
        s.add_all([CostEntry(agent="a", amount_cad=4.0, product_slug="fern", purpose="p",
                             at=NOW - timedelta(days=2)),
                   CostEntry(agent="a", amount_cad=3.0, product_slug="stuck", purpose="p",
                             at=NOW - timedelta(days=2)),
                   CostEntry(agent="a", amount_cad=1.0, product_slug="", purpose="p",
                             at=NOW - timedelta(days=2)),
                   AuditLog(actor="x", action="gate.certified", artifact="fern",
                            at=NOW - timedelta(days=1)),
                   AuditLog(actor="x", action="listing.drafted", artifact="fern",
                            at=NOW - timedelta(days=1)),
                   AuditLog(actor="x", action="gate.certified", artifact="stuck",
                            at=NOW - timedelta(days=90)),
                   AuditLog(actor="x", action="gate.certified", artifact="stuck",
                            at=NOW - timedelta(days=1))])
    got = governor.spend_to_progress(db, now=NOW)
    assert got["products"]["fern"]["cad_per_milestone"] == 2.0
    assert got["products"]["fern"]["listing_advanced"] is True
    assert got["cad_per_listing_advanced"] == 7.0
    assert got["spent_without_progress"] == ["stuck"], "re-reaching a milestone is not progress"
    assert got["shared_cad"] == 1.0
    with db.session() as s:
        assert governor.report(s, now=NOW)["spend_to_progress"]["listings_advanced"] == 1


# -- F-322 ----------------------------------------------------------------------------------

def test_cost_per_usable_gallery_includes_judging_and_unknown_judging_is_a_floor():
    from brambleloop.visual import reliability

    def gallery(slug, judging):
        g = {"slug": slug, "attempts": [{"spent_cad": 0.5, "usable_as_listing_asset": True,
                                         "failed_dimensions": [], "dimensions_asked": []}]}
        if judging is not None:
            g["judging_cad"] = judging
        return g

    known = reliability.assess([gallery("a", 0.25)])
    assert known["render_spend_cad"] == 0.5 and known["judging_spend_cad"] == 0.25
    assert known["total_spend_cad"] == 0.75 and known["cad_per_usable_gallery"] == 0.75
    assert known["cad_per_usable_basis"] == "render + judging"
    floor = reliability.assess([gallery("b", None)])
    assert floor["judging_unknown_for"] == ["b"] and floor["cad_per_usable_basis"].startswith("FLOOR")


def test_judging_cost_is_read_from_the_ledger_and_unknown_without_a_sequence():
    from brambleloop.core.models import AuditLog, CostEntry
    from brambleloop.publish import model_photography
    from brambleloop.visual import reliability

    db = boot()
    assert reliability._judging_cad(db, "fern") is None
    with db.session() as s:
        s.add(AuditLog(actor="x", action=model_photography.ACTION, artifact="fern",
                       at=NOW - timedelta(hours=1),
                       detail={"slug": "fern",
                               "method_version": model_photography.METHOD_VERSION}))
        s.add(CostEntry(agent="q", amount_cad=0.3, product_slug="fern",
                        purpose="asset_inspection", at=NOW - timedelta(hours=2)))
        s.add(CostEntry(agent="q", amount_cad=9.0, product_slug="fern",
                        purpose="asset_inspection", at=NOW - timedelta(days=3)))
    assert reliability._judging_cad(db, "fern") == 0.3


# -- F-325 ----------------------------------------------------------------------------------

def test_observation_cadence_is_its_own_forecast_term_and_not_counted_twice():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import sustainability

    db = boot()
    _listing(db, "cloud", etsy_id="222", created=NOW - timedelta(days=20))
    with db.session() as s:
        for d in range(1, 31):
            s.add(CostEntry(agent="g", kind="llm", amount_cad=0.02, purpose="gallery_observation",
                            at=NOW - timedelta(days=d)))
            s.add(CostEntry(agent="g", kind="llm", amount_cad=0.01, purpose="radar",
                            at=NOW - timedelta(days=d)))
        s.add(CostEntry(agent="g", kind="llm", amount_cad=3.0, product_slug="cloud",
                        purpose="creation", at=NOW - timedelta(days=40)))
        s.add(CostEntry(agent="g", kind="llm", amount_cad=0.3, product_slug="cloud",
                        purpose="revalidation", at=NOW - timedelta(days=5)))
    f = sustainability.forecast(db, now=NOW)
    m = f["measured"]
    assert m["observation_runs_per_day"] > 0 and m["cost_per_observation_run_cad"] == 0.02, m
    assert abs(m["platform_monthly_cad"] - 0.3) < 0.02, m   # radar only: observation split out
    if f["status"] == "computed":
        base = f["scenarios"]["base"]["components_cad"]
        assert base["observation"] > 0 and abs(base["observation"] - 0.6) < 0.05, base
        low, high = (f["scenarios"][k]["components_cad"]["observation"] for k in ("low", "high"))
        assert low < base["observation"] < high
    else:
        assert f["known_floor_monthly_cad"] >= m["observation_monthly_cad"]


# -- F-629 ----------------------------------------------------------------------------------

def test_credits_are_kept_apart_from_cash_and_never_raise_a_ceiling():
    from brambleloop.finance import credits, spend_policy, spend_report

    db = boot()
    before = spend_policy.headroom(0.0)
    assert credits.wallet(db)["why_empty"]
    for bad in (dict(kind="free_money"), dict(amount=0), dict(evidence_ref="")):
        args = dict(provider="anthropic", kind="promotional_credit", amount=5.0, currency="USD",
                    granted_on=(NOW - timedelta(days=3)).date().isoformat(),
                    evidence_ref="owner message 2026-10-07")
        args.update(bad)
        try:
            credits.grant(db, **args)
        except credits.CreditRefused:
            pass
        else:
            raise AssertionError(f"accepted {bad}")
    credits.grant(db, provider="anthropic", kind="promotional_credit", amount=5.0,
                  currency="CAD", granted_on=(NOW - timedelta(days=3)).date().isoformat(),
                  evidence_ref="owner message")
    spend_report.record(db, agent="a", amount_cad=7.0, purpose="p", provider="anthropic",
                        model="m")
    w = spend_report.governance(db)["credits"]
    a = w["providers"]["anthropic"]
    assert a["estimated_absorbed_by_credit_cad"] == 5.0 and a["estimated_cash_exposure_cad"] == 2.0
    assert a["basis"] == "ESTIMATED" and a["credits"][0]["expiry_basis"] == "UNKNOWN"
    assert w["ceilings_changed"] == 0 and spend_policy.headroom(0.0) == before
    # the month's recorded spend is unchanged by a credit: exposure is not netted
    assert spend_report.governance(db)["month"]["spent_cad"] >= 7.0


def test_the_f304_dimensions_are_columns_on_the_ledger_row_too():
    from brambleloop.core.models import CostEntry
    from brambleloop.finance import spend_report

    cols = set(CostEntry.__table__.columns.keys())
    assert {"listing_id", "image_count", "observed_cad", "evidence_ref"} <= cols, cols
    db = boot()
    lid = _listing(db, "fern-throw", etsy_id="4401")
    img = spend_report.record(db, agent="gateway", amount_cad=0.0411, purpose="image.generate",
                              provider="openai_gpt_image", model="openai_gpt_image",
                              product_slug="fern-throw", kind="image",
                              detail={"reservation_id": 9})
    txt = spend_report.record(db, agent="o", amount_cad=0.02, purpose="concept")
    with db.session() as s:
        r = s.get(CostEntry, img)
        assert (r.listing_id, r.image_count, r.observed_cad, r.evidence_ref) == (
            lid, 1, None, "reservation:9")
        t = s.get(CostEntry, txt)
        assert t.listing_id is None and t.image_count is None and t.observed_cad is None


def test_a_database_made_before_the_columns_upgrades_additively():
    import sqlite3

    from sqlalchemy import inspect

    from brambleloop.core import migrate
    from brambleloop.core.db import Database
    from brambleloop.core.models import CostEntry

    d = os.path.join(os.environ.get("TMPDIR") or "/tmp", "old-ledger.sqlite")
    if os.path.exists(d):
        os.remove(d)
    db = Database(f"sqlite:///{d}")
    db.create_all()
    con = sqlite3.connect(d)
    for col in ("listing_id", "image_count", "observed_cad", "evidence_ref"):
        con.execute(f'ALTER TABLE cost_entries DROP COLUMN "{col}"')
    con.execute("INSERT INTO cost_entries (at, agent, kind, amount_cad, tokens_in, tokens_out, "
                "provider, model, department, product_slug, purpose, estimated_cad, detail) "
                "VALUES ('2026-10-01 00:00:00', 'old', 'llm', 1.5, 0, 0, '', '', '', '', 'p', "
                "1.5, '{}')")
    con.commit()
    con.close()
    old = Database(f"sqlite:///{d}")
    have = {c["name"] for c in inspect(old.engine).get_columns("cost_entries")}
    assert "observed_cad" not in have
    changes = migrate.apply(old.engine)
    have = {c["name"] for c in inspect(old.engine).get_columns("cost_entries")}
    assert {"listing_id", "image_count", "observed_cad", "evidence_ref"} <= have, changes
    with old.session() as s:
        row = s.query(CostEntry).filter_by(agent="old").one()
        assert row.amount_cad == 1.5 and row.observed_cad is None and row.listing_id is None
        assert row.image_count is None and row.evidence_ref == ""
    os.remove(d)



# -- F-311 ----------------------------------------------------------------------------------

def test_every_evidence_reuse_path_keys_through_one_helper_with_unchanged_keys():
    import hashlib
    import importlib
    import inspect as _inspect
    import json

    from brambleloop.gateway import evidence_key as EK, image_bench, paid_calls, routing
    from brambleloop.intel import pods
    from brambleloop.visual import photoreal

    assert EK.REUSE_PATHS
    for name, target in EK.REUSE_PATHS.items():
        mod, fn = target.split(":")
        src = _inspect.getsource(getattr(importlib.import_module(mod), fn))
        assert "evidence_key" in src, (name, target)

    payload = {"b": [1, "é"], "a": NOW}
    legacy = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                       default=str).encode("utf-8")).hexdigest()
    assert routing.fingerprint(payload) == pods.fingerprint(payload) == legacy
    parts = ("render", 7, {"x": 1})
    assert paid_calls.fingerprint(*parts) == hashlib.sha256(json.dumps(
        parts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

    assert image_bench.CANDIDATES
    cand = image_bench.CANDIDATES[0]
    rubric_legacy = hashlib.sha256("|".join([
        image_bench.METHOD_VERSION, cand.key, cand.resolution, f"{cand.usd_per_image}",
        ",".join(d.key for d in image_bench.RUBRIC), image_bench.IDENTITY_DIMENSION.key,
        image_bench.GALLERY_DIMENSION.key, ",".join(t.key for t in image_bench.TRIALS),
        str(image_bench.SAMPLES_PER_TRIAL), str(image_bench.SCORE_MAX)]).encode()).hexdigest()[:16]
    assert image_bench.rubric_fingerprint(cand) == rubric_legacy
    assert image_bench.TRIALS
    for trial in image_bench.TRIALS:
        judged = ((image_bench.IDENTITY_DIMENSION.key,) if trial.needs_reference
                  else tuple(d.key for d in image_bench.RUBRIC))
        want = hashlib.sha256("|".join([
            cand.key, cand.resolution, f"{cand.usd_per_image}", trial.key, trial.prompt,
            ",".join(judged), str(image_bench.SCORE_MAX),
            image_bench.METHOD_VERSION if trial.needs_reference else "method-independent",
        ]).encode()).hexdigest()[:16]
        assert image_bench.trial_fingerprint(cand, trial) == want, trial.key

    f = os.path.join(os.environ.get("TMPDIR") or "/tmp", "portrait.bin")
    with open(f, "wb") as fh:
        fh.write(b"portrait-bytes")
    assert photoreal._portrait_fingerprint(f) == hashlib.sha256(b"portrait-bytes").hexdigest()
    os.remove(f)
    assert photoreal._portrait_fingerprint(f) == "", "unreadable is nothing to reuse"
    # a changed upstream is a miss, never a stale hit
    assert routing.fingerprint({"a": 1}) != routing.fingerprint({"a": 2})


if __name__ == "__main__":
    run_tests(globals())
