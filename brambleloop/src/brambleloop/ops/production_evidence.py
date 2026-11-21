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
* listing-package releases left unrecorded (degraded sweeps), by `slug@version` and class;
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
                            "intel.gallery_analysis", "etsy.listing_census", "culture.sweep",
                            # WS2 R1: category-leader discovery. Review 6816970157 M1: NOT
                            # intel.scan_evidence -- the daily join always reports every shop as
                            # work, so it would satisfy this stage with nothing scanned.
                            "intel.panel_discovery")),
    ("opportunity_validation", ("radar.score", "intel.opportunity_review",
                                "intel.watchlist_compare", "portfolio.review",
                                "research.investigate", "radar.concept_intake")),
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
    # legacy reclaim dead letters (before FIX-CYCLE-PROOF-BILLING): no class, just the clause
    ("| lease expired", "LeaseExpired"),
)
# FIX-CYCLE-PROOF-BILLING: `_known_exception_names` walks the classes loaded in THIS process,
# so a reader that had not imported the module defining an exception classified it
# `unclassified` (a fresh process read "PaidCallUnresolved: ..." that way). The modules whose
# exceptions dead letters carry are imported first, so the answer does not depend on what the
# reading process happened to load.
_EXCEPTION_MODULES = (
    "brambleloop.core.resilience", "brambleloop.queue.durable", "brambleloop.queue.effects",
    "brambleloop.queue.checkpoints", "brambleloop.gateway.paid_calls",
    "brambleloop.gateway.anthropic", "brambleloop.gateway.images",
    "brambleloop.gateway.failover", "brambleloop.gateway.paid_provider_gate",
    "brambleloop.creative.prospecting", "brambleloop.creative.prototype",
    "brambleloop.creative.concept", "brambleloop.commerce.intent",
    "brambleloop.seasonal.cycle",
)
_CLASS = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*:")
_CLASS_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]{1,63}$")


def _known_exception_names() -> frozenset[str]:
    """L1 (READBACK review): the names of every exception class loaded in this process. A name
    is emitted only when it is one of these, so one word of error text ("JaneDoe: refund
    requested") can never travel as an error_class."""
    import importlib

    for mod in _EXCEPTION_MODULES:
        try:
            importlib.import_module(mod)
        except Exception:  # noqa: BLE001 - an unimportable module cannot name a class
            continue
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
        # Review main-integ (Unit B): an owner-directed policy override releases holds, so
        # it must be visible wherever holds are read -- never silent. Unreadable is None.
        "owner_overridden_policy_changes": _overridden_view(db),
    }


def _overridden_view(db):
    try:
        from ..gates.platform_policy import overridden_changes

        return [{"source": str(r.get("source")), "checked_on": str(r.get("checked_on")),
                 "decision": str((r.get("override") or {}).get("decision") or ""),
                 "through": str((r.get("override") or {}).get("through") or ""),
                 "reviewed": False}
                for r in overridden_changes(db)][:SLUGS_PER_STAGE]
    except Exception:  # noqa: BLE001 - unreadable is UNKNOWN (None), never "no override"
        return None


def _exhausted(report_count, detail) -> bool:
    # review M-E of 0d2e6cbc: the one definition the retry hold and the publish gate read
    from ..ops.rebuild_graph import incomplete_exhausted

    return incomplete_exhausted(report_count, detail)


def _legacy(detail) -> bool:
    from ..ops.rebuild_graph import legacy_incomplete

    return legacy_incomplete(detail)


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
        # eng/stale-rebuild-loop: a refused rebuild (withheld, no stored release) finishes
        # DONE and writes neither completion nor unbound evidence -- invisible before.
        refused = list(s.execute(select(AuditLog.detail).where(
            AuditLog.action == "chain.rebuild_refused", AuditLog.at >= d7)))
        incomplete = list(s.execute(select(Incident.signature, Incident.report_count,
                                           Incident.detail).where(
            Incident.resolved == False,  # noqa: E712
            Incident.signature.like("rebuild-incomplete:%"))))
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
        "last_propagation_retry_waiting": len(pd.get("rebuild_retry_waiting") or []),
        "last_propagation_retry_held": len(pd.get("rebuild_retry_held") or {}),
        "last_propagation_retry_held_reasons": dict(list(
            (pd.get("rebuild_retry_held") or {}).items())[:EXAMPLES]),
        "rebuilds_verified_24h": sum(1 for c in real if _aware(c.at) >= d1),
        "rebuilds_verified_48h": sum(1 for c in real if _aware(c.at) >= d2),
        "rebuilds_verified_7d": len(real),
        "rebuilds_already_fresh_7d": len(noop),
        "rebuilds_unbound_7d": len(unbound),
        "rebuilds_refused_7d": len(refused),
        "rebuilds_refused_reasons": sorted({str((d or {}).get("why") or "")[:120]
                                            for (d,) in refused})[:EXAMPLES],
        "open_rebuild_incomplete": len(incomplete),
        # round 2 (review M-A/M-B): a legacy row exhausted by count (no `held` written) is
        # held too, and the named reason is shown, not only the slug.
        "rebuild_incomplete_held": sorted(sig.split(":", 1)[1] for sig, _n, d in incomplete
                                          if _exhausted(_n, d))[:SLUGS_PER_STAGE],
        "rebuild_incomplete_held_reasons": dict(sorted(
            (sig.split(":", 1)[1], str((d or {}).get("held") or f"{_n} attempts")[:200])
            for sig, _n, d in incomplete if _exhausted(_n, d))[:EXAMPLES]),
        # round 3 (review M-E of 0d2e6cbc): a remaining hold is visible to the owner, not
        # silent -- the full count (the lists above are capped), the pre-branch rows still
        # waiting for their first restate under the new budget (retried, not held), and the
        # rows whose legacy count was reset (slug -> the legacy count kept in the row).
        "rebuild_incomplete_held_count": sum(1 for _s, _n, d in incomplete
                                             if _exhausted(_n, d)),
        "rebuild_incomplete_legacy_budget_pending": sorted(
            sig.split(":", 1)[1] for sig, _n, d in incomplete if _legacy(d))[:SLUGS_PER_STAGE],
        "rebuild_incomplete_budget_reset": dict(sorted(
            (sig.split(":", 1)[1],
             int(((d or {}).get("budget_reset") or {}).get("legacy_report_count") or 0))
            for sig, _n, d in incomplete if (d or {}).get("budget_reset"))[:EXAMPLES]),
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


_RELEASE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}@[A-Za-z0-9._+-]{1,40}$")


def _safe_class(name) -> str:
    """A recorded class NAME, emitted only when it is a loaded exception class (L1)."""
    return (name if isinstance(name, str) and _CLASS_NAME.match(name)
            and name in _known_exception_names() else "unclassified")


def listing_package_releases(db, *, now: datetime, hours: int = PASS_WINDOW_HOURS) -> dict:
    """Review of a9feb805 (MEDIUM): releases the `listing.package` job did NOT record.

    A sweep whose final attempt records some releases but not others completes DONE with
    `degraded: true` (so one bad release does not dead-letter the rest), and every failing
    release is audited `listing.package_release_failed`. Neither is a dead letter, so the
    dead-letter readers never saw it: a release failing every six hours passed silently. This
    section reads both. Emitted: `slug@version`, error class names, counts, job ids, times."""
    from sqlalchemy import select

    from ..core.models import AuditLog, Job, JobStatus
    from ..runtime.listing_package_ops import JOB_TYPE, RELEASE_FAILED

    since = now - timedelta(hours=hours)
    with db.session() as s:
        rows = list(s.execute(select(AuditLog.artifact, AuditLog.detail, AuditLog.at,
                                     AuditLog.job_id).where(AuditLog.action == RELEASE_FAILED,
                                                            AuditLog.at >= since)))
        done = list(s.execute(select(Job.id, Job.outputs, Job.finished_at).where(
            Job.job_type == JOB_TYPE, Job.status == JobStatus.DONE, Job.finished_at >= since)))
    releases: dict[tuple, dict] = {}
    for r in rows:
        at = _aware(r.at)
        if at is None or at < since:
            continue
        d = r.detail if isinstance(r.detail, dict) else {}
        key = r.artifact if isinstance(r.artifact, str) and _RELEASE_KEY.match(r.artifact) \
            else "unparseable"
        cls = _safe_class(d.get("error_class"))
        g = releases.setdefault((key, cls), {"release": key, "error_class": cls,
                                             "failed_attempts": 0, "final_attempt_failures": 0,
                                             "newest_at": None, "job_ids": []})
        g["failed_attempts"] += 1
        g["final_attempt_failures"] += 1 if d.get("final_attempt") is True else 0
        if g["newest_at"] is None or at.isoformat() > g["newest_at"]:
            g["newest_at"] = at.isoformat()
        if r.job_id is not None and int(r.job_id) not in g["job_ids"]:
            g["job_ids"] = sorted(g["job_ids"] + [int(r.job_id)], reverse=True)[:EXAMPLES]
    degraded = sorted((int(j.id) for j in done
                       if isinstance(j.outputs, dict) and j.outputs.get("degraded") is True
                       and _aware(j.finished_at) is not None and _aware(j.finished_at) >= since),
                      reverse=True)
    by_release = sorted(releases.values(),
                        key=lambda g: (-g["final_attempt_failures"], -g["failed_attempts"],
                                       g["release"], g["error_class"]))
    return {"readable": True, "window_hours": hours,
            "degraded_sweeps": len(degraded), "degraded_job_ids": degraded[:EXAMPLES],
            "unrecorded_releases": len({g["release"] for g in by_release
                                        if g["final_attempt_failures"]}),
            "final_attempt_failures": sum(g["final_attempt_failures"] for g in by_release),
            "by_release": by_release[:30]}


def judge_listing_package_releases(ev: dict) -> bool:
    """True only when readable and no release went unrecorded on a final attempt."""
    return bool(ev.get("readable") and ev.get("degraded_sweeps") == 0
                and ev.get("final_attempt_failures") == 0)


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
    # W5-A7 (P0-SUPPLY-STALL): the newest recent no-new-concept-supply reading (counts,
    # period and reason only), informational: it changes no verdict here.
    try:
        from .flow_health import concept_supply_stall

        supply = concept_supply_stall(db, now=now)
    except Exception as exc:  # noqa: BLE001
        supply = _unreadable(exc)
    return {"readable": True, "window_days": days,
            "concept_supply_stall": supply,
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


# WS2 R1: the competitor-scan state of the owner's research shops (nine since
# D-OWNER-NINTH-SHOP, 2026-11-19), readable with the readback
# token. Aliases, fixed-vocabulary states, counts and UTC timestamps only -- never a shop name,
# a benchmark key (which embeds one), a URL or error text.
_WATCH_STATES = frozenset({"ok", "source_outage", "credential_refused", "not_accessible",
                           "not_configured"})
_FAILING_WATCH_STATES = ("source_outage", "credential_refused", "not_accessible")


# Review 6816970157 M2: a success older than twice the shop's own interval (at most 48 h) is
# not a CURRENT scan; owner acceptance needs current ones.
STALE_CAP_HOURS = 48.0


def stale_limit_hours(every_hours, interval_hours) -> float:
    """How old a shop's newest success may be before it is stale: twice the slower of its
    cadence and its adaptive interval, never more than STALE_CAP_HOURS (review 6816970157
    M2; 6819096414 LOW-4 pins the adaptive part)."""
    basis = max([h for h in (every_hours, interval_hours)
                 if isinstance(h, (int, float)) and not isinstance(h, bool)] or [0])
    return min(STALE_CAP_HOURS, 2 * basis) if basis else STALE_CAP_HOURS


def _shop_next_due(db, key, st: dict, now) -> tuple[str | None, str | None, float | None]:
    """(next adaptive due time, backoff-until time, adaptive interval hours) for one shop, all
    computed exactly as the scanners decide (`observe.scan_due`, `watchlist.backoff_for`);
    never stored."""
    from ..intel import observe, watchlist

    due_at = backoff_until = interval_h = None
    try:
        due = observe.scan_due(db, benchmark_key=key, now=now)
        last = (due.get("cadence") or {}).get("last_scan_at")
        interval = (due.get("cadence") or {}).get("interval_seconds")
        if isinstance(interval, (int, float)):
            interval_h = round(interval / 3600.0, 2)
        if last and isinstance(interval, (int, float)):
            due_at = _iso(_aware(last) + timedelta(seconds=interval * observe.DUE_TOLERANCE))
    except Exception:  # noqa: BLE001 - an unreadable due time is reported as unknown
        due_at = None
    fails = _int(st.get("consecutive_failures")) or 0
    last_attempt = _aware(st.get("last_attempt_at"))
    if fails and last_attempt is not None and st.get("state") in _FAILING_WATCH_STATES:
        backoff_until = _iso(last_attempt + watchlist.backoff_for(fails))
    return due_at, backoff_until, interval_h


ERRORS_WINDOW_DAYS = 7
_CLASS_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")


def _class_token(value) -> str:
    """An error class fit to leave on the readback route: an identifier, else "other"."""
    return value if isinstance(value, str) and _CLASS_TOKEN.match(value) else "other"


def _errors_7d(db, key: str | None, st: dict, now: datetime) -> dict | None:
    """WS2 R4: failed attempts in the last 7 days, counted by class (never error text).

    A watched shop keeps its own `error_history` (intel.watchlist); the anchor's failures are
    its failed `mjs.scan` jobs (deferrals are not attempts, review R2)."""
    from ..intel import benchmarks
    from ..intel import scan_evidence as SE

    if not key:
        return None
    since = now - timedelta(days=ERRORS_WINDOW_DAYS)
    classes: list[str] = []
    if key == benchmarks.MJS_KEY:
        for j in SE._jobs(db, "mjs.scan", limit=500):
            at = _aware(j.get("finished_at") or j.get("created_at"))
            out = j.get("outputs") or {}
            if at is None or at < since or out.get("deferred"):
                continue
            if j.get("status") in ("dead", "failed") or out.get("ran") is False:
                classes.append("credential_refused" if out.get("credential_refused")
                               else error_class(j.get("error") or str(out.get("reason") or "")))
    else:
        for e in st.get("error_history") or []:
            at = _aware((e or {}).get("at")) if isinstance(e, dict) else None
            if at is not None and since <= at <= now:
                classes.append(e.get("class"))
    by_class: dict[str, int] = {}
    for c in classes:
        t = _class_token(c)
        by_class[t] = by_class.get(t, 0) + 1
    return {"count": len(classes), "by_class": dict(sorted(by_class.items())),
            "window_days": ERRORS_WINDOW_DAYS}


def _anchor_active_count(db) -> int | None:
    """WS2 R4: Etsy's active-listing count from the anchor's newest successful scan."""
    from ..intel import scan_evidence as SE

    for j in SE._jobs(db, "mjs.scan", limit=200):
        out = j.get("outputs") or {}
        if j.get("status") == "done" and out.get("ran") is True:
            return _int(out.get("etsy_active_listing_count"))
    return None


def _not_attempted(db, key, r: dict, now: datetime, held: dict) -> dict | None:
    """ENG watchlist-cadence: why a mandatory shop was not attempted within its cadence --
    None when it was. Fixed cause codes and the scheduler's own sentences; no error text."""
    from ..intel import watchlist
    from ..ops import scheduler_readback as SR

    member = watchlist.BY_KEY.get(key)
    if member is None:
        return None
    period = SR._period_of(SR._job_type_of(member))
    last = _aware(SR.last_attempted(db, member))
    if last is not None and period and (now - last).total_seconds() <= period:
        return None
    cause = SR.shop_not_attempted(db, member, now=now, **held)
    # `detail` is a forbidden key on the read-only route: the scheduler's fixed sentence
    # leaves as `explanation`.
    out = {k: cause.get(k) for k in ("code", "job_type", "until", "incident")
           if cause.get(k) is not None}
    if cause.get("detail"):
        out["explanation"] = cause["detail"]
    return out


def scheduler(db, *, now: datetime) -> dict:
    """ENG watchlist-cadence: suspended job types, blocked departments, per-cadence last
    enqueue and next window, and the mandatory shops silent for > 2x their cadence."""
    from ..ops import scheduler_readback as SR

    out = SR.scheduler_block(db, now=now)
    out["unattempted_mandatory_shops"] = [
        {"alias": _alias(r["key"]), "job_type": r["job_type"],
         "last_attempted": r["last_attempted"], "hours_since": r["hours_since"],
         "limit_hours": r["limit_hours"], "cause": r["cause"].get("code"),
         "cause_explanation": r["cause"].get("detail")}
        for r in SR.unattempted(db, now=now)]
    return out


def _alias(key):
    from ..runtime.intel_ops import benchmark_alias

    return benchmark_alias(key) if key else None


def competitor_scans(db, *, now: datetime) -> dict:
    """Per-shop scan state, in the owner's order (`intel.scan_evidence.OWNER_SHOPS`), from the
    same read-only join `intel.scan_evidence` makes daily -- plus the facts it computes but did
    not project: next due, backoff, Etsy's active-listing count, live (non-withdrawn) listing
    coverage and the downstream research counts per shop. No network."""
    from sqlalchemy import func, select

    from ..core.models import BenchmarkListing, CoverageGap, MjsMissionEvent
    from ..intel import benchmarks
    from ..intel import scan_evidence as SE
    from ..intel import watchlist
    from ..runtime.intel_ops import benchmark_alias

    from ..ops import scheduler_readback as SR

    rep = SE.report(db, now=now)
    stored = SE.latest(db) or {}
    # ENG watchlist-cadence: per shop, why it was not attempted (the scheduler's own reasons)
    held = {"suspended": SR._suspended(db, now), "blocked": SR._blocked(db, now),
            "latest": SR._latest_cadence_jobs(db, now=now)}
    credential = str(rep.get("credential") or "UNKNOWN").split(":")[0].strip()
    rows = []
    with db.session() as s:
        for i, r in enumerate(rep.get("shops") or [], start=1):
            key = r.get("key")
            st = watchlist._state(db, key) if key in watchlist.BY_KEY else {}
            due_at, backoff_until, interval_h = (_shop_next_due(db, key, st, now) if key
                                                 else (None, None, None))
            reason = str(r.get("failure_reason") or "")
            if r.get("state") == SE.SCANNED:
                failure_class = None
            elif st.get("state") in _WATCH_STATES:
                failure_class = st["state"]
            elif "refused the read credential" in reason or re.search(
                    SE._REFUSED_TEXT, reason, re.I):
                # Review 6816970157 L3: the shop's OWN newest failure, never the global
                # credential state painted onto a shop that failed for another reason.
                failure_class = "credential_refused"
            elif r.get("state") == SE.NOT_ACCESSIBLE:
                failure_class = "not_accessible"
            elif r.get("state") == SE.NEVER:
                failure_class = None
            else:
                failure_class = error_class(reason)
            live = mission_events = gaps = None
            if key:
                live = s.scalar(select(func.count()).select_from(BenchmarkListing).where(
                    BenchmarkListing.benchmark_key == key,
                    BenchmarkListing.audit_state != "withdrawn"))
                mission_events = s.scalar(select(func.count()).select_from(MjsMissionEvent)
                                          .where(MjsMissionEvent.benchmark_key == key))
                gaps = s.scalar(select(func.count()).select_from(CoverageGap)
                                .where(CoverageGap.benchmark_key == key))
            schedule = r.get("schedule") or {}
            every = schedule.get("every_hours")
            age = _age_h(r.get("last_successful"), now)
            limit = stale_limit_hours(every, interval_h)
            # Review 6819096414 LOW-1: a scanned shop whose success time cannot be read is
            # stale (fails closed), never current.
            stale = ((age is None or age > limit) if r.get("state") == SE.SCANNED
                     else (age is not None and age > limit))
            rows.append({
                "owner_order": i,
                "alias": benchmark_alias(key) if key else None,
                "role": _name(r.get("owner_role")),
                "state": _name(r.get("state")),
                "method": "etsy_open_api_v3",
                "cadence_job_type": _name(schedule.get("job_type")),
                "cadence_every_hours": schedule.get("every_hours")
                if isinstance(schedule.get("every_hours"), (int, float)) else None,
                "last_attempted": _iso(r.get("last_attempted")),
                "last_successful": _iso(r.get("last_successful")),
                # WS2 R3: Etsy's newest listing modification time in the last successful
                # scan; None when it was not recorded (never our own clock).
                "etsy_source_timestamp": _iso(r.get("source_timestamp")),
                "success_age_hours": age,
                "stale": stale, "stale_after_hours": limit,
                "next_due": due_at,
                "backoff_until": backoff_until,
                "consecutive_failures": _int(r.get("consecutive_failures")),
                "failure_class": failure_class,
                "listings_live": _int(live),
                "listings_seen_last_scan": _int(r.get("listings_seen_last_scan")),
                "etsy_active_listing_count": (
                    _anchor_active_count(db) if key == benchmarks.MJS_KEY else
                    _int((st.get("shop") or {}).get("listing_active_count"))),
                # WS2 R4: failed attempts in the last 7 days, by class.
                "errors_7d": _errors_7d(db, key, st, now),
                "downstream": {"mission_events": _int(mission_events),
                               "coverage_gaps": _int(gaps)},
                "not_attempted_because": _not_attempted(db, key, r, now, held),
            })
    return {"readable": True, "as_of": now.isoformat(), "credential": credential,
            "reading_day": (str(stored.get("as_of") or "")[:10] or None),
            "counts": {str(k)[:40]: v for k, v in (rep.get("counts") or {}).items()
                       if _int(v) is not None},
            "shops": rows}


_SOURCE_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_LISTING_STATES = ("draft", "published", "incomplete_on_etsy", "active", "published_manually",
                   "withdrawn", "retired")


def first_listing_readiness(db, *, now: datetime) -> dict:
    """ENG-FIRSTLIST: which Launch-0 release could become the first Etsy draft, read-only.

    For every certified Launch-0 release with a stored listing: the code's own two readiness
    readings -- the publication approval packet (`ops.publication_authority.evidence`, the
    same reading the owner's Approvals card and `publication.approve` use; every gated section
    must be PASS) and the latest automatic listing package (`publish.listing_package.latest`,
    `ready_for_owner_review` or `blocked`). Emitted: `slug@version`, a 12-character release
    hash prefix, section names with PASS/FAIL/UNKNOWN, blocker *source* identifiers and
    counts, and whether the listing is already on Etsy. No copy, no reason text, no ids of
    grants. Nothing is written, rendered or sent."""
    from sqlalchemy import select

    from ..core.models import Listing, PatternVersion, Product
    from ..ops import publication_authority as pa
    from ..products.launch0 import LAUNCH0_SLUGS
    from ..publish import listing_package

    with db.session() as s:
        rows = list(s.execute(
            select(Product.slug, PatternVersion.version, PatternVersion.release_hash,
                   Listing.state, Listing.etsy_listing_id, Listing.release_hash)
            .join(PatternVersion, PatternVersion.product_id == Product.id)
            .join(Listing, (Listing.product_slug == Product.slug)
                  & (Listing.version == PatternVersion.version))
            .where(PatternVersion.certified == True,  # noqa: E712
                   Product.slug.in_(tuple(LAUNCH0_SLUGS)))
            .order_by(Product.slug, PatternVersion.id.desc())))
    releases, seen = [], set()
    for slug, version, release, state, etsy_id, listing_release in rows:
        if (slug, version) in seen:
            continue
        seen.add((slug, version))
        ev = {}
        try:
            ev = pa.evidence(db, slug, version, release or "")
            sections = {k: str((ev.get(k) or {}).get("state") or pa.UNKNOWN)
                        for k in pa.GATED_SECTIONS}
            sections = {k: (v if v in (pa.PASS, pa.FAIL, pa.UNKNOWN) else pa.UNKNOWN)
                        for k, v in sections.items()}
            evidence_class = None
        except Exception as exc:  # noqa: BLE001 - unreadable is never ready
            sections = {k: pa.UNKNOWN for k in pa.GATED_SECTIONS}
            evidence_class = _safe_class(type(exc).__name__)
        try:
            pkg = listing_package.latest(db, slug, version) or {}
        except Exception:  # noqa: BLE001
            pkg = {}
        pkg_state = pkg.get("state") if pkg.get("state") in (
            listing_package.READY, listing_package.BLOCKED) else None
        blockers = [b for b in (pkg.get("blockers") or []) if isinstance(b, dict)]
        sources = sorted({str(b.get("source")) for b in blockers
                          if isinstance(b.get("source"), str)
                          and _SOURCE_NAME.match(str(b.get("source")))})
        pkg_release = str(pkg.get("release_hash") or "")
        gated_pass = all(v == pa.PASS for v in sections.values())
        releases.append({
            "release": f"{slug}@{version}",
            "release_hash_prefix": str(release or "")[:12],
            "listing_bound_to_release": bool(release) and listing_release == release,
            "listing_state": state if state in _LISTING_STATES else "other",
            "on_etsy": bool(etsy_id),
            "publication_sections": sections,
            "publication_all_gated_pass": gated_pass,
            "evidence_error_class": evidence_class,
            "package_state": pkg_state,
            "package_is_current_release": bool(pkg_release) and pkg_release == release,
            "package_blocker_count": len(blockers),
            "package_blocker_sources": sources[:20],
            "draft_candidate": bool(gated_pass and not etsy_id and pkg_state ==
                                    listing_package.READY and pkg_release == release),
            # ENG-ETSY-PUBLISH: why each non-passing section does not pass, measurable from
            # outside: fixed-vocabulary identifiers, counts and booleans only (no copy, no
            # reason text, no ids of grants).
            "section_diagnostics": _section_diagnostics(ev),
        })
    return {"readable": True, "launch0_slugs": list(LAUNCH0_SLUGS),
            "certified_with_listing": len(releases),
            "draft_candidates": [r["release"] for r in releases if r["draft_candidate"]],
            "releases": releases[:30]}


def _vocab(values, allowed) -> list[str]:
    return sorted({str(v) for v in (values or []) if str(v) in allowed})


def _flag(v):
    return v if isinstance(v, bool) else None


def _section_diagnostics(ev: dict) -> dict:
    """ENG-ETSY-PUBLISH: the measurable half of each gated section, safe to emit.

    parity: which of the eight #75 dimensions are unjudged or failed, and whether the frames
    were independently reviewed. listing_set: whether a valid certificate exists and how many
    frames may export. rollback: which rehearsal steps failed. search: the category status and
    the failing check names. certification: the three booleans that decide it. Anything not
    in a fixed vocabulary is dropped, never echoed."""
    from ..visual import parity as _parity

    if not isinstance(ev, dict) or not ev:
        return {}
    par = ev.get("parity") or {}
    ls = ev.get("listing_set") or {}
    rb = ev.get("rollback") or {}
    se = ev.get("search") or {}
    ce = ev.get("certification") or {}
    frames = [f for f in (ls.get("frames") or []) if isinstance(f, dict)]
    steps = (rb.get("rehearsal") or {}).get("steps") or []
    step_names = ("certificate_retained", "listing_on_record", "deliverables_restorable",
                  "state_round_trip")
    checks = se.get("checks") or {}
    return {
        "parity": {"unjudged": _vocab(par.get("unjudged"), _parity.DIMENSIONS),
                   "failed": _vocab(par.get("failed"), _parity.DIMENSIONS),
                   "frames_judged": _int(par.get("frames_judged")),
                   "frame_review_done": _flag((par.get("frame_review") or {}).get("reviewed")),
                   "exported_frame_review_done": _flag(
                       (par.get("exported_frame_review") or {}).get("reviewed")),
                   "exported_frame_review_applies": _flag(
                       (par.get("exported_frame_review") or {}).get("applies"))},
        "listing_set": {"certificate_valid": _flag((ls.get("certificate") or {}).get("valid")),
                        "blocks_release": _flag(ls.get("blocks_release")),
                        "frames": len(frames),
                        "frames_may_export": sum(1 for f in frames if f.get("may_export") is True),
                        "reason_count": len(ls.get("reasons") or [])},
        "rollback": {"rehearsal_recent": rb.get("rehearsal") is not None,
                     "failing_steps": _vocab([st.get("step") for st in steps
                                              if isinstance(st, dict) and st.get("ok") is False],
                                             step_names)},
        "search": {"category_status": (str(se.get("category_status"))
                                       if _SOURCE_NAME.match(str(se.get("category_status") or "").lower())
                                       else None),
                   "failing_checks": sorted(str(k) for k, v in checks.items()
                                            if v is False and _SOURCE_NAME.match(str(k)))[:12]},
        "certification": {"certificate_granted": _flag(ce.get("certificate_granted")),
                          "release_matches": _flag(ce.get("release_matches")),
                          "withheld": _flag(ce.get("withheld"))},
    }


# ---- ENG-VISUAL: the listing-image and PDF factory, from persisted rows only ---------------

UNKNOWN_COUNT = "UNKNOWN"
# A blocked image run's reason is free text; it is grouped into this fixed vocabulary and
# never emitted. Matched in order, case-insensitively; the first family that matches wins.
BLOCK_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("identity", ("identity", "biometric", "laura")),
    ("product_truth", ("product_truth", "fidelity", "motif", "structural floor")),
    ("budget", ("budget", "spend", "ceiling", "reservation")),
    ("capability_gate", ("capability", "not enabled", "gate closed", "image_vision",
                         "image_generation")),
    ("provider", ("provider", "generator", "flux", "bfl", "timeout", "http")),
    ("references", ("reference", "outfit")),
    ("gallery_set", ("set check", "campaign_consistency", "gallery")),
    ("certified_pattern", ("certified", "certificate", "release")),
)
_TECH_STATUSES = ("PASS", "FAIL", "UNKNOWN", "UNMEASURABLE", "NOT_APPLICABLE")
_CANDIDATE_OUTCOMES = ("accepted", "rejected", "unverified", "provider_error")
_RUN_STATES = ("awaiting_certified_pattern", "awaiting_pre_image_readiness",
               "reference_preparation", "product_generation",
               "lifestyle_generation", "gallery_assembly", "automated_verification",
               "ready_for_owner_review", "blocked", "approved_for_publication")


def block_family(reason) -> str:
    text = str(reason or "").lower()
    for family, needles in BLOCK_FAMILIES:
        if any(n in text for n in needles):
            return family
    return "other" if text else "unrecorded"


def _has_tables(db, *names) -> dict:
    from sqlalchemy import inspect

    have = set(inspect(db.engine).get_table_names())
    return {n: n in have for n in names}


def _vp_pdfs(db) -> dict:
    from sqlalchemy import select

    from ..core.models import PatternVersion, Product
    from ..runtime.pipeline import _certified_pdf_hashes

    with db.session() as s:
        rows = list(s.execute(select(Product.slug, PatternVersion.version,
                                     PatternVersion.release_hash)
                              .join(PatternVersion, PatternVersion.product_id == Product.id)
                              .where(PatternVersion.certified == True)  # noqa: E712
                              .order_by(Product.slug, PatternVersion.id.desc())))
    both, us_only, uk_only, none, missing = 0, 0, 0, 0, []
    for slug, version, release in rows:
        hashes = _certified_pdf_hashes(db, slug, version, release or "") if release else None
        h = hashes or {}
        us, uk = bool(h.get("US")), bool(h.get("UK"))
        if us and uk:
            both += 1
        elif us:
            us_only += 1
        elif uk:
            uk_only += 1
        else:
            none += 1
        if not (us and uk) and len(missing) < SLUGS_PER_STAGE:
            missing.append(f"{slug}@{version}")
    return {"certified_releases": len(rows), "with_us_and_uk_pdf_hashes": both,
            "us_only": us_only, "uk_only": uk_only, "no_certified_pdf": none,
            "releases_missing_a_pdf": missing}


def _vp_runs(db) -> dict:
    from sqlalchemy import select

    from ..visual.image_records import ImageProductionRun as R

    by_state = {k: 0 for k in _RUN_STATES}
    grouped: dict[str, int] = {}
    blocked_examples: list[str] = []
    with db.session() as s:
        for status, stage, reason, exhausted, slug, version in s.execute(
                select(R.status, R.stage, R.blocked_reason, R.attempts_exhausted, R.slug,
                       R.version)):
            st = status if status in _RUN_STATES else "other"
            by_state[st] = by_state.get(st, 0) + 1
            if status == "blocked":
                stg = stage if isinstance(stage, str) and _SOURCE_NAME.match(stage) else "other"
                k = f"{stg}:{block_family(reason)}" + (":exhausted" if exhausted else "")
                grouped[k] = grouped.get(k, 0) + 1
                if len(blocked_examples) < SLUGS_PER_STAGE:
                    blocked_examples.append(f"{slug}@{version}")
    valid = by_state.get("ready_for_owner_review", 0) + by_state.get(
        "approved_for_publication", 0)
    return {"runs": sum(by_state.values()), "by_state": by_state,
            "valid": valid, "blocked": by_state.get("blocked", 0),
            "blocked_reasons_grouped": dict(sorted(grouped.items())),
            "blocked_releases": blocked_examples}


def _vp_images(db) -> tuple[dict, dict]:
    from sqlalchemy import select

    from ..visual.image_records import ImageCandidate as C

    tech = {k: 0 for k in _TECH_STATUSES}
    outcome = {k: 0 for k in _CANDIDATE_OUTCOMES}
    method: dict[str, int] = {}
    ident = {"laura_frames": 0, "run": 0, "passed": 0, "failed": 0, "not_run": 0,
             "unknown": 0, "fixture_only": 0, "biometric_measured": 0}
    with db.session() as s:
        for ts, oc, meth, laura, checks in s.execute(
                select(C.technical_status, C.outcome, C.method, C.laura_present, C.checks)):
            tech[ts if ts in _TECH_STATUSES else "UNKNOWN"] += 1
            outcome[oc if oc in _CANDIDATE_OUTCOMES else "unverified"] += 1
            m = meth if isinstance(meth, str) and _SOURCE_NAME.match(meth) else "other"
            method[m] = method.get(m, 0) + 1
            if not laura:
                continue
            ident["laura_frames"] += 1
            idc = (checks or {}).get("identity") if isinstance(checks, dict) else None
            if not isinstance(idc, dict) or not idc.get("status"):
                ident["not_run"] += 1
                continue
            if idc.get("fixture_only"):
                # A fixture reading tests the wiring; it is never an identity verification.
                ident["fixture_only"] += 1
                ident["not_run"] += 1
                continue
            ident["run"] += 1
            st = str(idc.get("status"))
            if st == "PASS":
                ident["passed"] += 1
            elif st == "FAIL":
                ident["failed"] += 1
            else:
                ident["unknown"] += 1
            if str((idc.get("biometric") or {}).get("status") or "").upper() in ("PASS",
                                                                                 "FAIL"):
                ident["biometric_measured"] += 1
    images = {"candidates": sum(tech.values()), "by_method": method,
              "verified": tech["PASS"], "failed": tech["FAIL"],
              "unmeasurable": tech["UNKNOWN"] + tech["UNMEASURABLE"],
              "by_technical_status": tech, "by_outcome": outcome}
    return images, ident


def _vp_identity_method() -> dict:
    """Whether production could run a qualified identity check at all (no row involved)."""
    out: dict = {}
    try:
        from ..visual import canonical
        from ..visual.vision_judges import SECOND_VISION_TRANSPORT, canonical_reference_bytes

        refs = canonical_reference_bytes()
        out["identity_id"] = str(getattr(canonical, "IDENTITY_ID", "") or "")[:40]
        out["canonical_references_expected"] = len(canonical.CURRENT_REFERENCE_HASHES)
        out["canonical_references_verified"] = sum(1 for v in refs.values() if v)
        out["second_vision_transport_configured"] = SECOND_VISION_TRANSPORT is not None
    except Exception as exc:  # noqa: BLE001
        out["canonical_error_class"] = _safe_class(type(exc).__name__)
    # Read from the code's own registers (visual.identity_gate): a production-qualified
    # identity check needs an owner-approved embedder qualification AND a second, independent
    # vision transport. Unreadable is not qualified.
    try:
        from ..visual import identity_gate as ig

        quals = len(ig.PRODUCTION_QUALIFICATIONS)
    except Exception as exc:  # noqa: BLE001
        quals = None
        out["qualification_error_class"] = _safe_class(type(exc).__name__)
    out["production_embedder_qualifications"] = quals if quals is not None else UNKNOWN_COUNT
    out["production_qualified"] = bool(
        isinstance(quals, int) and quals > 0
        and out.get("second_vision_transport_configured") is True
        and out.get("canonical_references_verified") == out.get(
            "canonical_references_expected"))
    return out


def _vp_packages(db) -> dict:
    from sqlalchemy import select

    from ..core.models import OperatingReading
    from ..publish import listing_package as lp

    ready, blocked, other, ready_rel, sources = 0, 0, 0, [], {}
    with db.session() as s:
        for key, payload in s.execute(select(OperatingReading.period_key,
                                             OperatingReading.payload)
                                      .where(OperatingReading.kind == lp.KIND)):
            p = payload or {}
            if p.get("state") == lp.READY:
                ready += 1
                if len(ready_rel) < SLUGS_PER_STAGE:
                    ready_rel.append(str(key)[:120])
            elif p.get("state") == lp.BLOCKED:
                blocked += 1
                for b in p.get("blockers") or []:
                    src = b.get("source") if isinstance(b, dict) else None
                    if isinstance(src, str) and _SOURCE_NAME.match(src):
                        sources[src] = sources.get(src, 0) + 1
            else:
                other += 1
    return {"listing_ready": ready, "blocked": blocked, "other": other,
            "ready_releases": ready_rel, "blocker_sources": dict(sorted(sources.items()))}


def _vp_drafts(db) -> dict:
    """Real Etsy drafts: the newest `store.publish*` audit row per release that names a listing,
    with what its read-back proved about the files and the images."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    acts = ("store.published", "store.publish_incomplete")
    newest: dict[str, dict] = {}
    with db.session() as s:
        for art, detail in s.execute(select(AuditLog.artifact, AuditLog.detail)
                                     .where(AuditLog.action.in_(acts))
                                     .order_by(AuditLog.id.desc())):
            d = detail or {}
            if not art or art in newest or not d.get("etsy_listing_id"):
                continue
            newest[art] = d
    rows = []
    for art, d in newest.items():
        rb = d.get("read_back") or {}
        files = rb.get("files") or {}
        images = rb.get("images") or {}
        attached = d.get("files_attached_by_terminology") or {}
        rows.append({
            "release": str(art)[:120],
            "read_back_verified": rb.get("verified") is True,
            "files_read_back_verified": (files.get("verified") is True
                                         if isinstance(files, dict) else False),
            "pdfs_attached": sorted(t for t, v in attached.items()
                                    if v is True and t in ("US", "UK")),
            "images_uploaded": _int(d.get("images_uploaded")),
            "images_read_back_verified": (images.get("verified") is True
                                          if isinstance(images, dict) else False),
        })
    return {"drafts": len(rows),
            "fully_read_back": sum(1 for r in rows if r["read_back_verified"]
                                   and r["files_read_back_verified"]
                                   and set(r["pdfs_attached"]) == {"US", "UK"}
                                   and r["images_read_back_verified"]),
            "releases": rows[:30]}


_GALLERY_ROLES = ("hero", "colour_context", "lifestyle", "angle", "detail", "size")


def _independent(checks) -> bool:
    """A PASS made with no test double and no fixture stand-in in any of its readings."""
    if not isinstance(checks, dict):
        return False
    for k, c in checks.items():
        if str(k).startswith("_") or not isinstance(c, dict):
            continue
        if c.get("test_double") or c.get("fixture_only"):
            return False
        fid = c.get("fidelity")
        if isinstance(fid, dict) and (fid.get("test_double") or fid.get("fixture_only")):
            return False
    return True


def _vp_generated(db) -> dict:
    """D-OWNER-FLUX-GALLERY: the seven-frame generated galleries, counted from rows only.

    Images generated and recovered in generated-gallery runs; how many are independently
    verified (technical PASS with no test-double or fixture reading); Laura identity passes
    and holds; completed (certified) seven-image galleries; products whose certified gallery
    awaits publication; verified Etsy drafts of them; spend and cost per completed gallery.
    Counts only: no prompt, image, reason text or listing id."""
    from sqlalchemy import select

    from ..core.models import AuditLog, ListingSetCertificateRecord
    from ..visual.image_production import ROUTE_SUFFIX
    from ..visual.image_records import ImageCandidate as C
    from ..visual.image_records import ImageProductionRun as R

    runs: dict[str, dict] = {}
    with db.session() as s:
        for key, slug, version, spent in s.execute(select(R.run_key, R.slug, R.version,
                                                          R.spent_cad)):
            if ROUTE_SUFFIX in str(key or "").split("#")[0]:
                runs[key] = {"release": f"{slug}@{version}", "spent": float(spent or 0)}
        img = {"generated": 0, "recovered": 0, "independently_verified": 0,
               "verified_with_test_doubles": 0, "failed": 0, "unmeasured": 0}
        laura = {"frames": 0, "identity_passed": 0, "identity_held": 0}
        for key, role, meth, ts, lp, checks, sha in s.execute(
                select(C.run_key, C.role, C.method, C.technical_status, C.laura_present,
                       C.checks, C.sha256).where(C.run_key.in_(list(runs) or [""]))):
            if role not in _GALLERY_ROLES or not sha:
                continue
            img["recovered" if meth == "recovered" else "generated"] += 1
            if ts == "PASS":
                img["independently_verified" if _independent(checks)
                    else "verified_with_test_doubles"] += 1
            elif ts == "FAIL":
                img["failed"] += 1
            else:
                img["unmeasured"] += 1
            if lp:
                laura["frames"] += 1
                idc = (checks or {}).get("identity") if isinstance(checks, dict) else None
                ok = (isinstance(idc, dict) and idc.get("status") == "PASS"
                      and not idc.get("fixture_only") and not idc.get("test_double"))
                laura["identity_passed" if ok else "identity_held"] += 1
        completed: set[str] = set()
        for slug, version, cert in s.execute(
                select(ListingSetCertificateRecord.product_slug,
                       ListingSetCertificateRecord.version,
                       ListingSetCertificateRecord.certificate)
                .where(ListingSetCertificateRecord.state == "valid")):
            frames = (cert or {}).get("frames") or []
            gen = [f for f in frames if f.get("kind") == "generated_render"]
            if len(frames) == 7 and len(gen) == 6:
                completed.add(f"{slug}@{version}")
        blocked_by_gate: dict[str, int] = {}
        latest: dict[str, dict] = {}
        for art, d in s.execute(select(AuditLog.artifact, AuditLog.detail).where(
                AuditLog.action == "images.generated_gallery_certify")
                .order_by(AuditLog.id.desc())):
            if art and art not in latest:
                latest[art] = d or {}
        for art, d in latest.items():
            if d.get("certified") or art in completed:
                continue
            for b in d.get("blockers") or []:
                g = str((b or {}).get("gate") or "?")
                g = g if _SOURCE_NAME.match(g) else "other"
                blocked_by_gate[g] = blocked_by_gate.get(g, 0) + 1
        published = {}
        for art, d in s.execute(select(AuditLog.artifact, AuditLog.detail).where(
                AuditLog.action == "store.published").order_by(AuditLog.id.desc())):
            if art in completed and art not in published:
                rb = (d or {}).get("read_back") or {}
                published[art] = bool(rb.get("verified") is True and (rb.get("images") or {})
                                      .get("verified") is True)
    spent_done = sum(r["spent"] for r in runs.values() if r["release"] in completed)
    return {
        "runs": len(runs), "images": img, "laura_identity": laura,
        "completed_seven_image_galleries": len(completed),
        "blocked_galleries": len([a for a, d in latest.items()
                                  if not d.get("certified") and a not in completed]),
        "blocked_by_gate": blocked_by_gate,
        "awaiting_publication": len(completed - set(published)),
        "etsy_drafts_verified": sum(1 for v in published.values() if v),
        "spent_cad": round(sum(r["spent"] for r in runs.values()), 4),
        "cost_per_completed_gallery_cad": (round(spent_done / len(completed), 4)
                                           if completed else UNKNOWN_COUNT),
    }


def visual_pipeline(db, *, now: datetime) -> dict:
    """ENG-VISUAL: certified pattern -> PDFs -> images -> identity/product QA -> gallery ->
    listing package -> Etsy draft, counted from persisted rows only.

    A part that cannot be read is reported as UNKNOWN (never 0), with the class of the reason;
    a count that has no producer yet (recovered images) is UNKNOWN with `not_measured_because`.
    No prompt, reason text, image bytes, copy or listing id is emitted."""
    out: dict = {"readable": True}

    def part(name, fn, *a):
        try:
            return fn(*a)
        except Exception as exc:  # noqa: BLE001 - unreadable is UNKNOWN, never 0
            return {"readable": False, "count": UNKNOWN_COUNT,
                    "error_class": _safe_class(type(exc).__name__)}

    out["certified_pdfs"] = part("certified_pdfs", _vp_pdfs, db)
    try:
        tables = _has_tables(db, "image_production_runs", "image_candidates")
    except Exception as exc:  # noqa: BLE001
        tables = {"image_production_runs": None, "image_candidates": None}
        out["table_probe_error_class"] = _safe_class(type(exc).__name__)
    if tables.get("image_production_runs"):
        out["galleries"] = part("galleries", _vp_runs, db)
    else:
        out["galleries"] = {"readable": False, "count": UNKNOWN_COUNT,
                            "why": "image_production_runs table absent or unprobed"}
    if tables.get("image_candidates"):
        try:
            out["images"], out["laura_identity_checks"] = _vp_images(db)
        except Exception as exc:  # noqa: BLE001
            u = {"readable": False, "count": UNKNOWN_COUNT,
                 "error_class": _safe_class(type(exc).__name__)}
            out["images"], out["laura_identity_checks"] = u, dict(u)
    else:
        u = {"readable": False, "count": UNKNOWN_COUNT,
             "why": "image_candidates table absent or unprobed"}
        out["images"], out["laura_identity_checks"] = u, dict(u)
    out["laura_identity_method"] = _vp_identity_method()
    out["recovered_images"] = _vp_recovered(db)
    if tables.get("image_production_runs") and tables.get("image_candidates"):
        out["generated_galleries"] = part("generated_galleries", _vp_generated, db)
    else:
        out["generated_galleries"] = {"readable": False, "count": UNKNOWN_COUNT,
                                      "why": "image tables absent or unprobed"}
    out["listing_packages"] = part("listing_packages", _vp_packages, db)
    out["etsy_drafts"] = part("etsy_drafts", _vp_drafts, db)
    try:
        from ..visual.shot_plans import CAMPAIGN_MIN_FRAMES

        out["gallery_standard_frames"] = CAMPAIGN_MIN_FRAMES
    except Exception:  # noqa: BLE001
        out["gallery_standard_frames"] = UNKNOWN_COUNT
    return out


def _vp_recovered(db) -> dict:
    """Images recovered by the motif backlog. No producer exists on this build: UNKNOWN."""
    try:
        from ..visual import motif_backlog  # type: ignore[attr-defined]  # noqa: F401
    except Exception:  # noqa: BLE001
        return {"count": UNKNOWN_COUNT,
                "not_measured_because": "motif backlog recovery not on this build"}
    fn = getattr(motif_backlog, "recovered_count", None)
    if not callable(fn):
        return {"count": UNKNOWN_COUNT,
                "not_measured_because": "motif backlog exposes no recovered count"}
    try:
        n = fn(db)
    except Exception as exc:  # noqa: BLE001
        return {"count": UNKNOWN_COUNT, "error_class": _safe_class(type(exc).__name__)}
    return {"count": n if isinstance(n, int) else UNKNOWN_COUNT}


# ---- the anonymous-safe checks ----------------------------------------------------------

def learning(db, *, now: datetime | None = None) -> dict:
    """ENG-LEARN: per learning loop, its metric's latest window and trend, active lessons,
    lessons a department acted on, and promotions/demotions. Rates and counts only; UNKNOWN
    where the sample is too small (`learning.progress.readback`)."""
    from ..learning import progress

    return {"readable": True, **progress.readback(db, now=now)}


def sale_pipeline(db, *, now: datetime) -> dict:
    """ENG-SALE-PIPELINE (D-OWNER-SALE-PIPELINE): counts only -- eligible, gallery done, PDFs
    certified, READY, blocked by named reason, stalled. No copy, slug lists or reason text."""
    from ..publish import sale_pipeline as SPL

    b = SPL.board(db, now=now)
    if not b.get("readable"):
        return {"readable": False, "error_class": _safe_class(str(b.get("error_class") or ""))}
    reasons = {k: v for k, v in b["blocked_by_reason"].items() if _SOURCE_NAME.match(str(k))}
    pre = {k: v for k, v in b["awaiting_pre_image_by_reason"].items()
           if _SOURCE_NAME.match(str(k))}
    return {"readable": True, **{k: b[k] for k in (
        "releases", "eligible", "gallery_done", "pdfs_certified", "ready", "stalled",
        "awaiting_pre_image_readiness", "awaiting_admission", "parked", "rejected",
        "reserved_cad", "per_listing_cap_cad")},
        "blocked_by_reason": reasons, "awaiting_pre_image_by_reason": pre}
def motif_backlog_recovery(db, *, now: datetime) -> dict:
    """ENG-MOTIF-BACKLOG (owner P0): paid renders whose motif check the budget gate refused,
    and what the recovery made of them. Counts only (`publish.motif_backlog.report`, from the
    persisted `motif_recovery` rows); a backlog never swept is UNKNOWN, never 0."""
    from ..publish import motif_backlog

    rep = motif_backlog.report(db)
    if not rep.get("readable"):
        return {"readable": False, "error_class": str(rep.get("why") or "unreadable")[:80]}
    return {"readable": True, "swept": rep.get("swept"),
            "last_sweep_at": rep.get("last_sweep_at"), "counts": rep.get("counts"),
            "recheck_spend_cad": rep.get("recheck_spend_cad")}


SECTIONS = {
    "dead_letters_24h": dead_letters,
    "publishing_halt": publishing_halt,
    "stale_artefact_rebuilds": stale_rebuilds,
    "paid_call_dedupe": paid_calls,
    "weekly_jobs": weekly_jobs,
    "certification_pipeline": certification,
    "autonomy_loop": autonomy_loop,
    "etsy_taxonomy": etsy_taxonomy,
    "competitor_scans": competitor_scans,
    "listing_package_releases": listing_package_releases,
    "scheduler": scheduler,
    "first_listing_readiness": first_listing_readiness,
    "motif_backlog_recovery": motif_backlog_recovery,
    "visual_pipeline": visual_pipeline,
    "learning": learning,
    "sale_pipeline": sale_pipeline,
}
CHECK_NAMES = ("publishing_halt_clear", "stale_artefacts_rebuilding",
               "no_repeated_paid_call_in_24h", "weekly_jobs_completing")


def daily_ledger(db, *, now: datetime) -> dict:
    """ENG-DAILY: per-UTC-day production counts (14 days), counts only; spend as recorded or
    not, never an amount (`ops.daily_ledger.readback`)."""
    from .daily_ledger import readback

    return readback(db, now=now)


SECTIONS["daily_ledger"] = daily_ledger


def engine_demand(db, *, now: datetime) -> dict:
    """ENG-DEMAND-SUPPLY: the ranked engines held concepts wait for, and demand per family,
    from stored evidence (`products.demand.readback`). Counts and keys only."""
    from ..products.demand import readback

    return readback(db, now=now)


SECTIONS["engine_demand"] = engine_demand


def autocoder(db, *, now: datetime) -> dict:
    """ENG-AUTOCODER: the coding job's switch, blockers and request counts by status. Counts
    and booleans only, never an amount (`improve.autocoder.readback`)."""
    from ..improve.autocoder import readback

    return readback(db, now=now)


SECTIONS["autocoder"] = autocoder


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
                                   "open_stale_artefact_incidents",
                                   # round 3 (M-E): a held rebuild is named here, not silent
                                   "rebuild_incomplete_held_count",
                                   "rebuild_incomplete_held_reasons",
                                   "rebuild_incomplete_legacy_budget_pending"))},
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
    # WS5 E3: the server's usable-for-operations judgement, not "two variables are set".
    "/api/etsy": "credential.usable",
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
            cur = body
            for part in field.split("."):          # a dotted field reads a nested value
                cur = cur.get(part) if isinstance(cur, dict) else None
            fields[field] = _project_value(cur)
        out[route] = {"status": status, "fields": fields}
    return out


def evidence(db, *, now: datetime | None = None, deploy_handlers: dict | None = None) -> dict:
    """The body of GET /api/readback/evidence (read-only token)."""
    now = _aware(now) or datetime.now(timezone.utc)
    sections = {name: _section(name, db, now) for name in SECTIONS}
    try:  # not a judged section: visibility only (no readback row, no verdict)
        sections["factory_visibility"] = factory_visibility(db, now=now)
    except Exception as exc:  # noqa: BLE001
        sections["factory_visibility"] = _unreadable(exc)
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
    # Review of a9feb805: a degraded listing-package sweep is not a dead letter but is a
    # release left unrecorded; judged beside the dead letters so it can never pass silently.
    judged["no_unrecorded_listing_releases_in_24h"] = judge_listing_package_releases(
        sections["listing_package_releases"])
    return {"as_of": now.isoformat(), "read_only": True,
            "never_included": ["job inputs/outputs", "error text", "incident text",
                               "paid-call payloads", "conversations", "owner data",
                               "customer data", "secrets"],
            "server_judgement": judged, **sections}


# ---- factory visibility (read-only; counts and fixed vocabulary only) --------------------

_VIS_JOB_TYPES = ("listing.package", "visual.image_production", "ops.owner_queue_consolidate",
                  "assets.generated_gallery", "visual.gallery_certify")


def factory_visibility(db, *, now: datetime) -> dict:
    """What the factory is doing right now, for the read-only token. It carries no job inputs
    or outputs, no error text and no secret: job counts by type and status (24 h), FLUX image
    runs by state, which paid providers are active (names only), and the owner Etsy-exercise
    attempts (outcome class only)."""
    from collections import Counter

    from sqlalchemy import select

    from ..core.models import Job

    out: dict = {"readable": True}
    since = now - timedelta(hours=24)
    try:
        with db.session() as s:
            rows = s.execute(select(Job.job_type, Job.status, Job.created_at)
                             .where(Job.job_type.in_(_VIS_JOB_TYPES))).all()
        jobs: Counter = Counter()
        for jt, st, at in rows:
            at = _aware(at)
            if at is None or at >= since:
                jobs[f"{jt}:{getattr(st, 'value', st)}"] += 1
        out["jobs_24h"] = dict(sorted(jobs.items()))
    except Exception as exc:  # noqa: BLE001
        out["jobs_24h"] = _unreadable(exc)
    try:
        from ..visual.image_records import ImageProductionRun, ensure_tables

        ensure_tables(db)
        with db.session() as s:
            states = Counter(str(r.status) for r in s.scalars(select(ImageProductionRun)))
        out["image_runs_by_state"] = dict(sorted(states.items()))
    except Exception as exc:  # noqa: BLE001
        out["image_runs_by_state"] = _unreadable(exc)
    try:  # why each parked run is not admitted: blocker sources and leading codes only
        import re as _re

        from ..visual import image_production as IP
        from ..visual.image_records import ImageProductionRun

        with db.session() as s:
            parked = [(r.slug, r.version, r.release) for r in s.scalars(
                select(ImageProductionRun).where(ImageProductionRun.status == IP.SALE_WAITING))]
        why = []
        for slug, version, release in parked[:12]:
            adm = IP.sale_admission(db, slug, version, release)
            codes = []
            for b in adm.get("non_image_blockers") or []:
                if not isinstance(b, dict):
                    continue
                m = _re.match(r"\s*([A-Za-z_][A-Za-z0-9_.]{0,40})", str(b.get("why") or ""))
                codes.append(f"{b.get('source')}:{m.group(1) if m else '?'}")
            why.append({"run": f"{slug}@{version}", "admitted": bool(adm.get("admitted")),
                        "blockers": codes[:8] or ([] if adm.get("admitted") else
                                                  [_re.sub(r"[^a-z_ ]", "", str(
                                                      adm.get("why") or "")[:60].lower())])})
        out["parked_admission"] = why
    except Exception as exc:  # noqa: BLE001
        out["parked_admission"] = _unreadable(exc)
    try:
        from ..gateway import paid_provider_gate as G

        G.ensure_tables(db)
        act = {}
        for provider, scope in (("flux-3-image", "generation"), ("openai-vision", "vision")):
            st = G.activation_state(db, provider, scope, now=now)
            act[f"{provider}:{scope}"] = bool(st.get("active"))
        out["paid_activations_active"] = act
    except Exception as exc:  # noqa: BLE001
        out["paid_activations_active"] = _unreadable(exc)
    try:
        from . import owner_etsy_exercise as OEE

        out["owner_etsy_exercise"] = [
            {"attempt": a.get("attempt"), "ok": a.get("ok"), "status": a.get("status"),
             "refused": a.get("refused")} for a in OEE._attempts(db)]
    except Exception as exc:  # noqa: BLE001
        out["owner_etsy_exercise"] = _unreadable(exc)
    return out
