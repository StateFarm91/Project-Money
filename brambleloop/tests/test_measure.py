"""One deterministic measurer per capability cell, and the first reading is never a win.

Requirements 90, 94, 193. Production reported twelve of twelve cells unmeasured because
nothing called `cells.record_capability`. These tests hold the measurer to three rules: an
empty source records nothing (a zero there would read as "defects: none"), a data-gated cell
names the table it needs, and the same rows give the same number -- recorded once, not once
per run, so the plateau detector is not fed copies.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.improve import cells, measure  # noqa: E402

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
DATA_GATED = ("pricing", "customer_experience", "portfolio", "finance", "growth")


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _seed(db):
    """Rows for the seven cells shadow mode can measure. No sale, so five stay data-gated."""
    from brambleloop.core.models import (AuditLog, BenchmarkObservation, Job, JobStatus,
                                         Keyword, ListingAsset, PatternVersion, Product)

    with db.session() as s:
        p = Product(slug="cable-throw", title="Cable Throw")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1.0.0", cir_json={}, certified=True,
                             created_at=NOW - timedelta(days=3)))
        s.add(PatternVersion(product_id=p.id, version="1.0.1", cir_json={}, certified=False,
                             created_at=NOW - timedelta(days=2)))
        s.add(ListingAsset(product_slug="cable-throw", version="1.0.0", position=1,
                           asset_class="photo", role="hero", approved=True))
        s.add(ListingAsset(product_slug="cable-throw", version="1.0.0", position=2,
                           asset_class="photo", role="detail", approved=False))
        for phrase in ("crochet blanket pattern pdf", "blanket crochet pattern",
                       "crochet cardigan"):
            s.add(Keyword(phrase=phrase))
        s.add(BenchmarkObservation(at=NOW - timedelta(hours=10), benchmark_key="mjs",
                                   listing_ref="L1", kind="gallery"))
        s.add(Job(agent="a", job_type="t", status=JobStatus.DEAD, inputs={},
                  created_at=NOW - timedelta(days=2)))
        s.add(Job(agent="a", job_type="t", status=JobStatus.DONE, inputs={},
                  created_at=NOW - timedelta(days=1)))
        s.add(AuditLog(actor="creative_director", action="creative.tournament",
                       detail={"field": {"generated": 10}, "survivors": [{}, {}],
                               "research_kill_rate": 0.8, "causes": {"sameness": 8}}))


def test_every_cell_has_exactly_one_measurer():
    assert set(measure.MEASURERS) == {c.key for c in cells.CELLS}
    assert len(measure.MEASURERS) == 13  # twelve + learn (F-799)


def test_an_empty_source_records_nothing_and_says_which_table_it_needs():
    db = _db()
    out = measure.record_all(db, now=NOW)
    assert out["found"] == 0 and out["recorded"] == []
    assert set(out["skipped"]) == {c.key for c in cells.CELLS}
    for key in DATA_GATED:
        assert out["skipped"][key]["reason"].startswith("data-gated: needs"), key
    assert cells.capability_history(db, "quality") == []


def test_a_measurement_over_zero_rows_is_refused():
    try:
        measure.Measurement("quality", 0.0, 0)
    except measure.MeasureRefused:
        return
    raise AssertionError("a zero-sample measurement was accepted")


def test_the_seeded_cells_measure_the_rows_they_name():
    db = _db()
    _seed(db)
    out = measure.record_all(db, now=NOW)
    values = {r["cell"]: r["value"] for r in out["recorded"]}
    assert values["pattern_engineering"] == 0.5          # one certified of two compiled
    assert values["creative_assets"] == 0.5              # one blocked of two assets
    assert values["seo_search"] == 2.0                   # blanket and cardigan clusters
    assert values["market_radar"] == 10.0                # ten hours old
    assert values["runtime"] == 0.5                      # one dead letter over two days
    assert values["product_creativity"] == 0.2           # two survivors of ten
    assert values["quality"] == 0.0                      # certified, no escaped incident
    for key in DATA_GATED:
        assert key not in values and out["skipped"][key]["reason"].startswith("data-gated")


def test_the_same_rows_give_the_same_reading_once():
    """Two runs over unchanged rows write one point per cell, not two: copies of one number
    are what the plateau detector reads as a flat capability."""
    db = _db()
    _seed(db)
    first = measure.record_all(db, now=NOW)
    second = measure.record_all(db, now=NOW)
    assert second["found"] == 0
    assert sorted(second["repeated"]) == sorted(r["cell"] for r in first["recorded"])
    assert len(cells.capability_history(db, "pattern_engineering")) == 1


def test_a_first_measurement_is_a_baseline_never_a_win():
    db = _db()
    hypothesis = ("measuring pattern certification should reveal where first-pass "
                  "failures come from before anything changes")
    before = cells.propose(db, cell="pattern_engineering", hypothesis=hypothesis,
                           expected_effect="a baseline", rollback_ref="capability:none",
                           touches=("weights",))
    assert cells.test_result(db, before, 0.9) == cells.REJECTED   # nothing to beat

    _seed(db)
    measure.record_all(db, now=NOW)
    after = cells.propose(db, cell="pattern_engineering", hypothesis=hypothesis,
                          expected_effect="a real comparison", rollback_ref="capability:1",
                          touches=("weights",))
    from brambleloop.core.models import Improvement
    with db.session() as s:
        # The baseline is the measurer's reading, taken before this change existed.
        assert s.get(Improvement, after).baseline_value == 0.5


def test_state_names_every_measurer_and_the_rules():
    out = measure.state()
    assert len(out["measurers"]) == 13
    assert any("baseline, never a win" in r for r in out["rules"])


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
