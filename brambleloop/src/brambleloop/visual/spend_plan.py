"""Bounded Visual Spend (F-877): every paid Visual experiment carries a complete plan.

Wave-3 lane K12. A paid visual experiment must state, before anything is bought:
hypothesis, provider/model, call count, max spend, and pass/fail criteria. `build` makes
that record, `validate` refuses one that lacks any of them, and `guard` is the ceiling check
an executor runs before each call -- the plan's own `max_spend_cad`, enforced in code, on top
of (never instead of) the global spend ceilings in `gateway.images.reserve_render`.

Consumers: `visual.rnd.loop.experiment` stores a plan on every GATED_SPEND experiment and
`visual.rnd.loop.execute_paid` refuses an incomplete plan before it even consults the
(closed) paid-execution gate; `visual.provider_trial.run` validates its own plan and
enforces its ceiling through it. A complete plan authorises nothing by itself: spend still
needs owner authority, which this build does not have.
"""
from __future__ import annotations

PLAN_VERSION = "visual-spend-plan/1"
REQUIRED: tuple[str, ...] = ("hypothesis", "provider_model", "call_count", "max_spend_cad",
                             "pass_criteria", "fail_criteria")


class PlanRefused(ValueError):
    """A paid visual experiment without a complete plan, or one past its own ceiling."""


def build(*, hypothesis: str, provider_model: str, call_count: int, max_spend_cad: float,
          pass_criteria: list[str] | tuple[str, ...], fail_criteria: list[str] | tuple[str, ...],
          price_cad_per_call: float | None = None, basis: str = "") -> dict:
    return {"version": PLAN_VERSION, "hypothesis": str(hypothesis or "").strip(),
            "provider_model": str(provider_model or "").strip(),
            "call_count": call_count, "max_spend_cad": max_spend_cad,
            "price_cad_per_call": price_cad_per_call,
            "pass_criteria": [str(c).strip() for c in pass_criteria or () if str(c).strip()],
            "fail_criteria": [str(c).strip() for c in fail_criteria or () if str(c).strip()],
            "basis": basis or "estimated: list price, not a measurement"}


def problems(plan: dict | None) -> list[str]:
    """Every reason this plan cannot govern a paid experiment. Empty means complete."""
    if not isinstance(plan, dict) or not plan:
        return ["no plan"]
    out = []
    if not str(plan.get("hypothesis") or "").strip():
        out.append("hypothesis missing")
    if not str(plan.get("provider_model") or "").strip():
        out.append("provider/model missing")
    n = plan.get("call_count")
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        out.append("call_count must be a positive integer")
    cap = plan.get("max_spend_cad")
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not cap > 0:
        out.append("max_spend_cad must be a positive amount")
    for key in ("pass_criteria", "fail_criteria"):
        if not [c for c in plan.get(key) or () if str(c).strip()]:
            out.append(f"{key} missing")
    price = plan.get("price_cad_per_call")
    if (not out and isinstance(price, (int, float)) and not isinstance(price, bool)
            and price * n > cap + 1e-9):
        out.append(f"call_count x price (CA${round(price * n, 4)}) exceeds max_spend_cad "
                   f"(CA${cap})")
    return out


def validate(plan: dict | None) -> dict:
    found = problems(plan)
    if found:
        raise PlanRefused("paid visual experiment refused: " + "; ".join(found) + " (F-877)")
    return plan


def guard(plan: dict, *, spent_cad: float, calls_made: int, next_cost_cad: float) -> None:
    """Before each paid call: refuse past the plan's call count or its max spend."""
    validate(plan)
    if calls_made + 1 > int(plan["call_count"]):
        raise PlanRefused(f"call {calls_made + 1} exceeds the plan's call_count "
                          f"{plan['call_count']}")
    if float(spent_cad) + float(next_cost_cad) > float(plan["max_spend_cad"]) + 1e-9:
        raise PlanRefused(f"CA${spent_cad} spent + CA${next_cost_cad} next exceeds the plan's "
                          f"max_spend_cad CA${plan['max_spend_cad']}")
