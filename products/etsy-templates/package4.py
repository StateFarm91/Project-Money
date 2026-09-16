#!/usr/bin/env python3
"""Listing images + copy file for listing 4. Usage: .venv/bin/python products/etsy-templates/package4.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from package import canvas, table, font, NAVY, CREAM, GREY, DIST
HERE = pathlib.Path(__file__).parent; OUT = DIST / "listing-4"; IMG = OUT / "images"
L = json.load(open(HERE / "listings.json"))["listing-4"]

def images():
    IMG.mkdir(parents=True, exist_ok=True)
    im, dr = canvas("Self-Employed Tax Set-Aside Planner", "Federal + provincial tax, CPP, monthly set-aside, instalment due dates")
    y = 300
    for line in ["✓ All 10 provinces and 3 territories, 2026 brackets", "✓ Federal basic personal amount credit built in",
                 "✓ Quebec's 16.5% federal abatement handled automatically", "✓ CPP base + CPP2 for the self-employed (2026 rates)",
                 "✓ Monthly set-aside and quarterly instalment estimate", "✓ CRA instalment rule of thumb + due dates",
                 "✓ Excel + Google Sheets"]:
        dr.text((100, y), line, font=font(46), fill=NAVY); y += 82
    dr.rectangle([100, 970, 1900, 1840], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 1000), "Example: Ontario, $50,000 net income", font=font(40, True), fill=NAVY)
    table(dr, 140, 1070, ["", "Amount"], [["Federal tax after BPA credit", "4,696.72"], ["Ontario tax", "2,525.00"], ["CPP (self-employed)", "5,533.50"], ["Total estimated tax + CPP", "12,755.22"], ["Monthly set-aside", "1,062.94"]], [760, 420], fs=32)
    im.save(IMG / "01-hero.png")

    im, dr = canvas("Full breakdown", "Every step shown — nothing is a black box")
    table(dr, 60, 320, ["", "Amount"], [["Federal tax before credits (14%–33% brackets)", "7,000.00"], ["Basic personal amount credit", "2,303.28"], ["Federal tax after credit", "4,696.72"], ["Provincial tax (your province's brackets)", "2,525.00"], ["CPP pensionable earnings", "46,500.00"], ["Base CPP (11.9%)", "5,533.50"], ["CPP2 (8%, only above $74,600)", "0.00"]], [700, 320], fs=30)
    dr.text((60, 950), "Quebec residents: the 16.5% federal abatement and QPP note are built in automatically when you pick Quebec.", font=font(30), fill=GREY)
    dr.rectangle([60, 1050, 1940, 1500], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 1080), "Why this runs a little high, on purpose", font=font(38, True), fill=NAVY)
    for i, t in enumerate(["Does not include your province's personal credits (only the federal one)", "Does not apply the CPP self-employment deduction", "Result: a safe amount to set aside, never an under-estimate"]):
        dr.text((140, 1160 + i * 90), "• " + t, font=font(34), fill=(30, 30, 30))
    im.save(IMG / "02-breakdown.png")

    im, dr = canvas("Instalments", "The CRA rule of thumb, and the four due dates if it applies")
    table(dr, 60, 320, ["Instalment", "Due date", "Amount"], [["Q1", "2026-03-15", "3,188.81"], ["Q2", "2026-06-15", "3,188.81"], ["Q3", "2026-09-15", "3,188.81"], ["Q4", "2026-12-15", "3,188.81"]], [300, 300, 300], fs=34)
    dr.text((60, 700), "Instalments are likely required when net tax owing exceeds $3,000 ($1,800 in Quebec) — and that was also true in one of the last two years.", font=font(30), fill=GREY)
    dr.rectangle([60, 850, 1940, 1500], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 880), "What you get", font=font(40, True), fill=NAVY)
    for i, t in enumerate(["One Planner sheet: inputs, full breakdown, set-aside, instalments", "Province dropdown drives every rate automatically", "2026 edition; validated by an automated test across three scenarios", "Bookkeeping tool, not tax advice — see the honest note inside"]):
        dr.text((140, 960 + i * 90), "• " + t, font=font(34), fill=(30, 30, 30))
    im.save(IMG / "03-instalments.png")

def build():
    OUT.mkdir(parents=True, exist_ok=True); images()
    (OUT / "listing-copy.txt").write_text(f"TITLE ({len(L['title'])} chars)\n{L['title']}\n\nTAGS ({len(L['tags'])})\n" + ", ".join(L["tags"]) + f"\n\nPRICE CA${L['price_cad']:.2f}\n\nDESCRIPTION\n{L['description']}\n")
    print("images:", sorted(p.name for p in IMG.iterdir()))

if __name__ == "__main__": build()
