"""ENG-ADMIT-TO-BUILD: which owner-activated vision provider may judge a concept board.

Production (0aeb81d2, 2026-11-21T20:40Z): every approved concept waited at the pre-engineering
gate on `image_vision`. The concept-board judge (`creative.intake.judge_held`) asked only
Claude, and Claude vision opens only with an `anthropic-vision:vision` activation. The owner
activated `openai-vision:vision` (D-OWNER-APPROVE-ALL), not Anthropic vision. So nothing was
judged, and nothing was engineered.

This module chooses the judge, and changes nothing about what a judgement must say:

* **Anthropic vision**, when `gateway.anthropic.vision_usable` (activation plus a successful
  probe under it) holds. This is unchanged.
* Otherwise **OpenAI vision**, when `openai-vision:vision` is active and its use is proven:
  - the latest settled `openai-vision` call under an activation still in force was BILLED;
  - or no `openai-vision` call has been settled yet, in which case the first judgement is
    the probe.
  A latest call that failed (RELEASED, meaning declined, or UNCERTAIN) closes the route
  until a judgement succeeds again, or 24 h pass (`RETRY_AFTER`).
* Otherwise **none**. The concept keeps waiting. Unmeasured is never pass.

The judge's answer is parsed by the same `intake.parse_judgement`, so the closed fields and
their ranges are unchanged. The pre-engineering gate reads only those recorded fields, with
the same deterministic thresholds. A provider failure records no judgement, so the concept
stays WAITING, never passed.

**Spend.** Every OpenAI call goes through `OpenAIProvider.see`, which means:
- `paid_provider_gate.enforce` applies the activation's daily, monthly and attempt ceilings,
  plus the company reservation;
- `paid_calls.guarded` applies the fingerprint;
- `judge_held` adds the CA$ budget reservation.
On top of that, on the openai-vision route `attempted` makes the call idempotent per board image:
one paid attempt per (concept, board sha256, provider) per `RETRY_AFTER`, recorded after the
budget reservation and BEFORE the send. A redrive, a retried
job or a second worker never repeats it, and a judgement already on file is never re-asked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

ANTHROPIC, OPENAI = "anthropic", "openai"
ATTEMPT_ACTION = "concept.judge_attempt"
RETRY_AFTER = timedelta(hours=24)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def openai_vision_usable(db, *, now: datetime | None = None) -> bool:
    """`openai-vision:vision` is active and not shown to be failing (see the module doc)."""
    from sqlalchemy import desc, select

    from ..gateway import paid_provider_gate as G

    now = _aware(now) or datetime.now(timezone.utc)
    try:
        from ..gateway.openai_chat import key_present

        if not key_present():                    # no credential: nothing could be judged
            return False
        if not G.activation_state(db, G.OPENAI_VISION, G.VISION, now=now)["active"]:
            return False
        with db.session() as s:
            last = s.scalar(select(G.PaidProviderCall).where(
                G.PaidProviderCall.provider == G.OPENAI_VISION,
                G.PaidProviderCall.status.in_((G.BILLED, G.RELEASED, G.UNCERTAIN)))
                .order_by(desc(G.PaidProviderCall.id)).limit(1))
            if last is None:
                return True                      # never used: the first judgement probes it
            status, act, at = last.status, last.activation_id, _aware(last.settled_at or last.at)
        if status == G.BILLED:
            return G.is_active_id(db, act, now=now)
        if at is None:
            return False
        if now - at >= RETRY_AFTER:
            return True
        # KEYS-19i4: a closure is evidence about the code and credential that produced it. A
        # deploy since that failure (new code, possibly a newly wired credential) gets one fresh
        # judgement; a failure on this deploy keeps the route closed for RETRY_AFTER as before.
        from ..ops.rebuild_graph import _current_deploy_started_at

        started = _aware(_current_deploy_started_at(db))
        return started is not None and at < started
    except Exception:  # noqa: BLE001 - unreadable evidence is a closed route
        return False


def choose(db) -> tuple[str | None, object | None]:
    """(vendor, provider) for the concept-board judge, or (None, None) when none is usable."""
    from ..gateway import providers as gw

    from .intake import JUDGE_TASK

    try:
        if gw.vision_usable(db):
            return ANTHROPIC, gw.provider_for(JUDGE_TASK)
    except Exception:  # noqa: BLE001
        pass
    if openai_vision_usable(db):
        try:
            from ..gateway import openai_chat, routing

            return OPENAI, openai_chat.OpenAIProvider(
                model=routing.openai_model_for(JUDGE_TASK))
        except Exception:  # noqa: BLE001 - an unpriced or unroutable model judges nothing
            return None, None
    return None, None


def attempted(db, board_sha: str, provider_name: str, *, slug: str | None = None,
              now: datetime | None = None) -> bool:
    """A paid judgement of this concept's bytes by this provider was attempted recently."""
    from sqlalchemy import select

    from ..core.models import AuditLog

    now = _aware(now) or datetime.now(timezone.utc)
    with db.session() as s:
        q = select(AuditLog.at, AuditLog.detail).where(
            AuditLog.action == ATTEMPT_ACTION, AuditLog.at >= now - RETRY_AFTER)
        if slug is not None:
            q = q.where(AuditLog.artifact == slug)
        for at, d in s.execute(q):
            d = d or {}
            if d.get("board_sha256") == board_sha and d.get("provider") == provider_name:
                return True
    return False


def record_attempt(ctx, *, slug: str, board_sha: str, provider_name: str, model: str) -> None:
    """Written before the paid call, so a crash mid-call still blocks a repeat."""
    ctx.audit(ATTEMPT_ACTION, artifact=slug, detail={
        "board_sha256": board_sha, "provider": provider_name, "model": str(model)[:80]})
