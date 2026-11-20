"""Paid experiment ledger (F-274) -- W4-C10.

"Every campaign/change records objective, authorization, listings, budget, settings, window,
evidence, verdict and rollback/next action."

The ledger is the existing experiments table (`core.models.Experiment`, kind `paid_ads`): one
row per campaign or change, whose `result` holds the ledger record and an append-only
`history`. Recording an entry is bookkeeping, not permission and not execution -- a ledger row
with no authorization is still written (so a refused idea is remembered), and its state says
UNAUTHORISED.

* `open_entry` refuses a record missing any of `REQUIRED`; the authorization is
  `{type, ref}` -- an owner action, or `none` -- and is checked, not trusted: an owner action
  that does not exist or is not done reads UNAUTHORISED;
* `record_evidence` appends dated evidence (a funnel snapshot);
* `close` sets the verdict (`VERDICTS`) with the rollback / next action, once; a closed entry
  is never rewritten, and a later change is a new entry pointing at it (`replaces`).

Phase is SHADOW for every entry this repository writes: nothing here can run a campaign.
"""
from __future__ import annotations

from datetime import datetime, timezone

KIND = "paid_ads"
REQUIRED = ("objective", "authorization", "listings", "budget", "settings", "window",
            "next_action")
VERDICTS = ("WIN", "LOSS", "INCONCLUSIVE", "STOPPED", "NOT_RUN")


class LedgerRefused(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _authorised(db, auth: dict) -> dict:
    from ..core.models import OwnerAction

    if auth.get("type") == "owner_action" and auth.get("ref") is not None:
        with db.session() as s:
            act = s.get(OwnerAction, int(auth["ref"]))
            if act is not None and act.done:
                return {"state": "AUTHORISED", "owner_action": act.id}
            return {"state": "UNAUTHORISED",
                    "why": "the owner action does not exist" if act is None else
                           "the owner has not decided the action"}
    return {"state": "UNAUTHORISED", "why": "no owner authorization"}


def open_entry(db, name: str, entry: dict, *, replaces: int | None = None) -> int:
    from ..core.models import Experiment

    missing = [k for k in REQUIRED if not entry.get(k)]
    b = entry.get("budget") or {}
    if b and not all(isinstance(b.get(k), (int, float)) and b[k] > 0
                     for k in ("daily_cad", "total_cad")):
        missing.append("budget.daily_cad/total_cad")
    w = entry.get("window") or {}
    if w and not (w.get("start") and w.get("days")):
        missing.append("window.start/days")
    if missing:
        raise LedgerRefused(f"ledger entry missing {missing}")
    auth = _authorised(db, entry["authorization"])
    record = {**entry, "phase": "SHADOW", "executed": False, "authorization_check": auth,
              "evidence": [], "verdict": None, "replaces": replaces,
              "history": [{"at": _now(), "event": "opened", "authorization": auth["state"]}]}
    with db.session() as s:
        row = Experiment(name=name, kind=KIND, product_slug=(entry["listings"] or [None])[0],
                         hypothesis=str(entry["objective"]), arms=list(entry["listings"]),
                         min_observations=int(entry.get("min_clicks", 200)),
                         max_loss_cad=float(b["total_cad"]),
                         state="designed" if auth["state"] == "AUTHORISED" else "unauthorised",
                         result=record)
        s.add(row)
        s.flush()
        return row.id


def _load(s, entry_id):
    from ..core.models import Experiment

    row = s.get(Experiment, entry_id)
    if row is None or row.kind != KIND:
        raise LedgerRefused(f"no paid-ads ledger entry {entry_id}")
    return row


def record_evidence(db, entry_id: int, evidence: dict) -> None:
    with db.session() as s:
        row = _load(s, entry_id)
        rec = dict(row.result)
        if rec.get("verdict"):
            raise LedgerRefused("a closed entry is not rewritten; open a new one")
        rec["evidence"] = [*rec["evidence"], {"at": _now(), **evidence}]
        rec["history"] = [*rec["history"], {"at": _now(), "event": "evidence"}]
        row.result = rec


def close(db, entry_id: int, *, verdict: str, next_action: str, rollback: str = "") -> dict:
    if verdict not in VERDICTS:
        raise LedgerRefused(f"verdict must be one of {VERDICTS}")
    if not next_action:
        raise LedgerRefused("a verdict needs its next action")
    with db.session() as s:
        row = _load(s, entry_id)
        rec = dict(row.result)
        if rec.get("verdict"):
            raise LedgerRefused("this entry already has a verdict")
        if verdict in ("WIN", "LOSS") and not rec["evidence"]:
            raise LedgerRefused("a WIN or LOSS needs recorded evidence")
        rec.update(verdict=verdict, next_action=next_action, rollback=rollback)
        rec["history"] = [*rec["history"], {"at": _now(), "event": "closed",
                                            "verdict": verdict}]
        row.result, row.state = rec, "closed"
        return rec


def entries(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import Experiment

    with db.session() as s:
        return [{"id": r.id, "name": r.name, "state": r.state, **dict(r.result or {})}
                for r in s.scalars(select(Experiment).where(Experiment.kind == KIND)
                                   .order_by(Experiment.id))]
