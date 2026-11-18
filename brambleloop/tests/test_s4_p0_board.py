"""S4: the P0 command board (`/api/cc/p0-board`). Read-only, owner-gated, honest levels.

The harness is the Command Center's own (test_v11_cc_views): the real app, an owner session,
no network.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_TMP = tempfile.mkdtemp(prefix="s4_p0_board_")
os.environ["BRAMBLELOOP_DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'cc.db')}"
os.environ.pop("DATABASE_URL", None)
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_EMBEDDED_WORKER"] = "0"
os.environ.pop("BRAMBLELOOP_REQUIRE_POSTGRES", None)
for _k in list(os.environ):
    if _k.startswith(("ANTHROPIC_API", "ETSY", "OPENAI", "REPLICATE", "FAL_", "GEMINI",
                      "RAILWAY_GIT", "BRAMBLELOOP_COMMIT", "GIT_COMMIT", "SOURCE_COMMIT")):
        os.environ.pop(_k)


def _no_network(*_a, **_k):
    raise OSError("network refused by the board harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from brambleloop.app import main  # noqa: E402
from brambleloop.app.command_center import auth  # noqa: E402
from brambleloop.app.command_center import p0_board as B  # noqa: E402
from brambleloop.core import build, opsauth  # noqa: E402
from brambleloop.core.models import (AuditLog, Customer, Incident, Job, JobStatus,  # noqa: E402
                                     Listing, Order, OwnerAction, PatternVersion, Product)

OPS = "b" * 40
PASS = "owner passphrase for the board harness"
os.environ[opsauth.TOKEN_VAR] = OPS
os.environ[auth.PASSPHRASE_VAR] = auth.hash_passphrase(PASS, iterations=100_000)
main.db.create_all()
DB = main.db
NOW = datetime.now(timezone.utc)
SHA = "0123456789abcdef0123456789abcdef01234567"


class _Deployed:
    """The process reports the commit it was built from, as Railway sets it."""
    def __enter__(self):
        self.p = patch.object(build, "commit", lambda env=None: SHA)
        self.p.start()

    def __exit__(self, *a):
        self.p.stop()


def _counts():
    with DB.session() as s:
        return {m.__name__: s.scalar(select(func.count()).select_from(m))
                for m in (AuditLog, Job, Listing, Order, OwnerAction, Incident)}


def test_every_section_reads_or_says_why_and_nothing_is_written():
    before = _counts()
    v = B.view(DB)
    assert _counts() == before, "the board wrote a row"
    assert v["read_only"] is True and v["vocabulary"] == list(B.LEVELS)
    assert v["not_provable_here"] == ["INDEPENDENTLY REVIEWED", "INTEGRATED"]
    assert set(v["sections"]) == {name for name, _ in B.SECTIONS}
    for name, sec in v["sections"].items():
        assert sec["state"], name
        assert sec["level"] in (None, *B.LEVELS), (name, sec["level"])
        assert sec["not_provable_here"] == list(B.NOT_PROVABLE_HERE)
        # No commit reported: nothing is DEPLOYED or above.
        assert sec["level"] in (None, B.CODE_BUILT), (name, sec["level"])
        if sec["level"] is None:
            assert sec["why"].startswith("could not be read"), name


def test_levels_never_skip_a_rung_and_never_claim_review_or_integration():
    assert B._level(False, running=True, verified=True, commerce=True)["level"] == B.CODE_BUILT
    assert B._level(True)["level"] == B.DEPLOYED
    assert B._level(True, running=False, verified=True, commerce=True)["level"] == B.DEPLOYED
    assert B._level(True, running=True, verified=False, commerce=True)["level"] == B.RUNNING
    top = B._level(True, running=True, verified=True, commerce=True)
    assert top["level"] == B.COMMERCE
    assert set(top["proved_by"]) == {B.CODE_BUILT, B.DEPLOYED, B.RUNNING, B.PROD_VERIFIED,
                                     B.COMMERCE}
    assert B.REVIEWED not in top["proved_by"] and B.INTEGRATED not in top["proved_by"]


def _health(minutes_ago, state):
    with DB.session() as s:
        s.add(Job(agent="orchestrator", job_type="ops.health", status=JobStatus.DONE,
                  inputs={}, outputs={"state": state, "bad": [], "why": "t",
                                      "activity": "work_completed"},
                  finished_at=NOW - timedelta(minutes=minutes_ago)))


def test_health_reaches_production_verified_only_on_a_fresh_healthy_sweep():
    with _Deployed():
        _health(300, "healthy")                                # stale
        sec = B.view(DB)["sections"]["running"]
        assert sec["commit"] == SHA and sec["level"] == B.DEPLOYED
        assert sec["state"] == B.UNKNOWN and sec["health"]["fresh"] is False
        _health(10, "idle")
        sec = B.view(DB)["sections"]["running"]
        assert sec["level"] == B.RUNNING and sec["health"]["state"] == "idle"
        _health(5, "healthy")
        assert B.view(DB)["sections"]["running"]["level"] == B.PROD_VERIFIED


def _customer(ref="board-buyer"):
    with DB.session() as s:
        c = Customer(customer_ref=ref)
        s.add(c)
        s.flush()
        return c.id


class _Measured:
    """The order source is connected and a completed receipt read is recorded."""
    def __init__(self, measured=True):
        self.measured = measured

    def __enter__(self):
        from brambleloop.commerce import orders_ingest as OI

        state = {"open": self.measured, "measured": self.measured,
                 "last_read_at": NOW.isoformat() if self.measured else None, "missing": [],
                 "why": "" if self.measured else "the order source is not connected: x"}
        self.p = patch.object(OI, "source_state", lambda db: state)
        self.p.start()

    def __exit__(self, *a):
        self.p.stop()


def test_only_an_unrefunded_etsy_order_is_real_commerce():
    cid = _customer()
    with _Deployed(), _Measured():
        with DB.session() as s:
            s.add(Order(customer_id=cid, external_ref="hand-1", product_slug="x",
                        revenue_cad=9.0, source=""))                       # hand-entered
            s.add(Order(customer_id=cid, external_ref="etsy-r", product_slug="x",
                        revenue_cad=9.0, refunded=True, source="etsy_receipts"))
        sec = B.view(DB)["sections"]["sales"]
        assert sec["real_orders"] == 0 and sec["level"] == B.DEPLOYED, sec
        with DB.session() as s:
            s.add(Order(customer_id=cid, external_ref="etsy-1", product_slug="x",
                        revenue_cad=7.5, source="etsy_receipts"))
        sec = B.view(DB)["sections"]["sales"]
        assert sec["real_orders"] == 1 and sec["revenue_cad"] == 7.5
        assert sec["level"] == B.COMMERCE


def test_releases_drafts_remote_ids_and_blockers_with_owners():
    with DB.session() as s:
        p = Product(**{k: v for k, v in {"slug": "board-coaster", "title": "Board Coaster",
                                          "category": "coaster"}.items()
                       if hasattr(Product, k)})
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={},
                             release_hash="r" * 64, certified=True))
        s.add(Listing(product_slug="board-coaster", version="1.0.0", title="t",
                      description="d", tags=[], price_cad=5.0, state="draft",
                      release_hash="r" * 64, etsy_listing_id="777"))
        q = Product(**{k: v for k, v in {"slug": "board-stale", "title": "Board Stale",
                                          "category": "coaster"}.items()
                       if hasattr(Product, k)})
        s.add(q)
        s.flush()
        s.add(PatternVersion(product_id=q.id, version="1.0.0", cir_json={},
                             release_hash="n" * 64, certified=True))
        s.add(Listing(product_slug="board-stale", version="1.0.0", title="t",
                      description="d", tags=[], price_cad=5.0, state="draft",
                      release_hash="o" * 64))
        s.add(OwnerAction(requirement_key="k", action="Approve the issuer service",
                          reason="r", max_cost_cad=2.35, minutes=5,
                          consequence_of_delay="c", blocks="standing grants", done=False))
        s.add(OwnerAction(requirement_key="k2", action="already done", reason="r",
                          max_cost_cad=0, minutes=1, consequence_of_delay="c", blocks="",
                          done=True))
        s.add(Incident(severity="P1", signature="dead-letter:x", summary="s",
                       resolved=False, halts_publication=False))
    v = B.view(DB)["sections"]
    rel = [r for r in v["releases"]["certified"] if r["slug"] == "board-coaster"][0]
    assert rel["etsy_listing_id"] == "777" and rel["listing_release_matches"] is True
    stale = [r for r in v["releases"]["certified"] if r["slug"] == "board-stale"][0]
    assert stale["listing_release_matches"] is False and stale["etsy_listing_id"] is None
    assert {"slug": "board-coaster", "version": "1.0.0", "state": "draft",
            "etsy_listing_id": "777"} in v["etsy"]["remote"]
    assert v["etsy"]["drafts_on_etsy"] >= 1
    acts = [a["action"] for a in v["blockers"]["owner_actions"]]
    assert "Approve the issuer service" in acts and "already done" not in acts
    assert all(a["owner"] == "owner" for a in v["blockers"]["owner_actions"])
    inc = v["blockers"]["incidents"][0]
    assert inc["owner"] == "system" and inc["family"] == "dead-letter"
    assert "summary" not in inc                                    # no free text


def test_a_broken_section_is_unknown_and_the_rest_still_read():
    def boom(db, now):
        raise RuntimeError("reader down")
    sections = tuple((n, boom if n == "shops" else f) for n, f in B.SECTIONS)
    with patch.object(B, "SECTIONS", sections):
        v = B.view(DB)["sections"]
    assert v["shops"]["state"] == B.UNKNOWN and "reader down" in v["shops"]["why"]
    assert v["shops"]["level"] is None
    assert v["blockers"]["state"] in ("OPEN", "CLEAR")
    # A section that reads but cannot be assembled is UNKNOWN too.
    def half(db, now):
        return lambda deployed: {"x": {}["missing"]}
    with patch.object(B, "SECTIONS", tuple((n, half if n == "etsy" else f)
                                           for n, f in B.SECTIONS)):
        v = B.view(DB)["sections"]
    assert v["etsy"]["state"] == B.UNKNOWN and "KeyError" in v["etsy"]["why"]


def test_the_route_is_owner_only_and_read_only():
    anon = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert anon.get("/api/cc/p0-board").status_code in (401, 403)
    c = TestClient(main.app, base_url="https://testserver", raise_server_exceptions=False)
    assert c.post("/api/cc/auth/login", json={"passphrase": PASS}).status_code == 200
    before = _counts()
    r = c.get("/api/cc/p0-board")
    assert r.status_code == 200, r.text
    body = r.json()
    data = body.get("data", body)
    assert data["tab"] == "P0_BOARD" and "sections" in data
    after = _counts()
    # Logging in writes its own security rows; the board itself writes nothing.
    assert {k: after[k] for k in after if k != "AuditLog"} == \
        {k: before[k] for k in before if k != "AuditLog"}
    assert c.post("/api/cc/p0-board").status_code in (404, 405)



def _shop(i, *, fresh=True, failures=0):
    return {"owner_order": i, "alias": f"shop-{i}", "role": "benchmark", "state": "ok",
            "last_attempted": NOW.isoformat(), "last_successful": NOW.isoformat() if fresh
            else None, "etsy_source_timestamp": NOW.isoformat(), "listings_seen_last_scan": 40,
            "listings_live": 40, "consecutive_failures": failures, "failure_class": None,
            "next_due": NOW.isoformat(), "stale": not fresh,
            "downstream": {"mission_events": 2, "coverage_gaps": 0}}


def test_all_eight_shops_fresh_and_clean_is_the_only_production_verified_scan_state():
    from brambleloop.ops import production_evidence as PE

    def scans(rows):
        return patch.object(PE, "competitor_scans",
                            lambda db, now: {"readable": True, "credential": "ok",
                                             "shops": rows})
    with _Deployed():
        with scans([_shop(i) for i in range(1, 9)]):
            sec = B.view(DB)["sections"]["shops"]
        assert sec["level"] == B.PROD_VERIFIED and sec["state"] == "OK" and sec["fresh"] == 8
        row = sec["shops"][0]
        for k in ("last_attempted", "last_successful", "etsy_source_timestamp",
                  "listings_seen_last_scan", "consecutive_failures", "next_due",
                  "downstream"):
            assert k in row, k
        for rows in ([_shop(i) for i in range(1, 8)],                       # only 7
                     [_shop(i) for i in range(1, 8)] + [_shop(8, fresh=False)],
                     [_shop(i) for i in range(1, 8)] + [_shop(8, failures=2)]):
            with scans(rows):
                sec = B.view(DB)["sections"]["shops"]
            assert sec["level"] == B.RUNNING and sec["state"] == "DEGRADED", sec["state"]
        # Nine configured is a misconfiguration, not "all eight", even with eight fresh.
        with scans([_shop(i) for i in range(1, 9)] + [_shop(9, fresh=False)]):
            assert B.view(DB)["sections"]["shops"]["level"] == B.RUNNING
        with scans([_shop(i, fresh=False) for i in range(1, 9)]):
            assert B.view(DB)["sections"]["shops"]["level"] == B.DEPLOYED


def test_assets_are_production_verified_only_when_every_item_is_proven():
    from brambleloop.app.command_center import company

    def ready(status, items, counts):
        return patch.object(company, "store_readiness",
                            lambda db, now=None: {"status": status, "items": items,
                                                  "counts": counts, "as_of": None})
    with _Deployed():
        with ready("OK", [], {"PROVEN": 12}):
            assert B.view(DB)["sections"]["assets"]["level"] == B.PROD_VERIFIED
        with ready("OK", [{"title": "gallery", "status": "NOT-PROVEN"}],
                   {"PROVEN": 11, "NOT-PROVEN": 1}):
            assert B.view(DB)["sections"]["assets"]["level"] == B.RUNNING
        with ready("OK", [], {}):
            assert B.view(DB)["sections"]["assets"]["level"] == B.DEPLOYED


def test_m1_held_or_unreconciled_orders_never_count():
    """Verdict 6990820438 M1: the board counts with `orders_ingest.countable_orders`."""
    from brambleloop.commerce import orders_ingest as OI

    cid = _customer("board-buyer-m1")
    with DB.session() as s:
        before = len(OI.countable_orders(s, select(Order).where(
            Order.source == B.REAL_ORDER_SOURCE)))
    with _Deployed(), _Measured():
        base = B.view(DB)["sections"]["sales"]
        assert base["real_orders"] == before, (base, before)
        with DB.session() as s:
            s.add(Order(customer_id=cid, external_ref="m1-unreconciled", product_slug="x",
                        revenue_cad=12.0, source="etsy_receipts",
                        detail={"state": OI.UNRECONCILED, "revenue_unknown": True}))
        sec = B.view(DB)["sections"]["sales"]
    with DB.session() as s:
        assert len(OI.countable_orders(s, select(Order).where(
            Order.source == B.REAL_ORDER_SOURCE))) == before
    assert sec["real_orders"] == before and sec["revenue_cad"] == base["revenue_cad"], sec


def test_m1_an_unreconciled_order_alone_is_never_real_commerce():
    from brambleloop.commerce import orders_ingest as OI

    with patch.object(OI, "countable_orders", lambda s, q=None: []), \
            _Deployed(), _Measured():
        sec = B.view(DB)["sections"]["sales"]
    assert sec["real_orders"] == 0 and sec["state"] == "NO_SALES"
    assert sec["level"] == B.DEPLOYED, sec["level"]


def test_m2_an_unmeasured_order_source_is_unknown_never_zero():
    """Verdict 6990820438 M2: not connected / never read -> UNKNOWN, not 0 orders and $0."""
    from brambleloop.commerce import orders_ingest as OI

    with patch.object(OI, "countable_orders", lambda s, q=None: []), \
            _Deployed(), _Measured(False):
        sec = B.view(DB)["sections"]["sales"]
    assert sec["state"] == B.UNKNOWN and "NO_SALES" not in str(sec["state"])
    assert sec["real_orders"] is None and sec["revenue_cad"] is None, sec
    assert "not connected" in sec["why"] and sec["source"]["measured"] is False
    # The real reader, on this harness's database (no probe, no grant): UNKNOWN too.
    real = B.view(DB)["sections"]["sales"]
    assert real["state"] == B.UNKNOWN and real["real_orders"] is None, real


def test_drafts_are_counted_over_every_remote_listing_not_the_capped_list():
    """Verdict 6990820438 LOW: 30 remote drafts are 30, not ROW_LIMIT (25)."""
    before = B.view(DB)["sections"]["etsy"]
    with DB.session() as s:
        for i in range(30):
            s.add(Listing(product_slug=f"cap-{i}", version="1.0.0", title="t",
                          description="d", tags=[], price_cad=5.0, state="draft",
                          etsy_listing_id=f"9{i:04d}"))
        s.add(Listing(product_slug="cap-inactive", version="1.0.0", title="t",
                      description="d", tags=[], price_cad=5.0, state="inactive",
                      etsy_listing_id="99999"))
    sec = B.view(DB)["sections"]["etsy"]
    assert len(sec["remote"]) == B.ROW_LIMIT == sec["remote_shown"]
    assert sec["drafts_on_etsy"] == before["drafts_on_etsy"] + 30, sec["drafts_on_etsy"]
    assert sec["not_live_on_etsy"] == before["not_live_on_etsy"] + 31
    assert sec["remote_total"] == before["remote_total"] + 31


def test_costs_and_blockers_run_only_on_recent_activity():
    """Verdict 6990820438 LOW: readable is not RUNNING."""
    from brambleloop.core.models import CostEntry

    later = NOW + timedelta(days=10)            # every row in this database is older than 24 h
    with _Deployed():
        v = B.view(DB, now=later)["sections"]
        assert v["costs"]["level"] == B.DEPLOYED, v["costs"]["level"]
        assert v["blockers"]["level"] == B.DEPLOYED, v["blockers"]["level"]
        with DB.session() as s:
            s.add(CostEntry(agent="board-test", provider="board-test", kind="api",
                            amount_cad=0.01, at=later - timedelta(hours=1)))
            s.add(Incident(severity="P3", signature="board:recent", summary="s",
                           resolved=True, at=later - timedelta(hours=2)))
        v = B.view(DB, now=later)["sections"]
        assert v["costs"]["level"] == B.RUNNING, v["costs"]
        assert v["blockers"]["level"] == B.RUNNING, v["blockers"]["level"]
        assert v["blockers"]["last_activity_at"] is not None


def test_an_unknown_shop_failure_count_is_not_zero():
    """Verdict 6990820438 LOW: eight fresh shops, one with no failure count, is not clean."""
    from brambleloop.ops import production_evidence as PE

    rows = [_shop(i) for i in range(1, 8)] + [_shop(8, failures=None)]
    with _Deployed(), patch.object(PE, "competitor_scans",
                                   lambda db, now: {"readable": True, "credential": "ok",
                                                    "shops": rows}):
        sec = B.view(DB)["sections"]["shops"]
    assert sec["state"] == "DEGRADED" and sec["failures_unknown"] == 1, sec["state"]
    assert sec["level"] == B.RUNNING and sec["failing"] == 0


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
    # run_tests.sh reads the exit code: a failing test must fail the suite.
    sys.exit(1 if failed else 0)
