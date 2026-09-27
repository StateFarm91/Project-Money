"""#59 and #61 on every listing frame, through `assets.build` (C-69).

Layout QA ran on the hero only, and the independent visual review never ran on the size card,
the chart preview or the finished-result frame. These tests run `assets.build` through the
worker on a certified release and assert that a box defect on a non-hero frame and a failed
independent review on a non-hero frame each stop the chain, and that unreviewed frames are
recorded and read by the publish path as not passed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="cert_frames_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Job, JobStatus, Phase  # noqa: E402
from brambleloop.publish import layout_qa, listing_assets  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402

SLUG = "nordic-forest-mosaic-throw"


def _certified():
    db = Database(f"sqlite:///{tempfile.mkdtemp()}/frames.sqlite")
    db.create_all()
    Registry(db).seed_defaults()
    cir = pipeline._engineered_cir(SLUG)
    JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                         idempotency_key="cert", priority=0)
    Worker(db, "f", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
    return db, cir


def _build(db, cir, key):
    job = JobQueue(db).enqueue("publishing", "assets.build",
                               {"slug": cir.slug, "version": cir.version, "release": "",
                                "rebuild": key}, idempotency_key=key, priority=0)
    Worker(db, f"f-{key}", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
    with db.session() as s:
        row = s.get(Job, job.id)
        assert row.status == JobStatus.DONE, row.last_error
        return dict(row.outputs)


def _review(db, cir):
    with db.session() as s:
        return [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == release.FRAME_REVIEW_ACTION))][-1]


def test_every_frame_is_measured_and_recorded_unreviewed_when_vision_is_closed():
    db, cir = _certified()
    out = _build(db, cir, "clean")
    assert out.get("ok") is not False, out
    review = _review(db, cir)
    assert review["vision_open"] is False
    assert len(review["frames"]) >= 6 and set(v["verdict"] for v in review["frames"].values()) \
        == {"unreviewed"}
    state = release.frame_review_state(db, cir.slug, cir.version)
    assert state["reviewed"] is False and "#61" in state["why"]


def test_type_over_the_chart_on_a_non_hero_frame_stops_the_chain():
    db, cir = _certified()
    real = listing_assets.build_frames

    def colliding(*a, **k):
        frames = real(*a, **k)
        chart = next(f for f in frames if f.role == "chart")
        box = next(e["box"] for e in chart.image.info["layout"] if e["kind"] == "chart")
        chart.image.info["layout"].append({"kind": "text", "box": [box[0] + 10, box[1] + 10,
                                                                  box[0] + 400, box[1] + 60],
                                           "text": "Row 12 label", "pt": 40})
        return frames

    release.build_frames = colliding
    try:
        out = _build(db, cir, "collide")
    finally:
        release.build_frames = real
    assert out.get("ok") is False, out
    assert any("LAYOUT_TEXT_GRAPHIC_COLLISION" in p and "frame 6" in p
               for p in out["blocking_image_problems"]), out["blocking_image_problems"]


def test_a_chart_preview_the_independent_review_says_is_not_a_chart_stops_the_chain():
    from brambleloop.build2 import executor
    from brambleloop.visual import inspect as inspection

    db, cir = _certified()
    gate = executor.GATE_BY_KEY["image_vision"]
    original_check, original_inspect = gate.check, inspection.inspect_image

    def fake_inspect(ref, *, db=None, provider=None, claim=None):
        chart = bool(claim and claim.get("shows_chart_preview"))
        description = {"object_shown": "a blanket" if chart else "a page",
                       "chart_or_diagram": False, "finished_or_in_progress": "finished",
                       "object_count": "1", "clarity": "clear", "text_present": True,
                       "third_party_marks": "none", "human_present": False}
        return {"described": True, "description": description,
                "realism": {}, "realism_unjudged": [],
                "semantic": inspection.compare(description, claim or {})}

    gate.check = lambda db_, env: True
    inspection.inspect_image = fake_inspect
    try:
        out = _build(db, cir, "review")
    finally:
        gate.check, inspection.inspect_image = original_check, original_inspect
    assert out.get("ok") is False
    assert any("FRAME_REVIEW_BLOCKED" in p and "(chart)" in p
               for p in out["blocking_image_problems"]), out["blocking_image_problems"]
    review = _review(db, cir)
    by_role = {v["role"]: v["verdict"] for v in review["frames"].values()}
    assert by_role["chart"] == "blocked" and by_role["size"] == "clear"


def test_the_box_rules_measure_truncation_and_footer_overlap():
    from PIL import Image

    img = Image.new("RGB", (1000, 1000), (240, 235, 225))
    img.info["layout"] = [
        {"kind": "text", "box": [100, 100, 990, 150], "text": "A very long title", "pt": 40},
        {"kind": "text", "box": [100, 880, 600, 920], "text": "line", "pt": 30},
        {"kind": "text", "box": [120, 900, 500, 940], "text": "footer", "pt": 30},
    ]
    problems = layout_qa.check_layout(img, position=3)
    assert any(p.startswith("LAYOUT_TEXT_OUTSIDE_SAFE_AREA") for p in problems)
    assert any(p.startswith("LAYOUT_FOOTER_OVERLAP") for p in problems)
    assert layout_qa.check_layout(Image.new("RGB", (10, 10)), position=1)[0].startswith(
        "LAYOUT_UNRECORDED")


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print("FAIL", name, repr(e))
    print(f"\n{'PASS' if not fails else 'FAIL'}: {fails} failing")
    sys.exit(1 if fails else 0)
