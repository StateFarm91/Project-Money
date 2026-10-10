"""W4-B2CLOSE (2026-10-10): the company-executable gaps the Build 2 re-verification found.

A. #35/#39 sit on `rendered_pages`, whose only opening was a recorded browser.probe -- which
   etsy.com/legal (DataDome, 403) can never honestly give. The closure's own remedy is a
   person's page reading through POST /api/policy/snapshot. A current, reviewed, audited set
   of those readings now opens the gate as well; everything short of that keeps it closed.
B. #10's company half: one real free motif asset (a library motif through the catalogue
   builder, granted a certificate by the release chain), and /api/free-to-paid plus the daily
   growth.distribution cadence planning against it. Nothing is published or sent.
C. The owner cards that showed UNKNOWN are costed: storage_offsite from the Backblaze B2 list
   price and production's archive size; browser_worker no longer exists (withdrawn in A).
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.build2 import closure as C  # noqa: E402
from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gates import platform_policy as PP  # noqa: E402
from brambleloop.gates import policy_reader  # noqa: E402
from brambleloop.intel import browser  # noqa: E402

RESULTS: list[str] = []
LEGAL = policy_reader.external_sources()
TEXT = "A person's reading of the page, long enough to be a policy text. " * 8


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _intake(db, source: str, *, text: str = TEXT, read_by: str = "owner",
            checked_on: str = "") -> dict:
    """What POST /api/policy/snapshot does: record the reading, then audit it by id."""
    res = PP.record_page_reading(db, source=source, text=text, version="v", summary="s",
                                 read_by=read_by, checked_on=checked_on)
    Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={
        k: res[k] for k in ("id", "source", "digest", "material_change", "checked_on",
                            "current", "incidents_resolved", "basis")})
    return res


def _gate(db) -> bool:
    return E.GATE_BY_KEY["rendered_pages"].open(db, {})


def test_the_legal_sources_are_the_five_the_owner_checklist_names():
    assert LEGAL == sorted(["seller_policy", "creativity_standards", "advertising_rules",
                            "shilling_and_reviews", "children_and_baby"]), LEGAL
    assert set(E.GATE_BY_KEY["rendered_pages"].requirement_ids) == {35, 39}
    ok("rendered_pages holds #35/#39; the five etsy.com/legal sources are the readings")


def test_nothing_recorded_keeps_the_gate_closed():
    db = _db()
    st = PP.page_readings_status(db)
    assert st["open"] is False and st["not_current"] == LEGAL
    assert _gate(db) is False
    ok("no reading: gate closed, all five not current")


def test_a_full_current_set_opens_the_gate_and_four_of_five_does_not():
    db = _db()
    for src in LEGAL[:-1]:
        _intake(db, src)
    assert _gate(db) is False
    assert PP.page_readings_status(db)["not_current"] == [LEGAL[-1]]
    _intake(db, LEGAL[-1])
    assert PP.page_readings_status(db)["open"] is True
    assert _gate(db) is True
    # Only the policy half opened: no browser exists, and the live storefront inspection
    # (which needs one) stays closed.
    assert browser.usable(db) is False
    from brambleloop.brand import storefront_preview

    assert storefront_preview.live_inspection(db)["gate_open"] is False
    ok("4/5 readings closed; 5/5 current readings open rendered_pages; browser half untouched")


def test_readings_go_stale_by_themselves_and_a_backdated_one_never_opens():
    db = _db()
    for src in LEGAL:
        _intake(db, src)
    later = date.today() + timedelta(days=PP.MAX_AGE_DAYS + 1)
    st = PP.page_readings_status(db, today=later)
    assert st["open"] is False and st["not_current"] == LEGAL, st
    edge = date.today() + timedelta(days=PP.MAX_AGE_DAYS)
    assert PP.page_readings_status(db, today=edge)["open"] is True

    db2 = _db()
    old = (date.today() - timedelta(days=PP.MAX_AGE_DAYS + 1)).isoformat()
    for src in LEGAL:
        _intake(db2, src, checked_on=old if src == LEGAL[0] else "")
    assert _gate(db2) is False
    assert PP.page_readings_status(db2)["sources"][LEGAL[0]]["why"].startswith("older than")
    ok("a set closes the day it passes 30 days; a backdated reading never opens it")


def test_a_reading_without_provenance_never_opens_the_gate():
    # Recorded by code rather than through the authenticated intake: no audit row.
    db = _db()
    for src in LEGAL:
        PP.record_page_reading(db, source=src, text=TEXT, read_by="owner")
    assert _gate(db) is False
    # Audited, but nobody is named as the reader.
    db = _db()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="", basis=PP.PAGE_BASIS)
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    # Audited and named, but not a page reading (a search-engine excerpt / repository basis).
    db = _db()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="owner", basis="excerpt")
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    # Dated in the future (the intake refuses this; a row written around it is not trusted).
    db = _db()
    future = (date.today() + timedelta(days=3)).isoformat()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="owner", basis=PP.PAGE_BASIS,
                                 checked_on=future)
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    assert PP.page_readings_status(db)["sources"][LEGAL[0]]["why"] == "dated in the future"
    ok("un-audited, anonymous, non-page and future-dated readings all keep it closed")


def test_an_unreviewed_change_closes_it_until_reviewed():
    db = _db()
    for src in LEGAL:
        _intake(db, src)
    assert _gate(db) is True
    _intake(db, "seller_policy", text=TEXT + " Etsy changed a sentence.")
    st = PP.page_readings_status(db)
    assert st["open"] is False and st["changed_unreviewed"] == ["seller_policy"], st
    assert _gate(db) is False
    PP.review_change(db, "seller_policy", reviewed_by="owner",
                     tested="tests/test_platform_policy.py re-run against the new reading")
    assert _gate(db) is True
    ok("a material change closes the gate until review_change records reviewer and tests")


def test_the_browser_path_still_opens_it_alone():
    db = _db()
    original = browser.fetch
    try:
        browser.fetch = lambda url, **kw: {
            "url": url, "final_url": url, "status": 200,
            "bytes": browser.MIN_PROBE_BYTES + 1, "text": "x" * (browser.MIN_PROBE_BYTES + 1),
            "latency_ms": 5.0}
        browser.probe(db, env={"BRAMBLELOOP_BROWSER_URL": "https://worker.test"})
    finally:
        browser.fetch = original
    assert PP.page_readings_status(db)["open"] is False
    assert _gate(db) is True
    ok("a recorded browser.probe still opens the gate on its own (unchanged path)")


def test_the_gate_kind_and_closure_text_are_unchanged_in_kind():
    assert C.kind_of("rendered_pages") == C.EXTERNAL_BLOCKED
    assert "page_readings_status" in C.EXTERNAL_GATES["rendered_pages"]
    assert "POST /api/policy/snapshot" in E.GATE_BY_KEY["rendered_pages"].how
    ok("rendered_pages stays EXTERNAL; its texts name the human-reading path")


def test_the_owner_card_is_the_ca0_reading_not_a_browser_at_unknown_cost():
    from brambleloop.ops import owner_queue as Q

    d = Q.DECISION_BY_GATE["rendered_pages"]
    assert d["id"] == "policy_page_reading", d["id"]
    assert d["max_cost_cad"] == 0.0 and d["minutes"] == 15
    for src in LEGAL:
        assert src in d["decision"], src
    assert "/api/policy/snapshot" in d["decision"]
    assert not [x for x in Q.DECISIONS if x["id"] == "browser_worker"]
    packet = json.loads((ROOT / "research/final_build/w4/OWNER_ACTIONS.json").read_text())
    items = {i["id"]: i for b in packet["batches"] for i in b["items"]}
    assert "browser_worker" not in items
    card = items["policy_page_reading"]
    assert card["max_cost_cad"] == 0.0 and card["max_cost_display"] == "CA$0.00", card
    assert card["gates"] == ["rendered_pages"]
    ok("OWNER_ACTIONS asks for the CA$0 15-minute reading; the browser-worker card is gone")



# ---- B. #10 Free-to-Paid, company half -------------------------------------------------------


def test_the_free_asset_is_a_certified_release_built_from_the_existing_library():
    from brambleloop.growth import free_assets as FA
    from brambleloop.products import builder, motifs

    assert list(FA.ASSETS) == ["diamond-lattice-relief-swatch"]
    cir = FA.cir_for("diamond-lattice-relief-swatch")
    # No new pattern content: the motif grid is the library's own, the palette the
    # catalogue's, and the provenance names the builder and the motif.
    assert "diamond-lattice" in motifs.LIBRARY
    assert cir.colors == builder.PALETTES["cloudline"]
    prov = str(cir.provenance)
    assert "products.motifs:diamond-lattice" in prov and "products.builder" in prov
    assert cir.slug not in builder.CATALOGUE
    cert = FA.certificate("diamond-lattice-relief-swatch")
    assert cert["granted"] is True and not cert["errors"], cert
    for stage in ("compile", "twin", "write", "reverse", "originality"):
        assert stage in cert["stages_run"], (stage, cert["stages_run"])
    assert cert["content_hash"] and cert["release_hash"]
    assert cert["physical_test_passed"] is False
    # Built at the gauge its declared yarn holds, not a typed one.
    from brambleloop.creative.prototype import gauge_for

    assert cir.gauge.stitches_per_10cm == gauge_for("worsted").stitches_per_10cm
    ok("one free motif asset: library motif -> CIR -> compile/twin/write/reverse -> granted")


def test_the_certificate_is_deterministic_for_its_content():
    from brambleloop.gates.certificate import certify
    from brambleloop.growth import free_assets as FA

    again = certify(FA.cir_for("diamond-lattice-relief-swatch"))
    assert again.granted and again.content_hash == FA.certificate(
        "diamond-lattice-relief-swatch")["content_hash"]
    ok("re-certifying the same content gives the same content hash")


def test_it_has_a_commercial_job_and_replaces_nothing_sold():
    from brambleloop.growth import free_assets as FA
    from brambleloop.growth import free_to_paid as F

    paid = FA.paid_slugs()
    asset = FA.ASSETS["diamond-lattice-relief-swatch"]
    assert "cloudline-baby-blanket" in paid and asset.leads_to in paid
    assert asset.makes not in paid
    verdict = F.check_asset(asset, paid_slugs=paid)
    assert verdict["ok"] is True, verdict
    # The check is live: the same asset making a sold object is refused.
    from dataclasses import replace

    bad = F.check_asset(replace(asset, makes="cloudline-baby-blanket"), paid_slugs=paid)
    assert bad["ok"] is False
    ok("check_asset passes against the real catalogue and still refuses a replacement")


def test_the_plan_reads_real_assets_and_publishes_nothing():
    from brambleloop.growth import free_assets as FA

    r = FA.reading()
    assert r["of"] == 1 and r["with_a_job"] == 1, r
    assert r["premium_products_fed"] == ["cloudline-baby-blanket"]
    assert r["published"] == [] and r["publication"]["waits_on"] == "owned_surfaces"
    assert r["certificates"]["diamond-lattice-relief-swatch"]["granted"] is True
    assert "no free work exists" not in r["note"]
    ok("plan over 1 real certified asset: 1 with a job, feeds Cloudline, 0 published")


def test_an_uncertified_asset_is_not_counted():
    from brambleloop.growth import free_assets as FA

    original = FA.certificate
    try:
        FA.certificate = lambda key: {"granted": False}
        assert FA.real_assets() == []
    finally:
        FA.certificate = original
    ok("an asset whose certificate is refused is not an asset")


def test_the_api_route_and_the_daily_cadence_read_the_real_plan():
    import ast

    main = (ROOT / "src/brambleloop/app/main.py").read_text()
    route = main[main.index('@app.get("/api/free-to-paid")'):]
    route = route[:route.index("@app.", 10)]
    assert "plan([])" not in route and "free_assets.reading()" in route
    ast.parse(main)
    ops = (ROOT / "src/brambleloop/runtime/growth_ops.py").read_text()
    assert '"free_to_paid": free_assets.reading(' in ops
    from brambleloop.build2 import reachability

    for rel in ("growth/free_assets.py", "growth/free_to_paid.py"):
        verdict = reachability.reached(rel)
        assert verdict["reached"], verdict
    ok("/api/free-to-paid and growth.distribution read free_assets; both modules reached")


def test_the_distribution_handler_records_the_free_to_paid_reading():
    from datetime import datetime

    from sqlalchemy import select

    from brambleloop.agents.registry import Registry as Reg
    from brambleloop.core.models import AuditLog, Phase
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import growth_ops
    from brambleloop.runtime.worker import JobContext, handlers

    db = _db()
    queue = JobQueue(db)
    job = queue.enqueue("growth", "growth.distribution", {},
                        idempotency_key=f"b2close:{datetime.now().timestamp()}")
    ctx = JobContext(job=job, db=db, queue=queue, registry=Reg(db), phase=Phase.SHADOW)
    summary = handlers.get("growth.distribution")(ctx)
    assert summary["free_assets_with_a_job"] == 1, summary
    reading = growth_ops.latest(db, growth_ops.DISTRIBUTION_KIND)
    assert reading and reading["free_to_paid"]["with_a_job"] == 1, reading
    assert reading["free_to_paid"]["published"] == []
    with db.session() as s:
        assert s.scalars(select(AuditLog).where(
            AuditLog.action == "growth.distribution")).first() is not None
    ok("growth.distribution records the free-to-paid reading (1 asset with a job, 0 published)")


# ---- C. the owner cards that were UNKNOWN are costed -----------------------------------------


def test_storage_offsite_is_costed_from_the_recorded_b2_price():
    from brambleloop.ops import owner_queue as Q

    d = Q.DECISION_BY_GATE["offsite_storage"]
    assert d["id"] == "storage_offsite"
    assert d["max_cost_cad"] == 1.0, d["max_cost_cad"]
    for fact in ("first 10 GB free", "US$6.95/TB", "US$0.00695/GB", "CA$0.0095/GB",
                 "0.94 GB", "expected CA$0.00", "2026-10-10"):
        assert fact in d["cost_basis"], fact
    assert "Backblaze B2" in d["decision"]
    # The arithmetic the basis states: 6.95 USD per TB is 0.00695 per GB, x1.37 ~ 0.0095 CAD;
    # 14 retained archives of production's 66,975,550 stored bytes is ~0.94 GB < 10 GB free.
    assert abs(6.95 / 1000 * 1.37 - 0.0095) < 0.0001
    from brambleloop.core.offsite import RETAIN_OFFSITE

    assert abs(RETAIN_OFFSITE * 66_975_550 / 1e9 - 0.94) < 0.01
    # The CA$1.00 ceiling covers 10 GB free plus about 105 GB at that price.
    assert 10 + 1.0 / (6.95 / 1000 * 1.37) > 110
    ok("storage_offsite: CA$1.00/month ceiling, expected CA$0.00 at ~0.94 GB (B2 list price)")


def test_no_owner_card_is_uncosted_except_the_two_unknown_by_design():
    packet = json.loads((ROOT / "research/final_build/w4/OWNER_ACTIONS.json").read_text())
    items = [i for b in packet["batches"] for i in b["items"]]
    assert items
    unknown = sorted(i["id"] for i in items if i["max_cost_cad"] is None)
    # ad_budget is not askable yet and OA-G2 is a fee on attributed sales (BUILD2_VERIFY).
    assert unknown == ["OA-G2", "ad_budget"], unknown
    for i in items:
        if i["max_cost_cad"] is None:
            assert "UNKNOWN" in i["max_cost_display"], i["id"]
    card = next(i for i in items if i["id"] == "storage_offsite")
    assert card["max_cost_display"] == "CA$1.00" and "US$6.95/TB" in card["max_cost_basis"]
    ok("only ad_budget and OA-G2 stay UNKNOWN (never CA$0); storage_offsite shows its price")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{len(RESULTS)} passing, {fails} failing")
    sys.exit(1 if fails else 0)
