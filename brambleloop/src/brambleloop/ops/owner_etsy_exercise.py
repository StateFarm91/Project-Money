"""D-OWNER-ETSY-EXERCISE: the owner's instruction to run the Etsy shadow-write exercise once.

On 2026-11-21 (~02:20 UTC) the owner, away from their PC, told the integrating session
"I can't do it. You do it" about the controlled Etsy exercise (OWNER_ACTIONS_P0.md P0-1).
The exercise normally runs only through the operator-authenticated
`POST /api/etsy/exercise`. This module runs the same `integrations.etsy_exercise.run`
(mode `full`) from the service itself, under that instruction:

* It runs only inside the directive's window, [GIVEN_AT, SUNSET], and never after it.
* It makes at most MAX_ATTEMPTS attempts, ever, counted from the audit log. It stops after
  the first clean run.
* The exercise is unchanged. It makes one clearly marked DRAFT, then deletes it and verifies
  the delete. Its client is built with `owner_authorised=False`, so nothing on this path can
  activate or publish. Cost: CA$0.
* Every attempt writes an audit row with the outcome. A refusal (an expired Etsy grant, for
  example) is recorded, never retried in a loop, and never worked around.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

DIRECTIVE_ID = "D-OWNER-ETSY-EXERCISE"
GIVEN_AT = datetime(2026, 11, 21, 2, 20, tzinfo=timezone.utc)
SUNSET = GIVEN_AT + timedelta(hours=24)
MAX_ATTEMPTS = 2
ACTOR = f"owner-directive:{DIRECTIVE_ID}"
ACTION = "owner_directive.etsy_exercise"

log = logging.getLogger("brambleloop.owner_etsy_exercise")


def _attempts(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == ACTION).order_by(AuditLog.id))]


def due(db, *, now: datetime | None = None) -> dict:
    """Whether an attempt may run now, and why not when it may not."""
    now = now or datetime.now(timezone.utc)
    if not (GIVEN_AT <= now <= SUNSET):
        return {"due": False, "why": "outside the directive's window"}
    prior = _attempts(db)
    if any(a.get("ok") is True for a in prior):
        return {"due": False, "why": "a clean exercise already ran under this directive"}
    if len(prior) >= MAX_ATTEMPTS:
        return {"due": False, "why": f"{MAX_ATTEMPTS} attempts made; not retried"}
    return {"due": True, "why": "", "attempt": len(prior) + 1}


def maybe_run(db, *, verify=None, now: datetime | None = None, runner=None) -> dict:
    """Run the exercise once if due. Never raises; every attempt is audited."""
    from ..core.models import AuditLog

    try:
        d = due(db, now=now)
    except Exception as exc:  # noqa: BLE001 - an unreadable store runs nothing
        return {"ran": False, "why": f"store unreadable: {type(exc).__name__}"}
    if not d["due"]:
        return {"ran": False, "why": d["why"]}
    if runner is None:
        from ..integrations import etsy_exercise

        def runner():
            return etsy_exercise.run(db, mode="full", verify=verify)
    detail: dict = {"directive": DIRECTIVE_ID, "attempt": d["attempt"]}
    try:
        report = runner() or {}
        detail.update({"ok": bool(report.get("ok")), "status": report.get("status"),
                       "shop_is_clean": report.get("shop_is_clean")})
    except Exception as exc:  # noqa: BLE001 - a refusal is recorded, never worked around
        detail.update({"ok": False, "refused": type(exc).__name__, "why": str(exc)[:300]})
    try:
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR[:64], action=ACTION, artifact="etsy.exercise:full",
                           detail=detail))
    except Exception:  # noqa: BLE001
        log.warning("could not audit %s attempt %s", DIRECTIVE_ID, d["attempt"])
    log.warning("%s attempt %s: ok=%s", DIRECTIVE_ID, d["attempt"], detail.get("ok"))
    return {"ran": True, **detail}


def visibility(db) -> dict:
    """`factory_visibility.owner_etsy_exercise` (ENG-ETSY-RECOVERY). Fixed vocabulary only.

    Counts, status classes, step names and taxonomy outcome names -- never a listing id, a
    title or an Etsy message. The directive's own rows (D-OWNER-ETSY-EXERCISE) predate the
    cause field, so their cause is read from the matching `etsy.exercise_finished` rows.
    """
    from sqlalchemy import select

    from ..core.models import AuditLog
    from ..integrations import etsy_exercise as X

    attempts = _attempts(db)
    with db.session() as s:
        finished = [dict(r.detail or {}) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == X.RUN_FINISHED)
            .order_by(AuditLog.id.desc()).limit(5))]
        rec = s.scalar(select(AuditLog).where(AuditLog.action == X.RECOVERED)
                       .order_by(AuditLog.id.desc()).limit(1))
        rec = dict(rec.detail or {}) if rec is not None else None

    def _ints(d) -> dict:
        return {k: int(v) for k, v in (d or {}).items()
                if isinstance(k, str) and all(X._word(p) for p in k.split(":", 1))
                and isinstance(v, int) and not isinstance(v, bool)}

    def _cause(c) -> dict | None:
        if not isinstance(c, dict):
            return None
        return {"failed_steps": [w for w in (X._word(x) for x in c.get("failed_steps") or [])
                                 if w][:12],
                "cleanup_outcomes": _ints(c.get("cleanup_outcomes")),
                "exercise_skipped": c.get("exercise_skipped") is True,
                "read_back_ok": c.get("read_back_ok") is True,
                "recovery_counts": _ints(c.get("recovery_counts")),
                "recovery_cleaned": int(c.get("recovery_cleaned") or 0),
                **{k: int(c.get(k) or 0) for k in (
                    "marked_drafts_in_shop", "ledger_confirmed_gone", "ledger_still_on_etsy",
                    "ledger_could_not_ask", "owner_actions")}}

    return {
        "directive": DIRECTIVE_ID,
        "attempts": len(attempts), "max_attempts": MAX_ATTEMPTS,
        "ok": any(a.get("ok") is True for a in attempts),
        "attempt_classes": ["refused" if a.get("refused") else X.status_class(a.get("status"))
                            for a in attempts],
        "last_runs": [{"mode": X._word(f.get("mode")) or "unknown", "ok": f.get("ok") is True,
                       "status_class": X.status_class(f.get("status")),
                       "shop_is_clean": f.get("shop_is_clean") is True,
                       "cause": _cause(f.get("cause"))} for f in finished],
        "last_recovery": None if rec is None else {
            "ok": rec.get("ok") is True, "counts": _ints(rec.get("counts")),
            "cleaned": int(rec.get("cleaned") or 0),
            "status_classes": _ints(rec.get("status_classes"))},
    }


# ---- D-OWNER-ETSY-EXERCISE-2 ------------------------------------------------------------
# The owner, again away from a PC ("I can't do it. You do it"; "full autonomous"), re-issued the
# instruction after the first two attempts found the shop not clean. Under this second
# directive the service first runs the recovery (`etsy_exercise.recover`: it deletes only
# listings provably our own, never-active exercise drafts, each delete read back), then the
# unchanged full exercise. It is bounded like the first: its own window, at most
# MAX_ATTEMPTS_2 attempts, it stops after the first clean run, and every attempt is audited.

DIRECTIVE_ID_2 = "D-OWNER-ETSY-EXERCISE-2"
GIVEN_AT_2 = datetime(2026, 11, 21, 12, 20, tzinfo=timezone.utc)
SUNSET_2 = GIVEN_AT_2 + timedelta(hours=24)
MAX_ATTEMPTS_2 = 3
ACTOR_2 = f"owner-directive:{DIRECTIVE_ID_2}"
ACTION_2 = "owner_directive.etsy_exercise_2"


def _attempts_2(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [dict(r.detail or {}) for r in s.scalars(
            select(AuditLog).where(AuditLog.action == ACTION_2).order_by(AuditLog.id))]


def due_2(db, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not (GIVEN_AT_2 <= now <= SUNSET_2):
        return {"due": False, "why": "outside the second directive's window"}
    prior = _attempts_2(db)
    if any(a.get("ok") is True for a in prior):
        return {"due": False, "why": "a clean exercise already ran under the second directive"}
    if len(prior) >= MAX_ATTEMPTS_2:
        return {"due": False, "why": f"{MAX_ATTEMPTS_2} attempts made; not retried"}
    return {"due": True, "why": "", "attempt": len(prior) + 1}


def maybe_run_2(db, *, verify=None, now: datetime | None = None, recoverer=None,
                runner=None) -> dict:
    """Recovery, then the full exercise, once if due. Never raises; audited."""
    from ..core.models import AuditLog

    try:
        d = due_2(db, now=now)
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "why": f"store unreadable: {type(exc).__name__}"}
    if not d["due"]:
        return {"ran": False, "why": d["why"]}
    if recoverer is None or runner is None:
        from ..integrations import etsy_exercise

        recoverer = recoverer or (lambda: etsy_exercise.recover(db))
        runner = runner or (lambda: etsy_exercise.run(db, mode="full", verify=verify))
    detail: dict = {"directive": DIRECTIVE_ID_2, "attempt": d["attempt"]}
    try:
        rec = recoverer() or {}
        detail["recovery_cleaned"] = int(rec.get("cleaned") or rec.get("recovery_cleaned") or 0)
        detail["recovery_ok"] = bool(rec.get("ok", True))
    except Exception as exc:  # noqa: BLE001 - recovery refusal recorded; exercise still tried
        detail.update({"recovery_ok": False, "recovery_refused": type(exc).__name__})
    try:
        report = runner() or {}
        detail.update({"ok": bool(report.get("ok")), "status": report.get("status"),
                       "shop_is_clean": report.get("shop_is_clean")})
    except Exception as exc:  # noqa: BLE001
        detail.update({"ok": False, "refused": type(exc).__name__, "why": str(exc)[:300]})
    try:
        with db.session() as s:
            s.add(AuditLog(actor=ACTOR_2[:64], action=ACTION_2, artifact="etsy.exercise:full",
                           detail=detail))
    except Exception:  # noqa: BLE001
        log.warning("could not audit %s attempt %s", DIRECTIVE_ID_2, d["attempt"])
    return {"ran": True, **detail}
