"""Certification C-58: every hero keeps its content out of the marketplace's title-safe band.

The #66 mobile gate, once wired (W1a), refused the flagship: 4.7% of the hero's title-safe band
carried ink at search-grid size, because the fabric spanned 96% of the width and the brand line
and the "not a photograph" disclosure sat inside the 8% band the marketplace overlays. The gate
was right; the layout was repaired, not the rule.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.cir.compiler import compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.commerce import thumbnail  # noqa: E402
from brambleloop.products import builder, nordic_forest  # noqa: E402
from brambleloop.publish import listing_assets as LA  # noqa: E402
from brambleloop.publish import mobile  # noqa: E402


def _heroes():
    cirs = [builder.build(d) for d in builder.CATALOGUE.values()]
    cirs.append(nordic_forest.build())
    for cir in cirs:
        yield cir.slug, LA._hero(cir, build_twin(cir, compile_cir(cir)))


def test_the_hero_margin_is_at_least_the_title_safe_band():
    assert LA.HERO_TITLE_SAFE >= mobile.TITLE_SAFE_MARGIN


def test_no_hero_puts_ink_in_the_title_safe_band_and_every_thumbnail_still_passes():
    for slug, hero in _heroes():
        ink = mobile.title_safe_ink(hero.image)
        assert ink == 0.0, (slug, ink)
        verdict = thumbnail.evaluate_thumbnail(hero.image)
        assert not verdict.problems, (slug, verdict.problems)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
