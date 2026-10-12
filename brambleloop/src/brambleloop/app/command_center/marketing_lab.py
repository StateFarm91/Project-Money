"""F-684 Marketing Laboratory: every growth channel and every experiment, one rule set each.

Criterion (registry F-684, quoted): "organic/paid growth, Share & Save, Offsite Ads, social,
seasonal campaigns and experiments with hypothesis, baseline, budget, attribution and
stop/scale rules."

Two read-only sections for the Insights tab:

* ``channels(db)`` -- one flat row per channel the criterion names (organic, paid / Etsy Ads,
  Share & Save, Offsite Ads, social / Pinterest, seasonal campaigns), each stating its state,
  hypothesis, baseline, budget, attribution rule, stop rule and scale rule. Rules are read from
  the modules that enforce them (`commerce.paid_media`, `growth.ads_readiness`,
  `growth.pins`, `seasonal.calendar`, `runtime.growth_ops`), never restated as constants here.
* ``experiments(db)`` -- one flat row per registered experiment with the same six fields.
  A baseline that was never measured is UNKNOWN, never 0; an attribution never measured says
  UNMEASURED.

Nothing here can spend, schedule or post: no campaign exists, `paid_media.authorise_spend`
refuses outside production without the owner's grant, and this module calls none of it.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from .providers import envelope

UNKNOWN = "UNKNOWN"


def _live_listings(db) -> int:
    from ...core.models import Listing

    with db.session() as s:
        return int(s.scalar(select(func.count()).select_from(Listing).where(
            Listing.state == "active", Listing.etsy_listing_id.is_not(None))) or 0)


def _caps_text(caps) -> str:
    return (f"CA${caps.daily_cad:.2f}/day, CA${caps.campaign_cad:.2f}/campaign, "
            f"CA${caps.monthly_cad:.2f}/month (hard caps, enforced before spend)")


# The criterion's six fields lead every row, so the Command Center's row renderer (which
# shows the first six facts) always shows all of them.
CRITERION_FIELDS = ("hypothesis", "baseline", "budget", "attribution", "stop_rule",
                    "scale_rule")


def _ordered(row: dict, title_key: str) -> dict:
    lead = [title_key] + [k for k in CRITERION_FIELDS if k in row]
    return {**{k: row[k] for k in lead}, **{k: v for k, v in row.items() if k not in lead}}


def channels(db, *, now: datetime | None = None) -> dict:
    from ...commerce import paid_media as pm
    from ...growth import ads_readiness as ar
    from ...growth import pins
    from ...seasonal import calendar

    now = now or datetime.now(timezone.utc)
    live = _live_listings(db)
    caps = pm.CONSERVATIVE_CAPS
    econ = pm.economics_state()
    terms = pm.offsite_ads_terms()
    ads = ar.summary(db)
    authorised = bool(ads.get("activation_authorised"))
    roas = ((ads.get("kpis") or {}).get("roas") or {}) if isinstance(ads.get("kpis"), dict) else {}
    roas_value = roas.get("contribution_roas") if isinstance(roas, dict) else None
    no_traffic = ("no live listing" if live == 0 else
                  f"{live} live listing(s); no measured baseline yet")
    floors = econ["organic_first"]["floors"]
    sns = econ["share_and_save"]
    pin_state = pins.state()
    cal = calendar.rolling(now.date())
    nxt = cal.get("next_event") or {}
    upcoming = ", ".join(f"{e['event']} in {e['days_away']} d" for e in (cal.get("events") or [])[:3])

    rows = [
        {"channel": "organic", "label": "Organic marketplace search",
         "state": "NOT_LIVE" if live == 0 else "MEASURING",
         "hypothesis": "a listing earns its traffic organically before any paid scale is read",
         "baseline": UNKNOWN, "why": no_traffic,
         "budget": "none (no spend)",
         "attribution": "orders whose acquisition_source is organic (finance.sources.channel)",
         "stop_rule": ("a weak organic conversion is not hidden behind paid traffic "
                       "(paid_media.organic_first_gate)"),
         "scale_rule": (f"paid scale may be read only after {floors['days']} organic days and "
                        f"{floors['visits']} organic visits"),
         "source": "commerce.paid_media.organic_first_gate"},
        {"channel": "paid", "label": "Paid growth (Etsy Ads)",
         "state": "ACTIVE" if authorised else "GATED",
         "gate": None if authorised else "owner: ad budget authority (paid_media)",
         "hypothesis": (f"ads return at least {caps.target_contribution_ratio:.2f}x "
                        f"contribution per ad dollar"),
         "baseline": UNKNOWN if roas_value is None else roas_value,
         "why": (roas.get("why") if isinstance(roas, dict) and roas.get("why")
                          else "attributed ROAS needs measured ad spend and attributed orders"),
         "budget": _caps_text(caps),
         "attribution": ("evidence-attributed Etsy Ads orders only "
                         "(growth.ads_readiness.attributed_roas)"),
         "stop_rule": (f"pause on CAC above CA${caps.max_cac_cad:.2f}, test loss "
                       f"CA${caps.max_test_loss_cad:.2f}, refund rate above "
                       f"{pm.REFUND_RATE_ALARM:.0%}, tracking failure or unavailable listing"),
         "scale_rule": (f"scale only after {caps.min_clicks_before_judging} clicks and "
                        f"{caps.min_conversions_before_scaling} conversions at target "
                        f"contribution (paid_media.may_scale)"),
         "proposals": (ads.get("proposals") or {}).get("total"),
         "spend_executed_cad": ads.get("spend_executed_cad"),
         "source": "commerce.paid_media.CONSERVATIVE_CAPS; growth.ads_readiness.summary"},
        {"channel": "share_and_save", "label": "Share & Save",
         "state": "UNMEASURED" if not sns.get("measurable") else "MEASURED",
         "hypothesis": ("qualified traffic sent through the shop's own trackable links "
                        "contributes more than ordinary marketplace acquisition"),
         "baseline": UNKNOWN, "why": sns.get("why") or no_traffic,
         "budget": "none (fee benefit, no spend)",
         "attribution": "orders arriving through eligible trackable links",
         "stop_rule": "drop a link source whose net contribution trails ordinary acquisition",
         "scale_rule": ("compare on net contribution after the official fee benefit; no rate "
                        "is assumed (paid_media.share_and_save)"),
         "source": "commerce.paid_media.share_and_save"},
        {"channel": "offsite_ads", "label": "Offsite Ads",
         "state": "TERMS_READ",
         "hypothesis": "offsite-attributed orders remain contribution-positive after the fee",
         "baseline": UNKNOWN, "why": no_traffic,
         "budget": (f"no budget: a fee of {terms['standard_fee_rate']:.0%} "
                    f"({terms['reduced_fee_rate']:.0%} reduced) per attributed order, capped "
                    f"at US${terms['fee_cap_usd']:.0f}"),
         "attribution": (f"Etsy attributes an order within "
                         f"{terms['attribution_window_days']} days of an offsite ad click"),
         "stop_rule": ("opt out while the fee makes attributed orders contribution-negative "
                       "(only possible below the sales threshold)"),
         "scale_rule": (f"participation becomes mandatory above US${terms['threshold_usd']:,.0f}"
                        f" trailing sales" if terms["mandatory_above_threshold"] else
                        "participation is optional"),
         "source": (f"gates.policy_knowledge advertising_rules (read "
                    f"{terms['source']['read_on']})")},
        {"channel": "social", "label": "Social (Pinterest)",
         "state": "GATED",
         "gate": "image capability and a landable destination (growth.pins.cannot_do_yet)",
         "hypothesis": ("several genuinely distinct pin angles per product earn saves that "
                        "lead to the listing"),
         "baseline": UNKNOWN, "why": pin_state["cannot_do_yet"]["attribution"],
         "budget": "none (organic posting; no promoted pins)",
         "attribution": "clicks to the pin's own landing destination",
         "stop_rule": (f"a set with fewer than {pin_state['min_angles']} distinct angles is "
                       f"refused as duplicate-pin spam"),
         "scale_rule": "amplify a winning angle with new angles, never re-posts (pins.amplify)",
         "source": "growth.pins.state"},
        {"channel": "seasonal", "label": "Seasonal campaigns",
         "state": "PLANNED" if nxt else UNKNOWN,
         "next_event": nxt.get("event"), "next_event_days": nxt.get("days_away"),
         "hypothesis": ("seasonal products learn CTR, conversion and CAC before peak demand, "
                        "not during it"),
         "baseline": UNKNOWN, "why": no_traffic,
         "budget": "within the paid caps above, only inside the learning window",
         "attribution": "as paid and organic, per seasonal product",
         "stop_rule": "no paid learning after the promotional ramp (late_for_learning)",
         "scale_rule": ("paid learning opens at the indexing milestone and must run by the "
                        "promotional ramp (growth_ops._learning_window, #294)"),
         "upcoming": upcoming or UNKNOWN,
         "source": "seasonal.calendar.rolling; runtime.growth_ops._learning_window"},
    ]
    rows = [_ordered(r, "label") for r in rows]
    return envelope("OK", rows,
                    ["commerce.paid_media", "growth.ads_readiness", "growth.pins",
                     "seasonal.calendar", "listings"],
                    basis="measured", provider="command_center.marketing_lab.channels",
                    as_of=now.isoformat(), can_spend=False,
                    note=("rules are read from the modules that enforce them; nothing here "
                          "can spend, schedule or post"))


def _rule(metric: str, higher: bool, threshold: float, sample: int, stop: bool) -> str:
    if stop:
        op = "<=" if higher else ">="
        return f"stop when {metric} {op} {threshold:g} after {sample} sample(s)"
    op = ">=" if higher else "<="
    return f"retain/scale when {metric} {op} {threshold:g} after {sample} sample(s)"


def experiments(db) -> dict:
    from ...core.models import RegisteredExperiment

    with db.session() as s:
        rows = list(s.scalars(select(RegisteredExperiment).order_by(
            RegisteredExperiment.id.desc()).limit(200)))
        items = []
        for r in rows:
            d = dict(r.detail or {})
            baseline = d.get("baseline")
            effect = d.get("measured_effect")
            items.append({
                "title": f"{r.product_slug or 'shop'}: {r.key}",
                "key": r.key, "product": r.product_slug or "(shop)", "state": r.state,
                "channel": d.get("channel") or r.design or UNKNOWN,
                "hypothesis": r.hypothesis or UNKNOWN,
                "metric": r.metric or UNKNOWN,
                "baseline": baseline if isinstance(baseline, (int, float)) else UNKNOWN,
                "budget": f"CA${float(r.cost_cad or 0.0):.2f} registered cost",
                "attribution": (f"measured effect {effect}" if isinstance(effect, (int, float))
                                else "UNMEASURED: no observation attributed yet"
                                if r.observed is None else f"observed {r.observed:g} "
                                f"over {r.sample} sample(s)"),
                "decision": d.get("retain_or_rollback") or r.decision or "UNDECIDED",
                "stop_rule": _rule(r.metric, r.higher_is_better, r.failure_threshold,
                                   r.minimum_sample, True),
                "scale_rule": _rule(r.metric, r.higher_is_better, r.success_threshold,
                                    r.minimum_sample, False),
                "gated_on": r.gated_on or None,
                "source": f"registered_experiments:{r.id}"})
            items[-1] = _ordered(items[-1], "title")
    status = "OK" if items else "UNKNOWN"
    return envelope(status, items, ["registered_experiments"],
                    basis="measured" if items else "unknown",
                    provider="command_center.marketing_lab.experiments",
                    reason=None if items else "no experiment is registered")
