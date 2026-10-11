"""CAP-1 (owner decision 2026-10-11) raised the Launch-0 cap 5 -> 8 and nothing else.

The approval is a catalogue configuration change. It does not certify, draft, publish or clear
any product. These tests take each of the three products that joined and show that, with
nothing recorded for it, every gate still refuses it on its own:

- certification (`ops.publication_authority` certification section)
- image truth (listing-set certificate; the storefront preview's certified-frame tile)
- listing readiness (`app.dashboard_truth.launch_inventory` launch clearance)
- publication (`publish.release_gates.for_publish`; no owner grant exists)

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_cap1_gates_intact.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402

NEW = ("nordic-forest-mosaic-throw-baby", "mosaic-placemat-pair", "housewarming-key-basket")
FAILS = 0


def check(name, fn):
    global FAILS
    try:
        fn()
        print(f"OK {name}")
    except Exception as e:  # noqa: BLE001
        FAILS += 1
        print(f"FAIL {name}: {e!r}")


def _db() -> Database:
    db = Database("sqlite://", scratch=True)
    db.create_all()
    return db


def _releases():
    out = []
    for slug in NEW:
        cand = l0.candidate(slug)
        assert cand.variants, slug
        for v in cand.variants:
            cir = l0.cir_for(v.build)
            out.append((cir.slug, cir.version))
    assert len(out) == 3, out
    return out


def test_the_three_are_in_launch0_by_the_owner_decision():
    assert l0.CATALOGUE_FLOOR_APPROVED is True
    assert set(NEW) <= set(l0.LAUNCH0_SLUGS)


def test_certification_is_still_required_per_product():
    from brambleloop.ops import publication_authority as pa

    db = _db()
    rels = _releases()
    assert rels
    for slug, version in rels:
        ev = pa.evidence(db, slug, version, "0" * 64)
        assert ev["certification"]["state"] != "PASS", (slug, ev["certification"])


def test_image_truth_is_still_required_per_product():
    from brambleloop.brand import storefront_preview as sp
    from brambleloop.ops import publication_authority as pa

    db = _db()
    rels = _releases()
    assert rels
    for slug, version in rels:
        ev = pa.evidence(db, slug, version, "0" * 64)
        assert ev["listing_set"]["state"] != "PASS", (slug, ev["listing_set"])
        grid = {"visible": [{"slug": slug, "version": version}]}
        tiles = sp.tiles(db, grid, store_root=tempfile.mkdtemp())
        assert [t["status"] for t in tiles["tiles"]] == ["not_certified"], tiles["tiles"]
        assert not tiles["ok"]


def test_listing_readiness_is_still_required_per_product():
    from brambleloop.app.dashboard_truth import launch_inventory
    from brambleloop.brand import storefront

    db = _db()
    inv = launch_inventory(db, survivors=list(NEW))
    cleared = set(inv.get("cleared_slugs") or [])
    rels = _releases()
    assert rels
    for slug, _v in rels:
        assert slug not in cleared, (slug, inv)
    grid = storefront.opening_grid(db, inventory=inv)
    assert not {t["slug"] for t in grid["tiles"]} & set(NEW), grid["tiles"]


def test_publication_is_still_refused_per_product():
    from brambleloop.ops import publication_authority as pa
    from brambleloop.publish import release_gates as rg

    db = _db()
    rels = _releases()
    assert rels
    for slug, version in rels:
        g = rg.for_publish(db, slug=slug, version=version, store_root=tempfile.mkdtemp(),
                           read_only=True)
        assert g["blocks_release"] is True and g["reasons"], (slug, g)
        from sqlalchemy import select

        from brambleloop.core.models import AuditLog

        with db.session() as s:
            grants = list(s.scalars(select(AuditLog).where(AuditLog.action == pa.APPROVED,
                                                           AuditLog.artifact == slug)))
        assert grants == [], slug


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    for name, fn in tests:
        check(name, fn)
    sys.exit(1 if FAILS else 0)
