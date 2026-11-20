"""The scale/kill routing table: deterministic rows, UNLEARNED thresholds, a sample floor (#23).

Every observed count here is a test fixture. The production inputs are all UNMEASURED, and
`state()` says so row by row.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.commerce import kill_table as K  # noqa: E402
from brambleloop.growth.loops import MEASURED_SAMPLE  # noqa: E402
from brambleloop.scale import runrate  # noqa: E402
from brambleloop.scale.runrate import Observed  # noqa: E402


def test_every_threshold_is_unlearned_and_names_its_source():
    state = K.state()
    assert state["all_thresholds_unlearned"] is True
    for t in K.THRESHOLDS.values():
        assert t.status == K.UNLEARNED and t.source
    assert set(state["inputs_today"].values()) == {K.UNMEASURED}


def test_the_defect_ceilings_flip_where_runrate_flips():
    base = Observed(visits=5000, impressions=100000, orders=100, revenue_cad=1000.0,
                    contribution_cad=800.0, repeat_orders=5)
    just_over = runrate.constraint(base, support_rate=K.DEFECT_SUPPORT_RATE + 0.001)
    at = runrate.constraint(base, support_rate=K.DEFECT_SUPPORT_RATE)
    assert just_over.get("rule") == "rising_defects"
    assert at.get("rule") != "rising_defects"
    assert runrate.constraint(base, refund_rate=K.DEFECT_REFUND_RATE + 0.001)["rule"] \
        == "rising_defects"


def test_nothing_observed_waits_and_never_routes_to_kill():
    out = K.route(Observed())
    assert out["verdict"] == "wait"
    assert set(out["unmeasured"]) == {"impressions", "visits", "orders"}
    assert all(r["status"] == K.UNMEASURED for r in out["rows"])


def test_below_the_visit_floor_no_rate_rule_fires():
    thin = Observed(impressions=2000, visits=MEASURED_SAMPLE - 1, orders=0)
    out = K.route(thin)
    assert out["verdict"] == "wait" and out["enough_sample"] is False
    rate_rows = [r for r in out["rows"] if r["key"] != "high_sales_high_support"]
    assert all(r["status"] == K.UNMEASURED for r in rate_rows)


def test_each_diagnosis_routes_to_its_owner():
    n = MEASURED_SAMPLE * 10
    weak_ctr = Observed(impressions=n * 1000, visits=n, orders=int(n * 0.05))
    assert K.route(weak_ctr)["verdict"] == "weak_ctr"
    assert K.route(weak_ctr)["owner"] == "creative"

    strong_ctr_weak_conv = Observed(impressions=n * 20, visits=n, orders=0)
    assert K.route(strong_ctr_weak_conv)["verdict"] == "strong_ctr_weak_conversion"

    closes_nobody_comes = Observed(impressions=n * 20, visits=n, orders=int(n * 0.05))
    out = K.route(closes_nobody_comes, needed_visits=n * 10)
    assert out["verdict"] == "strong_conversion_low_traffic" and out["owner"] == "growth"

    both_weak = Observed(impressions=n * 1000, visits=n, orders=0)
    assert K.route(both_weak)["verdict"] == "weak_ctr_and_weak_conversion"

    defect = Observed(impressions=n * 20, visits=n, orders=40)
    out = K.route(defect, support_cases=10, refunds=0)
    assert out["verdict"] == "high_sales_high_support" and out["owner"] == "quality"


def test_a_defect_rate_over_too_few_orders_is_not_read():
    from brambleloop.commerce.benchmarks import MIN_ORDERS_FOR_REFUND_RATE

    few = Observed(impressions=20000, visits=1000, orders=MIN_ORDERS_FOR_REFUND_RATE - 1)
    out = K.route(few, support_cases=3, refunds=3)
    assert out["signals"]["support_rate"] is None
    assert out["verdict"] != "high_sales_high_support"


def test_compose_reports_whether_the_table_and_runrate_agree():
    n = MEASURED_SAMPLE * 10
    out = K.compose(Observed(impressions=n * 1000, visits=n, orders=int(n * 0.05),
                             revenue_cad=500.0, contribution_cad=400.0))
    assert "agreement" in out
    if out["agreement"]["comparable"]:
        assert "agree" in out["agreement"]
    empty = K.compose(Observed())
    assert empty["agreement"]["comparable"] is False


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"{sum(1 for n in globals() if n.startswith('test_')) - fails} passing, {fails} failing")
    sys.exit(1 if fails else 0)
