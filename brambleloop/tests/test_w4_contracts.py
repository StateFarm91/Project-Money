"""W4-AGENTS W1: Shared Truth Contracts (F-456) and the Contract Change Barrier (F-482).

Every shared contract is versioned and pinned; a shape change without a version bump, or a
version bump without a declared CHANGELOG entry, fails; a consumer pinned to an old version
fails at import; every declared contract has at least one consumer pin.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_contracts.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import ast
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core import contracts as C  # noqa: E402

SRC = ROOT / "src" / "brambleloop"


def test_the_contracts_hold_at_head():
    assert set(C.CONTRACTS) == {"cir", "etsy_write_schemas", "shop_policy_sections",
                                "storefront_proposal", "live_shop_evidence"}
    assert C.check() == [], C.check()
    pinned = C.pins()
    assert set(pinned) == set(C.CONTRACTS)
    for name, (version, _fn, what) in C.CONTRACTS.items():
        assert pinned[name]["version"] == version and what
        assert len(pinned[name]["fingerprint"]) == 64


def test_fingerprints_are_deterministic():
    for name in C.CONTRACTS:
        assert C.fingerprint(name) == C.fingerprint(name)


def test_a_shape_change_without_a_version_bump_is_silent_drift():
    v, fn, what = C.CONTRACTS["cir"]
    moved = dict(C.CONTRACTS, cir=(v, lambda: {**fn(), "NewThing": [("x", "int")]}, what))
    with patch.object(C, "CONTRACTS", moved):
        problems = C.check()
    assert any("cir" in p and "silent drift" in p for p in problems), problems


def test_a_version_bump_must_be_declared_and_regenerated():
    v, fn, what = C.CONTRACTS["etsy_write_schemas"]
    bumped = dict(C.CONTRACTS, etsy_write_schemas=(v + 1, fn, what))
    with patch.object(C, "CONTRACTS", bumped):
        problems = C.check()
    assert any("no CHANGELOG entry" in p for p in problems), problems
    assert any("not regenerated" in p for p in problems), problems
    log = {**C.CHANGELOG, "etsy_write_schemas": {**C.CHANGELOG["etsy_write_schemas"],
                                                 v + 1: "test: declared"}}
    with patch.object(C, "CONTRACTS", bumped), patch.object(C, "CHANGELOG", log):
        problems = C.check()
    assert not any("CHANGELOG" in p for p in problems)
    assert any("not regenerated" in p for p in problems), problems


def test_a_removed_or_unpinned_contract_is_reported():
    # the shape functions import the producing modules, which pin their own contracts; load
    # them before removing one, so this test checks `check()` rather than the import pin
    C.current()
    gone = {k: v for k, v in C.CONTRACTS.items() if k != "live_shop_evidence"}
    with patch.object(C, "CONTRACTS", gone):
        assert any("no longer declared" in p for p in C.check())
    with patch.object(C, "pins", lambda: {}):
        assert len([p for p in C.check() if "not pinned" in p]) == len(C.CONTRACTS)


def test_require_passes_the_current_version_and_refuses_a_stale_pin():
    for name, (version, _fn, _w) in C.CONTRACTS.items():
        C.require(name, version)
    for bad in (("cir", 0), ("cir", 2), ("no_such_contract", 1)):
        try:
            C.require(*bad)
            raise AssertionError(f"require{bad} passed")
        except C.ContractDrift as exc:
            assert "migrate" in str(exc)


def _pins_in_source() -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = str(p.relative_to(SRC))
        if rel == "core/contracts.py":
            continue
        tree = ast.parse(p.read_text())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "require"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "_contracts"):
                name, ver = (a.value for a in node.args)
                out.setdefault(name, []).append((rel, ver))
    return out


def test_every_contract_has_a_consumer_pin_at_the_current_version():
    found = _pins_in_source()
    assert found, "no consumer pins at all"
    for name, (version, _fn, _w) in C.CONTRACTS.items():
        assert found.get(name), f"{name}: no consumer pins it"
        for rel, ver in found[name]:
            assert ver == version, (name, rel, ver, version)
    assert set(found) <= set(C.CONTRACTS), set(found) - set(C.CONTRACTS)


def test_the_pinned_consumers_import_cleanly():
    import importlib

    for rels in _pins_in_source().values():
        for rel, _v in rels:
            importlib.import_module("brambleloop." + rel[:-3].replace("/", "."))


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    print(f"{fails} failed")
    sys.exit(1 if fails else 0)
