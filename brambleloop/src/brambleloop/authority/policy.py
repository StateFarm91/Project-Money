"""Owner authority policy and the Earned Autonomy Ladder (F-703); the dispatch check that
keeps authority from expanding silently (F-669, F-497).

The ladder, per (agent, action class[, job type]):

    owner_each  -- the owner may let this agent hold the authority; every action is still
                   approved by the owner individually (work items wait AWAITING_APPROVAL)
    bounded     -- up to `max_per_day` actions run without a per-item approval
    standing    -- the class runs without per-item approval (still inside every gate,
                   spend ceiling and phase rule the action already had)

Rules, all enforced here, none by convention:

* Only the owner grants, with a fresh step-up and a recorded owner decision id. An agent name
  (or anything that is not the owner) is refused: agents may never self-grant (F-703).
* One rung at a time, and a rung above `owner_each` needs *measured* safe history from rows:
  at least `MIN_SAFE[level]` completed jobs of that class by that agent in the window, zero
  dead letters and zero incidents naming the job type. The history is frozen into the grant.
* DEPLOY, LEGAL-TAX and CREDENTIALS never rise above `owner_each`.
* A grant never raises a spend ceiling or bypasses a gate: SpendGuard, the agent's daily
  ceiling, Product Truth, the phase and every handler gate still apply to the action.
* Shadow first: in SHADOW or STAGING a rung above `owner_each` is recorded but not effective
  (the verdict reports what it *would* allow).
* Safe history must keep holding: a dead letter or incident after the grant drops the
  effective level back to `owner_each` until the owner re-grants.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import classes
from .classes import ActionClass

LEVELS: tuple[str, ...] = ("owner_each", "bounded", "standing")
MIN_SAFE: dict[str, int] = {"bounded": 5, "standing": 25}
HISTORY_WINDOW_DAYS = 90
EFFECTIVE_PHASES: frozenset[str] = frozenset({"limited_production", "production"})


class AuthorityRefused(PermissionError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: datetime | None) -> datetime | None:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _norm(name: str | None) -> str:
    return " ".join((name or "").split()).casefold()


def _declared_agents() -> dict[str, set[str]]:
    from ..agents.registry import DEFAULT_AGENTS

    return {a["name"]: set(a["allowed_job_types"]) for a in DEFAULT_AGENTS}


def _parse_class(value) -> ActionClass:
    if isinstance(value, ActionClass):
        return value
    for c in ActionClass:
        if str(value).strip().upper().replace("_", "-") == c.value or \
                str(value).strip().upper() == c.name:
            return c
    raise AuthorityRefused(f"unknown action class {value!r}")


# ---- reading policies -------------------------------------------------------------------

def active_policies(db, *, agent: str | None = None) -> list[dict]:
    from .models import AuthorityPolicy, ensure_tables

    ensure_tables(db)
    with db.session() as s:
        q = select(AuthorityPolicy).where(AuthorityPolicy.revoked_at.is_(None))
        if agent is not None:
            q = q.where(AuthorityPolicy.agent == agent)
        return [{"id": p.id, "agent": p.agent, "action_class": p.action_class,
                 "job_type": p.job_type, "level": p.level, "max_per_day": p.max_per_day,
                 "max_cost_cad": p.max_cost_cad, "granted_by": p.granted_by,
                 "owner_decision_id": p.owner_decision_id,
                 "at": _aware(p.at).isoformat() if p.at else None,
                 "safe_history": dict(p.safe_history or {})}
                for p in s.scalars(q.order_by(AuthorityPolicy.id))]


def policy_for(db, agent: str, job_type: str) -> dict | None:
    """The most specific active policy covering this agent and job type (job type beats a
    class-wide grant; the higher rung wins among equals)."""
    cls = classes.classify(job_type)
    if not isinstance(cls, ActionClass):
        return None
    best = None
    for p in active_policies(db, agent=agent):
        if p["action_class"] != cls.value or p["job_type"] not in ("", job_type):
            continue
        rank = (1 if p["job_type"] else 0, LEVELS.index(p["level"]))
        if best is None or rank > best[0]:
            best = (rank, p)
    return best[1] if best else None


# ---- measured safe history --------------------------------------------------------------

def job_types_of(cls: ActionClass) -> list[str]:
    return sorted(jt for jt, c in classes.JOB_CLASS.items() if c == cls)


def safe_history(db, agent: str, action_class, job_type: str = "", *,
                 since: datetime | None = None, now: datetime | None = None) -> dict:
    """Completed / dead jobs and incidents for this agent and class, read from rows."""
    from ..core.models import Incident, Job, JobStatus

    cls = _parse_class(action_class)
    now = now or _now()
    start = since or (now - timedelta(days=HISTORY_WINDOW_DAYS))
    types = [job_type] if job_type else job_types_of(cls)
    done = dead = 0
    with db.session() as s:
        for j in s.execute(select(Job.status, Job.created_at).where(
                Job.agent == agent, Job.job_type.in_(types))).all():
            at = _aware(j.created_at)
            if at is not None and at < _aware(start):
                continue
            if j.status == JobStatus.DONE:
                done += 1
            elif j.status == JobStatus.DEAD:
                dead += 1
        incidents = 0
        for row in s.execute(select(Incident.signature, Incident.at)).all():
            at = _aware(row.at)
            if at is not None and at < _aware(start):
                continue
            sig = str(row.signature or "")
            if any(t and t in sig for t in types):
                incidents += 1
    return {"agent": agent, "action_class": cls.value, "job_types": types,
            "since": _aware(start).isoformat(), "done": done, "dead": dead,
            "incidents": incidents, "basis": "measured (jobs, incidents rows)"}


# ---- granting ---------------------------------------------------------------------------

def grant(db, *, agent: str, action_class, job_type: str = "", level: str = "owner_each",
          max_per_day: int = 0, max_cost_cad: float = 0.0, granted_by: str,
          owner_decision_id: str, step_up_verified: bool, reason: str = "",
          now: datetime | None = None) -> int:
    """Record an owner grant. Refuses anything an agent could use to widen itself."""
    from ..agents.registry import Registry
    from .models import AuthorityPolicy, ensure_tables

    now = now or _now()
    actor = _norm(granted_by)
    declared = _declared_agents()
    if actor in {_norm(n) for n in declared} or actor != "owner":
        raise AuthorityRefused(
            f"{granted_by!r} cannot grant authority: only the owner grants, and agents may "
            "never self-grant broader authority (F-703)")
    if step_up_verified is not True:
        raise AuthorityRefused("a grant needs the owner's fresh step-up")
    if not (owner_decision_id or "").strip():
        raise AuthorityRefused("a grant cites the owner's recorded decision id")
    cls = _parse_class(action_class)
    if cls not in classes.GATED:
        raise AuthorityRefused(f"{cls.value} is already autonomous; there is nothing to grant")
    if job_type and classes.classify(job_type) != cls:
        raise AuthorityRefused(f"{job_type} is {classes.class_value(job_type)}, not {cls.value}")
    if level not in LEVELS:
        raise AuthorityRefused(f"unknown ladder level {level!r}")
    if cls in classes.LADDER_CAPPED and level != "owner_each":
        raise AuthorityRefused(f"{cls.value} never rises above owner_each (irreversible)")
    if cls == ActionClass.DEPLOY:
        raise AuthorityRefused("DEPLOY is never held by an agent; production deploy is the "
                               "owner's production_deploy gate (F-497)")
    if agent not in declared:
        raise AuthorityRefused(f"unknown agent {agent!r}")
    if declared[agent] & classes.BUILD_PLANE_JOB_TYPES:
        raise AuthorityRefused(f"{agent} is a build-plane agent; operate-plane authority would "
                               "join the two planes (F-497)")
    try:
        Registry(db).get(agent)
    except Exception as exc:  # noqa: BLE001 - fail closed
        raise AuthorityRefused(f"agent {agent!r} is not registered ({type(exc).__name__})")
    cur = [p for p in active_policies(db, agent=agent)
           if p["action_class"] == cls.value and p["job_type"] == job_type]
    current = max(cur, key=lambda p: LEVELS.index(p["level"])) if cur else None
    cur_index = LEVELS.index(current["level"]) if current else -1
    if LEVELS.index(level) > cur_index + 1:
        raise AuthorityRefused(
            f"the ladder rises one rung at a time: current "
            f"{current['level'] if current else 'none'}, requested {level}")
    history = safe_history(db, agent, cls, job_type, now=now)
    if level in MIN_SAFE:
        need = MIN_SAFE[level]
        if history["done"] < need or history["dead"] or history["incidents"]:
            raise AuthorityRefused(
                f"{level} needs measured safe history: >= {need} completed {cls.value} "
                f"actions with 0 dead letters and 0 incidents in {HISTORY_WINDOW_DAYS} days; "
                f"measured done={history['done']} dead={history['dead']} "
                f"incidents={history['incidents']}")
        if level == "bounded" and int(max_per_day) <= 0:
            raise AuthorityRefused("a bounded rung states its daily bound")
    ensure_tables(db)
    with db.session() as s:
        row = AuthorityPolicy(at=now, agent=agent, action_class=cls.value, job_type=job_type,
                              level=level, max_per_day=int(max_per_day),
                              max_cost_cad=float(max_cost_cad), granted_by="owner",
                              owner_decision_id=owner_decision_id.strip()[:64],
                              reason=(reason or "")[:2000], safe_history=history)
        s.add(row)
        s.flush()
        pid = int(row.id)
    Registry(db).audit("owner", "authority.granted", artifact=f"authority_policies:{pid}",
                       detail={"agent": agent, "class": cls.value, "job_type": job_type,
                               "level": level, "decision": owner_decision_id,
                               "safe_history": history})
    return pid


def revoke(db, policy_id: int, *, revoked_by: str, now: datetime | None = None) -> None:
    """Narrowing is always allowed (owner, Security or the automatic demotion)."""
    from ..agents.registry import Registry
    from .models import AuthorityPolicy, ensure_tables

    if not (revoked_by or "").strip():
        raise AuthorityRefused("a revocation names who revoked")
    ensure_tables(db)
    with db.session() as s:
        row = s.get(AuthorityPolicy, int(policy_id))
        if row is None:
            raise AuthorityRefused(f"no policy {policy_id}")
        if row.revoked_at is None:
            row.revoked_at, row.revoked_by = now or _now(), revoked_by[:64]
    Registry(db).audit(revoked_by, "authority.revoked",
                       artifact=f"authority_policies:{policy_id}")


# ---- effective authority ----------------------------------------------------------------

def _phase(db) -> str:
    try:
        from ..core.phase import effective

        return str(effective(db, record_incident=False))
    except Exception:  # noqa: BLE001 - unreadable phase is shadow
        return "shadow"


def effective_level(db, agent: str, job_type: str, *, now: datetime | None = None,
                    phase: str | None = None) -> dict:
    """The rung that actually applies now. Never raises; fails to owner_each."""
    out = {"recorded": None, "effective": "owner_each", "policy_id": None,
           "why": "no owner policy", "shadow_would": None}
    try:
        p = policy_for(db, agent, job_type)
    except Exception as exc:  # noqa: BLE001
        out["why"] = f"policy unreadable ({type(exc).__name__})"
        return out
    if p is None:
        return out
    out.update(recorded=p["level"], policy_id=p["id"], why="owner policy")
    if p["level"] == "owner_each":
        return out
    try:
        since = datetime.fromisoformat(p["at"]) if p["at"] else None
        hist = safe_history(db, agent, p["action_class"], p["job_type"], since=since,
                            now=now)
    except Exception as exc:  # noqa: BLE001
        out["why"] = f"safe history unreadable ({type(exc).__name__})"
        return out
    if hist["dead"] or hist["incidents"]:
        out["why"] = (f"demoted: {hist['dead']} dead letter(s), {hist['incidents']} "
                      "incident(s) since the grant")
        return out
    ph = phase or _phase(db)
    if ph not in EFFECTIVE_PHASES:
        out["shadow_would"] = p["level"]
        out["why"] = f"phase {ph}: rungs above owner_each are recorded, not effective"
        return out
    out["effective"] = p["level"]
    return out


def check_dispatch(db, agent, job_type: str, *, env: dict | None = None) -> str | None:
    """Why this agent may not run this job type now, or None. Called by
    `Registry.authorize` for every job. Only gated classes are examined; fails closed."""
    cls = classes.JOB_CLASS.get(job_type)
    if cls is None and _production_handler(job_type):
        # A production job type the table has not classified yet: judged by its name, so a
        # consequential one is gated until somebody classifies it (the coverage test makes
        # that a build failure). A type with no production handler can do nothing here.
        cls = classes.classify(job_type)
    if not (isinstance(cls, ActionClass) and cls in classes.GATED):
        return None
    name = getattr(agent, "name", str(agent))
    if classes.runtime_role(env) == "build":
        return (f"{job_type} is {cls.value}; a build runtime (BRAMBLELOOP_RUNTIME_ROLE=build) "
                "never executes operate-plane actions (F-497)")
    if cls == ActionClass.DEPLOY:
        return f"{job_type} is DEPLOY; production deploy is owner-only (F-497)"
    declared = _declared_agents().get(name)
    if declared is not None and declared & classes.BUILD_PLANE_JOB_TYPES:
        return (f"{name} is a build-plane agent and may not run {cls.value} work (F-497)")
    grade = str(getattr(getattr(agent, "authority", None), "value",
                        getattr(agent, "authority", "")) or "").lower()
    in_code = declared is not None and job_type in declared
    if in_code and grade in ("yellow", "red"):
        return None
    try:
        pol = policy_for(db, name, job_type)
    except Exception as exc:  # noqa: BLE001 - fail closed
        return f"authority policy unreadable ({type(exc).__name__}); {cls.value} refused"
    if pol is not None:
        return None
    if not in_code:
        return (f"silent authority expansion refused: {name!r} is not declared in code for "
                f"{job_type} ({cls.value}) and holds no owner AuthorityPolicy (F-669)")
    return (f"{name!r} is GREEN; {job_type} is {cls.value}, which a GREEN agent runs only "
            "under an owner AuthorityPolicy (F-669)")


def _production_handler(job_type: str) -> bool:
    try:
        from ..runtime.worker import handlers

        return handlers.get(job_type) is not None
    except Exception:  # noqa: BLE001 - unknowable: treat as production (fail closed)
        return True


def summary(db) -> dict:
    """Provider-contract summary of recorded authority."""
    try:
        # W4-CCFIN: accept the contract's Session as well as the `Database` facade.
        from ..autonomy.status import _db

        db = _db(db)
        pols = active_policies(db)
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": [], "reason": f"{type(exc).__name__}"}
    return {"status": "OK", "as_of": _now().isoformat(), "basis": "measured",
            "items": pols, "sources": ["authority_policies"], "phase": _phase(db),
            "classes": classes.describe()}
