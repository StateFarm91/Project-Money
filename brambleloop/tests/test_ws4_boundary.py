"""WS4-4: the pure in/out decision (design §4.1; the §3.3 checks at the classifier layer).

One test per check: each makes exactly one fact non-PASS (FAIL, UNKNOWN or missing), or one
value out of policy, and asserts OUT with that reason. A control makes everything PASS and
asserts IN. No I/O, no database.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # noqa: E702
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from brambleloop.ops import standing_boundary as sb  # noqa: E402
from brambleloop.products import launch0  # noqa: E402
from test_ws4_policy_object import content  # noqa: E402

P = sb.PASS


def _ok(value=True):
    return {"state": P, "value": value, "why": None}


def facts(**over) -> dict:
    f = {name: _ok() for name in sb.GATE_FACTS}
    f.update({
        "slug": _ok("mosaic-coaster-set"), "category": _ok("coaster"),
        "risk_declared": _ok("A"), "risk_derived": _ok("A"),
        "physical_held": _ok(["partial_physical"]), "price_cad": _ok(8.00),
        "sizes": _ok(1), "colourwork": _ok(True), "wearable": _ok(False),
        "grants_today": _ok({"consumed": 0, "outstanding": 0}),
        "grants_7d": _ok({"consumed": 0, "outstanding": 0}),
        "outstanding": _ok(0), "minutes_since_last": _ok(None), "ads_jobs_queued": _ok(0),
        "shop_id": _ok("12345678"), "shop_name": _ok("BrambleloopStudio")})
    for k, v in over.items():
        if v is None:
            f.pop(k, None)
        else:
            f[k] = v if isinstance(v, dict) and "state" in v else _ok(v)
    return f


def _out(result, needle):
    assert result["in_policy"] is False, result
    assert any(needle in r for r in result["reasons"]), (needle, result["reasons"])


def test_control_everything_pass_is_in_policy():
    r = sb.classify(content(), facts())
    assert r == {"in_policy": True, "reasons": [], "class_id": "flat-colourwork-A",
                 "effective_risk": "A"}, r


def test_every_gate_fact_failing_unknown_or_missing_is_out():
    """M1/M2: UNKNOWN (a reader that raised) and FAIL both hold; a missing fact holds."""
    for name in sb.GATE_FACTS:
        for bad in ({"state": sb.FAIL, "value": None, "why": "fixture"},
                    {"state": sb.UNKNOWN, "value": None, "why": "reader raised"},
                    {"state": "MAYBE", "value": True, "why": None}):
            _out(sb.classify(content(), facts(**{name: bad})), name)
        _out(sb.classify(content(), facts(**{name: None})), name)


def test_the_required_facts_are_exactly_the_design_checks():
    """A fact dropped from the list would silently stop being required: pinned here."""
    assert sb.GATE_FACTS == (
        "kill_switch", "policy_enabled", "mode_t", "phase_may_publish",
        "stop_conditions_clear", "stop_watch_fresh", "not_experiment", "taxonomy_agrees",
        "publication_evidence", "release_gates", "deterministic_reverify",
        "owner_attested_physical", "independent_vision_review", "no_fake_discount",
        "not_on_etsy", "no_publish_incomplete")
    assert sb.VALUE_FACTS == (
        "slug", "category", "risk_declared", "risk_derived", "physical_held", "price_cad",
        "sizes", "colourwork", "wearable", "grants_today", "grants_7d", "outstanding",
        "minutes_since_last", "ads_jobs_queued", "shop_id", "shop_name")


def test_every_value_fact_unknown_or_missing_is_out():
    for name in sb.VALUE_FACTS:
        _out(sb.classify(content(), facts(**{name: {"state": sb.UNKNOWN, "value": None,
                                                    "why": "x"}})), name)
        _out(sb.classify(content(), facts(**{name: None})), name)


def test_a_policy_failing_the_code_ceilings_is_out():
    bad = content(frequency={"max_per_day": 4, "max_per_7d": 6, "min_spacing_minutes": 0,
                             "max_outstanding_unconsumed_grants": 1})
    _out(sb.classify(bad, facts()), "code ceilings")
    _out(sb.classify({"schema": "something/2"}, facts()), "code ceilings")


def test_an_action_the_policy_does_not_name_is_out():
    _out(sb.classify(content(), facts(), action="store.activate"), "store.activate")


def test_launch0_held_and_excluded_slugs_are_always_out():
    """M17 / T-ST-5: Launch-0 and held products are never in policy."""
    for slug in launch0.LAUNCH0_SLUGS + launch0.HELD_FOR_VERIFICATION:
        _out(sb.classify(content(), facts(slug=slug)), "Launch-0 or held")
    c = content(exclusions={"launch0_slugs": "ALWAYS", "slugs": ["mosaic-coaster-set"],
                            "categories": []})
    _out(sb.classify(c, facts()), "excluded by the policy")


def test_category_must_match_exactly_one_class():
    """M18: zero matches, an excluded category, and an ambiguous (two-class) match are out."""
    _out(sb.classify(content(), facts(category="garment")), "excluded by the policy")
    _out(sb.classify(content(), facts(category="wall_hanging")), "matches 0 policy classes")
    c = content()
    twin = copy.deepcopy(c["product_classes"][0])
    twin["class_id"] = "second"
    c["product_classes"].append(twin)
    c["owner_statement_digest"] = "0" * 64
    from brambleloop.ops import standing_policy as sp

    c["owner_statement_digest"] = sp.statement_digest(c)
    _out(sb.classify(c, facts()), "matches 2 policy classes")


def test_the_effective_risk_class_is_max_of_declared_and_derived():
    """M12: a CIR declaring A whose derived class is B is a B product."""
    r = sb.classify(content(), facts(risk_declared="A", risk_derived="B"))
    _out(r, "effective risk class B exceeds the class's A")
    assert r["effective_risk"] == "B"
    _out(sb.classify(content(), facts(risk_declared="B", risk_derived="A")),
         "effective risk class B")
    _out(sb.classify(content(), facts(risk_declared="Z")), "risk class unreadable")
    c = content()
    c["product_classes"][0]["max_effective_risk_class"] = "B"
    from brambleloop.ops import standing_policy as sp

    c["owner_statement_digest"] = sp.statement_digest(c)
    r = sb.classify(c, facts(risk_declared="A", risk_derived="B"))
    assert r["in_policy"] is True and r["effective_risk"] == "B", r


def test_physical_evidence_meets_both_the_risk_class_and_the_class_requirement():
    """M23: the class's stricter physical_required applies even when the risk class asks
    for less; and a risk-B product needs partial physical evidence whatever the class says."""
    from brambleloop.ops import standing_policy as sp

    _out(sb.classify(content(), facts(physical_held=[])), "partial_physical is required")
    strict = content()
    strict["product_classes"][0]["physical_required"] = "full_physical_make"
    strict["owner_statement_digest"] = sp.statement_digest(strict)
    _out(sb.classify(strict, facts(physical_held=["partial_physical"])),
         "full_physical_make is required")
    assert sb.classify(strict, facts(physical_held=["full_physical_make"]))["in_policy"]
    lax = content()
    lax["product_classes"][0].update(physical_required="none", max_effective_risk_class="B")
    lax["owner_statement_digest"] = sp.statement_digest(lax)
    _out(sb.classify(lax, facts(risk_derived="B", physical_held=[])),
         "partial_physical is required")
    assert sb.classify(lax, facts(risk_derived="A", physical_held=[]))["in_policy"]
    _out(sb.classify(content(), facts(physical_held="partial_physical")), "unreadable")


def test_price_band_is_inclusive_and_exact_to_the_cent():
    """M19: both ends are in; one cent outside either end is out; sub-cent prices are out."""
    for price in (4.00, 4, "4.00", 12.00, 11.99):
        assert sb.classify(content(), facts(price_cad=price))["in_policy"], price
    for price in (3.99, 12.01, 12.005, 8.005, "8.001", float("nan"), "free", True):
        _out(sb.classify(content(), facts(price_cad=price)), "price")


def test_sizes_colourwork_and_wearables_follow_the_class():
    _out(sb.classify(content(), facts(sizes=2)), "sizes")
    _out(sb.classify(content(), facts(sizes=0)), "sizes")
    _out(sb.classify(content(), facts(wearable=True)), "wearable is not allowed")
    _out(sb.classify(content(), facts(wearable="no")), "wearable: unreadable")
    from brambleloop.ops import standing_policy as sp

    c = content()
    c["product_classes"][0]["colourwork_allowed"] = False
    c["owner_statement_digest"] = sp.statement_digest(c)
    _out(sb.classify(c, facts(colourwork=True)), "colourwork is not allowed")
    assert sb.classify(c, facts(colourwork=False))["in_policy"]


def test_frequency_counts_outstanding_as_well_as_consumed():
    """M20: one consumed plus one outstanding is two issued today (max_per_day 2)."""
    _out(sb.classify(content(), facts(grants_today={"consumed": 1, "outstanding": 1})),
         "grants_today: 2 issued")
    _out(sb.classify(content(), facts(grants_today={"consumed": 0, "outstanding": 2})),
         "grants_today: 2 issued")
    assert sb.classify(content(), facts(grants_today={"consumed": 1, "outstanding": 0}))[
        "in_policy"]
    _out(sb.classify(content(), facts(grants_7d={"consumed": 5, "outstanding": 1})),
         "grants_7d: 6 issued")
    _out(sb.classify(content(), facts(grants_today={"consumed": -1, "outstanding": 0})),
         "grants_today: unreadable")
    _out(sb.classify(content(), facts(outstanding=1)), "unconsumed grant(s) outstanding")
    _out(sb.classify(content(), facts(minutes_since_last=179)), "minutes since the last")
    assert sb.classify(content(), facts(minutes_since_last=180))["in_policy"]
    _out(sb.classify(content(), facts(minutes_since_last=-5)), "unreadable")


def test_ads_and_shop_must_match():
    _out(sb.classify(content(), facts(ads_jobs_queued=1)), "ads must be NONE")
    _out(sb.classify(content(), facts(shop_id="87654321")), "is not the policy's shop")
    _out(sb.classify(content(), facts(shop_name="Other")), "shop name")


def test_classify_reports_every_reason_not_just_the_first():
    r = sb.classify(content(), facts(kill_switch={"state": sb.FAIL, "value": None,
                                                  "why": "off"},
                                     price_cad=99.0, ads_jobs_queued=2))
    assert len(r["reasons"]) >= 3 and r["class_id"] is None, r


def test_classify_has_no_io():
    """Pure: it never opens a database session or reads the environment for a decision."""
    import ast
    from pathlib import Path

    src = Path(sb.__file__).read_text()
    tree = ast.parse(src)
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    for forbidden in ("session", "environ", "getenv", "open", "requests", "urlopen"):
        assert forbidden not in names, forbidden


if __name__ == "__main__":
    import _minipytest

    _minipytest.run_module(globals())
