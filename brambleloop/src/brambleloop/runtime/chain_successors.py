"""Deterministic successors for the release chain's dead ends (P0-CHAIN-DEADENDS).

W-INVENTORY (`research/final_build/w4/INVENTORY.md`, "Chain breaks found while deriving
states") found four places where a product stops with nothing after it:

1. `pricing.position` refuses (unknown product, or no in-band price clears the net floor) and
   enqueues nothing; nothing raises an owner action or a fix job.
2. `assets.build` returns `ok: false` (listing images misrepresent the pattern) and enqueues
   nothing; only a `CHAIN_VERSION` bump re-drives it.
3. The `listing.parity` audit row carries no version, so a verdict for one version can be read
   as another's. (Fixed at the producer in `runtime.pipeline`: the row now carries the version
   and release it judged.)
4. `launch.plan` holds a missed seasonal window and enqueues nothing unless it pivots;
   nothing re-plans when the window reopens.

Each now has a successor, chosen so that nothing loops and nothing is decided by guessing:

* **Who acts.** A business decision (a price no in-band amount can clear) becomes an owner
  action with the refusal's reasons. A company defect (an unknown product, misrepresenting
  images) becomes a P2 incident naming the department that fixes it. Neither halts anything
  the refusal did not already halt.
* **When it is asked again.** A deterministic refusal gives the same answer to the same code
  and inputs, so re-asking on a timer is a loop. The hourly `chain.successors` sweep therefore
  re-drives each recorded dead end **once per deployed commit** (`core.build.commit`), the one
  event that can change the answer, and never while the commit is unknown (the rule
  `ops.queue_check` already follows). A held launch is re-planned the day after the missed
  occasion, when `next_occurrence` moves to the next cycle.
* **When it is closed.** The sweep resolves a dead end's incident once the stage has
  succeeded for that release.

Records are `Incident` rows (signature `chain-deadend:<kind>:<slug>@<version>`) and owner
actions keyed `chain-deadend:pricing:<slug>@<version>`; the release identity a re-drive needs
is kept in the incident's detail. Writes nothing else. No model, network or spend.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

PREFIX = "chain-deadend:"
PRICING = "pricing"
ASSETS = "assets"
JOB_TYPE = "chain.successors"
AUDIT_ACTION = "chain.deadend"
OWNER_KEY = PREFIX + "pricing:"
UNKNOWN_COMMIT = "unknown"
REPLAN_FALLBACK_DAYS = 30
SWEEP_LIMIT = 200

# kind -> (stage job type, agent, department that fixes it)
STAGES: dict[str, tuple[str, str, str]] = {
    PRICING: ("pricing.position", "pricing", "store_commerce (pricing)"),
    ASSETS: ("assets.build", "publishing", "visual"),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def signature(kind: str, slug: str, version: str) -> str:
    return f"{PREFIX}{kind}:{slug}@{version}"[:200]


def _commit() -> str:
    from ..core import build

    return build.commit() or UNKNOWN_COMMIT


def record(ctx, kind: str, *, inputs: dict, summary: str, detail: dict,
           owner_action: dict | None = None) -> dict:
    """Record a dead end at the point the stage refuses. Idempotent per release.

    `inputs` are the refused job's inputs: what a re-drive enqueues again. The commit the
    refusal happened under is kept, so the sweep re-drives only under a different one.
    """
    from ..core.models import OwnerAction
    from ..ops import incident_lifecycle as lifecycle

    stage, agent, dept = STAGES[kind]
    slug = str(inputs.get("slug") or "")
    version = str(inputs.get("version") or "")
    sig = signature(kind, slug, version)
    payload = {"kind": kind, "stage": stage, "agent": agent, "department": dept,
               "inputs": {k: v for k, v in inputs.items() if k != "rebuild"},
               "refused_under_commit": _commit(), "refused_job": ctx.job.id,
               **detail}
    with ctx.db.session() as s:
        row, opened = lifecycle.open_or_restate(
            s, signature=sig, severity="P2", product_slug=slug or None,
            summary=f"{stage} refused for {slug}@{version}: {summary}"[:500],
            detail=payload, halts_publication=False)
        action_key = None
        if owner_action is not None:
            from sqlalchemy import select

            action_key = OWNER_KEY + f"{slug}@{version}"
            existing = s.scalar(select(OwnerAction).where(
                OwnerAction.requirement_key == action_key, OwnerAction.done.is_(False)))
            if existing is None:
                s.add(OwnerAction(requirement_key=action_key, **owner_action))
            else:
                existing.action = owner_action["action"]
                existing.reason = owner_action["reason"]
    ctx.audit(AUDIT_ACTION, artifact=f"{slug}@{version}",
              detail={"kind": kind, "signature": sig, "opened": opened,
                      "owner_action": action_key, "department": dept})
    return {"signature": sig, "opened": opened, "owner_action": action_key}


def pricing_refused(ctx, inputs: dict, decision: dict, *, code: str = "") -> dict:
    """Successor for a `pricing.position` refusal."""
    slug, version = inputs.get("slug"), inputs.get("version")
    reasons = [str(r) for r in (decision.get("reasons") or [])][:5]
    if code:
        # No product record: a catalogue defect for the company, never an owner's price call.
        return record(ctx, PRICING, inputs=inputs,
                      summary=f"{code}: no product record names what this product is",
                      detail={"code": code, "why": str(decision.get("why") or "")[:300]})
    refused = str(decision.get("refused") or "")[:400]
    action = {
        "action": (f"Decide the price for {slug} {version}: no price inside its category band "
                   f"clears the net-contribution floor. Approve a price outside the band, "
                   f"change the product, or retire it."),
        "reason": (f"{refused} Reasons: {'; '.join(reasons)}")[:1000],
        "max_cost_cad": 0.0, "minutes": 10,
        "consequence_of_delay": "the product stays priced-out; its listing is not drafted",
        "blocks": f"listing for {slug}@{version}",
        "why_software_cannot": ("pricing outside the observed band, or retiring a certified "
                                "product, is a commercial decision the policy reserves to the "
                                "owner"),
    }
    return record(ctx, PRICING, inputs=inputs, summary=refused or "net floor not cleared",
                  detail={"refused": refused, "reasons": reasons}, owner_action=action)


def images_blocked(ctx, inputs: dict, problems: list) -> dict:
    """Successor for an `assets.build` whose listing images misrepresent the pattern."""
    probs = [str(p)[:200] for p in (problems or [])][:5]
    return record(ctx, ASSETS, inputs=inputs,
                  summary=f"listing images misrepresent the pattern ({len(problems or [])} "
                          f"problem(s)); the visual department fixes the renderer or the CIR",
                  detail={"problems": probs})


def launch_held(ctx, inputs: dict, decision: dict, *, today: date):
    """Successor for a held seasonal launch: re-plan the day after the missed occasion.

    A pivot is already carried out by `launch.plan` itself. For HOLD / SIMPLIFY the plan is
    asked again once `next_occurrence` has moved to the next cycle; with no occasion date it is
    asked again after `REPLAN_FALLBACK_DAYS`. One re-plan per release per occasion date.
    """
    from ..seasonal import leadtime as lt
    from .release import chain_key

    if decision.get("action") == lt.PIVOT_EVERGREEN:
        return None
    slug, version = inputs.get("slug"), inputs.get("version")
    try:
        event = date.fromisoformat(str(decision.get("event_date")))
        when = event + timedelta(days=1)
    except (TypeError, ValueError):
        event, when = None, today + timedelta(days=REPLAN_FALLBACK_DAYS)
    if when <= today:
        when = today + timedelta(days=1)
    run_after = datetime(when.year, when.month, when.day, 6, 0, tzinfo=timezone.utc)
    nxt = {k: v for k, v in inputs.items() if k not in ("window_decision", "launch", "as_of")}
    key = chain_key("plan", str(slug), str(version), str(inputs.get("release", "")),
                    f"{inputs.get('rebuild', '')}:replan:{when.isoformat()}")
    job = ctx.enqueue("growth", "launch.plan", nxt, idempotency_key=key, run_after=run_after)
    ctx.audit(AUDIT_ACTION, artifact=f"{slug}@{version}",
              detail={"kind": "launch_hold", "action": decision.get("action"),
                      "occasion": decision.get("occasion"),
                      "event_date": event.isoformat() if event else None,
                      "replan_on": when.isoformat(), "queued": job is not None,
                      "design_note": ("a simplification is a creative decision for Product & "
                                      "Design" if decision.get("action") == lt.SIMPLIFY
                                      else None)})
    return {"replan_on": when.isoformat(), "queued": job is not None}


def _stage_succeeded(db, kind: str, inputs: dict) -> bool:
    """Whether the stage has since succeeded for this exact slug, version and release."""
    from sqlalchemy import desc, select

    from ..core.models import Job, JobStatus

    stage = STAGES[kind][0]
    with db.session() as s:
        for j in s.scalars(select(Job).where(Job.job_type == stage, Job.status == JobStatus.DONE)
                           .order_by(desc(Job.id)).limit(SWEEP_LIMIT)):
            i, o = j.inputs or {}, j.outputs or {}
            if (i.get("slug"), i.get("version"), i.get("release", "")) != (
                    inputs.get("slug"), inputs.get("version"), inputs.get("release", "")):
                continue
            if kind == PRICING and o.get("price_cad") and not o.get("stopped"):
                return True
            if kind == ASSETS and o.get("pdf_sha256") and o.get("ok") is not False:
                return True
    return False


def sweep(db, queue, *, now: datetime | None = None) -> dict:
    """Re-drive each open dead end once per deployed commit; resolve the ones that cleared."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle as lifecycle
    from ..queue.durable import DuplicateJob

    now = now or _now()
    here = _commit()
    with db.session() as s:
        rows = [(r.id, r.signature, dict(r.detail or {})) for r in s.scalars(
            select(Incident).where(Incident.signature.like(f"{PREFIX}%"),
                                   Incident.resolved.is_(False)).limit(SWEEP_LIMIT))]
    redriven, resolved, waiting = [], [], []
    for _id, sig, d in rows:
        kind, inputs = d.get("kind"), d.get("inputs") or {}
        if kind not in STAGES or not inputs:
            continue
        if _stage_succeeded(db, kind, inputs):
            with db.session() as s:
                lifecycle.resolve_signatures(s, [sig], resolution=(
                    f"{STAGES[kind][0]} has since succeeded for this release"), now=now)
            resolved.append(sig)
            continue
        if here == UNKNOWN_COMMIT:
            waiting.append({"signature": sig, "why": "deployed commit unknown: a re-drive "
                                                     "would be an unbounded loop"})
            continue
        last = d.get("redriven_under_commit") or d.get("refused_under_commit")
        if last == here:
            waiting.append({"signature": sig, "why": "refused under this commit; waits for "
                                                     "the next deploy or a fix"})
            continue
        stage, agent, _dept = STAGES[kind]
        try:
            queue.enqueue(agent, stage, {**inputs, "rebuild": f"deadend:{here[:12]}"},
                          idempotency_key=f"deadend:{sig}:{here}"[:200])
        except DuplicateJob:
            pass
        with db.session() as s:
            row = s.scalar(select(Incident).where(Incident.signature == sig,
                                                  Incident.resolved.is_(False)))
            if row is not None:
                row.detail = {**dict(row.detail or {}), "redriven_under_commit": here,
                              "redriven_at": now.isoformat()}
        redriven.append(sig)
    return {"open": len(rows), "redriven": redriven, "resolved": resolved,
            "waiting": waiting, "commit": here,
            "work_done": len(redriven) + len(resolved)}
