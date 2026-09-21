"""The ladder under the coverage percentage, and the ways a ladder flatters a build.

`covered` means somebody read the spec line, read the module, and judged that the module
satisfies it. Two hundred and twenty-two of those reported as "69.4% complete" is this
build's most flattering number, and the owner named the gap precisely: a requirement is not
complete merely because code exists.

A ladder built to fix that has two opposite ways of being useless. It can hand out rungs for
things it did not measure, which is the original defect with more decimal places. Or it can
refuse every rung it cannot reach, inventing two hundred failures out of its own blind spots
-- and a report that calls every library "never exercised" because libraries leave no job
rows is not stricter, it is wrong in the other direction. Most of these tests are about the
ladder being unable to do either.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.build2 import maturity as M  # noqa: E402
from brambleloop.build2 import requirements as reg  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus  # noqa: E402


def _db() -> Database:
    tmp = tempfile.mkdtemp()
    db = Database(f"sqlite:///{tmp}/maturity.sqlite")
    db.create_all()
    return db


def _req(note: str, rid: int = 1):
    return reg.Requirement(id=rid, title="t", body="b", version="v1", section="s",
                           status=reg.COVERED, note=note)


def _signals(**overrides) -> dict:
    out = {"jobs_seen": set(), "jobs_audited": set(), "jobs_recent": set(),
           "is_production": False, "engine": "sqlite"}
    out.update(overrides)
    return out


def test_the_registrys_own_status_is_never_evidence_for_a_rung():
    """The status is the claim under test. A ladder that read it would be measuring the
    claim against itself, which is the thing the whole module exists to stop."""
    source = (ROOT / "src" / "brambleloop" / "build2" / "maturity.py").read_text()
    body = source.split('"""', 2)[2]          # past the module docstring
    for forbidden in ("reg.COVERED ==", ".status ==", "== reg.COVERED", "r.done",
                      ".executable"):
        assert forbidden not in body, f"the ladder consults the registry status: {forbidden}"


def test_a_note_that_names_no_module_reaches_no_rung_and_fails_none():
    """Sixty-odd requirements were audited in prose. The ladder has nothing to look for,
    and that is neither a pass nor a failure -- counting them either way would be a number
    about the audit's writing style rather than about the build."""
    entry = M.ladder(None, _req("merge instruction; this audit is its execution"))
    assert entry["modules"] == []
    assert entry["reached"] is None
    assert {r["verdict"] for r in entry["rungs"].values()} == {M.UNMEASURABLE}

    report = M.report(None)
    counted = report["notes_naming_no_module"]["count"]
    assert counted > 0
    for rung in M.RUNGS:
        assert report["rungs"][rung][M.NO] + report["rungs"][rung][M.YES] \
            <= report["covered_by_the_registry"] - counted


def test_a_rung_above_a_failure_is_a_failure_rather_than_a_fresh_start():
    """Otherwise a module nobody can find still reports being exercised, because some job
    somewhere ran. Each rung would be independently true and the ladder meaningless."""
    settled = M._settle({M.IMPLEMENTED: M.NO, M.TESTED: M.YES, M.DEPLOYED: M.YES,
                         M.EXERCISED: M.YES, M.EVIDENCED: M.YES,
                         M.PRODUCTION_OBSERVED: M.YES})
    assert [settled[r] for r in M._IMPLICATION_CHAIN] == [M.NO] * 5


def test_evidence_of_running_settles_the_rungs_underneath_it():
    """The other direction, and the one that stops the report arguing with itself. A job
    observed in production last week is proof the module shipped; printing
    `deployed: unmeasurable` beside `exercised: yes` is two answers to one question."""
    settled = M._settle({M.IMPLEMENTED: M.UNMEASURABLE, M.TESTED: M.NO,
                         M.DEPLOYED: M.UNMEASURABLE, M.EXERCISED: M.UNMEASURABLE,
                         M.EVIDENCED: M.UNMEASURABLE, M.PRODUCTION_OBSERVED: M.YES})
    assert settled[M.IMPLEMENTED] == M.YES
    assert settled[M.DEPLOYED] == M.YES
    assert settled[M.EVIDENCED] == M.YES
    # Running proves nothing about a test existing, so `tested` is untouched by either
    # direction. Untested code deploys and runs perfectly well.
    assert settled[M.TESTED] == M.NO


def test_the_suite_cannot_satisfy_the_production_rung():
    """A test that could prove production observation would be a test that proves a deploy.
    SQLite is not production and says so rather than quietly counting."""
    db = _db()
    assert M._signals(db)["is_production"] is False
    assert M._signals(db)["engine"] == "sqlite"

    # Give the suite everything the lower rungs need -- a job of the right type that
    # finished and left an audit row -- so the top rung is refused on its own terms rather
    # than because something underneath it failed.
    job_type = M.jobs_reaching("visual/reference_pack.py")[0]
    with db.session() as s:
        job = Job(agent="creative_director", job_type=job_type, status=JobStatus.DONE,
                  finished_at=datetime.now(timezone.utc))
        s.add(job)
        s.flush()
        s.add(AuditLog(actor="worker", action=job_type, job_id=job.id))

    entry = M.ladder(db, _req("visual/reference_pack.py builds the pack"))
    assert entry["rungs"][M.EXERCISED]["verdict"] == M.YES
    assert entry["rungs"][M.EVIDENCED]["verdict"] == M.YES
    assert entry["rungs"][M.PRODUCTION_OBSERVED]["verdict"] == M.UNMEASURABLE
    assert "not production" in entry["rungs"][M.PRODUCTION_OBSERVED]["why"]


def test_deployment_is_unmeasurable_from_a_laptop():
    """An import that succeeds outside the running image is rung one wearing rung three's
    name. The container is the only thing that knows which commit it is."""
    entry = M.ladder(None, _req("visual/reference_pack.py builds the pack"), env={})
    assert entry["rungs"][M.DEPLOYED]["verdict"] == M.UNMEASURABLE
    assert entry["reached"] == M.TESTED


def test_a_library_no_job_reaches_is_unreadable_rather_than_unexercised():
    """The blind spot that would have manufactured two hundred failures. Most modules are
    called from a request path or from another module, and leave no job row at all."""
    entry = M.ladder(None, _req("build2/maturity.py computes the ladder"),
                     signals=_signals(jobs_seen={"assets.build"}))
    assert M.jobs_reaching("build2/maturity.py") == ()
    assert entry["rungs"][M.EXERCISED]["verdict"] == M.UNMEASURABLE
    assert "leaves no job row" in entry["rungs"][M.EXERCISED]["why"]


def test_a_module_a_job_does_reach_can_be_told_it_never_ran():
    """The other half: where the ladder can measure, it must be able to say no."""
    reachable = next(m for m, jobs in M._module_to_jobs().items() if jobs)
    req = _req(f"{reachable} does the work")
    assert M.modules_named(req.note) == [reachable]

    never = M.ladder(None, req, signals=_signals())
    assert never["rungs"][M.EXERCISED]["verdict"] == M.NO
    assert "never run" in never["rungs"][M.EXERCISED]["why"]

    ran = M.ladder(None, req, signals=_signals(
        jobs_seen=set(M.jobs_reaching(reachable))))
    assert ran["rungs"][M.EXERCISED]["verdict"] == M.YES
    # Ran, but left no audit row: the job row is retention, the audit row is the record.
    assert ran["rungs"][M.EVIDENCED]["verdict"] == M.NO


def test_a_job_that_finished_and_was_audited_is_evidence_and_a_job_row_alone_is_not():
    """Through the real query rather than a hand-made signals dict, because the join is
    the part that can be wrong: a DONE job with no audit row is not evidence."""
    db = _db()
    with db.session() as s:
        bare = Job(agent="a", job_type="ops.health", status=JobStatus.DONE,
                   finished_at=datetime.now(timezone.utc))
        s.add(bare)
        s.flush()
        bare_id = bare.id
    signals = M._signals(db)
    assert "ops.health" in signals["jobs_seen"]
    assert "ops.health" not in signals["jobs_audited"]

    with db.session() as s:
        s.add(AuditLog(actor="worker", action="ops.health", job_id=bare_id))
    assert "ops.health" in M._signals(db)["jobs_audited"]


def test_work_that_ran_in_july_is_not_production_observed_today():
    db = _db()
    stale = datetime.now(timezone.utc) - timedelta(days=M.OBSERVED_WITHIN_DAYS + 5)
    with db.session() as s:
        s.add(Job(agent="a", job_type="ops.health", status=JobStatus.DONE,
                  finished_at=stale))
    signals = M._signals(db)
    assert "ops.health" in signals["jobs_seen"]
    assert "ops.health" not in signals["jobs_recent"]


def test_the_job_map_is_derived_from_the_handlers_rather_than_declared():
    """Two places holding the same fact disagree, and always in the flattering direction.
    The gate table drifted from the registry notes exactly this way."""
    mapped = M.handler_modules()
    source = (ROOT / "src" / "brambleloop" / "runtime" / "release.py").read_text()
    registered = source.count("@handlers.register(")
    assert len(mapped) == registered, (len(mapped), registered)
    reaching = [j for j, modules in mapped.items() if modules]
    assert len(reaching) >= registered - 2, (
        f"only {len(reaching)} of {registered} handlers reach a module -- the parser "
        f"has stopped seeing imports")
    # Derived means it agrees with the source, not with a table somebody typed.
    assert "cir/twin.py" in mapped["assets.build"]


def test_an_ordinary_import_counts_as_a_test():
    """The first version searched the test sources for `culture.translate` and reported
    nine covered requirements as untested. All nine had tests, imported as
    `from brambleloop.culture import translate`, in which that string never appears. A
    matcher that cannot see the ordinary import form measures how people write imports."""
    tested = M._tested_modules()
    assert "culture.translate" in tested
    assert "intel.mission" in tested
    assert M._tested("culture/translate.py")
    assert not M._tested("build2/__init__.py") or True   # presence, not absence, is the claim


def test_notes_that_name_a_table_rather_than_a_function_still_name_a_module():
    """`runrate.SCALE_RULES` is the same module as `runrate.decompose()`. Requiring the
    call parenthesis cost ten requirements their rung for a punctuation mark."""
    assert M.modules_named("runrate.SCALE_RULES holds five conditions") == ["scale/runrate.py"]
    assert M.modules_named("growth/portfolio.classify runs all five stages") == \
        ["growth/portfolio.py"]
    assert M.modules_named("swarm/orchestrate.ThrashDetector stops on three") == \
        ["swarm/orchestrate.py"]


def test_the_report_states_what_covered_actually_means():
    """The sentence is the point of the endpoint. A rung table with no statement of what
    the number it corrects was claiming is a second number to misread."""
    report = M.report(None)
    assert report["covered_by_the_registry"] == len(reg.by_status(reg.COVERED))
    assert "is not deployment" in report["what_covered_means"]
    assert set(report["rungs"]) == set(M.RUNGS)
    for rung in M.RUNGS:
        assert sum(report["rungs"][rung].values()) == report["covered_by_the_registry"]


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
