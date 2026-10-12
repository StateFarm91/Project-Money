"""The shared systematic-failure breaker for every paid handler (F-309).

`visual.reliability` taught the distinction: a check that fails *every* time it is asked is
systematic -- the method is wrong and retrying is spending on a known answer -- while one that
fails *some* of the time is stochastic and retrying is the remedy. Until this module that
distinction stopped spending only in `model_photography` / `owned_photography`, each with its
own copy of the rule. Every other paid handler could keep paying for a floor that had never
once passed.

Here the rule lives once and binds at the one door all paid calls pass through:

* `classify(asked, failed, min_asks)` is the standard (`visual.reliability.assess` uses it).
* A paid handler declares its current method (`declare(handler, method_version)`) and records
  each attempt's floor verdicts (`record(...)`), keyed by handler + method version + floor.
* `gateway.anthropic.check_budget_cad` asks `refusal(db, purpose)` before reserving money: a
  handler whose current method has a systematic floor is refused (`which=systematic_failure`),
  recorded like every other refusal. Only a new method version clears it -- the measurement
  counts the current method only, exactly as `model_photography.METHOD_VERSION` does.

A floor asked fewer than `MIN_ASKS_TO_BLOCK` times is never systematic: "nobody has asked
enough" is not "this does not work".
"""
from __future__ import annotations

OUTCOME_ACTION = "paid.floor_outcome"
# Stricter than reliability's classification floor (2), because this one stops a handler
# across the whole company rather than one render path: five straight failures of the same
# floor under the same method, never a single pass.
MIN_ASKS_TO_BLOCK = 5

_DECLARED: dict[str, str] = {}


def classify(asked: dict[str, int], failed: dict[str, int], *,
             min_asks: int) -> tuple[list[str], list[str], list[str]]:
    """(systematic, stochastic, unclassified) floor names, each sorted."""
    systematic, stochastic, unclassified = [], [], []
    for name, n in failed.items():
        times = asked.get(name, 0)
        if n < times:
            stochastic.append(name)
        elif times >= min_asks:
            systematic.append(name)
        else:
            unclassified.append(name)
    return sorted(systematic), sorted(stochastic), sorted(unclassified)


def declare(handler: str, method_version: str) -> None:
    """The method a paid handler is running now. A new version starts a new measurement."""
    if handler and method_version:
        _DECLARED[handler] = method_version


def declared() -> dict[str, str]:
    return dict(_DECLARED)


def _artifact(handler: str, method_version: str) -> str:
    return f"{handler}@{method_version}"[:200]


def record(db, handler: str, method_version: str, floors: dict[str, str | bool], *,
           agent: str = "orchestrator") -> None:
    """One paid attempt's floor verdicts (`pass`/True = passed; anything else failed)."""
    from datetime import datetime, timezone

    from ..core.models import AuditLog

    if not floors:
        return
    verdicts = {k: ("pass" if v is True or v == "pass" else str(v or "fail"))
                for k, v in floors.items()}
    with db.session() as s:
        s.add(AuditLog(at=datetime.now(timezone.utc), actor=agent[:64],
                       action=OUTCOME_ACTION, artifact=_artifact(handler, method_version),
                       detail={"handler": handler, "method_version": method_version,
                               "floors": verdicts}))


def measure(db, handler: str, method_version: str, *, limit: int = 500) -> dict:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    asked: dict[str, int] = {}
    failed: dict[str, int] = {}
    with db.session() as s:
        rows = list(s.scalars(select(AuditLog.detail).where(
            AuditLog.action == OUTCOME_ACTION,
            AuditLog.artifact == _artifact(handler, method_version))
            .order_by(desc(AuditLog.id)).limit(limit)))
    for d in rows:
        for name, verdict in ((d or {}).get("floors") or {}).items():
            asked[name] = asked.get(name, 0) + 1
            if verdict != "pass":
                failed[name] = failed.get(name, 0) + 1
    systematic, stochastic, unclassified = classify(asked, failed, min_asks=MIN_ASKS_TO_BLOCK)
    return {"handler": handler, "method_version": method_version, "attempts": len(rows),
            "asked": asked, "failed": failed, "systematic": systematic,
            "stochastic": stochastic, "unclassified": unclassified}


def refusal(db, purpose: str) -> str:
    """Why a paid call for this purpose must not be made, or '' when it may.

    Only handlers that declared a method are measured; an undeclared purpose is not blocked
    (and not claimed to be measured)."""
    version = _DECLARED.get(purpose or "")
    if not version:
        return ""
    try:
        m = measure(db, purpose, version)
    except Exception:  # noqa: BLE001 - an unreadable measurement never invents a block
        return ""
    if not m["systematic"]:
        return ""
    return (f"{purpose} under method {version} has failed {m['systematic']} every time they "
            f"were asked ({m['attempts']} attempts, never once passed). Retrying cannot fix a "
            f"systematic failure; a new method version is what clears this, not more spend")


def state(db) -> dict:
    """Every declared handler's measurement, for the governance view."""
    return {h: measure(db, h, v) for h, v in sorted(_DECLARED.items())}
