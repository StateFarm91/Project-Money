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
silent -- except on a GATE task (W4-C03), where any fallback needs a full PASS. The measured
quality and latency come from recorded golden evaluations or from `failover_drill` (F-097).
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
#: Built from the routing table (the one place a model is named), so a tier's model change
#: carries its capability record with it rather than leaving a stale literal here.
def _capabilities() -> dict[str, dict]:
    from .routing import TIERS

    return {t.model: {"provider": "anthropic", "structured_output": True,
                      "vision": bool(t.vision), "context_tokens": 200_000}
            for t in TIERS.values()}


CAPABILITIES: dict[str, dict] = _capabilities()


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


#: W4-C03 (F-095 remainder): tasks whose answer satisfies a gate -- a release, a truth check,
#: or the choice every later render goes through. A fallback stands in for one of these only
#: on a PASS of the whole contract, whichever provider it is from: a same-provider model whose
#: quality or latency is UNKNOWN has not shown it can satisfy the gate, and a stronger model is
#: not a measured one. Every other task keeps the reviewed same-provider approval below.
GATE_TASKS: dict[str, str] = {
    "asset_inspection": "the physical-realism and caption-truth judgement a release waits on "
                        "(#61, #79)",
    "benchmark_challenge": "the release-blocking blinded benchmark comparison (#315)",
    "creative_evaluation": "the desirability gate a concept must pass to be built (#218)",
    "image_benchmark_judging": "chooses the image provider every listing image renders "
                               "through afterwards",
}


def is_gate_task(task_key: str) -> bool:
    return task_key in GATE_TASKS


def may_route(db, *, provider: str, primary_provider: str, model: str, task_key: str) -> dict:
    """Whether failover may route this fallback. Cross-provider or gate task: only on PASS."""
    ev = evaluate(db, provider=provider, model=model, task_key=task_key)
    if provider != primary_provider:
        return {"allowed": ev["verdict"] == PASS, "basis": "contract", "contract": ev}
    if is_gate_task(task_key):
        unmet = sorted(k for k, v in ev["checks"].items() if v["verdict"] != PASS)
        return {"allowed": ev["verdict"] == PASS,
                "basis": (f"gate task ({GATE_TASKS[task_key]}): a fallback satisfies it only "
                          f"on a full contract PASS" + (f"; not yet PASS: {unmet}" if unmet
                                                        else "")),
                "contract": ev}
    return {"allowed": ev["verdict"] != FAIL, "basis": "same-provider approved fallback "
            "(failover.APPROVED_FALLBACKS); contract reported, quality/latency may be UNKNOWN",
            "contract": ev}


# ---- F-097 Shadow Failover Drill ------------------------------------------------------------
#
# F-097: "Once a fallback exists, periodically route safe sampled work through it and compare
# quality/cost/latency." A drill is two paid calls per sampled item, so it is OFF unless
# `BRAMBLELOOP_FAILOVER_DRILL=1`, and even then it runs only on a task that is safe to sample
# (never a gate task, never Laura's owner-facing or private register), only with a fallback the
# reviewed list or a configured provider supplies, and only for a fallback whose contract has
# not FAILED. The caller hands the drill its `call(provider, model, item)`; the drill never
# builds a model client of its own.
#
# What it measures is the fallback against the primary on the same items: agreement of the
# structured answer (every key the primary returned, equal in the fallback's answer), cost per
# call and p95 latency. The fallback's latency and its agreement become the contract's recorded
# latency and evaluation rows -- the measured quality and latency F-095 said were missing --
# labelled with their source. A cross-provider drill is also F-093's evidence row
# (`scale.dependency.FALLBACK_DRILL_ACTION`); a same-provider drill never is, because a second
# model of the same provider does not survive that provider's outage.

DRILL_SWITCH = "BRAMBLELOOP_FAILOVER_DRILL"
DRILL_ACTION = "gateway.failover_drill"
DRILL_SAMPLE_RATE = 0.10
DRILL_MAX_ITEMS = 10
UNSAFE_PREFIXES = ("laura.",)


def drill_enabled() -> bool:
    import os

    return os.environ.get(DRILL_SWITCH, "").strip() == "1"


def drill_safe(task_key: str) -> tuple[bool, str]:
    from . import routing

    try:
        routing.route(task_key)
    except Exception as exc:  # noqa: BLE001 - an undeclared or compiler task is not sampled
        return False, str(exc)[:200]
    if is_gate_task(task_key):
        return False, f"{task_key} satisfies a gate ({GATE_TASKS[task_key]}); never sampled"
    if task_key.startswith(UNSAFE_PREFIXES):
        return False, f"{task_key} is owner-facing; never sampled"
    return True, "safe: extraction or judgement that no gate reads directly"


def _sampled(items: list[dict], rate: float, limit: int) -> list[dict]:
    """Deterministic sample: an item is in when its id hashes below the rate."""
    import hashlib

    out = []
    for it in items:
        h = int(hashlib.sha256(str(it.get("id")).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if h < rate:
            out.append(it)
    return out[:limit]


def _p95(values: list[float]) -> float:
    v = sorted(values)
    return v[max(0, min(len(v) - 1, int(round(0.95 * (len(v) - 1)))))]


def failover_drill(db, *, task_key: str, items: list[dict], call, fallback_model: str = "",
                   fallback_provider: str = "anthropic", primary_provider: str = "anthropic",
                   rate: float = DRILL_SAMPLE_RATE, limit: int = DRILL_MAX_ITEMS,
                   enabled: bool | None = None) -> dict:
    """Route sampled safe work through the fallback beside the primary, and compare."""
    from ..core.models import AuditLog
    from . import failover, routing

    on = drill_enabled() if enabled is None else bool(enabled)
    if not on:
        return {"ran": False, "task": task_key,
                "why": f"{DRILL_SWITCH} is off: a drill is paid calls, so it runs only when "
                       f"switched on"}
    ok, why = drill_safe(task_key)
    if not ok:
        return {"ran": False, "task": task_key, "why": why}
    _task, tier = routing.route(task_key)
    fallback = fallback_model or next(iter(failover.APPROVED_FALLBACKS.get(tier.key, ())), "")
    if not fallback:
        return {"ran": False, "task": task_key,
                "why": f"no fallback exists for the {tier.key} tier; there is nothing to drill"}
    before = evaluate(db, provider=fallback_provider, model=fallback, task_key=task_key)
    if before["verdict"] == FAIL:
        return {"ran": False, "task": task_key, "fallback": fallback,
                "why": "the fallback already FAILS its contract; it is not routed, not drilled"}
    picked = _sampled(items, rate, limit)
    if not picked:
        return {"ran": False, "task": task_key, "fallback": fallback,
                "why": f"none of {len(items)} item(s) fell in the {rate:.0%} sample"}
    agree, rows = 0, []
    cost = {"primary": 0.0, "fallback": 0.0}
    lat: dict[str, list[float]] = {"primary": [], "fallback": []}
    for it in picked:
        p = call(primary_provider, tier.model, it)
        f = call(fallback_provider, fallback, it)
        po, fo = dict(p.get("output") or {}), dict(f.get("output") or {})
        same = bool(po) and all(fo.get(k) == v for k, v in po.items())
        agree += int(same)
        for side, r in (("primary", p), ("fallback", f)):
            cost[side] += float(r.get("cost_cad") or 0.0)
            lat[side].append(float(r.get("latency_s") or 0.0))
        rows.append({"item": it.get("id"), "agree": same,
                     "differs_on": sorted(k for k, v in po.items() if fo.get(k) != v)[:10]})
    n = len(picked)
    contract = contract_for(task_key)
    p95_f = round(_p95(lat["fallback"]), 4)
    per_call_f = round(cost["fallback"] / n, 6)
    comparison = {
        "quality": {"agreement": round(agree / n, 4), "agreeing": agree, "items": n,
                    "basis": "fallback answer equals the primary's on every key it returned"},
        "cost_cad_per_call": {"primary": round(cost["primary"] / n, 6), "fallback": per_call_f},
        "p95_latency_s": {"primary": round(_p95(lat["primary"]), 4), "fallback": p95_f}}
    passed = (agree / n >= MIN_EVAL_PASS_RATE and p95_f <= contract["max_p95_latency_s"]
              and per_call_f <= contract["max_cad_per_call"])
    source = f"{DRILL_ACTION}:{task_key}:agreement-with-{tier.model}"
    record_latency(db, provider=fallback_provider, model=fallback, tier=tier.key, p95_s=p95_f,
                   samples=n)
    record_eval(db, provider=fallback_provider, model=fallback, tier=tier.key, passed=agree,
                total=n, source=source)
    detail = {"task": task_key, "tier": tier.key, "primary": f"{primary_provider}:{tier.model}",
              "fallback": f"{fallback_provider}:{fallback}", "sampled": n,
              "of": len(items), "rate": rate, "comparison": comparison, "passed": passed,
              "items": rows}
    with db.session() as s:
        s.add(AuditLog(actor="gateway", action=DRILL_ACTION, artifact=task_key[:200],
                       detail=detail))
        if fallback_provider != primary_provider:
            from ..scale import dependency

            s.add(AuditLog(actor="gateway", action=dependency.FALLBACK_DRILL_ACTION,
                           detail={"passed": passed, "workload": "judgement_vision",
                                   "task": task_key, "fallback": detail["fallback"]}))
    after = evaluate(db, provider=fallback_provider, model=fallback, task_key=task_key)
    return {"ran": True, **detail, "contract_before": before["verdict"],
            "contract_after": after["verdict"],
            "counts_for_provider_dependency": fallback_provider != primary_provider}
