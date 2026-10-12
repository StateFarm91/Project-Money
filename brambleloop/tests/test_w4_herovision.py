"""W4-HEROVISION: parity HERO can now be judged for the disclosed hero (F-253, F-027, F-031).

Before: `visual.parity` HERO read `inspection.semantic.finished_or_in_progress_agrees`, a key
no producer wrote, and the disclosed renders every Launch-0 listing carries were never
described at all. So HERO was unjudged for every product, whatever the vision gate said.
Now:
* `inspect.compare` writes `finished_or_in_progress_agrees` and `identified`;
* `visual.hero_review` describes the usable disclosed hero's exact bytes blind (one budgeted
  call; realism is not applicable to a disclosed render), plus the 230 px grid reading, and
  files them bound to the frame's sha256. It does this only while image_vision is open;
* `disclosed_listing.frames_with_presentation` attaches the review to the hero frame, so
  parity HERO passes, fails or stays unjudged on evidence.
Stub providers only: no network, no spend.

Run: cd brambleloop && PYTHONPATH=src:tests python tests/test_w4_herovision.py
"""
from __future__ import annotations

import _tmp; _tmp.install()  # W3-HYG: per-process temp sandbox, removed at exit
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_TMP = tempfile.mkdtemp(prefix="w4_herovision_")
os.environ["BRAMBLELOOP_ARTIFACT_DIR"] = os.path.join(_TMP, "artifacts")
os.environ["BRAMBLELOOP_PHASE"] = "shadow"
os.environ.pop("ANTHROPIC_API_KEY", None)


def _no_network(*_a, **_k):
    raise OSError("network refused by the W4-HEROVISION harness")


socket.socket.connect = _no_network  # type: ignore[assignment]
socket.create_connection = _no_network  # type: ignore[assignment]

from sqlalchemy import select  # noqa: E402

from brambleloop.agents.registry import Registry  # noqa: E402
from brambleloop.core.db import Database  # noqa: E402
from brambleloop.core.models import AuditLog, Phase  # noqa: E402
from brambleloop.publish import listing_asset  # noqa: E402
from brambleloop.queue.durable import JobQueue  # noqa: E402
from brambleloop.runtime import pipeline, release  # noqa: E402,F401
from brambleloop.runtime.worker import Worker  # noqa: E402
from brambleloop.visual import hero_review, parity  # noqa: E402
from brambleloop.visual import inspect as I  # noqa: E402

SLUG = "hexagon-coaster-set"


def _description(**over):
    base = {"object_shown": "four hexagon coasters", "object_count": 4,
            "finished_or_in_progress": "finished", "human_present": False,
            "text_present": True, "chart_or_diagram": False,
            "dominant_colours": "cream, wine", "clarity": "clear",
            "third_party_marks": "none"}
    base.update(over)
    return base


class _Provider:
    model = "claude-sonnet-5"
    cost_per_1k_input_cad = 0.003 * 1.37
    cost_per_1k_output_cad = 0.015 * 1.37

    def __init__(self, description=None):
        self.description = description or _description()
        self.calls = 0

    def see(self, system, prompt, images, max_tokens=0):
        self.calls += 1
        payload = json.dumps(self.description)

        class R:
            text = payload
            input_tokens = 1200
            output_tokens = 90
        return R()


_C: dict = {}


def _built():
    """A certified coaster release with its disclosed set, built with the vision gate closed."""
    if "db" not in _C:
        db = Database(f"sqlite:///{_TMP}/hv.sqlite")
        db.create_all()
        Registry(db).seed_defaults()
        cir = pipeline._engineered_cir(SLUG)
        JobQueue(db).enqueue("quality_director", "gate.certify", {"cir": cir.to_dict()},
                             idempotency_key="cert", priority=0)
        Worker(db, "c", phase=Phase.SHADOW, job_types=["gate.certify"]).run_once()
        JobQueue(db).enqueue("publishing", "assets.build",
                             {"slug": SLUG, "version": cir.version, "release": "",
                              "rebuild": "disclosed"}, idempotency_key="d", priority=0)
        Worker(db, "b", phase=Phase.SHADOW, job_types=["assets.build"]).run_once()
        _C["db"], _C["cir"] = db, cir
    return _C["db"], _C["cir"]


def _hero_verdict(db):
    frames = listing_asset.frames_for(db, slug=SLUG)
    assert frames
    return parity.assess(frames)["dimensions"][parity.HERO]


# ---- the comparison writes what parity reads -----------------------------------------

def test_compare_writes_the_readings_parity_hero_is_defined_on():
    claim = {"shows_finished_object": True, "identifies_as": ["coaster"]}
    ok = I.compare(_description(), claim)
    assert ok["finished_or_in_progress_agrees"] is True and ok["identified"] is True
    wip = I.compare(_description(finished_or_in_progress="in_progress"), claim)
    assert wip["finished_or_in_progress_agrees"] is False
    unclear = I.compare(_description(finished_or_in_progress="unclear"), claim)
    assert unclear["finished_or_in_progress_agrees"] is None
    wrong = I.compare(_description(object_shown="a striped blanket"), claim)
    assert wrong["identified"] is False
    assert I.compare(_description(), {})["finished_or_in_progress_agrees"] is None


def test_parity_hero_needs_the_product_identified_where_it_was_checked():
    def frames(sem):
        return [{"role": "hero", "inspection": {"described": True, "semantic": sem}}]
    assert parity.assess(frames({"finished_or_in_progress_agrees": True,
                                 "identified": True}))["dimensions"]["hero"]["verdict"] == "pass"
    assert parity.assess(frames({"finished_or_in_progress_agrees": True,
                                 "identified": False}))["dimensions"]["hero"]["verdict"] == "fail"
    assert parity.assess(frames({"finished_or_in_progress_agrees": True,
                                 "identified": None}))["dimensions"]["hero"]["verdict"] == "unjudged"
    # a record without the identification key is read exactly as before
    assert parity.assess(frames({"finished_or_in_progress_agrees": True})
                         )["dimensions"]["hero"]["verdict"] == "pass"


# ---- the disclosed hero, end to end --------------------------------------------------

def test_with_the_gate_closed_nothing_is_called_and_hero_stays_unjudged():
    db, _cir = _built()
    with db.session() as s:
        rows = [r.detail for r in s.scalars(select(AuditLog).where(
            AuditLog.action == "assets.disclosed_hero_review"))]
    assert rows and rows[-1]["reviewed"] is False and "closed" in rows[-1]["why"]
    p = _Provider()
    out = hero_review.review_disclosed_hero(db, SLUG, provider=p, gate_open=False)
    assert out["reviewed"] is False and p.calls == 0
    assert _hero_verdict(db)["verdict"] == "unjudged"


def test_a_blind_clear_description_of_the_exact_hero_bytes_passes_parity_hero():
    db, _cir = _built()
    p = _Provider()
    out = hero_review.review_disclosed_hero(db, SLUG, provider=p, gate_open=True)
    assert out["reviewed"] is True and p.calls == 2, (out, p.calls)   # describe + grid
    assert out["families"] == ["coaster"]
    assert out["inspection"]["realism_not_applicable"] is True
    assert out["inspection"]["grid"]["verdict"] == "clear"
    v = _hero_verdict(db)
    assert v["verdict"] == "pass", v


def test_a_misidentified_or_grid_ambiguous_hero_fails_parity_hero():
    db, _cir = _built()
    hero_review.review_disclosed_hero(
        db, SLUG, provider=_Provider(_description(object_shown="a patterned rug")),
        gate_open=True)
    assert _hero_verdict(db)["verdict"] == "fail"
    hero_review.review_disclosed_hero(
        db, SLUG, provider=_Provider(_description(clarity="ambiguous")), gate_open=True)
    assert _hero_verdict(db)["verdict"] == "fail"


def test_a_review_of_other_bytes_is_never_attached():
    db, _cir = _built()
    hero_review.review_disclosed_hero(db, SLUG, provider=_Provider(), gate_open=True)
    frames = listing_asset.frames_for(db, slug=SLUG)
    hero = next(f for f in frames if f.get("role") == "hero")
    assert hero.get("inspection"), "the review of these bytes is attached"
    assert hero_review.latest_for(db, SLUG, "0" * 64) is None
    assert hero_review.latest_for(db, SLUG, "") is None


if __name__ == "__main__":
    import time

    failures = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    assert tests
    for name, test in tests:
        started = time.time()
        try:
            test()
            print("OK  ", name, f"{time.time() - started:.1f}s")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            traceback.print_exc()
            print("FAIL", name, type(exc).__name__, str(exc)[:500])
    print(f"{len(tests) - failures}/{len(tests)} passing")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(bool(failures))
