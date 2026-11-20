"""W4-FMGATE (F-009): the catalogue console shows, per listing, the Etsy filters it enters and
the ones it loses -- read from the search profile listing.seo stored -- and says UNMEASURED
(never an empty "nothing lost") when the node's schema has not been read."""
from __future__ import annotations
import _opread  # W4-SECPATCH: owner-only GETs need the operator credential

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import atexit  # noqa: E402
import shutil  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="fmgate_cat_")
atexit.register(shutil.rmtree, _TMP, True)
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'c.db')}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)

import fixtures_etsy_taxonomy as FX  # noqa: E402
from brambleloop.commerce import category as C  # noqa: E402
from brambleloop.core.models import Listing, ListingSearchProfile  # noqa: E402


def _client():
    from fastapi.testclient import TestClient

    from brambleloop.app import main

    main.db.create_all()
    return main, TestClient(main.app)


def _filters_for(colors):
    snap = FX.snapshot()
    facts = C.Facts(category="coaster", difficulty="beginner", colors=colors, season=None)
    return C.properties_for(snap, C.choose(snap, "coaster"), facts)["filters"]


def test_entered_and_lost_filters_per_listing_and_unmeasured_without_a_schema():
    main, client = _client()
    audit = _filters_for([("zzz-unnamed", None)])
    assert audit["measurable"] is True and audit["lost_to_missing_data"]
    with main.db.session() as s:
        for slug in ("measured-coaster", "unknown-node", "no-profile"):
            s.add(Listing(product_slug=slug, version="1.0.0", title="t", description="d",
                          tags=[], price_cad=8.5, seo_score=0.5))
        s.add(ListingSearchProfile(product_slug="measured-coaster", version="1.0.0",
                                   category_status="CERTIFIED", filters=audit))
        s.add(ListingSearchProfile(product_slug="unknown-node", version="1.0.0",
                                   category_status="UNKNOWN",
                                   filters={"entered": [], "lost": [], "measurable": False}))
    rows = {r["slug"]: r for r in _opread.get(client, "/api/catalogue").json()["listings"]}
    measured = rows["measured-coaster"]["filters"]
    assert measured["state"] == "MEASURED"
    assert {"Craft type", "Skill level"} <= set(measured["entered"]), measured
    assert "Primary color" in measured["lost_to_missing_data"], measured
    assert any(x["filter"] == "Primary color" for x in measured["lost"])
    unknown = rows["unknown-node"]["filters"]
    assert unknown["state"] == "UNMEASURED" and "UNKNOWN" in unknown["why"], unknown
    none = rows["no-profile"]["filters"]
    assert none["state"] == "UNMEASURED" and "listing.seo" in none["why"], none


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
