"""Certification J: every number the dashboard and its endpoints serve, against the database.

A temp-file database is seeded with known rows -- jobs in every state, incidents open and
resolved (with and without evidence), owner actions open and done, CostEntry spend this
month and last, a LedgerEntry revenue row, certified and uncertified PatternVersions -- and
each endpoint is fetched through FastAPI's TestClient. Every figure is compared with an
independent SQL count written here, never with another endpoint.

The TestClient is used without its context manager so the application's startup hook (boot
jobs, the embedded worker) never runs.

Run: cd brambleloop && $PY tests/test_cert_dashboard.py
"""
from __future__ import annotations

import json
import os
import re
import socket
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="cert_dashboard_")
DB_FILE = os.path.join(_TMP, "dash.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the certification harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main  # noqa: E402
from brambleloop.core.models import (CostEntry, Incident, Job, JobStatus, LedgerEntry,  # noqa: E402
                                     OwnerAction, PatternVersion, Product, utcnow)

REQS = json.loads((ROOT / "src/brambleloop/build2/requirements.json").read_text())
_SEEDED: dict = {}


def seeded() -> TestClient:
    if _SEEDED:
        return _SEEDED["client"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    now = utcnow()
    with main.db.session() as s:
        # jobs in every state
        def job(status, jt="ops.heartbeat", agent="orchestrator", err=None, **kw):
            s.add(Job(agent=agent, job_type=jt, inputs={}, status=status, last_error=err,
                      idempotency_key=f"seed:{jt}:{status.value}:{len(_SEEDED.setdefault('n', []))}",
                      **kw))
            _SEEDED["n"].append(1)

        for _ in range(3):
            job(JobStatus.PENDING)
        job(JobStatus.RUNNING, leased_by="w", lease_expires_at=now + timedelta(minutes=5))
        for _ in range(4):
            job(JobStatus.DONE)
        for _ in range(2):
            job(JobStatus.FAILED, err="TransientError: later")
        job(JobStatus.DEAD, jt="store.publish", agent="store_operator",
            err="capability not enabled: store.publish is a production capability; the "
                "system is in SHADOW mode")
        job(JobStatus.DEAD, err="RuntimeError: a real defect")
        job(JobStatus.CANCELLED)
        # products and versions
        for i, certified in enumerate((True, True, False)):
            p = Product(slug=f"seed-product-{i}", title=f"Seed {i}", status="certified")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                                 certified=certified, release_hash="a" * 64))
        s.add(Product(slug="seed-product-bare", title="Bare"))
        # incidents
        s.add(Incident(signature="seed.open:one", severity="P1", summary="open 1"))
        s.add(Incident(signature="seed.open:two", severity="P2", summary="open 2"))
        s.add(Incident(signature="seed.closed:recent", resolved=True,
                       detail={"resolved_at": (now - timedelta(hours=1)).isoformat(),
                               "resolution": "condition cleared"}))
        s.add(Incident(signature="seed.closed:old", resolved=True,
                       detail={"resolved_at": (now - timedelta(days=3)).isoformat(),
                               "resolution": "condition cleared"}))
        s.add(Incident(signature="seed.closed:bare", resolved=True, detail={}))
        # owner actions
        s.add(OwnerAction(action="seed: open one", requirement_key="seed.1"))
        s.add(OwnerAction(action="seed: open two", requirement_key="seed.2"))
        s.add(OwnerAction(action="seed: done", requirement_key="seed.3", done=True))
        # spend: this month (llm, two agents; one hosting), last month (llm)
        s.add(CostEntry(agent="cfo", kind="llm", amount_cad=0.5, provider="anthropic",
                        model="m-small", department="finance", tokens_in=10, tokens_out=5))
        s.add(CostEntry(agent="market_radar", kind="llm", amount_cad=1.25, provider="anthropic",
                        model="m-large", department="radar"))
        s.add(CostEntry(agent="orchestrator", kind="hosting", amount_cad=3.0))
        s.add(CostEntry(agent="cfo", kind="llm", amount_cad=2.0, at=now - timedelta(days=45)))
        # revenue
        s.add(LedgerEntry(category="sale", description="seed sale", gross_cad=12.5,
                          fees_cad=1.44, evidence_ref="seed-order-1"))
        s.commit()
    _SEEDED["client"] = TestClient(main.app)
    return _SEEDED["client"]


def sql(q: str, *args):
    with sqlite3.connect(DB_FILE) as c:
        return c.execute(q, args).fetchall()


def one(q: str, *args):
    return sql(q, *args)[0][0]


def month_start_iso() -> str:
    n = utcnow()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d")


# ---- /api/status ---------------------------------------------------------

def test_status_numbers_equal_sql():
    c = seeded()
    st = c.get("/api/status").json()
    # SQLAlchemy stores the enum by member name (PENDING), not by value (pending).
    by_status = {k.lower(): v for k, v in sql("select status, count(*) from jobs group by status")}
    for key in ("pending", "running", "done", "failed", "dead", "cancelled"):
        assert st["queue"].get(key, 0) == by_status.get(key, 0), (key, st["queue"], by_status)
    assert st["dead_letters"] == by_status["dead"]
    refusals = one("select count(*) from jobs where status='DEAD' and last_error like 'capability not enabled%'")
    assert st["dead_letter_refusals"] == refusals == 1, st
    assert st["dead_letter_defects"] == by_status["dead"] - refusals
    assert st["products"] == one("select count(*) from products")
    assert st["certified_versions"] == one("select count(*) from pattern_versions where certified=1")
    assert st["open_incidents"] == one("select count(*) from incidents where resolved=0")
    assert st["owner_actions_open"] == one("select count(*) from owner_actions where done=0")
    assert abs(st["agent_opex_cad"] - one("select sum(amount_cad) from cost_entries")) < 1e-6
    assert abs(st["revenue_cad"] - one("select sum(gross_cad) from ledger")) < 1e-6


# ---- /api/console --------------------------------------------------------

def test_console_numbers_equal_sql():
    c = seeded()
    con = c.get("/api/console").json()
    assert con["queues"]["pending"] == one("select count(*) from jobs where status='PENDING'")
    assert con["queues"]["dead_letters"] == one("select count(*) from jobs where status='DEAD'")
    assert con["products"]["count"] == one("select count(*) from products")
    assert con["products"]["certified_versions"] == one(
        "select count(*) from pattern_versions where certified=1")
    assert len(con["incidents"]) == one("select count(*) from incidents where resolved=0")
    assert {i["signature"] for i in con["incidents"]} == {
        r[0] for r in sql("select signature from incidents where resolved=0")}
    assert len(con["agents"]) == one("select count(*) from agents")
    recent = [r["id"] for r in con["queues"]["recent"]]
    assert recent == [r[0] for r in sql("select id from jobs order by id desc limit 10")]


# ---- /api/incidents ------------------------------------------------------

def test_incidents_numbers_equal_sql():
    c = seeded()
    inc = c.get("/api/incidents").json()
    assert inc["open_total"] == one("select count(*) from incidents where resolved=0")
    rows = sql("select detail from incidents where resolved=1")
    cutoff = utcnow() - timedelta(hours=inc["resolved_last_hours"])
    from datetime import datetime

    recent = bare = 0
    for (detail,) in rows:
        stamp = (json.loads(detail or "{}") or {}).get("resolved_at")
        if not stamp:
            bare += 1
        elif datetime.fromisoformat(stamp) >= cutoff:
            recent += 1
    assert inc["resolved_recently_total"] == recent == 1, inc
    assert inc["resolved_without_evidence_in_sample"] == bare == 1, inc
    listed_open = sum(len(v["open"]) for v in inc["by_kind"].values())
    assert listed_open == inc["open_total"]


# ---- /api/spend-report ---------------------------------------------------

def test_spend_report_numbers_equal_sql():
    c = seeded()
    rep = c.get("/api/spend-report").json()
    ms = month_start_iso()
    month_llm = sql("select agent, amount_cad from cost_entries where kind='llm' and at >= ?", ms)
    assert rep["month"] == ms
    assert abs(rep["spent_cad"] - sum(a for _g, a in month_llm)) < 1e-6, (rep["spent_cad"], month_llm)
    assert rep["calls"] == len(month_llm)
    by_agent = Counter()
    for agent, amount in month_llm:
        by_agent[agent] += amount
    assert {k: round(v["cad"], 6) for k, v in rep["by_agent"].items()} == {
        k: round(v, 6) for k, v in by_agent.items()}, rep["by_agent"]


# ---- /api/build2 and /api/closure ----------------------------------------

def test_build2_counts_equal_the_registry_file():
    c = seeded()
    b = c.get("/api/build2").json()
    counts = Counter(r["status"] for r in REQS)
    assert b["coverage"]["total"] == len(REQS) == 320
    assert b["coverage"]["by_status"] == {k: counts.get(k, 0) for k in b["coverage"]["by_status"]}
    unparked = sorted(r["id"] for r in REQS
                      if r["status"] in ("partial", "missing") and not r.get("parked_on"))
    assert sorted(b["executable_unparked"]) == unparked
    assert b["coverage"]["executable_unparked"] == len(unparked)
    assert b["coverage"]["executable_remaining"] == counts["partial"] + counts.get("missing", 0)
    assert len(b["executable_remaining"]) == b["coverage"]["executable_remaining"]
    assert len(b["blocked_on_owner"]) == counts["owner_gated"]


def test_closure_counts_sum_to_320_and_match_its_rows():
    c = seeded()
    cl = c.get("/api/closure").json()
    assert cl["total"] == 320 and sum(cl["counts"].values()) == 320, cl["counts"]
    recount = Counter(r["state"] for r in cl["rows"])
    assert dict(recount) == {k: v for k, v in cl["counts"].items() if v}, (recount, cl["counts"])
    assert len(cl["open"]) == cl["counts"]["OPEN"]
    assert cl["closed_out"] is (cl["counts"]["OPEN"] == 0)
    assert sorted(r["id"] for r in cl["rows"]) == sorted(r["id"] for r in REQS)
    for sec, sc in cl["by_section"].items():
        assert sum(sc.values()) == sum(1 for r in REQS if r["section"] == sec), sec


# ---- the HTML dashboard --------------------------------------------------

def _card(html: str, label: str) -> str:
    m = re.search(rf"<span>{re.escape(label)}</span><b>([^<]*)</b>", html)
    assert m, f"no card {label!r} on the dashboard"
    return m.group(1)


def test_dashboard_cards_equal_sql():
    c = seeded()
    r = c.get("/")
    assert r.status_code == 200
    html = r.text
    assert int(_card(html, "Queue pending")) == one("select count(*) from jobs where status='PENDING'")
    assert int(_card(html, "Running")) == one("select count(*) from jobs where status='RUNNING'")
    assert int(_card(html, "Dead letters")) == one("select count(*) from jobs where status='DEAD'")
    assert int(_card(html, "Certified releases")) == one(
        "select count(*) from pattern_versions where certified=1")
    assert int(_card(html, "Open incidents")) == one("select count(*) from incidents where resolved=0")
    assert _card(html, "Agent opex") == f"CA${one('select sum(amount_cad) from cost_entries'):.2f}"
    assert _card(html, "Revenue") == f"CA${one('select sum(gross_cad) from ledger'):.2f}"
    assert int(_card(html, "Listings drafted")) == one("select count(*) from listings")
    counts = Counter(r["status"] for r in REQS)
    assert int(_card(html, "executable left")) == counts["partial"] + counts.get("missing", 0)
    cl = c.get("/api/closure").json()["counts"]
    for k, v in cl.items():
        assert int(_card(html, f"closure: {k}")) == v, k


def test_dashboard_never_claims_no_spend_limits():
    c = seeded()
    assert one("select count(*) from spend_limits") == 0  # the table the old text read
    html = c.get("/").text
    assert "No spend limits configured" not in html
    con = c.get("/api/console").json()
    assert con["spend"]["month"], "the console's spend block carries no live control"


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
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:900]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    sys.exit(1 if fails else 0)
