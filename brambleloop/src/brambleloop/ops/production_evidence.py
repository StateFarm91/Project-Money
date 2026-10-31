"""W4-READBACK: projected, read-only production evidence for the operator readback.

Production is deny-by-default on public GETs (W4-SECPATCH), which is correct and stays. It
left nothing outside the owner's browser able to see *why* a public `/api/verify` boolean is
false: `no_unexpected_dead_letters_in_24h` read false and nobody could say which job type.
This module answers the questions the owner asked production to prove, from rows only:

* the publishing-halt recovery (the company-wide `systemic-halt:publication` row);
* stale artefacts actually rebuilding (`ops.sentinel`, `chain.rebuild*`);
* repeated paid calls being prevented (`paid_call_records`, the write-ahead intents);
* weekly jobs completing (every 7-day cadence, `improve.weekly` among them);
* dead letters in 24 h by job type, with the error *class* only;
* products progressing through certification (`products.lifecycle` stages);
* the autonomous company loop, stage by stage, with useful work counted apart from no-ops
  (`runtime.pipeline.did_no_work` is the one judge).

Two readers:

* `checks(db)` -- the anonymous-safe `/api/verify` `evidence_checks`. Each is `{check, ok,
  evidence}`; the public projection keeps `check` and `ok` only. **Each is false without
  evidence**: a section that cannot be read, a sweep that never ran, a table with no rows is
  never a pass.
* `evidence(db)` -- the body of `GET /api/readback/evidence`, served only to the separate
  read-only `BRAMBLELOOP_READBACK_TOKEN` (`core.readbackauth`).

What is never emitted, by construction: job inputs or outputs, error text (only a class name
matched against an identifier pattern or a fixed vocabulary), incident summaries or
signatures (only the detector family), paid-call payloads (the stored model responses), owner
actions, conversations, customers, orders, spend amounts and secrets. Only ids, job types,
statuses, counts, ages, UTC timestamps, product slugs and `slug@version` artefacts.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

PASS_WINDOW_HOURS = 24
LOOP_WINDOW_DAYS = 7
# The truth sweep rides the 15-minute ops.health cadence; two hours is eight missed sweeps.
TRUTH_SWEEP_FRESH = timedelta(hours=2)
# The stale-artefact sentinel runs daily; 26 h allows one late run.
SENTINEL_FRESH = timedelta(hours=26)
REBUILD_PROGRESS = timedelta(hours=48)
WEEKLY_PERIOD = 7 * 24 * 60 * 60
WEEKLY_GRACE = timedelta(days=8)
# The weekly job the owner asked about by name (W4-PRODFIX2 fixed its dead letter). A weekly
# cadence that has never been enqueued (gated, or not yet due) is reported, not judged.
WEEKLY_REQUIRED = ("improve.weekly",)
EXAMPLES = 5
SLUGS_PER_STAGE = 50

# The autonomous company loop, in the owner's order. Each stage names the job types whose
# completed work is that stage's evidence. `delegation` and `execution` are Laura-specific:
# a tick that delegated something, and the delegated jobs themselves (inputs carry `laura`).
LOOP_STAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("market_observation", ("mjs.scan", "mjs.reviews", "radar.scan", "radar.competitor_snapshot",
                            "intel.serp_capture", "intel.watchlist_scan",
                            "intel.gallery_analysis", "etsy.listing_census", "culture.sweep")),
    ("opportunity_validation", ("radar.score", "intel.opportunity_review",
                                "intel.watchlist_compare", "portfolio.review",
                                "research.investigate")),
    ("laura_decision", ("laura.executive_tick",)),
    ("delegation", ("laura.executive_tick",)),
    ("execution", ()),
    ("independent_quality_review", ("gate.quality", "creative.blind_review",
                                    "storefront.review", "assets.launch_review",
                                    "swarm.review")),
    ("correction", ("cir.revise", "cir.reengineer", "chain.rebuild", "visual.portrait_repair")),
    ("original_product", ("cir.draft", "cir.compile", "gate.certify")),
    ("commercial_preparation", ("listing.draft", "listing.seo", "assets.build",
                                "pricing.position", "marketing.schedule", "content.draft")),
    ("measured_outcome", ("improve.measure", "growth.conclude", "etsy.shop_snapshot",
                          "finance.reconcile")),
    ("verified_lesson", ("learn.scan", "improve.mine", "improve.retrospective",
                         "creative.outcome_learning")),
    ("improved_decision", ("improve.weekly", "plan.cycle", "plan.strategy", "growth.steer")),
)
EXEC_JOB = "laura.executive_tick"

# Fixed vocabulary for the worker's own refusal messages (runtime.worker), which do not start
# with an exception class. Anything else that is not an identifier is "unclassified".
_REFUSAL_PREFIXES = (
    ("permission denied", "PermissionDenied"),
    ("no handler registered", "NoHandlerRegistered"),
    ("capability not enabled", "CapabilityNotEnabled"),
    ("budget exceeded", "BudgetExceeded"),
    ("provenance refused", "ProvenanceRefused"),
)
_CLASS = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*:")
_CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]{1,63}$")


def _known_exception_names() -> frozenset[str]:
    """L1 (READBACK review): the names of every exception class loaded in this process. A name
    is emitted only when it is one of these, so one word of error text ("JaneDoe: refund
    requested") can never travel as an error_class."""
    seen, stack = set(), [BaseException]
    while stack:
        cls = stack.pop()
        if cls.__name__ in seen:
            continue
        seen.add(cls.__name__)
        try:
            stack.extend(cls.__subclasses__())
        except TypeError:  # type.__subclasses__ needs an instance on some metaclasses
            continue
    return frozenset(seen)

# a few minutes of clock skew between writer and reader is tolerated; a future-dated row is not
_SKEW_H = 0.1


def error_class(last_error: str | None) -> str:
    """The exception class of a recorded error, never its text."""
    head = ((last_error or "").strip().splitlines() or [""])[0]
    low = head.lower()
    for prefix, name in _REFUSAL_PREFIXES:
        if low.startswith(prefix):
            return name
    m = _CLASS.match(head)
    if m:
        name = m.group(1).rsplit(".", 1)[-1]
        if _CLASS_NAME.match(name) and name in _known_exception_names():
            return name
    return "unclassified"


def _aware(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value) -> str | None:
    v = _aware(value)
    return v.isoformat() if v is not None else None


def _age_h(value, now) -> float | None:
    v = _aware(value)
    return None if v is None else round((now - v).total_seconds() / 3600.0, 2)


def _status(job_status) -> str:
    return getattr(job_status, "value", str(job_status))


def _unreadable(exc: Exception) -> dict:
    return {"readable": False, "error_class": type(exc).__name__}


# ---- sections ----------------------------------------------------------------------------


def dead_letters(db, *, now: datetime, hours: int = PASS_WINDOW_HOURS) -> dict:
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..queue.durable import deliberate_refusal

    since = now - timedelta(hours=hours)
    with db.session() as s:
        rows = list(s.execute(select(Job.id, Job.job_type, Job.last_error, Job.finished_at,
                                     Job.created_at).where(Job.status == JobStatus.DEAD)))
    groups: dict[tuple, dict] = {}
    recent_unexpected = 0
    for r in rows:
        at = _aware(r.finished_at or r.created_at)
        if at is None or at < since:
            continue
        expected = bool(deliberate_refusal(r.job_type, r.last_error or ""))
        cls = error_class(r.last_error)
        g = groups.setdefault((r.job_type, cls, expected), {
            "job_type": r.job_type, "error_class": cls, "expected_refusal": expected,
            "count": 0, "newest_at": None, "newest_job_ids": []})
        g["count"] += 1
        if g["newest_at"] is None or at.isoformat() > g["newest_at"]:
            g["newest_at"] = at.isoformat()
        g["newest_job_ids"] = sorted(g["newest_job_ids"] + [int(r.id)], reverse=True)[:EXAMPLES]
        recent_unexpected += 0 if expected else 1
    by_type = sorted(groups.values(), key=lambda g: (-g["count"], g["job_type"], g["error_class"]))
    return {"readable": True, "window_hours": hours, "unexpected_total": recent_unexpected,
            "expected_total": sum(g["count"] for g in by_type if g["expected_refusal"]),
            "by_type": by_type}


def publishing_halt(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident
    from ..ops.artefacts import SENTINEL_SIGNATURE
    from ..ops.incident_lifecycle import SYSTEMIC_SIGNATURE, kind_of
    from ..runtime.release_recovery import halted_releases

    with db.session() as s:
        sweep = s.scalar(select(AuditLog).where(AuditLog.action == "ops.truth.sweep")
                         .order_by(AuditLog.id.desc()).limit(1))
        sweep_at = sweep.at if sweep is not None else None
        systemic_reading = ((sweep.detail or {}).get("systemic")
                            if sweep is not None else None)
        systemic_rows = list(s.scalars(select(Incident).where(
            Incident.signature == SYSTEMIC_SIGNATURE).order_by(Incident.id.desc()).limit(20)))
        open_systemic = [i for i in systemic_rows if not i.resolved]
        last_resolved = next((i for i in systemic_rows if i.resolved), None)
        halting = list(s.scalars(select(Incident).where(
            Incident.resolved == False, Incident.halts_publication == True)))  # noqa: E712
        open_systemic_view = [{"incident_id": i.id, "opened_at": _iso(i.at),
                               "age_hours": _age_h(i.at, now)} for i in open_systemic]
        last_resolved_view = None if last_resolved is None else {
            "incident_id": last_resolved.id, "opened_at": _iso(last_resolved.at),
            "resolved_at": (last_resolved.detail or {}).get("resolved_at")}
        families: dict[str, set] = {}
        for i in halting:
            if i.signature == SYSTEMIC_SIGNATURE:
                continue
            families.setdefault(kind_of(i.signature), set()).add(i.product_slug or "")
    reading_ok = isinstance(systemic_reading, dict) and "error" not in systemic_reading
    halted = halted_releases(db)
    return {
        "readable": True,
        "truth_sweep_last_at": _iso(sweep_at),
        "truth_sweep_age_hours": _age_h(sweep_at, now),
        "truth_sweep_systemic_evaluated": reading_ok,
        "truth_sweep_systemic": (systemic_reading.get("systemic")
                                 if reading_ok and isinstance(systemic_reading.get("systemic"), bool)
                                 else None),
        "systemic_halt_open": len(open_systemic_view),
        "systemic_halt_open_rows": open_systemic_view,
        "systemic_halt_last_resolved": last_resolved_view,
        "per_product_halting_by_family": {
            fam: {"products": len({x for x in slugs if x}),
                  "slugs": sorted(x for x in slugs if x)[:SLUGS_PER_STAGE]}
            for fam, slugs in sorted(families.items())},
        "stale_artefact_family": SENTINEL_SIGNATURE,
        "halted_certifications": len(halted),
        "halted_certification_artefacts": [h["artifact"] for h in halted][:SLUGS_PER_STAGE],
    }


def stale_rebuilds(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog, Incident, Job, JobStatus
    from ..ops.artefacts import SENTINEL_SIGNATURE

    d1, d2, d7 = (now - timedelta(hours=24), now - REBUILD_PROGRESS, now - timedelta(days=7))
    with db.session() as s:
        sentinel = s.scalar(select(AuditLog).where(AuditLog.action == "ops.sentinel")
                            .order_by(AuditLog.id.desc()).limit(1))
        propagated = s.scalar(select(AuditLog).where(
            AuditLog.action == "ops.rebuild_propagated").order_by(AuditLog.id.desc()).limit(1))
        completed = list(s.execute(select(AuditLog.id, AuditLog.at, AuditLog.detail).where(
            AuditLog.action == "chain.rebuild_completed", AuditLog.at >= d7)))
        unbound = list(s.execute(select(AuditLog.id, AuditLog.at).where(
            AuditLog.action == "chain.rebuild_unbound", AuditLog.at >= d7)))
        jobs = list(s.execute(select(Job.id, Job.status, Job.created_at, Job.finished_at).where(
            Job.job_type == "chain.rebuild", Job.created_at >= d7)))
        unfinished_any = list(s.execute(select(Job.id, Job.created_at).where(
            Job.job_type == "chain.rebuild",
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING, JobStatus.FAILED)))))
        stale_incidents = list(s.execute(select(Incident.id, Incident.at, Incident.product_slug)
                                         .where(Incident.resolved == False,  # noqa: E712
                                                Incident.signature.like(
                                                    SENTINEL_SIGNATURE + ":%"))))
    sd = (sentinel.detail or {}) if sentinel is not None else {}
    stale = sd.get("stale")
    stale = len(stale) if isinstance(stale, list) else stale if isinstance(stale, int) else None
    pd = (propagated.detail or {}) if propagated is not None else {}

    def _verified(detail) -> bool:
        return not (detail or {}).get("already_fresh")

    real = [c for c in completed if _verified(c.detail)]
    noop = [c for c in completed if not _verified(c.detail)]
    by_status: dict[str, int] = {}
    for j in jobs:
        by_status[_status(j.status)] = by_status.get(_status(j.status), 0) + 1
    oldest_unfinished = min((_aware(j.created_at) for j in unfinished_any
                             if j.created_at is not None), default=None)
    return {
        "readable": True,
        "sentinel_last_at": _iso(sentinel.at) if sentinel is not None else None,
        "sentinel_age_hours": _age_h(sentinel.at, now) if sentinel is not None else None,
        "sentinel_stale_artefacts": stale,
        "sentinel_checked": sd.get("checked") if isinstance(sd.get("checked"), int) else None,
        "last_propagation_at": _iso(propagated.at) if propagated is not None else None,
        "last_propagation_enqueued": len(pd.get("rebuild_enqueued") or []),
        "last_propagation_retried": len(pd.get("rebuild_retried") or []),
        "last_propagation_already_queued": len(pd.get("rebuild_already_queued") or []),
        "rebuilds_verified_24h": sum(1 for c in real if _aware(c.at) >= d1),
        "rebuilds_verified_48h": sum(1 for c in real if _aware(c.at) >= d2),
        "rebuilds_verified_7d": len(real),
        "rebuilds_already_fresh_7d": len(noop),
        "rebuilds_unbound_7d": len(unbound),
        "newest_verified_rebuild_at": max((_iso(c.at) for c in real), default=None),
        "newest_verified_rebuild_audit_ids": sorted((int(c.id) for c in real),
                                                    reverse=True)[:EXAMPLES],
        "rebuild_jobs_7d_by_status": dict(sorted(by_status.items())),
        "rebuild_jobs_unfinished": len(unfinished_any),
        "oldest_unfinished_rebuild_age_hours": _age_h(oldest_unfinished, now),
        "open_stale_artefact_incidents": len(stale_incidents),
        "open_stale_artefact_products": len({i.product_slug for i in stale_incidents
                                             if i.product_slug}),
        "oldest_open_stale_artefact_age_hours": _age_h(
            min((_aware(i.at) for i in stale_incidents if i.at is not None), default=None), now),
    }


_BILLED = ("OK", "FAILED_BILLED", "UNCERTAIN")


def paid_calls(db, *, now: datetime, hours: int = PASS_WINDOW_HOURS) -> dict:
    from sqlalchemy import func, select

    from ..core.models import AuditLog
    from ..gateway.paid_calls import REPLAY_ACTION, PaidCallRecord

    since, d7 = now - timedelta(hours=hours), now - timedelta(days=7)
    with db.session() as s:
        rows = list(s.execute(select(
            PaidCallRecord.key, PaidCallRecord.effect, PaidCallRecord.job_id,
            PaidCallRecord.job_type, PaidCallRecord.fingerprint, PaidCallRecord.outcome,
            PaidCallRecord.replays, PaidCallRecord.orphan_billed, PaidCallRecord.at,
            PaidCallRecord.updated_at).where(PaidCallRecord.at >= d7)))
        replay_audits = int(s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == REPLAY_ACTION, AuditLog.at >= since)) or 0)
    recent = [r for r in rows if _aware(r.at) >= since]
    by_outcome: dict[str, int] = {}
    for r in recent:
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
    billed = [r for r in recent if r.outcome in _BILLED or r.orphan_billed]
    groups: dict[tuple, list] = {}
    for r in billed:
        groups.setdefault((r.effect, r.fingerprint), []).append(r)
    repeated = [{"effect": eff, "request_fingerprint": (fp or "")[:12], "billed_calls": len(g),
                 "job_types": sorted({x.job_type for x in g if x.job_type}),
                 "job_ids": sorted({int(x.job_id) for x in g if x.job_id is not None})[:EXAMPLES]}
                for (eff, fp), g in sorted(groups.items(), key=lambda kv: -len(kv[1]))
                if len(g) > 1]
    return {
        "readable": True, "window_hours": hours,
        "intents_7d": len(rows),
        "intents_in_window": len(recent),
        "intents_in_window_by_outcome": dict(sorted(by_outcome.items())),
        "billed_in_window": len(billed),
        "replays_served_in_window": sum(int(r.replays or 0) for r in rows
                                        if _aware(r.updated_at or r.at) >= since),
        "replay_audits_in_window": replay_audits,
        "repeated_billed_requests": len(repeated),
        "repeated": repeated[:20],
    }


def weekly_jobs(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..runtime.worker import CADENCES

    types = sorted({jt for _n, _a, jt, period in CADENCES if period == WEEKLY_PERIOD})
    out = []
    with db.session() as s:
        for jt in types:
            last_done = s.scalar(select(Job).where(Job.job_type == jt,
                                                   Job.status == JobStatus.DONE)
                                 .order_by(Job.finished_at.desc(), Job.id.desc()).limit(1))
            last_dead = s.scalar(select(Job).where(Job.job_type == jt,
                                                   Job.status == JobStatus.DEAD)
                                 .order_by(Job.finished_at.desc(), Job.id.desc()).limit(1))
            ever = s.scalar(select(Job.id).where(Job.job_type == jt).limit(1)) is not None
            done_at = _aware(last_done.finished_at) if last_done is not None else None
            dead_at = _aware(last_dead.finished_at) if last_dead is not None else None
            dead_after = dead_at is not None and (done_at is None or dead_at > done_at)
            out.append({
                "job_type": jt,
                "ever_enqueued": ever,
                "last_success_at": _iso(done_at), "last_success_job_id":
                    last_done.id if last_done is not None else None,
                "last_success_age_hours": _age_h(done_at, now),
                "last_dead_at": _iso(dead_at),
                "last_dead_job_id": last_dead.id if last_dead is not None else None,
                "last_dead_error_class": (error_class(last_dead.last_error)
                                          if last_dead is not None else None),
                "dead_after_last_success": dead_after,
                "completing": done_at is not None and now - done_at <= WEEKLY_GRACE
                              and not dead_after,
            })
    return {"readable": True, "grace_days": WEEKLY_GRACE.days, "required": list(WEEKLY_REQUIRED),
            "judged": "every weekly cadence that has ever been enqueued, and the required ones",
            "weekly_job_types": out}


def certification(db, *, now: datetime) -> dict:
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..products import lifecycle
    from ..runtime.release_recovery import halted_releases

    board = lifecycle.board(db)
    cols = board.get("columns") or {}
    d7 = now - timedelta(days=7)
    acts = ("gate.certified", "gate.halted", "gate.blocked", "gate.version_conflict")
    with db.session() as s:
        rows = list(s.execute(select(AuditLog.id, AuditLog.action, AuditLog.artifact).where(
            AuditLog.action.in_(acts), AuditLog.at >= d7).order_by(AuditLog.id.desc())))
    recent: dict[str, dict] = {a: {"count": 0, "newest_artefacts": []} for a in acts}
    for r in rows:
        e = recent[r.action]
        e["count"] += 1
        if r.artifact and len(e["newest_artefacts"]) < EXAMPLES:
            e["newest_artefacts"].append(r.artifact)
    return {
        "readable": True,
        "products": board.get("products"),
        "stage_order": list(lifecycle.STAGES),
        "count_by_stage": {st: len(cols.get(st) or []) for st in lifecycle.STAGES},
        "slugs_by_stage": {st: list(cols.get(st) or [])[:SLUGS_PER_STAGE]
                           for st in lifecycle.STAGES if cols.get(st)},
        "certify_outcomes_7d": recent,
        "halted_certifications": [h["artifact"] for h in halted_releases(db)][:SLUGS_PER_STAGE],
    }


def autonomy_loop(db, *, now: datetime, days: int = LOOP_WINDOW_DAYS) -> dict:
    from sqlalchemy import String, cast, select

    from ..autonomy.kpis import did_no_work
    from ..core.models import Job, JobStatus

    since = now - timedelta(days=days)
    types = sorted({jt for _st, jts in LOOP_STAGES for jt in jts})
    with db.session() as s:
        rows = list(s.execute(select(Job.id, Job.job_type, Job.status, Job.outputs,
                                     Job.finished_at, Job.created_at).where(
            Job.job_type.in_(types), Job.created_at >= since)))
        delegated = [r for r in s.execute(select(
            Job.id, Job.job_type, Job.status, Job.inputs, Job.outputs, Job.finished_at,
            Job.created_at).where(Job.created_at >= since,
                                  cast(Job.inputs, String).like('%"laura"%')))
            if isinstance(r.inputs, dict) and r.inputs.get("laura")]

    def tally(selected, judge) -> dict:
        useful, noop, failed, open_ = [], 0, 0, 0
        for r in selected:
            st = _status(r.status)
            if st == JobStatus.DONE.value:
                if judge(r):
                    useful.append(r)
                else:
                    noop += 1
            elif st == JobStatus.DEAD.value:
                failed += 1
            elif st in (JobStatus.PENDING.value, JobStatus.RUNNING.value,
                        JobStatus.FAILED.value):
                open_ += 1
        useful.sort(key=lambda r: (_iso(r.finished_at) or "", r.id), reverse=True)
        return {"useful_completed": len(useful), "noop_completed": noop,
                "dead": failed, "open": open_,
                "newest_useful_job_ids": [int(r.id) for r in useful[:EXAMPLES]],
                "newest_useful_at": _iso(useful[0].finished_at) if useful else None}

    def useful(r) -> bool:
        return not did_no_work(r.outputs or {}, r.job_type)

    def delegated_something(r) -> bool:
        d = (r.outputs or {}).get("delegated")
        return isinstance(d, (int, float)) and not isinstance(d, bool) and d > 0

    stages = []
    for name, jts in LOOP_STAGES:
        if name == "execution":
            sel, judge = delegated, useful
            basis = "jobs Laura delegated (inputs carry `laura`), judged by did_no_work"
        elif name == "delegation":
            sel, judge = [r for r in rows if r.job_type == EXEC_JOB], delegated_something
            basis = "executive ticks; useful when the tick delegated at least one job"
        else:
            sel, judge = [r for r in rows if r.job_type in jts], useful
            basis = "completed jobs of these types, judged by runtime.pipeline.did_no_work"
        t = tally(sel, judge)
        stages.append({"stage": name, "job_types": list(jts), "basis": basis, **t,
                       "evidenced": t["useful_completed"] > 0})
    return {"readable": True, "window_days": days,
            "judge": "runtime.pipeline.did_no_work (a no-op never counts as useful work)",
            "stages": stages,
            "stages_with_useful_work": sum(1 for x in stages if x["evidenced"]),
            "stages_total": len(stages),
            "first_stage_without_useful_work": next(
                (x["stage"] for x in stages if not x["evidenced"]), None)}


_NAME_MAX = 120


def _name(v) -> str | None:
    return str(v)[:_NAME_MAX] if isinstance(v, (str, int)) and not isinstance(v, bool) else None


def _int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def etsy_taxonomy(db, *, now: datetime) -> dict:
    """The newest `etsy.taxonomy_refreshed` row, projected for resolving the Etsy category
    without the operator token (W-LAUNCHFIX E4). Etsy's own public taxonomy ids and names
    only: per reported category the chosen node and whether that node's stored schema offers
    the value "Crochet"; per property candidate node its property ids and names; the refresh
    time. No free text (`why`), no possible-value lists, no credential or gate detail."""
    from sqlalchemy import select

    from ..commerce import category as cat
    from ..core.models import AuditLog, EtsyTaxonomySnapshot
    from ..integrations.etsy_taxonomy import REFRESHED_ACTION

    with db.session() as s:
        row = s.scalar(select(AuditLog).where(AuditLog.action == REFRESHED_ACTION)
                       .order_by(AuditLog.id.desc()).limit(1))
        detail = dict(row.detail or {}) if row is not None else {}
        sid = _int(detail.get("snapshot_id"))
        snap_row = s.get(EtsyTaxonomySnapshot, sid) if sid is not None else None
        properties = dict(snap_row.properties or {}) if snap_row is not None else None
    if row is None:
        return {"readable": True, "refreshed": False, "refreshed_at": None}
    snapshot = {"properties": properties or {}}

    def offers(node_id) -> bool | None:
        if properties is None or _int(node_id) is None or str(node_id) not in properties:
            return None
        return cat.crochet_property(snapshot, int(node_id)) is not None

    def basis(b) -> dict | None:
        if not isinstance(b, dict):
            return None
        return {"via": _name(b.get("via")), "property_id": _int(b.get("property_id")),
                "property": _name(b.get("property")), "value_id": _int(b.get("value_id")),
                "value": _name(b.get("value"))}

    choices = {}
    for c, ch in sorted((detail.get("category_choices") or {}).items()):
        if not isinstance(ch, dict):
            continue
        tid = _int(ch.get("taxonomy_id"))
        choices[str(c)[:40]] = {
            "status": _name(ch.get("status")), "taxonomy_id": tid,
            "path_ids": [x for x in (ch.get("path_ids") or []) if _int(x) is not None][:20],
            "path_names": [_name(x) for x in (ch.get("path_names") or [])][:20],
            "crochet_basis": basis(ch.get("crochet_basis")),
            "schema_offers_crochet": offers(tid) if tid is not None else None}
    candidates = []
    for n in (detail.get("property_candidates") or [])[:40]:
        if not isinstance(n, dict) or _int(n.get("id")) is None:
            continue
        nid = n["id"]
        props = None if properties is None else [
            {"property_id": _int(p.get("property_id")),
             "name": _name(p.get("name") or p.get("display_name"))}
            for p in (properties.get(str(nid)) or []) if isinstance(p, dict)][:60]
        candidates.append({"node_id": nid, "path": _name(n.get("path")),
                           "properties": props, "schema_offers_crochet": offers(nid)})
    return {"readable": True, "refreshed": True, "refreshed_at": _iso(row.at),
            "refresh_age_hours": _age_h(row.at, now), "snapshot_id": sid,
            "snapshot_readable": properties is not None,
            "category_choices": choices, "property_candidates": candidates}


# ---- the anonymous-safe checks ----------------------------------------------------------

SECTIONS = {
    "dead_letters_24h": dead_letters,
    "publishing_halt": publishing_halt,
    "stale_artefact_rebuilds": stale_rebuilds,
    "paid_call_dedupe": paid_calls,
    "weekly_jobs": weekly_jobs,
    "certification_pipeline": certification,
    "autonomy_loop": autonomy_loop,
    "etsy_taxonomy": etsy_taxonomy,
}
CHECK_NAMES = ("publishing_halt_clear", "stale_artefacts_rebuilding",
               "no_repeated_paid_call_in_24h", "weekly_jobs_completing")


def _section(name: str, db, now) -> dict:
    try:
        return SECTIONS[name](db, now=now)
    except Exception as exc:  # noqa: BLE001 - unreadable is no evidence, never a pass
        return _unreadable(exc)


def judge_publishing_halt(ev: dict) -> bool:
    age = ev.get("truth_sweep_age_hours")
    return bool(ev.get("readable") and age is not None and age >= -_SKEW_H
                and age <= TRUTH_SWEEP_FRESH.total_seconds() / 3600
                and ev.get("truth_sweep_systemic_evaluated") is True
                and ev.get("truth_sweep_systemic") is False
                and ev.get("systemic_halt_open") == 0)


def judge_stale_rebuilds(ev: dict) -> bool:
    age = ev.get("sentinel_age_hours")
    if not (ev.get("readable") and age is not None and age >= -_SKEW_H
            and age <= SENTINEL_FRESH.total_seconds() / 3600
            and isinstance(ev.get("sentinel_stale_artefacts"), int)):
        return False
    if ev["sentinel_stale_artefacts"] == 0 and ev.get("open_stale_artefact_incidents") == 0:
        return True
    stuck = ev.get("oldest_unfinished_rebuild_age_hours")
    return bool((ev.get("rebuilds_verified_48h") or 0) > 0
                and (stuck is None or stuck <= REBUILD_PROGRESS.total_seconds() / 3600))


def judge_paid_calls(ev: dict) -> bool:
    return bool(ev.get("readable") and (ev.get("intents_7d") or 0) > 0
                and ev.get("repeated_billed_requests") == 0)


def _weekly_judged(ev: dict) -> list[dict]:
    return [r for r in ev.get("weekly_job_types") or []
            if r.get("ever_enqueued") or r.get("job_type") in WEEKLY_REQUIRED]


def judge_weekly(ev: dict) -> bool:
    rows = _weekly_judged(ev)
    names = {r.get("job_type") for r in rows}
    return bool(ev.get("readable") and rows and set(WEEKLY_REQUIRED) <= names
                and all(r.get("completing") is True for r in rows))


def checks(db, *, now: datetime | None = None) -> list[dict]:
    """The `/api/verify` `evidence_checks`. False without evidence, never true by default."""
    now = _aware(now) or datetime.now(timezone.utc)
    halt = _section("publishing_halt", db, now)
    stale = _section("stale_artefact_rebuilds", db, now)
    paid = _section("paid_call_dedupe", db, now)
    weekly = _section("weekly_jobs", db, now)

    def short(ev: dict, keys: tuple) -> dict:
        return {k: ev.get(k) for k in keys if k in ev}

    return [
        {"check": "publishing_halt_clear", "ok": judge_publishing_halt(halt),
         "evidence": short(halt, ("readable", "error_class", "truth_sweep_last_at",
                                  "truth_sweep_systemic", "systemic_halt_open",
                                  "halted_certifications"))},
        {"check": "stale_artefacts_rebuilding", "ok": judge_stale_rebuilds(stale),
         "evidence": short(stale, ("readable", "error_class", "sentinel_last_at",
                                   "sentinel_stale_artefacts", "rebuilds_verified_48h",
                                   "oldest_unfinished_rebuild_age_hours",
                                   "open_stale_artefact_incidents"))},
        {"check": "no_repeated_paid_call_in_24h", "ok": judge_paid_calls(paid),
         "evidence": short(paid, ("readable", "error_class", "intents_7d",
                                  "billed_in_window", "repeated_billed_requests"))},
        {"check": "weekly_jobs_completing", "ok": judge_weekly(weekly),
         "evidence": {"readable": weekly.get("readable"),
                      "error_class": weekly.get("error_class"),
                      "not_completing": [r["job_type"] for r in _weekly_judged(weekly)
                                         if not r.get("completing")]}},
    ]


# W4-READBACK: the deploy readback's operator-only rows (ops/readback.py OPERATOR_ENDPOINTS),
# served here so the deploy readback needs only the read-only token. Each route's handler is
# called in-process; what leaves is its status and the ONE field the manifest row reads,
# projected: a bool, number or null as is, a list as its length only, anything else null.
# None means the row reads the status only.
DEPLOY_READBACK: dict[str, str | None] = {
    "/api/departments": None,
    "/api/swarm/runtime": None,
    "/api/funding/packets": "packets",
    "/api/offsite": "configured",
    "/api/continuity": "last_proof_ok",
    "/api/etsy": "usable",
}


def _project_value(v):
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, (list, tuple)):
        return {"list_length": len(v)}
    return None


def deploy_readback(handlers: dict) -> dict:
    """{route: {"status", "fields"}} for DEPLOY_READBACK, from `handlers[route]()`."""
    import json as _json

    out: dict[str, dict] = {}
    for route, field in DEPLOY_READBACK.items():
        fn = handlers.get(route)
        if fn is None:
            out[route] = {"status": None, "fields": {}, "error_class": "NotServed"}
            continue
        try:
            body = fn()
            status = 200
            if hasattr(body, "status_code") and hasattr(body, "body"):
                status = int(body.status_code)
                try:
                    body = _json.loads(bytes(body.body).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    body = None
        except Exception as exc:  # noqa: BLE001 - the route would have answered 500
            out[route] = {"status": 500, "fields": {}, "error_class": type(exc).__name__}
            continue
        fields = {}
        if field is not None:
            fields[field] = _project_value(body.get(field) if isinstance(body, dict) else None)
        out[route] = {"status": status, "fields": fields}
    return out


def evidence(db, *, now: datetime | None = None, deploy_handlers: dict | None = None) -> dict:
    """The body of GET /api/readback/evidence (read-only token)."""
    now = _aware(now) or datetime.now(timezone.utc)
    sections = {name: _section(name, db, now) for name in SECTIONS}
    if deploy_handlers is not None:
        try:
            sections["deploy_readback"] = deploy_readback(deploy_handlers)
        except Exception as exc:  # noqa: BLE001
            sections["deploy_readback"] = _unreadable(exc)
    judged = {
        "publishing_halt_clear": judge_publishing_halt(sections["publishing_halt"]),
        "stale_artefacts_rebuilding": judge_stale_rebuilds(sections["stale_artefact_rebuilds"]),
        "no_repeated_paid_call_in_24h": judge_paid_calls(sections["paid_call_dedupe"]),
        "weekly_jobs_completing": judge_weekly(sections["weekly_jobs"]),
    }
    dl = sections["dead_letters_24h"]
    judged["no_unexpected_dead_letters_in_24h"] = bool(
        dl.get("readable") and dl.get("unexpected_total") == 0)
    return {"as_of": now.isoformat(), "read_only": True,
            "never_included": ["job inputs/outputs", "error text", "incident text",
                               "paid-call payloads", "conversations", "owner data",
                               "customer data", "secrets"],
            "server_judgement": judged, **sections}
