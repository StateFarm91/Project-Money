"""Model synthesis of Laura's CEO briefing, through the existing gateway (W4-LAURA1).

`laura.agency.briefing` builds the evidence pack and the deterministic briefing in code. This
module only asks a model to *write* the briefing from that pack, and only when every existing
money control says the call may be made:

1. Laura's own daily permission (`agents.registry` row `laura`). A permission of CA$0.00 --
   the declared value until the owner authorises one -- means **no call**: it is refused here,
   before any reservation, and the refusal is written to the audit log like every other
   (`spend_report.record_refusal`). The gateway's generic path reads a zero permission as "no
   per-agent check" and only refuses *after* billing, so Laura's path refuses first.
2. A configured provider (an API key in the environment) unless a test injects a transport.
3. `failover.gateway_for` -> `decide`: the month's ceiling and the agent's remaining day, per
   candidate model, before a gateway is built (PARK otherwise).
4. `ModelGateway.complete_json` -> `anthropic.check_budget_cad`: month + provider + agent day
   + reservation, atomically, before the request; billing through the single `_record` path.

Any refusal or failure returns `{"source": "unavailable", "reason": ...}` and the caller shows
the deterministic briefing with that reason stated. Nothing here raises for money, health or
a missing provider, and nothing here sets, raises or works around a ceiling.
"""
from __future__ import annotations

import json
import math

from . import prompts, routing

TASK = "laura.ceo_briefing"
AGENT = "laura"          # Laura's canonical registry agent: her own daily permission binds

PROMPT = prompts.register(prompts.Prompt(
    name=TASK, version="1",
    system=(
        "You are writing as Laura, the AI Founder/CEO of Brambleloop, a crochet pattern "
        "studio, briefing its owner. Voice: warm, plain, decisive, first person, brief. You "
        "are an AI; never say or imply you are human, did anything physical, or own anything "
        "legally.\n"
        "Grounding rules, which are checked by code and anything breaking them is deleted:\n"
        "1. Use ONLY the evidence pack. Every item you write must cite one or more evidence "
        "ids (E#) or proposal ids (P#) in its \"evidence\" list. An item with no valid id is "
        "removed.\n"
        "2. Never introduce a number, amount, date or name that is not in the evidence you "
        "cite. Do not number your items; code numbers them.\n"
        "3. Evidence marked UNKNOWN stays UNKNOWN: say it is unknown, never estimate it and "
        "never present it as zero.\n"
        "4. Owner decisions: write one item per decision id given, in the given rank order; "
        "each cites exactly that decision's id. Do not add, drop or reorder decisions.\n"
        "5. What you will do on your own: only the listed proposals of kind 'mission' or "
        "work already in progress. Publishing, activating listings, pricing, spending, ads "
        "and customer messages are never yours to do; they are owner decisions.\n"
        "6. Answer only the requested components, in the requested order, prioritised, at "
        "most five items each (decisions: exactly the given count). Concise: each item one "
        "or two sentences.\n"
        "Reply with JSON only."),
    template=(
        "Owner's question:\n{question}\n\n"
        "Requested components, in order: {components}\n"
        "Time window: last {window_hours} hours. Decisions requested: {decisions_n}.\n\n"
        "Ranked owner decisions (cite these ids, in this order):\n{decisions}\n\n"
        "Proposals (P#):\n{proposals}\n\n"
        "Evidence pack (id | components | status | as_of | source | statement):\n{evidence}\n\n"
        "JSON: {{\"sections\": [{{\"component\": \"<one of the requested components>\", "
        "\"items\": [{{\"text\": \"...\", \"evidence\": [\"E1\"]}}]}}]}}"),
    output_schema=("sections",),
    max_output_tokens=routing.TASKS[TASK].max_output_tokens))


def render_values(*, question: str, components: list[str], window_hours: int,
                  decisions_n: int, pack: list[dict], decisions: list[dict],
                  proposals: list[dict]) -> dict:
    """The template values. Public so the cost estimate measures the real prompt."""
    ev_lines = [f"{e['id']} | {','.join(e.get('components') or [])} | {e['status']} | "
                f"{e.get('as_of') or 'UNKNOWN'} | {e['source']} | {e['statement']}"
                for e in pack]
    dec_lines = [f"rank {d['rank']}: {d['evidence_id']} -- {d['statement']}" for d in decisions]
    prop_lines = [f"{p['pid']} ({p['kind']}, {p['department']}, {p['job_type']}): "
                  f"{p['title']} -- {p['why']}" for p in proposals]
    return {"question": question, "components": ", ".join(components),
            "window_hours": str(window_hours), "decisions_n": str(decisions_n),
            "decisions": "\n".join(dec_lines) or "(none open)",
            "proposals": "\n".join(prop_lines) or "(none)",
            "evidence": "\n".join(ev_lines) or "(empty)"}


def laura_daily_permission(db, registry=None) -> float:
    """Laura's authorised daily model permission in CAD (0.0 when none is authorised)."""
    if registry is None:
        from ..agents.registry import Registry

        registry = Registry(db)
    try:
        ceiling = float(registry.get(AGENT).daily_cost_ceiling_cad or 0.0)
    except Exception:  # noqa: BLE001 - no agent row: nothing is authorised
        return 0.0
    return ceiling if math.isfinite(ceiling) and ceiling > 0 else 0.0


def synthesize(db, *, values: dict, registry=None, provider_factory=None) -> dict:
    """{source: model|unavailable, data, reason, cost_cad, model}. Never raises."""
    from ..agents.registry import BudgetExceeded, PermissionDenied
    from ..finance import spend_report
    from .failover import Parked, gateway_for
    from .model_gateway import NoProviderAvailable, available_providers

    def unavailable(reason: str, cost: float = 0.0) -> dict:
        return {"source": "unavailable", "data": None, "reason": reason, "cost_cad": cost,
                "model": None}

    if registry is None:
        from ..agents.registry import Registry

        registry = Registry(db)
    permission = laura_daily_permission(db, registry)
    if permission <= 0:
        why = ("laura has no authorised daily model budget (daily ceiling CA$0.00); "
               "authorising one is an owner decision")
        try:
            estimate = routing.estimate_cad(TASK)
        except Exception:  # noqa: BLE001
            estimate = 0.0
        spend_report.record_refusal(
            db, agent=AGENT, ceiling_cad=0.0, estimate_cad=estimate, committed_cad=0.0,
            which="agent_daily_ceiling_unset", why=why, purpose=PROMPT.ref)
        return unavailable(why)
    if provider_factory is None and "anthropic" not in available_providers():
        return unavailable("no model provider is configured in this environment (no API key)")
    try:
        gateway, decision = gateway_for(db, TASK, registry=registry, agent=AGENT,
                                        payload=None, provider_factory=provider_factory)
    except Parked as exc:
        return unavailable(f"parked by the spend controls: {exc}"[:300])
    except routing.TaskRefused as exc:
        return unavailable(f"task refused: {exc}"[:300])
    except NoProviderAvailable as exc:
        return unavailable(f"no provider: {exc}"[:300])
    except Exception as exc:  # noqa: BLE001
        return unavailable(f"gateway unavailable ({type(exc).__name__})")
    if gateway is None:      # not cacheable; defensive
        return unavailable("no gateway was built for this call")
    try:
        data = gateway.complete_json(PROMPT.ref, agent=AGENT, values=values,
                                     max_attempts_per_provider=1)
    except NoProviderAvailable as exc:
        return unavailable(f"no provider: {exc}"[:300], gateway.spend_cad())
    except (BudgetExceeded, PermissionDenied, PermissionError) as exc:
        return unavailable(f"refused by the spend controls: {exc}"[:300], gateway.spend_cad())
    except Exception as exc:  # noqa: BLE001 - provider error / malformed output (billed if paid)
        return unavailable(f"model call failed ({type(exc).__name__})", gateway.spend_cad())
    meta = data.pop("_meta", {}) or {}
    return {"source": "model", "data": data, "reason": decision.reason,
            "cost_cad": float(meta.get("cost_cad") or 0.0),
            "model": f"{meta.get('provider')}/{meta.get('model')}",
            "prompt_sha256": meta.get("prompt_sha256")}


def estimate(values: dict, model: str | None = None) -> dict:
    """The gateway's own padded estimate for one briefing with these template values."""
    from . import anthropic as gw

    task, tier = routing.route(TASK)
    model = model or tier.model
    user = PROMPT.render(**values)
    in_tok = (len(PROMPT.system) + len(user)) // 4
    out_tok = int(PROMPT.max_output_tokens)
    return {"model": model, "input_tokens": in_tok, "max_output_tokens": out_tok,
            "estimate_cad_padded": gw.estimate_cad(model, input_tokens=in_tok,
                                                   output_tokens=out_tok),
            "padding": gw.ESTIMATE_PADDING}
