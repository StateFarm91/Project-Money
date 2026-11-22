"""APPROVE-FIX: the owner's "Approve all" press actually approves, and covers every row the owner
can approve in-app, through the real `/api/cc/*` routes with a real owner session (passphrase +
TOTP login, CSRF + nonce, a fresh TOTP step-up).

Root cause (production http log, 2026-11-22 00:19 / 00:22 UTC): the preview took 122-166 s and
the press re-ran the whole preview before writing; both presses were closed by the browser
(HTTP 499) before any answer, so nothing was committed and nothing was shown. The press now
sends the previewed items, re-judges only those rows, writes each in its own savepoint and
stores its outcome, which the next preview shows (`last_press`).

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_approve_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_approve_all_v2 as V  # noqa: E402 - the same sandbox, session and seed helpers

from sqlalchemy import delete, select  # noqa: E402

from brambleloop.app.command_center import approve_everything as AE  # noqa: E402
from brambleloop.core.models import AuditLog, OwnerAction  # noqa: E402
from brambleloop.ops import owner_queue  # noqa: E402

DB = V.DB


def press_items(c, csrf, pv, items=None, confirm=True):
    return V.post(c, csrf, "/api/cc/approve-everything",
                  {"expected_digest": pv["digest"], "items": pv["items"] if items is None
                   else items, "confirm": confirm})


def preview0(c):
    r = c.get("/api/cc/approve-everything?cards=0")
    assert r.status_code == 200, r.text
    return r.json()


def inbox_owner_ids(c) -> set[int]:
    r = c.get("/api/cc/approvals")
    assert r.status_code == 200, r.text
    return {int(str(x["card_id"]).split(":", 1)[1]) for x in r.json()["cards"]
            if str(x.get("card_id") or "").startswith("owner_action:")}


def seed_big(n_unclassified=150, n_routine=20, n_child=3) -> dict:
    with DB.session() as s:
        s.execute(delete(OwnerAction))
        ids = {"unclassified": [], "routine": [], "child": []}
        for i in range(n_unclassified):
            r = OwnerAction(requirement_key=f"ops.followup.item{i}", action=f"follow up {i}",
                            reason="r", max_cost_cad=0.0, max_cost_basis="stated")
            s.add(r)
            s.flush()
            ids["unclassified"].append(r.id)
        for i in range(n_routine):
            r = OwnerAction(requirement_key=f"listing_package:p{i}@1:abc", action=f"pkg {i}",
                            reason="r", max_cost_cad=0.0, max_cost_basis="stated")
            s.add(r)
            s.flush()
            ids["routine"].append(r.id)
        for i in range(n_child):
            r = OwnerAction(requirement_key=f"childrens-decision:toy{i}", action=f"toy {i}",
                            reason="r", max_cost_cad=0.0, max_cost_basis="stated")
            s.add(r)
            s.flush()
            ids["child"].append(r.id)
    return ids


# ---------------------------------------------------------------------------------------------


def test_press_approves_in_the_database_and_the_rerender_no_longer_shows_them():
    ids = V.seed()
    c, csrf = V.session()
    with V.World():
        pv = preview0(c)
        assert pv["items"] and len(pv["items"]) == pv["count"], pv["count"]
        acted_rows = [i["id"] for i in pv["acted"] if "id" in i]
        assert set(acted_rows) <= inbox_owner_ids(c)          # shown before
        V.step_up(c, csrf)
        r = press_items(c, csrf, pv)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["failed_count"] == 0, out["failed"]
        assert out["approved_count"] == pv["count"], out
        st = V.states()
        for rid in acted_rows:                               # approved in the DATABASE
            assert st[rid] in owner_queue.CLOSED_STATES, (rid, st[rid])
        # ... and gone from the pending list on re-render, with the outcome shown.
        again = preview0(c)
        assert not set(acted_rows) & {i.get("id") for i in again["acted"]}
        assert not set(acted_rows) & inbox_owner_ids(c)
        lp = again["last_press"]
        assert lp["approved_count"] == pv["count"] and lp["failed_count"] == 0, lp
        # What stays is listed, each with a reason, and the counts add up.
        assert again["kept_count"] == len(again["kept"]) and all(k["reason"]
                                                                 for k in again["kept"])
    # Child safety and physical attestation never moved.
    for key in ("childrens-decision:baby-rattle", "portfolio.rework:baby-safety-rattle",
                "physical_size_conflict:moss-throw@1"):
        assert st[ids[key]] == owner_queue.OPEN, key


def test_a_queue_of_more_than_100_items_is_approved_in_one_press():
    ids = seed_big()
    c, csrf = V.session()
    with V.World(pub_cards=[], act_cards=[]):
        pv = preview0(c)
        assert pv["count"] == 170, (pv["count"], pv["by_bucket"])
        assert pv["by_bucket"][AE.OWNER_APPROVED] == 150, pv["by_bucket"]
        V.step_up(c, csrf)
        r = press_items(c, csrf, pv)
        assert r.status_code == 200, r.text
        assert r.json()["approved_count"] == 170, r.json()
        again = preview0(c)
    st = V.states()
    assert all(st[i] in owner_queue.CLOSED_STATES for i in ids["unclassified"] + ids["routine"])
    assert all(st[i] == owner_queue.OPEN for i in ids["child"])
    assert again["count"] == 0 and again["kept_count"] == 3, (again["count"], again["kept"])
    assert all(k["bucket"] == AE.NEVER_CHILD for k in again["kept"])
    # Recorded as owner-approved via step-up -- never as an attestation.
    with DB.session() as s:
        rows = list(s.scalars(select(AuditLog).where(
            AuditLog.action == AE.ROW_AUDIT_ACTION)))
    mine = [dict(x.detail or {}) for x in rows
            if (x.detail or {}).get("bucket") == AE.OWNER_APPROVED]
    assert len(mine) >= 150 and all(d.get("owner_approved_via_step_up") and d.get("step_up")
                                    for d in mine)
    assert all(a.actor.startswith("owner:") for a in rows)


def test_one_failing_row_is_shown_and_never_undoes_the_others():
    from brambleloop.improve import cells

    ids = V.seed()
    c, csrf = V.session()

    def boom(*_a, **_k):
        raise RuntimeError("improvement door refused for the test")

    with V.World(), patch.object(cells, "record_owner_approval", boom):
        pv = preview0(c)
        V.step_up(c, csrf)
        r = press_items(c, csrf, pv)
        assert r.status_code == 200, r.text
        out = r.json()
    assert out["failed_count"] == 1 and "refused for the test" in out["failed"][0]["reason"]
    assert out["approved_count"] == pv["count"] - 1
    st = V.states()
    assert st[ids["improve.upgrade:{imp}"]] == owner_queue.OPEN
    assert st[ids["something.nobody.named"]] == owner_queue.SATISFIED
    assert st[ids["benchmark_refresh:granny-square"]] == owner_queue.SATISFIED


def test_nothing_the_owner_did_not_preview_is_ever_approved():
    ids = V.seed()
    c, csrf = V.session()
    with V.World():
        pv = preview0(c)
        V.step_up(c, csrf)
        child = ids["childrens-decision:baby-rattle"]
        forged = [f"{AE.OWNER_APPROVED}|{child}|satisfied||",
                  f"{AE.PHYSICAL_DIRECTIVE}|{ids['physical_size_conflict:moss-throw@1']}"
                  f"|withdrawn||"]
        r = press_items(c, csrf, pv, items=forged)
        assert r.status_code == 200, r.text
        assert r.json()["approved_count"] == 0 and r.json()["failed_count"] == 2
        V.step_up(c, csrf)                       # each press spends its step-up
        r = press_items(c, csrf, pv, items=["not|a|real"])
        assert r.status_code == 409 and r.json()["code"] == "REFUSED_BY_AUTHORITY", r.text
        V.step_up(c, csrf)
        r = press_items(c, csrf, pv, confirm=False)
        assert r.status_code == 409, r.text
    st = V.states()
    assert st[ids["childrens-decision:baby-rattle"]] == owner_queue.OPEN
    assert st[ids["physical_size_conflict:moss-throw@1"]] == owner_queue.OPEN


def test_the_press_still_needs_a_fresh_step_up():
    V.seed()
    c, csrf = V.session()
    with V.World():
        pv = preview0(c)
        V.expire_stepup(c)
        before = V.states()
        r = press_items(c, csrf, pv)
        assert r.status_code == 403 and r.json()["code"] == "STEP_UP_REQUIRED", r.text
        assert V.states() == before


def test_spend_still_obeys_the_company_cap_at_the_write():
    ids = V.seed()
    c, csrf = V.session()
    with V.World():
        pv = preview0(c)
        V.step_up(c, csrf)
        # Month-to-date spend rose between the preview and the press: headroom CA$1 now.
        with patch.object(AE, "_spent_cad", lambda db, now: 99.0):
            r = press_items(c, csrf, pv)
        assert r.status_code == 200, r.text
        out = r.json()
    st = V.states()
    assert st[ids["benchmark_refresh:granny-square"]] == owner_queue.OPEN      # CA$3 > CA$1
    assert st[ids["knowledge_gap:amigurumi-eyes"]] == owner_queue.OPEN         # CA$2 > CA$1
    assert st[ids["benchmark_challenge"]] == owner_queue.OPEN                  # over the cap
    assert {f["requirement_key"] for f in out["failed"]} >= {
        "benchmark_refresh:granny-square", "knowledge_gap:amigurumi-eyes"}, out["failed"]
    assert st[ids["something.nobody.named"]] == owner_queue.SATISFIED


def test_choice_and_decision_read_rows_stay_on_their_own_card():
    rows = {k: (AE.OWN_CARD, 0.0, "stated") for k in (
        "decision.api_vision_equivalence", "acceptance_ruling", "phase",
        "correction_notice:moss-throw")}
    V.seed(rows)
    c, _csrf = V.session()
    with V.World(pub_cards=[], act_cards=[]):
        pv = preview0(c)
    assert pv["count"] == 0, pv["acted"]
    assert all(k["bucket"] != AE.OWNER_APPROVED for k in pv["kept"])
    assert "timings_ms" in pv and "total_ms" in pv["timings_ms"]


def test_the_ui_sends_the_items_and_keeps_the_outcome_on_the_page():
    js = (V.ROOT / "src/brambleloop/app/command_center/static/js/views/_mission.js").read_text()
    assert "api.approveEverything(p.digest, p.items)" in js
    assert "Needs your action elsewhere" in js and "Approved ${ok}" in js
    assert "onError" in js and "Keep this page open" in js
    api = (V.ROOT / "src/brambleloop/app/command_center/static/js/api.js").read_text()
    assert "items: items || []" in api and "?cards=0" in api


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
