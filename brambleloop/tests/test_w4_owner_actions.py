"""W4-OWNER: the owner's decision packet -- batches -> decisions -> seven fields.

Drives the real consumer (`build2.executor.approval_inbox`, which the Command Center approvals
inbox reads) over a fresh database and over the nine owner actions production held open on
2026-10-06 (deployed fcb982d, `/api/owner-actions`): object storage, open the shop, payout,
listing fees, trademark, phase, benchmark purchases and the same Anthropic top-up twice.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue as Q  # noqa: E402

RESULTS: list[str] = []

# requirement_key -> (max_cost_cad, minutes) as production stated them.
PRODUCTION_9 = [
    ("artifact_storage", 5.0, 10), ("etsy_shop", 0.0, 25), ("payout", 0.0, 15),
    ("listing_fees", 6.0, 2), ("brand_clearance", 460.0, 20), ("phase", 0.0, 5),
    ("benchmark_challenge", 300.0, 30), ("model_provider_balance", 25.0, 5),
    ("model_credits", 25.0, 3),
]


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _seed_production(db) -> dict[str, int]:
    ids = {}
    with db.session() as s:
        for key, cost, minutes in PRODUCTION_9:
            row = OwnerAction(requirement_key=key, action=f"production action {key}",
                              reason=f"production reason {key}", max_cost_cad=cost,
                              minutes=minutes, consequence_of_delay=f"delay {key}",
                              blocks=key)
            s.add(row)
            s.flush()
            ids[key] = row.id
    return ids


def test_decision_table_is_complete():
    assert Q.DECISIONS and Q.BATCHES
    seen = set()
    for d in Q.DECISIONS:
        assert d["id"] not in seen, d["id"]
        seen.add(d["id"])
        assert d["batch"] in Q.BATCH_BY_ID, d
        assert d["kind"] in Q.REQUIREMENT_KINDS, d
        for f in ("decision", "why", "consequence_of_yes", "consequence_of_no",
                  "cost_basis"):
            assert str(d[f]).strip(), (d["id"], f)
        assert d["minutes"] and d["minutes"] > 0, d["id"]
        assert d["max_cost_cad"] is None or d["max_cost_cad"] >= 0, d["id"]
        if d["max_cost_cad"] is None:
            assert "UNKNOWN" in d["cost_basis"] or "readiness" in d["cost_basis"], d["id"]
    ok(f"{len(Q.DECISIONS)} decisions in {len(Q.BATCHES)} batches carry every field")


def test_fresh_inbox_batches_every_card_with_seven_fields():
    from brambleloop.build2 import executor

    inbox = executor.approval_inbox(_db(), env={})
    cards, packet = inbox["cards"], inbox["batches"]
    assert cards and packet["batches"], packet
    items = [i for b in packet["batches"] for i in b["items"]]
    assert items
    assert packet["decisions"] == len(items) < len(cards), (packet["decisions"], len(cards))
    covered = {(g) for i in items for g in i["gates"]}
    assert {c["gate"] for c in cards if c["gate"]} <= covered
    for i in items:
        assert not i["fields_missing"], (i["id"], i["fields_missing"])
        for f in Q.DECISION_FIELDS:
            assert f in i, (i["id"], f)
        if i["max_cost_cad"] is None:
            assert i["max_cost_display"] == "UNKNOWN" and i["max_cost_basis"] == "UNKNOWN"
    for c in cards:
        if c["max_cost_cad"] is None:
            assert c["max_cost_basis"] == "UNKNOWN", c["gate"]
        assert c["monthly_ceiling_cad"] != 0.0 or c.get("gate") is None or c[
            "max_cost_cad"] is not None, c["gate"]
    assert "culture_feed" not in {c["gate"] for c in cards}
    assert [g["gate"] for g in inbox["company_opened_not_owner"]] == ["culture_feed"]
    # tester_roster and physical_proof are one decision (F-197: a tester, not the owner).
    tester = [i for i in items if "tester_roster" in i["gates"]]
    assert tester and "physical_proof" in tester[0]["gates"], tester
    ok(f"fresh inbox: {len(cards)} cards -> {len(items)} decisions in "
       f"{len(packet['batches'])} batches, all seven fields present, culture_feed not asked")


def test_production_nine_merge_into_decisions():
    from brambleloop.build2 import executor

    db = _db()
    ids = _seed_production(db)
    inbox = executor.approval_inbox(db, env={})
    items = {i["id"]: i for b in inbox["batches"]["batches"] for i in b["items"]}
    assert items
    fund = items["fund_model"]
    assert {ids["model_credits"], ids["model_provider_balance"]} <= set(
        fund["owner_action_ids"]), fund
    assert "phase" in items["leave_shadow"]["requirement_keys"]
    assert "live_listings" in items["leave_shadow"]["gates"]
    assert "benchmark_challenge" in items["benchmark_purchase"]["requirement_keys"]
    assert items["listing_fees"]["max_cost_cad"] == 6.0
    assert items["etsy_kyc_payout"]["requirement_keys"] and ids["payout"] in items[
        "etsy_kyc_payout"]["owner_action_ids"]
    shown = {oid for i in items.values() for oid in i["owner_action_ids"]}
    # "Open the Etsy shop": its gate un-parks nothing, so it is never a card; in production
    # the gate is open (satisfied_but_open) and the readiness closer closes the row.
    suppressed = {oid for g in inbox["suppressed_unblocks_nothing"]
                  for oid in g["owner_action_ids"]}
    assert ids["etsy_shop"] in suppressed, inbox["suppressed_unblocks_nothing"]
    assert set(ids.values()) - {ids["etsy_shop"]} <= shown, (ids, shown)
    batch_of = {i["id"]: i["batch"] for i in items.values()}
    assert batch_of["listing_fees"] == batch_of["leave_shadow"] == "go_live"
    assert not inbox["batches"]["incomplete"], inbox["batches"]["incomplete"]
    ok(f"production's 9 rows land in {len(items)} decisions; 19/20 merged, phase+"
       f"live_listings and benchmark rows merged")


def test_unknown_producer_lands_in_other_with_unknown_cost():
    from brambleloop.build2 import executor

    db = _db()
    with db.session() as s:
        s.add(OwnerAction(requirement_key="some.new_producer", action="decide the thing",
                          reason="because only you can", max_cost_cad=0.0,
                          max_cost_basis="UNKNOWN", minutes=4,
                          consequence_of_delay="it waits", blocks="the thing"))
    inbox = executor.approval_inbox(db, env={})
    other = [b for b in inbox["batches"]["batches"] if b["id"] == "other"]
    assert other and other[0]["items"], inbox["batches"]
    item = other[0]["items"][0]
    assert item["max_cost_cad"] is None and item["max_cost_display"] == "UNKNOWN", item
    assert other[0]["max_cost_cad_total"] is None
    ok("an unlisted producer's action is batched under 'other' and its UNKNOWN cost stays "
       "UNKNOWN")


def test_existing_shop_is_not_asked_for_again():
    from brambleloop.build2 import executor
    from brambleloop.launch import readiness as R
    from brambleloop.runtime import release

    db = _db()
    gate = executor.GATE_BY_KEY["etsy_shop"]
    original = gate.check
    try:
        closed = R.assess(db, phase="shadow")
        shop = next(r for r in closed.requirements if r.key == "etsy_shop")
        assert not shop.ready and shop.owner_request is R.ETSY_ACCOUNT
        gate.check = lambda _db, _env: True
        opened = R.assess(db, phase="shadow")
    finally:
        gate.check = original
    shop = next(r for r in opened.requirements if r.key == "etsy_shop")
    payout = next(r for r in opened.requirements if r.key == "payout")
    assert shop.ready and shop.owner_request is None, shop
    assert "identity verification complete" not in shop.description
    assert not payout.ready and payout.owner_request is R.ETSY_PAYOUT_CONFIRM
    keys = [o.key for o in opened.owner_requests()]
    assert "etsy_shop" not in keys and keys.count("payout") == 1, keys
    assert release._requirement_cleared("etsy_shop", opened)
    ok("an open etsy_shop gate clears the shop ask; payout becomes a confirmation")


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
