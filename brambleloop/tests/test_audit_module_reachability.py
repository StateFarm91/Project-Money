"""Every module under src/brambleloop is either imported by production code or inventoried (F-08).

A green suite for a module that no production path calls reads as "this capability exists".
CLAUDE.md forbids that claim. So this suite scans the import graph itself and holds the line:

  * a module that no *production* module imports (and that no deployed command runs) must be
    listed in `research/audit/UNWIRED_MODULES.json` with exactly one classification, so the
    sentence "exists but is not wired into production" is explicit and reviewable;
  * a module that nothing imports at all -- tests, scripts and ../ops included -- is dead
    code and must be deleted, not inventoried (unless it is an operator entry point that a
    script or runbook runs with `python -m`);
  * an inventory entry that has since become wired, or whose file is gone, fails, so the
    inventory cannot rot into a list of things that are no longer true.

What the scanner counts as a reference (production side = src/brambleloop only):
  * `import a.b` / `from a import b` / `from . import b` / `from .x import y`, relative imports
    resolved; `from pkg import name` marks `pkg.name` when that is a submodule (re-exports);
  * importing `a.b.c` marks the packages `a` and `a.b` (their `__init__` runs);
  * a string constant that is a dotted `brambleloop.x.y` module name (importlib tables,
    `__import__("brambleloop...")`, handler registries keyed by module path);
  * a string constant naming a sibling submodule inside a module that imports by name
    (`importlib.import_module(f"{__package__}.{NAME}")`);
  * `pkgutil.iter_modules(<pkg>.__path__)` (or of the module's own directory) followed by
    `import_module`: every direct submodule of that package is reachable;
  * the deployed commands: `uvicorn brambleloop.x:app` / `python -m brambleloop.x` in
    Dockerfile and railway.json are production roots.
Handlers registered by decorator at import time are covered by the import edge itself: the
registration only happens if something imports the module.

Run: python tests/test_audit_module_reachability.py
"""
from __future__ import annotations

import ast
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]           # brambleloop/
REPO = ROOT.parent
SRC = ROOT / "src"
PKG = SRC / "brambleloop"
INVENTORY = ROOT / "research" / "audit" / "UNWIRED_MODULES.json"
CLASSES = ("WIRED_ELSEWHERE", "ENTRYPOINT/TOOL", "TEST_SUPPORT", "UNWIRED_CAPABILITY", "DEAD")
# Places a non-production reference may come from (tests, operator scripts, ops tooling, and
# the research/evidence build scripts -- brand.iterations, for one, is imported only by
# research/final_build/w3/A_build_sheets.py, so it is a tool's dependency, not dead code).
NONPROD_DIRS = (ROOT / "tests", ROOT / "scripts", ROOT / "research", REPO / "ops")
DEPLOY_FILES = (ROOT / "Dockerfile", ROOT / "railway.json")
_DOTTED = re.compile(r"brambleloop(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_RUN_M = re.compile(r"(?:-m\s+|uvicorn\s+)(brambleloop(?:\.[A-Za-z_][A-Za-z0-9_]*)+)")


def _modname(path: Path, base: Path = SRC) -> str:
    rel = path.relative_to(base).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


@lru_cache(maxsize=None)
def modules() -> dict[str, Path]:
    return {_modname(p): p for p in sorted(PKG.rglob("*.py")) if "__pycache__" not in p.parts}


def _is_pkg(path: Path) -> bool:
    return path.name == "__init__.py"


def _ancestors(mod: str):
    parts = mod.split(".")
    for i in range(1, len(parts)):
        yield ".".join(parts[:i])


def _base_of(current: str | None, is_pkg: bool, level: int, module: str | None) -> str | None:
    if level == 0:
        return module
    if current is None:
        return None
    parts = current.split(".")
    if not is_pkg:
        parts = parts[:-1]
    if level > 1:
        parts = parts[: len(parts) - (level - 1)]
    base = ".".join(parts)
    return f"{base}.{module}" if module else base


def references(path: Path, current: str | None) -> set[str]:
    """Every brambleloop module the file at `path` references (see the module docstring)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    known = modules()
    is_pkg = _is_pkg(path)
    out: set[str] = set()
    aliases: dict[str, str] = {}

    def mark(name: str | None):
        if not name:
            return
        # Longest known prefix: `import a.b.c` where c is an attribute marks a.b.
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in known:
                out.add(cand)
                out.update(a for a in _ancestors(cand) if a in known)
                return

    dynamic = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mark(a.name)
                if a.asname:
                    aliases[a.asname] = a.name
        elif isinstance(node, ast.ImportFrom):
            base = _base_of(current, is_pkg, node.level, node.module)
            mark(base)
            for a in node.names:
                if base and f"{base}.{a.name}" in known:
                    mark(f"{base}.{a.name}")
                    aliases[a.asname or a.name] = f"{base}.{a.name}"
                elif base and a.name == "*":
                    pass
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in ("import_module", "__import__"):
                dynamic = True
    # A bare string statement (a docstring, or prose left in a body) executes nothing: a
    # module named only there is mentioned, not referenced.
    prose = {id(n.value) for n in ast.walk(tree)
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
    pkg_of_self = current if is_pkg else (current.rsplit(".", 1)[0] if current and "." in current else None)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in prose):
            for m in _DOTTED.findall(node.value):
                mark(m)
            if dynamic and pkg_of_self and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", node.value):
                cand = f"{pkg_of_self}.{node.value}"
                if cand in known:
                    mark(cand)
        # pkgutil.iter_modules(<pkg>.__path__ | [dir]) + import_module: every submodule of it.
        if (dynamic and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("iter_modules", "walk_packages")):
            target = pkg_of_self
            arg = node.args[0] if node.args else None
            if (isinstance(arg, ast.Attribute) and arg.attr == "__path__"
                    and isinstance(arg.value, ast.Name)):
                target = aliases.get(arg.value.id, target)
            if target:
                for m in known:
                    if m.startswith(target + ".") and "." not in m[len(target) + 1:]:
                        mark(m)
    out.discard(current) if current else None
    return out


@lru_cache(maxsize=None)
def production_importers() -> dict[str, frozenset[str]]:
    """module -> the production modules (src/brambleloop) that reference it."""
    acc: dict[str, set[str]] = {m: set() for m in modules()}
    for mod, path in modules().items():
        for ref in references(path, mod):
            acc[ref].add(mod)
    return {m: frozenset(v) for m, v in acc.items()}


@lru_cache(maxsize=None)
def deployed_roots() -> frozenset[str]:
    roots: set[str] = set()
    for f in DEPLOY_FILES:
        for m in _RUN_M.findall(f.read_text(encoding="utf-8")):
            roots.add(m)
    return frozenset(r for r in roots if r in modules())


@lru_cache(maxsize=None)
def nonprod_importers() -> dict[str, frozenset[str]]:
    """module -> the test/script/ops files (repo-relative) that reference it, incl. `-m` runs."""
    acc: dict[str, set[str]] = {m: set() for m in modules()}
    known = modules()
    for d in NONPROD_DIRS:
        for p in sorted(d.rglob("*")):
            if "__pycache__" in p.parts or not p.is_file():
                continue
            rel = str(p.relative_to(REPO))
            if p.suffix == ".py":
                if p.resolve() == Path(__file__).resolve():
                    continue   # this scanner names modules in its own fixtures
                for ref in references(p, None):
                    acc[ref].add(rel)
            if p.suffix in (".py", ".sh", ".md", ".txt", ".json", ".yml", ".yaml", ""):
                try:
                    text = p.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for m in _RUN_M.findall(text):
                    if m in known:
                        acc[m].add(rel)
    return {m: frozenset(v) for m, v in acc.items()}


def _wired(mod: str) -> bool:
    if mod in deployed_roots() or mod == "brambleloop":
        return True
    if production_importers()[mod]:
        return True
    # A package is wired when any of its submodules is (importing a.b runs a/__init__).
    return False


def unwired() -> list[str]:
    return sorted(m for m in modules() if not _wired(m))


def inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- scanner self-checks


def test_scanner_resolves_relative_and_reexport_imports():
    # runtime.worker is imported by app.worker_entry; the scanner must see a known edge,
    # or every module would read as unwired and the guard would be vacuous.
    imp = production_importers()
    assert imp["brambleloop.runtime.worker"], "scanner saw no importer of runtime.worker"
    assert "brambleloop.app.main" in deployed_roots(), deployed_roots()
    assert len(unwired()) < len(modules()) // 4, len(unwired())
    print("OK   test_scanner_resolves_relative_and_reexport_imports")


def test_scanner_follows_pkgutil_and_string_references(tmp=None):
    # creative.ideation walks the creative package with pkgutil + import_module, so every
    # creative submodule is referenced from production code.
    imp = production_importers()
    creative = [m for m in modules() if m.startswith("brambleloop.creative.")
                and m.count(".") == 2]
    assert creative and all(imp[m] for m in creative), [m for m in creative if not imp[m]]
    print("OK   test_scanner_follows_pkgutil_and_string_references")


# ---------------------------------------------------------------- the guard


def _runnable(mod: str) -> bool:
    path = modules()[mod]
    return path.name == "__main__.py" or '__name__ == "__main__"' in path.read_text(encoding="utf-8")


def test_no_module_is_dead():
    """Nothing at all imports it (tests, scripts, research, ops included) and no command runs it.

    The one exception is an operator entry point (`python -m ...`, a `__main__` guard) that is
    inventoried as ENTRYPOINT/TOOL naming what runs it: nothing imports a command."""
    non = nonprod_importers()
    tools = set()
    if INVENTORY.exists():
        tools = {e["module"] for e in inventory()["modules"]
                 if e.get("classification") == "ENTRYPOINT/TOOL" and e.get("run_by")}
    dead = [m for m in unwired() if not non[m] and not (m in tools and _runnable(m))]
    assert not dead, ("dead modules (delete them; inventory one only as ENTRYPOINT/TOOL naming the command "
                      f"that runs it): {dead}")
    print("OK   test_no_module_is_dead")


def test_every_unwired_module_is_inventoried():
    assert INVENTORY.exists(), f"missing inventory {INVENTORY.relative_to(REPO)}"
    entries = {e["module"]: e for e in inventory()["modules"]}
    missing = [m for m in unwired() if m not in entries]
    assert not missing, ("modules with no production importer and no inventory "
                         f"classification: {missing}")
    print("OK   test_every_unwired_module_is_inventoried")


def test_inventory_does_not_rot():
    assert INVENTORY.exists(), f"missing inventory {INVENTORY.relative_to(REPO)}"
    entries = inventory()["modules"]
    names = [e["module"] for e in entries]
    assert len(names) == len(set(names)), "duplicate inventory entries"
    gone = [m for m in names if m not in modules()]
    assert not gone, f"inventory names modules that no longer exist: {gone}"
    now_wired = [m for m in names if _wired(m)]
    assert not now_wired, ("inventory entries now have a production importer -- remove "
                           f"them from the inventory: {now_wired}")
    print("OK   test_inventory_does_not_rot")


def test_inventory_entries_are_well_formed():
    assert INVENTORY.exists(), f"missing inventory {INVENTORY.relative_to(REPO)}"
    non = nonprod_importers()
    for e in inventory()["modules"]:
        m = e["module"]
        assert e.get("classification") in CLASSES, (m, e.get("classification"))
        # DEAD code is deleted, and WIRED_ELSEWHERE means the scanner must be fixed instead.
        assert e["classification"] not in ("DEAD", "WIRED_ELSEWHERE"), (m, e["classification"])
        assert e.get("claim"), f"{m}: no claim (docstring first line)"
        assert isinstance(e.get("lines"), int) and e["lines"] > 0, m
        refs = e.get("covered_by") or []
        assert refs or e["classification"] == "ENTRYPOINT/TOOL", (
            f"{m}: no covering test/script recorded")
        stale = [r for r in refs if r not in non[m]]
        assert not stale, f"{m}: covered_by lists files that no longer reference it: {stale}"
        if e["classification"] == "ENTRYPOINT/TOOL":
            assert e.get("run_by"), f"{m}: ENTRYPOINT/TOOL must name the script that runs it"
            assert refs or _runnable(m), f"{m}: ENTRYPOINT/TOOL with no caller and no __main__"
        if e["classification"] == "TEST_SUPPORT":
            assert m.rsplit(".", 1)[-1].startswith("_testkit") or "_testkit" in m, m
    print("OK   test_inventory_entries_are_well_formed")


if __name__ == "__main__":
    import traceback

    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception:  # noqa: BLE001
                fails += 1
                print("FAIL", name)
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
