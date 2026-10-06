"""W3 lane D: wiring requests for lane H (visual.rnd) and closure K15, plus K3's cadence.

* `visual.rnd.cycle` is a registered handler with a cadence, an agent grant, a swarm band, a
  SAFE_GENERATED reason, and a Visual department provider (`visual.rnd.status.next_work`) the
  orchestrator and Laura draw on -- internal GREEN items only. Its work count is honest and it
  refuses a reported paid execution.
* K15: `finance.accounting.tax_pack` and `handoff` have a runtime caller
  (`finance.accounting.period_pack`), idempotent, writing no file; the importlib-loaded
  providers are imported statically so the C-65 reachability rule sees them.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS  # noqa: E402
from brambleloop.autonomy import charters, generators, orchestrator  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers the handlers
from brambleloop.runtime.worker import CADENCES, handlers  # noqa: E402
from brambleloop.swarm.orchestrate import JOB_BANDS  # noqa: E402

NEW = {"visual.rnd.cycle": ("visual_rnd", "publishing", 6 * 3600, "visual", "exploration"),
       "finance.accounting.period_pack": ("accounting_period_pack", "cfo", 86400, "finance",
                                          "housekeeping"),
       "listing.outcomes": ("listing_outcomes", "cfo", 86400, None, "exploration")}


def boot():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database

    tmp = tempfile.mkdtemp(prefix="w3d-wire-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db, tmp


def _handler(jt):
    reg = getattr(handlers, "_handlers", None)
    return reg.get(jt) if isinstance(reg, dict) else handlers.get(jt)


def test_each_wired_job_has_handler_cadence_grant_and_band():
    cad = {jt: (name, agent, period) for name, agent, jt, period in CADENCES}
    for jt, (name, agent, period, dept, band) in NEW.items():
        assert _handler(jt) is not None, jt
        assert cad.get(jt) == (name, agent, period), (jt, cad.get(jt))
        a = next(x for x in DEFAULT_AGENTS if x["name"] == agent)
        assert jt in a["allowed_job_types"], (agent, jt)
        assert jt not in FORBIDDEN_COMBINATIONS.get(agent, set()), (agent, jt)
        assert JOB_BANDS.get(jt) == band, (jt, JOB_BANDS.get(jt))
        assert orchestrator._agent_for(jt) == agent
        if dept:
            assert charters.department_of(jt) == dept
            assert jt in charters.BY_KEY[dept].generatable and jt in charters.SAFE_GENERATED
        assert jt not in charters.PROTECTED_JOB_TYPES


def test_visual_rnd_tables_are_created_by_create_all():
    from sqlalchemy import inspect

    db, _ = boot()
    names = set(inspect(db.engine).get_table_names())
    assert {"visual_rnd_pipelines", "visual_rnd_experiments", "visual_rnd_judgements",
            "visual_rnd_market", "visual_rnd_lessons"} <= names, names


def test_visual_provider_feeds_internal_green_work_only():
    assert generators.PROVIDERS["visual"][0][1] == "brambleloop.visual.rnd.status"
    adapt = generators._visual_item
    ok = {"kind": "visual.rnd.experiment", "key": "visual.rnd.experiment:x:2026-10-06",
          "job_type": "visual.rnd.cycle", "green": True}
    assert adapt(ok) == ("visual.rnd.cycle", ok["key"])
    assert adapt({**ok, "green": False}) is None
    assert adapt({**ok, "job_type": "visual.provider_trial"}) is None   # a paid/other type
    assert adapt({**ok, "kind": "visual.rnd.provider_error"}) is None
    db, _ = boot()
    snap = generators.Snapshot.read(db, datetime.now(timezone.utc))
    cands = generators.provider_candidates(db, charters.BY_KEY["visual"], snap)
    assert [c.job_type for c in cands] == ["visual.rnd.cycle"], cands
    assert cands[0].source == "provider" and not cands[0].protected
    # the company loop turns it into a Visual mission through the single enqueue boundary
    rep = orchestrator.tick(db, departments=[charters.BY_KEY["visual"]])
    assert rep["departments"]["visual"]["state"] == "GENERATED", rep["departments"]
    assert rep["missions"][0]["job_type"] in ("visual.rnd.cycle", "visual.identity_drift",
                                              "autonomy.department_review"), rep["missions"]
    # Laura's executive reads the same provider; a non-OK reading delegates the cycle
    from brambleloop.laura.executive import loop

    assert loop.PROVIDERS["visual_rnd"] == ("brambleloop.visual.rnd.status", "visual",
                                            "visual.rnd.cycle")


def test_visual_cycle_work_count_is_honest_and_paid_execution_is_refused():
    from brambleloop.autonomy.visual_rnd_job import summarise

    idle = {"classes": {"coasters_tabletop": {"monitor": {"action": "retain"},
                                              "calibration": {"verdict": "inconclusive"},
                                              "experiments": [], "paid": {"new": False,
                                                                          "state": "GATED"},
                                              "incumbent": "c/g1"}}}
    out = summarise(idle)
    assert out["work_done"] == 0 and out["spend_cad"] == 0.0
    assert pipeline.did_no_work(out, "visual.rnd.cycle")
    busy = {"classes": {"a": {"generated": {"frames": 3}, "experiments": [{"experiment": 1}],
                              "monitor": {"action": "rolled_back"},
                              "calibration": {"verdict": "overturned"},
                              "paid": {"new": True, "state": "GATED"}}}}
    assert summarise(busy)["work_done"] == 5
    assert not pipeline.did_no_work(summarise(busy), "visual.rnd.cycle")
    try:
        summarise({"classes": {"a": {"paid": {"state": "executed"}}}})
        raise AssertionError("a paid execution was recorded as work")
    except RuntimeError as e:
        assert "refusing" in str(e)


def test_period_pack_calls_tax_pack_and_handoff_idempotently_and_writes_no_file():
    from brambleloop.autonomy import memory, period_packs

    assert period_packs.last_closed_month(datetime(2026, 1, 5, tzinfo=timezone.utc)) == "2025-12"
    db, tmp = boot()
    before = sorted(os.listdir(tmp))
    now = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
    a = period_packs.build(db, now=now)
    assert a["spec"] == "2026-09" and a["work_done"] == 1 and a["filed"] is False
    assert "NOT FILED" in a["status"] and a["files"] >= 8
    row = memory.get(db, "finance.period_pack:2026-09")
    assert row and row["state"] == "prepared"
    assert "unattributed_share" in row["body"]["cost_attribution"]          # F-907
    assert "journal.csv" in row["body"]["manifest"] and row["body"]["fingerprint"] == \
        a["fingerprint"]
    b = period_packs.build(db, now=now.replace(hour=13))
    assert b["work_done"] == 0 and b["fingerprint"] == a["fingerprint"]
    assert pipeline.did_no_work(b, "finance.accounting.period_pack")
    assert sorted(os.listdir(tmp)) == before            # only the database, no exported file


def test_k15_provider_modules_are_reachable_from_the_runtime_roots():
    from brambleloop.build2 import reachability

    reach = reachability.reachable()
    for mod in ("brambleloop.finance.accounting.tax_pack",
                "brambleloop.finance.accounting.attribution",
                "brambleloop.finance.accounting.handoff",
                "brambleloop.finance.accounting.dashboard",
                "brambleloop.finance.accounting.forecast",
                "brambleloop.autonomy.status", "brambleloop.seo.status",
                "brambleloop.learn.improvement_status", "brambleloop.visual.rnd.status",
                "brambleloop.visual.rnd.loop", "brambleloop.autonomy.period_packs",
                "brambleloop.autonomy.visual_rnd_job"):
        assert mod in reach, mod


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
