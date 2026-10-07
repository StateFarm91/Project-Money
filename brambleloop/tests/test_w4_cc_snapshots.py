"""The deploy image ships no research/: the Command Center reads shipped snapshots that must equal
their research/final_build/w4 sources and carry no session state."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.app.command_center import company, snapshots  # noqa: E402


def test_every_present_source_has_an_identical_shipped_snapshot():
    present = [n for n in snapshots.NAMES if (snapshots.SOURCE / n).exists()]
    assert present, "no W4 owner-view source exists"
    for name in present:
        shipped = snapshots.HERE / name
        assert shipped.exists(), f"{name}: run `python -m brambleloop.app.command_center.snapshots`"
        assert shipped.read_bytes() == (snapshots.SOURCE / name).read_bytes(), (
            f"{name} snapshot is stale: run `python -m brambleloop.app.command_center.snapshots`")


def test_snapshots_carry_no_session_state():
    shipped = sorted(snapshots.HERE.glob("*.json"))
    assert shipped, "no snapshot shipped"
    for f in shipped:
        text = f.read_text(errors="replace").lower()
        for marker in (".claude", "claude.ai/code", "claude-session", "heartbeat"):
            assert marker not in text, (f.name, marker)


def test_without_research_the_readers_fall_back_to_the_snapshot():
    saved = company._REPO
    try:
        company._REPO = ROOT / "no-such-checkout"
        assert company.board_path() == snapshots.HERE / "COMPLETION_BOARD.json"
        assert company.visual_status_path() == snapshots.HERE / "VISUAL_STATUS.json"
    finally:
        company._REPO = saved
    assert company.board_path() == ROOT / company.BOARD_REL


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
