"""Wave-3 K7: owner queue lifecycle, packets, inventories, tester path, empty guard.

F-180 F-870 F-173 F-174 F-197 F-204 F-623. Each test drives the real consumer
(`build2.executor.approval_inbox`, the Command Center approvals inbox/defer action, the
`ops.truth` provider) rather than asserting that a helper exists.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select  # noqa: E402

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue as Q  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
RESULTS: list[str] = []


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _add(db, key, **kw):
    with db.session() as s:
        row = OwnerAction(requirement_key=key, action=kw.pop("action", f"do {key}"),
                          reason=kw.pop("reason", "because"), **kw)
        s.add(row)
        s.flush()
        return row.id


def ok(name):
    RESULTS.append(name)
    print(f"OK {name}")


def test_lifecycle_states_and_history():
    db = _db()
    ids = [_add(db, f"k{i}") for i in range(6)]
    with db.session() as s:
        rows = {r.id: r for r in s.scalars(select(OwnerAction))}
        assert rows, "rows must exist"
        Q.transition(s, rows[ids[0]], Q.SATISFIED, "the evidence arrived", now=NOW)
        Q.transition(s, rows[ids[1]], Q.SUPERSEDED, "replaced by k9", now=NOW)
        Q.transition(s, rows[ids[2]], Q.WITHDRAWN, "no longer needed", now=NOW)
        Q.transition(s, rows[ids[3]], Q.PARKED, "owner deferred", now=NOW)
        rows[ids[4]].expires_at = NOW - timedelta(minutes=1)
    out = Q.sweep(db, now=NOW)
    assert out["expired"] == [ids[4]], out
    h = Q.history(db)
    assert h["by_state"][Q.SATISFIED] == 1 and h["by_state"][Q.SUPERSEDED] == 1
    assert h["by_state"][Q.WITHDRAWN] == 1 and h["by_state"][Q.PARKED] == 1
    assert h["by_state"][Q.EXPIRED] == 1 and h["by_state"][Q.OPEN] == 1, h["by_state"]
    # History is kept: every row still exists, with when and why.
    assert len(h["rows"]) == 6
    sat = [r for r in h["rows"] if r["state"] == Q.SATISFIED]
    assert sat and sat[0]["state_at"] and sat[0]["state_reason"] == "the evidence arrived"
    with db.session() as s:
        moves = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "owner_action.lifecycle")))
    assert len(moves) == 5, len(moves)
    ok("F-180 explicit states with timestamps/reasons; history kept; expiry sweep")


def test_satisfied_leaves_active_queue_parked_listed_apart():
    from brambleloop.build2 import executor

    db = _db()
    a = _add(db, "standalone_decision_a", max_cost_cad=0.0, minutes=5,
             consequence_of_delay="later", why_software_cannot="only the owner may rule")
    b = _add(db, "standalone_decision_b")
    c = _add(db, "standalone_decision_c")
    inbox = executor.approval_inbox(db, env={})
    keys = {x["requirement_key"] for x in inbox["cards"]}
    assert {"standalone_decision_a", "standalone_decision_b",
            "standalone_decision_c"} <= keys, keys
    with db.session() as s:
        Q.transition(s, s.get(OwnerAction, b), Q.SATISFIED, "done", now=NOW)
        Q.transition(s, s.get(OwnerAction, c), Q.PARKED, "later", now=NOW)
    inbox = executor.approval_inbox(db, env={})
    keys = {x["requirement_key"] for x in inbox["cards"]}
    assert "standalone_decision_b" not in keys and "standalone_decision_c" not in keys, keys
    assert [p["owner_action_id"] for p in inbox["parked_owner_actions"]] == [c]
    card = next(x for x in inbox["cards"] if x["owner_action_id"] == a)
    assert card["why_software_cannot"] == "only the owner may rule"
    assert card["rank"] >= 1 and card["urgency"] and card["state"] == Q.OPEN
    ok("F-180 satisfied leaves the one queue; parked listed apart; F-623 rank/urgency")


def test_legacy_done_flag_is_closed_unclassified_not_satisfied():
    db = _db()
    i = _add(db, "legacy")
    with db.session() as s:
        s.get(OwnerAction, i).done = True     # a producer that names no state
    with db.session() as s:
        row = s.get(OwnerAction, i)
        assert Q.effective_state(row) == Q.CLOSED_UNCLASSIFIED, row.state
        assert row.state_at is not None and "without naming" in row.state_reason
    ok("F-180 a bare done flag is closed_unclassified, never credited as satisfied")


def test_refusals():
    db = _db()
    i = _add(db, "r")
    with db.session() as s:
        row = s.get(OwnerAction, i)
        for bad in (("nonsense", "x"), (Q.SATISFIED, "  "), (Q.CLOSED_UNCLASSIFIED, "x")):
            try:
                Q.transition(s, row, *bad)
            except Q.LifecycleRefused:
                continue
            raise AssertionError(f"accepted {bad}")
    ok("F-180 a lifecycle move needs a known state and a reason")


def test_packets_and_gate_inventory():
    from brambleloop.build2 import executor

    db = _db()
    inbox = executor.approval_inbox(db, env={})
    cards = inbox["cards"]
    assert cards, "a fresh database has closed owner gates, so cards exist"
    for c in cards:
        assert "why_software_cannot" in c and "packet_missing" in c, c
    gated = [c for c in cards if c["gate"] in Q.GATE_PACKETS]
    assert gated, [c["gate"] for c in cards]
    for c in gated:
        assert c["why_software_cannot"], c["gate"]
        assert c["requirement_kind"] in Q.REQUIREMENT_KINDS, c
    inv = Q.inventory(db, env={})
    assert inv["count"] == len(cards) and inv["items"]
    for it in inv["items"]:
        for f in ("capability", "max_cost_cad", "minutes", "consequence_of_waiting",
                  "requirement_kind", "why_software_cannot"):
            assert f in it, f
    assert "final_master_gates" in inv
    ok(f"F-870/F-173 every card carries a packet; inventory of {inv['count']} gates")


def test_physical_proof_offers_tester_route():
    from brambleloop.build2 import executor

    db = _db()
    cards = executor.approval_inbox(db, env={})["cards"]
    phys = [c for c in cards if c["gate"] == "physical_proof"]
    if not phys:
        # The gate may un-park nothing on this registry; the route is still on the module.
        card = Q.enrich_cards(db, [{"gate": "physical_proof", "kind": "OWNER-GATED",
                                    "action": "grant", "steps": "grant", "max_cost_cad": 0.0,
                                    "minutes": 10, "unblocks_count": 1}])[0]
    else:
        card = phys[0]
    route = card["tester_route"]
    assert route["asks_owner_to_crochet"] is False
    assert "tester" in route["normal_path"] and route["status_path"].startswith("/api/cc/")
    assert route["tester_status"]["status"] in ("OK", "NOT-YET-OBSERVED", "UNKNOWN")
    assert "crochet" in card["action"] and "not being asked" in card["action"]
    ok("F-197 physical proof routes to an independent tester and links roster status")


def test_empty_queue_proves_nothing_without_fresh_assessment():
    db = _db()
    g = Q.empty_guard(db, [], gates_read_live=True, now=NOW)
    assert g["empty"] and not g["proven_empty"] and g["state"] == "UNPROVEN-EMPTY", g
    assert g["closes_anything"] is False
    with db.session() as s:
        s.add(AuditLog(actor="worker", action="launch.assessed", artifact="launch",
                       at=NOW - timedelta(hours=1), detail={"ready": False}))
    g = Q.empty_guard(db, [], gates_read_live=True, now=NOW)
    assert g["proven_empty"] and g["state"] == "PROVEN-EMPTY", g
    g = Q.empty_guard(db, [], gates_read_live=False, now=NOW)
    assert not g["proven_empty"]
    with db.session() as s:
        s.add(AuditLog(actor="worker", action="launch.assessed", artifact="launch",
                       at=NOW - timedelta(minutes=5),
                       detail={"owner_requests_withheld_until_package_ready": ["etsy_shop"]}))
    g = Q.empty_guard(db, [], gates_read_live=True, now=NOW)
    assert not g["proven_empty"] and g["withheld"] == ["etsy_shop"], g
    stale = Q.empty_guard(db, [], gates_read_live=True, now=NOW + timedelta(days=3))
    assert not stale["proven_empty"]
    ok("F-204 empty queue is PROVEN-EMPTY only with a fresh assessment and live gates")


def test_inbox_and_cc_carry_empty_state_and_defer_parks():
    from brambleloop.app.command_center import approvals

    db = _db()
    i = _add(db, "standalone_to_defer")
    box = approvals.inbox(db)
    assert box["empty_state"] and box["empty_state"]["state"] in (
        "NOT-EMPTY", "UNPROVEN-EMPTY", "PROVEN-EMPTY")
    out = approvals.execute(db, "owner_action.defer",
                            {"owner_action_id": i, "note": "after launch",
                             "request_id": "k7-defer-1", "reason": "after launch"},
                            actor="owner:cc:test")
    assert out["result"]["state"] == Q.PARKED, out
    with db.session() as s:
        assert Q.effective_state(s.get(OwnerAction, i)) == Q.PARKED
    box = approvals.inbox(db)
    assert i in [p["owner_action_id"] for p in box["parked_owner_actions"]]
    ok("F-180 Command Center defer parks the action (active queue -> parked, audited)")


def test_data_gate_inventory_and_false_completion_guard():
    db = _db()
    dg = Q.data_gates(db, env={})
    assert dg["final_master_data_gated"], "the Final Master snapshot has data-gated rows"
    assert dg["customers_gate_open"] is False
    assert dg["false_completion"] == [] and dg["status"] == "OK", dg["false_completion"]
    # The guard itself: a data-gated row that claims COMPLETE before customers exist.
    from brambleloop.build2 import final_master

    snap = final_master.load()
    row = next(r for r in snap["rows"] if (r.get("gate") or {}).get("kind") == "data")
    fake = dict(row, coverage="FULL", maturity="INTEGRATED", defect=None, has_producer=True,
                has_consumer=True, launch_class="LAUNCH-CRITICAL")
    original = final_master.load
    final_master.load = lambda path=None: {"rows": [fake]}
    try:
        dg2 = Q.data_gates(db, env={})
    finally:
        final_master.load = original
    assert dg2["status"] == "BLOCKED" and dg2["false_completion"], dg2
    ok(f"F-174 {len(dg['final_master_data_gated'])} data-gated rows listed; "
       f"pre-launch COMPLETE refused")


def test_spend_gate_without_stated_cost_is_not_free():
    from brambleloop.build2 import executor

    db = _db()
    cards = executor.approval_inbox(db, env={})["cards"]
    spend = [c for c in cards if c.get("requirement_kind") == "spend"]
    assert spend, [c["gate"] for c in cards]
    unstated = [c for c in spend if not c["max_cost_cad"]]
    assert unstated, "a fresh database states no ceiling for some spend gate"
    for c in unstated:
        assert c["max_cost_basis"] == "UNKNOWN" and not c["packet_complete"], c["gate"]
        assert "free" not in c["urgency"], c["urgency"]
    ok(f"F-870 {len(unstated)} spend gate(s) with no stated ceiling read UNKNOWN, not free")


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
