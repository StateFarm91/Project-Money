"""F-579: the accounting-integration decision -- QuickBooks Online, Xero, or our own books.

The Master: evaluate QuickBooks Online, Xero and other finance integrations against
Brambleloop's ledger needs, duplication risk, cost and reconciliation quality *before*
connecting one. This module is that evaluation, as data with sources, and the rule that
follows from it: no accounting integration may get a software spend limit unless this
evaluation recommends it (`tool_decisions.check_scope` asks `connection_allowed`).

Scores are 1 (poor) to 5 (best) per criterion, each with its reason. Prices are the
vendors' published Canadian list prices read on `AS_OF` (CAD per month, before tax); a
promotion is not a price. They are re-read before any purchase -- the owner approves spend,
not this table.

The decision is recomputed from the table, never typed: the highest weighted score wins,
and an external tool is recommended only if it beats the in-house books by `MARGIN`.
Re-evaluate when any `REVISIT_WHEN` condition becomes true.
"""
from __future__ import annotations

AS_OF = "2026-10-27"
CRITERIA = {"ledger_fit": 0.35, "duplication_risk": 0.25, "cost": 0.15,
            "reconciliation_quality": 0.25}
MARGIN = 0.5
SOURCES = {
    "quickbooks_online": "https://quickbooks.intuit.com/ca/pricing/ (Essentials from CA$54/mo)",
    "xero": "https://www.xero.com/ca/pricing-plans/ and /ca/pricing-plans/update "
            "(Standard CA$60/mo from 2026-04-01)",
}

CANDIDATES = {
    "in_house_books": {
        "name": "Brambleloop's own double-entry books (finance.accounting)",
        "monthly_cost_cad": 0.0,
        "scores": {
            "ledger_fit": (5, "the journal is derived from the same order, fee and cost rows "
                              "the company writes; per-product/release attribution is native"),
            "duplication_risk": (5, "one source of truth; nothing re-keyed"),
            "cost": (5, "no subscription"),
            "reconciliation_quality": (4, "Etsy payment-account ledger and bank statements "
                                          "are matched line by line with exceptions "
                                          "(F-575/F-904); the Etsy type mapping is not yet "
                                          "verified against a live shop"),
        },
        "limits": "no filing, no payroll, no accountant-native workspace; the handoff pack "
                  "(finance.accounting.handoff) is the export a human accountant receives",
    },
    "quickbooks_online": {
        "name": "QuickBooks Online (Canada)",
        "monthly_cost_cad": 54.0,
        "scores": {
            "ledger_fit": (3, "general ledger and GST/HST returns fit; per-pattern release "
                              "attribution and the derived modelled/measured fee basis do "
                              "not exist there"),
            "duplication_risk": (2, "a second ledger fed from the same orders: two books to "
                                    "keep in agreement"),
            "cost": (2, "CA$54/mo before any revenue"),
            "reconciliation_quality": (3, "bank feeds are strong; Etsy fees arrive through a "
                                          "third-party connector or manual entry"),
        },
    },
    "xero": {
        "name": "Xero (Canada)",
        "monthly_cost_cad": 60.0,
        "scores": {
            "ledger_fit": (3, "general ledger fits; same attribution gap as QBO"),
            "duplication_risk": (2, "a second ledger, as QBO"),
            "cost": (2, "CA$60/mo (Standard) before any revenue"),
            "reconciliation_quality": (3, "bank feeds strong; Etsy fees through a connector"),
        },
    },
}

REVISIT_WHEN = (
    "a month closes with real orders and the human accountant asks for a QBO/Xero file "
    "rather than the handoff pack",
    "taxable supplies approach the CA$30,000 small-supplier threshold (GST/HST registration)",
    "payroll or a second sales channel needs a general-purpose ledger",
)


def score(key: str) -> float:
    c = CANDIDATES[key]
    return round(sum(CRITERIA[k] * c["scores"][k][0] for k in CRITERIA), 3)


def decide() -> dict:
    ranked = sorted(((score(k), k) for k in CANDIDATES), reverse=True)
    best_score, best = ranked[0]
    house = score("in_house_books")
    if best != "in_house_books" and best_score - house < MARGIN:
        best = "in_house_books"
    return {"as_of": AS_OF, "recommend": best,
            "connect_external": best != "in_house_books",
            "scores": {k: s for s, k in ranked}, "criteria": CRITERIA, "margin": MARGIN,
            "revisit_when": list(REVISIT_WHEN), "sources": SOURCES}


ACCOUNTING_TOOLS = {"quickbooks": "quickbooks_online", "quickbooks_online": "quickbooks_online",
                    "qbo": "quickbooks_online", "xero": "xero"}


def connection_allowed(tool: str) -> tuple[bool, str]:
    key = ACCOUNTING_TOOLS.get((tool or "").strip().lower())
    if key is None:
        return True, "not an accounting integration"
    d = decide()
    if d["recommend"] == key:
        return True, f"F-579 evaluation ({AS_OF}) recommends {key}"
    return False, (f"F-579 evaluation ({AS_OF}) recommends {d['recommend']} "
                   f"(scores {d['scores']}); connecting {key} would duplicate the books. "
                   f"Revisit when: {REVISIT_WHEN[0]}")
