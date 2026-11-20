"""OPUS2: a stuffed, closed piece is never told to damp-finish standing up or to check the
ball band "before blocking" (a9fac088, OPUS2P-8).

The amigurumi suite pinned this; the stuffed finishing ships on its own branch (queue Q16), so
it is pinned here on the catalogue's own stuffed pieces, which branch on the assembly's
`stuff_before_closing`, never on a title.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_stuffed_finishing.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.writer import finishing_lines  # noqa: E402
from brambleloop.products import inventory  # noqa: E402


def test_stuffed_catalogue_pieces_are_not_blocked_and_others_still_are():
    stuffed = ("heart-row-ring-pillow", "spring-garden-kneeler")
    checked = 0
    for slug in stuffed:
        cir = inventory._engineered(slug)
        assert cir is not None, slug
        assert any(s.stuff_before_closing for s in cir.assembly), slug
        text = " ".join(finishing_lines(cir))
        assert "stuffed and closed, so it is not blocked" in text, (slug, text)
        assert "standing up" not in text and "before blocking" not in text, (slug, text)
        checked += 1
    assert checked == len(stuffed)
    # A piece with nothing stuffed keeps its blocking advice and the ball-band line.
    plain = [s for s in inventory.universe()
             if (c := inventory._engineered(s)) is not None
             and not any(getattr(x, "stuff_before_closing", False) for x in (c.assembly or []))]
    assert plain
    for slug in plain:
        text = " ".join(finishing_lines(inventory._engineered(slug)))
        assert "stuffed and closed" not in text, slug
        assert "Check the ball band before blocking" in text, slug


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
