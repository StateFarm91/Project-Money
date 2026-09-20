"""#171/#173: freshness is proved, and a sentinel that can actually stop a publication.

The requirement names its own failure -- a stable slug must never make stale output appear
current -- and the test that matters is the one about absence. An artefact nobody
fingerprinted has no mismatch to report, so a sweep that only compares recorded rows calls
the estate clean and leaves every un-instrumented file exactly as it found it.

Both of #173's named test conditions are here: deliberate stale-data injection, and a
restart, because a record that does not survive a container replacement is a record of
nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Incident, PatternVersion, Product  # noqa: E402
from brambleloop.ops import artefacts as P  # noqa: E402

DESIGN = {"slug": "hex-coaster", "rows": 12}
CHAIN = P.fingerprint("7")


def _db():
    db = Database("sqlite://")
    db.create_all()
    return db


def _current(design=None):
    return {"cir:hex-coaster": P.fingerprint(design or DESIGN), "chain:release": CHAIN}


def _record(db, *, artefact_class="pdf", key="hex-coaster.pdf", design=None):
    with db.session() as s:
        P.record(s, artefact_class=artefact_class, artefact_key=key,
                 product_slug="hex-coaster",
                 inputs={"cir:hex-coaster": P.fingerprint(design or DESIGN),
                         "chain:release": CHAIN})


# --- absence is not freshness -----------------------------------------------------------------

def test_an_artefact_with_no_provenance_is_unproven_rather_than_fresh():
    """It has no mismatch to report, so a sweep comparing only recorded rows would call it
    fresh -- which is the requirement's stable-slug failure exactly."""
    db = _db()
    with db.session() as s:
        verdicts = P.check(s, current=_current(),
                           expected=[("pdf", "hex-coaster.pdf", "hex-coaster")])
    assert [v.state for v in verdicts] == [P.UNPROVEN]
    assert "must never make stale output appear current" in verdicts[0].why


def test_an_absence_is_a_backlog_and_a_mismatch_is_a_defect():
    """The requirement blocks on *any mismatch*. An absence is not a mismatch: blocking on
    it the first time this sentinel runs would halt an entire catalogue over instrumentation
    nobody had fitted, which is a different problem and a worse cure."""
    db = _db()
    with db.session() as s:
        out = P.sweep(s, current=_current(),
                      expected=[("chart", "hex-coaster.svg", "hex-coaster")])
    assert out["unproven"] == 1
    assert out["publication_blocked"] == []           # counted, not blocking
    assert out["instrument"] == [("chart", "hex-coaster.svg")]
    assert out["incidents_raised"][0]["blocking"] is False


def test_the_backlog_can_be_enforced_once_it_is_closed():
    db = _db()
    with db.session() as s:
        out = P.sweep(s, current=_current(),
                      expected=[("chart", "hex-coaster.svg", "hex-coaster")],
                      block_unproven=True)
    assert out["publication_blocked"] == ["hex-coaster"]


def test_graduation_is_a_count_rather_than_a_judgement():
    db = _db()
    expected = [("pdf", "hex-coaster.pdf", "hex-coaster")]
    with db.session() as s:
        before = P.graduation(s, current=_current(), expected=expected)
    assert before["may_enforce_unproven"] is False
    assert "never fitted" in before["why"]

    _record(db)
    with db.session() as s:
        after = P.graduation(s, current=_current(), expected=expected)
    assert after["may_enforce_unproven"] is True


def test_an_upstream_with_no_current_fingerprint_cannot_prove_freshness():
    db = _db()
    _record(db)
    with db.session() as s:
        verdicts = P.check(s, current={"chain:release": CHAIN})   # the design is unreadable
    assert verdicts[0].state == P.STALE
    assert verdicts[0].unknown == ("cir:hex-coaster",)
    assert "an unprovable artefact is not a fresh one" in verdicts[0].why


# --- deliberate stale-data injection ------------------------------------------------------------

def test_moving_an_upstream_under_a_fresh_artefact_turns_it_stale():
    """#173's own test condition. The artefact is untouched; only its evidence moved."""
    db = _db()
    _record(db)
    with db.session() as s:
        assert P.check(s, current=_current())[0].state == P.FRESH

    rebuilt = dict(DESIGN, rows=14)
    with db.session() as s:
        out = P.sweep(s, current=_current(rebuilt))
    assert out["stale"] == 1
    assert out["verdicts"][0]["moved"] == ["cir:hex-coaster"]
    assert out["rebuild"] == ["hex-coaster"]


def test_the_sentinel_incident_actually_stops_certification():
    """Asserted through the publish path rather than by reading the row it wrote. A block
    that is only a row is a claim about a block."""
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    _record(db)
    with db.session() as s:
        P.sweep(s, current=_current(dict(DESIGN, rows=14)))

    assert IncidentTracker(db).publication_halted("hex-coaster") is True


def test_a_sentinel_that_can_only_add_incidents_stops_the_company():
    """So a rebuilt artefact clears its own block on the next sweep."""
    from brambleloop.gates.incidents import IncidentTracker

    db = _db()
    _record(db)
    moved = dict(DESIGN, rows=14)
    with db.session() as s:
        P.sweep(s, current=_current(moved))
    assert IncidentTracker(db).publication_halted("hex-coaster") is True

    _record(db, design=moved)                    # the artefact is rebuilt against the new design
    with db.session() as s:
        out = P.sweep(s, current=_current(moved))
    assert out["fresh"] == 1 and out["stale"] == 0
    assert out["incidents_cleared"]
    assert IncidentTracker(db).publication_halted("hex-coaster") is False


def test_the_backlog_is_one_incident_carrying_its_size():
    """An alarm that arrives in hundreds is an alarm nobody reads, which is the same as no
    alarm and costs more. The first sweep of an un-instrumented estate would otherwise raise
    one row per artefact."""
    from sqlalchemy import func, select

    db = _db()
    expected = [("pdf", f"p{i}.pdf", "hex-coaster") for i in range(40)]
    with db.session() as s:
        out = P.sweep(s, current=_current(), expected=expected)
    assert out["unproven"] == 40
    with db.session() as s:
        rows = list(s.scalars(select(Incident)))
    assert len(rows) == 1
    assert rows[0].severity == "P3" and rows[0].halts_publication is False
    assert rows[0].detail["unproven"] == 40
    assert "instrumentation backlog rather than a defect" in rows[0].summary
    with db.session() as s:
        assert s.scalar(select(func.count(Incident.id))) == 1


def test_the_backlog_incident_closes_when_the_backlog_does():
    from sqlalchemy import select

    db = _db()
    expected = [("pdf", "hex-coaster.pdf", "hex-coaster")]
    with db.session() as s:
        P.sweep(s, current=_current(), expected=expected)
    _record(db)
    with db.session() as s:
        out = P.sweep(s, current=_current(), expected=expected)
        rows = [r for r in s.scalars(select(Incident)) if not r.resolved]
    assert out["unproven"] == 0
    assert rows == []


def test_a_mismatch_still_gets_its_own_row_because_each_is_a_defect():
    from sqlalchemy import select

    db = _db()
    _record(db, artefact_class="pdf", key="a.pdf")
    _record(db, artefact_class="chart", key="b.svg")
    with db.session() as s:
        P.sweep(s, current=_current(dict(DESIGN, rows=99)))
        rows = sorted(r.signature for r in s.scalars(select(Incident)))
    assert rows == [f"{P.SENTINEL_SIGNATURE}:chart:b.svg",
                    f"{P.SENTINEL_SIGNATURE}:pdf:a.pdf"]


def test_a_sweep_does_not_raise_the_same_incident_twice():
    db = _db()
    _record(db)
    moved = _current(dict(DESIGN, rows=14))
    with db.session() as s:
        first = P.sweep(s, current=moved)
        second = P.sweep(s, current=moved)
    assert len(first["incidents_raised"]) == 1
    assert second["incidents_raised"] == []
    with db.session() as s:
        from sqlalchemy import func, select
        assert s.scalar(select(func.count(Incident.id))) == 1


# --- a restart --------------------------------------------------------------------------------

def test_provenance_survives_a_restart():
    """A record that does not survive a container replacement is a record of nothing."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/p.sqlite"
        first = Database(url)
        first.create_all()
        with first.session() as s:
            P.record(s, artefact_class="certificate", artefact_key="hex-coaster@1.0.0",
                     product_slug="hex-coaster",
                     inputs={"cir:hex-coaster": P.fingerprint(DESIGN)})
        del first

        after = Database(url)          # a fresh process would do exactly this
        with after.session() as s:
            verdicts = P.check(s, current={"cir:hex-coaster": P.fingerprint(DESIGN)})
        assert [v.state for v in verdicts] == [P.FRESH]
        with after.session() as s:
            out = P.sweep(s, current={"cir:hex-coaster": P.fingerprint({"moved": True})})
        assert out["stale"] == 1


# --- what may be recorded ------------------------------------------------------------------------

def test_a_derived_artefact_with_no_inputs_is_a_file():
    db = _db()
    with db.session() as s:
        try:
            P.record(s, artefact_class="pdf", artefact_key="x.pdf", product_slug="x",
                     inputs={})
        except P.ProvenanceRefused as exc:
            assert "permanently fresh" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("an artefact with no upstream was recorded")


def test_a_version_string_is_not_a_fingerprint():
    """A version string compares equal to itself forever, which is exactly how a rebuilt
    design keeps its old artefacts."""
    db = _db()
    with db.session() as s:
        try:
            P.record(s, artefact_class="pdf", artefact_key="x.pdf", product_slug="x",
                     inputs={"cir:x": "1.0.0"})
        except P.ProvenanceRefused as exc:
            assert "compares equal to itself forever" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("a version string was accepted as evidence")


def test_an_upstream_kind_nobody_named_is_refused():
    db = _db()
    with db.session() as s:
        try:
            P.record(s, artefact_class="pdf", artefact_key="x.pdf", product_slug="x",
                     inputs={"vibes:x": P.fingerprint(1)})
        except P.ProvenanceRefused as exc:
            assert "nobody watches" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("an unwatched upstream joined the graph")


def test_a_bare_name_is_not_an_upstream_reference():
    db = _db()
    with db.session() as s:
        try:
            P.record(s, artefact_class="pdf", artefact_key="x.pdf", product_slug="x",
                     inputs={"hex-coaster": P.fingerprint(1)})
        except P.ProvenanceRefused as exc:
            assert "cannot be looked up" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("a bare name was accepted as a reference")


def test_every_artefact_class_the_requirement_names_is_watched():
    for named in ("twin", "geometry_proof", "reverse_result", "certificate", "pdf", "chart",
                  "visual_truth", "listing_copy", "seo", "pricing", "support_knowledge",
                  "marketing_asset", "release_bundle"):
        assert named in P.ARTEFACT_CLASSES, named


def test_recording_the_same_artefact_twice_updates_rather_than_duplicates():
    db = _db()
    _record(db)
    _record(db, design=dict(DESIGN, rows=14))
    with db.session() as s:
        verdicts = P.check(s, current=_current(dict(DESIGN, rows=14)))
    assert len(verdicts) == 1 and verdicts[0].state == P.FRESH


def test_current_fingerprints_come_from_the_records_that_hold_them():
    db = _db()
    with db.session() as s:
        s.add(Product(slug="hex-coaster", title="Hex Coaster"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json=DESIGN,
                             release_hash="a" * 64, certified=True))
    with db.session() as s:
        current = P.current_from_db(s)
    assert current["cir:hex-coaster"] == P.fingerprint(DESIGN)
    assert current["release:hex-coaster"] == "a" * 16
    assert "chain:release" in current


def test_the_sentinel_cadence_runs_against_artefacts_that_actually_exist():
    """A sweep of the instrumented estate is not a sweep of the estate, so the handler is
    exercised with real downstream rows rather than an empty database -- the empty case is
    where a handler's interesting half goes untested with a passing test beside it."""
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import Listing
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401  -- registers handlers
    from brambleloop.runtime.release import handle_stale_artefact_sentinel
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(Product(slug="hex-coaster", title="Hex Coaster"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json=DESIGN,
                             release_hash="b" * 64, certified=True))
        s.add(Listing(product_slug="hex-coaster", version="1.0.0", title="t",
                      description="", tags=[], price_cad=6.0))

    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.sentinel", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    out = handle_stale_artefact_sentinel(ctx)

    # A certificate, listing copy and SEO exist and none of them carries provenance.
    assert out["checked"] == 3
    assert out["unproven"] == 3
    assert out["stale"] == 0
    assert out["publication_blocked"] == []          # an absence is a backlog
    assert out["may_enforce_unproven"] is False


def test_a_stale_artefact_asks_for_its_own_rebuild():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime import pipeline  # noqa: F401
    from brambleloop.runtime.release import handle_stale_artefact_sentinel
    from brambleloop.runtime.worker import JobContext

    db = _db()
    Registry(db).seed_defaults()
    with db.session() as s:
        s.add(Product(slug="hex-coaster", title="Hex Coaster"))
        s.flush()
        s.add(PatternVersion(product_id=1, version="1.0.0", cir_json=DESIGN,
                             release_hash="b" * 64, certified=True))
        P.record(s, artefact_class="certificate", artefact_key="hex-coaster@1.0.0",
                 product_slug="hex-coaster",
                 inputs={"cir:hex-coaster": P.fingerprint({"moved": "long ago"})})

    queue = JobQueue(db)
    ctx = JobContext(job=queue.enqueue("orchestrator", "ops.sentinel", {}), db=db,
                     queue=queue, registry=Registry(db), phase=None)
    out = handle_stale_artefact_sentinel(ctx)

    assert out["stale"] == 1
    assert out["publication_blocked"] == ["hex-coaster"]
    assert out["rebuild"] == ["hex-coaster"]
    with db.session() as s:
        from sqlalchemy import select

        from brambleloop.core.models import Job
        kinds = [j.job_type for j in s.scalars(select(Job))]
    assert "chain.rebuild" in kinds


def test_state_says_what_absence_means():
    out = P.state()
    assert out["states"] == [P.FRESH, P.STALE, P.UNPROVEN]
    assert "unproven, not fresh" in out["note"]


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
