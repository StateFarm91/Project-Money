#!/usr/bin/env python3
"""Build the customer package and listing images for listing 1.
Outputs: dist/listing-1/<zip>, dist/listing-1/QuickStart.pdf, dist/listing-1/README.txt, dist/listing-1/images/*.png
Usage: .venv/bin/python products/etsy-templates/package.py"""
import json, pathlib, zipfile, datetime, textwrap
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.units import inch

HERE = pathlib.Path(__file__).parent; DIST = HERE / "dist"; OUT = DIST / "listing-1"; IMG = OUT / "images"
XLSX = DIST / "Canadian-Sole-Proprietor-Bookkeeping-T2125-2026.xlsx"
L = json.load(open(HERE / "listings.json"))["listing-1"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"; FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
NAVY = (31, 58, 95); CREAM = (255, 248, 220); BLUE = (238, 243, 248); GREY = (90, 90, 90); WHITE = (255, 255, 255); RED = (170, 40, 40)

README = f"""Canadian Sole Proprietor Bookkeeping System — T2125 edition 2026 (v1.0)
Thank you for your purchase.

FILES
- Canadian-Sole-Proprietor-Bookkeeping-T2125-2026.xlsx  (the workbook; opens in Excel 2016+ and Google Sheets)
- QuickStart.pdf  (5-minute setup and a tour of every sheet)
- README.txt  (this file)

GOOGLE SHEETS
Open sheets.google.com > File > Import > Upload > choose the .xlsx > "Replace spreadsheet". Dropdowns and formulas carry over.

FIRST STEPS
1. "Start here": type your business name, pick your province, answer the GST/HST questions.
2. Delete the three example rows on Income and Expenses (they are marked "delete me").
3. Add income and expenses as they happen. Everything else calculates.

SUPPORT AND REFUNDS
Message the shop on Etsy with a screenshot if anything does not work; we fix it or refund it.

IMPORTANT
This workbook is a bookkeeping tool, not tax, legal or accounting advice. Rates and CRA line numbers were checked in September 2026 for the 2026 tax year; verify with CRA or an accountant before filing. Keep your receipts for six years.
Sources used for rates: canada.ca (RC4058 quick method; T2125 expenses and business-use-of-home pages), Retail Council of Canada sales-tax table.
"""

def quickstart_pdf(path):
    ss = getSampleStyleSheet(); h = ParagraphStyle("h", parent=ss["Heading2"], textColor="#1F3A5F"); body = ss["BodyText"]; body.leading = 14
    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.9*inch, rightMargin=0.9*inch, topMargin=0.8*inch, bottomMargin=0.8*inch, title="Quick start — Canadian Sole Proprietor Bookkeeping System", author="MapleSheets")
    S = []
    S.append(Paragraph("Quick start — Canadian Sole Proprietor Bookkeeping System (T2125 edition 2026)", ss["Title"]))
    S.append(Paragraph("Version 1.0 · Works in Excel and Google Sheets · Bookkeeping tool, not tax advice", ss["Italic"])); S.append(Spacer(1, 10))
    def sec(title, items, ordered=False):
        S.append(Paragraph(title, h)); S.append(ListFlowable([ListItem(Paragraph(i, body)) for i in items], bulletType="1" if ordered else "bullet", leftIndent=14)); S.append(Spacer(1, 6))
    sec("Five-minute setup", ["Open the workbook (Excel) or import it into Google Sheets: File > Import > Upload > Replace spreadsheet.",
        "On <b>Start here</b>, fill the yellow cells: business name, fiscal year, province, whether you are registered for GST/HST, whether you charge PST/QST, whether you elected the quick method, your business type, filing frequency, and a tax set-aside percentage.",
        "Delete the example rows on <b>Income</b> and <b>Expenses</b> (marked 'delete me').",
        "Start logging. Yellow cells are yours; blue cells calculate."], ordered=True)
    sec("Sheet by sheet", ["<b>Income</b>: one row per sale or invoice. Enter the amount before tax; GST/HST and PST/QST fill in from your settings. Mark Paid? to track receivables.",
        "<b>Expenses</b>: one row per receipt. Choose the T2125 category from the dropdown. Meals and entertainment are limited to 50% automatically. Home-office and vehicle costs go on their own sheets, not here.",
        "<b>Home office</b>: enter your space measurements and yearly home costs. The sheet applies the business-use percentage, the loss cap (7N) and the carry-forward (7O) and produces the allowable claim (7P) for line 9945.",
        "<b>Vehicle</b>: keep the logbook (the CRA can ask for it). Enter total kilometres and actual yearly costs; the deductible part is costs × business-use %. Parking for business is 100%.",
        "<b>T2125 Summary</b>: every Part 4 line (8521 to 9270, 9936), total expenses (9368), net income (9369), home office (9945) and net income (9946). Copy the numbers into your tax software.",
        "<b>GST-HST</b>: quarterly sales, tax collected and input tax credits; net tax under the regular method; the quick-method calculation with the RC4058 rate for your province and business type and the 1% credit on the first $30,000; which method remits less; and the $30,000 small-supplier tracker.",
        "<b>Dashboard</b>: month-by-month income, expenses, net, tax set-aside and unpaid invoices, plus the year's headline numbers.",
        "<b>Lists</b>: the rate tables and dropdown lists. Edit only if a rate changes."])
    sec("Frequently asked", ["<b>I am not registered for GST/HST.</b> Leave 'Registered' at No: no tax is added to income and no ITCs are counted. Watch the small-supplier status on the GST-HST sheet; when it says you must register, register within 29 days.",
        "<b>Quick method or regular method?</b> The GST-HST sheet compares both for your numbers. The quick method is available if your worldwide taxable supplies are $400,000 or less and you file the election (Form GST74 or My Business Account).",
        "<b>Can I claim a per-kilometre amount?</b> Not on T2125. Self-employed people deduct actual vehicle costs times the business-use percentage.",
        "<b>Google Sheets shows a formula warning.</b> All formulas use standard functions; if a warning appears, re-import the original file rather than copying sheets across.",
        "<b>Something is wrong or unclear.</b> Message the shop with a screenshot. Fixes are free; if it is not right for you, ask for a refund."])
    sec("Sources checked (September 2026)", ["CRA RC4058 Quick Method of Accounting for GST/HST (remittance rates, eligibility, 1% credit).",
        "CRA Form T2125 expenses section (line numbers) and business-use-of-home pages (Part 7).",
        "CRA GST/HST registration rules (small-supplier $30,000 test).",
        "Retail Council of Canada sales-tax rates by province."])
    S.append(Spacer(1, 8)); S.append(Paragraph("<b>Important.</b> This workbook is a bookkeeping tool, not tax, legal or accounting advice. Verify anything that affects your return with the CRA or an accountant. Keep receipts for six years.", body))
    doc.build(S)

def font(sz, bold=False): return ImageFont.truetype(FONTB if bold else FONT, sz)

def table(dr, x, y, cols, rows, widths, fs=30, head=True, rowh=None):
    rowh = rowh or int(fs * 1.9); f = font(fs); fb = font(fs, True)
    if head:
        dr.rectangle([x, y, x + sum(widths), y + rowh], fill=NAVY); cx = x
        for c, w in zip(cols, widths): dr.text((cx + 14, y + rowh * 0.25), c, font=fb, fill=WHITE); cx += w
        y += rowh
    for i, r in enumerate(rows):
        dr.rectangle([x, y, x + sum(widths), y + rowh], fill=BLUE if i % 2 else WHITE, outline=(200, 200, 200)); cx = x
        for c, w in zip(r, widths):
            dr.text((cx + 14, y + rowh * 0.25), str(c), font=f, fill=(30, 30, 30)); cx += w
        y += rowh
    return y

def canvas(title, subtitle=None):
    im = Image.new("RGB", (2000, 2000), WHITE); dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, 2000, 230], fill=NAVY)
    dr.text((80, 60), title, font=font(64, True), fill=WHITE)
    if subtitle: dr.text((80, 145), subtitle, font=font(38), fill=(210, 225, 240))
    dr.text((80, 1930), "MapleSheets · T2125 edition 2026 · Excel + Google Sheets · Example data shown", font=font(28), fill=GREY)
    return im, dr

def images():
    IMG.mkdir(parents=True, exist_ok=True)
    # 1 hero
    im, dr = canvas("Canadian Bookkeeping Spreadsheet", "For sole proprietors · T2125 mapped · GST/HST/PST/QST by province")
    y = 300
    for line in ["✓ Every expense category = a T2125 line (8521 → 9270)", "✓ Sales tax calculated for your province", "✓ Quick method vs regular method (RC4058 rates)", "✓ $30,000 small-supplier tracker", "✓ Home office (Part 7) and vehicle (Chart A) schedules", "✓ Monthly dashboard with tax set-aside", "✓ Excel + Google Sheets · Quick-start PDF"]:
        dr.text((100, y), line, font=font(50), fill=NAVY); y += 88
    dr.rectangle([100, 960, 1900, 1840], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 990), "Dashboard (example)", font=font(40, True), fill=NAVY)
    table(dr, 140, 1060, ["Month", "Income", "Expenses", "Net", "Tax set-aside"], [["Jan 2026", "1,500.00", "20.00", "1,480.00", "370.00"], ["Feb 2026", "29.00", "30.00", "-1.00", "0.00"], ["Mar 2026", "800.00", "45.00", "755.00", "188.75"], ["Year", "2,329.00", "95.00", "2,234.00", "558.75"]], [360, 320, 320, 320, 400], fs=34)
    im.save(IMG / "01-hero.png")
    # 2 income
    im, dr = canvas("Income sheet", "Type the amount before tax — GST/HST and PST/QST fill in from your province")
    table(dr, 60, 320, ["Date", "Customer", "Description", "Channel", "Before tax", "GST/HST", "PST/QST", "Total", "Paid?"], [["2026-01-12", "Example Co.", "Consulting invoice", "Direct", "1,500.00", "195.00", "0.00", "1,695.00", "Yes"], ["2026-02-03", "Etsy buyer", "Digital product", "Etsy", "29.00", "3.77", "0.00", "32.77", "Yes"], ["2026-03-20", "Example Ltd.", "Retainer", "Direct", "800.00", "104.00", "0.00", "904.00", "No"]], [220, 230, 300, 150, 200, 180, 180, 200, 130], fs=28)
    dr.text((60, 700), "Shown with 'Registered for GST/HST = Yes' in Ontario (13% HST). Not registered? The tax columns stay at 0.", font=font(32), fill=GREY)
    dr.rectangle([60, 800, 1940, 1800], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 830), "Totals at a glance", font=font(40, True), fill=NAVY)
    table(dr, 100, 900, ["", "Amount"], [["Sales before tax", "2,329.00"], ["GST/HST collected", "302.77"], ["PST/QST collected", "0.00"], ["Unpaid invoices", "904.00"]], [700, 400], fs=36, head=False)
    dr.text((100, 1300), "500 rows per ledger · dropdowns for channel and Paid? · dates in yyyy-mm-dd", font=font(34), fill=GREY)
    im.save(IMG / "02-income.png")
    # 3 expenses
    im, dr = canvas("Expenses sheet", "Pick the CRA category from a dropdown — meals are limited to 50% automatically")
    table(dr, 60, 320, ["Date", "Vendor", "Category (T2125 line)", "Before tax", "GST/HST", "Deductible", "ITC"], [["2026-01-15", "Example Software", "8810 Office expenses", "20.00", "2.60", "20.00", "2.60"], ["2026-02-10", "Example Café", "8523 Meals and entertainment", "60.00", "7.80", "30.00", "3.90"], ["2026-03-01", "Example Ads", "8521 Advertising", "45.00", "5.85", "45.00", "5.85"]], [220, 300, 560, 200, 180, 220, 180], fs=28)
    dr.text((60, 720), "Categories in the dropdown", font=font(40, True), fill=NAVY)
    cats = ["8521 Advertising", "8523 Meals and entertainment", "8590 Bad debts", "8690 Insurance", "8710 Interest and bank charges", "8760 Business taxes, licences", "8810 Office expenses", "8811 Office stationery", "8860 Professional fees", "8871 Management fees", "8910 Rent", "8960 Repairs and maintenance", "9060 Salaries and wages", "9180 Property taxes", "9200 Travel", "9220 Utilities", "9224 Fuel (not vehicles)", "9275 Delivery and freight", "9270 Other expenses", "9936 Capital cost allowance", "Home office → own sheet", "Vehicle → own sheet", "Personal (not deductible)"]
    for i, c in enumerate(cats):
        col, row = divmod(i, 12); dr.text((100 + col * 900, 800 + row * 62), "▸ " + c, font=font(34), fill=(30, 30, 30))
    im.save(IMG / "03-expenses.png")
    # 4 t2125
    im, dr = canvas("T2125 Summary", "Every line adds itself up — copy the numbers into your tax software")
    rows = [["8000 Gross sales (before tax)", "2,329.00"], ["8521 Advertising", "45.00"], ["8523 Meals and entertainment (50%)", "30.00"], ["8810 Office expenses", "20.00"], ["9281 Motor vehicle (from Vehicle sheet)", "0.00"], ["9936 Capital cost allowance", "0.00"], ["9368 Total expenses", "95.00"], ["9369 Net income before adjustments", "2,234.00"], ["9945 Business-use-of-home (7P)", "0.00"], ["9946 Net income", "2,234.00"]]
    table(dr, 100, 320, ["T2125 line", "Amount"], rows, [1300, 500], fs=36)
    dr.text((100, 1200), "All 20 Part 4 lines are in the workbook; this preview shows the ones with example data.", font=font(32), fill=GREY)
    dr.rectangle([100, 1300, 1900, 1800], fill=CREAM, outline=NAVY, width=4)
    dr.text((140, 1340), "Also included", font=font(40, True), fill=NAVY)
    for i, t in enumerate(["Home office: Part 7 lines 7A–7P with the loss cap and carry-forward", "Vehicle: logbook + Chart A actual-cost method × business-use %", "GST-HST: regular vs quick method and the $30,000 tracker", "Dashboard: monthly view and tax set-aside"]):
        dr.text((140, 1420 + i * 80), "• " + t, font=font(36), fill=(30, 30, 30))
    im.save(IMG / "04-t2125.png")
    # 5 gst
    im, dr = canvas("GST/HST sheet", "Regular method vs quick method (RC4058) and the small-supplier tracker")
    table(dr, 60, 320, ["", "Q1", "Q2", "Q3", "Q4", "Year"], [["Sales before tax", "2,329.00", "0.00", "0.00", "0.00", "2,329.00"], ["GST/HST collected", "302.77", "0.00", "0.00", "0.00", "302.77"], ["ITC-eligible tax paid", "12.35", "0.00", "0.00", "0.00", "12.35"], ["Regular method: net tax", "290.42", "0.00", "0.00", "0.00", "290.42"]], [520, 260, 260, 260, 260, 300], fs=30)
    table(dr, 60, 720, ["Quick method (Ontario, services)", ""], [["Rate charged", "13%"], ["RC4058 remittance rate", "8.8%"], ["Eligible supplies incl. tax", "2,631.77"], ["Remittance before credit", "231.60"], ["1% credit on first $30,000", "26.32"], ["Net tax to remit", "205.28"], ["Which remits less this year?", "Quick method"]], [900, 500], fs=32)
    dr.rectangle([60, 1420, 1940, 1800], fill=CREAM, outline=NAVY, width=4)
    dr.text((100, 1450), "Small-supplier tracker", font=font(40, True), fill=NAVY)
    dr.text((100, 1530), "Highest single quarter: 2,329.00   Last four quarters: 2,329.00", font=font(34), fill=(30, 30, 30))
    dr.text((100, 1600), "Status: Small supplier  (turns red at $30,000: 'you must register for GST/HST')", font=font(34), fill=(30, 30, 30))
    dr.text((100, 1690), "Rates for all 13 provinces and territories and both RC4058 tables are built in.", font=font(32), fill=GREY)
    im.save(IMG / "05-gst-hst.png")
    # 6 what's inside
    im, dr = canvas("What you get", "Instant download · ZIP with the workbook, quick-start PDF and README")
    items = [("Workbook (.xlsx)", "9 sheets: Start here, Dashboard, Income, Expenses, Home office, Vehicle, T2125 Summary, GST-HST, Lists"), ("Google Sheets ready", "File > Import > Replace spreadsheet. Dropdowns and formulas carry over. No macros, no add-ons."), ("Quick-start PDF", "Five-minute setup, a tour of every sheet, FAQ and the CRA sources used."), ("2026 tax-year edition", "Rates and CRA line numbers checked September 2026; version stamp inside; validated by automated tests."), ("Support", "Message the shop; we fix problems or refund."), ("Honest note", "Bookkeeping tool, not tax advice. Built by a small Canadian shop with AI assistance in building and checking the formulas.")]
    y = 320
    for t, d in items:
        dr.text((100, y), t, font=font(46, True), fill=NAVY); y += 66
        for ln in textwrap.wrap(d, 70): dr.text((100, y), ln, font=font(36), fill=(30, 30, 30)); y += 50
        y += 40
    im.save(IMG / "06-whats-inside.png")

def build():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "README.txt").write_text(README); quickstart_pdf(OUT / "QuickStart.pdf"); images()
    z = OUT / L["files"][0]
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(XLSX, XLSX.name); zf.write(OUT / "QuickStart.pdf", "QuickStart.pdf"); zf.write(OUT / "README.txt", "README.txt")
    print("package:", z, f"{z.stat().st_size/1e6:.2f} MB"); print("images:", sorted(p.name for p in IMG.iterdir()))
    (OUT / "listing-copy.txt").write_text(f"TITLE ({len(L['title'])} chars)\n{L['title']}\n\nTAGS ({len(L['tags'])})\n" + ", ".join(L["tags"]) + f"\n\nPRICE CA${L['price_cad']:.2f}\n\nDESCRIPTION\n{L['description']}\n")
    assert z.stat().st_size < 20e6

if __name__ == "__main__": build()
