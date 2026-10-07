"""W4-FM2 / K2 (F-233, F-263): the shop trust gate reads the real storefront, not its briefs.

`brand.storefront.check_storefront` passes the banner and icon when their *brief strings* are
non-empty. Before this change the trust ladder's `shop_complete` rung (and through it the ads
gate) and launch readiness's `storefront` requirement read only that, so a shop with no icon
and no banner read as complete. Both now also read `store_foundation.storefront_gate`
(rendered icon at Etsy display sizes, the owner's canonical banner through its publication
gates, the buyer-facing copy), failing closed. `growth_ops.ads_plan` additionally requires the
listing's stored search certificate (F-294) to be PASS and current.

Every row below is a TEST FIXTURE in a throwaway database. Nothing spends or publishes.
Run: cd brambleloop && PYTHONPATH=src $PY tests/test_w4_fm2_storefront_trust.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import hashlib
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.commerce import trust  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.store_foundation import storefront_gate  # noqa: E402


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fm2_store_')}/t.sqlite")
    db.create_all()
    return db


class _Patch:
    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def _rung(state, key):
    rows = [r for r in state["rungs"] if r["rung"] == key]
    assert len(rows) == 1, key
    return rows[0]


def test_shop_complete_reads_the_asset_gate_not_the_brief():
    """Briefs present, asset gate finding -> the rung FAILS and names the asset finding."""
    db = _db()
    finding = ["STORE_ICON_NOT_RENDERED: asset not rendered (F-233)"]
    with _Patch(storefront_gate, "problems", lambda db=None: list(finding)):
        state = trust.accelerator(db)
    rung = _rung(state, "shop_complete")
    assert rung["verdict"] == trust.FAILED
    assert "asset: " + finding[0] in rung["evidence"]["storefront_problems"]
    assert "shop_complete" in state["failed"]


def test_shop_complete_passes_only_when_brief_and_asset_checks_both_pass():
    db = _db()
    from brambleloop.brand.storefront import build_storefront

    assert build_storefront().problems == []          # the drafted copy itself is clean
    with _Patch(storefront_gate, "problems", lambda db=None: []):
        state = trust.accelerator(db)
    assert _rung(state, "shop_complete")["verdict"] == trust.PASSED


def test_an_unevaluable_asset_gate_fails_closed():
    db = _db()

    def boom(db=None):
        raise OSError("icon raster missing")

    with _Patch(storefront_gate, "problems", boom):
        problems = trust.shop_complete_problems(db)
    assert problems, "an error evaluating the asset gate must be a finding"
    assert any("STORE_GATE_ERROR" in p and "OSError" in p for p in problems)


def test_the_real_gate_today_blocks_paid_traffic_on_the_owner_banner_review():
    """Runtime truth on this head: the owner's canonical banner has outstanding publication
    gates (UNKNOWN never passes), so shop_complete FAILS and ads stay blocked by the shop."""
    db = _db()
    problems = trust.shop_complete_problems(db)
    assets = [p for p in problems if p.startswith("asset: ")]
    assert assets, "the canonical banner's outstanding gates must appear"
    assert all("(F-2" in p for p in assets)
    decision = trust.may_scale_ads(db)
    assert decision["may_scale"] is False and "shop_complete" in decision["blocking"]


def test_launch_readiness_storefront_requirement_carries_the_asset_gate():
    """Runtime consumer: launch.readiness.assess -> requirement `storefront` (shop_trustworthy)."""
    from brambleloop.core.models import Phase
    from brambleloop.launch import readiness

    db = _db()
    r = readiness.assess(db, phase=Phase.SHADOW)
    rows = [q for q in r.requirements if q.key == "storefront"]
    assert len(rows) == 1
    store = rows[0]
    assert store.ready is False
    assert store.evidence["problems"], "the asset findings must be evidence"
    assert any(p.startswith("asset: STORE_BANNER_OWNER_") for p in store.evidence["problems"])


def _listing(db, slug, *, profile_verdict=None, current=True):
    from brambleloop.core.models import (
        Listing, ListingSearchProfile, PatternVersion, Product,
    )
    from brambleloop.publish.release_gates import search_fingerprint

    title, desc, tags = f"{slug} crochet pattern", "A throw.", ["crochet pattern"]
    with db.session() as s:
        p = Product(slug=slug, title=slug, status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={"components": []},
                             release_hash=hashlib.sha256(slug.encode()).hexdigest(),
                             certified=True, certificate={}))
        s.add(Listing(product_slug=slug, version="1.0.0", title=title, description=desc,
                      tags=tags, price_cad=12.5, state="published"))
        if profile_verdict:
            fp = search_fingerprint(title=title if current else "other", description=desc,
                                    tags=tags, taxonomy_id=1, properties=[])
            s.add(ListingSearchProfile(product_slug=slug, version="1.0.0", taxonomy_id=1,
                                       properties=[], verdict=profile_verdict,
                                       fingerprint=fp))


def test_ads_plan_requires_a_current_passing_search_certificate():
    from brambleloop.runtime import growth_ops

    db = _db()
    _listing(db, "no-profile")
    _listing(db, "refused", profile_verdict="REFUSED")
    _listing(db, "stale", profile_verdict="PASS", current=False)
    _listing(db, "certified", profile_verdict="PASS")
    plan = growth_ops.ads_plan(db)
    rows = {p["slug"]: p for p in plan["products"]}
    assert set(rows) >= {"no-profile", "refused", "stale", "certified"}
    want = {"no-profile": "NONE", "refused": "REFUSED", "stale": "STALE", "certified": "PASS"}
    assert want and rows
    for slug, verdict in want.items():
        assert rows[slug]["search_certificate"] == verdict, (slug, rows[slug])
        blocked = any(b.startswith("search certificate (#294)")
                      for b in rows[slug]["blocked_by"])
        assert blocked == (verdict != "PASS"), (slug, rows[slug]["blocked_by"])
    # the shop gate (F-233) still blocks every product today
    assert all(any(b.startswith("trust (#17)") for b in r["blocked_by"])
               for r in rows.values())
    assert plan["eligible"] == [] and plan["spend_cad"] == 0.0


def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    assert tests
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK {name}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    return failed


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
