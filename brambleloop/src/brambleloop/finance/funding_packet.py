"""F-871 / F-100: a funding request is a prepared packet, never a bare "add credit" ask.

F-871: "Model/vision credit is owner financial authority; bounded experiment and max spend are
prepared first." F-100: "Funding/connecting another provider requires owner approval backed by
measured resilience value."

Both asks used to be prose on an owner card (OWNER_ACTIONS `fund_model`; nothing at all for a
second provider). This module builds them as one standard, deterministic record from rows the
runtime wrote -- the cost ledger, the model probes, the parked model jobs and the funding
exhaustion events -- so the owner reads the evidence and the bound before deciding:

  * `credit_packet(db, provider)`: the bounded experiment (what the credit buys, read from the
    month's ledgered spend by purpose), the maximum spend (the monthly ceiling the gateway
    enforces before every call, and the remaining headroom), the measured run rate, and the
    balance-exhaustion events that prompted it;
  * `diversification_packet(db)`: the measured resilience value of a second provider -- the
    provider concentration from `scale.dependency` (holders, share, verdict), and the outage
    cost actually observed: failed probes, model jobs parked for the provider, and funding
    exhaustion events over the window -- with a one-off bounded experiment and its ceiling.

Nothing here spends, sets a key, contacts a provider or approves itself: approval stays the
owner's act (setting the provider's key in the hosting environment after reading the packet).
An unmeasured figure is null with the reason, never 0. Read-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

WINDOW_DAYS = 30
DIVERSIFICATION_EXPERIMENT_CAD = 10.0   # one-off, bounded: a second provider's trial calls


def _aware(v):
    if v is None:
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _spend(db, since):
    from sqlalchemy import select

    from ..core.models import CostEntry

    by_provider: dict[str, float] = {}
    by_purpose: dict[str, dict[str, float]] = {}
    rows = 0
    with db.session() as s:
        for c in s.scalars(select(CostEntry).where(CostEntry.at >= since)):
            p = (c.provider or "").strip() or "unattributed"
            amt = float(c.amount_cad or 0.0)
            by_provider[p] = by_provider.get(p, 0.0) + amt
            purpose = (c.purpose or "").strip() or "unattributed"
            by_purpose.setdefault(p, {})[purpose] = by_purpose.setdefault(p, {}).get(
                purpose, 0.0) + amt
            rows += 1
    return rows, by_provider, by_purpose


def _audit(db, action, since):
    from sqlalchemy import select

    from ..core.models import AuditLog

    with db.session() as s:
        return [{"at": _aware(a.at), "detail": a.detail or {}} for a in s.scalars(
            select(AuditLog).where(AuditLog.action == action, AuditLog.at >= since)
            .order_by(AuditLog.id))]


def _outage(db, since, provider: str) -> dict:
    from ..ops import funding
    from ..runtime.worker import PARKED_ACTION

    probes = _audit(db, "model.probe", since)
    failed = [p for p in probes if not p["detail"].get("ok")]
    parked = _audit(db, PARKED_ACTION, since)
    exhausted = [e for e in _audit(db, funding.ACTION, since)
                 if provider in str(e["detail"].get("provider") or provider)]
    return {
        "probes": len(probes) if probes else None,
        "failed_probes": len(failed) if probes else None,
        "probe_failure_share": (round(len(failed) / len(probes), 4) if probes else None),
        "model_jobs_parked": len(parked),
        "funding_exhaustion_events": len(exhausted),
        "last_exhaustion_at": (exhausted[-1]["at"].isoformat() if exhausted else None),
        "why_null": (None if probes else "no model.probe row in the window: unmeasured, "
                                         "not healthy"),
    }


def credit_packet(db, provider: str = "anthropic", *, now: datetime | None = None) -> dict:
    """F-871: the prepared packet for topping up a provider's credit."""
    from ..gateway.anthropic import monthly_ceiling_cad, spent_this_month_cad

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    rows, by_provider, by_purpose = _spend(db, since)
    ceiling = float(monthly_ceiling_cad())
    month = float(spent_this_month_cad(db))
    spent = by_provider.get(provider)
    daily = round(spent / WINDOW_DAYS, 4) if spent is not None else None
    purposes = sorted((by_purpose.get(provider) or {}).items(), key=lambda kv: -kv[1])[:8]
    return {
        "kind": "brambleloop.funding_packet", "packet": "model_credit",
        "requirement": "F-871", "provider": provider, "as_of": now.isoformat(),
        "bounded_experiment": {
            "what_the_credit_buys": [{"purpose": k, "cad_30d": round(v, 4)} for k, v in purposes],
            "basis": f"cost_entries over {WINDOW_DAYS} days for provider {provider!r}",
        },
        "max_spend": {
            "monthly_ceiling_cad": ceiling,
            "spent_this_month_cad": round(month, 4),
            "headroom_cad": round(max(0.0, ceiling - month), 4),
            "enforced_by": ("gateway.anthropic.check_budget_cad: a call that would cross the "
                            "ceiling is refused before it is made; no override"),
        },
        "measured_run_rate_cad_per_day": daily,
        "run_rate_basis": (f"{rows} cost row(s) in {WINDOW_DAYS} days" if spent is not None
                           else f"no {provider} cost row in {WINDOW_DAYS} days: unmeasured"),
        "outage_evidence": _outage(db, since, provider),
        "owner_action": (f"Add credit to the {provider} account the API key belongs to, up to "
                         f"the monthly ceiling of CA${ceiling:.2f}; the gateway cannot spend "
                         "beyond it whatever the balance"),
        "approves_itself": False,
    }


def diversification_packet(db, *, now: datetime | None = None) -> dict:
    """F-100: the measured resilience value of funding/connecting a second model provider."""
    from ..gateway.model_gateway import available_providers
    from ..scale import dependency

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    axis = next((a for a in dependency.report(db)["axes"] if a["axis"] == "ai_provider"), {})
    incumbent = (available_providers() or [None])[0]
    outage = _outage(db, since, incumbent or "anthropic")
    measured = outage["probes"] is not None
    value = None
    if measured:
        value = {"probe_failure_share": outage["probe_failure_share"],
                 "model_jobs_parked": outage["model_jobs_parked"],
                 "funding_exhaustion_events": outage["funding_exhaustion_events"],
                 "reading": ("a second provider would have carried the parked work"
                             if outage["model_jobs_parked"] or outage["failed_probes"] else
                             "no outage observed in the window: the measured resilience value "
                             "of a second provider is currently low")}
    return {
        "kind": "brambleloop.funding_packet", "packet": "provider_diversification",
        "requirement": "F-100", "as_of": now.isoformat(),
        "configured_providers": available_providers(),
        "concentration": {k: axis.get(k) for k in ("holders", "verdict", "concentration",
                                                  "share", "why") if k in axis},
        "measured_resilience_value": value,
        "unmeasured_because": (None if measured else outage["why_null"]),
        "bounded_experiment": {
            "max_cost_cad": DIVERSIFICATION_EXPERIMENT_CAD, "one_off": True,
            "what": ("route the probe and one low-risk judging purpose to the second provider "
                     "for a week and compare failure share and cost per call with the "
                     "incumbent"),
        },
        # F-094 (W4-FMBATCH1): whether a measured reason justifies diversifying now.
        "trigger": _trigger(db, now),
        "owner_action": ("Decide whether to fund/connect a second model provider, reading the "
                         "measured value above; approval is setting that provider's key in "
                         "the hosting environment. Declining keeps the incumbent only"),
        "approves_itself": False,
    }


def _trigger(db, now):
    try:
        from ..scale import dependency

        return dependency.diversification_trigger(db, now=now)
    except Exception as exc:  # noqa: BLE001 - unknown, never "not triggered"
        return {"triggered": None, "error": f"{type(exc).__name__}"}


def packets(db) -> dict:
    out = {"as_of": datetime.now(timezone.utc).isoformat(), "packets": []}
    for fn in (lambda: credit_packet(db), lambda: diversification_packet(db)):
        try:
            out["packets"].append(fn())
        except Exception as exc:  # noqa: BLE001 - an unreadable packet is UNKNOWN, not skipped
            out["packets"].append({"state": "UNKNOWN",
                                   "why": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return out
