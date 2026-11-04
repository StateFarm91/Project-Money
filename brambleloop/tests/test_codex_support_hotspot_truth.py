"""A case count is not proof of independent buyers or release-specific defects."""
import json

from sqlalchemy import select

from brambleloop.agents.registry import Registry
from brambleloop.core.db import Database
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase, SupportCase
from brambleloop.queue.durable import JobQueue
from brambleloop.runtime import pipeline  # noqa: F401 -- register actual handlers
from brambleloop.runtime.worker import Worker
from brambleloop.support.workspace import _upstream_fixes


def test_support_worker_counts_distinct_buyers_per_release_without_leaking_refs(tmp_path):
    url = f"sqlite:///{tmp_path / 'support.db'}"
    db = Database(url, scratch=True)
    db.create_all()
    Registry(db).seed_defaults()

    def add(ref, version, rows):
        with db.session() as session:
            session.add(SupportCase(customer_ref=ref, product_slug="fixture-pattern",
                version=version, question="fixture question", answer="fixture draft",
                specialist="crochet_help", sent=False, resolved=False,
                detail={"cited_rows": rows}))

    def run(number):
        job = JobQueue(db).enqueue("support", "support.triage", {"slug": "fixture-pattern"},
                                   idempotency_key=f"fixture-triage-{number}")
        assert Worker(db, f"fixture-worker-{number}", phase=Phase.SHADOW,
                      job_types=["support.triage"]).run_once()
        with db.session() as session:
            result = session.get(Job, job.id)
            assert result.status == JobStatus.DONE, result.last_error
            return dict(result.outputs)

    add("buyer-a", "1.0.0", [6, 6, "bad"])
    add("buyer-a", "1.0.0", [6])
    add("buyer-a", "2.0.0", [6])
    add("unknown", "1.0.0", [6])
    assert not run(1)["row_hotspots"]
    add("buyer-b", "1.0.0", [6])
    add("buyer-c", "1.0.0", [6])
    result = run(2)
    assert result["row_hotspots"] == [{"product": "fixture-pattern", "version": "1.0.0",
                                       "row": 6, "mentions": 3}]
    reopened = Database(url, scratch=True)
    with reopened.session() as session:
        evidence = list(session.scalars(select(AuditLog).where(
            AuditLog.action == "support.defect_candidate")))
        assert len(evidence) == 1
        detail = evidence[0].detail
        assert detail["version"] == "1.0.0" and detail["mentions"] == 3
        assert all(ref not in json.dumps(detail) for ref in ("buyer-a", "buyer-b", "buyer-c"))
    add("buyer-b", "2.0.0", [6])
    add("buyer-c", "2.0.0", [6])
    run(3)
    assert {row["version"] for row in _upstream_fixes(reopened)
            if row["product"] == "fixture-pattern"} == {"1.0.0", "2.0.0"}
