"""Run pytest-style test files as plain scripts when pytest is not installed (W6 N9).

The repository's runner (run_tests.sh) executes every tests/test_*.py as a script, and pytest
is not a dependency. A file written in pytest style therefore ran nothing -- or crashed on
import -- and read as a failed suite. A test file falls back to this module only when the real
pytest is absent (`try: import pytest / except ImportError: import _minipytest as pytest`), and
runs itself with `_minipytest.run_module(globals())`.

Supported, and nothing more: `raises` (context manager, with `match`), `mark.parametrize`
(stacked, multi-name), `fixture` (decorator no-op), and the `monkeypatch` and `tmp_path`
fixtures. A test that asks for any other fixture FAILS -- it is never skipped -- because a
test that silently does not run must never read as passed.
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import shutil
import sys
import tempfile
import traceback
from pathlib import Path


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match, self.value = exc, match, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match is not None and not re.search(self.match, str(ev)):
            raise AssertionError(f"pattern {self.match!r} not found in {str(ev)!r}")
        self.value = ev
        return True


def raises(exc, *args, match=None, **kwargs):
    if args:
        fn = args[0]
        try:
            fn(*args[1:], **kwargs)
        except exc:
            return None
        raise AssertionError(f"DID NOT RAISE {exc}")
    return _Raises(exc, match)


class _Mark:
    def parametrize(self, names, values, **_kw):
        def deco(fn):
            fn.__dict__.setdefault("_minipytest_params", []).append((names, list(values)))
            return fn
        return deco


mark = _Mark()


def fixture(*args, **_kw):
    if args and callable(args[0]):
        return args[0]
    return lambda fn: fn


_NOTSET = object()


class MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name=_NOTSET, value=_NOTSET, raising=True):
        if isinstance(target, str) and value is _NOTSET:
            value = name
            mod, attr = target.rsplit(".", 1)
            target, name = importlib.import_module(mod), attr
        old = getattr(target, name, _NOTSET)
        if old is _NOTSET and raising:
            raise AttributeError(f"{target!r} has no attribute {name!r}")
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def setenv(self, key, value):
        self._undo.append((os.environ, key, os.environ.get(key, _NOTSET)))
        os.environ[key] = str(value)

    def delenv(self, key, raising=True):
        if key not in os.environ:
            if raising:
                raise KeyError(key)
            return
        self._undo.append((os.environ, key, os.environ[key]))
        del os.environ[key]

    def undo(self):
        for target, name, old in reversed(self._undo):
            if target is os.environ:
                if old is _NOTSET:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = old
            elif old is _NOTSET:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
            else:
                setattr(target, name, old)
        self._undo = []


def _cases(fn):
    cases = [{}]
    for names, values in reversed(getattr(fn, "_minipytest_params", [])):
        keys = [n.strip() for n in names.split(",")] if isinstance(names, str) else list(names)
        cases = [{**c, **dict(zip(keys, v if len(keys) > 1 else (v,)))}
                 for c in cases for v in values]
    return cases


def run_module(namespace: dict) -> None:
    """Run every test_* function in `namespace`; print OK/FAIL lines; exit 1 on any failure."""
    passed = failed = 0
    for name, fn in list(namespace.items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        cases = _cases(fn)
        for i, case in enumerate(cases):
            label = f"{name}[{i}]" if len(cases) > 1 else name
            params = inspect.signature(fn).parameters
            kwargs, mp, tmp = dict(case), MonkeyPatch(), None
            if "monkeypatch" in params:
                kwargs["monkeypatch"] = mp
            if "tmp_path" in params:
                tmp = tempfile.mkdtemp(prefix="minipytest-")
                kwargs["tmp_path"] = Path(tmp)
            missing = [p for p in params if p not in kwargs]
            try:
                if missing:
                    raise AssertionError(f"unsupported fixtures {missing}: this test cannot run "
                                         "without pytest, so it fails rather than skips")
                fn(**kwargs)
                passed += 1
                print(f"OK   {label}")
            except Exception:  # noqa: BLE001 - every failure is reported and counted
                failed += 1
                print(f"FAIL {label}")
                traceback.print_exc()
            finally:
                mp.undo()
                if tmp:
                    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{passed} passed, {failed} failed")
    if passed == 0:
        print("FAIL no test ran")
        failed += 1
    sys.exit(1 if failed else 0)


# Function-level `import pytest` (some files import inside a test) resolves here too -- but only
# when the real pytest is absent, so an environment that has pytest always uses it.
try:
    import pytest as _real_pytest  # noqa: F401
except ImportError:
    sys.modules.setdefault("pytest", sys.modules[__name__])
