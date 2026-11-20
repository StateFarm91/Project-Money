# Etsy template line — product specification (v1, Day 1)

Status: spec. Built by `build_templates.py` (openpyxl) into `dist/` as .xlsx; Google Sheets versions are the same .xlsx imported into Sheets (formulas chosen to be Sheets-compatible: no dynamic arrays, no XLOOKUP; SUMIFS/INDEX-MATCH/IFERROR only). Each listing ships a ZIP (≤20 MB, ≤5 files) with: the .xlsx, a PDF quick-start guide, and a README.txt with the disclaimer and the Sheets import steps.

## Listing 1 — Canadian Sole Proprietor Bookkeeping System (T2125-mapped) — CA$29
Sheets:
1. **Start here** — instructions, disclaimer (bookkeeping tool, not tax advice; verify with CRA/an accountant), version and tax-year, how to import to Google Sheets, settings: business name, fiscal year, province (dropdown drives sales-tax rates), GST/HST registered? (yes/no), quick method? (yes/no), business type (services / goods for resale).
2. **Income** — date, client/customer, description, channel (dropdown: Etsy, Shopify, direct, other), invoice #, amount before tax, GST/HST collected (auto by province if registered), PST/QST collected (auto), total, paid? , notes. Monthly and channel subtotals via SUMIFS on a summary block.
3. **Expenses** — date, vendor, description, category (dropdown = T2125 lines 8521-9270 + "Home office (Part 7)" + "Vehicle (Chart A)" + "Personal (not deductible)"), amount before tax, GST/HST paid (ITC eligible if registered), PST/QST paid, total, payment method, receipt ref, notes. Meals & entertainment auto-flag 50%.
4. **T2125 Summary** — Part 3 gross income; Part 4 lines 8521…9270 with SUMIFS by category; 9369 net income before adjustments; Part 7 home-office feed (7A–7P) and 9945; Chart A vehicle feed; final net income; a "copy to your tax software" column.
5. **GST/HST** — quarterly/annual: collected, ITCs, net tax (regular method); quick-method computation with the RC4058 rate picked by province × business type × rate charged, 1% credit on first $30,000; side-by-side comparison "which method remits less this year"; remittance calendar (monthly/quarterly/annual filer dropdown). Small-supplier tracker: rolling four-quarter and single-quarter totals vs $30,000.
6. **Home office** — square footage (office/total), hours if shared, expense inputs 7A–7G, CCA optional, carry-forward, 7M/7N/7O/7P computed.
7. **Vehicle** — logbook (date, from/to, purpose, km) with business-km %; actual expenses (fuel, insurance, licence, maintenance, lease/loan interest, parking); deductible = expenses × business %; parking 100%.
8. **Dashboard** — monthly income vs expenses chart data, net by month, tax set-aside estimate (user-set %), GST/HST owing estimate.
9. **Lists** — provinces with rates, quick-method rate matrix, categories, channels (hidden/protected).

## Listing 2 — GST/HST Quick Method vs Regular Calculator + Small-Supplier Tracker — CA$14
Standalone: sheets 5 and 9 above, plus a "should I register voluntarily?" worksheet (ITCs vs admin).

## Listing 3 — Home-Office and Vehicle Expense Workbook (T2125 Part 7 + Chart A) — CA$12
Standalone: sheets 6, 7 and the relevant summary lines; printable logbook page.

## Listing 4 — Self-Employed Tax Set-Aside and Instalment Planner — CA$12
Inputs: expected net income, province; outputs: rough federal+provincial tax and CPP estimate bands (using published 2026 brackets — to be verified before build), monthly set-aside, CRA instalment rule of thumb (owing > $3,000 in the current year and either of the two prior years; Quebec $1,800) with due dates Mar 15 / Jun 15 / Sep 15 / Dec 15.

## Listing 5 — Bundle (1+2+3+4) — CA$44

## Quality gates (automated in the build)
- Every formula recalculates without errors in LibreOffice headless (convert to PDF and grep for `#REF!`, `#NAME?`, `#DIV/0!`).
- Unit tests: sales tax by province (13 rows), quick-method rates (32 cells) match TAX_REFERENCE.md; T2125 line totals equal the category sums on sample data; home-office cap logic (7P ≤ 7N).
- Workbook opens in Google Sheets without unsupported-function warnings (manual check by the owner once; formulas restricted to a whitelist).
- Listing images: 6 per listing, 2000×2000 px, generated from rendered sheet screenshots (LibreOffice → PNG) with captions; AI-assistance disclosed in the description.
