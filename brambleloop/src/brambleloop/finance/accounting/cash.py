"""Cash, obligations, payouts, reserves, safe discretionary budget and runway (F-908).

The company has no business bank feed in shadow, so **cash on hand is UNKNOWN** and every
figure that needs it -- safe discretionary budget, runway -- is UNKNOWN with the reason,
never computed from an assumed zero or an assumed balance. What *is* known is reported:

* Etsy payment-account balance (account 1100) = the **expected payout**, derived from the
  journal: sales less refunds and fees less listing fees, less payouts already deposited.
  A receivable, not cash; its basis follows the fee basis.
* Obligations: owner-funded spend payable (2000), accrued listing-fee exposure (2050).
* Committed spend: live `spend_reservations` (claimed before a call, not yet billed).
* Upcoming bills: the declared infrastructure run-rate and the model-spend ceiling, labelled
  `declared_not_observed` where that is what they are.
* Reserves: the sales-tax reserve (the books' rate on net sales, calendar year to date) and
  an income-tax set-aside (`finance.reinvestment.TAX_RATE` on positive profit before
  reserves), both management reserves for the human accountant to confirm.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import accounts as A
from . import health as H
from .ledger import balances, to_cad
from .schema import ensure


def _ytd_start(now: datetime) -> datetime:
    return datetime(now.year, 1, 1, tzinfo=timezone.utc)


def position(db, *, now: datetime | None = None, health: dict | None = None) -> dict:
    from .. import reinvestment, reservations, spend_policy
    from . import views

    db = ensure(db)
    now = now or datetime.now(timezone.utc)
    health = health or H.reading(db, now=now)
    with db.session() as s:
        b = balances(s)
        last30 = balances(s, since=now - timedelta(days=30), until=now)

    def bal(code):
        return int((b.get(code) or {}).get("balance", 0))

    cash_known = health["cash_known"]
    cash_micros = bal(A.BANK) if cash_known else None
    receivable = bal(A.ETSY_RECEIVABLE)
    owner_payable = bal(A.OWNER_PAYABLE)
    accrued_listing = bal(A.ACCRUED_LISTING)
    try:
        out = reservations.outstanding(db, now=now)
        committed = float(out["cad"])
    except Exception:  # noqa: BLE001
        out, committed = {}, None
    ytd = views.accrual(db, since=_ytd_start(now), until=now, health=health)
    m = ytd["_micros"]
    sales_reserve = m["reserve"] if ytd["sales_reading"] != "UNKNOWN" else None
    pbr = m["net_sales"] - m["fees"] - m["operating"]
    income_reserve = (int(round(max(0, pbr) * reinvestment.TAX_RATE))
                      if ytd["sales_reading"] != "UNKNOWN" else None)
    burn = sum(int((last30.get(c) or {}).get("balance", 0)) for c in A.OPERATING_ACCOUNTS)
    burn_measured = sum(int(((last30.get(c) or {}).get("by_basis") or {}).get("measured", 0))
                        for c in A.OPERATING_ACCOUNTS)
    operating_reserve = int(round(reinvestment.OPERATING_FLOOR_CAD
                                  * reinvestment.CASH_RESERVE_MONTHS * 1_000_000))
    bills = [
        {"name": "hosting (declared run-rate)", "amount_cad": spend_policy.INFRA_MONTHLY_CAD,
         "cadence": "monthly", "basis": spend_policy.INFRA_BASIS},
        {"name": "model/API spend ceiling", "amount_cad": spend_policy.ceiling_cad(),
         "cadence": "monthly", "basis": "policy ceiling (maximum, not a forecast)"},
    ]
    if cash_micros is None:
        safe = None
        safe_why = ("UNKNOWN: no bank source, so cash is unknown and nothing is safe to spend "
                    "on the strength of it. " + health["sources"]["bank"]["why"])
        runway = None
        runway_why = "UNKNOWN: cash is unknown. Operating spend is owner-funded today."
    else:
        deductions = (owner_payable + accrued_listing + int(round((committed or 0) * 1e6))
                      + (sales_reserve or 0) + (income_reserve or 0) + operating_reserve)
        safe = max(0, cash_micros - deductions)
        safe_why = ("cash less owner payable, accrued listing fees, committed reservations, "
                    "tax reserves and the operating reserve "
                    f"({reinvestment.CASH_RESERVE_MONTHS} months x "
                    f"CA${reinvestment.OPERATING_FLOOR_CAD:.0f})")
        if committed is None or sales_reserve is None:
            safe, safe_why = None, ("UNKNOWN: a reserve or commitment input is unknown "
                                    "(sales source or reservations unreadable)")
        runway = ({"low_months": round(cash_micros / burn, 1) if burn else None,
                   "high_months": round(cash_micros / burn_measured, 1)
                   if burn_measured else None}
                  if burn > 0 else None)
        runway_why = ("cash / trailing-30-day operating spend; the range is total spend vs "
                      "measured-only spend" if burn > 0 else "no operating spend in 30 days")
    return {
        "as_of": now.isoformat(), "currency": "CAD",
        "cash_on_hand_cad": to_cad(cash_micros) if cash_micros is not None else None,
        "cash_reading": "measured" if cash_known else "UNKNOWN",
        "cash_why": health["sources"]["bank"]["why"],
        "expected_payout_cad": to_cad(receivable),
        "expected_payout_by_basis_cad": {k: to_cad(v, 4) for k, v in
                                         ((b.get(A.ETSY_RECEIVABLE) or {}).get("by_basis")
                                          or {}).items() if v},
        "expected_payout_reading": ("derived receivable (not cash); "
                                    + H.figure_reading(health["sources"]["orders"]["state"],
                                                       bool(receivable))),
        "obligations": {
            "owner_funded_spend_payable_cad": to_cad(owner_payable, 4),
            "accrued_listing_fee_exposure_cad": to_cad(accrued_listing, 4),
        },
        "committed_spend_cad": round(committed, 4) if committed is not None else None,
        "committed_detail": {"live_reservations": out.get("count"),
                             "expired_unreleased_cad": out.get("expired_unreleased_cad"),
                             "basis": "spend_reservations (claimed before a call; not posted "
                                      "to the ledger -- a commitment, not an expense)"},
        "upcoming_bills": bills,
        "tax_reserve": {
            "sales_tax_reserve_ytd_cad": to_cad(sales_reserve) if sales_reserve is not None
            else None,
            "income_tax_setaside_ytd_cad": to_cad(income_reserve)
            if income_reserve is not None else None,
            "basis": "estimated (management reserve; treatment for the human accountant)",
        },
        "operating_reserve_cad": to_cad(operating_reserve),
        "safe_discretionary_budget_cad": to_cad(safe) if safe is not None else None,
        "safe_discretionary_budget_why": safe_why,
        "trailing_30d_operating_spend_cad": to_cad(burn, 4),
        "trailing_30d_operating_spend_measured_cad": to_cad(burn_measured, 4),
        "runway": runway, "runway_why": runway_why,
        "authority": ("Finance reports; it never moves money, pays a bill, or treats a "
                      "budget as permission (F-912, F-917)."),
    }
