#!/usr/bin/env python3
"""Listing 4: Self-Employed Tax Set-Aside and Instalment Planner (standalone).
Usage: .venv/bin/python products/etsy-templates/build_listing4.py [--out dist]
2026 federal/provincial brackets, CPP rates and the Quebec federal abatement come from
TAX_REFERENCE.md (verified 2026-09-16 against CRA's own page and cross-checked provincial
sources). The planner deliberately omits provincial personal credits and the CPP
self-employment deduction so its estimate runs a little HIGH (a safe amount to set aside),
never low; this is disclosed on the sheet. Formulas: only SUM, SUMIFS, INDEX, MATCH, IF,
IFERROR, MIN, MAX, AND, OR, DATE, EOMONTH, ROUND, COUNTIF, TEXT (Excel/Sheets-compatible)."""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from openpyxl import Workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from build_templates import H1, H2, B, INPUT_FILL, CALC_FILL, NOTE, BOX, MONEY, PCT, TAX_YEAR, VERSION, header, dv

MAX_BRACKETS = 8  # Newfoundland and Labrador has the most (8)

FEDERAL = [(0, 0.14), (58523, 0.205), (117045, 0.26), (181440, 0.29), (258482, 0.33)]
BPA_MAX, BPA_MIN, BPA_FULL_UP_TO, BPA_ZERO_AT = 16452, 14829, 181440, 258482
CPP_EXEMPTION, CPP_YMPE, CPP_YAMPE, CPP_RATE, CPP2_RATE = 3500, 74600, 85000, 0.119, 0.08
CPP_MAX_BASE, CPP_MAX_CPP2 = 8460.90, 832.00

# (province, [(lower_bound, rate), ...] ascending)
PROVINCES = [
    ("Alberta", [(0, 0.08), (61200, 0.10), (154259, 0.12), (185111, 0.13), (246813, 0.14), (370220, 0.15)]),
    ("British Columbia", [(0, 0.056), (50363, 0.077), (100728, 0.105), (115648, 0.1229), (140430, 0.147), (190405, 0.168), (265545, 0.205)]),
    ("Manitoba", [(0, 0.108), (47000, 0.1275), (100000, 0.174)]),
    ("New Brunswick", [(0, 0.094), (52333, 0.14), (104666, 0.16), (193861, 0.195)]),
    ("Newfoundland and Labrador", [(0, 0.087), (44678, 0.145), (89354, 0.158), (159528, 0.178), (223340, 0.198), (285319, 0.208), (570638, 0.213), (1141275, 0.218)]),
    ("Northwest Territories", [(0, 0.059), (53003, 0.086), (106009, 0.122), (172346, 0.1405)]),
    ("Nova Scotia", [(0, 0.0879), (30995, 0.1495), (61991, 0.1667), (97417, 0.175), (157124, 0.21)]),
    ("Nunavut", [(0, 0.04), (55801, 0.07), (111602, 0.09), (181439, 0.115)]),
    ("Ontario", [(0, 0.0505), (53891, 0.0915), (107785, 0.1116), (150000, 0.1216), (220000, 0.1316)]),
    ("Prince Edward Island", [(0, 0.095), (33928, 0.1347), (65820, 0.166), (106890, 0.1762), (142250, 0.19), (200000, 0.20)]),
    ("Quebec", [(0, 0.14), (54345, 0.19), (108680, 0.24), (132245, 0.2575)]),
    ("Saskatchewan", [(0, 0.105), (54532, 0.125), (155805, 0.145)]),
    ("Yukon", [(0, 0.064), (58523, 0.09), (117045, 0.109), (181440, 0.128), (500000, 0.15)]),
]

def cumtax(brackets):
    cum = [0.0]
    for i in range(1, len(brackets)):
        lower, _ = brackets[i]
        prev_lower, prev_rate = brackets[i - 1]
        cum.append(cum[-1] + (lower - prev_lower) * prev_rate)
    return cum

def padded(brackets, n=MAX_BRACKETS):
    b = list(brackets)
    while len(b) < n:
        last_lower, last_rate = b[-1]
        b.append((last_lower + 1, last_rate))
    return b[:n], cumtax(b[:n])

def build():
    wb = Workbook()
    L = wb.active; L.title = "Lists"
    L["A1"] = "Province"; L["A1"].font = B
    for i, (name, _) in enumerate(PROVINCES, 2): L.cell(i, 1, name)
    L.column_dimensions["A"].width = 26

    for j, (name, brackets) in enumerate(PROVINCES):
        col = 2 + j  # B, C, D, ...
        lowers, rates = zip(*brackets)
        lowers_p, cum_p = padded(brackets)
        rates_p = [r for _, r in lowers_p]
        L.cell(1, col, name).font = B
        for i in range(MAX_BRACKETS):
            L.cell(2 + i, col, lowers_p[i][0])
            L.cell(12 + i, col, lowers_p[i][1]).number_format = PCT
            L.cell(22 + i, col, round(cum_p[i], 2)).number_format = MONEY
        L.column_dimensions[get_column_letter(col)].width = 12
    L["A11"] = "Rate table (same columns)"; L["A11"].font = NOTE
    L["A21"] = "Cumulative tax at bracket start (same columns)"; L["A21"].font = NOTE

    L["P1"] = "Federal LB"; L["Q1"] = "Federal rate"; L["R1"] = "Federal CumTax"
    for c in "PQR": L[f"{c}1"].font = B
    fed_cum = cumtax(FEDERAL)
    for i, (lower, rate) in enumerate(FEDERAL, 2):
        L.cell(i, 16, lower); L.cell(i, 17, rate).number_format = PCT; L.cell(i, 18, round(fed_cum[i - 2], 2)).number_format = MONEY
    for c in "PQR": L.column_dimensions[c].width = 14
    L["P9"] = f"2026 federal, provincial/territorial brackets, CPP rates and the Quebec federal abatement: see TAX_REFERENCE.md. Version {VERSION}, tax year {TAX_YEAR}."
    L["P9"].font = NOTE; L.merge_cells("P9:R11")

    # ---------- Planner ----------
    P = wb.create_sheet("Planner", 0)
    P.column_dimensions["A"].width = 3; P.column_dimensions["B"].width = 52; P.column_dimensions["C"].width = 20; P.column_dimensions["D"].width = 56
    P["B2"] = f"Self-Employed Tax Set-Aside and Instalment Planner — {TAX_YEAR}"; P["B2"].font = H1
    P["B3"] = "Enter your expected net self-employment income and province; this shows a SAFE (slightly high) estimate of federal + provincial tax and CPP, a monthly set-aside, and whether the CRA instalment rule of thumb likely applies."
    P["B3"].font = NOTE; P["B3"].alignment = Alignment(wrap_text=True); P.merge_cells("B3:D3"); P.row_dimensions[3].height = 40

    P["B5"] = "1. Your numbers"; P["B5"].font = H2
    P["B6"] = "Expected net self-employment income (T2125 line 9946, or your best estimate)"; P["C6"] = 50000; P["C6"].fill = INPUT_FILL; P["C6"].border = BOX; P["C6"].number_format = MONEY
    P["B7"] = "Province or territory"; P["C7"] = "Ontario"; P["C7"].fill = INPUT_FILL; P["C7"].border = BOX
    dv(P, "Lists!$A$2:$A$14", "C7")

    P["B9"] = "2. Federal tax"; P["B9"].font = H2
    P["B10"] = "Bracket row"; P["C10"] = "=MATCH($C$6,Lists!$P$2:$P$6,1)"
    P["B11"] = "Bracket lower bound"; P["C11"] = "=INDEX(Lists!$P$2:$P$6,$C$10)"
    P["B12"] = "Bracket rate"; P["C12"] = "=INDEX(Lists!$Q$2:$Q$6,$C$10)"; P["C12"].number_format = PCT
    P["B13"] = "Tax before credits"; P["C13"] = "=INDEX(Lists!$R$2:$R$6,$C$10)+($C$6-$C$11)*$C$12"
    P["B14"] = "Basic personal amount (BPA), phased out $181,440–$258,482"; P["C14"] = f"=IF($C$6<={BPA_FULL_UP_TO},{BPA_MAX},IF($C$6>={BPA_ZERO_AT},{BPA_MIN},{BPA_MAX}-($C$6-{BPA_FULL_UP_TO})/({BPA_ZERO_AT}-{BPA_FULL_UP_TO})*({BPA_MAX}-{BPA_MIN})))"
    P["B15"] = "Federal BPA credit (BPA × lowest bracket rate 14%)"; P["C15"] = "=ROUND($C$14*0.14,2)"
    P["B16"] = "Federal tax after BPA credit"; P["C16"] = "=MAX(0,$C$13-$C$15)"
    P["B17"] = "Quebec federal abatement (16.5% of federal tax, Quebec residents only)"; P["C17"] = '=IF($C$7="Quebec",ROUND($C$16*0.165,2),0)'
    P["B18"] = "Federal tax after abatement"; P["C18"] = "=$C$16-$C$17"; P["B18"].font = B
    for r in range(10, 19): P.cell(r, 3).fill = CALC_FILL
    for r in (13, 14, 15, 16, 17, 18): P.cell(r, 3).number_format = MONEY

    P["B20"] = "3. Provincial / territorial tax (no provincial credits — runs a bit high; see note)"; P["B20"].font = H2
    P["B21"] = "Province column"; P["C21"] = "=MATCH($C$7,Lists!$A$2:$A$14,0)"
    P["B22"] = "Bracket row"; P["C22"] = "=MATCH($C$6,$F$2:$F$9,1)"
    P["B23"] = "Bracket lower bound"; P["C23"] = "=INDEX($F$2:$F$9,$C$22)"
    P["B24"] = "Bracket rate"; P["C24"] = "=INDEX($G$2:$G$9,$C$22)"; P["C24"].number_format = PCT
    P["B25"] = "Provincial / territorial tax"; P["C25"] = "=INDEX($H$2:$H$9,$C$22)+($C$6-$C$23)*$C$24"; P["B25"].font = B
    for r in range(21, 26): P.cell(r, 3).fill = CALC_FILL
    for r in (23, 25): P.cell(r, 3).number_format = MONEY

    # Staging columns (hidden): the selected province's 8 brackets copied out via single-cell INDEX
    # lookups (row AND column both fixed per cell) so MATCH can search a plain 1-D range. Avoids
    # INDEX(range,0,col) "whole column" broadcasting, which the `formulas` validation engine (and some
    # older spreadsheet apps) does not evaluate correctly even though Excel/Sheets support it.
    for i in range(8):
        r = 2 + i
        P.cell(r, 6, f"=INDEX(Lists!$B$2:$N$9,{i + 1},$C$21)")
        P.cell(r, 7, f"=INDEX(Lists!$B$12:$N$19,{i + 1},$C$21)")
        P.cell(r, 8, f"=INDEX(Lists!$B$22:$N$29,{i + 1},$C$21)")
    for c in "FGH": P.column_dimensions[c].hidden = True

    P["B27"] = "4. CPP (self-employed)"; P["B27"].font = H2
    P["B28"] = f"Pensionable earnings (income between ${CPP_EXEMPTION:,} exemption and ${CPP_YMPE:,} YMPE)"; P["C28"] = f"=MAX(0,MIN($C$6,{CPP_YMPE})-{CPP_EXEMPTION})"
    P["B29"] = f"Base CPP ({CPP_RATE:.1%})"; P["C29"] = "=ROUND($C$28*" + str(CPP_RATE) + ",2)"
    P["B30"] = f"CPP2 earnings (between ${CPP_YMPE:,} and ${CPP_YAMPE:,} YAMPE)"; P["C30"] = f"=MAX(0,MIN($C$6,{CPP_YAMPE})-{CPP_YMPE})"
    P["B31"] = f"CPP2 ({CPP2_RATE:.0%})"; P["C31"] = "=ROUND($C$30*" + str(CPP2_RATE) + ",2)"
    P["B32"] = "Total CPP"; P["C32"] = "=$C$29+$C$31"; P["B32"].font = B
    P["D27"] = "Quebec residents pay QPP, not CPP. QPP rates are close but not identical; this uses the CPP rate as an approximation." ; P["D27"].font = NOTE; P["D27"].alignment = Alignment(wrap_text=True); P.merge_cells("D27:D32")
    for r in range(28, 33): P.cell(r, 3).fill = CALC_FILL
    for r in (28, 29, 30, 31, 32): P.cell(r, 3).number_format = MONEY

    P["B34"] = "5. Set aside and instalments"; P["B34"].font = H2
    P["B35"] = "Total estimated tax + CPP"; P["C35"] = "=$C$18+$C$25+$C$32"; P["B35"].font = B
    P["B36"] = "Monthly set-aside"; P["C36"] = "=ROUND($C$35/12,2)"; P["B36"].font = B
    P["B37"] = "Quarterly instalment (even split; CRA also offers a prior-year option)"; P["C37"] = "=ROUND($C$35/4,2)"
    P["B38"] = "Instalment threshold (net tax owing) for the rule of thumb"; P["C38"] = '=IF($C$7="Quebec",1800,3000)'
    P["B39"] = "Instalments likely required?"; P["C39"] = '=IF($C$35>$C$38,"Likely — if this is also true in one of the last two years",  "Not required based on this estimate alone")'; P["B39"].font = B
    for r in (35, 36, 37, 38): P.cell(r, 3).number_format = MONEY
    for r in range(35, 40): P.cell(r, 3).fill = CALC_FILL

    P["B41"] = "Due dates (if instalments are required)"; P["B41"].font = H2
    header(P, 42, ["Instalment", "Due date", "Amount (quarterly estimate)"], [16, 16, 26])
    dates = [("Q1", f"{TAX_YEAR}-03-15"), ("Q2", f"{TAX_YEAR}-06-15"), ("Q3", f"{TAX_YEAR}-09-15"), ("Q4", f"{TAX_YEAR}-12-15")]
    for i, (q, d) in enumerate(dates, 43):
        P.cell(i, 2, q); P.cell(i, 3, d); c = P.cell(i, 4, "=$C$37"); c.number_format = MONEY; c.fill = CALC_FILL

    P["B48"] = "Important — read before relying on this"; P["B48"].font = H2
    P["B49"] = ("This planner is deliberately conservative: it does NOT include your provincial personal tax credits (only the federal basic personal amount) and does NOT apply the self-employment CPP deduction. "
                "Both would lower a real tax bill, so this estimate runs a bit HIGH — a safe amount to set aside, not your exact bill. It is a bookkeeping tool, not tax, legal or accounting advice. "
                f"Rates were checked against the CRA's own pages and cross-checked provincial sources in September 2026 for the {TAX_YEAR} tax year (see TAX_REFERENCE.md sources). "
                "Verify your instalment obligation and exact amount with the CRA (My Business Account) or an accountant; the two-of-three-years test above cannot be evaluated from one year's numbers alone.")
    P["B49"].alignment = Alignment(wrap_text=True, vertical="top"); P.merge_cells("B49:D52"); P.row_dimensions[49].height = 48
    P["B54"] = f"Version {VERSION} · MapleSheets"; P["B54"].font = NOTE
    return wb

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(pathlib.Path(__file__).parent / "dist")); a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    p = out / f"Self-Employed-Tax-Set-Aside-Instalment-Planner-{TAX_YEAR}.xlsx"; build().save(p); print("wrote", p)
