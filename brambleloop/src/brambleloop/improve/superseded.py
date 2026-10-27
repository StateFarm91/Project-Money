"""F-126 Superseded Evidence Retention: an invalid or confounded experiment is kept, marked.

F-126: "Keep invalid/confounded experiments marked superseded with reason."

Before this module the company had the idea in two places and nowhere general: a confounded
growth experiment keeps its confounder log (`growth.experiments.log_confounders`) and a
superseded visual frame is refused as a reference (`visual.model_registry`). An improvement
experiment -- the loop every department runs -- had no way to say "this result is not
evidence". It could only be REJECTED, and a rejected row with a baseline and a result is a
*measured failure* to `improve.failure_memory`: the same idea is then refused for ever, on a
result that was never about the idea.

Three rules:

* **Retained, never deleted.** `supersede` writes a marker on the row's evidence (reason,
  who, when, and the row that supersedes it, when one does). The baseline, the result and the
  trial record stay exactly as they were, so anybody can re-read why it was set aside.
* **Excluded from every aggregate that reads results as evidence.** Failure memory does not
  treat a superseded row as a failure (a confounded loss disproves nothing), and the
  Director's completed/killed experiment lists and the weekly retrospective report superseded
  rows on their own line rather than counting them as verdicts.
* **Write-once.** A marker cannot be replaced or removed: un-superseding a result to count it
  after all is the move the requirement exists to stop. A row still open (PROPOSED/TESTING) is
  closed as REJECTED by the same act, with the reason on it, so it cannot be promoted on the
  evidence just set aside.
"""
from __future__ import annotations

from datetime import datetime, timezone

MARKER = "superseded"
ACTION = "improve.superseded"
# Why a result is set aside. Closed, so "superseded" stays a statement about the evidence.
REASON_KINDS: tuple[str, ...] = ("confounded", "invalid", "replaced")


class SupersedeRefused(ValueError):
    """A supersession without a reason, of a missing row, or of a row already marked."""


def marker(evidence: dict | None) -> dict | None:
    m = (evidence or {}).get(MARKER)
    return m if isinstance(m, dict) and m.get("reason") else None


def is_superseded(evidence: dict | None) -> bool:
    return marker(evidence) is not None


def supersede(db, improvement_id: int, *, kind: str, reason: str, by: str,
              superseded_by: int | None = None, confounders: list | None = None,
              now: datetime | None = None) -> dict:
    """Mark one improvement's evidence superseded, keep the row, and say why (F-126)."""
    from ..core.models import AuditLog, Improvement
    from . import cells, governance

    if kind not in REASON_KINDS:
        raise SupersedeRefused(f"{kind!r} is not a supersession kind: {list(REASON_KINDS)}")
    if len((reason or "").split()) < 4:
        raise SupersedeRefused("a superseded result says why it is no longer evidence; this "
                               "is a label")
    who = governance.normalise_actor(by)
    if not who:
        raise SupersedeRefused("a supersession names who set the evidence aside")
    now = now or datetime.now(timezone.utc)
    with db.session() as s:
        row = s.get(Improvement, improvement_id)
        if row is None:
            raise SupersedeRefused(f"no improvement {improvement_id}")
        ev = dict(row.evidence or {})
        if is_superseded(ev):
            raise SupersedeRefused(
                f"improvement {improvement_id} was already superseded "
                f"({ev[MARKER]['reason'][:120]}); the marker is write-once")
        if superseded_by is not None and s.get(Improvement, superseded_by) is None:
            raise SupersedeRefused(f"superseded_by {superseded_by} is not an improvement")
        mark = {"kind": kind, "reason": reason.strip()[:500], "by": who,
                "at": now.isoformat(), "state_before": row.state,
                **({"superseded_by": int(superseded_by)} if superseded_by is not None else {}),
                **({"confounders": list(confounders)[:20]} if confounders else {})}
        ev[MARKER] = mark
        if row.state in (cells.PROPOSED, cells.TESTING):
            row.state = cells.REJECTED
            ev["why"] = f"superseded ({kind}): {reason.strip()[:300]}"
            ev.setdefault("decided_at", now.isoformat())
        row.evidence = ev
        s.add(AuditLog(actor=who[:60], action=ACTION, artifact=f"improvement:{improvement_id}",
                       detail={"improvement": improvement_id, **mark}))
    return {"improvement": improvement_id, "superseded": True, **mark}


def listing(db, *, cell: str | None = None) -> list[dict]:
    """Every superseded improvement, retained with its baseline, result and reason."""
    from sqlalchemy import select

    from ..core.models import Improvement

    out = []
    with db.session() as s:
        q = select(Improvement).order_by(Improvement.id)
        if cell:
            q = q.where(Improvement.cell == cell)
        for r in s.scalars(q):
            m = marker(r.evidence)
            if m:
                out.append({"improvement": r.id, "cell": r.cell, "state": r.state,
                            "baseline": r.baseline_value, "result": r.result_value, **m})
    return out
