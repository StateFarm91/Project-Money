"""F-095 Fallback Capability Contract: what a fallback must prove before it stands in.

F-095: "Define required structured output, vision, context, quality, latency and cost before a
fallback can satisfy a gate."

`contract_for(task_key)` is the contract for the task's tier: structured JSON output, vision
when the tier sees images, a minimum context (twice the task's typical input plus its output
budget), an evaluation pass rate, a p95 latency and a per-call cost ceiling. `evaluate()` checks
one provider/model against it from:
  * a static capability table (structured output, vision, context) -- a model not in it is
    UNKNOWN on those checks, never assumed capable;
  * recorded evaluation results (`gateway.contract_eval` audit rows: passed/total) and
    recorded latencies (`gateway.contract_latency`: p95_s) -- absent is UNKNOWN;
  * the gateway's own estimate of one call's cost against the ceiling.
The verdict is PASS only when every check passes; FAIL when any fails; else UNKNOWN.

`failover.decide` consults it: a fallback from ANOTHER provider is only routed when its
contract verdict is PASS (UNKNOWN never counts as a pass). A stronger model of the SAME
provider (`failover.APPROVED_FALLBACKS`, a reviewed list) is still routed on that approval,
and its contract verdict is reported on the decision row so a gap is visible rather than
silent -- the remaining half of F-095 (measured quality and latency for those models) is open.
"""
from __future__ import annotations

EVAL_ACTION = "gateway.contract_eval"
LATENCY_ACTION = "gateway.contract_latency"
PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
MIN_EVAL_PASS_RATE = 0.90
MIN_EVAL_SAMPLES = 20
P95_LATENCY_S = {"cheap": 30.0, "standard": 60.0, "deep": 180.0}
COST_HEADROOM = 1.0

#: Published capabilities of the models the gateway can route to. A model absent here is
#: UNKNOWN on these checks.
CAPABILITIES: dict[str, dict] = {
    "claude-haiku-4-5": {"provider": "anthropic", "structured_output": True, "vision": True,
                         "context_tokens": 200_000},
    "claude-sonnet-5": {"provider": "anthropic", "structured_output": True, "vision": True,
                        "context_tokens": 200_000},
    "claude-opus-5": {"provider": "anthropic", "structured_output": True, "vision": True,
                      "context_tokens": 200_000},
}


def contract_for(task_key: str) -> dict:
    from . import anthropic, routing

    from . import failover

    task, tier = routing.route(task_key)
    # The cost bound: no fallback may cost more per call than the costliest route the
    # reviewed approval list already allows for this tier (its own model or the approved
    # stronger fallback) -- a cheaper cross-provider fallback passes, a pricier one fails.
    approved = (tier.model,) + tuple(failover.APPROVED_FALLBACKS.get(tier.key, ()))
    primary = max(anthropic.estimate_cad(m, input_tokens=task.typical_input_tokens,
                                         output_tokens=task.max_output_tokens)
                  for m in approved)
    return {"task": task_key, "tier": tier.key, "structured_output": True,
            "vision": bool(tier.vision),
            "min_context_tokens": 2 * (task.typical_input_tokens + task.max_output_tokens),
            "min_eval_pass_rate": MIN_EVAL_PASS_RATE, "min_eval_samples": MIN_EVAL_SAMPLES,
            "max_p95_latency_s": P95_LATENCY_S.get(tier.key, 60.0),
            "max_cad_per_call": round(primary * COST_HEADROOM, 6)}


def _latest(db, action: str, provider: str, model: str, tier: str) -> dict | None:
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    with db.session() as s:
        for row in s.scalars(select(AuditLog).where(AuditLog.action == action)
                             .order_by(desc(AuditLog.id)).limit(500)):
            d = row.detail or {}
            if (d.get("provider"), d.get("model"), d.get("tier")) == (provider, model, tier):
                return d
    return None


def record_eval(db, *, provider: str, model: str, tier: str, passed: int, total: int,
                source: str) -> None:
    """Record a golden-task evaluation of a model for a tier (e.g. gateway/evals.py runs)."""
    from ..core.models import AuditLog

    if total <= 0 or not 0 <= passed <= total or not source.strip():
        raise ValueError("an evaluation names its source and 0 <= passed <= total, total > 0")
    with db.session() as s:
        s.add(AuditLog(actor="gateway", action=EVAL_ACTION,
                       detail={"provider": provider, "model": model, "tier": tier,
                               "passed": passed, "total": total, "source": source}))


def record_latency(db, *, provider: str, model: str, tier: str, p95_s: float,
                   samples: int) -> None:
    from ..core.models import AuditLog

    if samples <= 0 or p95_s < 0:
        raise ValueError("a latency reading has samples > 0 and p95 >= 0")
    with db.session() as s:
        s.add(AuditLog(actor="gateway", action=LATENCY_ACTION,
                       detail={"provider": provider, "model": model, "tier": tier,
                               "p95_s": p95_s, "samples": samples}))


def evaluate(db, *, provider: str, model: str, task_key: str) -> dict:
    from . import anthropic

    c = contract_for(task_key)
    cap = CAPABILITIES.get(model)
    checks: dict[str, dict] = {}

    def put(name, verdict, why):
        checks[name] = {"verdict": verdict, "why": why}

    if cap is None or cap.get("provider") != provider:
        for k in ("structured_output", "vision", "context"):
            put(k, UNKNOWN, f"{provider}:{model} is not in the capability table")
    else:
        put("structured_output", PASS if cap["structured_output"] else FAIL,
            "published capability")
        put("vision", PASS if (cap["vision"] or not c["vision"]) else FAIL,
            "vision required" if c["vision"] else "vision not required")
        put("context", PASS if cap["context_tokens"] >= c["min_context_tokens"] else FAIL,
            f"{cap['context_tokens']} vs {c['min_context_tokens']} tokens")
    ev = _latest(db, EVAL_ACTION, provider, model, c["tier"])
    if ev is None or int(ev.get("total") or 0) < MIN_EVAL_SAMPLES:
        put("quality", UNKNOWN, f"fewer than {MIN_EVAL_SAMPLES} recorded golden-task "
                                "evaluations for this tier")
    else:
        rate = ev["passed"] / ev["total"]
        put("quality", PASS if rate >= MIN_EVAL_PASS_RATE else FAIL,
            f"{rate:.0%} of {ev['total']} ({ev.get('source')})")
    lat = _latest(db, LATENCY_ACTION, provider, model, c["tier"])
    if lat is None:
        put("latency", UNKNOWN, "no recorded latency for this tier")
    else:
        put("latency", PASS if float(lat["p95_s"]) <= c["max_p95_latency_s"] else FAIL,
            f"p95 {lat['p95_s']}s vs {c['max_p95_latency_s']}s")
    if provider == "anthropic" and model in anthropic.PRICES_USD_PER_MTOK:
        from . import routing

        task, _tier = routing.route(task_key)
        est = anthropic.estimate_cad(model, input_tokens=task.typical_input_tokens,
                                     output_tokens=task.max_output_tokens)
        put("cost", PASS if est <= c["max_cad_per_call"] else FAIL,
            f"CA${est:.4f} vs CA${c['max_cad_per_call']:.4f} per call")
    else:
        put("cost", UNKNOWN, "no price for this provider/model in the gateway's tables")
    verdicts = {v["verdict"] for v in checks.values()}
    verdict = FAIL if FAIL in verdicts else UNKNOWN if UNKNOWN in verdicts else PASS
    return {"provider": provider, "model": model, "contract": c, "checks": checks,
            "verdict": verdict}


def may_route(db, *, provider: str, primary_provider: str, model: str, task_key: str) -> dict:
    """Whether failover may route this fallback. Cross-provider: only on PASS."""
    ev = evaluate(db, provider=provider, model=model, task_key=task_key)
    if provider != primary_provider:
        return {"allowed": ev["verdict"] == PASS, "basis": "contract", "contract": ev}
    return {"allowed": ev["verdict"] != FAIL, "basis": "same-provider approved fallback "
            "(failover.APPROVED_FALLBACKS); contract reported, quality/latency may be UNKNOWN",
            "contract": ev}
