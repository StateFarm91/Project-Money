"""V5 / audit P1-c: the product's scale against the CIR's finished size, from known anchors.

The judge is a stub that returns boxes, so there is no network and no spend. The arithmetic
is the real module's. market-basket-small's twin says 16.0 cm across the points. A frame
whose boxes put the basket beside a 9.5 cm mug at about that size passes; a basket drawn at
twice its size fails `product_scale`. Every unreadable case is UNKNOWN.

Run: cd brambleloop && PYTHONPATH=src $PY tests/test_v5_scale.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from brambleloop.products import launch0  # noqa: E402
from brambleloop.visual import scale as SC  # noqa: E402

CIR = launch0.cir_for("basket_small")
W, H = 2000, 1500


def _frame():
    buf = io.BytesIO()
    Image.new("RGB", (W, H), (200, 190, 170)).save(buf, "PNG")
    return buf.getvalue()


class _Judge:
    name = "stub-judge"

    def __init__(self, answer):
        self.answer = answer

    def read(self, prompt, images, *, system, max_tokens):
        assert "Do not estimate any size" in prompt and len(images) == 1
        return {"answered": self.answer is not None, "reading": self.answer, "why": "none"}


def _boxes(product_cm, anchor="coffee mug"):
    """Boxes as a judge would point at them, drawn so the product is `product_cm` long."""
    px_per_cm = 30.0
    a = SC.ANCHORS[anchor] * px_per_cm / H          # anchor stands upright: its height
    p = product_cm * px_per_cm / W                  # product is wider than tall
    return {"anchor": anchor, "anchor_box": [0.10, 0.30, 0.10 + 0.05, 0.30 + a],
            "product_box": [0.30, 0.55, 0.30 + p, 0.55 + 0.10]}


def test_the_expected_size_is_the_twins_longest_finished_dimension():
    assert round(SC.expected_cm(CIR), 1) == 16.0


def test_a_basket_at_its_own_size_beside_a_mug_passes():
    v = SC.verify(_Judge(_boxes(16.0)), _frame(), CIR)
    assert v["status"] == "PASS" and abs(v["implied_cm"] - 16.0) < 0.5, v
    v = SC.verify(_Judge(_boxes(19.0, "dinner plate")), _frame(), CIR)
    assert v["status"] == "PASS", v            # +19 %: perspective allowance


def test_a_basket_drawn_twice_its_size_fails():
    v = SC.verify(_Judge(_boxes(32.0)), _frame(), CIR)
    assert v["status"] == "FAIL" and v["code"] == "product_scale", v
    assert v["implied_cm"] > 30 and "+100%" in v["why"], v
    v = SC.verify(_Judge(_boxes(7.0)), _frame(), CIR)
    assert v["status"] == "FAIL", v            # half size fails too


def test_every_unreadable_case_is_unknown_never_pass():
    good = _boxes(16.0)
    cases = [
        SC.verify(None, _frame(), CIR),                                    # no judge
        SC.verify(_Judge(None), _frame(), CIR),                            # no answer
        SC.verify(_Judge({**good, "anchor": "none"}), _frame(), CIR),      # no anchor
        SC.verify(_Judge({**good, "anchor": "a giant teddy bear"}), _frame(), CIR),
        SC.verify(_Judge({**good, "anchor_box": [0.5, 0.5, 0.4, 0.6]}), _frame(), CIR),
        SC.verify(_Judge({**good, "product_box": [0.3, 0.3, 0.3001, 0.5]}), _frame(), CIR),
        SC.verify(_Judge({**good, "product_box": "big"}), _frame(), CIR),
        SC.verify(_Judge({**good, "product_box": [0.2, 0.2, 1.6, 0.9]}), _frame(), CIR),
        SC.verify(_Judge(good), b"not an image", CIR),
    ]
    for v in cases:
        assert v["status"] == "UNKNOWN", v


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception:  # noqa: BLE001
                import traceback

                failed += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
