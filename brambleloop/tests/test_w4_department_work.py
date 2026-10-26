"""W4-AGENTS2 batch 2: department duties that were silent no-ops.

Visual Production: the daily owned-photography cadence fell back to the first product row even
when that product has no CIR, so production repeated the same "no CIR" no-op on
`market-basket-trio` ten times. With no product-first product to photograph it now says so.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_department_work.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Phase, Product  # noqa: E402
from brambleloop.products.builder import for_slug  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4dw_")


def test_owned_photography_never_falls_back_to_a_product_with_no_cir():
    from brambleloop.runtime.release import _representative_slug

    db = Database(f"sqlite:///{_TMP}/v.db")
    db.create_all()
    Registry(db).seed_defaults()
    assert for_slug("market-basket-trio") is None
    with db.session() as s:
        s.add(Product(slug="market-basket-trio", title="Market basket trio",
                      status="certified"))
    assert _representative_slug(db) == ""
    job = JobQueue(db).enqueue("publishing", "assets.owned_photography", {})
    with patch("brambleloop.gateway.images.usable", return_value=True):
        out = handlers.get("assets.owned_photography")(JobContext(
            job=job, db=db, queue=JobQueue(db), registry=Registry(db), phase=Phase.SHADOW))
    assert out["ran"] is False and "no certified product" in out["reason"], out


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
