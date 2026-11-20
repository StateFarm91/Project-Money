#!/usr/bin/env python3
"""Listing images + copy file for listing 3. Usage: .venv/bin/python products/etsy-templates/package3.py"""
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from package import canvas, table, font, NAVY, CREAM, GREY, DIST
HERE = pathlib.Path(__file__).parent; OUT = DIST / "listing-3"; IMG = OUT / "images"
L = json.load(open(HERE / "listings.json"))["listing-3"]

def images():
    IMG.mkdir(parents=True, exist_ok=True)
    im, dr = canvas("Home Office and Vehicle Expense Tracker", "T2125 Part 7 · Chart A · loss cap and carry-forward handled")
    y = 300
    for line in ["✓ Business-use-of-home % from your space and hours", "✓ All seven cost lines (7A heat → 7G other)",
                 "✓ Loss cap (7N) and carry-forward (7O) calculated for you", "✓ 200-row vehicle logbook + printable page",
                 "✓ Actual-cost vehicle deduction × business-use %", "✓ Shows exactly which CRA line each number goes on",
                 "✓ Excel + Google Sheets"]:
        dr.text((100, y), line, font=font(48), fill=NAVY); y += 84
    dr.rectangle([100, 990, 1900, 1840], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 1020), "Example: 300 sq ft of 1200, net income $500", font=font(40, True), fill=NAVY)
    table(dr, 140, 1090, ["", "Amount"], [["Business-use %", "25%"], ["7M total available", "875.00"], ["7N net income cap", "500.00"], ["7P allowable claim → 9945", "500.00"], ["7O carried forward", "375.00"]], [700, 500], fs=34, head=False)
    im.save(IMG / "01-hero.png")

    im, dr = canvas("Home office", "Enter your space and yearly costs — the loss cap applies itself")
    table(dr, 60, 320, ["", "Amount"], [["7A Heat", "2,000.00"], ["7B Electricity", "1,500.00"], ["Subtotal", "3,500.00"], ["Personal-use part (75%)", "2,625.00"], ["7M Total available", "875.00"], ["7N Net income (cap)", "500.00"], ["7P Allowable claim → 9945", "500.00"], ["7O Carried forward", "375.00"]], [560, 320], fs=32)
    dr.text((60, 1080), "The claim can never create or increase a loss. Anything above your net income carries forward to next year automatically.", font=font(32), fill=GREY)
    dr.rectangle([60, 1180, 1940, 1800], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 1210), "All seven cost lines", font=font(40, True), fill=NAVY)
    for i, t in enumerate(["7A Heat  ·  7B Electricity  ·  7C Insurance  ·  7D Maintenance", "7E Mortgage interest  ·  7F Property taxes  ·  7G Other (rent, internet, condo fees)", "7K CCA on the home (optional)  ·  7L Carry-forward from last year"]):
        dr.text((140, 1290 + i * 90), "• " + t, font=font(34), fill=(30, 30, 30))
    im.save(IMG / "02-home-office.png")

    im, dr = canvas("Vehicle", "200-row logbook + actual-cost deduction — no per-km claims on T2125")
    table(dr, 60, 320, ["Date", "From", "To", "Purpose", "Km", "Business?"], [["2026-01-20", "Home", "Client office", "Client meeting", "34", "Yes"]], [220, 250, 250, 400, 120, 160], fs=30)
    table(dr, 60, 480, ["", "Amount"], [["Business km (logbook)", "34"], ["Total km driven this year", "12,000"], ["Business-use %", "0.28%"], ["Total vehicle costs (fuel, insurance, etc.)", "3,000.00"], ["Deductible part (costs × %) → 9281", "8.50"], ["Business parking (100%)", "0.00"]], [700, 400], fs=32)
    dr.text((60, 900), "Self-employed drivers deduct ACTUAL costs × business-use %, never a cents-per-km rate — this workbook does the math for you.", font=font(32), fill=GREY)
    dr.rectangle([60, 1000, 1940, 1500], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 1030), "Also included", font=font(40, True), fill=NAVY)
    for i, t in enumerate(["Printable logbook page for the glovebox", "CCA line for the vehicle (9936) if you claim it", "Every result labelled with its exact CRA line"]):
        dr.text((140, 1110 + i * 90), "• " + t, font=font(34), fill=(30, 30, 30))
    im.save(IMG / "03-vehicle.png")

def build():
    OUT.mkdir(parents=True, exist_ok=True); images()
    (OUT / "listing-copy.txt").write_text(f"TITLE ({len(L['title'])} chars)\n{L['title']}\n\nTAGS ({len(L['tags'])})\n" + ", ".join(L["tags"]) + f"\n\nPRICE CA${L['price_cad']:.2f}\n\nDESCRIPTION\n{L['description']}\n")
    print("images:", sorted(p.name for p in IMG.iterdir()))

if __name__ == "__main__": build()
