#!/usr/bin/env python3
"""Evaluate every formula in the built workbook with the `formulas` engine and check key values.
Usage: .venv/bin/python products/etsy-templates/test_workbook.py [path]"""
import sys, pathlib, re, time
import formulas
path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "dist" / "Canadian-Sole-Proprietor-Bookkeeping-T2125-2026.xlsx").resolve()
t0 = time.time()
xl = formulas.ExcelModel().loads(str(path)).finish()
sol = xl.calculate()
print(f"evaluated in {time.time()-t0:.1f}s; {len(sol)} cells")
fname = path.name
def get(sheet, cell):
    key = f"'[{fname}]{sheet.upper()}'!{cell}"
    v = sol.get(key)
    if v is None or not hasattr(v, "value"): return None
    val = v.value
    try:
        return val[0][0] if hasattr(val, "__len__") and not isinstance(val, str) else val
    except Exception:
        return val
errors = []
for k, v in sol.items():
    if not hasattr(v, "value"): continue
    val = v.value
    try:
        flat = val.ravel().tolist() if hasattr(val, "ravel") else [val]
    except Exception:
        flat = [val]
    for x in flat:
        if isinstance(x, formulas.tokens.operand.XlError) or (isinstance(x, str) and x.startswith("#")):
            errors.append((k, str(x))); break
print("cells with errors:", len(errors))
for e in errors[:20]: print("  ", e)
checks = {
    ("Start here", "C17"): 0.0, ("Start here", "C18"): 0.13, ("Start here", "C19"): 0.0, ("Start here", "C20"): 0.13, ("Start here", "C22"): 2,
    ("Income", "N5"): 2329.0, ("Income", "N6"): 0.0, ("Income", "N8"): 800.0,
    ("T2125 Summary", "C6"): 2329.0, ("T2125 Summary", "C10"): 45.0, ("T2125 Summary", "C11"): 30.0, ("T2125 Summary", "C16"): 20.0,
    ("GST-HST", "C13"): 2, ("GST-HST", "C14"): 0.088, ("GST-HST", "C16"): 2329.0,
    ("Home office", "C9"): 0.125,
    ("Vehicle", "I5"): 34.0,
}
fails = 0
for (sh, cell), exp in checks.items():
    got = get(sh, cell)
    ok = (abs(float(got) - float(exp)) < 1e-6) if isinstance(exp, (int, float)) and got is not None and not isinstance(got, str) else (got == exp)
    if not ok: fails += 1
    print(f"{'OK ' if ok else 'FAIL'} {sh}!{cell} expected {exp!r} got {got!r}")
print("T2125 9368/9369:", get("T2125 Summary", "C30"), get("T2125 Summary", "C31"), "| 9945/9946:", get("T2125 Summary", "C36"), get("T2125 Summary", "C37"))
print("GST-HST quarters:", [get("GST-HST", c + "6") for c in "CDEFG"], "regular", get("GST-HST", "G9"), "quick remit", get("GST-HST", "C20"), "which", get("GST-HST", "C22"), "status", get("GST-HST", "C29"))
print("Home office 7M/7N/7P:", get("Home office", "C23"), get("Home office", "C24"), get("Home office", "C26"))
print("Dashboard Jan:", get("Dashboard", "B6"), get("Dashboard", "C6"), get("Dashboard", "D6"), get("Dashboard", "E6"), get("Dashboard", "F6"), "| year:", get("Dashboard", "C18"), get("Dashboard", "D18"), "| net:", get("Dashboard", "D22"))
sys.exit(1 if (errors or fails) else 0)
