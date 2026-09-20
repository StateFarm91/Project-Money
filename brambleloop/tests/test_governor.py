"""#188: central budget control, and the three numbers it refuses to invent.

Three of this requirement's four controls are measurements this company cannot take yet.
The tests are mostly about the refusals, because a governor that produces an anomaly score,
a marginal value and a parallelism verdict out of a dollar of spend and no orders is a
governor that will be believed.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import CostEntry, Job, LedgerEntry  # noqa: E402
from brambleloop.finance import governor as G  # noqa: E402

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _db(entries=(), jobs=()):
    db = Database("sqlite://")
    db.create_all()
    with db.session() as s:
        for job_type in jobs:
            s.add(Job(agent="a", job_type=job_type, inputs={}))
        s.flush()
        for kwargs in entries:
            s.add(CostEntry(**kwargs))
    return db


# --- attribution sums to the bill -------------------------------------------------------------

def test_every_dollar_is_attributed_or_named_unattributed():
    """An attribution table that sums to less than the invoice is worse than none, because
    it is acted on -- and the missing spend is always the spend nobody has a story for."""
    db = _db(entries=[
        dict(agent="creative_director", job_id=1, amount_cad=0.27, at=NOW,
             detail={"product": "hex-coaster", "department": "ornaments"}),
        dict(agent="market_radar", amount_cad=0.10, at=NOW, detail={}),
    ], jobs=["creative.tournament"])
    with db.session() as s:
        out = G.spend_by(s, "agent", now=NOW)
    assert out["total_cad"] == 0.37
    assert sum(r["cad"] for r in out["rows"]) + out["unattributed_cad"] == out["total_cad"]
    assert out["reconciles"] is True


def test_spend_with_no_key_in_a_dimension_is_unattributed_rather_than_dropped():
    db = _db(entries=[
        dict(agent="creative_director", job_id=1, amount_cad=0.27, at=NOW,
             detail={"product": "hex-coaster"}),
        dict(agent="market_radar", amount_cad=0.10, at=NOW, detail={}),
    ], jobs=["creative.tournament"])
    with db.session() as s:
        by_task = G.spend_by(s, "task", now=NOW)
        by_product = G.spend_by(s, "product", now=NOW)
    assert by_task["unattributed_cad"] == 0.10      # the entry with no job
    assert by_product["unattributed_cad"] == 0.10   # the entry with no product
    for out in (by_task, by_product):
        assert sum(r["cad"] for r in out["rows"]) + out["unattributed_cad"] == out["total_cad"]


def test_all_five_dimensions_the_requirement_names_are_reconciled():
    db = _db(entries=[dict(agent="a", amount_cad=1.0, at=NOW,
                           detail={"product": "p", "department": "d", "experiment": "e"})])
    with db.session() as s:
        out = G.attribution(s, now=NOW)
    assert set(out["dimensions"]) == {"agent", "task", "product", "department", "experiment"}
    for name, table in out["dimensions"].items():
        assert table["total_cad"] == 1.0, name
        assert table["reconciles"] is True, name


def test_a_dimension_nobody_named_is_refused():
    db = _db()
    with db.session() as s:
        try:
            G.spend_by(s, "vibes", now=NOW)
        except G.GovernorRefused as exc:
            assert "is not a dimension" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("an untraceable dimension was reported")


# --- an anomaly needs a baseline -----------------------------------------------------------------

def test_a_first_observation_is_not_a_spike():
    """A detector with no history fires on the first real day of work, teaches everybody to
    ignore it, and then never fires again."""
    db = _db(entries=[dict(agent="a", amount_cad=25.0, at=NOW)])
    with db.session() as s:
        out = G.anomaly(s, now=NOW)
    assert out["measurable"] is False
    assert out["days_of_history"] == 0
    assert "never fires again" in out["why"]


def test_a_baseline_makes_a_spike_sayable():
    entries = [dict(agent="a", amount_cad=1.0, at=NOW - timedelta(days=d))
               for d in range(1, G.MIN_DAYS_FOR_BASELINE + 1)]
    entries.append(dict(agent="a", amount_cad=40.0, at=NOW))
    db = _db(entries=entries)
    with db.session() as s:
        out = G.anomaly(s, now=NOW)
    assert out["measurable"] is True
    assert out["spike"] is True
    assert out["ordinary_day_cad"] == 1.0


def test_a_dollar_floor_sits_under_the_statistical_threshold():
    """On a base of pennies every multiple is a spike."""
    entries = [dict(agent="a", amount_cad=0.01, at=NOW - timedelta(days=d))
               for d in range(1, G.MIN_DAYS_FOR_BASELINE + 1)]
    entries.append(dict(agent="a", amount_cad=0.05, at=NOW))
    db = _db(entries=entries)
    with db.session() as s:
        out = G.anomaly(s, now=NOW)
    assert out["measurable"] is True
    assert out["spike"] is False           # five times the base, and still five cents
    assert out["threshold_cad"] >= G.SPIKE_FLOOR_CAD


# --- marginal value has a zero numerator -----------------------------------------------------------

def test_no_orders_means_marginal_value_is_unmeasurable_rather_than_zero():
    """Reporting it as zero would justify cutting the spend that has not had time to work."""
    db = _db(entries=[dict(agent="a", amount_cad=1.17, at=NOW)])
    with db.session() as s:
        out = G.marginal_value(s, now=NOW)
    assert out["measurable"] is False
    assert out["orders"] == 0
    assert "arithmetic rather than a finding" in out["why"]
    assert out["needs"] == ["orders attributable to a spend"]
    assert "refuse before a spend" in out["live_control"]


def test_orders_make_it_measurable():
    db = _db(entries=[dict(agent="a", amount_cad=10.0, at=NOW)])
    with db.session() as s:
        s.add(LedgerEntry(category="sale", gross_cad=30.0, evidence_ref="e1"))
    with db.session() as s:
        out = G.marginal_value(s, now=NOW)
    assert out["measurable"] is True
    assert out["return_per_dollar"] == 3.0


# --- parallelism cannot be judged from one setting -------------------------------------------------

def test_one_worker_count_cannot_answer_whether_parallelism_helps():
    out = G.parallelism([{"workers": 4, "minutes": 60, "completed": 40}])
    assert out["advice"] is None
    assert "whatever was running when somebody asked" in out["why"]


def test_a_second_worker_that_added_nothing_is_duplication():
    out = G.parallelism([{"workers": 1, "minutes": 60, "completed": 10},
                         {"workers": 2, "minutes": 60, "completed": 11}])
    assert out["advice"] == "scale_down"
    assert "take turns" in out["why"]


def test_a_second_worker_that_nearly_doubled_throughput_is_worth_keeping():
    out = G.parallelism([{"workers": 1, "minutes": 60, "completed": 10},
                         {"workers": 2, "minutes": 60, "completed": 19}])
    assert out["advice"] == "scale_up"
    assert out["compared"]["throughput_gain"] == 0.9


def test_throughput_is_per_minute_rather_than_per_worker_minute_for_the_verdict():
    """Per-worker-minute always falls when a worker is added; the question is whether the
    queue drained faster, not whether each worker stayed as busy."""
    out = G.parallelism([{"workers": 1, "minutes": 60, "completed": 10},
                         {"workers": 4, "minutes": 60, "completed": 30}])
    assert out["advice"] == "scale_up"
    assert out["observations"][-1]["per_worker_minute"] < out["observations"][0]["per_worker_minute"]


def test_an_observation_with_no_time_or_no_workers_is_refused():
    try:
        G.parallelism([{"workers": 0, "minutes": 60, "completed": 10}])
    except G.GovernorRefused as exc:
        assert "above zero" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an impossible observation was scored")


# --- the report ---------------------------------------------------------------------------------------

def test_the_report_says_which_of_its_controls_are_live():
    db = _db(entries=[dict(agent="a", amount_cad=1.17, at=NOW)])
    with db.session() as s:
        out = G.report(s, now=NOW)
    assert out["anomaly"]["measurable"] is False
    assert out["marginal_value"]["measurable"] is False
    assert out["parallelism"]["advice"] is None
    assert "The ceilings are the live control" in out["note"]


def test_state_lists_what_it_will_not_invent():
    out = G.state()
    assert len(out["will_not_invent"]) == 3
    assert set(out["dimensions"]) == set(G.DIMENSIONS)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
