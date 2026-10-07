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
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

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


def departments(db, auto: dict | None = None) -> dict:
    """Every department with owner state, current job, last useful result and next wake."""
    auto = auto if auto is not None else providers.call("autonomy", db)
    dept_of = _job_dept_fn()
    useful = _useful_fn()

    def read():
        facts = _job_facts(db)
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
                    closure=c, maturity=value["maturity"], refreshing=refreshing,
                    last_error=err,
                    reason=(None if c["closed_out"] else
                            f"{c['counts'].get('OPEN', 0)} requirement(s) OPEN"
                            if not c["closeout_indeterminate"] else
                            "gates were not read live, so closeout is indeterminate"),
                    note=("closure states come from evidence, not the registry status; "
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
    owner = readers.owner_actions_summary(db)
    box = guard("approvals", lambda: approvals.inbox(db))
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
        "build2_closure": b2,
        "final_master_closure": fm,
        "visual": visual,
        "visual_stages": guard("visual_stages", visual_stages),
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
    return Path(env) if env else _REPO / VISUAL_REL


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
                    reason=None if items else "no stages in the visual status file",
                    stage_display={i["stage"]: f"{i['status']} ({i['basis']})" for i in items},
                    launch_imagery=data.get("launch_imagery"))


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
    return Path(__file__).resolve().parents[4] / BOARD_REL


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
                 "abandoned": "ABANDONED", "unknown": "UNKNOWN"}


def normalize_board(board):
    """Map the integrator's v1 board onto the CC schema; any other object passes through.

    An empty `rows_closed` list on a lane that is not DONE/MERGED means "nothing reported
    yet", so its count is UNKNOWN (None), never 0. Unrecognised statuses are kept verbatim so
    validate_board reports them instead of guessing.
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
        st = ln.get("status")
        out["status"] = _INTEG_STATUS.get(str(st).strip().lower(), st) if st is not None \
            else "UNKNOWN"
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
                      "detail": ln.get("detail"),
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
                          "committed JSON; in production it is as fresh as the last deploy"))
