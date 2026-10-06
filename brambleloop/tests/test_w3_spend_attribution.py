"""Wave-3 lane SPEND, K5a: spend attribution and reporting.

F-303 closed economic class, F-320 per-stage product creation cost, F-110 escalation names
the constrained work, F-183 one spend vocabulary, F-184 binding ceiling. Consumers:
`spend_report.governance` (served at /api/spend-governance), `spend_report.what_it_bought`,
`unit_cost.unit_costs` (governor + /api dashboard), `spend_policy.escalation`. Ledger rows
are written directly; nothing is paid.

Run: cd brambleloop && PYTHONPATH=src python tests/test_w3_spend_attribution.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from r2_autonomy_harness import boot, run_tests


def _now():
    return datetime.now(timezone.utc)


def _cost(db, amount, purpose, kind="llm", product="", agent="creative_director"):
    from brambleloop.core.models import CostEntry

    with db.session() as s:
        s.add(CostEntry(at=_now() - timedelta(minutes=5), agent=agent, amount_cad=amount,
                        kind=kind, purpose=purpose, product_slug=product, provider="anthropic"))


def test_every_row_has_one_closed_economic_class():
    from brambleloop.finance import economics, spend_report

    db = boot()
    _cost(db, 1.0, "concept.naming@1")
    _cost(db, 2.0, "gallery_observation")
    _cost(db, 0.5, "a.purpose.nobody.declared")
    got = spend_report.what_it_bought(db)["by_economic_class"]
    assert set(got["classes"]) == set(economics.CLASSES)
    assert got["classes"][economics.CREATION]["cad"] == 1.0
    assert got["classes"][economics.RECURRING]["cad"] == 2.0
    assert got["one_time_cad"] == 1.0 and got["recurring_cad"] == 2.0, got
    assert got["unclassified_cad"] == 0.5
    assert got["unclassified_purposes"] == ["a.purpose.nobody.declared"]
    assert economics.classify("x", "image")["stage"] == "imagery"


def test_product_creation_cost_is_split_by_stage():
    from brambleloop.finance import economics, unit_cost

    db = boot()
    _cost(db, 1.0, "concept_generation", product="fern-throw")
    _cost(db, 0.4, "asset_inspection", product="fern-throw")
    _cost(db, 0.3, "image.generate", kind="image", product="fern-throw")
    _cost(db, 0.2, "listing_copy", product="fern-throw")
    _cost(db, 0.1, "who.knows", product="fern-throw")
    direct = economics.product_creation_cost(db, "fern-throw")
    assert direct["by_stage"]["concept"] == 1.0 and direct["by_stage"]["judging"] == 0.4
    assert direct["by_stage"]["imagery"] == 0.3 and direct["by_stage"]["listing"] == 0.2
    assert direct["by_stage"]["unstaged"] == 0.1 and direct["by_provider"]["anthropic"] > 0
    assert economics.product_creation_cost(db, "ghost")["basis"] == "unknown"
    report = unit_cost.unit_costs(db)
    assert report["by_product_stage"]["fern-throw"]["concept"] == 1.0, report


def test_escalation_collects_what_is_constrained():
    from brambleloop.finance import spend_policy, spend_report
    from brambleloop.gateway import anthropic as gw

    db = boot()
    _cost(db, spend_policy.CEILING_CAD * 0.85, "gallery_observation")
    try:
        gw.check_budget_cad(db, estimate_cad=50.0, agent="creative_director",
                            purpose="concept_generation")
    except gw.BudgetExceeded:
        pass
    report = spend_policy.escalation(db)
    assert report["required"] is True
    text = " | ".join(report["what_is_constrained"])
    assert "gallery_observation: stopped by its allocation" in text, text
    assert "concept_generation: refused 1 time(s)" in text, text
    gov = spend_report.governance(db)
    assert gov["escalation"]["what_is_constrained"], gov["escalation"]


def test_binding_ceiling_and_vocabulary_are_in_the_governance_reading():
    from brambleloop.finance import spend_policy, spend_report

    db = boot()
    _cost(db, 1.0, "gallery_observation")
    gov = spend_report.governance(db)
    binding = gov["binding"]
    assert binding["binding"]["remaining_cad"] <= binding["company_binding"]["remaining_cad"]
    kinds = {row["limit"] for row in binding["limits"]}
    assert {"monthly model ceiling", "purpose allocation"} <= kinds, kinds
    assert len(binding["precedence"]) >= 5 and binding["unset"]["provider_ceilings"] is True
    for row in binding["limits"]:
        assert row["effective_remaining_cad"] <= binding["company_binding"]["remaining_cad"]
    terms = {row["term"] for row in gov["vocabulary"]}
    for needed in ("monthly model ceiling", "infrastructure ceiling",
                   "research/benchmark authority", "paid-media (ad) authority",
                   "agent daily permission", "department allocations"):
        assert needed in terms, (needed, terms)
    infra = next(r for r in gov["vocabulary"] if r["term"] == "infrastructure ceiling")
    assert infra["basis"] == spend_policy.INFRA_BASIS


if __name__ == "__main__":
    run_tests(globals())
