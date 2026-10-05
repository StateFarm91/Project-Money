"""The effective runtime phase: the environment AND the owner's recorded transition (F-299).

Before this module the phase was whatever `BRAMBLELOOP_PHASE` said. Nothing recorded who moved
the company out of Shadow Mode, why, on what evidence, or how it would be rolled back, and an
edited deployment variable was indistinguishable from an owner decision.

Now a phase change is a **PhaseTransition** record -- from, to, who, why, evidence refs, at --
written only through the owner credential (`record_transition`) and sealed under it, like the
publication grant. The effective phase is resolved from both sources:

* the environment and the newest valid recorded transition **agree** -> that phase;
* they **disagree** (env says limited_production with no transition recorded, a transition
  recorded but the env never changed, a forged or unsealed row, an unparseable env value)
  -> the **more restrictive** of the two, and a phase-mismatch incident is opened.

No recorded transition reads as "shadow", so Shadow stays the default and an environment flag
alone can never take the company out of it. Upward moves go one step at a time and must cite
readiness and rollback evidence; moving down (rollback) is always allowed with a reason.

Nothing here changes the deployed environment, contacts a provider or publishes anything.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from . import opsauth
from .models import Phase

ENV_VAR = "BRAMBLELOOP_PHASE"
DEFAULT = Phase.SHADOW.value
ORDER: tuple[str, ...] = tuple(p.value for p in (Phase.SHADOW, Phase.STAGING,
                                                 Phase.LIMITED_PRODUCTION, Phase.PRODUCTION))
TRANSITION = "owner.phase.transition"
MISMATCH = "phase.mismatch"
PRINCIPAL = "owner:ops-token"
INCIDENT_SIGNATURE = "phase_mismatch:runtime"
# An upward move must cite these; the values are ids/refs of evidence already on file.
REQUIRED_UPWARD_REFS: tuple[str, ...] = ("readiness", "rollback")


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _seal(detail: dict) -> str:
    if not opsauth.configured():
        raise ValueError("owner credential unavailable")
    return hmac.new(os.environ[opsauth.TOKEN_VAR].strip().encode(), _json(detail).encode(),
                    hashlib.sha256).hexdigest()


def rank(phase: str | None) -> int:
    return ORDER.index(phase) if phase in ORDER else 0


def more_restrictive(a: str | None, b: str | None) -> str:
    a = a if a in ORDER else DEFAULT
    b = b if b in ORDER else DEFAULT
    return a if rank(a) <= rank(b) else b


def _env_phase(env: dict | None) -> tuple[str, str | None]:
    """(raw value, parsed phase or None when the value is not a phase)."""
    e = env if env is not None else os.environ
    raw = (e.get(ENV_VAR) or DEFAULT).strip().lower() or DEFAULT
    return raw, (raw if raw in ORDER else None)


def _verify(detail: dict) -> str | None:
    """Why a recorded transition cannot be trusted, or None."""
    detail = dict(detail or {})
    seal = detail.pop("seal", "")
    try:
        expected = _seal(detail)
    except ValueError:
        return "owner credential unavailable, so no recorded transition can be verified"
    if not hmac.compare_digest(str(seal), expected):
        return "recorded transition seal invalid (edited, hand-inserted or credential rotated)"
    if detail.get("to") not in ORDER or detail.get("from") not in ORDER:
        return "recorded transition names an unknown phase"
    return None


def history(db, limit: int = 50) -> list[dict]:
    """Recorded transitions, newest first, each with whether its seal verifies."""
    from sqlalchemy import select

    from .models import AuditLog

    with db.session() as s:
        rows = list(s.scalars(select(AuditLog).where(AuditLog.action == TRANSITION)
                              .order_by(AuditLog.id.desc()).limit(limit)))
        out = []
        for r in rows:
            detail = dict(r.detail or {})
            why = _verify(detail)
            detail.pop("seal", None)
            out.append({"transition_id": r.id, **detail, "valid": why is None,
                        "invalid_because": why})
    return out


def latest_recorded(db) -> dict:
    """The newest recorded transition. A newest row that does not verify is not skipped:
    falling back to an older valid row would let a forged row hide a real rollback."""
    rows = history(db, limit=1)
    if not rows:
        return {"recorded": False, "phase": None, "valid": None, "transition_id": None,
                "why": "no phase transition has ever been recorded; recorded phase is shadow"}
    row = rows[0]
    return {"recorded": True, "phase": row.get("to") if row["valid"] else None,
            "valid": row["valid"], "transition_id": row["transition_id"],
            "why": row["invalid_because"] or f"recorded {row.get('from')} -> {row.get('to')}"}


def resolve(db, env: dict | None = None) -> dict:
    """The effective phase and how it was decided. Pure read; never raises."""
    raw, env_phase = _env_phase(env)
    try:
        rec = latest_recorded(db)
    except Exception as exc:  # noqa: BLE001 - an unreadable record is no record of authority
        rec = {"recorded": None, "phase": None, "valid": False, "transition_id": None,
               "why": f"phase record unreadable: {type(exc).__name__}"}
    if rec["recorded"] is False:
        recorded_phase = DEFAULT
    else:
        recorded_phase = rec["phase"]  # None when the newest row does not verify
    agree = env_phase is not None and recorded_phase is not None and env_phase == recorded_phase
    if agree:
        phase, why = env_phase, (f"{ENV_VAR}={env_phase} agrees with the recorded phase")
    else:
        phase = more_restrictive(env_phase or DEFAULT, recorded_phase or DEFAULT)
        if recorded_phase is None:
            phase = DEFAULT
        why = (f"{ENV_VAR}={raw!r} and the recorded phase "
               f"({recorded_phase or 'UNVERIFIABLE'}: {rec['why']}) disagree; running as the "
               f"more restrictive phase {phase!r}")
    return {"phase": phase, "env": raw, "env_phase": env_phase, "recorded_phase": recorded_phase,
            "transition_id": rec["transition_id"], "record": rec, "agree": agree,
            "mismatch": not agree, "why": why}


def effective(db, env: dict | None = None, *, record_incident: bool = True) -> str:
    """The phase to run as. A mismatch opens (or restates) an incident; agreement resolves it."""
    try:
        r = resolve(db, env)
    except Exception:  # noqa: BLE001 - fail closed
        return DEFAULT
    if record_incident:
        try:
            _reconcile_incident(db, r)
        except Exception:  # noqa: BLE001 - incident bookkeeping never widens the phase
            pass
    return r["phase"]


def effective_phase(db, env: dict | None = None, *, record_incident: bool = True) -> Phase:
    return Phase(effective(db, env, record_incident=record_incident))


def _reconcile_incident(db, r: dict) -> None:
    from .models import AuditLog
    from ..ops import incident_lifecycle

    with db.session() as s:
        if r["mismatch"]:
            detail = {k: r[k] for k in ("env", "recorded_phase", "phase", "transition_id",
                                        "why")}
            _row, opened = incident_lifecycle.open_or_restate(
                s, signature=INCIDENT_SIGNATURE, severity="P1",
                summary=("Runtime phase mismatch: " + r["why"])[:2000], detail=detail)
            if opened:
                s.add(AuditLog(actor="system", action=MISMATCH, artifact="phase",
                               detail=detail))
        else:
            incident_lifecycle.resolve_signatures(
                s, [INCIDENT_SIGNATURE],
                resolution=f"environment and recorded phase agree on {r['phase']!r}")


def record_transition(db, *, authorization, to, reason, evidence_refs=None,
                      env: dict | None = None) -> dict:
    """Write one sealed PhaseTransition under the owner credential.

    `from` is the currently recorded phase (shadow when none). Upward moves go one step at a
    time and cite `readiness` and `rollback` evidence refs; downward moves (rollback) need a
    reason only. This records the decision -- the deployment's `BRAMBLELOOP_PHASE` must also be
    set to the same value before the runtime will run in it.
    """
    opsauth.check(authorization)
    to = str(to or "").strip().lower()
    if to not in ORDER:
        raise ValueError(f"unknown phase {to!r}; one of {list(ORDER)}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    refs = evidence_refs if evidence_refs is not None else {}
    if not isinstance(refs, dict) or not all(isinstance(k, str) and isinstance(v, (str, int))
                                             and str(v).strip() for k, v in refs.items()):
        raise ValueError("evidence_refs must map evidence kind to a non-empty reference")
    rec = latest_recorded(db)
    if rec["recorded"] and not rec["valid"]:
        # An unverifiable newest row is resolved only by moving down to shadow.
        current = None
    else:
        current = rec["phase"] or DEFAULT
    if current is None and to != DEFAULT:
        raise ValueError("newest recorded transition does not verify; record a rollback to "
                         "shadow before any other move")
    current = current or DEFAULT
    if to == current and rec["recorded"] and rec["valid"]:
        raise ValueError(f"phase is already recorded as {to!r}")
    if rank(to) > rank(current):
        if rank(to) != rank(current) + 1:
            raise ValueError(f"phase moves up one step at a time: {current!r} -> "
                             f"{ORDER[rank(current) + 1]!r}, not {to!r}")
        missing = [k for k in REQUIRED_UPWARD_REFS if k not in refs]
        if missing:
            raise ValueError(f"an upward phase transition must cite evidence refs {missing}")
    now = datetime.now(timezone.utc).isoformat()
    detail = {"principal": PRINCIPAL, "from": current, "to": to, "reason": reason.strip(),
              "evidence_refs": {k: str(v) for k, v in sorted(refs.items())}, "at": now,
              "direction": ("up" if rank(to) > rank(current) else
                            "down" if rank(to) < rank(current) else "reaffirm")}
    detail["seal"] = _seal(detail)
    from .models import AuditLog

    with db.session() as s:
        row = AuditLog(actor=PRINCIPAL, action=TRANSITION, artifact=f"phase:{current}->{to}",
                       detail=detail)
        s.add(row)
        s.flush()
        ident = row.id
    out = {k: v for k, v in detail.items() if k != "seal"}
    out["transition_id"] = ident
    r = resolve(db, env)
    out["effective_now"] = r["phase"]
    out["env_must_be"] = to
    out["env_agrees"] = r["env_phase"] == to
    return out
