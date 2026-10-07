"""Vacuous-test detector (F-123): a test must not pass by looping over nothing.

THE DEFECT. `for row in rows: assert row.ok` passes when `rows` is empty, and an empty `rows` is
exactly what a broken producer returns. The suite has met this before: a certification loop
(C-5) passed for a whole session because the eligible set it iterated was empty, and the
suite-level guard in run_tests.sh ("SUITE REPORTED NO PASSES") only catches a whole file that
proves nothing, not one test inside a green file that does.

THE RULE, AS AN AST SCAN OF EVERY tests/test_*.py. A `for` loop whose body asserts (an `assert`
statement, or a call to `check(...)` / `assert_*` / `self.assert*`) is VACUOUS-RISK unless the
test establishes, somewhere in the same function, that the loop had something to iterate:

  * the iterable is a non-empty literal (list/tuple/set/dict/string), `range(<positive const>)`,
    or `enumerate`/`zip`/`sorted`/`reversed`/`.items()`/`.values()`/`.keys()` over one;
  * the iterable is a module constant bound to a non-empty literal;
  * an assertion anywhere in the function mentions the iterable's root name, or a name the
    loop body writes (a counter / a collected list that is asserted afterwards);
  * the loop has an `else:` or `break`-free body followed by an assert on the loop variable.

Deliberately syntactic and conservative. It proves the test *looked* at emptiness, not that it
looked correctly -- a named limit.

EMPTINESS UNDER TEST is legitimate (F-123 says so): a loop annotated on its `for` line with
`# vacuity-ok: <reason>` is exempt, and the reason is required.

THE BASELINE. When this detector was introduced (2026-09-28) it found the loops listed in
`BASELINE` below, in files owned by other build clusters that this change may not edit. They
are grandfathered as a RATCHET: each is keyed by (file, function, iterable source), a new
finding anywhere fails, and a baseline entry that no longer fires must be deleted (so the list
only shrinks). Fixing one means adding the non-emptiness assertion and removing its key.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
PRAGMA = "# vacuity-ok:"

_WRAPPERS = {"enumerate", "zip", "sorted", "reversed", "list", "tuple", "set", "iter"}
_VIEWS = {"items", "values", "keys"}


def _asserts(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Assert):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name == "check" or name.startswith("assert"):
                return True
    return False


def _nonempty_literal(node: ast.AST, consts: dict[str, ast.AST]) -> bool:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) > 0 and not any(isinstance(e, ast.Starred) for e in node.elts)
    if isinstance(node, ast.Dict):
        return len(node.keys) > 0
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return len(node.value) > 0
    if isinstance(node, ast.Name) and node.id in consts:
        return _nonempty_literal(consts[node.id], {})
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id == "range" and node.args:
            stop = node.args[-1] if len(node.args) == 1 else node.args[1]
            start = node.args[0] if len(node.args) > 1 else ast.Constant(0)
            if isinstance(stop, ast.Constant) and isinstance(start, ast.Constant):
                return isinstance(stop.value, int) and stop.value > start.value
            return False
        if isinstance(f, ast.Name) and f.id in _WRAPPERS and node.args:
            return all(_nonempty_literal(a, consts) for a in node.args)
        if isinstance(f, ast.Attribute) and f.attr in _VIEWS:
            return _nonempty_literal(f.value, consts)
    return False


def _code_constant(node: ast.AST) -> bool:
    """An UPPER_CASE table defined in code (`B.SIZES`, `GARMENTS[2:]`, `TILT_FOR.items()`).

    Exempt as a named limit: these are fixed data in the diff, not a producer's eligible set,
    and F-123 is about the latter. An empty code table is caught by that module's own tests.
    """
    while True:
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _VIEWS:
                node = f.value
                continue
            if isinstance(f, ast.Name) and f.id in _WRAPPERS and len(node.args) == 1:
                node = node.args[0]
                continue
            return False
        if isinstance(node, ast.Subscript):
            node = node.value
            continue
        name = node.attr if isinstance(node, ast.Attribute) else \
            node.id if isinstance(node, ast.Name) else ""
        return bool(name) and name.isupper() and len(name) > 1


def _root_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _iter_roots(node: ast.AST) -> set[str]:
    """The names an iterable is drawn from, with only the *view method* stripped (F-123).

    `d.items()` reads from `d`, so the attribute `items` of a call is not a root. A variable
    that is itself named `values`, `items` or `keys` is a root like any other: stripping the
    bare name made `assert values` before `for v in values:` invisible, so a loop that was
    guarded still read as vacuous (W4-FM2 regression case).
    """
    view_calls = {id(n.func) for n in ast.walk(node)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr in _VIEWS}
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node)
        if isinstance(n, ast.Attribute) and id(n) not in view_calls}


def _written_names(loop: ast.For) -> set[str]:
    out = set()
    for n in ast.walk(loop):
        if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                out |= {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name):
                    out.add(t.value.id)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                n.func.attr in {"append", "add", "extend", "update", "setdefault"} and \
                isinstance(n.func.value, ast.Name):
            out.add(n.func.value.id)
    return out - _loop_targets(loop)


def _loop_targets(loop: ast.For) -> set[str]:
    return {x.id for x in ast.walk(loop.target) if isinstance(x, ast.Name)}


def _assert_mentions(scope: ast.AST, names: set[str], exclude: ast.For) -> bool:
    """Does any assertion in `scope`, outside `exclude`'s body, mention one of `names`?"""
    inside = {id(n) for n in ast.walk(exclude)}
    for n in ast.walk(scope):
        if id(n) in inside:
            continue
        test = None
        if isinstance(n, ast.Assert):
            test = n.test
        elif isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name == "check" or name.startswith("assert"):
                test = ast.Tuple(elts=list(n.args), ctx=ast.Load())
        if test is not None and _root_names(test) & names:
            return True
    return False


def findings_in(path: Path) -> list[tuple[str, int, str, str]]:
    """[(function, line, iterable source, file)] for every vacuous-risk loop in one file."""
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines()
    consts = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
              for t in node.targets if isinstance(t, ast.Name)}
    out = []

    def visit(scope: ast.AST, fname: str) -> None:
        for node in ast.iter_child_nodes(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(node, node.name)
                continue
            if isinstance(node, ast.ClassDef):
                visit(node, fname)
                continue
            for loop in [n for n in ast.walk(node) if isinstance(n, (ast.For, ast.AsyncFor))]:
                if not _asserts(ast.Module(body=loop.body, type_ignores=[])):
                    continue
                line = lines[loop.lineno - 1]
                if PRAGMA in line and line.split(PRAGMA, 1)[1].strip():
                    continue
                if _nonempty_literal(loop.iter, consts):
                    continue
                if _code_constant(loop.iter):
                    continue
                roots = _iter_roots(loop.iter) - _WRAPPERS - {"range", "len"}
                if _assert_mentions(scope, roots | _written_names(loop), loop):
                    continue
                out.append((fname, loop.lineno, ast.unparse(loop.iter), path.name))
            # nested defs inside compound statements
            for inner in ast.walk(node):
                if inner is not node and isinstance(inner, (ast.FunctionDef,
                                                            ast.AsyncFunctionDef)):
                    visit(inner, inner.name)

    visit(tree, "<module>")
    # Helpers (`_scrubbed_env`, fixtures) are not tests: a loop there is only vacuous through
    # the test that calls it, which is where the finding belongs.
    out = [f for f in out if f[0] == "<module>" or f[0].startswith("test")]
    # a loop can be reached from both the module walk and a nested-def walk; keep one
    return sorted(set(out), key=lambda f: (f[3], f[1]))


def all_findings() -> list[tuple[str, int, str, str]]:
    out = []
    for p in sorted(TESTS.glob("test_*.py")):
        out += findings_in(p)
    return out


def key(f: tuple[str, int, str, str]) -> tuple[str, str, str]:
    return (f[3], f[0], f[2])


BASELINE: set[tuple[str, str, str]] = {
    ('test_cert_claude_independence.py', 'test_production_start_command_runs_kills_and_resumes_without_this_session', 'before.items()'),
    ('test_cert_claude_independence.py', 'test_production_start_command_runs_kills_and_resumes_without_this_session', 'cadence_keys_a'),
    ('test_launch.py', 'test_nothing_blocked_on_build_is_ever_sent_to_the_owner', 'readiness.buildable'),
    ('test_launch.py', 'test_the_owner_queue_carries_everything_the_directive_asks_for', "assess(db, phase='shadow').owner_requests()"),
    ('test_product_run.py', 'test_the_detected_repeat_is_the_real_one_not_a_convenient_one', 'enumerate(grid)'),
    ('test_product_run.py', 'test_the_detected_repeat_is_the_real_one_not_a_convenient_one', 'enumerate(row)'),
}


# --- the gate --------------------------------------------------------------------------------------
def test_no_new_vacuous_risk_loop_anywhere_in_the_suite():
    found = all_findings()
    new = [f for f in found if key(f) not in BASELINE]
    assert not new, "loops that assert over a possibly empty iterable (add a non-emptiness " \
        "assertion, or `# vacuity-ok: <reason>` if emptiness is the behaviour):\n  " + \
        "\n  ".join(f"{f[3]}:{f[1]} in {f[0]}: for ... in {f[2]}" for f in new)


def test_the_baseline_only_shrinks():
    live = {key(f) for f in all_findings()}
    dead = sorted(BASELINE - live)
    assert not dead, f"baseline entries that no longer fire -- delete them: {dead}"


def test_the_scan_sees_the_suite():
    files = list(TESTS.glob("test_*.py"))
    assert len(files) > 100, len(files)


# --- the detector detects (fixtures are parsed, never executed) --------------------------------------
def _scan(src: str) -> list:
    tmp = Path(__import__("tempfile").mkdtemp()) / "test_fixture.py"
    tmp.write_text(src)
    return findings_in(tmp)


def test_a_loop_asserting_over_an_unchecked_iterable_is_flagged():
    got = _scan("def test_x():\n    rows = load()\n    for r in rows:\n        assert r.ok\n")
    assert [(f[0], f[2]) for f in got] == [("test_x", "rows")], got
    got = _scan("def test_y():\n    for r in db.query():\n        check('ok', r.ok)\n")
    assert len(got) == 1, got


def test_a_non_emptiness_assertion_or_a_literal_clears_the_loop():
    clean = [
        "def test_a():\n    rows = load()\n    assert rows\n    for r in rows:\n        assert r\n",
        "def test_b():\n    rows = load()\n    assert len(rows) == 3\n    for r in rows:\n"
        "        assert r\n",
        "def test_c():\n    for r in (1, 2):\n        assert r\n",
        "def test_d():\n    for i in range(5):\n        assert i >= 0\n",
        "CASES = ['a', 'b']\ndef test_e():\n    for c in CASES:\n        assert c\n",
        "def test_f():\n    n = 0\n    for r in load():\n        assert r\n        n += 1\n"
        "    assert n > 0\n",
        "def test_g():\n    for k, v in {'a': 1}.items():\n        assert v\n",
        "def test_h():\n    for r in load():  # vacuity-ok: empty is the refusal under test\n"
        "        assert r\n",
    ]
    assert clean
    for src in clean:
        assert _scan(src) == [], src


def test_a_variable_named_like_a_view_is_still_a_root():
    """F-123 open note: `values`/`items`/`keys` as variable names were stripped as views."""
    for name in ("values", "items", "keys"):
        guarded = (f"def test_v():\n    {name} = load()\n    assert {name}\n"
                   f"    for v in {name}:\n        assert v\n")
        assert _scan(guarded) == [], name
        unguarded = f"def test_w():\n    {name} = load()\n    for v in {name}:\n        assert v\n"
        assert [(f[0], f[2]) for f in _scan(unguarded)] == [("test_w", name)], name
    # the view method itself is still not a root: `d.items()` is guarded by `assert d`
    assert _scan("def test_d():\n    d = load()\n    assert d\n    for k, v in d.items():\n"
                 "        assert v\n") == []
    assert len(_scan("def test_e():\n    d = load()\n    for k, v in d.items():\n"
                     "        assert v\n")) == 1


def test_a_pragma_without_a_reason_does_not_exempt():
    got = _scan("def test_x():\n    for r in load():  # vacuity-ok:\n        assert r\n")
    assert len(got) == 1, "a bare pragma exempted a loop without saying why"


def test_a_constant_table_is_exempt_but_a_computed_view_of_it_is_not():
    assert _scan("def test_a():\n    for s in B.SIZES:\n        assert s\n") == []
    assert len(_scan("def test_b():\n    for s in B.eligible(B.SIZES):\n        assert s\n")) == 1


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e)[:3000])
    sys.exit(1 if fails else 0)
