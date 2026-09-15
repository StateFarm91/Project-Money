#!/usr/bin/env python3
"""Summarize finance/FINANCIAL_LEDGER.csv (actuals only). Usage: python3 ops/ledger.py"""
import csv, pathlib
p = pathlib.Path(__file__).resolve().parent.parent / "finance" / "FINANCIAL_LEDGER.csv"
rows = list(csv.DictReader(p.open()))
def s(k): return sum(float(r[k] or 0) for r in rows)
gross = s("revenue_cad"); exp = s("expense_cad"); fees = s("platform_payment_fees_cad")
ads = s("advertising_cad"); ref = s("refunds_chargebacks_cad")
net = gross - exp - fees - ads - ref
last = rows[-1] if rows else {}
print(f"events: {len(rows)}")
print(f"gross_revenue_cad: {gross:.2f}")
print(f"expenses_cad: {exp:.2f}  fees: {fees:.2f}  ads: {ads:.2f}  refunds: {ref:.2f}")
print(f"net_contribution_cad: {net:.2f}")
print(f"running_available_cash_cad: {float(last.get('running_available_cash_cad', 0)):.2f}")
print(f"capital_deployed_committed_cad: {float(last.get('capital_deployed_committed_cad', 0)):.2f}")
