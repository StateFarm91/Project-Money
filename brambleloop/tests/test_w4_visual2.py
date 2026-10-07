"""W4-VISUAL2: the remaining gallery work after W4-VISUAL.

* wiring #7 -- `commerce.search_evidence` counts the sizes and colours a listing sells from
  its certified CIR (and Launch-0 sibling variants), never a hard-coded 1, so SIZING and
  COLOUR_CONTEXT applicability is measured rather than assumed; no CIR is UNMEASURED.
Local, deterministic, no network, no spend.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visual2_")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.setdefault("BRAMBLELOOP_ARTIFACT_DIR", os.path.join(_TMP, "artifacts"))

from brambleloop.commerce import search_evidence as SE  # noqa: E402
from brambleloop.products import launch0  # noqa: E402


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/se.sqlite")
    db.create_all()
    return db


def _certify(db, slug, version, jobs):
    from brambleloop.core.models import ListingSetCertificateRecord

    with db.session() as s:
        s.add(ListingSetCertificateRecord(product_slug=slug, version=version, state="valid",
                                          certificate={"frames": [{"job": j} for j in jobs]}))


def test_sizes_and_colours_come_from_the_certified_cir():
    basket = launch0.candidate("nursery-nesting-baskets")
    small = launch0.cir_for(basket.variants[0].build)
    assert len(basket.variants) == 3
    cat, sizes, colours = SE._category_for(small.slug)
    assert sizes == 3, sizes                       # S/M/L sold on the primary's listing
    assert colours == len(small.colors) and colours > 1, colours
    med = launch0.cir_for("basket_medium")
    _cat, msizes, mcolours = SE._category_for(med.slug)
    assert msizes == 1 and mcolours == len(med.colors)     # a sibling sells its one size
    assert SE._category_for("no-such-product-anywhere")[1:] == (None, None)


def test_gallery_applicability_is_measured_not_assumed():
    db = _db()
    basket = launch0.candidate("nursery-nesting-baskets")
    small = launch0.cir_for(basket.variants[0].build)
    base = ["DESIRE", "SCALE", "DETAIL", "ANGLE", "CONSTRUCTION", "MATERIALS"]
    _certify(db, small.slug, small.version, base)
    g = SE.gallery(db, small.slug, small.version)
    assert g["sizes"] == 3 and g["colours"] == len(small.colors)
    # with sizes/colours hard-coded to 1 these two jobs were silently not applicable
    assert "SIZING" in g["applicable"] and "COLOUR_CONTEXT" in g["applicable"], g
    assert {"SIZING", "COLOUR_CONTEXT"} <= set(g["missing"]) and g["status"] == SE.FAIL
    _certify(db, "no-such-product-anywhere", "1.0.0", base)
    u = SE.gallery(db, "no-such-product-anywhere", "1.0.0")
    assert u["status"] == SE.UNMEASURED, u


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    assert tests
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
