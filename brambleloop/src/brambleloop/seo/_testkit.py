"""Test support for tests/test_v11_seo_*.py (lane G). Hermetic: temp SQLite, no network.

Lives in the package so the lane's tests share it without a non-suite file under tests/.
Not imported by any runtime path.
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # brambleloop/
sys.path.insert(0, str(ROOT / "tests"))
_ART = tempfile.TemporaryDirectory()
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", _ART.name)
_TMP_DIR = tempfile.TemporaryDirectory(prefix="v11seo_")  # removed at interpreter exit
_TMP = _TMP_DIR.name
_N = [0]


def fresh_db(create: bool = True):
    from brambleloop.core.db import Database

    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/db{_N[0]}.sqlite", scratch=True)
    if create:
        db.create_all()
    return db


_FACTS = []


def launch0_facts():
    from brambleloop.seo import facts

    if not _FACTS:
        _FACTS.extend(facts.launch0_facts())
    return list(_FACTS)


def run(namespace: dict) -> None:
    fails = passes = 0
    for name, fn in sorted(namespace.items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passes += 1
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                traceback.print_exc()
                print("FAIL", name, repr(e))
    print(f"\n  {passes} passing, {fails} failing")
    sys.exit(1 if fails else 0)
