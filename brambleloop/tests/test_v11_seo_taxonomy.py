"""Lane G: taxonomy readiness -- confirmed vs assumed Etsy categories for Launch-0.

No Etsy credential has been demonstrated, so every Launch-0 category is assumed and must
read GATED(etsy_api). The 2112/2114/2115 ids are the illustrative fixture ids, never reported
as a category for a product.
"""
from __future__ import annotations

from datetime import datetime, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.seo._testkit import fresh_db, launch0_facts, run  # noqa: E402

import fixtures_etsy_taxonomy as FX
from brambleloop.seo import taxonomy


def test_empty_db_marks_every_launch0_category_gated_on_etsy_api():
    rows = taxonomy.readiness(fresh_db(), launch0_facts())
    assert len(rows) == len(launch0_facts()) and rows
    for r in rows:
        assert r["status"] == taxonomy.GATED == "GATED(etsy_api)", r
        assert r["gated_by"] == "etsy_api"
        assert r["taxonomy_id"] is None and r["basis"] == "assumed"
        assert r["category_intent"]                      # the intent is still reported
    assert {r["category_intent"] for r in rows} >= {"basket", "coaster", "baby"}


def test_a_snapshot_not_written_by_an_etsy_read_does_not_confirm():
    from brambleloop.core.models import EtsyTaxonomySnapshot

    db = fresh_db()
    snap = FX.snapshot()
    with db.session() as s:      # fixture insert: default source, but no confirmed_at
        s.add(EtsyTaxonomySnapshot(sha256="fixture", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"]))
    rows = taxonomy.readiness(db, launch0_facts())
    assert rows and all(r["status"] == taxonomy.GATED for r in rows), rows
    assert all(r["taxonomy_id"] is None for r in rows)


def test_an_etsy_read_snapshot_confirms_the_deepest_truthful_node():
    from brambleloop.core.models import EtsyTaxonomySnapshot

    db = fresh_db()
    snap = FX.snapshot()
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with db.session() as s:
        s.add(EtsyTaxonomySnapshot(sha256="etsyread", node_count=len(snap["nodes"]),
                                   nodes=snap["nodes"], properties=snap["properties"],
                                   source="etsy_open_api_v3", fetched_at=now,
                                   confirmed_at=now))
    rows = {r["slug"]: r for r in taxonomy.readiness(db, launch0_facts(), now=now)}
    assert rows
    assert rows["market-basket-small"]["status"] == taxonomy.CONFIRMED
    assert rows["market-basket-small"]["taxonomy_id"] == 2115     # fixture tree's basket node
    assert rows["hexagon-coaster-set"]["taxonomy_id"] == 2114
    assert all(r["basis"] == "measured" for r in rows.values() if r["status"] == "CONFIRMED")


def test_open_gate_without_a_snapshot_is_pending_refresh():
    from brambleloop.integrations import etsy_taxonomy

    original = etsy_taxonomy.gate
    etsy_taxonomy.gate = lambda db: {"open": True, "missing": []}
    try:
        rows = taxonomy.readiness(fresh_db(), launch0_facts())
    finally:
        etsy_taxonomy.gate = original
    assert rows and all(r["status"] == taxonomy.PENDING_REFRESH for r in rows), rows


if __name__ == "__main__":
    run(globals())
