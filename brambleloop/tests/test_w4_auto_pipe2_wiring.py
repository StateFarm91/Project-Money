"""W4-AUTO: wiring request from W4-PIPE2.

1. The six moment-first candidates are in `runtime.pipeline.ENGINEERED`, so a candidate that
   clears the taste gate builds its engineered CIR through `cir.draft`, never a prototype.
2. A daily cadence (`creative.candidates_file`) files every engineered creative candidate's
   concept board and registers it with the taste gate in the live database, idempotently, so
   production's `creative.intake.regate_held` sees them.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from brambleloop.agents.registry import DEFAULT_AGENTS, Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.creative import intake  # noqa: E402
from brambleloop.products import moment_candidates as mc  # noqa: E402
from brambleloop.products.pipeline_board import CREATIVE_ENGINEERED  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402
from brambleloop.runtime.worker import CADENCES, Worker  # noqa: E402
from brambleloop.swarm import orchestrate  # noqa: E402

JT = "creative.candidates_file"


def boot() -> Database:
    tmp = tempfile.mkdtemp(prefix="w4auto-pipe2-")
    db = Database(f"sqlite:///{tmp}/t.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    return db


def test_the_six_candidates_build_their_engineered_cir():
    six = sorted(mc.ENGINEERED)
    assert len(six) == 6, six
    for slug in six:
        assert slug in pipeline.ENGINEERED, f"{slug} would be drafted as a prototype"
        cir = pipeline._engineered_cir(slug)
        assert cir is not None and cir.slug == slug, slug
        built = mc.ENGINEERED[slug]()
        assert cir.fingerprint == CIR_fp(built, slug), slug
    print("OK test_the_six_candidates_build_their_engineered_cir")


def CIR_fp(cir, slug):
    from brambleloop.cir.model import CIR
    return CIR.from_dict({**cir.to_dict(), "slug": slug}).fingerprint


def test_the_filing_job_is_scheduled_allowed_banded_and_judged():
    sched = [c for c in CADENCES if c[2] == JT]
    assert len(sched) == 1 and sched[0][1] == "creative_director", sched
    agent = next(a for a in DEFAULT_AGENTS if a["name"] == "creative_director")
    assert JT in agent["allowed_job_types"]
    assert orchestrate.band_for(JT)["mapped"]
    assert pipeline.WORK_KEYS[JT] == ("boards_filed", "registered")
    print("OK test_the_filing_job_is_scheduled_allowed_banded_and_judged")


def _run(db) -> dict:
    job = JobQueue(db).enqueue("creative_director", JT, {"cadence": "test"})
    w = Worker(db, "w")
    assert w.run_once()
    with db.session() as s:
        from brambleloop.core.models import Job
        row = s.get(Job, job.id)
        assert getattr(row.status, "value", row.status) == "done", row.last_error
        return dict(row.outputs or {})


def test_filing_job_files_boards_and_registers_then_is_idempotent():
    db = boot()
    slugs = sorted(CREATIVE_ENGINEERED)
    assert len(slugs) >= 8, slugs
    first = _run(db)
    assert first["candidates"] == len(slugs), first
    assert not first["errors"], first["errors"]
    assert sorted(first["boards_filed"]) == slugs, first
    reg = {r["slug"] for r in first["registered"]}
    assert reg == set(slugs), first
    for slug in slugs:
        assert mc.board_record(db, slug) is not None, slug
        assert intake.intake_rows(db, slug=slug, limit=1), slug
        assert intake.board_for(db, slug), f"regate cannot find {slug}'s board"
    assert not pipeline.did_no_work(first, JT)
    second = _run(db)
    assert second["boards_filed"] == [] and second["registered"] == [], second
    assert sorted(second["unchanged"]) == slugs, second
    assert pipeline.did_no_work(second, JT), "a repeat with nothing new is a no-op"
    print("OK test_filing_job_files_boards_and_registers_then_is_idempotent")


TESTS = [
    test_the_six_candidates_build_their_engineered_cir,
    test_the_filing_job_is_scheduled_allowed_banded_and_judged,
    test_filing_job_files_boards_and_registers_then_is_idempotent,
]

if __name__ == "__main__":
    assert TESTS
    failed = 0
    for t in TESTS:
        try:
            t()
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.exit(1 if failed else 0)
