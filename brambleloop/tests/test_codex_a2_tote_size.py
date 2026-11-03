"""Tote sizing respects every named size, including direct builder calls."""
from brambleloop.creative import fallback_constructions as fallback
from brambleloop.runtime import pipeline


def test_tote_size_conflicts_are_refused_before_and_during_build():
    seed = pipeline._seed_for("nordic-forest-basket")
    geo = pipeline.concept_geometry(seed)
    def concept(title):
        return pipeline.Concept(slug="size-truth-tote", title=title, category="bag",
            stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]],
            width_stitches=10, rows=4, colors=geo["colors"])
    for title in ("Small Large Tote", "Small Big Tote", "Large Mini Tote",
                  "Small Tote (Large)", "Tote - Small - Large", "Ｓmall Ｌarge Tote",
                  "Jumbo Tote"):
        result = fallback.plan(category="bag", title=title)
        assert result["family"] == fallback.REFUSED, (title, result)
        try:
            fallback.tote(concept(title))
        except ValueError:
            pass
        else:
            raise AssertionError(f"direct builder accepted {title!r}")
    for title, size in (("Small Tote", "small"), ("Mini Small Tote", "small"),
                        ("Medium Tote", "medium"), ("Big Large Tote", "large"),
                        ("Market Tote", "large"), ("Small Market Tote", "small")):
        assert fallback.plan(category="bag", title=title)["family"] == fallback.TOTE, title
        assert fallback.tote_size_key(title) == (size, None), title
        assert fallback.tote(concept(title)).components, title


def test_worker_refuses_conflicting_title_on_persistent_database():
    import dataclasses
    import tempfile
    from brambleloop.agents.registry import Registry
    from brambleloop.core.db import Database
    from brambleloop.core.models import AuditLog, Job, PatternVersion, Product
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    from sqlalchemy import select

    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{directory}/tote.sqlite"
        db = Database(url, scratch=True)
        db.create_all()
        Registry(db).seed_defaults()
        seed = pipeline._seed_for("nordic-forest-basket")
        with db.session() as session:
            product = Product(slug=seed.slug, title=seed.title)
            session.add(product)
            session.flush()
            session.add(PatternVersion(product_id=product.id, version="0.9.0",
                                       cir_json={}, certified=True))
        payload = dataclasses.asdict(seed)
        payload.update(pipeline.concept_geometry(seed))
        payload.update(category="bag", title="Small Large Tote")
        JobQueue(db).enqueue("crochet_engineer", "cir.draft", payload,
                             idempotency_key="codex:tote:conflict")
        reopened = Database(url, scratch=True)
        assert Worker(reopened, "tote-conflict", job_types=["cir.draft"]).run_once()
        with reopened.session() as session:
            job = session.scalar(select(Job).where(Job.idempotency_key == "codex:tote:conflict"))
            assert job.outputs.get("drafted") is False, job.outputs
            assert job.outputs.get("gate") == "construction", job.outputs
            assert "conflicting" in str(job.outputs), job.outputs
            event = session.scalar(select(AuditLog).where(AuditLog.action == "cir.draft_refused"))
            assert event is not None and "conflicting" in str(event.detail), event
            assert session.scalar(select(Job).where(Job.job_type == "cir.compile")) is None


if __name__ == "__main__":
    test_tote_size_conflicts_are_refused_before_and_during_build()
    test_worker_refuses_conflicting_title_on_persistent_database()
    print("PASS conflicting and unsupported tote sizes fail closed")
