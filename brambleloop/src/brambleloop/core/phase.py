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

rc1-AUTH: a seal alone bound only a row's content, so a copy of an old sealed "production" row
appended after a rollback restored production (D1). Transitions now form a hash chain
(`core.sealed_chain`): each row's seal covers a monotonic `seq`, the previous row's id and
seal, and its `from` must be the previous row's `to`. A replayed, inserted or deleted row
breaks the chain; a broken chain is no recorded phase (shadow) plus the mismatch incident,
until the owner records a rebase down to shadow. Upward evidence refs must resolve to real,
recent `launch.assessed` / `launch.rollback_rehearsed` rows -- passing ones from
limited_production up (D4).

K4 (F-300): a cited `launch.assessed` row is history. Every move up past shadow now also
requires the launch readiness verdict (`launch.readiness.transition_verdict`: six questions,
every other hard gate, the off-device autonomy proof, the F-275 demand-capture plan)
evaluated at transition time and `ready`; the compact verdict is sealed into the chained row
as `readiness_at_transition`. Owner authority is unchanged and still checked first; a move
down (rollback) never evaluates readiness.

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


def _link_ok(prev: dict, cur: dict) -> str | None:
    if prev.get("to") != cur.get("from"):
        return (f"transition from {cur.get('from')!r} does not continue the previous recorded "
                f"phase {prev.get('to')!r}")
    return None


def _rebase_ok(cur: dict) -> str | None:
    if cur.get("to") != DEFAULT:
        return "a rebase over a broken phase record may only move down to shadow"
    return None


def chain(db) -> dict:
    """D1: the recorded transitions verified as one hash chain (core.sealed_chain).

    A transition is authority only while every row from the chain's genesis (or the newest
    owner rebase) to the newest row verifies its seal, names the row before it (id and seal),
    advances the sequence by one and starts from the phase the previous row recorded. A
    replayed copy of an old sealed row, an inserted row or a deleted row breaks it.
    """
    from . import sealed_chain

    with db.session() as s:
        rows = sealed_chain.load(s, (TRANSITION,))
    out = sealed_chain.walk(rows, _verify, link_ok=_link_ok, rebase_ok=_rebase_ok)
    out["details"] = rows
    return out


def history(db, limit: int = 50) -> list[dict]:
    """Recorded transitions, newest first, each with whether its seal AND its place in the
    chain verify (D1: a validly sealed row replayed out of place is not valid)."""
    c = chain(db)
    flags = {rid: (ok, why) for rid, ok, why in c["rows"]}
    out = []
    for rid, detail in reversed(c["details"][-max(1, int(limit)):] if limit else c["details"]):
        detail = dict(detail or {})
        ok, row_why = flags.get(rid, (False, "unverified"))
        why = None if ok else (row_why or c.get("why") or "phase record chain broken")
        detail.pop("seal", None)
        out.append({"transition_id": rid, **detail, "valid": ok, "invalid_because": why})
    return out


def latest_recorded(db) -> dict:
    """The newest recorded transition. A newest row that does not verify is not skipped:
    falling back to an older valid row would let a forged row hide a real rollback -- and
    since D1 the newest row is valid only when the whole chain up to it verifies."""
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


# D4: what an upward move's evidence refs must resolve to. Each ref is the id of an AuditLog
# row of the named action, recent enough to describe the system as it is now.
EVIDENCE_ACTIONS: dict[str, str] = {"readiness": "launch.assessed",
                                    "rollback": "launch.rollback_rehearsed"}
EVIDENCE_MAX_AGE_DAYS: dict[str, int] = {"readiness": 7, "rollback": 3}
# From this phase upward, the cited readiness must say ready and the rehearsal must have held.
EVIDENCE_MUST_PASS_FROM = Phase.LIMITED_PRODUCTION.value


def _resolve_evidence(session, to: str, refs: dict, now: datetime) -> dict:
    """D4: every required ref names a real, recent record of the right kind (and, for a move
    into limited_production or production, a passing one). Raises ValueError otherwise."""
    from .models import AuditLog

    out = {}
    must_pass = rank(to) >= rank(EVIDENCE_MUST_PASS_FROM)
    for key in REQUIRED_UPWARD_REFS:
        action = EVIDENCE_ACTIONS[key]
        raw = str(refs.get(key, "")).strip()
        if not raw.isdigit():
            raise ValueError(f"evidence ref {key!r} must be the id of a recorded {action!r} "
                             f"row, not {raw[:40]!r}")
        row = session.get(AuditLog, int(raw))
        if row is None or row.action != action:
            raise ValueError(f"evidence ref {key}={raw} does not resolve to a recorded "
                             f"{action!r} row")
        at = row.at if row.at.tzinfo else row.at.replace(tzinfo=timezone.utc)
        age_days = (now - at).total_seconds() / 86400
        if age_days > EVIDENCE_MAX_AGE_DAYS[key] or age_days < -0.01:
            raise ValueError(f"evidence ref {key}={raw} is {age_days:.1f} days old; it must be "
                             f"under {EVIDENCE_MAX_AGE_DAYS[key]} days")
        detail = dict(row.detail or {})
        verdict = detail.get("ready") if key == "readiness" else detail.get("ok")
        if must_pass and verdict is not True:
            raise ValueError(f"evidence ref {key}={raw} does not pass ("
                             f"{'ready' if key == 'readiness' else 'ok'}={verdict!r}); a move "
                             f"to {to!r} needs passing readiness and rollback evidence")
        out[key] = {"id": row.id, "action": action, "at": at.isoformat(),
                    "passing": verdict is True}
    return out


READINESS_AT_TRANSITION = "readiness_at_transition"


def live_readiness(db, to: str) -> dict:
    """The launch verdict for a move up to `to`, evaluated now
    (`launch.readiness.transition_verdict`: the six questions, every other hard gate, the
    off-device autonomy proof and the F-275 demand-capture plan)."""
    from ..launch.readiness import transition_verdict

    return transition_verdict(db, to=to)


def _readiness_at_transition(db, to: str, evaluator) -> dict:
    """K4 / F-300: evaluate the launch verdict at transition time and refuse unless ready.

    Fails closed: an evaluator that raises, returns something other than a dict, or returns
    anything but `ready is True` refuses the move. The compact verdict is returned for the
    sealed row, with the evaluator's name so a substituted evaluator is visible in the chain.
    """
    fn = evaluator if evaluator is not None else live_readiness
    name = f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', '?')}"
    try:
        v = fn(db, to)
    except Exception as exc:  # noqa: BLE001 - an unevaluable verdict is not a ready one
        raise ValueError(f"launch readiness could not be evaluated at transition time "
                         f"({type(exc).__name__}); a move to {to!r} requires "
                         f"readiness.ready") from exc
    if not isinstance(v, dict) or v.get("ready") is not True:
        failing = (v.get("failing") if isinstance(v, dict) else None) or []
        raise ValueError(f"launch readiness is not ready at transition time; a move to "
                         f"{to!r} requires readiness.ready (failing: "
                         f"{', '.join(map(str, failing[:12])) or 'unstated'})")
    keep = ("ready", "evaluated_at", "assessed_at_phase", "questions", "excluded",
            "off_device_autonomy_proof", "demand_capture", "synthetic_fixture")
    out = {k: v[k] for k in keep if k in v}
    out["evaluator"] = name
    out.setdefault("evaluated_at", datetime.now(timezone.utc).isoformat())
    return out


def record_transition(db, *, authorization, to, reason, evidence_refs=None,
                      env: dict | None = None, readiness_verdict=None) -> dict:
    """Write one sealed, chained PhaseTransition under the owner credential.

    `from` is the currently recorded phase (shadow when none). Upward moves go one step at a
    time and cite `readiness` and `rollback` evidence refs that resolve to real records (D4);
    downward moves (rollback) need a reason only. Each row is chained to the one before it
    (D1); over a broken chain only a rebase down to shadow may be recorded. This records the
    decision -- the deployment's `BRAMBLELOOP_PHASE` must also be set to the same value before
    the runtime will run in it.

    K4 / F-300: a move up additionally requires the launch readiness verdict evaluated at
    transition time (`live_readiness` unless the caller passes `readiness_verdict`, a
    callable `(db, to) -> dict`) to be ready; the compact verdict is sealed into the row as
    `readiness_at_transition`. A move down never evaluates readiness.
    """
    from . import sealed_chain
    from .models import AuditLog

    opsauth.check(authorization)
    to = str(to or "").strip().lower()
    if to not in ORDER:
        raise ValueError(f"unknown phase {to!r}; one of {list(ORDER)}")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("owner decision reason required")
    refs = evidence_refs if evidence_refs is not None else {}
    if not isinstance(refs, dict) or not all(isinstance(k, str) and isinstance(v, (str, int))
                                             and not isinstance(v, bool)
                                             and str(v).strip() for k, v in refs.items()):
        raise ValueError("evidence_refs must map evidence kind to a non-empty reference")
    now_dt = datetime.now(timezone.utc)

    def position(s):
        rows = sealed_chain.load(s, (TRANSITION,))
        c = sealed_chain.walk(rows, _verify, link_ok=_link_ok, rebase_ok=_rebase_ok)
        if rows and not c["valid"]:
            # An unverifiable chain is resolved only by an owner rebase down to shadow.
            if to != DEFAULT:
                raise ValueError("the recorded phase chain does not verify ("
                                 f"{c['why']}); record a rollback to shadow before any other "
                                 "move")
            current = DEFAULT
            recorded_valid = False
        else:
            current = str(rows[-1][1].get("to")) if rows else DEFAULT
            recorded_valid = bool(rows)
        return rows, c, current, recorded_valid

    def checked(s, expect=None):
        rows, c, current, recorded_valid = position(s)
        if expect is not None and current != expect:
            raise ValueError(f"the recorded phase changed from {expect!r} to {current!r} "
                             "while launch readiness was evaluated; retry the transition")
        if to == current and recorded_valid:
            raise ValueError(f"phase is already recorded as {to!r}")
        evidence = None
        if rank(to) > rank(current):
            if rank(to) != rank(current) + 1:
                raise ValueError(f"phase moves up one step at a time: {current!r} -> "
                                 f"{ORDER[rank(current) + 1]!r}, not {to!r}")
            missing = [k for k in REQUIRED_UPWARD_REFS if k not in refs]
            if missing:
                raise ValueError(f"an upward phase transition must cite evidence refs {missing}")
            evidence = _resolve_evidence(s, to, refs, now_dt)
        return rows, c, current, evidence

    # Every cheap precondition (credential, chain, one step, cited evidence) is checked first,
    # so a malformed request never pays for the readiness evaluation.
    with db.session() as s:
        _rows, _c, before, _ev = checked(s)
    verdict = None
    if rank(to) > rank(before):
        # K4 / F-300: every move up past shadow requires the launch readiness verdict,
        # evaluated NOW (not a cited old row) and sealed into this transition. It runs outside
        # the write session (it is a long read); the chain is re-read below and the move is
        # refused if the recorded phase changed meanwhile. A move down (rollback) never
        # consults readiness: it must always be possible.
        verdict = _readiness_at_transition(db, to, readiness_verdict)
    with db.session() as s:
        rows, c, current, evidence = checked(s, expect=before)
        detail = {"principal": PRINCIPAL, "from": current, "to": to, "reason": reason.strip(),
                  "evidence_refs": {k: str(v) for k, v in sorted(refs.items())},
                  "at": now_dt.isoformat(),
                  "direction": ("up" if rank(to) > rank(current) else
                                "down" if rank(to) < rank(current) else "reaffirm"),
                  **sealed_chain.next_link(rows, c)}
        if evidence is not None:
            detail["evidence"] = evidence
        if verdict is not None:
            detail["readiness_at_transition"] = verdict
        detail["seal"] = _seal(detail)
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
