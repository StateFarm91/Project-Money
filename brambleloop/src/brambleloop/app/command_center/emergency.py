"""Emergency controls (F-889), built only on the company's existing control mechanisms.

| control | existing mechanism it drives |
|---|---|
| pause a department | `Agent.enabled = False` -> `Registry.authorize` refuses every job of that agent in the worker |
| pause spend | `SpendLimit.paused = True` on every scope -> `SpendGuard.authorize_spend` refuses |
| pause publishing | disable `store_operator` + revoke every live grant through `ops.publication_authority` / `ops.activation_authority` (sealed revocation rows) |
| kill switch | `core.phase.record_transition(to="shadow")` (sealed, chained owner transition) + company pause |

Rules:
* **Monitoring, evidence and recovery never pause** (F-889): executive/orchestrator (it runs
  the Etsy observation reads), Product Truth (validation is evidence), Finance (reconciliation)
  and Platform (reliability) are listed as `never_paused` and refused by `pause`.
* **Pausing only ever tightens** and needs no step-up. **Resuming loosens** and needs step-up
  (enforced by the API), and it only undoes what the command center itself paused: an agent
  disabled for another reason, or a spend scope paused by a cap breach, stays as it is
  (a breached scope "stays paused until the owner reviews it" -- `finance.books`).
* The phase is never moved *up* from here; that stays on the evidence-bound owner phase route.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import select

from ...core import opsauth
from ...core.models import Agent, AuditLog, SpendLimit
from .models import ensure_tables, kv_get, kv_set

DEPARTMENTS: dict[str, tuple[str, ...]] = {
    "executive": ("orchestrator",),
    "intelligence": ("market_radar",),
    "product_design": ("creative_director", "crochet_engineer"),
    "product_truth": ("validator", "quality_director", "asset_truth", "policy"),
    "visual": ("publishing",),
    "store": ("store_operator", "listing", "pricing"),
    "support": ("support",),
    "finance": ("cfo",),
    "growth": ("growth", "ads"),
    "learn": ("learn", "evaluator", "failure_miner", "experiment_designer",
              "prompt_tool_challenger", "cost_optimiser", "creative_critic", "lesson_router",
              "experiment_steward"),
    "platform": ("reliability_engineer", "swarm_steward"),
}
# Monitoring / evidence / recovery: never paused by an emergency control (F-889).
NEVER_PAUSED: dict[str, str] = {
    "executive": "runs scheduling and the read-only Etsy observation/monitoring cadences",
    "product_truth": "deterministic validation is evidence collection, never an external effect",
    "finance": "reconciliation and spend challenge are monitoring",
    "platform": "reliability and recovery must keep running",
}
PUBLISHING_AGENTS = ("store_operator",)
SPEND_AGENTS = ("ads",)
STATE_KEY = "emergency_state"
PAUSE_SCOPES = ("company", "publishing", "spend", "department")


class EmergencyRefused(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state(s) -> dict:
    st = kv_get(s, STATE_KEY, {}) or {}
    st.setdefault("paused_agents", {})
    st.setdefault("paused_spend_scopes", [])
    st.setdefault("history", [])
    return st


def _audit(s, actor: str, action: str, detail: dict) -> int:
    row = AuditLog(actor=actor[:64], action=action, artifact="emergency", detail=detail)
    s.add(row)
    s.flush()
    return row.id


def _ops_token() -> str:
    if not opsauth.configured():
        raise EmergencyRefused("operator credential not configured")
    return os.environ[opsauth.TOKEN_VAR].strip()


def pausable_departments() -> list[str]:
    return [d for d in DEPARTMENTS if d not in NEVER_PAUSED]


def _disable_agents(s, names, reason: str, st: dict) -> list[str]:
    changed = []
    for a in s.scalars(select(Agent).where(Agent.name.in_(list(names)))):
        if a.enabled:
            a.enabled = False
            st["paused_agents"][a.name] = reason
            changed.append(a.name)
    return changed


def _live_grants(db) -> list[dict]:
    from ...ops import activation_authority as act
    from ...ops import publication_authority as pub

    out = []
    now = datetime.now(timezone.utc)
    for mod, kind in ((pub, "publication"), (act, "activation")):
        with db.session() as s:
            rows = [(r.id, dict(r.detail or {}), r.artifact) for r in s.scalars(
                select(AuditLog).where(AuditLog.action == mod.APPROVED))]
        for rid, detail, artifact in rows:
            try:
                expires = datetime.fromisoformat(detail.get("expires_at"))
            except (TypeError, ValueError):
                continue
            if expires <= now:
                continue
            try:
                if mod.LEDGER.refusal(db, rid) is not None:
                    continue
            except Exception:  # noqa: BLE001 - an unverifiable grant is not live
                continue
            out.append({"kind": kind, "approval_id": rid, "artifact": artifact,
                        "expires_at": detail.get("expires_at"),
                        "source": f"audit_log:{rid}"})
    return out


def revoke_grant(db, kind: str, approval_id: int) -> dict:
    from ...ops import activation_authority as act
    from ...ops import publication_authority as pub

    mod = {"publication": pub, "activation": act}[kind]
    return mod.revoke(db, authorization=_ops_token(), approval_id=int(approval_id))


def status(db) -> dict:
    from ...core import phase as phase_mod

    ensure_tables(db)
    with db.session() as s:
        st = _state(s)
        agents = {a.name: bool(a.enabled) for a in s.scalars(select(Agent))}
        scopes = [{"scope": r.scope, "paused": bool(r.paused),
                   "paused_by_command_center": r.scope in st["paused_spend_scopes"],
                   "source": f"spend_limits:{r.id}"}
                  for r in s.scalars(select(SpendLimit).order_by(SpendLimit.scope))]
    try:
        phase = phase_mod.resolve(db)
        phase = {k: phase[k] for k in ("phase", "env", "recorded_phase", "agree", "why")}
    except Exception as exc:  # noqa: BLE001
        phase = {"phase": "UNKNOWN", "why": f"unreadable: {type(exc).__name__}"}
    try:
        grants = _live_grants(db)
        grants_status = "OK"
    except Exception as exc:  # noqa: BLE001
        grants, grants_status = [], f"UNKNOWN ({type(exc).__name__})"
    depts = []
    for d, names in DEPARTMENTS.items():
        present = [n for n in names if n in agents]
        depts.append({"department": d, "agents": list(names),
                      "registered": present,
                      "paused": bool(present) and all(not agents[n] for n in present),
                      "paused_agents": [n for n in present if not agents[n]],
                      "pausable": d not in NEVER_PAUSED,
                      "never_paused_because": NEVER_PAUSED.get(d)})
    return {"phase": phase, "departments": depts,
            "spend": {"scopes": scopes,
                      "all_paused": bool(scopes) and all(x["paused"] for x in scopes),
                      "no_scopes_configured": not scopes},
            "publishing": {"agents": list(PUBLISHING_AGENTS),
                           "paused": all(not agents.get(n, True) for n in PUBLISHING_AGENTS),
                           "live_grants": grants, "grants_status": grants_status},
            "paused_by_command_center": st["paused_agents"],
            "never_paused": NEVER_PAUSED,
            "sources": ["agents", "spend_limits", "audit_log (phase + grants)", "cc_kv"]}


def pause(db, *, scope: str, department: str | None, reason: str, actor: str) -> dict:
    """Make the company more restrictive. Never needs step-up; never loosens anything."""
    ensure_tables(db)
    if scope not in PAUSE_SCOPES:
        raise EmergencyRefused(f"scope must be one of {list(PAUSE_SCOPES)}")
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise EmergencyRefused("a reason is required")
    if scope == "department":
        if department not in DEPARTMENTS:
            raise EmergencyRefused(f"unknown department {department!r}; one of "
                                   f"{list(DEPARTMENTS)}")
        if department in NEVER_PAUSED:
            raise EmergencyRefused(f"{department} is never paused: {NEVER_PAUSED[department]}")
    out: dict = {"scope": scope, "department": department, "agents_disabled": [],
                 "spend_scopes_paused": [], "grants_revoked": []}
    tag = f"{scope}{':' + department if department else ''}: {reason.strip()[:200]}"
    with db.session() as s:
        st = _state(s)
        if scope == "department":
            out["agents_disabled"] += _disable_agents(s, DEPARTMENTS[department], tag, st)
        if scope in ("spend", "company"):
            for lim in s.scalars(select(SpendLimit)):
                if not lim.paused:
                    lim.paused = True
                    st["paused_spend_scopes"].append(lim.scope)
                    out["spend_scopes_paused"].append(lim.scope)
            out["agents_disabled"] += _disable_agents(s, SPEND_AGENTS, tag, st)
        if scope in ("publishing", "company"):
            out["agents_disabled"] += _disable_agents(s, PUBLISHING_AGENTS, tag, st)
        if scope == "company":
            for d in pausable_departments():
                out["agents_disabled"] += _disable_agents(s, DEPARTMENTS[d], tag, st)
        st["history"] = (st["history"] + [{"at": _now(), "op": "pause", "scope": scope,
                                           "department": department, "by": actor,
                                           "reason": reason.strip()[:300]}])[-50:]
        kv_set(s, STATE_KEY, st)
    if scope in ("publishing", "company"):
        for g in _live_grants(db):
            revoke_grant(db, g["kind"], g["approval_id"])
            out["grants_revoked"].append(g)
    with db.session() as s:
        out["audit_id"] = _audit(s, actor, "cc.emergency.pause",
                                 {**out, "reason": reason.strip()[:300]})
    out["still_running"] = sorted(NEVER_PAUSED)
    return out


def resume(db, *, scope: str, department: str | None, reason: str, actor: str) -> dict:
    """Loosen: only undoes what the command center paused. The API requires step-up."""
    ensure_tables(db)
    if scope not in PAUSE_SCOPES:
        raise EmergencyRefused(f"scope must be one of {list(PAUSE_SCOPES)}")
    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise EmergencyRefused("a reason is required")
    if scope == "department" and department not in DEPARTMENTS:
        raise EmergencyRefused(f"unknown department {department!r}")
    if scope == "department":
        targets = set(DEPARTMENTS[department])
    elif scope == "spend":
        targets = set(SPEND_AGENTS)
    elif scope == "publishing":
        targets = set(PUBLISHING_AGENTS)
    else:
        targets = None  # company: everything the command center paused
    out = {"scope": scope, "department": department, "agents_enabled": [],
           "spend_scopes_unpaused": [], "left_alone": []}
    with db.session() as s:
        st = _state(s)
        for name in list(st["paused_agents"]):
            if targets is not None and name not in targets:
                continue
            a = s.scalar(select(Agent).where(Agent.name == name))
            if a is not None and not a.enabled:
                a.enabled = True
                out["agents_enabled"].append(name)
            st["paused_agents"].pop(name, None)
        if scope in ("spend", "company"):
            for lim in s.scalars(select(SpendLimit)):
                if lim.scope in st["paused_spend_scopes"]:
                    lim.paused = False
                    out["spend_scopes_unpaused"].append(lim.scope)
                elif lim.paused:
                    out["left_alone"].append(f"spend scope {lim.scope} (paused by a cap "
                                             f"breach, not by the command center)")
            st["paused_spend_scopes"] = [x for x in st["paused_spend_scopes"]
                                         if x not in out["spend_scopes_unpaused"]]
        st["history"] = (st["history"] + [{"at": _now(), "op": "resume", "scope": scope,
                                           "department": department, "by": actor,
                                           "reason": reason.strip()[:300]}])[-50:]
        kv_set(s, STATE_KEY, st)
        out["audit_id"] = _audit(s, actor, "cc.emergency.resume",
                                 {**out, "reason": reason.strip()[:300]})
    out["phase_note"] = ("the phase is not moved up from here; use the owner phase route with "
                         "readiness and rollback evidence")
    return out


def kill_to_shadow(db, *, reason: str, actor: str) -> dict:
    """Record an owner phase transition down to shadow, then pause the company."""
    from ...core import phase as phase_mod

    if not isinstance(reason, str) or len(reason.strip()) < 3:
        raise EmergencyRefused("a reason is required")
    try:
        transition = phase_mod.record_transition(
            db, authorization=_ops_token(), to=phase_mod.DEFAULT,
            reason=f"command-center kill switch ({actor}): {reason.strip()[:300]}")
    except ValueError as exc:
        if "already recorded" not in str(exc):
            raise EmergencyRefused(str(exc)) from exc
        transition = {"already_shadow": True, "why": str(exc)}
    paused = pause(db, scope="company", department=None, reason=f"kill switch: {reason}",
                   actor=actor)
    effective = phase_mod.effective(db)
    with db.session() as s:
        audit_id = _audit(s, actor, "cc.emergency.kill",
                          {"reason": reason.strip()[:300], "effective_phase": effective,
                           "transition_id": transition.get("transition_id")})
    return {"transition": transition, "pause": paused, "effective_phase": effective,
            "audit_id": audit_id}
