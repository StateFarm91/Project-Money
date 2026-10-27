"""F-389: cost learning -- the loop that proposes cheaper routes and right-sized context.

`bootstrap.register_routing_challengers` registers one cheaper-tier challenger per routed
task, and `routing.equivalence` says whether recorded eval evidence shows the cheaper model
clears every floor the declared one clears. Nothing put the two together with what the money
actually went on. This does, nightly (`league.cycle`), and writes one `improve.cost_learning`
audit row:

* **route opportunities** -- per routed task with a cheaper tier: this month's measured spend
  (`cost_entries` whose purpose is the task), the per-call saving from the two tiers' prices,
  the projected monthly saving at the observed call count, and the equivalence verdict.
  `proposable` only when equivalence holds; otherwise `needs_evidence` with the missing
  evidence named, ranked by projected saving so the eval worth running first is first.
  A proposal is never applied here: the downgrade itself is `routing.override_route`,
  which refuses without evidence (money alone is refused by name).
* **context findings** -- tasks whose observed mean input tokens differ from the declared
  `typical_input_tokens` by more than CONTEXT_DRIFT: larger means the context should be
  trimmed (or the estimate the ceiling checks against is too low); smaller means the
  reservation over-holds budget. Needs MIN_CALLS observed calls; fewer is UNMEASURED.

Spends nothing and calls no model.
"""
from __future__ import annotations

from datetime import datetime, timezone

ACTION = "improve.cost_learning"
CONTEXT_DRIFT = 0.5
MIN_CALLS = 5


def _observed(db, now) -> dict[str, dict]:
    from ..finance import spend_report

    out: dict[str, dict] = {}
    for r in spend_report.rows(db, now=now):
        p = (r.purpose or "").strip()
        if not p:
            continue
        o = out.setdefault(p, {"cad": 0.0, "calls": 0, "tokens_in": 0})
        o["cad"] += float(r.amount_cad or 0.0)
        o["calls"] += 1
        o["tokens_in"] += int(r.tokens_in or 0)
    return out


def opportunities(db, *, now: datetime | None = None) -> dict:
    from ..gateway import routing
    from . import bootstrap

    now = now or datetime.now(timezone.utc)
    seen = _observed(db, now)
    routes, context = [], []
    for key, task in routing.TASKS.items():
        o = seen.get(key) or {"cad": 0.0, "calls": 0, "tokens_in": 0}
        declared = routing.TIERS[task.tier]
        cheaper_key = bootstrap.CHEAPER_TIER.get(task.tier)
        if cheaper_key in routing.TIERS:
            cheaper = routing.TIERS[cheaper_key]
            try:
                per_call = (declared.cost_cad(task.typical_input_tokens, task.max_output_tokens)
                            - cheaper.cost_cad(task.typical_input_tokens,
                                               task.max_output_tokens))
            except Exception:  # noqa: BLE001 - an unpriced tier is UNKNOWN, never 0
                per_call = None
            eq = routing.equivalence(db, key, cheaper_key)
            routes.append({
                "task": key, "from_tier": task.tier, "to_tier": cheaper_key,
                "spent_cad_month": round(o["cad"], 6), "calls_month": o["calls"],
                "saving_per_call_cad": None if per_call is None else round(per_call, 6),
                "projected_saving_cad_month": (None if per_call is None
                                               else round(per_call * o["calls"], 6)),
                "status": "proposable" if eq["equivalent"] else "needs_evidence",
                "missing_evidence": eq["reasons"]})
        if o["calls"] >= MIN_CALLS and task.typical_input_tokens:
            mean_in = o["tokens_in"] / o["calls"]
            ratio = mean_in / task.typical_input_tokens
            if abs(ratio - 1.0) > CONTEXT_DRIFT:
                context.append({
                    "task": key, "declared_input_tokens": task.typical_input_tokens,
                    "observed_mean_input_tokens": round(mean_in, 1), "ratio": round(ratio, 3),
                    "finding": ("context larger than declared: trim it, or the pre-call "
                                "estimate the ceiling checks is too low" if ratio > 1 else
                                "context smaller than declared: the reservation over-holds "
                                "budget; lower typical_input_tokens")})
        elif o["calls"]:
            context.append({"task": key, "state": "UNMEASURED",
                            "why": f"{o['calls']} calls this month; needs {MIN_CALLS}"})
    routes.sort(key=lambda r: -(r["projected_saving_cad_month"] or 0.0))
    return {"as_of": now.isoformat(), "routes": routes, "context": context,
            "proposable": [r["task"] for r in routes if r["status"] == "proposable"],
            "note": ("proposals only; a downgrade is routing.override_route, which refuses "
                     "without recorded equivalence")}


def run(db, *, now: datetime | None = None) -> dict:
    from ..agents.registry import Registry

    out = opportunities(db, now=now)
    Registry(db).audit("cost_optimiser", ACTION, artifact="routing",
                       detail={"proposable": out["proposable"],
                               "routes": out["routes"][:40], "context": out["context"][:40]})
    # F-330: after the first live listing, the day 1/7/14/30 (then monthly) unit-economics
    # review rides the same nightly pass. A failure here never costs the routing reading.
    try:
        from ..finance import launch_cost_review

        out["launch_cost_review"] = launch_cost_review.review(db, now=now)
    except Exception as exc:  # noqa: BLE001
        out["launch_cost_review"] = {"state": "UNKNOWN",
                                     "why": f"{type(exc).__name__}: {str(exc)[:160]}"}
    return out
