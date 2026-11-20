"""ENG-RECOVERY fix round 1 (H1): which job handlers can reach a paid provider call.

A conservative static call graph over `src/brambleloop`, used by test_eng_recovery to prove
that every job type on `swarm.orchestrate.FREE_JOB_TYPES` cannot reach the paid gateway, and
that every job type that can is classified as spending.

What counts as a paid entry point (a "sink"):
- by name, wherever it appears (receiver unknown): `provider_for`, `for_task` -- each returns a
  paid provider whose methods the graph cannot follow on an unknown object;
- by resolution: `gateway.paid_calls.guarded`, `gateway.laura_converse.call`,
  `gateway.images.generate`, `gateway.providers.for_task`, both `provider_for`s;
- every function or method in a module declared in test_cert_spend_hosts.DECLARED as a paid
  request path, or in any `gateway` module other than the reviewed free reads, whose body
  builds an HTTP request (`urlopen`, `Request(`, `_post(`, `.post(`,
  `http.client`). A reference to a provider class reaches all its methods, so constructing one
  reaches its request method.

Edges are over-approximated: a reference to a function (called or passed as a callback) is an
edge; a reference to a class is an edge to every method of that class; `self.x` is an edge to
`x` in the same class; nested functions and lambdas belong to their enclosing function;
import aliases are collected per module from every import statement in the file (function-
local imports included). What it cannot see -- a method called on an object handed in from
outside (dependency injection), or `getattr` by string -- is the stated limit; the explicit
allow-list is the runtime rule, and this graph only has to agree with it.
"""
from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = "brambleloop"

SINK_NAMES = frozenset({"provider_for", "for_task"})
SINK_KEYS = frozenset({
    ("brambleloop.gateway.paid_calls", "guarded"),
    ("brambleloop.gateway.laura_converse", "call"),
    ("brambleloop.gateway.images", "generate"),
    ("brambleloop.gateway.providers", "for_task"),
    ("brambleloop.gateway.anthropic", "provider_for"),
    ("brambleloop.gateway.openai_chat", "provider_for"),
})
GATEWAY = "brambleloop.gateway."
# test_cert_spend_hosts.DECLARED entries reviewed as free reads (no billable call); their
# request sites are not paid entry points. Every other DECLARED module's are.
# ENG-VIS-FLUX: `gateway.flux_contract` is declared data only (the verified BFL contract and
# its citation URLs; test_cert_spend_hosts pins that it holds no HTTP client).
FREE_REQUEST_MODULES = frozenset({"brambleloop.gateway.credentials",
                                  "brambleloop.ops.provider_accounts",
                                  "brambleloop.ops.adoptions",
                                  "brambleloop.gateway.flux_contract"})
REQUEST_MARKERS = ("urlopen", "Request(", "_post(", ".post(", "http.client")


def _modname(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class Graph:
    def __init__(self, request_modules: set[str]):
        self.trees: dict[str, ast.Module] = {}
        self.sources: dict[str, str] = {}
        self.is_pkg: dict[str, bool] = {}
        for path in sorted((SRC / PKG).rglob("*.py")):
            mod = _modname(path)
            text = path.read_text(encoding="utf-8")
            self.sources[mod] = text
            self.trees[mod] = ast.parse(text)
            self.is_pkg[mod] = path.name == "__init__.py"
        self.funcs: dict[tuple[str, str], ast.AST] = {}
        self.top: dict[str, dict[str, tuple[str, str]]] = {}
        self.classes: dict[str, dict[str, list[tuple[str, str]]]] = {}
        self.aliases: dict[str, dict[str, set[tuple]]] = {}
        for mod, tree in self.trees.items():
            top, classes = {}, {}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    key = (mod, node.name)
                    self.funcs[key] = node
                    top[node.name] = key
                elif isinstance(node, ast.ClassDef):
                    methods = []
                    for sub in node.body:
                        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            key = (mod, f"{node.name}.{sub.name}")
                            self.funcs[key] = sub
                            methods.append(key)
                    classes[node.name] = methods
            self.top[mod], self.classes[mod] = top, classes
            self.aliases[mod] = self._aliases(mod, tree)
        self.sinks: set[tuple[str, str]] = {k for k in SINK_KEYS if k in self.funcs}
        for key, node in self.funcs.items():
            if key[0] in request_modules or (
                    key[0].startswith(GATEWAY) and key[0] not in FREE_REQUEST_MODULES):
                seg = ast.get_source_segment(self.sources[key[0]], node) or ""
                if any(m in seg for m in REQUEST_MARKERS):
                    self.sinks.add(key)

    # -- imports ---------------------------------------------------------------------------
    def _base(self, mod: str, level: int) -> str:
        parts = mod.split(".")
        if not self.is_pkg.get(mod):
            parts = parts[:-1]
        if level > 1:
            parts = parts[:len(parts) - (level - 1)]
        return ".".join(parts)

    def _aliases(self, mod: str, tree: ast.Module) -> dict[str, set[tuple]]:
        out: dict[str, set[tuple]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if not a.name.startswith(PKG):
                        continue
                    if a.asname:
                        out.setdefault(a.asname, set()).add(("mod", a.name))
                    else:
                        out.setdefault(a.name.split(".")[0], set()).add(("mod", PKG))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = self._base(mod, node.level)
                    src = f"{base}.{node.module}" if node.module else base
                else:
                    src = node.module or ""
                if not src.startswith(PKG):
                    continue
                for a in node.names:
                    name = a.asname or a.name
                    full = f"{src}.{a.name}"
                    if full in self.trees:
                        out.setdefault(name, set()).add(("mod", full))
                    else:
                        out.setdefault(name, set()).add(("sym", src, a.name))
        return out

    # -- resolution ------------------------------------------------------------------------
    def _symbol(self, mod: str, name: str, depth: int = 0) -> set[tuple[str, str]]:
        if depth > 6 or mod not in self.trees:
            return set()
        if name in self.top[mod]:
            return {self.top[mod][name]}
        if name in self.classes[mod]:
            return set(self.classes[mod][name])
        out: set[tuple[str, str]] = set()
        for target in self.aliases[mod].get(name, ()):
            if target[0] == "sym":
                out |= self._symbol(target[1], target[2], depth + 1)
        return out

    def _chain(self, mod: str, chain: list[str]) -> set[tuple[str, str]]:
        """Resolve `root.a.b...` where root is a name in `mod`."""
        root, rest = chain[0], chain[1:]
        out: set[tuple[str, str]] = set()
        if root in self.top[mod] or root in self.classes[mod]:
            hits = self._symbol(mod, root)
            if rest and root in self.classes[mod]:
                meth = (mod, f"{root}.{rest[0]}")
                return {meth} if meth in self.funcs else hits
            return hits
        for target in self.aliases[mod].get(root, ()):
            if target[0] == "sym":
                out |= self._symbol(target[1], target[2])
                continue
            cur = target[1]
            i = 0
            while i < len(rest) and f"{cur}.{rest[i]}" in self.trees:
                cur = f"{cur}.{rest[i]}"
                i += 1
            if i < len(rest):
                out |= self._symbol(cur, rest[i])
        return out

    @lru_cache(maxsize=None)  # noqa: B019 - one graph per process
    def edges(self, key: tuple[str, str]) -> tuple[frozenset, bool]:
        """(callees, direct sink by name) of one function."""
        mod, qual = key
        node = self.funcs[key]
        cls = qual.split(".")[0] if "." in qual else None
        out: set[tuple[str, str]] = set()
        named_sink = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute):
                if sub.attr in SINK_NAMES:
                    named_sink = True
                chain, cur = [], sub
                while isinstance(cur, ast.Attribute):
                    chain.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    chain.append(cur.id)
                    chain.reverse()
                    if cls and chain[0] in ("self", "cls"):
                        meth = (mod, f"{cls}.{chain[1]}")
                        if meth in self.funcs:
                            out.add(meth)
                    else:
                        out |= self._chain(mod, chain)
            elif isinstance(sub, ast.Name):
                if sub.id in SINK_NAMES:
                    named_sink = True
                out |= self._chain(mod, [sub.id])
        out.discard(key)
        return frozenset(out), named_sink

    def reach(self, start: tuple[str, str]) -> list[tuple[str, str]] | None:
        """A path from `start` to a paid entry point, or None."""
        if start not in self.funcs:
            raise KeyError(start)
        prev: dict[tuple[str, str], tuple[str, str] | None] = {start: None}
        queue = [start]
        while queue:
            cur = queue.pop(0)
            callees, named = self.edges(cur)
            if named or cur in self.sinks:
                path = [cur]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return list(reversed(path))
            for nxt in callees:
                if nxt not in prev:
                    prev[nxt] = cur
                    queue.append(nxt)
        return None


def handler_key(fn) -> tuple[str, str]:
    """The graph key of a registered handler: its top-level function or method."""
    import inspect

    fn = inspect.unwrap(fn)
    qual = fn.__qualname__
    if ".<locals>." in qual:
        qual = qual.split(".<locals>.")[0]
    return fn.__module__, qual
