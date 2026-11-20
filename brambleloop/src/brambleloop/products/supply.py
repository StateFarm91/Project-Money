"""ENG-SUPPLY: capacity-aware product admission, the one door new products enter engineering by.

Before this (measured in `research/final_build/w6/supply_bottleneck.md`), the only producer of
new products with a work-in-progress limit was `release_recovery.seed_launch0`: a fixed two
product chains in flight, one release per hourly `chain.rebuild`, drawn from a finite release
registry that runs dry (`catalogue-exhausted:launch0`). Every research and creative producer
(`radar.score`, `creative.intake`, `creative.regate`) enqueued `cir.draft` directly, with no
admission at all -- a burst of promotions could flood the one worker, and once the registry
was exhausted nothing paced new work in.

This module replaces both with one deterministic admission controller:

* **Offers.** A producer that has decided a concept deserves engineering calls `offer()`. The
  offer is recorded durably (`supply.offered`, the exact `cir.draft` payload and idempotency
  key it would have enqueued) and admitted at once if there is room, otherwise it waits in
  the supply queue. Nothing is lost when capacity is full, and a worker restart loses nothing
  because the queue is the audit log plus the durable job queue.
* **Admission** (`assess`, `admit`). A candidate is admitted only when every one of these
  holds, and each run records every admission and every refusal with its reason
  (`supply.admission`):

  1. free work-in-progress: product chains in flight are below a ceiling derived from the
     active worker target (`swarm.capacity.worker_target`), bounded by `MAX_WIP` and safe for
     one Railway worker (one worker -> the historical two chains);
  2. stage backlog: the due queue of every chain stage, weighted by that stage's measured mean
     job-seconds (expected work), is below `MAX_BACKLOG_SECONDS` per worker, and no stage's
     oldest due job is older than `MAX_STAGE_AGE`;
  3. cost: the month's company ceiling (`finance.spend_policy.binding_ceiling`) has room for
     the in-flight products' expected cost plus this one's, the month is below the escalation
     share, and no chain agent's daily permission is spent. Expected cost per product is
     measured from `CostEntry.product_slug`; with no measurement a conservative estimate is
     used and labelled so. An unreadable spend reading refuses (UNKNOWN is never PASS);
  4. family diversity: no more than `MAX_PER_FAMILY` products of one family in flight;
  5. research demand orders the queue: research-backed originals before static-pool
     re-promotions, then highest measured demand first (unknown demand last), then oldest.

* **Launch-0 first, without starving research.** The owner's Launch-0 releases are seeded
  first, but while research offers wait they hold at most `limit - 1` slots (`run`).
* **Parked products free their slot.** A product whose only live chain work is not running
  and that is waiting on a physical sample or an owner decision holds no slot (`waiting_on`).
  Finished, dead-lettered and cancelled chains hold nothing (unchanged). So the next eligible
  concept is admitted by the next `supply.admit` run (every 15 minutes) or `chain.rebuild`
  (hourly), with no manual kick.
* **Blocked products do not halt others.** Every refusal is per candidate; one candidate's
  refusal never stops the loop, only a global refusal (no capacity, backlog, cost) does.

Nothing here certifies, lists, publishes or spends. Admission enqueues the ordinary
`cir.draft` with the producer's own idempotency key, so drafting, compiling and certifying
keep every gate they had.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

OFFERED = "supply.offered"
ADMITTED = "supply.admitted"
ADMISSION = "supply.admission"

# ---- bounded defaults (safe for one Railway worker) --------------------------------------
# Product chains in flight per active worker. One worker -> 2, the historical WIP_LIMIT.
WIP_PER_WORKER = 2
# The ceiling whatever the worker target says; an env override may lower or raise it up to
# HARD_MAX_WIP, never past it.
MAX_WIP = 4
HARD_MAX_WIP = 8
# New products admitted by one run: a trickle, so a freed slot never becomes a burst.
MAX_ADMIT_PER_RUN = 1
# Due chain-stage work, in expected job-seconds per active worker, above which nothing new
# is admitted: the products already admitted are starved for the worker.
MAX_BACKLOG_SECONDS = 2 * 60 * 60
# A chain stage whose oldest due job has waited longer than this is not keeping up.
MAX_STAGE_AGE = timedelta(hours=6)
# Expected job-seconds for a stage with no measured run yet (labelled ESTIMATED).
DEFAULT_STAGE_SECONDS = 300.0
STAGE_WINDOW = timedelta(days=7)
STAGE_SAMPLE = 200
# Expected model + image cost of one product chain with no measurement (labelled ESTIMATED).
DEFAULT_PRODUCT_COST_CAD = 5.0
COST_WINDOW = timedelta(days=30)
# Agents whose daily permission a product chain spends against.
CHAIN_AGENTS = ("crochet_engineer", "publishing")
# Products of one family in flight at once.
MAX_PER_FAMILY = 1
# Offers read per run (newest first); far above any realistic waiting queue.
OFFER_SCAN = 2000


def _aware(value):
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def wip_ceiling(db, *, env=None, now=None) -> dict:
    """The work-in-progress ceiling for product chains, from the active worker target."""
    env = os.environ if env is None else env
    try:
        from ..swarm.capacity import worker_target

        target = int(worker_target(db, now=now).get("target") or 1)
        source = "swarm.capacity.worker_target"
    except Exception as exc:  # noqa: BLE001 - unreadable: the one-worker floor
        target, source = 1, f"worker target unreadable ({type(exc).__name__}); one worker"
    cap = MAX_WIP
    raw = env.get("BRAMBLELOOP_SUPPLY_MAX_WIP")
    if raw:
        try:
            cap = max(1, min(HARD_MAX_WIP, int(raw)))
        except ValueError:
            pass
    limit = max(1, min(cap, WIP_PER_WORKER * max(1, target)))
    return {"limit": limit, "workers": max(1, target), "cap": cap, "source": source}


# ---- what a product is waiting on --------------------------------------------------------

def waiting_on(db, slugs) -> dict[str, str]:
    """{slug: why} for each product waiting on a physical sample or an owner decision.

    * physical: an open (requested, not completed) physical test, or a certified release whose
      certificate requires a sample and no completed test exists for it;
    * owner: an open owner action naming the product (its action, blockers or requirement).
    A product not listed is not known to be waiting. Read-only."""
    from sqlalchemy import select

    from ..core.models import OwnerAction, PatternVersion, PhysicalTest, Product

    slugs = [s for s in slugs if s and not s.startswith("(unnamed")]
    if not slugs:
        return {}
    out: dict[str, str] = {}
    with db.session() as s:
        for t in s.scalars(select(PhysicalTest).where(PhysicalTest.product_slug.in_(slugs),
                                                      PhysicalTest.completed_at.is_(None))):
            out.setdefault(t.product_slug,
                           f"physical sample requested for {t.version}, not yet completed")
        done = {(t.product_slug, t.version) for t in s.scalars(select(PhysicalTest).where(
            PhysicalTest.product_slug.in_(slugs), PhysicalTest.completed_at.is_not(None)))}
        for slug, pv in s.execute(select(Product.slug, PatternVersion).join(
                PatternVersion, PatternVersion.product_id == Product.id).where(
                Product.slug.in_(slugs), PatternVersion.certified == True)):  # noqa: E712
            if (pv.certificate or {}).get("physical_test_required") \
                    and (slug, pv.version) not in done:
                out.setdefault(slug, f"{pv.version} is certified and needs a physical sample")
        for a in s.scalars(select(OwnerAction).where(OwnerAction.done.is_(False))):
            text = " ".join(str(x or "") for x in (a.action, a.blocks, a.requirement_key))
            for slug in slugs:
                if _names_slug(text, slug):
                    out.setdefault(slug, f"owner action #{a.id} open: {str(a.action)[:120]}")
    return out


def _names_slug(text: str, slug: str) -> bool:
    """True only when `slug` appears in `text` as a whole slug token.

    A substring test let an owner action about "granny-square-blanket" park the different
    product "granny-square" and free its slot while its chain work was still due (supply
    review M2). Slugs are runs of [a-z0-9-], so a match must not touch another slug
    character on either side."""
    import re

    return re.search(rf"(?<![A-Za-z0-9-]){re.escape(slug)}(?![A-Za-z0-9-])", text) is not None


def _due_now(db, slugs, *, now) -> set[str]:
    """Slugs with a chain-stage job PENDING or FAILED (retry) that is due now.

    Such a product is using the worker and the model budget now, so it keeps its slot even if
    an owner action or a sample also names it (supply review M2). Read-only."""
    from sqlalchemy import or_, select

    from ..core.models import Job, JobStatus
    from ..runtime.release_recovery import CHAIN_STAGE_JOBS, _job_slug

    wanted = set(slugs)
    if not wanted:
        return set()
    due: set[str] = set()
    with db.session() as s:
        for inputs, in s.execute(select(Job.inputs).where(
                Job.job_type.in_(CHAIN_STAGE_JOBS),
                Job.status.in_((JobStatus.PENDING, JobStatus.FAILED)),
                or_(Job.run_after.is_(None), Job.run_after <= now))):
            slug = _job_slug(inputs)
            if slug in wanted:
                due.add(slug)
    return due


# ---- the measurements admission reads -----------------------------------------------------

def stage_backlog(db, *, now, workers: int) -> dict:
    """Due chain-stage work per stage: depth, oldest age and expected job-seconds."""
    from sqlalchemy import select

    from ..core.models import Job, JobStatus
    from ..runtime.release_recovery import CHAIN_STAGE_JOBS

    stages: dict[str, dict] = {}
    with db.session() as s:
        for jt, created, run_after in s.execute(
                select(Job.job_type, Job.created_at, Job.run_after).where(
                    Job.job_type.in_(CHAIN_STAGE_JOBS),
                    Job.status.in_((JobStatus.PENDING, JobStatus.FAILED)),
                    Job.run_after <= now)):
            row = stages.setdefault(jt, {"depth": 0, "oldest_age_s": 0.0})
            row["depth"] += 1
            since = _aware(run_after) or _aware(created) or now
            row["oldest_age_s"] = max(row["oldest_age_s"], (now - since).total_seconds())
        since = now - STAGE_WINDOW
        for jt in list(stages):
            durations = [((_aware(f) - _aware(st)).total_seconds())
                         for st, f in s.execute(select(Job.started_at, Job.finished_at).where(
                             Job.job_type == jt, Job.status == JobStatus.DONE,
                             Job.finished_at >= since).order_by(Job.id.desc())
                             .limit(STAGE_SAMPLE))
                         if st is not None and f is not None]
            if durations:
                stages[jt].update(expected_s=round(max(1.0, sum(durations) / len(durations)), 1),
                                  basis=f"MEASURED mean of {len(durations)} run(s)")
            else:
                stages[jt].update(expected_s=DEFAULT_STAGE_SECONDS,
                                  basis="ESTIMATED (no measured run in the window)")
    total = sum(r["depth"] * r["expected_s"] for r in stages.values())
    per_worker = total / max(1, workers)
    oldest = max((r["oldest_age_s"] for r in stages.values()), default=0.0)
    refusals = []
    if per_worker > MAX_BACKLOG_SECONDS:
        refusals.append(f"stage backlog: {per_worker:.0f} expected job-seconds due per worker "
                        f"exceeds {MAX_BACKLOG_SECONDS}")
    if oldest > MAX_STAGE_AGE.total_seconds():
        late = max(stages, key=lambda k: stages[k]["oldest_age_s"])
        refusals.append(f"stage backlog: {late}'s oldest due job has waited {oldest / 3600:.1f}h, "
                        f"over {MAX_STAGE_AGE.total_seconds() / 3600:g}h")
    return {"stages": stages, "expected_seconds": round(total, 1),
            "per_worker_seconds": round(per_worker, 1), "oldest_age_s": round(oldest, 1),
            "refusals": refusals}


def expected_product_cost(db, *, now) -> dict:
    """Mean recorded cost per product over the window, or the labelled default."""
    from sqlalchemy import func, select

    from ..core.models import CostEntry

    with db.session() as s:
        rows = list(s.execute(select(CostEntry.product_slug, func.sum(CostEntry.amount_cad))
                              .where(CostEntry.product_slug != "",
                                     CostEntry.at >= now - COST_WINDOW)
                              .group_by(CostEntry.product_slug)))
    spent = [float(v or 0.0) for _, v in rows]
    if spent and sum(spent) > 0:
        return {"cad": round(max(DEFAULT_PRODUCT_COST_CAD / 5, sum(spent) / len(spent)), 4),
                "basis": f"MEASURED mean over {len(spent)} product(s), {COST_WINDOW.days}d"}
    return {"cad": DEFAULT_PRODUCT_COST_CAD,
            "basis": "ESTIMATED (no product-attributed cost recorded in the window)"}


def cost_check(db, *, in_flight: int, now) -> dict:
    """Room under the existing spend ceilings for the in-flight products and one more."""
    from ..finance import spend_policy

    expected = expected_product_cost(db, now=now)
    try:
        bc = spend_policy.binding_ceiling(db, now=now)
    except Exception as exc:  # noqa: BLE001 - UNKNOWN is never PASS
        return {"ok": False, "expected": expected,
                "refusals": [f"cost: spend reading unreadable ({type(exc).__name__}); "
                             f"UNKNOWN is never PASS"]}
    month = bc["company_binding"]
    need = round(expected["cad"] * (in_flight + 1), 4)
    refusals = []
    share = (month["used_cad"] / month["ceiling_cad"]) if month["ceiling_cad"] else 1.0
    if share >= spend_policy.ESCALATE_AT_SHARE:
        refusals.append(f"cost: the month is at {share:.0%} of its CA${month['ceiling_cad']:.2f} "
                        f"ceiling, at or over the {spend_policy.ESCALATE_AT_SHARE:.0%} "
                        f"escalation share; new products wait for owner review")
    if month["remaining_cad"] < need:
        refusals.append(f"cost: CA${month['remaining_cad']:.2f} left this month, below the "
                        f"CA${need:.2f} expected for {in_flight} in-flight product(s) plus one")
    for row in bc["limits"]:
        if row["limit"] == "agent daily permission" and row["scope"] in CHAIN_AGENTS \
                and row["remaining_cad"] <= 0:
            refusals.append(f"cost: {row['scope']}'s daily permission is spent "
                            f"(CA${row['used_cad']:.2f} of CA${row['ceiling_cad']:.2f})")
    return {"ok": not refusals, "expected": expected, "need_cad": need,
            "month": {k: month[k] for k in ("ceiling_cad", "used_cad", "remaining_cad")},
            "share": round(share, 4), "refusals": refusals}


def assess(db, *, now=None, wip_limit: int | None = None) -> dict:
    """The global admission reading: in-flight products, waiting products, slots, refusals.

    Keys `limit`, `in_flight`, `slots`, `idle` and `parked` keep the meaning they had in
    `release_recovery.idle_capacity`, so its callers read this unchanged. `waiting` names
    products moved out of WIP because they are parked on a sample or the owner."""
    from ..runtime.release_recovery import idle_capacity

    now = _aware(now) or datetime.now(timezone.utc)
    ceiling = wip_ceiling(db, now=now)
    limit = ceiling["limit"] if wip_limit is None else max(0, int(wip_limit))
    base = idle_capacity(db, limit=limit, now=now)
    running = {slug for slug, jobs in base["jobs"].items()
               if any(j.endswith(":running") for j in jobs)}
    due = _due_now(db, [s for s in base["in_flight"] if s not in running], now=now)
    parked_on = waiting_on(db, [s for s in base["in_flight"]
                                if s not in running and s not in due])
    in_flight = [s for s in base["in_flight"] if s not in parked_on]
    slots = max(0, limit - len(in_flight))
    backlog = stage_backlog(db, now=now, workers=ceiling["workers"])
    cost = cost_check(db, in_flight=len(in_flight), now=now)
    refusals = list(backlog["refusals"]) + list(cost["refusals"])
    if not slots:
        refusals.insert(0, f"capacity: {len(in_flight)} product chain(s) in flight at the "
                           f"work-in-progress limit {limit}")
    open_slots = 0 if refusals else slots
    return {"limit": limit, "in_flight": in_flight, "jobs": {k: base["jobs"][k]
                                                           for k in in_flight},
            "slots": open_slots, "idle": open_slots > 0, "parked": base["parked"],
            "waiting": parked_on, "wip": ceiling, "backlog": backlog, "cost": cost,
            "refusals": refusals, "as_of": now.isoformat()}


# ---- offers and admission -----------------------------------------------------------------

def _taken(db, key: str) -> bool:
    from sqlalchemy import select

    from ..core.models import AuditLog, Job
    from ..queue.durable import fit_idempotency_key

    with db.session() as s:
        if s.scalar(select(Job.id).where(Job.idempotency_key == fit_idempotency_key(key))
                    .limit(1)) is not None:
            return True
        # A job pruned later must not let its offer be admitted twice.
        return any((d or {}).get("key") == key for (d,) in s.execute(
            select(AuditLog.detail).where(AuditLog.action == ADMITTED)
            .order_by(AuditLog.id.desc()).limit(OFFER_SCAN)))


def offers(db) -> list[dict]:
    """Every recorded offer not yet admitted, highest demand first, then oldest first."""
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..queue.durable import fit_idempotency_key
    from ..core.models import Job

    latest: dict[str, dict] = {}
    with db.session() as s:
        for rid, artifact, detail in s.execute(
                select(AuditLog.id, AuditLog.artifact, AuditLog.detail)
                .where(AuditLog.action == OFFERED).order_by(AuditLog.id.desc())
                .limit(OFFER_SCAN)):
            d = dict(detail or {})
            key = d.get("key")
            if not key or key in latest:
                continue
            latest[key] = {**d, "slug": d.get("slug") or artifact, "offer_id": rid}
        admitted = {(d or {}).get("key") for (d,) in s.execute(
            select(AuditLog.detail).where(AuditLog.action == ADMITTED)
            .order_by(AuditLog.id.desc()).limit(OFFER_SCAN))}
        fitted = {fit_idempotency_key(k): k for k in latest}
        jobs = {k for (k,) in s.execute(select(Job.idempotency_key).where(
            Job.idempotency_key.in_(list(fitted))))} if fitted else set()
    out = [o for k, o in latest.items()
           if k not in admitted and fit_idempotency_key(k) not in jobs]
    # ENG-DEMAND-SUPPLY: the market's demand for the concept's cluster, from stored evidence
    # only (products.demand). Read at admission time, so a new scan re-ranks the queue.
    ix = _demand_index(db)
    for o in out:
        o["market_demand"] = _market_demand(ix, o)

    def order(o):
        demand = o.get("demand")
        market = (o.get("market_demand") or {}).get("score")
        # Market demand first (the owner core-family boost is inside it); then, on equal
        # market demand, research-backed originals before static-pool re-promotions; then
        # the producer's own score; then the oldest offer.
        # B-2: a missing market score reads as the UNKNOWN prior, never as 0.0
        return (-(float(market) if isinstance(market, (int, float)) else _prior()),
                0 if o.get("research") else 1,
                0 if isinstance(demand, (int, float)) else 1,
                -(float(demand) if isinstance(demand, (int, float)) else 0.0), o["offer_id"])
    return sorted(out, key=order)


def _prior() -> float:
    from . import demand

    return float(demand.PRIOR)


def engine_demand_waiting(db) -> dict[str, str]:
    """{slug: reason} for every waiting offer whose construction has no certified engine.

    ENG-DEMAND-STALL: such a concept is engine demand, not draftable supply. It stays in the
    queue (never dropped) and is admitted on the first pass after its engine certifies; the
    verdict is re-read live, so a certified engine removes it from this map at once."""
    from . import demand as demand_mod

    out: dict[str, str] = {}
    for o in offers(db):
        slug = str(o.get("slug") or "")
        if not slug or slug in out:
            continue
        v = demand_mod.engine_verdict(slug, o.get("payload"))
        if v["known"] and not v["certified"]:
            out[slug] = (f"engine_demand:{v['family']}: no certified engine builds it yet "
                         f"({str(v.get('reason') or '')[:200]})")
    return out


def _demand_index(db):
    try:
        from . import demand

        return demand.index(db)
    except Exception:  # noqa: BLE001 - no index: every offer reads the same UNKNOWN prior
        return None


def _market_demand(ix, o: dict) -> dict:
    from . import demand

    payload = dict(o.get("payload") or {})
    title = str(payload.get("title") or o.get("slug") or "").replace("-", " ")
    if ix is None:
        ix = demand.build_index((), ())
    d = ix.score(title, category=str(payload.get("category") or ""),
                 pod=str(payload.get("pod") or ""))
    return {k: d[k] for k in ("score", "confidence", "status", "cluster", "level", "core")}


def family_of(db, slug: str) -> str:
    """A product's family: the one its offer named, else its pool seed's, else itself."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        d = s.scalar(select(AuditLog.detail).where(AuditLog.action == OFFERED,
                                                   AuditLog.artifact == slug)
                     .order_by(AuditLog.id.desc()).limit(1))
    if d and d.get("family"):
        return str(d["family"])
    try:
        from ..radar.opportunity import POOL

        seed = next((p for p in POOL if p.slug == slug), None)
        if seed is not None and seed.family:
            return seed.family
    except Exception:  # noqa: BLE001 - no pool: the product is its own family
        pass
    return slug


def admit(ctx, *, per_run: int = MAX_ADMIT_PER_RUN, wip_limit: int | None = None,
          now=None) -> dict:
    """Admit waiting offers into free capacity, in rank order, recording every admission
    and refusal with its reason."""
    now = _aware(now) or datetime.now(timezone.utc)
    cap = assess(ctx.db, now=now, wip_limit=wip_limit)
    families: dict[str, int] = {}
    for slug in cap["in_flight"]:
        f = family_of(ctx.db, slug)
        families[f] = families.get(f, 0) + 1
    slots = cap["slots"]
    admitted, refused, already = [], {}, []
    budget = min(per_run, slots)
    pool = offers(ctx.db)
    # Work-conserving family diversity: a candidate whose family already has a product in
    # flight is deferred, and admitted only if no other eligible candidate wants the slot.
    # Diversity orders the work; it never leaves a free slot idle.
    deferred: list[tuple[dict, str]] = []
    from . import demand as demand_mod

    recorded = {(r.get("slug"), r.get("engine"), r.get("reason"))
                for r in demand_mod.recorded_engine_demand(ctx.db)}
    engine_waiting: list[str] = []

    def take(o, family):
        job = ctx.enqueue(o.get("agent") or "crochet_engineer",
                          o.get("job_type") or "cir.draft", dict(o.get("payload") or {}),
                          idempotency_key=o["key"])
        if job is None:
            already.append(o["key"])
            return
        ctx.audit(ADMITTED, artifact=o["slug"], detail={
            "key": o["key"], "job": job.id, "source": o.get("source"), "family": family,
            "demand": o.get("demand"), "market_demand": o.get("market_demand"),
            "offer_id": o["offer_id"], "family_in_flight": families.get(family, 0)})
        admitted.append({"slug": o["slug"], "key": o["key"], "job": job.id,
                         "family": family})
        families[family] = families.get(family, 0) + 1

    for o in pool:
        key, slug = o["key"], o["slug"]
        family = str(o.get("family") or family_of(ctx.db, slug))
        if slug in cap["in_flight"] or slug in cap["waiting"]:
            refused[key] = (f"product {slug} already has a chain in flight"
                            + (f" (waiting: {cap['waiting'][slug]})"
                               if slug in cap["waiting"] else ""))
            continue
        # ENG-DEMAND-SUPPLY: a concept whose construction has no certified engine is not
        # silently held: it is recorded as engine demand (the ranked "build this engine next"
        # list) and stays waiting, admitted on the first pass after its engine certifies.
        verdict = demand_mod.engine_verdict(slug, o.get("payload"))
        if verdict["known"] and not verdict["certified"]:
            refused[key] = (f"engine_demand:{verdict['family']}: no certified engine builds "
                            f"it yet ({verdict['reason'][:200]})")
            _record_engine_demand(ctx, o, verdict, recorded)
            engine_waiting.append(slug)
            continue
        if cap["refusals"]:
            refused[key] = "; ".join(cap["refusals"])
            continue
        if families.get(family, 0) >= MAX_PER_FAMILY:
            deferred.append((o, family))
            continue
        if len(admitted) >= budget:
            refused[key] = (f"per-run trickle: {len(admitted)} admitted this run "
                            f"(max {budget}); admitted on a later run")
            continue
        take(o, family)
    for o, family in deferred:
        if len(admitted) < budget:                # no other family wanted the slot
            take(o, family)
            continue
        refused[o["key"]] = (f"family diversity: {families.get(family, 0)} product(s) of "
                             f"family {family!r} already in flight (max {MAX_PER_FAMILY}); "
                             f"another family goes first")
    summary = {k: cap[k] for k in ("limit", "in_flight", "slots", "waiting", "refusals")}
    summary.update(backlog_per_worker_s=cap["backlog"]["per_worker_seconds"],
                   expected_cost=cap["cost"].get("expected"),
                   wip=cap["wip"])
    if admitted or refused or already:
        ctx.audit(ADMISSION, detail={"admitted": admitted, "refused": refused,
                                     "already": already, "capacity": summary,
                                     "engine_demand": engine_waiting})
    return {"admitted": admitted, "refused": refused, "already": already,
            "engine_demand": engine_waiting, "capacity": summary}


def _record_engine_demand(ctx, o: dict, verdict: dict, recorded: set) -> None:
    """One `supply.engine_demand` row per concept and engine reading; a 15-minute pass that
    sees the same reading again adds nothing."""
    from . import demand

    reason = str(verdict.get("reason") or "")[:300]
    sig = (o["slug"], verdict.get("family"), reason)
    if sig in recorded:
        return
    recorded.add(sig)
    ctx.audit(demand.ENGINE_DEMAND_ACTION, artifact=o["slug"], detail={
        "slug": o["slug"], "key": o["key"], "engine": verdict.get("family"),
        "family": verdict.get("family"), "engine_status": verdict.get("status"),
        "reason": reason, "build": demand.engine_need(verdict.get("family")),
        "demand": o.get("market_demand"), "source": o.get("source")})


def offer(ctx, *, slug: str, payload: dict, key: str, source: str,
          family: str | None = None, demand: float | None = None, research: bool = False,
          agent: str = "crochet_engineer", job_type: str = "cir.draft") -> dict:
    """Record a producer's decision that `slug` deserves engineering, then try to admit it.

    Returns {"offered", "admitted", "job", "why"}. An offer whose key is already taken (a
    job exists, or it was admitted before) is not recorded again."""
    if _taken(ctx.db, key):
        return {"offered": False, "admitted": False, "job": None,
                "why": "already admitted or enqueued under this key"}
    if any(o["key"] == key for o in offers(ctx.db)):
        # Already waiting: the first offer stands (a 6-hourly re-score adds no row); this
        # call only retries its admission.
        return {**_try(ctx, key), "already_waiting": True}
    ctx.audit(OFFERED, artifact=slug, detail={
        "slug": slug, "key": key, "payload": payload, "source": source,
        "family": family, "demand": demand, "research": bool(research), "agent": agent,
        "job_type": job_type})
    return _try(ctx, key)


def _try(ctx, key: str) -> dict:
    # A full pass, not this offer alone: the queue is admitted in rank order (research
    # first, then demand), so a higher-ranked waiting offer is never overtaken by arrival.
    out = admit(ctx)
    hit = next((a for a in out["admitted"] if a["key"] == key), None)
    return {"offered": True, "admitted": hit is not None,
            "job": hit["job"] if hit else None,
            "why": None if hit else out["refused"].get(key, "already enqueued")}


REFILL_PREFIX = "supply-refill"


def after_chain_job(db, queue, job) -> int | None:
    """Enqueue one admission pass when `job` ended its product's live chain work.

    Called by the worker after every job. Only a chain-stage job whose product now has no
    live chain-stage job (finished, dead-lettered or waiting on nothing) triggers it; the key
    is the ending job, so a retry or a second worker never enqueues it twice. Returns the
    enqueued job id, or None."""
    from sqlalchemy import select

    from ..core.models import LIVE_JOB_STATUSES, Job, JobStatus
    from ..runtime.release_recovery import CHAIN_STAGE_JOBS, _job_slug

    if job.job_type not in CHAIN_STAGE_JOBS:
        return None
    slug = _job_slug(job.inputs)
    with db.session() as s:
        status = s.scalar(select(Job.status).where(Job.id == job.id))
        if status in LIVE_JOB_STATUSES:
            return None                               # retrying or still running: no end
        for other in s.scalars(select(Job).where(Job.job_type.in_(CHAIN_STAGE_JOBS),
                                                 Job.status.in_(LIVE_JOB_STATUSES),
                                                 Job.id != job.id)):
            if slug is None or _job_slug(other.inputs) == slug:
                return None                           # the chain continues
        if s.scalar(select(Job.id).where(Job.job_type == "supply.admit",
                                         Job.status == JobStatus.PENDING,
                                         Job.run_after <= datetime.now(timezone.utc))
                    .limit(1)) is not None:
            return None                               # an admission pass is already due
    try:
        made = queue.enqueue("orchestrator", "supply.admit", {"after_job": job.id},
                             idempotency_key=f"{REFILL_PREFIX}:{job.id}")
    except Exception:  # noqa: BLE001 - a duplicate key is the same refill
        return None
    # CERTFIX-2: the refill is caused by the job that ended its chain, so the queue's causal
    # record (`job_links`) says so. Without the link a refill read as a manual enqueue.
    from ..runtime import lineage

    lineage.record(db, job, made)
    return getattr(made, "id", None)


def launch0_share(limit: int) -> int:
    """Launch-0 chains allowed in flight while research offers wait: at most limit - 1, at
    least one. The owner's launch scope keeps priority without starving research supply."""
    return max(1, int(limit) - 1)


def run(ctx) -> dict:
    """One admission pass: Launch-0 releases first (owner launch scope), then the offers.

    While research offers wait, Launch-0 yields once its products in flight reach
    `launch0_share(limit)`, so a freed slot goes to the research supply rather than the whole
    registry being drained first. Every yield is recorded with its reason."""
    from ..runtime import release_recovery

    out: dict = {}
    waiting = offers(ctx.db)
    research_waiting = [o for o in waiting if o.get("research")]
    cap = assess(ctx.db)
    launch0_slugs = {cir.slug for cir in release_recovery.launch0_releases()}
    l0_in_flight = sorted(s for s in cap["in_flight"] if s in launch0_slugs)
    share = launch0_share(cap["limit"])
    if research_waiting and len(l0_in_flight) >= share:
        out["launch0"] = {"seeded": [], "yielded": (
            f"{len(l0_in_flight)} Launch-0 chain(s) in flight ({l0_in_flight}) at its share "
            f"{share} of {cap['limit']} while {len(research_waiting)} research offer(s) "
            f"wait: the next slot goes to research supply")}
        ctx.audit(ADMISSION, detail={"admitted": [], "refused": {},
                                     "launch0_yielded": out["launch0"]["yielded"]})
    else:
        try:
            out["launch0"] = release_recovery.seed_launch0(ctx)
        except Exception as exc:  # noqa: BLE001 - recorded; the offers still run
            out["launch0"] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    seeded = len((out["launch0"] or {}).get("seeded") or [])
    out["offers"] = admit(ctx, per_run=max(0, MAX_ADMIT_PER_RUN - seeded))
    out["admitted"] = seeded + len(out["offers"]["admitted"])
    out["waiting_offers"] = len(offers(ctx.db))
    return out
