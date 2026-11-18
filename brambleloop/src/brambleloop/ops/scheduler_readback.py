"""What the scheduler is holding back, and why a mandatory watchlist shop was not attempted.

ENG watchlist-cadence (prod 2026-11-18). The seven non-anchor watchlist shops went ~19 h
without an attempt after the owner fixed the Etsy key, and nothing said so: the readback
showed `last_attempted` and a stale `credential_refused`, never that the scheduler had
backed `intel.watchlist_scan` off. P0: "a scanner that repeatedly reports blocked without
escalation is NOT OPERATIONAL". So:

* `scheduler_block` -- suspended/backed-off job types (kind, why, until, incident), blocked
  departments, and per cadence the last enqueue and the next window. Read-only.
* `shop_not_attempted` -- per mandatory shop, the first cause that explains why it was not
  attempted (scheduler suspension, department block, cadence not enqueued, enqueued but not
  executed, failing job, credential waiting on the probe, per-shop backoff, adaptive
  interval).
* `escalate_unattempted` -- a mandatory shop not attempted for more than 2x its cadence
  raises (or restates) a P1 owner incident naming that cause; it resolves itself, with the
  reason, once the shop is attempted again. An adaptive-interval deferral is the scanner
  working as designed and is never escalated.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

INCIDENT_PREFIX = "watchlist.not_attempted:"
CADENCE_LOOKBACK_DAYS = 30
ESCALATE_FACTOR = 2
# Causes that are the scanner working as designed: never escalated.
LEGITIMATE_CAUSES = frozenset({"adaptive_not_due"})


def _aware(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v) -> str | None:
    v = _aware(v)
    return v.isoformat() if v is not None else None


def _status(v) -> str:
    return str(getattr(v, "value", v) or "")


def _latest_cadence_jobs(db, *, now: datetime) -> dict[str, dict]:
    """Per job type, the newest cadence-keyed job (one grouped query + one fetch)."""
    from sqlalchemy import func, select

    from ..core.models import Job

    since = now - timedelta(days=CADENCE_LOOKBACK_DAYS)
    out: dict[str, dict] = {}
    with db.session() as s:
        ids = [i for (i,) in s.execute(
            select(func.max(Job.id)).where(Job.idempotency_key.like("cadence:%"),
                                           Job.created_at >= since)
            .group_by(Job.job_type))]
        for i in range(0, len(ids), 500):
            for j in s.scalars(select(Job).where(Job.id.in_(ids[i:i + 500]))):
                out[j.job_type] = {"id": j.id, "status": _status(j.status),
                                   "created_at": _aware(j.created_at),
                                   "finished_at": _aware(j.finished_at)}
    return out


def _suspended(db, now) -> dict[str, dict]:
    from ..swarm.orchestrate import suspended_job_types

    return suspended_job_types(db, now=now)


def _blocked(db, now) -> dict[str, str]:
    from ..runtime.worker import Scheduler

    return Scheduler(db)._blocked_departments(now)  # noqa: SLF001 - the tick's own rule


def _department_of(job_type: str) -> str | None:
    try:
        from ..autonomy.charters import department_of

        return department_of(job_type)
    except Exception:  # noqa: BLE001
        return None


def scheduler_block(db, *, now: datetime) -> dict:
    """The `scheduler` block of /api/readback/evidence. Read-only; no free text from rows
    (the `why` strings are the scheduler's own fixed sentences)."""
    from ..runtime.worker import CADENCES, cadence_next_at

    suspended = _suspended(db, now)
    blocked = _blocked(db, now)
    latest = _latest_cadence_jobs(db, now=now)
    cadences = []
    for name, agent, job_type, period in CADENCES:
        dept = _department_of(job_type)
        job = latest.get(job_type) or {}
        skipped = ("suspended" if job_type in suspended else
                   "department_blocked" if dept in blocked else None)
        cadences.append({
            "cadence": name, "job_type": job_type, "agent": agent, "department": dept,
            "period_hours": round(period / 3600.0, 2),
            "last_enqueued_at": _iso(job.get("created_at")),
            "last_status": job.get("status"),
            "last_finished_at": _iso(job.get("finished_at")),
            "next_window_at": datetime.fromtimestamp(cadence_next_at(name, period, now),
                                                     timezone.utc).isoformat(),
            "skipped_because": skipped,
        })
    return {
        "readable": True, "as_of": now.isoformat(),
        "suspended_job_types": [
            {"job_type": jt, "kind": v.get("kind"), "why": v.get("why"),
             "until": v.get("until"), "factor": v.get("factor"),
             "incident": v.get("incident")}
            for jt, v in sorted(suspended.items())],
        # the block's reason is operator text and stays off the read-only route
        "blocked_departments": [{"department": d, "blocked": True}
                                for d in sorted(blocked)],
        "cadences": cadences,
    }


# ---- per-shop: why was it not attempted? -------------------------------------------------

def _members():
    from ..intel import watchlist

    return watchlist.WATCHLIST


def _job_type_of(member) -> str:
    from ..intel import watchlist

    return "mjs.scan" if member.role == watchlist.ANCHOR else "intel.watchlist_scan"


def _period_of(job_type: str) -> int | None:
    from ..runtime.worker import CADENCES

    return next((p for _n, _a, jt, p in CADENCES if jt == job_type), None)


def last_attempted(db, member) -> datetime | None:
    """When the scanner last tried to read this shop (a deferral is not an attempt)."""
    from ..intel import scan_evidence as SE
    from ..intel import watchlist

    if member.role == watchlist.ANCHOR:
        for j in SE._jobs(db, "mjs.scan", limit=200):  # noqa: SLF001 - same join as readback
            if (j.get("outputs") or {}).get("deferred"):
                continue
            if j.get("status") in ("done", "failed", "dead"):
                return _aware(j.get("finished_at") or j.get("created_at"))
        return None
    return _aware(watchlist._state(db, member.key).get("last_attempt_at"))  # noqa: SLF001


def shop_not_attempted(db, member, *, now: datetime, suspended: dict | None = None,
                       blocked: dict | None = None, latest: dict | None = None) -> dict:
    """The first cause that explains why `member` is not being attempted now. Always returns
    a {code, detail} reading -- `attempting` when nothing holds it back."""
    from ..intel import observe, watchlist
    from ..intel.etsy_public import auth_refused, last_probe

    suspended = _suspended(db, now) if suspended is None else suspended
    blocked = _blocked(db, now) if blocked is None else blocked
    latest = _latest_cadence_jobs(db, now=now) if latest is None else latest
    jt = _job_type_of(member)
    period = _period_of(jt) or 6 * 3600
    if jt in suspended:
        v = suspended[jt]
        return {"code": f"scheduler_{v.get('kind') or 'suspended'}",
                "detail": (f"the scheduler is not enqueuing {jt}: {v.get('kind')}"
                           + (f" until {v['until']}" if v.get("until") else "")
                           + f" (incident {v.get('incident')})"),
                "job_type": jt, "until": v.get("until"), "incident": v.get("incident")}
    dept = _department_of(jt)
    if dept in blocked:
        # the block's reason is operator text: the incident carries it, the readback not
        return {"code": "department_blocked", "job_type": jt, "department": dept,
                "detail": f"department {dept} is blocked (command-center block)"}
    job = latest.get(jt)
    if job is None or job["created_at"] is None or \
            job["created_at"] < now - timedelta(seconds=ESCALATE_FACTOR * period):
        when = _iso((job or {}).get("created_at"))
        return {"code": "cadence_not_enqueued", "job_type": jt,
                "detail": (f"no {jt} cadence job enqueued since {when}" if when else
                           f"no {jt} cadence job enqueued in {CADENCE_LOOKBACK_DAYS} days")}
    if job["status"] in ("pending", "running") and job["created_at"] < now - timedelta(
            seconds=period):
        return {"code": "enqueued_not_executed", "job_type": jt,
                "detail": (f"{jt} job #{job['id']} enqueued at {_iso(job['created_at'])} is "
                           f"still {job['status']}")}
    if job["status"] in ("failed", "dead"):
        return {"code": "job_failing", "job_type": jt,
                "detail": f"{jt} job #{job['id']} is {job['status']}"}
    probe = last_probe(db)
    if auth_refused(probe):
        return {"code": "credential_refused_waiting_for_probe", "job_type": jt,
                "detail": "Etsy refused the key at the last etsy.probe; the scan resumes on "
                          "the first probe that succeeds"}
    if member.role != watchlist.ANCHOR:
        st = watchlist._state(db, member.key)  # noqa: SLF001
        fails = int(st.get("consecutive_failures") or 0)
        last = st.get("last_attempt_at")
        if fails and last and st.get("state") in ("source_outage", "credential_refused",
                                                   watchlist.NOT_ACCESSIBLE) \
                and not watchlist._credential_fixed_since(db, st, last):  # noqa: SLF001
            until = _aware(last) + watchlist.backoff_for(fails)
            if now < until:
                return {"code": "shop_backoff", "job_type": jt, "until": until.isoformat(),
                        "detail": (f"per-shop backoff after {fails} failure(s) "
                                   f"({st.get('state')}) until {until.isoformat()}")}
    try:
        due = observe.scan_due(db, benchmark_key=member.key, now=now)
        if not due["due"]:
            return {"code": "adaptive_not_due", "job_type": jt,
                    "detail": f"adaptive interval: {due['why']}"}
    except Exception:  # noqa: BLE001 - an unreadable interval is not a reason
        pass
    return {"code": "attempting", "job_type": jt, "detail": "nothing holds this shop back"}


def unattempted(db, *, now: datetime) -> list[dict]:
    """Every mandatory shop not attempted for more than 2x its cadence, with its cause."""
    suspended, blocked = _suspended(db, now), _blocked(db, now)
    latest = _latest_cadence_jobs(db, now=now)
    out = []
    for m in _members():
        jt = _job_type_of(m)
        period = _period_of(jt)
        if not period:
            continue
        last = last_attempted(db, m)
        if last is None:
            continue            # never attempted is the scan_evidence NEVER state, not silence
        age = (now - last).total_seconds()
        if age <= ESCALATE_FACTOR * period:
            continue
        cause = shop_not_attempted(db, m, now=now, suspended=suspended, blocked=blocked,
                                   latest=latest)
        out.append({"key": m.key, "shop": m.shop_name, "job_type": jt,
                    "last_attempted": last.isoformat(),
                    "hours_since": round(age / 3600.0, 1),
                    "limit_hours": round(ESCALATE_FACTOR * period / 3600.0, 1),
                    "cause": cause})
    return out


def escalate_unattempted(db, *, now: datetime | None = None) -> dict:
    """Raise/restate a P1 owner incident per silent mandatory shop; resolve recovered ones."""
    from ..ops import incident_lifecycle as L

    now = _aware(now) or datetime.now(timezone.utc)
    silent = [r for r in unattempted(db, now=now)
              if r["cause"]["code"] not in LEGITIMATE_CAUSES]
    raised, opened = [], []
    with db.session() as s:
        for r in silent:
            sig = f"{INCIDENT_PREFIX}{r['key']}"
            _row, new = L.open_or_restate(
                s, signature=sig, severity="P1",
                summary=(f"Mandatory watchlist shop {r['shop']} has not been attempted for "
                         f"{r['hours_since']} h (limit {r['limit_hours']} h = "
                         f"{ESCALATE_FACTOR}x its {r['job_type']} cadence). Cause: "
                         f"{r['cause']['code']} -- {r['cause']['detail']}")[:2000],
                detail={"shop_key": r["key"], "job_type": r["job_type"],
                        "last_attempted": r["last_attempted"],
                        "hours_since": r["hours_since"], "cause": r["cause"]}, now=now)
            raised.append(sig)
            if new:
                opened.append(sig)
        live = set(raised)
        rec = L.reconcile(s, INCIDENT_PREFIX, lambda row: row.signature in live,
                          resolution=lambda row: ("the shop was attempted again within "
                                                  f"{ESCALATE_FACTOR}x its cadence, or its "
                                                  "only cause is the adaptive interval"),
                          now=now)
    return {"raised": raised, "opened": opened, "resolved": rec["resolved"]}


# Throttle for the scheduler tick (per database, per process).
ESCALATE_EVERY = timedelta(minutes=15)
_LAST_ESCALATION: dict[str, datetime] = {}


def maybe_escalate(db, *, now: datetime) -> dict | None:
    key = str(db.engine.url)
    last = _LAST_ESCALATION.get(key)
    if last is not None and now - last < ESCALATE_EVERY and now >= last:
        return None
    _LAST_ESCALATION[key] = now
    return escalate_unattempted(db, now=now)
