"""W4-AGENTS cluster C3: F-527 Brand Asset Health, F-775 Cross-Sell Graph, F-113 Commercial
Salvage Test (recommends only). Deterministic, our own rows, CA$0.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_c3.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (Listing, ListingAsset, PatternVersion, Phase,  # noqa: E402
                                     Product)
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import etsy_ops, pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, JobContext, handlers  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="w4c3_")
_N = [0]


def _db():
    _N[0] += 1
    db = Database(f"sqlite:///{_TMP}/c{_N[0]}.db")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _certify(db, slug, version="1.0.0", width=40):
    from brambleloop.runtime.pipeline import Concept, concept_to_cir

    cir = concept_to_cir(Concept(slug=slug, title=f"{slug} panel", category="coaster",
                                 stitch_repeat=[("sc", 2), ("dc", 2)], width_stitches=width,
                                 rows=8, colors={"A": "cream", "B": "sage"}), version=version)
    with db.session() as s:
        p = s.scalar(select(Product).where(Product.slug == slug))
        if p is None:
            p = Product(slug=slug, title=slug, status="certified")
            s.add(p)
            s.flush()
        s.add(PatternVersion(product_id=p.id, version=version, cir_json=cir.to_dict(),
                             certified=True, release_hash=f"{slug}{version}"))
    return cir


def _run(db, agent, jt):
    job = JobQueue(db).enqueue(agent, jt, {})
    Registry(db).authorize(agent, jt)
    return handlers.get(jt)(JobContext(job=job, db=db, queue=JobQueue(db),
                                       registry=Registry(db), phase=Phase.SHADOW))


def test_f527_missing_stale_blocked_and_low_resolution_assets_are_routed():
    from brambleloop.store_foundation import asset_health as AH

    db = _db()
    etsy_ops.store_reading(db, etsy_ops.SHOP_READING, {"observed_at": time.time(),
                           "shop": {"icon_url_fullxfull": "", "image_url_760x100": ""}})
    _certify(db, "no-hero")
    _certify(db, "old-assets", "2.0.0")
    _certify(db, "bad-assets")
    with db.session() as s:
        s.add(ListingAsset(product_slug="old-assets", version="1.0.0", position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=True))
        s.add(ListingAsset(product_slug="bad-assets", version="1.0.0", position=1,
                           asset_class="DIGITAL_TWIN_RENDER", role="hero", approved=True,
                           claims={"width_px": 1000, "height_px": 1000}))
        s.add(ListingAsset(product_slug="bad-assets", version="1.0.0", position=2,
                           asset_class="AI_LIFESTYLE_CONCEPT", role="lifestyle",
                           approved=False, blocked_reasons=["off-brand palette"]))
    out = AH.check(db)
    codes = {(f["code"], f["subject"]): f["route_to"] for f in out["findings"]}
    assert codes[("ICON_MISSING", "shop_icon")] == "storefront_director"
    assert codes[("HERO_MISSING", "no-hero")] == "publishing"
    assert codes[("ASSETS_STALE", "old-assets")] == "publishing"
    assert codes[("ASSET_BLOCKED", "bad-assets")] == "publishing"
    assert codes[("ASSET_LOW_RESOLUTION", "bad-assets")] == "publishing"
    assert out["banner"] == "UNKNOWN"                     # LISTREADY E7: blank is not missing
    assert not any(c == "BANNER_MISSING" for c, _ in codes)
    assert out["live_colour_typography"] == "UNMEASURED" and out["writes"] == 0
    rv = _run(db, "storefront_director", "storefront.review")
    assert rv["asset_health"]["fixes"] >= 4


def test_f775_cross_sell_links_only_certified_products_with_tutorials_and_materials():
    from brambleloop.commerce import cross_sell as CS
    from brambleloop.radar.opportunity import POOL

    db = _db()
    fam = [p.slug for p in POOL if p.family == "nordic-forest" and not p.is_bundle][:2]
    for slug in fam:
        _certify(db, slug)
    g = CS.graph(db)
    nodes = {n["product"]: n for n in g["nodes"]}
    a, b = fam
    assert nodes[a]["related"] == [b] and nodes[b]["related"] == [a]
    assert any("bundle" in x for x in nodes[a]["bundles"])
    assert nodes[a]["materials"] and nodes[a]["attach_rate"] == "UNMEASURED"
    assert isinstance(nodes[a]["tutorials"], list)        # approved lessons only (none yet)
    certified = set(nodes)
    assert g["nodes"], "two certified products give two nodes"
    for n in g["nodes"]:
        assert set(n["related"]) <= certified and set(n["next_projects"]["in_catalogue"]) \
            <= certified
    assert ("cross_sell_graph", "listing", "listing.cross_sell_graph", 86400) in CADENCES
    assert _run(db, "listing", "listing.cross_sell_graph")["products"] == 2


def test_f113_salvage_only_recommends_and_never_writes():
    from brambleloop.creative import salvage as SV

    db = _db()
    _certify(db, "legacy-panel-one")
    _certify(db, "legacy-panel-two")
    with db.session() as s:
        s.add(Listing(product_slug="legacy-panel-one", version="1.0.0", title="t",
                      description="d", tags=[], price_cad=5.0))

    def counts():
        with db.session() as s:
            return tuple(s.scalar(select(func.count()).select_from(m))
                         for m in (Product, PatternVersion, Listing, ListingAsset))

    before = counts()
    real = SV.review(db)                                   # real gates run end to end
    assert real["count"] == 2 and "never deletes" in real["acts"] and real["writes"] == 0
    for row in real["legacy"]:
        assert set(row["gates"]) == {"creative", "mjs_market", "seasonal", "novelty",
                                     "portfolio"}
    orig = SV._gates
    SV._gates = lambda db_, r, sel, comp: {
        k: {"verdict": ("FAIL" if (r["slug"].endswith("one") and k == "creative")
                        else "PASS"), "why": "t"}
        for k in ("creative", "mjs_market", "seasonal", "novelty", "portfolio")}
    try:
        rep = SV.review(db)
    finally:
        SV._gates = orig
    rec = {r["slug"]: r["recommendation"] for r in rep["legacy"]}
    assert rec == {"legacy-panel-one": "retire_recommended",
                   "legacy-panel-two": "rescue_candidate"}
    out = _run(db, "creative_director", "creative.salvage_review")
    assert out["writes"] == 0
    assert counts() == before                              # nothing deleted, unlisted, changed
    with db.session() as s:
        assert s.scalar(select(Listing.state)) == "draft"


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
