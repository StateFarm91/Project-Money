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
    if inputs.get("fix_only"):
        # W6 FIX-ONLY (review STOREFRONT a1331372 H1): a remediation's refusal is not the
        # release's dead end. Recording it would replace an ordinary dead end's stored inputs
        # with the bound ones, and every later re-drive would then stop before launch.plan.
        ctx.audit("chain.deadend_not_recorded", artifact=f"{slug}@{version}",
                  detail={"kind": kind, "why": "a fix-only remediation refused; the "
                          "release's own dead end (if any) keeps its ordinary inputs"})
        return {"signature": sig, "opened": False, "owner_action": None, "recorded": False,
                "why": "fix_only"}
    payload = {"kind": kind, "stage": stage, "agent": agent, "department": dept,
               "inputs": {k: v for k, v in inputs.items() if k not in ("rebuild", "fix_only")},
               "refused_under_commit": _commit(), "refused_job": ctx.job.id,
               # Review b31a221b A-LOW-1: an ordinary refusal restates trustworthy inputs.
               "legacy_inputs_restated_by_fix_only": False,
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
            if i.get("fix_only"):
                # Review STOREFRONT a1331372 H1: a fix-only success stops before launch.plan,
                # so it never clears the release's own dead end.
                continue
            if (i.get("slug"), i.get("version"), i.get("release", "")) != (
                    inputs.get("slug"), inputs.get("version"), inputs.get("release", "")):
                continue
            if kind == PRICING and o.get("price_cad") and not o.get("stopped"):
                return True
            if kind == ASSETS and o.get("pdf_sha256") and o.get("ok") is not False:
                return True
    return False


def _resolve(s, sig: str, kind: str, inputs: dict, resolution: str, now,
             owner_reason: str = "") -> None:
    """Resolve a dead end; a pricing one also closes the owner's "decide the price" action
    (review OPUS2B2 F1.1; review b31a221b A-LOW-2: on every resolve path, legacy included)."""
    from sqlalchemy import select

    from ..ops import incident_lifecycle as lifecycle

    lifecycle.resolve_signatures(s, [sig], resolution=resolution, now=now)
    if kind == "pricing":
        from ..core.models import OwnerAction
        from ..ops import owner_queue

        key = OWNER_KEY + f"{inputs.get('slug')}@{inputs.get('version')}"
        for action in s.scalars(select(OwnerAction).where(
                OwnerAction.requirement_key == key, OwnerAction.done.is_(False))):
            owner_queue.close(action, owner_queue.SATISFIED,
                              (owner_reason or f"the pricing dead end closed: {resolution}")
                              [:900], now=now)


def sweep(db, queue, *, now: datetime | None = None) -> dict:
    """Re-drive each open dead end once per deployed commit; resolve the ones that cleared."""
    from sqlalchemy import select

    from ..core.models import Incident
    from ..ops import incident_lifecycle as lifecycle
    from ..queue.durable import DuplicateJob

    now = now or _now()
    here = _commit()
    with db.session() as s:
        rows = [(r.id, r.signature, dict(r.detail or {}) | {"_reports": int(r.report_count or 1)})
                for r in s.scalars(
            select(Incident).where(Incident.signature.like(f"{PREFIX}%"),
                                   Incident.resolved.is_(False)).limit(SWEEP_LIMIT))]
    redriven, resolved, waiting = [], [], []
    for _id, sig, d in rows:
        kind, inputs = d.get("kind"), d.get("inputs") or {}
        if kind not in STAGES or not inputs:
            continue
        if inputs.get("fix_only"):
            # Legacy rows only: since cdf4cb5e a fix-only refusal never records a dead end.
            # Review 4b4e3694: such a row is resolved only when it provably began as a
            # fix-only refusal (one report, and the refusing job itself was bound). A row that
            # was an ordinary dead end before a fix-only refusal restated its inputs
            # (open_or_restate replaces detail) still stands for the release's own refusal:
            # the bound is stripped and the row stays open -- so an ordinary success still
            # closes it -- but it is never re-driven, because its ordinary inputs (and
            # possibly its release) were lost and an ordinary chain could draft a live row.
            from ..core.models import Job

            with db.session() as s:
                try:
                    origin = (s.get(Job, int(d["refused_job"])) if d.get("refused_job")
                              else None)
                except (TypeError, ValueError):
                    origin = None              # unknown origin: kept open, never resolved
                origin_bound = bool(origin is not None and (origin.inputs or {}).get("fix_only"))
                if d.get("_reports", 1) == 1 and origin_bound:
                    _resolve(s, sig, kind, inputs, "recorded from a fix-only remediation's "
                             "refusal, which is not the release's own dead end; not "
                             "re-driven", now)
                    resolved.append(sig)
                    continue
                row = s.scalar(select(Incident).where(Incident.signature == sig,
                                                      Incident.resolved.is_(False)))
                if row is not None:
                    det = dict(row.detail or {})
                    det["inputs"] = {k: v for k, v in dict(det.get("inputs") or {}).items()
                                     if k != "fix_only"}
                    det["legacy_inputs_restated_by_fix_only"] = True
                    row.detail = det
            inputs = {k: v for k, v in inputs.items() if k != "fix_only"}
            if _stage_succeeded(db, kind, inputs):
                with db.session() as s:
                    _resolve(s, sig, kind, inputs,
                             f"{STAGES[kind][0]} has since succeeded for this release", now,
                             owner_reason="pricing.position has since cleared this "
                                          "release's price; no owner decision is needed")
                resolved.append(sig)
                continue
            waiting.append({"signature": sig, "why": "legacy inputs restated by a fix-only "
                            "refusal; the ordinary inputs were lost, so it is not re-driven "
                            "automatically"})
            continue
        if d.get("legacy_inputs_restated_by_fix_only"):
            if not _stage_succeeded(db, kind, inputs):
                waiting.append({"signature": sig, "why": "legacy inputs restated by a fix-only "
                                "refusal; not re-driven automatically"})
                continue
        if _stage_succeeded(db, kind, inputs):
            with db.session() as s:
                # Review OPUS2B2 F1.1: the owner's "decide the price" action closes with the
                # dead end, so the owner is not asked about a product that now has a price.
                _resolve(s, sig, kind, inputs,
                         f"{STAGES[kind][0]} has since succeeded for this release", now,
                         owner_reason="pricing.position has since cleared this release's "
                                      "price; no owner decision is needed")
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
            from .release import without_fix_only

            queue.enqueue(agent, stage, {**without_fix_only(inputs),
                                         "rebuild": f"deadend:{here[:12]}"},
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
