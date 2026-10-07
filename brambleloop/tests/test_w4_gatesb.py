"""W4-GATESB: the business gates cleared or honestly classified (owner authorisation 2026-10-07).

Drives the real consumers -- `build2.executor.approval_inbox` (the console's "waiting on the
owner" table), `build2.closure.classify`, `build2.gate_clearance`, the tester programme's
intake, the second-market selection and the store owner-action sync -- over fresh databases.
No network: every Etsy read goes through a recorded reader.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from brambleloop.build2 import closure, executor, gate_clearance  # noqa: E402
from brambleloop.build2 import requirements as reg  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    BenchmarkListing, CreatorProfile, Listing, OwnerAction,
)
from brambleloop.intel import benchmarks  # noqa: E402

RESULTS: list[str] = []


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    benchmarks.seed(db)
    return db


# ---- 6. customers: DATA/EXTERNAL, never an owner card ---------------------------------------

def test_customers_is_data_gated_and_never_an_owner_card():
    assert closure.kind_of("customers") == closure.DATA_GATED
    assert "customers" not in closure.OWNER_GATES
    from brambleloop.ops import owner_queue as Q

    assert "customers" not in Q.GATE_PACKETS
    inbox = executor.approval_inbox(_db(), env={})
    cards = inbox["cards"]
    assert cards, "a fresh database has owner cards"
    assert "customers" not in [c["gate"] for c in cards]
    assert "customers" in [d["gate"] for d in inbox["waiting_on_data"]]
    what = executor.GATE_BY_KEY["customers"].what
    assert "never an owner action" in what and "same table" not in what
    ok("customers: DATA-GATED in closure, listed under waiting_on_data, never an owner card")


def test_ads_economics_rows_park_on_data_not_ad_authority():
    rows = {r.id: r for r in reg.load()}
    for rid in (242, 243, 244, 245):
        assert rows[rid].parked_on == "customers", rid
        assert executor.gate_for(rid) == "customers"
        row = closure.classify(rows[rid], gate_open={})
        assert row["state"] in (closure.DATA_GATED, closure.OPEN), row
        assert row["gate"] == "customers"
    assert executor.GATE_BY_KEY["ad_authority"].requirement_ids == (294, 295)
    for rid in (294, 295):
        assert executor.gate_for(rid) == "ad_authority"
    ok("#242-245 park on customers (order data); only #294/#295 wait on an ad budget")


# ---- not-yet-askable: ads and listings wait on preconditions; the make is asked with testers ----------------

def test_preconditioned_gates_are_listed_not_asked():
    inbox = executor.approval_inbox(_db(), env={})
    gates = [c["gate"] for c in inbox["cards"]]
    waiting = {d["gate"]: d for d in inbox["not_yet_askable"]}
    assert waiting, "preconditioned gates are listed"
    for g in ("ad_authority", "live_listings"):
        assert g not in gates, g
        assert g in waiting and waiting[g]["precondition"], g
    assert "ready to sell" in waiting["ad_authority"]["precondition"]
    # physical_proof is asked with tester_roster: one owner decision (DECISIONS tester_outreach)
    assert "physical_proof" in gates and "physical_proof" not in waiting
    proof = [c for c in inbox["cards"] if c["gate"] == "physical_proof"]
    assert "not being asked to crochet" in proof[0]["action"], proof[0]["action"]
    tester = [c for c in inbox["cards"] if c["gate"] == "tester_roster"]
    assert tester and "Ravelry" in tester[0]["action"]
    assert tester[0]["max_cost_cad"] == 0.0 and tester[0]["minutes"] == 20
    ok(f"not_yet_askable: {sorted(waiting)}; tester_roster card carries the prepared outreach")


# ---- 1. benchmark_purchases: the exact list ----------------------------------------------

def _seed_mjs(db):
    pods = ["garments", "blankets", "collections", "education", "hats", "amigurumi",
            "stockings", "kitchen_bath", "seasonal_gift", "unclassified", "home_decor",
            "bags", "ornaments"]
    with db.session() as s:
        for i, pod in enumerate(pods):
            for j in range(2):
                s.add(BenchmarkListing(
                    benchmark_key=benchmarks.MJS_KEY, listing_ref=f"{1000 + 10 * i + j}",
                    title=f"CROCHET PATTERN Mj&#39;s {pod} {j}", pod=pod,
                    price_cad=16.0 + i + j, media_count=10 - j, audit_state="audited",
                    url=f"https://www.etsy.com/listing/{1000 + 10 * i + j}/x",
                    fingerprint=f"{pod}{j}",
                    detail={"num_favorers": 100 + i, "has_video": bool(j)}))


def test_benchmark_purchase_list_is_the_approved_set_with_links_and_intake():
    from brambleloop.teardown import intake

    db = _db()
    _seed_mjs(db)
    plan = gate_clearance.benchmark_purchase_list(db)
    picks = plan["picks"]
    assert picks and len(picks) <= intake.SET_SIZE
    assert plan["total_cad"] <= intake.SET_BUDGET_CAD and plan["within_budget"]
    for p in picks:
        assert p["url"].startswith("https://www.etsy.com/listing/") and p["price_cad"] > 0
        assert "&#39;" not in p["title"]
    assert plan["delivery"]["page"].endswith("/ops/teardown")
    assert plan["delivery"]["api_form"]["listing_ref"]
    # The same picks the upload page ticks off.
    assert [p["listing_ref"] for p in picks] == [
        p["listing_ref"] for p in intake.plan(db)["picks"]]
    fields = gate_clearance.card_fields(db, "benchmark_purchases")
    assert fields["max_cost_cad"] == plan["total_cad"] and len(fields["links"]) == len(picks) + 1
    ok(f"benchmark list: {len(picks)} picks, CA${plan['total_cad']:.2f}, intake order matches")


# ---- 5. owned_surfaces recognises the shop -----------------------------------------------

def test_owned_surfaces_recognises_the_etsy_shop_and_names_what_is_missing():
    db = _db()
    inv = gate_clearance.owned_surfaces_inventory(db, env={})
    assert "etsy_shop" in inv["present"] and inv["present"]["etsy_shop"]["evidence"]
    parked = [r.id for r in reg.load() if executor.gate_for(r.id) == "owned_surfaces"]
    assert parked
    for rid in parked:
        assert rid in gate_clearance.OWNED_SURFACE_NEEDS, rid
    assert {"site", "pinterest"} <= set(inv["missing"])
    for k, v in inv["missing"].items():
        assert v["why"] and v["owner_step"] and v["minutes"] > 0, k
    assert "Etsy shop" in executor.GATE_BY_KEY["owned_surfaces"].what
    ok(f"owned_surfaces: etsy shop recognised; missing {sorted(inv['missing'])} for "
       f"{len(parked)} rows")


# ---- 7. ad readiness and the recommendation ----------------------------------------------

def test_ad_budget_is_recommended_only_when_a_listing_is_ready():
    from brambleloop.commerce.paid_media import CONSERVATIVE_CAPS

    db = _db()
    state = gate_clearance.ad_readiness(db, env={})
    assert state["ready"] is False and state["recommended"] is None and state["why_not"]
    with db.session() as s:
        s.add(Listing(product_slug="market-basket-small", version="1.2.0", title="t",
                      description="d", price_cad=5.0, state="active", release_hash="h" * 64,
                      etsy_listing_id="123"))
    state = gate_clearance.ad_readiness(db, env={})
    assert state["ready"] is False and any("orders" in w for w in state["why_not"])
    gate = executor.GATE_BY_KEY["transactions_r"]
    saved = gate.check
    gate.check = lambda db, env: True
    try:
        state = gate_clearance.ad_readiness(db, env={})
        assert gate_clearance.prerequisite(db, "ad_authority", {}) is None
    finally:
        gate.check = saved
    assert state["ready"] is True and state["ready_listings"][0]["etsy_listing_id"] == "123"
    rec = state["recommended"]
    assert rec["daily_cad"] == CONSERVATIVE_CAPS.daily_cad
    assert rec["monthly_cad"] == CONSERVATIVE_CAPS.monthly_cad
    ok("ad budget: none before a listing is ready and measurable; then the in-code caps")


# ---- 3. tester roster ---------------------------------------------------------------------

def test_tester_agreement_needs_express_consent_and_opens_the_gate():
    from brambleloop.growth import creators
    from brambleloop.quality import tester_programme as tp

    db = _db()
    try:
        tp.record_agreement(db, handle_ref="t1", specialties=["home_decor"],
                            express_consent=False, consent_source="form")
        raise AssertionError("recorded without consent")
    except tp.TesterRefused:
        pass
    assert executor._tester_recruited(db, None) is False
    out = tp.record_agreement(db, handle_ref="t1", specialties=["home_decor"],
                              express_consent=True, consent_source="intake form v1 row 1",
                              photo_scopes=["brambleloop_listing"])
    assert out["recorded"] and out["brief"]["ok"]
    assert executor._tester_recruited(db, None) is True
    with db.session() as s:
        assert s.query(CreatorProfile).count() == 1
    body = tp.OUTREACH_POST["body"].lower()
    for needle, _why in creators.SENTIMENT_STRINGS:
        assert needle not in body, needle
    assert tp.OUTREACH_POST["sends_to_individuals"] is False
    assert "withdraw" in tp.CONSENT_TEXT and "unsubscribe" in tp.CONSENT_TEXT
    assert tp.packet()["sent"] is False
    ok("tester: refused without express consent; agreement opens tester_roster; nothing sent")


# ---- 2. physical proof kit -----------------------------------------------------------------

def test_physical_kit_feeds_the_existing_intake():
    from brambleloop.quality import tester_kit

    manifest = json.loads((ROOT / "research/final_build/w4/tester_kit/KIT_MANIFEST.json")
                          .read_text())
    version, chash = tester_kit.content_hash()
    assert manifest["content_hash"] == chash and manifest["version"] == version
    for name in manifest["files"]:
        assert (ROOT / "research/final_build/w4/tester_kit" / name).stat().st_size > 1000
    payload = tester_kit.intake_payload(
        {"tester_ref": "t1", "grams_cream": "21", "grams_wine": "6",
         "ball_band_grams": "71", "ball_band_metres": "109", "hook_mm": "5",
         "width_cm": "16.4", "height_cm": "9", "hours": "2.5", "followed": "yes",
         "problems": "rnd 9 unclear"}, content_hash=chash)
    for key in ("slug", "grams_by_color", "ball_band_grams", "ball_band_metres"):
        assert payload[key], key   # /api/physical-test's required fields
    assert payload["scope"] == "full_make" and payload["content_hash"] == chash
    assert tester_kit.MATERIALS_TOTAL_CAD > 0
    ok(f"physical kit: {manifest['slug']}@{version} content {chash[:12]}, intake payload "
       f"complete")


# ---- 4. second market ----------------------------------------------------------------------

class _Reader:
    def __init__(self, shops):
        self.shops = shops

    def resolve_shop(self, name):
        for sid, sh in self.shops.items():
            if sh["shop_name"].lower() == name.lower():
                return {"shop_id": sid, "shop_name": sh["shop_name"]}
        raise KeyError(name)

    def shop(self, sid):
        return self.shops[int(sid)]


def test_second_market_selection_is_verified_before_it_counts():
    from brambleloop.intel import second_market

    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="x",
                               pod="hats", price_cad=5.0, media_count=5, fingerprint="a"))
    liar = _Reader({1: {"shop_name": "LakesideLoops", "shop_location_country_iso": "US"}})
    out = second_market.ensure_selected(db, liar)
    assert out and out[0]["state"] == "refused" and out[1]["state"] == "unverified"
    reader = _Reader({1: {"shop_name": "LakesideLoops", "shop_location_country_iso": "CA"},
                      2: {"shop_name": "HanJanCrochet", "shop_location_country_iso": "GB"}})
    out = second_market.ensure_selected(db, reader)
    assert [o["state"] for o in out] == ["joined", "joined"], out
    assert [o["market"] for o in out] == ["CA", "other"]
    assert second_market.ensure_selected(db, reader)[0]["state"] == "already_joined"
    # Registered is not observed: the gate stays closed until listings are read.
    assert executor._second_market_observed(db, {}) is False
    with db.session() as s:
        s.add(BenchmarkListing(benchmark_key=out[0]["key"], listing_ref="2", title="y",
                               pod="blankets", price_cad=7.0, media_count=5, fingerprint="b"))
    assert executor._second_market_observed(db, {}) is True
    from brambleloop.core import decision_index

    assert decision_index.recorded(second_market.DECISION_ID)
    ok("second market: refused on a contradicting getShop, joined when verified, gate opens "
       "only on observed listings; decision recorded")


# ---- store owner actions as rows -------------------------------------------------------------

def test_store_owner_actions_become_batched_rows_once():
    from brambleloop.ops import owner_queue as Q
    from brambleloop.store_foundation import store_readiness as sr

    db = _db()
    first = sr.sync_owner_actions(db, {})
    assert first["created"] and "OA-A2" in first["skipped"] and "OA-STATS" in first["skipped"]
    assert "store:OA-B" in first["created"] and "store:OA-A2" not in first["created"]
    again = sr.sync_owner_actions(db, {})
    assert not again["created"]
    with db.session() as s:
        keys = [r.requirement_key for r in s.query(OwnerAction).all()]
    assert len(keys) == len(set(keys))
    inbox = executor.approval_inbox(db, env={})
    batches = {b["id"]: b for b in Q.batch_cards(inbox["cards"])["batches"]} \
        if isinstance(Q.batch_cards(inbox["cards"]), dict) else {}
    found = [i for b in batches.values() for i in b["items"]
             if "store:OA-B" in i.get("requirement_keys", [])]
    assert found and [b for b in batches.values() if found[0] in b["items"]][0]["id"] \
        == "etsy_account"
    ok(f"store: {len(first['created'])} owner-action rows, idempotent, batched with the "
       f"Etsy account screens")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert tests
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(RESULTS)} passed, {failed} failed")
    sys.exit(1 if failed else 0)
