"""W4-READBACK: the read-only production evidence surface.

Production is deny-by-default on public GETs (W4-SECPATCH) and must stay so; this proves the
evidence surface added beside it opens nothing:

1. the new anonymous `/api/verify` `evidence_checks` are each false without evidence, and true
   only with real seeded evidence (and false again when that evidence goes bad);
2. `GET /api/readback/evidence` refuses anonymous callers and refuses the operator token; it
   is closed (503) when `BRAMBLELOOP_READBACK_TOKEN` is unset, short, or equal to the operator
   token;
3. read-only: the readback token is refused on every other route the app serves (routers
   included, every method), and on the public reads it unlocks nothing beyond the anonymous
   projection;
4. the evidence carries no private field: seeded job inputs/outputs, error text, incident text,
   paid-call payloads and owner-inbox text never appear;
5. the token is never echoed -- not by the server, not by `ops/readback.py --evidence`;
6. `ops/readback.py --evidence` keeps UNKNOWN distinct from PASS.

Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_readback_evidence.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import contextlib
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO / "ops"))

_TMP = tempfile.mkdtemp(prefix="readback_ev_")
DB_FILE = os.path.join(_TMP, "rb.db")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the readback-evidence harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app import main, security  # noqa: E402
from brambleloop.core import opsauth, readbackauth  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    AuditLog, Incident, Job, JobStatus, OwnerAction, Product)
from brambleloop.gateway.paid_calls import PaidCallRecord  # noqa: E402
from brambleloop.ops import production_evidence as pe  # noqa: E402
from brambleloop.ops.incident_lifecycle import SYSTEMIC_SIGNATURE  # noqa: E402

# Built at run time so no credential-shaped literal sits in the repository.
OPS_TOKEN = "op" * 20
READBACK_TOKEN = "rb-" + "k7" * 20
NOW = datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc)

# Private content seeded into the shared database; none may appear in the evidence.
PRIVATE = {
    "error_text": "READBACK-PRIVATE-ERROR-5521 buyer said hello",
    "inputs": "READBACK-PRIVATE-INPUT-7710",
    "outputs": "READBACK-PRIVATE-OUTPUT-3308",
    "payload": "READBACK-PRIVATE-MODEL-RESPONSE-9046",
    "incident": "READBACK-PRIVATE-INCIDENT-TEXT-1187",
    "owner": "READBACK-PRIVATE-OWNER-ACTION-6620",
    "signature_tail": "READBACK-PRIVATE-SIGNATURE-4419",
}
FORBIDDEN_KEYS = ("inputs", "outputs", "payload", "last_error", "summary", "detail", "reason",
                  "action_text", "consequence_of_delay", "amount_cad", "customer_id",
                  "customer_ref", "intent_token", "error")

_STATE: dict = {}


def _fresh_db() -> Database:
    path = tempfile.mkdtemp(prefix="rbdb_", dir=_TMP)
    d = Database(f"sqlite:///{path}/n.db")
    d.create_all()
    return d


def _env(**kw):
    """Set (or with None, unset) the two credentials for the duration of a block."""
    @contextlib.contextmanager
    def cm():
        saved = {k: os.environ.get(k) for k in kw}
        try:
            for k, v in kw.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return cm()


def both_tokens():
    return _env(**{opsauth.TOKEN_VAR: OPS_TOKEN, readbackauth.TOKEN_VAR: READBACK_TOKEN})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def client() -> TestClient:
    if "c" in _STATE:
        return _STATE["c"]
    assert str(main.db.engine.url).endswith(DB_FILE), main.db.engine.url
    main.db.create_all()
    Registry(main.db).seed_defaults()
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    with main.db.session() as s:
        s.add(Product(slug="readback-slug-a", title="Readback A", status="concept"))
        dead = Job(agent="orchestrator", job_type="improve.weekly",
                   inputs={"note": PRIVATE["inputs"]}, outputs={"note": PRIVATE["outputs"]},
                   status=JobStatus.DEAD, attempts=3,
                   last_error=f"TypeError: {PRIVATE['error_text']}\nTraceback ...",
                   finished_at=recent)
        s.add(dead)
        s.add(Job(agent="coo", job_type="mjs.scan", inputs={"laura": {"priority": "p"},
                                                           "note": PRIVATE["inputs"]},
                  outputs={"work_done": 2, "note": PRIVATE["outputs"]},
                  status=JobStatus.DONE, created_at=recent, finished_at=recent))
        s.add(Incident(severity="P0", signature=f"{SYSTEMIC_SIGNATURE}",
                       summary=PRIVATE["incident"], halts_publication=True,
                       detail={"why": PRIVATE["incident"]}))
        s.add(Incident(severity="P1", signature=f"stale-artefact:{PRIVATE['signature_tail']}",
                       product_slug="readback-slug-a", summary=PRIVATE["incident"],
                       halts_publication=True))
        s.add(OwnerAction(requirement_key="readback_req", action=PRIVATE["owner"],
                          reason=PRIVATE["owner"], minutes=5,
                          consequence_of_delay=PRIVATE["owner"]))
        s.flush()
        s.add(PaidCallRecord(key="rbk1", effect="model.complete", job_id=dead.id,
                             job_type="improve.weekly", fingerprint="f" * 64, outcome="OK",
                             payload={"text": PRIVATE["payload"]}, at=recent,
                             updated_at=recent))
        _STATE["dead_id"] = dead.id
    _STATE["c"] = TestClient(main.app, raise_server_exceptions=False,
                             base_url="https://testserver")
    return _STATE["c"]


# ---- 1. each check is false without evidence, true only with real evidence -----------------


def _check(db, name, now=NOW) -> bool:
    got = {c["check"]: c for c in pe.checks(db, now=now)}
    assert set(got) == set(pe.CHECK_NAMES), sorted(got)
    assert all(set(c) == {"check", "ok", "evidence"} for c in got.values()), got
    return got[name]["ok"]


def test_every_check_is_false_on_an_empty_database():
    d = _fresh_db()
    got = pe.checks(d, now=NOW)
    assert [c["check"] for c in got] == list(pe.CHECK_NAMES), got
    assert [c["ok"] for c in got] == [False] * len(pe.CHECK_NAMES), got


def test_an_unreadable_database_is_false_never_a_pass():
    class Broken:
        def session(self):
            raise RuntimeError("down")
    got = pe.checks(Broken(), now=NOW)
    assert len(got) == len(pe.CHECK_NAMES)
    assert not any(c["ok"] for c in got), got
    assert {c["evidence"]["readable"] for c in got} == {False}, got


def _audit(d, action, detail, at, artifact=None):
    with d.session() as s:
        s.add(AuditLog(actor="sentinel", action=action, detail=detail, at=at, artifact=artifact))


def test_publishing_halt_clear_needs_a_fresh_sweep_and_no_open_systemic_halt():
    d = _fresh_db()
    assert _check(d, "publishing_halt_clear") is False          # no sweep: no evidence
    _audit(d, "ops.truth.sweep", {"systemic": {"error": "OperationalError"}},
           NOW - timedelta(minutes=10))
    assert _check(d, "publishing_halt_clear") is False          # sweep could not evaluate
    _audit(d, "ops.truth.sweep", {"systemic": {"systemic": False, "opened": False}},
           NOW - timedelta(minutes=5))
    assert _check(d, "publishing_halt_clear") is True           # evaluated and clear
    assert _check(d, "publishing_halt_clear", now=NOW + timedelta(hours=3)) is False  # stale
    with d.session() as s:
        s.add(Incident(severity="P0", signature=SYSTEMIC_SIGNATURE, halts_publication=True,
                       at=NOW - timedelta(hours=1)))
    assert _check(d, "publishing_halt_clear") is False          # the halt is open
    with d.session() as s:
        row = s.scalar(select(Incident).where(Incident.signature == SYSTEMIC_SIGNATURE))
        row.resolved = True
        row.detail = {"resolved_at": NOW.isoformat()}
    assert _check(d, "publishing_halt_clear") is True           # recovered
    ev = pe.publishing_halt(d, now=NOW)
    assert ev["systemic_halt_last_resolved"]["resolved_at"] == NOW.isoformat(), ev


def test_stale_artefacts_rebuilding_needs_the_sentinel_and_verified_rebuilds():
    d = _fresh_db()
    assert _check(d, "stale_artefacts_rebuilding") is False     # sentinel never ran
    _audit(d, "ops.sentinel", {"stale": 0, "checked": 9}, NOW - timedelta(hours=2))
    assert _check(d, "stale_artefacts_rebuilding") is True      # nothing stale, measured
    assert _check(d, "stale_artefacts_rebuilding", now=NOW + timedelta(hours=30)) is False
    _audit(d, "ops.sentinel", {"stale": 4, "checked": 9}, NOW - timedelta(hours=1))
    assert _check(d, "stale_artefacts_rebuilding") is False     # stale, nothing rebuilt
    _audit(d, "chain.rebuild_completed", {"already_fresh": True}, NOW - timedelta(hours=3),
           artifact="listing_asset:x")
    assert _check(d, "stale_artefacts_rebuilding") is False     # a no-op is not a rebuild
    _audit(d, "chain.rebuild_completed", {"verified_on_check": 1}, NOW - timedelta(hours=3),
           artifact="listing_asset:y")
    assert _check(d, "stale_artefacts_rebuilding") is True      # a verified rebuild
    with d.session() as s:
        s.add(Job(agent="listing", job_type="chain.rebuild", inputs={},
                  status=JobStatus.PENDING, created_at=NOW - timedelta(days=3)))
    assert _check(d, "stale_artefacts_rebuilding") is False     # a rebuild stuck for 72 h
    ev = pe.stale_rebuilds(d, now=NOW)
    assert ev["rebuilds_verified_48h"] == 1 and ev["rebuilds_already_fresh_7d"] == 1, ev
    assert ev["oldest_unfinished_rebuild_age_hours"] == 72.0, ev


def _paid(d, key, fp, outcome="OK", job_id=1, at=None):
    at = at or NOW - timedelta(hours=1)
    with d.session() as s:
        s.add(PaidCallRecord(key=key, effect="model.complete", job_id=job_id, job_type="x.y",
                             fingerprint=fp, outcome=outcome, at=at, updated_at=at,
                             payload={"text": PRIVATE["payload"]}))


def test_no_repeated_paid_call_needs_live_intents_and_no_double_billing():
    d = _fresh_db()
    assert _check(d, "no_repeated_paid_call_in_24h") is False   # no intents: no evidence
    _paid(d, "k1", "a" * 64, job_id=1)
    assert _check(d, "no_repeated_paid_call_in_24h") is True
    _paid(d, "k2", "a" * 64, outcome="DECLINED", job_id=2)      # declined: never billed
    assert _check(d, "no_repeated_paid_call_in_24h") is True
    _paid(d, "k3", "a" * 64, job_id=3, at=NOW - timedelta(hours=30))  # outside the 24 h
    assert _check(d, "no_repeated_paid_call_in_24h") is True
    _paid(d, "k4", "a" * 64, job_id=4)                          # the same request, paid again
    assert _check(d, "no_repeated_paid_call_in_24h") is False
    ev = pe.paid_calls(d, now=NOW)
    assert ev["repeated_billed_requests"] == 1 and ev["repeated"][0]["billed_calls"] == 2, ev
    assert ev["repeated"][0]["job_ids"] == [1, 4], ev
    assert PRIVATE["payload"] not in json.dumps(ev), ev


def _weekly(d, jt, status, finished):
    with d.session() as s:
        s.add(Job(agent="orchestrator", job_type=jt, inputs={}, status=status,
                  last_error="TypeError: x" if status == JobStatus.DEAD else None,
                  created_at=finished, finished_at=finished))


def test_weekly_jobs_completing_needs_a_recent_success_with_no_dead_letter_after_it():
    d = _fresh_db()
    assert _check(d, "weekly_jobs_completing") is False         # never ran
    _weekly(d, "improve.weekly", JobStatus.DEAD, NOW - timedelta(days=1))
    assert _check(d, "weekly_jobs_completing") is False         # only a dead letter
    _weekly(d, "improve.weekly", JobStatus.DONE, NOW - timedelta(hours=10))
    assert _check(d, "weekly_jobs_completing") is True          # the retry completed
    assert _check(d, "weekly_jobs_completing", now=NOW + timedelta(days=9)) is False
    _weekly(d, "portfolio.review", JobStatus.PENDING, NOW - timedelta(hours=1))
    assert _check(d, "weekly_jobs_completing") is False         # enqueued, never completed
    _weekly(d, "portfolio.review", JobStatus.DONE, NOW - timedelta(minutes=30))
    assert _check(d, "weekly_jobs_completing") is True
    _weekly(d, "improve.weekly", JobStatus.DEAD, NOW - timedelta(minutes=5))
    assert _check(d, "weekly_jobs_completing") is False         # dead after the success
    rows = {r["job_type"]: r for r in pe.weekly_jobs(d, now=NOW)["weekly_job_types"]}
    assert rows["improve.weekly"]["last_dead_error_class"] == "TypeError", rows
    assert rows["improve.weekly"]["dead_after_last_success"] is True, rows


def test_dead_letters_are_grouped_by_type_and_error_class_without_text():
    d = _fresh_db()
    with d.session() as s:
        for jt, err in (("improve.weekly", f"TypeError: {PRIVATE['error_text']}"),
                        ("improve.weekly", f"TypeError: {PRIVATE['error_text']}"),
                        ("mjs.scan", f"budget exceeded: {PRIVATE['error_text']}"),
                        ("radar.scan", f"{PRIVATE['error_text']} with no class")):
            s.add(Job(agent="a", job_type=jt, inputs={}, status=JobStatus.DEAD,
                      last_error=err, finished_at=NOW - timedelta(hours=2)))
        s.add(Job(agent="a", job_type="old.type", inputs={}, status=JobStatus.DEAD,
                  last_error="ValueError: x", finished_at=NOW - timedelta(hours=30)))
    ev = pe.dead_letters(d, now=NOW)
    got = {(g["job_type"], g["error_class"]): g["count"] for g in ev["by_type"]}
    assert got == {("improve.weekly", "TypeError"): 2, ("mjs.scan", "BudgetExceeded"): 1,
                   ("radar.scan", "unclassified"): 1}, got
    assert PRIVATE["error_text"] not in json.dumps(ev), ev
    assert pe.error_class("brambleloop.x.PaidCallUnresolved: y") == "PaidCallUnresolved"
    assert pe.error_class("lower.case: y") == "unclassified"
    assert pe.error_class(None) == "unclassified"


def test_certification_and_loop_count_useful_work_apart_from_noops():
    d = _fresh_db()
    with d.session() as s:
        s.add(Product(slug="cert-a", title="A"))
        s.add(AuditLog(actor="gate", action="gate.certified", artifact="cert-a@1.0.0",
                       at=NOW - timedelta(days=1)))
        recent = NOW - timedelta(hours=3)
        s.add(Job(agent="a", job_type="mjs.scan", inputs={}, outputs={"work_done": 3},
                  status=JobStatus.DONE, created_at=recent, finished_at=recent))
        s.add(Job(agent="a", job_type="mjs.scan", inputs={}, outputs={"work_done": 0},
                  status=JobStatus.DONE, created_at=recent, finished_at=recent))
        s.add(Job(agent="a", job_type="laura.executive_tick", inputs={},
                  outputs={"work_done": 1, "delegated": 0}, status=JobStatus.DONE,
                  created_at=recent, finished_at=recent))
        s.add(Job(agent="a", job_type="cir.draft", inputs={"laura": {"priority": "k"}},
                  outputs={"work_done": 1}, status=JobStatus.DONE, created_at=recent,
                  finished_at=recent))
    cert = pe.certification(d, now=NOW)
    assert cert["count_by_stage"]["SELECTED"] == 1 and cert["slugs_by_stage"]["SELECTED"] == [
        "cert-a"], cert
    assert cert["certify_outcomes_7d"]["gate.certified"]["count"] == 1, cert
    loop = {x["stage"]: x for x in pe.autonomy_loop(d, now=NOW)["stages"]}
    assert [x[0] for x in pe.LOOP_STAGES] == list(loop), list(loop)
    assert (loop["market_observation"]["useful_completed"],
            loop["market_observation"]["noop_completed"]) == (1, 1), loop["market_observation"]
    assert loop["laura_decision"]["useful_completed"] == 1, loop["laura_decision"]
    assert (loop["delegation"]["useful_completed"], loop["delegation"]["noop_completed"]) == (
        0, 1), loop["delegation"]                     # a tick that delegated nothing is a no-op
    assert loop["execution"]["useful_completed"] == 1, loop["execution"]
    assert loop["original_product"]["useful_completed"] == 1, loop["original_product"]
    assert loop["verified_lesson"]["evidenced"] is False, loop["verified_lesson"]


# ---- 2. the endpoint's credential ------------------------------------------------------------


def test_the_endpoint_refuses_anonymous_callers_and_the_operator_token():
    c = client()
    url = "/api/readback/evidence"
    with both_tokens():
        assert security.requires_operator("GET", url) and url not in security.PUBLIC_GET_ROUTES
        assert security.readback_route(url)
        r = c.get(url)
        assert r.status_code == 401, (r.status_code, r.text[:200])
        r = c.get(url, headers=bearer(OPS_TOKEN))
        assert r.status_code == 401, ("the operator token must not open it", r.status_code)
        assert c.get(url, headers=bearer("x" * 48)).status_code == 401
        r = c.get(url, headers=bearer(READBACK_TOKEN))
        assert r.status_code == 200, (r.status_code, r.text[:300])
        assert r.headers.get("cache-control") == "no-store"
        body = r.json()
        assert body["read_only"] is True and set(pe.SECTIONS) <= set(body), sorted(body)
        assert c.post(url, headers=bearer(READBACK_TOKEN)).status_code == 405
    # Absent means closed -- for every caller, with or without the operator token set.
    with _env(**{opsauth.TOKEN_VAR: OPS_TOKEN, readbackauth.TOKEN_VAR: None}):
        for h in ({}, bearer(OPS_TOKEN), bearer(READBACK_TOKEN)):
            assert c.get(url, headers=h).status_code == 503, h
    with _env(**{readbackauth.TOKEN_VAR: "short" * 6}):           # 30 < 32 characters
        assert c.get(url, headers=bearer("short" * 6)).status_code == 503
    # A readback value equal to the operator token would make it an operator token: closed.
    with _env(**{opsauth.TOKEN_VAR: OPS_TOKEN, readbackauth.TOKEN_VAR: OPS_TOKEN}):
        assert not readbackauth.configured()
        assert readbackauth.token_health()["reason"] == "equal to the operator token"
        assert c.get(url, headers=bearer(OPS_TOKEN)).status_code == 503


def test_readbackauth_rules():
    env = {readbackauth.TOKEN_VAR: READBACK_TOKEN, opsauth.TOKEN_VAR: OPS_TOKEN}
    readbackauth.check(READBACK_TOKEN, env)
    readbackauth.check("Bearer " + READBACK_TOKEN, env)
    for bad in (None, "", OPS_TOKEN, "Bearer " + OPS_TOKEN, READBACK_TOKEN[:-1], "té"):
        try:
            readbackauth.check(bad, env)
        except readbackauth.ReadbackAuthRefused as e:
            assert READBACK_TOKEN not in str(e) and OPS_TOKEN not in str(e)
        else:
            raise AssertionError(f"accepted {bad!r:.12}")
    try:
        readbackauth.check(READBACK_TOKEN, {})
    except readbackauth.ReadbackAuthUnavailable as e:
        assert READBACK_TOKEN not in str(e)
    else:
        raise AssertionError("an unset token must close the endpoint")
    assert readbackauth.MIN_TOKEN_LENGTH >= opsauth.MIN_TOKEN_LENGTH
    assert READBACK_TOKEN not in json.dumps(readbackauth.token_health(env))
    # The operator credential check never accepts the readback value.
    try:
        opsauth.check(READBACK_TOKEN, env)
    except opsauth.OpsAuthRefused:
        pass
    else:
        raise AssertionError("the operator gate accepted the readback token")
    with both_tokens():
        assert security.presents_operator_credential("Bearer " + OPS_TOKEN)
        assert not security.presents_operator_credential("Bearer " + READBACK_TOKEN)


# ---- 3. read-only: the readback token opens nothing else -----------------------------------


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _db_fingerprint() -> tuple:
    with main.db.session() as s:
        return (s.scalar(select(func.count()).select_from(Job)),
                s.scalar(select(func.count()).select_from(AuditLog)),
                s.scalar(select(func.count()).select_from(OwnerAction)),
                s.scalar(select(func.count()).select_from(Incident)))


def _shape(text: str):
    try:
        body = json.loads(text)
    except ValueError:
        return None

    def keys(v, p=""):
        if isinstance(v, dict):
            for k, x in v.items():
                yield p + k
                yield from keys(x, p + k + ".")
        elif isinstance(v, list):
            for x in v:
                yield from keys(x, p)
    return sorted(set(keys(body)))


def _is_public(method: str, path: str) -> bool:
    if method == "GET":
        return (not security.requires_operator("GET", path)
                and not security.owner_session_route(path))
    return (method, path) in security.PUBLIC_MUTATING_ROUTES


def test_the_readback_token_is_refused_on_every_other_route():
    c = client()
    routes = [(p, m) for p, methods, _ in security.iter_api_routes(main.app)
              for m in sorted(methods - {"HEAD", "OPTIONS"}) if not security.readback_route(p)]
    gated = [(p, m) for p, m in routes if not _is_public(m, p)]
    public_reads = [(p, m) for p, m in routes if m == "GET" and _is_public(m, p)]
    assert len(gated) > 200 and len(public_reads) >= 5, (len(gated), len(public_reads))
    bad = []
    with both_tokens():
        # Every gated route, every method: refused, nothing changed, nothing echoed.
        before = _db_fingerprint()
        for path, method in gated:
            r = c.request(method, _concrete(path), headers=bearer(READBACK_TOKEN), json={})
            if r.status_code not in (401, 403, 503):
                bad.append(f"{method} {path}: {r.status_code} with the readback token")
            if READBACK_TOKEN in r.text:
                bad.append(f"{method} {path}: echoed the token")
        after = _db_fingerprint()
        # A public read: the readback token unlocks nothing beyond the anonymous view.
        for path, _m in public_reads:
            url = _concrete(path)
            r = c.get(url, headers=bearer(READBACK_TOKEN))
            anon = c.get(url)
            if r.status_code != anon.status_code or _shape(r.text) != _shape(anon.text):
                bad.append(f"GET {path}: the readback token changed the response "
                           f"({anon.status_code} -> {r.status_code})")
            if READBACK_TOKEN in r.text:
                bad.append(f"GET {path}: echoed the token")
    assert not bad, bad[:40]
    assert after == before, "a request carrying the readback token changed the database"


def test_public_verify_shows_only_name_and_verdict_of_the_evidence_checks():
    c = client()
    with both_tokens():
        for headers in ({}, bearer(READBACK_TOKEN)):
            body = c.get("/api/verify", headers=headers).json()
            ev = body.get("evidence_checks")
            assert isinstance(ev, list) and [x["check"] for x in ev] == list(pe.CHECK_NAMES), body
            assert all(set(x) == {"check", "ok"} and isinstance(x["ok"], bool) for x in ev), ev
        full = c.get("/api/verify", headers=bearer(OPS_TOKEN)).json()
        assert all("evidence" in x for x in full["evidence_checks"]), full["evidence_checks"]


# ---- 4. no private fields; 5. the token is never echoed ------------------------------------


def test_the_evidence_carries_no_private_field():
    c = client()
    with both_tokens():
        r = c.get("/api/readback/evidence", headers=bearer(READBACK_TOKEN))
    assert r.status_code == 200, r.status_code
    text = r.text
    body = r.json()
    # Non-vacuity: the evidence did read the seeded rows that carry the private content.
    dl = {g["job_type"]: g for g in body["dead_letters_24h"]["by_type"]}
    assert dl["improve.weekly"]["newest_job_ids"] == [_STATE["dead_id"]], dl
    assert dl["improve.weekly"]["error_class"] == "TypeError", dl
    assert body["paid_call_dedupe"]["intents_in_window"] >= 1, body["paid_call_dedupe"]
    assert body["publishing_halt"]["systemic_halt_open"] == 1, body["publishing_halt"]
    fams = body["publishing_halt"]["per_product_halting_by_family"]
    assert fams.get("stale-artefact", {}).get("slugs") == ["readback-slug-a"], fams
    execution = {x["stage"]: x for x in body["autonomy_loop"]["stages"]}["execution"]
    assert execution["useful_completed"] >= 1, execution
    leaked = [k for k, v in PRIVATE.items() if v in text]
    assert not leaked, leaked
    keys = set(k.rsplit(".", 1)[-1] for k in _shape(text))
    assert not keys & set(FORBIDDEN_KEYS), sorted(keys & set(FORBIDDEN_KEYS))
    assert OPS_TOKEN not in text and READBACK_TOKEN not in text


def _fetcher(c, echo: bool = False):
    def fetch(url, headers=None):
        r = c.get(url.replace("https://prod.invalid", ""), headers=headers or {})
        try:
            body = r.json()
        except ValueError:
            body = None
        if echo and isinstance(body, dict):
            body["echo"] = (headers or {}).get("Authorization")  # a hostile server
        return r.status_code, body
    return fetch


def test_readback_evidence_cli_never_prints_the_token_and_keeps_unknown_apart():
    import readback

    c = client()
    with both_tokens():
        out = readback.run_evidence(url="https://prod.invalid", fetch=_fetcher(c, echo=True))
        assert out["token_present"] is True and out["evidence_http"] == 200, out["items"]
        dumped = json.dumps(out)
        assert READBACK_TOKEN not in dumped and "[redacted]" in dumped
        by = {i["item"]: i for i in out["items"]}
        assert by["dead letters in 24 h by job type"]["verdict"] == readback.FAIL, by
        assert "improve.weekly:TypeError" in by["dead letters in 24 h by job type"]["detail"]
        assert by["publishing halt clear"]["verdict"] == readback.FAIL, by  # the seeded halt
        assert all(i["verdict"] in (readback.PASS, readback.FAIL, readback.UNKNOWN)
                   for i in out["items"]) and len(out["items"]) == 11, out["items"]
        # An unreadable section is UNKNOWN, never PASS.
        v, _ = readback._judge_section("weekly_jobs", {"readable": False}, True)
        assert v == readback.UNKNOWN
        v, _ = readback._judge_section("paid_call_dedupe", {"readable": True}, None)
        assert v == readback.UNKNOWN
        # The CLI path: stdout and stderr both clean.
        buf_out, buf_err = io.StringIO(), io.StringIO()
        saved = readback._fetch
        readback._fetch = _fetcher(c, echo=True)
        try:
            with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
                code = readback.main(["--evidence", "--url", "https://prod.invalid"])
        finally:
            readback._fetch = saved
        assert code == 5, code
        assert READBACK_TOKEN not in buf_out.getvalue() + buf_err.getvalue()
        assert "FAIL" in buf_err.getvalue() and json.loads(buf_out.getvalue())["read_only"]
    # Without the token every evidence item is UNKNOWN -- never PASS.
    with _env(**{opsauth.TOKEN_VAR: OPS_TOKEN, readbackauth.TOKEN_VAR: None}):
        out = readback.run_evidence(url="https://prod.invalid", fetch=_fetcher(c))
    ev_items = [i for i in out["items"] if "section" in i]
    assert len(ev_items) == len(readback.EVIDENCE_ITEMS), out["items"]
    assert {i["verdict"] for i in ev_items} == {readback.UNKNOWN}, ev_items
    assert out["verdict"] != readback.PASS and out["token_present"] is False
    # The public checks are still read anonymously, name and verdict only.
    pub = [i for i in out["items"] if i["item"].startswith("/api/verify ")]
    assert len(pub) == 4 and all(i["verdict"] in (readback.PASS, readback.FAIL)
                                 for i in pub), pub


def test_readback_evidence_names_the_checks_the_server_serves():
    import readback

    assert tuple(readback.EVIDENCE_CHECKS) == tuple(pe.CHECK_NAMES)
    assert {s for _i, s, _k in readback.EVIDENCE_ITEMS} == set(pe.SECTIONS)
    assert readback.READBACK_TOKEN_VAR == readbackauth.TOKEN_VAR
    assert readback.EVIDENCE_ENDPOINT in security.READBACK_ROUTES


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
            print("FAIL", name, f"{type(e).__name__}: {str(e)[:2500]}", flush=True)
    print(f"{len(tests) - fails}/{len(tests)} passed in {time.monotonic() - t0:.0f}s")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
