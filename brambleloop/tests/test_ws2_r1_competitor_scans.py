"""WS2 R1 (audit WS2_research_audit §6): the eight shops' scan state, readable in production.

`/api/readback/evidence` (the read-only readback token) gains a `competitor_scans` section: per
shop, in the owner's order, alias, role, state, method, cadence, last attempted / successful,
next due, backoff-until, consecutive failures and a failure CLASS, live listing coverage, Etsy's
active-listing count and downstream counts. These tests drive it on rows only and check the
module's contract: no shop name, benchmark key, URL or error text ever leaves.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_ws2_r1_competitor_scans.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Benchmark, BenchmarkListing, Job,  # noqa: E402
                                     JobStatus)
from brambleloop.intel import benchmarks, watchlist  # noqa: E402
from brambleloop.intel import scan_evidence as SE  # noqa: E402
from brambleloop.ops import production_evidence as PE  # noqa: E402
from brambleloop.runtime.intel_ops import benchmark_alias  # noqa: E402

NOW = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='ws2r1_')}/s.sqlite", scratch=True)
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _watch(db, member, body):
    memory.remember(db, watchlist.STATE_PREFIX + member.key, kind="intel.watchlist",
                    department="intelligence", subject=f"watchlist {member.key}",
                    state=body.get("state", "unknown"), body=body, sources=["fixture"], now=NOW)


def _fixture():
    db = _db()
    others = [m for m in watchlist.WATCHLIST if m.key != benchmarks.MJS_KEY]
    ok_member, refused_member = others[0], others[1]
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"new": 2}, finished_at=NOW - timedelta(hours=3)))
        s.add(Benchmark(key=benchmarks.MJS_KEY, shop_name=benchmarks.MJS_SHOP,
                        canonical_url="https://example.invalid/anchor",
                        last_scan_at=NOW - timedelta(hours=3)))
        for ref, state in (("1", "discovered"), ("2", "audited"), ("3", "withdrawn")):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=ref,
                                   title=f"secret competitor title {ref}", audit_state=state))
    _watch(db, ok_member, {"state": "ok", "last_ok_at": (NOW - timedelta(hours=5)).isoformat(),
                           "last_attempt_at": (NOW - timedelta(hours=5)).isoformat(),
                           "listings_seen": 40, "shop": {"listing_active_count": 52}})
    _watch(db, refused_member, {
        "state": "credential_refused", "consecutive_failures": 2,
        "last_attempt_at": (NOW - timedelta(hours=1)).isoformat(),
        "last_error": "HTTP 403 Forbidden for https://openapi.etsy.com/v3/... MadelineMaeCo"})
    return db, ok_member, refused_member


def test_every_owner_shop_is_reported_in_order_with_its_state():
    db, ok_member, refused_member = _fixture()
    sec = PE.competitor_scans(db, now=NOW)
    assert sec["readable"] is True
    assert [r["owner_order"] for r in sec["shops"]] == list(range(1, len(SE.OWNER_SHOPS) + 1))
    assert len(sec["shops"]) == 8
    by = {r["alias"]: r for r in sec["shops"]}
    anchor = by[benchmark_alias(benchmarks.MJS_KEY)]
    assert anchor["state"] == SE.SCANNED and anchor["failure_class"] is None
    assert anchor["listings_live"] == 2                       # the withdrawn row is not coverage
    assert anchor["last_successful"] and anchor["success_age_hours"] == 3.0
    good = by[benchmark_alias(ok_member.key)]
    assert good["state"] == SE.SCANNED and good["etsy_active_listing_count"] == 52
    assert good["listings_seen_last_scan"] == 40 and good["cadence_job_type"] == (
        "intel.watchlist_scan")
    bad = by[benchmark_alias(refused_member.key)]
    assert bad["state"] == SE.NOT_ACCESSIBLE and bad["failure_class"] == "credential_refused"
    assert bad["consecutive_failures"] == 2
    expected = (NOW - timedelta(hours=1) + watchlist.backoff_for(2)).isoformat()
    assert bad["backoff_until"] == expected, bad


def test_no_shop_name_key_url_or_error_text_leaves():
    db, ok_member, refused_member = _fixture()
    text = json.dumps(PE.competitor_scans(db, now=NOW))
    forbidden = [benchmarks.MJS_KEY, benchmarks.MJS_SHOP, "etsy.com", "403", "Forbidden",
                 "secret competitor title"]
    for shop, url, _role in SE.OWNER_SHOPS:
        forbidden += [shop, url]
    for m in watchlist.WATCHLIST:
        forbidden += [m.key, m.shop_name]
    leaked = [f for f in forbidden if f and f in text]
    assert not leaked, leaked


def test_a_refused_credential_is_never_read_as_a_pass():
    """Main 6814167293: while Etsy refuses, the readback says so (credential_refused/UNKNOWN)."""
    db = _db()
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": False, "credential_refused": True,
                           "reason": "Etsy refused the read credential at the last etsy.probe"},
                  finished_at=NOW - timedelta(hours=1)))
        s.add(AuditLog(actor="system", action="etsy.probe", artifact="etsy",
                       detail={"ok": False, "status": 403, "reason": "HTTP 403"}))
    sec = PE.competitor_scans(db, now=NOW)
    anchor = next(r for r in sec["shops"] if r["alias"] == benchmark_alias(benchmarks.MJS_KEY))
    assert anchor["state"] != SE.SCANNED, anchor
    assert sec["credential"] in ("refused", "UNKNOWN", "not usable"), sec["credential"]
    assert anchor["failure_class"] == "credential_refused", anchor


def test_the_section_ships_on_the_readback_route_and_an_empty_database_is_honest():
    db = _db()
    body = PE.evidence(db, now=NOW)
    sec = body["sections"]["competitor_scans"] if "sections" in body else body[
        "competitor_scans"]
    assert sec["readable"] is True and len(sec["shops"]) == 8
    assert all(r["state"] == SE.NEVER for r in sec["shops"]), [r["state"] for r in sec["shops"]]
    assert all(r["last_successful"] is None for r in sec["shops"])
    assert "competitor_scans" in PE.SECTIONS


def test_the_research_jobs_are_counted_in_the_loop():
    stages = dict(PE.LOOP_STAGES)
    assert "intel.panel_discovery" in stages["market_observation"]
    assert "radar.concept_intake" in stages["opportunity_validation"]
    # Review 6816970157 M1: the daily join always reports eight shops as work, so it must not
    # satisfy market_observation on a day nothing was scanned.
    assert all("intel.scan_evidence" not in jts for _stage, jts in PE.LOOP_STAGES)


def test_review_m2_a_stale_success_is_not_a_current_scan_and_warns():
    sys.path.insert(0, str(ROOT.parent / "ops"))
    import readback

    db = _db()
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"new": 1}, finished_at=NOW - timedelta(days=60)))
        s.add(Benchmark(key=benchmarks.MJS_KEY, shop_name=benchmarks.MJS_SHOP,
                        canonical_url="https://example.invalid/anchor",
                        last_scan_at=NOW - timedelta(days=60)))
    sec = PE.competitor_scans(db, now=NOW)
    anchor = next(r for r in sec["shops"] if r["alias"] == benchmark_alias(benchmarks.MJS_KEY))
    assert anchor["state"] == SE.SCANNED and anchor["stale"] is True, anchor
    assert anchor["stale_after_hours"] <= PE.STALE_CAP_HOURS
    every_scanned = {**sec, "credential": "usable",
                     "shops": [{**anchor}] + [{**anchor, "stale": False} for _ in range(7)]}
    verdict, why = readback._judge_section("competitor_scans", every_scanned, None)
    assert verdict == readback.WARN and "stale" in why, why
    fresh = {**every_scanned, "shops": [{**anchor, "stale": False}] * 8}
    assert readback._judge_section("competitor_scans", fresh, None)[0] == readback.PASS


def test_review_l2_next_due_comes_from_the_adaptive_interval():
    from brambleloop.core.models import BenchmarkObservation
    from brambleloop.intel import observe

    db, _ok, _refused = _fixture()
    with db.session() as s:
        for h in (30, 20, 10, 3):
            s.add(BenchmarkObservation(at=NOW - timedelta(hours=h),
                                       benchmark_key=benchmarks.MJS_KEY, kind="official_api_read"))
    sec = PE.competitor_scans(db, now=NOW)
    anchor = next(r for r in sec["shops"] if r["alias"] == benchmark_alias(benchmarks.MJS_KEY))
    due = observe.scan_due(db, benchmark_key=benchmarks.MJS_KEY, now=NOW)
    last = due["cadence"]["last_scan_at"]
    expected = (datetime.fromisoformat(last) + timedelta(
        seconds=due["cadence"]["interval_seconds"] * observe.DUE_TOLERANCE)).isoformat()
    assert anchor["next_due"] == PE._iso(expected), (anchor["next_due"], expected)


def test_review_l2_backoff_only_for_a_failing_watch_state():
    db = _db()
    member = [m for m in watchlist.WATCHLIST if m.key != benchmarks.MJS_KEY][0]
    _watch(db, member, {"state": "not_configured", "consecutive_failures": 3,
                        "last_attempt_at": (NOW - timedelta(hours=1)).isoformat()})
    row = next(r for r in PE.competitor_scans(db, now=NOW)["shops"]
               if r["alias"] == benchmark_alias(member.key))
    assert row["backoff_until"] is None, row          # not_configured is not backed off
    _watch(db, member, {"state": "source_outage", "consecutive_failures": 3,
                        "last_attempt_at": (NOW - timedelta(hours=1)).isoformat()})
    row = next(r for r in PE.competitor_scans(db, now=NOW)["shops"]
               if r["alias"] == benchmark_alias(member.key))
    assert row["backoff_until"] is not None, row


def test_review_l1_l3_evidence_warns_with_its_code_and_classes_are_the_shops_own():
    sys.path.insert(0, str(ROOT.parent / "ops"))
    import readback

    def fetch(url, token=None):
        if url.endswith("/api/verify"):
            return 200, {"ok": True, "evidence_checks": [
                {"check": c, "ok": True} for c in readback.EVIDENCE_CHECKS]}
        return 200, {"competitor_scans": {"readable": True, "credential": "refused",
                                          "shops": [{"alias": "bm-x", "state": "scanned"}] * 8},
                     "server_judgement": {}}
    from unittest.mock import patch

    real = readback._judge_section

    def judge(name, section, judged):     # every other row PASS: the WARN row decides
        return real(name, section, judged) if name == "competitor_scans" else (
            readback.PASS, "")
    with patch.object(readback, "_judge_section", side_effect=judge):
        rep = readback.run_evidence(url="https://x.invalid", fetch=fetch,
                                    env={readback.READBACK_TOKEN_VAR: "t" * 40})
    assert rep["verdict"] == readback.WARN, [(i["item"], i["verdict"]) for i in rep["items"]]
    src = (ROOT.parent / "ops" / "readback.py").read_text()
    body = src[src.index("def main_evidence"):src.index("def main(")]
    assert "return WARN_EXIT" in body
    # L3: the global refusal is not painted onto a shop that failed for another reason
    db = _db()
    with db.session() as s:
        s.add(Job(agent="market_radar", job_type="mjs.scan", status=JobStatus.DONE, inputs={},
                  outputs={"ran": False, "reason": "ReadFailed: HTTP 500 upstream"},
                  finished_at=NOW - timedelta(hours=1)))
    from brambleloop.core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(actor="system", action="etsy.probe", artifact="etsy",
                       detail={"ok": False, "status": 403, "reason": "HTTP 403"}))
    anchor = next(r for r in PE.competitor_scans(db, now=NOW)["shops"]
                  if r["alias"] == benchmark_alias(benchmarks.MJS_KEY))
    assert anchor["failure_class"] != "credential_refused", anchor


def test_the_deploy_readback_row_is_advisory_pass_only_when_all_eight_are_scanned():
    sys.path.insert(0, str(ROOT.parent / "ops"))
    import readback

    assert ("competitor shops scanned (eight-shop research network)", "competitor_scans",
            None) in readback.EVIDENCE_ITEMS
    j = readback._judge_section
    shop = {"alias": "bm-x", "state": "scanned", "failure_class": None}
    all_ok = {"readable": True, "credential": "usable", "shops": [shop] * 8}
    assert j("competitor_scans", all_ok, None)[0] == readback.PASS
    one_bad = {**all_ok, "shops": [shop] * 7 + [{"alias": "bm-y", "state": "not_accessible",
                                                 "failure_class": "credential_refused"}]}
    verdict, why = j("competitor_scans", one_bad, None)
    assert verdict == readback.WARN and "7/8" in why and "credential_refused" in why, why
    refused = {**all_ok, "credential": "refused"}
    assert j("competitor_scans", refused, None)[0] == readback.WARN
    assert j("competitor_scans", {"readable": False, "error_class": "KeyError"},
             None)[0] == readback.WARN
    assert j("competitor_scans", None, None)[0] == readback.WARN
    # A WARN row never makes the whole readback FAIL or UNKNOWN.
    def fetch(url, token=None):
        return 200, {"competitor_scans": refused, "server_judgement": {}}
    rep = readback.run_evidence(url="https://x.invalid", fetch=fetch,
                                env={readback.READBACK_TOKEN_VAR: "t" * 40})
    row = next(i for i in rep["items"] if i.get("section") == "competitor_scans")
    assert row["verdict"] == readback.WARN, row

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"PASS: {fails} failing" if not fails else f"FAILED: {fails} failing")
    sys.exit(1 if fails else 0)
