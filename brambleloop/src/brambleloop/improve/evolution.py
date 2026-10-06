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
- `metric_revisions` -- the fourth architecture move (#194). A REVISE_METRIC change where a
  department's metric has been UNMEASURED for three weekly cycles while a proxy reads rows
  now, or where the metric moves its good way while every assessed promotion in the
  department realised nothing. Carded to the owner under `improve.weekly`'s own rules;
  never applied here and never from an invented measurement.
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
                from ..ops import owner_queue
                owner_queue.close(row, owner_queue.WITHDRAWN,
                                  "nothing is left for the owner to decide on this card")
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


# ---------------------------------------------------------------------------
# #194: metric revision, the dangerous move, generated from evidence and never applied here
#
# Two kinds of evidence, both read from rows and neither ever invented:
#
# - a department's metric has been UNMEASURED for `REVISE_AFTER_UNMEASURED_CYCLES` weekly
#   cycles in a row (this cycle plus the previous `improve.weekly` rows) while a proxy for
#   its function is computable from rows that exist now;
# - a department's metric moved in its good direction across its recent readings while every
#   assessed promotion in that department realised nothing against its own baseline
#   (`improve.roi.realised_benefit`): the number the department is judged on moves and the
#   outcomes it is meant to stand for do not.
#
# The change is a `weekly.ArchitectureChange(REVISE_METRIC)`, so every rule in `improve.weekly`
# applies: it names the metric it replaces and the new one, the proposer is never the
# department, and the justification is about what the metric fails to measure. It is carded to
# the owner: changing the scoreboard is a permission change, `improve.tiers` has no tier that
# pre-authorises it, and the metric table (`improve.cells.CELLS`) is code -- so nothing is
# auto-applied, and the old metric's history stays exactly where it is.

REVISE_AFTER_UNMEASURED_CYCLES = 3
CONTRADICTION_MIN_ASSESSED = 2
CONTRADICTION_MIN_READINGS = 2
REVISE_CARD_KEY = "improve.architecture:revise_metric"
REVISION_PROPOSER = "improvement_director"


def _proxy_portfolio(db) -> dict | None:
    """Value-ladder rungs filled by drafted listings, from Listing rows -- the shape
    `top_sku_revenue_share` will read from sales, read today from what is on the shelf."""
    from sqlalchemy import select

    from ..core.models import Listing

    with db.session() as s:
        prices = [float(li.price_cad or 0.0) for li in s.scalars(select(Listing))
                  if (li.price_cad or 0) > 0]
    if not prices:
        return None
    rungs = ("under_6", "6_to_10", "10_to_15", "15_and_up")
    filled = {("under_6" if p < 6 else "6_to_10" if p < 10 else "10_to_15" if p < 15
               else "15_and_up") for p in prices}
    return {"metric": "value_ladder_rungs_filled", "value": round(len(filled) / len(rungs), 4),
            "rows": len(prices),
            "reads": f"drafted listing prices across the {len(rungs)} value-ladder rungs"}


def _proxy_finance(db) -> dict | None:
    """Cost-estimate error from CostEntry rows carrying an estimate -- the forecasting skill
    `forecast_error` measures, read on the costs that exist before there is revenue."""
    from sqlalchemy import select

    from ..core.models import CostEntry

    with db.session() as s:
        pairs = [(float(c.amount_cad or 0.0), float(c.estimated_cad or 0.0))
                 for c in s.scalars(select(CostEntry)) if (c.estimated_cad or 0) > 0]
    if not pairs:
        return None
    error = sum(abs(a - e) / e for a, e in pairs) / len(pairs)
    return {"metric": "cost_estimate_error", "value": round(error, 4), "rows": len(pairs),
            "reads": "cost entries with an estimate: mean |actual - estimate| / estimate"}


def _proxy_growth(db) -> dict | None:
    """Experiments that reached a decision, from Experiment rows -- the discipline
    `acquisition_loops_with_evidence` will read from traffic, read today from the registry."""
    from sqlalchemy import select

    from ..core.models import Experiment

    with db.session() as s:
        rows = [bool(e.result) or e.state in ("stopped", "concluded", "killed", "decided")
                for e in s.scalars(select(Experiment))]
    if not rows:
        return None
    return {"metric": "experiments_decided_share",
            "value": round(sum(1 for r in rows if r) / len(rows), 4), "rows": len(rows),
            "reads": "experiment rows that recorded a result or reached a terminal state"}


def _proxy_pricing(db) -> dict | None:
    """Drafted listing prices against the benchmark's observed band for the same department,
    from Listing and BenchmarkListing rows -- the positioning `contribution_margin` will
    measure from sales, read today from the prices actually set."""
    from sqlalchemy import select

    from ..core.models import BenchmarkListing, Listing

    with db.session() as s:
        ours = [(li.product_slug, float(li.price_cad or 0.0)) for li in s.scalars(select(Listing))
                if (li.price_cad or 0) > 0]
        theirs = [float(b.price_cad) for b in s.scalars(select(BenchmarkListing))
                  if (b.price_cad or 0) > 0]
    if not ours or not theirs:
        return None
    low, high = min(theirs), max(theirs)
    inside = sum(1 for _slug, p in ours if low <= p <= high)
    return {"metric": "listing_price_inside_observed_band", "value": round(
        inside / len(ours), 4), "rows": len(ours) + len(theirs),
        "reads": f"drafted listing prices inside the observed CA${low:.2f}-{high:.2f} band"}


# The measurable proxy for each department whose metric waits on data that does not exist
# in shadow. A department with no proxy here is reported, never revised: inventing a proxy
# is inventing a measurement.
METRIC_PROXIES: dict[str, callable] = {
    "portfolio": _proxy_portfolio,
    "finance": _proxy_finance,
    "growth": _proxy_growth,
    "pricing": _proxy_pricing,
}


def unmeasured_cells(db) -> dict[str, str]:
    """The departments whose metric cannot be read now, with the measurer's stated reason."""
    from . import measure

    out = measure.measure_all(db)
    return {cell: v["reason"] for cell, v in out["skipped"].items()}


def _previous_unmeasured(db, *, cycles: int) -> list[list[str]]:
    """`cells_unmeasured` from the last `cycles` improve.weekly rows, newest first."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == "improve.weekly")
                              .order_by(desc(AuditLog.id)).limit(cycles)))
        return [list((r.detail or {}).get("cells_unmeasured") or []) for r in rows]


def _trend(db, cell) -> dict | None:
    """The cell's last two capability readings, and whether the metric moved its good way."""
    from sqlalchemy import select

    from ..core.models import CapabilityPoint

    with db.session() as s:
        points = [float(p.value) for p in s.scalars(
            select(CapabilityPoint).where(CapabilityPoint.cell == cell.key)
            .order_by(CapabilityPoint.id))]
    if len(points) < CONTRADICTION_MIN_READINGS:
        return None
    before, after = points[-2], points[-1]
    improved = after > before if cell.higher_is_better else after < before
    return {"from": before, "to": after, "improved": improved, "readings": len(points)}


def metric_revisions(db, *, unmeasured_now: dict[str, str] | None = None,
                     now: datetime | None = None) -> dict:
    """REVISE_METRIC changes the evidence supports this week, and the evidence for each."""
    from . import cells as cell_table
    from . import roi

    now = now or datetime.now(timezone.utc)
    unmeasured_now = unmeasured_cells(db) if unmeasured_now is None else unmeasured_now
    history = _previous_unmeasured(db, cycles=REVISE_AFTER_UNMEASURED_CYCLES - 1)
    changes: list[weekly.ArchitectureChange] = []
    evidence: dict[str, dict] = {}
    considered: dict[str, str] = {}

    # (a) UNMEASURED for N cycles while a proxy reads rows now.
    for cell_key, reason in sorted(unmeasured_now.items()):
        streak = 1 + sum(1 for past in history if cell_key in past)
        if len(history) < REVISE_AFTER_UNMEASURED_CYCLES - 1 or \
                streak < REVISE_AFTER_UNMEASURED_CYCLES:
            considered[cell_key] = (f"unmeasured {streak} cycle(s) of the "
                                    f"{REVISE_AFTER_UNMEASURED_CYCLES} required")
            continue
        reader = METRIC_PROXIES.get(cell_key)
        proxy = reader(db) if reader else None
        if proxy is None:
            considered[cell_key] = ("unmeasured for the streak but " + (
                "no proxy is defined for this department" if reader is None else
                "its proxy has no rows to read either") + "; nothing is invented")
            continue
        cell = cell_table.BY_KEY[cell_key]
        change = weekly.ArchitectureChange(
            move=weekly.REVISE_METRIC, subject=cell_key, proposed_by=REVISION_PROPOSER,
            replaces_metric=cell.metric, new_metric=proxy["metric"],
            because=(f"{cell.metric!r} has been UNMEASURED for {streak} weekly cycles "
                     f"({reason}), so it currently measures nothing about the department; "
                     f"{proxy['metric']!r} reads {proxy['rows']} row(s) today "
                     f"({proxy['reads']}) and measures the same function on the evidence "
                     f"that exists"))
        changes.append(change)
        evidence[cell_key] = {"kind": "unmeasured_streak", "cycles": streak,
                              "reason": reason, "proxy": proxy}

    # (b) the metric moves its good way while realised outcomes contradict it.
    realised = roi.realised_benefit(db, now=now)
    assessed_by_cell: dict[str, dict[str, int]] = {}
    for verdict in ("returned", "no_return", "regressed"):
        for row in realised[verdict]:
            tally = assessed_by_cell.setdefault(row["cell"], {"returned": 0, "missed": 0})
            tally["returned" if verdict == "returned" else "missed"] += 1
    for cell_key, tally in sorted(assessed_by_cell.items()):
        if cell_key in evidence:
            continue
        assessed = tally["returned"] + tally["missed"]
        if assessed < CONTRADICTION_MIN_ASSESSED or tally["returned"] > 0:
            continue
        cell = cell_table.BY_KEY.get(cell_key)
        trend = _trend(db, cell) if cell else None
        if not trend or not trend["improved"]:
            continue
        reader = METRIC_PROXIES.get(cell_key)
        proxy = reader(db) if reader else None
        if proxy is None:
            considered[cell_key] = (f"{cell.metric} improved {trend['from']} -> "
                                    f"{trend['to']} while {assessed} assessed promotion(s) "
                                    f"realised nothing; no proxy with rows is defined, so "
                                    f"the contradiction is reported and not revised")
            evidence[cell_key] = {"kind": "contradiction_unrevisable", "trend": trend,
                                  "assessed": assessed}
            continue
        change = weekly.ArchitectureChange(
            move=weekly.REVISE_METRIC, subject=cell_key, proposed_by=REVISION_PROPOSER,
            replaces_metric=cell.metric, new_metric=proxy["metric"],
            because=(f"{cell.metric!r} moved {trend['from']} -> {trend['to']} in its good "
                     f"direction while all {assessed} assessed promotion(s) in "
                     f"{cell_key} realised nothing against their own baselines, so the "
                     f"metric fails to measure the outcomes it stands for; "
                     f"{proxy['metric']!r} reads {proxy['rows']} row(s) of the department's "
                     f"actual output ({proxy['reads']})"))
        changes.append(change)
        evidence[cell_key] = {"kind": "contradiction", "trend": trend, "assessed": assessed,
                              "proxy": proxy}

    return {"changes": changes, "evidence": evidence, "considered": considered,
            "history_cycles_read": len(history)}
