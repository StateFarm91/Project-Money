#!/usr/bin/env python3
"""Evaluate every formula in the listing-4 workbook with the `formulas` engine and check key values.
Usage: .venv/bin/python products/etsy-templates/test_listing4.py [path]
Default scenario: Ontario, $50,000 net income (hand-computed in the commit that added this test)."""
import sys, pathlib, time
import formulas
path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).parent / "dist" / "Self-Employed-Tax-Set-Aside-Instalment-Planner-2026.xlsx").resolve()
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
# Ontario, $50,000 net income (the workbook's default inputs): hand-computed expected values.
checks = {
    ("Planner", "C13"): 7000.0,       # federal tax before credit (14% of 50,000)
    ("Planner", "C15"): 2303.28,      # federal BPA credit (16,452 * 14%)
    ("Planner", "C16"): 4696.72,      # federal tax after credit
    ("Planner", "C17"): 0.0,          # no Quebec abatement (Ontario)
    ("Planner", "C18"): 4696.72,      # federal tax after abatement
    ("Planner", "C21"): 9.0,          # Ontario is the 9th province alphabetically
    ("Planner", "C25"): 2525.0,       # Ontario tax (5.05% of 50,000)
    ("Planner", "C28"): 46500.0,      # CPP pensionable earnings (50,000-3,500)
    ("Planner", "C29"): 5533.5,       # base CPP (46,500 * 11.9%)
    ("Planner", "C30"): 0.0,          # no CPP2 (income below YMPE)
    ("Planner", "C32"): 5533.5,       # total CPP
    ("Planner", "C35"): 12755.22,     # total estimated tax + CPP
    ("Planner", "C36"): 1062.94,      # monthly set-aside
    ("Planner", "C37"): 3188.81,      # quarterly instalment
    ("Planner", "C38"): 3000.0,       # instalment threshold (not Quebec)
}
fails = 0
for (sh, cell), exp in checks.items():
    got = get(sh, cell)
    ok = (abs(float(got) - float(exp)) < 0.02) if got is not None and not isinstance(got, str) else (got == exp)
    if not ok: fails += 1
    print(f"{'OK ' if ok else 'FAIL'} {sh}!{cell} expected {exp!r} got {got!r}")
print("instalment status:", get("Planner", "C39"))
sys.exit(1 if (errors or fails) else 0)
