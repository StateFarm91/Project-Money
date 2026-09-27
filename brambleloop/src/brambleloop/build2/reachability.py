"""Is a module the proof names actually reached by the running system? (certification)

The 63f2493 closeout counted 160 requirements COMPLETE because a module named in the note
existed and had a test. A proof-chain audit then found most of them were libraries nothing in
the runtime ever called. This module makes that failure mechanically visible, so the closure
matrix cannot repeat it silently.

Static and deliberately conservative:

1. The runtime roots are the entry points a deployed system executes: the job handlers
   (`runtime/release.py`, `runtime/pipeline.py`), the worker and scheduler, and the API
   (`app/main.py`, `app/scheduler_entry.py`).
2. The *reachable* modules are every `brambleloop` module imported, at module level or inside
   a function, from a root -- transitively.
3. A module is *reached* when it is reachable AND at least one name it defines at top level
   (function, class or constant) is referenced by some other reachable module. A module that is
   imported but whose functions nobody calls is exactly the audit's "zero callers" finding.

What it cannot see is whether the reference sits on a live path (a call inside a branch that
never runs). That remains the human audit's job; this catches the cheap, common failure
without anybody having to remember to look.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # src/brambleloop
ROOTS = ("runtime/release.py", "runtime/pipeline.py", "runtime/worker.py", "app/worker_entry.py",
         "app/main.py", "app/scheduler_entry.py")


def module_name(rel: str) -> str:
    rel = rel.removesuffix(".py").replace("/", ".")
    return "brambleloop." + rel.removesuffix(".__init__")


def _path_of(mod: str) -> Path | None:
    parts = mod.split(".")[1:]
    f = PKG.joinpath(*parts).with_suffix(".py")
    if f.exists():
        return f
    init = PKG.joinpath(*parts, "__init__.py")
    return init if init.exists() else None


def _resolve(current: str, is_pkg: bool, node: ast.ImportFrom) -> list[str]:
    if node.level:
        base = current.split(".") if is_pkg else current.split(".")[:-1]
        base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
        prefix = ".".join(base + ([node.module] if node.module else []))
    else:
        prefix = node.module or ""
    if not prefix.startswith("brambleloop"):
        return []
    out = [prefix]
    for alias in node.names:
        cand = f"{prefix}.{alias.name}"
        if _path_of(cand) is not None:
            out.append(cand)
    return out


@lru_cache(maxsize=None)
def _parse(mod: str):
    path = _path_of(mod)
    if path is None:
        return None
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(mod: str) -> set[str]:
    tree = _parse(mod)
    if tree is None:
        return set()
    is_pkg = _path_of(mod).name == "__init__.py"
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(_resolve(mod, is_pkg, node))
        elif isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("brambleloop"))
    return {m for m in found if _path_of(m) is not None}


@lru_cache(maxsize=1)
def reachable() -> frozenset[str]:
    seen: set[str] = set()
    todo = [module_name(r) for r in ROOTS if _path_of(module_name(r))]
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        todo.extend(_imports(mod) - seen)
    return frozenset(seen)


def _defined(mod: str) -> set[str]:
    tree = _parse(mod)
    names: set[str] = set()
    for node in (tree.body if tree else []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


@lru_cache(maxsize=1)
def _references() -> dict[str, frozenset[str]]:
    out = {}
    for mod in reachable():
        tree = _parse(mod)
        refs: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                refs.add(node.attr)
            elif isinstance(node, ast.Name):
                refs.add(node.id)
            elif isinstance(node, ast.ImportFrom):
                refs.update(a.name for a in node.names)
        out[mod] = frozenset(refs)
    return out


def reached(rel: str) -> dict:
    """The verdict for one proof module path like `intel/serp.py`."""
    mod = module_name(rel)
    if _path_of(mod) is None:
        return {"module": rel, "reached": False, "why": "no such module"}
    if rel.startswith(tuple(ROOTS)):
        return {"module": rel, "reached": True, "why": "runtime root"}
    if mod not in reachable():
        return {"module": rel, "reached": False,
                "why": "not imported, directly or transitively, by any runtime root"}
    defined = _defined(mod) - {"__all__"}
    callers = sorted(m for m, refs in _references().items()
                     if m != mod and defined & refs)
    if not callers:
        return {"module": rel, "reached": False,
                "why": "imported, but no runtime module references anything it defines"}
    return {"module": rel, "reached": True, "why": f"referenced from {callers[0]}",
            "callers": callers[:5]}
