"""The shipped owner-decision index matches DECISION_LOG.md and is what the image relies on."""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core import decision_index  # noqa: E402


def test_the_index_matches_the_log():
    live = decision_index.build((ROOT / "DECISION_LOG.md").read_text(encoding="utf-8"))
    assert live, "DECISION_LOG.md has no headings"
    assert decision_index.load() == live, (
        "src/brambleloop/core/decision_index.json is stale: run "
        "`PYTHONPATH=src python -m brambleloop.core.decision_index`")


def test_the_index_carries_no_session_state():
    text = decision_index.INDEX.read_text().lower()
    for marker in (".claude", "claude.ai/code", "claude-session", "heartbeat"):
        assert marker not in text, marker


def test_runtime_readers_fall_back_to_the_index_when_the_log_is_absent():
    from brambleloop.laura.core import identity
    from brambleloop.laura.memory import provenance

    saved_log, env = provenance.DECISION_LOG, os.environ.get("BRAMBLELOOP_DECISION_LOG")
    absent = ROOT / "no-such-decision-log.md"
    try:
        provenance.DECISION_LOG = absent
        os.environ["BRAMBLELOOP_DECISION_LOG"] = str(absent)
        assert identity.decision_recorded("D-FB-18") is True
        assert identity.decision_recorded("D-FB-14") is True
        assert identity.decision_recorded("D-FB-99999") is False
        assert provenance._decision_exists("D-FB-17") is True
        assert provenance._decision_exists("D-NOT-A-DECISION") is False
    finally:
        provenance.DECISION_LOG = saved_log
        if env is None:
            os.environ.pop("BRAMBLELOOP_DECISION_LOG", None)
        else:
            os.environ["BRAMBLELOOP_DECISION_LOG"] = env


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
