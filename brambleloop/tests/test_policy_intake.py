"""An operator's reading of an Etsy policy page is recorded and closes the incident at once.

Etsy refuses automated retrieval, so the `policy_stale:<source>` incidents can only be closed
by a person reading the page. POST /api/policy/snapshot is that intake: authenticated like
every other operator POST, restricted to the watched sources, refusing an empty reading,
storing a digest and never the text, and resolving the incident with the same fields the
watch uses -- unless the reading is itself stale.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.TemporaryDirectory()
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{_TMP.name}/policy_intake.sqlite"
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ["BRAMBLELOOP_RUNNER_START_DELAY"] = "0"
OPS_TOKEN = "operator-token-for-policy-intake-0123456789"
os.environ["BRAMBLELOOP_OPS_TOKEN"] = OPS_TOKEN

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from brambleloop.app import main as app_main  # noqa: E402
from brambleloop.core.models import AuditLog, Incident, PolicySnapshot  # noqa: E402
from brambleloop.gates import platform_policy as PP  # noqa: E402

DB = app_main.db
DB.create_all()
AUTH = {"Authorization": f"Bearer {OPS_TOKEN}"}
PAGE = "SECRET-PAGE-TEXT: sellers must disclose AI assistance where it contributed."


def _open_incident(source: str) -> int:
    with DB.session() as s:
        inc = Incident(severity="P2", signature=f"policy_stale:{source}",
                       summary=f"Etsy {source} is stale", detail={"source": source})
        s.add(inc)
        s.flush()
        return inc.id


def _incident(inc_id: int) -> Incident:
    with DB.session() as s:
        inc = s.get(Incident, inc_id)
        s.expunge(inc)
        return inc


def test_a_current_page_reading_closes_the_incident_with_the_watch_fields():
    inc_id = _open_incident("seller_policy")
    with TestClient(app_main.app) as client:
        r = client.post("/api/policy/snapshot", headers=AUTH, json={
            "source": "seller_policy", "text": PAGE, "version": "2026-09-27",
            "summary": "AI disclosure required", "read_by": "owner"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current"] is True and inc_id in body["incidents_resolved"]
    assert body["basis"] == "page"
    assert PAGE not in r.text
    inc = _incident(inc_id)
    assert inc.resolved is True
    assert "resolution" in inc.detail and "resolved_at" in inc.detail
    assert "owner" in inc.detail["resolution"]
    with DB.session() as s:
        snap = s.get(PolicySnapshot, body["id"])
        assert snap.digest == PP.digest_of(PAGE)
        assert snap.detail["read_by"] == "owner" and snap.detail["basis"] == "page"
        assert PAGE not in str(snap.summary) + str(snap.detail)
        audits = list(s.scalars(select(AuditLog).where(
            AuditLog.action == "policy.page_reading_recorded")))
        assert audits and all(PAGE not in str(a.detail) for a in audits)


def test_a_stale_reading_is_recorded_but_does_not_close_the_incident():
    inc_id = _open_incident("advertising_rules")
    old = (date.today() - timedelta(days=PP.MAX_AGE_DAYS + 5)).isoformat()
    with TestClient(app_main.app) as client:
        r = client.post("/api/policy/snapshot", headers=AUTH, json={
            "source": "advertising_rules", "text": PAGE, "version": old,
            "summary": "", "read_by": "owner", "checked_on": old})
    assert r.status_code == 200, r.text
    assert r.json()["current"] is False and r.json()["incidents_resolved"] == []
    assert _incident(inc_id).resolved is False


def test_unknown_source_empty_text_and_missing_reader_are_refused():
    with TestClient(app_main.app) as client:
        r = client.post("/api/policy/snapshot", headers=AUTH, json={
            "source": "etsy_everything", "text": PAGE, "read_by": "owner"})
        assert r.status_code == 400 and "unknown policy source" in r.json()["error"]
        r = client.post("/api/policy/snapshot", headers=AUTH, json={
            "source": "seller_policy", "text": "   ", "read_by": "owner"})
        assert r.status_code == 400
        r = client.post("/api/policy/snapshot", headers=AUTH, json={
            "source": "seller_policy", "text": PAGE, "read_by": ""})
        assert r.status_code == 400


def test_the_intake_is_operator_authenticated_like_every_other_post():
    with TestClient(app_main.app) as client:
        for headers in ({}, {"Authorization": "Bearer wrong-token-of-sufficient-length"}):
            r = client.post("/api/policy/snapshot", headers=headers, json={
                "source": "seller_policy", "text": PAGE, "read_by": "owner"})
            assert r.status_code == 401, r.text
            assert PAGE not in r.text
    previous = os.environ.pop("BRAMBLELOOP_OPS_TOKEN")
    try:
        with TestClient(app_main.app) as client:
            r = client.post("/api/policy/snapshot", headers=AUTH, json={
                "source": "seller_policy", "text": PAGE, "read_by": "owner"})
        assert r.status_code == 503
    finally:
        os.environ["BRAMBLELOOP_OPS_TOKEN"] = previous


def test_the_function_refuses_what_the_endpoint_refuses():
    for kwargs in ({"source": "nope", "text": PAGE, "read_by": "x"},
                   {"source": "seller_policy", "text": "", "read_by": "x"},
                   {"source": "seller_policy", "text": PAGE, "read_by": " "},
                   {"source": "seller_policy", "text": PAGE, "read_by": "x",
                    "checked_on": (date.today() + timedelta(days=2)).isoformat()}):
        try:
            PP.record_page_reading(DB, **kwargs)
        except PP.PolicyRefused:
            continue
        raise AssertionError(f"accepted {kwargs}")


def test_api_policy_carries_the_dated_knowledge():
    from brambleloop.gates import policy_knowledge

    with TestClient(app_main.app) as client:
        r = client.get("/api/policy")
    assert r.status_code == 200
    assert r.json()["knowledge"] == policy_knowledge.describe()


def test_the_script_sends_the_fields_the_endpoint_reads():
    import argparse
    import importlib.util

    spec = importlib.util.spec_from_file_location("record_policy",
                                                  ROOT / "scripts" / "record_policy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    body = mod.build_body(argparse.Namespace(source="seller_policy", version="v", summary="s",
                                             read_by="owner", checked_on=""), PAGE)
    assert set(body) == {"source", "text", "version", "summary", "read_by"}
    assert "not evasion" in mod.__doc__


def test_the_new_read_endpoints_answer_with_unmeasured_rather_than_numbers():
    with TestClient(app_main.app) as client:
        leading = client.get("/api/leading")
        cohorts = client.get("/api/cohorts")
        acceptance = client.get("/api/acceptance")
        blind = client.get("/api/blind-review")
    assert leading.status_code == 200 and leading.json()["success"]["claimable"] is False
    assert cohorts.status_code == 200
    assert cohorts.json()["cohorts"]["source"]["status"] == "OWNER-GATED"
    assert acceptance.status_code == 200
    assert acceptance.json()["current"]["verdict"] == "FAIL"
    assert acceptance.json()["evidence_kind"] == "api_gallery_traversal"
    assert blind.status_code == 200 and "counts" in blind.json()


def test_zz_five_current_readings_through_the_intake_open_rendered_pages():
    """W4-B2CLOSE: the intake's audited readings are what opens #35/#39's gate (finding 2)."""
    from brambleloop.build2 import executor
    from brambleloop.gates import policy_reader

    gate = executor.GATE_BY_KEY["rendered_pages"]
    legal = policy_reader.external_sources()
    assert len(legal) == 5, legal
    with TestClient(app_main.app) as client:
        for i, source in enumerate(legal):
            if i == len(legal) - 1:
                assert gate.open(DB, {}) is False, "opened before the fifth reading"
            r = client.post("/api/policy/snapshot", headers=AUTH, json={
                "source": source, "text": PAGE, "version": "2026-10-10",
                "summary": "read in a browser", "read_by": "owner"})
            assert r.status_code == 200, r.text
    assert PP.page_readings_status(DB)["open"] is True
    assert gate.open(DB, {}) is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
