"""ENG-DAILY: the daily production ledger, the zero-output diagnosis and the Daily panel.

1. Counts are exact on fixtures, per UTC day, from persisted rows.
2. UNKNOWN is never 0: unreadable source, before the first recorded job, unregistered shop.
3. The diagnosis names each cause: suspended, empty upstream queue, gate refusing (top
   reasons), budget refused, policy and owner holds; an unexplained zero files a change request.
4. An automatic action fires only on a safe, free path (`rearm_probe` on a free loop under the
   cadence key; one supply re-offer when admission is clear), never on a spending loop, and
   nothing touches a gate, ceiling or owner exception.
5. `/api/cc/daily` is owner-only and read-only; the readback section withholds spend amounts.
6. The job is wired: handler, cadence, free list; a worker run records the ledger row.

Run: cd brambleloop && PYTHONPATH=src:tests python3 tests/test_eng_daily.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="eng_daily_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the daily-ledger harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (AuditLog, CostEntry, Incident, Job, JobStatus,  # noqa: E402
                                     Lesson, OperatingReading, OwnerVeto, PolicySnapshot,
                                     SpendLimit)
from brambleloop.ops import daily_ledger as L  # noqa: E402
from brambleloop.queue.durable import DEFECT, JobQueue, classify_dead_letter  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.swarm import orchestrate as orc  # noqa: E402

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
D0 = "2026-11-20"
D1 = "2026-11-19"
D2 = "2026-11-18"
D3 = "2026-11-17"
D4 = "2026-11-16"


def _db():
    db = Database(f"sqlite:///{tempfile.mkdtemp(dir=_TMP)}/d.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _at(day: str, hour: int = 10) -> datetime:
    return datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)


def _observing(db, since=datetime(2026, 10, 30, tzinfo=timezone.utc)):
    with db.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.heartbeat", inputs={},
                  status=JobStatus.DONE, outputs={}, created_at=since, finished_at=since))


def _audit(db, action, at, artifact=None, detail=None, job_id=None):
    with db.session() as s:
        s.add(AuditLog(actor="test", action=action, artifact=artifact, at=at,
                       detail=detail or {}, job_id=job_id))


def _job(db, job_type, *, status=JobStatus.DONE, at=NOW, outputs=None, error=None,
         inputs=None, created=None):
    with db.session() as s:
        j = Job(agent="orchestrator", job_type=job_type, inputs=inputs or {}, status=status,
                outputs=outputs, last_error=error, created_at=created or at,
                finished_at=at if status in (JobStatus.DONE, JobStatus.DEAD) else None)
        s.add(j)
        s.flush()
        return j.id


def _counts(db):
    with db.session() as s:
        return {m.__name__: s.scalar(select(func.count()).select_from(m)) for m in (
            AuditLog, Job, OperatingReading, SpendLimit, PolicySnapshot, OwnerVeto, Incident)}


# ---- 1. exact counts --------------------------------------------------------------------

def _seed_counts(db):
    _observing(db)
    for at in (_at(D1, 9), _at(D1, 23)):
        _audit(db, L.A_DRAFTED, at, "basket@1.0.0")
    _audit(db, L.A_DRAFTED, _at(D0, 1), "tote@1.0.0")
    _audit(db, L.A_CERTIFIED, _at(D2), "basket@1.0.0")
    _audit(db, L.A_BUILT, _at(D1), "basket@1.0.0", {"pdfs": {"US": {"sha": "a"},
                                                             "UK": {"sha": "b"}}})
    _audit(db, L.A_BUILT, _at(D0, 2), "tote@1.0.0", {"pdfs": {"US": {"sha": "c"}}})
    _audit(db, L.A_GALLERY, _at(D1), "basket@1.0.0")
    _audit(db, L.A_PACKAGE, _at(D1), detail={"results": [
        {"key": "basket@1.0.0", "state": "ready_for_owner_review"},
        {"key": "tote@1.0.0", "state": "blocked"}]})
    _audit(db, "store.published", _at(D0, 3), "basket@1.0.0", {"etsy_listing_id": "4400001"})
    _audit(db, "store.publish_incomplete", _at(D1), "tote@1.0.0", {"etsy_listing_id": "4400002"})
    _audit(db, L.A_ACTIVATED, _at(D0, 4), "basket@1.0.0", {"etsy_listing_id": "4400001"})
    _audit(db, L.A_ADMITTED, _at(D2), detail={"key": "draft:basket"})
    with db.session() as s:
        s.add(CostEntry(agent="a", amount_cad=1.25, at=_at(D3)))
        s.add(CostEntry(agent="a", amount_cad=0.75, at=_at(D3, 20)))
        s.add(Lesson(origin_cell="c", subject="s", statement="x", at=_at(D4),
                     acted_on_by=[{"cell": "d", "how": "h", "at": _at(D1).isoformat()}]))
    _job(db, "cir.draft", status=JobStatus.DEAD, at=_at(D1), error="ValueError: boom")
    _job(db, "gate.certify", status=JobStatus.DEAD, at=_at(D1),
         error="capability not enabled: publication")
    _job(db, "mjs.scan", at=_at(D0, 5), outputs={"ran": True})
    _job(db, "mjs.scan", at=_at(D1, 5), outputs={"ran": True, "deferred": True})


def test_counts_are_exact_on_fixtures():
    db = _db()
    _seed_counts(db)
    led = L.ledger(db, now=NOW)
    m = {k: v["days"] for k, v in led["metrics"].items()}
    assert led["today"] == D0 and len(led["days"]) == L.DAYS
    assert (m["products_started"][D1], m["products_started"][D0]) == (2, 1), m["products_started"]
    assert m["certifications"][D2] == 1 and m["certifications"][D1] == 0
    assert (m["pdfs_us"][D1], m["pdfs_us"][D0], m["pdfs_uk"][D1], m["pdfs_uk"][D0]) == (1, 1, 1, 0)
    assert m["galleries_completed"][D1] == 1
    assert m["listing_packages"][D1] == 1, "only the ready package counts"
    assert (m["etsy_drafts"][D0], m["etsy_drafts"][D1], m["etsy_live"][D0]) == (1, 1, 1)
    assert led["metrics"]["etsy_drafts"]["ids"] == {D1: ["4400002"], D0: ["4400001"]}
    assert m["concepts_admitted"][D2] == 1
    assert m["spend_cad"][D3] == 2.0 and m["spend_cad"][D2] == 0
    assert m["lessons_learned"][D4] == 1 and m["lessons_applied"][D1] == 1
    assert m["dead_letters"][D1] == 2
    expected_fail = sum(classify_dead_letter(jt, e) == DEFECT for jt, e in (
        ("cir.draft", "ValueError: boom"), ("gate.certify", "capability not enabled: publication")))
    assert m["failures"][D1] == expected_fail == 1
    anchor = led["shops"][0]
    assert anchor["role"] == "anchor" and anchor["attempted"][D0] == 1
    assert anchor["attempted"][D1] == 0, "a deferred scan is not an attempt"
    assert len(led["shops"]) == 9


def test_watchlist_shop_scans_are_counted_per_shop():
    from brambleloop.intel import watchlist
    from brambleloop.intel.scan_evidence import OWNER_SHOPS
    from brambleloop.runtime.intel_ops import benchmark_alias

    db = _db()
    _observing(db)
    by = {m.shop_name.lower(): m for m in watchlist.WATCHLIST}
    member = next(by[n.lower()] for n, _u, r in OWNER_SHOPS if r != "anchor" and n.lower() in by)
    alias = benchmark_alias(member.key)
    _audit(db, L.A_SCAN_WATCH, _at(D1), detail={"ran": True, "shops": [
        {"alias": alias, "ran": True, "state": "ok"}]})
    _audit(db, L.A_SCAN_WATCH, _at(D0), detail={"ran": True, "shops": [
        {"alias": alias, "ran": True, "state": "source_outage"},
        {"alias": "bm-other", "ran": True, "state": "ok"}]})
    _audit(db, L.A_SCAN_WATCH, _at(D0, 11), detail={"ran": True, "shops": [
        {"alias": alias, "deferred": True}]})
    row = next(r for r in L.ledger(db, now=NOW)["shops"] if r["alias"] == alias)
    assert (row["attempted"][D1], row["succeeded"][D1]) == (1, 1)
    assert (row["attempted"][D0], row["succeeded"][D0]) == (1, 0), row


def test_products_advanced_count_useful_stage_work_only():
    db = _db()
    _observing(db)
    _job(db, "gate.certify", at=_at(D1), outputs={"granted": True, "reasons": []})
    _job(db, "gate.certify", at=_at(D1, 11), outputs={})          # a no-op is not an advance
    _job(db, "gate.certify", status=JobStatus.DEAD, at=_at(D1, 12), outputs={"granted": True})
    m = L.ledger(db, now=NOW)["metrics"]["advanced:gate.certify"]["days"]
    assert (m[D1], m[D0]) == (1, 0), m


# ---- 2. UNKNOWN is never 0 --------------------------------------------------------------

def test_unknown_is_never_zero():
    db = _db()
    led = L.ledger(db, now=NOW)            # nothing has ever run: nothing was observing
    for k, v in led["metrics"].items():
        assert all(x == L.UNKNOWN for x in v["days"].values()), (k, v["days"])
    for r in led["shops"]:
        assert all(x == L.UNKNOWN for x in r["attempted"].values()), r
    # Observation began yesterday: earlier days UNKNOWN, from then on real zeros.
    _observing(db, since=_at(D1, 6))
    m = L.ledger(db, now=NOW)["metrics"]["certifications"]
    assert m["days"][D2] == L.UNKNOWN and m["unknown_why"][D2] == "before the first recorded job"
    assert m["days"][D1] == 0 and m["days"][D0] == 0
    # One unreadable source is UNKNOWN for that metric alone, with its class, never 0.
    from brambleloop.visual import image_records
    with patch.object(image_records, "ImageCandidate", None):
        led = L.ledger(db, now=NOW)
    assert all(v == L.UNKNOWN for v in led["metrics"]["images_generated"]["days"].values())
    assert led["metrics"]["images_generated"]["error_class"]
    assert led["metrics"]["certifications"]["days"][D0] == 0
    # A sum over shops is UNKNOWN while any shop is UNKNOWN.
    with patch("brambleloop.intel.watchlist.WATCHLIST", ()):
        led = L.ledger(db, now=NOW)
    assert any(r["registered"] is False for r in led["shops"])
    assert led["metrics"]["scans_succeeded"]["days"][D0] == L.UNKNOWN
    # A metric past its source's retention horizon is UNKNOWN.
    src = L._Src("x", 1)
    s = L._series(src, [D2, D1, D0], datetime(2026, 10, 1).date(), NOW)
    assert s["days"][D2] == L.UNKNOWN and s["days"][D0] == 0


def test_today_unknown_is_diagnosed_as_unknown_not_zero():
    db = _db()
    d = L.diagnose(db, None, now=NOW, act=False)
    assert d["diagnosed"] and all(r["today"] == L.UNKNOWN and r["causes"][0]["kind"] == "unknown"
                                  for r in d["diagnosed"])


# ---- 3. diagnosis -----------------------------------------------------------------------

def _diag(db, stage, **kw):
    d = L.diagnose(db, kw.pop("queue", None), now=NOW, act=kw.pop("act", False))
    return next((r for r in d["diagnosed"] if r["stage"] == stage), None)


def _kinds(row):
    return {c["kind"] for c in (row or {}).get("causes") or []}


def test_diagnosis_names_a_suspension_with_its_reason():
    db = _db()
    _observing(db)
    sus = {"cir.draft": {"kind": "suspended", "incident": "thrash:cir.draft:x",
                         "why": "a loop spending without progress"}}
    with patch.object(orc, "suspended_job_types", lambda db, now=None: sus):
        row = _diag(db, "products_started")
    c = next(c for c in row["causes"] if c["kind"] == "suspended")
    assert c["job_type"] == "cir.draft" and "without progress" in c["why"]


def test_diagnosis_names_an_empty_upstream_queue():
    db = _db()
    _observing(db)
    row = _diag(db, "certifications")
    c = next(c for c in row["causes"] if c["kind"] == "queue_empty_upstream")
    assert c["upstream"] == "products_started" and c["producer_jobs_open"] == 0
    _job(db, "gate.certify", status=JobStatus.PENDING, at=NOW)
    assert "queue_empty_upstream" not in _kinds(_diag(db, "certifications"))


def test_diagnosis_names_a_refusing_gate_with_its_top_reasons():
    db = _db()
    _observing(db)
    for r in (["tension_mismatch: row 4"], ["tension_mismatch: row 9"], ["photo_missing"]):
        _audit(db, "gate.blocked", NOW - timedelta(hours=2), "basket@1", {"reasons": r})
    _audit(db, "gate.halted", NOW - timedelta(hours=30), "x@1", {"reason": "old"})
    c = next(c for c in _diag(db, "certifications")["causes"] if c["kind"] == "gate_refusing")
    assert c["refusals_24h"] == 3
    assert c["top_reasons"][0] == {"reason": "tension_mismatch", "count": 2}


def test_diagnosis_names_a_budget_refusal():
    db = _db()
    _observing(db)
    _job(db, "gate.certify", status=JobStatus.DEAD, at=NOW - timedelta(hours=1),
         error="budget exceeded: daily ceiling")
    c = next(c for c in _diag(db, "certifications")["causes"] if c["kind"] == "budget_refused")
    assert c["producer_jobs_refused_24h"] == 1


def test_diagnosis_names_policy_and_owner_holds_in_scope():
    from brambleloop.gates import platform_policy

    db = _db()
    _observing(db)
    pub = [{"source": "listing_image_rules", "affects": ["publishing"]}]
    with patch.object(platform_policy, "unreviewed_changes", lambda db: pub):
        assert "hold" in _kinds(_diag(db, "etsy_drafts"))
        assert "hold" not in _kinds(_diag(db, "certifications")), \
            "a publication-only change never holds manufacturing (#39 scope)"
    with db.session() as s:
        s.add(OwnerVeto(subject_ref="basket", scope="flagship", owner_vetoed=True,
                        at=NOW - timedelta(days=1)))
    c = next(c for c in _diag(db, "certifications")["causes"] if c["kind"] == "hold")
    assert c["hold"] == "owner" and c["owner_vetoes_14d"] == 1


def test_an_unexplained_zero_files_a_change_request():
    db = _db()
    _observing(db)
    _job(db, "learn.scan", status=JobStatus.PENDING, at=NOW)     # producer alive, no output
    q = JobQueue(db)
    row = _diag(db, "lessons", queue=q, act=True)
    assert _kinds(row) == {"undiagnosed"}
    assert row["ecrs"] and (row["ecrs"][0].get("pending") or row["ecrs"][0].get("filed"))
    try:
        import brambleloop.improve.ecr  # noqa: F401
    except ImportError:
        with db.session() as s:
            req = s.scalar(select(AuditLog).where(AuditLog.action == L.ECR_PENDING))
        assert req.detail["request"]["defect_class"] == "missing_capability"
        assert req.detail["request"]["acceptance_criteria"]
    with db.session() as s:
        rec = s.scalar(select(OperatingReading).where(OperatingReading.kind == L.DIAG_KIND,
                                                      OperatingReading.period_key == f"{D0}:lessons"))
    assert rec is not None and rec.payload["causes"][0]["kind"] == "undiagnosed"


def test_a_stage_with_output_today_and_no_history_is_not_diagnosed():
    db = _db()
    _observing(db)
    _audit(db, L.A_CERTIFIED, NOW - timedelta(hours=1), "basket@1")
    assert _diag(db, "certifications") is None


# ---- 4. actions: safe and free only -----------------------------------------------------

def test_rearm_fires_only_on_a_free_loop_rearm_probe_releases():
    db = _db()
    _observing(db)
    q = JobQueue(db)
    sus = {"radar.scan": {"kind": "backoff", "incident": "thrash:backoff:radar.scan"}}
    with db.session() as s:
        s.add(Incident(severity="P2", signature="thrash:backoff:radar.scan", summary="x",
                       detail={"suspension": {"kind": "backoff", "job_type": "radar.scan"}}))
    hit = {"job_type": "radar.scan", "release": "c" * 40}
    before = _counts(db)
    with patch.object(orc, "suspended_job_types", lambda db, now=None: sus), \
            patch.object(orc, "rearm_probe", lambda s, jt, sus, boot_cache=None: hit):
        row = _diag(db, "concepts", queue=q, act=True)
        again = _diag(db, "concepts", queue=q, act=True)
    act = next(a for a in row["actions"] if a["action"] == "rearm")
    assert act["enqueued"] is True and act["job_type"] == "radar.scan"
    from brambleloop.runtime.worker import CADENCES, cadence_key
    name, _a, _jt, period = next(c for c in CADENCES if c[2] == "radar.scan")
    assert act["key"] == cadence_key(name, period, NOW), \
        "the cadence's own key: the scheduler cannot double it"
    assert not any(a.get("enqueued") for a in again["actions"]), "one probe, never two"
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "radar.scan")) == 1
        assert s.scalar(select(Incident.resolved)) is False, "the breaker's record is untouched"
    after = _counts(db)
    for k in ("SpendLimit", "PolicySnapshot", "OwnerVeto", "Incident"):
        assert after[k] == before[k], k


def test_a_spending_loop_is_never_rearmed_and_gets_a_change_request():
    db = _db()
    _observing(db)
    q = JobQueue(db)
    sus = {"cir.draft": {"kind": "suspended", "incident": "thrash:cir.draft:x"}}
    with db.session() as s:
        s.add(Incident(severity="P2", signature="thrash:cir.draft:x", summary="x",
                       detail={"suspension": {"kind": "suspended", "job_type": "cir.draft"}}))
    with db.session() as s:
        assert orc.spending_job_type(s, "cir.draft") is True
    with patch.object(orc, "suspended_job_types", lambda db, now=None: sus), \
            patch.object(orc, "rearm_probe", lambda *a, **k: {"release": "x"}), \
            patch("brambleloop.products.supply.offers", lambda db: []):
        row = _diag(db, "products_started", queue=q, act=True)
    assert not any(a["action"] == "rearm" for a in row["actions"])
    assert row["ecrs"], "a held spending loop needs a code change: a change request"
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "cir.draft")) == 0


def test_rearm_never_enqueues_a_spending_cadence_loop_even_if_probed():
    db = _db()
    _observing(db)
    q = JobQueue(db)
    jt = "creative.style_learning"
    with db.session() as s:
        assert orc.spending_job_type(s, jt) is True
        s.add(Incident(severity="P2", signature=f"thrash:{jt}:x", summary="x",
                       detail={"suspension": {"kind": "suspended", "job_type": jt}}))
    with patch.object(orc, "rearm_probe", lambda *a, **k: {"release": "x"}):
        assert L._rearm(db, q, jt, now=NOW) is None
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job).where(Job.job_type == jt)) == 0


def test_reoffer_fires_only_when_admission_is_clear():
    from brambleloop.products import supply

    db = _db()
    _observing(db)
    q = JobQueue(db)
    offer = [{"key": "draft:basket", "slug": "basket"}]
    with patch.object(supply, "offers", lambda db: offer), \
            patch.object(supply, "assess", lambda db, now=None: {
                "slots": 0, "refusals": ["cost: the month's ceiling has no room"]}):
        row = _diag(db, "products_started", queue=q, act=True)
    a = next(a for a in row["actions"] if a["action"] == "reoffer")
    assert a["enqueued"] is False and "cost" in a["why"]
    with patch.object(supply, "offers", lambda db: offer), \
            patch.object(supply, "assess", lambda db, now=None: {
                "slots": 1, "refusals": ["backlog: a stage is not keeping up"]}):
        row = _diag(db, "products_started", queue=q, act=True)
    a = next(a for a in row["actions"] if a["action"] == "reoffer")
    assert a["enqueued"] is False and "backlog" in a["why"], "an open slot never outvotes a refusal"
    with patch.object(supply, "offers", lambda db: offer), \
            patch.object(supply, "assess", lambda db, now=None: {"slots": 1, "refusals": []}):
        row = _diag(db, "products_started", queue=q, act=True)
        row2 = _diag(db, "products_started", queue=q, act=True)
    a = next(a for a in row["actions"] if a["action"] == "reoffer")
    assert a["enqueued"] is True and a["key"] == f"{L.REOFFER_PREFIX}:{NOW.date()}"
    assert not any(x.get("enqueued") for x in row2["actions"])
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Job).where(
            Job.job_type == "supply.admit")) == 1


def test_a_read_only_diagnosis_writes_and_enqueues_nothing():
    db = _db()
    _observing(db)
    before = _counts(db)
    sus = {"radar.scan": {"kind": "backoff"}}
    with patch.object(orc, "suspended_job_types", lambda db, now=None: sus), \
            patch.object(orc, "rearm_probe", lambda *a, **k: {"release": "x"}):
        L.panel(db, now=NOW)
    assert _counts(db) == before


# ---- 5. panel route and readback --------------------------------------------------------

def test_the_panel_route_is_owner_only_and_read_only():
    from fastapi.testclient import TestClient

    from brambleloop.app import main
    from brambleloop.app.command_center import auth
    from brambleloop.core import opsauth

    os.environ[opsauth.TOKEN_VAR] = "d" * 40
    pw = "owner passphrase for the daily harness"
    os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(pw, iterations=100_000)
    main.db.create_all()
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/daily").status_code in (401, 403)
    ops = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert ops.get("/api/cc/daily", headers={"Authorization": f"Bearer {'d' * 40}"}
                   ).status_code in (401, 403), "the operator token is not the owner"
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.post("/api/cc/auth/login", json={"passphrase": pw}).status_code == 200
    before = _counts(main.db)
    r = c.get("/api/cc/daily")
    assert r.status_code == 200, r.text
    data = r.json().get("data", r.json())
    assert data["tab"] == "DAILY" and data["read_only"] is True and "ledger" in data
    after = _counts(main.db)
    assert {k: v for k, v in after.items() if k != "AuditLog"} == \
        {k: v for k, v in before.items() if k != "AuditLog"}
    assert c.post("/api/cc/daily").status_code in (404, 405)


def test_the_readback_section_withholds_spend_ids_and_reason_text():
    from brambleloop.ops import production_evidence as PE

    db = _db()
    _seed_counts(db)
    ev = PE.evidence(db, now=NOW)["daily_ledger"]
    assert ev["readable"] is True and ev["metrics"]["products_started"]["days"][D1] == 2
    assert "spend_cad" not in ev["metrics"]
    assert ev["metrics"]["spend_recorded"]["days"][D3] is True
    text = repr(ev)
    for secret in ("1.25", "2.0", "4400001", "MJsOffTheHook", "boom"):
        assert secret not in text, secret


# ---- 6. wiring --------------------------------------------------------------------------

def test_the_job_is_wired_free_and_records_the_ledger():
    from brambleloop.ops import retention
    from brambleloop.runtime.worker import CADENCES, Worker

    assert any(jt == "ops.daily_ledger" for _n, _a, jt, _p in CADENCES)
    assert "ops.daily_ledger" in orc.FREE_JOB_TYPES
    assert retention.unknown_read_actions() == []
    db = _db()
    _observing(db)
    job = JobQueue(db).enqueue("orchestrator", "ops.daily_ledger", {}, idempotency_key="t:1",
                               priority=0)
    Worker(db, "daily", job_types=["ops.daily_ledger"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        rec = s.scalar(select(OperatingReading).where(OperatingReading.kind == L.LEDGER_KIND))
    assert rec is not None and rec.payload["metrics"]
    assert row.outputs["recorded"] == rec.period_key


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name} {exc!r}"[:600])
                import traceback

                traceback.print_exc()
    print(f"{failed} failed")
    sys.exit(1 if failed else 0)
