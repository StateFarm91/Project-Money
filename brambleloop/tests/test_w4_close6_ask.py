"""W4-CLOSE6: F-664 Ask Brambleloop.

  F-664  "universal company command/search bar answering what changed, why profit moved,
          what blocks launch, what agents are doing, opportunities, spend and evidence."

The mapping said MISSING. The surface already exists:
- `app/command_center/ask.py` (v1.1 F-928/F-929);
- POST /api/cc/ask;
- the Ask view in the Command Center shell.

It already answered what changed (overnight), profit/revenue and what blocks launch, every
answer citing its rows. It had no reader for three of the seven things the criterion names:
what agents are doing, spend and opportunities. Those questions fell through to UNKNOWN.

This file asserts all seven. Each new answer is assembled only from durable rows, each fact
cites its row, and an empty store answers "nothing recorded" or UNKNOWN, never an invention.
Local, deterministic; no model call.
Run: cd brambleloop && PYTHONPATH=src:tests $PY tests/test_w4_close6_ask.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.app.command_center import ask  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import (  # noqa: E402
    CostEntry, Improvement, Job, JobStatus, MjsMissionEvent,
)

NOW = datetime.now(timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/ask.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_every_named_question_routes_to_a_reader():
    named = {"what changed overnight?": "overnight", "why did profit fall?": "profit",
             "what is blocking launch?": "launch_blocked",
             "what are the agents doing?": "agents", "what opportunities are open?":
             "opportunities", "how much did we spend this month?": "spend",
             "what incidents are open?": "incidents"}
    assert len(named) == 7, "the seven things F-664 names"
    for q, intent in named.items():
        assert ask.classify(q)[0] == intent, (q, ask.classify(q))
    assert ask.classify("what is the meaning of life?")[0] == "unknown"
    for phrase in ("agents", "spend", "opportunities"):
        assert any(phrase in s for s in ask.SUPPORTED), ask.SUPPORTED


def test_an_empty_company_answers_nothing_recorded_never_an_invention():
    db = _db()
    a = ask.ask(db, "what did we spend this month?")
    assert a["status"] == "ANSWERED" and "Nothing is recorded as spent" in a["answer"], a
    assert a["sources"] == ["cost_entries"]
    a = ask.ask(db, "what opportunities are open?")
    assert a["status"] == "UNKNOWN" and a["answer"].startswith("UNKNOWN"), a
    a = ask.ask(db, "what are the agents doing?")
    assert a["status"] == "ANSWERED" and "0 agent(s) are running" in a["answer"], a


def test_spend_agents_and_opportunities_are_answered_from_cited_rows():
    db = _db()
    with db.session() as s:
        s.add_all([
            CostEntry(agent="market_radar", kind="llm", amount_cad=1.25,
                      purpose="gallery_observation", provider="anthropic", at=NOW),
            CostEntry(agent="creative_director", kind="llm", amount_cad=3.50,
                      purpose="creative.grid_tournament", provider="anthropic", at=NOW),
            Job(agent="listing", job_type="listing.seo", status=JobStatus.RUNNING, inputs={},
                created_at=NOW, run_after=NOW, started_at=NOW),
            Job(agent="pricing", job_type="pricing.position", status=JobStatus.PENDING,
                inputs={}, created_at=NOW, run_after=NOW - timedelta(minutes=1)),
            MjsMissionEvent(benchmark_key="mjs", listing_ref="L1", pod="blankets",
                            arena="baby", entered=True, decision="tournament",
                            seasonal={"target": {"event": "valentines"}}),
            MjsMissionEvent(benchmark_key="mjs", listing_ref="L2", pod="toys", arena="x",
                            entered=False),
            Improvement(cell="listing", metric="ctr", hypothesis="shorter titles lift CTR",
                        state="proposed"),
            Improvement(cell="listing", metric="ctr", hypothesis="already decided",
                        state="rejected"),
        ])
    a = ask.ask(db, "what did we spend this month?")
    assert a["status"] == "ANSWERED", a
    assert "CA$4.75" in a["answer"] and "creative.grid_tournament" in a["answer"], a["answer"]
    assert all(f["source"].startswith("cost_entries") for f in a["facts"]), a["facts"]

    a = ask.ask(db, "what are the agents doing?")
    assert a["status"] == "ANSWERED", a
    running = [f for f in a["facts"] if "is running listing.seo" in f["statement"]]
    assert running and running[0]["source"].startswith("jobs:"), a["facts"]
    assert any("pricing has 1 ready job" in f["statement"] for f in a["facts"]), a["facts"]

    a = ask.ask(db, "what opportunities are open?")
    assert a["status"] == "ANSWERED", a
    stmts = " | ".join(f["statement"] for f in a["facts"])
    assert "blankets / baby for valentines" in stmts and "shorter titles" in stmts, stmts
    assert "toys" not in stmts, "an opening the mission did not enter is not an opportunity"
    assert "already decided" not in stmts, "a decided improvement is not open"
    assert all(f["source"].split(":")[0] in ("mjs_mission_events", "improvements")
               for f in a["facts"]), a["facts"]


def test_the_surface_is_the_command_center_bar():
    api = (ROOT / "src/brambleloop/app/command_center/api.py").read_text()
    assert '@router.post("/ask")' in api and "ask_mod.ask" in api
    view = (ROOT / "src/brambleloop/app/command_center/static/js/views/ask.js").read_text()
    for q in ("What are the agents doing?", "What did we spend this month?",
              "What opportunities are open?", "What is blocking launch?"):
        assert q in view, q


if __name__ == "__main__":
    fails = 0
    ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    assert ran >= 4, "no tests collected"
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing of {ran}")
    sys.exit(1 if fails else 0)
