"""The weekly deep cycle's readings, additions and STOP list, computed from rows (#53, #194).

`improve.weekly` had the shape -- eight domains audited rather than visited, four
architecture moves of which three subtract -- and the handler fed it constants: conversion,
ads, support and cost were hard-coded zero findings, the only architecture changes ever
generated were retire and merge, and `velocity.stop_list` had no caller at all. A weekly
review that cannot add a specialist, cannot see its own conversion and never stops anything
is the autonomous bureaucracy #53 names.

Three readers, each from rows and each honest about an empty table:

- `domain_findings` -- conversion from listing outcomes, ads from paid spend and paid
  cohorts, support from the case table, cost from the cost and ledger tables. A domain whose
  table is empty reads `UNMEASURED` (zero read), never a clean zero-findings audit.
- `additions` -- an ADD specialist where work exists that no enabled agent can own: a domain
  with findings and no agent holding its job types, or open work of one kind that
  `swarm.orchestrate.work_items` finds unowned three times over.
- `stop_list` -- #53's five categories: experiments that ran long enough and have not
  concluded, cadences whose recent runs did nothing, products polished past what they sell,
  search queries whose captures never change, and housekeeping that consumes most of the
  week's work. Stopping an experiment is executed here (it is ours and in shadow); the rest
  are one batched owner card, because removing a cadence or a query is a change to how the
  company runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import velocity, weekly

ADD_THRESHOLD = 3
UNOWNED_FOR_ADD = 3
EXPERIMENT_STALE_DAYS = 30
CADENCE_IDLE_RUNS = 7
POLISH_VERSIONS = 3
QUERY_UNCHANGED_CAPTURES = 4
INFRA_SHARE = 0.5
STOP_CARD_KEY = "improve.stop_list:weekly"
ADD_CARD_KEY = "improve.architecture:add"

# Who can own each domain's work: the job types an enabled agent must hold.
DOMAIN_OWNER_JOBS: dict[str, tuple[str, ...]] = {
    "conversion": ("listing.seo", "growth.experiments"),
    "ads": ("ads.campaign", "ads.adjust"),
    "support": ("support.triage", "support.reply"),
    "cost": ("finance.governor", "finance.reconcile"),
}


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def domain_findings(db, *, now: datetime | None = None) -> dict:
    """Conversion, ads, support and cost, each read from its own table."""
    from sqlalchemy import select

    from ..core.models import (Cohort, CostEntry, LedgerEntry, ListingOutcome, SupportCase)
    from ..growth.portfolio import BENCH_CONVERSION, MIN_CLICKS

    now = now or datetime.now(timezone.utc)
    week = now - timedelta(days=7)
    fortnight = now - timedelta(days=14)
    out: dict[str, dict] = {}
    with db.session() as s:
        outcomes = list(s.scalars(select(ListingOutcome)))
        weak = [o for o in outcomes if (o.visits or 0) >= MIN_CLICKS
                and ((o.orders or 0) / o.visits) < BENCH_CONVERSION]
        out["conversion"] = {
            "read": len(outcomes), "findings": len(weak),
            "detail": [{"product": o.product_slug, "visits": o.visits, "orders": o.orders}
                       for o in weak[:10]],
            "reading": "measured" if outcomes else "UNMEASURED",
            "why": ("no listing outcome has been recorded: conversion needs live listings' "
                    "traffic" if not outcomes else
                    f"{len(weak)} listing period(s) converting below {BENCH_CONVERSION:.1%} "
                    f"on at least {MIN_CLICKS} visits")}

        ads_cost = [c for c in s.scalars(select(CostEntry)) if c.kind == "ads"]
        paid = [c for c in s.scalars(select(Cohort)) if c.arm != "organic"]
        losing = [c for c in paid if (c.spend_cad or 0) > 0
                  and (c.revenue_cad or 0) < (c.spend_cad or 0)]
        read = len(ads_cost) + len(paid)
        out["ads"] = {
            "read": read, "findings": len(losing),
            "detail": [{"cohort": c.key, "spend": c.spend_cad, "revenue": c.revenue_cad}
                       for c in losing[:10]],
            "reading": "measured" if read else "UNMEASURED",
            "why": ("no paid spend or paid cohort exists: paid media is owner-gated"
                    if not read else f"{len(losing)} paid cohort(s) returning less than spent")}

        cases = list(s.scalars(select(SupportCase)))
        stale = [c for c in cases if not c.resolved and _aware(c.at) < now - timedelta(days=2)]
        per_product: dict[str, int] = {}
        for c in cases:
            if c.product_slug:
                per_product[c.product_slug] = per_product.get(c.product_slug, 0) + 1
        hotspots = sorted(p for p, n in per_product.items() if n >= 3)
        escalated = [c for c in cases if c.escalated and not c.resolved]
        out["support"] = {
            "read": len(cases), "findings": len(stale) + len(hotspots) + len(escalated),
            "detail": {"stale_open": [c.id for c in stale[:10]], "hotspots": hotspots,
                       "escalated_open": [c.id for c in escalated[:10]]},
            "reading": "measured" if cases else "UNMEASURED",
            "why": ("no support case exists: there are no customers yet" if not cases else
                    f"{len(stale)} open past two days, {len(hotspots)} product hotspot(s), "
                    f"{len(escalated)} escalated and open")}

        costs = list(s.scalars(select(CostEntry)))
        ledger = list(s.scalars(select(LedgerEntry)))
        this_week: dict[str, float] = {}
        last_week: dict[str, float] = {}
        drift = []
        for c in costs:
            at = _aware(c.at)
            dept = c.department or c.agent
            if at >= week:
                this_week[dept] = this_week.get(dept, 0.0) + float(c.amount_cad or 0.0)
            elif at >= fortnight:
                last_week[dept] = last_week.get(dept, 0.0) + float(c.amount_cad or 0.0)
            if (c.estimated_cad or 0) > 0 and (c.amount_cad or 0) > 2 * c.estimated_cad:
                drift.append(c.id)
        rising = sorted(d for d, v in this_week.items()
                        if last_week.get(d, 0.0) > 0 and v > 1.5 * last_week[d])
        read = len(costs) + len(ledger)
        out["cost"] = {
            "read": read, "findings": len(rising) + len(drift),
            "detail": {"rising_departments": rising, "estimate_drift": drift[:10],
                       "this_week_cad": round(sum(this_week.values()), 4)},
            "reading": "measured" if read else "UNMEASURED",
            "why": ("no cost or ledger row exists" if not read else
                    f"{len(rising)} department(s) spending over 1.5x last week, {len(drift)} "
                    f"call(s) costing over twice their estimate")}
    return out


def additions(db, findings: dict) -> list[weekly.ArchitectureChange]:
    """ADD specialist changes, where the rows show work nothing can own."""
    from ..agents.registry import Registry
    from ..swarm.orchestrate import orphans, work_items

    agents = [a for a in Registry(db).all() if a.enabled]
    held = {jt for a in agents for jt in (a.allowed_job_types or [])}
    changes = []
    for domain, jobs in DOMAIN_OWNER_JOBS.items():
        f = findings.get(domain) or {}
        if f.get("findings", 0) >= ADD_THRESHOLD and not (set(jobs) & held):
            changes.append(weekly.ArchitectureChange(
                move=weekly.ADD, subject=f"{domain}_specialist",
                proposed_by="improvement_director",
                because=(f"{f['findings']} {domain} finding(s) this week and no enabled agent "
                         f"holds any of {list(jobs)}, so the work has nobody to do it")))
    entries = work_items(db)
    unowned: dict[str, int] = {}
    keys = {o["key"] for o in orphans([e["item"] for e in entries])}
    for e in entries:
        if e["item"].key in keys:
            unowned[e["source"]] = unowned.get(e["source"], 0) + 1
    for source, n in sorted(unowned.items()):
        if n >= UNOWNED_FOR_ADD:
            changes.append(weekly.ArchitectureChange(
                move=weekly.ADD, subject=f"{source}_steward",
                proposed_by="improvement_director",
                because=(f"{n} open {source} work item(s) have no accountable owner that can "
                         f"act on them (#176), so a steward for {source} work is missing")))
    return changes


def stop_list(db, *, now: datetime | None = None) -> dict:
    """#53's five categories, read from rows, and what is executed of them."""
    from sqlalchemy import select

    from ..core.models import (Experiment, Job, JobStatus, LedgerEntry, PatternVersion,
                               Product, SerpSnapshot)
    from ..runtime.pipeline import did_no_work
    from ..swarm.orchestrate import band_for

    now = now or datetime.now(timezone.utc)
    stops: list[velocity.Stop] = []
    executed: list[dict] = []
    with db.session() as s:
        for e in s.scalars(select(Experiment)):
            if e.result or e.state in ("concluded", "stopped", "killed", "decided"):
                continue
            if _aware(e.created_at) < now - timedelta(days=EXPERIMENT_STALE_DAYS):
                stops.append(velocity.Stop(
                    "experiment", e.name,
                    f"designed {(now - _aware(e.created_at)).days} days ago and still "
                    f"{e.state} with no result; an experiment that will not conclude is a "
                    f"standing cost", saves="its monitoring and its slot in the portfolio"))
                e.state = "stopped"
                e.result = {"stopped_by": "improve.weekly", "at": now.isoformat(),
                            "why": "#53: ran long enough to conclude and did not"}
                executed.append({"experiment": e.id, "state": "stopped"})

        by_type: dict[str, list] = {}
        for j in s.scalars(select(Job).where(Job.status == JobStatus.DONE)
                           .order_by(Job.id.desc())):
            if len(by_type.setdefault(j.job_type, [])) < CADENCE_IDLE_RUNS:
                by_type[j.job_type].append(dict(j.outputs or {}))
        for job_type, outs in sorted(by_type.items()):
            if len(outs) >= CADENCE_IDLE_RUNS and all(did_no_work(o) for o in outs):
                stops.append(velocity.Stop(
                    "cadence", job_type,
                    f"its last {len(outs)} completed runs all reported doing nothing; run it "
                    f"less often until what it reads exists", saves="worker time"))

        versions: dict[int, int] = {}
        for v in s.scalars(select(PatternVersion)):
            versions[v.product_id] = versions.get(v.product_id, 0) + 1
        revenue = " ".join((r.evidence_ref or "") + " " + (r.description or "")
                           for r in s.scalars(select(LedgerEntry)) if (r.gross_cad or 0) > 0)
        for p in s.scalars(select(Product)):
            n = versions.get(p.id, 0)
            if n >= POLISH_VERSIONS and p.slug not in revenue:
                stops.append(velocity.Stop(
                    "polish", p.slug,
                    f"{n} versions and no attributed revenue: another revision polishes a "
                    f"product nobody has bought yet", saves="engineering and render time"))

        captures: dict[str, list] = {}
        for snap in s.scalars(select(SerpSnapshot).order_by(SerpSnapshot.id)):
            captures.setdefault(snap.query, []).append(
                (tuple(snap.rank_list or []), snap.total_count))
        for query, seen in sorted(captures.items()):
            recent = seen[-QUERY_UNCHANGED_CAPTURES:]
            if len(recent) >= QUERY_UNCHANGED_CAPTURES and len(set(recent)) == 1:
                stops.append(velocity.Stop(
                    "query", query,
                    f"its last {len(recent)} captures are identical; monitoring it daily "
                    f"has stopped informing any decision", saves="one capture a day"))

        week = now - timedelta(days=7)
        hours: dict[str, float] = {}
        for j in s.scalars(select(Job).where(Job.status == JobStatus.DONE)):
            fin, st = _aware(j.finished_at), _aware(j.started_at)
            if fin is None or st is None or fin < week:
                continue
            kind = band_for(j.job_type)["kind"]
            hours[kind] = hours.get(kind, 0.0) + (fin - st).total_seconds() / 3600.0
        total = sum(hours.values())
        if total > 0 and hours.get("housekeeping", 0.0) / total > INFRA_SHARE:
            stops.append(velocity.Stop(
                "infrastructure", "housekeeping band",
                f"{hours['housekeeping'] / total:.0%} of this week's worker time went to "
                f"housekeeping with no line to a commercial outcome",
                saves="worker time for work that sells"))

    counted = sum(1 for _ in stops)
    nothing = ("" if stops else
               "every experiment is concluding, no cadence ran idle for a week, nothing was "
               "re-polished without a sale, no monitored query stopped moving and housekeeping "
               "is not most of the work")
    review = velocity.review(db, stops=stops, nothing_to_stop_because=nothing)
    return {"review": review, "executed": executed, "count": counted}


def route_owner_card(db, key: str, lines: list[str], *, reason: str) -> str:
    """One batched owner card per weekly list, restated while it changes, closed when empty."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    with db.session() as s:
        row = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                 OwnerAction.done == False))  # noqa: E712
        if not lines:
            if row is not None:
                row.done = True
                return "closed"
            return "none"
        action = "Decide each: " + " | ".join(lines)
        if row is None:
            s.add(OwnerAction(requirement_key=key, action=action[:4000], reason=reason,
                              max_cost_cad=0.0, minutes=3 * len(lines),
                              consequence_of_delay="the standing cost continues; nothing breaks",
                              blocks=key))
            return "queued"
        if row.action != action[:4000]:
            row.action = action[:4000]
            return "restated"
        return "already_open"
