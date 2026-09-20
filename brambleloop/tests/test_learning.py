"""External observations, and the one sentence in which a signal becomes something we know.

v1.4.3 requirement 98. The radar itself is unremarkable. The requirement's real instruction
is the second clause -- every observation is separated from verified internal causal evidence
-- and that separation is lost in a single sentence and never recovered afterwards.

So most of these tests are about the boundary: an observation that cannot say where it came
from, a domain nobody has looked at being reported as unlooked-at rather than as zero, and
the promotion of a signal into evidence refusing by name.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.intel import learning as L  # noqa: E402

TODAY = date(2026, 9, 19)


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/learning.sqlite")
    db.create_all()
    return db


def _record(db, domain="techniques", days_ago=10, **over) -> int:
    kwargs = dict(domain=domain, source="a named craft publication",
                  citation="https://example.invalid/article-42",
                  summary="a revived overlay technique is appearing across beginner patterns",
                  observed_on=TODAY - timedelta(days=days_ago))
    kwargs.update(over)
    return L.record(db, **kwargs)


def test_an_observation_with_no_source_is_refused():
    db = _db()
    try:
        _record(db, source="   ")
    except L.LearningRefused as e:
        assert "is a belief" in str(e)
    else:
        raise AssertionError("an observation with no source was stored")


def test_an_observation_with_no_citation_is_refused():
    """The summary is already an interpretation, so a reader has to be able to go back."""
    db = _db()
    try:
        _record(db, citation="")
    except L.LearningRefused as e:
        assert "go back to the thing itself" in str(e)
    else:
        raise AssertionError("an observation was stored with nothing to go back to")


def test_an_unclassified_domain_is_refused_rather_than_given_a_default():
    db = _db()
    try:
        _record(db, domain="vibes")
    except L.LearningRefused as e:
        assert "whatever freshness the reader assumes" in str(e)
    else:
        raise AssertionError("an observation was filed under an invented domain")


def test_freshness_is_per_domain_because_a_policy_ages_faster_than_a_stitch():
    db = _db()
    _record(db, domain="techniques", days_ago=200)
    _record(db, domain="marketplace_policy", days_ago=200,
            summary="the seller policy page added a section on digital delivery")

    rows = {r["domain"]: r for r in L.observations(db, today=TODAY)}

    assert rows["techniques"]["fresh"] is True
    assert rows["marketplace_policy"]["fresh"] is False
    assert (L.DOMAIN_BY_KEY["marketplace_policy"].fresh_for_days
            < L.DOMAIN_BY_KEY["techniques"].fresh_for_days)


def test_a_domain_nobody_looked_at_is_named_not_counted_as_zero():
    """Zero signal and no look are the same number and opposite situations."""
    db = _db()
    _record(db, domain="techniques")

    report = L.radar(db, today=TODAY)

    unobserved = {u["domain"] for u in report["unobserved"]}
    assert "competitor_positioning" in unobserved
    assert all(u["why_it_matters"] for u in report["unobserved"])
    assert "a different thing from quiet" in report["note"]


def test_an_empty_radar_says_it_is_a_shape_with_nothing_in_it():
    report = L.radar(_db(), today=TODAY)
    assert report["observations"] == 0
    assert len(report["unobserved"]) == len(L.DOMAINS)
    assert "nothing in it" in report["note"]


def test_a_stale_domain_is_separated_from_a_watched_one():
    db = _db()
    _record(db, domain="techniques", days_ago=5)
    _record(db, domain="search_behaviour", days_ago=400,
            summary="ranking appeared to favour listings with recent sales velocity")

    report = L.radar(db, today=TODAY)

    assert [w["domain"] for w in report["watched"]] == ["techniques"]
    assert [s["domain"] for s in report["stale"]] == ["search_behaviour"]


# ---- the boundary ---------------------------------------------------------


def test_an_observation_cannot_be_promoted_into_evidence():
    db = _db()
    _record(db)
    observation = L.observations(db, today=TODAY)[0]

    try:
        L.as_evidence(observation)
    except L.LearningRefused as e:
        assert "signal, not causal evidence" in str(e)
    else:
        raise AssertionError("an external observation became evidence")


def test_a_signal_passed_as_internal_evidence_is_refused():
    """The single sentence in which a signal becomes something the company knows."""
    db = _db()
    _record(db)
    observation = L.observations(db, today=TODAY)[0]

    try:
        L.support("textured stitches sell better", signals=[], evidence=[observation])
    except L.LearningRefused as e:
        assert "two lists" in str(e)
    else:
        raise AssertionError("an observation was accepted as internal causal evidence")


def test_a_claim_resting_on_signals_alone_is_allowed_and_says_so():
    db = _db()
    _record(db)
    observation = L.observations(db, today=TODAY)[0]

    result = L.support("try an overlay texture in the next field",
                       signals=[observation], evidence=[])

    assert result["rests_on_signals_alone"] is True
    assert result["causal_basis"] == "none"
    assert "not a thing this company has established" in result["note"]


def test_internal_evidence_gives_a_claim_a_causal_basis():
    result = L.support("the chart check catches stitch-count defects",
                       signals=[],
                       evidence=[{"kind": "internal_lesson", "id": 1,
                                  "statement": "measured here over 40 compilations"}])

    assert result["causal_basis"] == "internal_evidence"
    assert result["rests_on_signals_alone"] is False


def _run() -> int:
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
    return failures


# ---- feeding the radar from evidence this company has (#98) ------------------


def _benchmark_db(n=20):
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/feed.sqlite")
    db.create_all()
    with db.session() as s:
        for i in range(n):
            s.add(BenchmarkListing(benchmark_key=benchmarks.MJS_KEY, listing_ref=str(i),
                                   title="Cozy Crochet Christmas Stocking Pattern",
                                   pod="stockings" if i < 12 else "bags",
                                   media_count=3 if i < 17 else 7))
    return db


def test_only_the_domains_a_catalogue_can_answer_are_fed():
    """Filling all eight by inference turns a truthful "nobody has looked" into fiction,
    which is the one thing this radar exists to prevent."""
    from brambleloop.intel import learning

    report = learning.ingest_benchmark(_benchmark_db(), today=date(2026, 9, 20))
    assert set(report["recorded"]) == set(learning.FEEDABLE)
    assert set(report["skipped"]) == set(learning.NOT_FEEDABLE)
    assert not set(learning.FEEDABLE) & set(learning.NOT_FEEDABLE)


def test_a_technique_is_never_inferred_from_a_product_title():
    """A title naming "mosaic" says a product exists, not that the technique is reviving."""
    from brambleloop.intel import learning

    report = learning.ingest_benchmark(_benchmark_db(), today=date(2026, 9, 20))
    assert "techniques" not in report["recorded"]
    assert "source about the craft" in report["skipped"]["techniques"]


def test_marketplace_policy_keeps_one_writer():
    """Two writers would let two freshness clocks disagree about one policy."""
    from brambleloop.intel import learning

    assert "marketplace_policy" not in learning.FEEDABLE
    assert "ops.policy_watch" in learning.NOT_FEEDABLE["marketplace_policy"]


def test_ingesting_twice_in_a_day_records_nothing_the_second_time():
    """A radar accumulating a row per invocation reports freshness as a function of how
    often the scheduler fired."""
    from brambleloop.intel import learning

    db = _benchmark_db()
    assert learning.ingest_benchmark(db, today=date(2026, 9, 20))["recorded"]
    assert learning.ingest_benchmark(db, today=date(2026, 9, 20))["recorded"] == []
    assert learning.ingest_benchmark(db, today=date(2026, 9, 21))["recorded"]


def test_with_no_observed_catalogue_nothing_is_recorded():
    import tempfile

    from brambleloop.core.db import Database
    from brambleloop.intel import learning

    db = Database(f"sqlite:///{tempfile.mkdtemp()}/empty.sqlite")
    db.create_all()
    report = learning.ingest_benchmark(db, today=date(2026, 9, 20))
    assert report["recorded"] == []
    assert "nothing to report" in report["reason"]


def test_the_radar_still_names_the_four_nobody_has_looked_at():
    """Half-fed is the honest state, and a radar that hid it would be worse than empty."""
    from brambleloop.intel import learning

    db = _benchmark_db()
    learning.ingest_benchmark(db, today=date(2026, 9, 20))
    report = learning.radar(db, today=date(2026, 9, 20))
    assert len(report["watched"]) == 4
    assert {d["domain"] for d in report["unobserved"]} == set(learning.NOT_FEEDABLE)


def test_a_fed_observation_still_cannot_become_evidence():
    """The load-bearing clause: a signal is not evidence however it was recorded."""
    from brambleloop.intel import learning

    db = _benchmark_db()
    learning.ingest_benchmark(db, today=date(2026, 9, 20))
    observation = learning.observations(db, domain="competitor_positioning")[0]
    try:
        learning.as_evidence(observation)
    except learning.LearningRefused:
        pass
    else:
        raise AssertionError("an external signal was promoted into evidence")


if __name__ == "__main__":
    raise SystemExit(1 if _run() else 0)
