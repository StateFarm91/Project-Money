"""Which audit actions the code reads by name -- resolved through constants, imports and
helper parameters, not only string literals.

`ops.retention.unknown_read_actions` used to match `AuditLog.action == "literal"` with a
regex, so an action read through a constant (`AuditLog.action == SNAPSHOT_ACTION`), an
imported constant (`vision.TASK`), a tuple of constants, or a helper's parameter
(`_rows(db, OBSERVED_ACTION)` -> `AuditLog.action == action`) was invisible, and retention
could prune evidence that is still read (Workstream C found 43 such actions).

This scanner parses every module with `ast` and, for every read site --
`AuditLog.action == X`, `AuditLog.action.in_(X)`, `AuditLog.action.like/startswith(X)` --
resolves `X` through:

* string literals, tuples/lists/sets and `tuple()/frozenset()/sorted()` of them;
* module-level and class-level constants, followed across `import`/`from ... import`;
* attributes of imported modules (`vision.TASK`) and of classes (`Cls.X`, `self.X`);
* local assignments and `for` loop variables inside the enclosing function;
* the enclosing function's parameters, by finding every call site of that function in the
  package (positional or keyword argument, else the parameter default), transitively;
* dict values (a subscript reads one of them: the union is a conservative superset),
  `a if c else b`, and `a or b`.

Anything it cannot resolve is reported as an unresolved *site* (file, line, why), never
silently dropped. The guard fails closed: an unresolved site must be fixed or explicitly
listed with a reason (`retention.UNRESOLVED_READ_SITES`).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKAGE = "brambleloop"
_COLLECTIONS = {"tuple", "list", "set", "frozenset", "sorted"}


@dataclass
class _Mod:
    name: str
    path: Path
    tree: ast.Module
    is_pkg: bool
    consts: dict = field(default_factory=dict)      # name -> [expr]
    imports: dict = field(default_factory=dict)     # local -> (module, attr | None)
    funcs: dict = field(default_factory=dict)       # qualname -> FunctionDef
    classes: set = field(default_factory=set)
    fields: dict = field(default_factory=dict)      # class -> ordered field names


@dataclass
class Scan:
    exact: dict          # action -> sorted list of "path:line"
    prefixes: dict       # prefix -> sorted list of "path:line"
    unresolved: list     # {"site", "why"}


def _abs(mod: _Mod, level: int, module: str | None) -> str:
    if not level:
        return module or ""
    parts = mod.name.split(".")
    base = parts if mod.is_pkg else parts[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join(base + ([module] if module else []))


def _load(root: Path) -> dict[str, _Mod]:
    mods: dict[str, _Mod] = {}
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root).with_suffix("")
        parts = [PACKAGE, *rel.parts]
        is_pkg = parts[-1] == "__init__"
        if is_pkg:
            parts = parts[:-1]
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        m = _Mod(".".join(parts), p, tree, is_pkg)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = _abs(m, node.level, node.module)
                for a in node.names:
                    m.imports[a.asname or a.name] = (base, a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        m.imports[a.asname] = (a.name, None)
        for node in tree.body:
            _collect(m, node, prefix="")
        for node in ast.walk(tree):  # nested helpers (`def count(action)` inside a function)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and node not in m.funcs.values():
                m.funcs.setdefault(node.name, node)
        for node in ast.walk(tree):  # dataclass-style field order, for `Cls(a, b)` instances
            if isinstance(node, ast.ClassDef):
                m.fields[node.name] = [b.target.id for b in node.body
                                       if isinstance(b, ast.AnnAssign)
                                       and isinstance(b.target, ast.Name)]
        mods[m.name] = m
    return mods


def _collect(m: _Mod, node: ast.AST, prefix: str) -> None:
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                m.consts.setdefault(prefix + t.id, []).append(node.value)
    elif isinstance(node, ast.AnnAssign) and node.value is not None \
            and isinstance(node.target, ast.Name):
        m.consts.setdefault(prefix + node.target.id, []).append(node.value)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        m.funcs[prefix + node.name] = node
    elif isinstance(node, ast.ClassDef) and not prefix:
        m.classes.add(node.name)
        for b in node.body:
            _collect(m, b, prefix=node.name + ".")
    elif isinstance(node, (ast.If, ast.Try)) and not prefix:
        for b in [*node.body, *getattr(node, "orelse", []), *getattr(node, "finalbody", []),
                  *[x for h in getattr(node, "handlers", []) for x in h.body]]:
            _collect(m, b, prefix)


@dataclass
class _Elt:
    """Element `index` of each item a loop iterates (`for a, b in X`)."""
    iter: ast.AST
    index: int


class _Resolver:
    def __init__(self, mods: dict[str, _Mod]):
        self.mods = mods
        self._calls: dict[str, list] | None = None

    # -- values ------------------------------------------------------------------------
    def value(self, expr, mod: _Mod, fn, depth: int = 0, dv: bool = False, env=None):
        """-> (set of strings, set of (modname, funcqual, param)), raising ValueError(why).

        A dict resolves to its keys (iterating, `tuple()`, `in_()`), or to its values when
        subscripted or read through `.values()` (`dv`). `env` maps comprehension variables
        to what they iterate."""
        env = env or {}
        if depth > 25:
            raise ValueError("resolution too deep")
        d = depth + 1
        if isinstance(expr, _Elt):
            return self._element(expr, mod, fn, d, env)
        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                return {expr.value}, set()
            if expr.value is None:
                return set(), set()
            raise ValueError(f"non-string constant {expr.value!r}")
        if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
            return self._union([e.value if isinstance(e, ast.Starred) else e
                                for e in expr.elts], mod, fn, d, env=env)
        if isinstance(expr, ast.Dict):
            return self._union(expr.values if dv else [k for k in expr.keys if k is not None],
                               mod, fn, d, env=env)
        if isinstance(expr, ast.IfExp):
            return self._union([expr.body, expr.orelse], mod, fn, d, dv, env)
        if isinstance(expr, ast.BoolOp):
            return self._union(expr.values, mod, fn, d, dv, env)
        if isinstance(expr, ast.Subscript):
            return self.value(expr.value, mod, fn, d, True, env)
        if isinstance(expr, ast.Call):
            f = expr.func
            if isinstance(f, ast.Name) and f.id in _COLLECTIONS:
                return self._union(expr.args[:1], mod, fn, d, env=env)
            if isinstance(f, ast.Attribute) and f.attr in ("keys", "values") and not expr.args:
                return self.value(f.value, mod, fn, d, f.attr == "values", env)
            return self._returns(expr, mod, d)
        if isinstance(expr, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            if not isinstance(expr.elt, ast.Name):
                self._raise(expr)
            inner = dict(env)
            for g in expr.generators:
                if not isinstance(g.target, ast.Name):
                    self._raise(expr)
                inner[g.target.id] = g.iter
            return self.value(expr.elt, mod, fn, d, False, inner)
        if isinstance(expr, ast.Name):
            if expr.id in env:
                target = env[expr.id]
                rest = {k: v for k, v in env.items() if k != expr.id}
                return self.value(target, mod, fn, d, False, rest)
            return self._name(expr.id, mod, fn, d, dv)
        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name) and expr.value.id in env:
                return self._field(expr.attr, env[expr.value.id], mod, fn, d)
            return self._attr(expr, mod, fn, d, dv)
        self._raise(expr)

    def _literal(self, expr, mod, depth=0):
        """The literal AST nodes a constant expression stands for: [(node, module)]."""
        if depth > 10:
            raise ValueError("literal too deep")
        if isinstance(expr, ast.Name):
            if expr.id in mod.consts:
                return [x for e in mod.consts[expr.id] for x in self._literal(e, mod, depth + 1)]
            if expr.id in mod.imports:
                base, attr = mod.imports[expr.id]
                if attr and base in self.mods and attr in self.mods[base].consts:
                    src = self.mods[base]
                    return [x for e in src.consts[attr] for x in self._literal(e, src, depth + 1)]
            raise ValueError(f"no literal for {expr.id}")
        if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
            target = self._module_of(expr.value.id, mod)
            if target is not None and expr.attr in target.consts:
                return [x for e in target.consts[expr.attr]
                        for x in self._literal(e, target, depth + 1)]
            raise ValueError(f"no literal for {ast.unparse(expr)[:60]}")
        return [(expr, mod)]

    def _items(self, it, mod):
        """(item node, module, kind) for each item a loop over `it` yields."""
        kind = "item"
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and not it.args:
            if it.func.attr in ("items", "keys", "values"):
                kind, it = it.func.attr, it.func.value
        out = []
        for node, m in self._literal(it, mod):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values):
                    out.append((ast.Tuple(elts=[k, v]) if kind == "items" else
                                v if kind == "values" else k, m))
            elif isinstance(node, (ast.Tuple, ast.List, ast.Set)):
                out.extend((e, m) for e in node.elts)
            else:
                raise ValueError(f"cannot iterate {type(node).__name__}")
        return out

    def _element(self, elt: _Elt, mod, fn, d, env):
        vals, params = set(), set()
        for item, m in self._items(elt.iter, mod):
            if not isinstance(item, ast.Tuple) or elt.index >= len(item.elts):
                raise ValueError("loop item is not a tuple of the unpacked width")
            v, p = self.value(item.elts[elt.index], m, None, d, False, env)
            vals |= v
            params |= p
        return vals, params

    def _field(self, attr, it, mod, fn, d):
        """`x.attr` where `x` iterates instances built as `Cls(...)` literals."""
        vals, params = set(), set()
        for item, m in self._items(it, mod):
            if not (isinstance(item, ast.Call) and isinstance(item.func, ast.Name)):
                raise ValueError(f"cannot read .{attr} of {type(item).__name__}")
            arg = next((k.value for k in item.keywords if k.arg == attr), None)
            order = m.fields.get(item.func.id, [])
            if arg is None and attr in order and order.index(attr) < len(item.args):
                arg = item.args[order.index(attr)]
            if arg is None:
                raise ValueError(f"{item.func.id}(...) sets no {attr}")
            v, p = self.value(arg, m, None, d)
            vals |= v
            params |= p
        return vals, params

    def _returns(self, call, mod, d):
        """A call to a package function with no arguments: what its `return`s resolve to."""
        if call.args or call.keywords:
            raise ValueError(f"call {ast.unparse(call)[:60]}")
        for m, q in self._targets(call.func, mod):
            target = self.mods.get(m)
            fn = target.funcs.get(q) if target else None
            if fn is None:
                continue
            rets = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value]
            if rets:
                return self._union(rets, target, fn, d)
        raise ValueError(f"call {ast.unparse(call)[:60]}")

    @staticmethod
    def _raise(expr):
        raise ValueError(f"cannot resolve {type(expr).__name__}: {ast.unparse(expr)[:60]}")

    def _union(self, exprs, mod, fn, d, dv=False, env=None):
        vals, params = set(), set()
        for e in exprs:
            v, p = self.value(e, mod, fn, d, dv, env)
            vals |= v
            params |= p
        return vals, params

    def _locals(self, name: str, fn):
        assigned, loops = [], []
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                    assigned.append(node.value)
            elif isinstance(node, ast.AnnAssign) and node.value is not None \
                    and isinstance(node.target, ast.Name) and node.target.id == name:
                assigned.append(node.value)
            elif isinstance(node, (ast.For, ast.comprehension)):
                t = node.target
                if isinstance(t, ast.Name) and t.id == name:
                    loops.append(node.iter)
                elif isinstance(t, ast.Tuple):
                    for i, e in enumerate(t.elts):
                        if isinstance(e, ast.Name) and e.id == name:
                            loops.append(_Elt(node.iter, i))
        return assigned, loops

    def _name(self, name, mod, fn, d, dv=False):
        if fn is not None:
            assigned, loops = self._locals(name, fn)
            if assigned or loops:
                a, _ = self._union(assigned, mod, fn, d, dv) if assigned else (set(), set())
                lv, lp = self._union(loops, mod, fn, d) if loops else (set(), set())
                pa = self._union(assigned, mod, fn, d, dv)[1] if assigned else set()
                return a | lv, pa | lp
            args = fn.args
            names = [a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]]
            if name in names:
                return set(), {(mod.name, self._qual(mod, fn), name)}
        if name in mod.consts:
            return self._union(mod.consts[name], mod, None, d, dv)
        if name in mod.imports:
            base, attr = mod.imports[name]
            if attr is not None and base in self.mods and attr in self.mods[base].consts:
                return self._union(self.mods[base].consts[attr], self.mods[base], None, d, dv)
            if attr is not None and base in self.mods and attr in self.mods[base].imports:
                return self._name(attr, self.mods[base], None, d, dv)
        raise ValueError(f"unbound name {name}")

    def _module_of(self, name, mod):
        if name in mod.imports:
            base, attr = mod.imports[name]
            full = f"{base}.{attr}" if attr else base
            if full in self.mods:
                return self.mods[full]
        return None

    def _attr(self, expr, mod, fn, d, dv=False):
        v = expr.value
        if isinstance(v, ast.Name):
            target = self._module_of(v.id, mod)
            if target is not None:
                if expr.attr in target.consts:
                    return self._union(target.consts[expr.attr], target, None, d, dv)
                return self._name(expr.attr, target, None, d, dv)
            if v.id in mod.classes and f"{v.id}.{expr.attr}" in mod.consts:
                return self._union(mod.consts[f"{v.id}.{expr.attr}"], mod, None, d, dv)
            if v.id in ("self", "cls"):
                hits = [k for k in mod.consts if k.endswith("." + expr.attr)]
                if hits:
                    return self._union([e for k in hits for e in mod.consts[k]], mod, None,
                                       d, dv)
            if v.id in mod.imports:
                base, attr = mod.imports[v.id]
                if base in self.mods and f"{attr}.{expr.attr}" in self.mods[base].consts:
                    src = self.mods[base]
                    return self._union(src.consts[f"{attr}.{expr.attr}"], src, None, d, dv)
        self._raise(expr)

    @staticmethod
    def _qual(mod, fn):
        for q, f in mod.funcs.items():
            if f is fn:
                return q
        return fn.name

    # -- call sites for a parameter ------------------------------------------------------
    def calls(self):
        if self._calls is None:
            self._calls = {}
            for m in self.mods.values():
                for fn, node in _walk_scoped(m.tree):
                    if isinstance(node, ast.Call):
                        for key in self._targets(node.func, m):
                            self._calls.setdefault(key, []).append((m, fn, node))
        return self._calls

    def _targets(self, f, m):
        if isinstance(f, ast.Name):
            if f.id in m.funcs:
                yield (m.name, f.id)
            if f.id in m.imports and m.imports[f.id][1]:
                yield m.imports[f.id]
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            target = self._module_of(f.value.id, m)
            if target is not None:
                yield (target.name, f.attr)
            elif f.value.id in ("self", "cls"):
                for q in m.funcs:
                    if q.endswith("." + f.attr):
                        yield (m.name, q)
            elif f.value.id in m.classes:
                yield (m.name, f"{f.value.id}.{f.attr}")

    def param(self, modname, qual, pname, d):
        mod = self.mods[modname]
        fn = mod.funcs.get(qual)
        if fn is None:
            raise ValueError(f"no function {qual}")
        args = fn.args
        pos = [a.arg for a in [*args.posonlyargs, *args.args]]
        is_method = "." in qual and pos[:1] in (["self"], ["cls"])
        idx = pos.index(pname) if pname in pos else None
        default = None
        if idx is not None:
            k = idx - (len(pos) - len(args.defaults))
            default = args.defaults[k] if k >= 0 else None
        else:
            kw = [a.arg for a in args.kwonlyargs]
            if pname in kw:
                default = args.kw_defaults[kw.index(pname)]
        vals, params, sites = set(), set(), 0
        for cm, cfn, call in self.calls().get((modname, qual), []):
            sites += 1
            arg = next((k.value for k in call.keywords if k.arg == pname), None)
            if arg is None and idx is not None:
                i = idx - (1 if is_method else 0)
                if 0 <= i < len(call.args) and not any(
                        isinstance(a, ast.Starred) for a in call.args[:i + 1]):
                    arg = call.args[i]
            if arg is None:
                if any(isinstance(a, ast.Starred) for a in call.args) or any(
                        k.arg is None for k in call.keywords):
                    raise ValueError(f"{qual} called with *args/**kwargs at "
                                     f"{cm.path.name}:{call.lineno}")
                if default is None:
                    continue
                v, p = self.value(default, mod, None, d)
            else:
                v, p = self.value(arg, cm, cfn, d)
            vals |= v
            params |= p
        if sites == 0:
            if default is None:
                raise ValueError(f"{qual}({pname}) has no call site and no default")
            return self.value(default, mod, None, d)
        return vals, params


def _walk_scoped(tree):
    """Yield (enclosing function or None, node) for every node."""
    stack = [(None, tree)]
    while stack:
        fn, node = stack.pop()
        for child in ast.iter_child_nodes(node):
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
            yield inner, child
            stack.append((inner, child))


def _is_action(expr) -> bool:
    return (isinstance(expr, ast.Attribute) and expr.attr == "action"
            and isinstance(expr.value, ast.Name) and expr.value.id == "AuditLog")


def _sites(mod: _Mod):
    for fn, node in _walk_scoped(mod.tree):
        if isinstance(node, ast.Compare) and _is_action(node.left):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.In)):
                    yield "exact", fn, comp, node.lineno
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and _is_action(node.func.value) and node.args:
            kind = {"in_": "exact", "like": "prefix", "startswith": "prefix",
                    "ilike": "prefix"}.get(node.func.attr)
            if kind:
                yield kind, fn, node.args[0], node.lineno


def scan(source_root=None) -> Scan:
    root = Path(source_root) if source_root else Path(__file__).resolve().parents[1]
    return _scan_cached(str(root.resolve()), _fingerprint(root))


def _fingerprint(root: Path) -> tuple:
    """Cheap change detector so a long-lived process re-scans only when source changed."""
    files = sorted(root.rglob("*.py"))
    return (len(files), max((f.stat().st_mtime_ns for f in files), default=0))


@lru_cache(maxsize=4)
def _scan_cached(root_s: str, _fp: tuple) -> Scan:
    root = Path(root_s)
    mods = _load(root)
    r = _Resolver(mods)
    exact: dict[str, set] = {}
    prefixes: dict[str, set] = {}
    unresolved: list[dict] = []
    for mod in mods.values():
        for kind, fn, expr, line in _sites(mod):
            site = f"{mod.path.relative_to(root)}:{line}"
            try:
                vals, params = r.value(expr, mod, fn)
                seen = set()
                while params:
                    key = params.pop()
                    if key in seen:
                        continue
                    seen.add(key)
                    v, p = r.param(*key, 0)
                    vals |= v
                    params |= p - seen
            except (ValueError, RecursionError) as exc:
                where = f"{mod.path.relative_to(root)}::{fn.name if fn else '<module>'}"
                unresolved.append({"site": site, "key": where, "why": str(exc)[:160]})
                continue
            bucket = exact if kind == "exact" else prefixes
            for v in vals:
                key = v.rstrip("%") if kind == "prefix" else v
                bucket.setdefault(key, set()).add(site)
    return Scan(exact={k: sorted(v) for k, v in sorted(exact.items())},
                prefixes={k: sorted(v) for k, v in sorted(prefixes.items())},
                unresolved=sorted(unresolved, key=lambda x: x["site"]))
