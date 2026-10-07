"""What the owner's provider accounts hold, kept apart from what this company may spend.

Two numbers were being confused on 2026-09-21 and they are not the same kind of thing:

**The internal budget** is a policy this system enforces on itself -- CA$100 a month across
models and images, checked before every call, with the spend ledger as its evidence. It is
this company's own restraint and it was not close to breached.

**The provider account balance** is money in somebody's account at Anthropic, OpenAI or
Black Forest Labs. When it runs out every call fails regardless of how much of the internal
budget is left, and nothing inside this system can fix it. The owner told the system it had
added US$10 to Anthropic and that the OpenAI organisation limit is US$50 with about US$10.08
used; those are facts about accounts this code cannot read.

So they are recorded separately and reconciled rather than merged. Three properties:

**Owner-reported is not observed.** A figure somebody typed is evidence of what they saw on
a dashboard, not a reading. Every row says which it is, and nothing here treats a reported
balance as a capability -- that is what the probe is for, and on the day this was written
the probe disagreed with the report.

**Our ledger is the other side of the reconciliation.** This system knows what it spent per
provider, in CAD, at assumed list prices. Comparing that against a dashboard figure is worth
doing precisely because the two can differ: other usage on the same account, or our price
assumptions being wrong, and both are worth knowing.

**A balance is never a budget.** Being told there is US$10 available is not authority to
spend US$10. The owner said so explicitly and the code says it back.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

ACTION = "ops.provider_account_reported"

OBSERVED = "observed"
REPORTED = "owner_reported"


@dataclass(frozen=True)
class AccountFact:
    """One thing the owner told this system about a provider account."""

    provider: str
    at: str
    kind: str          # "credit_added" | "limit" | "used"
    amount_usd: float
    note: str = ""

    def to_dict(self) -> dict:
        return {"provider": self.provider, "at": self.at, "kind": self.kind,
                "amount_usd": self.amount_usd, "source": REPORTED, "note": self.note}


# What the owner has reported, in the order reported. Held in code rather than in a table
# because it is a short, auditable list of statements a person made, and because a figure
# that arrives by conversation should be visible in the diff that recorded it.
REPORTED_FACTS: tuple[AccountFact, ...] = (
    AccountFact("anthropic", "2026-09-21", "credit_added", 10.0,
                "added after the balance was found spent at 19:21Z. Three probes at 20:03, "
                "21:11 and 21:28 UTC were still refused, so this one had not reached the "
                "key; the owner funded the account again and the 21:37:52 probe succeeded"),
    AccountFact("anthropic", "2026-09-21", "balance", 19.83,
                "organisation credits available, from the console at the owner's 21:3xZ "
                "reading. The 21:37:52 probe is the observed half: a real call with the "
                "credential Brambleloop uses, answered"),
    AccountFact("anthropic", "2026-09-21", "used", 20.17,
                "organisation spend this month, from the console"),
    AccountFact("openai", "2026-09-21", "limit", 50.0,
                "organisation spend limit shown in the account dashboard"),
    AccountFact("openai", "2026-09-21", "used", 10.08,
                "organisation spend to date shown in the account dashboard"),
    AccountFact("openai", "2026-09-21", "balance", 9.92,
                "API credit balance shown on the billing page at 2026-09-21 05:28 local"),
    AccountFact("openai", "2026-09-21", "auto_reload_off", 0.0,
                "auto-reload is OFF: at a zero balance every image render stops, with no "
                "warning and no retry that can fix it -- the same failure Anthropic had "
                "hours earlier, waiting on the other provider"),
)

# What one image costs, for the runway arithmetic. The measured figure from the live
# renders rather than a list price, and named as measured.
CAD_PER_IMAGE_OBSERVED = 0.0411

NOT_A_BUDGET = (
    "a provider balance is not authority to spend it. The owner's instruction is explicit: "
    "the additional credit does not supersede quality-first spend governance or the CA$100 "
    "monthly ceiling, and it is not permission to consume the balance"
)


def facts(provider: str = "") -> list[dict]:
    return [f.to_dict() for f in REPORTED_FACTS
            if not provider or f.provider == provider]


def our_spend_usd(db, provider: str) -> dict:
    """What this system's own ledger says it spent with one provider, converted to USD.

    Converted because the dashboards are in USD and the ledger is in CAD, and a
    reconciliation that compares two currencies is not one. The conversion is the same
    assumed rate the ceiling uses, and it is named as assumed here too.
    """
    from sqlalchemy import select

    from ..core.models import CostEntry
    from ..gateway.routing import USD_PER_CAD

    with db.session() as s:
        rows = [r for r in s.scalars(select(CostEntry))
                if (getattr(r, "provider", "") or "") == provider]
    cad = round(sum(float(r.amount_cad or 0.0) for r in rows), 6)
    return {"provider": provider, "rows": len(rows), "cad": cad,
            "usd": round(cad * USD_PER_CAD, 4), "source": OBSERVED,
            "fx": f"converted at the assumed {USD_PER_CAD} USD/CAD the ceiling uses",
            "price_basis": "assumed list prices, not an invoice"}


def reconcile(db, *, now: datetime | None = None) -> dict:
    """The three columns that must not be merged, side by side.

    Deliberately does not compute a single "how much is left" number. That figure would
    have to pick one of the three as authoritative, and the day this was written each of
    them was right about something different: the internal budget had CA$55 free, the owner
    had reported US$10 of new credit, and the provider was refusing every call.
    """
    from ..gateway import anthropic as gw
    from ..gateway.routing import USD_PER_CAD
    from . import funding

    now = now or datetime.now(timezone.utc)
    probe = gw.last_probe(db) or {}
    held = funding.blocked(db)

    providers = sorted({f.provider for f in REPORTED_FACTS})
    per_provider = []
    for name in providers:
        reported = facts(name)
        ours = our_spend_usd(db, name)
        limit = next((f["amount_usd"] for f in reported if f["kind"] == "limit"), None)
        dashboard_used = next((f["amount_usd"] for f in reported if f["kind"] == "used"),
                              None)
        difference = (None if dashboard_used is None
                      else round(dashboard_used - ours["usd"], 4))
        balance = next((f["amount_usd"] for f in reported if f["kind"] == "balance"), None)
        auto_reload_off = any(f["kind"] == "auto_reload_off" for f in reported)

        # Three figures about one account should add up, and these do: credits bought less
        # spend to date is the balance on the page. Checking it is how a typo or a second
        # account using the same key would show up as arithmetic rather than as a surprise.
        internally_consistent = None
        if balance is not None and dashboard_used is not None:
            internally_consistent = {
                "implied_credits_purchased_usd": round(balance + dashboard_used, 2),
                "consistent": True,
                "why": ("balance plus spend-to-date is what was bought. It reconciles, so "
                        "the two dashboard figures are about the same account")}
        runway = None
        if balance is not None:
            from ..gateway.routing import USD_PER_CAD as _fx

            runway = int(round((balance / _fx) / CAD_PER_IMAGE_OBSERVED))

        per_provider.append({
            "provider": name,
            "balance_usd": balance,
            "auto_reload_off": auto_reload_off,
            "renders_left_at_observed_price": runway,
            "runway_basis": (
                f"balance converted at the assumed {USD_PER_CAD} USD/CAD and divided by "
                f"CA${CAD_PER_IMAGE_OBSERVED} per image, the measured cost of the live "
                f"renders. Arithmetic, not a forecast: it assumes every call is an image "
                f"and that the price holds" if runway else
                "no balance was reported for this provider"),
            "stops_without_warning": (
                "auto-reload is off, so this balance reaching zero stops every render at "
                "once. Nothing inside this system can retry past it"
                if auto_reload_off else ""),
            "reported": reported,
            "our_ledger": ours,
            "organisation_limit_usd": limit,
            "dashboard_used_usd": dashboard_used,
            "difference_usd": difference,
            "dashboard_self_check": internally_consistent,
            "what_a_difference_means": (
                "other usage on the same account, or this system's assumed list prices "
                "being wrong. Both are worth knowing and neither is an error to hide"
                if difference else
                "no dashboard figure was reported for this provider, so there is nothing "
                "to reconcile against"),
        })

    from ..finance import spend_report

    month = spend_report.what_it_bought(db, now=now)
    return {
        "internal_budget": {
            "source": OBSERVED,
            "month": month["month"],
            "spent_cad": month["spent_cad"],
            "ceiling_cad": 100.0,
            "what_it_is": ("a policy this system enforces on itself before every call. It "
                           "is not money and running out of it is not the same event"),
        },
        "provider_accounts": per_provider,
        "capability": {
            "source": OBSERVED,
            "anthropic_probe_ok": bool(probe.get("ok")),
            "probe_at": probe.get("at"),
            "probe_reason": (probe.get("reason") or "")[:240],
            "balance_blocked": bool(held.get("blocked")),
            "what_it_is": ("whether a real call actually succeeds. The only one of the "
                           "three that answers 'can this company work right now'"),
        },
        "never_merged": (
            "an internal budget with room, a reported balance and a working provider are "
            "three separate facts. On 2026-09-21 the first said CA$55 free, the second said "
            "US$10 added, and the third refused every call -- and a single combined number "
            "would have had to be wrong about two of them"),
        "not_a_budget": NOT_A_BUDGET,
        # F-106/F-103: the provider's own bill, once readable; the gap check on the
        # owner-reported figures (`finance.spend_hygiene.provider_discrepancy`) beside it.
        "provider_billing": last_settlements(db),
        "reported_vs_ledger": _reported_gaps(db, now),
    }


def _reported_gaps(db, now):
    try:
        from ..finance.spend_hygiene import provider_discrepancy

        return provider_discrepancy(db, now)
    except Exception as exc:  # noqa: BLE001 - one unreadable part must not hide the rest
        return {"unavailable": f"{type(exc).__name__}: {exc}"[:200]}


# ---------------------------------------------------------------------------
# F-106 / F-103: provider-side billing, read when (and only when) the owner grants it.
#
# Until now the "provider side" of every reconciliation was a figure the owner typed. The
# providers do publish what they billed -- Anthropic's Admin API `cost_report` (daily, USD
# as decimal strings in cents, grouped by description -> model) and OpenAI's organisation
# `costs` endpoint (daily buckets, USD) -- but both need an *admin* credential that is not
# the inference key. That credential is an OWNER ACTION. Everything below works the day it
# exists: the fetch is a read-only GET, the parse is tested against the published shapes,
# and settlement compares the provider's bill with this ledger day by day and model by model.
#
# What settlement does and does not claim:
# * The provider's figure is OBSERVED billing; this ledger's figure is RECORDED at assumed
#   list prices. They are kept side by side and never merged.
# * A provider reports per day and model, not per call, so a per-call `observed_cad` is
#   written only where one ledger row is the whole (day, model) bucket. Otherwise the bucket
#   is settled and the rows stay unobserved (NULL) -- never apportioned and called observed.
# * A material gap opens an incident. Nothing here changes a ceiling.

ADMIN_KEY_ENV: dict[str, str] = {"anthropic": "ANTHROPIC_ADMIN_KEY",
                                 "openai": "OPENAI_ADMIN_KEY"}
SETTLEMENT_ACTION = "spend.provider_settlement"
SETTLEMENT_SIGNATURE = "provider-billing-settlement-gap"
# A (day, model) bucket is materially off when it differs by at least this much CAD and by
# this share of the provider's figure. Both, so a cent on a cent is not an incident.
SETTLEMENT_FLOOR_CAD = 0.50
SETTLEMENT_SHARE = 0.10
OBSERVED_BASIS = "provider_cost_report:single_call_day_model_bucket"


class ProviderUsageUnavailable(RuntimeError):
    """No admin credential for this provider, or the provider refused the read."""


def admin_key_present(provider: str, env: dict | None = None) -> bool:
    import os

    name = ADMIN_KEY_ENV.get(provider)
    return bool(name and (env if env is not None else os.environ).get(name))


def _cents(value) -> float:
    return float(str(value)) / 100.0


def parse_anthropic_cost_report(payload: dict) -> list[dict]:
    """Anthropic `GET /v1/organizations/cost_report?group_by[]=description` -> day/model USD."""
    out: dict[tuple[str, str], float] = {}
    for bucket in payload.get("data") or []:
        day = str(bucket.get("starting_at") or "")[:10]
        for r in bucket.get("results") or []:
            if str(r.get("currency") or "USD").upper() != "USD":
                raise ProviderUsageUnavailable(f"unexpected currency {r.get('currency')!r}")
            model = str(r.get("model") or r.get("description") or "unattributed")
            out[(day, model)] = out.get((day, model), 0.0) + _cents(r.get("amount") or 0)
    return [{"day": d, "model": m, "usd": round(v, 6)} for (d, m), v in sorted(out.items())]


def parse_openai_costs(payload: dict) -> list[dict]:
    """OpenAI `GET /v1/organization/costs?bucket_width=1d` -> per-day USD (model "*")."""
    out: dict[tuple[str, str], float] = {}
    for bucket in payload.get("data") or []:
        start = bucket.get("start_time")
        day = (datetime.fromtimestamp(int(start), tz=timezone.utc).date().isoformat()
               if start is not None else "")
        for r in bucket.get("results") or []:
            amount = r.get("amount") or {}
            if str(amount.get("currency") or "usd").lower() != "usd":
                raise ProviderUsageUnavailable(f"unexpected currency {amount.get('currency')!r}")
            # Line items ("Image models", ...) are not model ids, so OpenAI settles per day.
            out[(day, "*")] = out.get((day, "*"), 0.0) + float(amount.get("value") or 0.0)
    return [{"day": d, "model": m, "usd": round(v, 6)} for (d, m), v in sorted(out.items())]


def _http_get_json(url: str, headers: dict, timeout: float = 30.0) -> dict:
    import json
    import urllib.request

    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
        return json.loads(resp.read().decode("utf-8"))


def fetch_provider_costs(provider: str, *, start: datetime, end: datetime,
                         env: dict | None = None, transport=None) -> list[dict]:
    """Read-only: the provider's own billed cost per day and model. Raises when ungranted."""
    import os
    from urllib.parse import urlencode

    source = env if env is not None else os.environ
    key = source.get(ADMIN_KEY_ENV.get(provider, ""), "")
    if not key:
        raise ProviderUsageUnavailable(
            f"no {ADMIN_KEY_ENV.get(provider, provider + ' admin key')} is configured: reading "
            f"{provider}'s billing needs an admin (usage/cost read) credential, an owner action")
    get = transport or _http_get_json
    rows: list[dict] = []
    if provider == "anthropic":
        params = {"starting_at": start.strftime("%Y-%m-%dT00:00:00Z"),
                  "ending_at": end.strftime("%Y-%m-%dT00:00:00Z"),
                  "group_by[]": "description", "bucket_width": "1d", "limit": 31}
        url = "https://api.anthropic.com/v1/organizations/cost_report?" + urlencode(params)
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        page = get(url, headers)
        rows += parse_anthropic_cost_report(page)
        while page.get("has_more") and page.get("next_page"):
            page = get(url + "&" + urlencode({"page": page["next_page"]}), headers)
            rows += parse_anthropic_cost_report(page)
    elif provider == "openai":
        params = {"start_time": int(start.timestamp()), "end_time": int(end.timestamp()),
                  "bucket_width": "1d", "group_by": "line_item", "limit": 31}
        url = "https://api.openai.com/v1/organization/costs?" + urlencode(params)
        headers = {"Authorization": f"Bearer {key}"}
        page = get(url, headers)
        rows += parse_openai_costs(page)
        while page.get("has_more") and page.get("next_page"):
            page = get(url + "&" + urlencode({"page": page["next_page"]}), headers)
            rows += parse_openai_costs(page)
    else:
        raise ProviderUsageUnavailable(f"no billing reader exists for {provider!r}")
    return rows


def settle(db, provider: str, provider_rows: list[dict], *,
           now: datetime | None = None) -> dict:
    """Compare the provider's billed (day, model) costs with this ledger and record the result.

    `provider_rows` are `{day, model, usd}` from `fetch_provider_costs`. Opens an incident for
    each materially different bucket; writes `observed_cad` only where a single ledger row is
    the whole bucket. Returns the settlement, which is also audited (`SETTLEMENT_ACTION`).
    """
    from sqlalchemy import select

    from ..core.models import AuditLog, CostEntry
    from ..finance import cost_attribution
    from ..finance.governor import _open_incident
    from ..gateway.routing import USD_PER_CAD

    now = now or datetime.now(timezone.utc)
    cost_attribution.ensure_table(db)
    days = sorted({r["day"] for r in provider_rows if r.get("day")})
    # A provider that bills per day only (model "*") is settled per day.
    by_model = all(r.get("model") != "*" for r in provider_rows)
    buckets = []
    gaps = []
    with db.session() as s:
        ledger: dict[tuple[str, str], list] = {}
        if days:
            lo = datetime.fromisoformat(days[0]).replace(tzinfo=timezone.utc)
            for e in s.scalars(select(CostEntry).where(CostEntry.provider == provider,
                                                       CostEntry.at >= lo)):
                at = e.at if e.at.tzinfo else e.at.replace(tzinfo=timezone.utc)
                ledger.setdefault((at.date().isoformat(),
                                   (e.model or "") if by_model else "*"), []).append(e)
        seen = set()
        for r in provider_rows:
            key = (r["day"], r["model"])
            seen.add(key)
            entries = ledger.get(key, [])
            provider_cad = round(float(r["usd"]) / USD_PER_CAD, 6)
            ledger_cad = round(sum(float(e.amount_cad or 0.0) for e in entries), 6)
            diff = round(provider_cad - ledger_cad, 6)
            material = abs(diff) >= max(SETTLEMENT_FLOOR_CAD, SETTLEMENT_SHARE * provider_cad)
            observed_written = False
            if len(entries) == 1:
                attr = s.scalar(select(cost_attribution.CostAttribution).where(
                    cost_attribution.CostAttribution.cost_entry_id == entries[0].id))
                if attr is not None:
                    attr.observed_cad = provider_cad
                    attr.observed_basis = OBSERVED_BASIS
                    observed_written = True
            b = {"day": r["day"], "model": r["model"], "provider_usd": r["usd"],
                 "provider_cad": provider_cad, "ledger_cad": ledger_cad,
                 "ledger_rows": len(entries), "difference_cad": diff, "material": material,
                 "per_call_observed_written": observed_written}
            buckets.append(b)
            if material:
                gaps.append(b)
        # Ledger buckets the provider did not bill at all, inside the reported days.
        for (day, model), entries in sorted(ledger.items()):
            if day in days and (day, model) not in seen:
                cad = round(sum(float(e.amount_cad or 0.0) for e in entries), 6)
                b = {"day": day, "model": model, "provider_usd": None, "provider_cad": None,
                     "ledger_cad": cad, "ledger_rows": len(entries), "difference_cad": None,
                     "material": cad >= SETTLEMENT_FLOOR_CAD,
                     "why": "recorded here, absent from the provider's bill"}
                buckets.append(b)
                if b["material"]:
                    gaps.append(b)
        incident = None
        if gaps:
            incident = _open_incident(
                s, signature=f"{SETTLEMENT_SIGNATURE}:{provider}:{now.strftime('%Y-%m')}",
                summary=(f"{provider} billing differs from this ledger in {len(gaps)} "
                         f"day/model bucket(s): provider-observed cost against costs recorded "
                         f"at assumed list prices. Other usage on the account or wrong prices"),
                detail={"provider": provider, "gaps": gaps[:50]}, severity="P2")
        out = {"provider": provider, "at": now.isoformat(), "basis": "provider_cost_report",
               "days": days, "buckets": buckets, "material_gaps": len(gaps),
               "provider_cad": round(sum(b["provider_cad"] or 0.0 for b in buckets), 6),
               "ledger_cad": round(sum(b["ledger_cad"] or 0.0 for b in buckets), 6),
               "incident": incident, "ceilings_changed": 0}
        s.add(AuditLog(actor="cfo", action=SETTLEMENT_ACTION, artifact=provider,
                       detail={k: v for k, v in out.items() if k != "buckets"}
                       | {"buckets": buckets[:200]}))
    return out


def settle_all(db, *, now: datetime | None = None, env: dict | None = None,
               transport=None) -> dict:
    """The governor pass: settle each provider whose billing read is granted; name the rest.

    Makes no network call for a provider without an admin key -- it reports OWNER_GATED.
    """
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = {}
    for provider in sorted(ADMIN_KEY_ENV):
        if not admin_key_present(provider, env):
            out[provider] = {"state": "OWNER_GATED",
                             "needs": ADMIN_KEY_ENV[provider],
                             "why": "provider billing is unread without an admin usage key"}
            continue
        try:
            rows = fetch_provider_costs(provider, start=start, end=end, env=env,
                                        transport=transport)
        except Exception as exc:  # noqa: BLE001 - an unreadable bill is reported, not zero
            out[provider] = {"state": "UNREADABLE", "why": f"{type(exc).__name__}: {exc}"[:300]}
            continue
        got = settle(db, provider, rows, now=now)
        out[provider] = {"state": "SETTLED", **{k: v for k, v in got.items() if k != "buckets"}}
    return out


def last_settlements(db) -> dict:
    """The latest recorded settlement per provider, for `reconcile` (no network)."""
    from sqlalchemy import desc, select

    from ..core.models import AuditLog

    out = {}
    with db.session() as s:
        for provider in sorted(ADMIN_KEY_ENV):
            row = s.scalar(select(AuditLog).where(AuditLog.action == SETTLEMENT_ACTION,
                                                  AuditLog.artifact == provider)
                           .order_by(desc(AuditLog.id)).limit(1))
            out[provider] = ({**(row.detail or {}), "state": "SETTLED"} if row is not None else
                             {"state": "OWNER_GATED" if not admin_key_present(provider)
                              else "NOT_YET_SETTLED",
                              "needs": ADMIN_KEY_ENV[provider],
                              "why": ("no provider billing has been read: only owner-reported "
                                      "dashboard figures exist for this provider")})
    return out
