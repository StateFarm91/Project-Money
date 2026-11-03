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


def test_later_listing_cannot_add_contradictory_tote_sizes():
    import tempfile
    from brambleloop.core.db import Database
    from brambleloop.core.models import PatternVersion, Product
    from brambleloop.gates.certificate import GAUGE_STANDARD
    from brambleloop.publish import eligibility

    seed = pipeline._seed_for("nordic-forest-basket")
    geo = pipeline.concept_geometry(seed)
    concept = pipeline.Concept(slug="codex-size-listing", title="Small Tote", category="bag",
        stitch_repeat=[tuple(x) for x in geo["stitch_repeat"]], width_stitches=10,
        rows=4, colors=geo["colors"])
    cir = fallback.tote(concept)
    with tempfile.TemporaryDirectory() as directory:
        url = f"sqlite:///{directory}/listing.sqlite"
        db = Database(url, scratch=True)
        db.create_all()
        with db.session() as session:
            product = Product(slug=cir.slug, title=cir.title, status="certified")
            session.add(product)
            session.flush()
            session.add(PatternVersion(product_id=product.id, version=cir.version, certified=True,
                cir_json=cir.to_dict(), release_hash="a" * 64,
                certificate={"granted": True, "gauge_standard": GAUGE_STANDARD}))
        reopened = Database(url, scratch=True)
        for listing in ({"title": "Small Large Tote"},
                        {"title": "Tote", "description": "A Mini Large Tote"},
                        {"title": "Tote", "tags": ["Jumbo Tote"]},
                        {"title": "Large Tote"},
                        {"title": "Large Bag"},
                        {"title": "Small Tote", "description": "Size: large"},
                        {"title": "Small Tote", "tags": ["large size"]}):
            verdict = eligibility.product_publication(reopened, cir.slug, cir.version, listing=listing)
            assert not verdict["publishable"], verdict
            assert any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN and
                       "size: listing" in r["why"] for r in verdict["reasons"]), verdict
        for title in ("Large Purse", "Giant Pouch", "Big Backpack"):
            verdict = eligibility.product_publication(reopened, cir.slug, cir.version,
                                                       listing={"title": title})
            assert not verdict["publishable"], (title, verdict)
            assert any(r["code"] == eligibility.NAME_OUTRUNS_PATTERN and
                       "object: listing title" in r["why"] for r in verdict["reasons"]), verdict
        truthful = eligibility.product_publication(reopened, cir.slug, cir.version,
                                                    listing={"title": "Small Tote"})
        assert not any("size: listing" in r["why"] for r in truthful["reasons"]), truthful
        non_size = eligibility.product_publication(reopened, cir.slug, cir.version,
            listing={"title": "Small Tote", "description": "Holds large books"})
        assert not any("size: listing" in r["why"] for r in non_size["reasons"]), non_size


if __name__ == "__main__":
    test_tote_size_conflicts_are_refused_before_and_during_build()
    test_worker_refuses_conflicting_title_on_persistent_database()
    test_later_listing_cannot_add_contradictory_tote_sizes()
    print("PASS conflicting and unsupported tote sizes fail closed")
