"""W4-F454 Department Agents: every focused domain the requirement names has an agent doing its
work, inside the existing eleven charters (no new department)."""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import DEFAULT_AGENTS, FORBIDDEN_COMBINATIONS, Registry  # noqa: E402
from brambleloop.autonomy import charters, departments  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401
from brambleloop.runtime.worker import CADENCES, handlers  # noqa: E402

FOCUSED = {"analyst": ("learn", ("improve.measure",)),
           "integration_steward": ("platform", ("ops.dependencies", "etsy.openapi_reverify"))}


def test_every_named_domain_has_a_focused_agent_in_an_existing_charter():
    assert charters.validate() == [] and len(charters.CHARTERS) == 11      # no new department
    assert set(departments.DOMAINS) == {
        "research", "pattern_cir_engineering", "visuals", "qa", "etsy_commerce",
        "seo_marketing", "catalogue", "analytics", "customer_experience", "finance_cost",
        "reliability", "integration"}
    assert all(departments.DOMAINS[d] for d in departments.DOMAINS)
    out = departments.coverage()
    assert out["domains_missing"] == []
    assert "analyst" in charters.BY_KEY["learn"].agents
    assert "integration_steward" in charters.BY_KEY["platform"].agents
    assert "integration_steward" in charters.BY_KEY["store_commerce"].agents


def test_the_focused_agents_do_the_domain_work_and_nothing_else():
    db = Database("sqlite://")
    db.create_all()
    Registry(db).seed_defaults()
    names = {a.name for a in Registry(db).all()}
    by = {a["name"]: a for a in DEFAULT_AGENTS}
    assert FOCUSED
    for agent, (_charter, jobs) in FOCUSED.items():
        assert agent in names
        assert by[agent]["daily_cost_ceiling_cad"] == 0.0
        assert jobs, agent
        for jt in jobs:
            assert jt in by[agent]["allowed_job_types"] and handlers.get(jt) is not None
            assert any(a == agent and j == jt for _n, a, j, _p in CADENCES), (agent, jt)
            # The orchestrator keeps its path: nothing that ran before loses permission.
            assert jt in by["orchestrator"]["allowed_job_types"], jt
        for banned in ("cir.draft", "gate.certify", "store.publish", "ads.campaign"):
            assert banned in FORBIDDEN_COMBINATIONS[agent]
    amap = json.loads((ROOT / "src/brambleloop/autonomy/autonomy_map.json").read_text())
    text = json.dumps(amap)
    assert '"analyst"' in text and '"integration_steward"' in text


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
