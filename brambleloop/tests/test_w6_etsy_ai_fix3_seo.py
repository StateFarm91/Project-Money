"""ENG-ETSY-AI-FIX3 (L-a, H1): the listing.seo hold-card wiring, through the real handler.

runtime/release.py::handle_listing_seo raises `etsy_ai_policy.hold_card` for every
POLICY_AUTHORSHIP_CLAIM finding on the copy it drafted. Pinned here on the real certified
release fixture (tests/test_search_hero_publish.py: certify -> assets.build -> listing.seo):

  L-a  a draft carrying "Handmade" raises the owner card `authorship_copy_hold:<slug>@<ver>`
       with its reason, and the draft is refused (not ok).
  H1   the listing the real chain drafts is a composition: every unit is an allowlisted
       honest statement, a closed template (slots validated) or validated free text.

Run: cd brambleloop && python3 tests/test_w6_etsy_ai_fix3_seo.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702 - W3-HYG per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_search_hero_publish as SH  # noqa: E402  (sets its env and loopback-only sockets)

from sqlalchemy import select  # noqa: E402

from brambleloop.commerce import seo as seo_mod  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Listing, OwnerAction  # noqa: E402
from brambleloop.products import launch0 as l0  # noqa: E402
from brambleloop.publish import etsy_ai_policy as pol  # noqa: E402
from brambleloop.publish import listing_composition as lc  # noqa: E402


def _seo(db, version, rh):
    plan = l0.launch_price(SH.SLUG)
    return SH._run(db, "listing", "listing.seo",
                   {"slug": SH.SLUG, "version": version, "release": rh,
                    "price_cad": plan["price_cad"], "category": "baby_blanket"})


def test_the_real_drafted_listing_is_a_composition_of_templates_and_validated_text():
    path, version, _rh = SH._chain()
    db = Database(f"sqlite:///{path}")
    with db.session() as s:
        row = s.scalar(select(Listing).where(Listing.product_slug == SH.SLUG)
                       .order_by(Listing.id.desc()))
        title, desc, tags = row.title, row.description, list(row.tags or [])
    units = lc.composition(title + "\n" + desc)
    assert len(units) > 20, units
    for u in units:
        assert u["problems"] == [], u
        assert u["kind"] in ("honest", "honest+free", "free") or u["kind"].startswith(
            "template:"), u
    kinds = {u["kind"] for u in units}
    assert {"template:lead", "template:fact.skill", "honest"} <= kinds, sorted(kinds)
    assert all(lc.constrained_problems(t) == [] for t in tags), tags


def test_listing_seo_raises_the_hold_card_for_a_handmade_draft():
    path, version, rh = SH._chain()
    db = Database(f"sqlite:///{path}")
    real = seo_mod.opening_sentence
    # The drafted copy carries "Handmade" (as an LLM-drafted marketing line would).
    seo_mod.opening_sentence = lambda phrases: "Handmade with love for your little one."
    try:
        job = _seo(db, version, rh)
    finally:
        seo_mod.opening_sentence = real
    assert not job.outputs.get("ok"), job.outputs
    key = f"authorship_copy_hold:{SH.SLUG}@{version}"
    with db.session() as s:
        rows = list(s.scalars(select(OwnerAction).where(OwnerAction.requirement_key == key)))
    assert len(rows) == 1 and not rows[0].done, rows
    reason = rows[0].reason
    assert pol.CODE in reason and "listing.seo" in reason, reason
    assert "handmade" in reason.lower() and "mentions" in reason, reason
    assert f"publication of {SH.SLUG}@{version}" in rows[0].blocks
    # the unpatched draft raises no card of its own
    path2, version2, rh2 = SH._chain()
    db2 = Database(f"sqlite:///{path2}")
    job = _seo(db2, version2, rh2)
    with db2.session() as s:
        assert not list(s.scalars(select(OwnerAction).where(
            OwnerAction.requirement_key == key))), "a clean draft raised a hold card"


if __name__ == "__main__":
    import traceback

    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests, "no tests collected"
    for name, fn in tests:
        try:
            fn()
            print(f"OK   {name}")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            print(f"FAIL {name}")
            fails += 1
    print(f"\n{len(tests) - fails} passed, {fails} failed")
    raise SystemExit(1 if fails else 0)
