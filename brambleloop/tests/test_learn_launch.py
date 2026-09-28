"""Hermetic adversarial checks for the launch Learn contract."""
import copy
import tempfile
from pathlib import Path
from sqlalchemy import select
from brambleloop.core.db import Database
from brambleloop.core.models import Product, PatternVersion, SupportCase
from brambleloop.learn.models import LearnGap, LearnEdge, Lesson
from brambleloop.learn.service import (scan, save_lesson, review_lesson, help_links,
                                      approved_lesson, DIMENSIONS)


def database(path):
    db = Database("sqlite:///" + str(path), scratch=True)
    db.create_all()
    return db


def spec():
    return {"author": "pattern-engineering", "learner_problem": "work a single crochet",
            "topics": ["stitch:sc"], "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": [{"rights": "brambleloop_original", "source": "canonical-demo",
                        "sha256": "a"*64}],
            "steps": [{"stitch": "sc", "repeat": 2, "consumes": 2, "produces": 2,
                       "term": "sc", "instruction": "Work one single crochet in each of next two stitches."}]}


def approve(db, revision):
    review_lesson(db, "single-crochet", revision, "independent-qa",
                  dict.fromkeys(DIMENSIONS, "PASS"), "fixture-review:test-only")


def seed(db):
    with db.session() as s:
        p = Product(slug="original", title="Original")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={
            "construction": "flat_rows", "rows": [{"stitch": "sc", "count": 2}]}))


def test_source_graph_queue_restart_and_idempotence():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)/"learn.db"
        db = database(path)
        seed(db)
        result = scan(db)
        assert result["decision"] == "QUEUE" and result["queued"] == 2
        db.engine.dispose()
        db = database(path)
        assert scan(db) == result
        with db.session() as s:
            assert len(s.scalars(select(LearnEdge)).all()) == 2
            assert len(s.get(LearnGap, "stitch:sc").evidence) == 1
        db.engine.dispose()


def test_no_sources_watch_not_filler():
    db = database(":memory:")
    assert scan(db) == {"decision": "WATCH", "queued": 0, "sources": 0, "generated": 0, "published": 0}


def test_invalid_count_and_licence_refused():
    db = database(":memory:")
    for mutate in (lambda v: v["steps"][0].update(produces=3),
                   lambda v: v["assets"][0].update(rights="competitor"),
                   lambda v: v["assets"][0].update(rights="licensed")):
        value = spec()
        mutate(value)
        try:
            save_lesson(db, "single-crochet", value)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid canonical specification accepted")


def test_unknown_visual_review_withholds_and_self_review_refused():
    db = database(":memory:")
    rev = save_lesson(db, "single-crochet", spec())
    verdicts = dict.fromkeys(DIMENSIONS, "PASS")
    verdicts["visual_accuracy"] = "UNKNOWN"
    review_lesson(db, "single-crochet", rev, "independent", verdicts, "test-only")
    assert not help_links(db, ["stitch:sc"])
    try:
        review_lesson(db, "single-crochet", rev, "pattern-engineering", verdicts, "test-only")
    except ValueError:
        pass
    else:
        raise AssertionError("self review accepted")


def test_revision_change_revokes_help_and_reopens_gap():
    db = database(":memory:")
    seed(db)
    scan(db)
    rev = save_lesson(db, "single-crochet", spec())
    approve(db, rev)
    assert help_links(db, ["stitch:sc"])[0]["href"] == "/learn/single-crochet?revision=" + rev
    scan(db)
    with db.session() as s:
        assert s.get(LearnGap, "stitch:sc").state == "COVERED"
    changed = spec()
    changed["learner_problem"] = "changed teaching objective"
    save_lesson(db, "single-crochet", changed)
    assert approved_lesson(db, "single-crochet") is None
    scan(db)
    with db.session() as s:
        assert s.get(LearnGap, "stitch:sc").state == "QUEUED"
    try:
        approve(db, rev)
    except ValueError:
        pass
    else:
        raise AssertionError("stale review accepted")


def test_direct_spec_tamper_cannot_retain_approval():
    db = database(":memory:")
    approve(db, save_lesson(db, "single-crochet", spec()))
    with db.session() as s:
        row = s.get(Lesson, "single-crochet")
        value = copy.deepcopy(row.spec)
        value["steps"][0]["instruction"] = "altered"
        row.spec = value
    assert not help_links(db, ["stitch:sc"])


def test_support_sources_do_not_copy_customer_pii():
    db = database(":memory:")
    with db.session() as s:
        s.add(SupportCase(customer_ref="secret-customer", question="private prose", specialist="gauge"))
    scan(db)
    with db.session() as s:
        gap = s.get(LearnGap, "support:gauge")
        assert gap and "private" not in str(gap.evidence) and "secret" not in str(gap.evidence)


def test_untrusted_slug_cannot_create_external_help_link():
    db = database(":memory:")
    try:
        save_lesson(db, "https://example.org", spec())
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe slug accepted")


def test_real_worker_scanner_reads_production_pattern_state():
    from brambleloop.agents.registry import Registry
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker, CADENCES
    from brambleloop.learn import runtime
    db = database(":memory:")
    Registry(db).seed_defaults()
    seed(db)
    assert ("learn_gap_scan", "learn", "learn.scan", 3600) in CADENCES
    JobQueue(db).enqueue("learn", "learn.scan", {})
    worker = Worker(db, job_types=["learn.scan"])
    assert worker.run_once() and worker.stats.completed == 1
    with db.session() as s:
        assert s.get(LearnGap, "stitch:sc").state == "QUEUED"


def test_public_route_refuses_draft_and_stale_revision():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    with tempfile.TemporaryDirectory() as td:
        db = database(Path(td)/"api.db")
        app = FastAPI()
        app.include_router(router(db))
        client = TestClient(app)
        rev = save_lesson(db, "single-crochet", spec())
        assert client.get("/learn/single-crochet").status_code == 404
        approve(db, rev)
        assert client.get("/learn/single-crochet?revision="+rev).status_code == 200
        assert client.get("/learn/single-crochet?revision=stale").status_code == 404
        assert "assets" not in client.get("/learn/single-crochet").json()
        db.engine.dispose()


def test_pdf_links_require_configured_origin_and_approved_revision():
    import os
    from unittest.mock import patch
    from brambleloop.learn.service import pdf_help_links
    db = database(":memory:")
    rev = save_lesson(db, "single-crochet", spec())
    cir = {"stitch": "sc"}
    with patch.dict(os.environ, {"BRAMBLELOOP_LEARN_PUBLIC_ORIGIN": ""}):
        assert pdf_help_links(db, cir) == []
    with patch.dict(os.environ, {"BRAMBLELOOP_LEARN_PUBLIC_ORIGIN": "https://learn.example.test"}):
        assert pdf_help_links(db, cir) == []
        approve(db, rev)
        assert pdf_help_links(db, cir)[0]["url"].endswith("?revision="+rev)
    with patch.dict(os.environ, {"BRAMBLELOOP_LEARN_PUBLIC_ORIGIN": "javascript:alert(1)"}):
        try:
            pdf_help_links(db, cir)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe origin accepted")


def test_actual_pdf_render_threads_revision_bound_help_to_layout():
    from brambleloop.cir.model import CIR, Component, Row, Op, Gauge, Material
    from brambleloop.publish.pdf import build_pattern_pdf
    cir = CIR(slug="learn-cloth", title="Learn Cloth", version="1", construction="flat_rows",
              gauge=Gauge(stitches_per_10cm=14, rows_per_10cm=16, stitch_type="sc", hook_mm=4),
              colors={"A": "#ffffff"}, materials=[Material(name="cotton", yarn_weight="worsted", colorway="white", color_id="A")],
              components=[Component(name="cloth", construction="flat_rows", foundation=4,
                 rows=[Row(index=i,ops=[Op("sc",4)], declared_count=4, color="A", turning_chain=1) for i in range(1,5)])])
    assert "Technique help" not in build_pattern_pdf(cir).prose
    rev = "a"*64
    url = "https://learn.example.test/learn/single-crochet?revision="+rev
    doc = build_pattern_pdf(cir, lesson_links=[{"url": url, "topics": ["stitch:sc"], "revision": rev}])
    assert url in doc.prose and "Technique help" in doc.prose


def test_authenticated_draft_review_serving_has_distinct_identities():
    import os
    from unittest.mock import patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    config = {"BRAMBLELOOP_OPS_TOKEN": "editor-test-credential-0000000000",
              "BRAMBLELOOP_LEARN_REVIEW_TOKEN": "reviewer-test-credential-0000000",
              "BRAMBLELOOP_LEARN_REVIEWER_ID": "independent-reviewer"}
    with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, config):
        db = database(Path(td)/"workflow.db")
        seed(db)
        scan(db)
        app = FastAPI()
        app.include_router(router(db))
        client = TestClient(app)
        editor = {"Authorization": "Bearer "+config["BRAMBLELOOP_OPS_TOKEN"]}
        reviewer = {"Authorization": "Bearer "+config["BRAMBLELOOP_LEARN_REVIEW_TOKEN"]}
        assert client.get("/api/learn/queue").status_code == 401
        assert client.get("/api/learn/queue", headers=editor).status_code == 200
        response = client.put("/api/learn/lessons/single-crochet", json=spec(), headers=editor)
        assert response.status_code == 200, response.text
        rev = response.json()["revision"]
        assert client.get("/api/learn/lessons/single-crochet", headers=editor).status_code == 401
        assert client.get("/api/learn/lessons/single-crochet", headers=reviewer).json()["spec"]["author"] == "learn-operator-editor"
        review = {"revision": rev, "verdicts": dict.fromkeys(DIMENSIONS,"PASS"),
                  "evidence_ref": "fixture-review-001", "evidence_class": "human_attestation"}
        assert client.post("/api/learn/lessons/single-crochet/review",json=review,headers=editor).status_code == 401
        review["verdicts"]["visual_accuracy"] = "UNKNOWN"
        assert client.post("/api/learn/lessons/single-crochet/review",json=review,headers=reviewer).json()["state"] == "WITHHELD"
        assert client.get("/learn/single-crochet").status_code == 404
        review["verdicts"]["visual_accuracy"] = "PASS"
        response = client.post("/api/learn/lessons/single-crochet/review",json=review,headers=reviewer)
        assert response.json()["automated_truth_proof"] is False
        assert client.get("/learn/single-crochet?revision="+rev).status_code == 200
        changed = spec(); changed["learner_problem"] = "new purpose"
        client.put("/api/learn/lessons/single-crochet",json=changed,headers=editor)
        assert client.post("/api/learn/lessons/single-crochet/review",json=review,headers=reviewer).status_code == 422
        assert client.get("/learn/single-crochet?revision="+rev).status_code == 404
        with patch.dict(os.environ,{"BRAMBLELOOP_LEARN_REVIEW_TOKEN": config["BRAMBLELOOP_OPS_TOKEN"]}):
            assert client.get("/api/learn/lessons/single-crochet",headers=editor).status_code == 503
        db.engine.dispose()


if __name__ == "__main__":
    tests = [v for k,v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(len(tests), "passing")
