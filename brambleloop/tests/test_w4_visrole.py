"""W4-VISROLE (owner decision D-W4-VISROLE): role-appropriate independent visual review.

A photographic frame is asked every photographic realism check, and an unclear one stays
unjudged. A chart, diagram, infographic or disclosed twin drawing is classified from its frame
plan, never by the model. It is described blind and held to role checks instead: data and
labels match the record, text legible at 340 px, no misleading scale, no third-party marks,
disclosure present. A failed role check blocks. An unanswered one is unjudged, never passed.
Product truth, semantic accuracy and every veto still apply to every frame.

Stub vision only: no network, no spend.
Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_visrole.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import copy
import os
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_visrole_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-VISROLE harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from brambleloop.cir.compiler import ERROR, Finding, compile_cir  # noqa: E402
from brambleloop.cir.twin import build_twin  # noqa: E402
from brambleloop.cir.writer import write_pattern  # noqa: E402
from brambleloop.gates.asset_truth import AssetClass  # noqa: E402
from brambleloop.publish.listing_assets import build_frames  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402
from brambleloop.visual import frame_role as FR  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402

SLUG = "hexagon-coaster-set"
_C: dict = {}


def _built():
    if "frames" not in _C:
        cir = pipeline._engineered_cir(SLUG)
        res = compile_cir(cir)
        twin = build_twin(cir, res)
        _C["cir"], _C["twin"] = cir, twin
        _C["frames"] = build_frames(cir, twin, pattern_text=write_pattern(cir, res),
                                    difficulty="easy", pages=6, siblings=["another pattern"])
    return _C["cir"], _C["twin"], _C["frames"]


def _frame(role):
    cir, twin, frames = _built()
    f = copy.copy(next(x for x in frames if x.role == role))
    f.image = f.image.copy()
    f.image.info["layout"] = [dict(e) for e in f.image.info.get("layout") or []]
    return f


def _desc(**over):
    d = {"object_shown": "a size card", "chart_or_diagram": False,
         "finished_or_in_progress": "finished", "object_count": "1", "clarity": "clear",
         "text_present": True, "third_party_marks": "none", "human_present": False,
         "dominant_colours": "cream", }
    d.update(over)
    return d


def _judge(frame, *, description=None, truth=(), plan=(), labels="record"):
    cir, twin, frames = _built()
    if labels == "record":
        labels = FR.expected_labels(frames, cir, twin).get(frame.position)
    role = FR.classify(frame)
    claim = release.ROLE_CLAIMS[frame.role]
    sem = I.compare(description, claim) if description else {}
    checks = FR.role_checks(frame, slug=SLUG, visual_role=role, description=description,
                            truth_findings=truth, plan_findings=plan, labels=labels)
    v = FR.verdict(described=description is not None,
                   semantic_problems=sem.get("problems") or [],
                   marks=I.marks_found(description or {}), checks=checks)
    return v, checks


def test_roles_are_classified_from_the_frame_plan_and_unknown_is_photographic():
    _c, _t, frames = _built()
    got = {f.role: FR.classify(f) for f in frames}
    assert got == {"hero": FR.DISCLOSED_RENDER, "whats_included": FR.INFOGRAPHIC,
                   "size": FR.INFOGRAPHIC, "materials": FR.INFOGRAPHIC,
                   "pattern_preview": FR.PATTERN_PREVIEW, "chart": FR.CHART,
                   "collection": FR.INFOGRAPHIC}, got
    concept = _frame("hero")
    concept.asset_class = AssetClass.AI_LIFESTYLE_CONCEPT
    photo = _frame("hero")
    photo.asset_class = AssetClass.PHYSICAL_PRODUCT_PHOTO
    odd = _frame("chart")
    odd.role = "something_new"   # a twin render in a role the table does not name
    modelled = _frame("size")
    modelled.has_model = True
    for f in (concept, photo, odd, modelled):
        assert FR.classify(f) == FR.PHOTOGRAPHIC, (f.role, f.asset_class)
    # the classifier reads only the plan: no description argument exists to consult
    import inspect as _py

    assert list(_py.signature(FR.classify).parameters) == ["frame"]


def test_a_non_photo_frame_passes_only_when_every_role_check_passes():
    for role in ("hero", "whats_included", "size", "materials", "pattern_preview", "chart",
                 "collection"):
        f = _frame(role)
        desc = _desc(chart_or_diagram=(role == "chart"),
                     object_shown="a set of hexagon coasters" if role == "hero" else "a card")
        v, checks = _judge(f, description=desc)
        assert set(checks) == set(FR.ROLE_CHECKS), checks
        assert v["verdict"] == "clear", (role, v, checks)
        assert all(c["passed"] is True for c in checks.values()), (role, checks)


def test_a_label_that_does_not_match_the_record_blocks():
    f = _frame("size")
    v, checks = _judge(f, description=_desc(), labels=["99 cm across × 99 cm tall"])
    assert checks["data_matches_record"]["passed"] is False
    assert v["verdict"] == "blocked" and "data_matches_record" in v["failed_role_checks"]
    # and a drawn label edited away from the record is caught against the real record
    g = _frame("size")
    for e in g.image.info["layout"]:
        if "cm across" in str(e.get("text")):
            e["text"] = "12 cm across × 8 cm tall"
    v, checks = _judge(g, description=_desc())
    assert v["verdict"] == "blocked" and checks["data_matches_record"]["passed"] is False


def test_illegible_text_at_340_px_blocks():
    f = _frame("whats_included")
    for e in f.image.info["layout"]:
        if e.get("kind") == "text":
            e["pt"] = 40          # headline 6.8 px at 340 px: under the 11 px floor
    v, checks = _judge(f, description=_desc())
    assert checks["text_legible_340"]["passed"] is False, checks["text_legible_340"]
    assert v["verdict"] == "blocked"
    g = _frame("materials")
    g.image.info["layout"].append({"kind": "text", "box": [100, 100, 200, 110],
                                   "text": "tiny", "pt": 10})
    v, checks = _judge(g, description=_desc())
    assert checks["text_legible_340"]["passed"] is False and v["verdict"] == "blocked"
    h = _frame("collection")
    h.image.info["layout"] = [e for e in h.image.info["layout"] if e.get("kind") != "text"]
    v, checks = _judge(h, description=_desc())
    assert checks["text_legible_340"]["passed"] is False and v["verdict"] == "blocked"


def test_a_missing_disclosure_blocks():
    f = _frame("hero")
    f.image.info["layout"] = [e for e in f.image.info["layout"]
                              if "not a photograph" not in str(e.get("text")).lower()]
    v, checks = _judge(f, description=_desc(object_shown="a set of hexagon coasters"))
    assert checks["disclosure_present"]["passed"] is False
    assert v["verdict"] == "blocked" and "disclosure_present" in v["failed_role_checks"]


def test_every_veto_still_blocks_a_non_photo_frame():
    f = _frame("size")
    where = f"asset:{SLUG}-frame-{f.position}"
    truth = [Finding(ERROR, "CLAIM_SIZE_UNSUPPORTED", "claims 40cm, pattern makes 10cm", where)]
    v, checks = _judge(f, description=_desc(), truth=truth)
    assert v["verdict"] == "blocked"
    assert checks["data_matches_record"]["passed"] is False
    assert checks["scale_not_misleading"]["passed"] is False
    # a frame-plan finding on this frame
    v, checks = _judge(f, description=_desc(),
                       plan=[f"LISTING_LAYOUT_TEXT_GRAPHIC_COLLISION: frame {f.position}: x"])
    assert v["verdict"] == "blocked" and checks["data_matches_record"]["passed"] is False
    # a finding on another frame is not this frame's
    v, _ = _judge(f, description=_desc(), plan=["LISTING_X: frame 6: y"],
                  truth=[Finding(ERROR, "ASSET_COLOR_ABSENT", "x", f"asset:{SLUG}-frame-6")])
    assert v["verdict"] == "clear", v
    # a third-party mark, and a semantic contradiction, each block
    v, checks = _judge(f, description=_desc(third_party_marks="KINFOLK"))
    assert v["verdict"] == "blocked" and checks["no_third_party_marks"]["passed"] is False
    chart = _frame("chart")
    v, _ = _judge(chart, description=_desc(chart_or_diagram=False))
    assert v["verdict"] == "blocked", v
    size = _frame("size")
    size.scale_shown = ""
    v, checks = _judge(size, description=_desc())
    assert v["verdict"] == "blocked" and checks["scale_not_misleading"]["passed"] is False


def test_an_unanswered_role_check_is_never_a_pass():
    f = _frame("materials")
    v, checks = _judge(f, description=_desc(third_party_marks="unclear"))
    assert checks["no_third_party_marks"]["passed"] is None
    assert v["verdict"] == "unjudged" and "no_third_party_marks" in v["unmade"]
    v, _ = _judge(f, description=None)
    assert v["verdict"] == "unjudged" and "description" in v["unmade"]
    g = _frame("materials")
    g.image.info.pop("layout")
    v, checks = _judge(g, description=_desc())
    assert checks["text_legible_340"]["passed"] is None and v["verdict"] == "unjudged"
    # a missing check (any of the five) is unjudged too
    v = FR.verdict(described=True, semantic_problems=[], marks=[],
                   checks={k: {"passed": True} for k in FR.ROLE_CHECKS[:-1]})
    assert v["verdict"] == "unjudged" and FR.ROLE_CHECKS[-1] in v["unmade"]


def test_a_photographic_frame_still_fails_when_a_realism_check_is_unclear():
    """End to end through `_review_frames`: the photographic frame goes to the realism
    inspection and stays unjudged on one unclear check; the non-photo frames never call it."""
    from brambleloop.build2 import executor
    from brambleloop.core.db import Database

    db = Database(f"sqlite:///{_TMP}/vr.sqlite")
    db.create_all()

    class Ctx:
        def __init__(self, db_):
            self.db = db_

        def audit(self, *a, **k):
            pass

    photo = _frame("hero")
    photo.asset_class = AssetClass.AI_LIFESTYLE_CONCEPT
    size = _frame("size")
    paths = {}
    for f in (photo, size):
        p = Path(_TMP, f"frame-{f.position}.png")
        f.image.save(p)
        paths[f.position] = str(p)
    called = {"inspect": [], "describe": []}

    def fake_inspect(ref, *, db=None, provider=None, claim=None):
        called["inspect"].append(ref)
        d = _desc(object_shown="a set of hexagon coasters")
        return {"described": True, "description": d, "realism": {"drape": True},
                "realism_unjudged": ["hands_and_fingers"], "semantic": I.compare(d, claim)}

    def fake_describe(ref, *, db=None, provider=None, claim=None):
        called["describe"].append(ref)
        d = _desc()
        return {"described": True, "description": d, "realism_not_applicable": True,
                "semantic": I.compare(d, claim)}

    def fake_grid(ref, *, families, db=None, provider=None, **_k):
        return {"verdict": "clear", "why": "fixture", "grid_px": 230, "clarity": "clear",
                "problems": [], "families": list(families or ())}

    gate = executor.GATE_BY_KEY["image_vision"]
    saved = (gate.check, I.inspect_image, I.describe_image, I.identify_at_grid)
    gate.check = lambda db_, env: True
    I.inspect_image, I.describe_image, I.identify_at_grid = fake_inspect, fake_describe, \
        fake_grid
    try:
        cir, twin, frames = _built()
        out = release._review_frames(Ctx(db), SLUG, cir.version, [photo, size], paths,
                                     families=["coaster"],
                                     labels=FR.expected_labels(frames, cir, twin))
    finally:
        gate.check, I.inspect_image, I.describe_image, I.identify_at_grid = saved
    v = out["verdicts"]
    assert v[photo.position]["visual_role"] == FR.PHOTOGRAPHIC
    assert v[photo.position]["verdict"] == "unjudged", v[photo.position]
    assert v[photo.position]["unmade"] == ["hands_and_fingers"]
    assert v[size.position]["visual_role"] == FR.INFOGRAPHIC
    assert v[size.position]["verdict"] == "clear", v[size.position]
    assert called["inspect"] == [paths[photo.position]]
    assert called["describe"] == [paths[size.position]]


if __name__ == "__main__":
    import shutil
    import traceback

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        try:
            test()
            print("OK  ", name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:400])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
