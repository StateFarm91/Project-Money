#!/usr/bin/env python3
"""Evaluate every formula in the listing-3 workbook with the `formulas` engine and check key values.
Usage: .venv/bin/python products/etsy-templates/test_listing3.py [path]"""
import sys, pathlib, time
import formulas
path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "dist" / "Home-Office-Vehicle-Expense-Workbook-2026.xlsx").resolve()
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
# Home office 9 = 150/1200 area share * min(168/168,1) time share = 0.125
# Vehicle: business km 34, total 12000 -> 0.0028333...
checks = {
    ("Home office", "C9"): 0.125,
    ("Home office", "C19"): 0.0,   # no yearly costs entered by default
    ("Home office", "C23"): 0.0,
    ("Home office", "C24"): 20000.0,  # from Start here C6
    ("Home office", "C26"): 0.0,
    ("Vehicle", "I5"): 34.0,
    ("Vehicle", "I6"): 12000.0,
    ("Vehicle", "I7"): 34.0 / 12000.0,
    ("Vehicle", "I17"): 0.0,
    ("Vehicle", "I20"): 0.0,
}
fails = 0
for (sh, cell), exp in checks.items():
    got = get(sh, cell)
    ok = (abs(float(got) - float(exp)) < 1e-6) if isinstance(exp, (int, float)) and got is not None and not isinstance(got, str) else (got == exp)
    if not ok: fails += 1
    print(f"{'OK ' if ok else 'FAIL'} {sh}!{cell} expected {exp!r} got {got!r}")
sys.exit(1 if (errors or fails) else 0)
