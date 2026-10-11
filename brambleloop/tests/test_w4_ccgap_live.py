"""W4-CCGAP: the Command Center shows the operating company, not a stale snapshot.

Four sections used to read only committed JSON shipped in the image. Now:

* Decision batches come LIVE from the running system's own owner queue
  (`approval_inbox()["batches"]`). Decisions only the release packet lists are shown apart, as
  `release_only`, labelled with the release and never added to the live count.
* Visual: a new live section, `visual_pipeline_live`, built from `listing_assets` and
  `listing_set_certificates` rows. The R&D milestone stages A-E exist only as a release artefact,
  so they are labelled as one.
* Completion: a new live section, `live_work`, built from `jobs`. The Claude development-lane board
  exists only in the release, so it is labelled as a release artefact.
* Final Master: the closure matrix is a release artefact. It is labelled "Release artefact, not
  live" with the mapping commits, and with the generation time as UNKNOWN because the file
  records none.

No data is fabricated, and nothing unknown is shown as 0.

Run: cd brambleloop && PYTHONPATH=src python3 tests/test_w4_ccgap_live.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_ccgap_live_")
os.environ.pop("BRAMBLELOOP_COMPLETION_BOARD", None)
os.environ.pop("BRAMBLELOOP_OWNER_ACTIONS", None)
STATIC = ROOT / "src" / "brambleloop" / "app" / "command_center" / "static" / "js"


def _db():
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/l{len(os.listdir(_TMP))}.sqlite")
    db.create_all()
    return db


def test_release_label_never_reads_as_live_and_unknowns_stay_unknown():
    from brambleloop.app.command_center import company

    ra = company.release_artefact("thing", None, source="x.json")
    assert ra["live"] is False and ra["label"].startswith("Release artefact, not live: thing")
    assert "generation time UNKNOWN" in ra["label"], ra["label"]
    assert ra["generated_at"] is None
    if ra["release_sha"] is None:
        assert "no release record matched this build" in ra["label"]
    dated = company.release_artefact("thing", "2026-10-10T04:00:00Z", source="x.json")
    assert "generated 2026-10-10T04:00:00Z" in dated["label"]
    mapped = company.release_artefact("fm", None, source="f", mapped_at="2f36fe0")
    assert "mapped at commit 2f36fe0; generation time UNKNOWN" in mapped["label"]


def test_snapshot_sections_carry_the_release_label():
    from brambleloop.app.command_center import company

    vs = company.visual_stages()
    assert vs["release_artefact"]["live"] is False and "VISUAL_STATUS" in vs["release_artefact"]["label"]
    fm = company.final_master(None)
    ra = fm.get("release_artefact")
    assert ra and ra["live"] is False and ra["generated_at"] is None, fm.get("reason")
    assert ra["mapped_at"] and "generation time UNKNOWN" in ra["label"]
    board = company.completion(None)
    assert board["release_artefact"]["live"] is False
    assert board["release_artefact"]["generated_at"] == board["board_updated_at"]
    # an operator-supplied board (env override) is not claimed to be a release artefact
    p = os.path.join(_TMP, "board.json")
    Path(p).write_text(json.dumps({"updated_at": "2026-10-11T00:00:00Z", "lanes": []}))
    os.environ["BRAMBLELOOP_COMPLETION_BOARD"] = p
    try:
        assert company.completion(None).get("release_artefact") is None
    finally:
        os.environ.pop("BRAMBLELOOP_COMPLETION_BOARD", None)


def test_visual_pipeline_live_reads_rows_and_is_unknown_without_them():
    from brambleloop.app.command_center import company
    from brambleloop.core.models import ListingAsset, ListingSetCertificateRecord

    db = _db()
    empty = company.visual_pipeline_live(db)
    assert empty["status"] == "UNKNOWN" and empty["items"] == [], empty
    with db.session() as s:
        for pos, ok in ((1, True), (2, True), (3, False)):
            s.add(ListingAsset(product_slug="hex", version="1.2.0", position=pos,
                               asset_class="render", role="hero", approved=ok,
                               blocked_reasons=[] if ok else ["no disclosure"]))
        s.add(ListingAsset(product_slug="blanket", version="1.0.0", position=1,
                           asset_class="render", role="hero", approved=True))
        s.add(ListingSetCertificateRecord(product_slug="blanket", version="1.0.0",
                                          certificate={"frames": [{"job": "HERO"},
                                                                  {"job": "SCALE"}]},
                                          state="valid"))
    out = company.visual_pipeline_live(db)
    by = {i["product"]: i for i in out["items"]}
    assert by["hex"]["frames_planned"] == 3 and by["hex"]["frames_approved"] == 2
    assert by["hex"]["frames_blocked"] == 1 and by["hex"]["certificate"] == "none issued"
    assert by["hex"]["status"] == "BLOCKED"
    assert by["blanket"]["status"] == "OK" and by["blanket"]["certified_jobs"] == "HERO, SCALE"
    assert out["status"] == "BLOCKED" and out["live"] is True and out["as_of"], out
    assert "1 of 2 release(s) without a valid listing-set certificate" in out["reason"]


def test_live_company_work_comes_from_jobs():
    from brambleloop.app.command_center import company
    from brambleloop.core.models import Job, JobStatus
    from brambleloop.queue.durable import JobQueue

    db = _db()
    q = JobQueue(db)
    q.enqueue("listing", "listing.draft", {}, idempotency_key="ccgap-a")
    q.enqueue("cfo", "finance.accounting.cycle", {}, idempotency_key="ccgap-b")
    with db.session() as s:
        j = s.query(Job).filter(Job.agent == "listing").one()
        j.status = JobStatus.RUNNING
    out = company.live_company_work(db)
    assert out["status"] == "OK" and out["live"] is True
    assert out["running"] == 1 and out["pending"] == 1, out
    assert out["items"][0]["title"] == "listing: listing.draft"
    assert out["completed_24h"] == 0 and out["failed_24h"] == 0  # measured zero, not unknown


def test_decision_batches_are_live_first_release_only_kept_apart():
    from brambleloop.app.command_center import company

    snap = os.path.join(_TMP, "owner.json")
    Path(snap).write_text(json.dumps({"generated_at": "2026-10-10T04:30:36Z", "batches": [
        {"id": "go_live", "title": "Go live", "items": [
            {"id": "leave_shadow", "decision": "d1", "max_cost_cad": 0},
            {"id": "etsy_kyc_payout", "decision": "d2", "minutes": 10}]}]}))
    os.environ["BRAMBLELOOP_OWNER_ACTIONS"] = snap
    try:
        live = {"batches": [{"id": "go_live", "title": "Go live", "decisions": 1,
                             "max_cost_display": "CA$0.00",
                             "items": [{"id": "leave_shadow", "decision": "live d1",
                                        "max_cost_cad": 0}]}]}
        out = company.owner_decision_batches(live)
        assert out["live"] is True and out["status"] == "OK"
        assert "live" in out["sources"][0]
        assert out["decisions"] == 1 and out["live_runtime_decisions"] == 1  # never merged
        assert out["items"][0]["items"][0]["decision"] == "live d1"
        ro = out["release_only"]
        assert [d["id"] for b in ro for d in b["items"]] == ["etsy_kyc_payout"]
        assert out["release_only_decisions"] == 1
        assert out["release_artefact"]["live"] is False
        assert out["release_artefact"]["generated_at"] == "2026-10-10T04:30:36Z"
        # the real shape: approval_inbox()["batches"] is batch_cards()'s dict (c131f07 missed it)
        real = company.owner_decision_batches({"batches": {"batches": live["batches"],
                                                           "decisions": 1}})
        assert real["live"] is True and real["decisions"] == 1, real
        # no live batches reported: the release packet is shown, labelled, never as live
        fb = company.owner_decision_batches({})
        assert fb["live"] is False and fb["release_artefact"]["live"] is False
        assert "may be out of date" in fb["reason"]
        # an empty live queue is live and empty; release-only decisions still listed apart
        none = company.owner_decision_batches({"batches": []})
        assert none["live"] is True and none["decisions"] == 0
        assert none["release_only_decisions"] == 2
    finally:
        os.environ.pop("BRAMBLELOOP_OWNER_ACTIONS", None)


def test_pwa_renders_release_labels_and_live_sections():
    comp = (STATIC / "components.js").read_text()
    assert "export function releaseNote(env)" in comp and "releaseNote(env)," in comp
    company = (STATIC / "views" / "company.js").read_text()
    assert '["visual_pipeline_live", "Visual pipeline (live: listing frames & certificates)"]' in company
    assert "Visual R&D milestones A-E (release artefact)" in company
    assert "releaseNote(env)," in company  # Final Master card
    completion = (STATIC / "views" / "completion.js").read_text()
    assert "liveWorkCard(sectionsOf(data).live_work, result)" in completion
    assert "releaseNote(env)," in completion
    approvals = (STATIC / "views" / "approvals.js").read_text()
    assert "Also in the release packet, not tracked live" in approvals
    api = (ROOT / "src/brambleloop/app/command_center/api.py").read_text()
    assert '"live_work": company_mod.live_company_work(db)' in api
    co = (ROOT / "src/brambleloop/app/command_center/company.py").read_text()
    assert '"visual_pipeline_live": guard("visual_pipeline_live"' in co


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
