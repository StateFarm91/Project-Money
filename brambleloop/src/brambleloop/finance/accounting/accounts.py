"""Chart of accounts (F-903).

Small on purpose: a one-shop digital-pattern business with no bank feed yet. Every account
says what it holds and which statement it lands in. A posting to an account not in this
chart is refused by `ledger.post`.

Notes a human accountant will want (also exported by `handoff`):

* **1100 Etsy payment account** is a receivable: Etsy holds sale proceeds net of fees and
  refunds until it pays out. Its balance is the *expected payout*, derived, not a bank fact.
* **2000 Owner-funded spend payable**: model, image, hosting and software charges are paid
  on the owner's card today. Until a business bank account exists they are a liability to
  the owner, not cash out of a company account this system can see.
* **2050 Accrued listing-fee exposure**: conservative listing-fee reservations written before
  Etsy's ledger shows the charge (`finance.listing_costs`). Modelled, and labelled so.
* No sales-tax liability account is posted automatically. Whether GST/HST is collected by
  Etsy (marketplace rules) or owed by the shop is a jurisdictional judgment for the human
  accountant (F-909); the tax *reserve* is a management reserve shown beside the ledger,
  never booked as if the treatment were decided.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: str          # asset | liability | equity | revenue | contra_revenue | expense
    statement: str     # balance_sheet | income_statement
    cash: bool = False  # a cash account (cash-basis view reads only these)
    note: str = ""

    @property
    def normal_debit(self) -> bool:
        return self.type in ("asset", "expense", "contra_revenue")

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "type": self.type,
                "statement": self.statement, "cash": self.cash, "note": self.note}


CHART: tuple[Account, ...] = (
    Account("1000", "Bank - operating", "asset", "balance_sheet", cash=True,
            note="Only bank statement lines post here. No bank feed is connected in shadow."),
    Account("1100", "Etsy payment account (receivable)", "asset", "balance_sheet",
            note="Sale proceeds held by Etsy, net of fees and refunds; expected payout."),
    Account("2000", "Owner-funded spend payable", "liability", "balance_sheet",
            note="Operating charges paid on the owner's card, owed to the owner."),
    Account("2050", "Accrued listing-fee exposure", "liability", "balance_sheet",
            note="Modelled listing-fee reservations not yet seen on Etsy's ledger."),
    Account("3000", "Owner contributions", "equity", "balance_sheet"),
    Account("4000", "Sales - digital patterns", "revenue", "income_statement"),
    Account("4100", "Refunds", "contra_revenue", "income_statement"),
    Account("4200", "Discounts", "contra_revenue", "income_statement"),
    Account("5100", "Marketplace transaction & processing fees", "expense", "income_statement"),
    Account("5110", "Listing fees", "expense", "income_statement"),
    Account("5200", "AI model & API", "expense", "income_statement"),
    Account("5210", "Image generation & rendering", "expense", "income_statement"),
    Account("5300", "Hosting & software", "expense", "income_statement"),
    Account("5400", "Advertising", "expense", "income_statement"),
    Account("5500", "Testing, contractors & physical samples", "expense", "income_statement"),
    Account("5600", "Benchmark & research purchases", "expense", "income_statement"),
    Account("5900", "Other operating expense", "expense", "income_statement"),
)

BY_CODE = {a.code: a for a in CHART}

BANK, ETSY_RECEIVABLE = "1000", "1100"
OWNER_PAYABLE, ACCRUED_LISTING = "2000", "2050"
OWNER_EQUITY = "3000"
SALES, REFUNDS, DISCOUNTS = "4000", "4100", "4200"
MARKETPLACE_FEES, LISTING_FEES = "5100", "5110"
AI_API, IMAGE, INFRA, ADS, TESTING, BENCHMARK, OTHER_EXPENSE = (
    "5200", "5210", "5300", "5400", "5500", "5600", "5900")

REVENUE_ACCOUNTS = (SALES,)
CONTRA_REVENUE_ACCOUNTS = (REFUNDS, DISCOUNTS)
EXPENSE_ACCOUNTS = tuple(a.code for a in CHART if a.type == "expense")
FEE_ACCOUNTS = (MARKETPLACE_FEES,)
OPERATING_ACCOUNTS = tuple(c for c in EXPENSE_ACCOUNTS if c not in FEE_ACCOUNTS)

# cost_entries.kind -> expense account (F-907). Unknown kinds go to 5900 and are named.
COST_KIND_ACCOUNT = {
    "llm": AI_API, "api": AI_API,
    "image": IMAGE, "render": IMAGE,
    "hosting": INFRA, "software": INFRA, "infra": INFRA,
    "ads": ADS,
    "testing": TESTING, "contractor": TESTING, "physical_test": TESTING,
    "benchmark": BENCHMARK, "benchmark_purchase": BENCHMARK,
    "etsy_listing_fee": LISTING_FEES, "etsy_listing_fee_actual": LISTING_FEES,
}


def account_for_cost_kind(kind: str) -> str:
    return COST_KIND_ACCOUNT.get((kind or "").strip().lower(), OTHER_EXPENSE)


def chart() -> list[dict]:
    return [a.to_dict() for a in CHART]
