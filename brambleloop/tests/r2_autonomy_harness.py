"""Shared setup for the R2 autonomy regression tests (audit ddf9c6e lane J findings)."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def boot(prefix: str = "r2auto-"):
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp(prefix=prefix)
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def run_tests(namespace: dict) -> None:
    fails = 0
    tests = [(n, f) for n, f in list(namespace.items()) if n.startswith("test_")]
    assert tests, "no tests collected"
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails += 1
            print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
