"""v1.1 lane C: Command Center views read real state and never fake it (F-884, F-896, F-897,
F-898, F-899, F-927, F-928, F-929; §95 "disconnect an accounting source: Money changes to
UNKNOWN/stale rather than CA$0.00", "routine machine events at high volume: notification
policy suppresses noise while a real incident reaches the owner", "ask the company why a
product is blocked: source-linked current evidence, gate and next action without inventing").

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_v11_cc_views.py
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="v11_cc_views_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the command-center harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth, providers  # noqa: E402
from brambleloop.app.command_center.models import Notification  # noqa: E402
from brambleloop.core import opsauth  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, CostEntry, Incident, Job, JobStatus, Listing, OwnerAction, PatternVersion,
    Product)

OPS = "v" * 40
PASS = "owner passphrase for the views harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
Registry(main.db).seed_defaults()
DB = main.db
NOW = datetime.now(timezone.utc)


def session():
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    r = c.post("/api/cc/auth/login", json={"passphrase": PASS})
    assert r.status_code == 200, r.text
    return c, r.json()["csrf_token"]


def fresh(csrf):
    return {"X-CSRF-Token": csrf, "X-CC-Nonce": uuid.uuid4().hex,
            "X-CC-Timestamp": str(int(time.time()))}


class FakeProvider:
    """Installs a provider module under its contract path for the duration of a block."""

    def __init__(self, key, fn):
        self.mod_name, self.fn_name = providers.PROVIDERS[key]
        self.fn = fn

    def __enter__(self):
        self.prev = sys.modules.get(self.mod_name)
        mod = types.ModuleType(self.mod_name)
        setattr(mod, self.fn_name, self.fn)
        sys.modules[self.mod_name] = mod
        return self

    def __exit__(self, *exc):
        if self.prev is None:
            sys.modules.pop(self.mod_name, None)
        else:
            sys.modules[self.mod_name] = self.prev


def _money_values(node, path=""):
    """Every (path, value_cad, state) money object in a JSON tree."""
    out = []
    if isinstance(node, dict):
        if "value_cad" in node and "state" in node:
            out.append((path, node["value_cad"], node["state"], node.get("display")))
        for k, v in node.items():
            out += _money_values(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _money_values(v, f"{path}[{i}]")
    return out


def _assert_no_unknown_zero(payload):
    vals = _money_values(payload)
    assert vals, "no money values found"
    bad = [v for v in vals if v[2] not in ("MEASURED", "ESTIMATED", "MODELLED", "RECORDED")
           and (v[1] is not None or "0.00" in str(v[3]))]
    assert not bad, bad


def test_money_is_unknown_not_zero_when_the_accountant_is_absent():
    c, _ = session()
    assert not providers.available("accounting")
    m = c.get("/api/cc/money").json()
    assert m["sections"]["accounting"]["status"] == "UNKNOWN"
    assert m["sections"]["accounting"]["reason"] == "not built"
    assert m["revenue"]["value_cad"] is None and m["revenue"]["display"] in ("UNMEASURED",
                                                                             "UNKNOWN")
    assert m["profit"]["value_cad"] is None and m["profit"]["display"] == "UNKNOWN"
    assert m["source_health"]["warning"], m["source_health"]
    _assert_no_unknown_zero(m)
    h = c.get("/api/cc/home").json()
    assert h["headline"]["profit"]["display"] == "UNKNOWN"
    _assert_no_unknown_zero(h)


def test_money_is_unknown_when_the_accounting_source_disconnects():
    c, _ = session()

    def disconnected(db):
        return {"status": "UNKNOWN", "as_of": None, "basis": "unknown", "items": [],
                "sources": ["bank_feed"], "reason": "accounting source disconnected (stale)"}

    with FakeProvider("accounting", disconnected):
        m = c.get("/api/cc/money").json()
        assert m["sections"]["accounting"]["status"] == "UNKNOWN"
        assert "disconnected" in m["sections"]["accounting"]["reason"]
        assert m["status"] == "UNKNOWN" and m["profit"]["value_cad"] is None
        _assert_no_unknown_zero(m)

    def raises(db):
        raise ConnectionError("bank down")

    with FakeProvider("accounting", raises):
        m = c.get("/api/cc/money").json()
        assert m["sections"]["accounting"]["status"] == "UNKNOWN"
        assert "ConnectionError" in m["sections"]["accounting"]["reason"]
        _assert_no_unknown_zero(m)

    with FakeProvider("accounting", lambda db: {"cash": 0}):
        m = c.get("/api/cc/money").json()
        assert m["sections"]["accounting"]["reason"] == "provider returned a malformed summary"
        _assert_no_unknown_zero(m)


def test_provider_output_passes_through_with_provenance():
    c, _ = session()

    def autonomy(db):
        from sqlalchemy.orm import Session

        assert isinstance(db, Session), "contract: providers receive a SQLAlchemy Session"
        n = db.scalar(select(func.count()).select_from(Job))
        return {"status": "OK", "as_of": NOW.isoformat(), "basis": "measured",
                "items": [{"department": "growth", "jobs": n}], "sources": ["jobs"]}

    with FakeProvider("autonomy", autonomy):
        sec = c.get("/api/cc/home").json()["sections"]["autonomy"]
    assert sec["status"] == "OK" and sec["provider"] == "brambleloop.autonomy.status.summary"
    assert sec["items"] and sec["sources"] == ["jobs"]


def _seed_activity():
    with DB.session() as s:
        for i in range(3):
            s.add(Job(agent="orchestrator", job_type="etsy.shop_snapshot",
                      status=JobStatus.DONE, idempotency_key=f"done-{i}-{uuid.uuid4().hex}",
                      finished_at=NOW - timedelta(hours=1)))
        inc = Incident(severity="P1", signature="render:drift", summary="render drift seen",
                       product_slug=None)
        s.add(inc)
        s.add(OwnerAction(requirement_key="budget_review_q4", action="review the Q4 budget",
                          reason="quarterly budget needs the owner", max_cost_cad=0.0,
                          minutes=5, consequence_of_delay="budget stays at current caps"))
        s.add(AuditLog(actor="orchestrator", action="mission.created", artifact="m-1",
                       detail={"summary": "created a research mission"}))
        s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=0.42,
                        at=NOW - timedelta(hours=2)))
        s.flush()
        return inc.id


def test_home_and_morning_brief_come_from_real_database_state():
    c, csrf = session()
    inc_id = _seed_activity()
    h = c.get("/api/cc/home").json()
    hl = h["headline"]
    assert hl["autonomy"]["jobs_completed_24h"] == 3, hl
    assert hl["incidents_open"] >= 1 and hl["owner_decisions"] >= 1, hl
    assert hl["launch"]["phase"] == "shadow"
    srcs = [i["source"] for i in h["sections"]["incidents"]["items"]]
    assert f"incidents:{inc_id}" in srcs, srcs
    changes = h["sections"]["changes_since_last_view"]["items"]
    assert any(e["action"] == "mission.created" for e in changes), changes
    # After marking seen, only newer events show.
    assert c.post("/api/cc/home/seen", json={}, headers=fresh(csrf)).status_code == 200
    time.sleep(1.1)
    with DB.session() as s:
        s.add(AuditLog(actor="cfo", action="ledger.reconciled", artifact="2026-10",
                       detail={}))
    changes = c.get("/api/cc/home").json()["sections"]["changes_since_last_view"]["items"]
    actions = [e["action"] for e in changes]
    assert "ledger.reconciled" in actions and "mission.created" not in actions, actions
    b = c.get("/api/cc/brief/morning?hours=12").json()
    secs = b["sections"]
    assert secs["completed"]["completed"] == 3
    assert secs["money_spent"]["total"]["value_cad"] == 0.42
    assert secs["money_spent"]["total"]["state"] == "RECORDED"
    assert secs["decisions_needed"]["items"], secs["decisions_needed"]
    assert {"what_changed", "completed", "money_spent", "incidents", "discoveries",
            "queued_actions", "decisions_needed"} <= set(secs)


def test_approval_cards_carry_the_f885_fields():
    c, _ = session()
    box = c.get("/api/cc/approvals").json()
    cards = box["cards"]
    assert cards, box
    for card in cards:
        for k in ("proposed_action", "recommendation", "evidence", "uncertainty",
                  "expected_benefit", "downside", "max_spend_cad", "reversibility",
                  "deadline", "consequence_of_no_action", "sources", "executable"):
            assert k in card, (k, card["card_id"])
        assert card["evidence"] and card["sources"], card["card_id"]
    budget = [x for x in cards if "Q4 budget" in (x["title"] or "")]
    assert budget and budget[0]["kind"] == "OWNER-DECISION"
    one = c.get(f"/api/cc/approvals/{budget[0]['card_id']}").json()
    assert one["card_id"] == budget[0]["card_id"]


def test_notifications_suppress_routine_noise_and_surface_real_incidents():
    c, csrf = session()
    with DB.session() as s:
        for i in range(300):
            s.add(Job(agent="validator", job_type="validate", status=JobStatus.DONE,
                      idempotency_key=f"routine-{i}", finished_at=NOW))
            s.add(AuditLog(actor="validator", action="job.done", artifact=f"j{i}", detail={}))
        for i in range(40):
            s.add(Job(agent="market_radar", job_type="scan", status=JobStatus.DEAD,
                      idempotency_key=f"dead-{i}", finished_at=NOW, last_error="boom"))
        sec = Incident(severity="P1", signature="security:credential_leak_suspected",
                       summary="credential exposure suspected in a log line")
        s.add(sec)
        s.flush()
        sec_id = sec.id
    n1 = c.get("/api/cc/notifications").json()
    keys = [n["dedupe_key"] for n in n1["notifications"]]
    assert f"incident:{sec_id}" in keys, keys
    crit = [n for n in n1["notifications"] if n["dedupe_key"] == f"incident:{sec_id}"][0]
    assert crit["severity"] == "critical" and crit["category"] == "security"
    assert keys.count("dead_letters") == 1, keys
    total = len(n1["notifications"]) + len(n1["digest"])
    assert total < 30, total  # 300 routine jobs + 300 audit rows did not become notifications
    assert n1["suppressed_count"] >= 600, n1["suppressed_count"]
    # Severity-ranked: the first notification is critical.
    assert n1["notifications"][0]["severity"] == "critical"
    # Deduplicated across refreshes.
    c.post("/api/cc/notifications/refresh", json={}, headers=fresh(csrf))
    c.get("/api/cc/notifications")
    with DB.session() as s:
        dupes = s.execute(select(Notification.dedupe_key, func.count())
                          .group_by(Notification.dedupe_key)
                          .having(func.count() > 1)).all()
    assert not dupes, dupes
    # Quiet hours hold non-critical notifications for the digest; critical still surfaces.
    now_local = datetime.now(timezone.utc)
    start = (now_local - timedelta(hours=1)).strftime("%H:%M")
    end = (now_local + timedelta(hours=1)).strftime("%H:%M")
    r = c.post("/api/cc/notifications/policy",
               json={"quiet_hours": {"start": start, "end": end, "tz": "UTC"}},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text
    n2 = c.get("/api/cc/notifications").json()
    assert n2["quiet_hours_now"] is True
    assert all(n["severity"] == "critical" or n["category"] == "security"
               for n in n2["notifications"]), n2["notifications"]
    assert f"incident:{sec_id}" in [n["dedupe_key"] for n in n2["notifications"]]
    assert any(n["dedupe_key"] == "dead_letters" for n in n2["digest"])
    c.post("/api/cc/notifications/policy", json={"quiet_hours": None}, headers=fresh(csrf))
    # Ack, and resolution when the condition clears.
    r = c.post(f"/api/cc/notifications/{crit['id']}/ack", json={}, headers=fresh(csrf))
    assert r.status_code == 200
    with DB.session() as s:
        s.get(Incident, sec_id).resolved = True
    n3 = c.get("/api/cc/notifications").json()
    assert f"incident:{sec_id}" not in [n["dedupe_key"] for n in
                                        n3["notifications"] + n3["digest"]]
    assert n3["policy"]["external_channels"].startswith("GATED")


def test_security_notification_counts_attacks_not_expired_tabs():
    from brambleloop.app.command_center.models import SecurityEvent

    with DB.session() as s:
        s.query(SecurityEvent).delete()
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    for _ in range(10):
        assert anon.get("/api/cc/home").status_code == 401  # an expired tab reloading
    c, _ = session()
    keys = [n["dedupe_key"] for n in c.get("/api/cc/notifications").json()["notifications"]]
    assert not [k for k in keys if k.startswith("security_refusals")], keys
    prober = TestClient(main.app, base_url="https://testserver",
                        headers={"user-agent": "credential-prober"})
    for i in range(5):
        assert prober.post("/api/cc/auth/login", json={"passphrase": f"x{i}"}).status_code == 401
    notes = c.get("/api/cc/notifications").json()["notifications"]
    sec = [n for n in notes if n["dedupe_key"].startswith("security_refusals")]
    assert sec and sec[0]["severity"] == "critical", notes[:3]
    with DB.session() as s:
        s.query(SecurityEvent).filter(SecurityEvent.kind == "login").delete()


def test_ask_why_is_a_product_blocked_is_grounded_in_gate_records():
    c, csrf = session()
    with DB.session() as s:
        p = Product(slug="moss-stitch-throw", title="Moss Stitch Throw", status="draft")
        s.add(p)
        s.flush()
        pv = PatternVersion(product_id=p.id, version="1", cir_json={}, certified=False,
                            certificate={"findings": [{"code": "REPEAT_MISMATCH",
                                                       "severity": "error",
                                                       "message": "row 12 repeat"}]})
        s.add(pv)
        inc = Incident(severity="P1", signature="asset_truth:moss", product_slug=p.slug,
                       summary="hero image shows the wrong stitch", halts_publication=True)
        s.add(inc)
        s.add(Listing(product_slug=p.slug, version="1", title="Moss Stitch Throw",
                      description="", state="draft"))
        s.flush()
        pv_id, inc_id = pv.id, inc.id
    r = c.post("/api/cc/ask", json={"question": "Why is product moss-stitch-throw blocked?"},
               headers=fresh(csrf))
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["intent"] == "product_blocked" and a["status"] == "ANSWERED", a
    assert f"pattern_versions:{pv_id}" in a["sources"], a["sources"]
    assert f"incidents:{inc_id}" in a["sources"], a["sources"]
    assert "not certified" in a["answer"] and "REPEAT_MISMATCH" in a["answer"], a["answer"]
    assert a["next_action"], a
    assert a["facts"]
    for f in a["facts"]:
        assert f["source"], f
    # By title too.
    a2 = c.post("/api/cc/ask", json={"question": "why is the Moss Stitch Throw not published?"},
                headers=fresh(csrf)).json()
    assert a2["status"] == "ANSWERED" and f"incidents:{inc_id}" in a2["sources"], a2


def test_ask_answers_unknown_rather_than_inventing():
    c, csrf = session()
    for q in ("why is product unicorn-blanket blocked?", "what is the meaning of life?",
              "why did profit fall?"):
        a = c.post("/api/cc/ask", json={"question": q}, headers=fresh(csrf)).json()
        assert a["status"] == "UNKNOWN", (q, a)
        assert a["answer"].startswith("UNKNOWN"), (q, a["answer"])
        assert a["method"].startswith("deterministic"), a
    a = c.post("/api/cc/ask", json={"question": "what did Brambleloop do overnight?"},
               headers=fresh(csrf)).json()
    assert a["status"] == "ANSWERED" and "jobs" in a["sources"], a
    a = c.post("/api/cc/ask", json={"question": "what is blocking launch?"},
               headers=fresh(csrf)).json()
    assert a["status"] == "ANSWERED" and a["facts"], a


def test_timeline_and_drill_down_carry_provenance():
    c, _ = session()
    t = c.get("/api/cc/timeline?limit=20").json()
    assert t["events"], t
    stamps = [e["at"] for e in t["events"]]
    assert stamps == sorted(stamps, reverse=True)
    assert all(e["source"].startswith("audit_log:") for e in t["events"]
               if e["origin"] == "audit_log")
    assert t["autonomy_timeline"]["status"] == "UNKNOWN"

    def a_timeline(db, limit=50):
        return [{"at": (NOW + timedelta(minutes=5)).isoformat(), "kind": "handoff",
                 "summary": "intelligence -> design", "source": "jobs:1"}]

    with FakeProvider("timeline", a_timeline):
        t2 = c.get("/api/cc/timeline").json()
    assert t2["events"][0]["origin"] == "autonomy.status.timeline", t2["events"][:1]
    with DB.session() as s:
        job = s.scalars(select(Job).order_by(Job.id)).first()
        s.add(AuditLog(actor=job.agent, action="job.done", artifact=job.job_type,
                       job_id=job.id, detail={}))
    d = c.get(f"/api/cc/operations/drill?kind=job&id={job.id}").json()
    assert d["status"] == "OK" and d["items"][0]["id"] == job.id
    assert d["responsible_agent"] == job.agent and d["audit_history"], d
    assert d["sources"] == [f"jobs:{job.id}"]
    d = c.get("/api/cc/operations/drill?kind=job&id=999999").json()
    assert d["status"] == "UNKNOWN"
    m = c.get("/api/cc/money/drill?metric=revenue").json()
    assert m["status"] == "UNKNOWN" and m["items"] == []
    m = c.get("/api/cc/money/drill?metric=recorded_spend").json()
    assert m["status"] == "OK" and m["items"][0]["source"].startswith("cost_entries:")


def test_every_tab_answers_and_carries_status_envelopes():
    c, _ = session()
    tabs = ("/api/cc/home", "/api/cc/approvals", "/api/cc/store", "/api/cc/money",
            "/api/cc/operations", "/api/cc/autonomy", "/api/cc/learn", "/api/cc/insights",
            "/api/cc/notifications", "/api/cc/account", "/api/cc/timeline",
            "/api/cc/brief/morning", "/api/cc/emergency")
    assert len(tabs) == 13
    for path in tabs:
        r = c.get(path)
        assert r.status_code == 200, (path, r.text[:300])
        body = r.json()
        for name, sec in (body.get("sections") or {}).items():  # vacuity-ok: list-shaped tabs (approvals, timeline, notifications, emergency) have no sections
            assert sec.get("status") in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN"), (path, name)
            assert "sources" in sec and "basis" in sec, (path, name)
            if sec["status"] != "OK":
                assert sec.get("reason"), (path, name, sec)
    acct = c.get("/api/cc/account").json()
    assert acct["sessions"] and acct["owner"]["login_configured"] is True
    assert "security_events" in acct and acct["emergency"]["never_paused"]


def test_no_fixture_or_demo_data_in_production_paths():
    pkg = ROOT / "src" / "brambleloop" / "app" / "command_center"
    files = sorted(pkg.glob("*.py"))
    assert len(files) >= 8
    for f in files:
        text = f.read_text().lower()
        for word in ("fixture", "lorem", "demo_data", "sample_data", "fake_", "mock"):
            assert word not in text, (f.name, word)


if __name__ == "__main__":
    t0 = time.monotonic()
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("OK  ", name, flush=True)
        except Exception as e:  # noqa: BLE001
            fails += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:1500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
