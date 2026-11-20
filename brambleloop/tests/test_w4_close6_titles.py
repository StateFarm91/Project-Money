"""W4-CLOSE6: every board and matrix row carries its registry title (the F-515 question).

The coordinator was told that the board titled F-515@v0.16 "Shop Completeness Gate" while the
registry row of that id read "Search Visibility Ingestion". That was a lookup error in my own
report, not in the board. A `grep -A6` matched the row's trailing `"uid"` line and printed the
NEXT row's text (F-516@v0.16).

In the registry, F-515@v0.16 IS "Shop Completeness Gate" and F-515@v0.15 is "Launch Non-Delay
Rule". The mapping rows of both describe those requirements. This test pins it for every row:
the completion board and the closure matrix carry exactly the registry's title for the id they
name, and every board id exists in the registry.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_titles.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "research" / "final_build"


def _registry() -> dict:
    reg = {}
    for r in json.loads((FB / "master_registry.json").read_text())["requirements"]:
        reg[r.get("uid") or r["id"]] = r
    for r in json.loads((FB / "master_registry_v1_1.json").read_text())["requirements"]:
        reg.setdefault(r.get("uid") or r["id"], r)
    return reg


def test_every_board_row_carries_its_registry_title():
    reg = _registry()
    rows = json.loads((FB / "w4" / "COMPLETION_BOARD_FINAL.json").read_text())["rows"]
    fm = rows["final_master"]
    assert len(fm) == len(reg) == 917, (len(fm), len(reg))
    missing = [x["id"] for x in fm if x["id"] not in reg]
    wrong = [(x["id"], x["title"], reg[x["id"]]["title"]) for x in fm
             if x["id"] in reg and x["title"] != reg[x["id"]]["title"][:90]]
    assert not missing and not wrong, (missing[:5], wrong[:5])


def test_every_matrix_row_carries_its_registry_title():
    reg = _registry()
    matrix = json.loads((FB / "closure_matrix.json").read_text())["matrix"]
    assert len(matrix) == 917
    wrong = [(r["uid"], r.get("title"), (reg.get(r["uid"]) or {}).get("title"))
             for r in matrix if (reg.get(r["uid"]) or {}).get("title") != r.get("title")]
    assert not wrong, wrong[:5]


def test_the_two_f515_rows_are_the_requirements_their_mapping_describes():
    reg = _registry()
    assert reg["F-515@v0.16"]["title"] == "Shop Completeness Gate"
    assert reg["F-515@v0.15"]["title"] == "Launch Non-Delay Rule"
    assert reg["F-516@v0.16"]["title"] == "Search Visibility Ingestion"
    s6 = {r["uid"]: r for r in json.loads((FB / "mapping" / "s6.json").read_text())}
    assert "shop" in (s6["F-515@v0.16"]["missing_part"] or s6["F-515@v0.16"]["producer"]
                      or "").lower()
    assert "launch" in (s6["F-515@v0.15"]["missing_part"] or "").lower()


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 3, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
