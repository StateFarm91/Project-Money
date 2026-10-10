"""W4-B2CLOSE (2026-10-10): the company-executable gaps the Build 2 re-verification found.

A. #35/#39 sit on `rendered_pages`, whose only opening was a recorded browser.probe -- which
   etsy.com/legal (DataDome, 403) can never honestly give. The closure's own remedy is a
   person's page reading through POST /api/policy/snapshot. A current, reviewed, audited set
   of those readings now opens the gate as well; everything short of that keeps it closed.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.build2 import closure as C  # noqa: E402
from brambleloop.build2 import executor as E  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.gates import platform_policy as PP  # noqa: E402
from brambleloop.gates import policy_reader  # noqa: E402
from brambleloop.intel import browser  # noqa: E402

RESULTS: list[str] = []
LEGAL = policy_reader.external_sources()
TEXT = "A person's reading of the page, long enough to be a policy text. " * 8


def ok(name: str) -> None:
    RESULTS.append(name)
    print(f"OK {name}")


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


def _intake(db, source: str, *, text: str = TEXT, read_by: str = "owner",
            checked_on: str = "") -> dict:
    """What POST /api/policy/snapshot does: record the reading, then audit it by id."""
    res = PP.record_page_reading(db, source=source, text=text, version="v", summary="s",
                                 read_by=read_by, checked_on=checked_on)
    Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={
        k: res[k] for k in ("id", "source", "digest", "material_change", "checked_on",
                            "current", "incidents_resolved", "basis")})
    return res


def _gate(db) -> bool:
    return E.GATE_BY_KEY["rendered_pages"].open(db, {})


def test_the_legal_sources_are_the_five_the_owner_checklist_names():
    assert LEGAL == sorted(["seller_policy", "creativity_standards", "advertising_rules",
                            "shilling_and_reviews", "children_and_baby"]), LEGAL
    assert set(E.GATE_BY_KEY["rendered_pages"].requirement_ids) == {35, 39}
    ok("rendered_pages holds #35/#39; the five etsy.com/legal sources are the readings")


def test_nothing_recorded_keeps_the_gate_closed():
    db = _db()
    st = PP.page_readings_status(db)
    assert st["open"] is False and st["not_current"] == LEGAL
    assert _gate(db) is False
    ok("no reading: gate closed, all five not current")


def test_a_full_current_set_opens_the_gate_and_four_of_five_does_not():
    db = _db()
    for src in LEGAL[:-1]:
        _intake(db, src)
    assert _gate(db) is False
    assert PP.page_readings_status(db)["not_current"] == [LEGAL[-1]]
    _intake(db, LEGAL[-1])
    assert PP.page_readings_status(db)["open"] is True
    assert _gate(db) is True
    # Only the policy half opened: no browser exists, and the live storefront inspection
    # (which needs one) stays closed.
    assert browser.usable(db) is False
    from brambleloop.brand import storefront_preview

    assert storefront_preview.live_inspection(db)["gate_open"] is False
    ok("4/5 readings closed; 5/5 current readings open rendered_pages; browser half untouched")


def test_readings_go_stale_by_themselves_and_a_backdated_one_never_opens():
    db = _db()
    for src in LEGAL:
        _intake(db, src)
    later = date.today() + timedelta(days=PP.MAX_AGE_DAYS + 1)
    st = PP.page_readings_status(db, today=later)
    assert st["open"] is False and st["not_current"] == LEGAL, st
    edge = date.today() + timedelta(days=PP.MAX_AGE_DAYS)
    assert PP.page_readings_status(db, today=edge)["open"] is True

    db2 = _db()
    old = (date.today() - timedelta(days=PP.MAX_AGE_DAYS + 1)).isoformat()
    for src in LEGAL:
        _intake(db2, src, checked_on=old if src == LEGAL[0] else "")
    assert _gate(db2) is False
    assert PP.page_readings_status(db2)["sources"][LEGAL[0]]["why"].startswith("older than")
    ok("a set closes the day it passes 30 days; a backdated reading never opens it")


def test_a_reading_without_provenance_never_opens_the_gate():
    # Recorded by code rather than through the authenticated intake: no audit row.
    db = _db()
    for src in LEGAL:
        PP.record_page_reading(db, source=src, text=TEXT, read_by="owner")
    assert _gate(db) is False
    # Audited, but nobody is named as the reader.
    db = _db()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="", basis=PP.PAGE_BASIS)
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    # Audited and named, but not a page reading (a search-engine excerpt / repository basis).
    db = _db()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="owner", basis="excerpt")
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    # Dated in the future (the intake refuses this; a row written around it is not trusted).
    db = _db()
    future = (date.today() + timedelta(days=3)).isoformat()
    for src in LEGAL:
        res = PP.record_snapshot(db, src, text=TEXT, read_by="owner", basis=PP.PAGE_BASIS,
                                 checked_on=future)
        Registry(db).audit("orchestrator", PP.PAGE_READING_AUDIT, detail={"id": res["id"]})
    assert _gate(db) is False
    assert PP.page_readings_status(db)["sources"][LEGAL[0]]["why"] == "dated in the future"
    ok("un-audited, anonymous, non-page and future-dated readings all keep it closed")


def test_an_unreviewed_change_closes_it_until_reviewed():
    db = _db()
    for src in LEGAL:
        _intake(db, src)
    assert _gate(db) is True
    _intake(db, "seller_policy", text=TEXT + " Etsy changed a sentence.")
    st = PP.page_readings_status(db)
    assert st["open"] is False and st["changed_unreviewed"] == ["seller_policy"], st
    assert _gate(db) is False
    PP.review_change(db, "seller_policy", reviewed_by="owner",
                     tested="tests/test_platform_policy.py re-run against the new reading")
    assert _gate(db) is True
    ok("a material change closes the gate until review_change records reviewer and tests")


def test_the_browser_path_still_opens_it_alone():
    db = _db()
    original = browser.fetch
    try:
        browser.fetch = lambda url, **kw: {
            "url": url, "final_url": url, "status": 200,
            "bytes": browser.MIN_PROBE_BYTES + 1, "text": "x" * (browser.MIN_PROBE_BYTES + 1),
            "latency_ms": 5.0}
        browser.probe(db, env={"BRAMBLELOOP_BROWSER_URL": "https://worker.test"})
    finally:
        browser.fetch = original
    assert PP.page_readings_status(db)["open"] is False
    assert _gate(db) is True
    ok("a recorded browser.probe still opens the gate on its own (unchanged path)")


def test_the_gate_kind_and_closure_text_are_unchanged_in_kind():
    assert C.kind_of("rendered_pages") == C.EXTERNAL_BLOCKED
    assert "page_readings_status" in C.EXTERNAL_GATES["rendered_pages"]
    assert "POST /api/policy/snapshot" in E.GATE_BY_KEY["rendered_pages"].how
    ok("rendered_pages stays EXTERNAL; its texts name the human-reading path")


def test_the_owner_card_is_the_ca0_reading_not_a_browser_at_unknown_cost():
    from brambleloop.ops import owner_queue as Q

    d = Q.DECISION_BY_GATE["rendered_pages"]
    assert d["id"] == "policy_page_reading", d["id"]
    assert d["max_cost_cad"] == 0.0 and d["minutes"] == 15
    for src in LEGAL:
        assert src in d["decision"], src
    assert "/api/policy/snapshot" in d["decision"]
    assert not [x for x in Q.DECISIONS if x["id"] == "browser_worker"]
    packet = json.loads((ROOT / "research/final_build/w4/OWNER_ACTIONS.json").read_text())
    items = {i["id"]: i for b in packet["batches"] for i in b["items"]}
    assert "browser_worker" not in items
    card = items["policy_page_reading"]
    assert card["max_cost_cad"] == 0.0 and card["max_cost_display"] == "CA$0.00", card
    assert card["gates"] == ["rendered_pages"]
    ok("OWNER_ACTIONS asks for the CA$0 15-minute reading; the browser-worker card is gone")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{len(RESULTS)} passing, {fails} failing")
    sys.exit(1 if fails else 0)
