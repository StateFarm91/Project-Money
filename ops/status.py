#!/usr/bin/env python3
"""Operator status report (directive section 28). Usage: python3 ops/status.py
Prints: day number, money spent, money earned, current cash, and pointers to what changed / is running / next / blockers.
Reads only committed state files; never invents values."""
import csv, pathlib, re, subprocess, sys
from datetime import datetime, timezone
root = pathlib.Path(__file__).resolve().parent.parent
START = datetime(2026, 9, 15, 11, 0, 7, tzinfo=timezone.utc)
now = datetime.now(timezone.utc)
day = (now - START).days + 1
rows = list(csv.DictReader((root / "finance" / "FINANCIAL_LEDGER.csv").open()))
def s(k): return sum(float(r[k] or 0) for r in rows)
gross = s("revenue_cad"); spent = s("expense_cad") + s("platform_payment_fees_cad") + s("advertising_cad") + s("refunds_chargebacks_cad")
cash = float(rows[-1]["running_available_cash_cad"]) if rows else 0.0
def section(path, heading):
    txt = (root / path).read_text()
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", txt, re.S | re.M)
    return (m.group(1).strip() if m else "(section not found)")
print(f"STATUS — Day {day}/90 ({now:%Y-%m-%d %H:%MZ})")
print(f"Money spent (all categories): {spent:.2f} CAD")
print(f"Money earned (gross revenue): {gross:.2f} CAD")
print(f"Current available cash: {cash:.2f} CAD")
print("\nWhat changed (latest DAILY_LOG entry):")
log = (root / "DAILY_LOG.md").read_text()
m = re.search(r"^## (.*?)$(.*?)(?=^## |\Z)", log, re.S | re.M)
print((m.group(1) + m.group(2)).strip() if m else "(none)")
print("\nWhat is running (AUTOMATIONS.md table):")
print(section("AUTOMATIONS.md", "Running") if "## Running" in (root / "AUTOMATIONS.md").read_text() else "(see AUTOMATIONS.md)")
print("\nWhat happens next (CURRENT_STATE.md):")
print(section("CURRENT_STATE.md", "Exact next actions (in order)"))
print("\nOwner-only blockers (OWNER_ACTIONS.md, open):")
print(section("OWNER_ACTIONS.md", "Open"))
