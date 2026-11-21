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
