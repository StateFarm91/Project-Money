"""v1.1 integrator wiring: the lane job types are reachable from the shared runtime.

Covers the WIRING REQUESTS of lanes A, B, E, G, H and I that land in shared files:
table registration (core/db.py), continuity labelling (core/continuity.py), cadences,
handlers, agent permissions, bands and liveness, the orchestrator's next_work providers,
the scheduler/worker heartbeat rows, the stale-scheduler self-exit, the single FX constant
and lane B's W-B1 decision subjects.

Run: cd brambleloop && PYTHONPATH=src python tests/test_v11_wiring.py
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ["BRAMBLELOOP_PHASE"] = "shadow"
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)

from sqlalchemy import func, inspect, select  # noqa: E402

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.autonomy import charters, generators, orchestrator  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, Job, JobStatus  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, Worker, handlers  # noqa: E402
from brambleloop.swarm import orchestrate as swarm  # noqa: E402

NEW_JOBS = {"seo.cycle": ("seo_cycle", "listing", "store_commerce"),
            "finance.accounting.cycle": ("accounting_cycle", "cfo", "finance"),
            "marketing.ads_readiness": ("ads_readiness", "growth", "growth"),
            "ops.slo": ("slo_check", "orchestrator", "platform")}


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="v11wire-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def jobs(db):
    with db.session() as s:
        rows = list(s.scalars(select(Job)))
        for r in rows:
            s.expunge(r)
        return rows


# ---- tables and continuity -------------------------------------------------------------


def test_create_all_registers_every_v11_table():
    db = Database("sqlite://", scratch=True)
    db.create_all()
    names = set(inspect(db.engine).get_table_names())
    want = {"company_memory", "company_timeline", "seo_keyword_evidence", "seo_proposals",
            "seo_cycles", "acct_journal_entries", "acct_postings", "acct_period_locks",
            "acct_statement_lines", "acct_exceptions", "acct_challenges",
            "ads_spend_proposals", "ads_finance_challenges", "marketplace_capabilities",
            "ops_runtime_samples", "ops_leases", "cc_owner_sessions", "cc_nonces",
            "cc_security_events", "cc_notifications", "cc_kv"}
    assert want, "the expected set must not be empty"
    missing = sorted(want - names)
    assert not missing, missing


def test_continuity_labels_memory_and_ledger_non_rederivable_and_excludes_live_sessions():
    from brambleloop.core import continuity

    for t in ("company_memory", "company_timeline", "acct_journal_entries", "acct_postings",
              "acct_period_locks", "acct_statement_lines", "acct_exceptions",
              "acct_challenges", "ads_spend_proposals", "ads_finance_challenges",
              "cc_security_events"):
        assert t in continuity.NON_REDERIVABLE, t
    for t in ("cc_owner_sessions", "cc_nonces"):
        assert t in continuity.EXCLUDED_TABLES, t
        assert t not in continuity.NON_REDERIVABLE, t
    # Every labelled name is a real table: a typo would label nothing.
    from brambleloop.core.db import Base

    Database("sqlite://", scratch=True).create_all()
    real = set(Base.metadata.tables)
    # (Scoped to the v1.1 additions: `ledger_entries` is a pre-existing label with no table
    # of that name, reported in WIRING_REPORT.md rather than silently changed here.)
    added = ("company_memory", "company_timeline", "acct_journal_entries", "acct_postings",
             "acct_period_locks", "acct_statement_lines", "acct_exceptions",
             "acct_challenges", "ads_spend_proposals", "ads_finance_challenges",
             "cc_security_events", "cc_owner_sessions", "cc_nonces")
    unknown = sorted(t for t in added if t not in real)
    assert not unknown, unknown


def test_an_export_carries_the_ledger_and_never_a_live_owner_session():
    import json

    from brambleloop.app.command_center.models import OwnerSession
    from brambleloop.autonomy import memory
    from brambleloop.core import continuity

    db = boot()
    memory.remember(db, "wire:test", kind="mission", department="platform",
                    subject="x", state="queued", body={}, sources=[])
    with db.session() as s:
        s.add(OwnerSession(public_id="p1", token_hash="h" * 64,
                           expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    out = Path(tempfile.mkdtemp(prefix="v11wire-exp-")) / "export.jsonl"
    result = continuity.export(db, out)
    tables = {t.name: t for t in result.tables}
    assert tables, "export wrote no tables"
    assert "cc_owner_sessions" not in tables and "cc_nonces" not in tables
    assert tables["company_memory"].rows >= 1 and tables["company_memory"].non_rederivable
    assert "acct_journal_entries" in tables and tables["acct_journal_entries"].non_rederivable
    assert "token_hash" not in out.read_text()
    json.loads(out.read_text().splitlines()[0])


# ---- cadences, handlers, permissions, bands --------------------------------------------


def test_every_wired_job_type_has_cadence_handler_permission_band_and_department():
    known = set(handlers.known())
    by_type = {jt: (name, agent, period) for name, agent, jt, period in CADENCES}
    allowed = {a["name"]: set(a["allowed_job_types"]) for a in DEFAULT_AGENTS}
    assert NEW_JOBS
    for jt, (cadence, agent, dept) in NEW_JOBS.items():
        assert jt in known, f"{jt} has no handler"
        assert by_type.get(jt, (None,))[0] == cadence, (jt, by_type.get(jt))
        assert by_type[jt][1] == agent, (jt, by_type[jt])
        assert jt in allowed[agent], (agent, jt)
        assert swarm.band_for(jt)["mapped"], jt
        assert charters.department_of(jt) == dept, (jt, charters.department_of(jt))
        assert jt in charters.BY_KEY[dept].generatable, (dept, jt)
        assert jt not in charters.PROTECTED_JOB_TYPES
    periods = {jt: by_type[jt][2] for jt in NEW_JOBS}
    assert periods == {"seo.cycle": 6 * 3600, "finance.accounting.cycle": 6 * 3600,
                       "marketing.ads_readiness": 3600, "ops.slo": 15 * 60}, periods
    assert "ops.slo" in swarm.LIVENESS_JOB_TYPES
    for jt in ("autonomy.orchestrate", "autonomy.department_review",
               "autonomy.morning_handoff"):
        assert jt in swarm.JOB_BANDS, jt


def test_the_four_jobs_run_under_the_real_worker_with_zero_spend():
    db = boot()
    q = JobQueue(db)
    assert NEW_JOBS
    for jt, (_c, agent, _d) in NEW_JOBS.items():
        q.enqueue(agent, jt, {}, idempotency_key=f"wire:{jt}")
    w = Worker(db, "wire", job_types=list(NEW_JOBS))
    for _ in range(10):
        if not w.run_once():
            break
    rows = {j.job_type: j for j in jobs(db)}
    for jt in NEW_JOBS:
        assert rows[jt].status == JobStatus.DONE, (jt, rows[jt].status, rows[jt].last_error)
    assert rows["seo.cycle"].outputs["writes_to_etsy"] is False
    assert rows["marketing.ads_readiness"].outputs["spend_cad"] == 0.0
    assert rows["marketing.ads_readiness"].outputs["campaign_activated"] is False
    assert rows["ops.slo"].outputs["ran"] is True
    with db.session() as s:
        assert (s.scalar(select(func.count()).select_from(CostEntry)) or 0) == 0
    protected = [j for j in jobs(db) if j.job_type in charters.PROTECTED_JOB_TYPES]
    assert protected == [], [j.job_type for j in protected]


# ---- next_work providers ---------------------------------------------------------------


def test_providers_feed_the_orchestrator_internal_work_only():
    db = boot()
    report = orchestrator.tick(db, JobQueue(db))
    made = {m["job_type"]: m for m in report["missions"]}
    sources = {m["job_type"]: m["source"] for m in report["missions"]}
    # A fresh company: finance has never run its cycle, SEO has no evidence, the ads
    # eligibility row was never initialised -- each provider says so, and each becomes the
    # department's mission through the real enqueue boundary.
    for jt in ("finance.accounting.cycle", "seo.cycle", "marketing.ads_readiness"):
        assert jt in made, (jt, sorted(made), report["errors"])
        assert sources[jt] == "provider", (jt, sources[jt])
    queued = {j.job_type for j in jobs(db)}
    assert queued, "nothing queued"
    assert not queued & charters.PROTECTED_JOB_TYPES, queued
    # Gated and owner items are never jobs (taxonomy confirmation, Stats export, owner
    # eligibility evidence, disconnected sources).
    assert "listing.taxonomy_refresh" not in queued
    assert not report["errors"], report["errors"]


def test_a_provider_item_naming_a_protected_or_foreign_job_is_never_queued():
    db = boot()
    saved = dict(generators.PROVIDERS)
    try:
        def evil(item):
            return item["job_type"], item["key"]

        import types
        mod = types.ModuleType("wire_evil_provider")
        mod.next_work = lambda db: [{"key": "publish", "job_type": "store.publish"},
                                    {"key": "ads", "job_type": "ads.campaign"},
                                    {"key": "foreign", "job_type": "radar.score"}]
        sys.modules["wire_evil_provider"] = mod
        generators.PROVIDERS["growth"] = (("evil", "wire_evil_provider", "next_work", evil),)
        snap = generators.Snapshot.read(db, datetime.now(timezone.utc))
        cands = generators.provider_candidates(db, charters.BY_KEY["growth"], snap)
        assert cands == [], [c.job_type for c in cands]
        report = orchestrator.tick(db, JobQueue(db), departments=[charters.BY_KEY["growth"]])
        queued = {j.job_type for j in jobs(db)}
        assert not queued & {"store.publish", "ads.campaign", "radar.score"}, queued
        assert not report["errors"], report["errors"]
    finally:
        generators.PROVIDERS.clear()
        generators.PROVIDERS.update(saved)
        sys.modules.pop("wire_evil_provider", None)


def test_a_broken_provider_costs_only_its_own_candidates():
    db = boot()
    saved = dict(generators.PROVIDERS)
    try:
        def adapt(item):
            return None

        generators.PROVIDERS["finance"] = (("broken", "no_such_module_xyz", "next_work",
                                            adapt),)
        report = orchestrator.tick(db, JobQueue(db), departments=[charters.BY_KEY["finance"]])
        assert report["departments"]["finance"]["state"] in ("GENERATED", "SATURATED"), report
        assert not report["errors"], report["errors"]
    finally:
        generators.PROVIDERS.clear()
        generators.PROVIDERS.update(saved)


def test_a_provider_does_not_re_ask_for_a_job_that_just_succeeded():
    db = boot()
    q = JobQueue(db)
    q.enqueue("cfo", "finance.accounting.cycle", {}, idempotency_key="wire:acct")
    w = Worker(db, "wire", job_types=["finance.accounting.cycle"])
    assert w.run_once()
    snap = generators.Snapshot.read(db, datetime.now(timezone.utc))
    cands = generators.provider_candidates(db, charters.BY_KEY["finance"], snap)
    assert all(c.job_type != "finance.accounting.cycle" for c in cands), cands


# ---- heartbeats and the stale-scheduler self-exit --------------------------------------


def test_scheduler_and_worker_heartbeats_are_durable_rows_the_slo_reads():
    from brambleloop.app import runner
    from brambleloop.ops import slo

    db = boot()
    runner._scheduler_heartbeat(db, ["a", "b"])
    runner._last_worker_heartbeat = 0.0
    runner._worker_heartbeat(db, "wire-worker")
    runner._worker_heartbeat(db, "wire-worker")        # rate-limited: one row a minute
    with db.session() as s:
        rows = list(s.scalars(select(slo.RuntimeSample)))
        kinds = sorted((r.component, r.kind) for r in rows)
        sched = slo.scheduler_staleness(s, datetime.now(timezone.utc))
    assert kinds == [("scheduler", "heartbeat"), ("worker", "heartbeat")], kinds
    assert sched["stale"] is False and "scheduler" in sched["source"], sched


def test_stale_scheduler_self_exit_is_conservative():
    from brambleloop.app import runner

    now = datetime.now(timezone.utc)
    st = runner.RunnerState()
    # No embedded scheduler in this process: never exits.
    assert runner.scheduler_stale(st, now, 900)[0] is False
    st.enabled, st.scheduler_started_at = True, now - timedelta(seconds=60)
    assert runner.scheduler_stale(st, now, 900)[0] is False        # starting, not stale
    st.scheduler_started_at = now - timedelta(hours=2)
    assert runner.scheduler_stale(st, now, 900)[0] is True         # never ticked in 2 h
    st.scheduler_last_tick = now - timedelta(seconds=120)
    assert runner.scheduler_stale(st, now, 900)[0] is False        # ticking
    st.scheduler_last_tick = now - timedelta(seconds=901)
    assert runner.scheduler_stale(st, now, 900)[0] is True
    # A tick from a previous start() is not evidence about this scheduler.
    st.scheduler_started_at = now - timedelta(seconds=30)
    assert runner.scheduler_stale(st, now, 900)[0] is False

    exits = []
    saved_exit, saved_state = runner._exit, runner.STATE
    try:
        runner._exit = lambda code: exits.append(code)
        runner.STATE = runner.RunnerState(enabled=True,
                                          scheduler_started_at=now - timedelta(hours=3),
                                          scheduler_last_tick=now - timedelta(hours=1))
        strikes = runner.supervise_once(0, now=now)
        assert strikes == 1 and exits == [], (strikes, exits)   # one strike never exits
        runner.supervise_once(strikes, now=now)
        assert exits == [1], exits
        runner.STATE.scheduler_last_tick = now
        assert runner.supervise_once(1, now=now) == 0           # recovery resets strikes
    finally:
        runner._exit, runner.STATE = saved_exit, saved_state


def test_self_exit_opt_out():
    from brambleloop.app import runner

    saved = os.environ.get("BRAMBLELOOP_SELF_EXIT_ON_STALE")
    try:
        os.environ["BRAMBLELOOP_SELF_EXIT_ON_STALE"] = "0"
        assert runner.self_exit_enabled() is False
        os.environ.pop("BRAMBLELOOP_SELF_EXIT_ON_STALE")
        assert runner.self_exit_enabled() is True
    finally:
        if saved is not None:
            os.environ["BRAMBLELOOP_SELF_EXIT_ON_STALE"] = saved


# ---- FX and W-B1 -----------------------------------------------------------------------


def test_one_fx_assumption_everywhere():
    from brambleloop.core import fx
    from brambleloop.finance import currency
    from brambleloop.gateway import anthropic, image_bench, images, routing
    from brambleloop.scale import target
    from brambleloop.visual import d_judge

    assert abs(anthropic.USD_TO_CAD * routing.USD_PER_CAD - 1.0) < 1e-12
    for v in (routing.USD_PER_CAD, currency.ASSUMED_USD_PER_CAD, target.USD_PER_CAD):
        assert v == fx.ASSUMED_USD_PER_CAD
    for v in (anthropic.USD_TO_CAD, images.USD_TO_CAD, image_bench.USD_TO_CAD,
              d_judge.USD_TO_CAD):
        assert v == fx.ASSUMED_CAD_PER_USD
    # The unified rate never makes a USD cost look cheaper than before (conservative).
    assert fx.ASSUMED_CAD_PER_USD >= 1.37


def test_w_b1_decisions_carry_their_subject():
    tree = ast.parse((ROOT / "src/brambleloop/runtime/release.py").read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "matching"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "consume"]
    cells = {}
    for c in calls:
        cell = c.args[1].value if len(c.args) > 1 and isinstance(c.args[1], ast.Constant) \
            else None
        cells[cell] = {k.arg for k in c.keywords}
    assert {"seo_search", "customer_experience"} <= set(cells), cells
    assert "subject" in cells["seo_search"], cells
    assert "subject" in cells["customer_experience"], cells


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
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
