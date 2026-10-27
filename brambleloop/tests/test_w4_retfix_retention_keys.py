"""W4-RETFIX: no retention key may be classified twice.

`ops/retention.py` classified `cir.drafted` twice (`windowed`, then `lifetime_total`). In a
dict literal the later entry silently wins, so the file read one way and ran another; had the
order been reversed, a lifetime read would have lost its protection. This scans every dict
literal in the module's source (AST, not the evaluated dict, which has already dropped the
duplicate) and also reports what production b2e49455 carried, when that commit is present.

Run: cd brambleloop && python3 tests/test_w4_retfix_retention_keys.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brambleloop" / "ops" / "retention.py"
PRODUCTION = "b2e49455"


class Skip(Exception):
    """Evidence not available here: reported as SKIP (UNKNOWN), never as a pass."""


def duplicates(source: str) -> list[tuple[str, int, int, str]]:
    """(key, first line, repeat line, class that wins) for every repeated dict-literal key."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict = {}
        for k, v in zip(node.keys, node.values):
            if not isinstance(k, ast.Constant) or not isinstance(k.value, str):
                continue
            if k.value in seen:
                cls = (v.elts[0].value if isinstance(v, ast.Tuple) and v.elts
                       and isinstance(v.elts[0], ast.Constant) else None)
                out.append((k.value, seen[k.value], k.lineno, cls))
            seen[k.value] = k.lineno
    return out


def test_no_retention_key_is_defined_twice():
    dups = duplicates(SRC.read_text())
    assert dups == [], f"retention keys defined twice (the later one silently wins): {dups}"


def test_the_scan_catches_a_duplicate():
    assert duplicates('X = {"a": ("windowed", ""), "a": ("lifetime_total", "")}') == [
        ("a", 1, 1, "lifetime_total")]


def test_cir_drafted_is_lifetime_total():
    sys.path.insert(0, str(ROOT / "src"))
    from brambleloop.ops import retention

    assert retention.KNOWN_READ_ACTIONS["cir.drafted"][0] == "lifetime_total"


def test_production_carried_the_duplicate_and_lifetime_total_won_there():
    got = subprocess.run(["git", "-C", str(ROOT), "show",
                          f"{PRODUCTION}:brambleloop/src/brambleloop/ops/retention.py"],
                         capture_output=True, text=True)
    if got.returncode != 0:
        raise Skip(f"production {PRODUCTION} is not in this clone (UNKNOWN, not a pass)")
    dups = duplicates(got.stdout)
    assert [(k, cls) for k, _a, _b, cls in dups] == [("cir.drafted", "lifetime_total")], dups


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Skip as e:
                print("SKIP", name, e)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
