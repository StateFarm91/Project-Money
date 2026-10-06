"""Model/provider failover and cost-aware routing (F-921, F-922).

`ModelGateway` already fails over between the providers it is handed and opens a circuit on a
provider that keeps failing. Two things were missing, and both showed up the moment the
gateway was read as a production component rather than a library:

1. **The circuit forgot.** A breaker lives on one `ModelGateway` instance, and production
   builds a new gateway per job (`runtime/release.py`). So every job re-discovered an outage
   by paying for it -- three doomed attempts each -- and nothing outside the process could see
   that a model was down. Health is now *durable*: every attempt the gateway makes is an
   `audit_log` row (`model.attempt`), and `health()` reads the rows. A model with recent
   consecutive failures is DOWN for a cooldown, then HALF_OPEN (one call allowed), then healthy
   again on a success.

2. **There was no fallback to fail over to.** Production hands the gateway exactly one
   provider: the tier's model. `decide()` now builds the ordered candidate list from an
   explicit, owner-reviewable policy:

   * The task's own tier comes first. `routing.TASKS` already routes by what the question needs
     (extraction vs taste vs release-blocking judgement), which is F-922's "expensive where the
     decision value justifies it, cheaper where sufficient" -- the cheapest *sufficient* model is
     the declared tier, and nothing here routes below it.
   * **Fallback only goes up.** `APPROVED_FALLBACKS` lists, per tier, the stronger models that
     may stand in. Never a weaker one: a provider outage cannot authorise a weaker gate (F-921),
     and cost optimisation cannot weaken required evidence (F-922). The deep tier has no
     fallback at all -- there is nothing stronger -- so a deep task with its model down PARKS.
   * **Every candidate must fit the money first.** The padded estimate is checked against the
     month's remaining ceiling and the agent's remaining daily permission before the candidate
     is offered. A stronger fallback costs more, so it is offered only if it fits; otherwise the
     work parks. This is a pre-filter: the authoritative check is still the one inside
     `ModelGateway.complete_json` (`anthropic.check_budget_cad`, with its reservation), and every
     billed attempt is still recorded by `ModelGateway._record` and nowhere else.
   * A cacheable task with an identical earlier answer is served from the cache
     (`routing.cached_analysis`) -- no call, no spend. A task the compiler owns is refused.

When nothing qualifies, the decision is **PARK**: `gateway_for` raises `Parked`, a
`TransientError`, so the worker records a failure and retries with backoff. The job is
queued, not lost and not degraded; no state is written except the job's own retry. That is the
"queue work ... or park honestly" half of F-921.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..core.resilience import MalformedModelOutput, PermanentError, TransientError
from . import routing

ATTEMPT_ACTION = "model.attempt"
HEALTH_WINDOW = timedelta(minutes=60)
# Consecutive failures (newest first) that make a model DOWN, matching the in-process breaker.
DOWN_AFTER_CONSECUTIVE = 3
# How long a DOWN model is skipped before one call is allowed through (HALF_OPEN).
COOLDOWN = timedelta(minutes=10)

HEALTHY, DEGRADED, DOWN, HALF_OPEN, UNKNOWN = (
    "HEALTHY", "DEGRADED", "DOWN", "HALF_OPEN", "UNKNOWN")

CALL, PARK, CACHED, REFUSED = "CALL", "PARK", "CACHED", "REFUSED"

# Relative capability, used only to enforce "fallback never goes down".
# Derived from routing.TIERS so the model names live only in the routing table
# (tests/test_visual_inspection pins that); tier order is the capability order.
_TIER_ORDER = (routing.CHEAP, routing.STANDARD, routing.DEEP)
CAPABILITY_RANK: dict[str, int] = {routing.TIERS[t].model: i + 1
                                   for i, t in enumerate(_TIER_ORDER)}

# Per tier, the stronger models approved to stand in when the tier's model is unavailable.
# Explicit rather than derived so a change is a reviewed edit, and asserted against
# CAPABILITY_RANK so nobody can list a weaker model here (tests/test_v11_reliability_gateway).
APPROVED_FALLBACKS: dict[str, tuple[str, ...]] = {
    routing.CHEAP: (routing.TIERS[routing.STANDARD].model,),
    routing.STANDARD: (routing.TIERS[routing.DEEP].model,),
    routing.DEEP: (),
}


class Parked(TransientError):
    """No approved model is both available and affordable. The job retries later."""

    def __init__(self, message: str, decision: dict | None = None):
        super().__init__(message)
        self.decision = decision or {}


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _session_of(db):
    """A context yielding a session for a `Database` (committed) or a `Session` (as-is)."""
    from contextlib import contextmanager

    if hasattr(db, "execute"):
        @contextmanager
        def _cm():
            yield db
            db.flush()
        return _cm()
    return db.session()


def _key(provider: str, model: str) -> str:
    return f"{provider}:{model}"


def error_kind(exc: BaseException | None) -> str:
    """What a failure says about the *provider's availability*.

    `malformed` means the provider answered (badly): it is up. `budget` is this company
    refusing itself and says nothing about the provider; it is never recorded as an attempt.
    """
    if exc is None:
        return "ok"
    from ..agents.registry import BudgetExceeded

    if isinstance(exc, BudgetExceeded):
        return "budget"
    if isinstance(exc, MalformedModelOutput):
        return "malformed"
    if isinstance(exc, (TransientError, TimeoutError)):
        return "transient"
    if isinstance(exc, PermanentError):
        return "permanent"
    return "error"


def record_attempt(db, *, provider: str, model: str, ok: bool, agent: str = "",
                   purpose: str = "", error: BaseException | None = None,
                   now: datetime | None = None) -> None:
    """One durable row per attempt. Not a spend record -- `ModelGateway._record` is that."""
    from ..core.models import AuditLog

    kind = "ok" if ok else error_kind(error)
    if kind == "budget":
        return
    with _session_of(db) as s:
        s.add(AuditLog(at=_now(now), actor=(agent or "gateway")[:64], action=ATTEMPT_ACTION,
                       artifact=_key(provider, model)[:200],
                       detail={"ok": bool(ok), "kind": kind, "purpose": purpose[:80],
                               "error": (str(error)[:200] if error else "")}))


def health(db, *, now: datetime | None = None, window: timedelta = HEALTH_WINDOW) -> dict:
    """Per `provider:model`, the state its recent attempts put it in."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = _now(now)
    with _session_of(db) as s:
        rows = list(s.execute(
            select(AuditLog.artifact, AuditLog.at, AuditLog.detail)
            .where(AuditLog.action == ATTEMPT_ACTION, AuditLog.at >= now - window)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())).all())
    by: dict[str, list[tuple[datetime, dict]]] = {}
    for art, at, detail in rows:
        by.setdefault(art or "", []).append((_aware(at), detail or {}))
    out: dict[str, dict] = {}
    for key, attempts in by.items():
        consecutive = 0
        for _at, d in attempts:
            if d.get("ok") or d.get("kind") == "malformed":
                break
            consecutive += 1
        permanent = bool(attempts) and attempts[0][1].get("kind") == "permanent"
        last_at = attempts[0][0]
        oks = sum(1 for _a, d in attempts if d.get("ok") or d.get("kind") == "malformed")
        if consecutive >= DOWN_AFTER_CONSECUTIVE or permanent:
            state = HALF_OPEN if now - last_at >= COOLDOWN else DOWN
        elif consecutive > 0:
            state = DEGRADED
        else:
            state = HEALTHY
        out[key] = {"state": state, "attempts": len(attempts), "answered": oks,
                    "consecutive_failures": consecutive, "last_attempt": last_at.isoformat(),
                    "last_kind": attempts[0][1].get("kind"),
                    "retry_after_s": (max(0, int((COOLDOWN - (now - last_at))
                                                 .total_seconds()))
                                      if state == DOWN else 0)}
    return out


def candidates(task_key: str) -> list[str]:
    """The task's tier model, then its approved stronger fallbacks. Refuses compiler tasks."""
    task, tier = routing.route(task_key)
    base = CAPABILITY_RANK.get(tier.model, 0)
    chain = [tier.model]
    for m in APPROVED_FALLBACKS.get(task.tier, ()):
        if CAPABILITY_RANK.get(m, 0) < base:
            raise ValueError(f"{m!r} is weaker than {tier.model!r}: a fallback may never "
                             f"route a task below its declared tier")
        if m not in chain:
            chain.append(m)
    return chain


@dataclass
class Decision:
    action: str
    task: str
    agent: str
    chosen: str | None = None
    order: list[str] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    reason: str = ""
    retry_after_s: int = 0
    cached: dict | None = None

    def to_dict(self) -> dict:
        return {"action": self.action, "task": self.task, "agent": self.agent,
                "chosen": self.chosen, "order": list(self.order),
                "candidates": list(self.candidates), "reason": self.reason,
                "retry_after_s": self.retry_after_s, "cached": self.cached is not None}


def _money(db, agent: str, now: datetime) -> dict:
    from . import anthropic as gw

    spent = gw.spent_this_month_cad(db, now=now)
    ceiling = gw.monthly_ceiling_cad()
    daily = gw.agent_daily_ceiling(db, agent, now=now) if agent else None
    return {"month_spent_cad": spent, "month_ceiling_cad": ceiling,
            "month_remaining_cad": round(max(0.0, ceiling - spent), 6),
            "agent_daily": daily}


def decide(db, task_key: str, *, agent: str = "", payload: dict | None = None,
           now: datetime | None = None) -> Decision:
    """Pick the model for one call, or say why there is none. Writes nothing."""
    from . import anthropic as gw

    now = _now(now)
    try:
        task, _tier = routing.route(task_key)
        chain = candidates(task_key)
    except routing.TaskRefused as exc:
        return Decision(REFUSED, task_key, agent, reason=str(exc))
    if payload is not None and task.cacheable:
        cached = routing.cached_analysis(_DbView(db), task_key, payload)
        if cached is not None:
            return Decision(CACHED, task_key, agent, cached=cached,
                            reason="an identical request was answered before; no call made")
    states = health(_DbView(db), now=now)
    money = _money(_DbView(db), agent, now)
    rows, order, waits = [], [], []
    for model in chain:
        h = states.get(_key("anthropic", model), {"state": UNKNOWN})
        estimate = gw.estimate_cad(model, input_tokens=task.typical_input_tokens,
                                   output_tokens=task.max_output_tokens)
        fits_month = money["month_spent_cad"] + estimate <= money["month_ceiling_cad"]
        daily = money["agent_daily"]
        fits_day = (daily is None
                    or daily["spent_today_cad"] + estimate <= daily["daily_ceiling_cad"])
        available = h["state"] != DOWN
        row = {"model": model, "provider": "anthropic", "health": h["state"],
               "estimate_cad": estimate, "fits_month": fits_month, "fits_agent_day": fits_day,
               "is_fallback": model != chain[0]}
        rows.append(row)
        if not available:
            waits.append(h.get("retry_after_s", 0))
            continue
        if fits_month and fits_day:
            order.append(model)
    if order:
        chosen = order[0]
        why = ("the declared tier's model" if chosen == chain[0] else
               f"approved stronger fallback: {chain[0]} is {rows[0]['health']}")
        return Decision(CALL, task_key, agent, chosen=chosen, order=order, candidates=rows,
                        reason=why)
    unaffordable = [r["model"] for r in rows if r["health"] != DOWN]
    if unaffordable:
        reason = (f"no available model fits the money: month CA${money['month_spent_cad']:.2f}"
                  f" of CA${money['month_ceiling_cad']:.2f} spent"
                  + ("" if money["agent_daily"] is None else
                     f"; agent {agent!r} CA${money['agent_daily']['spent_today_cad']:.2f} of "
                     f"CA${money['agent_daily']['daily_ceiling_cad']:.2f} today")
                  + ". Parked rather than routed to a weaker model")
        retry = 3600
    else:
        reason = (f"every approved model for {task_key!r} is DOWN "
                  f"({', '.join(chain)}); parked rather than degraded to a weaker model")
        retry = max([w for w in waits if w] or [int(COOLDOWN.total_seconds())])
    return Decision(PARK, task_key, agent, candidates=rows, reason=reason,
                    retry_after_s=int(retry))


class _DbView:
    """`Database`-shaped access to whatever `db` is (Database or Session)."""

    def __init__(self, db):
        self._db = db

    def session(self):
        return _session_of(self._db)

    def __getattr__(self, name):
        return getattr(self._db, name)


def gateway_for(db, task_key: str, *, registry, agent: str, job_id: int | None = None,
                payload: dict | None = None,
                provider_factory: Callable[[str], object] | None = None):
    """A `ModelGateway` whose providers are the decision's order. Raises `Parked`.

    Returns `(gateway, decision)`; for a CACHED decision the gateway is None and
    `decision.cached` holds the answer. `provider_factory(model)` defaults to the real
    `AnthropicProvider`; tests inject a transport stand-in.
    """
    from .model_gateway import ModelGateway

    decision = decide(db, task_key, agent=agent, payload=payload)
    if decision.action == REFUSED:
        raise routing.TaskRefused(decision.reason)
    if decision.action == CACHED:
        return None, decision
    if decision.action == PARK:
        raise Parked(decision.reason, decision.to_dict())
    if provider_factory is None:
        from .anthropic import AnthropicProvider

        def provider_factory(model: str):
            return AnthropicProvider(model=model)
    providers = [provider_factory(m) for m in decision.order]
    return ModelGateway(providers, registry=registry, job_id=job_id), decision


def status(db, *, now: datetime | None = None) -> dict:
    """For the Command Center: policy, per-model health, last probe. Never raises on empty."""
    now = _now(now)
    view = _DbView(db)
    try:
        states = health(view, now=now)
    except Exception as exc:  # noqa: BLE001
        return {"status": UNKNOWN, "reason": f"health unreadable: {type(exc).__name__}"}
    try:
        from .anthropic import last_probe

        probe = last_probe(view)
    except Exception:  # noqa: BLE001
        probe = None
    down = [k for k, v in states.items() if v["state"] == DOWN]
    if not states:
        st, why = UNKNOWN, ("no model attempt in the last hour: availability is not "
                            "observed, which is not the same as down")
    elif down:
        st, why = "DEGRADED", f"down: {', '.join(sorted(down))}"
    else:
        st, why = "OK", "every recently attempted model answered"
    return {"status": st, "reason": why, "models": states,
            "policy": {"approved_fallbacks": {k: list(v) for k, v in
                                              APPROVED_FALLBACKS.items()},
                       "fallback_direction": "stronger only; deep tier parks",
                       "down_after_consecutive_failures": DOWN_AFTER_CONSECUTIVE,
                       "cooldown_s": int(COOLDOWN.total_seconds())},
            "last_probe": probe, "as_of": now.isoformat()}
