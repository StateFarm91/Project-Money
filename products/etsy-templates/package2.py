#!/usr/bin/env python3
"""Listing images + copy file for listing 2. Usage: .venv/bin/python products/etsy-templates/package2.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from package import canvas, table, font, NAVY, CREAM, GREY, DIST
HERE = pathlib.Path(__file__).parent; OUT = DIST / "listing-2"; IMG = OUT / "images"
L = json.load(open(HERE / "listings.json"))["listing-2"]
def images():
    IMG.mkdir(parents=True, exist_ok=True)
    im, dr = canvas("GST/HST Quick Method Calculator", "Regular vs quick method · RC4058 rates · $30,000 small-supplier tracker")
    y = 300
    for line in ["✓ Enter quarterly sales and GST/HST paid", "✓ Remittance under BOTH methods, side by side", "✓ RC4058 rate for your province and business type", "✓ 1% credit on the first $30,000 handled by quarter", "✓ Eligibility check ($400,000 limit)", "✓ Small-supplier tracker: know when you must register", "✓ 'Should I register voluntarily?' worksheet", "✓ Excel + Google Sheets"]:
        dr.text((100, y), line, font=font(48), fill=NAVY); y += 84
    dr.rectangle([100, 1010, 1900, 1840], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 1040), "Example: Ontario, services, $50,000 in sales", font=font(40, True), fill=NAVY)
    table(dr, 140, 1110, ["", "Regular method", "Quick method"], [["GST/HST collected", "6,500.00", "—"], ["ITCs on purchases", "1,060.00", "capital only"], ["RC4058 rate 8.8% on $56,500", "—", "4,972.00"], ["1% credit on first $30,000", "—", "300.00"], ["Net tax to remit", "5,440.00", "4,672.00"], ["You keep more with", "", "Quick method (+768.00)"]], [760, 420, 520], fs=34)
    im.save(IMG / "01-hero.png")
    im, dr = canvas("Quarter by quarter", "Type the yellow cells; everything else calculates")
    table(dr, 60, 320, ["", "Q1", "Q2", "Q3", "Q4", "Year"], [["Taxable sales before tax", "12,000", "15,000", "9,000", "14,000", "50,000"], ["GST/HST paid (ITC-eligible)", "260", "300", "180", "320", "1,060"], ["GST/HST collected (13%)", "1,560", "1,950", "1,170", "1,820", "6,500"], ["Regular method net tax", "1,300", "1,650", "990", "1,500", "5,440"], ["Eligible supplies incl. tax", "13,560", "16,950", "10,170", "15,820", "56,500"], ["Quick: remittance (8.8%)", "1,193", "1,492", "895", "1,392", "4,972"], ["Quick: 1% credit", "136", "164", "0", "0", "300"], ["Quick method net tax", "1,058", "1,327", "895", "1,392", "4,672"]], [560, 250, 250, 250, 250, 300], fs=30)
    dr.text((60, 1000), "Rates for all 13 provinces and territories, both RC4058 tables (services and goods for resale) and the goods credit are built in.", font=font(32), fill=GREY)
    dr.rectangle([60, 1120, 1940, 1800], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 1150), "Small-supplier tracker", font=font(40, True), fill=NAVY)
    for i, t in enumerate(["Highest single quarter and rolling four quarters vs $30,000", "Status turns red: 'Over $30,000: you must register for GST/HST'", "Warns at $25,000: 'Approaching $30,000: plan to register'", "Voluntary registration worksheet: ITCs recovered vs your time"]):
        dr.text((100, 1230 + i * 90), "• " + t, font=font(36), fill=(30, 30, 30))
    im.save(IMG / "02-quarters.png")
    im, dr = canvas("What you get", "Instant download · .xlsx · works in Excel and Google Sheets")
    y = 320
    for t, d in [("One calculator sheet + rate tables", "Settings, quarterly inputs, regular method, quick method, comparison, small-supplier tracker, voluntary-registration worksheet."), ("2026 edition", "RC4058 rates and provincial rates checked against CRA in September 2026. Version stamp inside. Validated by automated tests."), ("Google Sheets ready", "File > Import > Replace spreadsheet. No macros, no add-ons."), ("Support", "Message the shop; we fix problems or refund."), ("Honest note", "Bookkeeping tool, not tax advice. Some businesses cannot use the quick method (see RC4058). Built by a small Canadian shop with AI assistance in building and checking the formulas.")]:
        dr.text((100, y), t, font=font(46, True), fill=NAVY); y += 66
        import textwrap
        for ln in textwrap.wrap(d, 70): dr.text((100, y), ln, font=font(36), fill=(30, 30, 30)); y += 50
        y += 40
    im.save(IMG / "03-whats-inside.png")
def build():
    OUT.mkdir(parents=True, exist_ok=True); images()
    (OUT / "listing-copy.txt").write_text(f"TITLE ({len(L['title'])} chars)\n{L['title']}\n\nTAGS ({len(L['tags'])})\n" + ", ".join(L["tags"]) + f"\n\nPRICE CA${L['price_cad']:.2f}\n\nDESCRIPTION\n{L['description']}\n")
    print("images:", sorted(p.name for p in IMG.iterdir()))
if __name__ == "__main__": build()
