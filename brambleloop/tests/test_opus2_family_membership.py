"""OPUS2 P0-FAMILY-MEMBERSHIP: products discovered after the opening pool can form families.

`creative.family_engine.family_of` read families only from the static radar POOL, so every
product the culture engine originated afterwards was a "single": family development, the
recolour-duplicate check, cross-sell and amplification never reached it. The culture engine
translates one cultural signal across product types and records which signal each concept came
from; that record is the declared family. Nothing is inferred from a category or a palette.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_opus2_family_membership.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CultureConcept, PatternVersion, Product  # noqa: E402
from brambleloop.creative import family_engine as FE  # noqa: E402


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/f.sqlite")
    db.create_all()
    return db


def _certified(db, slug, *, rows=4):
    cir = {"slug": slug, "title": slug, "components": [{"name": "body", "rows": [
        {"index": i, "ops": [{"stitch": "sc", "count": 10}]} for i in range(1, rows + 1)]}]}
    with db.session() as s:
        p = Product(slug=slug, title=slug)
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json=cir, certified=True))


def _concept(db, slug, signal, *, product_slug=""):
    with db.session() as s:
        s.add(CultureConcept(signal_key=signal, slug=slug, family="blanket",
                             product_slug=product_slug))


def test_one_signal_translated_across_types_is_one_family():
    db = _db()
    _concept(db, "aurora-ws-blanket", "sig-aurora", product_slug="aurora-throw")
    _concept(db, "aurora-ws-stocking", "sig-aurora", product_slug="aurora-stocking")
    _concept(db, "harbour-ws-blanket", "sig-harbour", product_slug="harbour-throw")
    for slug in ("aurora-throw", "aurora-stocking", "harbour-throw", "unrelated-coaster"):
        _certified(db, slug, rows=4 if "throw" in slug else 6)
    fam, source = FE.family_of("aurora-throw", db)
    assert fam == "culture:sig-aurora" and "culture_concepts[" in source
    rep = FE.family_report(db)
    families = {f["family"]: f for f in rep["families"]}
    aurora = families["culture:sig-aurora"]
    assert sorted(m["slug"] for m in aurora["members"]) == ["aurora-stocking", "aurora-throw"]
    assert aurora["distinct_designs"] == 2
    assert aurora["bundle_ready"] is False         # OPUS2I F-5: never derived as a set
    assert [m["slug"] for m in families["culture:sig-harbour"]["members"]] == ["harbour-throw"]
    assert "unrelated-coaster" in rep["single_products"]
    # The family grows: the signal's concept not yet made is its next member; a rejected one
    # is not.
    _concept(db, "aurora-ws-ornament", "sig-aurora")
    with db.session() as s:
        s.add(CultureConcept(signal_key="sig-aurora", slug="aurora-ws-pet", family="pet",
                             status="rejected"))
    nxt = {f["family"]: f for f in FE.family_report(db)["families"]}["culture:sig-aurora"]
    assert [m["concept"] for m in nxt["next_members"]] == ["aurora-ws-ornament"], nxt


def test_a_family_is_never_inferred_and_the_pool_still_wins():
    db = _db()
    _certified(db, "some-new-blanket")
    assert FE.family_of("some-new-blanket", db) == (None, "no declared family")
    assert FE.family_of("some-new-blanket") == (None, "no declared family")
    _concept(db, "blank-signal", "  ", product_slug="some-new-blanket")
    assert FE.family_of("some-new-blanket", db)[0] is None      # an empty signal is no family
    from brambleloop.radar.opportunity import POOL

    seed = next(p for p in POOL if p.family)
    _concept(db, "shadow-" + seed.slug, "sig-other", product_slug=seed.slug)
    assert FE.family_of(seed.slug, db)[0] == seed.family        # the declared pool family wins


def _orders(db, slug, n):
    from brambleloop.core.models import Customer, Order

    with db.session() as s:
        cust = Customer(customer_ref=f"c-{slug}")
        s.add(cust)
        s.flush()
        for i in range(n):
            s.add(Order(customer_id=cust.id, external_ref=f"{slug}-{i}", product_slug=slug))


def _aurora(db):
    _concept(db, "aurora-ws-blanket", "sig-aurora", product_slug="aurora-throw")
    _concept(db, "aurora-ws-stocking", "sig-aurora", product_slug="aurora-stocking")
    _concept(db, "aurora-ws-ornament", "sig-aurora")
    _certified(db, "aurora-throw")
    _certified(db, "aurora-stocking", rows=6)


def test_review_opus2g_f1_amplify_parks_a_culture_family_at_the_order_floor():
    db = _db()
    _aurora(db)
    _orders(db, "aurora-throw", FE.AMPLIFY_MIN_ORDERS + 1)
    queued = []
    out = FE.amplify(db, FE.family_report(db),
                     enqueue=lambda *a, **k: queued.append((a, k)))      # no KeyError
    assert queued == [], queued                      # radar.score never gets a concept slug
    decisions = {d["family"]: d["decision"] for d in out.get("decided", out.get("decisions", []))} \
        if isinstance(out, dict) else {}
    assert decisions.get("culture:sig-aurora") == "needs_member_route", out


def test_review_opus2g_f2_f3_cross_sell_and_children_read_the_culture_family():
    from brambleloop.commerce import cross_sell

    db = _db()
    _aurora(db)
    nodes = {n["product"]: n for n in cross_sell.graph(db)["nodes"]}
    throw = nodes["aurora-throw"]
    assert throw["family"] == "culture:sig-aurora"                 # db passed (F-2)
    assert throw["related"] == []                                  # never buyer-facing (F-3)
    assert throw["planned"]["internal"] is True
    assert throw["planned"]["culture_family_members"] == ["aurora-stocking"]


def test_review_opus2g_f2_the_childrens_architecture_reads_the_culture_family_too():
    from brambleloop.creative import children

    db = _db()
    slugs = [f"aurora-baby-blanket-{i}" for i in range(children.BABY_KIDS_DEPTH)]
    assert slugs
    for i, slug in enumerate(slugs):
        _concept(db, f"aurora-ws-baby-{i}", "sig-aurora", product_slug=slug)
        _certified(db, slug, rows=4 + 2 * i)
    arch = children.architecture(db)
    assert arch["propose_collection"] is True, arch
    # Read through the culture family (F-2), but never grouped under it in the navigation (F-5).
    by_family = arch["navigation"]["by_family"]
    assert "culture:sig-aurora" not in by_family and sorted(by_family["single"]) == sorted(slugs)
    assert all(k == "single" for k in by_family)
    assert arch["planned"]["culture_families"] == ["culture:sig-aurora"]   # db passed (F-2)


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
