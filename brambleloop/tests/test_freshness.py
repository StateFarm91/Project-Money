"""Per-department staleness, and the department that is never stale and never moves.

Requirement 191. A single thirty-day constant across every department -- which is what
`improve.profiles` and `improve.bus` each carried -- is far too slow for a competitor's
catalogue and meaningless for the compiler, and it is the arrangement this requirement is
written against.

The test that matters most is `test_a_department_that_is_on_time_and_flat_is_not_healthy`.
A freshness SLA measured in "when did we last look" rewards looking, and a department
re-running a scan every hour and learning nothing scores perfectly on recency. That is the
commonest real state of an improvement programme, and one clock cannot see it.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import cells  # noqa: E402
from brambleloop.improve import freshness as F  # noqa: E402

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def _db() -> Database:
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/freshness.sqlite")
    db.create_all()
    return db


def _points(db, cell: str, values, *, ages_days):
    """Record measurements and back-date them, since record_capability stamps `now`."""
    from brambleloop.core.models import CapabilityPoint

    ids = [cells.record_capability(db, cell, v) for v in values]
    with db.session() as s:
        for pid, age in zip(ids, ages_days):
            s.get(CapabilityPoint, pid).at = NOW - timedelta(days=age)
    return ids


# ---- the interval comes from the world, not from taste --------------------


def test_every_cell_has_a_declared_world_and_none_is_defaulted():
    for spec in cells.CELLS:
        assert spec.key in F.CELL_WORLD, spec.key
        F.sla(spec.key)


def test_a_cell_with_no_declared_world_is_refused_rather_than_defaulted():
    saved = F.CELL_WORLD.pop("pricing")
    try:
        F.sla("pricing")
    except F.FreshnessRefused as e:
        assert "single default interval" in str(e)
    else:  # pragma: no cover
        raise AssertionError("a cell took a default interval")
    finally:
        F.CELL_WORLD["pricing"] = saved


def test_an_adversarial_world_is_reconsidered_far_sooner_than_an_operational_one():
    assert F.sla("market_radar").hours < F.sla("finance").hours
    assert F.sla("seo_search").world == F.ADVERSARIAL


def test_compiler_mathematics_has_no_interval_rather_than_a_long_one():
    """A long interval reports it current for another month after the compiler changed."""
    spec = F.sla("pattern_engineering")
    assert spec.world == F.MATHEMATICAL
    assert spec.hours is None
    assert "fingerprint question" in spec.why


def test_an_unknown_cell_is_refused():
    try:
        F.sla("vibes")
    except F.FreshnessRefused as e:
        assert "not an improvement cell" in str(e)
    else:  # pragma: no cover
        raise AssertionError("an invented cell got an SLA")


# ---- clock one: evidence age ----------------------------------------------


def test_evidence_inside_its_own_interval_is_fresh():
    db = _db()
    _points(db, "market_radar", [1.0], ages_days=[0])
    assert F.evidence_age(db, "market_radar", now=NOW)["verdict"] == F.FRESH


def test_the_same_age_is_stale_for_one_department_and_fresh_for_another():
    """Two days old: yesterday's news for the radar, current for the ledger."""
    db = _db()
    _points(db, "market_radar", [1.0], ages_days=[2])
    _points(db, "finance", [1.0], ages_days=[2])
    assert F.evidence_age(db, "market_radar", now=NOW)["verdict"] == F.STALE
    assert F.evidence_age(db, "finance", now=NOW)["verdict"] == F.FRESH


def test_never_measured_is_its_own_verdict_and_not_stale():
    db = _db()
    out = F.evidence_age(db, "growth", now=NOW)
    assert out["verdict"] == F.NEVER_MEASURED
    assert "buries the second kind under the first" in out["why"]


def test_a_mathematical_cell_with_no_fingerprint_says_it_cannot_tell():
    db = _db()
    _points(db, "pattern_engineering", [1.0], ages_days=[400])
    out = F.evidence_age(db, "pattern_engineering", now=NOW)
    assert out["verdict"] == F.NOT_TIME_BASED
    assert "unknown rather than yes" in out["why"]


def test_a_mathematical_cell_goes_stale_when_the_code_changes_not_when_time_passes():
    db = _db()
    _points(db, "pattern_engineering", [1.0], ages_days=[400])
    same = F.evidence_age(db, "pattern_engineering", now=NOW,
                          code_fingerprint="abc", verified_fingerprint="abc")
    moved = F.evidence_age(db, "pattern_engineering", now=NOW,
                           code_fingerprint="def", verified_fingerprint="abc")
    assert same["verdict"] == F.FRESH, "four hundred days old and still correct"
    assert moved["verdict"] == F.FINGERPRINT_CHANGED
    assert "only way its evidence goes stale" in moved["why"]


# ---- clock two: capability movement ---------------------------------------


def test_a_direction_needs_three_measurements():
    db = _db()
    _points(db, "growth", [0.1, 0.5], ages_days=[10, 2])
    out = F.capability_movement(db, "growth", now=NOW)
    assert out["verdict"] == F.UNMEASURED
    assert "line through two points" in out["why"]


def test_a_rising_number_is_improvement_only_where_higher_is_better():
    """Half of these metrics are better when they fall, and rewarding every rise
    congratulates a department for breaking."""
    db = _db()
    _points(db, "growth", [1.0, 2.0, 3.0], ages_days=[20, 10, 1])           # higher better
    _points(db, "runtime", [1.0, 2.0, 3.0], ages_days=[20, 10, 1])          # lower better
    assert F.capability_movement(db, "growth", now=NOW)["verdict"] == F.IMPROVING
    assert F.capability_movement(db, "runtime", now=NOW)["verdict"] == F.DECLINING


def test_a_falling_defect_rate_is_improvement():
    db = _db()
    _points(db, "runtime", [10.0, 6.0, 3.0], ages_days=[20, 10, 1])
    assert F.capability_movement(db, "runtime", now=NOW)["verdict"] == F.IMPROVING


def test_noise_below_the_threshold_is_flat():
    db = _db()
    _points(db, "growth", [1.000, 1.005, 1.004], ages_days=[20, 10, 1])
    out = F.capability_movement(db, "growth", now=NOW)
    assert out["verdict"] == F.FLAT
    assert "different noise on it" in out["why"]


def test_measurements_outside_the_window_do_not_count():
    db = _db()
    _points(db, "growth", [1.0, 2.0, 3.0], ages_days=[400, 380, 360])
    assert F.capability_movement(db, "growth", now=NOW)["verdict"] == F.UNMEASURED


# ---- the two clocks disagreeing -------------------------------------------


def test_a_department_that_is_on_time_and_flat_is_not_healthy():
    """The whole reason there are two clocks."""
    db = _db()
    _points(db, "finance", [1.000, 1.004, 1.002], ages_days=[20, 10, 0])
    out = F.department(db, "finance", now=NOW)
    assert out["evidence"]["verdict"] == F.FRESH
    assert out["capability"]["verdict"] == F.FLAT
    assert out["state"] == F.CHURNING
    assert "freshness check alone reports it as healthy" in out["why"]


def test_fresh_and_moving_is_healthy():
    """`growth` counts loops with evidence, where higher is better. Using `finance` here
    would have read a rising forecast *error* as progress, which is the polarity trap the
    movement check exists to avoid -- and which this test fell into first time."""
    db = _db()
    _points(db, "growth", [1.0, 2.0, 3.0], ages_days=[20, 10, 0])
    assert F.department(db, "growth", now=NOW)["state"] == F.HEALTHY


def test_a_declining_department_is_at_risk_even_while_fresh():
    db = _db()
    _points(db, "runtime", [1.0, 4.0, 9.0], ages_days=[20, 10, 0])
    out = F.department(db, "runtime", now=NOW)
    assert out["evidence"]["verdict"] == F.FRESH
    assert out["state"] == F.AT_RISK


def test_a_never_measured_department_is_at_risk_with_nothing_to_be_stale_about():
    db = _db()
    out = F.department(db, "seo_search", now=NOW)
    assert out["state"] == F.AT_RISK
    assert "nothing to be fresh or stale about" in out["why"]


# ---- the sweep the orchestrator reads --------------------------------------


def test_the_sweep_flags_the_three_things_the_requirement_names():
    db = _db()
    _points(db, "market_radar", [1.0, 2.0, 3.0], ages_days=[20, 10, 5])   # stale, improving
    _points(db, "finance", [1.000, 1.003, 1.001], ages_days=[20, 10, 0])  # fresh, flat
    out = F.sweep(db, now=NOW)
    assert "market_radar" in out["stale_learning"]
    assert "finance" in out["not_improving"]
    assert "finance" in out["churning"]
    assert len(out["never_measured"]) == len(cells.CELLS) - 2


def test_the_sweep_reports_every_cell_and_its_interval():
    db = _db()
    out = F.sweep(db, now=NOW)
    assert len(out["departments"]) == len(cells.CELLS)
    assert set(out["intervals"]) == {c.key for c in cells.CELLS}


def test_never_measured_is_kept_out_of_the_stale_list():
    db = _db()
    out = F.sweep(db, now=NOW)
    assert out["stale_learning"] == []
    assert len(out["never_measured"]) == len(cells.CELLS)


def test_a_mathematical_cell_is_flagged_stale_by_a_changed_fingerprint_in_the_sweep():
    db = _db()
    _points(db, "pattern_engineering", [1.0], ages_days=[1])
    out = F.sweep(db, now=NOW, fingerprints={"pattern_engineering": ("new", "old")})
    assert "pattern_engineering" in out["stale_learning"]


def test_state_says_what_it_replaces_and_why_it_is_not_one_number():
    out = F.state()
    assert out["requirement"] == 191
    assert "single 30-day constant" in out["replaces"]
    assert out["worlds"][F.MATHEMATICAL]["hours"] is None
    assert any("no declared world speed" in r for r in out["refuses"])


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
