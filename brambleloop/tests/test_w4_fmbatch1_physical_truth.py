"""F-089: Physical Truth Dashboard -- per-product tester, version, stage, due, findings,
deltas and launch-blocked, over the tester plan and the recorded physical tests."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="phys_truth_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'p.db')}"
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
os.environ.pop("BRAMBLELOOP_EMBEDDED_WORKER", None)
os.environ.pop("BRAMBLELOOP_OPS_TOKEN", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the physical-truth harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, PhysicalTest  # noqa: E402
from brambleloop.quality import physical_truth as PT  # noqa: E402

TODAY = date(2026, 11, 20)


def _seed(db):
    with db.session() as s:
        s.add(AuditLog(actor="release", action=PT.PLAN_ACTION, detail={
            "demands": [
                {"product_slug": "hex-coaster", "risk_class": "B", "needed_by": "2026-12-01",
                 "must_start_by": "2026-11-10"},
                {"product_slug": "bear-amigurumi", "risk_class": "C",
                 "needed_by": "2026-11-15", "must_start_by": "2026-10-20"},
                {"product_slug": "cowl", "risk_class": "B", "needed_by": "2026-12-20",
                 "must_start_by": "2026-12-01"}],
            "assignments": [{"product_slug": "cowl", "tester": "tester-7"}],
            "unassigned": [{"product_slug": "bear-amigurumi",
                            "why": ["no recorded tester has tested 'amigurumi'"]}]}))
        s.add(PhysicalTest(product_slug="hex-coaster", version="1.0.0", tester_ref="tester-3",
                           completed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                           passed=False, measured={
                               "estimated_metres": {"MC": 100.0}, "measured_metres": {"MC": 130.0},
                               "factor": 1.3, "size_agrees": False,
                               "findings": [{"code": "size_disagreement", "severity": "high",
                                             "message": "came out 18% larger"}]},
                           notes="worked to pattern"))
        s.add(PhysicalTest(product_slug="hex-coaster", version="1.0.1", tester_ref="tester-3",
                           completed_at=None, passed=None, measured={}))
        s.add(PhysicalTest(product_slug="tote", version="2.0.0", tester_ref="tester-9",
                           completed_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                           passed=True, measured={"estimated_metres": {"A": 200.0},
                                                  "measured_metres": {"A": 190.0},
                                                  "factor": 0.95, "size_agrees": True}))


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def test_rows_carry_every_field_and_block_until_a_pass():
    db = _db()
    _seed(db)
    out = PT.dashboard(db, today=TODAY)
    rows = {r["product_slug"]: r for r in out["rows"]}
    assert set(rows) == {"hex-coaster", "bear-amigurumi", "cowl", "tote"}
    hx = rows["hex-coaster"]
    # A failed then in-progress product: latest version, in progress, still blocked.
    assert hx["version"] == "1.0.1" and hx["stage"] == "in_progress" and hx["samples"] == 2
    assert hx["launch_blocked"] is True and hx["tester"] == "tester-3"
    bear = rows["bear-amigurumi"]
    assert bear["stage"] == "not_started" and bear["assignment"] == "unassigned"
    assert bear["unassigned_why"] and bear["overdue"] is True and bear["launch_blocked"]
    cowl = rows["cowl"]
    assert cowl["assignment"] == "planned" and cowl["tester"] == "tester-7"
    assert cowl["due"] == "2026-12-20" and cowl["overdue"] is False
    tote = rows["tote"]
    assert tote["stage"] == "passed" and tote["launch_blocked"] is False
    assert tote["deltas"]["yarn_by_colour"] == {"A": -0.05}
    assert out["summary"] == {"products": 4, "launch_blocked": 3, "passed": 1,
                              "unassigned": 1, "overdue": 1}


def test_failed_sample_is_a_finding_not_a_pass():
    db = _db()
    with db.session() as s:
        s.add(PhysicalTest(product_slug="hat", version="1", tester_ref="t",
                           completed_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
                           passed=False, measured={
                               "estimated_metres": {"MC": 100.0},
                               "measured_metres": {"MC": 130.0}, "size_agrees": False,
                               "findings": [{"code": "size_disagreement"}]}))
    out = PT.dashboard(db, today=TODAY)
    r = out["rows"][0]
    assert r["stage"] == "failed" and r["launch_blocked"] is True
    assert r["findings"][0]["code"] == "size_disagreement"
    assert r["deltas"]["yarn_by_colour"] == {"MC": 0.3} and r["deltas"]["size_agrees"] is False
    assert r["risk_class"] == "unknown"          # no plan: never treated as Class A
    assert "no tester plan" in out["note"]


def test_class_a_products_are_not_listed_and_empty_db_is_empty():
    db = _db()
    with db.session() as s:
        s.add(AuditLog(actor="r", action=PT.PLAN_ACTION, detail={"demands": [
            {"product_slug": "simple", "risk_class": "A", "needed_by": "2026-12-01"}]}))
    assert PT.dashboard(db, today=TODAY)["rows"] == []
    assert PT.dashboard(_db(), today=TODAY)["summary"]["products"] == 0


def test_api_is_operator_only():
    from fastapi.testclient import TestClient

    from brambleloop.app import main, security
    from brambleloop.core import opsauth

    assert "/api/physical-truth" in security.OPERATOR_GET_ROUTES
    main.db.create_all()
    c = TestClient(main.app)
    token = "p" * 40
    os.environ[opsauth.TOKEN_VAR] = token
    try:
        assert c.get("/api/physical-truth").status_code == 401
        r = c.get("/api/physical-truth", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert set(r.json()) >= {"rows", "summary", "note"}
    finally:
        os.environ.pop(opsauth.TOKEN_VAR, None)


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("ok", n)
