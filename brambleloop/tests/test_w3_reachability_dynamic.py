"""Live-root reachability sees modules loaded by name from an import table (F-833, C-65).

Wave 3, lane TOOLS (cluster K13; unblocks K15). The Command Center loads its department
providers with `importlib.import_module(PROVIDERS[key][0])`; the static import walk could not see
those edges, so accounting/SEO/improvement providers read as unreached although the dashboard
calls them. The rule is bounded: only a module that itself performs a dynamic import, and only a
string literal naming a module file in full.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.build2 import reachability as R  # noqa: E402

PROVIDER_MODULES = ("brambleloop.finance.accounting.dashboard", "brambleloop.seo.status",
                    "brambleloop.learn.improvement_status")


def test_provider_table_modules_are_reached_from_a_live_root():
    reached = R.reachable()
    assert len(reached) > 300
    for m in PROVIDER_MODULES:
        assert m in reached, m
    edges = R._imports("brambleloop.app.command_center.providers")
    assert set(PROVIDER_MODULES) <= set(edges), edges


def test_a_dotted_literal_in_a_module_without_a_dynamic_import_is_not_an_edge():
    mod = "brambleloop.autonomy.map"
    src = (ROOT / "src" / "brambleloop" / "autonomy" / "map.py").read_text()
    named = set(re.findall(r"[\"'](brambleloop(?:\.[a-z_]+)+)[\"']", src))
    assert named, "fixture module no longer names any module by string"
    assert "import_module" not in src and "__import__" not in src
    edges = set(R._imports(mod))
    imported = set(re.findall(r"^\s*from (brambleloop[\w.]*) import|^\s*import (brambleloop[\w.]*)",
                              src, re.M))
    # Any dotted literal it names is an edge only if the module also really imports it.
    for name in named - {a or b for a, b in imported}:
        assert name not in edges or R._path_of(name) is None, name


def test_provider_modules_are_reached_by_ordinary_imports_even_without_the_rule():
    # Lane D (wave 3) moved the orchestrator and Laura to ordinary imports of the department
    # status modules, so the provider modules no longer depend on the dotted-literal rule:
    # they must be reachable with the rule switched off (stronger than the original check,
    # which asserted the rule was the only thing that made them visible).
    saved = R._DOTTED_MODULE
    try:
        R._DOTTED_MODULE = re.compile(r"(?!x)x")
        R._imports_cached.cache_clear()
        R._reachable_cached.cache_clear()
        before = R.reachable()
    finally:
        R._DOTTED_MODULE = saved
        R._imports_cached.cache_clear()
        R._reachable_cached.cache_clear()
    after = R.reachable()
    assert PROVIDER_MODULES
    assert set(PROVIDER_MODULES) <= before, set(PROVIDER_MODULES) - before
    assert before <= after


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
