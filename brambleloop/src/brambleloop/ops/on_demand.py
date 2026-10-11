"""W4-ONDEMAND: run the existing checks now instead of waiting for their cadence.

The owner's directive (2026-10-11): remove unnecessary waiting. Several gates open only when a
scheduled check next runs. Examples are a model probe every 6 h, an offsite archive daily, and
launch readiness daily. So a fix the owner made at 09:00 could stay invisible until the next
day. This module adds two things and nothing else:

* **On-demand runs** (`run_check`). The Command Center's "Run checks now" card enqueues
  the *existing* job types, using the agent the cadence table names, so the worker runs the
  *existing* handlers. The worker re-authorises every job, and every model call is still
  ceiling-checked in the gateway. No handler, budget, gate or authority check is bypassed or
  duplicated here. Each check is rate-limited (at least 60 s apart; checks that pay for a
  provider call are spaced further), audited as `cc.check.run`, and never doubles a job that
  is already pending or running.
* **Event chains** (`after_model_ok`, `after_etsy_ok`). A successful model probe brings
  parked model jobs forward and queues the capability probes, which include vision. A
  successful Etsy probe or OAuth callback queues the taxonomy refresh and the market-intel
  captures. These fire on a *transition* (the previous probe was not OK) or on an on-demand
  run. They never fire on every scheduled success, and each is idempotent per hour, so a
  chain cannot multiply external calls.

Authentication, CSRF, nonce and step-up belong to the caller (`/api/cc/checks/*`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

RUN_ACTION = "cc.check.run"
REFUSED_ACTION = "cc.check.refused"
UNPARK_ACTION = "ai.unparked"
CHAIN_ACTION = "ondemand.chain"


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    cadences: tuple[str, ...]        # names in runtime.worker.CADENCES
    external: bool                   # calls a third party -> step-up required
    min_interval_s: int = 60
    why: str = ""


# Every check reuses a scheduled cadence's job type and agent; nothing new is registered.
CHECKS: dict[str, Check] = {c.key: c for c in (
    Check("model", "Model provider (Anthropic)", ("model_probe",), True, 60,
          "smallest ceiling-checked call; on success parked model jobs resume and the "
          "capability (vision) probes are queued"),
    Check("capabilities", "Capabilities: vision, image generation, pages, culture, surfaces",
          ("capability_probes",), True, 15 * 60,
          "includes one real image generation and one vision call, both ceiling-checked, so "
          "it is spaced 15 minutes apart"),
    Check("etsy", "Etsy app key", ("etsy_probe",), True, 60,
          "read-only ping; on success the taxonomy refresh and market-intel captures queue"),
    Check("offsite", "Offsite archive (encrypted round trip)", ("offsite_archive",), True,
          15 * 60, "export, seal, upload, read back, decrypt, restore-prove"),
    Check("continuity", "Continuity restore proof", ("continuity_proof",), False, 5 * 60,
          "local export and restore into a scratch database"),
    Check("certification", "Certification re-check (lanes + stale rebuilds)",
          ("production_lanes", "chain_rebuild"), False, 60,
          "re-checks every certified release and re-certifies anything whose inputs moved"),
    Check("launch_readiness", "Launch readiness", ("launch_readiness",), False, 60,
          "re-assesses every launch requirement and the owner-action queue"),
)}


class CheckRefused(ValueError):
    def __init__(self, message: str, *, code: str, retry_after_s: int = 0):
        super().__init__(message)
        self.code = code
        self.retry_after_s = retry_after_s


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _cadence(name: str) -> tuple[str, str, str, int]:
    from ..runtime.worker import CADENCES

    for row in CADENCES:
        if row[0] == name:
            return row
    raise KeyError(name)


def _inflight(s, job_type: str):
    from sqlalchemy import select

    from ..core.models import Job, JobStatus

    return s.scalar(select(Job).where(
        Job.job_type == job_type,
        Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED]))
        .order_by(Job.id.desc()).limit(1))


def _last_run(s, key: str):
    from sqlalchemy import select

    from ..core.models import AuditLog

    return s.scalar(select(AuditLog).where(AuditLog.action == RUN_ACTION,
                                           AuditLog.artifact == f"check:{key}")
                    .order_by(AuditLog.id.desc()).limit(1))


def _run_at(row) -> datetime | None:
    """When a recorded run happened: the time the run itself stated, else the row's stamp."""
    if row is None:
        return None
    stated = (row.detail or {}).get("at")
    if stated:
        try:
            return _aware(datetime.fromisoformat(stated))
        except ValueError:
            pass
    return _aware(row.at)


def _enqueue_once(db, agent: str, job_type: str, inputs: dict, key: str) -> dict:
    """Enqueue unless a job of this type is already in flight or the key was used."""
    from ..queue.durable import DuplicateJob, JobQueue

    with db.session() as s:
        busy = _inflight(s, job_type)
        if busy is not None:
            return {"job_type": job_type, "enqueued": False, "job_id": busy.id,
                    "why": f"job {busy.id} is already {busy.status.value.lower()}"}
    try:
        job = JobQueue(db).enqueue(agent, job_type, inputs, idempotency_key=key)
    except DuplicateJob as exc:
        return {"job_type": job_type, "enqueued": False, "job_id": exc.existing_id,
                "why": "already queued in this window"}
    return {"job_type": job_type, "enqueued": True, "job_id": job.id}


def run_check(db, key: str, *, actor: str, now: datetime | None = None) -> dict:
    """Queue one check's existing job(s) now. Rate-limited and audited, refusals included."""
    from ..agents.registry import Registry

    now = _now(now)
    check = CHECKS.get(key)
    if check is None:
        raise CheckRefused(f"unknown check {key!r}", code="NOT_FOUND")
    if not (actor or "").strip():
        raise CheckRefused("an on-demand check needs the authenticated actor", code="REFUSED")
    with db.session() as s:
        last_at = _run_at(_last_run(s, key))
    if last_at is not None and (now - last_at).total_seconds() < check.min_interval_s:
        wait = int(check.min_interval_s - (now - last_at).total_seconds()) + 1
        Registry(db).audit("orchestrator", REFUSED_ACTION, artifact=f"check:{key}",
                           detail={"by": actor[:64], "code": "RATE_LIMITED",
                                   "retry_after_s": wait})
        raise CheckRefused(f"{check.label} was run {int((now - last_at).total_seconds())} s "
                           f"ago; next run allowed in {wait} s", code="RATE_LIMITED",
                           retry_after_s=wait)
    results = []
    for name in check.cadences:
        cname, agent, job_type, _period = _cadence(name)
        results.append(_enqueue_once(
            db, agent, job_type,
            {"cadence": cname, "on_demand": True, "requested_by": actor[:64]},
            f"ondemand:{cname}:{now:%Y%m%dT%H%M%S}"))
    Registry(db).audit("orchestrator", RUN_ACTION, artifact=f"check:{key}",
                       detail={"by": actor[:64], "check": key, "at": now.isoformat(),
                               "results": results})
    return {"check": key, "label": check.label, "results": results, "at": now.isoformat(),
            "next_allowed_at": (now + timedelta(seconds=check.min_interval_s)).isoformat()}


def _latest_job(s, job_type: str):
    from sqlalchemy import select

    from ..core.models import Job

    return s.scalar(select(Job).where(Job.job_type == job_type)
                    .order_by(Job.id.desc()).limit(1))


def _job_view(job) -> dict | None:
    if job is None:
        return None
    out = job.outputs if isinstance(job.outputs, dict) else {}
    ok = out.get("ok") if isinstance(out.get("ok"), bool) else None
    when = _aware(job.finished_at) or _aware(job.started_at) or _aware(job.created_at)
    return {"job_id": job.id, "job_type": job.job_type, "status": job.status.value,
            "ok": ok, "at": when.isoformat() if when else None,
            "on_demand": bool((job.inputs or {}).get("on_demand")),
            "note": str(job.last_error or out.get("reason") or out.get("why") or "")[:200]}


def status(db, *, now: datetime | None = None) -> dict:
    """The card: per check, its last result and time, and when it may next be run."""
    now = _now(now)
    rows = []
    with db.session() as s:
        for check in CHECKS.values():
            jobs = []
            for name in check.cadences:
                _n, _a, job_type, period = _cadence(name)
                jobs.append({"cadence": name, "scheduled_every_s": period,
                             "last": _job_view(_latest_job(s, job_type))})
            last_at = _run_at(_last_run(s, check.key))
            next_at = (last_at + timedelta(seconds=check.min_interval_s)) if last_at else None
            rows.append({"key": check.key, "label": check.label, "external": check.external,
                         "requires_stepup": check.external, "why": check.why,
                         "min_interval_s": check.min_interval_s, "jobs": jobs,
                         "last_on_demand_at": last_at.isoformat() if last_at else None,
                         "available_now": next_at is None or next_at <= now,
                         "next_allowed_at": next_at.isoformat() if next_at else None})
    from ..runtime.worker import CADENCES

    carded = {name for c in CHECKS.values() for name in c.cadences}
    others = [{"cadence": n, "job_type": t, "every_s": p}
              for n, _a, t, p in CADENCES if n not in carded]
    return {"checks": rows, "other_cadences": others, "as_of": now.isoformat(),
            "other_cadences_note": (
                "any other scheduled cadence can be re-run through Operations recovery "
                "(step-up; refused while one is in flight; audited)"),
            "note": ("each button queues the same job the schedule runs; the worker runs it "
                     "under the same authority, budget and rate-limit checks")}


# ---- event chains --------------------------------------------------------------------------


def _hour(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H")


def after_model_ok(db, *, previous: dict | None, on_demand: bool,
                   now: datetime | None = None) -> dict:
    """A model probe just succeeded: resume parked model jobs; maybe queue capability probes."""
    from sqlalchemy import update

    from ..agents.registry import Registry
    from ..core.models import Job, JobStatus
    from ..runtime.worker import MODEL_JOB_TYPES

    now = _now(now)
    with db.session() as s:
        res = s.execute(update(Job).where(
            Job.status == JobStatus.PENDING, Job.job_type.in_(sorted(MODEL_JOB_TYPES)),
            Job.run_after > now).values(run_after=now)
            .execution_options(synchronize_session=False))
        unparked = int(res.rowcount or 0)
    out: dict = {"unparked": unparked, "capability_probes": None}
    transition = not (previous or {}).get("ok")
    if transition or on_demand:
        _n, agent, job_type, _p = _cadence("capability_probes")
        out["capability_probes"] = _enqueue_once(
            db, agent, job_type, {"cadence": "capability_probes", "chain": "model_ok"},
            f"chain:model_ok:{job_type}:{_hour(now)}")
    if unparked or out["capability_probes"]:
        Registry(db).audit("orchestrator", UNPARK_ACTION if unparked else CHAIN_ACTION,
                           artifact="model.probe", detail={"trigger": "model.probe ok",
                                                           "transition": transition,
                                                           "on_demand": on_demand, **out})
    return out


ETSY_FOLLOW_ONS = ("etsy_taxonomy", "mjs_scan", "serp_capture")


def after_etsy_ok(db, *, trigger: str, now: datetime | None = None) -> dict:
    """Etsy just answered (probe success or OAuth grant): refresh what depended on it."""
    from ..agents.registry import Registry

    now = _now(now)
    results = []
    for name in ETSY_FOLLOW_ONS:
        cname, agent, job_type, _p = _cadence(name)
        results.append(_enqueue_once(db, agent, job_type,
                                     {"cadence": cname, "chain": f"etsy_ok:{trigger}"},
                                     f"chain:etsy_ok:{job_type}:{_hour(now)}"))
    Registry(db).audit("orchestrator", CHAIN_ACTION, artifact="etsy",
                       detail={"trigger": trigger, "results": results})
    return {"trigger": trigger, "results": results}
