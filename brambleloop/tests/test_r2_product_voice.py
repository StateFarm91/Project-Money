"""R2 / J-product P-7: no typewriter " -- " in the shop's own copy or in drafted Launch-0
listing descriptions (VOICE_DOUBLE_HYPHEN), fixed at the source: commerce.shop_package's
policy/FAQ/sale-message text, commerce.seo's description template and the children's safety
block it typesets. Drafted through the real listing chain (tests/test_launch0_listing_truth).

Run: cd brambleloop && PYTHONPATH=src python tests/test_r2_product_voice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from _r2_harness import run

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brambleloop.store_foundation import content as C, lint, readiness as R  # noqa: E402

_DRAFTED: dict = {}


def _voice_hyphens(text):
    return [f for f in lint.lint(text) if f["code"] == "VOICE_DOUBLE_HYPHEN"]


def _drafted() -> dict:
    if not _DRAFTED:
        import test_launch0_listing_truth as T
        from brambleloop.products import launch0 as L

        db = T._chain()
        for build in T.BUILDS:
            cir = L.cir_for(build)
            row = T._listing(db, cir.slug)
            _DRAFTED[cir.slug] = (row.title or "") + "\n" + (row.description or "")
    return _DRAFTED


def test_shop_copy_has_no_double_hyphen():
    s = C.build(None)
    facing = [x for x in s.values() if x.customer_facing]
    assert facing
    for surface in facing:
        assert not _voice_hyphens(surface.text()), (surface.key, _voice_hyphens(surface.text()))
    voice = next(r for r in R.evaluate(s) if r["key"] == "voice")
    assert not [f for f in voice["findings"] if f["code"] == "VOICE_DOUBLE_HYPHEN"], voice


def test_every_drafted_launch0_description_passes_the_voice_rule():
    drafted = _drafted()
    assert len(drafted) == 5, sorted(drafted)
    for slug, text in drafted.items():
        assert len(text) > 500, slug
        assert not _voice_hyphens(text), (slug, _voice_hyphens(text))


run(globals())
