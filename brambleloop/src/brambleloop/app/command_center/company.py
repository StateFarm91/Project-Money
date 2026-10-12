"""Company overview and completion effort for the Owner Command Center (wave 4, lane CC).

Two owner-facing reads, both behind the `/api/cc/*` owner-session gate:

* `company(db)` -- one mobile-first page that answers "how is the company right now": company
  status, every department and agent (active / sleeping / blocked / unhealthy, current job,
  last useful result, next wake), owner actions, approvals, store, product pipeline, finance,
  autonomy/learn, Build 2 closure, Final Master closure, visual status, Laura, blockers.
* `completion(db)` -- the parallel completion work, read from the committed
  `research/final_build/w4/COMPLETION_BOARD.json` (schema below) so the owner can watch it.

Every value carries `as_of` and a basis. Anything that cannot be read is UNKNOWN with a
reason; UNKNOWN is never rendered or summed as zero (F-898). Department state comes from the
autonomy provider (`autonomy.status.summary`, lane AUTO); its absence makes every department
UNKNOWN, never "sleeping".

The Build 2 closure matrix and maturity ladder take tens of seconds on a cold process (they
walk the module graph and the test sources), so they are computed off the request path, once
per `CLOSURE_TTL`, in one background thread; until the first computation lands the section is
UNKNOWN "computing" with the time it started. The Final Master summary reads a packaged
snapshot and is computed inline.
"""
from __future__ import annotations

import json
import re
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Integer, func, select

from . import approvals, providers, readers
from .providers import envelope, guard, now_iso, unknown

# ---- department / agent state ----------------------------------------------------------

#: Owner-facing department/agent states. UNKNOWN is a state, not an absence.
STATES = ("active", "sleeping", "blocked", "unhealthy", "UNKNOWN")
_LAST_USEFUL_SCAN = 400


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v):
    v = _aware(v)
    return v.isoformat() if v is not None else None


def department_state(provider_status: str, running: int) -> str:
    """Map the autonomy provider's department status (+ live running jobs) to an owner state."""
    st = str(provider_status or "UNKNOWN").upper()
    if st == "BLOCKED":
        return "blocked"
    if st == "DEGRADED":
        return "unhealthy"
    if st == "OK":
        return "active" if running else "sleeping"
    return "UNKNOWN"


def _job_dept_fn():
    """lane AUTO's department-of-a-job judge; None when it is not importable."""
    try:
        from ...autonomy.kpis import job_department

        return job_department
    except Exception:  # noqa: BLE001
        return None


def _useful_fn():
    try:
        from ...autonomy.kpis import did_no_work

        return lambda outputs, jt: not did_no_work(outputs, jt)
    except Exception:  # noqa: BLE001
        return None


def _result_text(outputs) -> str | None:
    if not isinstance(outputs, dict) or not outputs:
        return None
    for k in ("summary", "headline", "result", "message", "note", "what"):
        v = outputs.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:200]
    return "outputs: " + ", ".join(sorted(str(k) for k in outputs)[:8])


def _job_facts(db) -> dict:
    """Running jobs and the latest useful finished jobs, read once from `jobs`."""
    from ...core.models import Job, JobStatus

    with db.session() as s:
        running = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.inputs,
                                        Job.started_at)
                                 .where(Job.status == JobStatus.RUNNING)
                                 .order_by(Job.id.desc()).limit(200)).all())
        done = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.inputs, Job.outputs,
                                     Job.finished_at)
                              .where(Job.status == JobStatus.DONE)
                              .order_by(Job.finished_at.desc(), Job.id.desc())
                              .limit(_LAST_USEFUL_SCAN)).all())
        dead_24h = list(s.execute(select(Job.agent, Job.job_type).where(
            Job.status == JobStatus.DEAD,
            Job.finished_at >= datetime.now(timezone.utc) - timedelta(hours=24))).all())
        ever = set(s.scalars(select(Job.agent).distinct()))
    return {"running": running, "done": done, "dead_24h": dead_24h, "agents_ever": ever}


def _current(row) -> dict:
    return {"job_id": row.id, "job_type": row.job_type, "agent": row.agent,
            "started_at": _iso(row.started_at), "source": f"jobs:{row.id}"}


def _useful(row, useful) -> dict | None:
    if useful is None:
        return None
    if not useful(row.outputs, row.job_type):
        return None
    return {"job_id": row.id, "job_type": row.job_type, "agent": row.agent,
            "finished_at": _iso(row.finished_at), "result": _result_text(row.outputs),
            "source": f"jobs:{row.id}"}


TREND_DAYS = 7
SPEND_DAYS = 30


def _missions() -> dict:
    """Each department's objective, from its charter (autonomy.charters); {} if not importable."""
    try:
        from ...autonomy import charters

        return {c.key: c.mission for c in charters.CHARTERS}
    except Exception:  # noqa: BLE001
        return {}


def completed_trend(db, dept_of, *, days: int = TREND_DAYS, now: datetime | None = None) -> dict:
    """F-621: completed (DONE) jobs per department per UTC day over `days` days, from `jobs`.

    Measured from the table; a department with no completed job on a day reads 0 for that day
    only because the jobs table was read and held none (basis measured). Without the department
    judge the trend is UNKNOWN for everyone, never zeros."""
    from ...core.models import Job, JobStatus

    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    labels = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    if dept_of is None:
        return {"basis": "unknown", "days": labels, "by_department": {},
                "why": "autonomy.kpis.job_department not importable"}
    with db.session() as s:
        rows = list(s.execute(select(Job.job_type, Job.inputs, Job.finished_at).where(
            Job.status == JobStatus.DONE, Job.finished_at >= start)).all())
    out: dict[str, list[int]] = {}
    for jt, inputs, fin in rows:
        dept = dept_of(jt, inputs)
        fin = _aware(fin)
        if not dept or fin is None:
            continue
        i = (fin.date() - start.date()).days
        if 0 <= i < days:
            out.setdefault(dept, [0] * days)[i] += 1
    return {"basis": "measured", "days": labels, "by_department": out,
            "source": "jobs (status DONE, finished_at)", "as_of": now.isoformat()}


def department_spend(db, *, days: int = SPEND_DAYS) -> dict:
    """F-621: recorded spend per department over `days` days (finance.governor.spend_by)."""
    try:
        from ...finance import governor

        with db.session() as s:   # the governor reads through a session (as /api/governor)
            return {"ok": True, **governor.spend_by(s, "department", days=days)}
    except Exception as exc:  # noqa: BLE001 - unreadable spend is UNKNOWN, never CA$0
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _dept_spend(spend: dict, key: str) -> dict:
    if not spend.get("ok"):
        return {"value_cad": None, "state": "UNKNOWN", "why": spend.get("why")}
    rows = {r["key"]: r["cad"] for r in spend.get("rows") or []}
    if key in rows:
        return {"value_cad": rows[key], "state": "RECORDED", "days": spend.get("days"),
                "source": "finance.governor.spend_by(department)"}
    if not spend.get("total_cad"):
        # No cost row at all in the window: a recorded zero for every department.
        return {"value_cad": 0.0, "state": "RECORDED", "days": spend.get("days"),
                "source": "finance.governor.spend_by(department): no cost rows in window"}
    return {"value_cad": None, "state": "UNKNOWN", "days": spend.get("days"),
            "why": (f"no cost row names this department; CA${spend.get('unattributed_cad', 0):.2f}"
                    f" of recorded spend is unattributed")}


def departments(db, auto: dict | None = None) -> dict:
    """Every department with owner state, current job, last useful result and next wake."""
    auto = auto if auto is not None else providers.call("autonomy", db)
    dept_of = _job_dept_fn()
    useful = _useful_fn()

    def read():
        facts = _job_facts(db)
        missions = _missions()
        trend = guard("completed_trend", lambda: completed_trend(db, dept_of))
        spend = department_spend(db)
        items = []
        rows = [i for i in (auto.get("items") or []) if isinstance(i, dict) and i.get("department")]
        if auto.get("status") == "UNKNOWN" or not rows:
            # The provider is absent, not built or has nothing: list the charter departments
            # (when importable) as UNKNOWN rather than inventing a state.
            keys = list(auto.get("departments") or [])
            if not keys:
                try:
                    from ...autonomy import charters

                    keys = [c.key for c in charters.CHARTERS]
                except Exception:  # noqa: BLE001
                    keys = []
            rows = [{"department": k, "status": "UNKNOWN"} for k in keys]
        for d in rows:
            key = d["department"]
            mine_running = ([r for r in facts["running"] if dept_of(r.job_type, r.inputs) == key]
                            if dept_of else [])
            last_useful = None
            if dept_of is not None:
                for r in facts["done"]:
                    if dept_of(r.job_type, r.inputs) == key:
                        last_useful = _useful(r, useful)
                        if last_useful:
                            break
            state = department_state(d.get("status"), len(mine_running))
            why = None
            if state == "UNKNOWN":
                why = auto.get("reason") or "the autonomy provider did not report this department"
            elif state == "blocked":
                why = "; ".join(str(b.get("reason") or b.get("gate") or b.get("kind"))
                                for b in d.get("blockers") or []) or "blocked"
            elif state == "unhealthy":
                why = (f"{d.get('dead_24h', 0)} dead job(s) in 24 h with no useful result"
                       if d.get("dead_24h") else "generation error or degraded department")
            items.append({
                "department": key, "name": d.get("name") or key, "state": state,
                "status": d.get("status") or "UNKNOWN", "why": why,
                "current_job": _current(mine_running[0]) if mine_running else None,
                "running_jobs": len(mine_running) if dept_of else None,
                "last_useful_result": last_useful,
                "last_useful_scan": (f"last {_LAST_USEFUL_SCAN} finished jobs"
                                     if dept_of and useful else
                                     "UNKNOWN: autonomy.kpis not importable"),
                "last_run": d.get("last_run"), "next_wake": d.get("next_wake"),
                "open_jobs": d.get("open_jobs"), "useful_24h": d.get("useful_24h"),
                "completed_24h": d.get("completed_24h"),
                "blockers": d.get("blockers") or [],
                # F-621: objective, recorded spend and a measured 7-day completed-work trend.
                "objective": missions.get(key),
                "spend_30d": _dept_spend(spend, key),
                "completed_trend_7d": (
                    {"days": trend.get("days"), "counts": (trend.get("by_department") or {}).get(
                        key, [0] * len(trend.get("days") or [])), "basis": "measured",
                     "source": trend.get("source")}
                    if isinstance(trend, dict) and trend.get("basis") == "measured" else
                    {"days": None, "counts": None, "basis": "unknown",
                     "why": (trend or {}).get("why") or (trend or {}).get("reason")}),
                "source": "autonomy.status.summary"})
        counts = {s: sum(1 for i in items if i["state"] == s) for s in STATES}
        status = ("UNKNOWN" if not items or counts["UNKNOWN"] == len(items) else
                  "BLOCKED" if counts["blocked"] else
                  "DEGRADED" if counts["unhealthy"] or counts["UNKNOWN"] else "OK")
        return envelope(status, items, ["autonomy.status.summary", "jobs"],
                        basis="measured" if auto.get("status") != "UNKNOWN" else "unknown",
                        provider="company.departments", as_of=auto.get("as_of") or now_iso(),
                        counts=counts, orchestrator=auto.get("orchestrator"),
                        reason=(auto.get("reason") if auto.get("status") == "UNKNOWN" else
                                None))

    return guard("departments", read, sources=["autonomy.status.summary", "jobs"])


def _next_wake_by_agent(now: datetime) -> dict:
    try:
        from ...runtime.worker import CADENCES
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, int] = {}
    for _n, agent, _jt, period in CADENCES:
        nxt = (int(now.timestamp() // period) + 1) * period
        out[agent] = min(out.get(agent, nxt), nxt)
    return {a: datetime.fromtimestamp(t, tz=timezone.utc).isoformat() for a, t in out.items()}


def agents(db) -> dict:
    """Every registered agent: enabled, state, current job, last useful result, next wake."""
    from ...core.models import Agent

    useful = _useful_fn()

    def read():
        now = datetime.now(timezone.utc)
        facts = _job_facts(db)
        wakes = _next_wake_by_agent(now)
        with db.session() as s:
            rows = [(a.id, a.name, bool(a.enabled), getattr(a.authority, "value", a.authority))
                    for a in s.scalars(select(Agent).order_by(Agent.name))]
        if not rows:
            return envelope("UNKNOWN", [], ["agents"], basis="unknown",
                            reason="no agent registered", provider="company.agents")
        items = []
        for aid, name, enabled, authority in rows:
            run = [r for r in facts["running"] if r.agent == name]
            dead = sum(1 for r in facts["dead_24h"] if r.agent == name)
            last_useful = None
            for r in facts["done"]:
                if r.agent == name:
                    last_useful = _useful(r, useful)
                    if last_useful:
                        break
            if not enabled:
                state, why = "blocked", "agent disabled (paused) in the registry"
            elif run:
                state, why = "active", None
            elif name not in facts["agents_ever"]:
                state, why = "UNKNOWN", ("no job has ever been recorded for this agent here, "
                                         "so it is not known to be sleeping")
            elif dead and last_useful is None:
                state, why = "unhealthy", f"{dead} dead job(s) in 24 h, no useful result found"
            else:
                state, why = "sleeping", None
            items.append({"name": name, "state": state, "why": why, "enabled": enabled,
                          "authority": authority,
                          "current_job": _current(run[0]) if run else None,
                          "last_useful_result": last_useful,
                          "next_wake": wakes.get(name),
                          "next_wake_basis": ("worker.CADENCES" if name in wakes else
                                              "no cadence: woken only by the orchestrator or "
                                              "by queued work"),
                          "dead_24h": dead, "source": f"agents:{aid}"})
        counts = {s: sum(1 for i in items if i["state"] == s) for s in STATES}
        status = ("UNKNOWN" if counts["UNKNOWN"] == len(items) else
                  "DEGRADED" if counts["unhealthy"] or counts["blocked"] or counts["UNKNOWN"]
                  else "OK")
        return envelope(status, items, ["agents", "jobs", "worker.CADENCES"],
                        reason=(f"{counts['UNKNOWN']} agent(s) have no recorded job"
                                if counts["UNKNOWN"] else None),
                        provider="company.agents", counts=counts,
                        note=(f"last useful result searched in the last {_LAST_USEFUL_SCAN} "
                              "finished jobs; none found there is shown as Unknown"))

    return guard("agents", read, sources=["agents", "jobs"])


# ---- closure (Build 2 + Final Master) --------------------------------------------------

CLOSURE_TTL = timedelta(minutes=30)


def _compute_build2(db) -> dict:
    from ...build2 import closure, maturity

    m = closure.matrix(db)
    mat = maturity.report(db)
    return {
        # W4-B2: the owner's headline (ledger states; executable remaining = OPEN only).
        "headline": closure.dashboard(db, m=m),
        "closure": {"total": m["total"], "counts": m["counts"],
                    "closed_out": m["closed_out"],
                    "closeout_indeterminate": m["closeout_indeterminate"],
                    "gates_checked_live": m["gates_checked_live"],
                    "by_section": m["by_section"],
                    "external_blockers": sorted(m.get("external_blockers") or {}),
                    "open": [{"id": r["id"], "title": r.get("title"), "why": r.get("why")}
                             for r in m["open"]],
                    "matrix_as_of": m["as_of"]},
        "maturity": {"covered_by_the_registry": mat["covered_by_the_registry"],
                     "rungs": mat["rungs"],
                     "highest_rung_reached": mat["highest_rung_reached"],
                     "no_rung_reached": mat["no_rung_reached"],
                     "registered_but_never_run": len(mat["registered_but_never_run"]),
                     "is_production": mat["is_production"]},
    }


#: Replaceable in tests (the real computation takes tens of seconds on a cold process).
COMPUTE_BUILD2 = _compute_build2


class _Cache:
    def __init__(self):
        self.lock = threading.Lock()
        self.value: dict | None = None
        self.at: datetime | None = None
        self.error: str | None = None
        self.started: datetime | None = None
        self.thread: threading.Thread | None = None

    def reset(self):
        with self.lock:
            self.value = self.at = self.error = self.started = None
            self.thread = None


_BUILD2 = _Cache()


def _refresh(db):
    try:
        out = COMPUTE_BUILD2(db)
        err = None
    except Exception as exc:  # noqa: BLE001 - surfaced as UNKNOWN with the reason
        out, err = None, f"{type(exc).__name__}: {str(exc)[:200]}"
    with _BUILD2.lock:
        if out is not None:
            _BUILD2.value, _BUILD2.at = out, datetime.now(timezone.utc)
        _BUILD2.error = err
        _BUILD2.thread = None


def build2_snapshot(db, *, wait: float = 0.0) -> dict:
    """The latest Build 2 closure/maturity reading; starts a refresh when stale or absent."""
    now = datetime.now(timezone.utc)
    with _BUILD2.lock:
        stale = _BUILD2.at is None or now - _BUILD2.at > CLOSURE_TTL
        if stale and _BUILD2.thread is None:
            _BUILD2.started = now
            t = threading.Thread(target=_refresh, args=(db,), daemon=True,
                                 name="cc-build2-closure")
            _BUILD2.thread = t
            t.start()
        thread = _BUILD2.thread
    if wait and thread is not None:
        thread.join(wait)
    with _BUILD2.lock:
        value, at, err, started = _BUILD2.value, _BUILD2.at, _BUILD2.error, _BUILD2.started
        refreshing = _BUILD2.thread is not None
    srcs = ["build2.closure.matrix", "build2.maturity.report",
            "src/brambleloop/build2/requirements.json"]
    if value is None:
        reason = (f"could not be computed: {err}" if err else
                  f"computing (started {started.isoformat() if started else 'unknown'}); "
                  "the matrix walks the module graph and takes up to a minute on a cold "
                  "process -- refresh shortly")
        return unknown(reason, "build2.closure+maturity", srcs)
    c = value["closure"]
    status = "OK" if c["closed_out"] else ("UNKNOWN" if c["closeout_indeterminate"]
                                            else "DEGRADED")
    items = [{"state": k, "count": v} for k, v in c["counts"].items()]
    return envelope(status, items, srcs, provider="build2.closure+maturity",
                    as_of=at.isoformat(), basis="measured",
                    closure=c, maturity=value["maturity"], headline=value.get("headline"),
                    refreshing=refreshing,
                    last_error=err,
                    reason=(None if c["closed_out"] else
                            f"{c['counts'].get('OPEN', 0)} requirement(s) OPEN"
                            if not c["closeout_indeterminate"] else
                            "gates were not read live, so closeout is indeterminate"),
                    ledger="research/final_build/w4/BUILD2_LEDGER.json",
                    note=("closure states come from evidence, not the registry status "
                          "(requirements.coverage() is a registry claim); "
                          "maturity rungs say how far covered rows got (deployed / exercised / "
                          "production-observed are separate from 'covered')"))


def final_master(db) -> dict:
    def read():
        from ...build2 import final_master as fm

        out = fm.summary(db)
        # The snapshot is a release artefact (as_of null by design); show when this process
        # read it, and say so, so the card is never undated.
        if out.get("status") == "DEGRADED" and not out.get("reason"):
            out["reason"] = (f"{out.get('launch_critical_open')} of "
                             f"{out.get('launch_critical_total')} launch-critical rows OPEN")
        out = providers.validate(out, "build2.final_master.summary")
        out["read_at"] = now_iso()
        out["as_of_basis"] = ("snapshot bound to the tree digest; read_at is when this "
                              "process read it, mapping SHAs say how old the snapshot is")
        mb = out.get("mapping_basis") if isinstance(out.get("mapping_basis"), dict) else {}
        shas = [str(mb.get("base") or "")[:7]] + sorted(str(k)[:7] for k in
                                                        (mb.get("remaps") or {}))
        shas = [x for x in shas if x]
        out["release_artefact"] = release_artefact(
            "Final Master closure matrix (final_master_closure.json)", None,
            source="build2/final_master_closure.json",
            mapped_at=(", ".join(shas) if shas else None))
        return out

    return guard("final_master", read, sources=["build2/final_master_closure.json"])


# ---- company page ---------------------------------------------------------------------


def _phase(db) -> dict:
    try:
        from ...core import phase as phase_mod

        ph = phase_mod.resolve(db)
        return {"phase": ph["phase"], "why": ph["why"], "as_of": now_iso(),
                "source": "core.phase.resolve"}
    except Exception as exc:  # noqa: BLE001
        return {"phase": "UNKNOWN", "why": f"phase unreadable: {type(exc).__name__}",
                "as_of": None, "source": "core.phase.resolve"}


def _build() -> dict:
    try:
        from ...core.build import identity

        b = identity()
        return {"commit_short": b.get("commit_short") or None, "branch": b.get("branch"),
                "known": bool(b.get("known")), "source": "core.build.identity"}
    except Exception as exc:  # noqa: BLE001
        return {"commit_short": None, "known": False,
                "why": f"build identity unreadable: {type(exc).__name__}"}


def pipeline(db) -> dict:
    """Product pipeline counts from the products/pattern_versions/listings rows."""
    prods = readers.products(db)
    if prods.get("status") != "OK":
        return prods
    items = prods["items"]
    by_status: dict[str, int] = {}
    by_listing: dict[str, int] = {}
    for p in items:
        by_status[str(p.get("status") or "UNKNOWN")] = by_status.get(
            str(p.get("status") or "UNKNOWN"), 0) + 1
        ls = str(p.get("listing_state") or "no listing")
        by_listing[ls] = by_listing.get(ls, 0) + 1
    stages = [{"stage": "products", "count": len(items)},
              {"stage": "certified pattern version",
               "count": sum(1 for p in items if p.get("certified"))},
              {"stage": "listing drafted", "count": sum(1 for p in items
                                                        if p.get("listing_state"))},
              {"stage": "on Etsy", "count": sum(1 for p in items if p.get("on_etsy"))}]
    return envelope("OK", stages, prods.get("sources") or ["products"],
                    provider="company.pipeline", by_product_status=by_status,
                    by_listing_state=by_listing,
                    truncated_at=100 if len(items) >= 100 else None)


def _blockers(db, depts: dict, fm: dict, owner: dict) -> dict:
    items = []
    for d in depts.get("items") or []:
        for b in d.get("blockers") or []:
            items.append({"what": f"{d['name']}: {b.get('kind')}",
                          "gate": b.get("gate"), "reason": b.get("reason") or b.get("what"),
                          "owner_action": b.get("owner_action"),
                          "source": "autonomy.status.summary"})
    for key, uids in (fm.get("gated_by_key") or {}).items():
        items.append({"what": f"Final Master gate {key}", "rows": len(uids),
                      "source": "build2.final_master.summary"})
    for a in (owner.get("items") or [])[:10]:
        items.append({"what": f"Owner decision: {a.get('what')}", "card_id": a.get("card_id"),
                      "source": "build2.executor.approval_inbox"})
    st = "BLOCKED" if items else ("OK" if depts.get("status") != "UNKNOWN" else "UNKNOWN")
    return envelope(st, items, ["autonomy.status.summary", "build2.final_master.summary",
                                "build2.executor.approval_inbox"],
                    provider="company.blockers",
                    reason=(None if st != "UNKNOWN" else
                            "department blockers unknown: autonomy provider did not report"))


def _overall(depts: dict, money: dict, b2: dict, fm: dict, incidents: dict) -> tuple[str, str]:
    """Worst of the sections: BLOCKED > DEGRADED/UNKNOWN > OK. UNKNOWN never reads as OK."""
    rank = {"OK": 0, "DEGRADED": 1, "UNKNOWN": 1, "BLOCKED": 2}
    parts, worst = [], 0
    for name, env in (("departments", depts), ("money", money), ("build2", b2),
                      ("final master", fm), ("incidents", incidents)):
        s = str(env.get("status") or "UNKNOWN")
        if s != "OK":
            parts.append(f"{name} {s}")
        worst = max(worst, rank.get(s, 1))
    return ("OK", "BLOCKED", "DEGRADED")[0 if worst == 0 else 1 if worst == 2 else 2], (
        "; ".join(parts) or "every section reports OK")


def company(db) -> dict:
    from . import tabs

    ph = _phase(db)
    auto = providers.call("autonomy", db)
    depts = departments(db, auto)
    ags = agents(db)
    box = guard("approvals", lambda: approvals.inbox(db))
    owner = tabs.reconcile_owner_actions(readers.owner_actions_summary(db), box)
    m = guard("money", lambda: tabs.money_section(db))
    b2 = guard("build2", lambda: build2_snapshot(db))
    fm = final_master(db)
    inc = readers.incidents(db, limit=10)
    overall, why = _overall(depts, m, b2, fm, inc)
    comp = completion(db)
    status_env = envelope(overall, [{
        "phase": ph["phase"], "phase_why": ph["why"],
        "build": _build(), "departments": depts.get("counts"),
        "owner_decisions_open": box.get("open") if isinstance(box.get("open"), int) else None,
        "incidents_open": inc.get("open_total") if inc.get("status") != "UNKNOWN" else None,
        "build2_open": ((b2.get("closure") or {}).get("counts") or {}).get("OPEN")
        if b2.get("status") != "UNKNOWN" else None,
        "final_master_launch_critical_open": fm.get("launch_critical_open"),
        "completion_lanes": comp.get("counts")}],
        ["core.phase.resolve", "core.build.identity", "autonomy.status.summary",
         "build2.executor.approval_inbox", "incidents", "build2.closure",
         "build2.final_master"], provider="company.status", reason=why)
    approvals_env = envelope(
        box.get("status") if box.get("status") in providers.STATUSES else "UNKNOWN",
        (box.get("cards") or [])[:10], box.get("sources") or ["build2.executor.approval_inbox"],
        provider="approvals.inbox", open=box.get("open"), reason=box.get("reason"))
    money = envelope(
        m.get("status") or "UNKNOWN",
        [{"metric": "revenue", **(m.get("revenue") or {})},
         {"metric": "profit", **(m.get("profit") or {})},
         {"metric": "recorded_spend", **(m.get("recorded_spend") or {})}],
        ["finance.accounting.dashboard", "ledger", "cost_entries"], provider="money_section",
        basis="measured" if m.get("status") == "OK" else "unknown",
        source_health=m.get("source_health"), reason=m.get("reason"))
    store = providers.call("store_foundation", db)
    visibility = providers.call("visibility", db)
    improve = providers.call("improvement", db)
    visual = guard("visual", lambda: tabs.visual_rnd_section(db))
    laura = providers.call("laura_roadmap", db)
    sections = {
        "company_status": status_env,
        "departments": depts,
        "agents": ags,
        "owner_actions": owner,
        "approvals": approvals_env,
        "store": store,
        "store_visibility": visibility,
        "product_pipeline": guard("pipeline", lambda: pipeline(db)),
        "finance": money,
        "autonomy": auto,
        "learn": improve,
        "learn_outcomes": guard("learn_outcomes", lambda: learn_outcomes(db, improve)),
        "build2_closure": b2,
        "final_master_closure": fm,
        "visual": visual,
        "visual_stages": guard("visual_stages", visual_stages),
        "visual_pipeline_live": guard("visual_pipeline_live", lambda: visual_pipeline_live(db)),
        "competitor_intel": guard("competitor_intel", lambda: competitor_intel(db)),
        "store_live_drift": guard("store_live_drift", lambda: store_live_drift(db)),
        "laura": {**laura, "talk_href": "#/laura"},
        "blockers": _blockers(db, depts, fm, owner),
        "completion_effort": {k: comp.get(k) for k in
                              ("status", "as_of", "basis", "counts", "reason", "sources",
                               "provider", "board_updated_at", "stale")} | {
            "items": [], "href": "#/completion"},
    }
    return {"tab": "COMPANY", "generated_at": now_iso(), "status": overall, "reason": why,
            "sections": sections}


# ---- W4 wiring: competitor findings (MJS), live store drift + readiness (STORE), visual -----

_REPO = Path(__file__).resolve().parents[4]
VISUAL_ENV = "BRAMBLELOOP_VISUAL_STATUS"
VISUAL_REL = Path("research") / "final_build" / "w4" / "VISUAL_STATUS.json"


# Integrator (W4): the deploy image ships src/ but not research/, so each committed W4 JSON the
# owner views read has a shipped snapshot under app/command_center/snapshots/ (kept identical by
# tests/test_w4_cc_snapshots.py; refresh with `python -m brambleloop.app.command_center.snapshots`).
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"


def release_identity() -> dict:
    """Which release this process is running: the build commit and, when the boot guard matched
    a committed release record for this exact tree, that record's sha and recorded_at.
    Anything not known is None (shown as UNKNOWN), never guessed."""
    out = {"build_commit": None, "release_sha": None, "release_recorded_at": None}
    try:
        b = _build()
        out["build_commit"] = b.get("commit_short") if b.get("known") else None
    except Exception:  # noqa: BLE001
        pass
    try:
        from ...ops import release_record as rr

        rec = (rr.BOOT or {}).get("record") or {}
        if rec.get("file"):
            out["release_sha"] = (str(rec.get("sha") or "")[:12]) or None
            data = json.loads((Path(rr.BOOT.get("release_dir") or "") / rec["file"]).read_text())
            out["release_recorded_at"] = data.get("recorded_at")
    except Exception:  # noqa: BLE001 - an unreadable record leaves the fields UNKNOWN
        pass
    return out


def release_artefact(what: str, generated_at, *, source: str, mapped_at: str | None = None
                     ) -> dict:
    """W4-CCGAP: the label every release-time artefact carries so it can never read as live.
    `generated_at` is the artefact's own time (None -> UNKNOWN); the release fields say which
    deployed release shipped it."""
    rel = release_identity()
    gen = str(generated_at) if generated_at else None
    rel_txt = (f"release {rel['release_sha']} (recorded {rel['release_recorded_at'] or 'UNKNOWN'})"
               if rel["release_sha"] else
               f"build {rel['build_commit'] or 'UNKNOWN'} (no release record matched this build)")
    label = (f"Release artefact, not live: {what} as of {rel_txt}; "
             + (f"generated {gen}" if gen else
                (f"mapped at commit {mapped_at}; generation time UNKNOWN" if mapped_at
                 else "generation time UNKNOWN"))
             + ". It changes only when a new release ships.")
    return {"live": False, "label": label, "artefact": what, "source": source,
            "generated_at": gen, "mapped_at": mapped_at, **rel}


def _research_or_snapshot(rel: Path) -> Path:
    """The research file in a checkout; otherwise the shipped snapshot of the same name."""
    p = _REPO / rel
    return p if p.exists() else SNAPSHOT_DIR / rel.name


def competitor_intel(db) -> dict:
    """The latest `mjs.findings` reading: each finding with provenance and confidence."""
    from ...intel import findings as intel_findings

    src = ["intel.findings.latest (operating_readings kind mjs.findings)", "/api/mjs/findings"]
    latest = intel_findings.latest(db)
    if latest is None:
        return unknown("no competitor findings reading stored yet: intel.findings.refresh has "
                       "not run against this database (it needs stored mjs.scan observations)",
                       "intel.findings", src)
    items = []
    for f in latest.get("findings") or []:
        prov = f.get("provenance") or {}
        conf = f.get("confidence") or {}
        items.append({"title": f.get("statement"), "key": f.get("key"),
                      "category": f.get("category"),
                      "confidence": conf.get("grade"), "confidence_basis": conf.get("basis"),
                      "provenance_source": prov.get("source"),
                      "benchmark": prov.get("benchmark_key"), "sample": prov.get("sample"),
                      "observed_from": prov.get("observed_from"),
                      "observed_to": prov.get("observed_to"), "method": prov.get("method"),
                      "opportunity": f.get("opportunity") or None})
    blocked = latest.get("blocked_sources") or []
    unmeasured = latest.get("unmeasured") or []
    as_of = latest.get("generated_at") or latest.get("as_of")
    return envelope("OK" if items else "UNKNOWN", items, src, provider="intel.findings",
                    as_of=str(as_of) if as_of else None, basis="measured" if items else "unknown",
                    reason=(None if items else "the latest reading holds no findings"),
                    unmeasured=unmeasured, blocked_sources=blocked,
                    changed_since_previous=latest.get("changed_since_previous"),
                    note="demand/merchandising intelligence only; no competitor instructions, "
                         "charts or photography are stored or reproduced. A 'proxy' grade is a "
                         "labelled proxy, not a measurement.")


def store_live_drift(db) -> dict:
    """Live storefront vs repo drafts, field by field (stored readings only, no network)."""
    from ...runtime import etsy_ops
    from ...store_foundation import live_state

    src = ["store_foundation.live_state.drift", "audit_log store.live_observation",
           "operating_readings etsy.shop_snapshot / store.live_drift",
           "POST /api/store/live_observation"]
    d = live_state.drift(db)
    job = etsy_ops.latest_reading(db, live_state.DRIFT_READING)
    rows = d.get("fields") or []
    items = []
    for r in rows:
        prop = r.get("proposal") or {}
        items.append({"title": r.get("label"), "field": r.get("field"),
                      "status": r.get("status"), "live_state": r.get("live_state"),
                      "live_source": r.get("live_source"), "observed_at": r.get("observed_at"),
                      "owner_configured": r.get("owner_configured"),
                      "proposal": prop.get("kind"), "proposal_why": prop.get("why"),
                      "write_allowed": False})
    counts = d.get("counts") or {}
    known = [r for r in rows if r.get("status") != live_state.UNKNOWN]
    drifted = sum(counts.get(k, 0) for k in (live_state.DRIFT, live_state.LIVE_MISSING,
                                             live_state.LIVE_UNEXPECTED, live_state.STALE,
                                             live_state.LIVE_AUTHORITATIVE_DIFFERS))
    status = ("UNKNOWN" if not known else "DEGRADED" if drifted else "OK")
    adopt = [p for p in d.get("proposals") or [] if p.get("kind") == live_state.ADOPT_LIVE_INTO_REPO]
    owner = [p for p in d.get("proposals") or [] if p.get("kind") != live_state.ADOPT_LIVE_INTO_REPO]
    return envelope(status, items, src, provider="store_foundation.live_state",
                    as_of=d.get("generated_at"), basis="measured" if known else "unknown",
                    reason=(f"no live reading of any of {len(rows)} storefront fields yet: record "
                            "what the live shop shows (POST /api/store/live_observation) or run "
                            "etsy.shop_snapshot after re-authorisation" if not known else
                            f"{drifted} field(s) differ from the repo drafts" if drifted else None),
                    counts=counts, repo_proposals=adopt, owner_instructions=owner,
                    writes_performed=d.get("writes_performed", 0),
                    last_drift_job_at=(job or {}).get("generated_at") if job else None,
                    rule="software never writes to the live Etsy shop: repo proposals are "
                         "ADOPT_LIVE_INTO_REPO only; every other proposal is an instruction "
                         "for the owner")


_READINESS_MEMO: dict = {}
READINESS_TTL = timedelta(minutes=10)


def store_readiness(db, *, now: datetime | None = None) -> dict:
    """STORE_READINESS counts (store_foundation.store_readiness.build), memoised 10 minutes."""
    from ...store_foundation import store_readiness as sr

    now = now or datetime.now(timezone.utc)
    hit = _READINESS_MEMO.get("report")
    if not hit or now - hit[0] > READINESS_TTL:
        hit = (now, sr.build(db, now=now))
        _READINESS_MEMO["report"] = hit
    rep = hit[1]
    counts = rep.get("counts") or {}
    items = [{"title": it.get("item"), "id": it.get("id"), "area": it.get("area"),
              "status": it.get("status"), "gate": it.get("gate") or None,
              "owner_action": it.get("owner_action")}
             for it in rep.get("items") or [] if it.get("status") != "PROVEN"]
    defects = counts.get("OPEN-DEFECT", 0)
    return envelope("DEGRADED" if defects else "OK", items,
                    ["store_foundation.store_readiness.build",
                     "research/final_build/w4/STORE_READINESS.json"],
                    provider="store_foundation.store_readiness", as_of=rep.get("generated_at"),
                    reason=(f"{defects} open defect(s)" if defects else None),
                    counts=counts, total=sum(counts.values()) if counts else None,
                    phase=rep.get("phase"),
                    note="items listed are the ones not yet PROVEN, each with its exact gate")


def visual_status_path() -> Path:
    env = (os.environ.get(VISUAL_ENV) or "").strip()
    return Path(env) if env else _research_or_snapshot(VISUAL_REL)


def visual_stages() -> dict:
    """VISUAL_STATUS.json (lane VISUAL): stage A-E status with its basis, e.g. D PARTIAL (measured)."""
    path = visual_status_path()
    src = [str(VISUAL_REL) if path == _REPO / VISUAL_REL else str(path)]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return unknown(f"visual status not found at {src[0]}", "visual.status", src)
    except (OSError, ValueError) as exc:
        return unknown(f"visual status unreadable: {type(exc).__name__}", "visual.status", src)
    items = []
    for st in data.get("stages") or []:
        if not isinstance(st, dict):
            continue
        status = str(st.get("status") or "UNKNOWN").upper()
        measured = bool(st.get("evidence")) and status in ("PASS", "PARTIAL", "FAIL")
        basis = "measured" if measured else "unknown"
        items.append({"title": f"Stage {st.get('stage')}: {status} ({basis})",
                      "stage": st.get("stage"), "status": status, "basis": basis,
                      "class": st.get("class"), "evidence": st.get("evidence"),
                      "superseded_display": st.get("dashboard_said"),
                      "unknown_local": st.get("unknown_local"),
                      "unknown_paid": st.get("unknown_paid"), "next": st.get("next")})
    gen = data.get("generated_at")
    worst = {i["status"] for i in items}
    return envelope("UNKNOWN" if not items else "OK" if worst <= {"PASS"} else "DEGRADED",
                    items, src, provider="visual.status", basis="measured" if items else "unknown",
                    as_of=str(gen) if gen else None,
                    release_artefact=release_artefact(
                        "visual R&D milestone stages A-E (VISUAL_STATUS.json)", gen,
                        source=src[0]),
                    reason=None if items else "no stages in the visual status file",
                    stage_display={i["stage"]: f"{i['status']} ({i['basis']})" for i in items},
                    launch_imagery=data.get("launch_imagery"))


def visual_pipeline_live(db) -> dict:
    """W4-CCGAP: the operating visual pipeline from runtime rows: per product release, the
    planned listing frames (`listing_assets`: approved / blocked) and the latest listing-set
    certificate (`listing_set_certificates`: state, frame jobs, issued_at). Nothing recorded
    -> UNKNOWN with the reason, never 0 frames."""
    from sqlalchemy import func as _f

    from ...core.models import ListingAsset, ListingSetCertificateRecord

    src = ["listing_assets", "listing_set_certificates"]
    with db.session() as s:
        assets = list(s.execute(select(
            ListingAsset.product_slug, ListingAsset.version, _f.count(),
            _f.sum(ListingAsset.approved.cast(Integer)),
            _f.max(ListingAsset.created_at)).group_by(
            ListingAsset.product_slug, ListingAsset.version)))
        blocked = {}
        for slug, ver, reasons in s.execute(select(ListingAsset.product_slug,
                                                   ListingAsset.version,
                                                   ListingAsset.blocked_reasons)):
            if reasons:
                blocked[(slug, ver)] = blocked.get((slug, ver), 0) + 1
        certs = {}
        for c in s.scalars(select(ListingSetCertificateRecord)
                           .order_by(ListingSetCertificateRecord.id.desc())):
            certs.setdefault((c.product_slug, c.version), c)
        cert_rows = {k: {"state": c.state,
                         "jobs": sorted({str(f.get("job")) for f in (c.certificate or {})
                                         .get("frames") or [] if f.get("job")}),
                         "issued_at": _iso(c.issued_at), "id": c.id}
                     for k, c in certs.items()}
    keys = sorted({(a[0], a[1]) for a in assets} | set(cert_rows))
    if not keys:
        return unknown("no listing frame or listing-set certificate is recorded in this "
                       "database yet (assets.build / release gates have not run here)",
                       "company.visual_pipeline_live", src)
    by_asset = {(a[0], a[1]): a for a in assets}
    items, latest = [], None
    for k in keys:
        a, c = by_asset.get(k), cert_rows.get(k)
        planned = int(a[2]) if a else None
        approved = int(a[3] or 0) if a else None
        at = max([x for x in (_iso(a[4]) if a else None, c["issued_at"] if c else None) if x],
                 default=None)
        latest = max([x for x in (latest, at) if x], default=None)
        cert_state = c["state"] if c else None
        st = ("OK" if cert_state == "valid" else
              "BLOCKED" if blocked.get(k) else "DEGRADED" if a or c else "UNKNOWN")
        items.append({
            "title": f"{k[0]} v{k[1]}", "product": k[0], "version": k[1], "status": st,
            "frames_planned": planned, "frames_approved": approved,
            "frames_blocked": blocked.get(k, 0) if a else None,
            "certificate": cert_state or "none issued",
            "certified_jobs": ", ".join(c["jobs"]) if c and c["jobs"] else None,
            "last_change_at": at,
            "source": (f"listing_set_certificates:{c['id']}" if c else
                       f"listing_assets:{k[0]}@{k[1]}")})
    worst = {i["status"] for i in items}
    status = ("OK" if worst == {"OK"} else "BLOCKED" if "BLOCKED" in worst else "DEGRADED")
    return envelope(status, items, src, provider="company.visual_pipeline_live",
                    as_of=latest, live=True,
                    reason=(None if status == "OK" else
                            f"{sum(1 for i in items if i['status'] != 'OK')} of {len(items)} "
                            "release(s) without a valid listing-set certificate"))


# ---- W4-LEARN wiring (W4L-2): what learning can measure before a sale ----------------------


def learn_outcomes(db, improve: dict | None = None) -> dict:
    """Pre-sale internal outcomes (N / 9, never customer outcomes), the capability cells that
    can only be measured after launch, and the CA$5,000/month model state. UNMEASURED is
    shown as UNMEASURED, never 0 / 0.00."""
    if not isinstance(improve, dict) or "presale" not in improve:
        from ...learn import improvement_status

        improve = improvement_status.summary(db)
    pre = improve.get("presale") or {}
    cells = improve.get("cells") or {}
    items = []
    n, of = pre.get("measured"), pre.get("of")
    items.append({"metric": "presale_outcomes_measured", "label": "pre-sale outcomes measured "
                  "(internal, not customer outcomes)",
                  "value": f"{n} / {of}" if isinstance(n, int) else "UNKNOWN",
                  "state": "MEASURED" if isinstance(n, int) else "UNKNOWN",
                  "why": pre.get("reason") or pre.get("note")})
    if "error" in cells or not cells:
        items.append({"metric": "capability_cells", "label": "capability cells measured",
                      "value": "UNKNOWN", "state": "UNKNOWN",
                      "why": cells.get("error") or "cells not reported"})
    else:
        items.append({"metric": "capability_cells", "label": "capability cells measured",
                      "value": f"{cells.get('measured')} / {cells.get('cells')}",
                      "state": "MEASURED"})
        pl = list(cells.get("post_launch_only") or [])
        items.append({"metric": "post_launch_only_cells", "label": "cells measurable only "
                      "after launch (DATA-GATED: no customer evidence yet)",
                      "value": ", ".join(pl) if pl else "none", "count": len(pl),
                      "state": "DATA-GATED" if pl else "MEASURED"})
    try:
        from ...scale.confidence import probability

        p = probability(db)
        items.append({"metric": "ca5k_model", "label": "modelled probability of CA$5,000/month",
                      "value": p.get("display"), "state": p.get("state"),
                      "why": None if p.get("state") == "MEASURED" else
                      "evidence gate unmet: " + ", ".join(
                          sorted((p.get("evidence_gate") or {}).get("unmet") or []))})
    except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never 0.00
        items.append({"metric": "ca5k_model", "label": "modelled probability of CA$5,000/month",
                      "value": "UNKNOWN", "state": "UNKNOWN",
                      "why": f"unreadable: {type(exc).__name__}"})
    return envelope("OK", items, ["learn.improvement_status.summary", "improve.presale",
                                  "improve.cells", "scale.confidence.probability"],
                    provider="learn.outcomes", basis="measured")


# ---- W4-OWNER wiring: the consolidated owner decision packet -------------------------------

OWNER_ACTIONS_ENV = "BRAMBLELOOP_OWNER_ACTIONS"
OWNER_ACTIONS_REL = Path("research") / "final_build" / "w4" / "OWNER_ACTIONS.json"


def _cost_display(item: dict) -> str:
    disp = item.get("max_cost_display")
    if disp:
        return str(disp)
    v = item.get("max_cost_cad")
    return f"CA${v:,.2f}" if isinstance(v, (int, float)) else "UNKNOWN (not costed)"


def _batch_items(batches: list) -> list[dict]:
    items = []
    for b in batches:
        decs = []
        for it in b.get("items") or []:
            decs.append({"id": it.get("id"), "decision": it.get("decision"),
                         "why": it.get("why"), "evidence": it.get("evidence"),
                         "max_cost": _cost_display(it), "max_cost_cad": it.get("max_cost_cad"),
                         "max_cost_basis": it.get("max_cost_basis"),
                         "consequence_of_yes": it.get("consequence_of_yes"),
                         "consequence_of_no": it.get("consequence_of_no"),
                         "minutes": it.get("minutes"),
                         "fields_missing": it.get("fields_missing") or []})
        items.append({"id": b.get("id"), "title": b.get("title"),
                      "why_batched": b.get("why_batched"),
                      "decisions": b.get("decisions", len(decs)),
                      "minutes_total": b.get("minutes_total"),
                      "max_cost": b.get("max_cost_display") or (
                          f"CA${b['max_cost_cad_total']:,.2f}"
                          if isinstance(b.get("max_cost_cad_total"), (int, float))
                          else "UNKNOWN (at least one item is not costed)"),
                      "items": decs})
    return items


def owner_decision_batches(live: dict | None = None) -> dict:
    """Owner decisions, batch first. W4-CCGAP: LIVE first -- the running system's own
    `approval_inbox()["batches"]` (gate states + owner_actions rows, read on every request).
    The committed OWNER_ACTIONS.json packet is a release artefact: decisions it lists that the
    runtime does not track are shown separately as `release_only`, labelled with the release,
    never merged into the live count. A cost the producer did not state is UNKNOWN, never CA$0."""
    env = (os.environ.get(OWNER_ACTIONS_ENV) or "").strip()
    path = Path(env) if env else _research_or_snapshot(OWNER_ACTIONS_REL)
    src_file = str(OWNER_ACTIONS_REL) if not env else env
    data, why = None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        why = f"decision packet not found at {src_file}"
    except (OSError, ValueError) as exc:
        why = f"decision packet unreadable: {type(exc).__name__}"
    snap_batches = (data or {}).get("batches")
    snap_batches = snap_batches if isinstance(snap_batches, list) else []
    live_batches = (live or {}).get("batches") if isinstance(live, dict) else None
    # approval_inbox() returns owner_queue.batch_cards(cards): {"batches": [...], ...}.
    # c131f07 compared that dict against `list`, so the live batches were never used.
    if isinstance(live_batches, dict):
        live_batches = live_batches.get("batches")
    live_ok = isinstance(live_batches, list)
    live_items = _batch_items(live_batches) if live_ok else []
    live_ids = {d["id"] for b in live_items for d in b["items"]}
    release_only = []
    for b in _batch_items(snap_batches):
        extra = [d for d in b["items"] if d["id"] not in live_ids]
        if extra:
            release_only.append({**b, "items": extra, "decisions": len(extra),
                                 "minutes_total": None, "max_cost": None})
    label = (release_artefact("owner decision packet (OWNER_ACTIONS.json)",
                              (data or {}).get("generated_at"), source=src_file)
             if snap_batches else None)
    note = ("answer batch by batch; each decision states why, evidence, max cost (UNKNOWN when "
            "not costed, never CA$0), what yes and no/delay mean, and minutes")
    if not live_ok:
        if not snap_batches:
            return unknown(why or "no decision batches reported", "owner.decision_batches",
                           [src_file, "build2.executor.approval_inbox"])
        items = _batch_items(snap_batches)
        # The batches are the release packet's own, shown as such (labelled, as_of = its
        # generation time), never as the live queue.
        return envelope("OK", items, [src_file], provider="owner.decision_batches",
                        as_of=(data or {}).get("generated_at"), basis="measured", live=False,
                        release_artefact=label, batches=len(items),
                        decisions=sum(int(i["decisions"] or 0) for i in items),
                        live_runtime_decisions=None, release_only=[],
                        reason=("the live owner queue reported no batches; showing the "
                                "release packet, which may be out of date"), note=note)
    return envelope("OK", live_items, ["build2.executor.approval_inbox()['batches'] (live)"],
                    provider="owner.decision_batches", as_of=now_iso(), basis="measured",
                    live=True, batches=len(live_items),
                    decisions=sum(int(i["decisions"] or 0) for i in live_items),
                    live_runtime_decisions=sum(int(i["decisions"] or 0) for i in live_items),
                    release_only=release_only,
                    release_only_decisions=sum(b["decisions"] for b in release_only),
                    release_artefact=label if release_only else None,
                    release_only_note=("listed in the release packet but not tracked by the "
                                       "running system (account screens, physical or "
                                       "off-platform steps); it may already be done -- the "
                                       "runtime cannot tell" if release_only else None),
                    note=note)


# ---- completion board -------------------------------------------------------------------

BOARD_ENV = "BRAMBLELOOP_COMPLETION_BOARD"
BOARD_REL = Path("research") / "final_build" / "w4" / "COMPLETION_BOARD.json"
BOARD_KIND = "brambleloop.completion_board"
BOARD_STATUSES = ("QUEUED", "RUNNING", "BLOCKED", "REVIEW", "MERGED", "DONE", "ABANDONED",
                  "UNKNOWN")
BOARD_REQUIRED = ("lane", "worker", "task", "status", "started_at", "last_update_at",
                  "useful_output", "blocker", "next_action", "rows_closed")
#: A RUNNING lane whose last update is older than this is flagged STALE on the page.
LANE_STALE_AFTER = timedelta(hours=3)


def board_path() -> Path:
    env = (os.environ.get(BOARD_ENV) or "").strip()
    if env:
        return Path(env)
    return _research_or_snapshot(BOARD_REL)


def _parse_ts(v):
    if v in (None, ""):
        return None
    try:
        return _aware(datetime.fromisoformat(str(v).replace("Z", "+00:00")))
    except ValueError:
        return "bad"


#: The integrator's board format (wave4.completion_board.v1): lowercase status, `responsible`,
#: `started`/`last_update`, `rows_closed` as a plain id list. Normalised to the CC schema above.
INTEG_SCHEMA = "wave4.completion_board.v1"
_INTEG_KEYS = {"responsible": "worker", "started": "started_at", "last_update": "last_update_at"}
_INTEG_STATUS = {"pending": "QUEUED", "queued": "QUEUED", "running": "RUNNING",
                 "in_progress": "RUNNING", "blocked": "BLOCKED", "review": "REVIEW",
                 "merged": "MERGED", "done": "DONE", "complete": "DONE",
                 "abandoned": "ABANDONED", "unknown": "UNKNOWN", "completed": "DONE",
                 "stopped": "BLOCKED", "failed": "BLOCKED", "waiting": "QUEUED"}


def _integ_status(text) -> str:
    """The integrator writes free text ("running (resumed ...)", "complete; merged on ...").
    The leading word decides; "merged" anywhere upgrades DONE to MERGED. Anything unreadable
    is UNKNOWN (the verbatim text stays in `status_text`), never guessed into progress."""
    if text is None:
        return "UNKNOWN"
    low = str(text).strip().lower()
    m = re.match(r"[a-z_]+", low)
    st = _INTEG_STATUS.get(m.group(0), "UNKNOWN") if m else "UNKNOWN"
    if st == "DONE" and "merged" in low:
        return "MERGED"
    return st


def normalize_board(board):
    """Map the integrator's v1 board onto the CC schema; any other object passes through.

    An empty `rows_closed` list on a lane that is not DONE/MERGED means "nothing reported
    yet", so its count is UNKNOWN (None), never 0. An unreadable status is UNKNOWN with the
    integrator's text kept in `status_text`.
    """
    if not (isinstance(board, dict) and board.get("schema") == INTEG_SCHEMA):
        return board
    lanes = []
    for ln in board.get("lanes") or []:
        if not isinstance(ln, dict):
            lanes.append(ln)
            continue
        out = dict(ln)
        for src, dst in _INTEG_KEYS.items():
            if dst not in out:
                out[dst] = ln.get(src)
        # The integrator omits these on freshly added lanes; absent = not reported = shown
        # as Unknown (null), exactly as an explicit null is.
        for k in ("useful_output", "blocker", "next_action"):
            out.setdefault(k, None)
        out["status_text"] = ln.get("status")
        out["status"] = _integ_status(ln.get("status"))
        rc = ln.get("rows_closed")
        if isinstance(rc, list):
            ids = [str(x) for x in rc]
            out["rows_closed"] = {"count": len(ids) if ids or out["status"] in
                                  ("DONE", "MERGED") else None, "ids": ids}
        lanes.append(out)
    return {**board, "kind": BOARD_KIND, "schema_version": 1, "source_schema": INTEG_SCHEMA,
            "updated_by": board.get("updated_by") or "integrator", "lanes": lanes}


def validate_board(board) -> list[str]:
    """Schema problems in a completion board (empty list = valid). See COMPLETION_BOARD.json."""
    errs: list[str] = []
    board = normalize_board(board)
    if not isinstance(board, dict):
        return ["board is not a JSON object"]
    if board.get("kind") != BOARD_KIND:
        errs.append(f"kind must be {BOARD_KIND!r}")
    if board.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    if _parse_ts(board.get("updated_at")) in (None, "bad"):
        errs.append("updated_at must be an ISO 8601 UTC timestamp")
    lanes = board.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        errs.append("lanes must be a non-empty list")
        return errs
    seen = set()
    for i, ln in enumerate(lanes):
        where = f"lanes[{i}]"
        if not isinstance(ln, dict):
            errs.append(f"{where} is not an object")
            continue
        missing = [k for k in BOARD_REQUIRED if k not in ln]
        if missing:
            errs.append(f"{where} missing {missing}")
        if ln.get("lane") in seen:
            errs.append(f"{where} duplicate lane {ln.get('lane')!r}")
        seen.add(ln.get("lane"))
        if ln.get("status") not in BOARD_STATUSES:
            errs.append(f"{where} status must be one of {BOARD_STATUSES}")
        for k in ("started_at", "last_update_at"):
            if _parse_ts(ln.get(k)) == "bad":
                errs.append(f"{where} {k} is not ISO 8601")
        rc = ln.get("rows_closed")
        if rc is not None and not (isinstance(rc, dict) and (
                rc.get("count") is None or (isinstance(rc.get("count"), int)
                                            and rc["count"] >= 0))
                and isinstance(rc.get("ids", []), list)):
            errs.append(f"{where} rows_closed must be null or {{count:int|null, ids:[...]}}")
    return errs


def _baseline(board: dict):
    """The owner-dashboard scoreboard the board was seeded from: a dated snapshot, not live."""
    b = board.get("scoreboard_baseline_from_owner_dashboard")
    if not isinstance(b, dict) or not b:
        return None
    return {"values": b, "basis": "snapshot", "as_of": board.get("updated_at"),
            "note": "owner-dashboard figures copied into the board when the wave started; "
                    "the live figures are on the Company view"}


def live_company_work(db) -> dict:
    """W4-CCGAP: what the operating company is doing now, from `jobs` (not the dev board):
    running jobs and the last 24 h of completed / failed work."""
    from ...core.models import Job, JobStatus

    def read():
        jw = readers.jobs_window(db, 24)
        with db.session() as s:
            running = list(s.execute(select(Job.id, Job.agent, Job.job_type, Job.started_at)
                                     .where(Job.status == JobStatus.RUNNING)
                                     .order_by(Job.id.desc()).limit(20)))
            pending = s.scalar(select(func.count()).select_from(Job).where(
                Job.status == JobStatus.PENDING)) or 0
        items = [{"title": f"{r.agent}: {r.job_type}", "status": "RUNNING",
                  "started_at": _iso(r.started_at), "source": f"jobs:{r.id}"} for r in running]
        if jw.get("status") != "OK":
            return {**jw, "items": items}
        return envelope("OK", items, ["jobs"], provider="company.live_work", live=True,
                        running=len(items), pending=int(pending),
                        completed_24h=jw.get("completed"), failed_24h=jw.get("failed"),
                        by_agent_24h=jw.get("items"),
                        last_useful_action=jw.get("last_useful_action"),
                        note="company agents' jobs from the jobs table, live on every read")

    return guard("live_work", read, sources=["jobs"])


def completion(db=None, *, now: datetime | None = None) -> dict:
    """The completion board as an envelope; UNKNOWN when absent, DEGRADED when malformed."""
    now = now or datetime.now(timezone.utc)
    path = board_path()
    src = [str(BOARD_REL) if path == Path(__file__).resolve().parents[4] / BOARD_REL
           else str(path)]
    try:
        board = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return unknown(f"completion board not found at {src[0]} (in the deployed image the "
                       "research/ tree is only present when the Dockerfile copies it)",
                       "company.completion", src)
    except (OSError, ValueError) as exc:
        return unknown(f"completion board unreadable: {type(exc).__name__}",
                       "company.completion", src)
    board = normalize_board(board)
    errs = validate_board(board)
    lanes = board.get("lanes") if isinstance(board, dict) and isinstance(board.get("lanes"),
                                                                           list) else []
    items = []
    for ln in lanes:
        if not isinstance(ln, dict):
            continue
        last = _parse_ts(ln.get("last_update_at"))
        stale = bool(ln.get("status") == "RUNNING" and isinstance(last, datetime)
                     and now - last > LANE_STALE_AFTER)
        rc = ln.get("rows_closed")
        items.append({**{k: ln.get(k) for k in BOARD_REQUIRED},
                      "branch": ln.get("branch"), "head_sha": ln.get("head_sha"),
                      "detail": ln.get("detail"), "status_text": ln.get("status_text"),
                      "rows_closed_count": (rc.get("count") if isinstance(rc, dict) else None),
                      "stale": stale,
                      "title": f"{ln.get('lane')}: {ln.get('task')}",
                      "source": f"{src[0]}#{ln.get('lane')}"})
    counts = {s: sum(1 for i in items if i.get("status") == s) for s in BOARD_STATUSES}
    known_rc = [i["rows_closed_count"] for i in items if isinstance(i["rows_closed_count"], int)]
    updated = _parse_ts(board.get("updated_at")) if isinstance(board, dict) else None
    status = ("DEGRADED" if errs else "BLOCKED" if counts["BLOCKED"] else
              "DEGRADED" if any(i["stale"] for i in items) else "OK")
    return envelope(status, items, src, provider="company.completion",
                    as_of=updated.isoformat() if isinstance(updated, datetime) else None,
                    basis="measured" if not errs else "unknown",
                    board_updated_at=updated.isoformat() if isinstance(updated, datetime)
                    else None,
                    board_age_minutes=(round((now - updated).total_seconds() / 60, 1)
                                       if isinstance(updated, datetime) else None),
                    updated_by=board.get("updated_by") if isinstance(board, dict) else None,
                    counts=counts,
                    rows_closed_total=(sum(known_rc) if known_rc else None),
                    rows_closed_lanes_unknown=sum(1 for i in items
                                                  if i["rows_closed_count"] is None),
                    stale=[i["lane"] for i in items if i["stale"]],
                    source_schema=(board.get("source_schema") or board.get("kind")
                                   if isinstance(board, dict) else None),
                    baseline=(_baseline(board) if isinstance(board, dict) else None),
                    schema_errors=errs,
                    reason=("board schema errors: " + "; ".join(errs[:5]) if errs else
                            f"{counts['BLOCKED']} lane(s) blocked" if counts["BLOCKED"] else
                            None),
                    note=("as_of is the board's updated_at: the integrator updates the "
                          "committed JSON; in production it is as fresh as the last deploy"),
                    release_artefact=(None if (os.environ.get(BOARD_ENV) or "").strip() else
                                      release_artefact(
                                          "Claude development lane board (COMPLETION_BOARD.json)",
                                          updated.isoformat() if isinstance(updated, datetime)
                                          else None, source=src[0])))


# W4-BOARD: the finish-line board for Build 2 + the Final Master, generated by
# research/final_build/w4/completion_board_final.py from the ledgers and production GETs. The
# Command Center serves its compact card (counts + top root causes + critical path), read-only;
# the image carries the shipped snapshot of the same file.
FINISH_ENV = "BRAMBLELOOP_FINISH_LINE_CARD"
FINISH_REL = Path("research") / "final_build" / "w4" / "COMPLETION_BOARD_FINAL_CARD.json"
FINISH_CLASSES = ("verified_complete", "implemented_unverified", "in_progress",
                  "blocked_engineering", "blocked_owner", "blocked_external")


def finish_line_path() -> Path:
    env = (os.environ.get(FINISH_ENV) or "").strip()
    return Path(env) if env else _research_or_snapshot(FINISH_REL)


def finish_line() -> dict:
    """The finish-line card as an envelope. A missing count is UNKNOWN (null), never 0; a
    malformed card is DEGRADED. Generated counts only -- this reader closes nothing."""
    path = finish_line_path()
    src = [str(FINISH_REL), "research/final_build/w4/COMPLETION_BOARD_FINAL.json"]
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return unknown(f"finish-line card not found at {FINISH_REL}", "company.finish_line", src)
    except (OSError, ValueError) as exc:
        return unknown(f"finish-line card unreadable: {type(exc).__name__}",
                       "company.finish_line", src)
    head = card.get("headline") if isinstance(card, dict) else None
    problems = []
    scopes = {}
    for scope in ("build2", "final_master_launch_critical", "final_master_total"):
        c = (head or {}).get(scope)
        if not isinstance(c, dict) or not isinstance(c.get("total"), int):
            problems.append(f"{scope}: no total")
            scopes[scope] = None
            continue
        scopes[scope] = {"total": c["total"],
                         **{k: (c.get(k) if isinstance(c.get(k), int) else None)
                            for k in FINISH_CLASSES + ("not_applicable",)}}
    roots = [r for r in (card.get("top_root_causes") or []) if isinstance(r, dict)][:10]
    items = [{"title": r.get("title"), "rows": r.get("rows"),
              "fm_launch_critical": r.get("fm_launch_critical"), "build2": r.get("build2"),
              "classes": r.get("classes"), "owner_action": r.get("owner_action"),
              "source": f"{FINISH_REL}#{r.get('root')}"} for r in roots]
    status = "DEGRADED" if problems else "BLOCKED"
    lc = scopes.get("final_master_launch_critical") or {}
    if not problems and lc.get("verified_complete") == lc.get("total"):
        status = "OK"
    return envelope(status, items, src, provider="company.finish_line",
                    basis="measured", as_of=card.get("generated_at"),
                    reason=("; ".join(problems) if problems else None),
                    scopes=scopes, critical_path=card.get("critical_path") or [],
                    production_commit=card.get("production_commit"),
                    production_read_at=card.get("production_read_at"))
