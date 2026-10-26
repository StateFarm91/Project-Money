"""F-171 / production 2026-10-26: a model provider that answers its probe with a failure is
FAIL or DEGRADED in the smoke matrix and /api/verify, never PASS; an incident names the
provider and reason class; no error body leaks."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import _opread  # INTEG7 (R-1): owner-only reads present the operator credential
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_w4_smoke as base  # noqa: E402
from brambleloop.core.models import AuditLog, Incident  # noqa: E402
from brambleloop.ops import provider_health as PH, smoke  # noqa: E402

NOW = base.NOW
SECRET = "sk-" + "ant-api03-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"  # built at runtime; never a literal (test_secret_scan)
CREDIT = ('Error code: 400 - {"type":"error","error":{"type":"invalid_request_error",'
          '"message":"Your credit balance is too low to access the Anthropic API."},'
          '"request_id":"req_011CUVabcdefGHIJKLmnop"} key=' + SECRET)


def _with_probe(reason, ok=False, actions=("model.probe", "vision.probe")):
    db = base._healthy(base._db())
    with db.session() as s:
        for a in actions:
            s.add(AuditLog(actor="orchestrator", action=a, at=NOW - timedelta(minutes=5),
                           detail={"ok": ok, "reason": reason}))
    return db


def test_classify_reason_classes():
    assert PH.classify(CREDIT) == "credit"
    assert PH.classify("HTTP 401: invalid x-api-key") == "auth"
    assert PH.classify("no ANTHROPIC_API_KEY in this environment") == "no_key"
    assert PH.classify("HTTP 429 rate limit") == "rate_limit"
    assert PH.classify("HTTP 529 overloaded_error") == "overloaded"
    assert PH.classify("budget: monthly ceiling") == "budget"
    assert PH.classify("read timed out") == "network"
    assert PH.classify("something else") == "other"


def test_credit_exhaustion_fails_the_matrix_although_the_probe_ran():
    m = smoke.smoke_matrix(_with_probe(CREDIT), now=NOW)
    c = base._by_name(m)
    assert c["probe_ran:model.probe"]["verdict"] == "PASS"       # the machinery ran
    ph = c["provider_health:model.probe"]
    assert ph["verdict"] == "FAIL" and m["verdict"] == "FAIL"
    assert ph["evidence"]["reason_class"] == "credit"
    assert ph["evidence"]["owner_action_required"] is True
    assert "provider_health:vision.probe" in m["failing"]
    body = json.dumps(m)
    assert SECRET not in body and "req_011CUVabcdefGHIJKLmnop" not in body
    assert "credit balance" not in json.dumps(ph)                 # class only, no prose


def test_transient_failure_is_degraded_and_ok_passes():
    m = smoke.smoke_matrix(_with_probe("HTTP 529 overloaded_error"), now=NOW)
    assert base._by_name(m)["provider_health:model.probe"]["verdict"] == "DEGRADED"
    assert m["verdict"] == "DEGRADED" and m["degraded"]
    ok = smoke.smoke_matrix(_with_probe("", ok=True), now=NOW)
    assert ok["verdict"] == "PASS", ok["failing"]


def test_redact_removes_keys_ids_and_addresses():
    r = PH.redact(CREDIT + " owner@example.com Bearer abc.def")
    assert SECRET not in r and "req_011" not in r and "@" not in r and "abc.def" not in r


def test_incident_names_provider_and_class_and_resolves_on_ok():
    db = _with_probe(CREDIT)
    with db.session() as s:
        out = PH.reconcile(db, s, now=NOW)
    assert out["failing"] == ["provider-health:anthropic:credit"]
    with db.session() as s:
        inc = s.query(Incident).filter(Incident.signature == "provider-health:anthropic:credit"
                                       ).one()
        assert inc.severity == "P1" and not inc.resolved
        assert inc.detail["owner_action_required"] is True
        assert SECRET not in json.dumps(inc.detail) and "credit balance" not in inc.summary
        for a in ("model.probe", "vision.probe"):
            s.add(AuditLog(actor="orchestrator", action=a, at=NOW, detail={"ok": True}))
    with db.session() as s:
        again = PH.reconcile(db, s, now=NOW + timedelta(minutes=1))
    assert again["failing"] == [] and again["resolved"] == ["provider-health:anthropic:credit"]


def test_verify_reports_degraded_with_the_provider_named():
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="fmb1ph_")
    os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{tmp}/v.db"
    os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(tmp, "a")
    from fastapi.testclient import TestClient

    from brambleloop.agents.registry import Registry
    from brambleloop.app import main

    main.db.create_all()
    Registry(main.db).seed_defaults()
    with main.db.session() as s:
        for a in ("model.probe", "vision.probe"):
            s.add(AuditLog(actor="orchestrator", action=a,
                           at=datetime.now(timezone.utc), detail={"ok": False,
                                                                  "reason": CREDIT}))
    anon = TestClient(main.app).get("/api/verify").json()     # INTEG7 (R-1): projected
    assert set(anon) <= {"ok", "checks"} and SECRET not in json.dumps(anon)
    body = _opread.get(TestClient(main.app), "/api/verify").json()
    assert body["status"] in ("DEGRADED", "FAIL")
    ph = {c["check"]: c for c in body["provider_health"]}
    assert ph["provider_health:model.probe"]["verdict"] == "FAIL"
    assert ph["provider_health:model.probe"]["evidence"]["provider"] == "anthropic"
    assert SECRET not in json.dumps(body)
    smoke_resp = _opread.get(TestClient(main.app), "/api/verify/smoke")
    assert smoke_resp.status_code == 503 and smoke_resp.json()["verdict"] != "PASS"


def test_review_n6_unknown_outranks_degraded_in_the_smoke_headline():
    real = smoke.continuity_proof
    smoke.continuity_proof = lambda s, now: smoke._check(
        "continuity_restore_proven", smoke.UNKNOWN, "not yet judged", {})
    try:
        m = smoke.smoke_matrix(_with_probe("HTTP 529 overloaded_error"), now=NOW)
    finally:
        smoke.continuity_proof = real
    assert m["degraded"] and m["unknown"]
    assert m["verdict"] == "UNKNOWN", m["verdict"]


def test_review_n6_verify_status_is_ok_only_when_the_smoke_matrix_passes():
    from brambleloop.app import main

    st = main._verify_status
    assert st(True, {"verdict": "PASS"}, []) == "OK"
    assert st(True, {"verdict": "FAIL"}, []) == "FAIL"
    assert st(True, {"verdict": "UNKNOWN"}, []) == "UNKNOWN"
    assert st(True, {"verdict": "DEGRADED"}, []) == "DEGRADED"
    assert st(True, {"verdict": "PASS"}, [{"verdict": "FAIL"}]) == "DEGRADED"
    assert st(False, {"verdict": "PASS"}, []) == "FAIL"


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
