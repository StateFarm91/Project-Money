"""W4-OWNERHOME: the six-block owner overview on the Command Center Home.

Server half: `app/command_center/overview.py`, wired into `tabs.home` as the `overview` section.
Client half: `views/_overview.js` + `views/home.js` (browser proof at 390 px is
tests/fixtures/cc_mock/check.mjs, "ownerhome:" lines).

Run: cd brambleloop && PYTHONPATH=src:tests .venv/bin/python tests/test_w4_ownerhome.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
_TMP = tempfile.mkdtemp(prefix="w4_ownerhome_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")


def _no_network(*_a, **_k):
    raise OSError("network refused by the OWNERHOME harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import overview, tabs  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (ArtefactProvenance, AuditLog, CostEntry, Job,  # noqa: E402
                                     JobStatus, PatternVersion, Product)

STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static"
NOW = datetime.now(timezone.utc)
_n = [0]


def _db() -> Database:
    _n[0] += 1
    db = Database(f"sqlite:///{_TMP}/d{_n[0]}.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def _seed(db):
    with db.session() as s:
        for i in range(3):
            s.add(Job(agent="listing", job_type="test.useful", status=JobStatus.DONE,
                      inputs={}, outputs={"work_done": 2, "summary": f"refreshed {i}"},
                      finished_at=NOW - timedelta(minutes=10 + i)))
        s.add(Job(agent="orchestrator", job_type="test.idle", status=JobStatus.DONE,
                  inputs={}, outputs={"work_done": 0}, finished_at=NOW - timedelta(minutes=5)))
        s.add(Job(agent="listing", job_type="test.useful", status=JobStatus.DONE, inputs={},
                  outputs={"work_done": 1, "summary": "too old"},
                  finished_at=NOW - timedelta(hours=30)))
        s.add(CostEntry(agent="gateway", amount_cad=0.03, kind="image", purpose="image.probe",
                        detail={}))
        p = Product(slug="harbour-throw", title="Harbour Throw", status="certified")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={}, certified=True,
                             release_hash="r" * 64))
        s.add(Product(slug="moss-runner", title="Moss Runner", status="draft"))
        s.add(ArtefactProvenance(artefact_class="pdf", artefact_key="pdf:harbour-throw@1",
                                 product_slug="harbour-throw", inputs={}))
        s.add(AuditLog(actor="orchestrator", action="verify.completed",
                       detail={"ok": False, "failing": ["no_unexpected_dead_letters_in_24h"],
                               "commit": "abc"}))


def test_home_carries_six_blocks_in_order():
    db = _db()
    _seed(db)
    home = tabs.home(db)
    ov = home["sections"]["overview"]
    assert ov["order"] == ["working", "blocked", "decisions", "accomplished", "ready", "money"]
    for key in ov["order"]:
        b = ov["blocks"][key]
        assert b["key"] == key and b["title"] and b["headline"], b
        assert len(b["items"]) <= overview.TOP and len(b["evidence"]) <= overview.EVIDENCE_MAX
        assert b["status"] in ("OK", "DEGRADED", "BLOCKED", "UNKNOWN"), b["status"]
        assert b.get("sources"), key


def test_working_names_capabilities_and_last_self_check_with_times():
    db = _db()
    _seed(db)
    b = overview.overview(db)["blocks"]["working"]
    selfcheck = b["evidence"][0]
    assert selfcheck["title"].startswith("Production self-check")
    assert selfcheck["verified_at"] and "no_unexpected_dead_letters_in_24h" in selfcheck["detail"]
    assert selfcheck["status"] == "DEGRADED"
    assert all(r.get("verified_at") for r in b["evidence"])


def test_blocked_ranks_root_causes_by_count():
    db = _db()
    b = overview.overview(db)["blocks"]["blocked"]
    for unit in ("rows", "requirements"):
        counts = [r["count"] for r in b["evidence"] if r.get("unit") == unit]
        assert counts == sorted(counts, reverse=True), (unit, counts)
    units = [r.get("unit") for r in b["evidence"]]
    if "rows" in units:  # board causes lead, gates follow; units never interleave
        assert units[:units.count("rows")] == ["rows"] * units.count("rows"), units
    assert b["counts"]["closed_gates"] > 0 and b["status"] == "BLOCKED"
    assert b["items"] == b["evidence"][:overview.TOP]


def test_blocked_leads_with_the_finish_line_board_and_survives_its_absence():
    db = _db()
    board = {"status": "BLOCKED", "as_of": "2026-10-11T18:00:00+00:00", "production_commit": "x",
             "items": [{"title": "Etsy credential", "rows": 40, "fm_launch_critical": 12,
                        "build2": 3, "source": "board#etsy"},
                       {"title": "No customer yet", "rows": 90, "source": "board#cust"},
                       {"title": "Uncounted", "rows": None, "source": "board#u"}]}
    b = overview.blocked(db, board_reader=lambda: board)
    assert [r["title"] for r in b["evidence"][:3]] == ["No customer yet", "Etsy credential",
                                                       "Uncounted"], b["evidence"][:3]
    assert b["evidence"][2]["count"] is None  # unknown stays unknown, never 0
    assert b["headline"].startswith("Top root cause: No customer yet (90 rows)")
    assert b["counts"]["board_root_causes"] == 3 and b["board"]["as_of"]

    def boom():
        raise OSError("gone")

    g = overview.blocked(db, board_reader=boom)
    assert g["counts"]["board_root_causes"] == 0 and g["board"]["status"] == "UNKNOWN"
    assert g["status"] == "BLOCKED" and "closed gate" in g["headline"]


def test_accomplished_is_useful_outcomes_not_job_counts():
    db = _db()
    _seed(db)
    b = overview.overview(db)["blocks"]["accomplished"]
    assert [i["title"] for i in b["items"]] == ["test.useful"], b["items"]
    assert b["items"][0]["count"] == 3 and b["items"][0]["detail"] == "refreshed 0"
    assert b["counts"] == {"useful": 3, "kinds": 1, "no_work": 1, "finished": 4}, b["counts"]


def test_ready_to_sell_reads_certification_pdf_and_images_without_inventing():
    db = _db()
    _seed(db)
    b = overview.overview(db)["blocks"]["ready"]
    rows = {r["slug"]: r for r in b["evidence"]}
    hw, mr = rows["harbour-throw"], rows["moss-runner"]
    assert hw["certified"] is True and hw["pdf"]["state"] == "BUILT"
    assert hw["images"]["state"] == "UNKNOWN" and hw["images"]["why"]
    assert mr["certified"] is False and mr["pdf"]["state"] == "UNKNOWN"
    assert b["counts"]["ready"] == 0 and b["status"] == "BLOCKED"


def test_money_keeps_unknown_and_measures_agents_by_useful_results():
    db = _db()
    _seed(db)
    b = overview.overview(db)["blocks"]["money"]
    rev = next(i for i in b["evidence"] if i["title"] == "Revenue")
    assert rev["value_cad"] is None and rev["status"] == "UNKNOWN", rev
    assert "0.00" not in str(rev["display"])
    spend = next(i for i in b["evidence"] if i["title"] == "Recorded spend (24 h)")
    assert spend["value_cad"] == 0.03 and spend["state"] == "RECORDED"
    agents = {a["title"]: a for a in b["agents"]}
    assert agents["listing"]["useful_24h"] == 3 and agents["orchestrator"]["useful_24h"] == 0
    assert b["agents_counts"] == {"active_24h": 1, "ran_24h": 2}


def test_one_unreadable_source_makes_one_block_unknown():
    db = _db()
    real = overview._pdf_and_images

    def boom(*_a, **_k):
        raise RuntimeError("provenance table gone")

    overview._pdf_and_images = boom
    try:
        _seed(db)
        ov = overview.overview(db)
    finally:
        overview._pdf_and_images = real
    assert ov["blocks"]["ready"]["status"] == "UNKNOWN"
    assert "provenance table gone" in ov["blocks"]["ready"]["reason"]
    assert ov["blocks"]["accomplished"]["status"] == "OK"


def test_decisions_counts_the_queue_and_unknown_is_not_zero():
    assert overview.decisions({"status": "OK", "open": 4})["headline"] == "4 decision(s) open"
    u = overview.decisions({"status": "UNKNOWN", "reason": "queue unreadable"})
    assert u["status"] == "UNKNOWN" and "0" not in u["headline"]


def test_client_renders_overview_safely():
    ov = (STATIC / "js" / "views" / "_overview.js").read_text(encoding="utf-8")
    home = (STATIC / "js" / "views" / "home.js").read_text(encoding="utf-8")
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    assert "overviewBlocks(s.overview" in home and "nextDecisions(ranked" in home
    assert 'h("details", { class: "home-more" }' in home
    for bad in ("innerHTML", "insertAdjacentHTML", "?? 0", "|| 0"):
        assert bad not in ov, bad
    assert '"js/views/_overview.js"' in sw


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("OK  ", t.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print("FAIL", t.__name__, exc)
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
