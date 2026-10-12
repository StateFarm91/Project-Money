"""W3-PRIV: private input cannot reach protected decisions, and protected code cannot reach it.

1. `firewall.reject_private` / `@guard` refuse anything tagged private, however nested.
2. Static: no protected module (finance, Product Truth, security, authorization, spend, legal)
   imports anything from `brambleloop.laura.private` except the stdlib-only firewall/values;
   across the whole source tree only `access.ALLOWED_IMPORTERS` import the private API or call
   `.reveal()`.
3. Runtime: importing every protected module (and the firewall) in a fresh interpreter loads
   none of the private store, key handling or tables.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_priv_firewall.py
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from w3_laura_memory_harness import check, finish, fresh_db, raises

from brambleloop.laura.private import _testkit as kit
from brambleloop.laura.private import firewall
from brambleloop.laura.private.firewall import PrivateInputRefused, guard, reject_private
from brambleloop.laura.private.values import PrivateRecord, PrivateValue

SRC = Path(__file__).resolve().parents[1] / "src"
PKG = SRC / "brambleloop"
PRIVATE_API = ("brambleloop.laura.private.store", "brambleloop.laura.private.access",
               "brambleloop.laura.private.crypto", "brambleloop.laura.private.models",
               "brambleloop.laura.private.errors", "brambleloop.laura.private._testkit")
NEUTRAL = ("brambleloop.laura.private.firewall", "brambleloop.laura.private.values")
# Protected decision paths (spec/07 Ruling 2): finance/accounting/spend, Product Truth
# (CIR compiler, gates, quality), security/authorization, legal/platform policy, authorities.
PROTECTED_DIRS = ("finance", "gates", "quality", "cir")
PROTECTED_FILES = ("app/security.py", "app/command_center/auth.py",
                   "app/command_center/approvals.py", "app/command_center/emergency.py",
                   "app/activation_authority_api.py", "app/publication_authority_api.py",
                   "app/phase_api.py", "app/ledger_mapping_api.py",
                   "ops/activation_authority.py", "ops/publication_authority.py",
                   "ops/funding.py", "ops/credential_register.py", "ops/provider_accounts.py",
                   "growth/ads_readiness.py")


def _modname(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    mod = _modname(path)
    pkg = mod if path.name == "__init__.py" else mod.rpartition(".")[0]
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".")
                base = base[:len(base) - (node.level - 1)]
                root = ".".join(base + ([node.module] if node.module else []))
            else:
                root = node.module or ""
            out.add(root)
            out.update(f"{root}.{a.name}" for a in node.names)
    # Dynamic imports by string literal.
    text = path.read_text(encoding="utf-8")
    if "laura.private" in text and "import_module" in text:
        out.add("brambleloop.laura.private.<dynamic>")
    return out


def _protected_files() -> list[Path]:
    files = [p for d in PROTECTED_DIRS for p in (PKG / d).rglob("*.py")]
    files += [PKG / f for f in PROTECTED_FILES if (PKG / f).exists()]
    return files


def _touches_private_api(imports: set[str]) -> list[str]:
    bad = []
    for name in imports:
        if not name.startswith("brambleloop.laura.private"):
            continue
        if any(name == n or name.startswith(n + ".") for n in NEUTRAL):
            continue
        if name == "brambleloop.laura.private":
            continue          # the package itself imports nothing; its members are checked
        bad.append(name)
    return bad


def test_firewall_refuses_tagged_private_input_however_nested():
    db = fresh_db()
    kit.set_key(kit.new_key())
    p = kit.private_principal(db)
    v = PrivateValue(kit.SENTINELS[0])
    rec = PrivateRecord(record_id="pf_x", kind="fact", value=v)

    class Holder:
        def __init__(self):
            self.payload = {"deep": [("x", v)]}
    cases = [v, rec, p, [1, v], {"amount": 5, "note": v}, {"k": {"j": [{"i": (v,)}]}},
             {"x": frozenset([rec])},
             {"__brambleloop_private__": True}, {"privacy": "owner_private", "x": 1},
             {"tier": "private"}, Holder()]
    for c in cases:
        e = raises(PrivateInputRefused, reject_private, c, context="finance")
        assert kit.SENTINELS[0] not in str(e)
    nested = [v]
    for _ in range(firewall.MAX_DEPTH + 5):
        nested = [nested]
    raises(PrivateInputRefused, reject_private, nested, context="spend")
    deep_clean = [0]
    for _ in range(firewall.MAX_DEPTH + 5):
        deep_clean = [deep_clean]
    raises(PrivateInputRefused, reject_private, deep_clean, context="spend")  # fails closed
    for clean in (None, 0, 1.5, "PRIV-like text is not a tag", {"amount": 5},
                  [{"tier": "brand"}], ("a", b"b")):
        assert reject_private(clean, context="security") is clean
    assert len(cases) >= 10 and "finance" in firewall.PROTECTED_CONTEXTS


def test_guard_decorator_blocks_private_arguments():
    calls = []

    @guard("authorization")
    def decide(amount, *, note=None):
        calls.append(amount)
        return "approved"
    assert decide(10, note="ordinary") == "approved"
    raises(PrivateInputRefused, decide, PrivateValue("x"))
    raises(PrivateInputRefused, decide, 10, note={"why": PrivateValue("x")})
    assert calls == [10]


def test_the_import_scanner_detects_private_imports():
    got = _imports(PKG / "laura" / "private" / "store.py")      # relative imports resolved
    assert "brambleloop.laura.private.crypto" in got
    assert _touches_private_api(got)
    assert not _touches_private_api({"brambleloop.laura.private.firewall",
                                     "brambleloop.laura.private.firewall.reject_private"})


def test_protected_modules_never_import_the_private_store():
    files = _protected_files()
    assert len(files) >= 40, len(files)
    offenders = {}
    for f in files:
        bad = _touches_private_api(_imports(f))
        if bad:
            offenders[str(f.relative_to(PKG))] = bad
    assert not offenders, offenders


def test_only_allowed_modules_import_the_private_api_or_reveal():
    from brambleloop.laura.private.access import ALLOWED_IMPORTERS
    files = [p for p in PKG.rglob("*.py")]
    assert len(files) > 200
    offenders, reveals = {}, []
    for f in files:
        mod = _modname(f)
        allowed = any(mod == a or mod.startswith(a + ".") for a in ALLOWED_IMPORTERS)
        if allowed:
            continue
        bad = _touches_private_api(_imports(f))
        if bad:
            offenders[mod] = bad
        if ".reveal(" in f.read_text(encoding="utf-8"):
            reveals.append(mod)
    assert not offenders, offenders
    assert not reveals, reveals


def test_runtime_imports_of_protected_modules_load_nothing_private():
    mods = sorted({_modname(f) for f in _protected_files()})
    assert len(mods) >= 40
    code = ("import importlib, json, sys\n"
            f"mods = {mods!r}\n"
            "ok = []\n"
            "for m in mods:\n"
            "    try:\n"
            "        importlib.import_module(m); ok.append(m)\n"
            "    except Exception:\n"
            "        pass\n"
            "import brambleloop.laura.private.firewall\n"
            "import brambleloop.laura.memory\n"
            "loaded = [m for m in sys.modules if m.startswith('brambleloop.laura.private')]\n"
            "print(json.dumps({'ok': len(ok), 'loaded': sorted(loaded)}))\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(SRC.parent), env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin"},
                         timeout=300)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["ok"] >= 30, res["ok"]
    leaked = [m for m in res["loaded"] if m in PRIVATE_API]
    assert not leaked, leaked
    assert "brambleloop.laura.private.firewall" in res["loaded"]


def test_business_memory_never_imports_the_private_store():
    files = list((PKG / "laura" / "memory").rglob("*.py"))
    assert files
    for f in files:
        assert not _touches_private_api(_imports(f)), f


_TESTS = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
assert _TESTS
for _name, _fn in _TESTS:
    check(_name, _fn)
finish()
