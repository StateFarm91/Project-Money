"""W4-PRODFIX2: improve.weekly dead-lettered in production (051dbee2, job 26949,
2026-10-26T14:09Z) with `TypeError: unhashable type: 'dict'`.

`evolution.stop_list` compared a query's last QUERY_UNCHANGED_CAPTURES SERP captures with
`set()` over `tuple(rank_list)`, and `rank_list` entries are dicts. It raised the first week a
query had that many captures. Captures now compare by canonical JSON.
"""
import _tmp; _tmp.install()  # per-process temp sandbox, removed at exit
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import Job, JobStatus, Phase, SerpSnapshot  # noqa: E402
from brambleloop.improve import evolution  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline  # noqa: E402,F401 - registers handlers
from brambleloop.runtime.worker import Worker  # noqa: E402

RANKS = [{"listing_id": 11, "rank": 1, "favourites": 3}, {"listing_id": 12, "rank": 2}]


def _db(captures):
    db = Database(f"sqlite:///{tempfile.mkdtemp(prefix='pf2-')}/w.db")
    db.create_all()
    Registry(db).seed_defaults()
    with db.session() as s:
        for query, ranks in captures:
            s.add(SerpSnapshot(query=query, rank_list=ranks, total_count=40))
    return db


def test_identical_captures_with_dict_entries_become_a_query_stop():
    n = evolution.QUERY_UNCHANGED_CAPTURES
    db = _db([("crochet blanket", list(RANKS))] * n
             + [("crochet hat", [{"listing_id": i, "rank": 1}]) for i in range(n)])
    stops = evolution.stop_list(db)["review"]["stop"]["stopped"]
    queries = [r["subject"] for r in stops if r["category"] == "query"]
    assert queries == ["crochet blanket"], stops


def test_the_weekly_cycle_completes_with_serp_captures_on_file():
    db = _db([("crochet blanket", list(RANKS))] * evolution.QUERY_UNCHANGED_CAPTURES)
    JobQueue(db).enqueue("orchestrator", "improve.weekly", {}, idempotency_key="w")
    Worker(db, "pf2", phase=Phase.SHADOW, job_types=["improve.weekly"]).run_once()
    with db.session() as s:
        job = s.query(Job).filter(Job.job_type == "improve.weekly").one()
        assert job.status == JobStatus.DONE, job.last_error


if __name__ == "__main__":
    for n, fn in list(globals().items()):
        if n.startswith("test_"):
            fn()
            print("OK  ", n)  # run_tests.sh counts lines beginning OK
