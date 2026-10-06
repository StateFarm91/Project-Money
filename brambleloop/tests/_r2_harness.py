"""Shared runner for the tests/test_r2_product_*.py regression scripts (J-product audit of
final-candidate-ddf9c6e). Prints `OK <name>` / `FAIL <name>` lines for scripts/run_tests.sh."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT / "src"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def run(namespace: dict) -> None:
    tests = [(n, f) for n, f in list(namespace.items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests collected"
    fails = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK {name}")
        except Exception as exc:  # noqa: BLE001
            fails += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    if fails:
        sys.exit(1)
