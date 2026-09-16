#!/usr/bin/env python3
"""Listing 5: the bundle (1+2+3+4). Zips the four already-built workbooks with one combined
README (5 files total, well within Etsy's 20 MB / 5-file ZIP limit) and renders listing images.
Usage: .venv/bin/python products/etsy-templates/package5.py (run the other four build_*.py / package*.py first)"""
import json, pathlib, zipfile, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from package import canvas, table, font, NAVY, CREAM, GREY, DIST
from build_templates import TAX_YEAR, VERSION

HERE = pathlib.Path(__file__).parent; OUT = DIST / "listing-5"; IMG = OUT / "images"
L = json.load(open(HERE / "listings.json"))["listing-5"]

WORKBOOKS = [
    "Canadian-Sole-Proprietor-Bookkeeping-T2125-2026.xlsx",
    "GST-HST-Quick-Method-Calculator-Small-Supplier-Tracker-2026.xlsx",
    "Home-Office-Vehicle-Expense-Workbook-2026.xlsx",
    "Self-Employed-Tax-Set-Aside-Instalment-Planner-2026.xlsx",
]

README = f"""MapleSheets 2026 Bundle — all four tools (v{VERSION})
Thank you for your purchase.

FILES
- Canadian-Sole-Proprietor-Bookkeeping-T2125-2026.xlsx — the full bookkeeping system: income, expenses, GST/HST by province, home office, vehicle, T2125 Summary, dashboard. Start here for day-to-day bookkeeping.
- GST-HST-Quick-Method-Calculator-Small-Supplier-Tracker-2026.xlsx — standalone: which GST/HST method saves you more, and the $30,000 small-supplier tracker.
- Home-Office-Vehicle-Expense-Workbook-2026.xlsx — standalone: business-use-of-home (Part 7) and vehicle (Chart A) schedules with a printable logbook page.
- Self-Employed-Tax-Set-Aside-Instalment-Planner-2026.xlsx — standalone: a conservative federal + provincial + CPP estimate, monthly set-aside, and the CRA instalment due dates.

Workbook 1 already includes the Home office, Vehicle and GST-HST calculations for your own numbers as you enter them through the year. Workbooks 2-4 are the same calculations as quick standalone tools — useful for a one-off estimate, for sharing with someone who only needs one piece, or as a second check.

GOOGLE SHEETS
Open sheets.google.com > File > Import > Upload > choose the .xlsx > "Replace spreadsheet" for each file you want to use there. Dropdowns and formulas carry over.

SUPPORT AND REFUNDS
Message the shop on Etsy with a screenshot if anything does not work; we fix it or refund it.

IMPORTANT
These are bookkeeping tools, not tax, legal or accounting advice. Rates and CRA line numbers were checked in September 2026 for the {TAX_YEAR} tax year; verify with CRA or an accountant before filing. Keep your receipts for six years.
"""

def images():
    IMG.mkdir(parents=True, exist_ok=True)
    im, dr = canvas("MapleSheets 2026 Bundle", "All four Canadian self-employed tax tools · one download")
    y = 300
    for line in ["✓ 1. Full bookkeeping system (T2125, GST/HST, home office, vehicle)", "✓ 2. GST/HST quick vs regular method calculator", "✓ 3. Home office + vehicle expense tracker", "✓ 4. Tax set-aside and instalment planner", "✓ Every rate checked against CRA for 2026", "✓ Excel + Google Sheets, one ZIP download"]:
        dr.text((100, y), line, font=font(46), fill=NAVY); y += 84
    dr.rectangle([100, 970, 1900, 1840], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 1000), "Bundle price vs buying separately", font=font(40, True), fill=NAVY)
    table(dr, 140, 1070, ["", "Price"], [["1. Bookkeeping system", "29.00"], ["2. GST/HST calculator", "14.00"], ["3. Home office + vehicle", "12.00"], ["4. Instalment planner", "12.00"], ["Separately", "67.00"], ["Bundle price", "44.00 (save 23.00)"]], [700, 420], fs=32)
    im.save(IMG / "01-hero.png")

    im, dr = canvas("What's inside", "One ZIP: four workbooks, a quick-start PDF and a bundle guide")
    items = [("1. Bookkeeping system", "Income, expenses, GST/HST by province, home office, vehicle, T2125 Summary, dashboard — the year-round core."), ("2. GST/HST calculator", "Regular vs quick method side by side, RC4058 rates, $30,000 small-supplier tracker."), ("3. Home office + vehicle", "Part 7 loss cap and carry-forward handled; Chart A actual-cost vehicle deduction; printable logbook."), ("4. Instalment planner", "Federal + provincial + CPP estimate for all 13 provinces/territories, monthly set-aside, CRA due dates.")]
    y = 320
    for t, d in items:
        dr.text((100, y), t, font=font(44, True), fill=NAVY); y += 62
        import textwrap
        for ln in textwrap.wrap(d, 74): dr.text((100, y), ln, font=font(34), fill=(30, 30, 30)); y += 46
        y += 36
    im.save(IMG / "02-whats-inside.png")

    im, dr = canvas("Why bundle", "One consistent set of spreadsheets instead of four different sellers")
    for i, t in enumerate(["Same categories, same rates, same look across all four workbooks", "2026 edition; validated by an automated test before release", "Works in Excel and Google Sheets; no macros, no add-ons", "Support: message the shop; we fix problems or refund", "Bookkeeping tools, not tax advice — verify with CRA or an accountant"]):
        dr.text((100, 340 + i * 110), "• " + t, font=font(40), fill=(30, 30, 30))
    im.save(IMG / "03-savings.png")

def build():
    OUT.mkdir(parents=True, exist_ok=True); images()
    missing = [w for w in WORKBOOKS if not (DIST / w).exists()]
    if missing:
        raise SystemExit(f"missing workbooks, run the other build_*.py scripts first: {missing}")
    (OUT / "README.txt").write_text(README)
    z = OUT / L["files"][0]
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for w in WORKBOOKS: zf.write(DIST / w, w)
        zf.write(OUT / "README.txt", "README.txt")
        file_count = len(zf.namelist())
    print("package:", z, f"{z.stat().st_size/1e6:.2f} MB", f"{file_count} files")
    (OUT / "listing-copy.txt").write_text(f"TITLE ({len(L['title'])} chars)\n{L['title']}\n\nTAGS ({len(L['tags'])})\n" + ", ".join(L["tags"]) + f"\n\nPRICE CA${L['price_cad']:.2f}\n\nDESCRIPTION\n{L['description']}\n")
    print("images:", sorted(p.name for p in IMG.iterdir()))
    assert z.stat().st_size < 20e6

if __name__ == "__main__": build()
