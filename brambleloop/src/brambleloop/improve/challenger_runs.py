"""F-699: prompt and model challengers that actually run, under an owner-approved reservation.

F-699 (Continuous Greatness): "teams continuously grow, adapt, upgrade prompts/tools/models/
workflows and business strategy after launch, while preserving Product Truth, safety, policy,
finance and owner authority."

The league (`improve.league`) compares challengers with incumbents on recorded runs, and the
bootstrap registers a challenger per model task -- "registered, never run", because a run is
model calls and nothing was allowed to make them. So no prompt or model challenger ever ran,
and the league compared nothing. This module is the bounded way a challenger gets its run:

1. **Plan** (`plan`): every unrun prompt/model challenger, with the exact cost of one run --
   both sides of every shared task, at each configuration's recorded cost per call.
2. **Ask** (`request`): one owner card per challenger run, carrying that exact CAD figure. A run
   above `RUN_CEILING_CAD` is refused outright: the ceiling is code, not a field the card sets.
3. **Approve** (`approve`): only the owner, only up to the planned figure and the ceiling.
4. **Run** (`run`): only when `BRAMBLELOOP_CHALLENGER_RUNS=1`, only against an approval, and only
   inside a `finance.reservations` claim for the approved amount that fits the month's
   remaining model ceiling. Every call is checked against the claim before it is made and the
   run stops at the claim. The caller supplies `call(config, item)` and `score(item, output)`;
   this module never builds a model client. Both sides are recorded with
   `league.record_run` on the same shared tasks (and holdout), so `league.cycle` compares them
   with every existing rule -- and promotion still goes through the league's tiers and the
   owner's decision for code-mirrored routing.

Business-strategy upgrades go through `improve.methods` (the SEO strategy, the free asset, the
gate policy are registered methods), so strategy changes too are proposals, tested,
reversible and monitored. Product Truth, policy and finance remain gate-tier surfaces
(`improve.tiers`): nothing here can reach them without the owner.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

SWITCH = "BRAMBLELOOP_CHALLENGER_RUNS"
KINDS: tuple[str, ...] = ("prompt", "model")
RUN_CEILING_CAD = 2.00
CARD_PREFIX = "improve.challenger_run:"
APPROVAL = "run_spend_approval"
RUNNER = "challenger_runner"


class ChallengerRunRefused(ValueError):
    """A run without its switch, its approval, its reservation or its tasks."""


def enabled() -> bool:
    return os.environ.get(SWITCH, "").strip() == "1"


def _configs(db) -> list[dict]:
    from sqlalchemy import select

    from ..core.models import ConfigVersion

    with db.session() as s:
        return [{"id": r.id, "kind": r.kind, "key": r.key, "incumbent": bool(r.incumbent),
                 "retired": r.retired_at is not None, "version": r.version,
                 "cost": float(r.cost_per_call_cad or 0.0),
                 "outcome": dict(r.measured_outcome or {}),
                 "payload": (r.detail or {}).get("payload")}
                for r in s.scalars(select(ConfigVersion).where(ConfigVersion.kind.in_(KINDS))
                                   .order_by(ConfigVersion.id))]


def plan(db, *, tasks: int = 20, holdout: int = 5) -> list[dict]:
    """Each unrun challenger, its incumbent and the exact CAD one run costs."""
    from . import league

    runs = league._runs(db)
    configs = _configs(db)
    out = []
    for ch in configs:
        if ch["incumbent"] or ch["retired"] or runs.get(ch["id"]):
            continue
        inc = next((c for c in configs if c["incumbent"] and c["kind"] == ch["kind"]
                    and c["key"] == ch["key"]), None)
        if inc is None:
            continue
        n = int(tasks) + int(holdout)
        # Both sides run on the same items in the same pass, so the comparison is like for like.
        cost = round(n * (ch["cost"] + inc["cost"]), 4)
        out.append({"config_id": ch["id"], "incumbent": inc["id"], "kind": ch["kind"],
                    "key": ch["key"], "items": n, "cost_cad": cost,
                    "within_ceiling": cost <= RUN_CEILING_CAD})
    return out


def request(db, config_id: int, **plan_kw) -> dict:
    """Queue one owner card asking for this run's exact spend."""
    from sqlalchemy import select

    from ..core.models import OwnerAction

    p = next((x for x in plan(db, **plan_kw) if x["config_id"] == config_id), None)
    if p is None:
        raise ChallengerRunRefused(f"config {config_id} is not an unrun prompt/model challenger")
    if not p["within_ceiling"]:
        raise ChallengerRunRefused(
            f"one run of config {config_id} costs CA${p['cost_cad']:.2f}, above the "
            f"CA${RUN_CEILING_CAD:.2f} per-run ceiling; shrink the task set")
    key = f"{CARD_PREFIX}{config_id}"
    fields = {"action": (f"Approve CA${p['cost_cad']:.2f} for one league run of {p['kind']}/"
                         f"{p['key']} challenger {config_id} against incumbent "
                         f"{p['incumbent']} on {p['items']} shared and holdout items. Record "
                         f"with improve.challenger_runs.approve({config_id}, "
                         f"amount_cad={p['cost_cad']}, approved_by='owner', why=...)"),
              "reason": ("continuous improvement needs challengers measured, and a run is "
                         "paid model calls; consequential spend is the owner's decision"),
              "max_cost_cad": p["cost_cad"], "minutes": 2,
              "consequence_of_delay": ("the challenger stays registered and unmeasured; "
                                       "nothing running today changes"),
              "blocks": key}
    with db.session() as s:
        existing = s.scalar(select(OwnerAction).where(OwnerAction.requirement_key == key,
                                                      OwnerAction.done == False))  # noqa: E712
        if existing is None:
            s.add(OwnerAction(requirement_key=key, **fields))
            return {"requirement_key": key, "state": "queued", **p}
    return {"requirement_key": key, "state": "already_open", **p}


def approve(db, config_id: int, *, amount_cad: float, approved_by: str, why: str) -> dict:
    from ..core.models import ConfigVersion
    from . import governance

    if governance.normalise_actor(approved_by) != "owner":
        raise ChallengerRunRefused("only the owner approves spend on a challenger run")
    if len((why or "").split()) < 3:
        raise ChallengerRunRefused("an approval says why; this is a label")
    p = next((x for x in plan(db) if x["config_id"] == config_id), None)
    if p is None:
        raise ChallengerRunRefused(f"config {config_id} has no unrun challenger plan")
    amount = round(float(amount_cad), 4)
    if amount > RUN_CEILING_CAD or amount < p["cost_cad"]:
        raise ChallengerRunRefused(
            f"CA${amount:.2f} is outside CA${p['cost_cad']:.2f}..CA${RUN_CEILING_CAD:.2f} "
            f"(the planned run, and the per-run ceiling in code)")
    with db.session() as s:
        row = s.get(ConfigVersion, config_id)
        row.measured_outcome = {**dict(row.measured_outcome or {}), APPROVAL: {
            "by": "owner", "amount_cad": amount, "because": why,
            "at": datetime.now(timezone.utc).isoformat()}}
    return {"config_id": config_id, "approved_cad": amount}


def run(db, config_id: int, *, items: list[dict], holdout: list[dict], call, score,
        on: bool | None = None, now: datetime | None = None) -> dict:
    """One measured run of challenger and incumbent on the same items, inside its claim."""
    from ..finance import reservations
    from ..gateway import routing
    from . import league

    if not (enabled() if on is None else on):
        return {"ran": False, "why": f"{SWITCH} is off: a challenger run is paid calls"}
    configs = {c["id"]: c for c in _configs(db)}
    ch = configs.get(config_id)
    if ch is None or ch["incumbent"]:
        raise ChallengerRunRefused(f"config {config_id} is not a prompt/model challenger")
    approval = ch["outcome"].get(APPROVAL) or {}
    if approval.get("by") != "owner":
        return {"ran": False, "why": "no owner approval of this run's spend is recorded"}
    inc = next(c for c in configs.values() if c["incumbent"] and c["key"] == ch["key"]
               and c["kind"] == ch["kind"])
    if not items:
        raise ChallengerRunRefused("a run with no shared items measures nothing")
    amount = float(approval["amount_cad"])
    remaining = routing.MONTHLY_CEILING_CAD - routing.spent_this_month(db, now) \
        - reservations.outstanding_cad(db)
    if amount > remaining:
        return {"ran": False, "why": (f"CA${amount:.2f} does not fit the month's remaining "
                                      f"CA${max(0.0, remaining):.2f} of model ceiling")}
    rid = reservations.reserve(db, amount_cad=amount, agent=RUNNER,
                               purpose=f"challenger_run:{config_id}", now=now)
    spent = 0.0
    sides = {"incumbent": inc, "challenger": ch}
    results = {k: {"tasks": {}, "holdout": {}, "ok": 0, "n": 0, "lat": [], "cost": 0.0}
               for k in sides}
    stopped = ""
    try:
        for bucket, rows in (("tasks", items), ("holdout", holdout)):
            for it in rows:
                for side, cfg in sides.items():
                    # The dearer of the recorded per-call cost and the dearest call seen so
                    # far on this side: a configuration that costs more than it said cannot
                    # spend past the claim on the strength of its own estimate.
                    est = max(float(cfg["cost"]), results[side].get("max_call", 0.0))
                    if spent + est > amount + 1e-9:
                        stopped = f"stopped at the CA${amount:.2f} claim"
                        break
                    r = call(cfg, it)
                    c = float(r.get("cost_cad") if r.get("cost_cad") is not None else est)
                    spent += c
                    res = results[side]
                    res["n"] += 1
                    res["cost"] += c
                    res["max_call"] = max(res.get("max_call", 0.0), c)
                    res["lat"].append(float(r.get("latency_s") or 0.0))
                    good = r.get("output") is not None
                    res["ok"] += int(good)
                    res[bucket][str(it["id"])] = float(score(it, r.get("output"))) if good \
                        else 0.0
                if stopped:
                    break
            if stopped:
                break
    finally:
        reservations.release(db, rid, actual_cad=round(spent, 6))
    if stopped:
        return {"ran": False, "why": stopped, "spent_cad": round(spent, 6)}
    recorded = {}
    for side, cfg in sides.items():
        res = results[side]
        recorded[side] = league.record_run(
            db, cfg["id"], tasks=res["tasks"], holdout=res["holdout"],
            cost_cad=round(res["cost"] / max(1, res["n"]), 6),
            reliability=round(res["ok"] / max(1, res["n"]), 4),
            latency_s=round(sum(res["lat"]) / max(1, len(res["lat"])), 4),
            run_ref=f"challenger_run:{config_id}:reservation:{rid}", recorded_by=RUNNER)
    return {"ran": True, "config_id": config_id, "incumbent": inc["id"],
            "spent_cad": round(spent, 6), "approved_cad": amount, "reservation": rid,
            "recorded": recorded}
