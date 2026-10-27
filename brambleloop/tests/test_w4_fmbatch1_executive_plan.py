"""F-602: the executive plan (goals, critical path, priorities, owner decisions) is stored
and read by the swarm allocation, which boosts critical-path lanes within their ceilings."""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.autonomy import executive_plan as EP, memory  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.swarm import orchestrate as orc  # noqa: E402

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def boot():
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='fmb1ep-')}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_plan_has_goals_path_priorities_and_decisions():
    db = boot()
    plan = EP.refresh(db, env={}, now=NOW)
    goals = {g["key"]: g for g in plan["goals"]}
    assert goals["first_sale"]["met"] is None and goals["first_sale"]["reading"] == "UNKNOWN"  # N-3: no order source
    assert goals["sustainable_monthly"]["reading"] == "UNMEASURED"
    assert plan["critical_path"], "a fresh company has closed gates real work waits on"
    counts = [i["unblocks"] for i in plan["critical_path"]]
    assert counts == sorted(counts, reverse=True)
    assert plan["department_priority"][:len(plan["critical_departments"])] == \
        plan["critical_departments"]
    assert plan["owner_decisions"]["count"] != "UNKNOWN"
    assert memory.get(db, EP.MEMORY_KEY)["body"]["priority_agents"] == plan["priority_agents"]


def test_allocation_boosts_only_critical_lanes_with_open_work():
    db = boot()
    q = JobQueue(db)
    q.enqueue("market_radar", "radar.score", {})
    q.enqueue("support", "support.triage", {})
    memory.remember(db, EP.MEMORY_KEY, kind="executive.plan", department="executive",
                    body={"priority_agents": ["market_radar"]}, now=NOW)
    out = orc.allocate(db, now=NOW)
    mr, sup = out["lanes"]["market_radar"], out["lanes"]["support"]
    assert "executive plan: critical path" in mr["boosts"]
    assert "executive plan: critical path" not in sup["boosts"]
    assert out["spend_increase_cad"] == 0.0
    assert mr["granted"] <= max(1, int(mr["cad_available_now"] / orc.LANE_UNIT_COST_CAD))


def test_no_plan_is_no_boost():
    db = boot()
    JobQueue(db).enqueue("market_radar", "radar.score", {})
    out = orc.allocate(db, now=NOW)
    assert not any("executive plan" in b for b in out["lanes"]["market_radar"]["boosts"])


def test_review_n7_a_stale_plan_gives_no_boost():
    """Review cbd4ff1 N-7: a plan older than PLAN_MAX_AGE (refresh failing) stops boosting."""
    import tempfile as _tf
    from datetime import timedelta as _td

    d = _tf.mkdtemp(prefix="fmb1n7_")
    db = Database(f"sqlite:///{d}/n7.db")
    db.create_all()
    old = datetime.now(timezone.utc) - _td(hours=7)
    memory.remember(db, EP.MEMORY_KEY, kind="executive_plan", body={"priority_agents": ["a"]},
                    now=old)
    assert EP.priority_agents(db) == set()
    memory.remember(db, EP.MEMORY_KEY, kind="executive_plan", body={"priority_agents": ["a"]})
    assert EP.priority_agents(db) == {"a"}


def test_n3_first_sale_is_unknown_not_zero_when_the_order_source_is_not_connected():
    """Review cbd4ff1 N-3: zero orders on file with a disconnected source is not a measured
    zero; the goal reads UNKNOWN and `met` is None."""
    import tempfile as _tf
    from datetime import datetime as _d, timezone as _tz

    from brambleloop.autonomy import executive_plan as EP
    from brambleloop.core.db import Database

    d = _tf.mkdtemp(prefix="fmb1n3_")
    db = Database(f"sqlite:///{d}/n3.db")
    db.create_all()
    goals = {g["key"]: g for g in EP._goals(db, _d.now(_tz.utc))}
    fs = goals["first_sale"]
    assert fs["reading"] == "UNKNOWN" and fs["met"] is None, fs
    assert "order source" in fs["basis"]


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
