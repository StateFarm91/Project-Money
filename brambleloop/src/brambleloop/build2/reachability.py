"""Is a module the proof names actually reached by the running system? (certification)

The 63f2493 closeout counted 160 requirements COMPLETE because a module named in the note
existed and had a test. A proof-chain audit then found most of them were libraries nothing in
the runtime ever called. The first version of this module (C-41/C-43/C-59) made that visible
by asking whether *any* runtime module referenced *any* name a module defined -- and the
9434c53 audit (C-65) found the two ways that rule still closed a row nothing runs:

  * a module referenced only by a static route (`/api/x` returning `lib.state()`, a
    description computed from constants) counted as reached, although no job and no
    database reading ever touches it;
  * a module whose only caller put the result into an audit row (`ctx.audit(...,
    detail=lib.describe())`) counted as reached, although nothing reads the row back and
    nothing is decided by it.

So the rule is now a call graph from the things that actually execute, function by function:

1. **Live roots.** The job handlers registered with `@handlers.register(job_type)` whose job
   type is *scheduled* -- named by a cadence in `runtime/worker.py`, or enqueued (an
   `enqueue(...)` call or a `job_type=` keyword) from code that is itself live, including the
   boot enqueues in the API's startup hook. A handler only a manual operator POST can
   enqueue is not live: nothing runs it by itself. Plus the worker, scheduler and runner
   loops, and the API's startup/shutdown hooks.
2. **Routes compute from the database or they are not roots.** Inside `app/main.py` (routes
   and the module's own helpers) a reference to library code counts only when the call
   carries the database -- `db`, or a name derived from it (`s` from `db.session()`, rows
   read through it). `lib.state()` with no database argument is a description; it reaches
   nothing.
3. **Audit-only use is not use.** A call whose result lands only in the arguments of an audit
   write (`ctx.audit`, `.audit`, `AuditLog(...)`), directly or through a variable used for
   nothing else, does not reach its target -- unless the target itself writes to the
   database (adds rows, enqueues, executes an update), because then the call *is* the act and
   the audit row is only its receipt.
4. From each live function every function, class and method it references is live in turn,
   transitively. A class that is instantiated is live with its dunder methods; its other
   methods are live when some live code names them (`x.method`) -- the receiver's type is
   not tracked, so the method name is matched against live classes only.
5. A module is **reached** when one of its functions, classes or methods is live. A module
   that defines only constants is reached when live code reads one of them.

What it still cannot see is a reference inside a branch that never executes, or a result
computed and then ignored by live code; that remains the human audit's job. What it can no
longer be fooled by is a description route or an audit receipt.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from functools import lru_cache, wraps
from contextvars import ContextVar
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]          # src/brambleloop
ROOTS = ("runtime/release.py", "runtime/pipeline.py", "runtime/worker.py",
         "runtime/commerce_readings.py", "app/worker_entry.py", "app/main.py",
         "app/scheduler_entry.py", "app/runner.py")
# Modules whose every function is a runtime loop (not a library): they run by existing.
LOOP_MODULES = ("runtime/worker.py", "app/runner.py", "app/worker_entry.py",
                "app/scheduler_entry.py")
# Modules whose own module-level statements execute as runtime (the cadence table, the
# registrations). A library's module-level tables are data, not execution.
EXECUTING_MODULE_BODIES = ("runtime/worker.py", "app/main.py")
API = "app/main.py"
# Calls that are receipts rather than actions.
AUDIT_SINKS = frozenset({"audit", "AuditLog", "_audit"})
# Attribute calls that change the database or the queue.
WRITE_ATTRS = frozenset({"add", "add_all", "execute", "enqueue", "merge", "delete",
                         "bulk_save_objects", "commit", "flush"})


_GRAPH_SCOPE = ContextVar("brambleloop_graph_sources", default=None)
_POLICY_NAMES = ("ROOTS", "LOOP_MODULES", "EXECUTING_MODULE_BODIES", "API", "AUDIT_SINKS", "WRITE_ATTRS")


def _capture_graph_sources():
    root = PKG.resolve()
    if not root.is_dir():
        raise RuntimeError("runtime graph package source unavailable")
    policies = tuple((name, globals()[name]) for name in _POLICY_NAMES)
    def unreadable(error):
        raise error
    paths = []
    # pathlib glob can suppress directory traversal errors: an unreadable subtree must
    # not silently become missing evidence while another cached path still looks live.
    for directory, _dirs, files in os.walk(root, onerror=unreadable):
        paths.extend(Path(directory) / name for name in files if name.endswith(".py"))
    sources = tuple((path.relative_to(root).as_posix(), path.read_bytes())
                    for path in sorted(paths))
    return str(root), policies, sources


def _graph_boundary(function):
    @wraps(function)
    def checked(*args, **kwargs):
        if _GRAPH_SCOPE.get() is not None:
            return function(*args, **kwargs)
        captured = _capture_graph_sources()
        context = {"key": captured, "root": Path(captured[0]),
                   "policies": dict(captured[1]), "sources": dict(captured[2])}
        token = _GRAPH_SCOPE.set(context)
        try:
            result = function(*args, **kwargs)
            try:
                current = _capture_graph_sources()
            except Exception as exc:
                raise RuntimeError("runtime graph source unreadable during revalidation") from exc
            if current != captured:
                raise RuntimeError("runtime graph source changed during analysis")
            return result
        finally:
            _GRAPH_SCOPE.reset(token)
    return checked


def _policy(name):
    active = _GRAPH_SCOPE.get()
    return active["policies"][name] if active is not None else globals()[name]


def _package_root():
    active = _GRAPH_SCOPE.get()
    return active["root"] if active is not None else PKG


def _source_exists(path):
    active = _GRAPH_SCOPE.get()
    return path.relative_to(active["root"]).as_posix() in active["sources"] if active is not None else path.exists()


def module_name(rel: str) -> str:
    rel = rel.removesuffix(".py").replace("/", ".")
    return "brambleloop." + rel.removesuffix(".__init__")


def _rel_of(mod: str) -> str:
    p = _path_of(mod)
    return p.relative_to(_package_root()).as_posix() if p else mod


def _path_of(mod: str) -> Path | None:
    parts = mod.split(".")[1:]
    f = _package_root().joinpath(*parts).with_suffix(".py")
    if _source_exists(f):
        return f
    init = _package_root().joinpath(*parts, "__init__.py")
    return init if _source_exists(init) else None


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


def _from_prefix(current: str, is_pkg: bool, node: ast.ImportFrom) -> str:
    if node.level:
        base = current.split(".") if is_pkg else current.split(".")[:-1]
        base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
        return ".".join(base + ([node.module] if node.module else []))
    return node.module or ""


@lru_cache(maxsize=1024)
def _parse_source(root, rel, source):
    return ast.parse(source.decode("utf-8"), filename=str(Path(root) / rel))


@_graph_boundary
def _parse(mod: str):
    path = _path_of(mod)
    if path is None:
        return None
    active = _GRAPH_SCOPE.get()
    rel = path.relative_to(active["root"]).as_posix()
    return _parse_source(str(active["root"]), rel, active["sources"][rel])


@lru_cache(maxsize=1024)
def _imports_cached(snapshot, mod: str) -> frozenset[str]:
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
    return frozenset(m for m in found if _path_of(m) is not None)


@_graph_boundary
def _imports(mod: str):
    return _imports_cached(_GRAPH_SCOPE.get()["key"], mod)


@lru_cache(maxsize=2)
def _reachable_cached(snapshot) -> frozenset[str]:
    """Every module imported, transitively, from a runtime root (necessary, not sufficient)."""
    seen: set[str] = set()
    todo = [module_name(r) for r in _policy("ROOTS") if _path_of(module_name(r))]
    while todo:
        mod = todo.pop()
        if mod in seen:
            continue
        seen.add(mod)
        todo.extend(_imports(mod) - seen)
    return frozenset(seen)


@_graph_boundary
def reachable() -> frozenset[str]:
    return _reachable_cached(_GRAPH_SCOPE.get()["key"])


# ---------------------------------------------------------------------------
# the per-module symbol tables


@dataclass
class _Module:
    name: str
    tree: ast.Module
    aliases: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    funcs: dict[str, ast.AST] = field(default_factory=dict)       # 'f' and 'C.m'
    classes: dict[str, ast.ClassDef] = field(default_factory=dict)
    consts: dict[str, ast.AST] = field(default_factory=dict)      # NAME -> value node

    def const_str(self, name: str) -> str | None:
        v = self.consts.get(name)
        return v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else None


def _aliases_in(mod: str, nodes) -> dict[str, tuple[str, str | None]]:
    out: dict[str, tuple[str, str | None]] = {}
    is_pkg = _path_of(mod).name == "__init__.py"
    for node in nodes:
        if isinstance(node, ast.ImportFrom):
            prefix = _from_prefix(mod, is_pkg, node)
            if not prefix.startswith("brambleloop"):
                continue
            for a in node.names:
                cand = f"{prefix}.{a.name}"
                key = a.asname or a.name
                out[key] = (cand, None) if _path_of(cand) is not None else (prefix, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("brambleloop") and a.asname:
                    out[a.asname] = (a.name, None)
    return out


def _module_level(tree: ast.Module):
    """Every node outside a function body (imports under `try`/`if` at module level count)."""
    todo = list(tree.body)
    while todo:
        n = todo.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        todo.extend(ast.iter_child_nodes(n))


def _table(mod: str) -> _Module:
    tree = _parse(mod)
    m = _Module(mod, tree)
    m.aliases = _aliases_in(mod, _module_level(tree))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            m.funcs[node.name] = node
        elif isinstance(node, ast.ClassDef):
            m.classes[node.name] = node
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m.funcs[f"{node.name}.{sub.name}"] = sub
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    m.consts[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            m.consts[node.target.id] = node.value
    return m


def _body_nodes(fn: ast.AST):
    """Walk a function's body and defaults, never its annotations: a type hint runs nothing."""
    parts: list[ast.AST] = []
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        parts.extend(fn.body)
        parts.extend(d for d in fn.args.defaults if d is not None)
        parts.extend(d for d in fn.args.kw_defaults if d is not None)
    else:
        parts.append(fn)
    for p in parts:
        yield from ast.walk(p)


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# ---------------------------------------------------------------------------
# the analysis


class _Analysis:
    def __init__(self) -> None:
        self.mods = {m: _table(m) for m in reachable() if _parse(m) is not None}
        self.live: dict[tuple[str, str], str] = {}     # key -> how it became live
        self.candidates: set[str] = set()                # method names live code mentions
        self.handlers = self._registered_handlers()
        self.scheduled: dict[str, str] = {}               # job_type -> who schedules it
        self._writes = self._compute_writes()
        self._queue: list[tuple[str, str, str, str]] = []  # (mod, qual, mode, why)
        self._visited: set[tuple[str, str, str]] = set()
        self._run()

    # -- symbol resolution ---------------------------------------------------

    def _lookup(self, mod: str, name: str, depth: int = 0) -> tuple[str, str] | None:
        """A name in a module -> the (module, qualname) that defines it, following re-exports."""
        t = self.mods.get(mod)
        if t is None or depth > 5:
            return None
        if name in t.funcs or name in t.classes or name in t.consts:
            return (mod, name)
        if name in t.aliases:
            target, attr = t.aliases[name]
            if attr is None:
                return None
            return self._lookup(target, attr, depth + 1)
        return None

    def _resolve_ref(self, mod: str, node: ast.AST, cls: str | None,
                     local: dict | None = None) -> tuple[str, str] | None:
        t = self.mods[mod]
        aliases = {**t.aliases, **(local or {})}
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in aliases and (local and node.id in local):
                target, attr = aliases[node.id]
                return self._lookup(target, attr) if attr else None
            if node.id in t.funcs or node.id in t.classes or node.id in t.consts:
                return (mod, node.id)
            if node.id in aliases:
                target, attr = aliases[node.id]
                return self._lookup(target, attr) if attr else None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base in ("self", "cls") and cls and f"{cls}.{node.attr}" in t.funcs:
                return (mod, f"{cls}.{node.attr}")
            if base in aliases and aliases[base][1] is None:
                return self._lookup(aliases[base][0], node.attr)
        return None

    def _job_type_of(self, mod: str, node: ast.AST, local: dict | None = None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        ref = self._resolve_ref(mod, node, None, local)
        if ref and ref[1] in self.mods[ref[0]].consts:
            return self.mods[ref[0]].const_str(ref[1])
        return None

    # -- the registered handlers -------------------------------------------

    def _registered_handlers(self) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for mod, t in self.mods.items():
            for qual, fn in t.funcs.items():
                for d in getattr(fn, "decorator_list", []):
                    if isinstance(d, ast.Call) and _call_name(d) == "register" and d.args:
                        jt = self._job_type_of(mod, d.args[0])
                        if jt:
                            out[jt] = (mod, qual)
        return out

    # -- which functions write ---------------------------------------------

    def _compute_writes(self) -> set[tuple[str, str]]:
        direct: set[tuple[str, str]] = set()
        calls: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for mod, t in self.mods.items():
            for qual, fn in t.funcs.items():
                cls = qual.split(".")[0] if "." in qual else None
                out: set[tuple[str, str]] = set()
                nodes = list(_body_nodes(fn))
                local = _aliases_in(mod, nodes)
                for n in nodes:
                    if isinstance(n, ast.Call):
                        if isinstance(n.func, ast.Attribute) and n.func.attr in _policy("WRITE_ATTRS"):
                            direct.add((mod, qual))
                        ref = self._resolve_ref(mod, n.func, cls, local)
                        if ref:
                            out.add(ref)
                calls[(mod, qual)] = out
        writes = set(direct)
        changed = True
        while changed:
            changed = False
            for k, outs in calls.items():
                if k in writes:
                    continue
                if any(o in writes or any(w[0] == o[0] and w[1].startswith(o[1] + ".")
                                          for w in writes if o[1] in self.mods[o[0]].classes)
                       for o in outs):
                    writes.add(k)
                    changed = True
        return writes

    def _target_writes(self, key: tuple[str, str]) -> bool:
        mod, qual = key
        if key in self._writes:
            return True
        if qual in self.mods[mod].classes:
            return any(w[0] == mod and w[1].startswith(qual + ".") for w in self._writes)
        return False

    # -- visiting live code -------------------------------------------------

    def _mark(self, key: tuple[str, str], why: str) -> None:
        mod, qual = key
        if key in self.live:
            return
        self.live[key] = why
        t = self.mods[mod]
        if qual in t.funcs:
            self._queue.append((mod, qual, "full", why))
        elif qual in t.classes:
            cdef = t.classes[qual]
            for part in list(cdef.bases) + list(cdef.decorator_list):
                self._queue.append((mod, f"<expr:{id(part)}>", "full", why))
                self._exprs[id(part)] = (part, qual)
            for q in t.funcs:
                if q.startswith(qual + ".") and q.split(".", 1)[1].startswith("__"):
                    self._mark((mod, q), why)
            self._rescan_methods()
        elif qual in t.consts:
            v = t.consts[qual]
            if v is not None:
                self._exprs[id(v)] = (v, None)
                self._queue.append((mod, f"<expr:{id(v)}>", "full", why))

    def _rescan_methods(self) -> None:
        for key in list(self.live):
            mod, qual = key
            t = self.mods[mod]
            if qual not in t.classes:
                continue
            for q in t.funcs:
                if q.startswith(qual + ".") and q.split(".", 1)[1] in self.candidates:
                    if (mod, q) not in self.live:
                        self._mark((mod, q), self.live[key])

    def _db_names(self, fn: ast.AST) -> set[str]:
        names = {"db"}
        changed = True
        nodes = list(_body_nodes(fn))
        while changed:
            changed = False

            def carries(expr) -> bool:
                return any(isinstance(x, ast.Name) and x.id in names for x in ast.walk(expr))

            def bind(target) -> None:
                nonlocal changed
                for x in ast.walk(target):
                    if isinstance(x, ast.Name) and x.id not in names:
                        names.add(x.id)
                        changed = True

            for n in nodes:
                if isinstance(n, ast.Assign) and carries(n.value):
                    for t in n.targets:
                        bind(t)
                elif isinstance(n, (ast.AugAssign, ast.AnnAssign)) and n.value is not None \
                        and carries(n.value):
                    bind(n.target)
                elif isinstance(n, ast.withitem) and n.optional_vars is not None \
                        and carries(n.context_expr):
                    bind(n.optional_vars)
                elif isinstance(n, (ast.For, ast.comprehension)) and carries(n.iter):
                    bind(n.target)
                elif isinstance(n, ast.NamedExpr) and carries(n.value):
                    bind(n.target)
        return names

    def _audit_only_nodes(self, nodes: list[ast.AST]) -> set[int]:
        """ids of nodes whose value goes only into an audit write."""
        inside: set[int] = set()
        for n in nodes:
            if isinstance(n, ast.Call) and _call_name(n) in _policy("AUDIT_SINKS"):
                for a in list(n.args) + [k.value for k in n.keywords]:
                    inside.update(id(x) for x in ast.walk(a))
        # a variable assigned from a call and then read only inside audit writes
        loads: dict[str, list[int]] = {}
        for n in nodes:
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                loads.setdefault(n.id, []).append(id(n))
        for n in nodes:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call):
                uses = loads.get(n.targets[0].id, [])
                if uses and all(u in inside for u in uses):
                    inside.update(id(x) for x in ast.walk(n.value))
        return inside

    def _visit(self, mod: str, qual: str, mode: str, why: str) -> None:
        t = self.mods[mod]
        if qual.startswith("<expr:"):
            node, cls = self._exprs[int(qual[6:-1])]
        elif qual == "<module>":
            node, cls = ast.Module(body=[s for s in t.tree.body
                                         if not isinstance(s, (ast.FunctionDef,
                                                               ast.AsyncFunctionDef,
                                                               ast.ClassDef))],
                                   type_ignores=[]), None
        else:
            node = t.funcs[qual]
            cls = qual.split(".")[0] if "." in qual else None
        nodes = list(_body_nodes(node)) if qual not in ("<module>",) and not qual.startswith(
            "<expr:") else list(ast.walk(node))
        here = f"{_rel_of(mod)}:{'module constant' if qual.startswith('<expr:') else qual}"
        local = _aliases_in(mod, nodes)
        audit_only = self._audit_only_nodes(nodes)

        # the enqueues this code performs
        for n in nodes:
            if not isinstance(n, ast.Call):
                continue
            name = _call_name(n)
            jts: list[str] = []
            if "enqueue" in name.lower() and mode != "route":
                for a in n.args[:3]:
                    jt = self._job_type_of(mod, a, local)
                    if jt:
                        jts.append(jt)
            for k in n.keywords:
                if k.arg == "job_type" and mode != "route":
                    jt = self._job_type_of(mod, k.value, local)
                    if jt:
                        jts.append(jt)
            for jt in jts:
                self._schedule(jt, f"enqueued by {here}")
        if qual == "<module>" and _rel_of(mod) == "runtime/worker.py":
            for n in nodes:
                if isinstance(n, ast.Tuple) and len(n.elts) == 4:
                    jt = self._job_type_of(mod, n.elts[2], local)
                    if jt:
                        self._schedule(jt, f"cadence in {_rel_of(mod)}")
        # functions returning cadence tuples (the generated role cadences)
        if qual != "<module>" and _rel_of(mod) == "runtime/worker.py":
            for n in nodes:
                if isinstance(n, ast.Tuple) and len(n.elts) == 4:
                    jt = self._job_type_of(mod, n.elts[2], local)
                    if jt:
                        self._schedule(jt, f"cadence in {here}")

        if mode == "route":
            dbn = self._db_names(node)
            counted: set[int] = set()
            # A guard is a use: a call made inside a `try` whose handler answers the request
            # instead (the ops-token check) refuses work, whether or not it reads the database.
            guards: set[int] = set()
            for n in nodes:
                if isinstance(n, ast.Try) and n.handlers:
                    for st in n.body:
                        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
                            guards.add(id(st.value))
                    for h in n.handlers:
                        if h.type is not None:
                            counted.update(id(x) for x in ast.walk(h.type))
            for n in nodes:
                if not isinstance(n, ast.Call):
                    continue
                if id(n) in guards:
                    counted.update(id(x) for x in ast.walk(n.func))
                carries = any(isinstance(x, ast.Name) and x.id in dbn
                              for a in list(n.args) + [k.value for k in n.keywords]
                              for x in ast.walk(a))
                recv = n.func.value if isinstance(n.func, ast.Attribute) else None
                if recv is not None and any(isinstance(x, ast.Name) and x.id in dbn
                                            for x in ast.walk(recv)):
                    carries = True
                ref = self._resolve_ref(mod, n.func, cls, local)
                if ref and ref[0] == mod and ref[1] in t.funcs:
                    counted.add(id(n.func))          # the API's own helpers: visited as routes
                    self._queue.append((mod, ref[1], "route", why))
                    continue
                if carries:
                    counted.update(id(x) for x in ast.walk(n.func))
                    if isinstance(n.func, ast.Attribute):
                        self.candidates.add(n.func.attr)
            refs = [n for n in nodes if id(n) in counted]
        else:
            refs = nodes
            for n in nodes:
                if isinstance(n, ast.Attribute) and id(n) not in audit_only:
                    self.candidates.add(n.attr)
        for n in refs:
            if not isinstance(n, (ast.Name, ast.Attribute)):
                continue
            ref = self._resolve_ref(mod, n, cls, local)
            if ref is None or ref == (mod, qual):
                continue
            if id(n) in audit_only and not self._target_writes(ref):
                continue
            if mode == "route" and ref[0] == mod:
                continue
            self._mark(ref, f"{why} -> {here}")
        self._rescan_methods()

    def _schedule(self, jt: str, why: str) -> None:
        if jt in self.scheduled:
            return
        self.scheduled[jt] = why
        h = self.handlers.get(jt)
        if h:
            self._mark(h, f"handler {jt} ({why})")

    def _run(self) -> None:
        self._exprs: dict[int, tuple[ast.AST, str | None]] = {}
        for rel in _policy("LOOP_MODULES"):
            mod = module_name(rel)
            if mod not in self.mods:
                continue
            for qual in self.mods[mod].funcs:
                self._mark((mod, qual), f"runtime loop {rel}")
            for c in self.mods[mod].classes:
                self._mark((mod, c), f"runtime loop {rel}")
        for rel in _policy("EXECUTING_MODULE_BODIES"):
            mod = module_name(rel)
            if mod in self.mods:
                self._queue.append((mod, "<module>", "full", f"module body {rel}"))
        api = module_name(_policy("API"))
        if api in self.mods:
            for qual, fn in self.mods[api].funcs.items():
                for d in getattr(fn, "decorator_list", []):
                    f = d.func if isinstance(d, ast.Call) else d
                    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) \
                            and f.value.id == "app":
                        mode = "full" if f.attr == "on_event" else "route"
                        self._queue.append((api, qual, mode, f"API {f.attr} {qual}"))
        while self._queue:
            mod, qual, mode, why = self._queue.pop()
            key = (mod, qual, mode)
            if key in self._visited:
                continue
            self._visited.add(key)
            self._visit(mod, qual, mode, why)
            if not self._queue:
                self._rescan_methods()

    # -- the verdict ----------------------------------------------------------

    def module_verdict(self, mod: str) -> tuple[bool, str, list[str]]:
        t = self.mods.get(mod)
        if t is None:
            return False, "not imported, directly or transitively, by any runtime root", []
        has_code = bool(t.funcs or t.classes)
        live = [(q, w) for (m, q), w in self.live.items() if m == mod
                and (q in t.funcs or q in t.classes or (not has_code and q in t.consts))]
        if live:
            live.sort(key=lambda qw: (qw[0] not in t.funcs, len(qw[1])))
            q, w = live[0]
            return True, f"{q} is live: {w}", [q for q, _ in live]
        imported_by = sorted(m for m in self.mods if m != mod and mod in _imports(m))
        return False, ("imported, but no live path reaches anything it defines: no scheduled "
                       "handler, cadence, runtime loop or database-computing route calls it "
                       "(a static route or an audit receipt is not a caller)"
                       + (f"; imported by {imported_by[0]}" if imported_by else "")), []


@lru_cache(maxsize=2)
def _references_cached(snapshot) -> _Analysis:
    return _Analysis()


@_graph_boundary
def _references() -> _Analysis:
    return _references_cached(_GRAPH_SCOPE.get()["key"])


@_graph_boundary
def analysis() -> _Analysis:
    return _references()


@_graph_boundary
def reached(rel: str) -> dict:
    """The verdict for one proof module path like `intel/serp.py`."""
    mod = module_name(rel)
    if _path_of(mod) is None:
        return {"module": rel, "reached": False, "why": "no such module"}
    if rel in _policy("ROOTS"):
        return {"module": rel, "reached": True, "why": "runtime root"}
    if mod not in reachable():
        return {"module": rel, "reached": False,
                "why": "not imported, directly or transitively, by any runtime root"}
    ok, why, live = _references().module_verdict(mod)
    out = {"module": rel, "reached": ok, "why": why}
    if ok:
        out["live"] = live[:8]
    return out


@_graph_boundary
def function_reached(rel: str, qual: str) -> dict:
    """Is one named function (or `Class.method`) on a live path? For row-level proofs."""
    a = _references()
    key = (module_name(rel), qual)
    why = a.live.get(key)
    return {"module": rel, "function": qual, "reached": why is not None,
            "why": why or "no live path reaches it"}


def clear_cache() -> None:
    _parse_source.cache_clear()
    _imports_cached.cache_clear()
    _reachable_cached.cache_clear()
    _references_cached.cache_clear()


# Existing certification callers explicitly clear these caches between fixtures.
_parse.cache_clear = _parse_source.cache_clear
_imports.cache_clear = _imports_cached.cache_clear
reachable.cache_clear = _reachable_cached.cache_clear
_references.cache_clear = _references_cached.cache_clear
