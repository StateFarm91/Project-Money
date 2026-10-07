"""Reachability sees a function a live provider table names as a ("module", "function") pair.

Wave 4, lane FM (F-833; v1.1 F-913/F-914/F-915, seo.status, learn.improvement_status). The
Command Center's PROVIDERS table maps a key to ("brambleloop.finance.accounting.dashboard",
"summary") and `providers._resolve` imports the module by name and calls getattr(mod, fn). The
module-level import edge already existed (test_w3_reachability_dynamic); the function-level C-65
rule still read the accounting dashboard, forecast, SEO status and improvement status modules as
"imported, but no live path reaches anything it defines", so the v1.1 money rows stayed OPEN
although the owner's Money tab calls them. The pair is the call. Bounded: only in a module that
performs a dynamic import, only a 2-tuple of string literals, only a function the module defines.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))

import _tmp; _tmp.install()  # noqa: E402,E702  W3-HYG per-process temp sandbox

from brambleloop.build2 import reachability as R  # noqa: E402

DASH = "brambleloop.finance.accounting.dashboard"
PROVIDERS = "brambleloop.app.command_center.providers"
TABLE_ONLY = [("finance/accounting/dashboard.py", "drill"),
              ("finance/accounting/dashboard.py", "summary"),
              ("seo/status.py", "summary"),
              ("learn/improvement_status.py", "summary")]


def test_functions_named_in_the_live_provider_table_are_live():
    assert TABLE_ONLY
    for rel, fn in TABLE_ONLY:
        v = R.function_reached(rel, fn)
        assert v["reached"], (rel, fn, v["why"])
    # drill is called only through the table key "accounting_drill": its reason names the table
    why = R.analysis().live[(DASH, "drill")]
    assert "provider table" in why and "providers.py" in why, why


def test_modules_behind_the_table_are_reached():
    for rel in ("finance/accounting/dashboard.py", "finance/accounting/forecast.py",
                "seo/status.py", "learn/improvement_status.py"):
        v = R.reached(rel)
        assert v["reached"], (rel, v["why"])


def _pair(module: str, name: str) -> ast.Tuple:
    return ast.Tuple(elts=[ast.Constant(module), ast.Constant(name)], ctx=ast.Load())


def test_a_pair_outside_a_dynamic_importer_marks_nothing():
    a = R.analysis()
    plain = "brambleloop.autonomy.charters"
    assert plain in a.mods and not R._dynamic_importer(plain)
    assert R._dynamic_importer(PROVIDERS)
    before = dict(a.live)
    a._provider_pairs(plain, [_pair(DASH, "summary")], "probe", "probe")
    assert a.live == before


def test_a_pair_naming_no_defined_function_marks_nothing():
    a = R.analysis()
    before = dict(a.live)
    nodes = [_pair(DASH, "no_such_function"), _pair("brambleloop.no.such.module", "summary"),
             ast.Tuple(elts=[ast.Constant(DASH), ast.Constant("summary"), ast.Constant("x")],
                       ctx=ast.Load())]
    assert nodes
    a._provider_pairs(PROVIDERS, nodes, "probe", "probe")
    assert a.live == before


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
