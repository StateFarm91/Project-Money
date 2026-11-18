"""#59 and #61 on every listing frame, through `assets.build` (C-69).

Layout QA ran on the hero only, and the independent visual review never ran on the size card,
the chart preview or the finished-result frame. These tests run `assets.build` through the
worker on a certified release and assert that a box defect on a non-hero frame and a failed
independent review on a non-hero frame each stop the chain, and that unreviewed frames are
recorded and read by the publish path as not passed.
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
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

# CB2-P06 fixture: nordic-forest-mosaic-throw no longer certifies under the strict gauge gate
# (GAUGE_OUTSIDE_DECLARED_YARN_BAND, 6747ddd), so assets.build refused to run at all. These
# tests need *a* certified Launch-0 release; hexagon-coaster-set certifies as built (PT-11
# retired its old alias hexie-coaster-set). The gate is unchanged.
SLUG = "hexagon-coaster-set"


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
    # C-80 defect 6: every role the builder emits has a registered claim (none is reviewed
    # against nothing), and defect 7: the review records the bytes it was of.
    from brambleloop.core.models import ListingAsset

    with db.session() as s:
        stored = {str(r.position): (r.role, r.sha256) for r in s.scalars(
            select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                       ListingAsset.version == cir.version))}
    assert len(stored) >= 6
    assert {role for role, _ in stored.values()} <= set(release.ROLE_CLAIMS), (
        {role for role, _ in stored.values()} - set(release.ROLE_CLAIMS))
    assert review["frame_shas"] == {k: sha for k, (_r, sha) in stored.items()}
    assert not any(v["verdict"] == "unclaimed" for v in review["frames"].values())


def _fake_vision(unmade: list[str], marks: str = "none",
                 shown: str = "a set of hexagon coasters"):
    from brambleloop.visual import inspect as inspection

    def fake_inspect(ref, *, db=None, provider=None, claim=None):
        chart = bool(claim and claim.get("shows_chart_preview"))
        # W4-FIRSTIMG (F-027): the fixture describes what the release actually sells (a
        # hexagon coaster set); "a blanket" for a coaster set is now a misidentified hero.
        description = {"object_shown": "a chart" if chart else shown,
                       "chart_or_diagram": chart, "finished_or_in_progress": "finished",
                       "object_count": "1", "clarity": "clear", "text_present": True,
                       "third_party_marks": marks, "human_present": False}
        return {"described": True, "description": description,
                "realism": {}, "realism_unjudged": list(unmade),
                "semantic": inspection.compare(description, claim or {})}
    return fake_inspect


def _fake_describe(marks: str = "none", shown: str = "a set of hexagon coasters"):
    """`inspect.describe_image`: the blind description a non-photo frame gets (D-W4-VISROLE),
    with no realism call at all."""
    inspect = _fake_vision([], marks, shown)

    def fake_describe(ref, *, db=None, provider=None, claim=None):
        got = inspect(ref, db=db, provider=provider, claim=claim)
        got.pop("realism"), got.pop("realism_unjudged")
        return dict(got, realism_not_applicable=True)
    return fake_describe


def _fake_grid(verdict: str = "clear"):
    def fake_grid(ref, *, families, db=None, provider=None, **_k):
        return {"verdict": verdict, "why": f"fixture grid {verdict}", "grid_px": 230,
                "clarity": "clear", "problems": [], "families": list(families or ())}
    return fake_grid


def test_unjudged_stays_unjudged_and_only_a_bound_all_clear_review_opens_publication():
    """C-80 defects 6 and 7 (Codex P06), under the role-appropriate rule (D-W4-VISROLE).

    Every frame this builder makes is a deterministic non-photo frame (a disclosed twin
    drawing, a chart, infographics, a pattern preview). They are classified from the frame
    plan and are never asked the photographic realism checks; a realism checklist the
    reviewer could not answer no longer holds them. They are held to their role checks
    instead, and an unanswered role check is unjudged, never a pass. An empty review or a
    review of other bytes does not count; a complete clear review of exactly the stored
    frames does."""
    from brambleloop.build2 import executor
    from brambleloop.core.models import ListingAsset
    from brambleloop.visual import frame_role
    from brambleloop.visual import inspect as inspection

    db, cir = _certified()
    gate = executor.GATE_BY_KEY["image_vision"]
    original_check, original_inspect = gate.check, inspection.inspect_image
    original_describe = inspection.describe_image
    original_grid = inspection.identify_at_grid
    gate.check = lambda db_, env: True
    # W4-FIRSTIMG: the hero's grid identification (F-031) is a vision call; stubbed clear.
    inspection.identify_at_grid = _fake_grid("clear")
    # The realism inspection would leave a check unmade on every frame; no non-photo frame
    # may reach it, so it is wired to say so if it is ever called.
    inspection.inspect_image = _fake_vision(["texture_not_repeating"])
    try:
        # 1. A role check left unanswered ("unclear" on third-party marks): unjudged.
        inspection.describe_image = _fake_describe(marks="unclear")
        out = _build(db, cir, "unjudged")
        review = _review(db, cir)
        assert set(v["verdict"] for v in review["frames"].values()) == {"unjudged"}, review
        assert all(v["visual_role"] in frame_role.NON_PHOTO
                   for v in review["frames"].values()), review
        assert all(v["unmade"] == ["no_third_party_marks"]
                   for v in review["frames"].values()), review
        assert not any(v["failed_realism"] for v in review["frames"].values())
        # unjudged does not stop assets.build (nothing failed) but it is not a pass at publish
        assert out.get("ok") is not False, out
        state = release.frame_review_state(db, cir.slug, cir.version)
        assert state["reviewed"] is False and set(state["not_clear"].values()) == {"unjudged"}

        # 2. Every role check answered and passed, with the realism inspection still saying
        # it would leave a check unmade: the non-photo frames are clear, because the realism
        # checks are not theirs -- and every role check is recorded as passed.
        inspection.describe_image = _fake_describe(marks="none")
        _build(db, cir, "clear")
        review = _review(db, cir)
        assert all(set(v["role_checks"]) == set(frame_role.ROLE_CHECKS)
                   and all(c["passed"] is True for c in v["role_checks"].values())
                   for v in review["frames"].values()), review
        state = release.frame_review_state(db, cir.slug, cir.version)
        assert state["reviewed"] is True and state["bound_to_stored_frames"] is True, state
    finally:
        gate.check, inspection.inspect_image = original_check, original_inspect
        inspection.describe_image = original_describe
        inspection.identify_at_grid = original_grid

    # the same review no longer counts once the stored bytes differ
    with db.session() as s:
        row = s.scalar(select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                                  ListingAsset.position == 3))
        row.sha256 = "0" * 64
    state = release.frame_review_state(db, cir.slug, cir.version)
    assert state["reviewed"] is False and state["bound_to_stored_frames"] is False
    assert "differ" in state["why"]

    # and a review that judged no frames is not a review
    with db.session() as s:
        s.add(AuditLog(actor="publishing", action=release.FRAME_REVIEW_ACTION,
                       artifact=f"{cir.slug}@{cir.version}",
                       detail={"vision_open": True, "frames": {}, "frame_shas": {}}))
    state = release.frame_review_state(db, cir.slug, cir.version)
    assert state["reviewed"] is False and "empty review" in state["why"]


def test_a_frame_role_without_a_registered_claim_is_unclaimed_and_stops_the_chain():
    db, cir = _certified()
    real = listing_assets.build_frames

    def renamed(*a, **k):
        frames = real(*a, **k)
        next(f for f in frames if f.role == "materials").role = "mystery"
        return frames

    release.build_frames = renamed
    try:
        out = _build(db, cir, "unclaimed")
    finally:
        release.build_frames = real
    assert out.get("ok") is False, out
    assert any("FRAME_REVIEW_UNCLAIMED" in p and "(mystery)" in p
               for p in out["blocking_image_problems"]), out["blocking_image_problems"]
    review = _review(db, cir)
    assert any(v["verdict"] == "unclaimed" for v in review["frames"].values())


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

    def fake_describe(ref, *, db=None, provider=None, claim=None):
        got = fake_inspect(ref, db=db, provider=provider, claim=claim)
        got.pop("realism"), got.pop("realism_unjudged")
        return got

    gate.check = lambda db_, env: True
    original_describe = inspection.describe_image
    inspection.inspect_image = fake_inspect
    inspection.describe_image = fake_describe
    try:
        out = _build(db, cir, "review")
    finally:
        gate.check, inspection.inspect_image = original_check, original_inspect
        inspection.describe_image = original_describe
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



def test_l2_a_photo_led_listing_passes_the_61_publish_check_and_keeps_it_across_a_rebuild():
    """Review of 3928ba00 L2 (the owner's physical-sample plan). A genuine owner-attested sample
    photograph is put first by `plan_upgrade`, which shifts every render one slot; the #61
    frame review is keyed by the builder's positions, so `frame_review_state` could never
    match the stored frames again -- #61 refused every photo-led listing at publish
    (`pipeline._listing_parity`) and `publication_authority`'s parity read UNKNOWN.

    Driven here through the real build, intake, owner attestation, upgrade planner and the
    deterministic photo review: the photo awaiting its review holds #61 (by name); once the
    asset-truth review approves it, #61 passes on the publish path; a rebuild (renders
    re-placed after the photograph) keeps that authority; changed render bytes still fail."""
    from types import SimpleNamespace

    from brambleloop.build2 import executor
    from brambleloop.core.models import ListingAsset
    from brambleloop.ops import publication_authority
    from brambleloop.publish import photo_asset_review as par
    from brambleloop.visual import inspect as inspection

    sys.path.insert(0, str(ROOT / "tests"))
    import test_physfix_photo_first as T

    db = T._db()                     # records the tester's agreement
    cir, _release_hash = T._certified_basket(db)
    gate = executor.GATE_BY_KEY["image_vision"]
    saved = (gate.check, inspection.inspect_image, inspection.describe_image,
             inspection.identify_at_grid)
    gate.check = lambda db_, env: True
    inspection.identify_at_grid = _fake_grid("clear")
    inspection.inspect_image = _fake_vision(["texture_not_repeating"],
                                            shown="a small crochet basket")
    inspection.describe_image = _fake_describe(marks="none", shown="a small crochet basket")

    def publish_check():
        ctx = SimpleNamespace(db=db, job=SimpleNamespace(
            id=0, inputs={"slug": cir.slug, "version": cir.version}),
            audit=lambda *a, **k: None, enqueue=lambda *a, **k: None)
        verdict = pipeline._listing_parity(ctx)
        return verdict["frame_review"], verdict.get("why") or ""

    try:
        _build(db, cir, "photo-led-1")
        assert release.frame_review_state(db, cir.slug, cir.version)["reviewed"] is True
        test_id = T._passed_full_make(db, cir)
        plan = T._upgrade(db, cir, test_id)
        assert plan["frame_position"] == 1, plan
        with db.session() as s:
            gallery = [(r.position, r.asset_class) for r in s.scalars(
                select(ListingAsset).where(ListingAsset.product_slug == cir.slug,
                                           ListingAsset.version == cir.version)
                .order_by(ListingAsset.position))]
        assert gallery[0] == (1, par.PHOTO_CLASS), gallery

        # 1. The photograph awaiting its deterministic review holds #61, by name.
        state = release.frame_review_state(db, cir.slug, cir.version)
        assert state["reviewed"] is False and state["bound_to_stored_frames"] is True, state
        assert state["photo_frames_awaiting"] == [1] and "await" in state["why"], state

        # 2. The asset-truth review approves it: #61 passes, on the publish path too.
        assert par.sweep(db)["approved"] == 1
        state = release.frame_review_state(db, cir.slug, cir.version)
        assert state["reviewed"] is True and state["photo_frames_approved"] == [1], state
        review, why = publish_check()
        assert review["reviewed"] is True and "(#61)" not in why, (review, why)
        parity = publication_authority._parity(db, cir.slug, cir.version)
        assert parity["frame_review"]["reviewed"] is True, parity

        # 3. A rebuild re-places the renders after the photograph and re-reviews them under
        # the builder's own positions: the authority is kept.
        _build(db, cir, "photo-led-2")
        with db.session() as s:
            photo = s.scalar(select(ListingAsset).where(
                ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version,
                ListingAsset.asset_class == par.PHOTO_CLASS))
            assert photo.position == 1 and photo.approved is True, (photo.position,
                                                                    photo.blocked_reasons)
        state = release.frame_review_state(db, cir.slug, cir.version)
        assert state["reviewed"] is True and state["bound_to_stored_frames"] is True, state
        review, why = publish_check()
        assert review["reviewed"] is True and "(#61)" not in why, (review, why)
    finally:
        (gate.check, inspection.inspect_image, inspection.describe_image,
         inspection.identify_at_grid) = saved

    # 4. Still bound to bytes: a stored render that differs from the reviewed one fails.
    with db.session() as s:
        row = s.scalar(select(ListingAsset).where(
            ListingAsset.product_slug == cir.slug, ListingAsset.version == cir.version,
            ListingAsset.position == 3))
        assert row.asset_class != par.PHOTO_CLASS
        row.sha256 = "0" * 64
    state = release.frame_review_state(db, cir.slug, cir.version)
    assert state["reviewed"] is False and state["bound_to_stored_frames"] is False, state
    assert "differ" in state["why"], state

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
