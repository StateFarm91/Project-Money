"""Whether the photographic-realism standard can be met at all.

Two live renders in a row were blocked on `skin_looks_real`, `processing_is_restrained`
and `not_sterile_perfection`, and the second plainly had pores, freckles and fine lines in
it. At that point there are two possibilities needing opposite fixes: the renders really
are unphotographic, or the judge cannot pass a photograph.

This system has found "a floor nothing can clear" four times, so the flattering assumption
is the one not to make. The control is a real photograph -- used as a control and nothing
else: not copied, not re-hosted, not imitated, and never described.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from brambleloop.core.db import Database  # noqa: E402
from brambleloop.visual import photoreal  # noqa: E402


def _db() -> Database:
    db = Database("sqlite://")
    db.create_all()
    return db


class _Judge:
    """A provider that answers however the test needs, and records what it was shown."""

    model = "test-model"
    cost_per_1k_input_cad = 0.0
    cost_per_1k_output_cad = 0.0

    def __init__(self, **answers):
        self.answers = {k: True for k in photoreal.CHECKS}
        self.answers.update(answers)
        self.shown: list[str] = []

    def see(self, system, prompt, images, max_tokens=0):
        import json as _json
        self.shown.extend(images)
        payload = _json.dumps({**self.answers, "notes": ""})

        class R:
            text = payload
            input_tokens = output_tokens = 0
        return R()


def test_a_judge_that_clears_a_photograph_says_the_standard_is_reachable():
    judge = _Judge()
    out = photoreal.calibrate(_db(), image_url="https://example.invalid/photo.jpg",
                              provider=judge)
    assert out["verdict"] == "clear"
    assert out["reachable"] is True
    assert "needs changing" in out["what_it_means"]
    assert judge.shown == ["https://example.invalid/photo.jpg"]


def test_a_judge_that_blocks_a_photograph_is_the_thing_that_is_wrong():
    """The answer that must not be quietly discarded.

    If a real camera's output fails this standard, then tightening the render against it
    is chasing something nothing can meet -- and every render blocked by it has been
    blocked by a measurement rather than by a defect.
    """
    out = photoreal.calibrate(
        _db(), image_url="https://example.invalid/photo.jpg",
        provider=_Judge(skin_looks_real=False, not_sterile_perfection=False))
    assert out["verdict"] == "blocked"
    assert out["reachable"] is False
    assert out["failed"] == ["not_sterile_perfection", "skin_looks_real"]
    assert "not 'reads as generated'" in out["what_it_means"]


def test_the_calibration_says_what_the_control_is_and_what_it_is_not():
    """Competitor research is for intelligence. The photograph is a control, not a source."""
    out = photoreal.calibrate(_db(), image_url="https://example.invalid/photo.jpg",
                              provider=_Judge())
    for promise in ("not copied", "re-hosted", "never described"):
        assert promise in out["control_is"], promise


def test_no_observed_photograph_means_no_control_rather_than_a_substitute():
    """A generated image used as the control would calibrate the judge against itself."""
    assert photoreal.control_image(_db()) == ""


def test_a_control_is_read_from_the_observed_benchmark():
    from brambleloop.core.models import BenchmarkListing
    from brambleloop.intel import benchmarks

    db = _db()
    with db.session() as s:
        s.add(BenchmarkListing(
            benchmark_key=benchmarks.MJS_KEY, listing_ref="1", title="t",
            detail={"image_urls": ["https://i.etsystatic.com/example.jpg"]}))
    assert photoreal.control_image(db) == "https://i.etsystatic.com/example.jpg"


def test_a_calibration_belongs_to_the_checks_it_was_made_against():
    """A tightened judge that reads an older calibration back as current is never re-checked."""
    from brambleloop.agents.registry import Registry
    from brambleloop.runtime.release import photoreal_calibration

    db = _db()
    Registry(db).audit("creative_director", photoreal.CALIBRATION_ACTION,
                       detail={"checks_version": "v0-an-earlier-standard",
                               "reachable": True})
    assert photoreal_calibration(db) is None

    Registry(db).audit("creative_director", photoreal.CALIBRATION_ACTION,
                       detail={"checks_version": photoreal.CHECKS_VERSION,
                               "reachable": True})
    assert photoreal_calibration(db)["reachable"] is True


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("OK  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    sys.exit(1 if fails else 0)
