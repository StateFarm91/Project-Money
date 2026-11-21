"""ENG-SUPPLY-RESEARCH: READY concepts wait on research that the factory can actually produce.

Production readback (5188badb, 15:51Z): factory_visibility.supply last_admit {ready 32,
admitted 0, waiting_on_research 32}. Every pod's research is "absent": amigurumi, bags and
home_decor have "no_watchlist_gap", while garments and hats have "gap_not_pursuing". The
allowance had 5 units, so admission was blocked by research alone.

There were two causes:

1. ENG-SUPPLY-FEED (`link_demand`, deployed in 19h10) links the arenas we already sell in
   to the gap -> research -> answer path, but only inside `intel.watchlist_compare`. That
   job ran daily and last ran at 00:39Z, before the deploy. No deploy-triggered pass
   existed, so the gaps waited up to a day to open.
2. Even after it runs, `watchlist_research.answer` needs DURABLE_DAYS (3) distinct
   observation dates per shop, and it read them only from the daily comparison readings.
   The readings written before ENG-SUPPLY-FEED dropped every covered pod, so a covered arena
   had no recorded observation days. It would have stayed unanswered for three more days,
   although the successful scans that observed it are recorded (audit
   `intel.watchlist_scan` ran=True and stored listing rows with first_seen/last_seen).

Fix: durability also reads those primary records (`watchlist_research.scan_history`), with
the same rule: a read that really happened, enough live listings, never a withdrawn row, at
least MIN_SHOPS_FOR_ARENA shops, and only for days whose reading predates ENG-SUPPLY-FEED.
The comparison is also queued once per deploy before the pool pass (CA$0, no network).

Every listing, shop observation, judgement and product here is a TEST FIXTURE.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_supply_research.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - per-process temp sandbox, removed at exit
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

import test_concepts100 as C100  # noqa: E402
import test_new_product_flow as NPF  # noqa: E402
import test_supply_feed as SF  # noqa: E402
import test_supply_lane as LANE  # noqa: E402

from sqlalchemy import select  # noqa: E402

from brambleloop.core.models import AuditLog, BenchmarkListing, Product  # noqa: E402
from brambleloop.intel import research  # noqa: E402
from brambleloop.intel import watchlist as W  # noqa: E402
from brambleloop.intel import watchlist_research as WR  # noqa: E402
from brambleloop.radar import concept_pool as P  # noqa: E402
from brambleloop.runtime.intel_ops import benchmark_alias  # noqa: E402

NOW = SF.NOW


def _scan_audits(db, days) -> None:
    """What a successful `intel.watchlist_scan` job records for each shop it read."""
    with db.session() as s:
        for d in days:
            s.add(AuditLog(actor="market_radar", action="intel.watchlist_scan",
                           at=NOW - timedelta(days=d, hours=-1),
                           detail={"ran": True, "shops": [
                               {"alias": benchmark_alias(m.key), "ran": True, "state": None}
                               for m in SF._shops()]}))


def _pre_deploy_state(*, scans=(3, 2, 1, 0)):
    """Production before this fix: the earlier daily comparisons ran WITHOUT ENG-SUPPLY-FEED
    (covered pods dropped), the nine shops were scanned on several days, the halt is open."""
    db = C100._db()
    NPF._exhaust_launch0(db)
    LANE._open_staleness_halt(db, LANE._existing_slugs(), stale=LANE.STALE)
    with db.session() as s:
        for i, p in enumerate(s.scalars(select(Product).order_by(Product.slug))):
            p.title = SF.EXISTING_TITLES[i % len(SF.EXISTING_TITLES)]
    SF._scan(db)
    _scan_audits(db, scans)
    orig = W.link_demand
    W.link_demand = lambda rep: []           # the comparison as it ran before 19h10
    try:
        for d in range(SF.HISTORY_DAYS, 0, -1):
            at = NOW - timedelta(days=d)
            SF._read_shops(db, at)
            W.record_comparison(db, now=at)
    finally:
        W.link_demand = orig
    # ... and those readings recorded no covered arena at all (`demand_arenas` came with
    # ENG-SUPPLY-FEED): strip them, so the stored readings are what production holds.
    from sqlalchemy.orm.attributes import flag_modified

    from brambleloop.core.models import OperatingReading
    with db.session() as s:
        for r in s.scalars(select(OperatingReading).where(
                OperatingReading.kind == W.COMPARE_READING)):
            r.payload = {k: v for k, v in (r.payload or {}).items()
                         if k not in ("demand_arenas", "demand_unknown_arenas")}
            flag_modified(r, "payload")
    SF._read_shops(db, NOW - timedelta(hours=1))
    NPF._open_vision(db)
    return db


def test_reproduces_production_ready_concepts_research_absent_none_admitted():
    db = _pre_deploy_state()
    out = P.replenish(db, now=NOW, unit_cad=0.12)
    res = out["result"]
    covered = {p: e for p, e in res["ready_by_pod"].items() if p in SF.COVERED}
    assert covered, res["ready_by_pod"]
    assert all(e["research"] == P.RESEARCH_ABSENT and e["why"] == "no_watchlist_gap"
               for e in covered.values()), covered
    assert not {r.pod for r in C100._pool(db) if r.state == P.ADMITTED} & SF.COVERED


def test_the_deploy_pass_opens_answers_and_admits_from_recorded_scans():
    db = _pre_deploy_state()
    judge, restore = LANE._with_judge()
    try:
        SF._drain(db, cycles=3)      # the boot comparison, pool, intake, supply.admit
    finally:
        restore()
    st = P.research_status(db, "home_decor", today=NOW.date(), now=NOW)
    assert st["status"] == P.RESEARCH_PRESENT, st
    with db.session() as s:
        t = s.get(research.ResearchTask, st["research"]["task"])
        assert t.state == research.ANSWERED and t.trigger.startswith("watchlist_gap:")
        srcs = {x["source"] for x in t.sources or []}
        assert WR.SCAN_HISTORY in srcs, srcs     # durability came from the recorded scans
        facts = [f for f in t.findings or [] if f.get("claim_class") == "fact"]
        assert any(re.search(r"\b[3-9] or more distinct observation dates", f["statement"])
                   for f in facts), [f["statement"] for f in facts]
    admitted = Counter(r.pod for r in C100._pool(db) if r.state == P.ADMITTED)
    assert set(admitted) & SF.COVERED, admitted
    assert LANE._systemic_open(db)


def test_mutation_without_scan_history_covered_research_waits():
    """The defect restored: durability from the readings alone. Covered arenas stay
    unanswered ("not yet durable") and nothing is admitted there."""
    orig = WR.scan_history
    WR.scan_history = lambda db, pod, now: {}
    try:
        db = _pre_deploy_state()
        judge, restore = LANE._with_judge()
        try:
            SF._drain(db, cycles=2)
        finally:
            restore()
    finally:
        WR.scan_history = orig
    st = P.research_status(db, "home_decor", today=NOW.date(), now=NOW)
    assert st["status"] != P.RESEARCH_PRESENT, st
    admitted = Counter(r.pod for r in C100._pool(db) if r.state == P.ADMITTED)
    assert not set(admitted) & SF.COVERED, admitted


def test_honesty_scans_never_read_corroborate_nothing():
    """No successful read recorded on the earlier days -> the history adds nothing."""
    db = _pre_deploy_state(scans=(0,))
    for pod in SF.COVERED:
        hist = WR.scan_history(db, pod, now=NOW)
        assert all(len(v) <= 1 for v in hist.values()), hist
    st_days, _dates, _added = WR.durability_with_history(db, [], "home_decor", now=NOW)
    assert st_days < WR.DURABLE_DAYS


def test_withdrawn_or_too_few_listings_do_not_corroborate():
    db = _pre_deploy_state()
    with db.session() as s:
        for r in s.scalars(select(BenchmarkListing)):
            r.audit_state = "withdrawn"
    assert WR.scan_history(db, "home_decor", now=NOW) == {}


def test_a_failed_read_is_not_an_observation():
    db = C100._db()
    SF._scan(db)
    with db.session() as s:
        for d in (3, 2, 1):
            s.add(AuditLog(actor="market_radar", action="intel.watchlist_scan",
                           at=NOW - timedelta(days=d),
                           detail={"shops": [{"alias": benchmark_alias(m.key), "ran": False,
                                              "state": "source_outage"}
                                             for m in SF._shops()]}))
    assert WR.scan_history(db, "home_decor", now=NOW) == {}


def test_the_comparison_runs_on_every_deploy_before_the_pool():
    src = (ROOT / "src/brambleloop/app/main.py").read_text()
    i = src.index('("watchlist_compare", "market_radar", "intel.watchlist_compare")')
    assert i < src.index('("concept_pool", "market_radar", "radar.concept_pool")')


def test_a_current_reading_is_never_overridden_by_history():
    """Days with a reading written after ENG-SUPPLY-FEED are decided by that reading only."""
    readings = [("2026-11-20", {"validated_arenas": [], "demand_arenas": []}),
                ("2026-11-19", {"validated_arenas": [], "demand_arenas": []})]
    db = _pre_deploy_state()
    days, dates, added = WR.durability_with_history(db, readings, "home_decor", now=NOW)
    assert (days, added) == (0, False), (days, dates)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print("FAIL", name, type(e).__name__, str(e)[:500])
    print("OK" if not fails else f"{fails} FAILED")
    sys.exit(1 if fails else 0)
