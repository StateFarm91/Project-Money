"""ASSET-VISION (19i3): which owner-activated vision provider may inspect a listing asset.

Production (2026-11-22, FIRST-LISTING owner item 2): `inspect.describe_image`, `inspect_image`
and `identify_at_grid` always asked the `asset_inspection` route's default vendor, Anthropic.
The review paths (parity HERO, #61 frame review, exported-frame review) ran only while the
`image_vision` gate was open, and that gate opens only on Anthropic vision. The owner activated
`openai-vision:vision` (D-OWNER-APPROVE-ALL), not Anthropic vision. So hero and frame review
stayed unjudged for every release, and the certificate could never be valid.

The choice is the same rule the concept-board judge uses (`creative.concept_judge.choose`,
ENG-ADMIT-TO-BUILD), applied to the `asset_inspection` task:

* **Anthropic vision**, when the `image_vision` gate is open (an activation plus a successful
  probe). The route and the provider are exactly as before.
* Otherwise **OpenAI vision**, when `concept_judge.openai_vision_usable` holds: the
  `openai-vision:vision` activation is active and its latest settled call did not fail.
* Otherwise **no judge**. The provider refuses every call, so every check stays unmade,
  which reads as unjudged. Unmeasured is never a pass.

What a judgement must say is unchanged: the same prompts, the same parsers and the same
deterministic verdicts (`inspect.gate`, `frame_role.verdict`, the grid rule).

**Spend.** OpenAI calls still go through `OpenAIProvider.see`, so the activation's ceilings
(`paid_provider_gate`) and the paid-call fingerprint still apply. The inspect functions'
own `check_budget` reservation is unchanged as well. On top of that, the OpenAI route is
idempotent per image bytes (`once_key`, applied inside each inspect `_call`). One paid attempt is allowed per (image sha256,
system, prompt, max tokens) per `RETRY_AFTER`, recorded BEFORE the send:

* a successful answer is stored, and a repeat is served from it, with nothing sent and
  nothing billed;
* an attempt with no stored answer, such as a crash or a failure, is never re-sent
  within the window, and its checks stay unmade.

The Anthropic route keeps its existing paid-call store.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from ..core.resilience import PermanentError, TransientError

TASK = "asset_inspection"
ATTEMPT_ACTION = "asset_inspection.openai_attempt"
ANSWER_ACTION = "asset_inspection.openai_answer"
RETRY_AFTER = timedelta(hours=24)
ANTHROPIC, OPENAI = "anthropic", "openai"


NO_JUDGE_WHY = ("no owner-activated vision provider is usable (Anthropic vision gate closed, "
                "openai-vision not usable); nothing was sent and the check stays unmade")


class NoVisionJudge:
    """The provider when no vision route is usable: every call refuses, nothing is sent."""

    name = "none"
    model = "none"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def see(self, system, prompt, image_urls, *, max_tokens):  # noqa: ARG002
        raise PermanentError(NO_JUDGE_WHY)


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _image_sha(ref: str) -> str:
    """sha256 of the image's bytes (a local file), or of the reference itself (a URL)."""
    if not ref.startswith(("http://", "https://", "data:")):
        with open(ref, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    return hashlib.sha256(ref.encode()).hexdigest()


def _once_applies(db, provider) -> bool:
    """The per-bytes idempotency applies to the OpenAI vision route (the Anthropic route
    keeps its existing paid-call store)."""
    return db is not None and str(getattr(provider, "name", "")).startswith("openai")


def once_key(db, provider, system, prompt, image_urls, max_tokens) -> str | None:
    """The idempotency key of one question about these image bytes, or None (not applicable)."""
    if not _once_applies(db, provider):
        return None
    shas = [_image_sha(u) for u in image_urls]
    body = "\n".join([str(provider.name), str(provider.model), str(max_tokens),
                      hashlib.sha256((system or "").encode()).hexdigest(),
                      hashlib.sha256((prompt or "").encode()).hexdigest(), *shas])
    return hashlib.sha256(body.encode()).hexdigest()


def kept_answer(db, provider, key: str, *, now: datetime | None = None):
    """The stored answer to this exact question (served with nothing sent or billed), None
    when it was never asked, or TransientError when it was asked and no answer was kept."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog
    from ..gateway.model_gateway import ModelResponse

    now = _aware(now) or datetime.now(timezone.utc)
    answer, attempted = None, False
    with db.session() as s:
        for action, detail in s.execute(
                select(AuditLog.action, AuditLog.detail)
                .where(AuditLog.action.in_((ATTEMPT_ACTION, ANSWER_ACTION)),
                       AuditLog.artifact == key[:64],
                       AuditLog.at >= now - RETRY_AFTER)
                .order_by(desc(AuditLog.id))):
            d = detail or {}
            if action == ANSWER_ACTION and answer is None and "text" in d:
                answer = d
            elif action == ATTEMPT_ACTION:
                attempted = True
    if answer is not None:
        return ModelResponse(text=str(answer["text"]), provider=str(provider.name),
                             model=str(answer.get("model") or provider.model),
                             input_tokens=0, output_tokens=0, latency_ms=0.0, replayed=True)
    if attempted:
        raise TransientError("these image bytes were already sent to this judge with this "
                             "question within the retry window and no answer was kept; not "
                             "sent again (the check stays unmade)")
    return None


def _audit(db, action: str, key: str, detail: dict) -> None:
    from ..core.models import AuditLog

    with db.session() as s:
        s.add(AuditLog(action=action, artifact=key[:64], actor="quality_director",
                       detail=detail))


def record_attempt(db, provider, key: str) -> None:
    """Written after the budget reservation and BEFORE the send: a crash blocks a repeat."""
    _audit(db, ATTEMPT_ACTION, key, {"provider": str(provider.name),
                                     "model": str(provider.model), "task": TASK})


def record_answer(db, provider, key: str, response) -> None:
    _audit(db, ANSWER_ACTION, key, {"provider": str(provider.name),
                                    "model": str(getattr(response, "model", provider.model)),
                                    "text": str(response.text)[:20000], "task": TASK})


def choose(db) -> tuple[str | None, object]:
    """(vendor, provider) for `asset_inspection`. With no usable route, (None, NoVisionJudge())."""
    from ..gateway import providers as gw

    if db is None:
        return ANTHROPIC, gw.provider_for(TASK)          # no evidence to read: unchanged
    try:
        if gw.vision_usable(db):
            return ANTHROPIC, gw.provider_for(TASK)
    except Exception:  # noqa: BLE001 - unreadable evidence is a closed Anthropic route
        pass
    try:
        from ..creative import concept_judge

        if concept_judge.openai_vision_usable(db):
            from ..gateway import openai_chat, routing

            return OPENAI, openai_chat.OpenAIProvider(model=routing.openai_model_for(TASK))
    except Exception:  # noqa: BLE001 - an unpriced or unroutable model judges nothing
        pass
    return None, NoVisionJudge()


def provider_for(db):
    """The provider the inspect functions use when the caller names none."""
    return choose(db)[1]


def vision_open(db) -> bool:
    """Whether any asset review can be made: the image_vision gate, or usable openai-vision."""
    try:
        from .gallery import gates_now

        if gates_now(db, keys=("image_vision",)).get("image_vision"):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        from ..creative import concept_judge

        return bool(concept_judge.openai_vision_usable(db))
    except Exception:  # noqa: BLE001 - unreadable evidence is closed
        return False
