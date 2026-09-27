"""The MJs mission: recording evidence, and refusing a report that says nothing.

Requirements 318 and 319. #319 is unusually direct about the failure it expects: *"A system
report that says only 'competitor scan complete' fails this mandate."* That is a real thing
autonomous systems do -- they report the job status instead of the finding, because the job
status is what the job knows. So the report is validated the way a release is: a mission
report that cannot name the shop, the timestamp, what it covered, what changed, which listings
and images it inspected, which pods received the evidence and what happened as a result is
refused rather than filed.

Everything recorded here is graded through `launch.access` first, so an observation cannot
claim to satisfy the mandate while the capability that would produce it does not exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..launch import access
from . import benchmarks, coverage, pods

REQUIRED_REPORT_FIELDS: tuple[str, ...] = (
    "benchmark", "observed_at", "catalogue_coverage", "changes", "listings_inspected",
    "images_inspected", "pods_notified", "actions",
)

# Phrases that are the failure #319 names, in the words a status-reporting system reaches for.
_EMPTY_CLAIMS = ("scan complete", "monitoring active", "competitor scan", "no changes found",
                 "analysis complete", "up to date")


class ReportRefused(Exception):
    """A mission report that does not say what happened."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Recorded:
    observation_id: int
    grade: str
    satisfies_mandate: bool
    note: str


def record(db, *, benchmark_key: str, kind: str, detail: dict,
           listing_ref: str = "", pods_notified: tuple[str, ...] = (),
           mechanisms: tuple[dict, ...] = (), actions: tuple[str, ...] = (),
           env: dict[str, str] | None = None) -> Recorded:
    """Store one dated piece of benchmark evidence at the grade it actually earns.

    The grade is decided by whether the observation capability exists, not by what the caller
    called the evidence (#224). That is why this is the only way into the table.
    """
    from ..core.models import BenchmarkObservation

    acceptance = access.accept_evidence(
        kind, capability_available=access.available("benchmark_observation", env))

    unknown_pods = [p for p in pods_notified if p not in pods.POD_KEYS]
    if unknown_pods:
        raise ReportRefused(f"evidence routed to pods that do not exist: {unknown_pods}")

    with db.session() as s:
        row = BenchmarkObservation(
            benchmark_key=benchmark_key, listing_ref=listing_ref, kind=kind,
            grade=acceptance.grade, satisfies_mandate=acceptance.satisfies_mandate,
            pods_notified=list(pods_notified), mechanisms=[dict(m) for m in mechanisms],
            actions=list(actions), detail=dict(detail))
        s.add(row)
        s.flush()
        return Recorded(row.id, acceptance.grade, acceptance.satisfies_mandate,
                        acceptance.note)


def check_report(report: dict) -> None:
    """Refuse a mission report that is a status line wearing a report's name (#319)."""
    missing = [f for f in REQUIRED_REPORT_FIELDS if f not in report]
    if missing:
        raise ReportRefused(
            f"a mission report must name {sorted(missing)}. 'Scan complete' is the failure "
            f"this check exists for: it reports what the job did, not what was found")

    named = str(report.get("benchmark") or "")
    if benchmarks.MJS_SHOP.lower() not in named.lower():
        raise ReportRefused(
            f"the report names {named!r}. The owner's mandate is one specific shop by name "
            f"and forbids generalising it into 'proven sellers' (#301)")

    if not report.get("observed_at"):
        raise ReportRefused("undated evidence is not evidence")

    summary = str(report.get("summary") or "").strip().lower()
    if summary and len(summary) < 40 and any(p in summary for p in _EMPTY_CLAIMS):
        raise ReportRefused(
            f"the summary {summary!r} says only that the job ran. Say what was covered, what "
            f"changed and what happened as a result")

    coverage_ = report.get("catalogue_coverage") or {}
    if not isinstance(coverage_, dict) or "listings_known" not in coverage_:
        raise ReportRefused(
            "catalogue coverage must state how many listings are known and how many were "
            "inspected, so a partial baseline cannot read as a complete one (#207)")


def mission_report(db, *, benchmark_key: str = benchmarks.MJS_KEY,
                   env: dict[str, str] | None = None) -> dict:
    """The mission's state as evidence rather than as a claim (#318).

    Reports the capability first. A dashboard whose top line is coverage, computed from an
    empty table, reads as a healthy mission with nothing in it.
    """
    from sqlalchemy import desc, select

    from ..core.models import Benchmark, BenchmarkListing, BenchmarkObservation

    capability = access.available("benchmark_observation", env)

    with db.session() as s:
        bench = s.scalar(select(Benchmark).where(Benchmark.key == benchmark_key))
        listings = list(s.scalars(select(BenchmarkListing).where(
            BenchmarkListing.benchmark_key == benchmark_key)))
        observations = list(s.scalars(
            select(BenchmarkObservation)
            .where(BenchmarkObservation.benchmark_key == benchmark_key)
            .order_by(desc(BenchmarkObservation.id)).limit(20)))
        mandated = [o for o in observations if o.satisfies_mandate]
        last_mandated = mandated[0].at.isoformat() if mandated else None
        registry = {
            "shop_name": bench.shop_name if bench else benchmarks.MJS_SHOP,
            "canonical_url": bench.canonical_url if bench else benchmarks.MJS_CANONICAL_URL,
            # #301 wants the owner's own URL present in the registry and in acceptance
            # evidence, so it is on the dashboard verbatim rather than tidied.
            "owner_supplied_url": (bench.owner_supplied_url if bench
                                   else benchmarks.MJS_OWNER_SUPPLIED_URL),
            "mandatory": bool(bench.mandatory) if bench else True,
            "scan_health": (bench.scan_health if bench else {"state": benchmarks.UNVERIFIED}),
            "last_scan_at": (bench.last_scan_at.isoformat()
                             if bench and bench.last_scan_at else None),
            "last_baseline_at": (bench.last_baseline_at.isoformat()
                                 if bench and bench.last_baseline_at else None),
        }

    by_pod: dict[str, int] = {}
    for listing in listings:
        by_pod[listing.pod or pods.UNCLASSIFIED] = by_pod.get(
            listing.pod or pods.UNCLASSIFIED, 0) + 1
    audited = [listing for listing in listings if listing.audit_state == "audited"]

    return {
        "mandate": ("MJsOffTheHookDesigns is the named anchor benchmark, non-negotiable and "
                    "not generalisable into 'watch proven sellers' (#301)."),
        "capability_available": capability,
        "observation_state": ("observing" if capability else
                              "blocked — no observation capability has been granted"),
        "registry": registry,
        "catalogue_coverage": {
            "listings_known": len(listings),
            "listings_audited": len(audited),
            "gallery_audited": sum(1 for listing in listings
                                   if listing.detail.get("gallery_audited")),
            "by_pod": by_pod,
            "unclassified": by_pod.get(pods.UNCLASSIFIED, 0),
        },
        "last_mandated_evidence_at": last_mandated,
        "recent_observations": [{
            "at": o.at.isoformat(), "kind": o.kind, "grade": o.grade,
            "satisfies_mandate": o.satisfies_mandate, "listing_ref": o.listing_ref,
            "pods_notified": o.pods_notified, "actions": o.actions,
        } for o in observations],
        "pods": [{"key": p.key, "name": p.name, "rubric": list(p.rubric)} for p in pods.PODS],
        "gap_queue": coverage.summary(db, benchmark_key),
        # #318's remaining fields, each computed from the rows the mission writes.
        **mission_status(db, benchmark_key=benchmark_key, observations=observations),
        # #224, on the dashboard rather than in a footnote: the mission cannot look busy
        # while the capability that would make it real does not exist.
        "honest_statement": (
            "No mandated observation has been performed. The pods, the coverage matrix and "
            "the gap queue exist and are empty of benchmark evidence, because evidence "
            "requires the observation capability the owner has not yet granted. Nothing here "
            "is filled in from search snippets, screenshots or fixtures."
            if not capability else
            "Observation capability is configured; coverage above is measured, not assumed."),
    }


def mission_status(db, *, benchmark_key: str = benchmarks.MJS_KEY,
                   observations: list | None = None) -> dict:
    """#318: the command-centre fields beyond coverage, from rows. Unmeasured says so."""
    from collections import Counter

    from sqlalchemy import desc, func, select

    from ..core.models import (AuditLog, BenchmarkObservation, Incident, Listing,
                               MjsMissionEvent, Order)
    from ..creative.intake import intake_rows

    with db.session() as s:
        if observations is None:
            observations = list(s.scalars(
                select(BenchmarkObservation)
                .where(BenchmarkObservation.benchmark_key == benchmark_key)
                .order_by(desc(BenchmarkObservation.id)).limit(20)))
        scans = [o for o in observations if o.kind == "official_api_read"]
        changes = Counter()
        for o in scans[:1]:
            for c in (o.detail or {}).get("changes") or []:
                changes[str(c.get("what") or "other")] += 1
        events = list(s.scalars(select(MjsMissionEvent).where(
            MjsMissionEvent.benchmark_key == benchmark_key)
            .order_by(desc(MjsMissionEvent.id)).limit(200)))
        assignments = Counter(e.pod for e in events)
        adaptations, deadlines = [], []
        for e in events:
            target = (e.seasonal or {}).get("target") or {}
            if not (e.entered and target):
                continue
            winner = intake_rows(db, mjs_event_id=e.id, limit=50)
            win = winner[0] if winner else None
            adaptations.append({
                "event_id": e.id, "arena": e.arena, "pod": e.pod,
                "event": target.get("event"),
                "lenses": sorted((((e.seasonal or {}).get("seasonalise") or {})
                                  .get("lenses") or {}).keys())
                if isinstance(((e.seasonal or {}).get("seasonalise") or {}).get("lenses"),
                              dict) else [],
                "winner": win[1] if win else None,
                "winner_decision": win[2].get("decision") if win else None,
                "pipeline_stopped_at": ((e.pipeline or {}).get("stopped") or {}).get("stage"),
            })
            deadlines.append({"event_id": e.id, "arena": e.arena, "event": target.get("event"),
                              "preferred_launch": target.get("preferred_launch"),
                              "latest_effective_launch": target.get("latest_effective_launch"),
                              "status": ((e.sentinel or {}).get("status")
                                         or target.get("status"))})
        winners = sorted({a["winner"] for a in adaptations if a["winner"]})
        comparisons = {}
        for action in ("creative.blinded", "creative.grid_tournament",
                       "creative.benchmark_challenge"):
            row = s.scalar(select(AuditLog).where(AuditLog.action == action)
                           .order_by(desc(AuditLog.id)).limit(1))
            if row is not None:
                d = dict(row.detail or {})
                comparisons[action] = {"at": row.at.isoformat() if row.at else None,
                                       "verdict": d.get("verdict"),
                                       "pods": {k: (v or {}).get("verdict")
                                                for k, v in (d.get("pods") or {}).items()}}
        published = list(s.scalars(select(Listing).where(Listing.state == "published")))
        orders = [(o.product_slug, float(o.revenue_cad or 0.0))
                  for o in s.scalars(select(Order).where(Order.refunded == False))]  # noqa: E712
        incidents = [{"id": i.id, "severity": i.severity, "signature": i.signature,
                      "summary": (i.summary or "")[:200]}
                     for i in s.scalars(select(Incident).where(
                         Incident.resolved == False,  # noqa: E712
                         (Incident.signature.like("mjs.%")
                          | Incident.signature.like("benchmark.%"))))]
        last_scan = scans[0].at.isoformat() if scans else None
        n_orders = s.scalar(select(func.count()).select_from(Order)) or 0
    mission_orders = [o for o in orders if o[0] in winners]
    return {
        "last_successful_scan": last_scan,
        "listings_changed_new": {"last_scan": dict(changes),
                                 "events_processed": len(events)},
        "pod_assignments": dict(assignments.most_common()),
        "top_uncovered_opportunities": [
            {k: g[k] for k in ("arena", "pod", "score", "components")}
            for g in coverage.queue(db, benchmark_key, states=(coverage.UNCOVERED,),
                                    limit=10)],
        "upcoming_seasonal_adaptations": adaptations[:20],
        "launch_deadlines": sorted(deadlines, key=lambda d: d.get("latest_effective_launch")
                                   or "9999")[:20],
        "comparison_results": comparisons or {
            "state": "UNMEASURED: no blinded comparison or search-grid tournament has run"},
        "products_launched": {"published_listings": len(published),
                              "mission_responses": winners,
                              "mission_responses_published": sorted(
                                  {p.product_slug for p in published} & set(winners))},
        "conversion_revenue": ({"orders": len(orders), "revenue_cad": round(
            sum(r for _s, r in orders), 2), "mission_orders": len(mission_orders),
            "mission_revenue_cad": round(sum(r for _s, r in mission_orders), 2)}
            if n_orders else {"state": "UNMEASURED: no order has been recorded"}),
        "mission_incidents": incidents,
    }
