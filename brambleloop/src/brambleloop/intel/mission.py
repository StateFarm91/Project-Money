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
