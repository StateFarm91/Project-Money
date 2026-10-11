"""W4-CCGAP: Command Center cards that read healthier or more certain than the evidence.

Found by exercising the real app at c131f07 (SQLite, shadow, one Launch-0 product run):

* SLO card: the provider said OK "every judged objective is met" with 5 of 7 objectives
  UNKNOWN, including P1 scheduler_freshness. OK is now shown only when every objective was
  judged; otherwise DEGRADED naming the unjudged ones (CC_VERIFY FU-5).
* Autonomy & Learn agents card: agents that have never run read SLEEPING (Company said
  UNKNOWN for the same agents), a wake 12 min past still read SLEEPING, and the provider's
  `next_work` (queued next actions) was never shown. Never-run agents are now UNKNOWN, an
  overdue wake is flagged, and the card shows the next queued work (CC_VERIFY FU-3).
* "Your actions" (13) vs "Decisions for you" (14) vs Approvals: the card now says how its
  count relates to the inbox total (CC_VERIFY FU-4).
* Claude development lanes are labelled as such, never as company agents (CC_VERIFY FU-9).
* Phone: Approvals overflowed a 390px viewport (413px) on a long path in a proposal; card
  text now wraps long tokens.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_ccgap_views.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccgap_views_")
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js" / "views"

NOW = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc)


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/v{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def _slo(key, state, sev="P2"):
    return {"kind": "slo", "key": key, "state": state, "breach_severity": sev}


def test_slo_ok_with_unjudged_objectives_is_degraded_and_names_them():
    from brambleloop.app.command_center import tabs

    env = {"status": "OK", "as_of": "x", "basis": "measured", "sources": [], "items": [
        _slo("command_center_availability", "UNKNOWN"),
        _slo("scheduler_freshness", "UNKNOWN", "P1"),
        _slo("queue_latency", "MET"),
        {"kind": "scheduler_liveness", "stale": False}],
        "reason": "every judged objective is met (UNKNOWN ones are listed as such)"}
    out = tabs.slo_card(env)
    assert out["status"] == "DEGRADED" and out["provider_status"] == "OK", out
    assert "only 1 of 3 objectives have evidence" in out["reason"], out["reason"]
    assert "P1 with no evidence: scheduler_freshness" in out["reason"], out["reason"]
    assert out["unjudged"] == ["command_center_availability", "scheduler_freshness"]
    assert out["items"] == env["items"]  # nothing dropped or rewritten


def test_slo_all_judged_stays_ok_and_other_statuses_untouched():
    from brambleloop.app.command_center import tabs

    ok = {"status": "OK", "items": [_slo("a", "MET"), _slo("b", "AT_RISK")]}
    assert tabs.slo_card(ok) is ok
    for st in ("UNKNOWN", "DEGRADED", "BLOCKED"):
        env = {"status": st, "items": [_slo("a", "UNKNOWN")]}
        assert tabs.slo_card(env) is env


def _agent(name, state="sleeping", **kw):
    return {"agent": name, "department": "executive", "state": state, "last_run": None,
            "current_job": None, "doing_now": None, "next_wake": None, "next_work": [], **kw}


def test_never_run_agent_is_unknown_not_sleeping_and_counts_recomputed():
    from brambleloop.app.command_center import tabs
    from brambleloop.queue.durable import JobQueue

    db = _db()
    JobQueue(db).enqueue("coo", "ops.health", {}, idempotency_key="ccgap-1")
    env = {"status": "OK", "as_of": "x", "basis": "measured", "sources": ["jobs"],
           "counts": {"sleeping": 3}, "reason": "provider gave no reason",
           "items": [_agent("coo", next_wake=(NOW + timedelta(minutes=5)).isoformat()),
                     _agent("laura", next_wake=(NOW + timedelta(minutes=5)).isoformat()),
                     _agent("cfo", state="blocked")]}
    out = tabs.agents_card(db, env, now=NOW)
    by = {i["agent"]: i for i in out["items"]}
    assert by["coo"]["state"] == "sleeping", by["coo"]  # it has a recorded job
    assert by["laura"]["state"] == "UNKNOWN" and by["laura"]["provider_state"] == "sleeping"
    assert "not known to be sleeping" in by["laura"]["why"]
    assert by["cfo"]["state"] == "blocked"  # only "sleeping" is ever re-read
    assert out["counts"] == {"sleeping": 1, "UNKNOWN": 1, "blocked": 1}, out["counts"]
    assert out["status"] == "DEGRADED" and "1 agent(s) have no recorded job" in out["reason"]
    assert "provider gave no reason" not in out["reason"]


def test_overdue_wake_is_flagged_and_all_unknown_is_unknown():
    from brambleloop.app.command_center import tabs

    db = _db()
    env = {"status": "OK", "items": [
        _agent("orchestrator", next_wake=(NOW - timedelta(minutes=40)).isoformat(),
               next_work=[{"job_type": "model.probe"}])]}
    out = tabs.agents_card(db, env, now=NOW)
    it = out["items"][0]
    assert it["overdue_wake_minutes"] == 40 and "40 min ago" in it["why"], it
    assert it["state"] == "UNKNOWN" and out["status"] == "UNKNOWN", out
    # a wake inside the grace window is not overdue
    env2 = {"status": "OK", "items": [
        _agent("x", next_wake=(NOW - timedelta(minutes=5)).isoformat())]}
    assert "overdue_wake_minutes" not in tabs.agents_card(db, env2, now=NOW)["items"][0]
    # an unreadable / empty provider envelope passes through unchanged
    for e in ({"status": "UNKNOWN", "items": []}, None, {"status": "OK"}):
        assert tabs.agents_card(db, e, now=NOW) is e


def test_owner_action_count_reconciles_with_the_inbox():
    from brambleloop.app.command_center import tabs

    owner = {"status": "BLOCKED", "open_actions": 13, "reason": "13 owner decisions open",
             "items": [{}] * 13}
    box = {"open": 14, "cards": [{"card_id": f"gate:{i}"} for i in range(13)]
           + [{"card_id": "publication:hexagon-coaster-set@1.2.0"}]}
    out = tabs.reconcile_owner_actions(owner, box)
    assert out["reason"] == ("13 gate/owner-action decision(s) + 1 publication approval(s) = "
                             "14 open on Approvals"), out["reason"]
    assert out["inbox_open"] == 14 and out["publication_open"] == 1
    same = tabs.reconcile_owner_actions({**owner, "open_actions": 14}, box)
    assert same["reason"] == "13 owner decisions open"  # equal counts: original wording kept
    unk = {"status": "UNKNOWN", "open": None, "cards": []}
    assert tabs.reconcile_owner_actions(owner, unk) is owner  # unknown inbox: no invented sum


def test_tabs_wire_the_adapters():
    src = (ROOT / "src/brambleloop/app/command_center/tabs.py").read_text()
    assert '"slo": slo_card(providers.call("slo", db))' in src
    assert '"agents": agents_card(db, providers.call("agents", db))' in src
    assert "reconcile_owner_actions(readers.owner_actions_summary(db), box)" in src
    comp = (ROOT / "src/brambleloop/app/command_center/company.py").read_text()
    assert "tabs.reconcile_owner_actions(readers.owner_actions_summary(db), box)" in comp


def test_pwa_shows_agent_why_next_work_and_labels_dev_lanes():
    learn = (STATIC / "learn.js").read_text()
    assert 'fact("Next work", nextWorkText(it.next_work))' in learn
    assert "it.why ? h(\"p\", { class: \"callout callout-warn\" }, it.why)" in learn
    ops = (STATIC / "operations.js").read_text()
    assert '["agents", "Agent registry (configuration, not activity)"]' in ops
    company = (STATIC / "company.js").read_text()
    assert "Claude dev lanes running (board)" in company and '"Lanes running"' not in company
    completion = (STATIC / "completion.js").read_text()
    assert "Claude development lanes" in completion and "not company agents" in completion


def test_card_text_wraps_long_tokens_on_a_phone():
    """Approvals measured 413px wide on a 390px viewport: a repo path in a proposal."""
    import re

    css = (ROOT / "src/brambleloop/app/command_center/static/css/app.css").read_text()
    rules = re.findall(r"\.card\s*\{([^}]*)\}", css)
    assert any(re.search(r"overflow-wrap:\s*(break-word|anywhere)", r) for r in rules), rules
    # a long token in a flex card title must not push the status pill off a 390px screen
    assert re.search(r"\.card-head > :first-child\s*\{\s*min-width:\s*0", css)
    assert re.search(r"\.card-title\s*\{[^}]*overflow-wrap:\s*anywhere", css)


def test_data_cards_carry_a_timestamp_element_or_unknown():
    """FU-6: the cards CC_VERIFY / CCGAP listed without a timestamp now render `freshness()`
    (a <time> element, "as of: unknown" when the source has none), never a bare phrase."""
    want = {
        "money.js": ['card({ title: "Headline"', 'card({ title: "Period" }, h("p", { class: "card-meta" }, freshness(',
                     '"Order source last read: ", freshness(sh.last_read_at || null)'],
        "home.js": ['freshness((changes && changes.as_of) || null'],
        "approvals.js": ['"Inbox read: ", freshness(c.as_of || readAt || null)',
                         "readAt: data.generated_at || null", "freshness(env.as_of || null)"],
        "notifications.js": ['"Last seen: ", freshness(n.last_seen_at || n.first_seen_at || null)'],
        "laura.js": ["freshness(ov.generated_at || ov.as_of || null)", "freshness(t.at || null)"],
        "account.js": ["sessionsCard(sess, rerender, data.generated_at || null)"],
        "emergency.js": ["freshness(d.as_of || null)"],
        "completion.js": ['card({ title: "Claude development lanes" }, h("p", { class: "card-meta" }, freshness('],
        "ask.js": ["freshness(a.answered_at || null)"],
    }
    for name, needles in want.items():
        src = (STATIC / name).read_text()
        for n in needles:
            assert n in src, (name, n)
    money = (STATIC / "money.js").read_text()
    i = money.index('card({ title: "Headline"')
    assert "freshness(data.generated_at" in money[i:i + 300]
    assert (STATIC / "emergency.js").read_text().count("freshness(d.as_of || null)") == 3


def test_emergency_status_and_ask_answers_are_stamped():
    from brambleloop.app.command_center import ask, emergency

    db = _db()
    st = emergency.status(db)
    assert datetime.fromisoformat(st["as_of"]).tzinfo is not None, st.get("as_of")
    out = ask._result("q", "x", [], "nothing")
    assert out["status"] == "UNKNOWN" and datetime.fromisoformat(out["answered_at"]).tzinfo


if __name__ == "__main__":
    import time

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        t0 = time.time()
        try:
            t()
            print(f"OK   {t.__name__} {time.time() - t0:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__} {type(exc).__name__} {str(exc)[:500]}")
    print(f"{len(tests) - failed}/{len(tests)} passing")
    sys.exit(1 if failed else 0)
