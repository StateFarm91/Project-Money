"""Laura's executive tick: Laura -> COO -> departments -> results -> Laura (D-FB-13).

One deterministic pass, run on its own cadence (`laura.executive_tick`) and woken when the
COO closes a mission she delegated:

    OBSERVE    company state from durable evidence: autonomy.status (departments), latest
               department KPI snapshots, open owner actions, unresolved incidents, defect dead
               letters, and the Finance / Learn / SEO / Ads / SLO / Visual R&D providers
    REVIEW     every mission she delegated that the COO has closed is judged with the honest
               useful-work judge (`did_no_work`, via `orchestrator.reconcile_missions`)
    CHALLENGE  weak work is challenged with evidence: a no-op delegation gets a department
               review (measure, route lessons); a failed one is reworked once; a challenge or
               rework that is itself weak is escalated as a routed Lesson -- never a loop
    PRIORITISE durable priority records, each with a reason, a score and its evidence rows
    DELEGATE   through the COO's existing mission mechanism (`orchestrator._enqueue_mission`):
               only job types the department's charter may generate AND SAFE_GENERATED lists;
               protected work becomes an owner action item; every priority and delegation
               first passes the constitution (Finance / Product Truth / Security can block)
    IDLE       when the company queue is empty she takes the highest-value evidence-driven
               candidates the departments' own generators offer, so an empty queue never
               idles the company
    RECORD     every real action is one laura.memory operational entry (lane E's durable
               memory; written once) + the company timeline event it cites

No model is called. `work_done` is the number of NEW decisions this tick; a tick that observed
an unchanged company reports 0 and the useful-work judge calls it a no-op.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

EXEC_JOB = "laura.executive_tick"
LAURA_AGENT = "laura"
ACTOR = "laura"
MAX_DELEGATIONS_PER_TICK = 4
MAX_FOLLOWONS_PER_TICK = 3
IDLE_SAFE_WORK = 2
PROVIDER_FRESH_HOURS = 24
# Job types that keep the loop itself alive; they do not make the company "busy".
CONTROL_TYPES = frozenset({EXEC_JOB, "autonomy.orchestrate", "ops.heartbeat", "ops.health",
                           "ops.queue_check"})

# provider name -> (module, department, job type that refreshes it)
PROVIDERS: dict[str, tuple[str, str, str]] = {
    "finance": ("brambleloop.finance.accounting.dashboard", "finance",
                "finance.accounting.cycle"),
    "slo": ("brambleloop.ops.slo", "platform", "ops.slo"),
    "learn": ("brambleloop.learn.improvement_status", "learn", "improve.measure"),
    "seo": ("brambleloop.seo.status", "store_commerce", "seo.cycle"),
    "ads": ("brambleloop.growth.ads_readiness", "growth", "marketing.ads_readiness"),
    "visual_rnd": ("brambleloop.visual.rnd.status", "visual", "visual.identity_drift"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _fp(obj) -> str:
    from ...autonomy.kpis import fingerprint

    return fingerprint(obj)


def cognition() -> dict:
    """Which cognition produced this tick's decisions. Swappable; never part of identity."""
    return {"engine": "deterministic",
            "model": os.environ.get("BRAMBLELOOP_LAURA_MODEL") or None,
            "note": "the executive tick calls no model; a model, if configured, would only "
                    "narrate (via the gateway, with spend recorded)"}


@dataclass
class Priority:
    rule: str
    subject: str
    department: str
    title: str
    reason: str
    score: float
    evidence: list = field(default_factory=list)
    job_type: str = ""
    inputs: dict = field(default_factory=dict)
    window: str = ""                 # delegation fingerprint window
    waiting: str = ""                # why no delegation (awaiting_owner / monitoring)

    @property
    def key(self) -> str:
        return f"laura:{self.rule}:{self.subject}"[:200]

    @property
    def evidence_fp(self) -> str:
        return _fp({"reason": self.reason, "evidence": self.evidence,
                    "job_type": self.job_type})


# ---- OBSERVE ---------------------------------------------------------------------------

def _provider(name: str) -> dict:
    import importlib

    mod_name = PROVIDERS[name][0]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError:
        return {"status": "UNKNOWN", "reason": "not built", "source": mod_name}
    return mod


def observe(db, *, now: datetime | None = None) -> dict:
    """One read of company state. Never raises; unreadable parts are UNKNOWN with a reason."""
    from ...autonomy import memory, status
    from ...core import models as m
    from ...core.models import Job, JobStatus
    from ...queue.durable import classify_dead_letter

    now = now or _now()
    state: dict = {"at": now.isoformat(), "sources": [], "errors": {}}
    try:
        st = status.summary(db, now=now)
        state["company"] = {"status": st.get("status"),
                            "departments": [{k: i.get(k) for k in (
                                "department", "status", "open_jobs", "useful_24h",
                                "dead_24h", "blockers")} for i in st.get("items", [])],
                            "orchestrator": st.get("orchestrator")}
        state["sources"].append("autonomy.status.summary")
    except Exception as exc:  # noqa: BLE001
        state["company"] = {"status": "UNKNOWN", "departments": []}
        state["errors"]["company"] = f"{type(exc).__name__}: {exc}"[:200]
    kpis = {}
    for snap in memory.recall(db, kind="kpi_snapshot", limit=200):
        if snap["department"] not in kpis:
            kpis[snap["department"]] = {"key": snap["key"],
                                        "tripped": bool((snap["body"].get("guardrails") or {})
                                                        .get("tripped")),
                                        "breaches": ((snap["body"].get("guardrails") or {})
                                                     .get("breaches") or [])[:3]}
    state["kpis"] = kpis
    state["sources"].append("company_memory:kpi_snapshot")
    since = now - timedelta(hours=24)
    with db.session() as s:
        state["owner_actions"] = {
            "open": int(s.scalar(select(func.count()).select_from(m.OwnerAction).where(
                m.OwnerAction.done == False)) or 0),  # noqa: E712
            "top": [{"id": o.id, "key": o.requirement_key, "action": o.action[:160]}
                    for o in s.execute(select(m.OwnerAction.id, m.OwnerAction.requirement_key,
                                              m.OwnerAction.action)
                                       .where(m.OwnerAction.done == False)  # noqa: E712
                                       .order_by(m.OwnerAction.id.desc()).limit(5)).all()]}
        state["incidents"] = [
            {"id": i.id, "severity": i.severity, "signature": i.signature,
             "halts_publication": bool(i.halts_publication), "product_slug": i.product_slug,
             "summary": (i.summary or "")[:160]}
            for i in s.execute(select(m.Incident.id, m.Incident.severity, m.Incident.signature,
                                      m.Incident.halts_publication, m.Incident.product_slug,
                                      m.Incident.summary)
                               .where(m.Incident.resolved == False)  # noqa: E712
                               .order_by(m.Incident.id.desc()).limit(50)).all()]
        dead = s.execute(select(Job.id, Job.job_type, Job.last_error).where(
            Job.status == JobStatus.DEAD, Job.finished_at >= since)).all()
        state["defect_dead_letters"] = [
            {"id": d.id, "job_type": d.job_type}
            for d in dead if classify_dead_letter(d.job_type, d.last_error or "") == "DEFECT"]
        open_rows = s.execute(select(Job.job_type, func.count()).where(
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]))
            .group_by(Job.job_type)).all()
    state["queue"] = {"open_by_type": {jt: int(n) for jt, n in open_rows}}
    state["queue"]["company_work_open"] = sum(
        n for jt, n in state["queue"]["open_by_type"].items() if jt not in CONTROL_TYPES)
    state["sources"] += ["owner_actions", "incidents", "jobs"]
    providers = {}
    for name in PROVIDERS:
        mod = _provider(name)
        if isinstance(mod, dict):
            providers[name] = mod
            continue
        try:
            r = mod.summary(db)
            providers[name] = {"status": r.get("status", "UNKNOWN"),
                               "reason": str(r.get("reason") or "")[:200],
                               "as_of": r.get("as_of"), "source": PROVIDERS[name][0]}
        except Exception as exc:  # noqa: BLE001 - one provider never stops her
            providers[name] = {"status": "UNKNOWN", "source": PROVIDERS[name][0],
                               "reason": f"provider raised {type(exc).__name__}"}
    state["providers"] = providers
    state["sources"] += [f"{p}.summary" for p in PROVIDERS]
    return state


# ---- PRIORITISE ------------------------------------------------------------------------

def _day(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _six_h(now: datetime) -> str:
    return f"{_day(now)}T{now.hour // 6 * 6:02d}"


def prioritise(state: dict, *, now: datetime) -> list[Priority]:
    """Deterministic priorities from observed state, highest score first."""
    out: list[Priority] = []
    for inc in [i for i in state.get("incidents", []) if i["severity"] in ("P0", "P1")][:3]:
        pt = inc["halts_publication"] or bool(inc["product_slug"])
        dept, jt = ("product_truth", "ops.sentinel") if pt else ("platform", "ops.slo")
        out.append(Priority(
            rule="incident", subject=str(inc["id"]), department=dept,
            title=f"Resolve {inc['severity']} incident #{inc['id']}",
            reason=f"unresolved {inc['severity']} {inc['signature']}: {inc['summary']}",
            score=100 if inc["severity"] == "P0" else 90,
            evidence=[f"incidents:{inc['id']}"], job_type=jt, window=_day(now)))
    for dept, k in sorted(state.get("kpis", {}).items()):
        if k["tripped"]:
            out.append(Priority(
                rule="kpi_void", subject=dept, department=dept,
                title=f"{dept} KPIs are VOID: a guardrail tripped",
                reason="; ".join(map(str, k["breaches"])) or "guardrail tripped",
                score=85, evidence=[f"company_memory:{k['key']}"],
                job_type="autonomy.department_review", inputs={"department": dept},
                window=_day(now)))
    for d in state.get("company", {}).get("departments", []):
        if d.get("status") == "DEGRADED":
            out.append(Priority(
                rule="dept_degraded", subject=d["department"], department=d["department"],
                title=f"{d['department']} is DEGRADED",
                reason=f"{d.get('dead_24h', 0)} dead and {d.get('useful_24h', 0)} useful jobs "
                       "in 24 h; measure it and route lessons",
                score=80, evidence=[f"autonomy.status:{d['department']}"],
                job_type="autonomy.department_review",
                inputs={"department": d["department"]}, window=_six_h(now)))
        elif d.get("status") == "BLOCKED":
            b = (d.get("blockers") or [{}])[0]
            out.append(Priority(
                rule="dept_blocked", subject=d["department"], department=d["department"],
                title=f"{d['department']} is blocked",
                reason=str(b.get("reason") or b.get("what") or "blocked")[:300], score=70,
                evidence=[f"autonomy.status:{d['department']}"],
                waiting="awaiting_owner"))
    dl = state.get("defect_dead_letters", [])
    if dl:
        out.append(Priority(
            rule="defects", subject="dead_letters", department="learn",
            title=f"{len(dl)} defect dead letter(s) in 24 h",
            reason="defects are mined into routed lessons before they repeat",
            score=75, evidence=[f"jobs:{d['id']}" for d in dl[:10]],
            job_type="improve.mine", window=f"{_day(now)}:{max(d['id'] for d in dl)}"))
    for name, p in sorted(state.get("providers", {}).items()):
        st = p.get("status")
        if st == "OK" or (st == "UNKNOWN" and p.get("reason") == "not built"):
            continue
        _mod, dept, jt = PROVIDERS[name]
        out.append(Priority(
            rule="provider", subject=name, department=dept,
            title=f"{name} reads {st}",
            reason=(p.get("reason") or f"{name} provider status {st}")[:300],
            score=60 if st in ("DEGRADED", "BLOCKED") else 35,
            evidence=[f"{p.get('source')}.summary:{st}"], job_type=jt, window=_day(now)))
    oa = state.get("owner_actions", {})
    if oa.get("open"):
        out.append(Priority(
            rule="owner_decisions", subject="open", department="executive",
            title=f"{oa['open']} owner decision(s) open",
            reason="only the owner can act on these; Laura keeps them visible and current",
            score=50, evidence=[f"owner_actions:{o['id']}" for o in oa.get("top", [])],
            waiting="awaiting_owner"))
    out.sort(key=lambda p: (-p.score, p.key))
    return out


def _idle_priorities(db, state: dict, *, now: datetime, taken: set) -> list[Priority]:
    """Empty queue: the departments' own evidence-driven candidates, best first."""
    from ...autonomy import charters, generators, memory, orchestrator
    from ...core.models import Job

    snap = generators.Snapshot.read(db, now)
    best = []
    for ch in orchestrator.DEPARTMENT_ORDER:
        if ch.key in taken or memory.active_block(db, ch.key, now=now):
            continue
        try:
            cands = [c for c in generators.candidates(db, ch, snap) if not c.protected]
            supp = orchestrator._suppressed(db, ch, now)
        except Exception:  # noqa: BLE001 - one department never stops the others
            continue
        cands = [c for c in cands if c.job_type not in supp
                 and c.job_type in charters.SAFE_GENERATED]
        keys = {orchestrator.mission_key(ch, c): c for c in cands}
        if not keys:
            continue
        with db.session() as s:
            done = set(s.scalars(select(Job.idempotency_key).where(
                Job.idempotency_key.in_(list(keys)))))
        fresh = sorted((c for k, c in keys.items() if k not in done), key=lambda c: -c.value)
        if fresh:
            best.append((ch, fresh[0]))
    best.sort(key=lambda t: (-t[1].value, t[0].key))
    out = []
    for ch, c in best[:IDLE_SAFE_WORK]:
        out.append(Priority(
            rule="idle_work", subject=f"{ch.key}:{c.fingerprint}"[:150], department=ch.key,
            title=f"Company queue is empty: give {ch.name} its next safe work",
            reason=f"{c.source}: {c.reason}"[:300], score=20 + c.value / 10,
            evidence=list(c.evidence)[:10], job_type=c.job_type, inputs=dict(c.inputs),
            window=c.fingerprint))
    return out


# ---- RECORD ----------------------------------------------------------------------------

class _Tick:
    def __init__(self, db, now: datetime, ident_sha: str):
        self.db, self.now, self.ident_sha = db, now, ident_sha
        self.new = 0
        self.counts: dict[str, int] = {}
        self.cog = cognition()

    def decide(self, key: str, kind: str, *, department: str, subject: str, reason: str,
               evidence: list | None = None, refs: list | None = None) -> bool:
        """Record one decision (laura.memory, operational tier) unless its key exists.
        True when written (a real new act)."""
        from ..core import history as hist

        if not hist.record(self.db, key, kind=kind, department=department, subject=subject,
                           reason=reason, evidence=list(evidence or []),
                           refs=list(refs or []), cognition=self.cog,
                           identity_sha256=self.ident_sha, at=self.now):
            return False
        self.new += 1
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return True


def _upsert_priority(db, p: Priority, now: datetime, **fields) -> tuple[bool, bool]:
    """(created, evidence_changed)."""
    from ..core.models import LauraPriority

    with db.session() as s:
        row = s.scalar(select(LauraPriority).where(LauraPriority.key == p.key))
        if row is None:
            s.add(LauraPriority(key=p.key, rule=p.rule, department=p.department,
                                title=p.title[:300], reason=p.reason, evidence=p.evidence,
                                evidence_fp=p.evidence_fp, score=p.score, job_type=p.job_type,
                                created_at=now, updated_at=now, **fields))
            return True, True
        changed = row.evidence_fp != p.evidence_fp or row.status == "closed"
        row.title, row.reason, row.evidence = p.title[:300], p.reason, p.evidence
        row.evidence_fp, row.score, row.job_type = p.evidence_fp, p.score, p.job_type
        if row.status == "closed":
            row.status, row.closed_at, row.closed_reason = "open", None, ""
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = now
        return False, changed


def _set_status(db, key: str, now: datetime, **fields) -> None:
    from ..core.models import LauraPriority

    with db.session() as s:
        row = s.scalar(select(LauraPriority).where(LauraPriority.key == key))
        if row is not None:
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = now


# ---- DELEGATE --------------------------------------------------------------------------

def _delegate(t: _Tick, queue, p: Priority, *, kind: str = "delegation",
              fingerprint: str | None = None) -> dict:
    """Constitution check, then the COO's own enqueue boundary. Returns an outcome dict."""
    from ...autonomy import charters, generators, orchestrator
    from ...core.models import Job
    from ..core import constitution

    verdict = constitution.review(t.db, {"kind": kind, "department": p.department,
                                         "job_type": p.job_type, "cost_cad": 0.0,
                                         "title": p.title}, now=t.now)
    charter = charters.BY_KEY.get(p.department)
    cand = generators.Candidate(
        department=p.department, job_type=p.job_type, value=int(p.score), source="laura",
        reason=f"Laura: {p.title} -- {p.reason}"[:300],
        fingerprint=fingerprint or (f"laura:{p.rule}:{p.subject}:{p.window}"
                                    if p.rule != "idle_work" else p.window),
        evidence=list(p.evidence)[:10],
        inputs={**p.inputs, "laura": {"priority": p.key, "kind": kind}})
    if verdict["outcome"] == "owner_action" and charter is not None:
        cand.protected = True
        cand.approval = {"requirement_key": f"laura:{p.department}:{p.job_type}",
                         "action": f"Laura requests authority for protected work: {p.title}",
                         "reason": f"{p.job_type} is protected; Laura prepared it and will not "
                                   "perform it without owner authority",
                         "max_cost_cad": 0.0, "minutes": 10,
                         "consequence": "the protected step waits", "blocks": p.department}
        orchestrator._raise_approval(t.db, charter, cand, t.now)
        t.decide(f"owner_action:{p.key}:{p.evidence_fp}", "owner_action",
                 department=p.department, subject=p.title,
                 reason="protected work converted to an owner action item",
                 evidence=p.evidence, refs=[f"owner_actions:{cand.approval['requirement_key']}"])
        return {"outcome": "owner_action", "verdict": verdict}
    if not verdict["allowed"] or charter is None:
        t.decide(f"blocked:{p.key}:{p.evidence_fp}:{','.join(verdict['blocked_by'])}",
                 "blocked", department=p.department, subject=p.title,
                 reason="; ".join(c["why"] for c in verdict["checks"]
                                  if c["outcome"] == "block")[:2000],
                 evidence=p.evidence,
                 refs=[c["ref"] for c in verdict["checks"] if c.get("ref")])
        return {"outcome": "blocked", "verdict": verdict}
    if queue is None:
        from ...queue.durable import JobQueue

        queue = JobQueue(t.db)
    key = orchestrator.mission_key(charter, cand)
    with t.db.session() as s:
        exists = s.scalar(select(Job.id).where(Job.idempotency_key == key)) is not None
    if exists:
        return {"outcome": "already_delegated", "mission_key": key, "verdict": verdict}
    try:
        mission = orchestrator._enqueue_mission(t.db, queue, charter, cand, t.now)
    except orchestrator.ProtectedActionRefused as exc:
        t.decide(f"blocked:{p.key}:{p.evidence_fp}:authority", "blocked",
                 department=p.department, subject=p.title, reason=str(exc)[:500],
                 evidence=p.evidence)
        return {"outcome": "blocked", "verdict": verdict, "error": str(exc)}
    t.decide(f"{kind}:{key}", kind, department=p.department,
             subject=f"{p.job_type} -> {p.department}: {p.title}",
             reason=p.reason, evidence=p.evidence,
             refs=[f"jobs:{mission['job_id']}", f"company_memory:{key}"])
    return {"outcome": "delegated", "mission_key": key, "job_id": mission["job_id"],
            "created": mission["created"], "verdict": verdict}


# ---- REVIEW + CHALLENGE ----------------------------------------------------------------

def _review(t: _Tick, queue) -> dict:
    """Judge every closed mission she delegated; challenge weak work with evidence."""
    from types import SimpleNamespace

    from ...autonomy import memory
    from ..core import history as hist

    decisions = hist.all_decisions(t.db)
    delegated = [SimpleNamespace(key=d["decision_key"], kind=d["kind"],
                                 department=d["department"], subject=d["subject"])
                 for d in reversed(decisions)
                 if d["kind"] in ("delegation", "challenge", "rework")]
    reviewed = {d["decision_key"] for d in decisions if d["kind"] == "review"}
    out = {"reviewed": 0, "accepted": 0, "weak": 0, "failed": 0, "open": 0, "followons": 0}
    followons = 0
    for d in delegated:
        mkey = d.key.split(":", 1)[1]
        if f"review:{mkey}"[:200] in reviewed:
            continue
        mission = memory.get(t.db, mkey)
        st = (mission or {}).get("state")
        if st not in ("useful", "noop", "failed"):
            out["open"] += 1
            continue
        body = (mission or {}).get("body") or {}
        jt = body.get("job_type", "")
        verdict = {"useful": "accepted: produced useful work",
                   "noop": "weak: completed but did no work (did_no_work)",
                   "failed": f"failed: {str(body.get('error') or '')[:200]}"}[st]
        refs = [f"company_memory:{mkey}", f"jobs:{body.get('job_id')}"]
        t.decide(f"review:{mkey}", "review", department=d.department,
                 subject=f"{jt} ({d.kind}) -> {st}", reason=verdict, refs=refs)
        out["reviewed"] += 1
        out[{"useful": "accepted", "noop": "weak", "failed": "failed"}[st]] += 1
        if st == "useful":
            _close_for_mission(t, mkey, f"delegated work reviewed: useful (jobs:"
                                        f"{body.get('job_id')})")
            continue
        _close_for_mission(t, mkey, f"delegated work reviewed: {st}")
        if followons >= MAX_FOLLOWONS_PER_TICK:
            continue
        if d.kind == "delegation":
            if st == "noop":
                p = Priority(rule="challenge", subject=mkey, department=d.department,
                             title=f"Challenge: {jt} produced no work",
                             reason=f"{jt} completed with no useful output; measure "
                                    f"{d.department}'s KPIs and route what explains it",
                             score=55, evidence=refs, job_type="autonomy.department_review",
                             inputs={"department": d.department})
                r = _delegate(t, queue, p, kind="challenge", fingerprint=f"laura:challenge:"
                                                                         f"{_fp(mkey)}")
            else:
                p = Priority(rule="rework", subject=mkey, department=d.department,
                             title=f"Rework: {jt} failed",
                             reason=f"failed once; one rework with the failure as evidence: "
                                    f"{str(body.get('error') or '')[:160]}",
                             score=65, evidence=refs, job_type=jt,
                             inputs={k: v for k, v in (body.get("inputs") or {}).items()})
                if jt == "autonomy.department_review":
                    p.inputs = {"department": d.department}
                r = _delegate(t, queue, p, kind="rework", fingerprint=f"laura:rework:"
                                                                      f"{_fp(mkey)}")
            followons += 1 if r["outcome"] == "delegated" else 0
        else:
            followons += _escalate(t, d, mkey, jt, st, refs)
    out["followons"] = followons
    return out


def _escalate(t: _Tick, d, mkey: str, jt: str, st: str, refs: list) -> int:
    """A challenge or rework that was itself weak becomes a routed Lesson, not another job."""
    from ...core.models import Lesson

    ref = f"laura_decision:{d.kind}:{mkey}"[:200]
    statement = (f"{d.department}: Laura's {d.kind} of {jt} ended {st}; the department needs "
                 "a cause, not another run")
    with t.db.session() as s:
        if s.scalar(select(Lesson.id).where(Lesson.evidence_ref == ref)) is None:
            s.add(Lesson(origin_cell=d.department[:40], subject=f"Laura escalation: {jt}"[:80],
                         statement=statement, evidence_ref=ref, confidence="observed",
                         routed_to=["learn", d.department]))
    return int(t.decide(f"escalation:{mkey}", "escalation", department=d.department,
                        subject=f"{jt} {d.kind} ended {st}", reason=statement,
                        refs=[*refs, f"lessons:{ref}"]))


def _close_for_mission(t: _Tick, mkey: str, why: str) -> None:
    from ..core.models import LauraPriority

    with t.db.session() as s:
        rows = list(s.scalars(select(LauraPriority).where(LauraPriority.mission_key == mkey,
                                                          LauraPriority.status == "delegated")))
        for r in rows:
            r.status, r.closed_at, r.closed_reason = "closed", t.now, why
            r.updated_at = t.now


# ---- TICK ------------------------------------------------------------------------------

def tick(db, queue=None, *, now: datetime | None = None) -> dict:
    """One executive pass. Idempotent: re-running on unchanged state writes no decision."""
    from ...autonomy import memory, orchestrator
    from ...autonomy.models import ensure_tables as ensure_autonomy
    from ..core import identity
    from ..core.models import LauraPriority, ensure_tables

    now = now or _now()
    ensure_tables(db)
    ensure_autonomy(db)
    ident = identity.ensure(db)            # IdentityTampered stops the tick: fail closed
    t = _Tick(db, now, ident["sha256"])
    report: dict = {"at": now.isoformat(), "identity_sha256": ident["sha256"],
                    "identity_version": ident["version"], "cognition": t.cog}
    # MEASURE first, so the review reads closed missions (idempotent with the COO's own).
    report["reconciled"] = orchestrator.reconcile_missions(db, now=now)
    report["review"] = _review(t, queue)
    state = observe(db, now=now)
    report["observed"] = {"company": state["company"].get("status"),
                          "providers": {k: v.get("status") for k, v in
                                        state["providers"].items()},
                          "owner_actions_open": state["owner_actions"]["open"],
                          "incidents_open": len(state["incidents"]),
                          "company_work_open": state["queue"]["company_work_open"],
                          "errors": state["errors"]}
    prios = prioritise(state, now=now)
    idle = state["queue"]["company_work_open"] == 0
    if idle:
        prios += _idle_priorities(db, state, now=now,
                                  taken={p.department for p in prios if p.job_type})
    report["idle"] = idle
    delegated = idle_delegated = 0
    outcomes = []
    seen = set()
    for p in prios:
        if p.key in seen:
            continue
        seen.add(p.key)
        created, changed = _upsert_priority(db, p, now)
        if created or changed:
            t.decide(f"priority.set:{p.key}:{p.evidence_fp}", "priority.set",
                     department=p.department, subject=p.title,
                     reason=f"score {p.score:g}: {p.reason}", evidence=p.evidence)
        if p.waiting or not p.job_type:
            _set_status(db, p.key, now, status=p.waiting or "open")
            outcomes.append({"priority": p.key, "outcome": p.waiting or "open"})
            continue
        if state["queue"]["open_by_type"].get(p.job_type):
            _set_status(db, p.key, now, status="in_progress")
            outcomes.append({"priority": p.key, "outcome": "in_progress"})
            continue
        if p.rule == "provider" and state["providers"].get(p.subject, {}).get(
                "status") == "UNKNOWN" and _ran_recently(db, p.job_type, now):
            _set_status(db, p.key, now, status="monitoring")
            outcomes.append({"priority": p.key, "outcome": "monitoring",
                             "why": f"{p.job_type} ran inside {PROVIDER_FRESH_HOURS} h; "
                                    "still UNKNOWN means no data yet, not a fault"})
            continue
        cap_used = idle_delegated if p.rule == "idle_work" else delegated
        if cap_used >= (IDLE_SAFE_WORK if p.rule == "idle_work" else MAX_DELEGATIONS_PER_TICK):
            outcomes.append({"priority": p.key, "outcome": "deferred"})
            continue
        r = _delegate(t, queue, p)
        status = {"delegated": "delegated", "already_delegated": "delegated",
                  "blocked": "blocked", "owner_action": "awaiting_owner"}[r["outcome"]]
        fields = {"status": status, "constitution": {
            "outcome": r["verdict"]["outcome"], "blocked_by": r["verdict"]["blocked_by"]}}
        if r.get("mission_key"):
            fields["mission_key"] = r["mission_key"]
        if r["outcome"] == "already_delegated":
            # Delegated earlier in this window (and possibly already reviewed): watch it;
            # the next window or new evidence re-delegates.
            fields["status"] = "monitoring"
        _set_status(db, p.key, now, **fields)
        if r["outcome"] == "delegated":
            if p.rule == "idle_work":
                idle_delegated += 1
            else:
                delegated += 1
        outcomes.append({"priority": p.key, "outcome": r["outcome"],
                         "blocked_by": r["verdict"]["blocked_by"]})
    # Close priorities whose condition is no longer observed (delegated ones close on review).
    with db.session() as s:
        stale = list(s.scalars(select(LauraPriority).where(
            LauraPriority.status.in_(["open", "blocked", "awaiting_owner", "monitoring",
                                      "in_progress"]),
            LauraPriority.key.not_in(list(seen) or [""]))))
        closing = [(r.key, r.department, r.title, r.evidence_fp) for r in stale]
        for r in stale:
            r.status, r.closed_at = "closed", now
            r.closed_reason, r.updated_at = "condition no longer observed", now
    for key, dept, title, efp in closing:
        t.decide(f"priority.closed:{key}:{efp}", "priority.closed", department=dept,
                 subject=title, reason="condition no longer observed in company state",
                 evidence=[f"laura_priorities:{key}"])
    report.update(priorities=[{"key": p.key, "score": p.score, "department": p.department,
                               "title": p.title, "job_type": p.job_type} for p in prios],
                  outcomes=outcomes, delegated=delegated + idle_delegated,
                  idle_delegated=idle_delegated, new_decisions=t.new,
                  decisions_by_kind=t.counts)
    memory.remember(db, "laura:last_tick", kind="laura_tick", department="executive",
                    subject="Laura's last executive tick", state="ok",
                    body={k: report[k] for k in ("at", "identity_sha256", "identity_version",
                                                 "cognition", "review", "observed", "idle",
                                                 "delegated", "new_decisions",
                                                 "decisions_by_kind")},
                    sources=state["sources"], now=now)
    return report


def _ran_recently(db, job_type: str, now: datetime) -> bool:
    from ...core.models import Job, JobStatus

    with db.session() as s:
        last = s.scalar(select(func.max(Job.finished_at)).where(
            Job.job_type == job_type, Job.status == JobStatus.DONE))
    last = _aware(last)
    return last is not None and now - last <= timedelta(hours=PROVIDER_FRESH_HOURS)


def results_wake(db, queue, *, now: datetime | None = None) -> bool:
    """Event wake (results -> Laura): a mission she delegated was closed and is unreviewed.
    Keyed per five minutes, so it cannot flood."""
    from ...autonomy import memory
    from ...queue.durable import DuplicateJob
    from ..core import history as hist

    now = now or _now()
    decisions = hist.all_decisions(db)
    keys = [d["decision_key"].split(":", 1)[1] for d in decisions
            if d["kind"] in ("delegation", "challenge", "rework")][:200]
    reviewed = {d["decision_key"] for d in decisions if d["kind"] == "review"}
    pending = [k for k in keys if f"review:{k}"[:200] not in reviewed
               and (memory.get(db, k) or {}).get("state") in ("useful", "noop", "failed")]
    if not pending:
        return False
    try:
        queue.enqueue(LAURA_AGENT, EXEC_JOB, {"wake": "results"},
                      idempotency_key=f"{EXEC_JOB}:results:{int(now.timestamp() // 300)}")
        return True
    except DuplicateJob:
        return False


# ---- read API (Command Center, lane F) ---------------------------------------------------

def priorities(db, *, status: str | None = None, limit: int = 50) -> list[dict]:
    from ..core.models import LauraPriority, ensure_tables

    ensure_tables(db)
    q = select(LauraPriority).order_by(LauraPriority.updated_at.desc(),
                                       LauraPriority.id.desc()).limit(limit)
    if status:
        q = q.where(LauraPriority.status == status)
    with db.session() as s:
        return [{"key": r.key, "rule": r.rule, "department": r.department, "title": r.title,
                 "reason": r.reason, "evidence": r.evidence, "score": r.score,
                 "status": r.status, "job_type": r.job_type, "mission_key": r.mission_key,
                 "constitution": r.constitution, "closed_reason": r.closed_reason,
                 "created_at": _aware(r.created_at).isoformat() if r.created_at else None,
                 "updated_at": _aware(r.updated_at).isoformat() if r.updated_at else None}
                for r in s.scalars(q)]


def history(db, *, limit: int = 50, kind: str | None = None) -> list[dict]:
    """Her decisions, newest first, read from laura.memory (operational tier)."""
    from ..core import history as hist

    out = []
    for d in hist.all_decisions(db):
        if kind and d["kind"] != kind:
            continue
        out.append({"key": d["decision_key"], "at": d.get("at"), "kind": d["kind"],
                    "department": d.get("department", ""), "subject": d.get("subject", ""),
                    "reason": d.get("reason", ""), "evidence": d.get("evidence", []),
                    "refs": d.get("refs", []), "cognition": d.get("cognition", {}),
                    "identity_sha256": d.get("identity_sha256", ""),
                    "memory_ref": d.get("memory_ref")})
        if len(out) >= limit:
            break
    return out


def summary(db) -> dict:
    """Command Center provider: what Laura is prioritising, delegating and concluding."""
    try:
        from ...autonomy import memory
        from ..core import constitution
        from ..core import history as hist
        from ..core.models import ensure_tables

        ensure_tables(db)
        last = memory.get(db, "laura:last_tick")
        by_kind: dict[str, int] = {}
        for d in hist.all_decisions(db):
            by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
        reviews = history(db, kind="review", limit=500)
        verdicts = {"useful": 0, "noop": 0, "failed": 0}
        for r in reviews:
            for k in verdicts:
                if r["subject"].endswith(f"-> {k}"):
                    verdicts[k] += 1
        open_p = [p for p in priorities(db, limit=100) if p["status"] != "closed"]
        if last is None:
            return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": open_p,
                    "sources": ["laura_priorities", "laura_memory:operational:decision/*"],
                    "reason": "Laura's executive tick has not run here yet"}
        return {"status": "OK", "as_of": last["body"].get("at"), "basis": "measured",
                "items": open_p, "last_tick": last["body"],
                "decisions_by_kind": {k: int(v) for k, v in by_kind.items()},
                "delegation_outcomes": verdicts,
                "open_challenges": constitution.open_challenges(db),
                "recent_decisions": history(db, limit=20),
                "sources": ["laura_priorities", "laura_memory:operational:decision/*",
                            "laura_challenges",
                            "company_memory:laura:last_tick"]}
    except Exception as exc:  # noqa: BLE001 - a provider never raises
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"unreadable: {type(exc).__name__}: {exc}"[:300]}


def state_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
