"""W4-BOARD: the finish-line board puts every Build 2 and Final Master row in exactly one class,
closes nothing the ledgers have not, and the Command Center card reads it honestly."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.app.command_center import company, snapshots  # noqa: E402

W4 = ROOT / "research" / "final_build" / "w4"
BOARD = json.loads((W4 / "COMPLETION_BOARD_FINAL.json").read_text())
CLASSES = ("verified_complete", "implemented_unverified", "in_progress", "blocked_engineering",
           "blocked_owner", "blocked_external", "not_applicable")


def test_every_row_is_in_exactly_one_class_and_the_totals_are_the_ledgers():
    b2, fm = BOARD["rows"]["build2"], BOARD["rows"]["final_master"]
    assert len(b2) == 320 and len({r["id"] for r in b2}) == 320
    assert len(fm) == 917 and len({r["id"] for r in fm}) == 917
    assert sum(1 for r in fm if r["scope"] == "launch_critical") == 490
    for r in b2 + fm:
        assert r["cls"] in CLASSES, r
    h = BOARD["headline"]
    for scope, rows in (("build2", b2), ("final_master_total", fm),
                        ("final_master_launch_critical",
                         [r for r in fm if r["scope"] == "launch_critical"])):
        assert sum(h[scope][c] for c in CLASSES) == h[scope]["total"] == len(rows), scope


def test_nothing_is_complete_that_the_ledgers_do_not_prove():
    b2 = json.loads((W4 / "BUILD2_LEDGER.json").read_text())
    proven = {r["id"] for r in b2["rows"] if r["state"] == "PROVEN"}
    m = json.loads((ROOT / "research" / "final_build" / "closure_matrix.json").read_text())
    complete = {r["uid"] for r in m["matrix"] if r["completion"] == "COMPLETE"}
    vb2 = [r for r in BOARD["rows"]["build2"] if r["cls"] == "verified_complete"]
    assert vb2 and all(r["id"] in proven for r in vb2)
    vlc = [r for r in BOARD["rows"]["final_master"]
           if r["cls"] == "verified_complete" and r["scope"] == "launch_critical"]
    assert vlc and all(r["id"] in complete for r in vlc)
    lc_done = sum(1 for r in BOARD["rows"]["final_master"] if r["scope"] == "launch_critical"
                  and r["cls"] in ("verified_complete", "implemented_unverified"))
    assert lc_done == m["summary"]["launch_critical_completion"]["COMPLETE"]


def test_every_unfinished_row_says_what_blocks_it_and_owner_rows_name_the_action():
    unfinished = [r for r in BOARD["rows"]["build2"] + BOARD["rows"]["final_master"]
                  if r["cls"] not in ("verified_complete", "not_applicable",
                                      "implemented_unverified")]
    assert unfinished
    for r in unfinished:
        assert r.get("blocked_by") and r.get("root"), r
        if r["cls"] == "blocked_owner":
            assert (r.get("owner_action") or {}).get("action"), r


def test_root_causes_count_the_rows_they_unblock():
    unfinished = [r for r in BOARD["rows"]["build2"] + BOARD["rows"]["final_master"]
                  if r["cls"] not in ("verified_complete", "not_applicable")]
    assert sum(g["rows"] for g in BOARD["root_causes"]) == len(unfinished)
    assert BOARD["critical_path"] and all(s["unblocks_rows"] > 0 for s in BOARD["critical_path"])


def test_the_card_snapshot_ships_and_the_reader_serves_it():
    card = W4 / "COMPLETION_BOARD_FINAL_CARD.json"
    assert "COMPLETION_BOARD_FINAL_CARD.json" in snapshots.NAMES
    assert (snapshots.HERE / card.name).read_bytes() == card.read_bytes()
    env = company.finish_line()
    lc = env["scopes"]["final_master_launch_critical"]
    assert lc["total"] == 490 and lc["verified_complete"] == \
        BOARD["headline"]["final_master_launch_critical"]["verified_complete"]
    assert env["status"] in ("BLOCKED", "OK") and env["items"]
    assert env["items"][0]["rows"] == BOARD["root_causes"][0]["rows"]


def test_a_missing_or_malformed_card_is_unknown_or_degraded_never_zero():
    d = tempfile.mkdtemp()
    saved = os.environ.get(company.FINISH_ENV)
    try:
        os.environ[company.FINISH_ENV] = os.path.join(d, "absent.json")
        assert company.finish_line()["status"] == "UNKNOWN"
        bad = Path(d) / "bad.json"
        bad.write_text(json.dumps({"headline": {"build2": {"verified_complete": 3}}}))
        os.environ[company.FINISH_ENV] = str(bad)
        env = company.finish_line()
        assert env["status"] == "DEGRADED"
        assert env["scopes"]["build2"] is None and env["scopes"]["final_master_total"] is None
    finally:
        if saved is None:
            os.environ.pop(company.FINISH_ENV, None)
        else:
            os.environ[company.FINISH_ENV] = saved


def test_the_completion_view_carries_the_finish_line_section_and_the_phone_card():
    api = (ROOT / "src/brambleloop/app/command_center/api.py").read_text()
    assert '"finish_line": company_mod.finish_line()' in api
    js = (ROOT / "src/brambleloop/app/command_center/static/js/views/completion.js").read_text()
    assert "finishLineCard(sectionsOf(data).finish_line" in js
    assert 'h("details"' in js


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
