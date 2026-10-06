"""Wave-3 lane K10: Learn residuals F-799, F-801, F-805, F-806, F-826.

Hermetic: no network, no model, no secret. Each test names the row it closes.
"""
from __future__ import annotations

import copy
import hashlib
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("BRAMBLELOOP_PHASE", "shadow")

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import PatternVersion, Product, SupportCase  # noqa: E402
from brambleloop.learn import service as LS  # noqa: E402
from brambleloop.learn import technique as T  # noqa: E402
from brambleloop.learn.models import LearnGap  # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
EDITOR_TOKEN = "k10-editor-test-credential-000000000"
REVIEW_TOKEN = "k10-reviewer-test-credential-0000000"


def _db(name="k10.db"):
    td = tempfile.mkdtemp(prefix="k10_")
    db = Database("sqlite:///" + str(Path(td) / name), scratch=True)
    db.create_all()
    return db


def _spec(stitch="dc", term=None, assets=None, swatch=None, topics=None):
    spec = {"author": "pattern-engineering", "learner_problem": f"work a {stitch}",
            "topics": topics or [f"stitch:{stitch}"], "terminology": "US",
            "assumptions": {"hook_mm": 4, "yarn_weight": "worsted"},
            "assets": assets if assets is not None else [
                {"rights": "brambleloop_original", "source": "canonical-demo",
                 "sha256": "a" * 64}],
            "steps": [{"stitch": stitch, "repeat": 2, "consumes": 2, "produces": 2,
                       "term": term or stitch,
                       "instruction": f"Work one {stitch} in each of next two stitches."}]}
    if swatch is not None:
        spec["swatch"] = swatch
    return spec


def _swatch_cir(stitch="dc", rows=3, width=6, wrong_row=None, hook=4.0, weight="worsted"):
    return {"slug": "swatch", "title": "Practice swatch", "version": "1",
            "construction": "flat_rows",
            "gauge": {"stitches_per_10cm": 14, "rows_per_10cm": 8, "stitch_type": stitch,
                      "hook_mm": hook},
            "materials": [{"name": "practice yarn", "yarn_weight": weight}],
            "components": [{"name": "swatch", "construction": "flat_rows",
                            "foundation": width,
                            "rows": [{"index": i, "ops": [{"stitch": stitch, "count": width}],
                                      "declared_count": width + (1 if i == wrong_row else 0),
                                      "turning_chain": 3}
                                     for i in range(1, rows + 1)]}]}


def _diagram_asset(stitch="dc", loop="both"):
    return {"kind": "technique_diagram", "stitch": stitch, "loop": loop,
            "rights": "brambleloop_original", "source": f"learn.technique:{stitch}:{loop}",
            "sha256": T.digest(stitch, loop)}


def _refused(spec, needle=None):
    errors = LS.validate_spec(spec)
    assert errors, "spec accepted"
    if needle:
        assert any(needle in e for e in errors), errors
    return errors


# ---- F-801: pattern-to-lesson trigger covers finishing, seaming, blocking, gauge issues ------

def _cir_with_finishing():
    from brambleloop.products import launch0
    d = launch0.cir_for("basket_small").to_dict()
    d = copy.deepcopy(d)
    d["assembly"] = [{"method": "whipstitch", "piece_a": d["components"][0]["name"],
                      "piece_b": d["components"][0]["name"], "stuff_before_closing": True}]
    d["components"][0]["gauge"] = {"stitches_per_10cm": 20, "rows_per_10cm": 20,
                                   "stitch_type": "sc", "hook_mm": 3.5}
    return d


def test_f801_finishing_seaming_blocking_and_gauge_change_are_topics():
    from brambleloop.products import launch0
    real = launch0.cir_for("basket_small").to_dict()
    found = LS.pattern_topics(real)
    assert {"finishing:fasten_off_weave_in_ends", "finishing:blocking_upright",
            "technique:magic_ring"} <= found, found
    assert "finishing:blocking_upright" not in LS.topics(real)  # new, not pre-existing
    flat = LS.pattern_topics(launch0.cir_for("cloudline_blanket").to_dict())
    assert "finishing:blocking_flat" in flat and "finishing:blocking_upright" not in flat
    rich = LS.pattern_topics(_cir_with_finishing())
    assert {"finishing:seam_whipstitch", "finishing:stuffing",
            "technique:gauge_change"} <= rich, rich


def test_f801_real_launch0_pattern_creates_finishing_gaps_through_scan():
    from brambleloop.products import launch0
    db = _db()
    with db.session() as s:
        p = Product(slug="basket-small", title="Basket")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1",
                             cir_json=launch0.cir_for("basket_small").to_dict()))
    out = LS.scan(db)
    assert out["decision"] == "QUEUE"
    with db.session() as s:
        for topic in ("finishing:fasten_off_weave_in_ends", "finishing:blocking_upright",
                      "technique:magic_ring"):
            gap = s.get(LearnGap, topic)
            assert gap is not None and gap.state == "QUEUED", topic
            assert gap.evidence and gap.evidence[0]["product_slug"] == "basket-small"
    assert LS.scan(db)["queued"] == out["queued"]  # idempotent: one gap per topic
    db.engine.dispose()


def test_f801_toy_cir_without_components_is_unchanged():
    toy = {"construction": "flat_rows", "rows": [{"stitch": "sc", "count": 2}]}
    assert LS.pattern_topics(toy) == LS.topics(toy) == {"stitch:sc", "construction:flat_rows"}


# ---- F-805: lesson swatches compile and reverse-compile like patterns -------------------------

def test_f805_clean_swatch_is_accepted_and_served_written_from_cir():
    spec = _spec(swatch={"cir": _swatch_cir()})
    assert LS.validate_spec(spec) == []
    from brambleloop.learn import swatch
    text = swatch.written(spec)
    assert "Row 3:" in text and "(6 sts)" in text


def test_f805_wrong_row_total_is_refused():
    _refused(_spec(swatch={"cir": _swatch_cir(wrong_row=2)}), "COUNT_MISMATCH")


def test_f805_edited_swatch_text_is_refused_by_reverse_compiler():
    from brambleloop.cir.compiler import compile_cir
    from brambleloop.cir.model import CIR
    from brambleloop.cir.writer import write_pattern
    cir = CIR.from_dict(_swatch_cir())
    good = write_pattern(cir, compile_cir(cir), "US")
    assert LS.validate_spec(_spec(swatch={"cir": _swatch_cir(), "text": good})) == []
    bad = good.replace("Row 2: Ch 3, turn. dc in next 6 sts. (6 sts)",
                       "Row 2: Ch 3, turn. dc in next 5 sts. (5 sts)")
    assert bad != good
    _refused(_spec(swatch={"cir": _swatch_cir(), "text": bad}), "swatch text disagrees")


def test_f805_swatch_must_work_taught_stitch_and_match_assumptions():
    _refused(_spec(swatch={"cir": _swatch_cir(stitch="sc")}), "does not work the stitch")
    _refused(_spec(swatch={"cir": _swatch_cir(hook=5.0)}), "hook")
    _refused(_spec(swatch={"cir": _swatch_cir(weight="dk")}), "yarn weight")
    _refused(_spec(swatch={"cir": _swatch_cir(rows=1)}), "multi-row")
    _refused(_spec(swatch={"cir": {"slug": "x"}}), "not a valid CIR")
    _refused(_spec(swatch="three rows of dc"), "carrying a CIR")


def test_f805_uk_swatch_reverse_compiles_in_uk_terms():
    spec = _spec(term="tr", swatch={"cir": _swatch_cir()})
    spec["terminology"] = "UK"
    assert LS.validate_spec(spec) == [], LS.validate_spec(spec)


def test_f805_tampered_stored_swatch_loses_eligibility():
    db = _db()
    spec = _spec(swatch={"cir": _swatch_cir()})
    rev = LS.save_lesson(db, "dc-swatch", spec)
    LS.review_lesson(db, "dc-swatch", rev, "independent-qa",
                     dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture-review:test-only")
    assert LS.approved_lesson(db, "dc-swatch") is not None
    try:
        LS.save_lesson(db, "dc-swatch", _spec(swatch={"cir": _swatch_cir(wrong_row=3)}))
    except ValueError:
        pass
    else:
        raise AssertionError("wrong-total swatch saved")
    assert LS.approved_lesson(db, "dc-swatch") is not None  # refused save did not touch it
    from brambleloop.learn.models import Lesson
    with db.session() as s:  # a direct edit of the stored swatch cannot keep approval
        row = s.get(Lesson, "dc-swatch")
        value = copy.deepcopy(row.spec)
        value["swatch"]["cir"]["components"][0]["rows"][1]["declared_count"] = 7
        row.spec = value
    assert LS.approved_lesson(db, "dc-swatch") is None
    db.engine.dispose()


# ---- F-806: technique diagrams generated and verified from the drawing -----------------------

def test_f806_every_supported_diagram_verifies_and_is_deterministic():
    codes = T.supported()
    assert codes
    for code in codes:
        loops = ("both", "front", "back") if code in ("sc", "hdc", "dc", "tr") else ("both",)
        assert loops
        for loop in loops:
            svg = T.render(code, loop)
            assert svg == T.render(code, loop)
            assert T.verify(svg, code, loop)["stages"] >= 3
            assert T.technique(code, loop).stages()[-1]["loops"] == 1


def test_f806_dc_diagram_drawn_as_sc_fails():
    sc_drawing = T.render("sc")
    relabelled = sc_drawing.replace(b'data-technique="sc"', b'data-technique="dc"')
    try:
        T.verify(relabelled, "dc")
    except T.DiagramRefused as exc:
        assert "not the dc" in str(exc)
    else:
        raise AssertionError("a single-crochet drawing passed as double crochet")


def test_f806_wrong_insertion_point_wrong_post_and_orientation_fail():
    front = T.render("dc", "front")
    for claimed, loop in (("dc", "back"), ("dc", "both"), ("fpdc", "both")):
        try:
            T.verify(front, claimed, loop)
        except T.DiagramRefused:
            pass
        else:
            raise AssertionError(f"front-loop dc passed as {claimed}/{loop}")
    try:
        T.verify(T.render("fpdc"), "bpdc")
    except T.DiagramRefused:
        pass
    else:
        raise AssertionError("front-post passed as back-post")
    flipped = T.render("dc").replace(b'd="M100 120 L20 120"', b'd="M20 120 L100 120"')
    try:
        T.verify(flipped, "dc")
    except T.DiagramRefused as exc:
        assert "direction" in str(exc)
    else:
        raise AssertionError("reversed working direction passed")
    one_loop_short = T.render("tr").replace(b'<ellipse class="loop-on-hook" cx="78"', b'<ellipse class="decor" cx="78"', 1)
    try:
        T.verify(one_loop_short, "tr")
    except T.DiagramRefused:
        pass
    else:
        raise AssertionError("missing loop on hook passed")


def test_f806_unsupported_stitch_gets_no_diagram():
    for code, loop in (("bob", "both"), ("nonsense", "both"), ("fpdc", "front")):
        try:
            T.technique(code, loop)
        except T.UnsupportedTechnique:
            pass
        else:
            raise AssertionError(f"{code}/{loop} given a diagram")


def test_f806_lesson_assets_refuse_photos_generic_images_and_other_stitch_diagrams():
    assert LS.validate_spec(_spec(assets=[_diagram_asset("dc")])) == []
    photo = {"kind": "photo", "rights": "brambleloop_original", "source": "pretty.jpg",
             "sha256": "b" * 64}
    _refused(_spec(assets=[photo]), "nothing measures loops in a photograph")
    generic = {"rights": "brambleloop_original", "source": "x", "sha256": "c" * 64,
               "illustrates": "dc"}
    _refused(_spec(assets=[generic]), "must be a verified technique_diagram")
    _refused(_spec(assets=[_diagram_asset("sc")]), "do not teach")
    forged = dict(_diagram_asset("dc"), sha256=T.digest("sc"))
    _refused(_spec(assets=[forged]), "not the canonical generated diagram")


def test_f806_public_route_serves_only_verified_declared_diagram():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    db = _db()
    spec = _spec(assets=[_diagram_asset("dc")], swatch={"cir": _swatch_cir()})
    rev = LS.save_lesson(db, "double-crochet", spec)
    app = FastAPI()
    app.include_router(router(db))
    client = TestClient(app)
    url = f"/learn/double-crochet/technique/dc.svg?revision={rev}&loop=both"
    assert client.get(url).status_code == 404  # draft: nothing served
    LS.review_lesson(db, "double-crochet", rev, "independent-qa",
                     dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture-review:test-only")
    body = client.get("/learn/double-crochet?revision=" + rev).json()
    assert body["technique_diagrams"][0]["href"] == url
    assert "Row 3:" in body["swatch_instructions"]
    r = client.get(url)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
    assert hashlib.sha256(r.content).hexdigest() == T.digest("dc")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert client.get(f"/learn/double-crochet/technique/sc.svg?revision={rev}").status_code == 404
    assert client.get(f"/learn/double-crochet/technique/dc.svg?revision=stale").status_code == 404
    db.engine.dispose()


def test_f806_human_visual_attestation_is_still_required():
    db = _db()
    rev = LS.save_lesson(db, "double-crochet", _spec(assets=[_diagram_asset("dc")]))
    verdicts = dict.fromkeys(LS.DIMENSIONS, "PASS")
    verdicts["visual_accuracy"] = "UNKNOWN"
    LS.review_lesson(db, "double-crochet", rev, "independent-qa", verdicts, "fixture")
    assert LS.approved_lesson(db, "double-crochet") is None
    db.engine.dispose()


# ---- F-826: no content mill -----------------------------------------------------------------

def test_f826_draft_without_source_backed_gap_is_refused_422():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    db = _db()
    app = FastAPI()
    app.include_router(router(db))
    client = TestClient(app)
    editor = {"Authorization": "Bearer " + EDITOR_TOKEN}
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": EDITOR_TOKEN}):
        # No scan has found any source: every topic is filler.
        r = client.put("/api/learn/lessons/double-crochet", json=_spec(), headers=editor)
        assert r.status_code == 422 and "source-backed content gap" in r.text
        with db.session() as s:
            p = Product(slug="p", title="P")
            s.add(p)
            s.flush()
            s.add(PatternVersion(product_id=p.id, version="1", cir_json={
                "construction": "flat_rows", "rows": [{"stitch": "dc", "count": 2}]}))
        LS.scan(db)
        # A real gap for one topic does not license a lesson that also claims another.
        mixed = _spec(topics=["stitch:dc", "stitch:tr"])
        r = client.put("/api/learn/lessons/double-crochet", json=mixed, headers=editor)
        assert r.status_code == 422
        for empty in ([], "stitch:dc", [None]):
            bad = _spec()
            bad["topics"] = empty
            assert client.put("/api/learn/lessons/x", json=bad, headers=editor).status_code == 422
        ok = client.put("/api/learn/lessons/double-crochet", json=_spec(), headers=editor)
        assert ok.status_code == 200, ok.text
    db.engine.dispose()


def test_f826_scan_never_generates_and_watches_when_all_covered():
    db = _db()
    with db.session() as s:
        p = Product(slug="p", title="P")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", cir_json={
            "construction": "flat_rows", "rows": [{"stitch": "dc", "count": 2}]}))
    first = LS.scan(db)
    assert first["generated"] == 0 and first["published"] == 0
    for slug, topic in (("double-crochet", "stitch:dc"), ("flat-rows", "construction:flat_rows")):
        spec = _spec(topics=[topic])
        rev = LS.save_lesson(db, slug, spec)
        LS.review_lesson(db, slug, rev, "independent-qa",
                         dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture")
    out = LS.scan(db)
    assert out["decision"] == "WATCH" and out["queued"] == 0 and out["generated"] == 0
    db.engine.dispose()


# ---- F-799: Learn metrics, calendar, experiments, improve cell ------------------------------

def _seeded_db():
    db = _db()
    with db.session() as s:
        p = Product(slug="p", title="P")
        s.add(p)
        s.flush()
        s.add(PatternVersion(product_id=p.id, version="1", created_at=NOW - timedelta(hours=50),
                             cir_json={"construction": "flat_rows",
                                       "rows": [{"stitch": "dc", "count": 2}]}))
        s.add(SupportCase(customer_ref="c", question="q", specialist="gauge",
                          at=NOW - timedelta(hours=5)))
    LS.scan(db)
    return db


def test_f799_department_metrics_are_derived_from_rows():
    from brambleloop.learn import metrics
    empty = metrics.summary(_db(), now=NOW)
    assert empty["status"] == "UNKNOWN" and "unknowable" in empty["reason"]
    db = _seeded_db()
    m = metrics.department_metrics(db, now=NOW)
    assert m["gaps_total"] == 3 and m["gaps_queued"] == 3 and m["gaps_covered"] == 0
    assert m["coverage"] == 0.0 and m["oldest_queued_age_hours"] == 50.0
    assert m["queued_undated"] == 0 and m["decision"] == "QUEUE"
    rev = LS.save_lesson(db, "double-crochet", _spec())
    LS.review_lesson(db, "double-crochet", rev, "independent-qa",
                     dict.fromkeys(LS.DIMENSIONS, "PASS"), "fixture")
    LS.scan(db)
    m = metrics.department_metrics(db, now=NOW)
    assert m["gaps_covered"] == 1 and m["coverage"] == round(1 / 3, 4)
    assert m["lessons_by_state"] == {"APPROVED": 1} and m["lessons_approved"] == 1
    cal = metrics.calendar(db, now=NOW)
    assert cal["basis"] == "planned" and len(cal["slots"]) == 2
    assert all(slot["week_of"] == "2026-10-12" for slot in cal["slots"])
    out = metrics.summary(db, now=NOW)
    assert out["status"] == "DEGRADED" and out["basis"] == "measured"
    assert out["experiments"]["cell"] == "learn"
    db.engine.dispose()


def test_f799_learn_is_an_improvement_cell_measured_nightly():
    from brambleloop.improve import cells, freshness, measure, profiles
    assert "learn" in cells.BY_KEY and "learn" in measure.MEASURERS
    assert freshness.CELL_WORLD["learn"] and profiles.CELL_AGENT["learn"] == "learn"
    db = _db()
    assert isinstance(measure.measure_cell(db, "learn"), measure.NotMeasured)
    db = _seeded_db()
    reading = measure.measure_cell(db, "learn")
    assert reading.value == 0.0 and reading.sample == 3
    out = measure.record_all(db)
    assert any(r["cell"] == "learn" for r in out["recorded"])
    assert cells.latest_capability(db, "learn") == 0.0
    # The same propose/test/promote loop applies: a Learn experiment needs a baseline.
    iid = cells.propose(db, cell="learn", hypothesis=(
        "drafting lessons for the most-evidenced gaps first raises lesson gap coverage"),
        expected_effect="coverage rises", rollback_ref="capability:learn",
        touches=("ordering",))
    from brambleloop.learn import metrics
    assert metrics.experiments(db)["items"][-1]["id"] == iid
    db.engine.dispose()


def test_f799_runtime_consumers_carry_learn_metrics():
    from brambleloop.agents.registry import Registry
    from brambleloop.core.models import AuditLog
    from brambleloop.learn import improvement_status
    from brambleloop.learn import runtime  # noqa: F401 - registers learn.scan
    from brambleloop.queue.durable import JobQueue
    from brambleloop.runtime.worker import Worker
    from sqlalchemy import select
    db = _seeded_db()
    Registry(db).seed_defaults()
    JobQueue(db).enqueue("learn", "learn.scan", {})
    worker = Worker(db, job_types=["learn.scan"])
    assert worker.run_once() and worker.stats.completed == 1
    with db.session() as s:
        audit = [a for a in s.scalars(select(AuditLog).where(AuditLog.action == "learn.scanned"))]
        assert audit and audit[-1].detail["metrics"]["gaps_total"] == 3
    dept = improvement_status.summary(db)["department"]
    assert dept["metrics"]["gaps_queued"] == 3 and dept["calendar"]["slots"]
    db.engine.dispose()


def test_f799_metrics_route_is_editor_only():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from brambleloop.learn.api import router
    db = _seeded_db()
    app = FastAPI()
    app.include_router(router(db))
    client = TestClient(app)
    with patch.dict(os.environ, {"BRAMBLELOOP_OPS_TOKEN": EDITOR_TOKEN}):
        assert client.get("/api/learn/metrics").status_code == 401
        r = client.get("/api/learn/metrics", headers={"Authorization": "Bearer " + EDITOR_TOKEN})
        assert r.status_code == 200 and r.json()["metrics"]["gaps_total"] == 3
    db.engine.dispose()


def test_learn_constants_are_protected_from_self_improvement():
    from brambleloop.improve import governance, invariants
    governance.protected_constants.cache_clear()
    table = governance.protected_constants()
    assert "ANCHOR_TOLERANCE" in table and "ASSET_KINDS" in table
    assert not invariants.check("ANCHOR_TOLERANCE", 30.0, tunable=None).ok
    from brambleloop.improve import policy_loops as pl
    loops = list(pl.LOOPS)
    assert loops
    for lp in loops:  # no launch loop's own tunable became protected by this
        assert invariants.check(lp.param, lp.default, tunable=lp.tunable()).ok, lp.key


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print("OK  ", test.__name__)
        except Exception as exc:  # noqa: BLE001
            import traceback
            failed += 1
            print("FAIL", test.__name__, type(exc).__name__, exc)
            traceback.print_exc()
    print(len(tests) - failed, "passing,", failed, "failing")
    sys.exit(1 if failed else 0)
