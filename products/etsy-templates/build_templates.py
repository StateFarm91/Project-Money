#!/usr/bin/env python3
"""Build the Canadian Sole Proprietor Bookkeeping System workbook (Listing 1).
Usage: .venv/bin/python products/etsy-templates/build_templates.py [--out dist]
Formulas are restricted to functions that behave identically in Excel and Google Sheets
(SUM, SUMIFS, INDEX, MATCH, IF, IFERROR, MIN, MAX, AND, OR, DATE, EOMONTH, ROUND, COUNTIF, TEXT).
Facts (rates, lines) come from TAX_REFERENCE.md; change TAX_YEAR and the tables together."""
import argparse, pathlib, datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule

TAX_YEAR = 2026
VERSION = "1.0"
ROWS = 500  # data rows per ledger sheet

PROVINCES = [  # name, GST, HST, PST/QST, quick-method PE column (1=5%,2=13%,3=14%,4=15%)
    ("Alberta", 0.05, 0, 0, 1), ("British Columbia", 0.05, 0, 0.07, 1), ("Manitoba", 0.05, 0, 0.07, 1),
    ("New Brunswick", 0, 0.15, 0, 4), ("Newfoundland and Labrador", 0, 0.15, 0, 4), ("Northwest Territories", 0.05, 0, 0, 1),
    ("Nova Scotia", 0, 0.14, 0, 3), ("Nunavut", 0.05, 0, 0, 1), ("Ontario", 0, 0.13, 0, 2),
    ("Prince Edward Island", 0, 0.15, 0, 4), ("Quebec", 0.05, 0, 0.09975, 1), ("Saskatchewan", 0.05, 0, 0.06, 1), ("Yukon", 0.05, 0, 0, 1),
]
# RC4058 quick-method remittance rates: rows = rate charged (5,13,14,15), cols = PE (5,13,14,15)
QM_SERVICES = [[0.036, 0.018, 0.016, 0.014], [0.105, 0.088, 0.086, 0.084], [0.113, 0.096, 0.094, 0.092], [0.120, 0.104, 0.102, 0.100]]
QM_GOODS = [[0.018, 0.0, 0.0, 0.0], [0.088, 0.044, 0.039, 0.033], [0.096, 0.053, 0.047, 0.042], [0.104, 0.061, 0.056, 0.050]]
QM_GOODS_CREDIT = [0.0, 0.028, 0.034, 0.040]  # credit for 5% supplies from an HST PE (goods)
CATEGORIES = [
    "8521 Advertising", "8523 Meals and entertainment", "8590 Bad debts", "8690 Insurance", "8710 Interest and bank charges",
    "8760 Business taxes, licences, memberships", "8810 Office expenses", "8811 Office stationery and supplies",
    "8860 Professional fees (legal, accounting)", "8871 Management and administration fees", "8910 Rent", "8960 Repairs and maintenance",
    "9060 Salaries, wages, benefits", "9180 Property taxes", "9200 Travel expenses", "9220 Utilities", "9224 Fuel costs (not vehicles)",
    "9275 Delivery, freight, express", "9270 Other expenses", "9936 Capital cost allowance (CCA)",
    "Home office (enter on Home office sheet)", "Vehicle (enter on Vehicle sheet)", "Personal (not deductible)",
]
T2125_LINES = CATEGORIES[:20]
CHANNELS = ["Etsy", "Shopify", "Direct / invoice", "Amazon", "Other"]
YESNO = ["Yes", "No"]
BIZTYPE = ["Services", "Goods for resale"]
FREQ = ["Annual", "Quarterly", "Monthly"]

H1 = Font(bold=True, size=16, color="1F3A5F"); H2 = Font(bold=True, size=12, color="1F3A5F"); B = Font(bold=True)
HEAD_FILL = PatternFill("solid", fgColor="1F3A5F"); HEAD_FONT = Font(bold=True, color="FFFFFF")
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC"); CALC_FILL = PatternFill("solid", fgColor="EEF3F8"); NOTE = Font(italic=True, color="666666", size=9)
THIN = Side(style="thin", color="BBBBBB"); BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY = '#,##0.00;[Red]-#,##0.00'; PCT = '0.00%'; DATEF = 'yyyy-mm-dd'

def header(ws, row, labels, widths=None):
    for i, lab in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=lab); c.fill = HEAD_FILL; c.font = HEAD_FONT; c.alignment = Alignment(wrap_text=True, vertical="center"); c.border = BOX
    if widths:
        for i, w in enumerate(widths, 1): ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[row].height = 30

def dv(ws, formula, rng, allow_blank=True):
    d = DataValidation(type="list", formula1=formula, allow_blank=allow_blank, showErrorMessage=True, errorTitle="Pick from the list", error="Please choose a value from the dropdown.")
    ws.add_data_validation(d); d.add(rng); return d

def build():
    wb = Workbook()
    # ---------- Lists ----------
    L = wb.active; L.title = "Lists"
    header(L, 1, ["Province", "GST", "HST", "PST/QST", "Quick-method PE column"], [26, 8, 8, 10, 22])
    for i, (n, g, h, p, col) in enumerate(PROVINCES, 2):
        L.cell(i, 1, n); L.cell(i, 2, g).number_format = PCT; L.cell(i, 3, h).number_format = PCT; L.cell(i, 4, p).number_format = PCT; L.cell(i, 5, col)
    L["G1"] = "Quick method — services (rows: rate charged 5/13/14/15; cols: PE 5/13/14/15)"; L["G1"].font = B
    for r, row in enumerate(QM_SERVICES, 2):
        L.cell(r, 7, [5, 13, 14, 15][r - 2])
        for c, v in enumerate(row, 8): L.cell(r, c, v).number_format = PCT
    L["G7"] = "Quick method — goods for resale"; L["G7"].font = B
    for r, row in enumerate(QM_GOODS, 8):
        L.cell(r, 7, [5, 13, 14, 15][r - 8])
        for c, v in enumerate(row, 8): L.cell(r, c, v).number_format = PCT
    L["G13"] = "Goods credit on 5% supplies from HST PE"; L["G13"].font = B
    for c, v in enumerate(QM_GOODS_CREDIT, 8): L.cell(14, c, v).number_format = PCT
    L["M1"] = "Categories"; L["M1"].font = B
    for i, c in enumerate(CATEGORIES, 2): L.cell(i, 13, c)
    L["N1"] = "Channels"; L["N1"].font = B
    for i, c in enumerate(CHANNELS, 2): L.cell(i, 14, c)
    L["O1"] = "YesNo"; L["O1"].font = B
    for i, c in enumerate(YESNO, 2): L.cell(i, 15, c)
    L["P1"] = "BizType"; L["P1"].font = B
    for i, c in enumerate(BIZTYPE, 2): L.cell(i, 16, c)
    L["Q1"] = "Freq"; L["Q1"].font = B
    for i, c in enumerate(FREQ, 2): L.cell(i, 17, c)
    L.column_dimensions["M"].width = 42; L.column_dimensions["N"].width = 16
    L["A17"] = f"Source: CRA RC4058 and provincial rates as of 2026-09 (see TAX_REFERENCE). Version {VERSION}, tax year {TAX_YEAR}."; L["A17"].font = NOTE

    # ---------- Start here ----------
    S = wb.create_sheet("Start here", 0)
    S.column_dimensions["A"].width = 3; S.column_dimensions["B"].width = 34; S.column_dimensions["C"].width = 28; S.column_dimensions["D"].width = 70
    S["B2"] = f"Canadian Sole Proprietor Bookkeeping System — T2125 edition {TAX_YEAR}"; S["B2"].font = H1
    S["B3"] = "Track income and expenses all year, then copy the T2125 Summary into your tax software. Works in Excel and Google Sheets."; S["B3"].font = NOTE
    S["B5"] = "1. Your settings (yellow cells)"; S["B5"].font = H2
    settings = [("Business name", "My Business", None, "Shown on the dashboard."),
                ("Fiscal year (calendar year)", TAX_YEAR, None, "Most sole proprietors use the calendar year."),
                ("Province of your business", "Ontario", "Lists!$A$2:$A$14", "Drives GST/HST and PST/QST rates."),
                ("Registered for GST/HST?", "No", "Lists!$O$2:$O$3", "You must register once you pass $30,000 in a quarter or over four consecutive quarters (small-supplier rule). See the GST-HST sheet."),
                ("Charge PST / QST?", "No", "Lists!$O$2:$O$3", "Only if you are registered provincially (BC, SK, MB, QC)."),
                ("Elected the quick method?", "No", "Lists!$O$2:$O$3", "Form GST74 / My Business Account. Compare both methods on the GST-HST sheet."),
                ("Business type (quick method)", "Services", "Lists!$P$2:$P$3", "Goods for resale uses the lower RC4058 rates."),
                ("GST/HST filing frequency", "Annual", "Lists!$Q$2:$Q$4", "Annual is the default under $1.5M in sales."),
                ("Income tax set-aside %", 0.25, None, "Rule of thumb to reserve for income tax + CPP. Adjust for your bracket.")]
    for i, (lab, val, lst, note) in enumerate(settings, 6):
        S.cell(i, 2, lab).font = B; c = S.cell(i, 3, val); c.fill = INPUT_FILL; c.border = BOX; S.cell(i, 4, note).font = NOTE
        if lst: dv(S, lst, f"C{i}")
    S["C14"].number_format = PCT
    S["B16"] = "2. Rates in use (calculated)"; S["B16"].font = H2
    S["B17"] = "GST rate"; S["C17"] = "=IFERROR(INDEX(Lists!$B$2:$B$14,MATCH($C$8,Lists!$A$2:$A$14,0)),0)"
    S["B18"] = "HST rate"; S["C18"] = "=IFERROR(INDEX(Lists!$C$2:$C$14,MATCH($C$8,Lists!$A$2:$A$14,0)),0)"
    S["B19"] = "PST / QST rate"; S["C19"] = "=IFERROR(INDEX(Lists!$D$2:$D$14,MATCH($C$8,Lists!$A$2:$A$14,0)),0)"
    S["B20"] = "GST/HST rate you charge"; S["C20"] = "=C17+C18"
    S["B21"] = "Combined sales-tax rate"; S["C21"] = "=C20+IF($C$10=\"Yes\",C19,0)"
    S["B22"] = "Quick-method PE column"; S["C22"] = "=IFERROR(INDEX(Lists!$E$2:$E$14,MATCH($C$8,Lists!$A$2:$A$14,0)),1)"
    for r in range(17, 22): S.cell(r, 3).number_format = PCT; S.cell(r, 3).fill = CALC_FILL
    S["C22"].fill = CALC_FILL
    S["B24"] = "3. How to use"; S["B24"].font = H2
    steps = ["Income sheet: one row per sale or invoice. Tax columns fill in automatically from your settings.",
             "Expenses sheet: one row per receipt. Pick the category (T2125 line). Meals are automatically limited to 50%.",
             "Home office and Vehicle sheets: enter the yearly figures; the deductible parts flow to the T2125 Summary.",
             "GST-HST sheet: see what you owe under the regular method and the quick method, and track the $30,000 small-supplier threshold.",
             "T2125 Summary: copy the line amounts into your tax software or hand the sheet to your accountant.",
             "Google Sheets: File > Import > Upload this file > 'Replace spreadsheet'. Dropdowns and formulas carry over.",
             "Delete the three example rows on the Income and Expenses sheets before you start."]
    for i, s in enumerate(steps, 25): S.cell(i, 2, f"{i-24}. {s}")
    S["B33"] = "Important"; S["B33"].font = H2
    S["B34"] = ("This workbook is a bookkeeping tool, not tax, legal or accounting advice. Rates and CRA line numbers were checked in September 2026 for the "
                f"{TAX_YEAR} tax year; verify against current CRA guidance or with an accountant before filing. Keep receipts for six years (CRA rule).")
    S["B34"].alignment = Alignment(wrap_text=True, vertical="top"); S.merge_cells("B34:D36"); S.row_dimensions[34].height = 48
    S["B38"] = f"Version {VERSION} · Built with care (and with AI assistance) in Canada."; S["B38"].font = NOTE

    # ---------- Income ----------
    I = wb.create_sheet("Income")
    I["A1"] = "Income"; I["A1"].font = H1; I["A2"] = "One row per sale/invoice. Enter the amount BEFORE tax; tax columns calculate from your settings. Yellow = you type, blue = calculated."; I["A2"].font = NOTE
    header(I, 4, ["Date", "Customer", "Description", "Channel", "Invoice #", "Amount before tax", "GST/HST collected", "PST/QST collected", "Total invoiced", "Paid?", "Notes"], [12, 22, 30, 14, 12, 16, 16, 16, 16, 8, 30])
    first, last = 5, 4 + ROWS
    for r in range(first, last + 1):
        I.cell(r, 1).number_format = DATEF
        for col in (1, 2, 3, 4, 5, 6, 10, 11): I.cell(r, col).fill = INPUT_FILL
        I.cell(r, 6).number_format = MONEY
        I.cell(r, 7, f'=IF(F{r}="","",IF(\'Start here\'!$C$9="Yes",ROUND(F{r}*\'Start here\'!$C$20,2),0))')
        I.cell(r, 8, f'=IF(F{r}="","",IF(\'Start here\'!$C$10="Yes",ROUND(F{r}*\'Start here\'!$C$19,2),0))')
        I.cell(r, 9, f'=IF(F{r}="","",F{r}+G{r}+H{r})')
        for col in (7, 8, 9): I.cell(r, col).number_format = MONEY; I.cell(r, col).fill = CALC_FILL
    dv(I, "Lists!$N$2:$N$6", f"D{first}:D{last}"); dv(I, "Lists!$O$2:$O$3", f"J{first}:J{last}")
    ex = [(datetime.date(TAX_YEAR, 1, 12), "Example Co.", "Example: consulting invoice (delete me)", "Direct / invoice", "INV-001", 1500, "Yes"),
          (datetime.date(TAX_YEAR, 2, 3), "Etsy buyer", "Example: digital product sale (delete me)", "Etsy", "", 29, "Yes"),
          (datetime.date(TAX_YEAR, 3, 20), "Example Ltd.", "Example: retainer (delete me)", "Direct / invoice", "INV-002", 800, "No")]
    for i, (d, cu, de, ch, inv, amt, paid) in enumerate(ex, first):
        I.cell(i, 1, d); I.cell(i, 2, cu); I.cell(i, 3, de); I.cell(i, 4, ch); I.cell(i, 5, inv); I.cell(i, 6, amt); I.cell(i, 10, paid)
    I.freeze_panes = "A5"
    I["M4"] = "Totals"; I["M4"].font = B
    I["M5"] = "Amount before tax"; I["N5"] = f"=SUM(F{first}:F{last})"
    I["M6"] = "GST/HST collected"; I["N6"] = f"=SUM(G{first}:G{last})"
    I["M7"] = "PST/QST collected"; I["N7"] = f"=SUM(H{first}:H{last})"
    I["M8"] = "Unpaid invoices"; I["N8"] = f'=SUMIFS(I{first}:I{last},J{first}:J{last},"No")'
    for r in range(5, 9): I.cell(r, 14).number_format = MONEY; I.cell(r, 14).fill = CALC_FILL
    I.column_dimensions["M"].width = 20; I.column_dimensions["N"].width = 16

    # ---------- Expenses ----------
    E = wb.create_sheet("Expenses")
    E["A1"] = "Expenses"; E["A1"].font = H1; E["A2"] = "One row per receipt. Pick the T2125 category. Meals & entertainment are limited to 50% automatically. Home-office and vehicle costs go on their own sheets."; E["A2"].font = NOTE
    header(E, 4, ["Date", "Vendor", "Description", "Category (T2125 line)", "Amount before tax", "GST/HST paid", "PST/QST paid", "Total paid", "Deductible (Part 4)", "ITC-eligible GST/HST", "Payment method", "Receipt ref", "Notes"], [12, 20, 30, 40, 16, 14, 14, 14, 16, 16, 14, 12, 30])
    for r in range(first, last + 1):
        E.cell(r, 1).number_format = DATEF
        for col in (1, 2, 3, 4, 5, 6, 7, 11, 12, 13): E.cell(r, col).fill = INPUT_FILL
        for col in (5, 6, 7): E.cell(r, col).number_format = MONEY
        E.cell(r, 8, f'=IF(E{r}="","",E{r}+F{r}+G{r})')
        E.cell(r, 9, f'=IF(E{r}="","",IF(D{r}="8523 Meals and entertainment",ROUND(E{r}*0.5,2),IF(OR(D{r}="Personal (not deductible)",D{r}="Home office (enter on Home office sheet)",D{r}="Vehicle (enter on Vehicle sheet)"),0,E{r})))')
        E.cell(r, 10, f'=IF(E{r}="","",IF(\'Start here\'!$C$9="Yes",IF(D{r}="8523 Meals and entertainment",ROUND(F{r}*0.5,2),IF(OR(D{r}="Personal (not deductible)",D{r}="Home office (enter on Home office sheet)",D{r}="Vehicle (enter on Vehicle sheet)"),0,F{r})),0))')
        for col in (8, 9, 10): E.cell(r, col).number_format = MONEY; E.cell(r, col).fill = CALC_FILL
    dv(E, "Lists!$M$2:$M$24", f"D{first}:D{last}")
    exe = [(datetime.date(TAX_YEAR, 1, 15), "Example Software Inc.", "Example: accounting app (delete me)", "8810 Office expenses", 20, 2.6, 0),
           (datetime.date(TAX_YEAR, 2, 10), "Example Café", "Example: client lunch (delete me)", "8523 Meals and entertainment", 60, 7.8, 0),
           (datetime.date(TAX_YEAR, 3, 1), "Example Ads", "Example: Etsy ads (delete me)", "8521 Advertising", 45, 5.85, 0)]
    for i, (d, v, de, cat, amt, g, p) in enumerate(exe, first):
        E.cell(i, 1, d); E.cell(i, 2, v); E.cell(i, 3, de); E.cell(i, 4, cat); E.cell(i, 5, amt); E.cell(i, 6, g); E.cell(i, 7, p)
    E.freeze_panes = "A5"

    # ---------- Home office ----------
    Hm = wb.create_sheet("Home office")
    Hm.column_dimensions["A"].width = 3; Hm.column_dimensions["B"].width = 46; Hm.column_dimensions["C"].width = 18; Hm.column_dimensions["D"].width = 60
    Hm["B2"] = "Business-use-of-home expenses (T2125 Part 7)"; Hm["B2"].font = H1
    Hm["B3"] = "Qualify if your home is your principal place of business (>50% of your work) OR the space is used only for business and regularly to meet clients. Enter yearly totals for the whole home."; Hm["B3"].font = NOTE; Hm["B3"].alignment = Alignment(wrap_text=True); Hm.merge_cells("B3:D3"); Hm.row_dimensions[3].height = 40
    Hm["B5"] = "Space"; Hm["B5"].font = H2
    Hm["B6"] = "Area used for business (sq ft or m²)"; Hm["C6"] = 150
    Hm["B7"] = "Total area of home"; Hm["C7"] = 1200
    Hm["B8"] = "Hours per week the space is used for business (24×7=168 if exclusive)"; Hm["C8"] = 168
    Hm["B9"] = "Business-use percentage"; Hm["C9"] = "=IFERROR(MIN(1,C6/C7)*MIN(1,C8/168),0)"; Hm["C9"].number_format = PCT; Hm["C9"].fill = CALC_FILL
    Hm["D9"] = "Area share × time share (time share = 100% if the room is used only for business)."; Hm["D9"].font = NOTE
    Hm["B11"] = "Yearly costs for the whole home"; Hm["B11"].font = H2
    lines = [("7A", "Heat"), ("7B", "Electricity"), ("7C", "Insurance"), ("7D", "Maintenance"), ("7E", "Mortgage interest"), ("7F", "Property taxes"), ("7G", "Other (rent, internet share, condo fees)")]
    for i, (code, lab) in enumerate(lines, 12):
        Hm.cell(i, 2, f"{code} {lab}"); c = Hm.cell(i, 3, 0); c.number_format = MONEY; c.fill = INPUT_FILL; c.border = BOX
    for r in range(6, 9): Hm.cell(r, 3).fill = INPUT_FILL; Hm.cell(r, 3).border = BOX
    Hm["B19"] = "Subtotal"; Hm["C19"] = "=SUM(C12:C18)"
    Hm["B20"] = "Personal-use part"; Hm["C20"] = "=ROUND(C19*(1-C9),2)"
    Hm["B21"] = "7K CCA on the home (business part; usually leave 0 — claiming CCA can affect the principal-residence exemption)"; Hm["C21"] = 0; Hm["C21"].fill = INPUT_FILL; Hm["C21"].border = BOX
    Hm["B22"] = "7L Carry-forward from previous year"; Hm["C22"] = 0; Hm["C22"].fill = INPUT_FILL; Hm["C22"].border = BOX
    Hm["B23"] = "7M Total available (subtotal − personal part + 7K + 7L)"; Hm["C23"] = "=C19-C20+C21+C22"
    Hm["B24"] = "7N Net income after adjustments (from T2125 Summary; cannot claim more than this)"; Hm["C24"] = "=MAX(0,'T2125 Summary'!$C$33)"
    Hm["B25"] = "7O Amount to carry forward to next year"; Hm["C25"] = "=MAX(0,C23-C24)"
    Hm["B26"] = "7P Allowable claim (lesser of 7M and 7N) → line 9945"; Hm["C26"] = "=MAX(0,MIN(C23,C24))"; Hm["B26"].font = B
    for r in (19, 20, 23, 24, 25, 26): Hm.cell(r, 3).number_format = MONEY; Hm.cell(r, 3).fill = CALC_FILL
    Hm["C21"].number_format = MONEY; Hm["C22"].number_format = MONEY

    # ---------- Vehicle ----------
    V = wb.create_sheet("Vehicle")
    V["A1"] = "Motor vehicle expenses (T2125 Chart A)"; V["A1"].font = H1
    V["A2"] = "Self-employed people deduct ACTUAL costs × business-use %. A cents-per-km claim is not allowed on T2125. Keep a logbook: the CRA can ask for it."; V["A2"].font = NOTE
    header(V, 4, ["Date", "From", "To", "Purpose", "Kilometres", "Business trip?"], [12, 18, 18, 30, 12, 14])
    for r in range(first, last + 1):
        V.cell(r, 1).number_format = DATEF
        for col in range(1, 7): V.cell(r, col).fill = INPUT_FILL
    dv(V, "Lists!$O$2:$O$3", f"F{first}:F{last}")
    V.cell(first, 1, datetime.date(TAX_YEAR, 1, 20)); V.cell(first, 2, "Home"); V.cell(first, 3, "Client office"); V.cell(first, 4, "Example: client meeting (delete me)"); V.cell(first, 5, 34); V.cell(first, 6, "Yes")
    V.column_dimensions["H"].width = 44; V.column_dimensions["I"].width = 16
    V["H4"] = "Kilometres"; V["H4"].font = B
    V["H5"] = "Business km (logbook rows marked Yes)"; V["I5"] = f'=SUMIFS(E{first}:E{last},F{first}:F{last},"Yes")'
    V["H6"] = "Total km driven this year (all use) — enter"; V["I6"] = 12000; V["I6"].fill = INPUT_FILL; V["I6"].border = BOX
    V["H7"] = "Business-use %"; V["I7"] = "=IFERROR(MIN(1,I5/I6),0)"; V["I7"].number_format = PCT
    V["H9"] = "Yearly vehicle costs (enter)"; V["H9"].font = B
    costs = ["Fuel and oil", "Insurance", "Licence and registration", "Maintenance and repairs", "Interest on vehicle loan (limits apply)", "Leasing costs (limits apply)", "Other (car washes, roadside assistance)"]
    for i, c in enumerate(costs, 10):
        V.cell(i, 8, c); x = V.cell(i, 9, 0); x.number_format = MONEY; x.fill = INPUT_FILL; x.border = BOX
    V["H17"] = "Total vehicle costs"; V["I17"] = "=SUM(I10:I16)"
    V["H18"] = "Deductible part (costs × business %)"; V["I18"] = "=ROUND(I17*I7,2)"
    V["H19"] = "Business parking (100% deductible) — enter"; V["I19"] = 0; V["I19"].fill = INPUT_FILL; V["I19"].border = BOX
    V["H20"] = "Motor vehicle expenses → line 9281"; V["I20"] = "=I18+I19"; V["H20"].font = B
    V["H21"] = "CCA on the vehicle (enter if you claim it) → line 9936"; V["I21"] = 0; V["I21"].fill = INPUT_FILL; V["I21"].border = BOX
    for r in (5, 17, 18, 19, 20, 21): V.cell(r, 9).number_format = MONEY
    for r in (5, 7, 17, 18, 20): V.cell(r, 9).fill = CALC_FILL
    V.freeze_panes = "A5"

    # ---------- T2125 Summary ----------
    T = wb.create_sheet("T2125 Summary")
    T.column_dimensions["A"].width = 3; T.column_dimensions["B"].width = 50; T.column_dimensions["C"].width = 18; T.column_dimensions["D"].width = 50
    T["B2"] = f"T2125 Summary — {TAX_YEAR}"; T["B2"].font = H1
    T["B3"] = "Copy these amounts into your tax software (Statement of Business or Professional Activities). Line numbers follow CRA's form."; T["B3"].font = NOTE
    T["B5"] = "Part 3 — Income"; T["B5"].font = H2
    T["B6"] = "8000 Gross sales, commissions or fees (before tax)"; T["C6"] = "=Income!$N$5"
    T["B7"] = "GST/HST collected (memo; not income)"; T["C7"] = "=Income!$N$6"
    T["B9"] = "Part 4 — Expenses"; T["B9"].font = H2
    row = 10
    for cat in T2125_LINES:
        T.cell(row, 2, cat)
        if cat.startswith("9281"):
            T.cell(row, 3, "=Vehicle!$I$20"); T.cell(row, 4, "From the Vehicle sheet").font = NOTE
        elif cat.startswith("9936"):
            T.cell(row, 3, f'=SUMIFS(Expenses!$I${first}:$I${last},Expenses!$D${first}:$D${last},"{cat}")+Vehicle!$I$21'); T.cell(row, 4, "CCA entered on Expenses plus vehicle CCA").font = NOTE
        else:
            T.cell(row, 3, f'=SUMIFS(Expenses!$I${first}:$I${last},Expenses!$D${first}:$D${last},"{cat}")')
        T.cell(row, 3).number_format = MONEY; T.cell(row, 3).fill = CALC_FILL; row += 1
    T.cell(row, 2, "9368 Total expenses").font = B; T.cell(row, 3, f"=SUM(C10:C{row-1})"); T.cell(row, 3).number_format = MONEY; T.cell(row, 3).fill = CALC_FILL; tot = row
    row += 1
    T.cell(row, 2, "9369 Net income (loss) before adjustments").font = B; T.cell(row, 3, f"=C6-C{tot}"); T.cell(row, 3).number_format = MONEY; T.cell(row, 3).fill = CALC_FILL; net = row
    adj = net + 2
    T.cell(adj, 2, "Net income after adjustments (used as the home-office cap, 7N)"); T.cell(adj, 3, f"=C{net}"); T.cell(adj, 3).number_format = MONEY; T.cell(adj, 3).fill = CALC_FILL
    T.cell(adj + 2, 2, "Part 7 — Business-use-of-home").font = H2
    T.cell(adj + 3, 2, "9945 Business-use-of-home expenses (7P)"); T.cell(adj + 3, 3, "='Home office'!$C$26")
    T.cell(adj + 4, 2, "9946 Your net income (loss)").font = B; T.cell(adj + 4, 3, f"=C{net}-C{adj+3}")
    for r in (adj + 3, adj + 4): T.cell(r, 3).number_format = MONEY; T.cell(r, 3).fill = CALC_FILL
    T.cell(adj + 6, 2, "Reminder: enter CCA (line 9936) only if you claim it; keep receipts six years; meals are already limited to 50%.").font = NOTE
    ROW_NET, ROW_ADJ, ROW_9945, ROW_9946 = net, adj, adj + 3, adj + 4

    # ---------- GST-HST ----------
    G = wb.create_sheet("GST-HST")
    G.column_dimensions["A"].width = 3; G.column_dimensions["B"].width = 52
    for col in "CDEFG": G.column_dimensions[col].width = 16
    G["B2"] = "GST/HST — regular method vs quick method, and the $30,000 small-supplier tracker"; G["B2"].font = H1
    G["B3"] = "Amounts come from the Income and Expenses sheets and your settings. Quarters follow the calendar year."; G["B3"].font = NOTE
    header(G, 5, ["", "Q1 (Jan–Mar)", "Q2 (Apr–Jun)", "Q3 (Jul–Sep)", "Q4 (Oct–Dec)", "Year"])
    G["B5"] = ""; qs = [(1, 3), (4, 6), (7, 9), (10, 12)]
    def sumq(sheet, col, m1, m2):
        return f"SUMIFS({sheet}!${col}${first}:${col}${last},{sheet}!$A${first}:$A${last},\">=\"&DATE('Start here'!$C$7,{m1},1),{sheet}!$A${first}:$A${last},\"<=\"&EOMONTH(DATE('Start here'!$C$7,{m2},1),0))"
    rows_def = [("Sales before tax", "Income", "F"), ("GST/HST collected", "Income", "G"), ("ITC-eligible GST/HST paid", "Expenses", "J")]
    for i, (lab, sh, col) in enumerate(rows_def, 6):
        G.cell(i, 2, lab)
        for j, (m1, m2) in enumerate(qs):
            G.cell(i, 3 + j, "=" + sumq(sh, col, m1, m2)).number_format = MONEY
        G.cell(i, 7, f"=SUM(C{i}:F{i})").number_format = MONEY
    G["B9"] = "Regular method — net tax (collected − ITCs)"; G["B9"].font = B
    for j in range(5): G.cell(9, 3 + j, f"={get_column_letter(3+j)}7-{get_column_letter(3+j)}8").number_format = MONEY
    G["B11"] = "Quick method"; G["B11"].font = H2
    G["B12"] = "Rate charged on your supplies"; G["C12"] = "='Start here'!$C$20"; G["C12"].number_format = PCT
    G["B13"] = "Row in the RC4058 table (5%→1, 13%→2, 14%→3, 15%→4)"; G["C13"] = "=IFERROR(MATCH(ROUND(C12*100,0),Lists!$G$2:$G$5,0),1)"
    G["B14"] = "Your remittance rate (RC4058)"; G["C14"] = "=IF('Start here'!$C$12=\"Goods for resale\",INDEX(Lists!$H$8:$K$11,C13,'Start here'!$C$22),INDEX(Lists!$H$2:$K$5,C13,'Start here'!$C$22))"; G["C14"].number_format = PCT
    G["B15"] = "Goods credit on 5% supplies from an HST province (RC4058)"; G["C15"] = "=IF(AND('Start here'!$C$12=\"Goods for resale\",C13=1),INDEX(Lists!$H$14:$K$14,1,'Start here'!$C$22),0)"; G["C15"].number_format = PCT
    G["B16"] = "Eligible supplies including GST/HST (year)"; G["C16"] = "=G6+G7"; G["C16"].number_format = MONEY
    G["B17"] = "Remittance before credit = supplies × rate"; G["C17"] = "=ROUND(C16*C14,2)"; G["C17"].number_format = MONEY
    G["B18"] = "1% credit on the first $30,000 of eligible supplies"; G["C18"] = "=ROUND(MIN(C16,30000)*0.01,2)"; G["C18"].number_format = MONEY
    G["B19"] = "Goods credit (if applicable)"; G["C19"] = "=ROUND(C16*C15,2)"; G["C19"].number_format = MONEY
    G["B20"] = "Quick method — net tax to remit (year)"; G["C20"] = "=MAX(0,C17-C18-C19)"; G["C20"].number_format = MONEY; G["B20"].font = B
    G["B21"] = "Regular method — net tax (year)"; G["C21"] = "=G9"; G["C21"].number_format = MONEY
    G["B22"] = "Which method remits less this year?"; G["C22"] = "=IF(C16=0,\"n/a\",IF(C20<C21,\"Quick method\",\"Regular method\"))"; G["B22"].font = B
    G["D22"] = "Quick method is only available if worldwide taxable supplies are ≤ $400,000 and you elected it (GST74). ITCs on capital purchases can still be claimed under the quick method; this comparison ignores them."; G["D22"].font = NOTE; G["D22"].alignment = Alignment(wrap_text=True); G.merge_cells("D22:G24")
    for r in range(12, 23): G.cell(r, 3).fill = CALC_FILL
    G["B26"] = "Small-supplier tracker ($30,000 of taxable supplies)"; G["B26"].font = H2
    G["B27"] = "Highest single calendar quarter this year"; G["C27"] = "=MAX(C6:F6)"; G["C27"].number_format = MONEY
    G["B28"] = "Last four calendar quarters (this year to date)"; G["C28"] = "=G6"; G["C28"].number_format = MONEY
    G["B29"] = "Status"; G["C29"] = "=IF('Start here'!$C$9=\"Yes\",\"Registered\",IF(OR(C27>30000,C28>30000),\"Over $30,000: you must register for GST/HST\",IF(C28>25000,\"Approaching $30,000: plan to register\",\"Small supplier\")))"; G["B29"].font = B
    G["D29"] = "Rule: you stop being a small supplier the moment a single quarter exceeds $30,000, or at the end of the month after four consecutive quarters exceed $30,000. Include the previous year's quarters yourself if you started mid-year."; G["D29"].font = NOTE; G["D29"].alignment = Alignment(wrap_text=True); G.merge_cells("D29:G32")
    for r in (27, 28, 29): G.cell(r, 3).fill = CALC_FILL
    G.conditional_formatting.add("C29", CellIsRule(operator="equal", formula=['"Over $30,000: you must register for GST/HST"'], fill=PatternFill("solid", fgColor="F8D7DA")))
    G["B34"] = "Filing"; G["B34"].font = H2
    G["B35"] = "Your filing frequency"; G["C35"] = "='Start here'!$C$13"
    G["B36"] = "Annual filers (individuals): return and payment due June 15 / April 30 for most sole proprietors — check My Business Account for your exact dates."; G["B36"].font = NOTE

    # ---------- Dashboard ----------
    D = wb.create_sheet("Dashboard", 1)
    D.column_dimensions["A"].width = 3; D.column_dimensions["B"].width = 14
    for col in "CDEFG": D.column_dimensions[col].width = 16
    D["B2"] = "='Start here'!$C$6"; D["B2"].font = H1
    D["B3"] = "Monthly picture, tax set-aside and GST/HST at a glance."; D["B3"].font = NOTE
    header(D, 5, ["Month", "Income (before tax)", "Expenses (deductible)", "Net", "Set aside for income tax", "Unpaid invoices"])
    for m in range(1, 13):
        r = 5 + m
        D.cell(r, 2, f"=TEXT(DATE('Start here'!$C$7,{m},1),\"mmm yyyy\")")
        D.cell(r, 3, "=" + sumq("Income", "F", m, m)).number_format = MONEY
        D.cell(r, 4, "=" + sumq("Expenses", "I", m, m)).number_format = MONEY
        D.cell(r, 5, f"=C{r}-D{r}").number_format = MONEY
        D.cell(r, 6, f"=MAX(0,ROUND(E{r}*'Start here'!$C$14,2))").number_format = MONEY
        D.cell(r, 7, f"=SUMIFS(Income!$I${first}:$I${last},Income!$J${first}:$J${last},\"No\",Income!$A${first}:$A${last},\">=\"&DATE('Start here'!$C$7,{m},1),Income!$A${first}:$A${last},\"<=\"&EOMONTH(DATE('Start here'!$C$7,{m},1),0))").number_format = MONEY
    D["B18"] = "Year"; D["B18"].font = B
    for col in "CDEFG": D[f"{col}18"] = f"=SUM({col}6:{col}17)"; D[f"{col}18"].number_format = MONEY; D[f"{col}18"].font = B
    D["B20"] = "Net income before home office (T2125 line 9369)"; D["D20"] = f"='T2125 Summary'!$C${ROW_NET}"
    D["B21"] = "Home-office claim (line 9945)"; D["D21"] = f"='T2125 Summary'!$C${ROW_9945}"
    D["B22"] = "Net income (line 9946)"; D["D22"] = f"='T2125 Summary'!$C${ROW_9946}"; D["B22"].font = B
    D["B23"] = "GST/HST net tax — regular method (year)"; D["D23"] = "='GST-HST'!$G$9"
    D["B24"] = "GST/HST net tax — quick method (year)"; D["D24"] = "='GST-HST'!$C$20"
    D["B25"] = "Small-supplier status"; D["D25"] = "='GST-HST'!$C$29"
    for r in range(20, 25): D.cell(r, 4).number_format = MONEY; D.cell(r, 4).fill = CALC_FILL
    D["D25"].fill = CALC_FILL
    D.column_dimensions["B"].width = 44
    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    L.sheet_state = "visible"
    return wb

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(pathlib.Path(__file__).parent / "dist")); a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    wb = build(); path = out / f"Canadian-Sole-Proprietor-Bookkeeping-T2125-{TAX_YEAR}.xlsx"; wb.save(path); print("wrote", path)
